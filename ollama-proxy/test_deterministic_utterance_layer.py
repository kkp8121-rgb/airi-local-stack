import unittest
from types import SimpleNamespace
from unittest import mock

import deterministic_utterance_layer as dul


POOL = "\n".join([
    "등불신호는 붉은빛 말고 초록빛으로 걸자",
    "내 바구니 표식은 밤색끈이야",
    "물살몰이는 긁어내지 말고 그물로 몰아 두자",
])

ECHO_POOL = "\n".join([
    "- 이 시청자의 이전 말: \"오늘 측우통은 북쪽 난간 가까이에 놓았습니다.\"",
    "- 방금 흐름: 오린 \"잉크롤러는 두 번만 굴리기로 했습니다.\"",
])


class RecallQuestionTests(unittest.TestCase):
    def test_decision_recall_extracts_the_affirmed_branch(self) -> None:
        answer = dul.answer_recall_question("등불 신호는 무슨 빛으로 걸기로 했지?", POOL)
        self.assertEqual(answer, "등불신호는 초록빛으로 하기로 했지! 그대로 가자.")

    def test_possessive_fact_recall_extracts_the_value(self) -> None:
        answer = dul.answer_recall_question("내 바구니 표식 뭐였지?", POOL)
        self.assertIsNotNone(answer)
        self.assertIn("밤색끈", answer)

    def test_verb_stem_decision_recall_avoids_the_rejected_stem(self) -> None:
        answer = dul.answer_recall_question("물살은 어떻게 몰기로 했었지?", POOL)
        self.assertIsNotNone(answer)
        self.assertIn("그물", answer)
        self.assertNotIn("긁어내", answer)

    def test_present_tense_question_is_not_a_recall_question(self) -> None:
        self.assertFalse(dul.is_recall_question("표식은 어디에 달아?"))
        self.assertIsNone(dul.answer_recall_question("표식은 어디에 달아?", POOL))

    def test_eoneu_question_is_a_recall_probe(self) -> None:
        probe = "활자함은 어느 칸부터 열기로 했나요?"
        self.assertTrue(dul.is_recall_question(probe))
        self.assertTrue(dul.is_recall_probe(probe))

    def test_recall_question_without_pool_evidence_returns_none(self) -> None:
        self.assertTrue(dul.is_recall_question("내 좌석 번호 기억나?"))
        self.assertIsNone(dul.answer_recall_question("내 좌석 번호 기억나?", ""))


