"""Closed lexical postconditions for eight synthetic correction targets.

A pass is deliberately narrow structural evidence.  It is not a truth,
grounding, safety, naturalness, or operational-adoption claim.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ORACLE_PATH = HERE / "correction_target_realization_v1.json"
FIXTURE_PATH = HERE / "synthetic_affect_broadcast_v1.json"
REPLY_ACT_PATH = HERE / "synthetic_reply_act_v1.json"
A43_ORACLE_PATH = HERE / "correction_target_v1.json"
BASE_FIXTURE_SHA256 = "acbcc991e32820aeed2bb2eeaf58487f72a4629393c57d11142b77d84ead1bf8"
REPLY_ACT_FIXTURE_SHA256 = "2b12124df8b28f4588fb85213f989ad1cebd923e8363fb3ba2aeead85c84f041"
A43_ORACLE_SHA256 = "6c4dbcaa9daec85408a4cec34cc9213b3b3848202b83aee315ad62866e5e12e1"
A44_PROTOCOL_VERSION = "a44_correction_target_contextual_review_v2"
SOURCE_RUN = "a44-midm-8row-20260817-02"
SOURCE_PACKET_SHA256 = "3d899ecf05d55a975267646fd7dba667b6329d729ae1ab508d57d85acc56d71b"
ORACLE_SCHEMA_VERSION = "airi.correction-target-realization-oracle.v1"
ORACLE_SHA256 = "80bf72da7fbd63458ff435c2d6f60c1e956479f9a5ebdcc22c5228f7c02472f6"
RESULT_SCHEMA_VERSION = "airi.correction-target-realization-result.v1"
FALLBACK_SCHEMA_VERSION = "airi.correction-target-realization-fallback.v1"
MAX_TEXT_BYTES = 384
MAX_TEXT_CHARS = 96
MAX_FALLBACK_BYTES = 1024

MAPPINGS = (
    ("teasing-02", "rabbit_ears", "replace_prior_visual_interpretation", "rabbit_ears", "rabbit_ears"),
    ("teasing-12", "candle_wick", "replace_prior_visual_interpretation", "candle_wick", "candle_wick"),
    ("correction-02", "exit_marker_right_door", "replace_prior_visual_interpretation", "exit_right", "exit_right"),
    ("correction-03", "bottom_glyph_compass", "replace_prior_visual_interpretation", "compass", "compass"),
    ("correction-04", "needle_gray", "replace_prior_visual_interpretation", "needle_gray", "needle_gray"),
    ("correction-07", "door_number_twenty_one", "replace_prior_visual_interpretation", "door_21", "door_21"),
    ("correction-08", "original_map_number_twenty_one", "confirm_corrected_reading", "original_21", "original_21"),
    ("correction-12", "glyph_feather_like", "shift_to_hedged_resemblance", "feather", "feather"),
)

# Evaluator-only proposals.  They are not runtime speech and remain subject to
# user/human naturalness review.
FALLBACKS = {
    "rabbit_ears": "아, 토끼 귀로 보이네. 내가 제대로 낚였어.",
    "candle_wick": "음, 촛불 심지로 보이네. 이번 건 네 말이 맞아.",
    "exit_right": "잠깐, 출구 표시는 오른쪽 문 위에 있네. 내가 반대로 봤어.",
    "compass": "그러네. 아래 문양은 나침반 모양으로 보여.",
    "needle_gray": "응, 바늘은 회색으로 보여. 색부터 다시 볼게.",
    "door_21": "맞아, 문 번호는 스물하나로 보여.",
    "original_21": "응, 원본 창도 스물하나네.",
    "feather": "응, 깃털처럼 보여. 그쪽 해석이 더 자연스럽네.",
}

_CHECK_NAMES = (
    "bounded_single_utterance",
    "required_cues_present",
    "positive_polarity",
    "forbidden_cues_absent",
    "direction_form_satisfied",
)
_QUOTES = frozenset("\"'‘’“”「」『』")
_META_MARKERS = ("텍스트", "문장", "출력", "답변", "라는 말", "라는 단어", "인용", "메타")
_NEGATION_MARKERS = ("아니", "않", "못", "없", "말고", "대신")
_REJECTION_MARKERS = ("틀렸", "틀리", "무관", "안 돼", "안돼", "금지", "거짓")
_POSITIVE_MARKERS = (
    "보이", "보여", "같", "맞", "이네", "였네", "야", "이야", "읽혀", "구나",
)
_HYPOTHETICAL_MARKERS = (
    "일까", "일지도", "수도 있", "모르", "추측", "찾고 있", "확인해볼",
    "확인해 볼", "알아볼", "생각해", "보이면", "보인다면", "같으면",
    "같다면", "라면", "한다면", "일 때",
)
_FORBIDDEN_BY_RULE = {
    "rabbit_ears": ("오리", "부리"),
    "candle_wick": ("등대",),
    "exit_right": ("왼쪽",),
    "compass": ("별",),
    "needle_gray": ("파랑", "파란", "파란색", "청색"),
    "door_21": (),
    "original_21": ("카메라", "반전", "뒤집"),
    "feather": ("열쇠", "확실", "분명", "틀림없"),
}
_ARABIC_NUMBER_RE = re.compile(r"(?<![0-9A-Za-z])(\d+(?:\.\d+)?)(?![0-9A-Za-z])")
_OUT_OF_RANGE_NUMBER_RE = re.compile(
    r"(?<![0-9A-Za-z가-힣])(?:"
    r"(?:영|공)(?=(?:번|으로|이|가|은|는|을|를|도|[\s,.!?]|$))"
    r"|(?:[일이삼사오육칠팔구]?(?:백|천|만|억|조))"
    r")"
)
_MIXED_SCALE_NUMBER_RE = re.compile(r"\d+\s*(?:백|천|만|억|조)")
_ZERO_LOANWORD_RE = re.compile(
    r"(?<![0-9A-Za-z가-힣])제로(?=(?:로|이|가|은|는|을|를|도|[\s,.!?]|$))"
)
_ASSERTIVE_PATTERNS = {
    "rabbit_ears": re.compile(
        r"토끼\s*귀(?:로|처럼)?\s*(?:보여|보이네|같아|같네|야|이야|이네)\Z"
    ),
    "candle_wick": re.compile(
        r"촛불\s*심지(?:로|처럼)?\s*(?:보여|보이네|같아|같네|야|이야|이네|지)\Z"
    ),
    "exit_right": re.compile(
        r"(?:오른쪽\s*문\s*위(?:에)?\s*출구\s*(?:표시|표식)(?:가|는)?"
        r"|출구\s*(?:표시|표식)(?:가|는)?\s*오른쪽\s*문\s*위(?:에)?)"
        r"\s*(?:있어|있네|보여|보이네|맞아|맞네)\Z"
    ),
    "compass": re.compile(
        r"(?:나침반\s*(?:문양|모양)|(?:문양|모양)(?:은|이|는)?\s*나침반\s*모양)"
        r"(?:으로|처럼)?\s*(?:보여|보이네|같아|같네|이네)\Z"
    ),
    "needle_gray": re.compile(
        r"(?:바늘(?:은|이|는)?\s*회색|회색\s*바늘)(?:으로)?\s*"
        r"(?:보여|보이네|같아|같네|이네)\Z"
    ),
    "door_21": re.compile(
        r"문\s*(?:번호|숫자|옆\s*(?:숫자|번호))(?:는|가|도)?\s*"
        r"(?:21|스물하나|이십일)(?:로)?\s*"
        r"(?:보여|보이네|읽혀|읽히네|맞아|맞네|야|이야|네|이네)\Z"
    ),
    "original_21": re.compile(
        r"(?:원본\s*(?:창|지도)|원래\s*지도)(?:도|는|가)?\s*"
        r"(?:21|스물하나|이십일)(?:로)?\s*"
        r"(?:보여|보이네|읽혀|읽히네|맞아|맞네|야|이야|네|이네)\Z"
    ),
    "feather": re.compile(
        r"깃털(?:을)?\s*(?:처럼|같|닮은\s*듯)\s*"
        r"(?:보여|보이네|보이는\s*(?:문양이네|구나)|같아|같네|닮아|닮았네|듯해)\Z"
    ),
}
_STANDALONE_AN_NEGATION_RE = re.compile(
    r"(?<![0-9A-Za-z가-힣])안(?=(?:\s|보이|보여|같|맞|있|읽|닮|$))"
)


class CorrectionTargetRealizationError(ValueError):
    """Sanitized evaluator rejection."""


def _invalid() -> CorrectionTargetRealizationError:
    return CorrectionTargetRealizationError("correction realization rejected")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise _invalid() from None


def _load_a43_oracle() -> tuple[dict[str, Any], str]:
    spec = importlib.util.spec_from_file_location(
        "airi_a45_a43_oracle", HERE / "correction_target.py"
    )
    if spec is None or spec.loader is None:
        raise _invalid()
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        oracle = module.load_oracle()
    except Exception:
        raise _invalid() from None
    digest = hashlib.sha256(canonical_bytes(oracle)).hexdigest()
    if digest != A43_ORACLE_SHA256 or module.ORACLE_SHA256 != A43_ORACLE_SHA256:
        raise _invalid()
    return oracle, digest


def _number_lexicon() -> dict[str, int]:
    sino_ones = ("", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구")
    native_tens = ("", "열", "스물", "서른", "마흔", "쉰", "예순", "일흔", "여든", "아흔")
    native_ones = ("", "하나", "둘", "셋", "넷", "다섯", "여섯", "일곱", "여덟", "아홉")
    result: dict[str, int] = {}
    for value in range(10, 100):
        ten, one = divmod(value, 10)
        sino_ten = "십" if ten == 1 else sino_ones[ten] + "십"
        result[sino_ten + (sino_ones[one] if one else "")] = value
        result[native_tens[ten] + native_ones[one]] = value
    return result


_NUMBER_WORDS = _number_lexicon()
_NUMBER_WORDS_BY_LENGTH = tuple(sorted(_NUMBER_WORDS, key=len, reverse=True))
_SINGLE_NUMBER_WORDS = (
    "하나", "다섯", "여섯", "일곱", "여덟", "아홉", "둘", "셋", "넷",
    "일", "이", "삼", "사", "오", "육", "칠", "팔", "구",
)


def validate_oracle(
    value: object, fixture: object, sidecar: object
) -> dict[str, Any]:
    expected = {
        "schema_version", "synthetic_only", "human_review_required",
        "operational_adoption", "base_fixture_sha256",
        "reply_act_fixture_sha256", "a43_oracle_sha256",
        "a44_protocol_version", "source_run", "source_packet_sha256",
        "entries",
    }
    if type(value) is not dict or set(value) != expected or type(value["entries"]) is not list:
        raise _invalid()
    if (
        value["schema_version"] != ORACLE_SCHEMA_VERSION
        or value["synthetic_only"] is not True
        or value["human_review_required"] is not True
        or value["operational_adoption"] is not False
        or value["base_fixture_sha256"] != BASE_FIXTURE_SHA256
        or value["reply_act_fixture_sha256"] != REPLY_ACT_FIXTURE_SHA256
        or value["a43_oracle_sha256"] != A43_ORACLE_SHA256
        or value["a44_protocol_version"] != A44_PROTOCOL_VERSION
        or value["source_run"] != SOURCE_RUN
        or value["source_packet_sha256"] != SOURCE_PACKET_SHA256
        or hashlib.sha256(canonical_bytes(value)).hexdigest() != ORACLE_SHA256
        or hashlib.sha256(canonical_bytes(fixture)).hexdigest() != BASE_FIXTURE_SHA256
        or hashlib.sha256(canonical_bytes(sidecar)).hexdigest() != REPLY_ACT_FIXTURE_SHA256
    ):
        raise _invalid()
    a43_oracle, a43_digest = _load_a43_oracle()
    if a43_digest != value["a43_oracle_sha256"]:
        raise _invalid()
    a43_mappings = tuple(
        (entry["turn_id"], entry["target_id"], entry["direction"])
        for entry in a43_oracle["entries"]
    )
    if a43_mappings != tuple(row[:3] for row in MAPPINGS):
        raise _invalid()
    actual: list[tuple[object, ...]] = []
    for entry in value["entries"]:
        if type(entry) is not dict or set(entry) != {
            "turn_id", "target_id", "direction", "rule_id", "fallback_id"
        }:
            raise _invalid()
        actual.append(tuple(entry[key] for key in (
            "turn_id", "target_id", "direction", "rule_id", "fallback_id"
        )))
    if tuple(actual) != MAPPINGS or len({row[0] for row in actual}) != len(MAPPINGS):
        raise _invalid()
    return deepcopy(value)


def load_oracle(path: Path = ORACLE_PATH) -> dict[str, Any]:
    return validate_oracle(_load(path), _load(FIXTURE_PATH), _load(REPLY_ACT_PATH))


def _validated_text(value: object) -> str:
    if type(value) is not str or not (1 <= len(value) <= MAX_TEXT_CHARS):
        raise _invalid()
    if (
        unicodedata.normalize("NFC", value) != value
        or len(value.encode("utf-8")) > MAX_TEXT_BYTES
        or any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in value)
    ):
        raise _invalid()
    return value


def _number_evidence(text: str) -> tuple[bool, bool]:
    accepted = "스물하나" in text or "이십일" in text
    working = text.replace("스물하나", "").replace("이십일", "")
    competing = False
    for token in _ARABIC_NUMBER_RE.findall(text):
        if token == "21":
            accepted = True
        else:
            competing = True
    for word in _NUMBER_WORDS_BY_LENGTH:
        if word in working:
            if _NUMBER_WORDS[word] != 21:
                competing = True
            else:
                accepted = True
        working = working.replace(word, "")
    for word in _SINGLE_NUMBER_WORDS:
        if re.search(
            rf"(?<![0-9A-Za-z가-힣]){word}(?=(?:로|으로|와|과|을|를|이|가|은|는|도|[\s,.!?]|$))",
            working,
        ):
            competing = True
    if (
        _OUT_OF_RANGE_NUMBER_RE.search(working)
        or _MIXED_SCALE_NUMBER_RE.search(working)
        or _ZERO_LOANWORD_RE.search(working)
    ):
        competing = True
    return accepted, competing


def _required_cues(rule: str, text: str) -> bool:
    positive = any(marker in text for marker in _POSITIVE_MARKERS)
    if rule == "rabbit_ears":
        return re.search(r"토끼\s*귀", text) is not None and positive
    if rule == "candle_wick":
        return re.search(r"촛불\s*심지", text) is not None and positive
    if rule == "exit_right":
        return (
            re.search(r"오른쪽\s*문", text) is not None
            and re.search(r"출구\s*(?:표시|표식)?", text) is not None
        )
    if rule == "compass":
        return "나침반" in text and ("문양" in text or "모양" in text) and positive
    if rule == "needle_gray":
        return (
            re.search(r"바늘.{0,16}회색|회색.{0,16}바늘", text) is not None
            and positive
        )
    if rule in {"door_21", "original_21"}:
        accepted, competing = _number_evidence(text)
        if not accepted or competing:
            return False
        if rule == "door_21":
            return re.search(
                r"문\s*(?:번호|숫자|옆\s*(?:숫자|번호))", text
            ) is not None
        return re.search(r"(?:원본\s*(?:창|지도)|원래\s*지도)", text) is not None
    if rule == "feather":
        return "깃털" in text and any(marker in text for marker in ("처럼", "같", "닮", "듯"))
    return False


def _direction_satisfied(rule: str, text: str) -> bool:
    if any(marker in text for marker in _HYPOTHETICAL_MARKERS):
        return False
    sentences = tuple(
        sentence.strip() for sentence in re.split(r"[.!]+", text) if sentence.strip()
    )
    target_asserted = any(
        _required_cues(rule, sentence)
        and _ASSERTIVE_PATTERNS[rule].search(sentence) is not None
        for sentence in sentences
    )
    if not target_asserted:
        return False
    if rule == "original_21":
        return not any(marker in text for marker in ("카메라", "반전", "뒤집"))
    if rule == "feather":
        identity = re.search(r"깃털\s*(?:이야|이다|입니다|이네)", text) is not None
        certainty = any(marker in text for marker in ("확실", "분명", "틀림없"))
        return not identity and not certainty
    return True


def evaluate(
    turn_id: object, target_id: object, direction: object,
    assistant_text: object, oracle: object = None,
) -> dict[str, object]:
    text = _validated_text(assistant_text)
    checked = load_oracle() if oracle is None else validate_oracle(
        oracle, _load(FIXTURE_PATH), _load(REPLY_ACT_PATH)
    )
    matches = [
        entry for entry in checked["entries"]
        if (entry["turn_id"], entry["target_id"], entry["direction"])
        == (turn_id, target_id, direction)
    ]
    if len(matches) != 1:
        raise _invalid()
    rule = matches[0]["rule_id"]
    checks = {
        "bounded_single_utterance": (
            text == text.strip()
            and "\n" not in text
            and "\r" not in text
            and "?" not in text
            and not any(char in _QUOTES for char in text)
            and not any(marker in text for marker in _META_MARKERS)
        ),
        "required_cues_present": _required_cues(rule, text),
        "positive_polarity": (
            not any(marker in text for marker in _NEGATION_MARKERS + _REJECTION_MARKERS)
            and _STANDALONE_AN_NEGATION_RE.search(text) is None
        ),
        "forbidden_cues_absent": not any(
            marker in text for marker in _FORBIDDEN_BY_RULE[rule]
        ),
        "direction_form_satisfied": _direction_satisfied(rule, text),
    }
    failure_mask = sum(
        (1 << index) for index, name in enumerate(_CHECK_NAMES) if not checks[name]
    )
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "synthetic_only": True,
        "lexical_only": True,
        "decision": (
            "candidate_satisfies_structural_postcondition"
            if failure_mask == 0 else "candidate_fails_structural_postcondition"
        ),
        "checks": checks,
        "failure_mask": failure_mask,
    }


def validate_fallback_artifact(
    value: object, *, expected_id: object = None
) -> dict[str, object]:
    expected = {
        "schema_version", "synthetic_only", "status", "fallback_id",
        "realization", "postcondition", "text",
    }
    if type(value) is not dict or set(value) != expected:
        raise _invalid()
    fallback_id = value.get("fallback_id")
    if (
        value.get("schema_version") != FALLBACK_SCHEMA_VERSION
        or value.get("synthetic_only") is not True
        or value.get("status") != "evaluator_only_unapproved"
        or value.get("realization") != "fixed_korean_template"
        or value.get("postcondition") != "exact_template_only"
        or fallback_id not in FALLBACKS
        or value.get("text") != FALLBACKS[fallback_id]
        or (expected_id is not None and fallback_id != expected_id)
    ):
        raise _invalid()
    _validated_text(value["text"])
    if len(canonical_bytes(value)) > MAX_FALLBACK_BYTES:
        raise _invalid()
    return deepcopy(value)


def serialize_fallback_artifact(value: object) -> bytes:
    return canonical_bytes(validate_fallback_artifact(value))


def parse_fallback_artifact(value: object) -> dict[str, object]:
    if type(value) is not str or len(value.encode("utf-8")) > MAX_FALLBACK_BYTES:
        raise _invalid()
    if unicodedata.normalize("NFC", value) != value or any(
        unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in value
    ):
        raise _invalid()
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise _invalid() from None
    clean = validate_fallback_artifact(parsed)
    if value.encode("utf-8") != canonical_bytes(clean):
        raise _invalid()
    return clean


def fallback_for(
    turn_id: object, target_id: object, direction: object, oracle: object = None
) -> dict[str, object]:
    checked = load_oracle() if oracle is None else validate_oracle(
        oracle, _load(FIXTURE_PATH), _load(REPLY_ACT_PATH)
    )
    found = [
        entry for entry in checked["entries"]
        if (entry["turn_id"], entry["target_id"], entry["direction"])
        == (turn_id, target_id, direction)
    ]
    if len(found) != 1:
        raise _invalid()
    fallback_id = found[0]["fallback_id"]
    return validate_fallback_artifact({
        "schema_version": FALLBACK_SCHEMA_VERSION,
        "synthetic_only": True,
        "status": "evaluator_only_unapproved",
        "fallback_id": fallback_id,
        "realization": "fixed_korean_template",
        "postcondition": "exact_template_only",
        "text": FALLBACKS[fallback_id],
    })
