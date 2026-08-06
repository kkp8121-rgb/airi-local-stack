"""OpenAI-compatible speech facade for local GPT-SoVITS v2ProPlus."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Iterator
from uuid import uuid4

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from latency_trace import elapsed_ms, emit_latency_event, request_id

app = FastAPI(title="GPT-SoVITS OpenAI-compatible speech proxy")
logger = logging.getLogger("uvicorn.error")
HTTP = requests.Session()
HTTP.headers.update({"Connection": "keep-alive"})
GPT_TTS_URL = os.environ.get("GPT_SOVITS_TTS_URL", "http://127.0.0.1:9880/tts")
REFERENCE_AUDIO = os.environ.get(
    "GPT_SOVITS_REFERENCE_AUDIO",
    r"C:\Projects\airi\chatterbox\voices\airi-reference.wav",
)
PROMPT_LANG = os.environ.get("GPT_SOVITS_PROMPT_LANG", "ja")
PROMPT_TEXT = os.environ.get(
    "GPT_SOVITS_PROMPT_TEXT",
    "声聞こえてるかどうかだけ教えてほしいんだけどなぁ。聞こえてる？あ、よかった。ふぅ。",
)
STREAMING_MODE = int(os.environ.get("GPT_SOVITS_STREAMING_MODE", "2"))
MIN_CHUNK_LENGTH = int(os.environ.get("GPT_SOVITS_MIN_CHUNK_LENGTH", "16"))
TTS_LOCK = threading.Lock()


class SpeechRequest(BaseModel):
    model: str = "tts-1-ko"
    input: str
    voice: str = "airi-vtuber"
    response_format: str = "wav"
    speed: float = 1.0


@app.get("/health")
def health():
    try:
        response = HTTP.get(GPT_TTS_URL.rsplit("/", 1)[0] + "/docs", timeout=2)
        backend = response.status_code < 500
    except requests.RequestException:
        backend = False
    return {"status": "ok" if backend else "degraded", "engine": "gpt-sovits-v2ProPlus", "backend_url": GPT_TTS_URL}


@app.get("/v1/models")
@app.get("/models")
def models():
    return {"object": "list", "data": [{"id": "tts-1-ko", "object": "model", "owned_by": "local-gpt-sovits"}]}


def _stream_backend(
    payload: dict,
    trace_id: str,
    request_started: float,
) -> Iterator[bytes]:
    # GPT-SoVITS streaming generations must not overlap: mixed streams sound
    # like murmuring when AIRI sends adjacent sentence chunks concurrently.
    failed = False
    try:
        lock_started = time.perf_counter()
        with TTS_LOCK:
            lock_wait_ms = elapsed_ms(lock_started)
            with HTTP.post(GPT_TTS_URL, json=payload, stream=True, timeout=180) as response:
                if response.status_code != 200:
                    raise RuntimeError(f"GPT-SoVITS returned {response.status_code}: {response.text[:500]}")
                emitted_first = False
                for chunk in response.iter_content(4096):
                    if not chunk:
                        continue
                    if not emitted_first:
                        emit_latency_event(
                            "tts",
                            "first",
                            trace_id,
                            duration_ms=elapsed_ms(request_started),
                            meta={"lock_wait_ms": lock_wait_ms},
                        )
                        emitted_first = True
                    yield chunk
    except GeneratorExit:
        failed = True
        emit_latency_event(
            "tts",
            "error",
            trace_id,
            duration_ms=elapsed_ms(request_started),
            meta={"client_cancelled": 1},
        )
        raise
    except requests.RequestException as exc:
        failed = True
        emit_latency_event("tts", "error", trace_id, duration_ms=elapsed_ms(request_started))
        raise RuntimeError(f"GPT-SoVITS backend unavailable: {exc}") from exc
    except Exception:
        failed = True
        emit_latency_event("tts", "error", trace_id, duration_ms=elapsed_ms(request_started))
        raise
    finally:
        if not failed:
            emit_latency_event(
                "tts",
                "end",
                trace_id,
                duration_ms=elapsed_ms(request_started),
            )


@app.post("/v1/audio/speech")
@app.post("/audio/speech")
def speech(request: SpeechRequest, http_request: Request):
    text = request.input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="input text is empty")
    if request.response_format.casefold() not in {"wav", "pcm"}:
        raise HTTPException(status_code=400, detail="GPT-SoVITS proxy supports wav or pcm output")
    trace_id = request_id(http_request.headers, uuid4().hex)
    request_started = time.perf_counter()
    emit_latency_event(
        "tts",
        "start",
        trace_id,
        meta={"text_chars": len(text)},
    )
    payload = {
        "text": text,
        "text_lang": "ko",
        "ref_audio_path": REFERENCE_AUDIO,
        "prompt_lang": PROMPT_LANG,
        "prompt_text": PROMPT_TEXT,
        "streaming_mode": STREAMING_MODE,
        "min_chunk_length": MIN_CHUNK_LENGTH,
        "speed_factor": request.speed,
        "parallel_infer": False,
        "media_type": "wav",
    }
    logger.info(
        "speech request path=/audio/speech model=%s voice=%s chars=%d user_agent=%s origin=%s",
        request.model,
        request.voice,
        len(text),
        http_request.headers.get("user-agent", "-"),
        http_request.headers.get("origin", "-"),
    )
    return StreamingResponse(
        _stream_backend(payload, trace_id, request_started),
        media_type="audio/wav",
        headers={"X-AIRI-Request-ID": trace_id},
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8891)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
