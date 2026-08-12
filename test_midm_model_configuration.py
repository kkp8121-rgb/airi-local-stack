import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parent
STACK = (ROOT / "start-airi-local-stack.ps1").read_text(encoding="utf-8")
PROXY = (ROOT / "ollama-proxy" / "start-local-ollama-proxy.ps1").read_text(encoding="utf-8")
SETUP = (ROOT / "ollama-proxy" / "setup-midm-airi-model.ps1").read_text(encoding="utf-8")
MODELFILE = (ROOT / "ollama-proxy" / "Modelfile.midm-airi").read_text(encoding="utf-8")
STT_STOP = (ROOT / "stt" / "stop-local-stt.ps1").read_text(encoding="utf-8")


class MidmModelConfigurationTests(unittest.TestCase):
    def test_output_moderation_launcher_contract_is_validated_and_forwarded(self) -> None:
        for script in (STACK, PROXY):
            self.assertIn("[ValidateSet('on', 'off')]", script)
            self.assertIn("[string]$OutputModerationTerms = $env:AIRI_OUTPUT_MODERATION_TERMS", script)
            self.assertIn("throw 'OutputModerationTerms must be a regular file.'", script)
            self.assertIn("[IO.Path]::GetFullPath($termsItem.FullName)", script)
        self.assertEqual(STACK.count("-OutputModeration $OutputModeration"), 3)
        self.assertEqual(STACK.count("-OutputModerationTerms $resolvedOutputModerationTerms"), 3)
        self.assertIn("AIRI_OUTPUT_MODERATION = $OutputModeration", PROXY)
        self.assertIn("AIRI_OUTPUT_MODERATION_TERMS = $resolvedOutputModerationTerms", PROXY)

    def test_existing_proxy_moderation_reuse_fails_closed(self) -> None:
        self.assertIn("Existing proxy cannot be reused with OutputModerationTerms", PROXY)
        self.assertIn("Existing proxy output moderation state could not be verified", PROXY)
        self.assertIn("Existing proxy health does not report output moderation state.", PROXY)
        self.assertIn("$existingHealth.output_moderation.enabled", PROXY)
        self.assertIn("$existingModerationEnabled -ne $requestedModerationEnabled", PROXY)
        self.assertIn("OutputModerationEnabled = $proxy.output_moderation.enabled", STACK)
        self.assertIn("OutputModerationReady = $proxy.output_moderation.ready", STACK)

    def test_local_midm_default_uses_the_verified_digest_without_affecting_rollbacks_or_external_chat(self) -> None:
        verified_digest = "92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f"
        self.assertIn(verified_digest, STACK)
        self.assertIn("$ChatProvider -eq 'local' -and $effectiveChatModel -ceq 'midm-airi:2.0-mini'", STACK)
        self.assertIn("[string]::IsNullOrWhiteSpace($ChatModelDigest)", STACK)

        # Mirrors the launcher resolution: parameter/environment values win;
        # only the standard local Mi:dm tag acquires the verified default.
        def resolved_digest(provider: str, model: str, supplied_digest: str) -> str:
            effective_model = "midm-airi:2.0-mini" if provider == "local" and not model else model
            if provider == "local" and effective_model == "midm-airi:2.0-mini" and not supplied_digest.strip():
                return verified_digest
            return supplied_digest

        self.assertEqual(resolved_digest("local", "", ""), verified_digest)
        self.assertEqual(resolved_digest("local", "midm-airi:2.0-mini", ""), verified_digest)
        self.assertEqual(resolved_digest("local", "", "environment-or-parameter-pin"), "environment-or-parameter-pin")
        self.assertEqual(resolved_digest("local", "exaone-airi:2.4b", ""), "")
        self.assertEqual(resolved_digest("openai", "gpt-4.1-mini", ""), "")

    def test_midm_runtime_tag_and_local_source_are_pinned(self) -> None:
        self.assertIn("'midm-airi:2.0-mini'", STACK)
        self.assertIn("'midm-airi:2.0-mini'", PROXY)
        self.assertEqual(
            MODELFILE.splitlines()[0],
            "FROM hf.co/DevQuasar/K-intelligence.Midm-2.0-Mini-Instruct-GGUF:Q4_K_M",
        )
        self.assertIn("TEMPLATE \"\"\"{{ if .System }}", MODELFILE)
        self.assertIn("{{ .System }}<|eot_id|>", MODELFILE)
        self.assertIn("PARAMETER num_ctx 2048", MODELFILE)
        self.assertIn("PARAMETER num_gpu 999", MODELFILE)
        self.assertNotIn("Mi:dm은", MODELFILE)
        self.assertNotIn("경어체", MODELFILE)

    def test_selected_chat_model_reaches_proxy_warmup_and_runtime_display(self) -> None:
        self.assertIn("-ChatModel $effectiveChatModel", STACK)
        self.assertIn("model = $effectiveChatModel", STACK)
        self.assertIn("ChatModel = $effectiveChatModel", STACK)
        self.assertIn("AIRI_CHAT_MODEL = $effectiveChatModel", PROXY)
        self.assertIn("AIRI_CHARACTER_EVALUATOR_MODEL = $effectiveEvaluatorModel", PROXY)
        self.assertIn("chat=$ChatProvider/$effectiveChatModel", PROXY)

    def test_character_evaluator_is_opt_in_and_uses_a_preflighted_local_model(self) -> None:
        self.assertIn("[bool]$EnableCharacterEvaluator = $false", STACK)
        self.assertIn("[bool]$EnableCharacterEvaluator = $false", PROXY)
        for script in (STACK, PROXY):
            self.assertIn("$effectiveEvaluatorModel = if ($ChatProvider -eq 'local')", script)
            self.assertIn("if ($EnableCharacterEvaluator)", script)
            self.assertIn("$requiredLocalModels += $effectiveEvaluatorModel", script)
            self.assertIn("$requiredLocalModels | Sort-Object -Unique", script)

    def test_model_selection_contracts_cover_default_rollback_and_external_evaluator(self) -> None:
        # local/no override -> Mi:dm; local/override -> requested rollback tag;
        # external chat + evaluator -> locally preflighted Mi:dm evaluator.
        def selected_models(provider: str, chat_model: str, evaluator: bool) -> list[str]:
            effective_chat = "midm-airi:2.0-mini" if provider == "local" and not chat_model else chat_model
            effective_evaluator = effective_chat if provider == "local" else "midm-airi:2.0-mini"
            required = []
            if provider == "local":
                required.append(effective_chat)
            if evaluator:
                required.append(effective_evaluator)
            return sorted(set(required))

        self.assertEqual(selected_models("local", "", False), ["midm-airi:2.0-mini"])
        self.assertEqual(selected_models("local", "exaone-airi:2.4b", True), ["exaone-airi:2.4b"])
        self.assertEqual(selected_models("openai", "gpt-4.1-mini", True), ["midm-airi:2.0-mini"])
        self.assertEqual(selected_models("anthropic", "", False), [])

    def test_normal_startup_only_preflights_local_models_and_never_pulls(self) -> None:
        self.assertIn("-Model $model -PreflightOnly", STACK)
        self.assertIn("-Model $model -PreflightOnly", PROXY)
        self.assertEqual(STACK.count("-ChatModelPreflighted"), 3)
        self.assertIn("if (-not $ChatModelPreflighted)", PROXY)
        self.assertIn("if (-not $VerifyExtractionGateOnly)", PROXY)
        self.assertIn("normal startup never pulls models", SETUP)
        self.assertNotIn(" pull ", SETUP.lower())
        self.assertIn("& $ollama.Source create $DefaultModel -f $Modelfile", SETUP)
        self.assertIn("[switch]$Recreate", SETUP)
        self.assertIn("Required local Mi:dm source model", SETUP)

    def test_launcher_labels_evaluation_records_with_the_selected_model(self) -> None:
        # Without this the proxy would fall back to its own default and an
        # evaluation of the selected model could be filed under another name.
        self.assertIn("AIRI_EVAL_MODEL = $effectiveChatModel", PROXY)

    def test_model_digest_pin_reaches_preflight_and_the_running_proxy(self) -> None:
        for script in (STACK, PROXY):
            self.assertIn("[string]$ChatModelDigest = $env:AIRI_CHAT_MODEL_DIGEST", script)
            self.assertIn(
                "$expectedDigest = if ($model -ceq $effectiveChatModel) "
                "{ $ChatModelDigest } else { '' }",
                script,
            )
            self.assertIn("-Model $model -PreflightOnly -ExpectedDigest $expectedDigest", script)
        self.assertIn("AIRI_CHAT_MODEL_DIGEST = $ChatModelDigest", PROXY)
        # Preflight fails closed on a mismatch and otherwise records the digest
        # it observed, so a locally rebuilt tag cannot pass unnoticed.
        self.assertIn("[string]$ExpectedDigest = ''", SETUP)
        self.assertIn("'^[0-9a-f]{64}$'", SETUP)
        self.assertIn("does not match the expected artifact digest", SETUP)
        self.assertIn("$digests = Get-LocalOllamaModelDigests", SETUP)
        self.assertNotIn("Get-LocalOllamaModelNames", SETUP)

    def test_every_proxy_start_forwards_the_digest_pin(self) -> None:
        # A gate-only invocation verifies memory extraction and returns before
        # any chat traffic; every invocation that actually starts the proxy
        # must carry the selected model and its optional artifact pin.
        commands = re.findall(
            r"start-local-ollama-proxy\.ps1'\)(?:[^\n]*`\r?\n)*[^\n]*", STACK
        )
        starting = [command for command in commands if "-VerifyExtractionGateOnly" not in command]
        self.assertGreaterEqual(len(starting), 2)
        self.assertLess(len(starting), len(commands))
        for command in starting:
            self.assertIn("-ChatModel $effectiveChatModel", command)
            self.assertIn("-ChatModelDigest $ChatModelDigest", command)

    def test_proxy_health_is_a_fail_fast_gate_before_gpu_speech_services(self) -> None:
        proxy_ready = STACK.rindex(
            "$proxy = Wait-LocalHealth -Uri 'http://127.0.0.1:11435/health'"
        )
        tts_start = STACK.index("'gpt-sovits\\start-local-stack.ps1'")
        stt_start = STACK.index("'stt\\start-local-stt.ps1'")
        self.assertLess(proxy_ready, tts_start)
        self.assertLess(proxy_ready, stt_start)

    def test_stt_defaults_off_and_honors_a_nonblank_environment_override(self) -> None:
        self.assertIn("[ValidateSet('on', 'off')]", STACK)
        self.assertIn("[string]$Stt = $(if ([string]::IsNullOrWhiteSpace($env:AIRI_STT)) { 'off' } else { $env:AIRI_STT })", STACK)
        validation = "if ($Stt -notin @('on', 'off')) {"
        self.assertIn(validation, STACK)
        self.assertIn("throw 'Stt must be on or off. Check the -Stt parameter or AIRI_STT environment variable.'", STACK)
        self.assertIn("$Stt = $Stt.ToLowerInvariant()", STACK)
        self.assertLess(STACK.index(validation), STACK.index("$resolvedOutputModerationTerms = ''"))
        self.assertIn("[string]$SttModel = 'mobiuslabsgmbh/faster-whisper-large-v3-turbo'", STACK)
        self.assertIn("[string]$SttComputeType = 'int8_float16'", STACK)

    def test_stt_start_and_health_wait_are_conditional_on_opt_in_mode(self) -> None:
        start = "& (Join-Path $PSScriptRoot 'stt\\start-local-stt.ps1') `"
        self.assertIn("if ($Stt -eq 'on') {\n    " + start, STACK)
        self.assertIn("-Model $SttModel", STACK)
        self.assertIn("-ComputeType $SttComputeType", STACK)
        self.assertIn("$sttHealth = if ($Stt -eq 'on') {\n    Wait-LocalHealth -Uri 'http://127.0.0.1:8890/health'", STACK)
        stt_assignments = [line.strip() for line in re.findall(r"(?im)^\s*\$stt\s*=.*$", STACK)]
        self.assertEqual(stt_assignments, ["$Stt = $Stt.ToLowerInvariant()"])

    def test_stt_off_stops_only_matching_server_signature_and_fails_closed_for_remaining_listener(self) -> None:
        stop = "& (Join-Path $PSScriptRoot 'stt\\stop-local-stt.ps1')"
        self.assertIn("if ($Stt -eq 'off') {", STACK)
        self.assertIn(stop, STACK)
        self.assertIn(
            "Get-NetTCPConnection -LocalPort 8890 -State Listen",
            STACK,
        )
        self.assertIn("throw 'STT is disabled, but a listener remains on local port 8890. Refusing to continue.'", STACK)
        self.assertNotIn("Stop-Process", STACK[STACK.index(stop):STACK.index("'gpt-sovits\\start-local-stack.ps1'")])
        self.assertLess(STACK.index(stop), STACK.index("$ollamaListener = Get-NetTCPConnection"))
        self.assertLess(STACK.index(stop), STACK.index("'gpt-sovits\\start-local-stack.ps1'"))
        for signature in (
            "$pythonExecutablePattern",
            "$serverTokenPattern",
            "$hostTokenPattern",
            "$portTokenPattern",
            "[IO.Path]::GetFileName($_.ExecutablePath)",
        ):
            self.assertIn(signature, STT_STOP)
        self.assertNotIn("Get-NetTCPConnection", STT_STOP)

    def test_stt_summary_is_unambiguous_when_disabled(self) -> None:
        self.assertIn("STTMode = $Stt", STACK)
        self.assertIn("STT = if ($Stt -eq 'on') { $sttHealth.status } else { 'disabled' }", STACK)
        self.assertIn("STTModel = if ($Stt -eq 'on') { $sttHealth.model } else { '' }", STACK)
        self.assertIn("STTDevice = if ($Stt -eq 'on') { $sttHealth.device } else { '' }", STACK)


if __name__ == "__main__":
    unittest.main()
