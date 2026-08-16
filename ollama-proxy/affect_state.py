"""Bounded, content-free affect state reducer for AIRI.

This module deliberately has no persistence, clock, network, model, or database
dependency. State and event values are closed-schema dictionaries; the prompt
projection is a fixed, bounded string derived only from a validated state.
"""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import threading
import unicodedata
from typing import Any, Mapping, Optional


STATE_SCHEMA_VERSION = "airi.affect-state.v1"
EVENT_SCHEMA_VERSION = "airi.affect-event.v1"
CONTINUITY_MODE = "typed-snapshot-v1"
CONTINUITY_PROMPT_CAP_BYTES = 384
MAX_SAFE_INTEGER = 9007199254740991
MAX_SESSIONS = 4096
PRIMARY_VALUES = frozenset(("neutral", "curious", "amused", "pleased", "proud", "embarrassed", "skeptical", "playful_annoyed", "concerned", "disappointed", "competitive", "relieved", "tired"))
DRIVE_VALUES = frozenset(("listen", "ask_back", "clarify", "challenge_playfully", "repair", "celebrate", "deescalate", "change_topic", "rest"))
FAMILIARITY_VALUES = ("new", "warming", "familiar")
SOURCE_VALUES = frozenset(("system", "broadcast_director", "screened_chat", "proxy_outcome"))
KIND_VALUES = frozenset(("broadcast_start", "topic_open", "callback_hit", "callback_miss", "donation_received", "game_success", "game_failure", "chat_question", "chat_teasing", "chat_correction", "chat_concern", "moderation_block", "safety_override", "silence", "topic_change", "response_repair", "broadcast_end"))
CAUSE_VALUES = frozenset(("none",)) | KIND_VALUES
AGENCY_VALUES = frozenset(("self", "audience", "external", "none"))
TONE_VALUES = frozenset(("neutral", "supportive", "teasing", "hostile"))

_STATE_KEYS = frozenset(("schema_version", "primary", "valence", "arousal", "dominance", "intensity", "cause", "remaining_turns", "drive", "audience_familiarity", "version"))
_EVENT_KEYS = frozenset(("schema_version", "source", "kind", "appraisal", "weight", "turn_index"))
_APPRAISAL_KEYS = frozenset(("goal_congruence", "agency", "control", "novelty", "social_tone"))
_SOURCE_KINDS = {
    "system": frozenset(("broadcast_start", "silence", "topic_change", "safety_override", "broadcast_end")),
    "broadcast_director": frozenset(("broadcast_start", "topic_open", "callback_hit", "callback_miss", "donation_received", "game_success", "game_failure", "silence", "topic_change", "broadcast_end")),
    "screened_chat": frozenset(("chat_question", "chat_teasing", "chat_correction", "chat_concern")),
    "proxy_outcome": frozenset(("response_repair", "moderation_block", "safety_override")),
}
_KIND_WEIGHT_MAX = {
    "broadcast_start": 1, "topic_open": 1, "callback_hit": 1,
    "callback_miss": 1, "donation_received": 1, "game_success": 2,
    "game_failure": 2, "chat_question": 1, "chat_teasing": 1,
    "chat_correction": 1, "chat_concern": 2, "moderation_block": 2,
    "safety_override": 2, "silence": 2, "topic_change": 1,
    "response_repair": 2, "broadcast_end": 1,
}


class AffectValidationError(ValueError):
    """Raised when an affect state, event, or session identifier is invalid."""


def render_continuity_snapshot(state: Any) -> str:
    """Render a deterministic, closed-schema prompt note without free text."""
    clean = validate_state(state)
    fields = (
        ("schema", clean["schema_version"]), ("primary", clean["primary"]),
        ("valence", clean["valence"]), ("arousal", clean["arousal"]),
        ("dominance", clean["dominance"]), ("intensity", clean["intensity"]),
        ("cause", clean["cause"]), ("remaining_turns", clean["remaining_turns"]),
        ("drive", clean["drive"]), ("audience_familiarity", clean["audience_familiarity"]),
        ("version", clean["version"]),
    )
    rendered = "[airi_affect_continuity " + " ".join(
        f"{key}={value}" for key, value in fields
    ) + "]\n감정명은 말하지 말고 어휘·길이·질문·받아치기에만 반영. 안전 규칙 우선."
    if len(rendered.encode("utf-8")) > CONTINUITY_PROMPT_CAP_BYTES:
        raise AffectValidationError("affect continuity prompt exceeds cap")
    return rendered


