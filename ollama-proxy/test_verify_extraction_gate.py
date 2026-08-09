import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from verify_extraction_gate import RUNTIME_OPTIONS, _contract_hashes, verify


MODEL = "local-extraction-model"
MODEL_DIGEST = "a" * 64


def fixture_document():
    return {"extraction": [{"id": "one"}, {"id": "two"}]}


def valid_report(fixture_path: Path):
    digest = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    rows = [
        {
            "id": fixture_id, "schema_pass": True, "stage_a_schema_pass": True,
            "stage_b_schema_pass": True, "connectivity": True, "stage_b_coverage": True,
            "placeholder_preserved": True, "alias_ok": True, "critical_recall": 1.0,
            "stage_a_critical_recall": 1.0, "stage_b_op_alias_accuracy": 1.0,
            "unexpected": 0, "stage_a_unexpected": 0, "failure_codes": [],
            "stage_b_decision_schema_sha256": "b" * 64,
        }
        for fixture_id in ("one", "two")
    ]
    return {
        "config": {
            "mode": "extraction", "model": MODEL, "allow_cloud": False, "think": False,
            "model_digest": MODEL_DIGEST,
            **RUNTIME_OPTIONS,
            "stage_a_contract": "conversation-v2b", "stage_b_contract": "decision-v2.1",
            "reproducibility": {"fixture_sha256": digest, **_contract_hashes()},
        },
        "results": {"extraction": {
            "status": "measured", "gate_pass": True, "model": MODEL, "runs": 1,
            "stage_a_contract": "conversation-v2b", "stage_b_contract": "decision-v2.1",
            "fixture_ids": ["one", "two"], "fixtures": rows,
            "schema_pass_rate": 1.0, "stage_a_schema_pass_rate": 1.0,
            "stage_b_schema_pass_rate": 1.0, "connectivity_rate": 1.0,
            "stage_b_coverage_rate": 1.0, "critical_recall": 1.0,
            "placeholder_rate": 1.0, "stage_b_op_alias_accuracy": 1.0,
            "unexpected": 0, "stage_a_unexpected": 0, "failure_code_counts": {},
        }},
    }


class ExtractionGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.fixtures = self.directory / "fixtures.json"
        self.report = self.directory / "report.json"
        self.fixtures.write_text(json.dumps(fixture_document()), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def check(self, mutate=None):
        report = valid_report(self.fixtures)
        if mutate:
            mutate(report)
        self.report.write_text(json.dumps(report), encoding="utf-8")
        return verify(self.report, self.fixtures, MODEL, MODEL_DIGEST)

    def test_valid_synthetic_report_and_cli(self):
        self.assertIsNone(self.check())
        command = [sys.executable, str(Path(__file__).with_name("verify_extraction_gate.py")),
                   "--report", str(self.report), "--fixtures", str(self.fixtures), "--model", MODEL,
                   "--model-digest", MODEL_DIGEST]
        # Write after check so the CLI sees the valid report.
        self.report.write_text(json.dumps(valid_report(self.fixtures)), encoding="utf-8")
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout.strip(), "extraction gate verified")
        self.assertEqual(completed.stderr, "")

    def test_gate_false_and_model_and_hash_mismatch(self):
        self.assertEqual(self.check(lambda r: r["results"]["extraction"].update(gate_pass=False)), "GATE_NOT_PASSED")
        self.assertEqual(self.check(lambda r: r["config"].update(model="other")), "CONFIG_MODEL_MISMATCH")
        self.assertEqual(self.check(lambda r: r["config"]["reproducibility"].update(fixture_sha256="0" * 64)), "FIXTURE_HASH_MISMATCH")
        self.assertEqual(self.check(lambda r: r["config"].update(model_digest="not-a-digest")), "MODEL_DIGEST_INVALID")
        self.report.write_text(json.dumps(valid_report(self.fixtures)), encoding="utf-8")
        self.assertEqual(verify(self.report, self.fixtures, MODEL, "b" * 64), "MODEL_DIGEST_MISMATCH")

    def test_fixture_coverage_unknown_duplicate_and_runs_bool(self):
        self.assertEqual(self.check(lambda r: r["results"]["extraction"].update(fixture_ids=["one"])), "FIXTURE_ID_COVERAGE_MISMATCH")
        self.assertEqual(self.check(lambda r: r["results"]["extraction"]["fixtures"].append({"id": "unknown"})), "UNKNOWN_RESULT_FIXTURE")
        self.assertEqual(
            self.check(lambda r: r["results"]["extraction"]["fixtures"].append(
                dict(r["results"]["extraction"]["fixtures"][0])
            )),
            "FIXTURE_RUN_COUNT_MISMATCH",
        )
        self.assertEqual(self.check(lambda r: r["results"]["extraction"].update(runs=True)), "RUNS_INVALID")

    def test_contract_mismatch_and_allow_cloud(self):
        self.assertEqual(self.check(lambda r: r["results"]["extraction"].update(stage_b_contract="old")), "RESULT_STAGE_B_CONTRACT_MISMATCH")
        self.assertEqual(self.check(lambda r: r["config"].update(allow_cloud=True)), "CLOUD_NOT_DISABLED")

    def test_thinking_must_be_exact_boolean_false(self):
        self.assertEqual(self.check(lambda r: r["config"].pop("think")), "THINK_NOT_DISABLED")
        self.assertEqual(self.check(lambda r: r["config"].update(think=True)), "THINK_NOT_DISABLED")
        self.assertEqual(self.check(lambda r: r["config"].update(think=0)), "THINK_NOT_DISABLED")
        self.assertIsNone(self.check(lambda r: r["config"].update(think=False)))

    def test_runtime_options_reject_value_or_bool_bypass(self):
        self.assertEqual(self.check(lambda r: r["config"].update(seed=0)), "RUNTIME_OPTIONS_MISMATCH")
        self.assertEqual(self.check(lambda r: r["config"].update(temperature=False)), "RUNTIME_OPTIONS_MISMATCH")
        self.assertEqual(self.check(lambda r: r["config"].update(num_ctx=True)), "RUNTIME_OPTIONS_MISMATCH")

    def test_contract_hash_mismatch(self):
        self.assertEqual(
            self.check(lambda r: r["config"]["reproducibility"].update(stage_a_schema_sha256="0" * 64)),
            "CONTRACT_HASH_MISMATCH",
        )
        self.assertEqual(
            self.check(lambda r: r["config"]["reproducibility"].pop("stage_b_decision_factory_probe_sha256")),
            "CONTRACT_HASH_MISMATCH",
        )

    def test_rejects_tampered_aggregate_or_fixture_result(self):
        self.assertEqual(
            self.check(lambda r: r["results"]["extraction"].update(schema_pass_rate=0.5)),
            "GATE_METRICS_INVALID",
        )
        self.assertEqual(
            self.check(lambda r: r["results"]["extraction"]["fixtures"][0].update(connectivity=False)),
            "FIXTURE_RESULT_FAILED",
        )
        self.assertEqual(
            self.check(lambda r: r["results"]["extraction"]["fixtures"][0].pop("stage_b_decision_schema_sha256")),
            "FIXTURE_RESULT_FAILED",
        )

    def test_cli_failure_does_not_leak_report_content(self):
        secret = "DO_NOT_LEAK_THIS_REPORT_CONTENT"
        report = valid_report(self.fixtures)
        report["private"] = secret
        report["results"]["extraction"]["gate_pass"] = False
        self.report.write_text(json.dumps(report), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("verify_extraction_gate.py")), "--report", str(self.report),
             "--fixtures", str(self.fixtures), "--model", MODEL, "--model-digest", MODEL_DIGEST], text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stderr.strip(), "EXTRACTION_GATE_GATE_NOT_PASSED")
        self.assertNotIn(secret, completed.stdout + completed.stderr)

    def test_launcher_places_guard_before_proxy_start(self):
        launcher = Path(__file__).with_name("start-local-ollama-proxy.ps1").read_text(encoding="utf-8")
        self.assertIn("MemoryExtractionGateReport", launcher)
        self.assertIn("Resolve-LocalOllamaModelDigest", launcher)
        self.assertIn("--model-digest $memoryExtractionModelDigest", launcher)
        self.assertIn("[switch]$VerifyExtractionGateOnly", launcher)
        self.assertLess(launcher.index("if ($VerifyExtractionGateOnly)"), launcher.index("$listener = Get-NetTCPConnection"))
        self.assertIn("Existing proxy cannot be reused for memory extraction.", launcher)
        self.assertIn("AIRI_MEMORY_EXTRACTION_NUM_CTX = '8192'", launcher)
        self.assertIn("[string]$OllamaKeepAlive = '30m'", launcher)
        self.assertIn("AIRI_CHARACTER_EVALUATOR_NUM_GPU = $NumGpu.ToString", launcher)
        self.assertIn("AIRI_CHARACTER_EVALUATOR_KEEP_ALIVE = $OllamaKeepAlive", launcher)
        self.assertIn("AIRI_CHARACTER_EVALUATOR_IDLE_DELAY_SECONDS = '6'", launcher)
        self.assertIn("AIRI_OLLAMA_KEEP_ALIVE = $OllamaKeepAlive", launcher)
        self.assertLess(launcher.index("verify_extraction_gate.py"), launcher.index("Start-Process"))

    def test_root_launcher_gates_proxy_before_extractor(self):
        root_launcher = Path(__file__).parent.parent / "start-airi-local-stack.ps1"
        launcher = root_launcher.read_text(encoding="utf-8")
        self.assertIn("MemoryExtractionGateReport", launcher)
        self.assertIn("-MemoryExtractionGateReport $MemoryExtractionGateReport", launcher)
        gate_only = launcher.index("-VerifyExtractionGateOnly")
        extractor_start = launcher.index("start-memory-extractor.ps1")
        gate_proxy_start = launcher.rfind("start-local-ollama-proxy.ps1", 0, gate_only)
        normal_proxy_start = launcher.index("start-local-ollama-proxy.ps1", extractor_start)
        self.assertLess(gate_proxy_start, gate_only)
        self.assertLess(gate_only, extractor_start)
        self.assertLess(extractor_start, normal_proxy_start)
        self.assertLess(launcher.index("Existing proxy must be restarted"), gate_proxy_start)
        self.assertIn("-ExpectedDigest $liveDigest", launcher)
        self.assertLess(launcher.index("Local model digest changed after gate verification"), extractor_start)
        self.assertIn("$extractorResult.StartedByCaller -eq $true", launcher)
        self.assertIn("-ExpectedPid ([int]$extractorResult.Pid)", launcher)
        self.assertIn("stop-memory-extractor.ps1", launcher)
        self.assertIn("function Resolve-LocalOllamaModelDigest", launcher)
        self.assertIn("$value.LastIndexOf('/')", launcher)
        self.assertLess(launcher.index("function Resolve-LocalOllamaModelDigest"), launcher.index("Resolve-LocalOllamaModelDigest -Model"))
        self.assertIn("[string]$OllamaKeepAlive = '30m'", launcher)
        self.assertIn("-OllamaKeepAlive $OllamaKeepAlive", launcher)
        self.assertIn("keep_alive = $OllamaKeepAlive", launcher)

    def test_extractor_launcher_requires_verified_model_digest(self):
        launcher = Path(__file__).with_name("start-memory-extractor.ps1").read_text(encoding="utf-8")
        self.assertIn("[string]$Model", launcher)
        self.assertIn("[string]$ExpectedDigest", launcher)
        self.assertIn("Get-VerifiedOllamaModelDigest", launcher)
        self.assertIn("$value.LastIndexOf('/')", launcher)
        self.assertIn("ModelVerified = $true", launcher)
        self.assertIn("StartedByCaller = $false", launcher)
        self.assertIn("StartedByCaller = $true", launcher)
        self.assertIn("Started memory extractor ownership could not be verified.", launcher)
        self.assertIn("Stop-Process -Id $process.Id -Force", launcher)

    def test_extractor_stop_launcher_guards_expected_pid(self):
        launcher = Path(__file__).with_name("stop-memory-extractor.ps1").read_text(encoding="utf-8")
        self.assertIn("[int]$ExpectedPid = 0", launcher)
        self.assertIn("$processIds.Count -ne 1", launcher)
        self.assertIn("$ExpectedPid -ne 0", launcher)


if __name__ == "__main__":
    unittest.main()
