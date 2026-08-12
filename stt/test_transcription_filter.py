import unittest
import asyncio
from pathlib import Path
from unittest.mock import patch
import numpy as np
import openai_stt_server as stt

from openai_stt_server import (
    BEAM_SIZE,
    COMPUTE_TYPE,
    DEBUG_AUDIO_DIR,
    MODEL_NAME,
    RECOVERY_BEAM_SIZE,
    VERBOSE_TRANSCRIPTION_LOG,
    build_hotwords,
    calculate_input_gain,
    health,
    filter_implausible_transcription,
    filter_low_confidence_transcription,
    frame_energy_stats,
    is_quiet_speech_candidate,
    is_allowed_origin,
    normalize_proper_nouns,
    prepare_audio_for_whisper,
    preserve_debug_audio,
    should_retry_rejected_transcription,
    should_retry_without_vad,
    validate_decoded_transcription,
)


class RuntimeDefaultTests(unittest.TestCase):
    def test_direct_and_launcher_defaults_match_scout_profile(self) -> None:
        launcher = Path(__file__).with_name("start-local-stt.ps1").read_text(encoding="utf-8")
        root_launcher = Path(__file__).parents[1].joinpath("start-airi-local-stack.ps1").read_text(encoding="utf-8")
        expected_model = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
        self.assertEqual((MODEL_NAME, COMPUTE_TYPE), (expected_model, "int8_float16"))
        self.assertIn(f"[string]$Model = '{expected_model}'", launcher)
        self.assertIn(f"[string]$SttModel = '{expected_model}'", root_launcher)
        self.assertIn("[string]$ComputeType = 'int8_float16'", launcher)
        self.assertIn("[string]$SttComputeType = 'int8_float16'", root_launcher)
        self.assertIn("$ComputeType = 'int8'", launcher)

    def test_primary_and_recovery_beams_are_intentionally_tiered(self) -> None:
        self.assertEqual(BEAM_SIZE, 1)
        self.assertEqual(RECOVERY_BEAM_SIZE, 3)

    def test_health_exposes_exact_runtime_and_beam_configuration(self) -> None:
        payload = asyncio.run(health())
        self.assertEqual(payload["model"], MODEL_NAME)
        self.assertEqual(payload["compute_type"], COMPUTE_TYPE)
        self.assertEqual(payload["primary_beam_size"], BEAM_SIZE)
        self.assertEqual(payload["recovery_beam_size"], RECOVERY_BEAM_SIZE)


class PreparedAudioTests(unittest.TestCase):
    def test_preparation_reuses_contiguous_decoded_samples_and_preserves_unamplified_audio(self) -> None:
        decoded = np.ascontiguousarray(np.array([0.1, -0.2, 0.3], dtype=np.float32))
        metrics = {"rms": 0.2, "peak": 0.3}
        prepared = prepare_audio_for_whisper(decoded, metrics)
        self.assertTrue(prepared.flags.c_contiguous)
        np.testing.assert_array_equal(prepared, decoded)
        self.assertEqual(metrics["input_gain"], 1.0)


class BeamDecodeTests(unittest.TestCase):
    def test_transcription_uses_primary_then_recovery_beam_without_changing_retry_contract(self) -> None:
        calls = []

        class Segment:
            start, end, text = 0.0, 0.1, "ok"
            avg_logprob, compression_ratio, no_speech_prob = -0.1, 1.0, 0.1

        class WhisperDouble:
            def transcribe(self, _audio, **options):
                calls.append(options)
                return iter([Segment()]), type("Info", (), {"language": "ko"})()

        metrics = {"duration_seconds": 1.0, "rms": 0.04, "peak": 0.4}
        with patch.object(stt, "whisper", WhisperDouble()):
            stt.transcribe_file(np.zeros(1600, dtype=np.float32), "ko", None, metrics)
            stt.transcribe_file(np.zeros(1600, dtype=np.float32), "ko", None, metrics, True)
        self.assertEqual(calls[0]["beam_size"], 1)
        self.assertEqual(calls[0]["best_of"], 1)
        self.assertTrue(calls[0]["vad_filter"])
        self.assertEqual(calls[1]["beam_size"], 3)
        self.assertEqual(calls[1]["best_of"], 3)
        self.assertFalse(calls[1]["vad_filter"])


