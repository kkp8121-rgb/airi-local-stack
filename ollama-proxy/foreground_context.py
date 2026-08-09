"""Request-local, conservative foreground dialogue selection.

This module has no runtime state. It deliberately decides continuity from the
shape of adjacent turns, rather than from named topics or application state.
"""
from __future__ import annotations

import re
from typing import Any, Iterable


_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_AIRI_TIMESTAMP_PREFIX_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]\s+")
_ENGLISH_ANAPHORA_RE = re.compile(
    r"\b(?:it|that|this|they|them|those|these|there|then|what about|continue|same)\b",
    re.IGNORECASE,
)
# Explicit referents and continuation words only. Korean discourse connectors
# such as 그래서/그리고/그런데 are intentionally not continuity signals.
_KOREAN_ANAPHORA_RE = re.compile(
    r"(?<![가-힣])(?:그것|그거|이것|이거|저것|저거|거기|그때|"
    r"그\s*(?:부분|얘기|이야기|문제|방법)|계속|다시)"
    r"(?:은|는|이|가|을|를|에|에서|에게|한테|으로|로|도|만|과|와)?"
    r"(?![가-힣])"
)
_KOREAN_PARTICLES = (
    "으로", "에서", "에게", "한테", "처럼", "까지", "부터",
    "은", "는", "이", "가", "을", "를", "의", "에", "도", "만", "과", "와", "로",
)
# Function words are not informative overlap. This is linguistic filtering,
# not a subject, brand, or test-specific allow/deny list.
_FUNCTION_WORDS = frozenset({
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is", "are",
    "was", "were", "i", "you", "we", "me", "my", "your", "please", "can", "do",
    "did", "what", "when", "where", "who", "with", "about", "yeah", "yes", "no",
    "그냥", "좀", "조금", "정말", "진짜", "오늘", "지금", "그래서", "그리고", "그런데",
})


def _text(message: dict[str, Any]) -> str:
    value = message.get("content", "")
    return _AIRI_TIMESTAMP_PREFIX_RE.sub("", value) if isinstance(value, str) else ""


def _normalize_token(token: str) -> str:
    token = token.casefold()
    if re.fullmatch(r"[가-힣]+", token) and len(token) >= 3:
        for particle in _KOREAN_PARTICLES:
            if token.endswith(particle) and len(token) - len(particle) >= 2:
                return token[:-len(particle)]
    return token


def _tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for token in _TOKEN_RE.findall(text):
        if len(token) < 2 and not token.isdecimal():
            continue
        normalized = _normalize_token(token)
        if normalized not in _FUNCTION_WORDS:
            tokens.add(normalized)
    return tokens


def _meaningful(exchange: list[dict[str, Any]]) -> bool:
    text = " ".join(_text(message).strip() for message in exchange)
    return len(_tokens(text)) >= 1 or len(text) >= 12


def _continues(later: str, earlier_exchange: list[dict[str, Any]]) -> bool:
    """Whether *later* structurally refers back to an adjacent exchange."""
    earlier = " ".join(_text(message) for message in earlier_exchange)
    if _tokens(later) & _tokens(earlier):
        return True
    return bool(
        (_ENGLISH_ANAPHORA_RE.search(later) or _KOREAN_ANAPHORA_RE.search(later))
        and _meaningful(earlier_exchange)
    )


def _short_direct_answer(current: str, prior_assistant: dict[str, Any]) -> bool:
    words = _TOKEN_RE.findall(current)
    return bool(words) and len(words) <= 5 and "?" in _text(prior_assistant)


def project_foreground_context(messages: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return at most two bridged exchanges plus the current user message.

    Returned entries are the caller's original objects and are never modified.
    System/card entries are intentionally excluded: callers retain them through
    their existing system-prompt/card pipeline, separately from dialogue.
    """
    dialogue = [message for message in messages if isinstance(message, dict) and message.get("role") != "system"]
    current_index = next((i for i in range(len(dialogue) - 1, -1, -1)
                         if dialogue[i].get("role") == "user"), None)
    if current_index is None:
        return []
    current = dialogue[current_index]
    # Only a structurally complete adjacent U/A pair can be foregrounded.
    exchanges: list[list[dict[str, Any]]] = []
    cursor = current_index - 1
    while cursor >= 1 and len(exchanges) < 2:
        assistant, user = dialogue[cursor], dialogue[cursor - 1]
        if assistant.get("role") != "assistant" or user.get("role") != "user":
            break
        exchanges.append([user, assistant])
        cursor -= 2

    kept: list[list[dict[str, Any]]] = []
    if exchanges and (_continues(_text(current), exchanges[0]) or _short_direct_answer(_text(current), exchanges[0][1])):
        kept.append(exchanges[0])
        # The older pair needs its own bridge into the already-kept pair.
        if len(exchanges) > 1 and _continues(
            " ".join(_text(message) for message in exchanges[0]), exchanges[1]
        ):
            kept.append(exchanges[1])
    return [message for exchange in reversed(kept) for message in exchange] + [current]
