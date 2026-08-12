#!/usr/bin/env python3
"""Read-only operational gate for local memory extraction benchmark reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping

from memory_prompts import (
    STAGE_A_CONVERSATION_SYSTEM_PROMPT,
    STAGE_A_SCHEMA,
    STAGE_B_DECISION_SYSTEM_PROMPT,
)
from memory_stage_b import DECISION_SCHEMA_TEMPLATE, decision_factory_probe_sha256


STAGE_A_CONTRACT = "conversation-v2b"
STAGE_B_CONTRACT = "decision-v2.1"
RUNTIME_OPTIONS = {
    "temperature": 0,
    "num_ctx": 8192,
    "num_gpu": 0,
    "seed": 42,
    "max_tokens": 2048,
}
_EPSILON = 1e-9

# Structural rates stay at 1.0 in every profile.  A batch that fails schema,
# entity connectivity or Stage-B coverage is rejected again at runtime by
# compile_decisions/_validate_extraction_coverage, so the watermark never
# advances.  With temperature=0 the same batch then fails identically on every
# retry until the session dead-letters, which means a sub-1.0 structural rate
# is a permanently stuck extractor rather than a graded quality loss.
STRUCTURAL_RATES = (
    "schema_pass_rate",
    "stage_a_schema_pass_rate",
    "stage_b_schema_pass_rate",
    "connectivity_rate",
    "stage_b_coverage_rate",
)
# Model-judgement metrics.  These never fail a batch: they change what gets
# stored, not whether storing succeeds, so they are the only relaxable knobs.
MIN_RATE_METRICS = {
    "critical_recall": "min_critical_recall",
    "placeholder_rate": "min_placeholder_rate",
    "stage_b_op_alias_accuracy": "min_stage_b_op_alias_accuracy",
}
# Counted per row so the bound does not loosen as fixtures or runs grow.
MAX_COUNT_METRICS = {
    "unexpected": "max_unexpected_rate",
    "stage_a_unexpected": "max_stage_a_unexpected_rate",
}
# Single source of truth for the gate numbers; nothing else hardcodes them.
GATE_PROFILES: dict[str, dict[str, float]] = {
    "strict": {
        "min_critical_recall": 1.0,
        "min_placeholder_rate": 1.0,
        "min_stage_b_op_alias_accuracy": 1.0,
        "max_unexpected_rate": 0.0,
        "max_stage_a_unexpected_rate": 0.0,
    },
    "balanced": {
        # A miss is recoverable: the turn stays in the journal, bounded journal
        # recall still answers from it, and a repeated topic is re-extracted.
        "min_critical_recall": 0.70,
        # A dropped {{user}} placeholder writes the real display name into the
        # store permanently.  Not destructive, but it violates the universal
        # storage policy, so only a single fixture may miss it.
        "min_placeholder_rate": 0.85,
        # A wrong Stage-B action can SUPERSEDE a correct memory, which is the
        # only relaxable metric that can destroy existing data.  Held above
        # recall for that reason.
        "min_stage_b_op_alias_accuracy": 0.80,
        # Over-extraction stores something the user did not say.  0.25 per row
        # means at most one such item across the frozen 7-fixture set.
        "max_unexpected_rate": 0.25,
        # Stage-A-only accounting does not offset legitimate optional items the
        # way the combined metric does, so the same bound would double-penalize.
        "max_stage_a_unexpected_rate": 0.5,
    },
}
DEFAULT_GATE_PROFILE = "balanced"
PROFILE_ENV = "AIRI_MEMORY_EXTRACTION_GATE_PROFILE"
THRESHOLD_ENV_PREFIX = "AIRI_MEMORY_EXTRACTION_GATE_"


def resolve_gate_thresholds(
    profile: str | None = None, env: Mapping[str, str] | None = None
) -> tuple[str, dict[str, float]]:
    """Resolve the active profile name and its thresholds.

    Precedence: explicit argument, then ``AIRI_MEMORY_EXTRACTION_GATE_PROFILE``,
    then the default profile.  Every threshold accepts an individual override
    such as ``AIRI_MEMORY_EXTRACTION_GATE_MIN_CRITICAL_RECALL``.
    """
    source = os.environ if env is None else env
    raw_profile = profile if profile is not None else source.get(PROFILE_ENV, "")
    name = (raw_profile or DEFAULT_GATE_PROFILE).strip().lower()
    if name not in GATE_PROFILES:
        raise ValueError("extraction gate profile must be one of: " + ", ".join(sorted(GATE_PROFILES)))
    thresholds = dict(GATE_PROFILES[name])
    for key in thresholds:
        variable = THRESHOLD_ENV_PREFIX + key.upper()
        raw = source.get(variable)
        if raw is None or not raw.strip():
            continue
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"{variable} must be a number") from exc
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{variable} must be between 0 and 1")
        thresholds[key] = value
    return name, thresholds


def _rate(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0.0 <= float(value) <= 1.0


def _count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def gate_metrics_pass(metrics: Mapping[str, Any], row_count: int, thresholds: Mapping[str, float]) -> bool:
    """Shared gate formula for the benchmark writer and this verifier."""
    rows = max(1, int(row_count))
    if any(not _unit_number(metrics.get(name)) for name in STRUCTURAL_RATES):
        return False
    for name, key in MIN_RATE_METRICS.items():
        value = metrics.get(name)
        if not _rate(value) or float(value) < float(thresholds[key]) - _EPSILON:
            return False
    for name, key in MAX_COUNT_METRICS.items():
        value = metrics.get(name)
        if not _count(value) or value / rows > float(thresholds[key]) + _EPSILON:
            return False
    return True


def _load_json(path: Path, error: str) -> tuple[Any | None, str | None]:
    try:
        with path.open("r", encoding="utf-8") as source:
            return json.load(source), None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, error


def _mapping(value: Any) -> bool:
    return isinstance(value, dict)


def _unit_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == 1.0


def _thresholds_not_more_lenient(
    declared: Any, active: Mapping[str, float]
) -> str | None:
    """Reject a report measured under a looser gate than the operator's own."""
    if declared is None:
        # A report without recorded thresholds predates profiles; treat it as
        # strict, which is never more lenient than any active profile.
        return None
    if not _mapping(declared) or set(declared) - set(active):
        return "GATE_THRESHOLDS_INVALID"
    for key, active_value in active.items():
        value = declared.get(key, 1.0 if key.startswith("min_") else 0.0)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return "GATE_THRESHOLDS_INVALID"
        if key.startswith("min_") and float(value) < float(active_value) - _EPSILON:
            return "GATE_THRESHOLDS_TOO_LENIENT"
        if key.startswith("max_") and float(value) > float(active_value) + _EPSILON:
            return "GATE_THRESHOLDS_TOO_LENIENT"
    return None


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _contract_hashes() -> dict[str, str]:
    return {
        "stage_a_active_prompt_sha256": hashlib.sha256(
            STAGE_A_CONVERSATION_SYSTEM_PROMPT.encode("utf-8")
        ).hexdigest(),
        "stage_b_decision_prompt_sha256": hashlib.sha256(
            STAGE_B_DECISION_SYSTEM_PROMPT.encode("utf-8")
        ).hexdigest(),
        "stage_a_schema_sha256": _canonical_sha256(STAGE_A_SCHEMA),
        "stage_b_decision_schema_template_sha256": _canonical_sha256(
            DECISION_SCHEMA_TEMPLATE
        ),
        "stage_b_decision_factory_probe_sha256": decision_factory_probe_sha256(),
    }


