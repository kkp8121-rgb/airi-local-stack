"""Closed correction targets for the synthetic AIRI broadcast fixtures.

This module is intentionally pure.  It accepts only the fixture assertions
listed below and renders only fixed Korean instructions; caller supplied text
never reaches the rendered prompt.
"""
from __future__ import annotations

import json
import unicodedata


CORRECTION_TARGET_MESSAGE_NAME = "airi_synthetic_correction_target"
CORRECTION_TARGET_SCHEMA_VERSION = "airi.correction-target.v1"
CORRECTION_TARGET_ACT = "correct"
CORRECTION_TARGET_EVIDENCE_BASIS = "pinned_synthetic_fixture_assertion"
CORRECTION_TARGET_MAX_BYTES = 512
CORRECTION_TARGET_RENDER_MAX_BYTES = 768

_TARGET_STATEMENTS = {
    "rabbit_ears": "앞선 시각 해석은 토끼 귀라는 읽음으로 바로잡는다.",
    "candle_wick": "앞선 시각 해석은 촛불 심지라는 읽음으로 바로잡는다.",
    "exit_marker_right_door": "앞선 시각 해석은 오른쪽 문 출구 표식이라는 읽음으로 바로잡는다.",
    "bottom_glyph_compass": "앞선 시각 해석은 아래 문양이 나침반이라는 읽음으로 바로잡는다.",
    "needle_gray": "앞선 시각 해석은 바늘이 회색이라는 읽음으로 바로잡는다.",
    "door_number_twenty_one": "앞선 시각 해석은 문 번호가 21이라는 읽음으로 바로잡는다.",
    "original_map_number_twenty_one": "수정된 읽음인 원래 지도 번호 21을 확인한다.",
    "glyph_feather_like": "문양은 깃털을 닮았다는 조심스러운 유사 표현으로 옮긴다.",
}

_DIRECTION_INSTRUCTIONS = {
    "replace_prior_visual_interpretation": "직전의 다른 시각 해석은 반복하지 말고 이 수정만 반영한다.",
    "confirm_corrected_reading": "수정된 읽음을 확인하되 새 사실을 덧붙이지 않는다.",
    "shift_to_hedged_resemblance": "단정하지 말고 닮았다는 표현으로만 말한다.",
}

_ALLOWED_PAIRS = frozenset({
    ("rabbit_ears", "replace_prior_visual_interpretation"),
    ("candle_wick", "replace_prior_visual_interpretation"),
    ("exit_marker_right_door", "replace_prior_visual_interpretation"),
    ("bottom_glyph_compass", "replace_prior_visual_interpretation"),
    ("needle_gray", "replace_prior_visual_interpretation"),
    ("door_number_twenty_one", "replace_prior_visual_interpretation"),
    ("original_map_number_twenty_one", "confirm_corrected_reading"),
    ("glyph_feather_like", "shift_to_hedged_resemblance"),
})


class CorrectionTargetValidationError(ValueError):
    """A deliberately non-reflective correction-target validation failure."""


def _invalid() -> CorrectionTargetValidationError:
    return CorrectionTargetValidationError("invalid correction-target candidate")


def validate_correction_target_candidate(candidate: object) -> dict[str, str]:
    """Validate and copy the exact closed correction-target shape."""
    if type(candidate) is not dict:
        raise _invalid()
    expected = {"schema_version", "act", "target_id", "direction", "evidence_basis"}
    if set(candidate) != expected:
        raise _invalid()
    values = {key: candidate[key] for key in expected}
    if any(type(value) is not str for value in values.values()):
        raise _invalid()
    if (
        values["schema_version"] != CORRECTION_TARGET_SCHEMA_VERSION
        or values["act"] != CORRECTION_TARGET_ACT
        or values["evidence_basis"] != CORRECTION_TARGET_EVIDENCE_BASIS
        or (values["target_id"], values["direction"]) not in _ALLOWED_PAIRS
    ):
        raise _invalid()
    return {
        "schema_version": values["schema_version"],
        "act": values["act"],
        "target_id": values["target_id"],
        "direction": values["direction"],
        "evidence_basis": values["evidence_basis"],
    }


def serialize_correction_target_candidate(candidate: object) -> str:
    """Return the sole canonical JSON spelling of a valid candidate."""
    return json.dumps(
        validate_correction_target_candidate(candidate), ensure_ascii=False,
        sort_keys=True, separators=(",", ":"),
    )


def _unsafe_text(value: str) -> bool:
    return (
        unicodedata.normalize("NFC", value) != value
        or any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in value)
    )


def parse_correction_target_candidate(candidate: object) -> dict[str, str]:
    """Parse only exact NFC canonical JSON produced by the serializer."""
    if (
        type(candidate) is not str
        or len(candidate.encode("utf-8")) > CORRECTION_TARGET_MAX_BYTES
        or _unsafe_text(candidate)
    ):
        raise _invalid()
    try:
        decoded = json.loads(candidate)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise _invalid() from None
    validated = validate_correction_target_candidate(decoded)
    if serialize_correction_target_candidate(validated) != candidate:
        raise _invalid()
    return validated


def render_correction_target_contract(candidate: object) -> str:
    """Render a bounded fixed Korean correction instruction."""
    validated = validate_correction_target_candidate(candidate)
    rendered = (
        "아래 수정은 고정된 합성 평가 fixture 증거에만 근거한다. "
        "이 밖의 증거를 만들거나 추측하지 않는다. "
        + _TARGET_STATEMENTS[validated["target_id"]] + " "
        + _DIRECTION_INSTRUCTIONS[validated["direction"]]
    )
    if len(rendered.encode("utf-8")) > CORRECTION_TARGET_RENDER_MAX_BYTES:
        raise RuntimeError("correction-target contract exceeds fixed byte cap")
    return rendered
