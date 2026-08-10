#!/usr/bin/env python3
"""Read-only, candidate-only readiness check for externally supplied fixtures."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import TextIO

from verify_airi_style_dataset import load_jsonl_bytes, validate_fixture_rows


ENABLE_FLAG = "--audit-airi-style-fixture-readiness"
STAGE = "fixture-readiness"
MAX_FIXTURE_BYTES = 16 * 1024 * 1024


class ReadinessError(ValueError):
    """A deliberately detail-free refusal of a fixture candidate."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ReadinessError("invalid command line")


def _is_reparse(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse and attributes & reparse)


def _absolute_without_resolving(path: Path) -> Path:
    expanded = path.expanduser()
    return expanded if expanded.is_absolute() else Path.cwd() / expanded


def _assert_no_reparse_chain(path: Path, label: str) -> Path:
    """Reject network, symlink, and junction/reparse components without resolving."""
    candidate = _absolute_without_resolving(path)
    text = str(candidate)
    if text.startswith(("\\\\", "//")):
        raise ReadinessError(label)
    if os.name == "nt" and candidate.drive:
        try:
            if ctypes.windll.kernel32.GetDriveTypeW(f"{candidate.drive}\\") == 4:
                raise ReadinessError(label)
        except AttributeError as exc:
            raise ReadinessError(label) from exc
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            # The final missing component is still rejected below; continuing
            # lets us avoid resolving or following any future component.
            continue
        except OSError as exc:
            raise ReadinessError(label) from exc
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise ReadinessError(label)
    return candidate


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size,
            getattr(info, "st_mtime_ns", 0), getattr(info, "st_ctime_ns", 0))


def _read_regular_snapshot(path: Path, label: str) -> bytes:
    """Capture one bounded stable local file through a checked descriptor."""
    candidate = _assert_no_reparse_chain(path, label)
    try:
        before = os.lstat(candidate)
        if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode) or _is_reparse(before):
            raise ReadinessError(label)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(candidate, flags)
    except (OSError, ReadinessError) as exc:
        raise ReadinessError(label) from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _identity(opened)[:2] != _identity(before)[:2]:
            raise ReadinessError(label)
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            descriptor = -1
            chunks=[]; total=0
            while True:
                block=handle.read(1024*1024)
                if not block: break
                total += len(block)
                if total > MAX_FIXTURE_BYTES: raise ReadinessError(label)
                chunks.append(block)
            after=os.fstat(handle.fileno())
        if _identity(after) != _identity(opened):
            raise ReadinessError(label)
        return b"".join(chunks)
    except OSError as exc:
        raise ReadinessError(label) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _emit(output: TextIO, *, status: str, c0_cases: int = 0, s1_cases: int = 0,
          c0_sha256: str | None = None, s1_sha256: str | None = None) -> None:
    # This is intentionally the complete public interface: no paths, fixture
    # text, IDs, groups, or human authority claims can escape this audit.
    print(json.dumps({
        "c0_cases": c0_cases,
        "c0_sha256": c0_sha256,
        "s1_cases": s1_cases,
        "s1_sha256": s1_sha256,
        "stage": STAGE,
        "status": status,
    }, sort_keys=True, separators=(",", ":")), file=output)


def _audit(c0_path: Path, s1_path: Path) -> tuple[int, int, str, str]:
    # Each path is opened exactly once. All counts, validation, and hashes use
    # those immutable byte snapshots; no verifier path loader is called here.
    c0 = _assert_no_reparse_chain(c0_path, "C0 fixture")
    s1 = _assert_no_reparse_chain(s1_path, "S1 fixture")
    if os.path.normcase(os.path.normpath(str(c0))) == os.path.normcase(os.path.normpath(str(s1))):
        raise ReadinessError("fixtures")
    c0_data = _read_regular_snapshot(c0, "C0 fixture")
    s1_data = _read_regular_snapshot(s1, "S1 fixture")
    c0_rows = load_jsonl_bytes(c0_data, "C0 fixture")
    s1_rows = load_jsonl_bytes(s1_data, "S1 fixture")
    c0_rows, c0_ids, c0_groups, c0_prompts = validate_fixture_rows(c0_rows, "C0")
    s1_rows, s1_ids, s1_groups, s1_prompts = validate_fixture_rows(s1_rows, "S1")
    if c0_ids & s1_ids or c0_groups & s1_groups or c0_prompts & s1_prompts:
        raise ReadinessError("fixtures")
    return (len(c0_rows), len(s1_rows), hashlib.sha256(c0_data).hexdigest(),
            hashlib.sha256(s1_data).hexdigest())


def run_cli(argv: list[str] | None = None, *, output: TextIO | None = None) -> int:
    """Run a non-authorizing fixture check; the default branch is inert."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    stream = sys.stdout if output is None else output
    # Do this before argparse, Path construction, or any filesystem access.
    if ENABLE_FLAG not in arguments:
        _emit(stream, status="disabled")
        return 0
    if arguments.count(ENABLE_FLAG) != 1:
        _emit(stream, status="not-ready")
        return 2
    parser = _Parser(add_help=False)
    parser.add_argument(ENABLE_FLAG, action="store_true")
    parser.add_argument("--c0-fixture", type=Path)
    parser.add_argument("--s1-fixture", type=Path)
    try:
        args = parser.parse_args(arguments)
        if not args.c0_fixture or not args.s1_fixture:
            raise ReadinessError("invalid command line")
        c0_cases, s1_cases, c0_hash, s1_hash = _audit(args.c0_fixture, args.s1_fixture)
    except Exception:
        # The public audit deliberately never surface parser/loader details or
        # fixture content, including unexpected decoding failures.
        _emit(stream, status="not-ready")
        return 2
    _emit(stream, status="candidate", c0_cases=c0_cases, s1_cases=s1_cases,
          c0_sha256=c0_hash, s1_sha256=s1_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
