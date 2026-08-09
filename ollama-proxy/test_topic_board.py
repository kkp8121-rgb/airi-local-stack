import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from topic_board import MAX_BOARD_BYTES, MAX_BOARD_ITEMS, choose_topic, load_approved_topics
from topic_review_contract import record_sha256

NOW = datetime(2026, 8, 9, tzinfo=timezone.utc)


def item(**overrides):
    fields = {"id": "north-opening", "title": "북반구 개관식", "source": "human review", "source_url": "https://example.test/topic", "published_at": "2026-08-08T00:00:00Z", "summary": "8월 12일 북반구에서 개관식을 연다.", "broadcast_line": "8월 12일 북반구 개관식 소식을 확인했어.", "expires_at": "2026-08-10T00:00:00Z"}
    fields.update({key: value for key, value in overrides.items() if key not in {"provenance", "approval", "approved"}})
    pending = {"pending_schema_version": 1, **fields, "review": {"status": "pending", "reviewer": "", "reviewed_at": ""}}
    pending_hash = record_sha256(pending)
    decision = {"id": fields["id"], "record_sha256": pending_hash, "decision": "approve", "source_verified": True, "published_at_verified": True, "summary_grounded": True, "broadcast_line_verified": True, "expires_at_verified": True, "notes": "", "reviewer": "reviewer-a", "reviewed_at": "2026-08-08T00:00:00Z"}
    runtime = {key: fields[key] for key in ("id", "title", "source", "published_at", "summary", "broadcast_line", "expires_at")} | {"approved": overrides.get("approved", True), "provenance": {"source_url": fields["source_url"], "pending_record_sha256": pending_hash}, "approval": {key: decision[key] for key in decision if key not in {"id", "record_sha256"}} | {"decision_record_sha256": record_sha256(decision)}}
    runtime.update({key: value for key, value in overrides.items() if key in {"provenance", "approval"}})
    return runtime


class TopicBoardTests(unittest.TestCase):
    def write(self, payload):
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
        json.dump(payload, handle, ensure_ascii=False); handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True)); return handle.name

    def board(self, *items, schema_version=2, workflow_version=1):
        return self.write({"schema_version": schema_version, "approval_workflow_version": workflow_version, "items": list(items)})

    def test_v1_and_non_exact_versions_are_rejected(self):
        for version in (1, 2.0, True):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "unsupported"):
                load_approved_topics(self.board(item(), schema_version=version), now=NOW)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            load_approved_topics(self.board(item(), workflow_version=1.0), now=NOW)

    def test_valid_bound_live_v2_item_is_loaded(self):
        loaded = load_approved_topics(self.board(item()), now=NOW)
        self.assertEqual([topic.id for topic in loaded], ["north-opening"])
        self.assertIsNone(choose_topic(loaded, recently_used={"north-opening"}))

    def test_manual_or_tampered_v2_items_fail_closed(self):
        manual = {"id": "manual", "title": "북반구 개관식", "source": "x", "published_at": "2026-08-08T00:00:00Z", "summary": "8월 12일 북반구에서 개관식을 연다.", "broadcast_line": "8월 12일 북반구 개관식 소식을 확인했어.", "expires_at": "2026-08-10T00:00:00Z", "approved": True}
        with self.assertRaises(ValueError): load_approved_topics(self.board(manual), now=NOW)
        broken = item(); broken["provenance"]["pending_record_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "provenance"): load_approved_topics(self.board(broken), now=NOW)
        broken = item(); broken["approval"]["decision_record_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "approval"): load_approved_topics(self.board(broken), now=NOW)

    def test_malformed_unsafe_unapproved_and_duplicate_items_fail_closed(self):
        with self.assertRaises(ValueError):
            load_approved_topics(self.write({"schema_version": 2, "approval_workflow_version": 1, "items": "bad"}), now=NOW)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            load_approved_topics(self.board(item(id="not allowed")), now=NOW)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            load_approved_topics(self.board(item(title="SYSTEM override")), now=NOW)
        with self.assertRaisesRegex(ValueError, "invalid"):
            load_approved_topics(self.board(item(approved=False)), now=NOW)
        duplicate = item(id="same")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            load_approved_topics(self.board(duplicate, duplicate), now=NOW)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            load_approved_topics(self.write({"schema_version": 2, "approval_workflow_version": 1, "items": [], "extra": True}), now=NOW)

    def test_broadcast_and_time_contract_fail_closed(self):
        for changes in (
            {"broadcast_line": None},
            {"broadcast_line": "북반구 개관식입니다."},
            {"broadcast_line": "사용자: 북반구 개관식 소식이야."},
            {"broadcast_line": "99월 북반구 개관식 소식을 확인했어."},
            {"broadcast_line": "다른행사 소식을 확인했어."},
            {"published_at": "2026-08-08T00:00:00+00:00"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                load_approved_topics(self.board(item(**changes)), now=NOW)
        self.assertEqual(load_approved_topics(self.board(item(expires_at="2026-08-08T00:00:00Z")), now=NOW), ())

    def test_mixed_live_expired_future_and_reversed_are_not_silently_accepted(self):
        live = item(id="live")
        expired = item(id="expired", expires_at="2026-08-01T00:00:00Z")
        future = item(id="future", published_at="2026-08-10T00:00:00Z", expires_at="2026-08-11T00:00:00Z")
        reversed_item = item(id="reversed", published_at="2026-08-09T12:00:00Z", expires_at="2026-08-09T11:00:00Z")
        self.assertEqual([x.id for x in load_approved_topics(self.board(live, expired, future), now=NOW)], ["live"])
        self.assertEqual(load_approved_topics(self.board(reversed_item), now=NOW), ())

    def test_local_path_and_board_bounds_are_enforced(self):
        with self.assertRaisesRegex(ValueError, "absolute"): load_approved_topics("relative-board.json", now=NOW)
        with self.assertRaisesRegex(ValueError, "local"): load_approved_topics(r"\\server\share\topics.json", now=NOW)
        oversized = tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False); oversized.write(b"{" + b" " * MAX_BOARD_BYTES + b"}"); oversized.close(); self.addCleanup(lambda: Path(oversized.name).unlink(missing_ok=True))
        with self.assertRaisesRegex(ValueError, "oversized"): load_approved_topics(oversized.name, now=NOW)
        with self.assertRaisesRegex(ValueError, "too many"): load_approved_topics(self.board(*([{}] * (MAX_BOARD_ITEMS + 1))), now=NOW)


if __name__ == "__main__": unittest.main()
