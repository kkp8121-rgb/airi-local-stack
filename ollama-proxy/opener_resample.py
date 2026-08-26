"""Default-off, request-local opener resampling helpers."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any


OPENER_RESAMPLE_ENV = "AIRI_OPENER_RESAMPLE"
OPENER_RESAMPLE_TEMPERATURE = 0.9
_TRUE_VALUES = frozenset({"1", "true", "on", "yes"})
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def opener_resample_enabled(value: object | None = None) -> bool:
    """Read the opt-in switch; invalid and absent values stay disabled."""
    if value is None:
        value = os.environ.get(OPENER_RESAMPLE_ENV, "")
    return isinstance(value, str) and value.strip().casefold() in _TRUE_VALUES


def opener_words(text: object) -> tuple[str, ...]:
    """Return the first two Unicode words without treating punctuation as text."""
    if not isinstance(text, str):
        return ()
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return tuple(_WORD_RE.findall(normalized)[:2])


def previous_assistant_text(messages: object) -> str:
    """Return the latest assistant text before the current user turn."""
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "assistant":
            content = message.get("content")
            return content if isinstance(content, str) else ""
    return ""


def extract_seed(payload: object) -> int | None:
    """Read an explicit integer seed without inventing one for the caller."""
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
    if not isinstance(payload, dict):
        return None
    options = payload.get("options")
    value = (
        options.get("seed")
        if isinstance(options, dict) and "seed" in options
        else payload.get("seed")
    )
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def resample_overrides(
    previous_text: object,
    draft_text: object,
    payload: object,
    *,
    enabled: bool | None = None,
) -> dict[str, object] | None:
    """Return the one allowed decoding change when the frozen S2 shape matches."""
    if enabled is None:
        enabled = opener_resample_enabled()
    if not enabled:
        return None
    previous = previous_text if isinstance(previous_text, str) else ""
    draft = draft_text if isinstance(draft_text, str) else ""
    if not previous.rstrip().endswith("?") or not draft.rstrip().endswith("?"):
        return None
    previous_words = opener_words(previous)
    draft_words = opener_words(draft)
    if len(previous_words) != 2 or previous_words != draft_words:
        return None
    seed = extract_seed(payload)
    if seed is None:
        return None
    return {"seed": seed + 1, "temperature": OPENER_RESAMPLE_TEMPERATURE}


def apply_resample_overrides(body: bytes, overrides: dict[str, object]) -> bytes:
    """Apply S2 decoding values to either OpenAI-shaped or native payloads."""
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("prepared payload is invalid")
    for key, value in overrides.items():
        payload[key] = value
    options = payload.get("options")
    if isinstance(options, dict):
        options.update(overrides)
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")
