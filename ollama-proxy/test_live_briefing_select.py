import asyncio
import os
import unittest
from unittest import mock

from live_briefing_select import (
    DEFAULT_COVERAGE,
    MAX_CANDIDATES,
    accept_early,
    best_index,
    briefing_coverage,
    candidate_budget,
    candidate_is_unfit,
    candidate_score,
    coverage_threshold,
    say_line,
    select_candidate,
)

CONTEXT_NOTE = (
    "[오늘 방송]\n- 주제: 첫 방송\n- 지금 구간: 목 이야기\n- 상황: 인사가 끝났다.\n"
    "- 주제에서 벗어난 채팅에는 짧게 반응하고 현재 주제로 돌아와.\n\n"
    "[턴 브리핑 — 방송 스태프가 주는 메모야. 자연스럽게 참고만 해.]\n"
    "- 이번 턴에 말할 것: 나아지긴커녕 오늘 자고 일어나니까 통증이 왼쪽 귀 안쪽까지 번져 있었어.\n"
    "- 이미 말한 것: 어제 녹음하다 목이 아팠다."
)
SAY = "나아지긴커녕 오늘 자고 일어나니까 통증이 왼쪽 귀 안쪽까지 번져 있었어."


class LiveBriefingSelectTests(unittest.TestCase):
    def test_budget_is_default_off_and_bounded(self) -> None:
        self.assertEqual(candidate_budget(""), 0)
        self.assertEqual(candidate_budget("1"), 0)
        self.assertEqual(candidate_budget("abc"), 0)
        self.assertEqual(candidate_budget("-3"), 0)
        self.assertEqual(candidate_budget("3"), 3)
        self.assertEqual(candidate_budget("99"), MAX_CANDIDATES)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(candidate_budget(), 0)

    def test_threshold_falls_back_outside_the_unit_interval(self) -> None:
        self.assertEqual(coverage_threshold(""), DEFAULT_COVERAGE)
        self.assertEqual(coverage_threshold("0.5"), 0.5)
        self.assertEqual(coverage_threshold("0"), DEFAULT_COVERAGE)
        self.assertEqual(coverage_threshold("1.5"), DEFAULT_COVERAGE)
        self.assertEqual(coverage_threshold("x"), DEFAULT_COVERAGE)

    def test_say_line_is_read_only_from_its_own_line(self) -> None:
        self.assertEqual(say_line(CONTEXT_NOTE), SAY)
        self.assertEqual(say_line("[오늘 방송]\n- 주제: 첫 방송"), "")
        self.assertEqual(say_line("앞 글자 - 이번 턴에 말할 것: 안 됨"), "")
        self.assertEqual(say_line(None), "")

    def test_coverage_rewards_the_briefed_fact_over_the_presupposed_one(self) -> None:
        followed_briefing = "아니, 오히려 오늘 자고 일어나니까 왼쪽 귀 안쪽까지 번져 있었어."
        followed_chat = "응, 어제보다 훨씬 나아졌어! 물 자주 마시고 있어."
        self.assertGreater(briefing_coverage(followed_briefing, SAY), 0.5)
        self.assertLess(briefing_coverage(followed_chat, SAY), 0.2)
        self.assertEqual(briefing_coverage("아무 말", ""), 0.0)

    def test_unfit_register_copy_label_and_lookup(self) -> None:
        self.assertTrue(candidate_is_unfit("오늘 귀까지 아팠어요!", SAY))
        self.assertTrue(candidate_is_unfit("어제 마라탕을 먹었다.", SAY))
        self.assertTrue(candidate_is_unfit("이번 턴에 말할 것: 귀가 아팠어.", SAY))
        self.assertTrue(candidate_is_unfit("[AIRI]는 귀가 아팠어.", SAY))
        self.assertTrue(candidate_is_unfit("궁금해서 검색해봤는데 그 캐릭터래.", SAY))
        self.assertFalse(candidate_is_unfit("궁금해서 검색해봤는데 그 캐릭터래.", "검색해봤는데 그 캐릭터래."))
        self.assertTrue(candidate_is_unfit("", SAY))
        self.assertFalse(candidate_is_unfit("아니, 오늘은 귀까지 번졌어. 진짜 황당하지?", SAY))

    def test_unfit_repeat_but_not_a_repeated_opener(self) -> None:
        previous = "아, 그래서 어제 저녁에 마라탕을 먹었는데 먹는 동안은 아픈 걸 잊었거든."
        self.assertTrue(candidate_is_unfit("응 어제 저녁에 마라탕을 먹었는데 먹는 동안은 아픈 걸 잊었거든!", SAY, previous))
        self.assertFalse(candidate_is_unfit("아, 그래서 오늘은 귀까지 번졌어.", SAY, previous))
        self.assertFalse(candidate_is_unfit("근데 오늘은 귀까지 번졌어.", SAY, previous))

    def test_pick_prefers_fit_then_coverage_and_keeps_draw_order_on_ties(self) -> None:
        scores = [(False, 0.9), (True, 0.2), (True, 0.4), (True, 0.4)]
        self.assertEqual(best_index(scores), 2)
        self.assertEqual(best_index([(False, 0.1), (False, 0.3)]), 1)
        self.assertTrue(accept_early((True, 0.3), 0.3))
        self.assertFalse(accept_early((False, 0.9), 0.3))
        self.assertFalse(accept_early((True, 0.29), 0.3))
        self.assertEqual(candidate_score("오늘 귀까지 아팠어요!", SAY)[0], False)

    def _select(self, first: str, drafts: list[str], say: str = SAY, budget: int = 3):
        queue = list(drafts)

        async def draw():
            text = queue.pop(0)
            return text, {"draft": text}

        return asyncio.run(select_candidate(
            first, draw, say=say, previous_reply="", budget=budget, threshold=DEFAULT_COVERAGE,
        ))

    def test_select_keeps_the_first_covering_draft_without_the_line(self) -> None:
        text, payload, unchosen, said = self._select(
            "응, 훨씬 나아졌어!", ["아니, 오늘 자고 일어나니까 왼쪽 귀 안쪽까지 번져 있었어.", "셋째"],
        )
        self.assertEqual(text, "아니, 오늘 자고 일어나니까 왼쪽 귀 안쪽까지 번져 있었어.")
        self.assertEqual(payload, {"draft": text})
        self.assertEqual(unchosen, [])
        self.assertFalse(said)

    def test_select_speaks_the_line_when_every_draft_fails(self) -> None:
        text, payload, unchosen, said = self._select("응, 훨씬 나아졌어!", ["응, 좋아졌어.", "물 마시고 있어."])
        self.assertTrue(said)
        self.assertEqual(text, SAY)
        # Both drawn payloads are accounted for: one may carry the metadata, the rest are unchosen.
        self.assertEqual(len(unchosen) + (payload is not None), 2)

    def test_select_never_reads_out_a_staff_note_line(self) -> None:
        staff_note = "오늘 자고 일어나니 통증이 왼쪽 귀 안쪽까지 번져 있었다."
        text, _, _, said = self._select("응, 훨씬 나아졌어!", ["응, 좋아졌어.", "물 마시고 있어."], say=staff_note)
        self.assertFalse(said)
        self.assertNotEqual(text, staff_note)


if __name__ == "__main__":
    unittest.main()
