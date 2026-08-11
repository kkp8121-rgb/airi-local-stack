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
from fastapi.responses import JSONResponse, Response, StreamingResponse
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
# The reference recording ships with this repository, so a fresh clone works
# without machine-specific paths. GPT_SOVITS_REFERENCE_AUDIO still overrides it.
DEFAULT_REFERENCE_AUDIO = PROJECT_ROOT / "chatterbox" / "voices" / "airi-reference.wav"
REFERENCE_AUDIO = os.environ.get("GPT_SOVITS_REFERENCE_AUDIO", str(DEFAULT_REFERENCE_AUDIO))
PROMPT_LANG = os.environ.get("GPT_SOVITS_PROMPT_LANG", "ja")
PROMPT_TEXT = os.environ.get(
    "GPT_SOVITS_PROMPT_TEXT",
    "声聞こえてるかどうかだけ教えてほしいんだけどなぁ。聞こえてる？あ、よかった。ふぅ。",
)
STREAMING_MODE = int(os.environ.get("GPT_SOVITS_STREAMING_MODE", "2"))
MIN_CHUNK_LENGTH = int(os.environ.get("GPT_SOVITS_MIN_CHUNK_LENGTH", "16"))
# One request may hold the engine lock for at most this long, so a stuck backend
# cannot block every other speech request behind it.
BACKEND_TIMEOUT_SECONDS = float(os.environ.get("GPT_SOVITS_BACKEND_TIMEOUT", "15"))
# AIRI speaks one sentence chunk at a time; anything longer is a caller bug that
# would otherwise occupy the engine lock for the whole backend timeout.
MAX_INPUT_CHARS = int(os.environ.get("TTS_MAX_INPUT_CHARS", "300"))
# GPT-SoVITS streams RIFF/WAVE only, and AIRI consumes WAV. Advertising anything
# else would hand the caller a container it did not ask for.
SUPPORTED_RESPONSE_FORMATS = ("wav",)
WAV_HEADER_BYTES = 44
# Acquired by the request handler and released by the streaming generator, which
# run on different threadpool threads. That is why this is a plain (non-owner
# bound) Lock rather than an RLock.
TTS_LOCK = threading.Lock()
# These short acknowledgements are intentionally fixed application phrases.  Only
# their synthesized WAV bytes live in memory; user-provided speech is never cached.
IMMEDIATE_RESPONSE_TEXTS = ("응!", "바로 찾아볼게.")
_WAV_CACHE: dict[str, bytes] = {}
_WAV_CACHE_STATUS: dict[str, str] = {text: "pending" for text in IMMEDIATE_RESPONSE_TEXTS}
_WAV_CACHE_LOCK = threading.Lock()


class SpeechRequest(BaseModel):
    model: str = "tts-1-ko"
    input: str
    voice: str = "airi-vtuber"
    response_format: str = "wav"
    speed: float = 1.0


def reference_audio_exists() -> bool:
    """Report whether the configured reference recording is readable right now."""
    try:
        return Path(REFERENCE_AUDIO).is_file()
    except OSError:
        return False


@app.get("/health")
def health():
    try:
        response = HTTP.get(GPT_TTS_URL.rsplit("/", 1)[0] + "/docs", timeout=2)
        backend = response.status_code < 500
    except requests.RequestException:
        backend = False
    # A missing reference clip makes every synthesis fail inside the backend, so
    # it must degrade the health status instead of surfacing later as silence.
    reference_found = reference_audio_exists()
    return {
        "status": "ok" if backend and reference_found else "degraded",
        "engine": "gpt-sovits-v2ProPlus",
        "backend_url": GPT_TTS_URL,
        "reference_audio": REFERENCE_AUDIO,
        "reference_audio_found": reference_found,
        "immediate_response_cache": cache_health(),
    }


@app.get("/v1/models")
@app.get("/models")
def models():
    return {"object": "list", "data": [{"id": "tts-1-ko", "object": "model", "owned_by": "local-gpt-sovits"}]}


def build_backend_payload(text: str, speed: float = 1.0) -> dict:
    """Build the existing GPT-SoVITS payload in one testable place."""
    return {
        "text": text,
        "text_lang": "ko",
        "ref_audio_path": REFERENCE_AUDIO,
        "prompt_lang": PROMPT_LANG,
        "prompt_text": PROMPT_TEXT,
        "streaming_mode": STREAMING_MODE,
        "min_chunk_length": MIN_CHUNK_LENGTH,
        "speed_factor": speed,
        "parallel_infer": False,
        "media_type": "wav",
    }


def cached_wav_for_request(text: str, response_format: str, speed: float) -> bytes | None:
    """Return a preload only when it is byte-for-byte compatible with the request."""
    if response_format.casefold() != "wav" or speed != 1.0 or text not in IMMEDIATE_RESPONSE_TEXTS:
        return None
    with _WAV_CACHE_LOCK:
        return _WAV_CACHE.get(text)


