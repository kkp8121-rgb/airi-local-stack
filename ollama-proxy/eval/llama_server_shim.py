"""Evaluation-only Ollama-compatible shim in front of llama.cpp's llama-server.

The AIRI proxy speaks Ollama's native ``/api/chat`` NDJSON to 127.0.0.1:11434 and
is not modified for this experiment.  This shim takes that port (with Ollama
stopped), relays the request to llama-server's OpenAI-shaped
``/v1/chat/completions``, and translates the SSE answer back into the exact
NDJSON rows the proxy already parses.  Generation constraints such as
``logit_bias`` are applied by llama-server's startup flags, so nothing here
inspects or rewrites prompt material: the served constraint is the only changed
variable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Mapping, Sequence

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11434
DEFAULT_LLAMA_SERVER = "http://127.0.0.1:11500"
DEFAULT_MODEL = "midm-airi:2.0-mini"
DEFAULT_DIGEST = "106cfaacc185aec489ccbddd82894d6558aac745444b844a73cef4ea450e9f6c"
DEFAULT_TIMEOUT_SECONDS = 600.0
UPSTREAM_CONNECT_TIMEOUT_SECONDS = 5.0
# Size of the pinned GGUF blob the evaluation runs against.  /api/tags only has
# to be shaped like Ollama's; the digest is what the proxy actually binds to.
DEFAULT_MODEL_SIZE_BYTES = 1_426_272_672
NDJSON_CONTENT_TYPE = "application/x-ndjson"
SSE_DATA_PREFIX = "data:"
SSE_TERMINATOR = "[DONE]"
UPSTREAM_ERROR_DETAIL_MAX_CHARS = 500
# Only used when llama-server reports no usage block.  A count of zero would be
# read by the proxy's prompt-budget telemetry as a real observation, so fall
# back to a stated estimate instead: one streamed chunk is one generated token,
# and Korean prompt text runs near two characters per token on this tokenizer.
ESTIMATED_CHARS_PER_TOKEN = 2.0


def utc_now_iso() -> str:
    """Return an Ollama-shaped RFC 3339 timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _int_or_zero(value: object) -> int:
    """Coerce a duration/count to a non-negative int, defaulting to zero."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    if isinstance(value, float) and value != value:  # NaN
        return 0
    return max(int(value), 0)


def ollama_request_to_openai(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Translate one Ollama-native ``/api/chat`` body into an OpenAI body.

    ``num_ctx`` and ``num_gpu`` are dropped on purpose: llama-server fixes both
    at startup.  Messages are passed through untouched.
    """
    raw_options = payload.get("options")
    options: Mapping[str, Any] = raw_options if isinstance(raw_options, Mapping) else {}
    request: dict[str, Any] = {
        "model": payload.get("model"),
        "messages": payload.get("messages", []),
        "stream": bool(payload.get("stream", True)),
    }
    num_predict = options.get("num_predict")
    if isinstance(num_predict, int) and not isinstance(num_predict, bool) and num_predict > 0:
        request["max_tokens"] = num_predict
    # The proxy stamps OLLAMA_SAMPLING_DEFAULTS onto every request; relaying all
    # three keeps the Stage 2 run different from run-89 only by the serving
    # layer's token suppression.
    for ollama_key, openai_key in (
        ("temperature", "temperature"),
        ("top_p", "top_p"),
        ("repeat_penalty", "repeat_penalty"),
    ):
        value = options.get(ollama_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            request[openai_key] = value
    seed = options.get("seed")
    if isinstance(seed, int) and not isinstance(seed, bool):
        request["seed"] = seed
    stop = options.get("stop")
    if isinstance(stop, str) and stop:
        request["stop"] = [stop]
    elif isinstance(stop, Sequence) and not isinstance(stop, (str, bytes)):
        entries = [item for item in stop if isinstance(item, str) and item]
        if entries:
            request["stop"] = entries
    return request


def parse_openai_sse_payload(line: str) -> dict[str, Any] | None:
    """Return the JSON object of one OpenAI SSE ``data:`` line, else ``None``."""
    if not isinstance(line, str):
        return None
    stripped = line.strip()
    if not stripped.startswith(SSE_DATA_PREFIX):
        return None
    body = stripped[len(SSE_DATA_PREFIX):].strip()
    if not body or body == SSE_TERMINATOR:
        return None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def openai_delta_content(payload: Mapping[str, Any]) -> str | None:
    """Return the generated text of one OpenAI streaming chunk, else ``None``."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, Mapping):
        return None
    delta = first.get("delta")
    if not isinstance(delta, Mapping):
        return None
    content = delta.get("content")
    return content if isinstance(content, str) and content else None


def parse_openai_sse_line(line: str) -> str | None:
    """Return the delta text carried by one SSE line, else ``None``."""
    payload = parse_openai_sse_payload(line)
    return openai_delta_content(payload) if payload is not None else None


def openai_finish_reason(payload: Mapping[str, Any]) -> str:
    """Return the finish reason of one OpenAI chunk, or an empty string."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, Mapping):
        return ""
    reason = first.get("finish_reason")
    return reason if isinstance(reason, str) and reason else ""


def openai_usage(payload: Mapping[str, Any]) -> dict[str, int]:
    """Return the token counts of one OpenAI payload, when it carries them."""
    usage = payload.get("usage")
    if not isinstance(usage, Mapping):
        return {}
    counts: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens"):
        value = usage.get(key)
        if not isinstance(value, bool) and isinstance(value, (int, float)):
            counts[key] = _int_or_zero(value)
    return counts


def estimate_prompt_tokens(messages: object) -> int:
    """Estimate prompt tokens from message text when upstream reports none."""
    if not isinstance(messages, list):
        return 0
    chars = 0
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        content = message.get("content")
        if isinstance(content, str):
            chars += len(content)
    return int(chars / ESTIMATED_CHARS_PER_TOKEN) if chars else 0


def openai_delta_to_ollama_line(model: str, content: str, created_at: str) -> dict[str, Any]:
    """Build one non-terminal Ollama NDJSON row."""
    return {
        "model": model,
        "created_at": created_at,
        "message": {"role": "assistant", "content": content},
        "done": False,
    }


def ollama_final_line(
    model: str,
    created_at: str,
    usage: Mapping[str, Any],
    durations: Mapping[str, Any],
    done_reason: str = "stop",
) -> dict[str, Any]:
    """Build the terminal Ollama NDJSON row, keys and order as measured."""
    usage = usage if isinstance(usage, Mapping) else {}
    durations = durations if isinstance(durations, Mapping) else {}
    return {
        "model": model,
        "created_at": created_at,
        "message": {"role": "assistant", "content": ""},
        "done": True,
        "done_reason": done_reason,
        "total_duration": _int_or_zero(durations.get("total_duration")),
        "load_duration": _int_or_zero(durations.get("load_duration")),
        "prompt_eval_count": _int_or_zero(usage.get("prompt_tokens")),
        "prompt_eval_duration": _int_or_zero(durations.get("prompt_eval_duration")),
        "eval_count": _int_or_zero(usage.get("completion_tokens")),
        "eval_duration": _int_or_zero(durations.get("eval_duration")),
    }


def encode_ndjson_line(row: Mapping[str, Any]) -> bytes:
    """Serialize one NDJSON row exactly as Ollama frames it."""
    return json.dumps(row, ensure_ascii=False).encode("utf-8") + b"\n"


def ollama_tag_entry(model: str, digest: str, modified_at: str) -> dict[str, Any]:
    """Build the single ``/api/tags`` entry the proxy validates against."""
    return {
        "name": model,
        "model": model,
        "digest": digest,
        "size": DEFAULT_MODEL_SIZE_BYTES,
        "modified_at": modified_at,
    }


def _log(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def _error_response(message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=502)


def create_app(
    *,
    llama_server: str = DEFAULT_LLAMA_SERVER,
    model: str = DEFAULT_MODEL,
    digest: str = DEFAULT_DIGEST,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> FastAPI:
    """Build the shim application bound to one llama-server upstream."""
    upstream = llama_server.rstrip("/")
    chat_url = f"{upstream}/v1/chat/completions"
    started_at = utc_now_iso()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        limits = httpx.Timeout(timeout, connect=UPSTREAM_CONNECT_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=limits) as client:
            app.state.client = client
            yield
        app.state.client = None

    app = FastAPI(lifespan=lifespan)
    app.state.client = None

    @app.get("/api/tags")
    async def api_tags() -> dict[str, Any]:
        return {"models": [ollama_tag_entry(model, digest, started_at)]}

    @app.post("/api/chat")
    async def api_chat(request: Request) -> Response:
        client = getattr(request.app.state, "client", None)
        if client is None:
            return JSONResponse({"error": "shim upstream client is not ready"}, status_code=503)
        try:
            payload = json.loads(await request.body())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JSONResponse({"error": "request body is not JSON"}, status_code=400)
        if not isinstance(payload, dict):
            return JSONResponse({"error": "request body is not an object"}, status_code=400)

        row_model = payload.get("model") if isinstance(payload.get("model"), str) else model
        upstream_body = ollama_request_to_openai(payload)
        estimated_prompt_tokens = estimate_prompt_tokens(payload.get("messages"))
        started_ns = time.perf_counter_ns()

        if not upstream_body["stream"]:
            return await _relay_buffered(
                client,
                chat_url,
                upstream_body,
                row_model,
                estimated_prompt_tokens,
                started_ns,
            )

        stream = client.stream("POST", chat_url, json=upstream_body)
        try:
            response = await stream.__aenter__()
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            _log("shim_upstream_open_failed", error=type(exc).__name__)
            return _error_response(f"llama-server request failed: {type(exc).__name__}")
        if response.status_code >= 400:
            detail = (await response.aread()).decode("utf-8", errors="replace")
            await stream.__aexit__(None, None, None)
            _log("shim_upstream_status", status=response.status_code)
            return _error_response(
                f"llama-server returned {response.status_code}: "
                f"{detail[:UPSTREAM_ERROR_DETAIL_MAX_CHARS]}"
            )
        headers_ns = time.perf_counter_ns()
        return StreamingResponse(
            _relay_stream(
                stream,
                response,
                row_model,
                estimated_prompt_tokens,
                started_ns,
                headers_ns,
            ),
            media_type=NDJSON_CONTENT_TYPE,
            headers={"Cache-Control": "no-cache"},
        )

    return app


async def _relay_stream(
    stream: Any,
    response: httpx.Response,
    model: str,
    estimated_prompt_tokens: int,
    started_ns: int,
    headers_ns: int,
) -> AsyncIterator[bytes]:
    """Yield Ollama NDJSON rows for one llama-server SSE response."""
    usage: dict[str, int] = {}
    done_reason = "stop"
    content_chunks = 0
    first_content_ns = 0
    last_content_ns = 0
    try:
        async for line in response.aiter_lines():
            chunk = parse_openai_sse_payload(line)
            if chunk is None:
                continue
            usage.update(openai_usage(chunk))
            reason = openai_finish_reason(chunk)
            if reason:
                done_reason = reason
            content = openai_delta_content(chunk)
            if content is None:
                continue
            now = time.perf_counter_ns()
            if first_content_ns == 0:
                first_content_ns = now
            last_content_ns = now
            content_chunks += 1
            yield encode_ndjson_line(
                openai_delta_to_ollama_line(model, content, utc_now_iso())
            )
    except (httpx.HTTPError, asyncio.TimeoutError) as exc:
        # A partial generation still has to be closed with a terminal row, or
        # the proxy would raise on an incomplete NDJSON stream.  The failure is
        # reported in done_reason instead of being silently relabelled "stop".
        done_reason = "error"
        _log("shim_upstream_stream_failed", error=type(exc).__name__, chunks=content_chunks)
    finally:
        await stream.__aexit__(None, None, None)
    end_ns = time.perf_counter_ns()
    usage.setdefault("prompt_tokens", estimated_prompt_tokens)
    usage.setdefault("completion_tokens", content_chunks)
    yield encode_ndjson_line(
        ollama_final_line(
            model,
            utc_now_iso(),
            usage,
            {
                "total_duration": end_ns - started_ns,
                "load_duration": headers_ns - started_ns,
                "prompt_eval_duration": (first_content_ns - headers_ns) if first_content_ns else 0,
                "eval_duration": (last_content_ns - first_content_ns) if first_content_ns else 0,
            },
            done_reason,
        )
    )


async def _relay_buffered(
    client: httpx.AsyncClient,
    chat_url: str,
    upstream_body: Mapping[str, Any],
    model: str,
    estimated_prompt_tokens: int,
    started_ns: int,
) -> Response:
    """Relay one non-streaming request as a single Ollama-shaped JSON row."""
    try:
        response = await client.post(chat_url, json=dict(upstream_body))
    except (httpx.HTTPError, asyncio.TimeoutError) as exc:
        _log("shim_upstream_request_failed", error=type(exc).__name__)
        return _error_response(f"llama-server request failed: {type(exc).__name__}")
    if response.status_code >= 400:
        detail = response.text[:UPSTREAM_ERROR_DETAIL_MAX_CHARS]
        _log("shim_upstream_status", status=response.status_code)
        return _error_response(f"llama-server returned {response.status_code}: {detail}")
    try:
        payload = response.json()
    except ValueError:
        return _error_response("llama-server returned a non-JSON body")
    if not isinstance(payload, dict):
        return _error_response("llama-server returned a non-object body")

    choices = payload.get("choices")
    choice: Mapping[str, Any] = (
        choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], Mapping) else {}
    )
    message = choice.get("message")
    content = message.get("content") if isinstance(message, Mapping) else ""
    text = content if isinstance(content, str) else ""
    usage = dict(openai_usage(payload))
    usage.setdefault("prompt_tokens", estimated_prompt_tokens)
    usage.setdefault("completion_tokens", 0)
    elapsed_ns = time.perf_counter_ns() - started_ns
    row = ollama_final_line(
        model,
        utc_now_iso(),
        usage,
        {"total_duration": elapsed_ns, "prompt_eval_duration": 0, "eval_duration": elapsed_ns},
        openai_finish_reason(payload) or "stop",
    )
    row["message"]["content"] = text
    return Response(
        content=json.dumps(row, ensure_ascii=False).encode("utf-8"),
        media_type="application/json; charset=utf-8",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluation-only Ollama-compatible shim in front of llama-server.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--llama-server", default=DEFAULT_LLAMA_SERVER)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--digest", default=DEFAULT_DIGEST)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    import uvicorn

    args = build_arg_parser().parse_args(argv)
    app = create_app(
        llama_server=args.llama_server,
        model=args.model,
        digest=args.digest,
        timeout=args.timeout,
    )
    _log(
        "shim_start",
        host=args.host,
        port=args.port,
        llama_server=args.llama_server,
        model=args.model,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