class AdaptiveInputGainTests(unittest.TestCase):
    def test_boosts_observed_soft_speech_without_clipping(self) -> None:
        gain = calculate_input_gain(
            {"duration_seconds": 0.959, "rms": 0.010608, "peak": 0.120361}
        )

        self.assertGreater(gain, 3.7)
        self.assertLess(gain * 0.120361, 0.95)

    def test_leaves_normal_quiet_and_clipped_input_unchanged(self) -> None:
        cases = (
            {"rms": 0.0394, "peak": 0.4732},
            {"rms": 0.0052, "peak": 0.0451},
            {"rms": 0.0351, "peak": 1.0},
        )

        for metrics in cases:
            with self.subTest(metrics=metrics):
                self.assertEqual(calculate_input_gain(metrics), 1.0)

    def test_moderately_soft_speech_gets_bounded_gain(self) -> None:
        gain = calculate_input_gain({"rms": 0.025, "peak": 0.204})

        self.assertAlmostEqual(gain, 1.6)
        self.assertLessEqual(gain, 4.0)

    def test_boosts_low_rms_chunk_when_peak_still_indicates_speech(self) -> None:
        gain = calculate_input_gain({"rms": 0.006672, "peak": 0.08786})

        self.assertEqual(gain, 4.0)


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