def cache_health() -> dict:
    with _WAV_CACHE_LOCK:
        states = dict(_WAV_CACHE_STATUS)
    return {"ready": sum(state == "ready" for state in states.values()), "total": len(states), "states": states}


def _fetch_wav_from_backend(payload: dict) -> bytes:
    """Fetch a complete WAV for startup warmup while holding the engine lock."""
    with TTS_LOCK:
        with HTTP.post(GPT_TTS_URL, json=payload, stream=True, timeout=BACKEND_TIMEOUT_SECONDS) as response:
            if response.status_code != 200:
                raise RuntimeError(f"GPT-SoVITS returned {response.status_code}: {response.text[:500]}")
            audio = b"".join(chunk for chunk in response.iter_content(4096) if chunk)
    if not audio:
        raise RuntimeError("GPT-SoVITS returned an empty WAV")
    return audio


def warm_immediate_response_cache() -> None:
    """Best-effort server-start warmup. Each failure leaves normal streaming intact."""
    for text in IMMEDIATE_RESPONSE_TEXTS:
        with _WAV_CACHE_LOCK:
            _WAV_CACHE_STATUS[text] = "warming"
        try:
            audio = _fetch_wav_from_backend(build_backend_payload(text))
            with _WAV_CACHE_LOCK:
                _WAV_CACHE[text] = audio
                _WAV_CACHE_STATUS[text] = "ready"
        except Exception as exc:
            logger.warning("immediate response cache warmup failed for configured phrase: %s", exc)
            with _WAV_CACHE_LOCK:
                _WAV_CACHE.pop(text, None)
                _WAV_CACHE_STATUS[text] = "failed"


@app.on_event("startup")
def warm_cache_on_startup() -> None:
    if not reference_audio_exists():
        logger.warning(
            "reference audio was not found at %s; synthesis will fail until the file "
            "exists or GPT_SOVITS_REFERENCE_AUDIO points at a readable WAV",
            REFERENCE_AUDIO,
        )
    # Warmup synthesizes real audio and uvicorn binds the port only after every
    # startup handler returns, so run it on a background thread. /health reports
    # the progress through immediate_response_cache.
    threading.Thread(
        target=warm_immediate_response_cache,
        name="airi-tts-cache-warmup",
        daemon=True,
    ).start()


class _BackendStream:
    """Owns TTS_LOCK plus one backend response until the body has been drained.

    The lock is taken in the request handler so a backend error can still become
    a real HTTP error, and released here once the response body is finished. It
    is therefore held for the entire generation, exactly as before.
    """

    def __init__(self, response: requests.Response, lock_wait_ms: float) -> None:
        self.response = response
        self.lock_wait_ms = lock_wait_ms
        self._release_guard = threading.Lock()
        self._released = False

    def release(self) -> None:
        """Close the backend response and release the engine lock exactly once.

        Closing an unfinished streaming response drops the underlying socket
        instead of returning it to the keep-alive pool. That is the intended
        trade-off: cancellation is rare, the session simply opens a new
        connection, and severing the socket is what stops GPT-SoVITS from
        synthesizing audio nobody will hear.
        """
        with self._release_guard:
            if self._released:
                return
            self._released = True
        try:
            self.response.close()
        finally:
            TTS_LOCK.release()


def open_backend_stream(payload: dict) -> _BackendStream:
    """Take the engine lock and return once the backend response headers arrive.

    GPT-SoVITS generations must not overlap: mixed streams sound like murmuring
    when AIRI sends adjacent sentence chunks concurrently. Ownership of the lock
    moves to the returned object, which must always be released by the caller.
    """
    lock_started = time.perf_counter()
    TTS_LOCK.acquire()
    lock_wait_ms = elapsed_ms(lock_started)
    try:
        response = HTTP.post(GPT_TTS_URL, json=payload, stream=True, timeout=BACKEND_TIMEOUT_SECONDS)
    except BaseException:
        TTS_LOCK.release()
        raise
    return _BackendStream(response, lock_wait_ms)


