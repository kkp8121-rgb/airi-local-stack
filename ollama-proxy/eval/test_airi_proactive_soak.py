import unittest

from run_airi_proactive_soak import _score


class ProactiveSoakScoreTests(unittest.TestCase):
    def test_speaker_labels_fail_meta_gate(self) -> None:
        for output in (
            "사용자: 오늘 날씨 어때?",
            "너: 우주유영이라니!",
            '“AIRI: 이 토픽은 흥미롭네!”',
        ):
            with self.subTest(output=output):
                self.assertFalse(_score(output)["no_meta"])

    def test_ordinary_second_person_is_not_a_label(self) -> None:
        self.assertTrue(_score("너라면 이 발상이 꽤 재밌을 것 같아.")["no_meta"])

    def test_empty_short_or_questioning_output_fails(self) -> None:
        self.assertFalse(_score("")["non_empty"])
        self.assertFalse(_score("핵심 내용.")["minimum_12_chars"])
        self.assertFalse(_score("오늘 날씨 어때?")["no_question"])


if __name__ == "__main__":
    unittest.main()