class QuietSpeechRecoveryTests(unittest.TestCase):
    def test_frame_stats_have_only_numeric_shape_and_identify_sustained_soft_speech(self) -> None:
        # 0.5 s silence, then 0.5 s of quiet voiced energy: no lexical/audio content is kept.
        samples = np.concatenate((np.zeros(8000, dtype=np.float32), np.full(8000, 0.006, dtype=np.float32)))
        stats = frame_energy_stats(samples)
        self.assertEqual(set(stats), {"frame_rms_p50", "frame_rms_p90", "frame_rms_p95", "active_frame_count", "active_frame_fraction", "longest_active_run", "relative_energy"})
        self.assertTrue(all(isinstance(value, float) for value in stats.values()))
        metrics = {"duration_seconds": 1.0, "rms": 0.0042, "peak": 0.006, **stats}
        self.assertTrue(is_quiet_speech_candidate(metrics))
        self.assertTrue(should_retry_without_vad(metrics, []))

    def test_rejects_flat_noise_click_and_too_short_quiet_audio(self) -> None:
        cases = (
            np.full(16000, 0.004, dtype=np.float32),
            np.pad(np.full(400, 0.02, dtype=np.float32), (0, 15600)),
        )
        for samples in cases:
            with self.subTest(samples=samples.size):
                stats = frame_energy_stats(samples)
                metrics = {"duration_seconds": 1.0, "rms": 0.004, "peak": 0.04, **stats}
                self.assertFalse(is_quiet_speech_candidate(metrics))
        stats = frame_energy_stats(np.concatenate((np.zeros(1600), np.full(1600, 0.006))).astype(np.float32))
        self.assertFalse(is_quiet_speech_candidate({"duration_seconds": 0.2, "rms": 0.004, "peak": 0.006, **stats}))

    def test_strict_quiet_recovery_accepts_only_plausible_confident_non_speech_decode(self) -> None:
        stats = frame_energy_stats(
            np.concatenate((np.zeros(8000, dtype=np.float32), np.full(8000, 0.006, dtype=np.float32)))
        )
        metrics = {"duration_seconds": 1.0, "rms": 0.004, "peak": 0.04, **stats}
        text, reason, _, _ = validate_decoded_transcription("hello", [{"avg_logprob": -0.4, "no_speech_prob": 0.2}], metrics, True)
        self.assertEqual(text, "hello")
        self.assertIsNone(reason)
        # A single bounded band rescues the observed quiet -1.20 decode, without lowering
        # the normal -1.0 threshold used by non-quiet audio.
        text, reason, _, _ = validate_decoded_transcription("hello", [{"avg_logprob": -1.20, "no_speech_prob": 0.2}], metrics, True)
        self.assertEqual(text, "hello")
        self.assertIsNone(reason)
        for segments, expected in (([{"avg_logprob": -1.30, "no_speech_prob": 0.2}], "quiet_recovery_low_log_probability"), ([{"avg_logprob": -0.4, "no_speech_prob": 0.7}], "quiet_recovery_no_speech")):
            with self.subTest(expected=expected):
                _, reason, _, _ = validate_decoded_transcription("hello", segments, metrics, True)
                self.assertEqual(reason, expected)
        _, reason, _, _ = validate_decoded_transcription("x" * 50, [{"avg_logprob": -0.4, "no_speech_prob": 0.2}], metrics, True)
        self.assertEqual(reason, "short_audio_text_overflow")

    def test_rejects_impossible_decoder_timing_without_inflating_evidence(self) -> None:
        metrics = {"duration_seconds": 2.939, "rms": 0.004, "peak": 0.04}
        text, reason, _, dropped = validate_decoded_transcription(
            "hello",
            [{"start": 0.0, "end": 29.98, "text": "hello", "avg_logprob": -1.2, "no_speech_prob": 0.2}],
            metrics,
            True,
        )

        self.assertEqual(text, "")
        self.assertEqual(reason, "timing_invalid")
        self.assertEqual(dropped, 0)
        self.assertEqual(metrics["timing_invalid_segment_count"], 1)
        self.assertTrue(metrics["timing_invalid"])

    def test_quiet_recovery_rejects_low_confidence_no_speech_and_flat_noise(self) -> None:
        sustained = frame_energy_stats(
            np.concatenate((np.zeros(8000, dtype=np.float32), np.full(8000, 0.006, dtype=np.float32)))
        )
        quiet_speech = {"duration_seconds": 1.0, "rms": 0.004, "peak": 0.04, **sustained}
        for segment, expected in (
            ({"avg_logprob": -1.26, "no_speech_prob": 0.2}, "quiet_recovery_low_log_probability"),
            ({"avg_logprob": -1.2, "no_speech_prob": 0.61}, "quiet_recovery_no_speech"),
        ):
            with self.subTest(expected=expected):
                _, reason, _, _ = validate_decoded_transcription("hello", [segment], quiet_speech.copy(), True)
                self.assertEqual(reason, expected)
        flat = frame_energy_stats(np.full(16000, 0.004, dtype=np.float32))
        _, reason, _, _ = validate_decoded_transcription(
            "hello", [{"avg_logprob": -1.2, "no_speech_prob": 0.2}],
            {"duration_seconds": 1.0, "rms": 0.004, "peak": 0.04, **flat}, True,
        )
        self.assertEqual(reason, "quiet_recovery_frame_gate")

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

    def test_rejects_observed_broadcast_subtitle_hallucination(self) -> None:
        for raw in (
            "자막 제공 및 광고를 포함하고 있습니다.",
            "  자막  제공 및 광고를 포함하고 있습니다!  ",
            "자막 제공 및 광고를 포함합니다",
        ):
            with self.subTest(raw=raw):
                text, reason = filter_implausible_transcription(
                    raw,
                    {"duration_seconds": 2.879, "rms": 0.0121, "peak": 0.0699},
                )

                self.assertEqual(text, "")
                self.assertEqual(reason, "known_whisper_hallucination")

    def test_keeps_a_real_sentence_that_only_mentions_the_blocked_phrase(self) -> None:
        raw = "영상에 자막 제공 및 광고를 포함하고 있습니다라고 적혀 있어"
        text, reason = filter_implausible_transcription(
            raw,
            {"duration_seconds": 5.0, "rms": 0.04, "peak": 0.35},
        )

        self.assertEqual(text, raw)
        self.assertIsNone(reason)

    def test_keeps_observed_normal_middle_chunk(self) -> None:
        text, reason = filter_implausible_transcription(
            "오늘 목소리가 잘 들려",
            {"duration_seconds": 2.24, "rms": 0.10, "peak": 1.0},
        )

        self.assertEqual(text, "오늘 목소리가 잘 들려")
        self.assertIsNone(reason)

    def test_rejects_observed_low_confidence_misrecognition(self) -> None:
        text, reason, dropped = filter_low_confidence_transcription(
            "AIRI 이내밤툴",
            [{"avg_logprob": -1.2033, "no_speech_prob": 0.4409}],
        )

        self.assertEqual(text, "")
        self.assertEqual(reason, "low_log_probability")
        self.assertEqual(dropped, 1)

    def test_keeps_high_confidence_clean_transcription(self) -> None:
        expected = "아이리 내 말 들려"
        text, reason, dropped = filter_low_confidence_transcription(
            expected,
            [{"avg_logprob": -0.5218, "no_speech_prob": 0.0143}],
        )

        self.assertEqual(text, expected)
        self.assertIsNone(reason)
        self.assertEqual(dropped, 0)

    def test_keeps_correct_short_speech_even_when_no_speech_probability_is_high(self) -> None:
        expected = "아이리 내 말 들려?"
        text, reason, dropped = filter_low_confidence_transcription(
            expected,
            [{"avg_logprob": -0.5218, "no_speech_prob": 0.7}],
        )

        self.assertEqual(text, expected)
        self.assertIsNone(reason)
        self.assertEqual(dropped, 0)

    def test_corrects_observed_proper_noun_failures(self) -> None:
        for raw in (
            "음류인경 웹서팅해줘",
            "윤류린 여 검색해줘",
            "음료인 찾아봐",
            "유행렬 웹에서 검색해",
        ):
            with self.subTest(raw=raw):
                text, corrections = normalize_proper_nouns(raw)
                self.assertIn("음유잉여", text)
                self.assertNotIn("웹서팅", text)
                self.assertGreaterEqual(corrections, 1)

    def test_does_not_modify_unrelated_transcript(self) -> None:
        text, corrections = normalize_proper_nouns("이건 음료인 것 같아")

        self.assertEqual(text, "이건 음료인 것 같아")
        self.assertEqual(corrections, 0)

    def test_maplestory_vocabulary_bias_does_not_rewrite_apple_store(self) -> None:
        hotwords = build_hotwords()

        for expected in ("메이플스토리", "메이플 스토리", "넥슨", "게임"):
            with self.subTest(expected=expected):
                self.assertIn(expected, hotwords)

        text, corrections = normalize_proper_nouns("애플 스토리에 들렀어")
        self.assertEqual(text, "애플 스토리에 들렀어")
        self.assertEqual(corrections, 0)


