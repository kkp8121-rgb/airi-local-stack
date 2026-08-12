import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SPEC = importlib.util.spec_from_file_location("context_gate", Path(__file__).with_name("run_airi_context_gate.py"))
gate = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(gate)

def args(**changes):
    value = dict(endpoint="http://127.0.0.1:11434/api/chat", allow_host=False, model="synthetic", num_ctx=2048, num_gpu=999, temperature=0, seed=42, runs=3, max_retries=1, timeout=1, num_predict=128)
    value.update(changes); return argparse.Namespace(**value)

class ContextGateTests(unittest.TestCase):
    def setUp(self): self.fixture = gate.load_fixture(); self.system, self.contract = gate.source_literals()
    def test_fixture_validation(self):
        self.assertEqual(4, len(self.fixture["pressure_levels"])); self.assertTrue(gate.validate_fixture(self.fixture))
        broken = dict(self.fixture); broken["synthetic_only"] = False
        with self.assertRaises(gate.EvalError): gate.validate_fixture(broken)
    def test_loopback_and_argument_bounds(self):
        self.assertEqual("127.0.0.1", gate.ensure_local_endpoint(args().endpoint).hostname)
        self.assertEqual("::1", gate.ensure_local_endpoint("http://[::1]:11434/api/chat").hostname)
        with self.assertRaises(gate.EvalError): gate.ensure_local_endpoint("http://localhost:11434/api/chat")
        self.assertEqual("localhost", gate.ensure_local_endpoint("http://localhost:11434/api/chat", allow_host=True).hostname)
        with self.assertRaises(gate.EvalError): gate.ensure_local_endpoint("http://127.0.0.1:99999/api/chat")
        with self.assertRaises(gate.EvalError): gate.ensure_local_endpoint("http://example.invalid/api/chat")
        with self.assertRaises(gate.EvalError): gate.ensure_local_endpoint("http://192.0.2.1/api/chat")
        with self.assertRaises(gate.EvalError): gate.validate_args(args(runs=6))
        with self.assertRaises(gate.EvalError): gate.validate_args(args(num_ctx=512))
        with self.assertRaises(gate.EvalError): gate.validate_args(args(temperature=float("nan")))
        with self.assertRaises(gate.EvalError): gate.validate_args(args(temperature=2.1))
        with self.assertRaises(gate.EvalError): gate.validate_args(args(timeout=float("inf")))
    def test_ordering_and_pressure(self):
        messages = gate.build_messages(self.system, self.contract, self.fixture, 2)
        self.assertEqual("system", messages[0]["role"]); self.assertIn("[활성 캐릭터 설정]", messages[0]["content"])
        self.assertEqual(self.fixture["canaries"]["early_user"], messages[1]["content"]); self.assertEqual("assistant", messages[2]["role"])
        self.assertEqual("user", messages[-4]["role"]); self.assertEqual("user", messages[-3]["role"]); self.assertEqual("system", messages[-2]["role"]); self.assertIn("[Character Memory]", messages[-2]["content"]); self.assertEqual("user", messages[-1]["role"])
        self.assertGreater(len(gate.build_messages(self.system, self.contract, self.fixture, 48)), 100)
    def test_exact_scoring_detects_speaker_and_negation_failures(self):
        expected = self.fixture["expected"]; good = dict(expected); self.assertTrue(gate.score(good, expected)["passed"])
        score = gate.score(dict(good, early_assistant=good["early_user"]), expected); self.assertFalse(score["speaker_preserved"])
        score = gate.score(dict(good, latest_correction="red-comet", early_user_negated=False), expected); self.assertFalse(score["negation_preserved"]); self.assertIn("latest_correction", score["failures"])
    def test_retry_only_invalid_and_accounting(self):
        response = {"done":True,"message":{"content":json.dumps(self.fixture["expected"])},"prompt_eval_count":9,"eval_count":6}
        calls = [gate.TransportError("offline"), response]
        def fake(*_):
            item = calls.pop(0)
            if isinstance(item, Exception): raise item
            return item
        result = gate.run_one("x", {}, args(), self.fixture["expected"], fake)
        self.assertTrue(result["complete"]); self.assertTrue(result["retry_used"]); self.assertEqual(2, len(result["attempts"]))
        semantic = dict(self.fixture["expected"], active_card="wrong")
        result = gate.run_one("x", {}, args(), self.fixture["expected"], lambda *_: {"done":True,"message":{"content":json.dumps(semantic)}})
        self.assertEqual(1, len(result["attempts"])); self.assertFalse(result["result"]["score"]["passed"])
    def test_aggregate_incomplete_and_percentiles(self):
        good = {"complete":True,"first_pass_valid":True,"retry_used":False,"result":{"score":{"passed":True},"metrics":{"eval_count":4,"total_duration":12}}}; bad = {"complete":False,"first_pass_valid":False,"retry_used":True}
        summary = gate.aggregate([good, bad]); self.assertFalse(summary["complete"]); self.assertEqual("FAIL", summary["gate"]); self.assertEqual(.5, summary["retry_rate"]); self.assertEqual(4, summary["p50"]["eval_count"])
    def test_schema_and_atomic_incomplete_report(self):
        with self.assertRaises(gate.SchemaError): gate.valid_response({"done":True,"message":{"content":"{}"}})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"; gate.atomic_write(output, {"complete":False}); self.assertFalse(json.loads(output.read_text())["complete"])
    def test_safe_metadata_requires_exact_tag_and_digest(self):
        digest = "A" * 64
        safe = gate.safe_model_metadata(
            {"models":[{"name":"model:tag","digest":digest},{"name":"other:tag","digest":"B"*64}]},
            {"details":{"family":"synthetic"},"modelfile":"do not copy"},
            "model:tag",
        )
        self.assertEqual(digest.lower(), safe["digest"])
        self.assertNotIn("modelfile", safe)
        with self.assertRaises(gate.EvalError):
            gate.safe_model_metadata({"models":[{"name":"model:tag","digest":"short"}]}, {}, "model:tag")
        with self.assertRaises(gate.EvalError):
            gate.safe_model_metadata({"models":[]}, {}, "model:tag")
    def test_allow_host_propagates_to_metadata_validation(self):
        runtime = {"timeout":1}
        with mock.patch.object(gate, "ensure_local_endpoint", side_effect=gate.EvalError("blocked")) as guarded:
            with self.assertRaises(gate.EvalError): gate.metadata("http://example.invalid/api/chat", "model:tag", runtime, True)
        guarded.assert_called_once_with("http://example.invalid/api/chat", True)

if __name__ == "__main__": unittest.main()
