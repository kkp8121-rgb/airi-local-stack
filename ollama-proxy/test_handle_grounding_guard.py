import unittest

from handle_grounding_guard import (
    apply_handle_grounding_guard,
    build_grounding_context,
    build_grounding_pools,
    extract_vocative_targets,
    guard_invented_vocative,
)


class ExtractVocativeTargetsTests(unittest.TestCase):
    def test_finds_nim_suffixed_names_and_dedupes(self) -> None:
        self.assertEqual(
            extract_vocative_targets("민지님, 잘 지냈어? 민지님 오랜만이야!"),
            ["민지"],
        )
        self.assertEqual(extract_vocative_targets("배접천님 어서 와"), ["배접천"])

    def test_stopword_titles_are_not_treated_as_names(self) -> None:
        for text in ("여러분님", "시청자님 반가워요", "구독자분 고마워요", "손님 어서 오세요"):
            self.assertEqual(extract_vocative_targets(text), [], text)

    def test_no_match_without_the_honorific(self) -> None:
        # 실측 회귀: 회수된 이름의 대다수(53건 중 46건)는 일반 명사처럼
        # 쓰였고 vocative 접미사가 없다 — 이 함수는 의도적으로 그런 문장은
        # 잡지 않는다 (roster 없이 안전하게 구분할 방법이 없음).
        for text in ("배접천부터 꺼내야 해", "표제칸이야", "가장자리보강 순서대로"):
            self.assertEqual(extract_vocative_targets(text), [], text)

    def test_verb_endings_are_not_mistaken_for_names(self) -> None:
        self.assertEqual(extract_vocative_targets("정말 좋아, 오늘 방송 재밌었어"), [])


class GuardInventedVocativeTests(unittest.TestCase):
    def test_grounded_target_passes_through_untouched(self) -> None:
        text, signal = guard_invented_vocative("민지님, 아까 그 얘기 또 해줄까?", "민지가 어제 그 얘기를 했었지")
        self.assertEqual(text, "민지님, 아까 그 얘기 또 해줄까?")
        self.assertEqual(signal["checked"], ["민지"])
        self.assertEqual(signal["grounded"], ["민지"])
        self.assertEqual(signal["stripped"], [])

    def test_ungrounded_target_is_replaced_with_a_safe_address(self) -> None:
        text, signal = guard_invented_vocative("초코님, 반가워!", "")
        self.assertNotIn("초코님", text)
        self.assertIn("여러분", text)
        self.assertEqual(signal["checked"], ["초코"])
        self.assertEqual(signal["stripped"], ["초코"])

    def test_no_vocative_target_is_a_pure_no_op(self) -> None:
        text, signal = guard_invented_vocative("오늘 방송 재밌었지?", "")
        self.assertEqual(text, "오늘 방송 재밌었지?")
        self.assertEqual(signal, {"checked": [], "grounded": [], "stripped": []})


class BuildGroundingContextTests(unittest.TestCase):
    def test_joins_only_the_supplied_fragments(self) -> None:
        context = build_grounding_context(
            last_user_text="오늘 뭐 했어",
            memory_block="민지가 어제 케이크를 만들었다",
            journal_messages=[
                {"role": "user", "content": "초코는 고양이 이름이야"},
                {"role": "system", "content": "무시되어야 할 역할 아님"},
                "not-a-dict",
            ],
        )
        self.assertIn("오늘 뭐 했어", context)
        self.assertIn("민지가 어제 케이크를 만들었다", context)
        self.assertIn("초코는 고양이 이름이야", context)

    def test_empty_inputs_produce_empty_string(self) -> None:
        self.assertEqual(build_grounding_context(), "")


