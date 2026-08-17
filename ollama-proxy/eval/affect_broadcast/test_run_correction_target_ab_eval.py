"""Offline contracts for the A4.4 isolated correction-target runner."""
from __future__ import annotations

import importlib.util
import json
import hashlib
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a44_test_runner", HERE / "run_correction_target_ab_eval.py")
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class CorrectionTargetABTests(unittest.TestCase):
    def _execution(self, rows=None):
        rows = rows or [{"ordinal": i, "responses": {"control": "control response", "target": "target response"}} for i in range(8)]
        return {"schema_version": "airi.correction-target-execution.v1", "rows": rows, "orders": ["CT"] * 4 + ["TC"] * 4, "row_order": list(range(8)), "health_profile_sha256": hashlib.sha256(runner.canonical_bytes(runner.base._expected_health_profile(runner.base.EVAL_PROFILE))).hexdigest(), "transport_contract": {"scope": "normal_cli_path_not_external_transport_proof", "literal_loopback": True, "no_proxy": True, "no_redirect": True, "bounded": True}}
    def _health(self):
        profile = runner.base.EVAL_PROFILE
        return {"status": "ok", "num_ctx": profile["num_ctx"], "chat_model": {"model": profile["model"], "digest": {"digest": profile["model_digest"], "status": "pinned", "verified": True}}, "affect_continuity": {"enabled": False, "ready": False, "mode": "typed-snapshot-v1", "schema_version": "airi.affect-state.v1", "prompt_cap_bytes": 384}}

    def test_exact_oracle_cohort_and_target_only_delta(self) -> None:
        rows = runner.load_cohort()
        self.assertEqual(8, len(rows))
        self.assertEqual(["teasing-02", "teasing-12", "correction-02", "correction-03", "correction-04", "correction-07", "correction-08", "correction-12"], [row["turn"]["id"] for row in rows])
        for row in rows:
            pair = runner.pair_requests(row)
            candidate = runner._serializer(row["candidate"])
            runner.assert_target_only_delta(pair["control"], pair["target"], candidate)

    def test_default_eligibility_never_calls_transport(self) -> None:
        evidence = runner.eligibility()
        self.assertTrue(evidence["eligible"])
        self.assertEqual(8, evidence["cohort_count"])
        self.assertFalse(evidence["operational_adoption"])

    def test_tampered_delta_fails_closed(self) -> None:
        pair = runner.pair_requests(runner.load_cohort()[0])
        value = json.loads(pair["target"])
        value["options"]["seed"] = 7
        with self.assertRaises(runner.EvalError):
            runner.assert_target_only_delta(pair["control"], runner.canonical_bytes(value), runner._serializer(runner.load_cohort()[0]["candidate"]))

    def test_packet_separates_keys_and_is_blank_locked_review_input(self) -> None:
        packet, key = runner.build_packet(self._execution(), randbelow=lambda n: 0)
        text = json.dumps(packet, ensure_ascii=False)
        self.assertNotIn("target_id", text)
        self.assertNotIn('"direction"', text)
        self.assertTrue(packet["locked_review_overlay_required"])
        self.assertEqual("correct", packet["pairs"][0]["review_context"]["expected_act"])
        self.assertIn("selected_message", packet["pairs"][0]["review_context"])
        self.assertIn("target_id", json.dumps(key))
        self.assertEqual(runner.PROTOCOL_ID, key["protocol_id"])
        with self.assertRaises(runner.EvalError): runner.validate_locked_overlay({}, packet)

    def test_fake_transport_makes_exactly_sixteen_posts_and_two_health_checks(self) -> None:
        calls = []
        def transport(method, url, body, headers):
            calls.append((method, url, body, headers))
            if method == "GET": return {"http_status": 200, "json": self._health()}
            return {"http_status": 200, "json": {"message": {"role": "assistant", "content": "ok"}}}
        draws = []
        result = runner.execute(runner.ENDPOINT, transport, randbelow=lambda n: draws.append(n) or 0)
        self.assertEqual(14, len(draws))
        self.assertEqual(16, sum(call[0] == "POST" for call in calls))
        self.assertEqual(2, sum(call[0] == "GET" for call in calls))
        self.assertEqual(4, result["orders"].count("CT")); self.assertEqual(4, result["orders"].count("TC"))

    def test_execution_rejects_bad_row_order(self) -> None:
        value=self._execution(); value["row_order"]=[0]*8
        with self.assertRaises(runner.EvalError): runner.validate_execution(value)

    def test_execution_rejects_bad_health_hash(self) -> None:
        value=self._execution(); value["health_profile_sha256"]="0"*64
        with self.assertRaises(runner.EvalError): runner.validate_execution(value)

    def test_execution_rejects_untrimmed_response(self) -> None:
        value=self._execution(); value["rows"][0]["responses"]["control"]=" bad "
        with self.assertRaises(runner.EvalError): runner.validate_execution(value)

    def test_overlay_requires_exact_packet_hash_and_complete_reviews(self) -> None:
        packet,_=runner.build_packet(self._execution(), randbelow=lambda n: 0)
        fields={"target_grounding":True,"correction_direction":True,"act":True,"continuity":True,"safety":True,"notes":""}
        overlay={"schema_version":"airi.correction-target-review-overlay.v2","locked":True,"packet_sha256":hashlib.sha256(runner.canonical_bytes(packet)).hexdigest(),"reviews":[{"pair":i,"review_a":fields,"review_b":fields,"preference_or_tie":"tie"} for i in range(1,9)]}
        runner.validate_locked_overlay(overlay, packet)
        overlay["packet_sha256"]="0"*64
        with self.assertRaises(runner.EvalError): runner.validate_locked_overlay(overlay,packet)

    def test_safe_run_accepts_normal_and_rejects_reserved(self) -> None:
        old_results,old_keys=runner.RESULTS,runner.KEYS
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); runner.RESULTS=root/"results"; runner.KEYS=root/"keys"
            reservation=runner._safe_path("normal-run")
            self.assertTrue(reservation["stage"].exists()); runner._abort_reservation(reservation)
            with self.assertRaises(runner.EvalError): runner._safe_path("CON")
        runner.RESULTS,runner.KEYS=old_results,old_keys

    def test_casefold_collision_rejected_before_transport(self) -> None:
        old_results,old_keys=runner.RESULTS,runner.KEYS
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); runner.RESULTS=root/"results"; runner.KEYS=root/"keys"; runner.RESULTS.mkdir(); (runner.RESULTS/"Run").mkdir(); runner.KEYS.mkdir()
            with self.assertRaises(runner.EvalError): runner._safe_path("run")
        runner.RESULTS,runner.KEYS=old_results,old_keys

    def test_packet_validator_rejects_nonblank_packet(self) -> None:
        packet,_=runner.build_packet(self._execution(), randbelow=lambda n: 0)
        packet["pairs"][0]["review_a"]["act"]=True
        with self.assertRaises(runner.EvalError): runner.validate_packet(packet)

    def test_packet_validator_rejects_context_drift(self) -> None:
        packet,_=runner.build_packet(self._execution(), randbelow=lambda n: 0)
        packet["pairs"][0]["review_context"]["screen"]="바뀐 화면"
        with self.assertRaises(runner.EvalError): runner.validate_packet(packet)

    def test_v1_review_packet_and_overlay_are_obsolete(self) -> None:
        packet,_=runner.build_packet(self._execution(), randbelow=lambda n: 0)
        packet["schema_version"]="airi.correction-target-blinded-review.v1"
        with self.assertRaises(runner.EvalError): runner.validate_packet(packet)
        current,_=runner.build_packet(self._execution(), randbelow=lambda n: 0)
        overlay={"schema_version":"airi.correction-target-review-overlay.v1","locked":True,"packet_sha256":"0"*64,"reviews":[]}
        with self.assertRaises(runner.EvalError): runner.validate_locked_overlay(overlay,current)

    def test_packet_rejects_invalid_label_draw(self) -> None:
        with self.assertRaises(runner.EvalError): runner.build_packet(self._execution(), randbelow=lambda n: 2)

    def test_abort_never_deletes_replaced_foreign_stage(self) -> None:
        old_results,old_keys=runner.RESULTS,runner.KEYS
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); runner.RESULTS=root/"results"; runner.KEYS=root/"keys"; reservation=runner._safe_path("owned")
            reservation["stage"].rmdir(); reservation["stage"].mkdir(); foreign=reservation["stage"] / "foreign"; foreign.write_text("keep", encoding="utf-8")
            runner._abort_reservation(reservation)
            self.assertTrue(foreign.exists())
        runner.RESULTS,runner.KEYS=old_results,old_keys

    def test_publish_rejects_reservation_from_other_run_before_writes(self) -> None:
        old_results,old_keys=runner.RESULTS,runner.KEYS
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); runner.RESULTS=root/"results"; runner.KEYS=root/"keys"; reservation=runner._safe_path("alpha")
            with self.assertRaises(runner.EvalError): runner.publish("beta", self._execution(), reservation=reservation)
            self.assertFalse((root/"results"/"alpha").exists())
            self.assertFalse((root/"results"/"beta").exists())
            self.assertFalse((root/"keys"/"alpha.json").exists())
            self.assertFalse((root/"keys"/"beta.json").exists())
        runner.RESULTS,runner.KEYS=old_results,old_keys

    def test_invalid_endpoint_has_no_output_mutation(self) -> None:
        old_results,old_keys=runner.RESULTS,runner.KEYS
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); runner.RESULTS=root/"results"; runner.KEYS=root/"keys"
            with self.assertRaises(runner.base.EvalError): runner.base.ensure_loopback("http://127.0.0.1:9/api/chat")
            self.assertFalse((root/"results").exists()); self.assertFalse((root/"keys").exists())
        runner.RESULTS,runner.KEYS=old_results,old_keys


if __name__ == "__main__": unittest.main()
