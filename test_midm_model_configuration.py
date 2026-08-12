import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parent
STACK = (ROOT / "start-airi-local-stack.ps1").read_text(encoding="utf-8")
PROXY = (ROOT / "ollama-proxy" / "start-local-ollama-proxy.ps1").read_text(encoding="utf-8")
SETUP = (ROOT / "ollama-proxy" / "setup-midm-airi-model.ps1").read_text(encoding="utf-8")
MODELFILE = (ROOT / "ollama-proxy" / "Modelfile.midm-airi").read_text(encoding="utf-8")


class MidmModelConfigurationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
