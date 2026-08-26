"""Default-off exact repeated-chat pickup decisions for S4."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re


PICKUP_BATCH_ENV = "AIRI_S4_PICKUP_BATCH"
MIN_CONTENT_TOKENS_ENV = "AIRI_S4_MIN_CONTENT_TOKENS"
PICKUP_BATCH_MIN_REPEATS = 3
MAX_PICKUP_SURFACE_CHARS = 80
_TRUE_VALUES = frozenset({"1", "true", "on"})
_PLATFORM_OR_TIMESTAMP_PREFIX = re.compile(
    r"^\s*(?:\[youtube\]|\[(?:\d{1,2}:){1,2}\d{2}\]|(?:\d{1,2}:){1,2}\d{2})\s*",
    re.IGNORECASE,
)
_CONTENT_TOKEN_RE = re.compile(r"[가-힣]+|[A-Za-z]+|\d+")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class PickupBatchDecision:
    """Structured result for the future request-local integration seam."""

    enabled: bool
    eligible: bool
    surface: str
    content_tokens: int
    consecutive_count: int
    line: str | None


def pickup_batch_enabled(value: object | None = None) -> bool:
    """Return whether the default-off S4 switch was explicitly enabled."""
    if value is None:
        value = os.environ.get(PICKUP_BATCH_ENV, "")
    return isinstance(value, str) and value.strip().casefold() in _TRUE_VALUES


def min_content_tokens(value: object | None = None) -> int:
    """Read a nonnegative content-token floor; invalid values fall back to zero."""
    if value is None:
        value = os.environ.get(MIN_CONTENT_TOKENS_ENV, "0")
    if isinstance(value, bool) or not isinstance(value, str):
        return 0
    try:
        parsed = int(value.strip())
    except ValueError:
        return 0
    return parsed if parsed >= 0 else 0


def strip_platform_timestamp_prefix(text: object) -> str:
    """Remove only leading YouTube and timestamp transport labels."""
    if not isinstance(text, str):
        return ""
    stripped = text
    while True:
        match = _PLATFORM_OR_TIMESTAMP_PREFIX.match(stripped)
        if match is None:
            return stripped.strip()
        stripped = stripped[match.end():]


def normalized_surface(text: object) -> str:
    """Normalize only whitespace and case for exact matching."""
    return _WHITESPACE_RE.sub(" ", strip_platform_timestamp_prefix(text)).strip().casefold()


def content_token_count(text: object) -> int:
    """Count lexical Hangul, Latin, and digit runs after transport-prefix removal."""
    return len(_CONTENT_TOKEN_RE.findall(strip_platform_timestamp_prefix(text)))


def render_pickup_batch_line(surface: object) -> str:
    """Keep the broadcast line code-owned and bounded even for empty input."""
    value = _WHITESPACE_RE.sub(" ", strip_platform_timestamp_prefix(surface)).strip()
    if not value:
        return "다들 그러네"
    if len(value) > MAX_PICKUP_SURFACE_CHARS:
        value = value[:MAX_PICKUP_SURFACE_CHARS].rstrip() + "…"
    return f"다들 {value} 하네"


def _message_text(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and value.get("role") == "user":
        content = value.get("content")
        return content if isinstance(content, str) else None
    return None


def pickup_batch_decision(
    messages: object,
    *,
    enabled: bool | None = None,
    minimum_content_tokens: int | None = None,
) -> PickupBatchDecision:
    """Decide whether the tail has three exact normalized viewer repeats.

    ``messages`` is a chronological list of raw viewer strings, or user-role
    message dictionaries. Non-viewer entries break the consecutive run.
    """
    active = pickup_batch_enabled() if enabled is None else enabled
    minimum = min_content_tokens() if minimum_content_tokens is None else minimum_content_tokens
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
        minimum = 0
    if not isinstance(messages, list) or not messages:
        return PickupBatchDecision(active, False, "", 0, 0, None)
    current = _message_text(messages[-1])
    if current is None:
        return PickupBatchDecision(active, False, "", 0, 0, None)
    surface = normalized_surface(current)
    tokens = content_token_count(current)
    consecutive = 0
    for message in reversed(messages):
        candidate = _message_text(message)
        if candidate is None or normalized_surface(candidate) != surface:
            break
        consecutive += 1
    eligible = active and tokens >= minimum and consecutive >= PICKUP_BATCH_MIN_REPEATS
    return PickupBatchDecision(
        active,
        eligible,
        surface,
        tokens,
        consecutive,
        render_pickup_batch_line(current) if eligible else None,
    )
