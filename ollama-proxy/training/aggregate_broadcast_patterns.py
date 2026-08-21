"""Aggregate research-only broadcast observations into a content-free profile.

The source ledger may contain official URLs and creator names for custody, while
observation rows contain only abstract mechanics.  This module verifies that
boundary and emits counts only; no quote, transcript, handle, amount, URL, or
creator identity can enter the synthesis profile.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Sequence


PROFILE_SCHEMA_VERSION = "airi.broadcast-pattern-profile.v1"
MIN_OBSERVATIONS = 30
MIN_CREATORS = 4
MIN_EVENT_TYPES = 5
MIN_CONTIGUOUS = 8
MIN_BURST = 6
MIN_EXPANDED = 6


class BroadcastPatternError(ValueError):
    """Research input violated the non-training observation contract."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _counter(values: Sequence[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def validate_observation(row: dict[str, Any]) -> None:
    if row.get("schema_version") != "airi.broadcast-reference-event.v1":
        raise BroadcastPatternError("unexpected observation schema")
    if row.get("dataset_role") != "observation_only":
        raise BroadcastPatternError("observation must stay research-only")
    provenance = row.get("provenance") or {}
    if provenance.get("contains_transcript") is not False:
        raise BroadcastPatternError("observation may not contain a transcript")
    if provenance.get("contains_pii") is not False:
        raise BroadcastPatternError("observation may not contain PII")
    if provenance.get("training_permitted") is not False:
        raise BroadcastPatternError("observation may not authorize training")
    beats = row.get("response_beats")
    registers = row.get("register_by_beat")
    if not isinstance(beats, list) or not beats or len(beats) != len(registers or []):
        raise BroadcastPatternError("observation beat/register contract is malformed")


def aggregate(rows: Sequence[dict[str, Any]], ledger: dict[str, Any]) -> dict[str, Any]:
    if not rows:
        raise BroadcastPatternError("observation corpus is empty")
    for row in rows:
        validate_observation(row)
    if ledger.get("training_permitted") is not False:
        raise BroadcastPatternError("source ledger may not authorize training")
    if ledger.get("contains_transcript") is not False or ledger.get("contains_viewer_pii") is not False:
        raise BroadcastPatternError("source ledger custody boundary is open")
    sources = ledger.get("sources") or []
    ledger_cases = {source.get("source_case_id") for source in sources}
    observation_cases = {row.get("source_case_id") for row in rows}
    if len(observation_cases) != len(rows) or observation_cases != ledger_cases:
        raise BroadcastPatternError("observation/source-ledger binding mismatch")

    creators = {source.get("creator") for source in sources if source.get("creator")}
    event_types = [row["event_type"] for row in rows]
    pressures = [row["queue_pressure"] for row in rows]
    evidence = [row["evidence_tier"] for row in rows]
    expansions = [row["expansion_scope"] for row in rows]
    handoffs = [row["handoff"] for row in rows]
    beat_counts = Counter(beat for row in rows for beat in row["response_beats"])
    sequences = Counter(">".join(row["response_beats"]) for row in rows)
    register_transitions = Counter()
    for row in rows:
        registers = row["register_by_beat"]
        for left, right in zip(registers, registers[1:]):
            register_transitions[f"{left}>{right}"] += 1

    coverage_checks = {
        "observations": len(rows) >= MIN_OBSERVATIONS,
        "creator_diversity": len(creators) >= MIN_CREATORS,
        "event_diversity": len(set(event_types)) >= MIN_EVENT_TYPES,
        "contiguous_evidence": evidence.count("official_primary_contiguous") >= MIN_CONTIGUOUS,
        "burst_pressure": pressures.count("burst") >= MIN_BURST,
        "expanded_responses": sum(scope in {"brief", "sustained"} for scope in expansions) >= MIN_EXPANDED,
    }
    source_digest = hashlib.sha256(canonical_bytes({
        "observations": rows,
        "ledger_case_ids": sorted(observation_cases),
    })).hexdigest()
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "dataset_role": "content_free_pattern_profile",
        "training_permitted": False,
        "source_digest_sha256": source_digest,
        "observations": len(rows),
        "source_creator_count": len(creators),
        "coverage_checks": coverage_checks,
        "promotion_ready": all(coverage_checks.values()),
        "counts": {
            "event_type": _counter(event_types),
            "queue_pressure": _counter(pressures),
            "evidence_tier": _counter(evidence),
            "expansion_scope": _counter(expansions),
            "handoff": _counter(handoffs),
            "response_beat": dict(sorted(beat_counts.items())),
            "response_sequence": dict(sorted(sequences.items())),
            "register_transition": dict(sorted(register_transitions.items())),
        },
        "privacy": {
            "contains_creator_identity": False,
            "contains_source_url": False,
            "contains_transcript": False,
            "contains_viewer_pii": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="abstract broadcast observations → content-free profile")
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--source-ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    rows = [
        json.loads(line) for line in args.observations.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ledger = json.loads(args.source_ledger.read_text(encoding="utf-8"))
    profile = aggregate(rows, ledger)
    payload = json.dumps(profile, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")
    return 0 if profile["promotion_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