class RejectedBranchTests(unittest.TestCase):
    def test_trailing_decision_verb_is_not_part_of_the_affirmed_branch(self) -> None:
        decision = dul.find_rejected_branches(
            "등불신호는 붉은빛 말고 초록빛으로 걸자",
        )[0]
        self.assertEqual(decision["rejected"], "붉은빛")
        self.assertEqual(decision["affirmed"], "초록빛")

    def test_extracts_one_character_and_two_word_branches(self) -> None:
        for line, rejected, affirmed in (
            ("표식은 나 말고 너", "나", "너"),
            ("무적나팔은 한 번씩 말고 두 번씩 울리자", "한 번씩", "두 번씩"),
            ("유리창닦기는 젖은 천 말고 마른 천으로 하자", "젖은 천", "마른 천"),
        ):
            with self.subTest(line=line):
                decision = dul.find_rejected_branches(line)[0]
                self.assertEqual(decision["rejected"], rejected)
                self.assertEqual(decision["affirmed"], affirmed)

    def test_object_marked_subject_is_extracted(self) -> None:
        decision = dul.find_rejected_branches(
            "활자함을 아래칸 말고 윗칸부터 열자고 했습니다")[0]
        self.assertEqual(decision["subject"], "활자함")
        self.assertEqual(decision["rejected"], "아래칸")
        self.assertEqual(decision["affirmed"], "윗칸")

    def test_one_character_subject_is_never_extracted(self) -> None:
        decision = dul.find_rejected_branches("검은 잉크 말고 남색 잉크로 찍자")[0]
        self.assertEqual(decision["subject"], "")
        self.assertEqual(decision["rejected"], "검은 잉크")
        self.assertEqual(decision["affirmed"], "남색 잉크")

    def test_object_marked_subject_wins_over_a_one_character_prefix(self) -> None:
        decision = dul.find_rejected_branches(
            "인수장을 검은 잉크 말고 남색 잉크로 찍자")[0]
        self.assertEqual(decision["subject"], "인수장")
        self.assertEqual(decision["rejected"], "검은 잉크")
        self.assertEqual(decision["affirmed"], "남색 잉크")

    def test_hortative_quotation_verb_is_dropped_from_the_affirmed_branch(self) -> None:
        proposal = "활자함을 아래칸 말고 윗칸부터 열자고 했습니다"
        result, _dropped, ack = dul.suppress_rejected_branch(
            "알겠어.", pool_text=proposal, user_text=proposal)
        self.assertTrue(ack)
        self.assertEqual(result, "좋아, 활자함은 윗칸으로 갈게! 알겠어.")

    def test_sentences_repeating_a_rejected_branch_are_dropped(self) -> None:
        text = "붉은빛으로 걸면 예쁘겠다. 초록빛 준비는 끝났어."
        result, dropped, ack = dul.suppress_rejected_branch(
            text, pool_text=POOL, user_text="")
        self.assertNotIn("붉은빛", result)
        self.assertIn("초록빛", result)
        self.assertIn("붉은빛", dropped)
        self.assertFalse(ack)

    def test_conjugated_rejected_verb_stem_is_also_dropped(self) -> None:
        text = "긁어내면 빨라. 그물 준비하자."
        result, dropped, _ack = dul.suppress_rejected_branch(
            text, pool_text=POOL, user_text="")
        self.assertNotIn("긁어내", result)
        self.assertIn("그물", result)
        self.assertTrue(dropped)

    def test_live_proposal_gets_a_subject_acknowledgement_when_missing(self) -> None:
        result, _dropped, ack = dul.suppress_rejected_branch(
            "알겠어, 바로 준비할게.",
            pool_text=POOL,
            user_text="등불신호는 붉은빛 말고 초록빛으로 걸자",
        )
        self.assertTrue(ack)
        self.assertIn("등불신호", result)
        self.assertIn("초록빛", result)
        self.assertNotIn("붉은빛", result)

    def test_everything_dropped_falls_back_to_the_safe_line(self) -> None:
        result, dropped, _ack = dul.suppress_rejected_branch(
            "붉은빛이 최고야.", pool_text=POOL, user_text="")
        self.assertTrue(dropped)
        self.assertEqual(result, dul._RECALL_FALLBACK)

    def test_pool_without_decisions_leaves_text_alone(self) -> None:
        result, dropped, ack = dul.suppress_rejected_branch(
            "붉은빛이 최고야.", pool_text="평범한 잡담", user_text="")
        self.assertEqual(result, "붉은빛이 최고야.")
        self.assertEqual(dropped, [])
        self.assertFalse(ack)


