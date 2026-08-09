#!/usr/bin/env python3
"""Read-only operational gate for local memory extraction benchmark reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

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


def _zero_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


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


def verify(report_path: Path, fixtures_path: Path, model: str, expected_model_digest: str) -> str | None:
    """Return a stable failure code, or ``None`` when the gate passes."""
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
    unit_metrics = (
        "schema_pass_rate", "stage_a_schema_pass_rate", "stage_b_schema_pass_rate",
        "connectivity_rate", "stage_b_coverage_rate", "critical_recall",
        "placeholder_rate", "stage_b_op_alias_accuracy",
    )
    if (any(not _unit_number(extraction.get(metric)) for metric in unit_metrics)
            or not _zero_int(extraction.get("unexpected"))
            or not _zero_int(extraction.get("stage_a_unexpected"))
            or extraction.get("failure_code_counts") != {}):
        return "GATE_METRICS_INVALID"

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
    counts = {fixture_id: 0 for fixture_id in expected_set}
    for row in result_rows:
        if not _mapping(row) or not isinstance(row.get("id"), str):
            return "RESULT_FIXTURE_ROWS_INVALID"
        fixture_id = row["id"]
        if fixture_id not in counts:
            return "UNKNOWN_RESULT_FIXTURE"
        true_fields = (
            "schema_pass", "stage_a_schema_pass", "stage_b_schema_pass", "connectivity",
            "stage_b_coverage", "placeholder_preserved", "alias_ok",
        )
        unit_fields = (
            "critical_recall", "stage_a_critical_recall", "stage_b_op_alias_accuracy",
        )
        if (any(row.get(field) is not True for field in true_fields)
                or any(not _unit_number(row.get(field)) for field in unit_fields)
                or not _zero_int(row.get("unexpected"))
                or not _zero_int(row.get("stage_a_unexpected"))
                or row.get("failure_codes") != []
                or not isinstance(row.get("stage_b_decision_schema_sha256"), str)
                or re.fullmatch(r"[0-9a-fA-F]{64}", row["stage_b_decision_schema_sha256"]) is None
                or row.get("error_stage") is not None
                or row.get("error_code") is not None):
            return "FIXTURE_RESULT_FAILED"
        counts[fixture_id] += 1
    if any(count != runs for count in counts.values()):
        return "FIXTURE_RUN_COUNT_MISMATCH"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify an extraction benchmark gate without side effects.")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--fixtures", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-digest", required=True)
    args = parser.parse_args(argv)
    reason = verify(args.report, args.fixtures, args.model, args.model_digest)
    if reason is not None:
        print(f"EXTRACTION_GATE_{reason}", file=sys.stderr)
        return 1
    print("extraction gate verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
