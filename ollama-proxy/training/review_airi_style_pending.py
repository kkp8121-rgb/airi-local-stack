#!/usr/bin/env python3
"""Offline interactive human review for a pending AIRI-style JSONL sidecar only."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TextIO

DECISION_FIELDS = {"id", "decision", "vtuber_voice", "counselor_tone", "safety_truth", "notes", "reviewer", "reviewed_at"}
DECISIONS = {"approve", "rewrite", "reject"}
Input = Callable[[str], str]

class ReviewError(ValueError):
    pass

def _regular_input(path: Path) -> Path:
    path = path.expanduser().resolve()
    if not path.is_file() or path.is_symlink(): raise ReviewError("pending input must be an existing regular file")
    return path

def _output_path(path: Path, pending: Path) -> Path:
    path = path.expanduser().resolve()
    if path == pending: raise ReviewError("decision output must differ from pending input")
    if not path.parent.is_dir(): raise ReviewError("decision output parent directory must already exist")
    if path.exists() and (not path.is_file() or path.is_symlink()): raise ReviewError("decision output must be a regular file")
    return path

def _read_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    try: lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc: raise ReviewError(f"could not read {label}") from exc
    rows = []
    for line in lines:
        if not line.strip(): continue
        try: row = json.loads(line)
        except json.JSONDecodeError as exc: raise ReviewError(f"{label} contains invalid JSONL") from exc
        if not isinstance(row, dict): raise ReviewError(f"{label} contains an invalid row")
        rows.append(row)
    return rows

def _load_pending(path: Path) -> list[dict[str, Any]]:
    rows, seen = _read_jsonl(path, "pending input"), set()
    for row in rows:
        if (not isinstance(row.get("id"), str) or not row["id"].strip() or row["id"] in seen or any(not isinstance(row.get(key), str) for key in ("prompt", "answer", "category", "split"))): raise ReviewError("pending input has invalid review fields")
        seen.add(row["id"])
    return rows

def _load_decisions(path: Path, pending_ids: set[str]) -> list[dict[str, Any]]:
    if not path.exists(): return []
    rows, seen = _read_jsonl(path, "decision sidecar"), set()
    for row in rows:
        if set(row) != DECISION_FIELDS or row.get("id") not in pending_ids or row["id"] in seen: raise ReviewError("decision sidecar has invalid or duplicate decisions")
        if row.get("decision") not in DECISIONS or not all(type(row.get(key)) is bool for key in ("vtuber_voice", "counselor_tone", "safety_truth")): raise ReviewError("decision sidecar has invalid decision fields")
        if not isinstance(row.get("notes"), str) or not isinstance(row.get("reviewer"), str) or not row["reviewer"].strip() or not _rfc3339_utc(row.get("reviewed_at")): raise ReviewError("decision sidecar has invalid reviewer fields")
        if row["decision"] in {"rewrite", "reject"} and not row["notes"].strip(): raise ReviewError("decision sidecar has missing decision notes")
        if row["decision"] == "approve" and not (row["vtuber_voice"] and not row["counselor_tone"] and row["safety_truth"]): raise ReviewError("decision sidecar has invalid approval confirmations")
        seen.add(row["id"])
    return rows

def _rfc3339_utc(value: Any) -> bool:
    if not isinstance(value, str) or "T" not in value or not value.endswith("Z"):
        return False
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").utcoffset() == timezone.utc.utcoffset(None)
    except ValueError:
        return False

def _atomic_write(path: Path, rows: list[dict[str, Any]]) -> None:
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temp = Path(handle.name)
            for row in rows: handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists(): temp.unlink()

def _ask(prompt: str, input_fn: Input) -> str | None:
    try: return input_fn(prompt)
    except (EOFError, KeyboardInterrupt): return None

def _boolean(prompt: str, input_fn: Input, output: TextIO) -> bool | None:
    while True:
        value = _ask(prompt, input_fn)
        if value is None: return None
        if value.strip().casefold() in {"y", "yes", "true"}: return True
        if value.strip().casefold() in {"n", "no", "false"}: return False
        print("Enter yes or no.", file=output)

def _show(row: dict[str, Any], output: TextIO) -> None:
    print("\n--- pending record ---", file=output)
    for key in ("category", "split", "prompt", "answer"): print(f"{key}: {row[key]}", file=output)

def _status(pending: list[dict[str, Any]], decisions: list[dict[str, Any]], output: TextIO) -> None:
    counts = Counter(row["decision"] for row in decisions)
    print(json.dumps({"pending_count": len(pending), "decision_count": len(decisions), "remaining_count": len(pending)-len(decisions), "decisions": dict(sorted(counts.items()))}, sort_keys=True), file=output)

def run_cli(argv: list[str] | None = None, *, input_fn: Input = input, output: TextIO = sys.stdout, error: TextIO = sys.stderr) -> int:
    parser = argparse.ArgumentParser(description="Local human review; writes only a decision sidecar.")
    parser.add_argument("--pending", type=Path, required=True); parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--reviewer", help="Required human identity; never inferred.")
    parser.add_argument("--replace-decision", action="store_true"); parser.add_argument("--status", action="store_true")
    parser.add_argument("--limit", type=int, default=None); args = parser.parse_args(argv)
    try:
        if args.limit is not None and args.limit < 0: raise ReviewError("limit must be zero or greater")
        pending_path = _regular_input(args.pending); decisions_path = _output_path(args.decisions, pending_path)
        pending = _load_pending(pending_path); decisions = _load_decisions(decisions_path, {row["id"] for row in pending})
        if args.status: _status(pending, decisions, output); return 0
        reviewer = args.reviewer if args.reviewer is not None else _ask("Reviewer identity (required): ", input_fn)
        if reviewer is None: print("Review ended; no decision recorded.", file=output); return 0
        reviewer = reviewer.strip()
        if not reviewer: raise ReviewError("reviewer identity is required")
        existing, seen_count, changed = {row["id"]: row for row in decisions}, 0, False
        for row in pending:
            if args.limit is not None and seen_count >= args.limit: break
            prior = existing.get(row["id"])
            if prior is not None and not args.replace_decision: continue
            if prior is not None and prior["reviewer"] != reviewer:
                print("Existing decision belongs to a different reviewer; not replaced.", file=output); continue
            _show(row, output); choice = _ask("Decision [approve/rewrite/reject/skip]: ", input_fn)
            if choice is None: print("Review ended; completed decisions were preserved.", file=output); return 0
            choice = choice.strip().casefold()
            if choice == "skip": seen_count += 1; continue
            if choice not in DECISIONS: print("Decision not recorded.", file=output); seen_count += 1; continue
            voice = _boolean("VTuber voice confirmed [yes/no]: ", input_fn, output)
            tone = _boolean("Counselor tone present [yes/no]: ", input_fn, output)
            safety = _boolean("Safety and truth confirmed [yes/no]: ", input_fn, output)
            if None in (voice, tone, safety): print("Review ended; completed decisions were preserved.", file=output); return 0
            notes = ""
            if choice in {"rewrite", "reject"}:
                value = _ask("Notes (required): ", input_fn)
                if value is None: print("Review ended; completed decisions were preserved.", file=output); return 0
                notes = value.strip()
                if not notes: print("Decision not recorded: notes are required.", file=output); seen_count += 1; continue
            if choice == "approve" and not (voice is True and tone is False and safety is True): print("Decision not recorded: approval confirmations were not satisfied.", file=output); seen_count += 1; continue
            decision = {"id": row["id"], "decision": choice, "vtuber_voice": voice, "counselor_tone": tone, "safety_truth": safety, "notes": notes, "reviewer": reviewer, "reviewed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}
            if prior is None: decisions.append(decision)
            else: decisions[decisions.index(prior)] = decision
            existing[row["id"]] = decision; _atomic_write(decisions_path, decisions); changed = True; seen_count += 1
        print("Decision sidecar updated." if changed else "No decision recorded.", file=output)
        return 0
    except ReviewError as exc:
        print(f"REJECTED: {exc}", file=error); return 2

def main() -> int: return run_cli()
if __name__ == "__main__": raise SystemExit(main())
