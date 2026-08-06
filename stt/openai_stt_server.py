from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
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
from faster_whisper import WhisperModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from latency_trace import elapsed_ms, emit_latency_event, request_id


app = FastAPI(title="AIRI local Whisper transcription server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL_NAME = "small"
MODEL_ID = "whisper-1"
MODEL_ROOT = Path(__file__).resolve().parent / "models"
CPU_THREADS = max(1, min(8, (os.cpu_count() or 8) - 2))
DEBUG_AUDIO_DIR: Path | None = None
VERBOSE_TRANSCRIPTION_LOG = False
DEBUG_AUDIO_LIMIT = 10
whisper: WhisperModel | None = None

QUIET_RMS_THRESHOLD = 0.01
QUIET_PEAK_THRESHOLD = 0.08
SHORT_AUDIO_SECONDS = 1.5
SHORT_AUDIO_MAX_COMPACT_CHARS = 18
MAX_COMPACT_CHARS_PER_SECOND = 14.0
MAX_RATE_MIN_COMPACT_CHARS = 24
MIN_ACCEPTED_AVG_LOGPROB = -1.0
DEFAULT_INITIAL_PROMPT = "한국어 대화입니다. 아이리, 내 말 들려? 아이리는 사용자의 말을 듣고 대답합니다."
BEAM_SIZE = 1


def load_model() -> None:
    global whisper
    MODEL_ROOT.mkdir(parents=True, exist_ok=True)
    whisper = WhisperModel(
        MODEL_NAME,
        device="cpu",
        compute_type="int8",
        cpu_threads=CPU_THREADS,
        num_workers=1,
        download_root=str(MODEL_ROOT),
    )


@app.on_event("startup")
async def startup() -> None:
    await asyncio.to_thread(load_model)


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok" if whisper is not None else "loading",
        "model": MODEL_NAME,
        "model_id": MODEL_ID,
        "device": "cpu",
        "compute_type": "int8",
        "cpu_threads": CPU_THREADS,
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


def analyze_audio(path: str) -> dict[str, float]:
    sample_count = 0
    clipped_sample_count = 0
    square_sum = 0.0
    peak = 0.0
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

    return {
        "duration_seconds": sample_count / 16000.0,
        "rms": (square_sum / sample_count) ** 0.5 if sample_count else 0.0,
        "peak": peak,
        "clipped_ratio": clipped_sample_count / sample_count if sample_count else 0.0,
    }


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


def transcribe_file(path: str, language: str | None, prompt: str | None) -> tuple[str, str, float, list[dict[str, object]]]:
    if whisper is None:
        raise RuntimeError("Whisper model is not ready")

    normalized_language = language.split("-")[0].lower() if language else "ko"
    segments, info = whisper.transcribe(
        path,
        language=normalized_language,
        task="transcribe",
        beam_size=BEAM_SIZE,
        best_of=BEAM_SIZE,
        temperature=0,
        vad_filter=True,
        vad_parameters={
            "min_silence_duration_ms": 300,
            "speech_pad_ms": 200,
        },
        condition_on_previous_text=False,
        initial_prompt=prompt or DEFAULT_INITIAL_PROMPT,
        hotwords="아이리 AIRI",
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
        repetition_penalty=1.1,
        no_repeat_ngram_size=3,
        max_new_tokens=64,
    )

    completed = list(segments)
    text = " ".join(segment.text.strip() for segment in completed if segment.text.strip()).strip()
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
    duration = completed[-1].end if completed else 0.0
    return text, info.language, duration, verbose_segments


def filter_implausible_transcription(
    text: str,
    audio_metrics: dict[str, float],
) -> tuple[str, str | None]:
    """Suppress common Whisper hallucinations from short or quiet AIRI chunks."""
    if not text:
        return text, None

    duration = audio_metrics.get("duration_seconds", 0.0)
    rms = audio_metrics.get("rms", 0.0)
    peak = audio_metrics.get("peak", 0.0)
    compact_chars = len("".join(text.split()))
    chars_per_second = compact_chars / max(duration, 0.001)

    if rms < QUIET_RMS_THRESHOLD and peak < QUIET_PEAK_THRESHOLD:
        return "", "quiet_audio"
    if duration < SHORT_AUDIO_SECONDS and compact_chars > SHORT_AUDIO_MAX_COMPACT_CHARS:
        return "", "short_audio_text_overflow"
    if (
        compact_chars > MAX_RATE_MIN_COMPACT_CHARS
        and chars_per_second > MAX_COMPACT_CHARS_PER_SECOND
    ):
        return "", "implausible_text_rate"

    return text, None


def filter_low_confidence_transcription(
    text: str,
    segments: list[dict[str, object]],
) -> tuple[str, str | None]:
    if not text or not segments:
        return text, None

    avg_logprob = min(float(segment["avg_logprob"]) for segment in segments)
    if avg_logprob < MIN_ACCEPTED_AVG_LOGPROB:
        return "", "low_log_probability"
    return text, None


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
        analysis_ms = elapsed_ms(analysis_started)
        inference_started = time.perf_counter()
        raw_text, detected_language, duration, segments = await asyncio.to_thread(
            transcribe_file,
            temp_path,
            language,
            prompt,
        )
        inference_ms = elapsed_ms(inference_started)
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

    text, rejected_reason = filter_implausible_transcription(raw_text, audio_metrics)
    if rejected_reason is None:
        text, rejected_reason = filter_low_confidence_transcription(text, segments)
    if rejected_reason:
        segments = []

    emit_latency_event(
        "stt",
        "end",
        trace_id,
        duration_ms=elapsed_ms(request_started),
        meta={
            "audio_duration_ms": round(audio_metrics.get("duration_seconds", 0.0) * 1000, 1),
            "speech_duration_ms": round(duration * 1000, 1),
            "analysis_ms": analysis_ms,
            "inference_ms": inference_ms,
            "text_chars": len(text),
            "accepted": rejected_reason is None,
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
                "segments": len(segments),
                "avg_logprob": min(
                    (segment["avg_logprob"] for segment in segments),
                    default=None,
                ),
                "max_no_speech_prob": max(
                    (segment["no_speech_prob"] for segment in segments),
                    default=None,
                ),
                "accepted": rejected_reason is None,
                "rejected_reason": rejected_reason,
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
    global MODEL_NAME, MODEL_ROOT, CPU_THREADS, DEBUG_AUDIO_DIR, VERBOSE_TRANSCRIPTION_LOG

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8890)
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--model-root", default=str(MODEL_ROOT))
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
    CPU_THREADS = max(1, args.cpu_threads)
    DEBUG_AUDIO_DIR = Path(args.debug_audio_dir).resolve() if args.debug_audio_dir else None
    VERBOSE_TRANSCRIPTION_LOG = bool(args.verbose_transcription_log)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
