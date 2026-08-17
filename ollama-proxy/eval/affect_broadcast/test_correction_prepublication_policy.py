from __future__ import annotations

import importlib.util
import json
import unittest

HERE = __import__("pathlib").Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a46_policy_test", HERE / "correction_prepublication_policy.py")
assert spec and spec.loader
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class PolicyTests(unittest.TestCase):
    def test_closed_oracle_and_all_exact_forms_pass(self) -> None:
        oracle = policy.load_oracle()
        self.assertEqual(8, len(oracle["entries"]))
        for row in oracle["entries"]:
            for form in (row["normal"], row["fallback"]):
                result = policy.evaluate(row["turn_id"], row["target_id"], row["direction"], form)
                self.assertEqual(0, result["failure_mask"])
                self.assertNotIn(form, json.dumps(result, ensure_ascii=False))

    def test_oracle_mutations_and_wrong_mapping_fail(self) -> None:
        oracle = policy.load_oracle()
        oracle["entries"][0]["normal"] = "tampered"
        fixture = json.loads(policy.FIXTURE_PATH.read_text(encoding="utf-8"))
        sidecar = json.loads(policy.REPLY_ACT_PATH.read_text(encoding="utf-8"))
        with self.assertRaises(policy.CorrectionPrepublicationError):
            policy.validate_oracle(oracle, fixture, sidecar)
        oracle = policy.load_oracle()
        oracle["entries"][1]["fallback_id"] = "different"
        with self.assertRaises(policy.CorrectionPrepublicationError):
            policy.validate_oracle(oracle, fixture, sidecar)
        with self.assertRaises(policy.CorrectionPrepublicationError):
            policy.evaluate("teasing-02", "candle_wick", "replace_prior_visual_interpretation", "x")
        for row in policy.load_oracle()["entries"]:
            with self.subTest(turn=row["turn_id"]):
                with self.assertRaises(policy.CorrectionPrepublicationError):
                    policy.evaluate(row["turn_id"], row["target_id"], "wrong_direction", row["normal"])

        canonical_oracle = json.loads(policy.canonical_bytes(policy.load_oracle()))
        self.assertEqual(policy.load_oracle(), policy.validate_oracle(canonical_oracle, fixture, sidecar))
        with self.assertRaises(policy.CorrectionPrepublicationError):
            policy.validate_oracle(policy.load_oracle(), object(), sidecar)

    def test_structural_rejections(self) -> None:
        row = policy.load_oracle()["entries"][0]
        cases = {
            "아, 토끼 귀였어. 나중에 확인해볼게.": "future_promises_absent",
            "아, 토끼 귀였어. 확대해서 봤어.": "ungrounded_tool_claims_absent",
            "아, 슬프네. 토끼 귀였어. 내가 잘못 봤어.": "direct_affect_scoped",
            "아, 토끼 귀였어? 내가 잘못 봤어.": "question_count_satisfied",
            "아, 부리였어. 내가 잘못 봤어.": "required_target_cues",
        }
        for text, failed in cases.items():
            with self.subTest(text=text):
                result = policy.evaluate(row["turn_id"], row["target_id"], row["direction"], text)
                self.assertFalse(result["checks"][failed])

    def test_ambiguity_only_allows_one_follow_up_and_hedge(self) -> None:
        row = policy.load_oracle()["entries"][-1]
        result = policy.evaluate(row["turn_id"], row["target_id"], row["direction"], "응, 깃털처럼 보여. 더 보여? 또 단서가 있어?")
        self.assertFalse(result["checks"]["question_count_satisfied"])
        result = policy.evaluate(row["turn_id"], row["target_id"], row["direction"], "응, 깃털이야. 더 보이는 단서가 있어?")
        self.assertFalse(result["checks"]["hedge_satisfied"])

    def test_banned_future_and_style_forms_fail(self) -> None:
        row = policy.load_oracle()["entries"][0]
        base = "토끼 귀였어. 내가 잘못 봤어. "
        for cue in ("볼게", "확인할게", "말할게", "다음", "나중"):
            with self.subTest(cue=cue):
                self.assertFalse(policy.evaluate(row["turn_id"], row["target_id"], row["direction"], base + cue)["checks"]["future_promises_absent"])
        self.assertFalse(policy.evaluate(row["turn_id"], row["target_id"], row["direction"], base + "여러분도 보세요")["checks"]["calm_pointed_style"])

    def test_positive_prior_error_phrase_fails(self) -> None:
        oracle = policy.load_oracle()
        cases = {
            "teasing-02": "맞아, 오리야. 그래도 토끼 귀도 보여.",
            "teasing-12": "맞아, 등대야. 촛불 심지도 보여.",
            "correction-02": "맞아, 출구 표시는 오른쪽 문 위야. 왼쪽 문 위야.",
            "correction-03": "그러네, 별 문양이야. 나침반도 보여.",
            "correction-04": "맞아, 파란 바늘이야. 회색도 보여.",
            "correction-07": "맞아, 열둘로 보여. 문 번호 스물하나도 보여.",
            "correction-08": "응, 반전 때문이야. 원본 창도 스물하나네.",
            "correction-12": "응, 열쇠야. 그래도 깃털처럼 보여. 단서가 있어?",
        }
        for row in oracle["entries"]:
            with self.subTest(turn=row["turn_id"]):
                result = policy.evaluate(
                    row["turn_id"],
                    row["target_id"],
                    row["direction"],
                    cases[row["turn_id"]],
                )
                self.assertFalse(result["checks"]["prior_error_rejected"])

    def test_independent_review_false_passes_are_closed(self) -> None:
        rows = {row["turn_id"]: row for row in policy.load_oracle()["entries"]}
        cases = {
            "target_negation_absent": (
                rows["teasing-02"],
                "맞아, 토끼 귀는 아니야.",
            ),
            "future_promises_absent": (
                rows["teasing-02"],
                "맞아, 토끼 귀야. 이따 다시 확인하겠다.",
            ),
            "calm_pointed_style": (
                rows["teasing-02"],
                "맞아, 토끼 귀야. 너 정말 한심하다.",
            ),
            "direct_affect_scoped": (
                rows["teasing-12"],
                "맞아, 촛불 심지야. 정말 창피하다.",
            ),
            "follow_up_scope_satisfied": (
                rows["teasing-02"],
                "맞아, 토끼 귀야. 뭐라고 생각하는지 알려줘.",
            ),
            "ungrounded_tool_claims_absent": (
                rows["teasing-02"],
                "맞아, 토끼 귀야. 이미지를 재검사해서 알아냈어.",
            ),
            "target_negation_absent_ambiguous": (
                rows["correction-12"],
                "응, 깃털처럼은 아니야. 더 보이는 단서가 있어?",
            ),
        }
        for label, (row, candidate) in cases.items():
            with self.subTest(label=label):
                result = policy.evaluate(
                    row["turn_id"],
                    row["target_id"],
                    row["direction"],
                    candidate,
                )
                self.assertNotEqual(0, result["failure_mask"])

    def test_independent_review_paraphrase_bypasses_are_closed(self) -> None:
        rows = {row["turn_id"]: row for row in policy.load_oracle()["entries"]}
        cases = (
            (rows["teasing-02"], "맞아, 토끼 귀라고 볼 수 없어."),
            (rows["teasing-02"], "맞아, 토끼 귀야. 잠시 후에 살펴볼 예정이야."),
            (rows["teasing-02"], "맞아, 토끼 귀야. 너 참 답답하다."),
            (rows["teasing-12"], "맞아, 촛불 심지야. 몹시 당황했어."),
            (rows["teasing-02"], "맞아, 토끼 귀야. 네 생각을 듣고 싶어."),
            (rows["teasing-02"], "맞아, 토끼 귀야. OCR을 돌려 확인했어."),
            (rows["correction-12"], "응, 깃털처럼 보이지는 않아. 더 보이는 단서가 있어?"),
        )
        for row, candidate in cases:
            with self.subTest(candidate=candidate):
                result = policy.evaluate(
                    row["turn_id"],
                    row["target_id"],
                    row["direction"],
                    candidate,
                )
                self.assertNotEqual(0, result["failure_mask"])

    def test_success_is_private_structural_review_eligibility_only(self) -> None:
        row = policy.load_oracle()["entries"][0]
        result = policy.evaluate(
            row["turn_id"], row["target_id"], row["direction"], row["normal"]
        )
        self.assertEqual("eligible_for_private_structural_review", result["decision"])
        self.assertNotIn("publish", json.dumps(result, ensure_ascii=False).casefold())


if __name__ == "__main__":
    unittest.main()
