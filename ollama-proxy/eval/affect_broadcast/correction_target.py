"""Pure offline validation for pinned synthetic correction-target assertions."""
from __future__ import annotations

import hashlib
import json
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
FIXTURE_PATH = HERE / "synthetic_affect_broadcast_v1.json"
REPLY_ACT_PATH = HERE / "synthetic_reply_act_v1.json"
ORACLE_PATH = HERE / "correction_target_v1.json"
ORACLE_SCHEMA_VERSION = "airi.correction-target-oracle.v1"
CANDIDATE_SCHEMA_VERSION = "airi.correction-target.v1"
ELIGIBILITY_SCHEMA_VERSION = "airi.correction-target-eligibility.v1"
BASE_FIXTURE_SHA256 = "acbcc991e32820aeed2bb2eeaf58487f72a4629393c57d11142b77d84ead1bf8"
REPLY_ACT_FIXTURE_SHA256 = "2b12124df8b28f4588fb85213f989ad1cebd923e8363fb3ba2aeead85c84f041"
ORACLE_SHA256 = "6c4dbcaa9daec85408a4cec34cc9213b3b3848202b83aee315ad62866e5e12e1"
MAX_CANDIDATE_BYTES = 512
_EVIDENCE_BASIS = "pinned_synthetic_fixture_assertion"
_POSTCONDITION = "exact_closed_target_pair_only"
_CANDIDATE_KEYS = ["schema_version", "act", "target_id", "direction", "evidence_basis"]
_TURN_TARGETS = (
    ("teasing-02", "rabbit_ears", "replace_prior_visual_interpretation"),
    ("teasing-12", "candle_wick", "replace_prior_visual_interpretation"),
    ("correction-02", "exit_marker_right_door", "replace_prior_visual_interpretation"),
    ("correction-03", "bottom_glyph_compass", "replace_prior_visual_interpretation"),
    ("correction-04", "needle_gray", "replace_prior_visual_interpretation"),
    ("correction-07", "door_number_twenty_one", "replace_prior_visual_interpretation"),
    ("correction-08", "original_map_number_twenty_one", "confirm_corrected_reading"),
    ("correction-12", "glyph_feather_like", "shift_to_hedged_resemblance"),
)
_ALLOWED_PAIRS = frozenset((target_id, direction) for _, target_id, direction in _TURN_TARGETS)


class CorrectionTargetError(ValueError):
    """Sanitized rejection for this offline-only evaluator."""


def _invalid() -> CorrectionTargetError:
    return CorrectionTargetError("correction target rejected")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _valid_text(value: object) -> bool:
    return (
        type(value) is str
        and unicodedata.normalize("NFC", value) == value
        and not any(unicodedata.category(character) in {"Cc", "Cf", "Cs"} for character in value)
    )


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise _invalid() from None


def validate_candidate(candidate: object) -> dict[str, str]:
    """Accept only the exact, bounded, canonical correction-target shape."""
    if type(candidate) is not dict or set(candidate) != set(_CANDIDATE_KEYS):
        raise _invalid()
    if any(not _valid_text(value) for value in candidate.values()):
        raise _invalid()
    if (
        candidate["schema_version"] != CANDIDATE_SCHEMA_VERSION
        or candidate["act"] != "correct"
        or candidate["evidence_basis"] != _EVIDENCE_BASIS
        or (candidate["target_id"], candidate["direction"]) not in _ALLOWED_PAIRS
        or len(canonical_bytes(candidate)) > MAX_CANDIDATE_BYTES
    ):
        raise _invalid()
    return deepcopy(candidate)


def serialize_candidate(candidate: object) -> bytes:
    """Return the sole canonical UTF-8 representation of a valid candidate."""
    return canonical_bytes(validate_candidate(candidate))


def parse_candidate(candidate: object) -> dict[str, str]:
    """Parse only a byte-for-byte canonical JSON candidate representation."""
    if (
        type(candidate) is not str
        or not _valid_text(candidate)
        or len(candidate.encode("utf-8")) > MAX_CANDIDATE_BYTES
    ):
        raise _invalid()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        raise _invalid() from None
    clean = validate_candidate(parsed)
    if candidate.encode("utf-8") != canonical_bytes(clean):
        raise _invalid()
    return clean


