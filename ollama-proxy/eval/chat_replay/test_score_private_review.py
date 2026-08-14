import ast
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chat_replay import ReplayEvent, _canonical, run_replay
import run_chat_replay
import score_private_review as scorer
from score_private_review import PrivateReviewError, score_private_review


class PrivateReviewScorerTests(unittest.TestCase):
    def fixture(self, directory: Path):
        key = b"k" * 32
        key_path = directory / "identity.key"; key_path.write_bytes(key)
        events = [ReplayEvent(1, 100, "under_1s", "chat", "sensitive input", None, True, ())]
        source = run_replay(events, lambda *_: "private response", report_hmac_key=key,
                            capture_profile={"source_slot": "channel_a", "phase": "opening"})
        evidence = {"provider": "test", "source_identity_hmac": "a" * 64, "exact_capture_hmac": "b" * 64}
        runtime = {"model": "frozen", "history_turns": 8}
        binding = hashlib.sha256(_canonical({"source_structural_sha256": source["structural_sha256"], "source_evidence": evidence, "runtime_profile": runtime, "response_rows": source["response_rows"]})).hexdigest()
        replay = {**source, "source_evidence": evidence, "runtime_profile": runtime, "run_binding_sha256": binding}
        replay["report_hmac_sha256"] = run_chat_replay.replay_report_hmac(key, replay)
        packet = run_chat_replay.build_private_review_packet(events, {1: "private response"}, source["capture_profile"], source["structural_sha256"], evidence, runtime, binding, replay["report_hmac_sha256"], source["response_rows"])
        packet["source_review"] = {"atmosphere": "calm", "pace": "steady", "context_pressure": "low", "dominant_patterns": ["question_wave"]}
        packet["rows"][0]["review"] = {"expected_action": "respond", "grounded": True, "context_preserved": True, "tone_ok": True, "privacy_ok": False, "current_fact_ok": False, "reference_grounding_ok": True, "agreement_calibration_ok": False}
        packet_path, replay_path = directory / "packet.json", directory / "replay.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8"); replay_path.write_text(json.dumps(replay), encoding="utf-8")
        return packet_path, replay_path, key_path

    def test_binding_and_content_free_score(self):
        with tempfile.TemporaryDirectory() as temp:
            packet, replay, key = self.fixture(Path(temp)); report = score_private_review(packet, replay, key)
        self.assertEqual(report["critical_failure_counts"], {"privacy_ok": 1, "current_fact_ok": 1, "reference_grounding_ok": 0, "agreement_calibration_ok": 1, "total_critical_rows": 1})
        self.assertRegex(report["source_label_hmac_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(report["score_hmac_sha256"], r"^[0-9a-f]{64}$")
        encoded = json.dumps(report); self.assertNotIn("private response", encoded); self.assertNotIn("sensitive input", encoded)

    def test_wrong_key_changed_response_or_swapped_report_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); packet, replay, key = self.fixture(root)
            wrong = root / "wrong.key"; wrong.write_bytes(b"x" * 32)
            with self.assertRaises(PrivateReviewError): score_private_review(packet, replay, wrong)
            value = json.loads(packet.read_text()); value["rows"][0]["response"] = "changed response"; packet.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(PrivateReviewError): score_private_review(packet, replay, key)
            other = root / "other.json"; other.write_text(json.dumps({}), encoding="utf-8")
            with self.assertRaises(PrivateReviewError): score_private_review(packet, other, key)

    def test_incomplete_source_labels_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); packet, replay, key = self.fixture(root); value = json.loads(packet.read_text()); value["source_review"]["pace"] = None; packet.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(PrivateReviewError): score_private_review(packet, replay, key)

    def test_duplicate_replay_response_row_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packet, replay, key = self.fixture(root)
            value = json.loads(replay.read_text(encoding="utf-8"))
            value["response_rows"].append(value["response_rows"][0])
            replay.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(PrivateReviewError):
                score_private_review(packet, replay, key)

    def test_source_observation_is_bound_by_score_structure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            packet, replay, key = self.fixture(root)
            first = score_private_review(packet, replay, key)
            value = json.loads(packet.read_text(encoding="utf-8"))
            value["source_review"]["atmosphere"] = "playful"
            packet.write_text(json.dumps(value), encoding="utf-8")
            second = score_private_review(packet, replay, key)
        self.assertNotEqual(first["structural_sha256"], second["structural_sha256"])

    def test_scorer_has_no_network_imports(self):
        tree = ast.parse((Path(__file__).parent / "score_private_review.py").read_text(encoding="utf-8"))
        forbidden = {"requests", "urllib", "http", "socket", "aiohttp", "webbrowser"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [x.name.split(".")[0] for x in node.names] if isinstance(node, ast.Import) else [(node.module or "").split(".")[0]]
                self.assertFalse(set(names) & forbidden)

    def test_cli_refuses_to_overwrite_replay_evidence(self):
        replay = Path("same-report.json")
        with mock.patch.object(scorer, "_secure_inside", return_value=True):
            with self.assertRaises(SystemExit):
                scorer.main([
                    "--input", "review.json",
                    "--replay-report", str(replay),
                    "--identity-key", "identity.key",
                    "--report", str(replay),
                ])

if __name__ == "__main__": unittest.main()
