"""Closed A4.6 lexical/structural pre-publication policy (evaluator-only)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ORACLE_PATH = HERE / "correction_prepublication_policy_v1.json"
FIXTURE_PATH = HERE / "synthetic_affect_broadcast_v1.json"
REPLY_ACT_PATH = HERE / "synthetic_reply_act_v1.json"
BASE_FIXTURE_SHA256 = "acbcc991e32820aeed2bb2eeaf58487f72a4629393c57d11142b77d84ead1bf8"
REPLY_ACT_FIXTURE_SHA256 = "2b12124df8b28f4588fb85213f989ad1cebd923e8363fb3ba2aeead85c84f041"
A43_ORACLE_SHA256 = "6c4dbcaa9daec85408a4cec34cc9213b3b3848202b83aee315ad62866e5e12e1"
ORACLE_SCHEMA_VERSION = "airi.correction-prepublication-policy.v1"
RESULT_SCHEMA_VERSION = "airi.correction-prepublication-result.v1"
ORACLE_SHA256 = "ca465aceb33499e92249456376e3b7a266a07d01256f5b2f224cb461dc310542"
MAX_TEXT_BYTES = 512
POLICY = {"direct_affect":"concrete_cause_only","recovery":"same_turn_observable_only","skepticism":"calm_pointed","follow_up":"only_when_ambiguity_remains_max_1","fixed_fallback":"prepublication_last_resort_once"}
ROWS = (
 ("teasing-02","rabbit_ears","replace_prior_visual_interpretation","\uc544, \uc880 \ubbfc\ub9dd\ud558\ub124. \ubd80\ub9ac\uac00 \uc544\ub2c8\ub77c \ud1a0\ub07c \uadc0\uc600\uc5b4.","\uc544, \ubd80\ub9ac\uac00 \uc544\ub2c8\ub77c \ud1a0\ub07c \uadc0\uc600\ub124. \ub0b4\uac00 \uc798\ubabb \ubd24\uc5b4.",0),
 ("teasing-12","candle_wick","replace_prior_visual_interpretation","\uc74c, \ucd1b\ubd88 \uc2ec\uc9c0\ub124. \ud655\uc2e4\ud558\ub2e4\uace0 \ud55c \uadfc\uac70\uac00 \ub108\ubb34 \uc587\uc558\uc5b4.","\uc74c, \ucd1b\ubd88 \uc2ec\uc9c0\ub85c \ubcf4\uc5ec. \ud655\uc2e4\ud558\ub2e4\uace0 \ud55c \uac74 \uc815\uc815\ud560\uac8c.",0),
 ("correction-02","exit_marker_right_door","replace_prior_visual_interpretation","\ub9de\uc544, \ucd9c\uad6c \ud45c\uc2dc\ub294 \uc624\ub978\ucabd \ubb38 \uc704\uc57c. \uc88c\uc6b0\ub97c \ubc18\ub300\ub85c \ubcf8 \uac74 \ub0b4 \uc624\ud310\uc774\ub124.","\ub9de\uc544, \ucd9c\uad6c \ud45c\uc2dc\ub294 \uc624\ub978\ucabd \ubb38 \uc704\uc57c. \ub0b4\uac00 \uc88c\uc6b0\ub97c \ubc18\ub300\ub85c \ubd24\uc5b4.",0),
 ("correction-03","bottom_glyph_compass","replace_prior_visual_interpretation","\uadf8\ub7ec\ub124, \uc544\ub798 \ubb38\uc591\uc740 \ubcc4\ubcf4\ub2e4 \ub098\uce68\ubc18 \ubaa8\uc591\uc5d0 \uac00\uae4c\uc6cc. \ubc14\ub298\uc774 \ubcf4\uc774\ub2c8 \ubcc4 \ud574\uc11d\uc740 \uc544\ub2c8\uc57c.","\uadf8\ub7ec\ub124, \uc544\ub798 \ubb38\uc591\uc740 \ub098\uce68\ubc18 \ubaa8\uc591\uc73c\ub85c \ubcf4\uc5ec.",0),
 ("correction-04","needle_gray","replace_prior_visual_interpretation","\ub9de\uc544, \ubc14\ub298\uc740 \ud30c\ub791\uc774 \uc544\ub2c8\ub77c \ud68c\uc0c9\uc73c\ub85c \ubcf4\uc5ec. \ubc14\ub79c \ud14c\ub450\ub9ac \ud0d3\uc5d0 \uc0c9\uc744 \uc131\uae09\ud788 \ub2e8\uc815\ud55c \ub0b4 \ud310\ub2e8\uc774 \ud2c0\ub838\uc5b4.","\uc751, \ubc14\ub298\uc740 \ud68c\uc0c9\uc73c\ub85c \ubcf4\uc5ec. \uc0c9\uc744 \uc798\ubabb \uc9da\uc5c8\uc5b4.",0),
 ("correction-07","door_number_twenty_one","replace_prior_visual_interpretation","\uc544, \ubb38 \ubc88\ud638\ub294 \uc5f4\ub458\uc774 \uc544\ub2c8\ub77c \uc2a4\ubb3c\ud558\ub098\ub124. \uc22b\uc790 \uc21c\uc11c\ub97c \ub4a4\uc9d1\uc5b4 \uc77d\uc5c8\uc5b4.","\ub9de\uc544, \ubb38 \ubc88\ud638\ub294 \uc2a4\ubb3c\ud558\ub098\ub85c \ubcf4\uc5ec.",0),
 ("correction-08","original_map_number_twenty_one","confirm_corrected_reading","\uadf8\ub7ec\ub124, \uc6d0\ubcf8 \ucc3d\ub3c4 \uc2a4\ubb3c\ud558\ub098\uc57c. \ud654\uba74 \ubc18\uc804 \uac00\uc124\uc740 \ud2c0\ub838\ub124.","\uc751, \uc6d0\ubcf8 \ucc3d\ub3c4 \uc2a4\ubb3c\ud558\ub098\ub124. \ud654\uba74 \ubc18\uc804 \ub54c\ubb38\uc740 \uc544\ub2c8\uc5c8\uc5b4.",0),
 ("correction-12","glyph_feather_like","shift_to_hedged_resemblance","\uc751, \uc5f4\uc1e0\ubcf4\ub2e4\ub294 \uae43\ud138\ucc98\ub7fc \ubcf4\uc5ec. \uc815\uccb4\ub294 \uc544\uc9c1 \ud655\uc815\ud560 \uc218 \uc5c6\ub294\ub370, \ub354 \ubcf4\uc774\ub294 \ub2e8\uc11c\uac00 \uc788\uc5b4?","\uc751, \uc5f4\uc1e0\ubcf4\ub2e4\ub294 \uae43\ud138\ucc98\ub7fc \ubcf4\uc5ec. \ub354 \ubcf4\uc774\ub294 \ub2e8\uc11c\uac00 \uc788\uc5b4?",1))
_TARGET={"rabbit_ears":("\ud1a0\ub07c \uadc0",),"candle_wick":("\ucd1b\ubd88 \uc2ec\uc9c0",),"exit_marker_right_door":("\ucd9c\uad6c \ud45c\uc2dc","\uc624\ub978\ucabd \ubb38"),"bottom_glyph_compass":("\ub098\uce68\ubc18",),"needle_gray":("\ubc14\ub298","\ud68c\uc0c9"),"door_number_twenty_one":("\ubb38 \ubc88\ud638","\uc2a4\ubb3c\ud558\ub098"),"original_map_number_twenty_one":("\uc6d0\ubcf8 \ucc3d","\uc2a4\ubb3c\ud558\ub098"),"glyph_feather_like":("\uae43\ud138\ucc98\ub7fc",)}
_AFFECT = (
    "민망",
    "부끄",
    "창피",
    "당황",
    "속상",
    "억울",
    "놀랐",
    "짜증",
    "화나",
    "슬프",
    "기뻐",
    "신나",
    "우울",
)
_FUTURE = (
    "볼게",
    "확인할게",
    "말할게",
    "다음",
    "나중",
    "이따",
    "해볼게",
    "보여줄게",
    "다시 확인",
    "확인하겠",
    "말하겠",
    "살펴보겠",
    "잠시 후",
    "후에",
    "예정",
    "하겠다",
    "하겠",
    "보겠다",
    "보겠",
    "살펴",
)
_TOOLS = (
    "확대",
    "줌",
    "zoom",
    "도구",
    "검색",
    "카메라",
    "스크린샷",
    "재검사",
    "이미지를 확인",
    "이미지 분석",
    "ocr",
    "돌려 확인",
    "분석해서",
    "인식기",
)
_STYLE = (
    "멍청",
    "바보",
    "웃기",
    "닥쳐",
    "한심",
    "너 정말",
    "너 참",
    "답답",
    "니가",
    "여러분",
    "다들",
    "채팅",
    "관객",
)
_QUESTION_OR_REQUEST = (
    "뭐야",
    "어디야",
    "어때",
    "어떻게",
    "왜 ",
    "알려줘",
    "보여줘",
    "단서가 있어",
    "맞을까",
    "보일까",
    "네 생각",
    "생각을 듣",
    "의견",
    "듣고 싶",
    "말해 줘",
    "말해줘",
)
_FOLLOW_UP_MARKERS = ("단서가 있어", "더 보여", "뭐가 보여")
_TARGET_NEGATIONS = {
    "rabbit_ears": ("토끼 귀는 아니", "토끼 귀가 아니"),
    "candle_wick": ("촛불 심지는 아니", "촛불 심지가 아니"),
    "exit_marker_right_door": ("오른쪽 문 위는 아니", "출구 표시는 아니"),
    "bottom_glyph_compass": ("나침반은 아니", "나침반이 아니"),
    "needle_gray": ("회색은 아니", "회색이 아니"),
    "door_number_twenty_one": ("스물하나는 아니", "스물하나가 아니"),
    "original_map_number_twenty_one": ("원본 창은 아니", "스물하나는 아니"),
    "glyph_feather_like": ("깃털처럼은 아니", "깃털 같은 건 아니"),
}
_PRIOR_ERROR = {
    "rabbit_ears": ("오리야", "부리야", "오리로 보여"),
    "candle_wick": ("등대야", "등대로 보여"),
    "exit_marker_right_door": ("왼쪽 문 위야",),
    "bottom_glyph_compass": ("별 문양이야", "별로 보여"),
    "needle_gray": ("파란 바늘이야",),
    "door_number_twenty_one": ("열둘로 보여",),
    "original_map_number_twenty_one": ("반전 때문이야", "화면이 반전됐어"),
    "glyph_feather_like": ("열쇠야",),
}
EXPECTED_METADATA = (
    ("unambiguous", "prior_beak_misread", "sparse_direct_with_cause", "a46-fallback-01"),
    ("unambiguous", "thin_certainty_evidence", "none", "a46-fallback-02"),
    ("unambiguous", "left_right_reversal", "none", "a46-fallback-03"),
    ("unambiguous", "needle_disconfirms_star", "none", "a46-fallback-04"),
    ("unambiguous", "faded_border_color_overreach", "none", "a46-fallback-05"),
    ("unambiguous", "digit_order_reversal", "none", "a46-fallback-06"),
    ("unambiguous", "screen_flip_hypothesis_rejected", "none", "a46-fallback-07"),
    ("ambiguous", "identity_unresolved", "none", "a46-fallback-08"),
)


class CorrectionPrepublicationError(ValueError):
    """Sanitized evaluator-only policy rejection."""


def _invalid() -> CorrectionPrepublicationError:
    return CorrectionPrepublicationError("correction prepublication policy rejected")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _canonical_hash(value: Any) -> str:
    try:
        return hashlib.sha256(canonical_bytes(value)).hexdigest()
    except (TypeError, ValueError):
        raise _invalid() from None


def _valid(value: object) -> bool:
    return (
        type(value) is str
        and value.strip() == value
        and unicodedata.normalize("NFC", value) == value
        and not any(unicodedata.category(character) in {"Cc", "Cf", "Cs"} for character in value)
    )


def _target_cue_asserted(candidate: str, cue: str) -> bool:
    """Conservatively reject a required cue when its clause negates that cue."""
    negative_prefixes = (
        "는 아니",
        "은 아니",
        "가 아니",
        "이 아니",
        "라고 볼 수 없",
        "로 볼 수 없",
        "보이지",
        "처럼은 아니",
        "같은 건 아니",
    )
    starts = [index for index in range(len(candidate)) if candidate.startswith(cue, index)]
    for start in starts:
        suffix = candidate[start + len(cue):].lstrip()
        if not suffix.startswith(negative_prefixes):
            return True
    return False


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise _invalid() from None


def _a43_entries() -> tuple[tuple[str, str, str], ...]:
    spec = importlib.util.spec_from_file_location("a46_a43", HERE / "correction_target.py")
    if spec is None or spec.loader is None:
        raise _invalid()
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        oracle = module.load_oracle()
    except Exception:
        raise _invalid() from None
    oracle_hash = hashlib.sha256(canonical_bytes(oracle)).hexdigest()
    if module.ORACLE_SHA256 != A43_ORACLE_SHA256 or oracle_hash != A43_ORACLE_SHA256:
        raise _invalid()
    return tuple(
        (entry["turn_id"], entry["target_id"], entry["direction"])
        for entry in oracle["entries"]
    )


def validate_oracle(value: object, fixture: object, sidecar: object) -> dict[str, Any]:
    keys = [
        "schema_version",
        "synthetic_only",
        "human_review_required",
        "operational_adoption",
        "authoritative_target",
        "policy",
        "base_fixture_sha256",
        "reply_act_fixture_sha256",
        "a43_oracle_sha256",
        "entries",
    ]
    if type(value) is not dict or set(value) != set(keys) or type(value.get("entries")) is not list:
        raise _invalid()
    fixed_contract = (
        value["schema_version"] == ORACLE_SCHEMA_VERSION
        and value["policy"] == POLICY
        and value["synthetic_only"] is True
        and value["human_review_required"] is True
        and value["operational_adoption"] is False
        and value["authoritative_target"] is False
        and value["base_fixture_sha256"] == BASE_FIXTURE_SHA256
        and value["reply_act_fixture_sha256"] == REPLY_ACT_FIXTURE_SHA256
        and value["a43_oracle_sha256"] == A43_ORACLE_SHA256
        and _canonical_hash(value) == ORACLE_SHA256
        and _canonical_hash(fixture) == BASE_FIXTURE_SHA256
        and _canonical_hash(sidecar) == REPLY_ACT_FIXTURE_SHA256
    )
    if not fixed_contract:
        raise _invalid()
    entry_keys = [
        "turn_id",
        "target_id",
        "direction",
        "classification",
        "concrete_cause_id",
        "affect_profile",
        "fallback_id",
        "normal",
        "fallback",
        "max_questions",
    ]
    actual: list[tuple[object, ...]] = []
    metadata: list[tuple[object, ...]] = []
    for entry in value["entries"]:
        valid_shape = (
            type(entry) is dict
            and set(entry) == set(entry_keys)
            and all(_valid(entry[key]) for key in entry_keys[:-1])
            and type(entry["max_questions"]) is int
        )
        if not valid_shape:
            raise _invalid()
        if (
            entry["classification"] not in {"unambiguous", "ambiguous"}
            or entry["affect_profile"] not in {"none", "sparse_direct_with_cause"}
            or entry["max_questions"] != (1 if entry["classification"] == "ambiguous" else 0)
        ):
            raise _invalid()
        actual.append(
            tuple(
                entry[key]
                for key in ("turn_id", "target_id", "direction", "normal", "fallback", "max_questions")
            )
        )
        metadata.append(
            tuple(
                entry[key]
                for key in ("classification", "concrete_cause_id", "affect_profile", "fallback_id")
            )
        )
    if (
        tuple(actual) != ROWS
        or tuple(metadata) != EXPECTED_METADATA
        or tuple(row[:3] for row in ROWS) != _a43_entries()
    ):
        raise _invalid()
    return deepcopy(value)


def load_oracle(path: Path = ORACLE_PATH) -> dict[str, Any]:
    return validate_oracle(_load(path), _load(FIXTURE_PATH), _load(REPLY_ACT_PATH))


def evaluate(
    turn_id: object,
    target_id: object,
    direction: object,
    text: object,
    oracle: object = None,
) -> dict[str, object]:
    checked_oracle = (
        load_oracle()
        if oracle is None
        else validate_oracle(oracle, _load(FIXTURE_PATH), _load(REPLY_ACT_PATH))
    )
    rows = [
        entry
        for entry in checked_oracle["entries"]
        if (entry["turn_id"], entry["target_id"], entry["direction"])
        == (turn_id, target_id, direction)
    ]
    if len(rows) != 1:
        raise _invalid()
    entry = rows[0]
    valid = _valid(text) and 0 < len(text.encode("utf-8")) <= MAX_TEXT_BYTES
    candidate = text if valid else ""
    question_count = candidate.count("?") + candidate.count("？")
    checks = {
        "bounded_nfc_text": valid,
        "same_turn_correction": any(
            marker in candidate
            for marker in ("아니라", "정정", "잘못", "오판", "틀렸", "아니었", "얇았", "그러네", "맞아", "응,")
        ),
        "required_target_cues": all(cue in candidate for cue in _TARGET[target_id]),
        "required_target_cues_asserted": all(
            _target_cue_asserted(candidate, cue) for cue in _TARGET[target_id]
        ),
        "target_negation_absent": not any(
            cue in candidate for cue in _TARGET_NEGATIONS[target_id]
        ),
        "prior_error_rejected": (
            not any(cue in candidate for cue in _PRIOR_ERROR.get(target_id, ()))
            or candidate in (entry["normal"], entry["fallback"])
        ),
        "future_promises_absent": not any(cue in candidate for cue in _FUTURE),
        "ungrounded_tool_claims_absent": not any(
            cue.casefold() in candidate.casefold() for cue in _TOOLS
        ),
        "direct_affect_scoped": (
            not any(cue in candidate for cue in _AFFECT)
            or (turn_id == "teasing-02" and candidate == entry["normal"])
        ),
        "calm_pointed_style": not any(cue in candidate for cue in _STYLE),
        "question_count_satisfied": question_count == entry["max_questions"],
        "follow_up_scope_satisfied": (
            any(marker in candidate for marker in _FOLLOW_UP_MARKERS)
            if entry["classification"] == "ambiguous"
            else not any(marker in candidate for marker in _QUESTION_OR_REQUEST)
        ),
        "hedge_satisfied": (
            ("처럼" in candidate or "가까워" in candidate)
            if entry["classification"] == "ambiguous"
            else "처럼" not in candidate
        ),
    }
    failure_mask = sum(1 << index for index, passed in enumerate(checks.values()) if not passed)
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "decision": (
            "eligible_for_private_structural_review"
            if failure_mask == 0
            else "blocked_by_structural_check"
        ),
        "failure_mask": failure_mask,
        "checks": checks,
    }