class VadFallbackDeadBandTests(unittest.TestCase):
    """F1 regression: chunks observed in the audit must all qualify for the VAD fallback."""

    def test_rescues_observed_chunks_that_fell_between_the_quiet_and_fallback_gates(
        self,
    ) -> None:
        observed = (
            {"duration_seconds": 1.159, "rms": 0.00889, "peak": 0.0932},
            {"duration_seconds": 0.899, "rms": 0.012, "peak": 0.10},
            {"duration_seconds": 0.5, "rms": 0.05, "peak": 0.6},
        )

        for metrics in observed:
            with self.subTest(metrics=metrics):
                self.assertTrue(should_retry_without_vad(metrics, []))

    def test_rescues_short_confirmation_utterance(self) -> None:
        self.assertTrue(
            should_retry_without_vad(
                {"duration_seconds": 0.42, "rms": 0.03, "peak": 0.4},
                [],
            )
        )

    def test_still_skips_chunks_below_the_minimum_duration(self) -> None:
        self.assertFalse(
            should_retry_without_vad(
                {"duration_seconds": 0.2, "rms": 0.05, "peak": 0.6},
                [],
            )
        )

    def test_fallback_eligibility_matches_the_quiet_gate(self) -> None:
        """A chunk the hallucination filter would accept must never be denied a retry."""
        borderline = {"duration_seconds": 1.0, "rms": 0.00889, "peak": 0.0932}

        self.assertTrue(should_retry_without_vad(borderline, []))
        text, reason = filter_implausible_transcription("응 들려", borderline)
        self.assertEqual(text, "응 들려")
        self.assertIsNone(reason)


