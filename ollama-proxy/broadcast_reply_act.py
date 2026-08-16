"""Closed-schema reply-act selection for synthetic AIRI broadcast evaluation.

This module is deliberately pure: it does not inspect a conversation, call a
model, or retain state.  The only renderable material is a fixed contract.
"""
from __future__ import annotations

import json
import unicodedata


REPLY_ACT_MESSAGE_NAME = "airi_synthetic_reply_contract"
REPLY_ACT_SCHEMA_VERSION = "airi.broadcast-reply-act.v1"
REPLY_ACT_EVIDENCE_SCOPE = "prior_airi_and_latest_viewer"
REPLY_ACT_RENDER_MAX_BYTES = 640

REPLY_ACTS = frozenset(
    {
        "respond_grounded",
        "correct",
        "repair",
        "thank",
        "callback",
        "deescalate",
        "challenge_playfully",
        "celebrate",
        "transition",
        "close",
    }
)


class ReplyActValidationError(ValueError):
    """A deliberately non-reflective validation failure."""


def _invalid() -> ReplyActValidationError:
    # Do not include caller data: these errors can be logged by an evaluator.
    return ReplyActValidationError("invalid reply-act candidate")


def validate_reply_act(candidate: object) -> dict[str, str]:
    """Validate and copy the exact reply-act object shape.

    ``dict`` is intentional here: accepting arbitrary Mapping subclasses could
    invoke caller-defined behavior and would not be an exact closed schema.
    """
    if type(candidate) is not dict:
        raise _invalid()
    expected = {"schema_version", "act", "evidence_scope"}
    if set(candidate) != expected:
        raise _invalid()
    schema_version = candidate["schema_version"]
    act = candidate["act"]
    evidence_scope = candidate["evidence_scope"]
    if (
        type(schema_version) is not str
        or type(act) is not str
        or type(evidence_scope) is not str
        or schema_version != REPLY_ACT_SCHEMA_VERSION
        or evidence_scope != REPLY_ACT_EVIDENCE_SCOPE
        or act not in REPLY_ACTS
    ):
        raise _invalid()
    return {
        "schema_version": schema_version,
        "act": act,
        "evidence_scope": evidence_scope,
    }


def serialize_reply_act_candidate(candidate: object) -> str:
    """Return the sole canonical JSON spelling of a valid candidate."""
    validated = validate_reply_act(candidate)
    return json.dumps(
        validated, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _contains_disallowed_json_text(value: str) -> bool:
    if unicodedata.normalize("NFC", value) != value:
        return True
    return any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in value)


def parse_reply_act_candidate(candidate: object) -> dict[str, str]:
    """Parse only the exact NFC canonical JSON created by the serializer."""
    if type(candidate) is not str or _contains_disallowed_json_text(candidate):
        raise _invalid()
    try:
        decoded = json.loads(candidate)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise _invalid() from None
    validated = validate_reply_act(decoded)
    if serialize_reply_act_candidate(validated) != candidate:
        raise _invalid()
    return validated


_ACT_INSTRUCTIONS = {
    "respond_grounded": (
        "질문이면 AIRI 자신이 직접 답하고, 관찰·제안이면 그 방향 그대로 받아 이어가. "
        "질문을 되돌리거나 시청자가 하지 않은 말을 만들지 마."
    ),
    "correct": "최신 시청자의 정정을 우선해 직전 AIRI 오류를 짧게 인정하고 방향·대상을 그대로 바로잡아.",
    "repair": "직전 AIRI의 문제를 인정하고 변명이나 역할 전도 없이 차분히 수습해.",
    "thank": "후원 사실에 짧게 고마움을 말하되 이름·금액을 추측하거나 후원을 압박하지 마.",
    "callback": "대화에 이미 나온 구체 맥락 하나만 정확히 회수해 현재 말과 연결해.",
    "deescalate": "기존 안전 안내를 끊지 말고 새 진단 없이 다음 안전 행동을 분명히 이어가.",
    "challenge_playfully": "사실은 뒤집지 말고 가볍게 받아치되 공격하거나 억지로 확정하지 마.",
    "celebrate": "실제로 확인된 성공만 짧게 기뻐하고 앞선 도움을 정확히 인정해.",
    "transition": "현재 결론을 짧게 묶고 시청자가 말한 다음 화제로 자연스럽게 넘어가.",
    "close": "종료 의사를 확인하고 새 일을 약속하지 말고 짧은 마무리로 끝내.",
}


def render_reply_act_contract(reply_act: object) -> str:
    """Render a bounded, fixed Korean prompt for a validated reply act."""
    act = validate_reply_act(reply_act)["act"]
    rendered = (
        "직전 AIRI 발화와 최신 시청자 말만 근거로 반말로 답해. "
        "역할이나 말한 방향을 뒤집지 말고, 새 사실·이름·수치·추측은 넣지 마. "
        + _ACT_INSTRUCTIONS[act]
    )
    if len(rendered.encode("utf-8")) > REPLY_ACT_RENDER_MAX_BYTES:
        raise RuntimeError("reply-act contract exceeds fixed byte cap")
    return rendered
