"""Pure, default-inert realization of a deliberately tiny reply-act subset."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
FIXTURE_PATH = HERE / "synthetic_affect_broadcast_v1.json"
REPLY_ACT_PATH = HERE / "synthetic_reply_act_v1.json"
ORACLE_PATH = HERE / "must_act_realization_v1.json"
ORACLE_SCHEMA_VERSION = "airi.must-act-realization-oracle.v1"
OUTPUT_SCHEMA_VERSION = "airi.must-act-realization.v1"
BASE_FIXTURE_SHA256 = "acbcc991e32820aeed2bb2eeaf58487f72a4629393c57d11142b77d84ead1bf8"
REPLY_ACT_FIXTURE_SHA256 = "2b12124df8b28f4588fb85213f989ad1cebd923e8363fb3ba2aeead85c84f041"
ORACLE_SHA256 = "cec3f9b8c2fc797da8a73b4b35632d9fd7b9305d4e5537812c8d263fb0ffc997"
MAX_RENDERED_BYTES = 512
SUPPORTED_ACTS = frozenset(("thank", "deescalate", "close", "correct", "repair"))
_DIRECTION = "fixed_korean_template"
_POSTCONDITION = "exact_template_only"
_HUMAN_DIRECTION = "human_review_only"
_HUMAN_POSTCONDITION = "emergency_context_required"
_TEMPLATES = {
    "thank": "고마워. 함께해줘서 힘이 돼.",
    "close": "오늘은 여기까지 할게. 고마워.",
    "correct": "정정할게. 확인된 내용만 말할게.",
    "repair": "미안해. 내가 잘못 말했어. 확인하고 바로잡을게.",
    "deescalate": "지금은 안전이 먼저야. 바로 119에 연락하고 주변 사람에게도 도움을 요청해.",
}


class MustActRealizationError(ValueError):
    """Non-reflective failure suitable for evaluator logs."""


def _invalid() -> MustActRealizationError:
    return MustActRealizationError("must-act realization rejected")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _reply_act_api():
    spec = importlib.util.spec_from_file_location("airi_must_act_reply_act", HERE.parents[1] / "broadcast_reply_act.py")
    if spec is None or spec.loader is None:
        raise _invalid()
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_must_act_candidate(candidate: object) -> dict[str, str]:
    """Accept only the existing exact canonical reply-act object."""
    try:
        clean = _reply_act_api().validate_reply_act(candidate)
    except Exception:
        raise _invalid() from None
    if clean != candidate or clean["act"] not in SUPPORTED_ACTS:
        raise _invalid()
    return clean


def parse_must_act_candidate(candidate: object) -> dict[str, str]:
    """Parse only the existing canonical reply-act JSON spelling."""
    try:
        clean = _reply_act_api().parse_reply_act_candidate(candidate)
    except Exception:
        raise _invalid() from None
    return validate_must_act_candidate(clean)


def _trusted_emergency_context(value: object) -> bool:
    return type(value) is dict and value == {"emergency_context": True}


def render_must_act(reply_act: object, *, oracle_context: object = None) -> dict[str, str]:
    """Return a fixed artifact; caller content is neither accepted nor copied."""
    act = validate_must_act_candidate(reply_act)["act"]
    if act == "deescalate" and not _trusted_emergency_context(oracle_context):
        raise _invalid()
    if act != "deescalate" and oracle_context is not None:
        raise _invalid()
    rendered = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "act": act,
        "direction": _DIRECTION,
        "postcondition": _POSTCONDITION,
        "text": _TEMPLATES[act],
    }
    if len(canonical_bytes(rendered)) > MAX_RENDERED_BYTES:
        raise _invalid()
    return validate_rendered_artifact(rendered, expected_act=act)


def serialize_rendered_artifact(value: object) -> bytes:
    """Validate and return the sole UTF-8 canonical representation."""
    return canonical_bytes(validate_rendered_artifact(value))


def validate_rendered_artifact(value: object, *, expected_act: object = None) -> dict[str, str]:
    """Conservative structural postcondition only; not a quality or truth claim."""
    if type(value) is not dict or list(value) != ["schema_version", "act", "direction", "postcondition", "text"]:
        raise _invalid()
    if any(type(value[key]) is not str for key in value):
        raise _invalid()
    act = value["act"]
    if (
        value["schema_version"] != OUTPUT_SCHEMA_VERSION
        or act not in SUPPORTED_ACTS
        or value["direction"] != _DIRECTION
        or value["postcondition"] != _POSTCONDITION
        or value["text"] != _TEMPLATES[act]
        or (expected_act is not None and (type(expected_act) is not str or act != expected_act))
        or unicodedata.normalize("NFC", value["text"]) != value["text"]
        or len(canonical_bytes(value)) > MAX_RENDERED_BYTES
    ):
        raise _invalid()
    return deepcopy(value)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise _invalid() from None


def validate_oracle(value: object, fixture: object, sidecar: object) -> dict[str, Any]:
    """Validate the content-free, ordered realization oracle against pinned inputs."""
    if type(value) is not dict or list(value) != ["schema_version", "synthetic_only", "base_fixture_sha256", "reply_act_fixture_sha256", "entries"]:
        raise _invalid()
    if (
        value["schema_version"] != ORACLE_SCHEMA_VERSION or value["synthetic_only"] is not True
        or value["base_fixture_sha256"] != BASE_FIXTURE_SHA256
        or value["reply_act_fixture_sha256"] != REPLY_ACT_FIXTURE_SHA256
        or hashlib.sha256(canonical_bytes(value)).hexdigest() != ORACLE_SHA256
        or hashlib.sha256(canonical_bytes(fixture)).hexdigest() != BASE_FIXTURE_SHA256
        or hashlib.sha256(canonical_bytes(sidecar)).hexdigest() != REPLY_ACT_FIXTURE_SHA256
    ):
        raise _invalid()
    if type(fixture) is not dict or type(sidecar) is not dict or type(value["entries"]) is not list:
        raise _invalid()
    selected_ids = [turn["id"] for scenario in fixture.get("scenarios", []) if type(scenario) is dict for turn in scenario.get("turns", []) if type(turn) is dict and turn.get("selected_message") is not None]
    supported = [(entry.get("turn_id"), entry.get("expected_reply_act", {}).get("act")) for entry in sidecar.get("entries", []) if type(entry) is dict and type(entry.get("expected_reply_act")) is dict and entry["expected_reply_act"].get("act") in SUPPORTED_ACTS]
    if [turn_id for turn_id, _ in supported if turn_id not in selected_ids] != [] or len(value["entries"]) != len(supported):
        raise _invalid()
    actual: list[tuple[str, str]] = []
    for entry in value["entries"]:
        if type(entry) is not dict:
            raise _invalid()
        required = ["turn_id", "expected_act", "direction", "postcondition"]
        if entry.get("expected_act") == "deescalate":
            required.append("emergency_context")
        if list(entry) != required or type(entry["turn_id"]) is not str or type(entry["expected_act"]) is not str:
            raise _invalid()
        if entry["expected_act"] == "deescalate":
            if type(entry["emergency_context"]) is not bool:
                raise _invalid()
            expected_labels = (
                (_DIRECTION, _POSTCONDITION)
                if entry["emergency_context"]
                else (_HUMAN_DIRECTION, _HUMAN_POSTCONDITION)
            )
        else:
            expected_labels = (_DIRECTION, _POSTCONDITION)
        if (entry["direction"], entry["postcondition"]) != expected_labels:
            raise _invalid()
        actual.append((entry["turn_id"], entry["expected_act"]))
    if actual != supported or len({turn_id for turn_id, _ in actual}) != len(actual):
        raise _invalid()
    return deepcopy(value)


def load_oracle(path: Path = ORACLE_PATH) -> dict[str, Any]:
    """Load the pinned default oracle without contacting any service."""
    return validate_oracle(_load_json(path), _load_json(FIXTURE_PATH), _load_json(REPLY_ACT_PATH))
