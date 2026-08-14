"""Deterministic pre-publication checks for unsupported confidence.

This module deliberately does not moderate language or model output.  It
classifies the latest user turn before generation, where a streamed claim can
still be safely replaced with a short, honest response.
"""
from __future__ import annotations

import re
import threading
import unicodedata
from dataclasses import dataclass


MODE_OFF = "off"
MODE_ENFORCE = "enforce"

CURRENT_STATE_FALLBACK = "지금 상태를 확인할 근거가 없어서 단정할 수 없어."
UNSUPPORTED_AGREEMENT_FALLBACK = "근거 없이 무조건 맞다고 동의하진 않을게."
UNRESOLVED_REFERENCE_FALLBACK = "어떤 대상을 말하는지 조금만 더 알려 줘."

_TRUE = {"1", "true", "yes", "on", "enabled"}
_FALSE = {"0", "false", "no", "off", "disabled", ""}
_CURRENT_TIME = re.compile(
    r"\b(?:current|currently|latest|live|today|now|right\s+now|real[ -]?time)\b|"
    r"(?:지금|현재|오늘|실시간|최신)", re.IGNORECASE,
)
_VOLATILE_FACT = re.compile(
    r"\b(?:status|server|patch|update|weather|price|stock|schedule|ranking|news|"
    r"release|availability|open|online)\b|"
    r"(?:현황|상태|서버|패치|업데이트|날씨|가격|재고|일정|순위|뉴스|출시|"
    r"영업|접속|온라인|열렸|닫혔|적용됐|가능해)", re.IGNORECASE,
)
_AGREEMENT = re.compile(
    r"\b(?:just|simply|unconditionally|always)\s+(?:agree|say yes)\b|"
    r"\b(?:agree with me|say yes to me|validate me)\b|"
    r"(?:무조건|그냥)\s*(?:동의|맞다고|찬성)", re.IGNORECASE,
)
_DEICTIC_ONLY = re.compile(
    r"^\s*(?:this|that|it|these|those|그거|이거|저거|그것|이것|저것)"
    r"(?:\s*(?:again|mean|refer|다시|뭐|누구|어떻게|해\s*줘|말해\s*줘).*)?[?.!]*\s*$",
    re.IGNORECASE,
)
_SHORT_ENTITY_QUESTION = re.compile(
    r"^\s*([가-힣]{2,8}?)(?:이|가|은|는)?\s*(?:누구|뭐)(?:야|예요|에요|지)?\s*[?？]?\s*$"
)


@dataclass(frozen=True)
class EpistemicVerdict:
    reason: str = ""
    fallback: str = ""

    @property
    def blocked(self) -> bool:
        return bool(self.fallback)


class EpistemicConfidenceRuntime:
    """Content-free telemetry plus deterministic request classification."""

    def __init__(self, *, enabled: bool = False, mode: str = MODE_OFF) -> None:
        self.enabled = enabled
        self.mode = mode
        self._counters = {"checked": 0, "blocked": 0, "live_state": 0, "agreement": 0, "reference": 0}
        self._lock = threading.Lock()

    def inspect(self, messages: list[dict[str, object]], user_text: str, *, approved_evidence: bool = False) -> EpistemicVerdict:
        if not self.enabled:
            return EpistemicVerdict()
        with self._lock:
            self._counters["checked"] += 1
        # Request-role messages are caller-controlled and never establish
        # provenance. Only an internal caller that already validated a
        # claim-bound evidence record may set approved_evidence.
        if approved_evidence:
            return EpistemicVerdict()
        text = _normalise(user_text)
        if _CURRENT_TIME.search(text) and _VOLATILE_FACT.search(text):
            return self._blocked("live_state", CURRENT_STATE_FALLBACK)
        if _AGREEMENT.search(text):
            return self._blocked("agreement", UNSUPPORTED_AGREEMENT_FALLBACK)
        if _DEICTIC_ONLY.match(text) and not _has_prior_dialogue(messages):
            return self._blocked("reference", UNRESOLVED_REFERENCE_FALLBACK)
        entity = _SHORT_ENTITY_QUESTION.match(text)
        if entity and not _entity_has_context(messages, entity.group(1)):
            return self._blocked("reference", UNRESOLVED_REFERENCE_FALLBACK)
        return EpistemicVerdict()

    def _blocked(self, reason: str, fallback: str) -> EpistemicVerdict:
        with self._lock:
            self._counters["blocked"] += 1
            self._counters[reason] += 1
        return EpistemicVerdict(reason=reason, fallback=fallback)

    def health(self) -> dict[str, object]:
        with self._lock:
            counters = dict(self._counters)
        return {"enabled": self.enabled, "mode": self.mode, "counters": counters}


def build_runtime(enabled_value: object, mode_value: object) -> EpistemicConfidenceRuntime:
    """Parse an explicit opt-in; invalid enabled configuration stops startup."""
    enabled_text = _normalise(enabled_value).casefold()
    if enabled_text in _FALSE:
        return EpistemicConfidenceRuntime()
    if enabled_text not in _TRUE:
        raise ValueError("AIRI_EPISTEMIC_CONFIDENCE must be an explicit on/off value")
    mode = _normalise(mode_value).casefold()
    if mode != MODE_ENFORCE:
        raise ValueError("AIRI_EPISTEMIC_CONFIDENCE_MODE must be 'enforce' when enabled")
    return EpistemicConfidenceRuntime(enabled=True, mode=mode)


def _normalise(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _has_prior_dialogue(messages: list[dict[str, object]]) -> bool:
    latest_user_index = max(
        (index for index, message in enumerate(messages) if message.get("role") == "user"),
        default=len(messages),
    )
    return any(
        message.get("role") in {"user", "assistant"} and bool(str(message.get("content") or "").strip())
        for message in messages[:latest_user_index]
    )


def _entity_has_context(messages: list[dict[str, object]], entity: str) -> bool:
    latest_user_index = max(
        (index for index, message in enumerate(messages) if message.get("role") == "user"),
        default=len(messages),
    )
    return any(
        message.get("role") in {"user", "assistant", "tool", "function"}
        and entity in str(message.get("content") or "")
        for message in messages[:latest_user_index]
    )
