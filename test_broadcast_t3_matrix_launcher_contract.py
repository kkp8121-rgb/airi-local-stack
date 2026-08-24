"""Offline fail-closed launcher preflight tests; no service is started."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / 'run-airi-broadcast-t3-matrix.ps1'


class LauncherHarness:
    """Shared offline fixtures for both matrix profiles."""

    def manifest(self, shuffled=False, duplicate=False):
        arms = [
            {'name': 'baseline', 'tag': 'base:one', 'digest': 'a' * 64},
            {'name': 'e1', 'tag': 'e1:one', 'digest': 'b' * 64},
            {'name': 'e2', 'tag': 'e2:one', 'digest': 'c' * 64},
        ]
        if duplicate:
            arms[2]['tag'] = arms[1]['tag']
        if shuffled:
            arms = [arms[1], arms[2], arms[0]]
        return {'schema_version': 'airi.broadcast-sim-t3-model-manifest.v2', 'arms': arms}

    def tags(self):
        return {'models': [{'name': 'base:one', 'digest': 'a' * 64},
                           {'model': 'e1:one', 'digest': 'b' * 64},
                           {'name': 'e2:one', 'digest': 'c' * 64}]}

    def health(self):
        return {
            'status': 'ok', 'num_ctx': 2048, 'immediate_ack': 'marker',
            'broadcast_contract': True,
            'chat_model': {'provider': 'local', 'model': 'base:one', 'enforced': True,
                           'digest': {'status': 'pinned', 'verified': True, 'digest': 'a' * 64}},
            'chat_provider': {'external_approved': False, 'configured': True, 'ready': False},
            'memory': {'enabled': True, 'ready': True},
            'knowledge': {'enabled': True, 'ready': True, 'documents': 0, 'chunks': 0,
                          'accepted_chunks': 0},
            'input_screening': {'enabled': True, 'ready': True},
            'output_moderation': {'enabled': True, 'ready': True},
            'epistemic_confidence': {'enabled': True, 'mode': 'enforce'},
            'affect_continuity': {'enabled': True, 'ready': True},
            'show_arc': {'enabled': True, 'ready': True, 'evaluation_clock': True},
            'broadcast_affect': {'enabled': True, 'ready': True, 'evaluation_clock': True},
        }

    def report(self):
        return {
            'schema_version': 'airi.broadcast-sim-report.v1',
            'model': 'base:one', 'memory_arm': 'seeded', 'contract': 'on',
            'protocol': 'operational', 'author_format': 'runtime', 'history_turns': 8,
            'briefing': 'on', 'briefing_evidence': 'on', 'acts': 'on',
            'live_broadcast_context': 'on', 'live_contract_verified': True, 'seed': 11,
            'fixture_sha256': '0d558c0ce3e019569673ed96f4f171e3464e1e044028e7de6b7ede9d5b8085d6',
            'summary': {'transport_failures': 0, 'turns': 1},
            'rows': [{'live_broadcast_context': True, 'live_receipt_bound': True,
                      'live_action_id': 'action-1', 'live_trace_id': 'trace-1',
                      'turn_index': 7, 'failure': None}],
        }

    def stream_plan(self):
        return {
            'schema_version': 'airi.broadcast-sim-report.v1', 'mode': 'stream_only', 'seed': 11,
            'fixture_sha256': '0d558c0ce3e019569673ed96f4f171e3464e1e044028e7de6b7ede9d5b8085d6',
            'picks': [{'turn_index': 7}],
        }

    def blind_manifest(self, legacy_arms=False):
        if legacy_arms:
            return self.manifest()
        arms = [
            {'name': 'baseline', 'tag': 'base:one', 'digest': 'a' * 64},
            {'name': 'e2', 'tag': 'e2:one', 'digest': 'b' * 64},
            {'name': 'e2-c1', 'tag': 'e2c1:one', 'digest': 'c' * 64},
        ]
        return {'schema_version': 'airi.broadcast-sim-t3-model-manifest.v2', 'arms': arms}

    def blind_tags(self):
        return {'models': [{'name': 'base:one', 'digest': 'a' * 64},
                           {'name': 'e2:one', 'digest': 'b' * 64},
                           {'name': 'e2c1:one', 'digest': 'c' * 64}]}

    def invoke(self, directory, manifest, tags, *extra):
        model, tag_file, out = directory/'models.json', directory/'tags.json', directory/'out'
        model.write_text(json.dumps(manifest), encoding='utf-8')
        tag_file.write_text(json.dumps(tags), encoding='utf-8')
        command = ['powershell', '-NoProfile', '-File', str(SCRIPT), '-OutputDir', str(out),
                   '-ModelManifest', str(model), '-FixtureManifest', str(ROOT/'ollama-proxy/eval/broadcast_sim/t3_fixture_manifest_v2.json'),
                   '-OllamaTagsFile', str(tag_file), *extra]
        return subprocess.run(command, cwd=ROOT, text=True, capture_output=True), out


class T3LauncherContract(LauncherHarness, unittest.TestCase):
    def test_invalid_arms_fail_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            result, out = self.invoke(Path(temp), {'schema_version': 'airi.broadcast-sim-t3-model-manifest.v2', 'arms': self.manifest()['arms'][:2]}, self.tags(), '-PreflightOnly')
            self.assertNotEqual(result.returncode, 0); self.assertFalse(out.exists())

    def test_missing_e2_fails_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            result, out = self.invoke(Path(temp), self.manifest(), {'models': self.tags()['models'][:2]}, '-PreflightOnly')
            self.assertNotEqual(result.returncode, 0); self.assertFalse(out.exists())

    def test_shuffled_manifest_returns_canonical_matrix(self):
        with tempfile.TemporaryDirectory() as temp:
            result, out = self.invoke(Path(temp), self.manifest(True), self.tags(), '-PreflightOnly')
            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads(result.stdout)
            self.assertEqual((plan['runs'], plan['arms']), (36, ['baseline', 'e1', 'e2']))
            self.assertEqual(plan['seed_sets'][2], [44, 55, 66, 20260822])
            self.assertEqual(len(plan['run_keys']), 36); self.assertEqual(len(set(plan['run_keys'])), 36)
            self.assertIn('baseline-3-44', plan['run_keys']); self.assertIn('e2-3-20260822', plan['run_keys'])
            self.assertEqual(plan['comparisons'], ['baseline-vs-e1', 'baseline-vs-e2'])
            self.assertFalse(out.exists())

    def test_tags_file_without_preflight_rejects_before_output(self):
        with tempfile.TemporaryDirectory() as temp:
            result, out = self.invoke(Path(temp), self.manifest(), self.tags())
            self.assertNotEqual(result.returncode, 0); self.assertFalse(out.exists())

    def test_existing_output_is_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); out = path/'out'; out.mkdir(); (out/'keep').write_text('x')
            result, _ = self.invoke(path, self.manifest(), self.tags(), '-PreflightOnly')
            self.assertNotEqual(result.returncode, 0); self.assertEqual((out/'keep').read_text(), 'x')

    def test_duplicate_model_and_bad_fixture_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            result, out = self.invoke(Path(temp), self.manifest(duplicate=True), self.tags(), '-PreflightOnly')
            self.assertNotEqual(result.returncode, 0); self.assertFalse(out.exists())
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); fixture = path/'bad.json'; fixture.write_text('{}', encoding='utf-8')
            result, out = self.invoke(path, self.manifest(), self.tags(), '-PreflightOnly', '-FixtureManifest', str(fixture))
            self.assertNotEqual(result.returncode, 0); self.assertFalse(out.exists())

    def test_script_ast_and_python_compile(self):
        ast = subprocess.run(['powershell', '-NoProfile', '-Command', "[void][scriptblock]::Create((Get-Content -Raw './run-airi-broadcast-t3-matrix.ps1'))"], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(ast.returncode, 0, ast.stderr)
        compiled = subprocess.run(['python', '-m', 'py_compile', str(Path(__file__))], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        source = SCRIPT.read_text(encoding='utf-8')
        for required in ('-memory-arm seeded', '-max-tokens 220', '-timeout 180',
                         '-briefing-evidence on', '-live-broadcast-context on',
                         '-OllamaNumGpu 999', '-AllowExternalMemoryExtraction $false',
                         '-OutputModeration on', '-EpistemicConfidence on',
                         '-AffectContinuity on', 'compare_broadcast_t3.py',
                         "$env:AIRI_GPT_SOVITS_SV_CACHE = 'on'",
                         "$env:GPT_SOVITS_STREAMING_MODE = '2'",
                         "$env:GPT_SOVITS_MIN_CHUNK_LENGTH = '16'",
                         'Assert-TtsHealth', 'Test-ExactBoolean',
                         'Get-OwnedPortKey', "ProcessId = $ownerProcessId",
                         'Stop-Process -Id $ownerProcessId -Force -PassThru',
                         'WaitForExit(10000)',
                         "foreach ($key in $plannedKeys)",
                         "foreach ($dbName in @('memory.sqlite3','knowledge.sqlite3'))",
                         "foreach ($candidateName in @('e1','e2'))",
                         'Restore-Env GPT_SOVITS_REFERENCE_AUDIO',
                         'Restore-Env NLTK_DATA', 'Restore-Env PYTHONPATH',
                         'Restore-Env PYTHONIOENCODING',
                         'report_evidence=$reportEvidence', 'packet_evidence=$packetEvidence',
                         'run_contract_evidence=$contractEvidence',
                         'comparison_evidence=$comparisonEvidence',
                         'runtime_evidence=$runtimeEvidence'):
            self.assertIn(required, source)

    def test_health_and_report_fixtures_accept_valid_and_reject_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); health = path/'health.json'; report = path/'report.json'; plan = path/'plan.json'
            health.write_text(json.dumps(self.health()), encoding='utf-8')
            report.write_text(json.dumps(self.report()), encoding='utf-8')
            plan.write_text(json.dumps(self.stream_plan()), encoding='utf-8')
            result, out = self.invoke(
                path, self.manifest(), self.tags(), '-PreflightOnly',
                '-HealthFixtureFile', str(health), '-ReportFixtureFile', str(report),
                '-ReportPlanFixtureFile', str(plan),
            )
            self.assertEqual(result.returncode, 0, result.stderr); self.assertFalse(out.exists())

            broken_health = self.health(); broken_health['chat_model']['digest']['status'] = 'observed'
            health.write_text(json.dumps(broken_health), encoding='utf-8')
            result, _ = self.invoke(
                path, self.manifest(), self.tags(), '-PreflightOnly', '-HealthFixtureFile', str(health),
            )
            self.assertNotEqual(result.returncode, 0)

            numeric_boolean = self.health(); numeric_boolean['memory']['ready'] = 1
            health.write_text(json.dumps(numeric_boolean), encoding='utf-8')
            result, _ = self.invoke(
                path, self.manifest(), self.tags(), '-PreflightOnly', '-HealthFixtureFile', str(health),
            )
            self.assertNotEqual(result.returncode, 0)

            string_integer = self.health(); string_integer['num_ctx'] = '2048'
            health.write_text(json.dumps(string_integer), encoding='utf-8')
            result, _ = self.invoke(
                path, self.manifest(), self.tags(), '-PreflightOnly', '-HealthFixtureFile', str(health),
            )
            self.assertNotEqual(result.returncode, 0)

            health.write_text(json.dumps(self.health()), encoding='utf-8')
            broken_report = self.report(); broken_report['rows'][0]['live_receipt_bound'] = False
            report.write_text(json.dumps(broken_report), encoding='utf-8')
            result, _ = self.invoke(
                path, self.manifest(), self.tags(), '-PreflightOnly', '-ReportFixtureFile', str(report),
                '-ReportPlanFixtureFile', str(plan),
            )
            self.assertNotEqual(result.returncode, 0)

            broken_report = self.report(); broken_report['schema_version'] = 'airi.broadcast-sim-report.v0'
            report.write_text(json.dumps(broken_report), encoding='utf-8')
            result, _ = self.invoke(
                path, self.manifest(), self.tags(), '-PreflightOnly', '-ReportFixtureFile', str(report),
                '-ReportPlanFixtureFile', str(plan),
            )
            self.assertNotEqual(result.returncode, 0)

            typed_report = self.report(); typed_report['seed'] = '11'
            report.write_text(json.dumps(typed_report), encoding='utf-8')
            result, _ = self.invoke(
                path, self.manifest(), self.tags(), '-PreflightOnly', '-ReportFixtureFile', str(report),
                '-ReportPlanFixtureFile', str(plan),
            )
            self.assertNotEqual(result.returncode, 0)

            typed_report = self.report(); typed_report['live_contract_verified'] = 'true'
            report.write_text(json.dumps(typed_report), encoding='utf-8')
            result, _ = self.invoke(
                path, self.manifest(), self.tags(), '-PreflightOnly', '-ReportFixtureFile', str(report),
                '-ReportPlanFixtureFile', str(plan),
            )
            self.assertNotEqual(result.returncode, 0)

            report.write_text(json.dumps(self.report()), encoding='utf-8')
            typed_plan = self.stream_plan(); typed_plan['picks'][0]['turn_index'] = '7'
            plan.write_text(json.dumps(typed_plan), encoding='utf-8')
            result, _ = self.invoke(
                path, self.manifest(), self.tags(), '-PreflightOnly', '-ReportFixtureFile', str(report),
                '-ReportPlanFixtureFile', str(plan),
            )
            self.assertNotEqual(result.returncode, 0)

            report.write_text(json.dumps(self.report()), encoding='utf-8')
            incomplete = self.stream_plan(); incomplete['picks'].append({'turn_index': 8})
            plan.write_text(json.dumps(incomplete), encoding='utf-8')
            result, _ = self.invoke(
                path, self.manifest(), self.tags(), '-PreflightOnly', '-ReportFixtureFile', str(report),
                '-ReportPlanFixtureFile', str(plan),
            )
            self.assertNotEqual(result.returncode, 0)


class E2C1BlindProfileContract(LauncherHarness, unittest.TestCase):
    """The e2c1 profile is fail-closed offline: its blind bodies live outside the repo."""

    def test_e2c1_requires_blind_root(self):
        with tempfile.TemporaryDirectory() as temp:
            result, out = self.invoke(Path(temp), self.blind_manifest(), self.blind_tags(),
                                      '-PreflightOnly', '-MatrixProfile', 'e2c1')
            self.assertNotEqual(result.returncode, 0); self.assertFalse(out.exists())

    def test_blind_root_is_rejected_by_the_t3_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); blind = path/'blind'; blind.mkdir()
            result, out = self.invoke(path, self.manifest(), self.tags(), '-PreflightOnly',
                                      '-BlindRoot', str(blind))
            self.assertNotEqual(result.returncode, 0); self.assertFalse(out.exists())

    def test_e2c1_rejects_the_t3_arm_set(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); blind = path/'blind'; blind.mkdir()
            result, out = self.invoke(path, self.blind_manifest(legacy_arms=True), self.tags(),
                                      '-PreflightOnly', '-MatrixProfile', 'e2c1',
                                      '-BlindRoot', str(blind))
            self.assertNotEqual(result.returncode, 0); self.assertFalse(out.exists())

    def test_e2c1_fails_closed_on_an_unbound_blind_root(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp); blind = path/'blind'; blind.mkdir()
            (blind/'identity_unknown_and_donation_ritual.json').write_text('{}', encoding='utf-8')
            result, out = self.invoke(path, self.blind_manifest(), self.blind_tags(),
                                      '-PreflightOnly', '-MatrixProfile', 'e2c1',
                                      '-BlindRoot', str(blind))
            self.assertNotEqual(result.returncode, 0); self.assertFalse(out.exists())

    def test_launcher_parses_and_binds_the_frozen_e2c1_inputs(self):
        ast = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "$e=$null;$t=$null;"
             "[void][Management.Automation.Language.Parser]::ParseFile("
             "(Resolve-Path './run-airi-broadcast-t3-matrix.ps1'),[ref]$t,[ref]$e);"
             "if ($e) { $e | ForEach-Object { $_.Message }; exit 1 }"],
            cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(ast.returncode, 0, ast.stdout + ast.stderr)
        source = SCRIPT.read_text(encoding='utf-8')
        for required in ("[ValidateSet('t3','e2c1')] [string]$MatrixProfile = 't3'",
                         '[string]$BlindRoot',
                         "The e2c1 profile requires -BlindRoot.",
                         "@('baseline','e2','e2-c1')",
                         'airi_e2_c1_blind_commitment.json',
                         'airi_e2_c1_metric_policy.json',
                         "airi-e2-c1-blind-freeze-20260824-v2",
                         'ce81bbb59edd473210b0c5b6637a5728827fef3e56e077786f213b52f989c9d4',
                         'compare_e2c1_blind.py', '--reports-dir', '--commitment',
                         '--environment-attestation', '--expected-model-manifest-sha256',
                         "airi.e2-c1-environment-attestation.v1",
                         "airi.e2-c1-blind-comparison.v1",
                         'blind_commitment_sha256=$commitmentSha256'):
            self.assertIn(required, source)

    def test_matrix_profile_is_a_two_value_validate_set(self):
        query = subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             "$e=$null;$t=$null;"
             "$ast=[Management.Automation.Language.Parser]::ParseFile("
             "(Resolve-Path './run-airi-broadcast-t3-matrix.ps1'),[ref]$t,[ref]$e);"
             "$p=$ast.ParamBlock.Parameters | Where-Object { $_.Name.VariablePath.UserPath -ceq "
             "'MatrixProfile' };"
             "($p.Attributes | Where-Object { $_.TypeName.FullName -eq 'ValidateSet' }"
             ").PositionalArguments.Value -join ','"],
            cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(query.returncode, 0, query.stderr)
        self.assertEqual(query.stdout.strip(), 't3,e2c1')


if __name__ == '__main__':
    unittest.main()
