"""Offline static contracts for the isolated remote-model test stack."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
START = (ROOT / 'start-airi-remote-model-test.ps1').read_text(encoding='utf-8')
STOP = (ROOT / 'stop-airi-remote-model-test.ps1').read_text(encoding='utf-8')


class RemoteModelTestStackContracts(unittest.TestCase):
    def test_start_is_loopback_only_and_never_edits_firewall(self) -> None:
        self.assertIn("$MotifPort = 11437", START)
        self.assertIn("$GatewayPort = 11439", START)
        self.assertIn("'--host', '127.0.0.1'", START)
        self.assertNotIn('0.0.0.0', START)
        self.assertNotIn('New-NetFirewallRule', START)
        self.assertNotIn('Set-NetFirewallProfile', START)

    def test_start_requires_pinned_local_inputs_and_midm_digest(self) -> None:
        self.assertIn('[Parameter(Mandatory)]\n    [string]$MotifSnapshot', START)
        self.assertIn('[Parameter(Mandatory)]\n    [string]$MotifPython', START)
        self.assertIn("model-usage-manifests\\motif-2.6b-v1.1-lc.json", START)
        self.assertIn('92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f', START)
        self.assertIn("http://127.0.0.1:11434/api/tags", START)
        self.assertIn('Existing Ollama must listen only on loopback port 11434.', START)
        self.assertIn('Assert-PortIsFree -Port $MotifPort', START)
        self.assertIn('Assert-PortIsFree -Port $GatewayPort', START)
        self.assertIn("/api/show\" -ContentType 'application/json'", START)
        self.assertIn("if (-not $motifReady) { throw 'Pinned Motif backend did not become ready.' }", START)

    def test_secret_and_background_process_contracts_are_explicit(self) -> None:
        self.assertIn("'ai.moeru.airi'", START)
        self.assertIn('[Security.Cryptography.RandomNumberGenerator]::Create()', START)
        self.assertIn('$generator.GetBytes($bytes)', START)
        self.assertIn('$generator.Dispose()', START)
        self.assertIn('$acl.SetAccessRuleProtection($true, $false)', START)
        self.assertIn('$tokenItem.SetAccessControl($acl)', START)
        self.assertNotIn('Set-Acl', START)
        self.assertIn('-WindowStyle Hidden', START)
        self.assertIn('-RedirectStandardOutput $motifOut', START)
        self.assertIn('-RedirectStandardError $gatewayErr', START)
        self.assertNotIn('Write-Output $token', START)
        self.assertIn("/health\" -Headers @{ Authorization = \"Bearer $token\" }", START)

    def test_gateway_receives_all_fixed_upstream_and_digest_arguments(self) -> None:
        for argument in ('--token-file', '--port', '--midm-url', '--motif-url', '--midm-digest', '--motif-digest'):
            self.assertIn("'" + argument + "'", START)
        self.assertIn("'http://127.0.0.1:11434'", START)
        self.assertIn("\"http://127.0.0.1:$MotifPort\"", START)
        self.assertIn('run_airi_remote_model_test_gateway.py', START)
        self.assertIn('2753574351457fd11b22ecd2e3b35ddc28350389843fbe1cc0b427e2b84f6be6', START)

    def test_stop_fails_closed_then_only_stops_verified_owned_processes(self) -> None:
        self.assertIn('Remote model test state is absent; refusing to target any process.', STOP)
        self.assertIn('Get-CimInstance Win32_Process', STOP)
        self.assertIn('does not match its recorded script and port signature', STOP)
        self.assertIn('Remote model test state has unexpected process script paths.', STOP)
        self.assertIn('not associated with the sole loopback listener on port', STOP)
        self.assertIn('not the verified parent of listener', STOP)
        self.assertIn("http://127.0.0.1:11437/api/show", STOP)
        self.assertIn("http://127.0.0.1:11434/api/generate", STOP)
        self.assertLess(STOP.index('api/show'), STOP.index('Stop-Process -Id ([int]$gateway.Listener.ProcessId)'))
        self.assertIn('Stop-Process -Id ([int]$gateway.Listener.ProcessId)', STOP)
        self.assertIn('[IO.File]::Move($StatePath, $retiredState)', STOP)
        self.assertIn('The local token file was preserved', STOP)


if __name__ == '__main__':
    unittest.main()
