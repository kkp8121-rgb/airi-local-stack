from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import av
import numpy as np
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from latency_trace import elapsed_ms, emit_latency_event, request_id


# This server only ever answers the local AIRI desktop app, so any other browser origin is
# a cross-site request forgery attempt rather than a legitimate caller.
DEFAULT_ALLOWED_ORIGINS = "app://.,file://,http://localhost,http://127.0.0.1"
ALLOWED_ORIGIN_PREFIXES = tuple(
    prefix.strip()
    for prefix in os.environ.get("AIRI_STT_ALLOW_ORIGINS", DEFAULT_ALLOWED_ORIGINS).split(",")
    if prefix.strip()
)


def is_allowed_origin(origin: str) -> bool:
    # A bare startswith would also accept "http://localhost.attacker.example", so the prefix
    # has to end the host: either the origin stops there or a port/path separator follows.
    return any(
        origin == prefix or origin.startswith(prefix + ":") or origin.startswith(prefix + "/")
        for prefix in ALLOWED_ORIGIN_PREFIXES
    )


app = FastAPI(title="AIRI local Whisper transcription server")
app.add_middleware(
    CORSMiddleware,
    # Starlette matches this with fullmatch, so this mirrors is_allowed_origin above.
    allow_origin_regex="|".join(
        re.escape(prefix) + "(?:[:/].*)?" for prefix in ALLOWED_ORIGIN_PREFIXES
    )
    or r"(?!)",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def block_disallowed_origins(request: Request, call_next):
    """Reject browser callers outside the allowlist. Origin-less callers (curl, AIRI's own
    native fetch) are still allowed because they cannot be driven by a hostile page."""
    origin = request.headers.get("origin")
    if origin and not is_allowed_origin(origin):
        return JSONResponse(status_code=403, content={"detail": "Origin is not allowed"})
    return await call_next(request)


MODEL_NAME = "small"
MODEL_ID = "whisper-1"
MODEL_ROOT = Path(__file__).resolve().parent / "models"
PROPER_NOUNS_PATH = Path(__file__).resolve().parent / "proper_nouns.json"
DEVICE = "cuda"
COMPUTE_TYPE = "float16"
CPU_THREADS = max(1, min(8, (os.cpu_count() or 8) - 2))
DEBUG_AUDIO_DIR: Path | None = None
VERBOSE_TRANSCRIPTION_LOG = False
DEBUG_AUDIO_LIMIT = 10
whisper: WhisperModel | None = None

QUIET_RMS_THRESHOLD = 0.01
QUIET_PEAK_THRESHOLD = 0.08
NORMALIZE_BELOW_RMS = 0.03
NORMALIZE_TARGET_RMS = 0.04
MAX_INPUT_GAIN = 4.0
MAX_NORMALIZED_PEAK = 0.95
SHORT_AUDIO_MAX_COMPACT_CHARS = 18
MAX_COMPACT_CHARS_PER_SECOND = 14.0
MIN_ACCEPTED_AVG_LOGPROB = -1.0
# Short confirmations such as "응" or "아니" run 0.4-0.6 s, so the fallback has to reach below
# the old 0.6 s floor to rescue them.
VAD_FALLBACK_MIN_DURATION_SECONDS = 0.3
QUIET_RECOVERY_MIN_DURATION_SECONDS = 0.5
FRAME_ENERGY_MS = 25
QUIET_RECOVERY_MIN_ACTIVE_FRAMES = 3
QUIET_RECOVERY_MIN_ACTIVE_FRACTION = 0.08
QUIET_RECOVERY_MAX_ACTIVE_FRACTION = 0.85
QUIET_RECOVERY_MIN_RELATIVE_ENERGY = 1.5
QUIET_RECOVERY_MAX_NO_SPEECH_PROB = 0.6
# This is deliberately a small rescue band, not a lower global confidence threshold.
QUIET_RECOVERY_MIN_AVG_LOGPROB = -1.25
SEGMENT_TIMESTAMP_TOLERANCE_SECONDS = 0.25
SEARCH_INTENT_TERMS = ("검색", "서칭", "서치", "찾아", "알아봐")
SEARCH_ALIAS_MAX_WORD_DISTANCE = 2
# A complete prompt sentence is echoed back verbatim when the audio is ambiguous, so the
# prompt only lists vocabulary instead of forming a sentence Whisper can copy.
DEFAULT_INITIAL_PROMPT = "한국어 일상 대화. 아이리, AIRI."
BEAM_SIZE = 3
RECOVERY_BEAM_SIZE = 3
RECOVERY_MAX_NEW_TOKENS = 32
RETRYABLE_TRANSCRIPTION_REASONS = frozenset(
    {"short_audio_text_overflow", "implausible_text_rate", "low_log_probability"}
)
# Whisper sometimes fills ambiguous Korean audio with stock broadcast subtitle copy. Keep
# this list exact after punctuation/spacing normalization so ordinary discussion about
# captions or advertising is not suppressed.
KNOWN_WHISPER_HALLUCINATION_PHRASES = frozenset(
    {
        "자막제공및광고를포함하고있습니다",
        "자막제공및광고를포함합니다",
    }
)
VAD_PARAMETERS = {
    "min_silence_duration_ms": 300,
    "speech_pad_ms": 200,
}


def load_proper_nouns(path: Path = PROPER_NOUNS_PATH) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    return [entry for entry in entries if isinstance(entry, dict) and entry.get("canonical")]


PROPER_NOUNS = load_proper_nouns()


def build_hotwords() -> str:
    words = ["아이리", "AIRI"]
    for entry in PROPER_NOUNS:
        words.append(str(entry["canonical"]))
        words.extend(str(value) for value in entry.get("context", []) if value)
    return " ".join(dict.fromkeys(words))


def is_hangul_syllable(char: str) -> bool:
    return "가" <= char <= "힣"


def word_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of the whitespace separated words (어절) of the text."""
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for index, char in enumerate(text):
        if char.isspace():
            if start is not None:
                spans.append((start, index))
                start = None
        elif start is None:
            start = index
    if start is not None:
        spans.append((start, len(text)))
    return spans


def search_intent_word_indices(text: str, spans: list[tuple[int, int]]) -> list[int]:
    return [
        index
        for index, (start, end) in enumerate(spans)
        if any(term in text[start:end] for term in SEARCH_INTENT_TERMS)
    ]


def is_word_boundary_match(text: str, start: int, end: int) -> bool:
    """Reject a match that sits inside a longer Hangul word, such as "음료인" in "음료인지"."""
    if start > 0 and is_hangul_syllable(text[start - 1]):
        return False
    if end < len(text) and is_hangul_syllable(text[end]):
        return False
    return True


def is_near_search_intent(
    spans: list[tuple[int, int]],
    search_indices: list[int],
    start: int,
    end: int,
) -> bool:
    """Keep search-only aliases confined to the search query itself.

    "음료인 검색해줘" is a misrecognized query, while "음료인 것 같은데 검색해줘" merely
    mentions a drink before an unrelated search request.
    """
    if not search_indices:
        return False
    covered = [
        index
        for index, (word_start, word_end) in enumerate(spans)
        if word_start < end and start < word_end
    ]
    return any(
        abs(word_index - search_index) <= SEARCH_ALIAS_MAX_WORD_DISTANCE
        for word_index in covered
        for search_index in search_indices
    )


def replace_alias(
    text: str,
    alias: str,
    canonical: str,
    search_scoped: bool,
) -> tuple[str, int]:
    spans = word_spans(text)
    search_indices = search_intent_word_indices(text, spans) if search_scoped else []
    parts: list[str] = []
    cursor = 0
    replacements = 0
    while True:
        start = text.find(alias, cursor)
        if start < 0:
            break
        end = start + len(alias)
        accepted = is_word_boundary_match(text, start, end) and (
            not search_scoped or is_near_search_intent(spans, search_indices, start, end)
        )
        if accepted:
            parts.append(text[cursor:start])
            parts.append(canonical)
            replacements += 1
        else:
            parts.append(text[cursor:end])
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), replacements


def normalize_proper_nouns(text: str) -> tuple[str, int]:
    normalized = text.replace("웹서팅", "웹서칭")
    corrections = int(normalized != text)
    search_like = any(term in normalized for term in SEARCH_INTENT_TERMS)
    for entry in PROPER_NOUNS:
        canonical = str(entry["canonical"])
        candidates = [(str(alias), False) for alias in entry.get("aliases", [])]
        if search_like:
            candidates.extend((str(alias), True) for alias in entry.get("search_aliases", []))
        for alias, search_scoped in candidates:
            alias_text = alias.strip()
            if not alias_text or alias_text not in normalized:
                continue
            normalized, replacements = replace_alias(
                normalized,
                alias_text,
                canonical,
                search_scoped,
            )
            corrections += replacements
    return normalized, corrections


def load_model() -> None:
    global whisper
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    whisper = WhisperModel(
        MODEL_NAME,
        device=DEVICE,
        compute_type=COMPUTE_TYPE,
        cpu_threads=CPU_THREADS,
        num_workers=1,
        download_root=str(MODEL_ROOT),
    )
    # Force CUDA kernels and model weights to initialize during service startup,
    # not during the user's first utterance.
    warmup_audio = np.zeros(16000, dtype=np.float32)
    warmup_options = {
        "language": "ko",
        "beam_size": BEAM_SIZE,
        "best_of": BEAM_SIZE,
        "temperature": 0,
        "condition_on_previous_text": False,
        "initial_prompt": DEFAULT_INITIAL_PROMPT,
        "hotwords": build_hotwords(),
        "max_new_tokens": 1,
    }
    warmup_segments, _ = whisper.transcribe(
        warmup_audio,
        **warmup_options,
        vad_filter=False,
    )
    list(warmup_segments)
    # Silence makes the VAD path skip the encoder, so it cannot replace the pass above; it is
    # run in addition so that the Silero ONNX session is created here instead of costing about
    # 380 ms on the first real request.
    vad_warmup_segments, _ = whisper.transcribe(
        warmup_audio,
        **warmup_options,
        vad_filter=True,
        vad_parameters=VAD_PARAMETERS,
    )
    list(vad_warmup_segments)


@app.on_event("startup")
async def startup() -> None:
    await asyncio.to_thread(load_model)


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok" if whisper is not None else "loading",
        "model": MODEL_NAME,
        "model_id": MODEL_ID,
        "device": DEVICE,
        "compute_type": COMPUTE_TYPE,
        "cpu_threads": CPU_THREADS,
        "proper_nouns": len(PROPER_NOUNS),
    }


@app.get("/v1/models")
async def list_models() -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_ID,
                "object": "model",
                "created": 0,
                "owned_by": "local-faster-whisper",
            }
        ],
    }


def frame_energy_stats(samples: np.ndarray, sample_rate: int = 16000) -> dict[str, float]:
    """Return scalar 25 ms energy features without retaining audio or text."""
    frame_size = max(1, round(sample_rate * FRAME_ENERGY_MS / 1000))
    frame_count = samples.size // frame_size
    if not frame_count:
        return {"frame_rms_p50": 0.0, "frame_rms_p90": 0.0, "frame_rms_p95": 0.0,
                "active_frame_count": 0.0, "active_frame_fraction": 0.0,
                "longest_active_run": 0.0, "relative_energy": 0.0}
    frames = samples[: frame_count * frame_size].reshape(frame_count, frame_size)
    rms = np.sqrt(np.mean(np.square(frames, dtype=np.float64), axis=1))
    p20, p50, p90, p95 = (float(np.percentile(rms, value)) for value in (20, 50, 90, 95))
    active = rms >= max(0.002, p20 * QUIET_RECOVERY_MIN_RELATIVE_ENERGY)
    longest_run = run = 0
    for is_active in active:
        run = run + 1 if is_active else 0
        longest_run = max(longest_run, run)
    return {"frame_rms_p50": p50, "frame_rms_p90": p90, "frame_rms_p95": p95,
            "active_frame_count": float(np.count_nonzero(active)),
            "active_frame_fraction": float(np.mean(active)),
            "longest_active_run": float(longest_run),
            "relative_energy": p90 / max(p20, 1e-6)}


def analyze_audio(path: str) -> dict[str, float]:
    sample_count = clipped_sample_count = 0
    square_sum = peak = 0.0
    chunks: list[np.ndarray] = []
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    with av.open(path) as container:
        for frame in container.decode(audio=0):
            for mono in resampler.resample(frame):
                samples = mono.to_ndarray().astype(np.float32).reshape(-1) / 32768.0
                if samples.size == 0:
                    continue
                sample_count += int(samples.size)
                clipped_sample_count += int((np.abs(samples) >= 0.99).sum())
                square_sum += float(np.square(samples).sum())
                peak = max(peak, float(np.abs(samples).max()))
                chunks.append(samples)
    decoded = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
    return {"duration_seconds": sample_count / 16000.0,
            "rms": (square_sum / sample_count) ** 0.5 if sample_count else 0.0,
            "peak": peak, "clipped_ratio": clipped_sample_count / sample_count if sample_count else 0.0,
            **frame_energy_stats(decoded)}


def load_audio_samples(path: str) -> np.ndarray:
    """Decode a local upload to the float32 mono/16 kHz array Whisper accepts."""
    chunks: list[np.ndarray] = []
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    with av.open(path) as container:
        for frame in container.decode(audio=0):
            for mono in resampler.resample(frame):
                samples = mono.to_ndarray().astype(np.float32).reshape(-1) / 32768.0
                if samples.size:
                    chunks.append(samples)
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.ascontiguousarray(np.concatenate(chunks), dtype=np.float32)


def preserve_debug_audio(contents: bytes, suffix: str) -> str | None:
    if DEBUG_AUDIO_DIR is None:
        return None

    DEBUG_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    debug_path = DEBUG_AUDIO_DIR / f"{timestamp}-{uuid4().hex[:8]}{suffix}"
    debug_path.write_bytes(contents)

    recordings = sorted(
        (path for path in DEBUG_AUDIO_DIR.iterdir() if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for stale_path in recordings[DEBUG_AUDIO_LIMIT:]:
        stale_path.unlink(missing_ok=True)

    return str(debug_path)


def is_quiet_audio(audio_metrics: dict[str, float]) -> bool:
    """Single definition of "too quiet to hold speech".

    The hallucination filter and the VAD fallback share it so that no chunk can fall into a
    band where it is loud enough to be transcribed but too quiet to be rescued.
    """
    return (
        audio_metrics.get("rms", 0.0) < QUIET_RMS_THRESHOLD
        and audio_metrics.get("peak", 0.0) < QUIET_PEAK_THRESHOLD
    )


def calculate_input_gain(audio_metrics: dict[str, float]) -> float:
    """Return conservative gain for speech-like but unusually soft uploads.

    AIRI already gates microphone chunks with its own VAD. Either RMS or peak
    may establish that a quiet chunk contains speech; requiring both discarded
    the user's soft 2.9-second utterance even though its peak crossed the speech
    floor. Normal, fully quiet, or clipped input remains untouched.
    """
    rms = audio_metrics.get("rms", 0.0)
    peak = audio_metrics.get("peak", 0.0)
    if (
        is_quiet_audio(audio_metrics)
        or rms >= NORMALIZE_BELOW_RMS
        or peak >= MAX_NORMALIZED_PEAK
    ):
        return 1.0
    return max(
        1.0,
        min(MAX_INPUT_GAIN, NORMALIZE_TARGET_RMS / rms, MAX_NORMALIZED_PEAK / peak),
    )


def prepare_audio_for_whisper(
    path: str, audio_metrics: dict[str, float]
) -> np.ndarray:
    samples = load_audio_samples(path)
    gain = calculate_input_gain(audio_metrics)
    audio_metrics["input_gain"] = round(gain, 3)
    if gain > 1.0 and samples.size:
        samples = np.clip(samples * gain, -1.0, 1.0).astype(np.float32, copy=False)
    return np.ascontiguousarray(samples, dtype=np.float32)


def should_retry_without_vad(
    audio_metrics: dict[str, float],
    segments: list[object],
) -> bool:
    """Retry speech-like AIRI chunks when Whisper's second VAD drops everything."""
    if segments:
        return False
    if is_quiet_audio(audio_metrics):
        return is_quiet_speech_candidate(audio_metrics)
    return audio_metrics.get("duration_seconds", 0.0) >= VAD_FALLBACK_MIN_DURATION_SECONDS


def is_quiet_speech_candidate(audio_metrics: dict[str, float]) -> bool:
    """Conservatively distinguish sustained quiet speech from flat noise or a click."""
    active_fraction = audio_metrics.get("active_frame_fraction", 0.0)
    return (
        is_quiet_audio(audio_metrics)
        and audio_metrics.get("duration_seconds", 0.0) >= QUIET_RECOVERY_MIN_DURATION_SECONDS
        and audio_metrics.get("relative_energy", 0.0) >= QUIET_RECOVERY_MIN_RELATIVE_ENERGY
        and audio_metrics.get("active_frame_count", 0.0) >= QUIET_RECOVERY_MIN_ACTIVE_FRAMES
        and QUIET_RECOVERY_MIN_ACTIVE_FRACTION <= active_fraction <= QUIET_RECOVERY_MAX_ACTIVE_FRACTION
        and audio_metrics.get("longest_active_run", 0.0) >= QUIET_RECOVERY_MIN_ACTIVE_FRAMES
    )


def prepare_quiet_recovery_audio(audio: np.ndarray, audio_metrics: dict[str, float]) -> np.ndarray:
    """Apply one bounded gain only after the numeric quiet-speech gate passes."""
    peak, rms = audio_metrics.get("peak", 0.0), audio_metrics.get("rms", 0.0)
    if not audio.size or peak <= 0.0 or rms <= 0.0:
        return audio
    gain = max(1.0, min(MAX_INPUT_GAIN, NORMALIZE_TARGET_RMS / rms, MAX_NORMALIZED_PEAK / peak))
    audio_metrics["quiet_recovery_gain"] = round(gain, 3)
    return np.clip(audio * gain, -1.0, 1.0).astype(np.float32, copy=False)


def segment_timing_is_valid(segment: dict[str, object], audio_duration: float) -> bool:
    """Accept only finite segment bounds that can belong to this upload.

    Unit-level callers that provide confidence-only segment dictionaries predate
    timestamp telemetry; those remain valid. Whisper-produced segments always
    include both bounds and are checked strictly with a small decoder tolerance.
    """
    if "start" not in segment and "end" not in segment:
        return True
    try:
        start = float(segment["start"])
        end = float(segment["end"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        np.isfinite(start)
        and np.isfinite(end)
        and start >= -SEGMENT_TIMESTAMP_TOLERANCE_SECONDS
        and end >= start
        and end <= audio_duration + SEGMENT_TIMESTAMP_TOLERANCE_SECONDS
    )


def filter_invalid_timing_segments(
    segments: list[dict[str, object]], audio_metrics: dict[str, float]
) -> list[dict[str, object]]:
    audio_duration = max(0.0, float(audio_metrics.get("duration_seconds", 0.0)))
    valid = [segment for segment in segments if segment_timing_is_valid(segment, audio_duration)]
    invalid_count = max(
        int(audio_metrics.get("timing_invalid_segment_count", 0)),
        len(segments) - len(valid),
    )
    audio_metrics["timing_invalid_segment_count"] = invalid_count
    audio_metrics["timing_invalid"] = bool(invalid_count)
    return valid


def transcribe_file(
    path: str | np.ndarray,
    language: str | None,
    prompt: str | None,
    audio_metrics: dict[str, float],
    recovery_decode: bool = False,
) -> tuple[str, str, float, list[dict[str, object]], bool]:
    if whisper is None:
        raise RuntimeError("Whisper model is not ready")
    # This invocation is the authoritative decoder attempt. A later clean retry
    # must not inherit an invalid-timing flag from a discarded first attempt.
    audio_metrics["timing_invalid_segment_count"] = 0
    audio_metrics["timing_invalid"] = False

    normalized_language = language.split("-")[0].lower() if language else "ko"
    beam_size = RECOVERY_BEAM_SIZE if recovery_decode else BEAM_SIZE
    transcription_options = {
        "language": normalized_language,
        "task": "transcribe",
        "beam_size": beam_size,
        "best_of": beam_size,
        "temperature": 0,
        "condition_on_previous_text": False,
        "initial_prompt": prompt or DEFAULT_INITIAL_PROMPT,
        "hotwords": build_hotwords(),
        "no_speech_threshold": 0.6,
        "log_prob_threshold": -1.0,
        "repetition_penalty": 1.1,
        "no_repeat_ngram_size": 3,
        "max_new_tokens": RECOVERY_MAX_NEW_TOKENS if recovery_decode else 64,
    }
    segments, info = whisper.transcribe(
        path,
        **transcription_options,
        vad_filter=not recovery_decode,
        vad_parameters=VAD_PARAMETERS,
    )

    completed = list(segments)
    vad_fallback_used = recovery_decode
    if not recovery_decode and should_retry_without_vad(audio_metrics, completed):
        vad_fallback_used = True
        recovery_input = (
            prepare_quiet_recovery_audio(path, audio_metrics)
            if isinstance(path, np.ndarray) and is_quiet_speech_candidate(audio_metrics)
            else path
        )
        fallback_segments, info = whisper.transcribe(
            recovery_input,
            **transcription_options,
            vad_filter=False,
        )
        completed = list(fallback_segments)
    verbose_segments = [
        {
            "id": index,
            "seek": 0,
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip(),
            "tokens": [],
            "temperature": 0,
            "avg_logprob": segment.avg_logprob,
            "compression_ratio": segment.compression_ratio,
            "no_speech_prob": segment.no_speech_prob,
        }
        for index, segment in enumerate(completed)
    ]
    # Preserve content-free decoder diagnostics before rejecting impossible timing.
    audio_metrics["decoded_segment_count"] = len(verbose_segments)
    decoded_avg = [float(segment["avg_logprob"]) for segment in verbose_segments]
    decoded_no_speech = [float(segment["no_speech_prob"]) for segment in verbose_segments]
    audio_metrics["decoded_min_avg_logprob"] = min(decoded_avg, default=None)
    audio_metrics["decoded_max_no_speech_prob"] = max(decoded_no_speech, default=None)
    verbose_segments = filter_invalid_timing_segments(verbose_segments, audio_metrics)
    text = " ".join(
        str(segment.get("text", "")).strip()
        for segment in verbose_segments
        if str(segment.get("text", "")).strip()
    ).strip()
    # Never publish a decoder timestamp beyond the actual upload duration.
    duration = max(
        (min(float(segment["end"]), audio_metrics.get("duration_seconds", 0.0))
         for segment in verbose_segments if "end" in segment),
        default=0.0,
    )
    return text, info.language, duration, verbose_segments, vad_fallback_used


def should_retry_rejected_transcription(
    rejected_reason: str | None, audio_metrics: dict[str, float]
) -> bool:
    """Retry only speech-like chunks rejected for a potentially bad decode.

    Quiet tails and empty chunks remain rejected. The retry uses a wider beam
    without Whisper's internal VAD, and therefore only runs on an otherwise
    lost user turn instead of adding latency to normal speech.
    """
    return (
        rejected_reason in RETRYABLE_TRANSCRIPTION_REASONS
        and not is_quiet_audio(audio_metrics)
        and audio_metrics.get("duration_seconds", 0.0) >= VAD_FALLBACK_MIN_DURATION_SECONDS
    )


def validate_decoded_transcription(
    raw_text: str,
    segments: list[dict[str, object]],
    audio_metrics: dict[str, float],
    strict_quiet_recovery: bool = False,
) -> tuple[str, str | None, int, int]:
    """Normalize and validate one Whisper decode without losing its metrics."""
    segments = filter_invalid_timing_segments(segments, audio_metrics)
    if audio_metrics.get("timing_invalid_segment_count", 0) and not segments:
        return "", "timing_invalid", 0, 0
    corrected_text, proper_noun_corrections = normalize_proper_nouns(raw_text)
    text, rejected_reason = filter_implausible_transcription(
        corrected_text, audio_metrics, allow_quiet_speech=strict_quiet_recovery
    )
    low_confidence_segments = 0
    if rejected_reason is None and not strict_quiet_recovery:
        text, rejected_reason, low_confidence_segments = filter_low_confidence_transcription(
            text,
            segments,
        )
        if low_confidence_segments and text:
            text, proper_noun_corrections = normalize_proper_nouns(text)
    if rejected_reason is None and not text.strip():
        rejected_reason = "empty_transcription"
    if rejected_reason is None and strict_quiet_recovery:
        if not is_quiet_speech_candidate(audio_metrics):
            rejected_reason = "quiet_recovery_frame_gate"
        elif not segments:
            rejected_reason = "quiet_recovery_empty_segments"
        elif any(
            not np.isfinite(float(segment.get("avg_logprob", float("nan"))))
            or float(segment["avg_logprob"]) < QUIET_RECOVERY_MIN_AVG_LOGPROB
            for segment in segments
        ):
            rejected_reason = "quiet_recovery_low_log_probability"
        elif any(
            not np.isfinite(float(segment.get("no_speech_prob", float("nan"))))
            or float(segment.get("no_speech_prob", 1.0)) > QUIET_RECOVERY_MAX_NO_SPEECH_PROB
            for segment in segments
        ):
            rejected_reason = "quiet_recovery_no_speech"
    return text, rejected_reason, proper_noun_corrections, low_confidence_segments


def filter_implausible_transcription(
    text: str,
    audio_metrics: dict[str, float],
    allow_quiet_speech: bool = False,
) -> tuple[str, str | None]:
    """Suppress common Whisper hallucinations from short or quiet AIRI chunks."""
    if not text:
        return text, None

    compact_phrase = re.sub(r"[^0-9A-Za-z가-힣]+", "", text).lower()
    if compact_phrase in KNOWN_WHISPER_HALLUCINATION_PHRASES:
        return "", "known_whisper_hallucination"

    duration = audio_metrics.get("duration_seconds", 0.0)
    compact_chars = len("".join(text.split()))

    if is_quiet_audio(audio_metrics) and not allow_quiet_speech:
        return "", "quiet_audio"

    # One continuous character budget instead of two step functions. The old 1.5 s split let a
    # 1.51 s chunk carry 24 characters while a 1.49 s chunk was rejected at 19, which punished
    # slow speakers for nothing.
    rate_budget = MAX_COMPACT_CHARS_PER_SECOND * duration
    max_compact_chars = max(SHORT_AUDIO_MAX_COMPACT_CHARS, rate_budget)
    if compact_chars > max_compact_chars:
        if rate_budget <= SHORT_AUDIO_MAX_COMPACT_CHARS:
            return "", "short_audio_text_overflow"
        return "", "implausible_text_rate"

    return text, None


def filter_low_confidence_transcription(
    text: str,
    segments: list[dict[str, object]],
) -> tuple[str, str | None, int]:
    """Drop only the low confidence segments and report how many were dropped.

    Aggregating with min() threw away a whole utterance because of one bad segment, so a
    clean -0.31 segment was lost together with a -1.24 one.
    """
    if not text or not segments:
        return text, None, 0

    kept = [
        segment
        for segment in segments
        if float(segment["avg_logprob"]) >= MIN_ACCEPTED_AVG_LOGPROB
    ]
    dropped = len(segments) - len(kept)
    if not kept:
        return "", "low_log_probability", dropped
    if dropped == 0:
        return text, None, 0

    kept_text = " ".join(
        str(segment.get("text", "")).strip()
        for segment in kept
        if str(segment.get("text", "")).strip()
    ).strip()
    if not kept_text:
        return "", "low_log_probability", dropped
    return kept_text, None, dropped


def finite_audit_number(value: object, *, lower: float = 0.0, upper: float = 1_000_000.0) -> float:
    """Keep latency telemetry numeric, bounded, and safe for downstream JSON consumers."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return lower
    if not np.isfinite(number):
        return lower
    return round(min(upper, max(lower, number)), 4)


def rejection_reason_flags(reason: str | None) -> dict[str, bool]:
    """Content-free audit flags; the latency event never exposes decoder text or a reason string."""
    return {
        "timing_invalid": reason == "timing_invalid",
        "quiet_audio": reason == "quiet_audio",
        "quiet_recovery_low_confidence": reason == "quiet_recovery_low_log_probability",
        "quiet_recovery_no_speech": reason == "quiet_recovery_no_speech",
        "quiet_recovery_frame_gate": reason == "quiet_recovery_frame_gate",
        "low_confidence": reason == "low_log_probability",
        "text_rate": reason in {"short_audio_text_overflow", "implausible_text_rate"},
        "known_hallucination": reason == "known_whisper_hallucination",
        "empty": reason in {"empty_transcription", "quiet_recovery_empty_segments"},
    }


@app.post("/v1/audio/transcriptions")
async def create_transcription(
    http_request: Request,
    file: UploadFile = File(...),
    model: str = Form(MODEL_ID),
    language: str | None = Form(None),
    prompt: str | None = Form(None),
    response_format: str = Form("json"),
) -> dict[str, object] | str:
    if whisper is None:
        raise HTTPException(status_code=503, detail="Whisper model is still loading")
    if model not in {MODEL_ID, MODEL_NAME}:
        raise HTTPException(status_code=400, detail=f"Unsupported model: {model}")

    content_type = (file.content_type or "").lower()
    if "webm" in content_type:
        suffix = ".webm"
    elif "ogg" in content_type:
        suffix = ".ogg"
    else:
        suffix = Path(file.filename or "recording.wav").suffix or ".wav"
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded audio is empty")
    if len(contents) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio file exceeds 25 MiB")

    trace_id = request_id(http_request.headers, uuid4().hex)
    request_started = time.perf_counter()
    emit_latency_event(
        "stt",
        "start",
        trace_id,
        meta={"audio_bytes": len(contents)},
    )

    temp_path = ""
    debug_audio_path = await asyncio.to_thread(preserve_debug_audio, contents, suffix)
    audio_metrics: dict[str, float] = {}
    analysis_ms = 0.0
    inference_ms = 0.0
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(contents)
            temp_path = temp_file.name
        analysis_started = time.perf_counter()
        audio_metrics = await asyncio.to_thread(analyze_audio, temp_path)
        audio_input = await asyncio.to_thread(
            prepare_audio_for_whisper,
            temp_path,
            audio_metrics,
        )
        analysis_ms = elapsed_ms(analysis_started)
        inference_started = time.perf_counter()
        raw_text, detected_language, duration, segments, vad_fallback_used = await asyncio.to_thread(
            transcribe_file,
            audio_input,
            language,
            prompt,
            audio_metrics,
        )
        inference_ms = elapsed_ms(inference_started)

        text, rejected_reason, proper_noun_corrections, low_confidence_segments = (
            validate_decoded_transcription(
                raw_text,
                segments,
                audio_metrics,
                strict_quiet_recovery=vad_fallback_used
                and is_quiet_speech_candidate(audio_metrics),
            )
        )
        decode_retry_used = False
        first_rejected_reason = rejected_reason
        if should_retry_rejected_transcription(rejected_reason, audio_metrics):
            retry_started = time.perf_counter()
            (
                retry_raw_text,
                retry_language,
                retry_duration,
                retry_segments,
                retry_vad_fallback_used,
            ) = await asyncio.to_thread(
                transcribe_file,
                audio_input,
                language,
                prompt,
                audio_metrics,
                True,
            )
            inference_ms += elapsed_ms(retry_started)
            retry_result = validate_decoded_transcription(
                retry_raw_text,
                retry_segments,
                audio_metrics,
            )
            decode_retry_used = True
            if retry_result[1] is None:
                raw_text = retry_raw_text
                detected_language = retry_language
                duration = retry_duration
                segments = retry_segments
                vad_fallback_used = retry_vad_fallback_used
                (
                    text,
                    rejected_reason,
                    proper_noun_corrections,
                    low_confidence_segments,
                ) = retry_result
    except Exception:
        emit_latency_event(
            "stt",
            "error",
            trace_id,
            duration_ms=elapsed_ms(request_started),
        )
        raise
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)

    # Keep the segment statistics for threshold tuning even when the transcription is
    # rejected; only the response body drops the segments.
    segment_count = int(audio_metrics.get("decoded_segment_count", len(segments)))
    avg_logprobs = [
        float(segment["avg_logprob"])
        for segment in segments
        if np.isfinite(float(segment.get("avg_logprob", float("nan"))))
    ]
    no_speech_probs = [
        float(segment["no_speech_prob"])
        for segment in segments
        if np.isfinite(float(segment.get("no_speech_prob", float("nan"))))
    ]
    min_avg_logprob = audio_metrics.get("decoded_min_avg_logprob", min(avg_logprobs, default=None))
    max_no_speech_prob = audio_metrics.get("decoded_max_no_speech_prob", max(no_speech_probs, default=None))
    if rejected_reason:
        segments = []

    emit_latency_event(
        "stt",
        "end",
        trace_id,
        duration_ms=elapsed_ms(request_started),
        meta={
            "audio_duration_ms": finite_audit_number(audio_metrics.get("duration_seconds", 0.0) * 1000),
            "speech_duration_ms": finite_audit_number(duration * 1000),
            "analysis_ms": finite_audit_number(analysis_ms),
            "inference_ms": finite_audit_number(inference_ms),
            "rms": finite_audit_number(audio_metrics.get("rms", 0.0), upper=1.0),
            "peak": finite_audit_number(audio_metrics.get("peak", 0.0), upper=1.0),
            "quiet_speech_candidate": is_quiet_speech_candidate(audio_metrics),
            "quiet_recovery_gain": finite_audit_number(audio_metrics.get("quiet_recovery_gain", 1.0), upper=MAX_INPUT_GAIN),
            "segment_count": min(256, max(0, segment_count)),
            "min_avg_logprob": finite_audit_number(min_avg_logprob, lower=-20.0, upper=0.0) if min_avg_logprob is not None else None,
            "max_no_speech_prob": finite_audit_number(max_no_speech_prob, upper=1.0) if max_no_speech_prob is not None else None,
            "timing_invalid_segment_count": min(256, max(0, int(audio_metrics.get("timing_invalid_segment_count", 0)))),
            "timing_invalid": bool(audio_metrics.get("timing_invalid", False)),
            "accepted": rejected_reason is None,
            **rejection_reason_flags(rejected_reason),
            "vad_fallback_used": vad_fallback_used,
            "decode_retry_used": decode_retry_used,
        },
    )

    print(
        json.dumps(
            {
                "event": "transcription",
                "filename": file.filename,
                "content_type": file.content_type,
                "bytes": len(contents),
                "debug_audio_path": debug_audio_path,
                **audio_metrics,
                "language": detected_language,
                **({"text": raw_text} if VERBOSE_TRANSCRIPTION_LOG else {}),
                "text_logged": VERBOSE_TRANSCRIPTION_LOG,
                "text_chars": len(text),
                "segments": segment_count,
                "avg_logprob": min_avg_logprob,
                "max_no_speech_prob": max_no_speech_prob,
                "accepted": rejected_reason is None,
                "rejected_reason": rejected_reason,
                "first_rejected_reason": first_rejected_reason,
                "proper_noun_corrections": proper_noun_corrections,
                "low_confidence_segments": low_confidence_segments,
                "vad_fallback_used": vad_fallback_used,
                "decode_retry_used": decode_retry_used,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    if response_format == "text":
        return text
    if response_format == "verbose_json":
        return {
            "task": "transcribe",
            "language": detected_language,
            "duration": duration,
            "text": text,
            "segments": segments,
        }
    return {"text": text}


def main() -> None:
    global MODEL_NAME, MODEL_ROOT, DEVICE, COMPUTE_TYPE, CPU_THREADS, DEBUG_AUDIO_DIR, VERBOSE_TRANSCRIPTION_LOG

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8890)
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--model-root", default=str(MODEL_ROOT))
    parser.add_argument("--device", choices=("cpu", "cuda"), default=DEVICE)
    parser.add_argument("--compute-type", default=COMPUTE_TYPE)
    parser.add_argument("--cpu-threads", type=int, default=CPU_THREADS)
    parser.add_argument("--debug-audio-dir")
    parser.add_argument(
        "--verbose-transcription-log",
        action="store_true",
        help="Include recognized text in server logs. Disabled by default for privacy.",
    )
    args = parser.parse_args()

    MODEL_NAME = args.model
    MODEL_ROOT = Path(args.model_root).resolve()
    DEVICE = args.device
    COMPUTE_TYPE = args.compute_type
    CPU_THREADS = max(1, args.cpu_threads)
    DEBUG_AUDIO_DIR = Path(args.debug_audio_dir).resolve() if args.debug_audio_dir else None
    VERBOSE_TRANSCRIPTION_LOG = bool(args.verbose_transcription_log)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
