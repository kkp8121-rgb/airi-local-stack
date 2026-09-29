import asyncio
import os
import unittest
from unittest import mock

import live_briefing_select
from live_broadcast_runtime import BROADCAST_BRIEFING_HEADER
from live_briefing_select import (
    DEFAULT_COVERAGE,
    MAX_CANDIDATES,
    accept_early,
    accepted_word,
    best_index,
    briefing_coverage,
    candidate_budget,
    candidate_is_unfit,
    candidate_score,
    canon_say_line,
    canon_say_lines,
    coverage_threshold,
    required_word,
    say_line,
    select_candidate,
    show_say_lines,
    speakable_line,
    lead_line,
    lead_lines,
    with_canon_say_line,
    with_ruling,
    with_lead,
    without_do_not_say,
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

    def test_do_not_say_lines_are_removed_and_nothing_else(self) -> None:
        note = CONTEXT_NOTE + "\n- 아직 말하지 말 것: 병원, 진료 결과"
        self.assertEqual(without_do_not_say(note), CONTEXT_NOTE)
        self.assertEqual(without_do_not_say(CONTEXT_NOTE), CONTEXT_NOTE)

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

    def test_unfit_when_a_corrected_term_is_asserted_again(self) -> None:
        say = "아 설거지는 아니고 ㅋㅋ 꼴찌가 떡볶이 쏘기로 했거든."
        self.assertTrue(candidate_is_unfit("내가 설거지 벌칙 받았어! 그런데 친구가 떡볶이 사줬거든.", say))
        self.assertFalse(candidate_is_unfit("설거지는 아니고 꼴찌가 떡볶이 쐈어!", say))
        self.assertFalse(candidate_is_unfit(say, say))
        cold = "감기는 아니고, 어제 집에서 녹음하다가 목 위쪽이 아프기 시작했어."
        self.assertTrue(candidate_is_unfit("감기 기운도 있는 것 같아.", cold))
        self.assertFalse(candidate_is_unfit("감기가 아니라 어제 녹음하다 목이 아팠어.", cold))
        self.assertFalse(candidate_is_unfit("감기라기보다는 목이 좀 결린 느낌이야.", cold))
        # A one-syllable term ("불은 안 났어") is too ambiguous to police.
        self.assertFalse(candidate_is_unfit("불이 확 올라와서 놀랐어.", "아니 불은 안 났어 ㅋㅋ"))

    def test_unfit_when_the_viewer_is_answered_with_their_own_role(self) -> None:
        say = "고마워! 두 번째 방송인데 또 와 줘서 너무 반가워."
        self.assertTrue(candidate_is_unfit("ㅎㅇ 축하해! 두 번째 방송까지 와줘서 고마워.", say, "", "[YouTube] 두번째 방송 축하"))
        self.assertFalse(candidate_is_unfit("고마워! 또 와 줘서 반가워.", say, "", "[YouTube] 두번째 방송 축하"))
        self.assertTrue(candidate_is_unfit("오 첫방이라니 진짜 떨리겠다!", say, "", "[YouTube] 오 첫방이다 ㅎㅇㅎㅇ"))
        # A viewer who talks about their own state may be answered about it.
        self.assertFalse(candidate_is_unfit("내일 면접이라니 떨리겠다! 잘할 거야.", say, "", "[YouTube] 나 내일 면접이야"))
        self.assertFalse(candidate_is_unfit("합격 축하해!", say, "", "[YouTube] 나 합격했어"))

    def test_canon_line_answers_a_question_about_airis_body_or_offline_life(self) -> None:
        for chat, word in (
            ("[YouTube] 그럼 오늘 점심은 뭐 먹었어?", "밥"),
            ("[YouTube] 아니 ㅋㅋ 추천 말고 아이리가 뭐 먹었냐고", "밥"),
            ("[YouTube] 아이리 좋아하는 음식 뭐야?", "밥"),
            # 2026-09-29 real-path show T02: "먹고 켰어?" matched no meal word and got "저녁은 먹었지!".
            ("[YouTube] 아이리 저녁은 먹고 켰어?", "밥"),
            ("[YouTube] 아이리 밥 먹음?", "밥"),
            ("[YouTube] 아이리 어제 잘 잤어?", "잠"),
            # 2026-09-29 ep06: "몇 시에 일어났어?" matched no category and ended in a silence fallback.
            ("[YouTube] 아이리 오늘 몇 시에 일어났어?", "잠"),
            # 2026-09-29 ep04 T16: "피곤하지 않아?" had no line and ended in "음, 잠깐만.".
            ("[YouTube] 아이리는 오늘 어땠어? 피곤하지 않아?", ""),
            ("[YouTube] 아이리 감기 안 걸렸어?", ""),
            # 2026-09-29 ep05: advice to AIRI is no question but presupposes a body just the same
            # ("감기는 몸이 먼저 알아서 막아주니까 걱정하지 마.").
            ("[YouTube] 아이리 감기 조심해 요즘 유행이래", ""),
            ("[YouTube] 아이리 밥 꼭 챙겨 먹어", "밥"),
            ("[YouTube] 아이리 운동 좋아해?", "몸"),
            ("[YouTube] 아이리 어디 살아?", "방송"),
            ("[YouTube] 아이리는 주말에 뭐 했어?", "방송"),
        ):
            with self.subTest(chat=chat):
                self.assertIn(canon_say_line(chat), canon_say_lines(chat))
                self.assertGreaterEqual(len(canon_say_lines(chat)), 4)
                for line in canon_say_lines(chat):
                    self.assertIn(word, line)
                    self.assertFalse(candidate_is_unfit(line, line))
                    # 2026-09-25 user: "그냥 단순 버추얼이고 기계라 밥을 못먹는다가 이어지고 있어".
                    self.assertNotIn("버추얼이라", line)
                    self.assertFalse(line.endswith(("?", "？")))
        for chat in (
            "[YouTube] 나 오늘 점심 김치찌개 먹었어", "[YouTube] 점심 뭐 먹을까?", "[YouTube] 밥 먹고 올게",
            "[YouTube] 첫방 ㅊㅋ", "[YouTube] 다음 방송은 언제 해?", "",
            "[YouTube] 아이리 규칙 까먹었어?", "[YouTube] 아이리 나 밥 먹었어", "[YouTube] 감기 조심해 다들",
        ):
            with self.subTest(chat=chat):
                self.assertEqual(canon_say_line(chat), "")

    def test_a_referee_word_is_required_in_the_answer(self) -> None:
        # 2026-09-29 ep04 T09: "말으로 받을게." covered "…로 받을게." without the referee's word.
        note = BROADCAST_BRIEFING_HEADER + "\n- 심판 판정: 양말 유효, AIRI 차례\n- AIRI 낼 단어: 말씀\n- 이번 턴에 말할 것: 말씀으로 받을게."
        self.assertEqual(required_word(note), "말씀")
        self.assertEqual(required_word(CONTEXT_NOTE), "")
        say = say_line(note)
        self.assertTrue(candidate_is_unfit("말으로 받을게.", say, required="말씀"))
        self.assertFalse(candidate_is_unfit("양말 다음은 말씀으로 받을게.", say, required="말씀"))
        self.assertFalse(candidate_is_unfit("말으로 받을게.", say))
        # 2026-09-29 recheck: the word said as a refusal is not a move ("기차로는 차이로 못 넘어가겠다.").
        for line in ("기차로는 차이로 못 넘어가겠다. 이번엔 네 차례야.", "차이로는 막히네.", "차이는 안 되겠다."):
            with self.subTest(line=line):
                self.assertTrue(candidate_is_unfit(line, "차이로 받을게.", required="차이"))
        for line in ("기차 다음은 차이! 이로 이어 봐.", "음, 기차엔 차이로 할게. 이건 못 받겠지?"):
            with self.subTest(line=line):
                self.assertFalse(candidate_is_unfit(line, "차이로 받을게.", required="차이"))
        # 2026-09-29 ep06: the word hidden inside a longer word is no move ("본격적으로 받아 볼게").
        self.assertTrue(candidate_is_unfit("리본이면, 나는 본격적으로 받아 볼게.", "본격으로 받을게.", required="본격"))
        for line in ("리본엔 본격! 격으로 이어 봐.", "그럼 본격으로 받을게.", "본격이다, 격 차례야."):
            with self.subTest(line=line):
                self.assertFalse(candidate_is_unfit(line, "본격으로 받을게.", required="본격"))

        async def run(drafts: list[str]) -> tuple[str, bool]:
            queue = list(drafts[1:])

            async def draw() -> tuple[str, object | None]:
                return queue.pop(0), {"draw": len(queue)}

            dialogue, _, _, said = await select_candidate(
                drafts[0], draw, say=say, previous_reply="", budget=3, threshold=DEFAULT_COVERAGE, required="말씀",
            )
            return dialogue, said

        self.assertEqual(asyncio.run(run(["말으로 받을게.", "그럼 이걸로 받을게.", "음, 받을게."])), ("말씀으로 받을게.", True))
        self.assertEqual(asyncio.run(run(["말으로 받을게.", "양말엔 말씀으로 받을게!"])), ("양말엔 말씀으로 받을게!", False))

    def test_a_draft_that_refuses_the_word_the_referee_accepted_is_unfit(self) -> None:
        # 2026-09-29 ep07 T12: referee "람보르기니 유효", AIRI "람보로는 안 돼. 이번으로 받을게, 이제 네 차례다."
        note = (BROADCAST_BRIEFING_HEADER + "\n- 심판 판정: 람보르기니 유효, AIRI 차례\n- AIRI 낼 단어: 이번"
                "\n- 이번 턴에 말할 것: 이번으로 받을게.")
        self.assertEqual(accepted_word(note), "람보르기니")
        self.assertEqual(accepted_word(CONTEXT_NOTE), "")
        self.assertEqual(accepted_word(BROADCAST_BRIEFING_HEADER + "\n- 심판 판정: 기차 무효(이미 나옴), 다시"), "")
        say = say_line(note)
        for line in ("람보로는 안 돼. 이번으로 받을게, 이제 네 차례다.", "람보르기니는 무효야! 이번으로 받을게."):
            with self.subTest(line=line):
                self.assertTrue(candidate_is_unfit(line, say, required="이번", accepted="람보르기니"))
                self.assertFalse(candidate_is_unfit(line, say, required="이번"))
        for line in ("람보르기니 인정! 이번으로 받을게.", "람보르기니라니 어렵게 왔네. 이번으로 받을게.",
                     "이번으로 받을게. 이건 안 되겠지?"):
            with self.subTest(line=line):
                self.assertFalse(candidate_is_unfit(line, say, required="이번", accepted="람보르기니"))

    def test_a_ruling_asked_for_leads_the_answer(self) -> None:
        # 2026-09-29 ep07 T15: "션샤인 이거 되냐? 판정 ㄱ" was answered "인물로 받을게." with no ruling.
        self.assertEqual(with_ruling("인물로 받을게.", "션샤인"), "션샤인 인정! 인물로 받을게.")
        for ruled in ("션샤인 인정! 인물로 받을게.", "션샤인 유효야, 인물로 받을게.", "통과! 인물로 받을게."):
            with self.subTest(ruled=ruled):
                self.assertEqual(with_ruling(ruled, "션샤인"), ruled)
        self.assertEqual(with_ruling("인물로 받을게.", ""), "인물로 받을게.")

    def test_a_repeated_canon_question_does_not_get_the_same_line_again(self) -> None:
        # 2026-09-29 canon probe with candidates on: 30 of 36 answers were the same fixed line.
        live_briefing_select._recent_canon_lines.clear()
        chat = "[YouTube] 아이리 밥은 먹고 방송 켠 거임?"
        spoken = [say_line(with_canon_say_line(CONTEXT_NOTE.split("\n\n")[0], chat)) for _ in range(4)]
        self.assertEqual(len(set(spoken)), 4)
        self.assertTrue(set(spoken) <= set(canon_say_lines(chat)))
        # A briefing that already names a line keeps it and uses up nothing.
        self.assertEqual(with_canon_say_line(CONTEXT_NOTE, chat), CONTEXT_NOTE)

    def test_a_first_time_viewer_is_welcomed_before_the_answer(self) -> None:
        # 2026-09-29 ep07 T06: "처음 와봤는데 여기 무슨 방송이에요?" got the show's topic and no welcome.
        # A welcome say line then made AIRI say the welcome alone (newcomer probe), so it goes in front instead.
        live_briefing_select._recent_canon_lines.clear()
        chats = (
            "[YouTube] 처음 와봤는데 여기 무슨 방송이에요?", "[YouTube] 안녕하세요 처음 왔어요",
            "[YouTube] 뉴비입니다 ㅎㅇ", "[YouTube] 처음 뵙겠습니다",
        )
        spoken = [lead_line(chat) for chat in chats]
        self.assertEqual(len(set(spoken)), 4)
        for line in spoken:
            self.assertIn(line, lead_lines(chats[0]))
            self.assertFalse(candidate_is_unfit(line, line))
        for chat in ("[YouTube] 이 노래 처음 들어봐", "[YouTube] 저번에 처음 왔었는데 또 왔어", "[YouTube] 처음 보는 노래네", ""):
            with self.subTest(chat=chat):
                self.assertEqual(lead_lines(chat), ())
                self.assertEqual(lead_line(chat), "")
        # The note names nothing to say: the model answers the question itself.
        base = CONTEXT_NOTE.split("\n\n")[0]
        self.assertEqual(with_canon_say_line(base, chats[0]), base)
        answer = "채팅이 추천하는 노래로 끝말잇기를 하는 방송이야."
        self.assertEqual(with_lead(answer, "처음 왔구나, 반가워!"), "처음 왔구나, 반가워! " + answer)
        for welcomed in ("반가워, 첫 방문이네.", "뉴비구나, 반가워!", "어서 와! 여긴 끝말잇기 방송이야.", "와 줘서 고마워!"):
            with self.subTest(welcomed=welcomed):
                self.assertEqual(with_lead(welcomed, "처음 왔구나, 반가워!"), welcomed)
        self.assertEqual(with_lead("", "처음 왔구나, 반가워!"), "처음 왔구나, 반가워!")
        self.assertEqual(with_lead(answer, ""), answer)
        # A newcomer's question about AIRI's body keeps its canon line.
        chat = "[YouTube] 처음 왔는데 아이리 밥은 먹었어?"
        self.assertIn(say_line(with_canon_say_line(base, chat)), canon_say_lines(chat))

    def test_closing_and_next_show_chats_get_a_line_the_show_stands_behind(self) -> None:
        # 2026-09-29 ep07 closing with no briefing: "벌써 끝나?" ended in "음, 잠깐만." (grounding-off drafts
        # stalled: "어, 그건 잠깐 생각해 볼게.") and "다음 방송은 언제 해?" drafts invented "내일 저녁 8시" 4/4.
        live_briefing_select._recent_canon_lines.clear()
        closing = "[오늘 방송]\n- 주제: AIRI 일곱 번째 방송\n- 지금 구간: 마무리\n- 상황: 방송을 마무리한다."
        opening = "[오늘 방송]\n- 주제: AIRI 일곱 번째 방송\n- 지금 구간: 오프닝\n- 상황: 방송이 막 시작됐다."
        spoken = set()
        for chat in ("[YouTube] 벌써 끝나? ㅠㅠ 오늘 끝말잇기 재밌었는데", "[YouTube] 오늘 방송 여기까지야?",
                     "[YouTube] 오늘 재밌었다 담방 때 봐 ㅂㅂ", "[YouTube] 수고했어 아이리"):
            with self.subTest(chat=chat):
                line = say_line(with_canon_say_line(closing, chat))
                self.assertIn(line, show_say_lines(closing, chat))
                spoken.add(line)
                self.assertEqual(with_canon_say_line(opening, chat), opening)
        self.assertEqual(len(spoken), 4)
        for chat in ("[YouTube] 다음 방송은 언제 해?", "[YouTube] 담방 언제임?", "[YouTube] 다음 방송엔 뭐 해?",
                     "[YouTube] 방송 언제 또 해?"):
            for note in (opening, closing):
                with self.subTest(chat=chat, note=note[-12:]):
                    line = say_line(with_canon_say_line(note, chat))
                    self.assertIn("안 정해", line)
                    self.assertNotRegex(line, r"\d|내일|저녁|시에")
                    # A plan the operator gave is left to the model.
                    given = note + " 다음 방송은 금요일 저녁 8시에 한다."
                    self.assertEqual(with_canon_say_line(given, chat), given)
        for chat in ("[YouTube] 다음 방송 때 봐", "[YouTube] 오늘 방송 재밌다", "[YouTube] 끝말잇기 끝나면 뭐 해?"):
            with self.subTest(chat=chat):
                self.assertEqual(show_say_lines(opening, chat), ())
        for line in (*show_say_lines(closing, "[YouTube] 벌써 끝나?"), *show_say_lines(opening, "[YouTube] 담방 언제임?")):
            with self.subTest(line=line):
                self.assertFalse(candidate_is_unfit(line, line))
                self.assertFalse(line.endswith(("?", "？")))
        # The operator's own closing line stays.
        briefed = closing + "\n\n" + BROADCAST_BRIEFING_HEADER + "\n- 이번 턴에 말할 것: 오늘도 와 줘서 고마워."
        self.assertEqual(with_canon_say_line(briefed, "[YouTube] 벌써 끝나?"), briefed)

    def test_a_viewer_who_is_ill_hears_concern_before_the_answer(self) -> None:
        # 2026-09-29 ep07 T20: "나 오늘 감기 걸려서 목소리가 안 나와" -> "목소리가 안 나오면 끝말잇기는 잠시 쉬자."
        live_briefing_select._recent_canon_lines.clear()
        chats = (
            "[YouTube] 잠깐 끝말잇기 쉬고 ㅠ 나 오늘 감기 걸려서 목소리가 안 나와", "[YouTube] 머리 아파서 오늘은 눈팅만 할게",
            "[YouTube] 몸살 났어 ㅠ", "[YouTube] 어제 넘어져서 다쳤어",
        )
        spoken = [lead_line(chat) for chat in chats]
        self.assertEqual(len(set(spoken)), 4)
        for line in spoken:
            self.assertIn(line, lead_lines(chats[0]))
            self.assertNotIn(line, lead_lines("[YouTube] 처음 왔어요"))
            self.assertFalse(candidate_is_unfit(line, line))
        for chat in (
            "[YouTube] 감기 조심해 다들", "[YouTube] 이제 안 아파 다 나았어", "[YouTube] 아이리 아파?",
            "[YouTube] 우리 아파트 앞에 눈 왔어", "[YouTube] 아이리는 감기 안 걸려?",
        ):
            with self.subTest(chat=chat):
                self.assertEqual(lead_lines(chat), ())
        care = spoken[0]
        answer = "목소리가 안 나오면 끝말잇기는 잠시 쉬자."
        self.assertEqual(with_lead(answer, care), f"{care} {answer}")
        for cared in ("저런, 푹 쉬어.", "괜찮아? 오늘은 채팅만 해도 돼.", "아이고, 얼른 나아."):
            with self.subTest(cared=cared):
                self.assertEqual(with_lead(cared, care), cared)
        # A lead that is in no pool is never added.
        self.assertEqual(with_lead(answer, "아무 줄"), answer)

    def test_with_no_say_line_the_first_fit_draft_is_kept(self) -> None:
        async def run(drafts: list[str]) -> tuple[str, bool, int]:
            queue = list(drafts[1:])

            async def draw() -> tuple[str, object | None]:
                return queue.pop(0), {"draw": len(queue)}

            dialogue, _, _, said = await select_candidate(
                drafts[0], draw, say="", previous_reply="", budget=3, threshold=DEFAULT_COVERAGE,
            )
            return dialogue, said, len(queue)

        self.assertEqual(asyncio.run(run(["끝말잇기 하는 방송이야.", "안 쓰일 후보야."])), ("끝말잇기 하는 방송이야.", False, 1))
        self.assertEqual(
            asyncio.run(run(["끝말잇기 하는 방송이에요.", "끝말잇기 하는 방송이야.", "안 쓰일 후보야."])),
            ("끝말잇기 하는 방송이야.", False, 1),
        )

    def test_unfit_when_airi_claims_a_body_or_an_offline_life(self) -> None:
        # Answers the 2.3B generator gave on 2026-09-24 (series-01 broadcast 1 and its probes).
        for claim in (
            "오늘 점심에는 김치찌개 먹었어.", "오늘 점심은 아직 안 먹었는데, 첫 방송부터 하고 있어!",
            "어제는 첫 방송 준비하느라 일찍 잠들었어!", "방송 준비로 가볍게 스트레칭했어!",
            "방송 스튜디오에서 살고 있어!", "음... 나는 다양한 음식을 좋아해!",
            "나는 방송 밖에서 따로 살아. 여기서 너희랑 이야기하는 게 내 하루야.",
        ):
            with self.subTest(claim=claim):
                self.assertTrue(candidate_is_unfit(claim, ""))
        # A question to the viewer and a reaction to the viewer's own day are not AIRI's claims.
        self.assertFalse(candidate_is_unfit("너는 오늘 뭐 먹었어?", ""))
        self.assertFalse(candidate_is_unfit("너 떡볶이 먹었구나! 맛있었겠다.", ""))
        # A reaction/guess about the viewer's own day ("구나", "겠다") is not AIRI's bodily claim either,
        # even with no second-person word in the sentence (2026-09-25 false positive).
        self.assertFalse(candidate_is_unfit("산책 다녀왔구나, 강아지도 기분 좋았겠다.", ""))
        # Only the claim word itself running into 구나/겠 is a reaction; 죽겠다, 해야겠다 and 친구나 are not.
        for claim in (
            "아 배고파 죽겠다!", "배고파서 뭐 좀 먹어야겠다.", "나 어제 친구나 동생이랑 산책했어!",
            "나도 아까 떡볶이 먹었는데, 진짜 맛있었겠다.",
            # 2026-09-29 v4 canon probe drafts that passed the filter.
            "이제 막 깨어났는데 채팅이 벌써 열렸네.", "어제는 잠이 안 왔어.", "잠이 좀 부족했어.",
            "그래도 오늘 점심은 같이 먹자!", "오늘은 좀 피곤해.",
        ):
            with self.subTest(claim=claim):
                self.assertTrue(candidate_is_unfit(claim, ""))
        for line in ("피곤하면 푹 쉬어도 돼.", "너 오늘 피곤해 보여.", "다들 잠이 안 와서 모였구나."):
            with self.subTest(line=line):
                self.assertFalse(candidate_is_unfit(line, ""))

    def test_an_idiom_with_meogeot_is_not_a_meal(self) -> None:
        # 2026-09-26 handoff §5-5: "까먹었으면" (if you forgot) tripped the bodily rule's "먹었".
        for line in (
            "혹시 까먹었으면 내가 다시 말해 줄게.", "앗, 그거 완전 까먹었어!", "규칙을 잊어먹었네.",
            "그 말 듣고 좀 겁먹었어.", "오늘은 꼭 이기기로 마음먹었어!", "그 문제 푸느라 애먹었어.",
            "나 그 판정 때문에 욕먹었어!",
        ):
            with self.subTest(line=line):
                self.assertFalse(candidate_is_unfit(line, ""))
        self.assertTrue(candidate_is_unfit("나 아까 까먹고 간식 먹었어!", ""))

    def test_written_end_only_rejects_past_tense_narration(self) -> None:
        # Spoken present-tense declaratives are AIRI's natural persona speech, not copied staff notes
        # (2026-09-25 false positive found designing the competitive persona).
        self.assertFalse(candidate_is_unfit("2회전에서 바로 복수한다.", SAY))
        self.assertFalse(candidate_is_unfit("한 개파 반박 듣고 판결한다.", SAY))
        # Past-tense staff-note narration stays unfit, also without a bodily word.
        self.assertTrue(candidate_is_unfit("통증이 왼쪽 귀까지 번져 있었다.", SAY))
        # Spoken praise and a spoken groan end in 했다 too (2026-09-26 handoff §5-5: "고생했다").
        for line in ("오늘 진짜 고생했다!", "다들 수고했다.", "와, 그 설명 잘했다!", "아 이번 판은 망했다!"):
            with self.subTest(line=line):
                self.assertFalse(candidate_is_unfit(line, SAY))
        self.assertTrue(candidate_is_unfit("방송 전에 설거지를 했다.", SAY))

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

    def test_spoken_line_drops_trailing_laughter_and_gets_a_terminal_mark(self) -> None:
        self.assertEqual(speakable_line("난간 잡고 게처럼 내려왔어 ㅋㅋ"), "난간 잡고 게처럼 내려왔어.")
        self.assertEqual(speakable_line("후회는 없어 ㅋㅋㅋ ㅎㅎ"), "후회는 없어.")
        self.assertEqual(speakable_line("진짜 반가워!"), "진짜 반가워!")
        self.assertEqual(speakable_line("아 설거지는 아니고 ㅋㅋ 꼴찌가 쐈어"), "아 설거지는 아니고 ㅋㅋ 꼴찌가 쐈어.")
        text, _, _, said = self._select("응, 좋아졌어.", ["물 마시고 있어."], say=SAY.rstrip(".") + " ㅋㅋ", budget=2)
        self.assertTrue(said)
        self.assertEqual(text, SAY)

    def test_select_never_reads_out_a_staff_note_line(self) -> None:
        staff_note = "오늘 자고 일어나니 통증이 왼쪽 귀 안쪽까지 번져 있었다."
        text, _, _, said = self._select("응, 훨씬 나아졌어!", ["응, 좋아졌어.", "물 마시고 있어."], say=staff_note)
        self.assertFalse(said)
        self.assertNotEqual(text, staff_note)


if __name__ == "__main__":
    unittest.main()
