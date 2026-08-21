"""Offline contracts for fail-closed local stack activation.

These tests intentionally inspect launcher text: starting or stopping a local
Ollama process is not a deterministic CI operation.
"""
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parent
PROXY = (ROOT / "ollama-proxy" / "ollama_proxy.py").read_text(encoding="utf-8")
PROXY_START = (ROOT / "ollama-proxy" / "start-local-ollama-proxy.ps1").read_text(encoding="utf-8")
STACK_START = (ROOT / "start-airi-local-stack.ps1").read_text(encoding="utf-8")
STACK_STOP = (ROOT / "stop-airi-local-stack.ps1").read_text(encoding="utf-8")


class StackActivationContractTests(unittest.TestCase):
    def test_health_exposes_content_free_safety_booleans(self) -> None:
        health = PROXY[PROXY.index('async def health()'):PROXY.index('\ndef transform_body')]
        self.assertIn('"broadcast_contract": broadcast_contract_enabled()', health)
        self.assertIn('"memory_claim_guard": MEMORY_CLAIM_GUARD_ENABLED', health)
        self.assertNotIn('MEMORY_CLAIM_GUARD_FALLBACK', health)

    def test_reused_proxy_checks_each_important_configuration_category(self) -> None:
        reuse = PROXY_START[PROXY_START.index('if ($listener) {'):PROXY_START.index('$memoryEnvironment = @')]
        self.assertIn('Existing proxy cannot be reused with LiveBroadcast', reuse)
        for token in (
            'chat provider or model differs', 'chat model digest differs',
            'memory state differs', 'knowledge state differs',
            'external search approval', 'broadcast_contract',
            'memory_claim_guard', 'immediate acknowledgement state',
            'num_gpu differs', 'num_ctx differs',
        ):
            with self.subTest(token=token):
                self.assertIn(token, reuse)
        self.assertIn('knowledge is ready but has no indexed documents', reuse)

    def test_live_broadcast_is_explicit_opt_in_with_child_only_token_and_fail_closed_reuse(self) -> None:
        self.assertIn('[switch]$LiveBroadcast', PROXY_START)
        self.assertIn('[switch]$LiveBroadcastEvalClock', PROXY_START)
        self.assertIn('LiveBroadcast requires InputScreening on.', PROXY_START)
        self.assertIn('LiveBroadcastEvalClock requires LiveBroadcast.', PROXY_START)
        self.assertIn("$LiveBroadcastMasterToken -notmatch '^[A-Za-z0-9_-]{32,128}$'", PROXY_START)
        self.assertIn("$LiveBroadcastObserverToken -notmatch '^[A-Za-z0-9_-]{32,128}$'", PROXY_START)
        self.assertIn("AIRI_LIVE_BROADCAST_ENABLED = if ($LiveBroadcast) { 'on' } else { 'off' }", PROXY_START)
        self.assertIn('AIRI_LIVE_BROADCAST_MASTER_TOKEN = if ($LiveBroadcast)', PROXY_START)
        self.assertIn('AIRI_LIVE_BROADCAST_OBSERVER_TOKEN = if ($LiveBroadcast)', PROXY_START)
        self.assertIn("AIRI_LIVE_BROADCAST_MASTER_TOKEN = if ($LiveBroadcast) { $LiveBroadcastMasterToken } else { '' }", PROXY_START)
        self.assertIn("AIRI_LIVE_BROADCAST_OBSERVER_TOKEN = if ($LiveBroadcast) { $LiveBroadcastObserverToken } else { '' }", PROXY_START)
        self.assertIn("AIRI_LIVE_BROADCAST_EVAL_CLOCK = if ($LiveBroadcastEvalClock) { 'on' } else { 'off' }", PROXY_START)
        reuse = PROXY_START[PROXY_START.index('if ($listener) {'):PROXY_START.index('$memoryEnvironment = @')]
        for token in ('show_arc', 'broadcast_affect', 'Existing proxy live broadcast state differs'):
            with self.subTest(token=token):
                self.assertIn(token, reuse)
        self.assertIn('function New-AiriLiveBroadcastMasterToken', STACK_START)
        self.assertIn('[Security.Cryptography.RandomNumberGenerator]::Create()', STACK_START)
        self.assertIn('[string]$LiveBroadcastMasterTokenOverride', STACK_START)
        self.assertIn('[string]$LiveBroadcastObserverTokenOverride', STACK_START)
        self.assertIn('Live broadcast token overrides must be supplied together.', STACK_START)
        self.assertIn('$LiveBroadcastMasterTokenOverride', STACK_START)
        self.assertIn('$LiveBroadcastObserverTokenOverride', STACK_START)
        self.assertGreaterEqual(STACK_START.count('New-AiriLiveBroadcastMasterToken'), 3)
        self.assertIn("$liveBroadcastObserverToken -notmatch '^[A-Za-z0-9_-]{32,128}$'", STACK_START)
        self.assertIn('$liveBroadcastMasterToken -ceq $liveBroadcastObserverToken', STACK_START)
        self.assertIn('-LiveBroadcastMasterToken $liveBroadcastMasterToken', STACK_START)
        self.assertIn('-LiveBroadcastObserverToken $liveBroadcastObserverToken', STACK_START)
        self.assertNotIn('LiveBroadcastMasterToken = $env:', STACK_START)
        self.assertNotIn('LiveBroadcastObserverToken = $env:', STACK_START)
        self.assertNotIn('Write-Output $liveBroadcastMasterToken', STACK_START)
        self.assertNotIn('Write-Output $liveBroadcastObserverToken', STACK_START)
        self.assertIn('LiveBroadcast requires InputScreening on.', STACK_START)
        self.assertIn('[switch]$LiveBroadcastEvalClock', STACK_START)
        self.assertIn('LiveBroadcastEvalClock requires LiveBroadcast.', STACK_START)
        self.assertEqual(STACK_START.count('-LiveBroadcastEvalClock:$LiveBroadcastEvalClock'), 2)

    def test_root_launcher_confirms_live_broadcast_health_state(self) -> None:
        for token in (
            'Live proxy show arc enabled', 'Live proxy show arc ready',
            'Live proxy broadcast affect enabled', 'Live proxy broadcast affect ready',
            'Live proxy broadcast evaluation clock',
            'Live proxy broadcast state is missing, unready, or differs',
        ):
            with self.subTest(token=token):
                self.assertIn(token, STACK_START)

    def test_root_launcher_refuses_unready_requested_memory_and_knowledge(self) -> None:
        self.assertIn("-EnableMemory $EnableMemory", STACK_START)
        self.assertEqual(STACK_START.count('-MemoryDbPath $MemoryDbPath'), 2)
        self.assertEqual(STACK_START.count('-KnowledgeDbPath $KnowledgeDbPath'), 2)
        self.assertIn('AIRI_MEMORY_DB = $resolvedMemoryDbPath', PROXY_START)
        self.assertIn('AIRI_KNOWLEDGE_DB = $resolvedKnowledgeDbPath', PROXY_START)
        self.assertIn('AIRI_KNOWLEDGE_RUNTIME_DIR = $knowledgeDbParent', PROXY_START)
        self.assertIn('MemoryDbPath must use the .sqlite3 extension.', PROXY_START)
        self.assertIn('AIRI_KNOWLEDGE_RUNTIME_DIR', PROXY)
        self.assertIn("Live proxy memory state is missing, unready, or differs", STACK_START)
        self.assertIn("Live proxy knowledge state is missing, unready, or differs", STACK_START)

    def test_owner_record_is_only_written_for_new_extractor_and_cleanup_removes_it(self) -> None:
        self.assertIn('if ($extractorResult.StartedByCaller -eq $true)', STACK_START)
        self.assertIn('Write-MemoryExtractorOwnerRecord', STACK_START)
        self.assertIn('Remove-MemoryExtractorOwnerRecord', STACK_START)
        self.assertIn("memory-extractor-owner.json", STACK_START)
        self.assertIn('Move-Item -LiteralPath $temporary -Destination $extractorOwnerPath -Force', STACK_START)
        self.assertIn('Write-MemoryExtractorOwnerRecord -Port $MemoryExtractionPort -OwnerPid', STACK_START)

    def test_write_memory_extractor_owner_record_actually_executes(self) -> None:
        # Regression guard for F1: `param([int]$Port, [int]$Pid)` crashed at call
        # time with "Cannot overwrite variable Pid" because $Pid is PowerShell's
        # read-only automatic current-process-id variable. A string-presence
        # check alone let that regression through, so actually invoke the
        # extracted function body via pwsh/powershell here.
        pwsh = shutil.which('pwsh') or shutil.which('powershell')
        if not pwsh:
            self.skipTest('pwsh/powershell is not available on this runner')
        start = STACK_START.index('function Write-MemoryExtractorOwnerRecord {')
        end = STACK_START.index('function Remove-MemoryExtractorOwnerRecord {')
        function_source = STACK_START[start:end]
        with tempfile.TemporaryDirectory() as runtime_dir:
            runtime_path = pathlib.Path(runtime_dir)
            owner_path = runtime_path / 'memory-extractor-owner.json'
            script = (
                f"$extractorRuntimeDir = '{runtime_path}'\n"
                f"$extractorOwnerPath = '{owner_path}'\n"
                + function_source
                + "\nWrite-MemoryExtractorOwnerRecord -Port 4321 -OwnerPid 9876\n"
            )
            script_path = runtime_path / 'invoke-write-owner-record.ps1'
            script_path.write_text(script, encoding='utf-8')
            completed = subprocess.run(
                [pwsh, '-NoProfile', '-NonInteractive', '-File', str(script_path)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotIn('Cannot overwrite variable', completed.stderr)
            record = json.loads(owner_path.read_text(encoding='utf-8'))
            self.assertEqual(record, {'port': 4321, 'pid': 9876})

    def test_stop_uses_owner_pid_only_and_retains_stale_record(self) -> None:
        self.assertIn('-ExpectedPid $ownerPid', STACK_STOP)
        self.assertIn('Memory extractor owner record was retained', STACK_STOP)
        self.assertNotIn('Get-NetTCPConnection -LocalPort 11436', STACK_STOP)
        self.assertIn('Remove-Item -LiteralPath $extractorOwnerPath', STACK_STOP)


if __name__ == '__main__':
    unittest.main()
