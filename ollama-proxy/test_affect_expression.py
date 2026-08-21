"""Unit tests for the content-free affect expression selector."""

from __future__ import annotations

from copy import deepcopy
import unittest

from affect_expression import (CONTRACT_KEYS, EXPRESSION_MODES,
                               EXPRESSION_SCHEMA_VERSION, PROMPT_CAP_BYTES,
                               SAFETY_TONES, render_affect_expression_contract,
                               select_affect_expression)
from affect_state import AffectValidationError, PRIMARY_VALUES, initial_state


class AffectExpressionTests(unittest.TestCase):
    def state(self, primary: str, **changes: object) -> dict[str, object]:
        value = initial_state()
        value["primary"] = primary
        value.update(changes)
        return value

    def test_every_primary_has_a_closed_meaningful_contract(self) -> None:
        expected = {
            "neutral": "neutral", "curious": "curious", "amused": "happy",
            "pleased": "happy", "proud": "happy", "embarrassed": "surprised",
            "skeptical": "think", "playful_annoyed": "angry", "concerned": "sad",
            "disappointed": "sad", "competitive": "angry", "relieved": "happy",
            "tired": "neutral",
        }
        for primary, expression in expected.items():
            with self.subTest(primary=primary):
                contract = select_affect_expression(self.state(primary))
                self.assertEqual(contract["mood_mode"], primary)
                self.assertEqual(contract["expression_mode"], expression)
                self.assertEqual(set(contract), CONTRACT_KEYS)
                self.assertEqual(contract["schema_version"], EXPRESSION_SCHEMA_VERSION)
                self.assertIn(contract["expression_mode"], EXPRESSION_MODES)
                self.assertIn(contract["safety_tone"], SAFETY_TONES)

    def test_question_drive_selects_wire_question_mode(self) -> None:
        contract = select_affect_expression(self.state("curious", drive="ask_back"))
        self.assertEqual(contract["expression_mode"], "question")
        self.assertEqual(contract["response_mode"], "ask_back")

    def test_selection_is_deterministic_and_does_not_mutate_input(self) -> None:
        state = self.state("proud", drive="celebrate", version=42)
        original = deepcopy(state)
        self.assertEqual(select_affect_expression(state), select_affect_expression(state))
        self.assertEqual(render_affect_expression_contract(state), render_affect_expression_contract(state))
        self.assertEqual(state, original)

    def test_emergency_conditions_override_to_careful_deescalation(self) -> None:
        for changes in ({"cause": "safety_override"}, {"drive": "deescalate"}):
            with self.subTest(changes=changes):
                contract = select_affect_expression(self.state("competitive", **changes))
                self.assertEqual(contract, {
                    "schema_version": EXPRESSION_SCHEMA_VERSION,
                    "mood_mode": "concerned", "expression_mode": "neutral",
                    "response_mode": "deescalate", "safety_tone": "careful",
                })
                self.assertIn("안전 우선", render_affect_expression_contract(self.state("competitive", **changes)))

    def test_moderation_uses_a_boundary_without_faking_an_emergency(self) -> None:
        state = self.state("competitive", cause="moderation_block", drive="deescalate")
        contract = select_affect_expression(state)
        self.assertEqual(contract, {
            "schema_version": EXPRESSION_SCHEMA_VERSION,
            "mood_mode": "concerned", "expression_mode": "neutral",
            "response_mode": "deescalate", "safety_tone": "boundary",
        })
        rendered = render_affect_expression_contract(state)
        self.assertIn("선을 짧고 분명하게", rendered)
        self.assertIn("119를 언급하지 말고", rendered)

    def test_playful_annoyed_is_witty_but_has_fixed_anti_hostility_directive(self) -> None:
        contract = select_affect_expression(self.state("playful_annoyed"))
        rendered = render_affect_expression_contract(self.state("playful_annoyed"))
        self.assertEqual((contract["expression_mode"], contract["safety_tone"]), ("angry", "light"))
        self.assertIn("한 단어를 비틀어", rendered)
        self.assertIn("재치 있게", rendered)
        self.assertIn("모욕·비하·위협은 금지", rendered)

    def test_renderer_is_bounded_and_does_not_copy_state_values_beyond_contract(self) -> None:
        for primary in PRIMARY_VALUES:
            with self.subTest(primary=primary):
                rendered = render_affect_expression_contract(
                    self.state(primary, version=9007199254740991),
                )
                self.assertLessEqual(len(rendered.encode("utf-8")), PROMPT_CAP_BYTES)
                self.assertNotIn("9007199254740991", rendered)
        safety = render_affect_expression_contract(
            self.state("competitive", cause="safety_override"),
        )
        self.assertLessEqual(len(safety.encode("utf-8")), PROMPT_CAP_BYTES)
        moderation = render_affect_expression_contract(
            self.state("competitive", cause="moderation_block", drive="deescalate"),
        )
        self.assertLessEqual(len(moderation.encode("utf-8")), PROMPT_CAP_BYTES)

    def test_invalid_state_is_rejected_fail_closed(self) -> None:
        invalid = self.state("not-a-mood")
        with self.assertRaises(AffectValidationError):
            select_affect_expression(invalid)
        with self.assertRaises(AffectValidationError):
            render_affect_expression_contract({"primary": "neutral"})


if __name__ == "__main__":
    unittest.main()
