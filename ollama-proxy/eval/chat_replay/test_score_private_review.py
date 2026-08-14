import ast
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score_private_review import PrivateReviewError, score_private_review
from chat_replay import _canonical


def row(
    seq, *, delivered, expected, event_kind="chat", signals=None,
    duplicate_of_seq=None, quality=True,
):
    return {
        "seq": seq,
        "offset_ms": seq * 100,
        "timing_bucket": "under_1s",
        "event_kind": event_kind,
        "duplicate_of_seq": duplicate_of_seq,
        "surface_signals": signals or [],
        "selection_eligible": event_kind != "system_noise" and duplicate_of_seq is None,
        "delivered": delivered,
        "input": f"민감 입력 {seq}",
        "response": f"민감 응답 {seq}" if delivered else None,
        "review": {
            "expected_action": expected,
            "grounded": quality if delivered else None,
            "context_preserved": quality if delivered else None,
            "tone_ok": quality if delivered else None,
            "privacy_ok": True if delivered else None,
            "epistemic_ok": quality if delivered else None,
        },
    }


class PrivateReviewScorerTests(unittest.TestCase):
    def write_packet(self, directory: Path) -> Path:
        path = directory / "review.json"
        rows = [
            row(1, delivered=True, expected="respond"),
            row(2, delivered=True, expected="ignore", event_kind="system_noise", signals=["noise", "source_text_repeat"], duplicate_of_seq=1, quality=False),
            row(3, delivered=False, expected="respond"),
            row(4, delivered=False, expected="ignore"),
        ]
        profile = {"source_slot": "channel_a", "phase": "opening"}
        source_rows = [{
            "seq": item["seq"],
            "offset_ms": item["offset_ms"],
            "timing_bucket": item["timing_bucket"],
            "event_kind": item["event_kind"],
            "duplicate_of_seq": item["duplicate_of_seq"],
            "selection_eligible": item["selection_eligible"],
            "surface_signals": item["surface_signals"],
        } for item in rows]
        packet = {
            "schema_version": "airi.chat-replay-private-review.v2",
            "local_only": True,
            "capture_profile": profile,
            "source_structural_sha256": hashlib.sha256(_canonical({
                "capture_profile": profile, "events": source_rows,
            })).hexdigest(),
            "rows": rows,
        }
        path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
        return path

    def test_scores_all_confusion_cells_and_emits_no_text(self):
        with tempfile.TemporaryDirectory() as temp:
            path = self.write_packet(Path(temp))
            report = score_private_review(path)
        self.assertEqual(report["replay_selector"], {
            "tp": 1, "fp": 1, "fn": 1, "tn": 1,
            "precision": 0.5, "recall": 0.5, "f1": 0.5,
            "noise_delivery_count": 1,
            "source_repeat_delivery_count": 1,
        })
        self.assertEqual(report["reviewed_response_count"], 2)
        self.assertEqual(report["response_quality"]["grounded"], {
            "pass_count": 1, "pass_rate": 0.5,
        })
        self.assertEqual(report["critical_failure_count"], 1)
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("민감 입력", serialized)
        self.assertNotIn("민감 응답", serialized)

    def test_incomplete_or_free_text_labels_fail_closed(self):
        for change in (
            lambda packet: packet["rows"][0]["review"].update(expected_action=None),
            lambda packet: packet["rows"][0]["review"].update(grounded=None),
            lambda packet: packet["rows"][0].update(event_kind="named-channel"),
            lambda packet: packet["rows"][0].update(surface_signals=["free-text-signal"]),
        ):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                path = self.write_packet(Path(temp))
                packet = json.loads(path.read_text(encoding="utf-8"))
                change(packet)
                path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
                with self.assertRaises(PrivateReviewError):
                    score_private_review(path)

    def test_scorer_has_no_network_imports(self):
        path = Path(__file__).parent / "score_private_review.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        forbidden = {"requests", "urllib", "http", "socket", "aiohttp", "webbrowser"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name.split(".")[0] for alias in node.names] if isinstance(node, ast.Import) else [(node.module or "").split(".")[0]]
                self.assertFalse(set(names) & forbidden)


if __name__ == "__main__":
    unittest.main()