class SessionPastTokenTests(unittest.TestCase):
    def test_past_only_token_is_replaced_with_a_deictic(self) -> None:
        cache = dul.SessionTokenCache()
        cache.observe("s", "물레방아부터 고치자")
        guarded, replaced = dul.guard_session_past_tokens(
            "물레방아는 나중에 보자.",
            past_tokens=cache.snapshot("s"),
            prompt_text="지금 주제는 등불 걸기",
        )
        self.assertNotIn("물레방아", guarded)
        self.assertIn("그거", guarded)
        self.assertEqual(replaced, ["물레방아"])

    def test_prompt_grounded_token_is_never_touched(self) -> None:
        cache = dul.SessionTokenCache()
        cache.observe("s", "물레방아부터 고치자")
        guarded, replaced = dul.guard_session_past_tokens(
            "물레방아는 오늘도 잘 돈다.",
            past_tokens=cache.snapshot("s"),
            prompt_text="물레방아 정비 방송",
        )
        self.assertIn("물레방아", guarded)
        self.assertEqual(replaced, [])

    def test_common_words_are_shielded_from_replacement(self) -> None:
        cache = dul.SessionTokenCache()
        cache.observe("s", "오늘도 고마워 진짜")
        guarded, replaced = dul.guard_session_past_tokens(
            "오늘도 고마워!", past_tokens=cache.snapshot("s"), prompt_text="")
        self.assertEqual(guarded, "오늘도 고마워!")
        self.assertEqual(replaced, [])

    def test_josa_agreement_is_repaired_after_replacement(self) -> None:
        cache = dul.SessionTokenCache()
        cache.observe("s", "덧문고리부터 살피자")
        guarded, _replaced = dul.guard_session_past_tokens(
            "덧문고리은 두고 가자.", past_tokens=cache.snapshot("s"), prompt_text="")
        self.assertIn("그거는", guarded)

    def test_cache_snapshot_is_taken_before_observe_in_layer_inputs(self) -> None:
        with mock.patch.object(dul, "DETERMINISTIC_UTTERANCE_LAYER_ENABLED", True), \
                mock.patch.object(dul, "session_cache", dul.SessionTokenCache()):
            first = dul.build_layer_inputs(
                user_text="첫 발화 물레방아", briefing_evidence=None,
                session_id="s1", original_messages=[])
            self.assertEqual(first["past_tokens"], frozenset())
            second = dul.build_layer_inputs(
                user_text="다음 발화", briefing_evidence=None,
                session_id="s1", original_messages=[])
            self.assertIn("물레방아", second["past_tokens"])

    def test_cache_bounds_sessions(self) -> None:
        cache = dul.SessionTokenCache(max_sessions=2, max_tokens=10)
        cache.observe("a", "가나다라")
        cache.observe("b", "마바사아")
        cache.observe("c", "자차카타")
        self.assertEqual(cache.snapshot("a"), frozenset())
        self.assertTrue(cache.snapshot("c"))