def verify(report_path: Path, fixtures_path: Path, model: str, expected_model_digest: str,
           *, profile: str | None = None, thresholds: Mapping[str, float] | None = None) -> str | None:
    """Return a stable failure code, or ``None`` when the gate passes."""
    if thresholds is None:
        try:
            _name, thresholds = resolve_gate_thresholds(profile)
        except ValueError:
            return "PROFILE_INVALID"
    report, error = _load_json(report_path, "REPORT_INVALID")
    if error:
        return error
    fixtures, error = _load_json(fixtures_path, "FIXTURES_INVALID")
    if error:
        return error
    if not _mapping(report) or not _mapping(fixtures):
        return "REPORT_INVALID"

    config = report.get("config")
    results = report.get("results")
    if not _mapping(config) or not _mapping(results):
        return "REPORT_STRUCTURE_INVALID"
    extraction = results.get("extraction")
    if not _mapping(extraction):
        return "EXTRACTION_RESULT_MISSING"

    if config.get("mode") != "extraction":
        return "CONFIG_MODE_INVALID"
    if config.get("model") != model:
        return "CONFIG_MODEL_MISMATCH"
    model_digest = config.get("model_digest")
    if not isinstance(model_digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", model_digest) is None:
        return "MODEL_DIGEST_INVALID"
    if (not isinstance(expected_model_digest, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", expected_model_digest) is None):
        return "EXPECTED_MODEL_DIGEST_INVALID"
    if model_digest.lower() != expected_model_digest.lower():
        return "MODEL_DIGEST_MISMATCH"
    if any(type(config.get(name)) is not int or config[name] != expected
           for name, expected in RUNTIME_OPTIONS.items()):
        return "RUNTIME_OPTIONS_MISMATCH"
    if config.get("allow_cloud") is not False:
        return "CLOUD_NOT_DISABLED"
    if type(config.get("think")) is not bool or config["think"] is not False:
        return "THINK_NOT_DISABLED"
    reproducibility = config.get("reproducibility")
    if not _mapping(reproducibility):
        return "REPRODUCIBILITY_MISSING"
    try:
        actual_hash = hashlib.sha256(fixtures_path.read_bytes()).hexdigest()
    except OSError:
        return "FIXTURES_INVALID"
    if reproducibility.get("fixture_sha256") != actual_hash:
        return "FIXTURE_HASH_MISMATCH"
    if any(reproducibility.get(name) != expected for name, expected in _contract_hashes().items()):
        return "CONTRACT_HASH_MISMATCH"

    if config.get("stage_a_contract") != STAGE_A_CONTRACT:
        return "CONFIG_STAGE_A_CONTRACT_MISMATCH"
    if config.get("stage_b_contract") != STAGE_B_CONTRACT:
        return "CONFIG_STAGE_B_CONTRACT_MISMATCH"
    if extraction.get("stage_a_contract") != STAGE_A_CONTRACT:
        return "RESULT_STAGE_A_CONTRACT_MISMATCH"
    if extraction.get("stage_b_contract") != STAGE_B_CONTRACT:
        return "RESULT_STAGE_B_CONTRACT_MISMATCH"
    if extraction.get("stage_a_contract") != config.get("stage_a_contract"):
        return "STAGE_A_CONTRACT_INCONSISTENT"
    if extraction.get("stage_b_contract") != config.get("stage_b_contract"):
        return "STAGE_B_CONTRACT_INCONSISTENT"

    if extraction.get("status") != "measured":
        return "EXTRACTION_NOT_MEASURED"
    if extraction.get("gate_pass") is not True:
        return "GATE_NOT_PASSED"
    if extraction.get("model") != model:
        return "RESULT_MODEL_MISMATCH"
    runs = extraction.get("runs")
    if isinstance(runs, bool) or not isinstance(runs, int) or runs < 1:
        return "RUNS_INVALID"
    declared_profile = extraction.get("gate_profile")
    if declared_profile is not None and (
            not isinstance(declared_profile, str)
            or declared_profile.strip().lower() not in GATE_PROFILES):
        return "GATE_PROFILE_UNKNOWN"
    lenience_error = _thresholds_not_more_lenient(extraction.get("gate_thresholds"), thresholds)
    if lenience_error:
        return lenience_error

    fixture_rows = fixtures.get("extraction")
    if not isinstance(fixture_rows, list):
        return "FIXTURE_STRUCTURE_INVALID"
    expected_ids: list[str] = []
    for row in fixture_rows:
        if not _mapping(row) or not isinstance(row.get("id"), str):
            return "FIXTURE_STRUCTURE_INVALID"
        expected_ids.append(row["id"])
    expected_set = set(expected_ids)
    if len(expected_set) != len(expected_ids):
        return "FIXTURE_IDS_NOT_UNIQUE"

    result_ids = extraction.get("fixture_ids")
    if not isinstance(result_ids, list) or any(not isinstance(item, str) for item in result_ids):
        return "RESULT_FIXTURE_IDS_INVALID"
    if len(result_ids) != len(set(result_ids)) or set(result_ids) != expected_set:
        return "FIXTURE_ID_COVERAGE_MISMATCH"

    result_rows = extraction.get("fixtures")
    if not isinstance(result_rows, list):
        return "RESULT_FIXTURE_ROWS_INVALID"
    if (not gate_metrics_pass(extraction, len(result_rows), thresholds)
            or extraction.get("failure_code_counts") != {}):
        return "GATE_METRICS_INVALID"
    counts = {fixture_id: 0 for fixture_id in expected_set}
    totals: dict[str, float] = {name: 0.0 for name in (
        *STRUCTURAL_RATES, *MIN_RATE_METRICS, *MAX_COUNT_METRICS)}
    # Structural outcomes stay mandatory per row: a batch that fails one of
    # them cannot advance the watermark at runtime under any profile.
    true_fields = (
        "schema_pass", "stage_a_schema_pass", "stage_b_schema_pass", "connectivity",
        "stage_b_coverage",
    )
    rate_fields = ("critical_recall", "stage_a_critical_recall", "stage_b_op_alias_accuracy")
    bool_fields = ("placeholder_preserved", "alias_ok")
    count_fields = ("unexpected", "stage_a_unexpected")
    for row in result_rows:
        if not _mapping(row) or not isinstance(row.get("id"), str):
            return "RESULT_FIXTURE_ROWS_INVALID"
        fixture_id = row["id"]
        if fixture_id not in counts:
            return "UNKNOWN_RESULT_FIXTURE"
        if (any(row.get(field) is not True for field in true_fields)
                or any(not _rate(row.get(field)) for field in rate_fields)
                or any(not isinstance(row.get(field), bool) for field in bool_fields)
                or any(not _count(row.get(field)) for field in count_fields)
                or row.get("failure_codes") != []
                or not isinstance(row.get("stage_b_decision_schema_sha256"), str)
                or re.fullmatch(r"[0-9a-fA-F]{64}", row["stage_b_decision_schema_sha256"]) is None
                or row.get("error_stage") is not None
                or row.get("error_code") is not None):
            return "FIXTURE_RESULT_FAILED"
        counts[fixture_id] += 1
        totals["schema_pass_rate"] += 1.0
        totals["stage_a_schema_pass_rate"] += 1.0
        totals["stage_b_schema_pass_rate"] += 1.0
        totals["connectivity_rate"] += 1.0
        totals["stage_b_coverage_rate"] += 1.0
        totals["critical_recall"] += float(row["critical_recall"])
        totals["placeholder_rate"] += float(row["placeholder_preserved"])
        totals["stage_b_op_alias_accuracy"] += float(row["stage_b_op_alias_accuracy"])
        totals["unexpected"] += row["unexpected"]
        totals["stage_a_unexpected"] += row["stage_a_unexpected"]
    if any(count != runs for count in counts.values()):
        return "FIXTURE_RUN_COUNT_MISMATCH"
    # The relaxed gate reads the aggregates, so they must be derived from the
    # rows rather than merely asserted next to them.
    divisor = max(1, len(result_rows))
    for name in (*STRUCTURAL_RATES, *MIN_RATE_METRICS):
        if abs(float(extraction[name]) - totals[name] / divisor) > 1e-6:
            return "AGGREGATE_MISMATCH"
    for name in MAX_COUNT_METRICS:
        if extraction[name] != totals[name]:
            return "AGGREGATE_MISMATCH"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify an extraction benchmark gate without side effects.")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--fixtures", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-digest", required=True)
    parser.add_argument("--profile", choices=sorted(GATE_PROFILES), default=None,
                        help=f"Gate threshold profile; defaults to ${PROFILE_ENV} or {DEFAULT_GATE_PROFILE}.")
    args = parser.parse_args(argv)
    try:
        name, thresholds = resolve_gate_thresholds(args.profile)
    except ValueError:
        print("EXTRACTION_GATE_PROFILE_INVALID", file=sys.stderr)
        return 1
    reason = verify(args.report, args.fixtures, args.model, args.model_digest, thresholds=thresholds)
    if reason is not None:
        print(f"EXTRACTION_GATE_{reason}", file=sys.stderr)
        return 1
    print(f"extraction gate verified (profile={name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
