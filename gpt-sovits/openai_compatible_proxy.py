"""OpenAI-compatible speech facade for local GPT-SoVITS v2ProPlus."""

from __future__ import annotations

import argparse
import os
from typing import Iterator

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI(title="GPT-SoVITS OpenAI-compatible speech proxy")
GPT_TTS_URL = os.environ.get("GPT_SOVITS_TTS_URL", "http://127.0.0.1:9880/tts")
REFERENCE_AUDIO = os.environ.get(
    "GPT_SOVITS_REFERENCE_AUDIO",
    r"C:\Projects\airi\chatterbox\voices\airi-reference.wav",
)
PROMPT_LANG = os.environ.get("GPT_SOVITS_PROMPT_LANG", "ko")
PROMPT_TEXT = os.environ.get("GPT_SOVITS_PROMPT_TEXT", "안녕하세요.")
STREAMING_MODE = int(os.environ.get("GPT_SOVITS_STREAMING_MODE", "2"))
MIN_CHUNK_LENGTH = int(os.environ.get("GPT_SOVITS_MIN_CHUNK_LENGTH", "8"))


class SpeechRequest(BaseModel):
    model: str = "tts-1-ko"
    input: str
    voice: str = "airi-vtuber"
    response_format: str = "wav"
    speed: float = 1.0


@app.get("/health")
def health():
    try:
        response = requests.get(GPT_TTS_URL.rsplit("/", 1)[0] + "/docs", timeout=2)
        backend = response.status_code < 500
    except requests.RequestException:
        backend = False
    return {"status": "ok" if backend else "degraded", "engine": "gpt-sovits-v2ProPlus", "backend_url": GPT_TTS_URL}


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": "tts-1-ko", "object": "model", "owned_by": "local-gpt-sovits"}]}


def _stream_backend(payload: dict) -> Iterator[bytes]:
    try:
        with requests.post(GPT_TTS_URL, json=payload, stream=True, timeout=180) as response:
            if response.status_code != 200:
                raise RuntimeError(f"GPT-SoVITS returned {response.status_code}: {response.text[:500]}")
            yield from response.iter_content(4096)
    except requests.RequestException as exc:
        raise RuntimeError(f"GPT-SoVITS backend unavailable: {exc}") from exc


@app.post("/v1/audio/speech")
def speech(request: SpeechRequest):
    text = request.input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="input text is empty")
    if request.response_format.casefold() not in {"wav", "pcm"}:
        raise HTTPException(status_code=400, detail="GPT-SoVITS proxy supports wav or pcm output")
    payload = {
        "text": text,
        "text_lang": "ko",
        "ref_audio_path": REFERENCE_AUDIO,
        "prompt_lang": PROMPT_LANG,
        "prompt_text": PROMPT_TEXT,
        "streaming_mode": STREAMING_MODE,
        "min_chunk_length": MIN_CHUNK_LENGTH,
        "speed_factor": request.speed,
        "parallel_infer": True,
        "media_type": "wav",
    }
    return StreamingResponse(_stream_backend(payload), media_type="audio/wav")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8891)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
