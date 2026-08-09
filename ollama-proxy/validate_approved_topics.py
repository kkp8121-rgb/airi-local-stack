"""Offline startup gate for a configured AIRI topic board.

This command intentionally performs only local filesystem and JSON validation.
It never contacts a model or service and never modifies the board.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from topic_board import load_approved_topics


RUNTIME_ROOT = Path(__file__).resolve().parent / "runtime"


def _inside_runtime_regular_file(board_path: str | Path) -> Path:
    raw = str(board_path).strip()
    if not raw or raw.startswith(("\\\\", "//")):
        raise ValueError("invalid board")
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise ValueError("invalid board")
    resolved = candidate.resolve(strict=True)
    runtime_root = RUNTIME_ROOT.resolve(strict=False)
    try:
        resolved.relative_to(runtime_root)
    except ValueError as exc:
        raise ValueError("invalid board") from exc
    if not resolved.is_file():
        raise ValueError("invalid board")
    return resolved


def validate(board_path: str | Path) -> int:
    """Return the live approved item count or raise for any failed gate."""
    resolved = _inside_runtime_regular_file(board_path)
    items = load_approved_topics(resolved)
    if not items:
        raise ValueError("no live approved topics")
    return len(items)


def _emit(status: str, live_approved_count: int) -> None:
    # Keep stdout suitable for logs and safe to expose: no board text, IDs,
    # filenames, paths, exception details, or timestamps.
    print(json.dumps({"status": status, "live_approved_count": live_approved_count}, separators=(",", ":")))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--board")
    try:
        args, unknown = parser.parse_known_args(argv)
        if unknown or not args.board:
            raise ValueError("missing board")
        count = validate(args.board)
    except (OSError, RuntimeError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        _emit("rejected", 0)
        return 1
    # Validation confirms that already-approved records are runnable.  It
    # never creates or implies a human approval decision.
    _emit("valid", count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
