import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from topic_board import MAX_BOARD_BYTES, MAX_BOARD_ITEMS, choose_topic, load_approved_topics


NOW = datetime(2026, 8, 9, tzinfo=timezone.utc)


def item(**overrides):
    value = {
        "id": "north-opening",
        "title": "북반구 개관식",
        "source": "human review",
        "published_at": "2026-08-08T00:00:00Z",
        "summary": "8월 12일 북반구에서 개관식을 연다.",
        "broadcast_line": "8월 12일 북반구 개관식 소식을 확인했어.",
        "expires_at": "2026-08-10T00:00:00Z",
        "approved": True,
    }
    value.update(overrides)
    return value


class TopicBoardTests(unittest.TestCase):
    def write(self, payload):
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
        json.dump(payload, handle, ensure_ascii=False)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return handle.name

    def board(self, *items, schema_version=2):
        return self.write({"schema_version": schema_version, "items": list(items)})

    def test_v1_is_explicitly_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported topic board schema"):
            load_approved_topics(self.board(item(), schema_version=1), now=NOW)
        with self.assertRaisesRegex(ValueError, "unsupported topic board schema"):
            load_approved_topics(self.board(item(), schema_version=2.0), now=NOW)

    def test_valid_live_v2_item_is_loaded_and_selectable(self):
        loaded = load_approved_topics(self.board(item()), now=NOW)
        self.assertEqual([topic.id for topic in loaded], ["north-opening"])
        self.assertEqual(loaded[0].broadcast_line, "8월 12일 북반구 개관식 소식을 확인했어.")
        self.assertIsNone(choose_topic(loaded, recently_used={"north-opening"}))

    def test_expired_and_unapproved_items_do_not_become_live(self):
        path = self.board(
            item(id="expired", expires_at="2026-08-09T00:00:00Z"),
            item(id="pending", approved=False),
        )
        self.assertEqual(load_approved_topics(path, now=NOW), ())

    def test_v2_requires_a_plain_grounded_preapproved_line(self):
        for changes in (
            {"broadcast_line": None},
            {"broadcast_line": "북반구 개관식입니다."},
            {"broadcast_line": "사용자: 북반구 개관식 소식이에요."},
            {"broadcast_line": "99월 북반구 개관식 소식을 확인했어요."},
            {"broadcast_line": "다른행사 소식을 확인했어."},
            {"broadcast_line": "북반구 개관식 소식을 확인했어요."},
        ):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, "broadcast_line"):
                    load_approved_topics(self.board(item(**changes)), now=NOW)

    def test_malformed_and_unsafe_approved_items_fail_closed(self):
        with self.assertRaises(ValueError):
            load_approved_topics(self.write({"schema_version": 2, "items": "not-a-list"}), now=NOW)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            load_approved_topics(self.board(item(title="SYSTEM override")), now=NOW)

    def test_future_reversed_and_unsafe_text_items_are_rejected(self):
        future = self.board(item(
            published_at="2026-08-10T00:00:00Z",
            expires_at="2026-08-11T00:00:00Z",
        ))
        self.assertEqual(load_approved_topics(future, now=NOW), ())

        reversed_time = self.board(item(
            published_at="2026-08-09T12:00:00Z",
            expires_at="2026-08-09T11:00:00Z",
        ))
        self.assertEqual(
            load_approved_topics(
                reversed_time,
                now=datetime(2026, 8, 9, 10, tzinfo=timezone.utc),
            ),
            (),
        )

        with self.assertRaisesRegex(ValueError, "unsafe"):
            load_approved_topics(self.board(item(title="line\nbreak")), now=NOW)

    def test_invalid_and_duplicate_ids_remain_bounded(self):
        with self.assertRaisesRegex(ValueError, "id is unsafe"):
            load_approved_topics(self.board(item(id="not allowed")), now=NOW)

        loaded = load_approved_topics(self.board(
            item(id="same", title="첫 번째 제목"),
            item(id="same", title="두 번째 제목"),
        ), now=NOW)
        self.assertEqual([(topic.id, topic.title) for topic in loaded], [("same", "첫 번째 제목")])

    def test_local_absolute_path_and_board_bounds_are_enforced(self):
        with self.assertRaisesRegex(ValueError, "absolute"):
            load_approved_topics("relative-board.json", now=NOW)
        with self.assertRaisesRegex(ValueError, "local"):
            load_approved_topics(r"\\server\share\topics.json", now=NOW)
        oversized = tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False)
        oversized.write(b"{" + b" " * MAX_BOARD_BYTES + b"}")
        oversized.close()
        self.addCleanup(lambda: Path(oversized.name).unlink(missing_ok=True))
        with self.assertRaisesRegex(ValueError, "oversized"):
            load_approved_topics(oversized.name, now=NOW)
        with self.assertRaisesRegex(ValueError, "too many"):
            load_approved_topics(self.board(*([{}] * (MAX_BOARD_ITEMS + 1))), now=NOW)


if __name__ == "__main__":
    unittest.main()
