import unittest

from foreground_context import (
    filter_journal_recall,
    parse_feedback_hygiene,
    project_foreground_context,
)


def _u(text: str) -> dict:
    return {"role": "user", "content": text}


def _a(text: str) -> dict:
    return {"role": "assistant", "content": text}


class ParseFeedbackHygieneTests(unittest.TestCase):
    def test_default_and_unknown_values_are_off(self) -> None:
        for value in ("", None, "off", "0", "false", "garbage"):
            self.assertEqual(parse_feedback_hygiene(value), "off", repr(value))

    def test_truthy_values_and_journal(self) -> None:
        for value in ("1", "true", "YES", " on "):
            self.assertEqual(parse_feedback_hygiene(value), "on", repr(value))
        self.assertEqual(parse_feedback_hygiene("journal"), "journal")


class ForegroundHygieneTests(unittest.TestCase):
    # 실측(run 05): 짧은 채팅 + 직전 AIRI 되묻기("?")는 매 턴 그 되묻기를 유지해
    # "음... 뭐가 X인데?" 붕괴를 되먹였다. off는 기존 동작 그대로여야 한다.
    ASK_BACK = [_u("뭐해"), _a("게임 고르는 중인데 뭐 볼래?"), _u("롤")]

    def test_off_keeps_the_short_answer_bridge_unchanged(self) -> None:
        expected = self.ASK_BACK
        self.assertEqual(project_foreground_context(self.ASK_BACK), expected)
        self.assertEqual(project_foreground_context(self.ASK_BACK, hygiene="off"), expected)
        self.assertEqual(project_foreground_context(self.ASK_BACK, hygiene="journal"), expected)
        # Returned entries stay the caller's objects.
        self.assertIs(project_foreground_context(self.ASK_BACK)[1], self.ASK_BACK[1])

    def test_on_drops_a_pair_whose_airi_turn_asks_back(self) -> None:
        self.assertEqual(project_foreground_context(self.ASK_BACK, hygiene="on"), [self.ASK_BACK[-1]])

    def test_on_keeps_a_declarative_bridge(self) -> None:
        dialogue = [_u("뭐해"), _a("롤 하는 중이야. 요즘 랭크 올리는 중"), _u("랭크 몇이야")]
        self.assertEqual(project_foreground_context(dialogue, hygiene="on"), dialogue)

    def test_on_drops_a_pair_whose_airi_turn_repeats_the_previous_opener(self) -> None:
        dialogue = [
            _u("오늘 뭐 먹었어"), _a("음... 뭐가 좋은데"),
            _u("김밥"), _a("음... 뭐가 김밥인데"),
            _u("그거 맛있어"),
        ]
        # 그거 bridges the newest pair, but its AIRI turn reuses the "음... 뭐가" opener.
        # (No "?" ending, so only the opener rule can drop it.)
        self.assertEqual(project_foreground_context(dialogue, hygiene="on"), [dialogue[-1]])

    def test_on_does_not_bridge_older_pairs_through_a_dropped_one(self) -> None:
        dialogue = [
            _u("롤 랭크 몇이야"), _a("골드야. 랭크는 요즘 안 올라"),
            _u("랭크 왜"), _a("랭크가 뭐가 문제인데?"),
            _u("랭크 말이야"),
        ]
        self.assertEqual(project_foreground_context(dialogue, hygiene="off"), dialogue)
        self.assertEqual(project_foreground_context(dialogue, hygiene="on"), [dialogue[-1]])

    def test_on_keeps_two_clean_bridged_pairs(self) -> None:
        dialogue = [
            _u("롤 랭크 몇이야"), _a("골드야. 랭크는 요즘 안 올라"),
            _u("랭크 왜"), _a("랭크는 시간이 없어서 못 돌려"),
            _u("랭크 말이야"),
        ]
        self.assertEqual(project_foreground_context(dialogue, hygiene="on"), dialogue)


class JournalRecallHygieneTests(unittest.TestCase):
    JOURNAL = [_u("어제 뭐 했어"), _a("어제는 방송 쉬었어?"), _u("왜")]

    def test_off_returns_the_same_object(self) -> None:
        self.assertIs(filter_journal_recall(self.JOURNAL, hygiene="off"), self.JOURNAL)
        self.assertIsNone(filter_journal_recall(None, hygiene="on"))

    def test_journal_and_on_drop_airi_rows_only(self) -> None:
        for mode in ("journal", "on"):
            self.assertEqual(
                filter_journal_recall(self.JOURNAL, hygiene=mode), [self.JOURNAL[0], self.JOURNAL[2]], mode,
            )


if __name__ == "__main__":
    unittest.main()