class RejectedDecodeRecoveryTests(unittest.TestCase):
    def test_retries_nonquiet_implausible_decode(self) -> None:
        metrics = {"duration_seconds": 1.319, "rms": 0.0181, "peak": 0.1335}

        self.assertTrue(
            should_retry_rejected_transcription("implausible_text_rate", metrics)
        )
        self.assertTrue(
            should_retry_rejected_transcription("short_audio_text_overflow", metrics)
        )
        self.assertTrue(
            should_retry_rejected_transcription("low_log_probability", metrics)
        )

    def test_does_not_retry_quiet_or_empty_transcription(self) -> None:
        quiet = {"duration_seconds": 1.319, "rms": 0.0052, "peak": 0.0451}
        speech = {"duration_seconds": 1.319, "rms": 0.0181, "peak": 0.1335}

        self.assertFalse(
            should_retry_rejected_transcription("implausible_text_rate", quiet)
        )
        self.assertFalse(
            should_retry_rejected_transcription("empty_transcription", speech)
        )
        self.assertFalse(
            should_retry_rejected_transcription(
                "known_whisper_hallucination", speech
            )
        )


class SegmentConfidenceTests(unittest.TestCase):
    """F2 regression: a single bad segment must not erase the whole utterance."""

    def test_keeps_confident_segments_and_drops_only_the_bad_one(self) -> None:
        text, reason, dropped = filter_low_confidence_transcription(
            "아이리 오늘 날씨 어때 쿠쿠쿠쿠",
            [
                {"avg_logprob": -0.31, "text": "아이리 오늘 날씨 어때", "no_speech_prob": 0.02},
                {"avg_logprob": -1.24, "text": "쿠쿠쿠쿠", "no_speech_prob": 0.31},
            ],
        )

        self.assertEqual(text, "아이리 오늘 날씨 어때")
        self.assertIsNone(reason)
        self.assertEqual(dropped, 1)

    def test_rejects_only_when_every_segment_is_low_confidence(self) -> None:
        text, reason, dropped = filter_low_confidence_transcription(
            "쿠쿠쿠쿠 라라라",
            [
                {"avg_logprob": -1.24, "text": "쿠쿠쿠쿠", "no_speech_prob": 0.31},
                {"avg_logprob": -1.51, "text": "라라라", "no_speech_prob": 0.44},
            ],
        )

        self.assertEqual(text, "")
        self.assertEqual(reason, "low_log_probability")
        self.assertEqual(dropped, 2)

    def test_rejects_when_the_surviving_segments_carry_no_text(self) -> None:
        text, reason, dropped = filter_low_confidence_transcription(
            "쿠쿠쿠쿠",
            [
                {"avg_logprob": -0.4, "text": "   ", "no_speech_prob": 0.02},
                {"avg_logprob": -1.24, "text": "쿠쿠쿠쿠", "no_speech_prob": 0.31},
            ],
        )

        self.assertEqual(text, "")
        self.assertEqual(reason, "low_log_probability")
        self.assertEqual(dropped, 1)


class ProperNounScopeTests(unittest.TestCase):
    """F3 regression: search aliases must stay inside the search query."""

    def test_does_not_rewrite_drinks_mentioned_away_from_the_search_query(self) -> None:
        for raw in (
            "음료인 것 같은데 검색해줘",
            "그 음료인 것 같아 나중에 검색해줘",
            "이 음료인지 찾아봐",
        ):
            with self.subTest(raw=raw):
                text, corrections = normalize_proper_nouns(raw)
                self.assertEqual(text, raw)
                self.assertEqual(corrections, 0)

    def test_still_rewrites_a_search_alias_inside_the_search_query(self) -> None:
        text, corrections = normalize_proper_nouns("음료인 검색해줘")

        self.assertEqual(text, "음유잉여 검색해줘")
        self.assertEqual(corrections, 1)

    def test_does_not_rewrite_an_alias_embedded_in_a_longer_word(self) -> None:
        text, corrections = normalize_proper_nouns("음류인경우를 검색해줘")

        self.assertEqual(text, "음류인경우를 검색해줘")
        self.assertEqual(corrections, 0)


