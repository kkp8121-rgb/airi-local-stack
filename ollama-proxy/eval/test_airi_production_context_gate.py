import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("production_context_gate", Path(__file__).with_name("run_airi_production_context_gate.py"))
gate = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(gate)

def args(**changes):
    values = dict(endpoint="http://127.0.0.1:11434/api/chat", allow_host=False, model="synthetic", runs=3, num_ctx=2048, num_gpu=999, temperature=0, seed=42, num_predict=64, keep_alive="5m", timeout=1, output="unused", fail_on_gate=False)
    values.update(changes); return argparse.Namespace(**values)

class ProductionContextGateTests(unittest.TestCase):
    def setUp(self): self.fixture = gate.load_fixture()
    def test_endpoint_guard_and_exact_fixture_pressures(self):
        self.assertEqual([0, 8, 20, 48], self.fixture["pressure_levels"])
        self.assertEqual("::1", gate.ensure_local_endpoint("http://[::1]:11434/api/chat").hostname)
        with self.assertRaises(gate.EvalError): gate.ensure_local_endpoint("http://localhost:11434/api/chat")
        with self.assertRaises(gate.EvalError): gate.ensure_local_endpoint("http://127.0.0.1:11434/api/tags")
        with self.assertRaises(gate.EvalError): gate.ensure_local_endpoint("http://user@127.0.0.1:11434/api/chat")
        with self.assertRaises(gate.EvalError): gate.ensure_local_endpoint("http://127.0.0.1:11434/api/chat?x=1")
        self.assertEqual("localhost", gate.ensure_local_endpoint("http://localhost:11434/api/chat", True).hostname)
        with self.assertRaises(gate.EvalError): gate.validate_args(args(timeout=float("inf")))
        with self.assertRaises(gate.EvalError): gate.validate_args(args(num_gpu=-1))
    def test_pure_pipeline_no_mutation_order_and_projection(self):
        states = [gate.pipeline(self.fixture, pressure, args()) for pressure in self.fixture["pressure_levels"]]
        self.assertEqual(1, len({state["native_hash"] for state in states}))
        for state in states:
            self.assertTrue(all(state["structural"].values()))
            self.assertIn('"polarity":"negated"', state["ledger"])
            self.assertIn('"value":"green-lantern"', state["ledger"])
            joined = json.dumps(state["native"], ensure_ascii=False)
            self.assertNotIn("SYNTHETIC_PRESSURE_", joined)
            self.assertNotIn(self.fixture["canaries"]["dropped_holdout"], joined)
            self.assertNotIn(gate.ACTIVE_CARD_MESSAGE_NAME, joined)
            self.assertNotIn(gate.CONTINUITY_LEDGER_MESSAGE_NAME, joined)
            self.assertEqual(2048, state["native"]["options"]["num_ctx"])
            self.assertEqual(999, state["native"]["options"]["num_gpu"])
    def test_score_and_aggregate(self):
        good = gate.score(self.fixture["expected"], self.fixture["expected"])
        self.assertTrue(good["passed"])
        bad = gate.score(dict(self.fixture["expected"], bridge_fact="wrong"), self.fixture["expected"])
        self.assertFalse(bad["passed"])
        summary = gate.aggregate([
            {"complete":True,"structural_pass":True,"retry_used":False,"score":good,
             "raw_response_sha256":"a","parsed_result_sha256":"x",
             "metrics":{"prompt_eval_count":100,"total_duration_ms":10}},
            {"complete":True,"structural_pass":True,"retry_used":True,"score":bad,
             "raw_response_sha256":"b","parsed_result_sha256":"y",
             "metrics":{"prompt_eval_count":100,"total_duration_ms":20}},
        ])
        self.assertFalse(summary["semantic_pass"]); self.assertFalse(summary["gate_pass"])
        self.assertEqual(10.0, summary["total_duration_ms_p50"])
        self.assertEqual(20.0, summary["total_duration_ms_p95"])
        self.assertEqual(1, summary["retry_runs"])
    def test_fake_transport_atomic_report_and_malformed_retry(self):
        native = gate.pipeline(self.fixture, 0, args())["native"]
        response = {"done":True,"message":{"content":json.dumps(self.fixture["expected"])} }
        result = gate.run_one("ignored", native, args(), self.fixture["expected"], lambda *_: response)
        self.assertTrue(result["complete"]); self.assertFalse(result["retry_used"])
        calls = [gate.SchemaError("bad"), response]
        def fake(*_):
            item = calls.pop(0)
            if isinstance(item, Exception): raise item
            return item
        retried = gate.run_one("ignored", native, args(), self.fixture["expected"], fake)
        self.assertTrue(retried["complete"]); self.assertTrue(retried["retry_used"]); self.assertEqual(2, len(retried["attempts"]))
        for scalar in ("null", "1", '"text"', "[]"):
            calls = [
                {"done": True, "message": {"content": scalar}},
                response,
            ]
            recovered = gate.run_one(
                "ignored", native, args(), self.fixture["expected"],
                lambda *_: calls.pop(0),
            )
            self.assertTrue(recovered["complete"])
            self.assertTrue(recovered["retry_used"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"; gate.atomic_write(path, {"ok": True}); self.assertEqual({"ok": True}, json.loads(path.read_text(encoding="utf-8")))

if __name__ == "__main__": unittest.main()