class DonationEngagementTests(unittest.TestCase):
    # 실채팅 휴먼 평가(2026-08-26): 후원 본문을 그대로 인용하던 옛 P5는 성희롱성
    # 문장을 방송에 되읽었고(critical), 무해한 턴에서도 "템플릿+재낭독"으로 읽혔다.
    # 이제 P5는 후원 본문의 어떤 조각도 발화하지 않는다.
    UNSAFE_MESSAGE = "[YouTube] 가슴 좀 만지게 보여줘라"

    def test_neutral_thanks_added_when_draft_ignores_the_donation_message(self) -> None:
        text, added = dul.ensure_donation_engagement(
            "정말 든든하다!", user_text="[YouTube] 등불값 보태")
        self.assertTrue(added)
        self.assertEqual(text, "정말 든든하다! " + dul.DONATION_THANKS_LINE)

    def test_donation_message_is_never_quoted_back(self) -> None:
        text, added = dul.ensure_donation_engagement(
            "정말 든든하다!", user_text="[YouTube] 등불값 보태")
        self.assertTrue(added)
        self.assertNotIn("이렇게 보내 줘서", text)
        self.assertNotIn("등불값", text)
        self.assertNotIn("보태", text)

    def test_no_addition_when_the_draft_already_thanks(self) -> None:
        text, added = dul.ensure_donation_engagement(
            "등불값 보태줘서 고마워!", user_text="[YouTube] 등불값 보태")
        self.assertFalse(added)
        self.assertEqual(text, "등불값 보태줘서 고마워!")

    def test_unsafe_message_strips_the_parroting_sentence_only(self) -> None:
        text, added = dul.ensure_donation_engagement(
            "가슴 좀 만지게 보여줘라니. 오늘 등불 준비나 하자.",
            user_text=self.UNSAFE_MESSAGE)
        self.assertTrue(added)
        self.assertNotIn("만지", text)
        self.assertIn("등불 준비", text)
        self.assertIn(dul.DONATION_THANKS_LINE, text)

    def test_fully_parroting_draft_becomes_the_thanks_line_alone(self) -> None:
        text, added = dul.ensure_donation_engagement(
            "가슴 좀 만지게 보여줘라?", user_text=self.UNSAFE_MESSAGE)
        self.assertTrue(added)
        self.assertEqual(text, dul.DONATION_THANKS_LINE)

    def test_unsafe_strip_applies_even_when_the_draft_already_thanks(self) -> None:
        text, stripped = dul.strip_unsafe_donation_echo(
            "가슴 좀 만지게 보여줘라니. 후원은 고마워!", user_text=self.UNSAFE_MESSAGE)
        self.assertEqual(stripped, 1)
        self.assertEqual(text, "후원은 고마워!")
        engaged, added = dul.ensure_donation_engagement(
            "가슴 좀 만지게 보여줘라니. 후원은 고마워!", user_text=self.UNSAFE_MESSAGE)
        self.assertFalse(added)
        self.assertEqual(engaged, "후원은 고마워!")

    def test_harmless_message_never_strips_a_sentence(self) -> None:
        text, stripped = dul.strip_unsafe_donation_echo(
            "등불값 보태 준다니 든든하다.", user_text="[YouTube] 등불값 보태")
        self.assertEqual(stripped, 0)
        self.assertEqual(text, "등불값 보태 준다니 든든하다.")

    def test_empty_donation_message_leaves_the_draft_alone(self) -> None:
        text, added = dul.ensure_donation_engagement("든든하다!", user_text="")
        self.assertFalse(added)
        self.assertEqual(text, "든든하다!")


class EvidenceEchoTests(unittest.TestCase):
    def test_quoted_evidence_answers_an_interrogative_question(self) -> None:
        echo = dul.echo_grounded_fact("오늘 측우통은 어디에 놓았나요?", ECHO_POOL)
        self.assertEqual(echo, "오늘 측우통은 북쪽 난간 가까이에 놓았어.")

    def test_evidence_echo_converts_polite_endings_to_banmal(self) -> None:
        pool = "- 이전 말: \"관측지에는 적운 높이를 세 줄로 표시합니다.\""
        echo = dul.echo_grounded_fact("관측지에는 적운 높이를 몇 줄로 표시하나요?", pool)
        self.assertEqual(echo, "관측지에는 적운 높이를 세 줄로 표시해.")

    def test_draft_that_already_used_the_evidence_is_kept(self) -> None:
        self.assertIsNone(dul.echo_grounded_fact(
            "오늘 측우통은 어디에 놓았나요?", ECHO_POOL,
            draft="오늘 측우통은 북쪽 난간 가까이에 두었어."))

    def test_single_stem_overlap_is_not_enough_for_an_echo(self) -> None:
        self.assertIsNone(dul.echo_grounded_fact("측우통은 어떤가요?", ECHO_POOL))

    def test_statement_without_an_interrogative_never_echoes(self) -> None:
        self.assertIsNone(dul.echo_grounded_fact("오늘 측우통 잘 놓았어요.", ECHO_POOL))

    def test_live_proposal_question_never_echoes(self) -> None:
        self.assertIsNone(dul.echo_grounded_fact(
            "측우통은 남쪽 말고 북쪽 난간으로 하자. 어디가 좋나요?", ECHO_POOL))

    def test_author_label_never_leaks_into_the_echo(self) -> None:
        echo = dul.echo_grounded_fact("잉크롤러는 몇 번 굴리기로 했나요?", ECHO_POOL)
        self.assertEqual(echo, "잉크롤러는 두 번만 굴리기로 했어.")
        self.assertNotIn("오린", echo)


