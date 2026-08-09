"""Best-effort, non-blocking telemetry for the local AIRI latency monitor."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import urllib.request
from collections.abc import Mapping
from typing import Any


MONITOR_URL = os.environ.get(
    "AIRI_LATENCY_MONITOR_URL",
    "http://127.0.0.1:8892/api/event",
)
_EVENTS: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=128)
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()


def timestamp_ms() -> int:
    return time.time_ns() // 1_000_000


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def request_id(headers: Mapping[str, str], fallback: str) -> str:
    """Resolve one turn-scoped correlation id across LLM, STT, and TTS.

    AIRI's ``x-airi-round-id`` is the authoritative per-round identifier.  The
    older request headers remain supported for callers which have not yet been
    upgraded, while the random fallback preserves the existing fail-soft
    telemetry behavior.
    """
    return (
        headers.get("x-airi-round-id")
        or headers.get("x-airi-request-id")
        or headers.get("x-request-id")
        or fallback
    )[:128]


def _sender() -> None:
    while True:
        payload = _EVENTS.get()
        try:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            request = urllib.request.Request(
                MONITOR_URL,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=0.1):
                pass
        except Exception:
            # Telemetry must never delay or break the speech pipeline.
            pass
        finally:
            _EVENTS.task_done()


def _ensure_worker() -> None:
    global _WORKER_STARTED
    if _WORKER_STARTED:
        return
    with _WORKER_LOCK:
        if not _WORKER_STARTED:
            threading.Thread(
                target=_sender,
                name="airi-latency-trace",
                daemon=True,
            ).start()
            _WORKER_STARTED = True


def emit_latency_event(
    source: str,
    phase: str,
    request_id_value: str,
    *,
    duration_ms: float | None = None,
    meta: Mapping[str, int | float | bool] | None = None,
    event_timestamp_ms: int | None = None,
) -> None:
    """Queue a numeric-only event and immediately return to the caller."""
    _ensure_worker()
    clean_meta = {
        str(key)[:48]: value
        for key, value in (meta or {}).items()
        if isinstance(value, (int, float, bool))
    }
    payload: dict[str, Any] = {
        "source": source,
        "phase": phase,
        "request_id": request_id_value,
        "timestamp_ms": event_timestamp_ms or timestamp_ms(),
        "meta": clean_meta,
    }
    if duration_ms is not None:
        payload["duration_ms"] = round(duration_ms, 1)
    try:
        _EVENTS.put_nowait(payload)
    except queue.Full:
        pass
