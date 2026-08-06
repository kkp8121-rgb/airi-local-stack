#!/usr/bin/env python3
"""Local OpenAI-compatible API for Chatterbox Multilingual V3."""

import argparse
import asyncio
import io
import logging
import os
import struct
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chatterbox-openai")

app = FastAPI(title="Chatterbox Multilingual V3 OpenAI-compatible API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

model = None
reference_audio: Optional[Path] = None
default_exaggeration = 0.70
default_cfg_weight = 0.30
default_temperature = 0.65
default_cfm_steps = 10
sample_rate = 24000
model_lock = threading.Lock()

VOICE_PRESETS = {
    "airi-vtuber": None,
    "airi-065": 0.65,
    "airi-070": 0.70,
    "airi-075": 0.75,
    "airi-080": 0.80,
}


class SpeechRequest(BaseModel):
    model: str = "tts-1-ko"
    input: str
    voice: str = "airi-vtuber"
    response_format: str = "wav"
    speed: float = 1.0
    exaggeration: Optional[float] = None
    cfg_weight: Optional[float] = None
    temperature: Optional[float] = None
    seed: Optional[int] = None
    cfm_steps: Optional[int] = None


def _pcm16(audio: np.ndarray) -> bytes:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    return np.clip(audio * 32767.0, -32768, 32767).astype("<i2").tobytes()


def _wav(audio: np.ndarray, rate: int) -> bytes:
    raw = _pcm16(audio)
    header = io.BytesIO()
    header.write(b"RIFF")
    header.write(struct.pack("<I", 36 + len(raw)))
    header.write(b"WAVEfmt ")
    header.write(struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16))
    header.write(b"data")
    header.write(struct.pack("<I", len(raw)))
    return header.getvalue() + raw


def _mp3(audio: np.ndarray, rate: int) -> bytes:
    try:
        from pydub import AudioSegment
    except ImportError as exc:
        raise HTTPException(status_code=400, detail="MP3 support is unavailable") from exc
    segment = AudioSegment(_pcm16(audio), frame_rate=rate, sample_width=2, channels=1)
    output = io.BytesIO()
    segment.export(output, format="mp3", bitrate="192k")
    return output.getvalue()


def _resolve_parameters(req: SpeechRequest) -> tuple[float, float, float]:
    preset = VOICE_PRESETS.get(req.voice.casefold())
    exaggeration = req.exaggeration
    if exaggeration is None:
        exaggeration = preset if preset is not None else default_exaggeration
    cfg_weight = req.cfg_weight if req.cfg_weight is not None else default_cfg_weight
    temperature = req.temperature if req.temperature is not None else default_temperature
    if not 0.25 <= exaggeration <= 2.0:
        raise HTTPException(status_code=400, detail="exaggeration must be between 0.25 and 2.0")
    if not 0.0 <= cfg_weight <= 1.0:
        raise HTTPException(status_code=400, detail="cfg_weight must be between 0.0 and 1.0")
    if not 0.1 <= temperature <= 1.5:
        raise HTTPException(status_code=400, detail="temperature must be between 0.1 and 1.5")
    return exaggeration, cfg_weight, temperature


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": model is not None,
        "engine": "chatterbox-multilingual-v3",
        "reference_audio": str(reference_audio) if reference_audio else None,
        "default_exaggeration": default_exaggeration,
        "default_cfg_weight": default_cfg_weight,
        "default_temperature": default_temperature,
        "default_cfm_steps": default_cfm_steps,
    }


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [{"id": "tts-1-ko", "object": "model", "owned_by": "local-chatterbox"}],
    }


@app.get("/v1/voices")
async def list_voices():
    return {
        "object": "list",
        "data": [{"id": name, "name": name} for name in VOICE_PRESETS],
    }


@app.post("/v1/audio/speech")
async def create_speech(req: SpeechRequest):
    if model is None:
        raise HTTPException(status_code=503, detail="Model is not loaded")
    text = req.input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="input text is empty")
    if len(text) > 1000:
        raise HTTPException(status_code=400, detail="input text exceeds 1000 characters")

    exaggeration, cfg_weight, temperature = _resolve_parameters(req)
    cfm_steps = req.cfm_steps if req.cfm_steps is not None else default_cfm_steps
    if not 2 <= cfm_steps <= 10:
        raise HTTPException(status_code=400, detail="cfm_steps must be between 2 and 10")
    loop = asyncio.get_running_loop()
    queued_at = time.perf_counter()

    def generate():
        with model_lock:
            queue_seconds = time.perf_counter() - queued_at
            started_at = time.perf_counter()
            if req.seed is not None:
                torch.manual_seed(req.seed)
                torch.cuda.manual_seed_all(req.seed)
            audio = model.generate(
                text,
                language_id="ko",
                exaggeration=exaggeration,
                cfg_weight=cfg_weight,
                temperature=temperature,
                n_cfm_timesteps=cfm_steps,
            )
            generation_seconds = time.perf_counter() - started_at
            return (
                audio.squeeze().detach().cpu().float().numpy(),
                queue_seconds,
                generation_seconds,
            )

    logger.info(
        "Generating %d chars: voice=%s exaggeration=%.2f cfg_weight=%.2f temperature=%.2f cfm_steps=%d",
        len(text),
        req.voice,
        exaggeration,
        cfg_weight,
        temperature,
        cfm_steps,
    )
    audio, queue_seconds, generation_seconds = await loop.run_in_executor(None, generate)
    logger.info(
        "Completed %d chars: queue=%.3fs generation=%.3fs total=%.3fs",
        len(text),
        queue_seconds,
        generation_seconds,
        queue_seconds + generation_seconds,
    )
    fmt = req.response_format.casefold()
    if fmt == "pcm":
        return Response(_pcm16(audio), media_type="audio/pcm")
    if fmt == "mp3":
        return Response(_mp3(audio, sample_rate), media_type="audio/mpeg")
    if fmt != "wav":
        raise HTTPException(status_code=400, detail="response_format must be wav, mp3, or pcm")
    return Response(_wav(audio, sample_rate), media_type="audio/wav")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-audio", required=True)
    parser.add_argument("--exaggeration", type=float, default=0.70)
    parser.add_argument("--cfg-weight", type=float, default=0.30)
    parser.add_argument("--temperature", type=float, default=0.65)
    parser.add_argument("--cfm-steps", type=int, choices=range(2, 11), default=10)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8880)
    return parser.parse_args()


def main():
    global model, reference_audio, default_exaggeration, default_cfg_weight, default_temperature, default_cfm_steps, sample_rate
    args = parse_args()
    reference_audio = Path(args.reference_audio).resolve()
    if not reference_audio.is_file():
        raise SystemExit(f"Reference audio not found: {reference_audio}")

    info = sf.info(reference_audio)
    duration = info.frames / info.samplerate
    if duration < 4.0 or duration > 30.0:
        raise SystemExit(f"Reference audio should be 4-30 seconds; got {duration:.2f}s")

    default_exaggeration = args.exaggeration
    default_cfg_weight = args.cfg_weight
    default_temperature = args.temperature
    default_cfm_steps = args.cfm_steps
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True
    torch.backends.cudnn.benchmark = True
    torch.set_float32_matmul_precision("high")
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    logger.info("Loading Multilingual V3 on CUDA")
    model = ChatterboxMultilingualTTS.from_pretrained(device="cuda", t3_model="v3")
    sample_rate = model.sr
    logger.info("Preparing %.2fs reference audio: %s", duration, reference_audio)
    model.prepare_conditionals(str(reference_audio), exaggeration=default_exaggeration)
    logger.info("Ready on http://%s:%d", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
