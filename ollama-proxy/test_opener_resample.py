import json
import os
import unittest
from unittest import mock

from opener_resample import (
    OPENER_RESAMPLE_TEMPERATURE,
    apply_resample_overrides,
    extract_seed,
    opener_resample_enabled,
    opener_words,
    previous_assistant_text,
    resample_overrides,
)


class OpenerResampleTests(unittest.TestCase):
    def test_gate_is_default_off_and_accepts_only_true_values(self) -> None:
        self.assertFalse(opener_resample_enabled(""))
        self.assertTrue(opener_resample_enabled("on"))
        self.assertTrue(opener_resample_enabled("TRUE"))
        self.assertFalse(opener_resample_enabled("off"))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(opener_resample_enabled())

    def test_words_and_previous_assistant_are_content_only(self) -> None:
        self.assertEqual(opener_words("Alpha, beta?"), ("alpha", "beta"))
        self.assertEqual(
            previous_assistant_text([
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "old"},
                {"role": "user", "content": "two"},
            ]),
            "old",
        )

    def test_matching_question_opener_returns_one_allowed_override(self) -> None:
        overrides = resample_overrides(
            "alpha beta?", "Alpha beta?", {"seed": 11}, enabled=True,
        )
        self.assertEqual(
            overrides,
            {"seed": 12, "temperature": OPENER_RESAMPLE_TEMPERATURE},
        )

    def test_mismatch_non_question_or_missing_seed_does_not_trigger(self) -> None:
        cases = (
            ("alpha beta?", "alpha gamma?", {"seed": 11}),
            ("alpha beta?", "alpha beta.", {"seed": 11}),
            ("alpha beta?", "alpha beta?", {}),
            ("alpha?", "alpha?", {"seed": 11}),
        )
        for previous, draft, payload in cases:
            with self.subTest(previous=previous, draft=draft):
                self.assertIsNone(resample_overrides(previous, draft, payload, enabled=True))

    def test_body_override_preserves_existing_options_and_sets_both_shapes(self) -> None:
        body = json.dumps({
            "model": "local",
            "seed": 11,
            "temperature": 0.45,
            "options": {"top_p": 0.9, "repeat_penalty": 1.05},
        }).encode()
        result = json.loads(apply_resample_overrides(
            body, {"seed": 12, "temperature": 0.9},
        ))
        self.assertEqual(result["seed"], 12)
        self.assertEqual(result["temperature"], 0.9)
        self.assertEqual(result["options"], {
            "top_p": 0.9,
            "repeat_penalty": 1.05,
            "seed": 12,
            "temperature": 0.9,
        })

    def test_extract_seed_rejects_bool_and_non_integer(self) -> None:
        self.assertEqual(extract_seed({"options": {"seed": 3}}), 3)
        self.assertIsNone(extract_seed({"seed": True}))
        self.assertIsNone(extract_seed({"seed": "3"}))


if __name__ == "__main__":
    unittest.main()
