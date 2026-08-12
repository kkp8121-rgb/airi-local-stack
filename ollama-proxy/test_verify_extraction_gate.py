import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from verify_extraction_gate import (
    DEFAULT_GATE_PROFILE,
    GATE_PROFILES,
    RUNTIME_OPTIONS,
    _contract_hashes,
    resolve_gate_thresholds,
    verify,
)


MODEL = "local-extraction-model"
MODEL_DIGEST = "a" * 64


def fixture_document():
    return {"extraction": [{"id": "one"}, {"id": "two"}]}


def perfect_row(fixture_id: str, **overrides):
    row = {
        "id": fixture_id, "schema_pass": True, "stage_a_schema_pass": True,
        "stage_b_schema_pass": True, "connectivity": True, "stage_b_coverage": True,
        "placeholder_preserved": True, "alias_ok": True, "critical_recall": 1.0,
        "stage_a_critical_recall": 1.0, "stage_b_op_alias_accuracy": 1.0,
        "unexpected": 0, "stage_a_unexpected": 0, "failure_codes": [],
        "stage_b_decision_schema_sha256": "b" * 64,
    }
    row.update(overrides)
    return row


def report_with_rows(fixture_path: Path, rows, *, profile=None, thresholds=None):
    """Build a report whose aggregates are derived from its own rows."""
    digest = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    total = max(1, len(rows))
    mean = lambda name: sum(float(row[name]) for row in rows) / total
    extraction = {
        "status": "measured", "gate_pass": True, "model": MODEL, "runs": 1,
        "stage_a_contract": "conversation-v2b", "stage_b_contract": "decision-v2.1",
        "fixture_ids": sorted({row["id"] for row in rows}), "fixtures": rows,
        "schema_pass_rate": mean("schema_pass"),
        "stage_a_schema_pass_rate": mean("stage_a_schema_pass"),
        "stage_b_schema_pass_rate": mean("stage_b_schema_pass"),
        "connectivity_rate": mean("connectivity"),
        "stage_b_coverage_rate": mean("stage_b_coverage"),
        "critical_recall": mean("critical_recall"),
        "placeholder_rate": mean("placeholder_preserved"),
        "stage_b_op_alias_accuracy": mean("stage_b_op_alias_accuracy"),
        "unexpected": sum(row["unexpected"] for row in rows),
        "stage_a_unexpected": sum(row["stage_a_unexpected"] for row in rows),
        "failure_code_counts": {},
    }
    if profile is not None:
        extraction["gate_profile"] = profile
    if thresholds is not None:
        extraction["gate_thresholds"] = thresholds
    return {
        "config": {
            "mode": "extraction", "model": MODEL, "allow_cloud": False, "think": False,
            "model_digest": MODEL_DIGEST,
            **RUNTIME_OPTIONS,
            "stage_a_contract": "conversation-v2b", "stage_b_contract": "decision-v2.1",
            "reproducibility": {"fixture_sha256": digest, **_contract_hashes()},
        },
        "results": {"extraction": extraction},
    }


def valid_report(fixture_path: Path):
    return report_with_rows(fixture_path, [perfect_row("one"), perfect_row("two")])


class ExtractionGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.fixtures = self.directory / "fixtures.json"
        self.report = self.directory / "report.json"
        self.fixtures.write_text(json.dumps(fixture_document()), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def check(self, mutate=None, **kwargs):
        report = valid_report(self.fixtures)
        if mutate:
            mutate(report)
        self.report.write_text(json.dumps(report), encoding="utf-8")
        return verify(self.report, self.fixtures, MODEL, MODEL_DIGEST, **kwargs)

    def check_rows(self, rows, **kwargs):
        report = report_with_rows(self.fixtures, rows, **kwargs.pop("report", {}))
        self.report.write_text(json.dumps(report), encoding="utf-8")
        return verify(self.report, self.fixtures, MODEL, MODEL_DIGEST, **kwargs)

    def test_valid_synthetic_report_and_cli(self):
        self.assertIsNone(self.check())
        command = [sys.executable, str(Path(__file__).with_name("verify_extraction_gate.py")),
                   "--report", str(self.report), "--fixtures", str(self.fixtures), "--model", MODEL,
                   "--model-digest", MODEL_DIGEST]
        # Write after check so the CLI sees the valid report.
        self.report.write_text(json.dumps(valid_report(self.fixtures)), encoding="utf-8")
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stdout.strip(), f"extraction gate verified (profile={DEFAULT_GATE_PROFILE})")
        self.assertEqual(completed.stderr, "")

    def test_profile_resolution_precedence_and_overrides(self):
        with patch.dict(os.environ, {}, clear=True):
            name, thresholds = resolve_gate_thresholds()
            self.assertEqual(name, DEFAULT_GATE_PROFILE)
            self.assertEqual(thresholds, GATE_PROFILES[DEFAULT_GATE_PROFILE])
            self.assertEqual(resolve_gate_thresholds("strict")[1], GATE_PROFILES["strict"])
        with patch.dict(os.environ, {"AIRI_MEMORY_EXTRACTION_GATE_PROFILE": "STRICT "}, clear=True):
            self.assertEqual(resolve_gate_thresholds()[0], "strict")
            # An explicit argument still wins over the environment.
            self.assertEqual(resolve_gate_thresholds("balanced")[0], "balanced")
        with patch.dict(os.environ, {
            "AIRI_MEMORY_EXTRACTION_GATE_MIN_CRITICAL_RECALL": "0.5",
            "AIRI_MEMORY_EXTRACTION_GATE_MAX_UNEXPECTED_RATE": "0",
        }, clear=True):
            _name, thresholds = resolve_gate_thresholds("balanced")
            self.assertEqual(thresholds["min_critical_recall"], 0.5)
            self.assertEqual(thresholds["max_unexpected_rate"], 0.0)
            self.assertEqual(thresholds["min_placeholder_rate"], GATE_PROFILES["balanced"]["min_placeholder_rate"])
        for variables in ({"AIRI_MEMORY_EXTRACTION_GATE_PROFILE": "lenient"},
                          {"AIRI_MEMORY_EXTRACTION_GATE_MIN_CRITICAL_RECALL": "many"},
                          {"AIRI_MEMORY_EXTRACTION_GATE_MIN_CRITICAL_RECALL": "1.5"}):
            with patch.dict(os.environ, variables, clear=True):
                with self.assertRaises(ValueError):
                    resolve_gate_thresholds()

    def test_balanced_profile_accepts_bounded_recall_loss_that_strict_rejects(self):
        rows = [perfect_row("one"), perfect_row("two", critical_recall=0.5)]
        self.assertIsNone(self.check_rows(rows, thresholds=GATE_PROFILES["balanced"]))
        self.assertEqual(
            self.check_rows(rows, thresholds=GATE_PROFILES["strict"]), "GATE_METRICS_INVALID")
        # 0.75 clears 0.70; the historical 55.56% measurement still does not.
        below = [perfect_row("one", critical_recall=0.6), perfect_row("two", critical_recall=0.5)]
        self.assertEqual(
            self.check_rows(below, thresholds=GATE_PROFILES["balanced"]), "GATE_METRICS_INVALID")

    def test_balanced_profile_bounds_placeholder_alias_and_hallucination(self):
        balanced = GATE_PROFILES["balanced"]
        # 1/2 placeholder and 1/2 alias accuracy stay below the relaxed floors.
        self.assertEqual(self.check_rows(
            [perfect_row("one"), perfect_row("two", placeholder_preserved=False)],
            thresholds=balanced), "GATE_METRICS_INVALID")
        self.assertEqual(self.check_rows(
            [perfect_row("one"), perfect_row("two", stage_b_op_alias_accuracy=0.0, alias_ok=False)],
            thresholds=balanced), "GATE_METRICS_INVALID")
        # Over-extraction is bounded per row, not per report.
        self.assertEqual(self.check_rows(
            [perfect_row("one"), perfect_row("two", unexpected=1)],
            thresholds=balanced), "GATE_METRICS_INVALID")
        # Stage-A-only accounting keeps the looser bound and is still allowed.
        self.assertIsNone(self.check_rows(
            [perfect_row("one"), perfect_row("two", stage_a_unexpected=1)], thresholds=balanced))

    def test_structural_metrics_are_never_relaxed(self):
        balanced = GATE_PROFILES["balanced"]
        for field in ("schema_pass", "stage_a_schema_pass", "stage_b_schema_pass",
                      "connectivity", "stage_b_coverage"):
            rows = [perfect_row("one"), perfect_row("two", **{field: False})]
            self.assertEqual(self.check_rows(rows, thresholds=balanced), "GATE_METRICS_INVALID", field)

    def test_aggregates_must_be_derived_from_rows(self):
        def inflate(report):
            report["results"]["extraction"]["fixtures"][0]["critical_recall"] = 0.5
        self.assertEqual(self.check(inflate, thresholds=GATE_PROFILES["balanced"]), "AGGREGATE_MISMATCH")

        def hide_hallucination(report):
            report["results"]["extraction"]["fixtures"][0]["stage_a_unexpected"] = 1
        self.assertEqual(
            self.check(hide_hallucination, thresholds=GATE_PROFILES["balanced"]), "AGGREGATE_MISMATCH")

    def test_report_measured_under_a_looser_gate_is_rejected(self):
        looser = dict(GATE_PROFILES["balanced"], min_critical_recall=0.2)
        self.assertEqual(
            self.check_rows([perfect_row("one"), perfect_row("two")],
                            report={"profile": "balanced", "thresholds": looser},
                            thresholds=GATE_PROFILES["balanced"]),
            "GATE_THRESHOLDS_TOO_LENIENT")
        self.assertEqual(
            self.check_rows([perfect_row("one"), perfect_row("two")],
                            report={"profile": "balanced", "thresholds": GATE_PROFILES["balanced"]},
                            thresholds=GATE_PROFILES["strict"]),
            "GATE_THRESHOLDS_TOO_LENIENT")
        # A stricter report under a relaxed operator profile stays acceptable.
        self.assertIsNone(self.check_rows(
            [perfect_row("one"), perfect_row("two")],
            report={"profile": "strict", "thresholds": GATE_PROFILES["strict"]},
            thresholds=GATE_PROFILES["balanced"]))
        self.assertEqual(
            self.check_rows([perfect_row("one")],
                            report={"profile": "balanced", "thresholds": {"unknown": 1.0}},
                            thresholds=GATE_PROFILES["balanced"]),
            "GATE_THRESHOLDS_INVALID")
        self.assertEqual(
            self.check(lambda r: r["results"]["extraction"].update(gate_profile="lenient")),
            "GATE_PROFILE_UNKNOWN")

    def test_cli_profile_selection_and_invalid_profile(self):
        rows = [perfect_row("one"), perfect_row("two", critical_recall=0.5)]
        self.report.write_text(json.dumps(report_with_rows(self.fixtures, rows)), encoding="utf-8")
        command = [sys.executable, str(Path(__file__).with_name("verify_extraction_gate.py")),
                   "--report", str(self.report), "--fixtures", str(self.fixtures), "--model", MODEL,
                   "--model-digest", MODEL_DIGEST]
        balanced = subprocess.run(command + ["--profile", "balanced"], text=True, capture_output=True, check=False)
        self.assertEqual(balanced.returncode, 0)
        strict = subprocess.run(command + ["--profile", "strict"], text=True, capture_output=True, check=False)
        self.assertEqual(strict.returncode, 1)
        self.assertEqual(strict.stderr.strip(), "EXTRACTION_GATE_GATE_METRICS_INVALID")
        environment = dict(os.environ, AIRI_MEMORY_EXTRACTION_GATE_PROFILE="strict")
        from_env = subprocess.run(command, text=True, capture_output=True, check=False, env=environment)
        self.assertEqual(from_env.returncode, 1)
        broken = subprocess.run(command, text=True, capture_output=True, check=False,
                                env=dict(os.environ, AIRI_MEMORY_EXTRACTION_GATE_PROFILE="lenient"))
        self.assertEqual(broken.returncode, 1)
        self.assertEqual(broken.stderr.strip(), "EXTRACTION_GATE_PROFILE_INVALID")

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
        self.assertIn("[string]$MemoryExtractionGateProfile = 'balanced'", launcher)
        self.assertIn("--profile $MemoryExtractionGateProfile", launcher)
        self.assertLess(launcher.index("--profile $MemoryExtractionGateProfile"), launcher.index("Start-Process"))

    def test_root_launcher_auto_enables_extraction_fail_open(self):
        launcher = (Path(__file__).parent.parent / "start-airi-local-stack.ps1").read_text(encoding="utf-8")
        self.assertIn("[bool]$EnableMemoryExtraction = $true", launcher)
        self.assertIn("[string]$MemoryExtractionGateProfile = 'balanced'", launcher)
        self.assertIn("-MemoryExtractionGateProfile $MemoryExtractionGateProfile", launcher)
        # The gate report names the model, so activation cannot drift from it.
        self.assertIn("$autoModel = [string]$autoReport.config.model", launcher)
        # Every auto-enable precondition degrades to the OFF path with a warning.
        for warning in ("Memory extraction stays off: no extraction gate report at",
                        "Memory extraction stays off: a proxy already listens on 11435.",
                        "Memory extraction stays off: the extraction gate report does not name a model.",
                        "Memory extraction stays off: the extraction gate report did not verify."):
            self.assertIn(warning, launcher)
        auto_block = launcher.index("$memoryExtractionAutoEnabled = $false")
        self.assertLess(launcher.index("Existing proxy must be restarted"), auto_block)
        self.assertLess(auto_block, launcher.index("start-memory-extractor.ps1"))
        # An explicit model keeps the original fail-closed path untouched.
        self.assertIn("[string]::IsNullOrWhiteSpace($MemoryExtractionModel) `", launcher)

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
