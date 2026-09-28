import os
import unittest
from unittest import mock

from persona_temperament import TEMPERAMENT_CARD, temperament_enabled, with_temperament


class PersonaTemperamentTests(unittest.TestCase):
    def test_flag_parses_on_values_only(self) -> None:
        for value in ("on", "ON", "1", "true", "True", "  on  "):
            with self.subTest(value=value):
                self.assertTrue(temperament_enabled(value))
        for value in ("", "off", "0", "false", "yes", "2"):
            with self.subTest(value=value):
                self.assertFalse(temperament_enabled(value))

    def test_flag_reads_the_env_when_value_is_none(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(temperament_enabled())
            os.environ["AIRI_LIVE_PERSONA_TEMPERAMENT"] = "on"
            self.assertTrue(temperament_enabled())

    def test_card_begins_with_the_header(self) -> None:
        self.assertTrue(TEMPERAMENT_CARD.startswith("[AIRI 기질 — 반응 규칙]"))

    def test_card_keeps_the_cheek_warm_and_off_the_viewer(self) -> None:
        # 2026-09-25: "살짝 건방지다" plus judge frames made AIRI command and interrogate viewers
        # ("대 봐", "자수해", "처음 왔으면 규칙부터"); the user called it rude.
        self.assertNotIn("건방", TEMPERAMENT_CARD)
        for rule in ("반가워하고 고마워한다", "명령하거나 캐묻거나 훈계하거나 깎아내리지 않", "처음 온 시청자는 반갑게"):
            with self.subTest(rule=rule):
                self.assertIn(rule, TEMPERAMENT_CARD)

    def test_card_sets_a_calm_baseline_with_a_range_of_feelings(self) -> None:
        # 2026-09-28: "밝고 당당, 좋은 소식에 크게 기뻐하고 묻는다" produced lines that were all peaks and a question
        # after every answer; the user called the character shallow ("하이하이하이하이의 반복").
        for gone in ("크게 기뻐하고", "한 걸음 더 묻는다"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, TEMPERAMENT_CARD)
        for rule in ("느긋하고 담백", "느낌표와 감탄은 아껴", "감정에 결이 있다", "칭찬을 남발하지 않는다",
                     "캐묻지 않고 곁에 있어 준다"):
            with self.subTest(rule=rule):
                self.assertIn(rule, TEMPERAMENT_CARD)

    def test_with_temperament_prefixes_a_non_empty_context_note(self) -> None:
        note = "[오늘 방송]\n- 주제: 첫 방송"
        self.assertEqual(with_temperament(note), TEMPERAMENT_CARD + "\n\n" + note)

    def test_with_temperament_is_the_card_alone_when_the_note_is_empty(self) -> None:
        self.assertEqual(with_temperament(""), TEMPERAMENT_CARD)


if __name__ == "__main__":
    unittest.main()