class EmptyTranscriptionTests(unittest.TestCase):
    """F5 regression: an empty transcription is not a passing filter result."""

    def test_filters_pass_empty_text_through_without_a_reason(self) -> None:
        text, reason = filter_implausible_transcription(
            "",
            {"duration_seconds": 1.2, "rms": 0.04, "peak": 0.35},
        )

        self.assertEqual(text, "")
        self.assertIsNone(reason)

        text, reason, dropped = filter_low_confidence_transcription(
            "",
            [{"avg_logprob": -0.5, "no_speech_prob": 0.1}],
        )

        self.assertEqual(text, "")
        self.assertIsNone(reason)
        self.assertEqual(dropped, 0)


class CharacterBudgetBoundaryTests(unittest.TestCase):
    """F6 regression: the character budget has to grow monotonically with duration."""

    def test_keeps_slow_speech_just_below_the_old_step_boundary(self) -> None:
        raw = "아이리 오늘 날씨가 어떤지 좀 알려줄 수 있을까"
        self.assertEqual(len("".join(raw.split())), 19)

        text, reason = filter_implausible_transcription(
            raw,
            {"duration_seconds": 1.49, "rms": 0.04, "peak": 0.35},
        )

        self.assertEqual(text, raw)
        self.assertIsNone(reason)

    def test_budget_never_shrinks_as_duration_grows(self) -> None:
        raw = "아이리 오늘 날씨가 어떤지 좀 알려줄 수 있을까"
        accepted_at = []
        for duration in (1.40, 1.45, 1.49, 1.51, 1.60, 2.00):
            text, reason = filter_implausible_transcription(
                raw,
                {"duration_seconds": duration, "rms": 0.04, "peak": 0.35},
            )
            accepted_at.append(reason is None)

        self.assertEqual(accepted_at, sorted(accepted_at))
        self.assertTrue(all(accepted_at))

    def test_still_rejects_the_observed_hallucination_samples(self) -> None:
        samples = (
            (
                "실제 발화 길이로는 나올 수 없는 매우 긴 환각 문장이 반복해서 생성되는 상황",
                1.15,
                "short_audio_text_overflow",
            ),
            (
                "시청해주셔서 감사합니다 구독과 좋아요 부탁드립니다 다음 영상에서 만나요",
                1.49,
                "implausible_text_rate",
            ),
            (
                "이 영상이 도움이 되셨다면 구독과 좋아요 알림 설정까지 부탁드리겠습니다 감사합니다",
                2.10,
                "implausible_text_rate",
            ),
        )

        for raw, duration, expected_reason in samples:
            with self.subTest(raw=raw):
                text, reason = filter_implausible_transcription(
                    raw,
                    {"duration_seconds": duration, "rms": 0.04, "peak": 0.35},
                )

                self.assertEqual(text, "")
                self.assertEqual(reason, expected_reason)


class OriginAllowlistTests(unittest.TestCase):
    """F8 regression: only local AIRI origins may reach the transcription endpoint."""

    def test_accepts_local_desktop_origins(self) -> None:
        for origin in (
            "app://.",
            "file://",
            "http://localhost:5173",
            "http://127.0.0.1:8890",
        ):
            with self.subTest(origin=origin):
                self.assertTrue(is_allowed_origin(origin))

    def test_rejects_remote_origins(self) -> None:
        for origin in ("https://evil.example", "http://localhost.evil.example"):
            with self.subTest(origin=origin):
                self.assertFalse(is_allowed_origin(origin))


if __name__ == "__main__":
    unittest.main()
