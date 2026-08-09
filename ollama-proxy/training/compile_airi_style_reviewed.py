#!/usr/bin/env python3
"""Offline, fail-closed promotion of a fully reviewed AIRI pending queue."""
from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import secrets
import shutil
import stat
import sys
import tempfile
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


PROMOTION_CONTRACT_VERSION = "airi-reviewed-promotion/v1"
ENVELOPE_FIELDS = {
    "schema_version", "promotion_contract_version", "policy_version",
    "pending_dataset_sha256", "decision_sidecar_sha256", "approved_decisions_sha256",
    "c0_fixture_sha256", "s1_fixture_sha256", "pending_record_count",
    "human_approved", "approved_by", "approved_at", "reviewer_provenance",
}


class PromotionError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise PromotionError("invalid command line")


def _is_reparse(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse and attributes & reparse)


def _absolute_without_resolving(path: Path) -> Path:
    expanded = path.expanduser()
    return expanded if expanded.is_absolute() else Path.cwd() / expanded


def _assert_no_reparse_chain(path: Path, label: str) -> None:
    """Reject symlinks and Windows junction/reparse points already on disk."""
    path_text = str(path)
    if not path.is_absolute() or path_text.startswith(("\\\\", "//")):
        raise PromotionError(label)
    if os.name == "nt" and path.drive and ctypes.windll.kernel32.GetDriveTypeW(f"{path.drive}\\") == 4:
        raise PromotionError(label)
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise PromotionError(label) from exc
        if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise PromotionError(label)


def _read_regular_snapshot(path: Path, label: str) -> bytes:
    """Read one stable regular-file snapshot through a checked file handle."""
    _assert_no_reparse_chain(path, label)
    try:
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode) or _is_reparse(before):
            raise PromotionError(label)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
    except (OSError, PromotionError) as exc:
        raise PromotionError(label) from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise PromotionError(label)
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            descriptor = -1
            data = handle.read()
            after = os.fstat(handle.fileno())
        if (
            (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
            or after.st_size != opened.st_size
            or getattr(after, "st_mtime_ns", None) != getattr(opened, "st_mtime_ns", None)
        ):
            raise PromotionError(label)
        return data
    except OSError as exc:
        raise PromotionError(label) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


class _OutputLock:
    """Cooperative, ownership-checked single writer for one output directory."""

    def __init__(self, output: Path):
        self.path = output.parent / f".{output.name}.promotion.lock"
        self.token = secrets.token_hex(24).encode("ascii")
        self.descriptor: int | None = None
        self.identity: tuple[int, int] | None = None

    def _same_identity(self) -> bool:
        if self.identity is None:
            return False
        try:
            info = os.lstat(self.path)
        except OSError:
            return False
        return not stat.S_ISLNK(info.st_mode) and not _is_reparse(info) and (info.st_dev, info.st_ino) == self.identity

    def _remove_partial_owned_lock(self) -> None:
        if self._same_identity():
            try:
                os.unlink(self.path)
            except OSError:
                pass

    def __enter__(self) -> "_OutputLock":
        _assert_no_reparse_chain(self.path.parent, "output lock")
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
        descriptor: int | None = None
        try:
            descriptor = os.open(self.path, flags, 0o600)
            info = os.fstat(descriptor)
            self.identity = (info.st_dev, info.st_ino)
            self.descriptor = descriptor
            os.write(descriptor, self.token)
            os.fsync(descriptor)
            return self
        except BaseException:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            self.descriptor = None
            self._remove_partial_owned_lock()
            raise

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        descriptor = self.descriptor
        self.descriptor = None
        if descriptor is not None:
            os.close(descriptor)
        if not self._same_identity():
            raise PromotionError("output lock")
        try:
            lock_bytes = self.path.read_bytes()
        except BaseException:
            self._remove_partial_owned_lock()
            raise
        if lock_bytes != self.token:
            raise PromotionError("output lock")
        try:
            os.unlink(self.path)
        except BaseException:
            self._remove_partial_owned_lock()
            raise


def _compact(payload: dict[str, Any], output: TextIO) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), file=output)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _future(value: str, label: str) -> None:
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PromotionError(label) from exc
    if instant.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise PromotionError(label)


