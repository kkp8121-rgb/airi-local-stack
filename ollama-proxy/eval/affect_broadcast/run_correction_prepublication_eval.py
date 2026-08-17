"""Offline A4.6 comparison using a strict injected fake-transport envelope.

Attestations are evaluator inputs, not evidence that safety or tool truth was
actually established.  No live transport is implemented.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
ENVELOPE_SCHEMA_VERSION = "airi.correction-prepublication-candidate.v1"
REPORT_SCHEMA_VERSION = "airi.correction-prepublication-public-report.v1"
ATTESTATION_FAILURE_MASK = 1 << 20
FALLBACK_SOURCE_FAILURE_MASK = 1 << 21
MAX_PUBLIC_TOKEN_COUNT = 1_000_000


class CorrectionPrepublicationEvalError(ValueError):
    """Sanitized evaluator failure."""


def _policy() -> Any:
    spec = importlib.util.spec_from_file_location("airi_a46_policy", HERE / "correction_prepublication_policy.py")
    if spec is None or spec.loader is None:
        raise CorrectionPrepublicationEvalError("a4.6 evaluator unavailable")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        raise CorrectionPrepublicationEvalError("a4.6 evaluator unavailable") from None
    return module


policy = _policy()
Transport = Callable[[int, int], dict[str, object]]
FallbackAttestor = Callable[[int, str], dict[str, object]]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def validate_candidate_envelope(value: object) -> dict[str, object]:
    keys = ["schema_version", "candidate", "safety_passed", "tool_truth_unchanged", "public_token_count"]
    if type(value) is not dict or set(value) != set(keys):
        raise CorrectionPrepublicationEvalError("candidate envelope rejected")
    valid = (
        value["schema_version"] == ENVELOPE_SCHEMA_VERSION
        and type(value["candidate"]) is str
        and type(value["safety_passed"]) is bool
        and type(value["tool_truth_unchanged"]) is bool
        and type(value["public_token_count"]) is int
        and 0 <= value["public_token_count"] <= MAX_PUBLIC_TOKEN_COUNT
    )
    if not valid:
        raise CorrectionPrepublicationEvalError("candidate envelope rejected")
    return dict(value)


def eligibility() -> dict[str, object]:
    oracle = policy.load_oracle()
    return {
        "schema_version": "airi.correction-prepublication-eval-eligibility.v1",
        "decision": "eligible_for_injected_fake_transport_only",
        "entry_count": len(oracle["entries"]),
        "network_call_count": 0,
        "proxy_call_count": 0,
        "model_call_count": 0,
        "operational_adoption": False,
    }


def _attestation_ok(envelope: dict[str, object]) -> bool:
    return envelope["safety_passed"] is True and envelope["tool_truth_unchanged"] is True and envelope["public_token_count"] == 0


def _check(
    row: dict[str, Any],
    envelope: dict[str, object],
    source: str,
) -> dict[str, object]:
    if not _attestation_ok(envelope):
        return {"failure_mask": ATTESTATION_FAILURE_MASK, "boundary_passed": False}
    if source == "transport" and envelope["candidate"].strip() == row["fallback"]:
        return {"failure_mask": FALLBACK_SOURCE_FAILURE_MASK, "boundary_passed": True}
    checked = policy.evaluate(row["turn_id"], row["target_id"], row["direction"], envelope["candidate"])
    return {"failure_mask": checked["failure_mask"], "boundary_passed": True}


def _ledger(attempt: int, source: str, checked: dict[str, object]) -> dict[str, object]:
    return {
        "attempt": attempt,
        "source": source,
        "failure_mask": checked["failure_mask"],
        "eligible_for_private_review": checked["failure_mask"] == 0,
    }


def _transport_candidate(
    transport: Transport,
    ordinal: int,
    attempt: int,
) -> dict[str, object]:
    try:
        candidate = transport(ordinal, attempt)
    except Exception:
        raise CorrectionPrepublicationEvalError("fake transport failed") from None
    return validate_candidate_envelope(candidate)


def _fallback_candidate(
    attestor: FallbackAttestor,
    ordinal: int,
    expected: str,
) -> dict[str, object]:
    try:
        candidate = attestor(ordinal, expected)
    except Exception:
        raise CorrectionPrepublicationEvalError("fallback attestation failed") from None
    envelope = validate_candidate_envelope(candidate)
    if envelope["candidate"] != expected:
        raise CorrectionPrepublicationEvalError("fallback attestation failed")
    return envelope


def _row_result(
    row: dict[str, Any],
    ordinal: int,
    transport: Transport,
    fallback_attestor: FallbackAttestor,
    strategy: str,
    initial: dict[str, object],
) -> dict[str, object]:
    first = _check(row, dict(initial), "transport")
    ledger = [_ledger(1, "transport", first)]
    upstream_attempts = 1
    result = first
    # A failed boundary is terminal: never retry, fall back, or mark eligible.
    if first["failure_mask"] != 0 and first["boundary_passed"]:
        if strategy == "retry":
            result = _check(
                row,
                _transport_candidate(transport, ordinal, 2),
                "transport",
            )
            upstream_attempts = 2
            ledger.append(_ledger(2, "transport", result))
        elif strategy == "fallback":
            fallback = _fallback_candidate(
                fallback_attestor,
                ordinal,
                row["fallback"],
            )
            result = _check(row, fallback, "fixed_fallback")
            ledger.append(_ledger(2, "fixed_fallback", result))
        else:
            raise CorrectionPrepublicationEvalError("unknown strategy")
    return {
        "status": "eligible_for_private_review" if result["failure_mask"] == 0 else "blocked",
        "failure_mask": result["failure_mask"],
        "upstream_attempts": upstream_attempts,
        "ledger": ledger,
    }


def validate_public_report(value: object) -> dict[str, object]:
    keys = [
        "schema_version",
        "synthetic_only",
        "human_review_required",
        "operational_adoption",
        "attestations_only_not_proof",
        "strategies",
    ]
    valid_root = (
        type(value) is dict
        and set(value) == set(keys)
        and value["schema_version"] == REPORT_SCHEMA_VERSION
        and value["synthetic_only"] is True
        and value["human_review_required"] is True
        and value["operational_adoption"] is False
        and value["attestations_only_not_proof"] is True
        and type(value["strategies"]) is dict
        and set(value["strategies"]) == {"retry", "fallback"}
    )
    if not valid_root:
        raise CorrectionPrepublicationEvalError("public report rejected")
    for name, arm in value["strategies"].items():
        counts = ("row_count", "eligible_count", "blocked_count", "upstream_attempt_count")
        expected_keys = [
            "row_count",
            "eligible_count",
            "blocked_count",
            "upstream_attempt_count",
            "failure_mask_counts",
        ]
        valid_masks = type(arm) is dict and type(arm.get("failure_mask_counts")) is list
        if valid_masks:
            mask_rows = arm["failure_mask_counts"]
            valid_masks = (
                all(
                    type(mask_row) is dict
                    and set(mask_row) == {"mask", "count"}
                    and type(mask_row["mask"]) is int
                    and mask_row["mask"] >= 0
                    and type(mask_row["count"]) is int
                    and mask_row["count"] >= 0
                    for mask_row in mask_rows
                )
                and [mask_row["mask"] for mask_row in mask_rows]
                == sorted({mask_row["mask"] for mask_row in mask_rows})
                and sum(mask_row["count"] for mask_row in mask_rows) == 8
            )
        valid_arm = (
            type(arm) is dict
            and set(arm) == set(expected_keys)
            and all(type(arm[key]) is int and arm[key] >= 0 for key in counts)
            and arm["row_count"] == 8
            and arm["eligible_count"] + arm["blocked_count"] == 8
            and valid_masks
            and sum(
                mask_row["count"]
                for mask_row in arm["failure_mask_counts"]
                if mask_row["mask"] == 0
            )
            == arm["eligible_count"]
            and (name != "retry" or 8 <= arm["upstream_attempt_count"] <= 16)
            and (name != "fallback" or arm["upstream_attempt_count"] == 8)
        )
        if not valid_arm:
            raise CorrectionPrepublicationEvalError("public report rejected")
    return dict(value)


def compare_strategies(
    transport: Transport,
    fallback_attestor: FallbackAttestor,
) -> dict[str, object]:
    """Return content-free aggregates for private structural-review eligibility."""
    if not callable(transport):
        raise CorrectionPrepublicationEvalError("fake transport required")
    if not callable(fallback_attestor):
        raise CorrectionPrepublicationEvalError("fallback attestor required")
    oracle = policy.load_oracle()
    initials = [
        _transport_candidate(transport, ordinal, 1)
        for ordinal, _row in enumerate(oracle["entries"])
    ]
    summary: dict[str, object] = {}
    for strategy in ("retry", "fallback"):
        rows = [
            _row_result(
                row,
                ordinal,
                transport,
                fallback_attestor,
                strategy,
                initials[ordinal],
            )
            for ordinal, row in enumerate(oracle["entries"])
        ]
        mask_counts = Counter(int(row["failure_mask"]) for row in rows)
        summary[strategy] = {
            "row_count": len(rows),
            "eligible_count": sum(
                row["status"] == "eligible_for_private_review" for row in rows
            ),
            "blocked_count": sum(row["status"] == "blocked" for row in rows),
            "upstream_attempt_count": sum(int(row["upstream_attempts"]) for row in rows),
            "failure_mask_counts": [
                {"mask": mask, "count": count}
                for mask, count in sorted(mask_counts.items())
            ],
        }
    return validate_public_report(
        {
            "schema_version": REPORT_SCHEMA_VERSION,
            "synthetic_only": True,
            "human_review_required": True,
            "operational_adoption": False,
            "attestations_only_not_proof": True,
            "strategies": summary,
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A4.6 offline eligibility only")
    parser.parse_args(argv)
    print(canonical_bytes(eligibility()).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