def _selected_turn_ids(fixture: object) -> list[str]:
    if type(fixture) is not dict or type(fixture.get("scenarios")) is not list:
        raise _invalid()
    identifiers: list[str] = []
    for scenario in fixture["scenarios"]:
        if type(scenario) is not dict or type(scenario.get("turns")) is not list:
            raise _invalid()
        for turn in scenario["turns"]:
            if type(turn) is not dict or not _valid_text(turn.get("id")):
                raise _invalid()
            if turn.get("selected_message") is not None:
                identifiers.append(turn["id"])
    return identifiers


def _correct_sidecar_turn_ids(sidecar: object) -> list[str]:
    if type(sidecar) is not dict or type(sidecar.get("entries")) is not list:
        raise _invalid()
    identifiers: list[str] = []
    for row in sidecar["entries"]:
        if type(row) is not dict or not _valid_text(row.get("turn_id")):
            raise _invalid()
        reply_act = row.get("expected_reply_act")
        if type(reply_act) is not dict:
            raise _invalid()
        if reply_act.get("act") == "correct":
            identifiers.append(row["turn_id"])
    return identifiers


def validate_oracle(value: object, fixture: object, sidecar: object) -> dict[str, Any]:
    """Validate the immutable synthetic-only oracle and its pinned inputs."""
    required = ["schema_version", "synthetic_only", "base_fixture_sha256", "reply_act_fixture_sha256", "entries"]
    if type(value) is not dict or list(value) != required or type(value["entries"]) is not list:
        raise _invalid()
    if (
        value["schema_version"] != ORACLE_SCHEMA_VERSION
        or value["synthetic_only"] is not True
        or value["base_fixture_sha256"] != BASE_FIXTURE_SHA256
        or value["reply_act_fixture_sha256"] != REPLY_ACT_FIXTURE_SHA256
        or hashlib.sha256(canonical_bytes(value)).hexdigest() != ORACLE_SHA256
        or hashlib.sha256(canonical_bytes(fixture)).hexdigest() != BASE_FIXTURE_SHA256
        or hashlib.sha256(canonical_bytes(sidecar)).hexdigest() != REPLY_ACT_FIXTURE_SHA256
    ):
        raise _invalid()
    selected_ids = _selected_turn_ids(fixture)
    sidecar_ids = _correct_sidecar_turn_ids(sidecar)
    actual: list[tuple[str, str, str]] = []
    for entry in value["entries"]:
        keys = ["turn_id", "expected_act", "target_id", "direction", "evidence_basis", "postcondition"]
        if type(entry) is not dict or list(entry) != keys or any(not _valid_text(part) for part in entry.values()):
            raise _invalid()
        if entry["expected_act"] != "correct" or entry["evidence_basis"] != _EVIDENCE_BASIS or entry["postcondition"] != _POSTCONDITION:
            raise _invalid()
        actual.append((entry["turn_id"], entry["target_id"], entry["direction"]))
    if (
        [turn_id for turn_id, _, _ in actual] != sidecar_ids
        or tuple(actual) != _TURN_TARGETS
        or any(turn_id not in selected_ids for turn_id, _, _ in actual)
        or len({turn_id for turn_id, _, _ in actual}) != len(actual)
        or len({target_id for _, target_id, _ in actual}) != len(actual)
    ):
        raise _invalid()
    return deepcopy(value)


def load_oracle(path: Path = ORACLE_PATH) -> dict[str, Any]:
    """Load the pinned local oracle; no service or runtime integration is used."""
    return validate_oracle(_load_json(path), _load_json(FIXTURE_PATH), _load_json(REPLY_ACT_PATH))


def validate_target_for_turn(turn_id: object, candidate: object, oracle: object = None) -> dict[str, str]:
    """Return a closed eligibility marker only for the exact pinned turn/pair."""
    if not _valid_text(turn_id):
        raise _invalid()
    clean = validate_candidate(candidate)
    checked_oracle = load_oracle() if oracle is None else validate_oracle(
        oracle, _load_json(FIXTURE_PATH), _load_json(REPLY_ACT_PATH)
    )
    matches = [
        entry for entry in checked_oracle["entries"]
        if entry["turn_id"] == turn_id
        and entry["target_id"] == clean["target_id"]
        and entry["direction"] == clean["direction"]
    ]
    if len(matches) != 1:
        raise _invalid()
    return deepcopy({
        "schema_version": ELIGIBILITY_SCHEMA_VERSION,
        "decision": "eligible_for_offline_human_review",
        "act": "correct",
        "target_id": clean["target_id"],
        "direction": clean["direction"],
        "evidence_basis": _EVIDENCE_BASIS,
    })
