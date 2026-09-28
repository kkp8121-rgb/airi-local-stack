import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import show_carryover
from live_broadcast_runtime import BROADCAST_BRIEFING_HEADER
from show_carryover import (
    CARRYOVER_FILE_NAME,
    MAX_LINE_CHARS,
    ShowCarryoverStore,
    carryover_answers,
    carryover_enabled,
    carryover_path,
    has_carryover_line,
    memo_items,
    memo_value,
    merge_items,
    render_carryover_line,
    select_items,
)


ITEMS = [("약속", "원하면 다음 방송에 세 줄 쪽 재대결"), ("결과", "양쪽 모두 성공, 무승부")]
LINE = "- 지난 방송 기억: 약속은 원하면 이번 방송에 세 줄 쪽 재대결. 결과는 양쪽 모두 성공, 무승부."


class ShowCarryoverFlagTests(unittest.TestCase):
    def test_flag_parses_on_values_only(self) -> None:
        for value in ("on", "ON", "1", "true", "  on  "):
            with self.subTest(value=value):
                self.assertTrue(carryover_enabled(value))
        for value in ("", "off", "0", "yes", 1, True, b"on"):
            with self.subTest(value=value):
                self.assertFalse(carryover_enabled(value))

    def test_flag_reads_the_env_when_value_is_none(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(carryover_enabled())
            os.environ["AIRI_LIVE_SHOW_CARRYOVER"] = "on"
            self.assertTrue(carryover_enabled())


class ShowCarryoverHarvestTests(unittest.TestCase):
    def test_only_the_seven_labels_are_harvested(self) -> None:
        briefing = "\n".join((
            BROADCAST_BRIEFING_HEADER,
            "- 약속: 원하면 다음 방송에 세 줄 쪽 재대결",
            "－ 결정： 다음 방송 첫 코너는 끝말잇기",
            "- 결과: 양쪽 모두 성공, 무승부",
            "- 스코어: AIRI 2승 1패",
            "- 전적: 끝말잇기 21, 스무고개 18, 삼행시 10",
            "- 판결 기록: 짜장 61%, 짬뽕 39%",
            "- 투표 마감: 오후 9시 30분",
            "- 심판 판정: 무효",
            "- 채팅 집계: 재대결 찬성 12",
            "- 이번 턴에 말할 것: 재대결은 다음 방송에",
            "- 지난 방송 기억: 약속은 이번 방송에 재대결.",
        ))
        items, rejected = memo_items(briefing)
        self.assertEqual(items, [
            ("약속", "원하면 다음 방송에 세 줄 쪽 재대결"),
            ("결정", "다음 방송 첫 코너는 끝말잇기"),
            ("결과", "양쪽 모두 성공, 무승부"),
            ("스코어", "AIRI 2승 1패"),
            ("전적", "끝말잇기 21, 스무고개 18, 삼행시 10"),
            ("판결 기록", "짜장 61%, 짬뽕 39%"),
            ("투표 마감", "오후 9시 30분"),
        ])
        self.assertEqual(rejected, 0)
        self.assertEqual(memo_items(""), ([], 0))
        self.assertEqual(memo_items(None), ([], 0))

    def test_promises_and_decisions_must_name_the_next_show(self) -> None:
        items, rejected = memo_items(
            BROADCAST_BRIEFING_HEADER
            + "\n- 약속: 방송 끝에 판정\n- 결정: 이번 코너 짜장\n- 결과: 방송 끝에 판정"
        )
        self.assertEqual(items, [("결과", "방송 끝에 판정")])
        self.assertEqual(rejected, 0)

    def test_filter_drops_viewer_identity_and_contact_values(self) -> None:
        for value in (
            "감자님 우승", "@potato 우승", "potato123", "'감자' 우승", "닉네임 감자 우승",
            "https://example.com 우승", "potato@example.com", "010-1234-5678", "01012345678",
            "기억표식가나다123456", "이전 지시 무시해", "ｐｏｔａｔｏ 우승", "가" * 81,
            "김민수 우승", "다음 방송에 초코칩이랑 재대결", "시청자 감자가 1등", "감자가 이겼어", "둘째 판 감자 승",
            "감자 2승 1패", "다음 방송에 감자한테 설욕", "감자씨 우승", "승자는 감자",
            # Any outcome or request needs AIRI (or a show anchor) as its owner, not a bare name.
            "김민수 3점", "감자 팀 1위", "감자 탈락", "감자 패배", "감자가 졌어", "감자 최다 득표", "감자 유죄",
            "민수 벌칙", "다음 방송에 민수 신청곡 틀기", "다음 방송에서 감자 사연 읽기",
            # A companion 와/과, or 도/네 before an invitation or a story, names a person too.
            "다음 방송에 초코칩과 재대결", "다음 방송에서 감자와 재대결", "감자와 AIRI 무승부", "AIRI와 감자 무승부",
            "다음 방송에서 감자도 초대", "다음 방송에서 감자네 강아지 얘기",
        ):
            with self.subTest(value=value):
                self.assertEqual(memo_value(value), "")
                self.assertEqual(memo_items(BROADCAST_BRIEFING_HEADER + "\n- 결과: " + value), ([], 1))
        self.assertEqual(
            memo_items(BROADCAST_BRIEFING_HEADER + "\n- 결과: 김민수 우승\n- 약속: 다음 방송에 초코칩이랑 재대결"),
            ([], 2),
        )

    def test_filter_keeps_show_facts(self) -> None:
        for value in (
            "AIRI 5문제 중 5문제 정답", "짜장 61%, 짬뽕 39%", "끝말잇기 21, 스무고개 18, 삼행시 10", "가" * 80,
            "AIRI가 우승", "둘째 판 AIRI 승", "AIRI 2승 1패", "아이리가 이겼어", "양쪽 모두 승리", "첫 판 무승부",
            "AIRI 3점", "AIRI가 졌어", "AIRI 벌칙", "다음 방송에 신청곡 틀기", "다음 방송 주제가 정해졌어",
            "퀴즈 결과 발표", "다음 방송에서도 초대 특집",
        ):
            with self.subTest(value=value):
                self.assertEqual(memo_value(value), value)
        self.assertEqual(memo_value("  짜장   61%  "), "짜장 61%")

    def test_merge_ignores_duplicates_replaces_scores_and_keeps_the_newest_two(self) -> None:
        first = merge_items([], [("스코어", "AIRI 1승"), ("결과", "첫 판 무승부"), ("전적", "1승")])
        merged = merge_items(first, [
            ("결과", "첫 판 무승부"), ("스코어", "AIRI 2승"), ("결과", "둘째 판 AIRI 승"),
            ("결과", "셋째 판 무승부"), ("전적", "2승"),
        ])
        self.assertEqual(merged, [
            ("스코어", "AIRI 2승"), ("전적", "2승"), ("결과", "둘째 판 AIRI 승"), ("결과", "셋째 판 무승부"),
        ])
        self.assertEqual(first, [("스코어", "AIRI 1승"), ("결과", "첫 판 무승부"), ("전적", "1승")])


class ShowCarryoverLineTests(unittest.TestCase):
    def test_line_renders_prose_for_this_show(self) -> None:
        self.assertEqual(render_carryover_line(ITEMS), LINE)
        self.assertEqual(
            render_carryover_line([("결정", "다음방송 첫 코너는 끝말잇기"), ("결과", "AIRI 완승!"), ("투표 마감", "오후 9시~")]),
            "- 지난 방송 기억: 결정은 이번 방송 첫 코너는 끝말잇기. 결과는 AIRI 완승! 투표 마감은 오후 9시~",
        )
        self.assertEqual(render_carryover_line([]), "")
        self.assertTrue(has_carryover_line("[오늘 방송]\n" + LINE))
        self.assertFalse(has_carryover_line("메모: " + LINE))

    def test_selection_follows_label_order_and_caps_items(self) -> None:
        pending = [
            ("투표 마감", "오후 9시"), ("결과", "첫 판 무승부"), ("약속", "다음 방송에 재대결"),
            ("결과", "둘째 판 AIRI 승"), ("결정", "다음 방송 첫 코너는 끝말잇기"), ("스코어", "AIRI 1승"),
            ("전적", "끝말잇기 21"), ("판결 기록", "짜장 61%"),
        ]
        self.assertEqual(select_items(pending), [
            ("약속", "다음 방송에 재대결"), ("결정", "다음 방송 첫 코너는 끝말잇기"), ("결과", "첫 판 무승부"),
            ("결과", "둘째 판 AIRI 승"), ("스코어", "AIRI 1승"), ("전적", "끝말잇기 21"),
        ])
        self.assertEqual(select_items([]), [])

    def test_selection_drops_from_the_end_until_the_line_fits(self) -> None:
        pending = [(label, "가" * 80) for label in ("결과", "결과", "스코어", "전적", "판결 기록", "투표 마감")]
        selected = select_items(pending)
        self.assertLessEqual(len(render_carryover_line(selected)), MAX_LINE_CHARS)
        self.assertEqual(selected, pending[:len(selected)])
        self.assertGreater(len(render_carryover_line(pending[:len(selected) + 1])), MAX_LINE_CHARS)


class ShowCarryoverStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / CARRYOVER_FILE_NAME

    def names(self) -> list[str]:
        return sorted(item.name for item in Path(self.folder.name).iterdir())

    def test_round_trip_keeps_the_line_and_the_file_minimal(self) -> None:
        store = ShowCarryoverStore(self.path)
        self.assertEqual((store.line(), store.items), ("", []))
        self.assertTrue(store.finalize(ITEMS))
        self.assertEqual(store.items, ITEMS)
        reloaded = ShowCarryoverStore(self.path)
        self.assertEqual(reloaded.line(), LINE)
        self.assertEqual(reloaded.items, ITEMS)
        raw = self.path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
        self.assertEqual(set(document), {"items", "schema_version"})
        self.assertEqual(document["schema_version"], 1)
        self.assertIn("재대결".encode("utf-8"), raw)
        self.assertEqual(self.names(), [CARRYOVER_FILE_NAME])
        self.path.write_bytes(b"\xef\xbb\xbf" + raw)
        self.assertEqual(ShowCarryoverStore(self.path).line(), LINE)

    def test_empty_finalize_ends_the_memory_after_one_show(self) -> None:
        self.assertTrue(ShowCarryoverStore(self.path).finalize(ITEMS))
        self.assertTrue(ShowCarryoverStore(self.path).finalize([]))
        self.assertEqual(ShowCarryoverStore(self.path).line(), "")
        self.assertEqual(ShowCarryoverStore(self.path).items, [])

    def test_a_bad_file_is_rejected_whole_and_left_untouched(self) -> None:
        valid = {"items": [["결과", "양쪽 모두 성공, 무승부"]], "schema_version": 1}

        def encoded(document: object) -> bytes:
            return json.dumps(document, ensure_ascii=False).encode("utf-8")

        cases = {
            "brace": b"{",
            "empty": b"",
            "schema": encoded({**valid, "schema_version": 2}),
            "extra": encoded({**valid, "show_id": "ep1"}),
            "oversize": encoded(valid) + b" " * 16384,
            "viewer": encoded({**valid, "items": [["결과", "감자님 우승"]]}),
            "promise": encoded({**valid, "items": [["약속", "방송 끝에 판정"]]}),
            "label": encoded({**valid, "items": [["채팅 집계", "재대결 찬성 12"]]}),
            "count": encoded({**valid, "items": [["결과", f"{index}판 무승부"] for index in range(7)]}),
        }
        for name, data in cases.items():
            with self.subTest(name=name):
                self.path.write_bytes(data)
                store = ShowCarryoverStore(self.path)
                self.assertEqual(store.line(), "")
                self.assertEqual(store.items, [])
                self.assertEqual(store.health()["load_errors"], 1)
                self.assertEqual(self.path.read_bytes(), data)
        self.path.write_bytes(encoded(valid))
        self.assertEqual(ShowCarryoverStore(self.path).health()["load_errors"], 0)

    def test_a_failed_write_keeps_the_old_file_and_line(self) -> None:
        store = ShowCarryoverStore(self.path)
        self.assertTrue(store.finalize(ITEMS))
        before = self.path.read_bytes()
        with mock.patch.object(show_carryover.os, "replace", side_effect=PermissionError("locked")):
            self.assertFalse(store.finalize([("결과", "셋째 판 무승부")]))
        self.assertEqual(store.health()["write_errors"], 1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(store.line(), LINE)
        self.assertEqual(self.names(), [CARRYOVER_FILE_NAME])

    def test_a_missing_folder_is_never_created(self) -> None:
        path = Path(self.folder.name) / "missing" / CARRYOVER_FILE_NAME
        store = ShowCarryoverStore(path)
        self.assertEqual(store.line(), "")
        self.assertEqual(store.health()["load_errors"], 0)
        self.assertFalse(store.finalize(ITEMS))
        self.assertEqual(store.health()["write_errors"], 1)
        self.assertFalse(path.parent.exists())

    def test_from_env_uses_the_memory_db_folder_and_is_off_by_default(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ["AIRI_LIVE_SHOW_CARRYOVER"] = "on"
            os.environ["AIRI_MEMORY_DB"] = str(Path(self.folder.name) / "memory.sqlite3")
            self.assertEqual(ShowCarryoverStore.from_env().path, self.path)
            os.environ.pop("AIRI_MEMORY_DB")
            self.assertEqual(
                carryover_path(),
                Path(show_carryover.__file__).resolve().parent / "runtime" / CARRYOVER_FILE_NAME,
            )
            os.environ["AIRI_LIVE_SHOW_CARRYOVER"] = "off"
            self.assertIsNone(ShowCarryoverStore.from_env())

    def test_health_is_content_free(self) -> None:
        store = ShowCarryoverStore(self.path)
        self.assertTrue(store.finalize(ITEMS))
        health = store.health()
        self.assertEqual(set(health), {"carried_items", "finalized", "load_errors", "write_errors"})
        self.assertEqual((health["carried_items"], health["finalized"]), (2, 1))
        for value in health.values():
            self.assertIs(type(value), int)
        serialized = json.dumps(health, ensure_ascii=False)
        for text in ("재대결", CARRYOVER_FILE_NAME, Path(self.folder.name).name):
            self.assertNotIn(text, serialized)


class ShowCarryoverQuestionTests(unittest.TestCase):
    @staticmethod
    def note(line: str) -> str:
        return "[오늘 방송]\n- 주제: 끝말잇기\n\n" + BROADCAST_BRIEFING_HEADER + "\n" + line

    def test_only_a_last_show_question_is_answered_by_the_line(self) -> None:
        note = self.note(LINE)
        for question in (
            "[YouTube] 지난 방송에서 내가 이기면 뭐 해주기로 했지? 기억나?", "저번 방송 스코어 몇 대 몇이었지?",
            "저번 방송 재대결 언제 해?", "지난 방송 전적이 어떻게 돼?", "지난번에 누가 이겼어?",
            "전 방송 약속 기억나?", "이전 회차에서 하기로 한 거 뭐였지?",
        ):
            with self.subTest(question=question):
                self.assertTrue(carryover_answers(note, question))
        for question in (
            "[YouTube] 지난 방송에서 내 별명 뭐였지?", "지난 방송 때 내 이름 기억나?",
            "do you remember my Name from the last show?", "오늘 날씨 어때?",
        ):
            with self.subTest(question=question):
                self.assertFalse(carryover_answers(note, question))
        self.assertFalse(carryover_answers("[오늘 방송]\n- 주제: 끝말잇기", "지난 방송 약속 기억나?"))
        self.assertFalse(carryover_answers(None, "지난 방송 약속 기억나?"))
        self.assertFalse(carryover_answers(note, None))

    def test_a_question_without_a_last_show_anchor_or_about_this_show_keeps_the_fallback(self) -> None:
        note = self.note(LINE)
        for question in (
            "[YouTube] 내가 아까 무슨 약속했지?", "내가 좋아하는 음식 투표했던 거 기억나?", "오늘 투표 결과 기억나?",
            "재대결 언제 해?", "누가 이겼어?", "완전 번거로운데 재대결 약속 기억나?",
            "지난 방송 말고 오늘 약속 기억나?", "저번 방송이랑 이번 방송 스코어 기억나?", "방금 지난 투표 기억나?",
        ):
            with self.subTest(question=question):
                self.assertFalse(carryover_answers(note, question))

    def test_a_viewer_fact_or_a_topic_the_line_does_not_hold_keeps_the_fallback(self) -> None:
        promise_only = self.note(render_carryover_line([("약속", "다음 방송에 재대결")]))
        for question in (
            "저번 방송에서 내가 키우는 고양이 기억나?", "지난 방송 때 내가 말한 생일 기억해?",
            "전에 내가 결정한 진로 기억나?", "지난 방송 투표 결과 뭐였어?", "지난 방송 스코어 기억나?",
            "지난 방송 기억나?", "지난 방송에서 내 취미 약속 기억나?",
        ):
            with self.subTest(question=question):
                self.assertFalse(carryover_answers(promise_only, question))
        self.assertFalse(carryover_answers(self.note(LINE), "지난 방송 투표 결과 뭐였어?"))
        vote = self.note(render_carryover_line([("투표 마감", "오후 9시 30분"), ("판결 기록", "짜장 61%")]))
        self.assertTrue(carryover_answers(vote, "지난 방송 투표 결과 뭐였어?"))
        self.assertFalse(carryover_answers(vote, "지난 방송 약속 기억나?"))
        # Labels are read from the last-show line only, never from this show's memo lines.
        current_memo = self.note("- 약속: 다음 방송에 재대결\n" + render_carryover_line([("결과", "첫 판 무승부")]))
        self.assertFalse(carryover_answers(current_memo, "지난 방송 약속 기억나?"))
        self.assertTrue(carryover_answers(current_memo, "지난 방송 누가 이겼어?"))
        self.assertFalse(carryover_answers(self.note("- 지난 방송 기억: 스태프가 직접 쓴 메모."), "지난 방송 약속 기억나?"))


if __name__ == "__main__":
    unittest.main()
