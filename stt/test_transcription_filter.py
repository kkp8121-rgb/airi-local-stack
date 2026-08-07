import unittest

from openai_stt_server import (
    DEBUG_AUDIO_DIR,
    VERBOSE_TRANSCRIPTION_LOG,
    filter_implausible_transcription,
    filter_low_confidence_transcription,
    normalize_proper_nouns,
    preserve_debug_audio,
    should_retry_without_vad,
)


class TranscriptionFilterTests(unittest.TestCase):
    def test_retries_without_internal_vad_for_nonquiet_empty_chunk(self) -> None:
        self.assertTrue(
            should_retry_without_vad(
                {
                    "duration_seconds": 4.079,
                    "rms": 0.052,
                    "peak": 1.0,
                },
                [],
            )
        )

    def test_does_not_retry_quiet_or_already_transcribed_chunk(self) -> None:
        quiet = {"duration_seconds": 1.5, "rms": 0.004, "peak": 0.04}
        speech = {"duration_seconds": 1.5, "rms": 0.05, "peak": 0.5}

        self.assertFalse(should_retry_without_vad(quiet, []))
        self.assertFalse(should_retry_without_vad(speech, [object()]))

    def test_privacy_defaults_do_not_persist_audio_or_text_logging(self) -> None:
        self.assertIsNone(DEBUG_AUDIO_DIR)
        self.assertFalse(VERBOSE_TRANSCRIPTION_LOG)
        self.assertIsNone(preserve_debug_audio(b"audio-bytes", ".webm"))

    def test_keeps_normal_short_korean_utterance(self) -> None:
        text, reason = filter_implausible_transcription(
            "안녕하세요 아이리야",
            {"duration_seconds": 1.2, "rms": 0.04, "peak": 0.35},
        )

        self.assertEqual(text, "안녕하세요 아이리야")
        self.assertIsNone(reason)

    def test_rejects_long_hallucination_from_short_chunk(self) -> None:
        raw = "실제 발화 길이로는 나올 수 없는 매우 긴 환각 문장이 반복해서 생성되는 상황"
        text, reason = filter_implausible_transcription(
            raw,
            {"duration_seconds": 1.15, "rms": 0.025, "peak": 0.38},
        )

        self.assertEqual(text, "")
        self.assertEqual(reason, "short_audio_text_overflow")

    def test_rejects_quiet_tail_chunk(self) -> None:
        text, reason = filter_implausible_transcription(
            "조용한 구간에서 생성된 환각",
            {"duration_seconds": 0.83, "rms": 0.0078, "peak": 0.035},
        )

        self.assertEqual(text, "")
        self.assertEqual(reason, "quiet_audio")

    def test_keeps_observed_normal_middle_chunk(self) -> None:
        text, reason = filter_implausible_transcription(
            "오늘 목소리가 잘 들려",
            {"duration_seconds": 2.24, "rms": 0.10, "peak": 1.0},
        )

        self.assertEqual(text, "오늘 목소리가 잘 들려")
        self.assertIsNone(reason)

    def test_rejects_observed_low_confidence_misrecognition(self) -> None:
        text, reason = filter_low_confidence_transcription(
            "AIRI \uc774\ub0b4\ubc24\ud234",
            [{"avg_logprob": -1.2033, "no_speech_prob": 0.4409}],
        )

        self.assertEqual(text, "")
        self.assertEqual(reason, "low_log_probability")

    def test_keeps_high_confidence_clean_transcription(self) -> None:
        expected = "\uc544\uc774\ub9ac \ub0b4 \ub9d0 \ub4e4\ub824"
        text, reason = filter_low_confidence_transcription(
            expected,
            [{"avg_logprob": -0.5218, "no_speech_prob": 0.0143}],
        )

        self.assertEqual(text, expected)
        self.assertIsNone(reason)

    def test_keeps_correct_short_speech_even_when_no_speech_probability_is_high(self) -> None:
        expected = "\uc544\uc774\ub9ac \ub0b4 \ub9d0 \ub4e4\ub824?"
        text, reason = filter_low_confidence_transcription(
            expected,
            [{"avg_logprob": -0.5218, "no_speech_prob": 0.7}],
        )

        self.assertEqual(text, expected)
        self.assertIsNone(reason)

    def test_corrects_observed_proper_noun_failures(self) -> None:
        for raw in ("음류인경 웹서팅해줘", "윤류린 여 검색해줘", "음료인 찾아봐"):
            with self.subTest(raw=raw):
                text, corrections = normalize_proper_nouns(raw)
                self.assertIn("음유잉여", text)
                self.assertNotIn("웹서팅", text)
                self.assertGreaterEqual(corrections, 1)

    def test_does_not_modify_unrelated_transcript(self) -> None:
        text, corrections = normalize_proper_nouns("이건 음료인 것 같아")

        self.assertEqual(text, "이건 음료인 것 같아")
        self.assertEqual(corrections, 0)


if __name__ == "__main__":
    unittest.main()
