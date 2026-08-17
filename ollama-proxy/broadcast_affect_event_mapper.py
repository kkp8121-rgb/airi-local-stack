"""Pure, inert mapping from broadcast outcome candidates to affect events.

This module is intentionally not wired into a runtime.  It accepts only a
small, content-free candidate schema and constructs one fixed A1 affect event
for each allowed pair.  Shape validation does not authenticate the caller or
prove delivery; a future B4b observer must establish that trust boundary.
"""
from __future__ import annotations

from typing import Any

from affect_state import EVENT_SCHEMA_VERSION, validate_event


BROADCAST_AFFECT_OUTCOME_CANDIDATE_SCHEMA_VERSION = "airi.broadcast-affect-outcome-candidate.v1"
MAX_SAFE_INTEGER = 9007199254740991

_OUTCOME_KEYS = frozenset(("schema_version", "evidence", "outcome", "delivery_status", "turn_index"))
_MAPPINGS = {
    ("director_delivery", "donation_acknowledged"): (
        "broadcast_director", "donation_received",
        {"goal_congruence": 1, "agency": "none", "control": 1, "novelty": 1, "social_tone": "neutral"}, 1,
    ),
    ("director_delivery", "callback_hit"): (
        "broadcast_director", "callback_hit",
        {"goal_congruence": 1, "agency": "none", "control": 1, "novelty": 1, "social_tone": "neutral"}, 1,
    ),
    ("director_delivery", "callback_miss"): (
        "broadcast_director", "callback_miss",
        {"goal_congruence": -1, "agency": "none", "control": 1, "novelty": 1, "social_tone": "neutral"}, 1,
    ),
    ("game_telemetry", "game_success"): (
        "broadcast_director", "game_success",
        {"goal_congruence": 1, "agency": "self", "control": 2, "novelty": 1, "social_tone": "neutral"}, 2,
    ),
    ("game_telemetry", "game_failure"): (
        "broadcast_director", "game_failure",
        {"goal_congruence": -1, "agency": "none", "control": 1, "novelty": 1, "social_tone": "neutral"}, 2,
    ),
    ("silence_observer", "silence"): (
        "broadcast_director", "silence",
        {"goal_congruence": -1, "agency": "none", "control": 1, "novelty": 1, "social_tone": "neutral"}, 1,
    ),
    ("proxy_terminal_output", "response_repair"): (
        "proxy_outcome", "response_repair",
        {"goal_congruence": 1, "agency": "none", "control": 1, "novelty": 1, "social_tone": "neutral"}, 2,
    ),
}


class BroadcastAffectMappingError(ValueError):
    """A deliberately sanitized mapping failure that never reflects input."""


def _invalid() -> BroadcastAffectMappingError:
    return BroadcastAffectMappingError("invalid broadcast affect outcome")


def map_broadcast_outcome_candidate(value: object) -> dict[str, Any]:
    """Map one exact outcome candidate to a newly validated affect event.

    Caller-provided data is never copied into event content except the bounded
    integer ``turn_index``.  A1 validation is the final authority over event
    shape, not over the candidate's delivery provenance.
    """
    if type(value) is not dict or set(value) != _OUTCOME_KEYS:
        raise _invalid()
    schema_version = value["schema_version"]
    evidence = value["evidence"]
    outcome = value["outcome"]
    delivery_status = value["delivery_status"]
    turn_index = value["turn_index"]
    if (
        type(schema_version) is not str
        or type(evidence) is not str
        or type(outcome) is not str
        or type(delivery_status) is not str
        or schema_version != BROADCAST_AFFECT_OUTCOME_CANDIDATE_SCHEMA_VERSION
        or delivery_status != "delivered"
        or len(evidence) > 64
        or len(outcome) > 64
        or len(delivery_status) > 16
        or type(turn_index) is not int
        or not 0 <= turn_index <= MAX_SAFE_INTEGER
    ):
        raise _invalid()
    mapping = _MAPPINGS.get((evidence, outcome))
    if mapping is None:
        raise _invalid()
    source, kind, appraisal, weight = mapping
    event = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "source": source,
        "kind": kind,
        "appraisal": dict(appraisal),
        "weight": weight,
        "turn_index": turn_index,
    }
    try:
        return validate_event(event)
    except Exception:
        raise _invalid() from None