def _stream_backend(
    stream: _BackendStream,
    trace_id: str,
    request_started: float,
) -> Iterator[bytes]:
    """Relay an already-validated 200 response body and free the engine lock."""
    total_bytes = 0
    phase = "end"
    event_meta: dict[str, int | float] = {}
    try:
        emitted_first = False
        for chunk in stream.response.iter_content(4096):
            if not chunk:
                continue
            if not emitted_first:
                emit_latency_event(
                    "tts",
                    "first",
                    trace_id,
                    duration_ms=elapsed_ms(request_started),
                    meta={"lock_wait_ms": stream.lock_wait_ms},
                )
                emitted_first = True
            total_bytes += len(chunk)
            yield chunk
    except GeneratorExit:
        # AIRI dropped the connection (barge-in or a new turn). uvicorn cancels
        # the streaming task, so the release() below closes the backend socket
        # and GPT-SoVITS stops generating audio nobody will hear. Without that,
        # the engine lock stayed busy for the rest of the abandoned utterance.
        # Reported as "error" with client_cancelled=1 because the latency
        # monitor only accepts start/first/end/error phases.
        phase = "error"
        event_meta = {"client_cancelled": 1, "bytes": total_bytes}
        raise
    except requests.RequestException as exc:
        # The backend cut the stream after the headers were already sent. Abort
        # the transfer so the client sees a broken download instead of a
        # silently truncated utterance.
        phase = "error"
        event_meta = {"backend_truncated": 1, "bytes": total_bytes}
        raise RuntimeError(f"GPT-SoVITS stream ended early: {exc}") from exc
    except Exception:
        phase = "error"
        event_meta = {"stream_failed": 1, "bytes": total_bytes}
        raise
    else:
        event_meta = {"bytes": total_bytes}
        if total_bytes <= WAV_HEADER_BYTES:
            # HTTP 200 carrying nothing but a WAV header is the silent-playback
            # failure mode, so never record it as a successful generation.
            phase = "error"
            event_meta = {"empty_body": 1, "bytes": total_bytes}
            logger.error("GPT-SoVITS returned %d bytes, which contains no audio", total_bytes)
    finally:
        # Always first: this closes the backend stream and frees the engine lock
        # for the next sentence, including on cancellation.
        stream.release()
        emit_latency_event(
            "tts",
            phase,
            trace_id,
            duration_ms=elapsed_ms(request_started),
            meta=event_meta,
        )


class _EngineStreamingResponse(StreamingResponse):
    """StreamingResponse that always hands the engine lock back.

    Starlette abandons the body iterator when the client disconnects instead of
    closing it, so a barge-in would otherwise keep TTS_LOCK and the backend
    generation alive until the generator happened to be garbage collected.
    Releasing here is the one point that runs on every exit path, including
    ClientDisconnect and cancellation.
    """

    def __init__(self, stream: _BackendStream, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._stream = stream

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Idempotent, so the generator's own finally may also reach it.
            self._stream.release()


def _backend_error_response(trace_id: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"error": {"message": message, "type": "gpt_sovits_backend_error"}},
        headers={"X-AIRI-Request-ID": trace_id},
    )


@app.post("/v1/audio/speech")
@app.post("/audio/speech")
def speech(request: SpeechRequest, http_request: Request):
    text = request.input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="input text is empty")
    if len(text) > MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"input text is {len(text)} characters; the limit is {MAX_INPUT_CHARS}",
        )
    if request.response_format.casefold() not in SUPPORTED_RESPONSE_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"GPT-SoVITS proxy only supports response_format=wav, "
                f"not '{request.response_format}'"
            ),
        )
    trace_id = request_id(http_request.headers, uuid4().hex)
    request_started = time.perf_counter()
    emit_latency_event(
        "tts",
        "start",
        trace_id,
        meta={"text_chars": len(text)},
    )
    payload = build_backend_payload(text, request.speed)
    logger.info(
        "speech request path=/audio/speech model=%s voice=%s chars=%d user_agent=%s origin=%s",
        request.model,
        request.voice,
        len(text),
        http_request.headers.get("user-agent", "-"),
        http_request.headers.get("origin", "-"),
    )
    cached_audio = cached_wav_for_request(text, request.response_format, request.speed)
    if cached_audio is not None:
        latency = elapsed_ms(request_started)
        emit_latency_event("tts", "first", trace_id, duration_ms=latency, meta={"cache_hit": 1})
        emit_latency_event("tts", "end", trace_id, duration_ms=latency, meta={"cache_hit": 1})
        return Response(
            content=cached_audio,
            media_type="audio/wav",
            headers={"X-AIRI-Request-ID": trace_id, "X-AIRI-TTS-Cache": "hit"},
        )
    # Contact the backend before the streaming response starts. Returning a
    # StreamingResponse first would turn every backend failure into "HTTP 200
    # with zero audio bytes", which is indistinguishable from silence.
    try:
        stream = open_backend_stream(payload)
    except requests.RequestException as exc:
        emit_latency_event(
            "tts",
            "error",
            trace_id,
            duration_ms=elapsed_ms(request_started),
            meta={"backend_unreachable": 1},
        )
        logger.error("GPT-SoVITS backend unavailable: %s", exc)
        return _backend_error_response(trace_id, f"GPT-SoVITS backend unavailable: {exc}")
    if stream.response.status_code != 200:
        status_code = stream.response.status_code
        detail = stream.response.text[:500]
        stream.release()
        emit_latency_event(
            "tts",
            "error",
            trace_id,
            duration_ms=elapsed_ms(request_started),
            meta={"backend_status": status_code},
        )
        logger.error("GPT-SoVITS returned %d: %s", status_code, detail)
        return _backend_error_response(trace_id, f"GPT-SoVITS returned {status_code}: {detail}")
    return _EngineStreamingResponse(
        stream,
        _stream_backend(stream, trace_id, request_started),
        media_type="audio/wav",
        headers={"X-AIRI-Request-ID": trace_id},
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8880)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