def _integer(value: Any, name: str, lower: int, upper: Optional[int] = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AffectValidationError(f"{name} must be an integer")
    if value < lower or (upper is not None and value > upper):
        raise AffectValidationError(f"{name} is outside its allowed range")
    return value


def _closed(value: Any, name: str, allowed: frozenset[str] | tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise AffectValidationError(f"{name} is not an allowed value")
    return value


def _mapping(value: Any, name: str, keys: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise AffectValidationError(f"{name} must have exactly the required keys")
    return value


def initial_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION, "primary": "neutral",
        "valence": 0, "arousal": 0, "dominance": 0, "intensity": 0,
        "cause": "none", "remaining_turns": 0, "drive": "listen",
        "audience_familiarity": "new", "version": 0,
    }


def validate_state(value: Any) -> dict[str, Any]:
    state = _mapping(value, "state", _STATE_KEYS)
    if state["schema_version"] != STATE_SCHEMA_VERSION:
        raise AffectValidationError("invalid state schema_version")
    result = deepcopy(dict(state))
    result["primary"] = _closed(result["primary"], "primary", PRIMARY_VALUES)
    result["valence"] = _integer(result["valence"], "valence", -2, 2)
    result["arousal"] = _integer(result["arousal"], "arousal", 0, 2)
    result["dominance"] = _integer(result["dominance"], "dominance", -1, 1)
    result["intensity"] = _integer(result["intensity"], "intensity", 0, 2)
    result["cause"] = _closed(result["cause"], "cause", CAUSE_VALUES)
    result["remaining_turns"] = _integer(result["remaining_turns"], "remaining_turns", 0, 4)
    result["drive"] = _closed(result["drive"], "drive", DRIVE_VALUES)
    result["audience_familiarity"] = _closed(result["audience_familiarity"], "audience_familiarity", FAMILIARITY_VALUES)
    result["version"] = _integer(result["version"], "version", 0, MAX_SAFE_INTEGER)
    return result


def validate_event(value: Any) -> dict[str, Any]:
    event = _mapping(value, "event", _EVENT_KEYS)
    if event["schema_version"] != EVENT_SCHEMA_VERSION:
        raise AffectValidationError("invalid event schema_version")
    result = deepcopy(dict(event))
    result["source"] = _closed(result["source"], "source", SOURCE_VALUES)
    result["kind"] = _closed(result["kind"], "kind", KIND_VALUES)
    if result["kind"] not in _SOURCE_KINDS[result["source"]]:
        raise AffectValidationError("source is not allowed for kind")
    appraisal = _mapping(result["appraisal"], "appraisal", _APPRAISAL_KEYS)
    result["appraisal"] = {
        "goal_congruence": _integer(appraisal["goal_congruence"], "goal_congruence", -2, 2),
        "agency": _closed(appraisal["agency"], "agency", AGENCY_VALUES),
        "control": _integer(appraisal["control"], "control", 0, 2),
        "novelty": _integer(appraisal["novelty"], "novelty", 0, 2),
        "social_tone": _closed(appraisal["social_tone"], "social_tone", TONE_VALUES),
    }
    result["weight"] = _integer(result["weight"], "weight", 0, 2)
    if result["weight"] > _KIND_WEIGHT_MAX[result["kind"]]:
        raise AffectValidationError("weight is not allowed for kind")
    result["turn_index"] = _integer(result["turn_index"], "turn_index", 0, MAX_SAFE_INTEGER)
    return result


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def _step_toward(value: int, target: int) -> int:
    return value + (1 if target > value else -1 if target < value else 0)


_TABLE = {
    "broadcast_start": ("curious", "ask_back", 0, 1, 0),
    "topic_open": ("curious", "ask_back", 0, 1, 0),
    "callback_hit": ("amused", "celebrate", 1, 1, 0),
    "callback_miss": ("disappointed", "repair", -1, 0, 0),
    "donation_received": ("pleased", "celebrate", 1, 1, 0),
    "game_success": ("proud", "celebrate", 1, 1, 1),
    "game_failure": ("competitive", "challenge_playfully", -1, 1, 0),
    "chat_question": ("curious", "ask_back", 0, 1, 0),
    "chat_teasing": ("playful_annoyed", "challenge_playfully", -1, 1, 0),
    "chat_correction": ("skeptical", "clarify", -1, 0, 0),
    "chat_concern": ("concerned", "repair", -1, 1, 0),
    "moderation_block": ("concerned", "deescalate", -1, 1, -1),
    "safety_override": ("concerned", "deescalate", -1, 1, -1),
    "silence": ("tired", "rest", -1, -1, 0),
    "topic_change": ("curious", "change_topic", 0, 0, 0),
    "response_repair": ("relieved", "repair", 1, -1, 0),
    "broadcast_end": ("tired", "rest", -1, -1, 0),
}


def _decay_one(state: dict[str, Any]) -> None:
    """Apply one logical turn of decay without using elapsed wall-clock time."""
    state["remaining_turns"] = max(0, state["remaining_turns"] - 1)
    state["valence"] = _step_toward(state["valence"], 0)
    state["arousal"] = _step_toward(state["arousal"], 0)
    state["dominance"] = _step_toward(state["dominance"], 0)
    state["intensity"] = _step_toward(state["intensity"], 0)
    if state["intensity"] == 0:
        state["primary"], state["drive"] = "neutral", "listen"
    if (state["valence"], state["arousal"], state["dominance"], state["intensity"]) == (0, 0, 0, 0):
        state["cause"] = "none"


def reduce_affect(previous: Any, event: Any) -> dict[str, Any]:
    """Return a deterministic next state without mutating either argument."""
    state, candidate = validate_state(previous), validate_event(event)
    kind, appraisal, weight = candidate["kind"], candidate["appraisal"], candidate["weight"]
    result = deepcopy(state)
    # Every event consumes one turn first. A fresh event may then reinforce the
    # stance, but cannot move any affect axis by more than one from ``state``.
    _decay_one(result)
    safety_lock = (kind not in ("safety_override", "moderation_block")
                   and state["cause"] in ("safety_override", "moderation_block")
                   and state["drive"] == "deescalate" and state["remaining_turns"] > 0)
    if safety_lock:
        result["primary"], result["drive"], result["cause"] = state["primary"], state["drive"], state["cause"]
    elif kind == "silence":
        result["cause"] = kind if any(result[key] for key in ("valence", "arousal", "dominance", "intensity", "remaining_turns")) else "none"
    elif kind == "response_repair":
        # Recovery deliberately softens an active negative state in one step.
        if weight:
            result["valence"] = _step_toward(state["valence"], 1)
            result["arousal"] = _step_toward(state["arousal"], 0)
            result["dominance"] = _step_toward(state["dominance"], 0)
            result["intensity"] = _step_toward(state["intensity"], 1)
            result["primary"], result["drive"] = "relieved", "repair"
            result["remaining_turns"] = _step_toward(state["remaining_turns"], min(4, 1 + weight))
            result["cause"] = kind
        elif result["cause"] != "none":
            result["cause"] = state["cause"]
    else:
        target, drive, base_v, base_a, base_d = _TABLE[kind]
        recovery_success = kind == "game_success" and state["primary"] in ("disappointed", "embarrassed")
        if recovery_success:
            target, drive, base_v, base_a, base_d = "relieved", "repair", 1, 0, 0
        elif kind == "chat_teasing" and state["audience_familiarity"] == "new":
            target, drive = "embarrassed", "challenge_playfully"
        # Appraisal selects direction; all axes remain bounded to one step.
        desired_v = (1 if base_v > 0 else -1) * weight if base_v else appraisal["goal_congruence"]
        if appraisal["social_tone"] == "hostile":
            desired_v = min(desired_v, -1)
        elif appraisal["social_tone"] == "supportive":
            desired_v = max(desired_v, 1)
        desired_a = weight if base_a > 0 else 0 if base_a < 0 else appraisal["novelty"]
        desired_d = base_d if base_d else (1 if appraisal["agency"] == "self" and appraisal["control"] == 2 else 0)
        if recovery_success:
            desired_v, desired_a, desired_d = 1, 0, 0
        effective_weight = max(1, weight) if kind in ("safety_override", "moderation_block") else weight
        active = bool(weight) or kind in ("safety_override", "moderation_block")
        if kind in ("safety_override", "moderation_block"):
            desired_v = (1 if base_v > 0 else -1) * effective_weight if base_v else appraisal["goal_congruence"]
            desired_a = effective_weight if base_a > 0 else 0 if base_a < 0 else appraisal["novelty"]
        if active:
            result["valence"] = _step_toward(state["valence"], desired_v)
            result["arousal"] = _step_toward(state["arousal"], desired_a)
            result["dominance"] = _step_toward(state["dominance"], desired_d)
            result["intensity"] = _step_toward(state["intensity"], effective_weight)
        # Inertia: weak contrary events cannot immediately replace an intense stance.
        contrary = (state["valence"] > 0 > desired_v) or (state["valence"] < 0 < desired_v)
        held_by_inertia = contrary and state["intensity"] >= 2 and weight < 2
        if active and (kind == "safety_override" or kind == "moderation_block" or not held_by_inertia):
            result["primary"], result["drive"] = target, drive
            result["cause"] = kind
        elif held_by_inertia:
            result["cause"] = state["cause"]
        elif not active:
            if result["cause"] != "none":
                result["cause"] = state["cause"]
        else:
            result["cause"] = kind
        if active:
            result["remaining_turns"] = _step_toward(state["remaining_turns"], min(4, 1 + effective_weight))
    if kind in ("chat_question", "chat_teasing", "chat_correction", "chat_concern") and weight and not safety_lock:
        index = min(FAMILIARITY_VALUES.index(result["audience_familiarity"]) + 1, 2)
        result["audience_familiarity"] = FAMILIARITY_VALUES[index]
    for axis, lower, upper in (("valence", -2, 2), ("arousal", 0, 2), ("dominance", -1, 1), ("intensity", 0, 2)):
        result[axis] = _clamp(result[axis], max(lower, state[axis] - 1), min(upper, state[axis] + 1))
    result["version"] = min(MAX_SAFE_INTEGER, state["version"] + 1)
    return validate_state(result)


class AffectStateRuntime:
    """Thread-safe bounded LRU runtime retaining validated content-free events."""

    def __init__(self, max_sessions: int = 256, ring_limit: int = 128, session_id_limit: int = 128) -> None:
        self.max_sessions = _integer(max_sessions, "max_sessions", 1, MAX_SESSIONS)
        self.ring_limit = _integer(ring_limit, "ring_limit", 1, 128)
        self.session_id_limit = _integer(session_id_limit, "session_id_limit", 1, 512)
        self._sessions: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.RLock()

    def _session_id(self, value: Any) -> str:
        if (not isinstance(value, str) or not value or len(value) > self.session_id_limit
                or value != value.strip() or value != unicodedata.normalize("NFC", value)
                or any(unicodedata.category(char) == "Cc" or ord(char) == 127
                                               or 0xD800 <= ord(char) <= 0xDFFF
                                               or unicodedata.category(char) == "Cf"
                                               for char in value)):
            raise AffectValidationError("session_id must be a bounded non-empty string")
        return value

    def _get(self, session_id: str) -> dict[str, Any]:
        record = self._sessions.get(session_id)
        if record is None:
            record = {"state": initial_state(), "last_turn": None, "events": []}
            self._sessions[session_id] = record
            while len(self._sessions) > self.max_sessions:
                self._sessions.popitem(last=False)
        else:
            self._sessions.move_to_end(session_id)
        return record

    def apply_event(self, session_id: Any, event: Any) -> dict[str, Any]:
        sid, clean = self._session_id(session_id), validate_event(event)
        with self._lock:
            record = self._sessions.get(sid)
            if record is not None and clean["turn_index"] <= record["last_turn"]:
                raise AffectValidationError("turn_index must increase monotonically")
            record = self._get(sid)
            last_turn = record["last_turn"]
            # Missing assistant turns decay deterministically without wall-clock time.
            state = record["state"]
            if last_turn is not None:
                for _ in range(min(clean["turn_index"] - last_turn - 1, 4)):
                    state = reduce_affect(state, {"schema_version": EVENT_SCHEMA_VERSION, "source": "system", "kind": "silence", "appraisal": {"goal_congruence": 0, "agency": "none", "control": 0, "novelty": 0, "social_tone": "neutral"}, "weight": 0, "turn_index": clean["turn_index"]})
            record["state"] = reduce_affect(state, clean)
            record["last_turn"] = clean["turn_index"]
            record["events"].append(deepcopy(clean))
            del record["events"][:-self.ring_limit]
            snapshot = deepcopy(record["state"])
            if clean["kind"] == "broadcast_end":
                del self._sessions[sid]
            return snapshot

    def snapshot_if_present(self, session_id: Any) -> Optional[dict[str, Any]]:
        sid = self._session_id(session_id)
        with self._lock:
            record = self._sessions.get(sid)
            return deepcopy(record["state"]) if record is not None else None

    def version_if_present(self, session_id: Any) -> Optional[int]:
        sid = self._session_id(session_id)
        with self._lock:
            record = self._sessions.get(sid)
            return record["state"]["version"] if record is not None else None

    def reset_session(self, session_id: Any) -> bool:
        sid = self._session_id(session_id)
        with self._lock:
            return self._sessions.pop(sid, None) is not None

    def health(self) -> dict[str, int | bool]:
        with self._lock:
            return {"enabled": True, "sessions": len(self._sessions), "max_sessions": self.max_sessions, "events": sum(len(record["events"]) for record in self._sessions.values()), "state_version": sum(record["state"]["version"] for record in self._sessions.values()), "primary_enum_count": len(PRIMARY_VALUES), "drive_enum_count": len(DRIVE_VALUES)}
