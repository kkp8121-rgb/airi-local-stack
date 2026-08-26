import os
import unittest
from unittest import mock

from pickup_batch import (
    MAX_PICKUP_SURFACE_CHARS,
    PickupBatchDecision,
    content_token_count,
    min_content_tokens,
    normalized_surface,
    pickup_batch_decision,
    pickup_batch_enabled,
    render_pickup_batch_line,
)


class PickupBatchTests(unittest.TestCase):
    def test_default_off_and_documented_switch_values(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(pickup_batch_enabled())
        for value in ("on", "true", "1", " TRUE "):
            self.assertTrue(pickup_batch_enabled(value))
        for value in ("yes", "off", "0", "enabled", None):
            self.assertFalse(pickup_batch_enabled(value))
        decision = pickup_batch_decision(["같아", "같아", "같아"])
        self.assertIsInstance(decision, PickupBatchDecision)
        self.assertFalse(decision.eligible)
        self.assertIsNone(decision.line)

    def test_content_tokens_strip_transport_prefixes_and_threshold_boundaries(self) -> None:
        text = "[YouTube] [12:34] 안녕 AIRI 2026!"
        self.assertEqual(content_token_count(text), 3)
        self.assertEqual(normalized_surface(text), "안녕 airi 2026!")
        messages = [text] * 3
        self.assertFalse(pickup_batch_decision(
            messages, enabled=True, minimum_content_tokens=4,
        ).eligible)
        decision = pickup_batch_decision(messages, enabled=True, minimum_content_tokens=3)
        self.assertTrue(decision.eligible)
        self.assertEqual(decision.content_tokens, 3)
        self.assertEqual(decision.consecutive_count, 3)

    def test_invalid_or_negative_threshold_environment_defaults_to_zero(self) -> None:
        for value in ("", "nope", "-1", "1.5"):
            with self.subTest(value=value), mock.patch.dict(
                    os.environ, {"AIRI_S4_MIN_CONTENT_TOKENS": value}, clear=True):
                self.assertEqual(min_content_tokens(), 0)
        with mock.patch.dict(os.environ, {"AIRI_S4_MIN_CONTENT_TOKENS": "2"}, clear=True):
            self.assertEqual(min_content_tokens(), 2)

    def test_exact_repeat_requires_three_consecutive_matches(self) -> None:
        self.assertFalse(pickup_batch_decision(
            ["[YouTube] 같은 말", "12:34 같은 말"], enabled=True,
        ).eligible)
        decision = pickup_batch_decision(
            ["[YouTube] 같은 말", "12:34 같은   말", "[00:12] 같은 말"], enabled=True,
        )
        self.assertTrue(decision.eligible)
        self.assertEqual(decision.consecutive_count, 3)

    def test_punctuation_and_different_messages_do_not_match(self) -> None:
        punctuated = pickup_batch_decision(
            ["같아!", "같아!", "같아?"], enabled=True,
        )
        self.assertEqual(punctuated.consecutive_count, 1)
        changed = pickup_batch_decision(
            ["같아", "다르지", "같아"], enabled=True,
        )
        self.assertEqual(changed.consecutive_count, 1)
        self.assertFalse(punctuated.eligible)
        self.assertFalse(changed.eligible)

    def test_batch_line_is_code_owned_clipped_and_safe_when_empty(self) -> None:
        decision = pickup_batch_decision(["같아"] * 3, enabled=True)
        self.assertEqual(decision.line, "다들 같아 하네")
        self.assertEqual(render_pickup_batch_line(""), "다들 그러네")
        clipped = render_pickup_batch_line("가" * (MAX_PICKUP_SURFACE_CHARS + 1))
        self.assertEqual(clipped, f"다들 {'가' * MAX_PICKUP_SURFACE_CHARS}… 하네")


if __name__ == "__main__":
    unittest.main()
