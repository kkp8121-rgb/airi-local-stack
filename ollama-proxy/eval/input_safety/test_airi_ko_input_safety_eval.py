import ast
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location("b3d_runner", HERE / "run_airi_ko_input_safety_eval.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class B3dInputSafetyEvalTests(unittest.TestCase):
    def fixture(self):
        return runner.load_fixture()[0]

    def test_exact_matrix_counts(self):
        cases = self.fixture()["cases"]
        self.assertEqual(len(cases), 120)
        self.assertEqual(sum(c["partition"] == "policy_bound" for c in cases), 70)
        self.assertEqual(sum(c["partition"] == "adversarial_transform" for c in cases), 30)
        self.assertEqual(sum(c["partition"] == "semantic_gap" for c in cases), 20)

    def test_contract_diversity_and_korean_ratio(self):
        cases = self.fixture()["cases"]
        contract = [c for c in cases if c["partition"] != "semantic_gap"]
        self.assertEqual(len({c["text"] for c in contract}), 100)
        self.assertGreaterEqual(sum(any("가" <= x <= "힣" for x in c["text"]) for c in contract), 70)

    def test_language_labels_and_privacy_pattern_coverage(self):
        cases = self.fixture()["cases"]
        languages = {label: sum(c["language"] == label for c in cases) for label in runner.LANGUAGES}
        self.assertEqual(languages["ko"], 80)
        self.assertEqual(languages["fr"], 6)
        self.assertEqual(languages["es"], 1)
        privacy_patterns = {
            c["id"] for c in cases
            if c["partition"] == "policy_bound"
            and c["family"] == "privacy"
            and c["expected_rule"] == "pattern"
        }
        self.assertTrue({"b3d_055", "b3d_056", "b3d_057", "b3d_058", "b3d_059"} <= privacy_patterns)

    def test_hashes_and_canonical_pin(self):
        fixture, raw = runner.load_fixture()
        self.assertEqual(fixture["policy_sha256"], runner.POLICY_SHA256)
        self.assertRegex(runner.CANONICAL_FIXTURE_SHA256, r"^[0-9a-f]{64}$")
        self.assertEqual(hashlib.sha256(raw).hexdigest(), runner.CANONICAL_FIXTURE_SHA256)
        self.assertTrue(all(
            case["text_sha256"] == hashlib.sha256(case["text"].encode()).hexdigest()
            for case in fixture["cases"]
        ))

    def test_all_contract_cases_exact(self):
        report = runner.evaluate()
        self.assertEqual(report["counts"]["contract_total"], 100)
        self.assertEqual(report["counts"]["contract_exact"], 100)
        self.assertEqual(report["policy_contract_gate"], "PASS")

    def test_semantic_is_excluded(self):
        report = runner.evaluate()
        semantic_rows = [c for c in report["cases"] if c["partition"] == "semantic_gap"]
        self.assertEqual(len(semantic_rows), 20)
        self.assertTrue(all(c["exact"] is None for c in semantic_rows))
        self.assertEqual(sum(report["semantic_histogram"].values()), 20)

    def test_extra_and_missing_fields_fail(self):
        fixture = self.fixture()
        fixture["cases"][0]["extra"] = True
        with self.assertRaises(runner.EvalError): runner.validate_fixture(fixture)
        fixture = self.fixture()
        del fixture["cases"][0]["language"]
        with self.assertRaises(runner.EvalError): runner.validate_fixture(fixture)

    def test_type_nfc_control_cf_and_zero_width_matrix(self):
        fixture = self.fixture()
        fixture["schema_version"] = True
        with self.assertRaises(runner.EvalError): runner.validate_fixture(fixture)
        for text, transformation in (("e\u0301", "plain"), ("ok\x01", "plain"), ("a\u200bb", "plain")):
            self.assertFalse(runner._valid_text(text, transformation))
        self.assertTrue(runner._valid_text("a\u200bb", "zero_width"))
        self.assertFalse(runner._valid_text("a\u200bb\u200bc\u200bd", "zero_width"))

    def test_hash_and_duplicate_mutations_fail(self):
        fixture = self.fixture()
        fixture["cases"][0]["text_sha256"] = "0" * 64
        with self.assertRaises(runner.EvalError): runner.validate_fixture(fixture)
        fixture = self.fixture()
        fixture["cases"][1]["text"] = fixture["cases"][0]["text"]
        fixture["cases"][1]["text_sha256"] = fixture["cases"][0]["text_sha256"]
        with self.assertRaises(runner.EvalError): runner.validate_fixture(fixture)

    def test_report_is_content_free(self):
        fixture = self.fixture()
        report = runner.evaluate()
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertTrue(all(c["text"] not in encoded for c in fixture["cases"]))
        self.assertNotIn(str(runner.FIXTURE_PATH), encoded)

    def test_report_schema_and_metrics(self):
        report = runner.evaluate()
        required = {
            "schema_version", "runner_version", "suite_id", "fixture_sha256",
            "evaluator_sha256", "policy_sha256", "counts", "transform_metrics",
            "semantic_histogram", "cases", "policy_contract_gate",
            "semantic_safety_claim", "installed_airi_claim", "runtime_changed",
            "b3d_overall", "operational_gate",
        }
        self.assertEqual(set(report), required)
        self.assertEqual(sum(
            value["exact"] + value.get("mismatch", 0)
            for value in report["transform_metrics"].values()
        ), 30)

    def test_mismatched_contract_cannot_false_pass(self):
        always_allowed = SimpleNamespace(
            inspect=lambda _text: SimpleNamespace(allowed=True, category="", rule=""),
        )
        policy = SimpleNamespace(sha256=runner.POLICY_SHA256)
        with mock.patch.object(runner, "_runtime", return_value=(always_allowed, policy)):
            report = runner.evaluate()
        self.assertLess(report["counts"]["contract_exact"], 100)
        self.assertEqual(report["policy_contract_gate"], "FAIL")
        self.assertEqual(report["b3d_overall"], "FAIL")
        self.assertEqual(report["operational_gate"], "OFF")

    def test_no_network_or_dynamic_imports(self):
        tree = ast.parse((HERE / "run_airi_ko_input_safety_eval.py").read_text(encoding="utf-8"))
        imports = {
            name.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for name in node.names
        }
        self.assertFalse(imports & {"socket", "http", "urllib", "requests", "httpx", "importlib", "ollama_proxy"})

    def test_atomic_write_and_default_cli_no_write(self):
        report = runner.evaluate()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            runner.write_report(report, path)
            first = path.read_bytes()
            runner.write_report(report, path)
            self.assertEqual(first, path.read_bytes())
            self.assertFalse(list(Path(directory).glob(".b3d-*")))
            result = subprocess.run(
                [sys.executable, str(HERE / "run_airi_ko_input_safety_eval.py")],
                cwd=directory,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(list(Path(directory).glob("*.json")), [path])

    def test_fixture_size_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.json"
            path.write_bytes(b"{" + b" " * runner.MAX_FIXTURE_BYTES + b"}")
            with self.assertRaises(runner.EvalError):
                runner.load_fixture(path)

    def test_policy_drift_and_false_pass(self):
        original = runner.POLICY_SHA256
        runner.POLICY_SHA256 = "0" * 64
        try:
            with self.assertRaises(runner.EvalError): runner.load_fixture()
        finally:
            runner.POLICY_SHA256 = original


if __name__ == "__main__":
    unittest.main()
