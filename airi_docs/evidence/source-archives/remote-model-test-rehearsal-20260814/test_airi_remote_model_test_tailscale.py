"""Offline contract tests for the fail-closed Tailscale Serve wrappers."""

from pathlib import Path
import json
import re
import unittest


ROOT = Path(__file__).resolve().parent
ENABLE = (ROOT / 'enable-airi-remote-model-test-tailscale.ps1').read_text(encoding='utf-8')
DISABLE = (ROOT / 'disable-airi-remote-model-test-tailscale.ps1').read_text(encoding='utf-8')


class TailscaleServeWrapperTests(unittest.TestCase):
    def test_enable_requires_local_token_authenticated_gateway(self) -> None:
        self.assertIn('[Parameter(Mandatory = $true)]', ENABLE)
        self.assertIn('Resolve-Path -LiteralPath $TokenFile', ENABLE)
        self.assertIn('Get-Content -LiteralPath $resolvedTokenFile -Raw', ENABLE)
        self.assertIn("$gatewayTarget = 'http://127.0.0.1:11439'", ENABLE)
        self.assertIn('"$gatewayTarget/v1/models"', ENABLE)
        self.assertIn('Authorization = "Bearer $token"', ENABLE)

    def test_enable_requires_installed_logged_in_tailscale(self) -> None:
        self.assertIn("Join-Path ${env:ProgramFiles} 'Tailscale\\tailscale.exe'", ENABLE)
        self.assertIn('Get-Command tailscale -CommandType Application -ErrorAction Stop', ENABLE)
        self.assertIn("@('version')", ENABLE)
        self.assertIn("@('status', '--json')", ENABLE)
        self.assertIn("$node.BackendState -cne 'Running'", ENABLE)
        self.assertIn('$node.Self.DNSName', ENABLE)

    def test_cli_absence_and_login_failures_are_fail_closed(self) -> None:
        # These are intentionally static: no system Tailscale binary or login is
        # needed to prove that either prerequisite reaches the generic failure path.
        cli_lookup = ENABLE.index('Get-Command tailscale -CommandType Application -ErrorAction Stop')
        catch = ENABLE.index('} catch {', cli_lookup)
        self.assertLess(cli_lookup, catch)
        self.assertIn("if ($node.BackendState -cne 'Running')", ENABLE)
        self.assertIn("throw 'Tailscale is not logged in and running.'", ENABLE)
        self.assertIn('exit 1', ENABLE[catch:])

    def test_enable_is_scoped_https_serve_and_verifies_exact_loopback_target(self) -> None:
        self.assertIn("@('serve', '--bg', '--https=11439', $gatewayTarget)", ENABLE)
        self.assertIn("@('serve', 'status', '--json')", ENABLE)
        self.assertIn("$handler.Proxy -ceq $gatewayTarget", ENABLE)
        self.assertIn("$tcp.PSObject.Properties[$script:servePort]", ENABLE)
        self.assertIn("$site = $web.PSObject.Properties[$serveHostName].Value", ENABLE)
        self.assertIsNone(re.search(r'(?im)^\s*\$host\s*=', ENABLE + DISABLE))
        self.assertIn('Test-NoFunnelOrPublicServe', ENABLE)
        self.assertIn("$property.Value -ne $false", ENABLE)
        self.assertIn('Tailscale HTTPS 11439 is already configured; refusing to replace it.', ENABLE)
        self.assertIn('Get-ServeWithoutRemotePort', ENABLE)
        self.assertIn('Test-StructuralEqual', ENABLE)
        self.assertIn('Existing Tailscale Serve rules changed; refusing to report success.', ENABLE)

    def test_other_existing_https_ports_are_preserved_by_json_comparison(self) -> None:
        # The wrapper strips only its 11439 entries before comparing snapshots;
        # HTTPS 11435/8880/8890 and any future unrelated listener stay present.
        self.assertIn('$tcp.PSObject.Properties.Remove($script:servePort)', ENABLE)
        self.assertIn('if ($property.Name -like "*:$script:servePort")', ENABLE)
        self.assertIn('ConvertTo-CanonicalJson', ENABLE)
        self.assertIn('Sort-Object Name', ENABLE)
        self.assertIn('Test-StructuralEqual -Left $beforeOtherRules', ENABLE)
        self.assertIn('Test-StructuralEqual -Left $beforeOtherRules', DISABLE)

    def test_expected_existing_mapping_is_idempotent_success(self) -> None:
        self.assertIn('if (Test-ExpectedRemoteServeStatus -Status $before -DnsName $dnsName)', ENABLE)
        self.assertIn('An exact pre-existing mapping is an idempotent success.', ENABLE)
        self.assertIn('exit 0', ENABLE)

    def test_current_status_shape_preserves_rules_despite_property_reordering(self) -> None:
        before = {
            'TCP': {'11435': {'HTTPS': True}, '8880': {'HTTPS': True}, '8890': {'HTTPS': True}},
            'Web': {'node.example.ts.net:11435': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:11435'}}}},
            'Funnel': False,
        }
        after = {
            'Funnel': False,
            'Web': {'node.example.ts.net:11439': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:11439'}}},
                    'node.example.ts.net:11435': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:11435'}}}},
            'TCP': {'11439': {'HTTPS': True}, '8890': {'HTTPS': True}, '8880': {'HTTPS': True}, '11435': {'HTTPS': True}},
        }

        def without_remote_port(status: dict) -> dict:
            copy = json.loads(json.dumps(status))
            copy['TCP'].pop('11439', None)
            for key in list(copy['Web']):
                if key.endswith(':11439'):
                    copy['Web'].pop(key)
            return copy

        self.assertEqual(
            json.dumps(without_remote_port(before), sort_keys=True, separators=(',', ':')),
            json.dumps(without_remote_port(after), sort_keys=True, separators=(',', ':')),
        )
        self.assertIn("$property.Value -ne $false", ENABLE)

    def test_token_is_never_written_or_included_in_errors(self) -> None:
        self.assertNotIn('Write-Output $token', ENABLE)
        self.assertNotIn('Write-Host $token', ENABLE)
        self.assertNotIn('Write-Error $token', ENABLE)
        self.assertNotIn('$_.Exception.ToString()', ENABLE)
        self.assertIn('Write-Output $resolvedTokenFile', ENABLE)

    def test_never_uses_funnel_or_raw_model_ports(self) -> None:
        combined = ENABLE + DISABLE
        self.assertNotIn("@('funnel'", combined.lower())
        self.assertNotIn(' --funnel', combined.lower())
        for forbidden in ('tailscale up', 'tailscale down', 'tailscale login', 'tailscale install', '11434', '11437', '11888'):
            self.assertNotIn(forbidden, combined.lower())

    def test_disable_only_removes_11439_and_preserves_other_listeners(self) -> None:
        self.assertIn("@('serve', '--https=11439', 'off')", DISABLE)
        self.assertIn('Test-RemoteGatewayServeAbsent', DISABLE)
        self.assertIn('Test-ExpectedRemoteGatewayServe', DISABLE)
        self.assertIn('Get-ServeWithoutRemotePort', DISABLE)
        self.assertIn('Existing Tailscale Serve rules changed; refusing to report success.', DISABLE)
        self.assertNotIn("@('serve', 'reset')", DISABLE)
        self.assertNotIn("@('down')", DISABLE)
        self.assertNotIn("@('uninstall')", DISABLE)


if __name__ == '__main__':
    unittest.main()
