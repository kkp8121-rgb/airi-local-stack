"""Small, dependency-free gate for pending behavior answers."""
from __future__ import annotations

import re
from typing import Any, Mapping


class BehaviorAnswerGateError(ValueError):
    """Raised when a candidate behavior answer is unsafe or malformed."""


_QUOTE_SPANS = re.compile(r"[\"“”'‘’「」『』]([^\"“”'‘’「」『』]{0,200})[\"“”'‘’「」『』]")
_SENTENCE_SPLIT = re.compile(r"[.!?…。？！]+|\n+")
_POLITE_END = re.compile(r"(요|죠|쥬|니다|십시오|나이다)\s*$")
_INTERNAL = re.compile(
    r"(?:airi_|schema|primary|valence|arousal|dominance|intensity|drive|"
    r"safety_tone|expression_mode|response_mode|mood_mode|enum|"
    r"playful_annoyed|safety_override|moderation_block|내 상태는|감정 상태)",
    re.I,
)
_HOSTILE = re.compile(r"(?:병신|멍청|바보|죽어|꺼져|혐오|쓸모없)")
_ACUTE_FORBIDDEN = re.compile(r"(?:진단|처방|약을|복용|호흡법|심호흡)")


def validate_behavior_answer(record: Mapping[str, Any], answer: str, minimum: int = 1,
                             maximum: int = 160) -> None:
    """Validate a natural Korean reply; affect metadata enables stricter checks."""
    if not isinstance(answer, str) or not minimum <= len(answer) <= maximum:
        raise BehaviorAnswerGateError("answer length is outside the allowed range")
    unquoted = _QUOTE_SPANS.sub(" ", answer)
    sentences = [part.strip() for part in _SENTENCE_SPLIT.split(unquoted) if part.strip()]
    if any(_POLITE_END.search(sentence) for sentence in sentences):
        raise BehaviorAnswerGateError("polite register is not allowed")
    if "affect_state" not in record:
        return
    if _INTERNAL.search(answer):
        raise BehaviorAnswerGateError("internal affect metadata leaked into answer")
    if _HOSTILE.search(answer):
        raise BehaviorAnswerGateError("hostile or insulting answer")
    required = record.get("must_include_any", [])
    if required and not any(token in answer for token in required):
        raise BehaviorAnswerGateError("answer misses required content")
    if any(token in answer for token in record.get("must_not_include", [])):
        raise BehaviorAnswerGateError("answer contains forbidden content")
    safety = record.get("safety_class")
    if safety == "acute_physical":
        if not any(token in answer for token in ("주변 사람", "119", "현지 응급")):
            raise BehaviorAnswerGateError("acute safety answer lacks immediate help guidance")
        if _ACUTE_FORBIDDEN.search(answer):
            raise BehaviorAnswerGateError("acute safety answer gives medical instruction")
    if safety == "moderation_boundary" and ("119" in answer or "응급" in answer):
        raise BehaviorAnswerGateError("moderation boundary must not impersonate emergency guidance")
