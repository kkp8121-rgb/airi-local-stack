"""Read-only, content-free preflight for the approved topic workflow."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO

from compile_approved_topics import build_runtime_board, runtime_items_are_live
from topic_board import load_approved_topics
from topic_discovery_contract import load_raw, load_source_policies, materialize_curations
from topic_review_contract import TopicReviewError, load_decisions, load_pending, read_jsonl, review_output_path, runtime_output_path

_KEYS = ("status", "stage", "policy_count", "raw_count", "curation_count", "pending_count", "decision_count", "approved_count", "live_count")
_DISABLED = {"status": "disabled", "stage": "disabled", "policy_count": 0, "raw_count": 0, "curation_count": 0, "pending_count": 0, "decision_count": 0, "approved_count": 0, "live_count": 0}
_NAMES = ("source-policies", "raw-discoveries", "curations", "pending", "decisions", "runtime-board", "policy-id")


def _render(output: TextIO, status: str, stage: str, counts: dict[str, int]) -> None:
    value = {"status": status, "stage": stage, **{key: int(counts.get(key, 0)) for key in _KEYS[2:]}}
    output.write(json.dumps(value, separators=(",", ":")) + "\n")
    output.flush()


def _arguments(argv: list[str]) -> dict[str, str]:
    if argv.count("--inspect-topic-workflow") != 1:
        raise TopicReviewError("invalid request")
    values: dict[str, str] = {}
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--inspect-topic-workflow":
            index += 1; continue
        if not token.startswith("--") or token[2:] not in _NAMES or token in values or index + 1 >= len(argv):
            raise TopicReviewError("invalid request")
        values[token] = argv[index + 1]
        index += 2
    if set(values) != {f"--{name}" for name in _NAMES}:
        raise TopicReviewError("invalid request")
    return {name: values[f"--{name}"] for name in _NAMES}


def run_cli(argv: list[str] | None = None, *, output: TextIO | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    output = sys.stdout if output is None else output
    # This branch is deliberately before parsing or any dependency/path access.
    if "--inspect-topic-workflow" not in argv:
        _render(output, "disabled", "disabled", {})
        return 0
    counts: dict[str, int] = {}
    try:
        args = _arguments(argv)
        paths = {name: review_output_path(args[name]) for name in _NAMES[:-2]}
        runtime = runtime_output_path(args["runtime-board"])
        policy_id = args["policy-id"]
        present = {name: paths[name].exists() for name in paths}
        runtime_present = runtime.exists()
        later = lambda *names: runtime_present or any(present[name] for name in names)
        if not present["source-policies"]:
            if later("raw-discoveries", "curations", "pending", "decisions"):
                raise TopicReviewError("orphan artifact")
            _render(output, "ok", "policy_required", counts); return 0
        policies = load_source_policies(paths["source-policies"]); counts["policy_count"] = len(policies)
        if policy_id not in policies:
            raise TopicReviewError("unknown policy")
        if not present["raw-discoveries"]:
            if later("curations", "pending", "decisions"):
                raise TopicReviewError("orphan artifact")
            _render(output, "ok", "raw_required", counts); return 0
        raw = load_raw(paths["raw-discoveries"], paths["source-policies"]); counts["raw_count"] = len(raw)
        if not present["curations"] or not present["pending"]:
            if present["curations"] != present["pending"] or later("decisions"):
                raise TopicReviewError("orphan artifact")
            if runtime_present:
                raise TopicReviewError("orphan artifact")
            _render(output, "ok", "raw_required" if not raw else "curation_required", counts); return 0
        curations = read_jsonl(paths["curations"]); counts["curation_count"] = len(curations)
        pending = load_pending(paths["pending"]); counts["pending_count"] = len(pending)
        curated = materialize_curations(raw, curations)
        if curated != pending:
            raise TopicReviewError("partial curation")
        if len(curations) < len(raw):
            if present["decisions"] or runtime_present:
                raise TopicReviewError("orphan artifact")
            _render(output, "ok", "curation_required", counts); return 0
        if not pending:
            if present["decisions"]:
                decisions = load_decisions(paths["decisions"], pending)
                counts["decision_count"] = len(decisions)
            if runtime_present:
                raise TopicReviewError("stale runtime")
            _render(output, "ok", "raw_required", counts); return 0
        if not present["decisions"]:
            if runtime_present:
                raise TopicReviewError("orphan artifact")
            _render(output, "ok", "review_required", counts); return 0
        decisions = load_decisions(paths["decisions"], pending); counts["decision_count"] = len(decisions)
        if {row["id"] for row in decisions} != {row["id"] for row in pending}:
            if runtime_present:
                raise TopicReviewError("orphan artifact")
            _render(output, "ok", "review_required", counts); return 0
        approved = [row for row in decisions if row["decision"] == "approve"]
        counts["approved_count"] = len(approved)
        if not approved:
            if runtime_present:
                raise TopicReviewError("stale runtime")
            _render(output, "ok", "raw_required", counts); return 0
        items, data = build_runtime_board(pending, decisions)
        if not runtime_items_are_live(items):
            raise TopicReviewError("no live topics")
        if not runtime_present:
            _render(output, "ok", "compile_required", counts); return 0
        live = load_approved_topics(runtime)
        if not live or len(live) != len(items) or runtime.read_bytes() != data:
            raise TopicReviewError("stale runtime")
        counts["live_count"] = len(live)
        _render(output, "ok", "ready", counts); return 0
    except (OSError, RuntimeError, UnicodeDecodeError, ValueError, TopicReviewError, json.JSONDecodeError):
        _render(output, "rejected", "rejected", counts)
        return 2


def main(argv: list[str] | None = None) -> int:
    return run_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
