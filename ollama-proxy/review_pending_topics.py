"""Offline human reviewer for topic-review decision sidecars only."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Callable, TextIO

from topic_review_contract import (
    DECISIONS, TopicReviewError, atomic_write_jsonl, load_decisions, load_pending,
    record_sha256, review_output_path, validate_decision,
)

Input = Callable[[str], str]


def _ask(prompt: str, input_fn: Input) -> str | None:
    try:
        return input_fn(prompt)
    except (EOFError, KeyboardInterrupt):
        return None


def _bool(prompt: str, input_fn: Input) -> bool | None:
    value = _ask(prompt, input_fn)
    if value is None:
        return None
    value = value.strip().casefold()
    if value in {"yes", "y", "true"}:
        return True
    if value in {"no", "n", "false"}:
        return False
    return None


def _status(pending, decisions, output: TextIO) -> None:
    counts = Counter(row["decision"] for row in decisions)
    print(json.dumps({"status": "pending_review", "pending_count": len(pending), "decision_count": len(decisions), "remaining_count": len(pending) - len(decisions), "decisions": dict(sorted(counts.items()))}, separators=(",", ":")), file=output)


def _show_for_human(row, output: TextIO) -> None:
    """Interactive review is the one intentional local display of the record."""
    for key in ("id", "title", "source", "source_url", "published_at", "summary", "broadcast_line", "expires_at"):
        print(f"{key}: {row[key]}", file=output)


def run_cli(argv: list[str] | None = None, *, input_fn: Input = input, output: TextIO = sys.stdout, error: TextIO = sys.stderr) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--pending"); parser.add_argument("--decisions")
    parser.add_argument("--reviewer"); parser.add_argument("--replace-decision", action="store_true")
    parser.add_argument("--status", action="store_true"); parser.add_argument("--limit", type=int)
    try:
        args, unknown = parser.parse_known_args(argv)
        if unknown or not args.pending or not args.decisions or (args.limit is not None and args.limit < 0):
            raise TopicReviewError("invalid request")
        pending = load_pending(args.pending)
        decisions_path = review_output_path(args.decisions)
        decisions = load_decisions(args.decisions, pending, allow_missing=True)
        if args.status:
            _status(pending, decisions, output)
            return 0
        reviewer = (args.reviewer or "").strip()
        if not reviewer:
            raise TopicReviewError("reviewer required")
        existing = {row["id"]: row for row in decisions}
        reviewed = 0
        for row in pending:
            if args.limit is not None and reviewed >= args.limit:
                break
            old = existing.get(row["id"])
            if old and not args.replace_decision:
                continue
            if old and old["reviewer"] != reviewer:
                continue
            _show_for_human(row, output)
            choice = _ask("Decision [approve/rewrite/reject/skip]: ", input_fn)
            if choice is None:
                return 0
            choice = choice.strip().casefold()
            if choice == "skip":
                reviewed += 1; continue
            if choice not in DECISIONS:
                reviewed += 1; continue
            confirmations = [_bool("Source verified [yes/no]: ", input_fn), _bool("Publication time verified [yes/no]: ", input_fn), _bool("Summary grounded [yes/no]: ", input_fn), _bool("Broadcast line verified [yes/no]: ", input_fn), _bool("Expiry verified [yes/no]: ", input_fn)]
            if any(value is None for value in confirmations):
                return 0
            notes = ""
            if choice in {"rewrite", "reject"}:
                note = _ask("Notes (required): ", input_fn)
                if note is None:
                    return 0
                notes = note.strip()
                if not notes:
                    reviewed += 1; continue
            if choice == "approve" and not all(confirmations):
                reviewed += 1; continue
            decision = {
                "id": row["id"], "record_sha256": record_sha256(row), "decision": choice,
                "source_verified": confirmations[0], "published_at_verified": confirmations[1],
                "summary_grounded": confirmations[2], "broadcast_line_verified": confirmations[3],
                "expires_at_verified": confirmations[4], "notes": notes, "reviewer": reviewer,
                "reviewed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            }
            # Do not create or replace a sidecar row until the exact shared
            # contract accepts every generated reviewer and notes field.
            decision = validate_decision(decision, {row["id"]: row})
            if old is None:
                decisions.append(decision)
            else:
                decisions[decisions.index(old)] = decision
            existing[row["id"]] = decision
            atomic_write_jsonl(decisions_path, decisions)
            reviewed += 1
        _status(pending, decisions, output)
        return 0
    except (OSError, RuntimeError, TopicReviewError, ValueError):
        print('{"status":"rejected"}', file=error)
        return 2


if __name__ == "__main__":
    raise SystemExit(run_cli())
