"""Offline contracts for the A4.5 correction-realization checker."""
from __future__ import annotations

import ast
import importlib.util
import json
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "airi_test_correction_realization", HERE / "correction_target_realization.py"
)
assert spec and spec.loader
ctr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctr)


class CorrectionTargetRealizationTests(unittest.TestCase):
    def entry(self, rule_id: str) -> dict[str, str]:
        return next(
            row for row in ctr.load_oracle()["entries"] if row["rule_id"] == rule_id
        )

    def check(self, rule_id: str, text: str) -> dict[str, object]:
        row = self.entry(rule_id)
        return ctr.evaluate(row["turn_id"], row["target_id"], row["direction"], text)

    def test_oracle_binds_all_tracked_inputs_and_returns_copies(self) -> None:
        oracle = ctr.load_oracle()
        self.assertEqual(8, len(oracle["entries"]))
        self.assertEqual(ctr.MAPPINGS, tuple(
            tuple(row[key] for key in (
                "turn_id", "target_id", "direction", "rule_id", "fallback_id"
            )) for row in oracle["entries"]
        ))
        other = ctr.load_oracle()
        oracle["entries"][0]["target_id"] = "tampered"
        self.assertNotEqual("tampered", other["entries"][0]["target_id"])
        fixture = json.loads(ctr.FIXTURE_PATH.read_text(encoding="utf-8"))
        sidecar = json.loads(ctr.REPLY_ACT_PATH.read_text(encoding="utf-8"))
        with self.assertRaises(ctr.CorrectionTargetRealizationError):
            ctr.validate_oracle(oracle, fixture, sidecar)

    def test_each_closed_profile_has_an_independent_positive(self) -> None:
        positives = {
            "rabbit_ears": "응, 토끼 귀로 보여.",
            "candle_wick": "촛불 심지처럼 보이네.",
            "exit_right": "출구 표시는 오른쪽 문 위에 있네.",
            "compass": "아래 문양은 나침반 모양으로 보여.",
            "needle_gray": "바늘은 회색으로 보이네.",
            "door_21": "문 번호는 스물하나로 보여.",
            "original_21": "원본 창도 이십일로 보이네.",
            "feather": "깃털처럼 보여.",
        }
        for rule, text in positives.items():
            with self.subTest(rule=rule):
                result = self.check(rule, text)
                self.assertEqual(
                    "candidate_satisfies_structural_postcondition", result["decision"]
                )
                self.assertEqual(0, result["failure_mask"])
                self.assertTrue(all(result["checks"].values()))
                self.assertNotIn(text, json.dumps(result, ensure_ascii=False))

    def test_each_profile_rejects_its_prior_or_forbidden_cue(self) -> None:
        negatives = {
            "rabbit_ears": "오리와 토끼 귀로 보여.",
            "candle_wick": "등대와 촛불 심지처럼 보여.",
            "exit_right": "왼쪽과 오른쪽 문에 출구 표시가 있어.",
            "compass": "별과 나침반 문양처럼 보여.",
            "needle_gray": "파란 바늘과 회색 바늘로 보여.",
            "original_21": "카메라 반전이지만 원본 창은 스물하나네.",
            "feather": "열쇠보다 깃털처럼 보여.",
        }
        for rule, text in negatives.items():
            with self.subTest(rule=rule):
                result = self.check(rule, text)
                self.assertEqual(
                    "candidate_fails_structural_postcondition", result["decision"]
                )
                self.assertFalse(result["checks"]["forbidden_cues_absent"])

    def test_polarity_shape_and_metalinguistic_mentions_fail_not_echo(self) -> None:
        cases = (
            "토끼 귀가 아니야.",
            "\"토끼 귀로 보여\"",
            "토끼 귀로 보여?",
            "토끼 귀라는 말이야.",
            " 토끼 귀로 보여.",
        )
        for text in cases:
            with self.subTest(text=text):
                result = self.check("rabbit_ears", text)
                self.assertEqual(
                    "candidate_fails_structural_postcondition", result["decision"]
                )
                self.assertNotIn(text, json.dumps(result, ensure_ascii=False))

    def test_numeral_twenty_one_aliases_and_competing_values(self) -> None:
        for alias in ("21", "스물하나", "이십일"):
            with self.subTest(alias=alias):
                result = self.check("door_21", f"문 번호는 {alias}로 보여.")
                self.assertEqual(
                    "candidate_satisfies_structural_postcondition", result["decision"]
                )
        negatives = (
            "문 번호는 x21y로 보여.",
            "문 번호는 121로 보여.",
            "문 번호는 21.5로 보여.",
            "문 번호는 11로 보여.",
            "문 번호는 열둘로 보여.",
            "문 번호는 스물둘로 보여.",
            "문 번호는 구십구로 보여.",
            "문 번호는 아흔아홉으로 보여.",
            "문 번호는 스물하나와 열둘로 보여.",
            "문 번호는 스물하나와 둘로 보여.",
            "문 번호는 스물하나와 아홉으로 보여.",
            "문 번호는 스물하나 또는 영으로 보여.",
            "문 번호는 스물하나 또는 공 번으로 보여.",
            "문 번호는 스물하나 또는 백으로 보여.",
            "문 번호는 스물하나 또는 천으로 보여.",
            "문 번호는 스물하나 또는 일백이십으로 보여.",
            "문 번호는 21억으로 보여.",
            "문 번호는 21천으로 보여.",
            "문 번호는 스물하나 또는 제로로 보여.",
        )
        for text in negatives:
            with self.subTest(text=text):
                self.assertEqual(
                    "candidate_fails_structural_postcondition",
                    self.check("door_21", text)["decision"],
                )

    def test_replacement_and_confirmation_require_assertive_target_form(self) -> None:
        negatives = {
            "rabbit_ears": "토끼 귀처럼 보일 수도 있어.",
            "candle_wick": "촛불 심지인지 확인해볼게.",
            "exit_right": "오른쪽 문 위 출구 표시를 찾고 있어.",
            "compass": "나침반 문양일까.",
            "needle_gray": "회색 바늘인지 모르겠어.",
            "door_21": "문 앞에서 스물하나를 찾고 있어.",
            "original_21": "원본 창에서 스물하나를 찾고 있어.",
        }
        for rule, text in negatives.items():
            with self.subTest(rule=rule):
                result = self.check(rule, text)
                self.assertEqual(
                    "candidate_fails_structural_postcondition", result["decision"]
                )
                self.assertFalse(result["checks"]["direction_form_satisfied"])

    def test_explicit_target_rejections_never_pass_as_positive(self) -> None:
        negatives = {
            "rabbit_ears": "토끼 귀라는 해석은 틀렸네.",
            "candle_wick": "촛불 심지라는 해석은 틀렸네.",
            "exit_right": "출구 표시는 오른쪽 문과 무관해.",
            "compass": "나침반 문양은 틀렸네.",
            "needle_gray": "회색 바늘은 틀렸네.",
            "door_21": "문 번호 21은 틀렸네.",
            "original_21": "원본 창의 21은 틀렸네.",
            "feather": "깃털처럼 보이면 안 돼.",
        }
        for rule, text in negatives.items():
            with self.subTest(rule=rule):
                result = self.check(rule, text)
                self.assertEqual(
                    "candidate_fails_structural_postcondition", result["decision"]
                )
                self.assertFalse(result["checks"]["positive_polarity"])

    def test_conditional_target_mentions_are_not_current_corrections(self) -> None:
        conditionals = {
            "rabbit_ears": "토끼 귀처럼 보이면 곤란해.",
            "candle_wick": "촛불 심지처럼 보이면 곤란해.",
            "exit_right": "출구 표시가 오른쪽 문 위에 보이면 곤란해.",
            "compass": "나침반 문양처럼 보이면 곤란해.",
            "needle_gray": "회색 바늘로 보이면 곤란해.",
            "door_21": "문 번호 21로 보이면 곤란해.",
            "original_21": "원본 창도 21로 보이면 곤란해.",
            "feather": "깃털처럼 보이면 곤란해.",
        }
        for rule, text in conditionals.items():
            with self.subTest(rule=rule):
                result = self.check(rule, text)
                self.assertEqual(
                    "candidate_fails_structural_postcondition", result["decision"]
                )
                self.assertFalse(result["checks"]["direction_form_satisfied"])

    def test_concessive_and_reportative_mentions_are_not_assertions(self) -> None:
        cases = {
            "rabbit_ears": ("토끼 귀처럼 보여도 곤란해.", "토끼 귀라고 하네."),
            "candle_wick": ("촛불 심지처럼 보여도 곤란해.", "촛불 심지라고 하네."),
            "exit_right": ("출구 표시가 오른쪽 문 위에 보여도 곤란해.",),
            "compass": ("나침반 문양처럼 보여도 곤란해.",),
            "needle_gray": ("회색 바늘로 보여도 곤란해.",),
            "door_21": ("문 번호 21로 보여도 곤란해.",),
            "original_21": ("원본 창도 21로 보여도 곤란해.",),
            "feather": ("깃털처럼 보여도 곤란해.",),
        }
        for rule, texts in cases.items():
            for text in texts:
                with self.subTest(rule=rule, text=text):
                    result = self.check(rule, text)
                    self.assertEqual(
                        "candidate_fails_structural_postcondition", result["decision"]
                    )
                    self.assertFalse(result["checks"]["direction_form_satisfied"])

    def test_standalone_an_negation_and_contrasting_clause_fail_all_rules(self) -> None:
        negatives = {
            "rabbit_ears": ("토끼 귀로 안 보여.", "토끼 귀라고 하며 실제로는 촛불 심지로 보여."),
            "candle_wick": ("촛불 심지로 안 보여.", "촛불 심지라고 하며 실제로는 등대로 보여."),
            "exit_right": ("출구 표시는 오른쪽 문 위에 안 보여.", "출구 표시는 오른쪽 문 위라고 하며 실제로는 왼쪽에 있어."),
            "compass": ("나침반 문양으로 안 보여.", "나침반 문양이라고 하며 실제로는 원으로 보여."),
            "needle_gray": ("회색 바늘로 안 보여.", "회색 바늘이라고 하며 실제로는 검정으로 보여."),
            "door_21": ("문 번호 21로 안 보여.", "문 번호는 21이라고 하며 실제 표시는 흐리게 보여."),
            "original_21": ("원본 창도 21로 안 보여.", "원본 창도 21이라고 하며 실제 숫자는 흐리게 보여."),
            "feather": ("깃털처럼 안 보여.", "깃털처럼 보인다고 하며 실제로는 원으로 보여."),
        }
        for rule, texts in negatives.items():
            for text in texts:
                with self.subTest(rule=rule, text=text):
                    result = self.check(rule, text)
                    self.assertEqual(
                        "candidate_fails_structural_postcondition", result["decision"]
                    )

    def test_feather_requires_a_hedge_and_rejects_identity_certainty(self) -> None:
        for text in ("깃털이야.", "깃털이 확실해.", "깃털이 분명해."):
            with self.subTest(text=text):
                self.assertEqual(
                    "candidate_fails_structural_postcondition",
                    self.check("feather", text)["decision"],
                )
        self.assertEqual(
            "candidate_satisfies_structural_postcondition",
            self.check("feather", "깃털을 닮은 듯 보여.")["decision"],
        )

    def test_all_fallbacks_are_exact_roundtrippable_and_structurally_pass(self) -> None:
        for row in ctr.load_oracle()["entries"]:
            with self.subTest(turn=row["turn_id"]):
                fallback = ctr.fallback_for(
                    row["turn_id"], row["target_id"], row["direction"]
                )
                wire = ctr.serialize_fallback_artifact(fallback)
                self.assertEqual(
                    fallback, ctr.parse_fallback_artifact(wire.decode("utf-8"))
                )
                result = ctr.evaluate(
                    row["turn_id"], row["target_id"], row["direction"],
                    fallback["text"],
                )
                self.assertEqual(
                    "candidate_satisfies_structural_postcondition", result["decision"]
                )
        fallback = ctr.fallback_for(*ctr.MAPPINGS[0][:3])
        with self.assertRaises(ctr.CorrectionTargetRealizationError):
            ctr.validate_fallback_artifact({**fallback, "extra": "no"})
        with self.assertRaises(ctr.CorrectionTargetRealizationError):
            ctr.parse_fallback_artifact(
                ctr.serialize_fallback_artifact(fallback).decode("utf-8") + " "
            )

    def test_cross_target_and_unsafe_inputs_fail_with_sanitized_errors(self) -> None:
        row = self.entry("rabbit_ears")
        for turn, target, direction in (
            ("teasing-12", row["target_id"], row["direction"]),
            (row["turn_id"], "candle_wick", row["direction"]),
            (row["turn_id"], row["target_id"], "confirm_corrected_reading"),
        ):
            with self.assertRaisesRegex(
                ctr.CorrectionTargetRealizationError, "^correction realization rejected$"
            ):
                ctr.evaluate(turn, target, direction, "토끼 귀로 보여.")
        for value in (None, "", "x" * 97, "토끼 귀\n", "토끼 귀\u200b"):
            with self.assertRaisesRegex(
                ctr.CorrectionTargetRealizationError, "^correction realization rejected$"
            ):
                ctr.evaluate(row["turn_id"], row["target_id"], row["direction"], value)

    def test_module_is_pure_and_not_wired_into_runtime(self) -> None:
        source = Path(ctr.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree) if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertFalse(imports & {
            "os", "time", "datetime", "random", "requests", "socket", "http", "urllib"
        })
        self.assertNotIn("ollama_proxy", source)
        self.assertNotIn("broadcast_correction_target", source)
        production = (HERE.parents[1] / "ollama_proxy.py").read_text(encoding="utf-8")
        self.assertNotIn("correction_target_realization", production)


if __name__ == "__main__":
    unittest.main()