def _regular_input(path: Path, label: str, local_path: Any) -> Path:
    candidate = _absolute_without_resolving(path)
    _assert_no_reparse_chain(candidate, label)
    try:
        resolved = local_path(candidate, label)
    except Exception as exc:
        raise PromotionError(label) from exc
    if not resolved.is_file() or resolved.is_symlink():
        raise PromotionError(label)
    _assert_no_reparse_chain(resolved, label)
    return resolved


def _output_path(path: Path, local_path: Any) -> Path:
    candidate = _absolute_without_resolving(path)
    _assert_no_reparse_chain(candidate.parent, "output directory")
    if candidate.parent.is_symlink() or not candidate.parent.is_dir():
        raise PromotionError("output directory")
    try:
        output = local_path(candidate, "output directory")
    except Exception as exc:
        raise PromotionError("output directory") from exc
    parent = output.parent
    if not parent.is_dir() or parent.is_symlink() or output.exists() or output.is_symlink():
        raise PromotionError("output directory")
    _assert_no_reparse_chain(parent, "output directory")
    return output


def _parent_identity(parent: Path) -> tuple[int, int]:
    if not parent.is_dir() or parent.is_symlink():
        raise PromotionError("output parent")
    info = parent.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise PromotionError("output parent")
    return info.st_dev, info.st_ino


