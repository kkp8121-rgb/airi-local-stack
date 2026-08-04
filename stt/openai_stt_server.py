from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import av
import numpy as np
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from faster_whisper import WhisperModel


app = FastAPI(title="AIRI local Whisper transcription server")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL_NAME = "base"
MODEL_ID = "whisper-1"
MODEL_ROOT = Path(__file__).resolve().parent / "models"
CPU_THREADS = max(1, min(6, (os.cpu_count() or 6) - 2))
whisper: WhisperModel | None = None


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
                square_sum += float(np.square(samples).sum())
                peak = max(peak, float(np.abs(samples).max()))

    return {
        "duration_seconds": sample_count / 16000.0,
        "rms": (square_sum / sample_count) ** 0.5 if sample_count else 0.0,
        "peak": peak,
    }


def transcribe_file(path: str, language: str | None, prompt: str | None) -> tuple[str, str, float, list[dict[str, object]]]:
    if whisper is None:
        raise RuntimeError("Whisper model is not ready")

    normalized_language = language.split("-")[0].lower() if language else "ko"
    segments, info = whisper.transcribe(
        path,
        language=normalized_language,
        task="transcribe",
        beam_size=3,
        best_of=3,
        temperature=0,
        vad_filter=False,
        condition_on_previous_text=False,
        initial_prompt=prompt or None,
        no_speech_threshold=0.8,
        log_prob_threshold=-1.2,
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


@app.post("/v1/audio/transcriptions")
async def create_transcription(
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

    suffix = Path(file.filename or "recording.webm").suffix or ".webm"
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded audio is empty")
    if len(contents) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio file exceeds 25 MiB")

    temp_path = ""
    audio_metrics: dict[str, float] = {}
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(contents)
            temp_path = temp_file.name
        audio_metrics = await asyncio.to_thread(analyze_audio, temp_path)
        text, detected_language, duration, segments = await asyncio.to_thread(
            transcribe_file,
            temp_path,
            language,
            prompt,
        )
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)

    print(
        json.dumps(
            {
                "event": "transcription",
                "filename": file.filename,
                "content_type": file.content_type,
                "bytes": len(contents),
                **audio_metrics,
                "language": detected_language,
                "text_chars": len(text),
                "segments": len(segments),
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
    global MODEL_NAME, MODEL_ROOT, CPU_THREADS

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8890)
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--model-root", default=str(MODEL_ROOT))
    parser.add_argument("--cpu-threads", type=int, default=CPU_THREADS)
    args = parser.parse_args()

    MODEL_NAME = args.model
    MODEL_ROOT = Path(args.model_root).resolve()
    CPU_THREADS = max(1, args.cpu_threads)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