class BuildGroundingPoolsTests(unittest.TestCase):
    def test_disabled_by_default_returns_none_none(self) -> None:
        # 모듈 기본값: AIRI_HANDLE_GROUNDING_GUARD 미설정 -> off.
        import handle_grounding_guard as guard_module

        self.assertFalse(guard_module.HANDLE_GROUNDING_GUARD_ENABLED)
        pools = build_grounding_pools(
            last_user_text="x", briefing_evidence="y", memory_result=object(),
        )
        self.assertEqual(pools, (None, None))

    def test_disabled_never_touches_a_shapeless_memory_result(self) -> None:
        # 회귀 재현: off일 때도 호출부가 memory_result.block 을 먼저 꺼내
        # 넘기면, RetrievalResult가 아닌 자리표시자(mock/object())에서
        # AttributeError가 난다. build_grounding_pools 는 memory_result를
        # 그대로 받아, flag 확인 뒤에만 getattr로 읽어야 한다.
        import handle_grounding_guard as guard_module

        self.assertFalse(guard_module.HANDLE_GROUNDING_GUARD_ENABLED)
        pools = build_grounding_pools(
            last_user_text="x", briefing_evidence="y", memory_result=object(),
        )
        self.assertEqual(pools, (None, None))
        self.assertEqual(build_grounding_pools(last_user_text="x", briefing_evidence="y"), (None, None))

    def test_enabled_builds_both_pools(self) -> None:
        import handle_grounding_guard as guard_module

        class _StubMemoryResult:
            block = "기억 블록"
            journal_messages = [{"role": "assistant", "content": "저널 회수"}]

        original = guard_module.HANDLE_GROUNDING_GUARD_ENABLED
        guard_module.HANDLE_GROUNDING_GUARD_ENABLED = True
        try:
            full_context, memory_pool = build_grounding_pools(
                last_user_text="유저 발화",
                briefing_evidence="브리핑 증거",
                memory_result=_StubMemoryResult(),
            )
        finally:
            guard_module.HANDLE_GROUNDING_GUARD_ENABLED = original
        self.assertIn("유저 발화", full_context)
        self.assertIn("브리핑 증거", full_context)
        self.assertIn("기억 블록", full_context)
        self.assertIn("저널 회수", full_context)
        # memory_pool은 브리핑/유저 발화를 일부러 뺀다 — 그레이더가 이미 아는
        # 근거까지 다시 노출하지 않고, 새로 드러나는 memory/journal 증거만 준다.
        self.assertNotIn("유저 발화", memory_pool)
        self.assertNotIn("브리핑 증거", memory_pool)
        self.assertIn("기억 블록", memory_pool)
        self.assertIn("저널 회수", memory_pool)

    def test_enabled_with_no_memory_result_yields_empty_pools_not_a_crash(self) -> None:
        import handle_grounding_guard as guard_module

        original = guard_module.HANDLE_GROUNDING_GUARD_ENABLED
        guard_module.HANDLE_GROUNDING_GUARD_ENABLED = True
        try:
            full_context, memory_pool = build_grounding_pools(
                last_user_text="유저 발화", briefing_evidence=None, memory_result=None,
            )
        finally:
            guard_module.HANDLE_GROUNDING_GUARD_ENABLED = original
        self.assertEqual(full_context, "유저 발화")
        self.assertEqual(memory_pool, "")


class ApplyHandleGroundingGuardTests(unittest.TestCase):
    def test_empty_content_short_circuits(self) -> None:
        self.assertEqual(
            apply_handle_grounding_guard("", full_context="anything", memory_pool="anything"),
            ("", None),
        )

    def test_always_attaches_memory_pool_even_with_no_vocative_hit(self) -> None:
        # 재호명의 대다수(87%)는 vocative가 아니라 일반 명사 사용이었다 — 이
        # 신호는 vocative가 하나도 없는 턴에도 그레이더가 자체적으로 roster
        # 멤버십을 검사할 수 있도록 memory_pool을 항상 실어 보낸다.
        text, signal = apply_handle_grounding_guard(
            "배접천부터 꺼내야 해", full_context="", memory_pool="배접천이 회수된 기억 블록",
        )
        self.assertEqual(text, "배접천부터 꺼내야 해")
        self.assertEqual(signal["vocative_checked"], [])
        self.assertEqual(signal["memory_pool"], "배접천이 회수된 기억 블록")

    def test_ungrounded_vocative_is_stripped_and_signalled(self) -> None:
        text, signal = apply_handle_grounding_guard(
            "초코님, 반가워!", full_context="", memory_pool="",
        )
        self.assertNotIn("초코님", text)
        self.assertEqual(signal["vocative_stripped"], ["초코"])
        self.assertEqual(signal["memory_pool"], "")


if __name__ == "__main__":
    unittest.main()