def _load_envelope(data: bytes, *, _strict: Any, _identity: Any, _rfc: Any,
                   _reviewers: Any, _privacy: Any, policy_version: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
        envelope = _strict(value, ENVELOPE_FIELDS, "promotion approval")
    except Exception as exc:
        raise PromotionError("governance envelope") from exc
    if type(envelope["schema_version"]) is not int or envelope["schema_version"] != 1:
        raise PromotionError("governance envelope")
    if envelope["promotion_contract_version"] != PROMOTION_CONTRACT_VERSION or envelope["policy_version"] != policy_version:
        raise PromotionError("governance envelope")
    if type(envelope["pending_record_count"]) is not int or envelope["pending_record_count"] != 200:
        raise PromotionError("governance envelope")
    if envelope["human_approved"] is not True:
        raise PromotionError("governance envelope")
    for key in ("pending_dataset_sha256", "decision_sidecar_sha256", "approved_decisions_sha256", "c0_fixture_sha256", "s1_fixture_sha256"):
        if not isinstance(envelope[key], str) or len(envelope[key]) != 64 or any(c not in "0123456789abcdef" for c in envelope[key]):
            raise PromotionError("governance envelope")
    try:
        _identity(envelope["approved_by"], "promotion approval.approved_by")
        _rfc(envelope["approved_at"], "promotion approval.approved_at")
        _future(envelope["approved_at"], "governance envelope")
        _reviewers(envelope["reviewer_provenance"])
        _privacy(envelope, "promotion approval")
    except Exception as exc:
        raise PromotionError("governance envelope") from exc
    return envelope


def _write(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _publish_no_replace(source: Path, destination: Path) -> None:
    """Atomically publish a directory without replacing an existing target."""
    if source.parent != destination.parent:
        raise PromotionError("output directory")
    try:
        if os.name == "nt":
            # MoveFileEx without MOVEFILE_REPLACE_EXISTING is atomic and fails if
            # the destination appears after the caller's final preflight.
            os.rename(source, destination)
            return
        if sys.platform.startswith("linux"):
            library = ctypes.CDLL(None, use_errno=True)
            renameat2 = library.renameat2
            renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            renameat2.restype = ctypes.c_int
            if renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1) == 0:
                return
            number = ctypes.get_errno()
            if number in (errno.EEXIST, errno.ENOTEMPTY):
                raise PromotionError("output directory")
            raise OSError(number, os.strerror(number))
        if sys.platform == "darwin":
            library = ctypes.CDLL(None, use_errno=True)
            renamex_np = library.renamex_np
            renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
            renamex_np.restype = ctypes.c_int
            if renamex_np(os.fsencode(source), os.fsencode(destination), 4) == 0:
                return
            number = ctypes.get_errno()
            if number in (errno.EEXIST, errno.ENOTEMPTY):
                raise PromotionError("output directory")
            raise OSError(number, os.strerror(number))
        raise PromotionError("unsupported no-replace publication platform")
    except FileExistsError as exc:
        raise PromotionError("output directory") from exc
    except AttributeError as exc:
        raise PromotionError("no-replace publication unavailable") from exc


def _compile(args: argparse.Namespace) -> None:
    # Keep production validation imports inside the opt-in path: the default mode
    # must be inert even if optional validation dependencies are unavailable.
    from validate_airi_style_pending import record_sha256, validate_decisions, validate_pending_dataset
    from verify_airi_style_dataset import (
        CATEGORY_TAXONOMY, POLICY_VERSION, _identity, _privacy, _reviewers, _rfc,
        _strict, load_jsonl, local_path, verify_reviewed_dataset,
    )

    pending = _regular_input(args.pending, "pending dataset", local_path)
    decisions = _regular_input(args.decisions, "decision sidecar", local_path)
    envelope_path = _regular_input(args.governance_envelope, "governance envelope", local_path)
    c0 = _regular_input(args.c0_fixture, "C0 fixture", local_path)
    s1 = _regular_input(args.s1_fixture, "S1 fixture", local_path)
    inputs = (pending, decisions, envelope_path, c0, s1)
    if len(set(inputs)) != len(inputs):
        raise PromotionError("inputs")
    output = _output_path(args.output_dir, local_path)
    if output in inputs:
        raise PromotionError("output directory")
    parent_identity = _parent_identity(output.parent)

    pending_bytes = _read_regular_snapshot(pending, "pending dataset")
    decision_bytes = _read_regular_snapshot(decisions, "decision sidecar")
    envelope_bytes = _read_regular_snapshot(envelope_path, "governance envelope")
    c0_bytes = _read_regular_snapshot(c0, "C0 fixture")
    s1_bytes = _read_regular_snapshot(s1, "S1 fixture")
    envelope = _load_envelope(envelope_bytes, _strict=_strict,
                              _identity=_identity, _rfc=_rfc, _reviewers=_reviewers,
                              _privacy=_privacy, policy_version=POLICY_VERSION)
    bindings = {
        "pending_dataset_sha256": hashlib.sha256(pending_bytes).hexdigest(),
        "decision_sidecar_sha256": hashlib.sha256(decision_bytes).hexdigest(),
        "c0_fixture_sha256": hashlib.sha256(c0_bytes).hexdigest(),
        "s1_fixture_sha256": hashlib.sha256(s1_bytes).hexdigest(),
    }
    if any(envelope[key] != value for key, value in bindings.items()):
        raise PromotionError("governance envelope")
    stage: Path | None = None
    with _OutputLock(output), ExitStack() as cleanup:
        if _parent_identity(output.parent) != parent_identity or output.exists() or output.is_symlink():
            raise PromotionError("output directory")
        stage = Path(tempfile.mkdtemp(prefix="." + output.name + ".stage-", dir=output.parent))
        cleanup.callback(shutil.rmtree, stage, ignore_errors=True)
        source_pending = stage / ".source-pending.jsonl"
        source_decisions = stage / ".source-decisions.jsonl"
        _write(source_pending, pending_bytes)
        _write(source_decisions, decision_bytes)
        _write(stage / "c0-fixture.jsonl", c0_bytes)
        _write(stage / "s1-fixture.jsonl", s1_bytes)
        _write(stage / "promotion-approval.json", envelope_bytes)

        # Every subsequent decision and dataset field is derived from these
        # exact captured bytes, never from a second read of mutable inputs.
        validate_pending_dataset(source_pending)
        rows = load_jsonl(source_pending, "pending dataset")
        if len(rows) != 200:
            raise PromotionError("pending dataset")
        by_id = {row["id"]: row for row in rows}
        validate_decisions(source_decisions, by_id)
        decision_rows = load_jsonl(source_decisions, "decision sidecar")
        if len(decision_rows) != len(rows) or {item["id"] for item in decision_rows} != set(by_id):
            raise PromotionError("decision sidecar")
        provenance_ids, _ = _reviewers(envelope["reviewer_provenance"])
        provenance_by_fold = {value.casefold(): value for value in provenance_ids}
        if len(provenance_by_fold) != len(provenance_ids):
            raise PromotionError("governance envelope")
        approved_by = envelope["approved_by"]
        if approved_by not in provenance_ids:
            raise PromotionError("governance envelope")
        seen_reviewers: set[str] = set()
        decisions_by_id: dict[str, dict[str, Any]] = {}
        approval_bindings = []
        for decision in decision_rows:
            if decision["decision"] != "approve" or not (decision["vtuber_voice"] is True and decision["counselor_tone"] is False and decision["safety_truth"] is True):
                raise PromotionError("decision sidecar")
            try:
                _identity(decision["reviewer"], "decision reviewer")
                _rfc(decision["reviewed_at"], "decision timestamp")
                _future(decision["reviewed_at"], "decision timestamp")
            except Exception as exc:
                raise PromotionError("decision sidecar") from exc
            folded = decision["reviewer"].casefold()
            if folded not in provenance_by_fold or decision["reviewer"] != provenance_by_fold[folded]:
                raise PromotionError("decision sidecar")
            seen_reviewers.add(folded)
            decisions_by_id[decision["id"]] = decision
            approval_bindings.append({key: decision[key] for key in ("id", "record_sha256", "reviewer", "reviewed_at")})
        if seen_reviewers != set(provenance_by_fold):
            raise PromotionError("governance envelope")
        approval_bindings.sort(key=lambda item: item["id"])
        if envelope["approved_decisions_sha256"] != hashlib.sha256(_canonical(approval_bindings)).hexdigest():
            raise PromotionError("governance envelope")

        transformed: list[dict[str, Any]] = []
        ids: set[str] = set(); groups: set[str] = set()
        for row in rows:
            digest = record_sha256(row)
            item = {
                "id": "style-" + digest[:32], "split": row["split"], "category": row["category"],
                "prompt": row["prompt"], "answer": row["answer"],
                "partition": {"tier": "S1", "group": "reviewed-" + digest[-32:]},
                "review": {"status": "approved", "reviewer": decisions_by_id[row["id"]]["reviewer"], "approved_at": decisions_by_id[row["id"]]["reviewed_at"]},
                "provenance": {"synthetic": True, "source": "human-reviewed-synthetic-v3"},
                "training_eligible": True,
            }
            if item["id"] in ids or item["partition"]["group"] in groups:
                raise PromotionError("derived collision")
            ids.add(item["id"]); groups.add(item["partition"]["group"]); transformed.append(item)
        dataset_bytes = b"".join(_canonical(row) + b"\n" for row in transformed)
        dataset_hash = hashlib.sha256(dataset_bytes).hexdigest()
        manifest = {
            "schema_version": 3, "policy_version": POLICY_VERSION, "dataset_sha256": dataset_hash,
            "human_approved": True, "approved_by": approved_by, "approved_at": envelope["approved_at"],
            "reviewed_record_count": 200, "categories": list(CATEGORY_TAXONOMY),
            "reviewer_provenance": envelope["reviewer_provenance"],
        }
        _write(stage / "reviewed-dataset.jsonl", dataset_bytes)
        _write(stage / "review-manifest.json", _canonical(manifest) + b"\n")
        result = verify_reviewed_dataset(stage / "reviewed-dataset.jsonl", stage / "review-manifest.json", stage / "c0-fixture.jsonl", stage / "s1-fixture.jsonl")
        if result.dataset_sha256 != dataset_hash or result.c0_fixture_sha256 != envelope["c0_fixture_sha256"] or result.s1_fixture_sha256 != envelope["s1_fixture_sha256"]:
            raise PromotionError("staged verification")
        source_pending.unlink()
        source_decisions.unlink()
        _assert_no_reparse_chain(output.parent, "output directory")
        if _parent_identity(output.parent) != parent_identity or output.exists() or output.is_symlink():
            raise PromotionError("output directory")
        _publish_no_replace(stage, output)
        stage = None


def run_cli(argv: list[str] | None = None, *, output: TextIO = sys.stdout, error: TextIO = sys.stderr) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if "--promote-reviewed-style" not in values:
        _compact({"status": "disabled", "record_count": 0}, output)
        return 0
    parser = _Parser(add_help=False)
    parser.add_argument("--promote-reviewed-style", action="store_true")
    parser.add_argument("--pending", type=Path, required=True); parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--governance-envelope", type=Path, required=True); parser.add_argument("--c0-fixture", type=Path, required=True)
    parser.add_argument("--s1-fixture", type=Path, required=True); parser.add_argument("--output-dir", type=Path, required=True)
    try:
        if any(values.count(flag) != 1 for flag in ("--promote-reviewed-style", "--pending", "--decisions", "--governance-envelope", "--c0-fixture", "--s1-fixture", "--output-dir")):
            raise PromotionError("invalid command line")
        args = parser.parse_args(values)
        _compile(args)
    except (PromotionError, OSError, ValueError):
        _compact({"status": "rejected", "record_count": 0}, output)
        return 2
    _compact({"status": "compiled", "record_count": 200}, output)
    return 0


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
