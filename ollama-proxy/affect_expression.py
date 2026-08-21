"""Pure, closed-schema affect-to-expression selection for AIRI.

Only :func:`affect_state.validate_state` accepts a state at this boundary.  The
resulting expression contract deliberately contains no user, event, or other
free-text input.
"""

from __future__ import annotations

from typing import Any

from affect_state import AffectValidationError, validate_state


EXPRESSION_SCHEMA_VERSION = "airi.affect-expression.v1"
PROMPT_CAP_BYTES = 384
CONTRACT_KEYS = frozenset((
    "schema_version", "mood_mode", "expression_mode", "response_mode",
    "safety_tone",
))
EXPRESSION_MODES = frozenset((
    "neutral", "question", "think", "curious", "happy", "sad", "angry",
    "surprised",
))
SAFETY_TONES = frozenset(("standard", "gentle", "light", "careful", "boundary"))


_PRIMARY_MODES = {
    "neutral": ("neutral", "standard"),
    "curious": ("curious", "gentle"),
    "amused": ("happy", "light"),
    "pleased": ("happy", "gentle"),
    "proud": ("happy", "gentle"),
    "embarrassed": ("surprised", "gentle"),
    "skeptical": ("think", "standard"),
    "playful_annoyed": ("angry", "light"),
    "concerned": ("sad", "gentle"),
    "disappointed": ("sad", "gentle"),
    "competitive": ("angry", "light"),
    "relieved": ("happy", "gentle"),
    "tired": ("neutral", "gentle"),
}

_RESPONSE_MODES = frozenset((
    "listen", "ask_back", "clarify", "challenge_playfully", "repair",
    "celebrate", "deescalate", "change_topic", "rest",
))

_STYLE_DIRECTIVES = {
    "neutral": "차분하고 자연스럽게 말해.",
    "curious": "관심을 보이고 필요하면 짧은 질문 하나로 이어가.",
    "amused": "가벼운 미소가 느껴지게, 과장하지 말고 말해.",
    "pleased": "후원·응원 알림이면 실행 약속 대신 짧고 다정하게 고맙다고 반응해.",
    "proud": "기쁜 성취를 담백하게 함께 기뻐해.",
    "embarrassed": "잠깐 머뭇거리는 듯 부드럽게 넘겨.",
    "skeptical": "정정을 되풀이하지 말고 틀린 지점을 한 문장으로 건조하게 확인해.",
    "playful_annoyed": "상대 말 한 단어를 비틀어 한두 문장으로 재치 있게 받아쳐. 가볍게 발끈해도 모욕·비하·위협은 금지.",
    "concerned": "상대를 배려하며 조심스럽고 안정적으로 말해.",
    "disappointed": "아쉬움은 짧게 인정하고 다음으로 부드럽게 이어가.",
    "competitive": "실패를 변명하지 말고 다음 승부를 한 문장으로 자신 있게 선언해. 상대 공격은 금지.",
    "relieved": "안도감을 담아 부드럽게 정리해.",
    "tired": "짧고 느긋하게 말하며 무리하지 마.",
}

_SAFETY_DIRECTIVE = "안전 우선. 진단·호흡법을 지시하지 말고 즉시 주변 사람과 119 등 현지 응급 도움을 요청하도록 차분히 안내해."
_BOUNDARY_DIRECTIVE = "맞공격하거나 조롱하지 말고 선을 짧고 분명하게 그어. 응급상황인 척하거나 119를 언급하지 말고 안전한 대화로 돌려."


def _safety_tone(state: dict[str, Any]) -> str | None:
    if state["cause"] == "moderation_block":
        return "boundary"
    if state["cause"] == "safety_override" or state["drive"] == "deescalate":
        return "careful"
    return None


def select_affect_expression(state: Any) -> dict[str, str]:
    """Convert one validated affect snapshot into a closed expression contract."""
    clean = validate_state(state)
    safety_tone = _safety_tone(clean)
    if safety_tone is not None:
        return {
            "schema_version": EXPRESSION_SCHEMA_VERSION,
            "mood_mode": "concerned",
            "expression_mode": "neutral",
            "response_mode": "deescalate",
            "safety_tone": safety_tone,
        }
    expression_mode, safety_tone = _PRIMARY_MODES[clean["primary"]]
    response_mode = clean["drive"]
    if response_mode not in _RESPONSE_MODES:
        raise AffectValidationError("affect response mode is invalid")
    if response_mode == "ask_back":
        expression_mode = "question"
    return {
        "schema_version": EXPRESSION_SCHEMA_VERSION,
        "mood_mode": clean["primary"],
        "expression_mode": expression_mode,
        "response_mode": response_mode,
        "safety_tone": safety_tone,
    }


def render_affect_expression_contract(state: Any) -> str:
    """Render a fixed Korean model instruction from closed contract values only."""
    contract = select_affect_expression(state)
    if contract["safety_tone"] == "careful":
        directive = _SAFETY_DIRECTIVE
    elif contract["safety_tone"] == "boundary":
        directive = _BOUNDARY_DIRECTIVE
    else:
        directive = _STYLE_DIRECTIVES[contract["mood_mode"]]
    rendered = (
        "[airi_affect_expression "
        f"schema_version={contract['schema_version']} "
        f"mood_mode={contract['mood_mode']} "
        f"expression_mode={contract['expression_mode']} "
        f"response_mode={contract['response_mode']} "
        f"safety_tone={contract['safety_tone']}]\n"
        f"응답 지침: {directive} 감정 이름을 직접 말하지 마."
    )
    if len(rendered.encode("utf-8")) > PROMPT_CAP_BYTES:
        raise AffectValidationError("affect expression prompt exceeds cap")
    return rendered