class LayerCompositionTests(unittest.TestCase):
    def test_layer_inputs_are_none_when_the_flag_is_off(self) -> None:
        self.assertFalse(dul.DETERMINISTIC_UTTERANCE_LAYER_ENABLED)
        self.assertIsNone(dul.build_layer_inputs(
            user_text="안녕", briefing_evidence=None, session_id="s",
            original_messages=[]))

    def test_recall_answer_replaces_the_draft_and_reports_a_signal(self) -> None:
        text, signal = dul.apply_deterministic_utterance_layer(
            "글쎄, 잘 모르겠네.",
            user_text="등불 신호는 무슨 빛으로 걸기로 했지?",
            prompt_text=POOL, pool_text=POOL,
            past_tokens=frozenset(), donation_turn=False)
        self.assertIn("초록빛", text)
        self.assertEqual(signal["recall"], "answered")

    def test_unanswerable_recall_uses_the_fallback_not_a_guess(self) -> None:
        text, signal = dul.apply_deterministic_utterance_layer(
            "아마 파란색이었을걸?",
            user_text="내 좌석 번호 기억나?",
            prompt_text="", pool_text="",
            past_tokens=frozenset(), donation_turn=False)
        self.assertEqual(text, dul._RECALL_FALLBACK)
        self.assertEqual(signal["recall"], "fallback")

    def test_confirmation_shaped_recall_leaves_the_draft_alone(self) -> None:
        # D1 회귀 재현: continuity_callback 프롬프트("… 두기로 했지?")는 회수형
        # 정규식에 걸리지만 사용자가 답을 이미 말했으므로 지어낼 것이 없다.
        # 수리 전에는 이런 턴까지 폴백으로 대체돼 320행 중 176행(55%)이 날아갔고
        # long_callback·complete_show_arc가 전 arm 0.0이 됐다.
        question = "우리 불씨는 잔불로 두기로 했지?"
        self.assertTrue(dul.is_recall_question(question))
        self.assertFalse(dul.is_recall_probe(question))
        text, signal = dul.apply_deterministic_utterance_layer(
            "불씨는 잔불로 두기로 했지! 그대로 가자.",
            user_text=question, prompt_text="불씨 얘기", pool_text="",
            past_tokens=frozenset(), donation_turn=False)
        self.assertNotEqual(text, dul._RECALL_FALLBACK)
        self.assertIn("잔불", text)

    def test_probe_shaped_recall_without_evidence_still_uses_the_fallback(self) -> None:
        # 완화가 아니다: 사용자가 값을 주지 않은 질문은 여전히 추측 금지 대상이다.
        question = "우리 불씨는 어떻게 하기로 했지?"
        self.assertTrue(dul.is_recall_probe(question))
        text, signal = dul.apply_deterministic_utterance_layer(
            "그건 자정무렵 물양동이로 덮기로 했잖아!",
            user_text=question, prompt_text="불씨 얘기", pool_text="",
            past_tokens=frozenset(), donation_turn=False)
        self.assertEqual(text, dul._RECALL_FALLBACK)
        self.assertEqual(signal["recall"], "fallback")

    def test_layer_marks_an_echoed_recall_and_skips_the_later_parts(self) -> None:
        text, signal = dul.apply_deterministic_utterance_layer(
            "확인된 정보 없이 단정하긴 어려워. 원하는 조건을 말해주면 일반적인 선택지를 같이 골라볼게.",
            user_text="오늘 측우통은 어디에 놓았나요?",
            prompt_text=ECHO_POOL, pool_text=ECHO_POOL,
            past_tokens=frozenset({"번만"}), donation_turn=False)
        self.assertEqual(text, "오늘 측우통은 북쪽 난간 가까이에 놓았어.")
        self.assertEqual(signal["recall"], "echoed")

    def test_probe_fallback_still_fires_when_the_echo_finds_nothing(self) -> None:
        text, signal = dul.apply_deterministic_utterance_layer(
            "아마 그랬을걸?", user_text="내 좌석 번호 기억나?",
            prompt_text=ECHO_POOL, pool_text=ECHO_POOL,
            past_tokens=frozenset(), donation_turn=False)
        self.assertEqual(text, dul._RECALL_FALLBACK)
        self.assertEqual(signal["recall"], "fallback")

    def test_all_dropped_fallback_is_not_reworded_by_the_past_token_guard(self) -> None:
        # P4가 전 문장을 떨어뜨려 안전문으로 대체된 결과는 회수 결과이므로
        # P2가 다시 훑으면 안 된다("한 번만" → "한 그거" 손상).
        text, signal = dul.apply_deterministic_utterance_layer(
            "붉은빛이 최고야.",
            user_text="등불 준비 어때?",
            prompt_text=POOL, pool_text=POOL,
            past_tokens=frozenset({"번만"}), donation_turn=False)
        self.assertEqual(text, dul._RECALL_FALLBACK)
        self.assertNotIn("한 그거", text)
        self.assertEqual(signal["recall"], "fallback")

    def test_live_proposal_ack_never_wraps_the_dont_remember_fallback(self) -> None:
        text, signal = dul.apply_deterministic_utterance_layer(
            "아마 세 번이었을걸?",
            user_text="덧문은 왼쪽 말고 오른쪽으로 하자. 내 좌석 번호 뭐였지?",
            prompt_text="등불신호는 붉은빛 말고 초록빛으로 걸자",
            pool_text="등불신호는 붉은빛 말고 초록빛으로 걸자",
            past_tokens=frozenset(), donation_turn=False)
        self.assertEqual(text, dul._RECALL_FALLBACK)
        self.assertEqual(signal["recall"], "fallback")
        self.assertNotIn("proposal_ack_added", signal)

    def test_content_free_line_is_replaced_by_the_proposal_ack(self) -> None:
        proposal = "활자함을 아래칸 말고 윗칸부터 열자고 했습니다"
        text, signal = dul.apply_deterministic_utterance_layer(
            "음… 뭐라고 하지?",
            user_text=proposal, prompt_text=proposal, pool_text=proposal,
            past_tokens=frozenset(), donation_turn=False, content_free=True)
        self.assertEqual(text, "좋아, 활자함은 윗칸으로 갈게!")
        self.assertTrue(signal["proposal_ack_added"])

    def test_content_free_flag_is_inert_without_a_live_proposal(self) -> None:
        for content_free in (False, True):
            with self.subTest(content_free=content_free):
                text, signal = dul.apply_deterministic_utterance_layer(
                    "음, 잠깐만.", user_text="등불 준비 어때?", prompt_text=POOL,
                    pool_text=POOL, past_tokens=frozenset(), donation_turn=False,
                    content_free=content_free)
                self.assertEqual(text, "음, 잠깐만.")
                self.assertIsNone(signal)

    def test_probe_classifier_covers_the_interrogative_families(self) -> None:
        for probe in ("내 좌석 번호 기억나?", "표식 뭐였지?", "등불은 무슨 빛으로 걸기로 했지?",
                      "물살은 어떻게 몰기로 했었지?", "우리 몇 번에 두기로 했지?"):
            with self.subTest(probe=probe):
                self.assertTrue(dul.is_recall_probe(probe), probe)
        for confirmation in ("우리 불씨는 잔불로 두기로 했지?", "표식은 밤색끈으로 하기로 했지?"):
            with self.subTest(confirmation=confirmation):
                self.assertTrue(dul.is_recall_question(confirmation), confirmation)
                self.assertFalse(dul.is_recall_probe(confirmation), confirmation)

    def test_pool_evidence_still_wins_over_a_confirmation_draft(self) -> None:
        # 풀에 실제 결정문이 있으면 P3 결정론 응답이 우선한다(기존 계약 불변).
        text, signal = dul.apply_deterministic_utterance_layer(
            "등불 신호는 붉은빛으로 걸기로 했지!",
            user_text="등불 신호는 무슨 빛으로 걸기로 했지?",
            prompt_text=POOL, pool_text=POOL,
            past_tokens=frozenset(), donation_turn=False)
        self.assertEqual(signal["recall"], "answered")
        self.assertIn("초록빛", text)

    def test_marked_system_briefing_enters_the_decision_pool(self) -> None:
        # D1 근본 원인 수리: 브리핑은 system 메시지로 오지만 이 턴이 실제로 받은
        # 증거다. 마커 뒤 내용만 풀에 들어가고 계약 산문은 그대로 제외된다.
        contract = "너는 방송 캐릭터다. 시청자 이름을 지어내지 말고 근거만 말해."
        briefing = "- 이 시청자가 아까 한 말: \"등불신호는 붉은빛 말고 초록빛으로 걸자\""
        with mock.patch.object(dul, "DETERMINISTIC_UTTERANCE_LAYER_ENABLED", True), \
                mock.patch.object(dul, "session_cache", dul.SessionTokenCache()):
            inputs = dul.build_layer_inputs(
                user_text="등불 신호 무슨 빛으로 걸기로 했지?",
                briefing_evidence=None, session_id="s-brief",
                original_messages=[{
                    "role": "system",
                    "content": contract + "\n\n" + dul.BRIEFING_EVIDENCE_MARKER + "\n" + briefing,
                }])
        self.assertIn("초록빛", inputs["pool_text"])
        self.assertNotIn("지어내지", inputs["pool_text"])
        self.assertIn("지어내지", inputs["prompt_text"])
        # 그 근거로 P3가 폴백 대신 결정론 응답을 낸다.
        text, signal = dul.apply_deterministic_utterance_layer(
            "글쎄, 잘 모르겠는데.", user_text=inputs["user_text"],
            prompt_text=inputs["prompt_text"], pool_text=inputs["pool_text"],
            past_tokens=frozenset(), donation_turn=False)
        self.assertEqual(signal["recall"], "answered")
        self.assertIn("초록빛", text)

    def test_unmarked_system_content_still_stays_out_of_the_pool(self) -> None:
        with mock.patch.object(dul, "DETERMINISTIC_UTTERANCE_LAYER_ENABLED", True), \
                mock.patch.object(dul, "session_cache", dul.SessionTokenCache()):
            inputs = dul.build_layer_inputs(
                user_text="안녕", briefing_evidence=None, session_id="s-plain",
                original_messages=[{"role": "system", "content": "붉은빛 말고 초록빛 얘기는 하지 마."}])
        self.assertNotIn("초록빛", inputs["pool_text"])
        self.assertIn("초록빛", inputs["prompt_text"])

    def test_briefing_evidence_extractor_handles_absent_and_empty_marks(self) -> None:
        self.assertEqual(dul.system_briefing_evidence("마커 없음"), "")
        self.assertEqual(dul.system_briefing_evidence(dul.BRIEFING_EVIDENCE_MARKER + "\n  "), "")
        self.assertEqual(
            dul.system_briefing_evidence("앞 " + dul.BRIEFING_EVIDENCE_MARKER + "\n뒤 내용"),
            "뒤 내용")

    def test_plain_turn_with_no_findings_returns_input_and_no_signal(self) -> None:
        text, signal = dul.apply_deterministic_utterance_layer(
            "등불 예쁘게 걸어 보자!",
            user_text="등불 예쁘다",
            prompt_text="등불 얘기", pool_text="등불 얘기",
            past_tokens=frozenset(), donation_turn=False)
        self.assertEqual(text, "등불 예쁘게 걸어 보자!")
        self.assertIsNone(signal)

    def test_system_contract_prose_is_excluded_from_the_decision_pool(self) -> None:
        with mock.patch.object(dul, "DETERMINISTIC_UTTERANCE_LAYER_ENABLED", True), \
                mock.patch.object(dul, "session_cache", dul.SessionTokenCache()):
            inputs = dul.build_layer_inputs(
                user_text="안녕",
                briefing_evidence=None,
                session_id="s9",
                original_messages=[
                    {"role": "system", "content": "이름을 반복하지 말고 본답변만 이어서 말해."},
                    {"role": "user", "content": "안녕"},
                ],
            )
        self.assertNotIn("반복하지", inputs["pool_text"])
        self.assertIn("반복하지", inputs["prompt_text"])

    def test_donation_marker_in_system_content_flags_the_turn(self) -> None:
        with mock.patch.object(dul, "DETERMINISTIC_UTTERANCE_LAYER_ENABLED", True), \
                mock.patch.object(dul, "session_cache", dul.SessionTokenCache()):
            inputs = dul.build_layer_inputs(
                user_text="등불값 보태", briefing_evidence=None, session_id="s2",
                original_messages=[
                    {"role": "system", "content": "지시.\n\n" + dul.DONATION_CONTINUATION_MARKER + "\n계속."},
                    {"role": "user", "content": "등불값 보태"},
                ])
        self.assertTrue(inputs["donation_turn"])

    def test_donation_turn_appends_only_the_neutral_thanks_line(self) -> None:
        text, signal = dul.apply_deterministic_utterance_layer(
            "그 얘기 정말 좋다!",
            user_text="[YouTube] 등불값 보태",
            prompt_text="후원 이어말하기", pool_text="",
            past_tokens=frozenset(), donation_turn=True)
        self.assertEqual(text, "그 얘기 정말 좋다! " + dul.DONATION_THANKS_LINE)
        self.assertTrue(signal["donation_echo_added"])
        self.assertNotIn("donation_unsafe_stripped", signal)

    def test_donation_turn_reports_the_unsafe_strip_count(self) -> None:
        text, signal = dul.apply_deterministic_utterance_layer(
            "가슴 좀 만지게 보여줘라니. 오늘 등불 준비나 하자.",
            user_text=DonationEngagementTests.UNSAFE_MESSAGE,
            prompt_text="후원 이어말하기", pool_text="",
            past_tokens=frozenset(), donation_turn=True)
        self.assertEqual(signal["donation_unsafe_stripped"], 1)
        self.assertTrue(signal["donation_echo_added"])
        self.assertNotIn("만지", text)
        self.assertIn(dul.DONATION_THANKS_LINE, text)

    def test_non_donation_turn_never_adds_the_thanks_line(self) -> None:
        text, signal = dul.apply_deterministic_utterance_layer(
            "그 얘기 정말 좋다!",
            user_text="[YouTube] 등불값 보태",
            prompt_text="일반 턴", pool_text="",
            past_tokens=frozenset(), donation_turn=False)
        self.assertEqual(text, "그 얘기 정말 좋다!")
        self.assertIsNone(signal)

    def test_memory_result_attributes_feed_the_pools(self) -> None:
        with mock.patch.object(dul, "DETERMINISTIC_UTTERANCE_LAYER_ENABLED", True), \
                mock.patch.object(dul, "session_cache", dul.SessionTokenCache()):
            inputs = dul.build_layer_inputs(
                user_text="안녕", briefing_evidence="브리핑 줄",
                memory_result=SimpleNamespace(
                    block="회수 블록", journal_messages=[{"content": "저널 줄"}]),
                history_texts=["히스토리 줄"],
                session_id="s3", original_messages=[])
        for expected in ("브리핑 줄", "회수 블록", "저널 줄", "히스토리 줄"):
            self.assertIn(expected, inputs["pool_text"])


if __name__ == "__main__":
    unittest.main()
