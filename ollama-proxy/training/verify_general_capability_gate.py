"""Offline general-capability regression gate for trained Mi:dm merges.

Three cumulative LoRA merges (v3 -> E2-C1 -> E2-C2) were shipped before anyone
measured whether general Korean ability was eroding.  The 2026-08-25 M2
baseline showed it is, monotonically: kobest -0.90%p and haerae -1.92%p for the
latest merge.  This gate compares one lm-evaluation-harness results file for a
candidate merge against the frozen stock baseline commitment and fails closed
when any committed group drops by more than the committed budget.

It reads JSON only.  It never loads a model, never relaxes the threshold from
the command line, and treats a missing group or subtask as a failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

BASELINE_SCHEMA_VERSION = "airi.general-capability-baseline.v1"
VERDICT_SCHEMA_VERSION = "airi.general-capability-gate-verdict.v1"
DEFAULT_BASELINE = (Path(__file__).resolve().parents[1] / "eval" / "broadcast_sim" / "fixtures"
                    / "commitments" / "airi_general_capability_baseline.json")
EPSILON = 1e-9


class GateError(ValueError):
    """Fail-closed: the inputs cannot be judged, so the gate does not pass."""


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError(f"{label}: unreadable JSON at {path}") from exc
    if not isinstance(document, dict):
        raise GateError(f"{label}: top level is not an object")
    return document


def _ratio(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GateError(f"{label}: not a number")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise GateError(f"{label}: outside [0, 1]")
    return number


def load_baseline(path: Path) -> dict[str, Any]:
    baseline = _read_json(path, "baseline")
    if baseline.get("schema_version") != BASELINE_SCHEMA_VERSION:
        raise GateError(f"baseline schema_version is not {BASELINE_SCHEMA_VERSION}")
    groups = baseline.get("groups")
    subtasks = baseline.get("subtasks")
    gate = baseline.get("gate")
    if not isinstance(groups, dict) or not groups:
        raise GateError("baseline lacks groups")
    if not isinstance(subtasks, dict) or not subtasks:
        raise GateError("baseline lacks subtasks")
    if not isinstance(gate, dict):
        raise GateError("baseline lacks gate")
    budget = gate.get("max_group_drop_pct_points")
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not 0 < float(budget) <= 100:
        raise GateError("baseline gate budget must be a percentage-point number in (0, 100]")
    for name, value in list(groups.items()) + list(subtasks.items()):
        _ratio(value, f"baseline {name}")
    if baseline.get("metric") != "acc,none":
        raise GateError("baseline metric must be acc,none")
    return baseline


def load_candidate_results(path: Path) -> tuple[dict[str, Any], str]:
    document = _read_json(path, "candidate")
    results = document.get("results")
    if not isinstance(results, dict) or not results:
        raise GateError("candidate results file has no results")
    return document, hashlib.sha256(path.read_bytes()).hexdigest()


def judge(baseline: dict[str, Any], candidate: dict[str, Any], candidate_sha256: str) -> dict[str, Any]:
    """Pure comparison; returns the verdict document (status pass|fail)."""
    metric = baseline["metric"]
    budget = float(baseline["gate"]["max_group_drop_pct_points"])
    results = candidate["results"]
    config = candidate.get("config") if isinstance(candidate.get("config"), dict) else {}
    expected = baseline.get("harness", {})
    mismatches: list[str] = []
    # lm_eval records CLI values verbatim (batch_size "16", limit None), so
    # compare their text forms rather than their types.
    for key in ("num_fewshot", "batch_size", "limit"):
        if key in expected and key in config and str(config[key]) != str(expected[key]):
            mismatches.append(f"{key}: candidate {config[key]!r} != baseline {expected[key]!r}")
    if mismatches:
        raise GateError("candidate harness settings differ from the baseline: " + "; ".join(mismatches))

    group_rows: dict[str, dict[str, float | bool]] = {}
    failed: list[str] = []
    for group, base in baseline["groups"].items():
        if group not in results or metric not in results[group]:
            raise GateError(f"candidate lacks group {group} ({metric})")
        value = _ratio(results[group][metric], f"candidate {group}")
        drop = round((float(base) - value) * 100.0, 4)
        passed = drop <= budget + EPSILON
        group_rows[group] = {"baseline": float(base), "candidate": value,
                             "drop_pct_points": drop, "passed": passed}
        if not passed:
            failed.append(group)
    subtask_rows: dict[str, dict[str, float]] = {}
    for task, base in baseline["subtasks"].items():
        if task not in results or metric not in results[task]:
            raise GateError(f"candidate lacks subtask {task} ({metric})")
        value = _ratio(results[task][metric], f"candidate {task}")
        subtask_rows[task] = {"baseline": float(base), "candidate": value,
                              "delta_pct_points": round((value - float(base)) * 100.0, 4)}
    return {
        "schema_version": VERDICT_SCHEMA_VERSION,
        "status": "pass" if not failed else "fail",
        "adoption_authorized": False,
        "baseline_schema_version": baseline["schema_version"],
        "baseline_stock_results_sha256": baseline.get("stock_model", {}).get("results_sha256"),
        "candidate_results_sha256": candidate_sha256,
        "candidate_model_args": config.get("model_args"),
        "max_group_drop_pct_points": budget,
        "groups": group_rows,
        "subtasks": subtask_rows,
        "failed_groups": failed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--candidate", type=Path, required=True,
                        help="lm-eval results_*.json for the trained merge")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE,
                        help="frozen stock baseline commitment (default: in-repo)")
    parser.add_argument("--output", type=Path, help="write the verdict JSON here (no overwrite)")
    args = parser.parse_args(argv)
    try:
        baseline = load_baseline(args.baseline)
        candidate, sha = load_candidate_results(args.candidate)
        verdict = judge(baseline, candidate, sha)
        if args.output is not None:
            if args.output.exists():
                raise GateError(f"verdict already exists: {args.output}")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(verdict, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                   encoding="utf-8")
    except GateError as exc:
        print(json.dumps({"schema_version": VERDICT_SCHEMA_VERSION, "status": "fail",
                          "adoption_authorized": False, "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": verdict["status"], "failed_groups": verdict["failed_groups"],
                      "groups": {g: r["drop_pct_points"] for g, r in verdict["groups"].items()}},
                     ensure_ascii=False))
    return 0 if verdict["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
