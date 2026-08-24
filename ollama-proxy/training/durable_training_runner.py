"""Agent-independent supervisor for durable AIRI behavior training.

The supervisor persists only content-free process and artifact evidence.  It
never stores the trainer command line or environment; their canonical SHA-256
identities are enough to reject duplicate or stale-process recovery.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Mapping, Sequence


RUN_STATE_SCHEMA = "airi.behavior-durable-run.v1"
RUN_STATE_ANCHOR_SCHEMA = "airi.behavior-durable-run-anchor.v1"
PROGRESS_SCHEMA = "airi.behavior-training-progress.v1"
CHECKPOINT_INDEX_SCHEMA = "airi.behavior-checkpoint-index.v1"
TRANSACTION_CHECKPOINT_INDEX_SCHEMA = "airi.behavior-checkpoint-index.v2"
CHECKPOINT_EVENT_SCHEMA = "airi.behavior-checkpoint-event.v2"
PAUSE_ACK_SCHEMA = "airi.behavior-pause-ack.v1"
RESUME_ACCEPTED_SCHEMA = "airi.behavior-resume-accepted.v1"
CHECKPOINT_VERIFICATION_SCHEMA = "airi.behavior-checkpoint-verification.v1"
SAFE_PAUSE_EXIT_CODE = 75
HEX64 = re.compile(r"^[0-9a-f]{64}$")
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
STATUSES = {
    "starting", "running", "pause-requested", "checkpointing",
    "paused-safe", "resuming", "complete", "failed", "interrupted",
}
SENSITIVE_FLAG = re.compile(r"(?i)(?:password|passwd|secret|token|api[-_]?key)")


class DurableRunnerError(RuntimeError):
    """Fail-closed runner contract violation."""


class CheckpointIntegrityError(DurableRunnerError):
    """A checkpoint is structurally incomplete or byte-corrupt."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def checkpoint_canonical_bytes(value: object) -> bytes:
    """Match behavior_training_checkpoint.py's byte-exact JSON contract."""

    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(_read_regular_file_snapshot(path, "pinned file"))


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_fsynced(path: Path, payload: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def publish_new_bytes(path: Path, payload: bytes, label: str) -> None:
    """Durably publish *payload* once; a concurrent creator always wins."""
    parent = validate_local_path(path.parent, f"{label} parent")
    if not parent.is_dir():
        raise DurableRunnerError(f"{label} target is not a fresh local path")
    if os.path.lexists(path):
        raise DurableRunnerError(f"{label} target already exists")
    stage = parent / f".{path.name}.tmp.{uuid.uuid4().hex}"
    try:
        _write_fsynced(stage, payload)
        if os.name == "nt":
            import ctypes  # noqa: PLC0415
            move_file = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
            move_file.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
            move_file.restype = ctypes.c_int
            # WRITE_THROUGH only: REPLACE_EXISTING would destroy a competitor.
            if not move_file(str(stage), str(path), 0x8):
                raise FileExistsError(ctypes.get_last_error(), "fresh publication failed")
        else:
            os.link(stage, path)
            _fsync_directory(parent)
            stage.unlink()
            _fsync_directory(parent)
        if path.read_bytes() != payload:
            raise DurableRunnerError(f"{label} publication verification failed")
    except FileExistsError as exc:
        raise DurableRunnerError(f"{label} target appeared during publication") from exc
    finally:
        with contextlib.suppress(FileNotFoundError):
            stage.unlink()


def _replace_write_through(source: Path, target: Path) -> None:
    """Atomically replace a same-volume target and request durable metadata."""

    if source.resolve().anchor.lower() != target.resolve().anchor.lower():
        raise DurableRunnerError("atomic replacement must remain on one volume")
    if os.name != "nt":
        os.replace(source, target)
        _fsync_directory(target.parent)
        return
    import ctypes  # noqa: PLC0415

    move_file = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
    move_file.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
    move_file.restype = ctypes.c_int
    movefile_replace_existing = 0x1
    movefile_write_through = 0x8
    if not move_file(str(source), str(target),
                     movefile_replace_existing | movefile_write_through):
        error = ctypes.get_last_error()
        raise DurableRunnerError(
            f"write-through atomic replacement failed with Windows error {error}")


def atomic_write_json(path: Path, value: Mapping[str, Any], *, keep_previous: bool) -> None:
    """Flush and atomically replace a JSON receipt, retaining the old receipt."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_bytes(value)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    _write_fsynced(temporary, payload)
    try:
        if keep_previous and path.is_file():
            previous = path.with_name(path.stem + ".prev" + path.suffix)
            previous_tmp = previous.with_name(f".{previous.name}.{uuid.uuid4().hex}.tmp")
            _write_fsynced(previous_tmp, path.read_bytes())
            _replace_write_through(previous_tmp, previous)
        _replace_write_through(temporary, path)
        if path.read_bytes() != payload:
            raise DurableRunnerError(f"atomic JSON verification failed: {path.name}")
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_read_regular_file_snapshot(path, "JSON receipt").decode("utf-8"))
    except (DurableRunnerError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DurableRunnerError(f"invalid JSON receipt: {path.name}") from exc
    if not isinstance(value, dict):
        raise DurableRunnerError(f"JSON receipt must be an object: {path.name}")
    return value


def validate_run_state(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version", "revision", "run_id", "status", "created_at_utc",
        "updated_at_utc", "runner", "trainer", "inputs", "command",
        "progress", "heartbeat", "checkpoint", "logs", "outputs", "terminal",
    }
    if set(value) != required:
        raise DurableRunnerError("run-state keys do not match the v1 schema")
    if value["schema_version"] != RUN_STATE_SCHEMA:
        raise DurableRunnerError("run-state schema mismatch")
    if not isinstance(value["revision"], int) or value["revision"] < 0:
        raise DurableRunnerError("run-state revision is invalid")
    if not isinstance(value["run_id"], str) or not RUN_ID.fullmatch(value["run_id"]):
        raise DurableRunnerError("run-state run_id is invalid")
    if value["status"] not in STATUSES:
        raise DurableRunnerError("run-state status is invalid")
    for key in ("runner", "inputs", "command", "progress", "heartbeat", "logs", "outputs"):
        if not isinstance(value[key], dict):
            raise DurableRunnerError(f"run-state {key} must be an object")
    if value["trainer"] is not None and not isinstance(value["trainer"], dict):
        raise DurableRunnerError("run-state trainer must be null or an object")
    process_keys = {
        "pid", "creation_time_utc", "executable_path_sha256", "command_line_sha256"}
    for label in ("runner", "trainer"):
        record = value[label]
        if record is None:
            continue
        if (set(record) != process_keys
                or not isinstance(record["pid"], int)
                or isinstance(record["pid"], bool)
                or record["pid"] <= 0
                or not isinstance(record["creation_time_utc"], str)
                or not record["creation_time_utc"]
                or not isinstance(record["executable_path_sha256"], str)
                or not HEX64.fullmatch(record["executable_path_sha256"])
                or not isinstance(record["command_line_sha256"], str)
                or not HEX64.fullmatch(record["command_line_sha256"])):
            raise DurableRunnerError(f"run-state {label} process identity is invalid")
    if value["checkpoint"] is not None and not isinstance(value["checkpoint"], dict):
        raise DurableRunnerError("run-state checkpoint must be null or an object")
    if value["terminal"] is not None and not isinstance(value["terminal"], dict):
        raise DurableRunnerError("run-state terminal must be null or an object")
    terminal_statuses = {"paused-safe", "complete", "failed", "interrupted"}
    if value["status"] in terminal_statuses and value["terminal"] is None:
        raise DurableRunnerError("terminal run-state is missing its receipt")
    if value["status"] not in terminal_statuses and value["terminal"] is not None:
        raise DurableRunnerError("nonterminal run-state has a terminal receipt")
    if value["status"] == "paused-safe":
        terminal = value["terminal"]
        verification = terminal.get("checkpoint_verification") if terminal else None
        if (value["trainer"] is None
                or set(terminal) != {
                    "exit_code", "reason", "at_utc", "checkpoint_verification"}
                or terminal["exit_code"] != SAFE_PAUSE_EXIT_CODE
                or terminal["reason"] != "safe-optimizer-boundary"
                or not isinstance(terminal["at_utc"], str)
                or not terminal["at_utc"]
                or not isinstance(verification, dict)
                or set(verification) != {
                    "schema_version", "checkpoint_relative_path",
                    "checkpoint_manifest_sha256", "checkpoint_payload_sha256",
                    "checkpoint_payload_bytes", "canonical_pins_sha256"}
                or verification["schema_version"] != CHECKPOINT_VERIFICATION_SCHEMA
                or not isinstance(verification["checkpoint_relative_path"], str)
                or not re.fullmatch(
                    r"checkpoint-[0-9]{8}", verification["checkpoint_relative_path"])
                or not isinstance(verification["checkpoint_payload_bytes"], int)
                or isinstance(verification["checkpoint_payload_bytes"], bool)
                or verification["checkpoint_payload_bytes"] < 1
                or any(not isinstance(verification[key], str)
                       or not HEX64.fullmatch(verification[key]) for key in (
                           "checkpoint_manifest_sha256", "checkpoint_payload_sha256",
                           "canonical_pins_sha256"))):
            raise DurableRunnerError("paused-safe checkpoint verification receipt is invalid")
    return dict(value)


def _quarantine_file(run_dir: Path, path: Path, label: str) -> Path:
    payload = _read_regular_file_snapshot(path, f"{label} quarantine source")
    quarantine = run_dir / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    target = quarantine / (
        f"{label}.corrupt.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}."
        f"{sha256_bytes(payload)[:12]}.{uuid.uuid4().hex}.json"
    )
    _replace_write_through(path, target)
    _fsync_directory(quarantine)
    return target


def _load_run_state_anchor(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "run-state.anchor.json"
    if not path.is_file():
        return None
    anchor = _load_json(path)
    if (set(anchor) != {"schema_version", "run_id", "current", "previous"}
            or anchor["schema_version"] != RUN_STATE_ANCHOR_SCHEMA
            or not isinstance(anchor["run_id"], str) or not RUN_ID.fullmatch(anchor["run_id"])):
        raise DurableRunnerError("run-state anchor schema mismatch")
    for name in ("current", "previous"):
        receipt = anchor[name]
        if receipt is None:
            continue
        if (not isinstance(receipt, dict) or set(receipt) != {"sha256", "revision"}
                or not isinstance(receipt["sha256"], str) or not HEX64.fullmatch(receipt["sha256"])
                or not isinstance(receipt["revision"], int) or isinstance(receipt["revision"], bool)
                or receipt["revision"] < 0):
            raise DurableRunnerError("run-state anchor receipt is invalid")
    if anchor["current"] is None:
        raise DurableRunnerError("run-state anchor current receipt is invalid")
    return anchor


def _state_receipt_if_matches(path: Path, anchor: Mapping[str, Any], receipt: Any) -> bool:
    if not path.is_file() or not isinstance(receipt, dict):
        return False
    try:
        state = validate_run_state(_load_json(path))
        return (state["run_id"] == anchor["run_id"]
                and state["revision"] == receipt["revision"]
                and sha256_file(path) == receipt["sha256"])
    except DurableRunnerError:
        return False


def load_run_state_with_previous(run_dir: Path) -> tuple[dict[str, Any] | None, str | None]:
    current = run_dir / "run-state.json"
    previous = run_dir / "run-state.prev.json"
    anchor_path = run_dir / "run-state.anchor.json"
    anchor = _load_run_state_anchor(run_dir)
    if current.is_file():
        try:
            state = validate_run_state(_load_json(current))
            if anchor is not None:
                if not _state_receipt_if_matches(current, anchor, anchor["current"]):
                    raise DurableRunnerError("run-state current is not anchor-authorized")
            return state, "current"
        except DurableRunnerError:
            _quarantine_file(run_dir, current, "run-state")
            if anchor is not None and previous.is_file():
                candidate = validate_run_state(_load_json(previous))
                if (_state_receipt_if_matches(previous, anchor, anchor["current"])
                        and candidate["status"] not in {"complete", "paused-safe"}):
                    return candidate, "anchor-authorized-predecessor"
            return None, None
    if previous.is_file() and anchor is not None:
        # A predecessor is only a durability companion to an existing current
        # receipt.  Atomic publication never intentionally leaves current
        # absent, so no predecessor can authorize launch or resume alone.
        candidate = validate_run_state(_load_json(previous))
        if (_state_receipt_if_matches(previous, anchor, anchor["current"])
                and candidate["status"] not in {"complete", "paused-safe"}):
            return candidate, "anchor-authorized-predecessor"
        return None, None
    return None, None


def _reject_remote_or_reparse_path(value: Path, label: str) -> Path:
    raw = str(value)
    if (raw.startswith(("\\\\", "//"))
            or re.match(r"^[A-Za-z][A-Za-z0-9+.\-]+:[\\/]", raw)):
        raise DurableRunnerError(f"{label} must be a local filesystem path")
    absolute = value.expanduser().absolute()
    existing = absolute
    while not os.path.lexists(existing) and existing != existing.parent:
        existing = existing.parent
    for candidate in (existing, *existing.parents):
        try:
            attributes = os.lstat(candidate).st_file_attributes
        except (AttributeError, OSError):
            attributes = 0
        if (candidate.is_symlink()
                or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise DurableRunnerError(f"{label} cannot traverse a reparse point")
    if os.name == "nt":
        import ctypes  # noqa: PLC0415

        drive_type = ctypes.WinDLL("kernel32").GetDriveTypeW(str(absolute.anchor))
        if drive_type != 3:
            raise DurableRunnerError(f"{label} must use a local fixed volume")
    resolved = absolute.resolve()
    if resolved == Path(resolved.anchor):
        raise DurableRunnerError(f"{label} cannot be a volume root")
    return resolved


def validate_local_run_dir(value: Path, *, create: bool = True) -> Path:
    resolved = _reject_remote_or_reparse_path(value, "run directory")
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def validate_local_path(value: Path, label: str) -> Path:
    return _reject_remote_or_reparse_path(value, label)


def _read_regular_file_snapshot(path: Path, label: str,
                                error_type: type[DurableRunnerError] = DurableRunnerError) -> bytes:
    """Read one local regular-file handle; never validate a pathname then reopen it."""

    resolved = validate_local_path(path, label)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if os.name == "nt":
        import ctypes  # noqa: PLC0415
        import msvcrt  # noqa: PLC0415
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel.CreateFileW
        create_file.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                ctypes.c_void_p]
        create_file.restype = ctypes.c_void_p
        handle = create_file(str(resolved), 0x80000000, 0x1, None, 3,
                             0x00200000, None)  # OPEN_EXISTING | OPEN_REPARSE_POINT
        if handle == ctypes.c_void_p(-1).value:
            raise error_type(f"{label} is missing or cannot be opened safely")
        class _FileTime(ctypes.Structure):
            _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]

        class _Info(ctypes.Structure):
            _fields_ = [("attributes", ctypes.c_uint32), ("created", _FileTime),
                       ("accessed", _FileTime), ("written", _FileTime),
                       ("volume_serial", ctypes.c_uint32), ("size_high", ctypes.c_uint32),
                       ("size_low", ctypes.c_uint32), ("links", ctypes.c_uint32),
                       ("index_high", ctypes.c_uint32), ("index_low", ctypes.c_uint32)]
        info = _Info()
        kernel.GetFileInformationByHandle.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Info)]
        kernel.GetFileInformationByHandle.restype = ctypes.c_int
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = ctypes.c_int
        if not kernel.GetFileInformationByHandle(handle, ctypes.byref(info)):
            kernel.CloseHandle(handle)
            raise error_type(f"{label} handle cannot be classified")
        if info.attributes & 0x400:
            kernel.CloseHandle(handle)
            raise error_type(f"{label} must be a local regular file")
        try:
            descriptor = msvcrt.open_osfhandle(handle, flags)
        except OSError as exc:
            kernel.CloseHandle(handle)
            raise error_type(f"{label} handle cannot be adopted safely") from exc
        try:
            with os.fdopen(descriptor, "rb") as stream:
                return stream.read()
        except OSError as exc:
            raise error_type(f"{label} is missing or unreadable") from exc
    try:
        descriptor = os.open(resolved, flags | nofollow)
    except OSError as exc:
        raise error_type(f"{label} is missing or cannot be opened safely") from exc
    try:
        metadata = os.fstat(descriptor)
        attributes = getattr(metadata, "st_file_attributes", 0)
        if (not stat.S_ISREG(metadata.st_mode)
                or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise error_type(f"{label} must be a local regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            return stream.read()
    finally:
        os.close(descriptor)


class _HeldRegularInput:
    """A no-follow immutable-input handle kept open for the child lifetime."""

    def __init__(self, path: Path, label: str, descriptor: int, identity: tuple[int, ...],
                 payload: bytes) -> None:
        self.path = path
        self.label = label
        self.descriptor = descriptor
        self.identity = identity
        self.payload = payload
        self.sha256 = sha256_bytes(payload)

    def close(self) -> None:
        if self.descriptor >= 0:
            os.close(self.descriptor)
            self.descriptor = -1

    def verify_held_bytes(self) -> None:
        try:
            os.lseek(self.descriptor, 0, os.SEEK_SET)
            chunks: list[bytes] = []
            while True:
                chunk = os.read(self.descriptor, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
        except OSError as exc:
            raise DurableRunnerError(f"{self.label} held handle is unreadable") from exc
        payload = b"".join(chunks)
        if len(payload) != len(self.payload) or sha256_bytes(payload) != self.sha256:
            raise DurableRunnerError(f"{self.label} changed while held for training")

    def verify_path_still_matches(self) -> None:
        """Detect POSIX rename/symlink swaps; Windows locks prevent those changes."""
        try:
            current = _open_held_regular_input(self.path, self.label)
        except DurableRunnerError as exc:
            raise DurableRunnerError(f"{self.label} path changed while held for training") from exc
        try:
            if (current.identity != self.identity or len(current.payload) != len(self.payload)
                    or current.sha256 != self.sha256):
                raise DurableRunnerError(f"{self.label} path changed while held for training")
        finally:
            current.close()

    def verify_unchanged(self) -> None:
        self.verify_held_bytes()
        self.verify_path_still_matches()


def _input_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (int(metadata.st_dev), int(metadata.st_ino), int(metadata.st_size),
            int(metadata.st_mtime_ns))


def _open_held_regular_input(path: Path, label: str) -> _HeldRegularInput:
    """Open a file once with no-follow semantics and retain a read-only share lock.

    On Windows CreateFileW permits only subsequent readers, so writes, deletes and
    replacements are denied until ``close``.  POSIX uses O_NOFOLLOW plus fstat;
    the post-exit identity check closes the rename gap POSIX intentionally permits.
    """
    resolved = validate_local_path(path, label)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if os.name == "nt":
        import ctypes  # noqa: PLC0415
        import msvcrt  # noqa: PLC0415
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel.CreateFileW
        create_file.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                ctypes.c_void_p]
        create_file.restype = ctypes.c_void_p
        # GENERIC_READ, FILE_SHARE_READ, OPEN_EXISTING, OPEN_REPARSE_POINT.
        handle = create_file(str(resolved), 0x80000000, 0x1, None, 3, 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise DurableRunnerError(f"{label} is missing or cannot be held safely")
        try:
            descriptor = msvcrt.open_osfhandle(handle, flags)
        except OSError as exc:
            kernel.CloseHandle(handle)
            raise DurableRunnerError(f"{label} handle cannot be adopted safely") from exc
    else:
        try:
            descriptor = os.open(resolved, flags | getattr(os, "O_NOFOLLOW", 0))
        except OSError as exc:
            raise DurableRunnerError(f"{label} is missing or cannot be held safely") from exc
    try:
        metadata = os.fstat(descriptor)
        attributes = getattr(metadata, "st_file_attributes", 0)
        if (not stat.S_ISREG(metadata.st_mode)
                or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise DurableRunnerError(f"{label} must be a local regular file")
        payload_parts: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            payload_parts.append(chunk)
        os.lseek(descriptor, 0, os.SEEK_SET)
        return _HeldRegularInput(resolved, label, descriptor, _input_identity(metadata),
                                 b"".join(payload_parts))
    except BaseException:
        os.close(descriptor)
        raise


def _hold_training_inputs(dataset: Path, dataset_sha256: str, model_dir: Path,
                          inventory: list[dict[str, Any]] | None,
                          initial_adapter: Mapping[str, Any] | None = None) -> list[_HeldRegularInput]:
    """Acquire all v2 loader inputs atomically enough to leave no launch gap."""
    held: list[_HeldRegularInput] = []
    try:
        dataset_handle = _open_held_regular_input(dataset, "dataset")
        held.append(dataset_handle)
        if dataset_handle.sha256 != dataset_sha256:
            raise DurableRunnerError("dataset changed after manifest publication")
        if inventory is not None:
            for row in inventory:
                handle = _open_held_regular_input(model_dir / row["path"],
                                                  "pinned model inventory file")
                held.append(handle)
                if len(handle.payload) != row["bytes"] or handle.sha256 != row["sha256"]:
                    raise DurableRunnerError("model inventory changed after manifest publication")
        if initial_adapter is not None:
            adapter_dir = Path(initial_adapter["directory"])
            for row in [*initial_adapter["files"], initial_adapter["artifact_manifest"]]:
                handle = _open_held_regular_input(adapter_dir / row["path"], "pinned init adapter file")
                held.append(handle)
                if len(handle.payload) != row["bytes"] or handle.sha256 != row["sha256"]:
                    raise DurableRunnerError("init adapter changed after manifest publication")
        return held
    except BaseException:
        for handle in reversed(held):
            handle.close()
        raise


def _verify_held_training_inputs(handles: Sequence[_HeldRegularInput]) -> None:
    for handle in handles:
        handle.verify_unchanged()


def _read_checkpoint_snapshot(path: Path, label: str) -> bytes:
    try:
        return _read_regular_file_snapshot(path, label)
    except DurableRunnerError as exc:
        raise CheckpointIntegrityError(str(exc)) from exc


def validate_input_manifest(path: Path, expected_sha256: str) -> tuple[Path, str]:
    """Return a fixed-local regular manifest only when its exact bytes are pinned."""

    if not isinstance(expected_sha256, str) or not HEX64.fullmatch(expected_sha256):
        raise DurableRunnerError("input manifest SHA-256 is required and invalid")
    resolved = validate_local_path(path, "input manifest")
    raw = _read_regular_file_snapshot(resolved, "input manifest")
    actual_sha256 = sha256_bytes(raw)
    if actual_sha256 != expected_sha256:
        raise DurableRunnerError("input manifest SHA-256 does not match its bytes")
    return resolved, actual_sha256


def _manifest_training_config(arguments: Sequence[str], checkpoint_interval: int) -> dict[str, Any]:
    fields: tuple[tuple[str, str, type], ...] = (
        ("mode", "--mode", str), ("seed", "--seed", int),
        ("lora_r", "--lora-r", int), ("lora_alpha", "--lora-alpha", int),
        ("lora_dropout", "--lora-dropout", float),
        ("learning_rate", "--learning-rate", float),
        ("max_steps", "--max-steps", int), ("batch_size", "--batch-size", int),
        ("gradient_accumulation", "--gradient-accumulation", int),
        ("max_seq_len", "--max-seq-len", int),
    )
    config: dict[str, Any] = {"checkpoint_every_optimizer_steps": checkpoint_interval,
                              "deterministic_validation": "--deterministic-validation" in arguments}
    for name, flag, converter in fields:
        value = _argument_value(arguments, flag, required=True)
        try:
            config[name] = converter(value or "")
        except ValueError as exc:
            raise DurableRunnerError(f"training configuration value is invalid: {flag}") from exc
    init = _init_adapter_arguments(arguments)
    config["init_mode"] = "adapter-weights-only" if init is not None else "fresh-lora"
    return _validate_manifest_training_config(config)


def _init_adapter_arguments(arguments: Sequence[str]) -> dict[str, str] | None:
    flags = ("--init-adapter-dir", "--init-adapter-model-sha256",
             "--init-adapter-config-sha256", "--init-adapter-artifact-manifest-sha256")
    values = {flag: _argument_value(arguments, flag) for flag in flags}
    if not any(value is not None for value in values.values()):
        return None
    if any(value is None for value in values.values()):
        raise DurableRunnerError("init adapter trainer flags must be supplied together")
    for flag in flags[1:]:
        if not HEX64.fullmatch(values[flag] or ""):
            raise DurableRunnerError(f"init adapter SHA-256 is invalid: {flag}")
    return {"directory": values[flags[0]] or "", "model_sha256": values[flags[1]] or "",
            "config_sha256": values[flags[2]] or "",
            "artifact_manifest_sha256": values[flags[3]] or ""}


def _validate_manifest_training_config(value: Any) -> dict[str, Any]:
    """Validate the full, typed config that an input manifest commits to."""

    required_v2 = {
        "mode", "seed", "lora_r", "lora_alpha", "lora_dropout",
        "learning_rate", "max_steps", "batch_size", "gradient_accumulation",
        "max_seq_len", "checkpoint_every_optimizer_steps",
        "deterministic_validation",
    }
    required = required_v2 | {"init_mode"}
    if (not isinstance(value, dict)
            or (set(value) != required_v2 and set(value) != required)):
        raise DurableRunnerError("input manifest training configuration schema mismatch")
    if value["mode"] not in {"cuda-qlora", "cpu-smoke"}:
        raise DurableRunnerError("input manifest training mode is invalid")
    for key in ("seed", "lora_r", "lora_alpha", "max_steps", "batch_size",
                "gradient_accumulation", "max_seq_len",
                "checkpoint_every_optimizer_steps"):
        if (not isinstance(value[key], int) or isinstance(value[key], bool)
                or value[key] <= 0):
            raise DurableRunnerError(f"input manifest training configuration is invalid: {key}")
    for key in ("lora_dropout", "learning_rate"):
        if not isinstance(value[key], float) or not math.isfinite(value[key]):
            raise DurableRunnerError(f"input manifest training configuration is non-finite: {key}")
    if not 0 <= value["lora_dropout"] < 1 or value["learning_rate"] <= 0:
        raise DurableRunnerError("input manifest dropout/learning-rate contract failure")
    if not isinstance(value["deterministic_validation"], bool):
        raise DurableRunnerError("input manifest deterministic validation is invalid")
    normalized = dict(value)
    normalized.setdefault("init_mode", "fresh-lora")
    if normalized["init_mode"] not in {"fresh-lora", "adapter-weights-only"}:
        raise DurableRunnerError("input manifest init mode is invalid")
    return normalized


def _validate_initial_adapter(manifest_value: Any, trainer_args: Sequence[str]) -> dict[str, Any] | None:
    requested = _init_adapter_arguments(trainer_args)
    if manifest_value is None:
        if requested is not None:
            raise DurableRunnerError("input manifest initial adapter mismatch")
        return None
    required = {"run_id", "model_sha256", "config_sha256", "artifact_manifest_sha256", "files"}
    if not isinstance(manifest_value, dict) or set(manifest_value) != required or requested is None:
        raise DurableRunnerError("input manifest initial adapter schema mismatch")
    if not isinstance(manifest_value["run_id"], str) or not manifest_value["run_id"]:
        raise DurableRunnerError("input manifest initial adapter run_id is invalid")
    for key in ("model_sha256", "config_sha256", "artifact_manifest_sha256"):
        if (not HEX64.fullmatch(str(manifest_value[key]))
                or manifest_value[key] != requested[key]):
            raise DurableRunnerError("input manifest initial adapter pin mismatch")
    directory = validate_local_path(Path(requested["directory"]), "init adapter directory")
    if not directory.is_dir():
        raise DurableRunnerError("init adapter directory is missing")
    artifact_path = directory / "artifact-manifest.json"
    raw = _read_regular_file_snapshot(artifact_path, "init adapter artifact manifest")
    if sha256_bytes(raw) != manifest_value["artifact_manifest_sha256"]:
        raise DurableRunnerError("init adapter artifact manifest SHA-256 mismatch")
    try:
        artifact = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DurableRunnerError("init adapter artifact manifest is invalid") from exc
    if raw != canonical_bytes(artifact):
        raise DurableRunnerError("init adapter artifact manifest is not canonical")
    if (set(artifact) != {"schema_version", "run_id", "pins", "files"}
            or artifact.get("schema_version") != "airi.behavior-adapter-artifact.v1"
            or artifact.get("run_id") != manifest_value["run_id"]
            or not isinstance(artifact.get("pins"), dict)
            or not HEX64.fullmatch(str(artifact["pins"].get("model_weight_sha256", "")))
            or artifact["pins"]["model_weight_sha256"] != _argument_value(trainer_args, "--model-sha256", required=True)):
        raise DurableRunnerError("init adapter artifact schema/pin mismatch")
    files = manifest_value["files"]
    if not isinstance(files, list) or not files or artifact.get("files") != files:
        raise DurableRunnerError("init adapter declared inventory mismatch")
    seen: set[str] = set()
    for row in files:
        if (not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}
                or not isinstance(row["path"], str) or not row["path"] or row["path"] in seen
                or Path(row["path"]).is_absolute() or ".." in Path(row["path"]).parts
                or not isinstance(row["bytes"], int) or row["bytes"] < 0
                or not HEX64.fullmatch(str(row["sha256"]))):
            raise DurableRunnerError("init adapter inventory row is invalid")
        seen.add(row["path"])
        payload = _read_regular_file_snapshot(directory / row["path"], "init adapter file")
        if len(payload) != row["bytes"] or sha256_bytes(payload) != row["sha256"]:
            raise DurableRunnerError("init adapter inventory does not match disk")
    _validate_closed_model_inventory(directory, [
        *files,
        {"path": "artifact-manifest.json", "bytes": len(raw),
         "sha256": sha256_bytes(raw)},
    ])
    for path, key in (("adapter_model.safetensors", "model_sha256"),
                      ("adapter_config.json", "config_sha256")):
        row = next((item for item in files if item["path"] == path), None)
        if row is None or row["sha256"] != manifest_value[key]:
            raise DurableRunnerError("init adapter required file pin mismatch")
    return {"directory": str(directory), "files": files,
            "artifact_manifest": {"path": "artifact-manifest.json", "bytes": len(raw),
                                  "sha256": sha256_bytes(raw)}}


def _validate_closed_model_inventory(model_dir: Path, inventory: list[dict[str, Any]]) -> None:
    """Require a manifest to enumerate every entry a local loader may see."""
    root = validate_local_path(model_dir, "model directory")
    if not root.is_dir():
        raise DurableRunnerError("model directory is missing")
    declared = {row["path"]: {"bytes": row["bytes"], "sha256": row["sha256"]}
                for row in inventory}
    declared_directories = {
        parent.as_posix()
        for relative in declared
        for parent in Path(relative).parents
        if parent != Path(".")
    }
    actual: dict[str, dict[str, Any]] = {}
    actual_directories: set[str] = set()
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as scan:
                entries = sorted(scan, key=lambda entry: entry.name, reverse=True)
        except OSError as exc:
            raise DurableRunnerError("model inventory directory cannot be inspected") from exc
        for entry in entries:
            candidate = Path(entry.path)
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise DurableRunnerError("model inventory entry cannot be inspected") from exc
            attributes = getattr(metadata, "st_file_attributes", 0)
            if (entry.is_symlink()
                    or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
                raise DurableRunnerError("model inventory cannot contain links or reparse points")
            if stat.S_ISDIR(metadata.st_mode):
                actual_directories.add(candidate.relative_to(root).as_posix())
                pending.append(candidate)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise DurableRunnerError("model inventory cannot contain special entries")
            relative = candidate.relative_to(root).as_posix()
            data = _read_regular_file_snapshot(candidate, "model inventory entry")
            actual[relative] = {"bytes": len(data), "sha256": sha256_bytes(data)}
    if actual != declared or actual_directories != declared_directories:
        raise DurableRunnerError("input manifest model inventory is not a closed exact file set")


def validate_input_manifest_content(path: Path, expected_sha256: str,
                                    trainer_args: Sequence[str], trainer_sha256: str,
                                    dataset_sha256: str, model_sha256: str,
                                    checkpoint_interval: int,
                                    helper_sha256: str | None = None) -> dict[str, Any]:
    """Require canonical schema and bind every immutable launch input to it."""

    # One immutable observation: never hash then reopen an attacker-replaced path.
    resolved = validate_local_path(path, "input manifest")
    raw = _read_regular_file_snapshot(resolved, "input manifest")
    actual_sha256 = sha256_bytes(raw)
    if actual_sha256 != expected_sha256:
        raise DurableRunnerError("input manifest SHA-256 does not match its bytes")
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DurableRunnerError("input manifest is not valid UTF-8 JSON") from exc
    try:
        canonical_manifest = canonical_bytes(manifest)
    except (TypeError, ValueError) as exc:
        raise DurableRunnerError("input manifest contains non-canonical values") from exc
    if raw != canonical_manifest:
        raise DurableRunnerError("input manifest is not canonical JSON")
    required_v2 = {"schema_version", "dataset_sha256", "model_weight_sha256",
                   "trainer_source_sha256", "training_config", "training_config_sha256",
                   "checkpoint_helper_source_sha256", "model_inventory"}
    required_v3 = required_v2 | {"initial_adapter"}
    schema = manifest.get("schema_version")
    if ((schema == "airi.behavior-input-manifest.v2" and set(manifest) != required_v2)
            or (schema == "airi.behavior-input-manifest.v3" and set(manifest) != required_v3)
            or schema not in {"airi.behavior-input-manifest.v2", "airi.behavior-input-manifest.v3"}):
        raise DurableRunnerError("input manifest schema mismatch")
    config = _manifest_training_config(trainer_args, checkpoint_interval)
    raw_manifest_config = manifest["training_config"]
    required_config_v2 = {
        "mode", "seed", "lora_r", "lora_alpha", "lora_dropout",
        "learning_rate", "max_steps", "batch_size", "gradient_accumulation",
        "max_seq_len", "checkpoint_every_optimizer_steps",
        "deterministic_validation",
    }
    required_config = (required_config_v2 | {"init_mode"}
                       if schema == "airi.behavior-input-manifest.v3"
                       else required_config_v2)
    if not isinstance(raw_manifest_config, dict) or set(raw_manifest_config) != required_config:
        raise DurableRunnerError("input manifest training configuration schema mismatch")
    manifest_config = _validate_manifest_training_config(raw_manifest_config)
    if (manifest_config != config
            or not isinstance(manifest["training_config_sha256"], str)
            or not HEX64.fullmatch(manifest["training_config_sha256"])
            or manifest["training_config_sha256"] != sha256_bytes(canonical_bytes(raw_manifest_config))):
        raise DurableRunnerError("input manifest training configuration mismatch")
    expected = {"dataset_sha256": dataset_sha256, "model_weight_sha256": model_sha256,
                "trainer_source_sha256": trainer_sha256}
    for key, value in expected.items():
        if not isinstance(manifest[key], str) or manifest[key] != value or not HEX64.fullmatch(value):
            raise DurableRunnerError(f"input manifest {key} mismatch")
    if not helper_sha256 or manifest["checkpoint_helper_source_sha256"] != helper_sha256:
        raise DurableRunnerError("input manifest checkpoint helper mismatch")
    inventory = manifest["model_inventory"]
    if not isinstance(inventory, list) or not inventory:
        raise DurableRunnerError("input manifest model inventory is invalid")
    seen: set[str] = set()
    for row in inventory:
        if (not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}
                or not isinstance(row["path"], str) or row["path"] in seen
                or Path(row["path"]).is_absolute() or ".." in Path(row["path"]).parts
                or not isinstance(row["bytes"], int) or not HEX64.fullmatch(str(row["sha256"]))):
            raise DurableRunnerError("input manifest model inventory row is invalid")
        seen.add(row["path"])
    # The builder validates a manifest before it has a launch command;
    # only a real runner invocation can compare the declaration to disk.
    model_dir_value = _argument_value(trainer_args, "--model-dir")
    if model_dir_value is not None:
        _validate_closed_model_inventory(Path(model_dir_value), inventory)
    initial_adapter = None
    if schema == "airi.behavior-input-manifest.v3":
        initial_adapter = _validate_initial_adapter(manifest["initial_adapter"], trainer_args)
        if ((manifest_config["init_mode"] == "fresh-lora" and initial_adapter is not None)
                or (manifest_config["init_mode"] == "adapter-weights-only" and initial_adapter is None)):
            raise DurableRunnerError("input manifest initial adapter mode mismatch")
    elif _init_adapter_arguments(trainer_args) is not None:
        raise DurableRunnerError("v2 input manifest cannot initialize an adapter")
    return {"path": str(resolved), "sha256": actual_sha256,
            "training_config_sha256": manifest["training_config_sha256"],
            "model_inventory": inventory, "initial_adapter": initial_adapter,
            "schema_version": schema, "init_mode": manifest_config["init_mode"]}


def _relative_inside(root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise DurableRunnerError("runtime receipt path escapes run directory") from exc
    return relative.as_posix()


def _argument_value(arguments: Sequence[str], flag: str, *, required: bool = False) -> str | None:
    positions = [index for index, value in enumerate(arguments) if value == flag]
    if len(positions) > 1:
        raise DurableRunnerError(f"duplicate trainer argument: {flag}")
    if not positions:
        if required:
            raise DurableRunnerError(f"missing trainer argument: {flag}")
        return None
    index = positions[0]
    if index + 1 >= len(arguments) or arguments[index + 1].startswith("--"):
        raise DurableRunnerError(f"trainer argument has no value: {flag}")
    return arguments[index + 1]


def _ensure_argument(arguments: list[str], flag: str, value: str) -> None:
    existing = _argument_value(arguments, flag)
    if existing is None:
        arguments.extend((flag, value))
    elif existing != value:
        raise DurableRunnerError(f"trainer argument conflicts with runner: {flag}")


def _remove_argument(arguments: list[str], flag: str) -> None:
    value = _argument_value(arguments, flag)
    if value is None:
        return
    index = arguments.index(flag)
    del arguments[index:index + 2]


def _validate_trainer_arguments(arguments: Sequence[str]) -> None:
    for argument in arguments:
        if argument.startswith("--") and SENSITIVE_FLAG.search(argument):
            raise DurableRunnerError("secret-bearing trainer flags are forbidden")


def _process_snapshot(pid: int) -> dict[str, Any] | None:
    if pid <= 0:
        return None
    if os.name == "nt":
        script = (
            f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}' "
            "-ErrorAction SilentlyContinue; if($null -eq $p){exit 3};"
            "$c=$p.CreationDate.ToUniversalTime().ToString('o');"
            "[pscustomobject]@{pid=[int]$p.ProcessId;creation_time_utc=$c;"
            "executable_path=[string]$p.ExecutablePath;command_line=[string]$p.CommandLine}"
            "|ConvertTo-Json -Compress"
        )
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if completed.returncode != 0:
            return None
        try:
            value = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None
    proc = Path("/proc") / str(pid)
    if not proc.exists():
        return None
    try:
        command = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8")
        executable = str((proc / "exe").resolve())
        created = str((proc / "stat").read_text(encoding="utf-8").split()[21])
    except (OSError, UnicodeDecodeError, IndexError):
        return None
    return {"pid": pid, "creation_time_utc": created,
            "executable_path": executable, "command_line": command}


def _process_record(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "pid": int(snapshot["pid"]),
        "creation_time_utc": str(snapshot["creation_time_utc"]),
        "executable_path_sha256": sha256_bytes(
            str(snapshot.get("executable_path", "")).lower().encode("utf-8")),
        "command_line_sha256": sha256_bytes(
            str(snapshot.get("command_line", "")).encode("utf-8")),
    }


def process_matches(record: Mapping[str, Any] | None) -> bool:
    if not record:
        return False
    try:
        snapshot = _process_snapshot(int(record["pid"]))
    except (KeyError, TypeError, ValueError):
        return False
    if snapshot is None:
        return False
    return _process_record(snapshot) == dict(record)


def _validate_checkpoint_manifest(checkpoint_dir: Path,
                                  manifest: Mapping[str, Any]) -> None:
    required = {"schema_version", "generation", "run_id", "payload", "pins"}
    if set(manifest) != required or manifest["schema_version"] != 1:
        raise CheckpointIntegrityError("checkpoint manifest schema mismatch")
    if (manifest["generation"] != checkpoint_dir.name
            or not isinstance(manifest["run_id"], str)
            or not isinstance(manifest["pins"], dict)):
        raise CheckpointIntegrityError("checkpoint manifest identity is invalid")
    payload = manifest["payload"]
    if (not isinstance(payload, dict)
            or set(payload) != {"name", "bytes", "sha256"}
            or payload["name"] != "state.pt"
            or not isinstance(payload["bytes"], int)
            or payload["bytes"] < 1
            or not isinstance(payload["sha256"], str)
            or not HEX64.fullmatch(payload["sha256"])):
        raise CheckpointIntegrityError("checkpoint payload metadata is invalid")
    path = checkpoint_dir / payload["name"]
    data = _read_checkpoint_snapshot(path, "checkpoint payload")
    if len(data) != payload["bytes"] or sha256_bytes(data) != payload["sha256"]:
        raise CheckpointIntegrityError("checkpoint payload integrity mismatch")


def validate_checkpoint_reference(run_dir: Path, reference: Mapping[str, Any]) -> dict[str, Any]:
    if set(reference) != {"relative_path", "manifest_sha256"}:
        raise CheckpointIntegrityError("checkpoint reference keys are invalid")
    relative = reference["relative_path"]
    digest = reference["manifest_sha256"]
    if (not isinstance(relative, str) or Path(relative).name != relative
            or not re.fullmatch(r"checkpoint-[0-9]{8}", relative)
            or not isinstance(digest, str)
            or not HEX64.fullmatch(digest)):
        raise CheckpointIntegrityError("checkpoint reference is invalid")
    checkpoint_dir = (run_dir / "checkpoints" / relative).resolve()
    _relative_inside(run_dir / "checkpoints", checkpoint_dir)
    manifest_path = checkpoint_dir / "manifest.json"
    manifest_bytes = _read_checkpoint_snapshot(manifest_path, "checkpoint manifest")
    if sha256_bytes(manifest_bytes) != digest:
        raise CheckpointIntegrityError("checkpoint manifest integrity mismatch")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckpointIntegrityError("checkpoint manifest JSON is invalid") from exc
    if not isinstance(manifest, dict):
        raise CheckpointIntegrityError("checkpoint manifest must be an object")
    try:
        expected_manifest = checkpoint_canonical_bytes(manifest)
    except (TypeError, ValueError) as exc:
        raise CheckpointIntegrityError("checkpoint manifest values are invalid") from exc
    if manifest_bytes != expected_manifest:
        raise CheckpointIntegrityError("checkpoint manifest is not canonical")
    _validate_checkpoint_manifest(checkpoint_dir, manifest)
    return {"relative_path": relative, "manifest_sha256": digest,
            "absolute_path": str(checkpoint_dir), "manifest": manifest}


def _quarantine_checkpoint(run_dir: Path, reference: Mapping[str, Any]) -> None:
    relative = reference.get("relative_path")
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        return
    source = run_dir / "checkpoints" / relative
    if not source.exists():
        return
    quarantine = run_dir / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    target = quarantine / f"{source.name}.corrupt.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    _replace_write_through(source, target)


def _checkpoint_event(run_dir: Path, reference: Mapping[str, Any], run_id: str) -> dict[str, Any]:
    """Validate the immutable event that a v2 index commits, byte for byte."""
    event_path = run_dir / str(reference["event_relative_path"])
    raw = _read_checkpoint_snapshot(event_path, "checkpoint event")
    if sha256_bytes(raw) != reference["event_sha256"]:
        raise CheckpointIntegrityError("checkpoint event hash mismatch")
    try:
        event = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckpointIntegrityError("checkpoint event JSON is invalid") from exc
    if not isinstance(event, dict) or raw != checkpoint_canonical_bytes(event):
        raise CheckpointIntegrityError("checkpoint event is not canonical")
    required = {
        "schema_version", "run_id", "generation", "reason", "microsteps_completed",
        "optimizer_steps", "pending_microbatches", "training_elapsed_ns",
        "checkpoint_payload_progress", "checkpoint_manifest_sha256",
        "checkpoint_payload_sha256", "pins_sha256", "previous_event_sha256",
        "previous_index_sha256", "publish_started_at_utc", "checkpoint_durable_at_utc",
        "publish_elapsed_ns",
    }
    if (set(event) != required or event["schema_version"] != CHECKPOINT_EVENT_SCHEMA
            or event["run_id"] != run_id or event["generation"] != reference["relative_path"]
            or event["checkpoint_manifest_sha256"] != reference["manifest_sha256"]
            or event["reason"] not in {"interval", "safe-pause", "epoch-tail", "epoch-complete"}
            or any(not isinstance(event[key], int) or isinstance(event[key], bool) or event[key] < 0
                   for key in ("microsteps_completed", "optimizer_steps", "training_elapsed_ns", "publish_elapsed_ns"))
            or event["pending_microbatches"] != 0
            or not isinstance(event["checkpoint_payload_progress"], dict)
            or event["checkpoint_payload_progress"] != {
                "microsteps_completed": event["microsteps_completed"],
                "optimizer_steps": event["optimizer_steps"],
                "pending_microbatches": 0}
            or event["optimizer_steps"] > event["microsteps_completed"]
            or not all(isinstance(event[key], str) and event[key]
                       for key in ("publish_started_at_utc", "checkpoint_durable_at_utc"))
            or not isinstance(event["previous_event_sha256"], (str, type(None)))
            or not isinstance(event["previous_index_sha256"], (str, type(None)))
            or (isinstance(event["previous_event_sha256"], str)
                and not HEX64.fullmatch(event["previous_event_sha256"]))
            or (isinstance(event["previous_index_sha256"], str)
                and not HEX64.fullmatch(event["previous_index_sha256"]))
            or not all(isinstance(event[key], str) and HEX64.fullmatch(event[key])
                       for key in ("checkpoint_payload_sha256", "pins_sha256"))):
        raise CheckpointIntegrityError("checkpoint event schema/identity mismatch")
    return event


def _validate_transaction_index(run_dir: Path, raw: bytes) -> dict[str, Any]:
    try:
        index = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DurableRunnerError("checkpoint index JSON is invalid") from exc
    if not isinstance(index, dict) or raw != checkpoint_canonical_bytes(index):
        raise DurableRunnerError("checkpoint index is not canonical")
    required = {"schema_version", "run_id", "latest", "previous", "previous_index_sha256"}
    if set(index) != required or index["schema_version"] != TRANSACTION_CHECKPOINT_INDEX_SCHEMA:
        raise DurableRunnerError("checkpoint index must use the current v2 transaction schema")
    if (not isinstance(index["run_id"], str) or not index["run_id"]
            or not isinstance(index["previous_index_sha256"], (str, type(None)))
            or (isinstance(index["previous_index_sha256"], str)
                and not HEX64.fullmatch(index["previous_index_sha256"]))):
        raise DurableRunnerError("checkpoint index predecessor is invalid")
    for name in ("latest", "previous"):
        reference = index[name]
        if reference is None:
            continue
        if (not isinstance(reference, dict)
                or set(reference) != {"relative_path", "manifest_sha256", "event_relative_path", "event_sha256"}
                or not isinstance(reference["relative_path"], str)
                or not re.fullmatch(r"checkpoint-[0-9]{8}", reference["relative_path"])
                or reference["event_relative_path"] != f"checkpoint-events/{reference['relative_path']}.json"
                or not all(isinstance(reference[key], str) and HEX64.fullmatch(reference[key])
                           for key in ("manifest_sha256", "event_sha256"))):
            raise DurableRunnerError("checkpoint index reference is invalid")
    if index["latest"] is None:
        raise DurableRunnerError("checkpoint index lacks a latest transaction")
    latest_event = _checkpoint_event(run_dir, index["latest"], index["run_id"])
    if latest_event["previous_index_sha256"] != index["previous_index_sha256"]:
        raise DurableRunnerError("checkpoint event/index predecessor commitment differs")
    if index["previous"] is None:
        if latest_event["previous_event_sha256"] is not None:
            raise DurableRunnerError("initial checkpoint event has a predecessor")
    else:
        previous_event = _checkpoint_event(run_dir, index["previous"], index["run_id"])
        if latest_event["previous_event_sha256"] != index["previous"]["event_sha256"]:
            raise DurableRunnerError("checkpoint event-before-index chain is broken")
        # Force validation of the predecessor event before it can authorize a
        # fallback, even though its body is not otherwise returned.
        del previous_event
    return index


def _load_checkpoint_index_with_previous(run_dir: Path) -> dict[str, Any]:
    """Load only current v2 evidence; a .prev is valid only as its bound predecessor."""
    checkpoints = run_dir / "checkpoints"
    current = checkpoints / "checkpoint-index.json"
    previous = checkpoints / "checkpoint-index.prev.json"
    if not current.is_file():
        # A predecessor alone is not an authenticated resume anchor: accepting
        # it would turn deletion/replacement of current evidence into rollback.
        raise DurableRunnerError("current checkpoint index is required for resume")
    try:
        current_raw = _read_regular_file_snapshot(current, "checkpoint index")
        index = _validate_transaction_index(run_dir, current_raw)
        if index["previous_index_sha256"] is None:
            if previous.is_file():
                raise DurableRunnerError("unexpected checkpoint predecessor index")
        else:
            if not previous.is_file():
                raise DurableRunnerError("checkpoint predecessor index is missing")
            previous_raw = _read_regular_file_snapshot(previous, "checkpoint predecessor index")
            if sha256_bytes(previous_raw) != index["previous_index_sha256"]:
                raise DurableRunnerError("checkpoint predecessor index hash mismatch")
            predecessor = _validate_transaction_index(run_dir, previous_raw)
            if (predecessor["run_id"] != index["run_id"]
                    or predecessor["latest"] != index["previous"]):
                raise DurableRunnerError("checkpoint predecessor/index chain is broken")
        return index
    except DurableRunnerError:
        # Never fall back to an unbound predecessor.  Quarantine only current
        # evidence; preserving previous makes power-cut forensics recoverable.
        _quarantine_file(run_dir, current, "checkpoint-index")
        raise


def resolve_resume_checkpoint(run_dir: Path, run_id: str,
                              expected_inputs: Mapping[str, str]) -> dict[str, Any]:
    index = _load_checkpoint_index_with_previous(run_dir)
    for name in ("latest", "previous"):
        reference = index.get(name)
        if reference is None:
            continue
        try:
            validated = validate_checkpoint_reference(
                run_dir, {key: reference[key] for key in ("relative_path", "manifest_sha256")})
            manifest = validated["manifest"]
            if manifest["run_id"] != run_id:
                raise DurableRunnerError("checkpoint run_id mismatch")
            pins = manifest["pins"]
            for key in ("dataset_sha256", "model_weight_sha256",
                        "trainer_source_sha256"):
                expected = expected_inputs.get(key, "")
                if expected and pins.get(key) != expected:
                    raise DurableRunnerError(f"checkpoint input pin mismatch: {key}")
            validated.pop("manifest")
            validated["pins"] = pins
            validated["source"] = name
            return validated
        except CheckpointIntegrityError:
            if name == "latest":
                _quarantine_checkpoint(run_dir, reference)
                continue
            raise
    raise DurableRunnerError("no verified checkpoint is available")


def _load_progress(run_dir: Path, run_id: str) -> dict[str, Any] | None:
    path = run_dir / "progress.json"
    if not path.is_file():
        return None
    value = _load_json(path)
    required_keys_v1 = {
        "schema_version", "run_id", "status", "epoch", "next_batch_index",
        "microsteps_completed", "optimizer_steps", "pending_microbatches",
        "checkpoint", "updated_at_utc",
    }
    required_keys_v2 = required_keys_v1 | {"training_elapsed_ns"}
    if set(value) not in (required_keys_v1, required_keys_v2):
        raise DurableRunnerError("trainer progress keys do not match the v1 schema")
    if value.get("schema_version") not in {PROGRESS_SCHEMA, "airi.behavior-training-progress.v2"} or value.get("run_id") != run_id:
        raise DurableRunnerError("trainer progress identity mismatch")
    counters = ("epoch", "next_batch_index", "microsteps_completed",
                 "optimizer_steps", "pending_microbatches")
    if any(not isinstance(value[key], int) or isinstance(value[key], bool)
           or value[key] < 0 for key in counters):
            raise DurableRunnerError("trainer progress counters are invalid")
    if "training_elapsed_ns" in value and (not isinstance(value["training_elapsed_ns"], int)
                                             or value["training_elapsed_ns"] < 0):
        raise DurableRunnerError("trainer progress elapsed time is invalid")
    if value["optimizer_steps"] > value["microsteps_completed"]:
        raise DurableRunnerError("trainer progress optimizer count is impossible")
    checkpoint = value["checkpoint"]
    if checkpoint is not None:
        if value["pending_microbatches"] != 0:
            raise DurableRunnerError("checkpoint progress is not an optimizer boundary")
        validated = validate_checkpoint_reference(run_dir, checkpoint)
        if validated["manifest"]["run_id"] != run_id:
            raise DurableRunnerError("progress checkpoint run_id mismatch")
    return value


def _checkpoint_from_progress(progress: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not progress or progress.get("checkpoint") is None:
        return None
    checkpoint = progress["checkpoint"]
    if not isinstance(checkpoint, dict):
        raise DurableRunnerError("progress checkpoint reference is invalid")
    return {key: checkpoint[key] for key in ("relative_path", "manifest_sha256")}


def _log_receipt(run_dir: Path, path: Path) -> dict[str, Any]:
    return {"path": _relative_inside(run_dir, path),
            "size": path.stat().st_size if path.is_file() else 0}


def _artifact_receipt(path_value: str | None) -> dict[str, Any] | None:
    if path_value is None:
        return None
    path = Path(path_value).resolve()
    if path.is_file():
        return {"path": str(path), "kind": "file", "size": path.stat().st_size,
                "sha256": sha256_file(path)}
    if path.is_dir():
        rows = []
        for item in sorted(path.rglob("*")):
            if item.is_symlink():
                raise DurableRunnerError("artifact receipt cannot include links")
            if item.is_file():
                rows.append({"path": item.relative_to(path).as_posix(),
                             "size": item.stat().st_size, "sha256": sha256_file(item)})
        return {"path": str(path), "kind": "directory", "files": rows,
                "manifest_sha256": sha256_bytes(canonical_bytes(rows))}
    return {"path": str(path), "kind": "missing"}


def _validate_artifact_receipt(receipt: Mapping[str, Any] | None,
                               *, required: bool) -> None:
    if receipt is None:
        if required:
            raise DurableRunnerError("required terminal artifact receipt is missing")
        return
    if not isinstance(receipt, dict) or not isinstance(receipt.get("path"), str):
        raise DurableRunnerError("terminal artifact receipt is invalid")
    actual = _artifact_receipt(receipt["path"])
    if actual != dict(receipt):
        raise DurableRunnerError("terminal artifact receipt no longer matches disk")


def _validate_completed_outputs(state: Mapping[str, Any]) -> None:
    outputs = state.get("outputs")
    if not isinstance(outputs, dict) or set(outputs) != {"adapter", "report"}:
        raise DurableRunnerError("completed run outputs schema is invalid")
    _validate_artifact_receipt(outputs["adapter"], required=True)
    _validate_artifact_receipt(outputs["report"], required=False)


def _bind_final_evidence_root(run_dir: Path, run_id: str, state: Mapping[str, Any],
                              progress: Mapping[str, Any], inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Commit one non-circular terminal evidence cut before complete state publication."""
    producer_path = run_dir / "producer-evidence-root.json"
    producer_raw = _read_regular_file_snapshot(producer_path, "producer evidence root")
    producer = json.loads(producer_raw.decode("utf-8"))
    if producer_raw != canonical_bytes(producer) or producer.get("schema_version") != "airi.behavior-producer-evidence-root.v1" or producer.get("run_id") != run_id:
        raise DurableRunnerError("producer evidence root is invalid")
    index_path = run_dir / "checkpoints" / "checkpoint-index.json"
    index_raw = _read_regular_file_snapshot(index_path, "checkpoint index")
    index = json.loads(index_raw.decode("utf-8"))
    latest = index.get("latest") if isinstance(index, dict) else None
    if (producer.get("checkpoint_index_sha256") != sha256_bytes(index_raw)
            or producer.get("latest_checkpoint") != latest):
        raise DurableRunnerError("producer evidence root index commitment mismatch")
    if not isinstance(latest, dict) or not isinstance(latest.get("event_relative_path"), str):
        raise DurableRunnerError("producer evidence root lacks transaction event")
    event_raw = _read_regular_file_snapshot(run_dir / latest["event_relative_path"], "latest checkpoint event")
    if sha256_bytes(event_raw) != latest.get("event_sha256"):
        raise DurableRunnerError("producer evidence root latest event mismatch")
    progress_raw = _read_regular_file_snapshot(run_dir / "progress.json", "completed progress")
    if (progress_raw != canonical_bytes(dict(progress)) or progress.get("status") != "completed"
            or producer.get("progress") != {key: progress.get(key) for key in ("microsteps_completed", "optimizer_steps", "pending_microbatches", "training_elapsed_ns")}):
        raise DurableRunnerError("producer evidence root progress mismatch")
    outputs = state["outputs"]
    report = outputs.get("report")
    if report is not None and producer.get("report_sha256") != report.get("sha256"):
        raise DurableRunnerError("producer evidence root report mismatch")
    adapter_files = outputs["adapter"].get("files")
    artifact_manifests = ([row for row in adapter_files
                           if isinstance(row, dict)
                           and row.get("path") == "artifact-manifest.json"]
                          if isinstance(adapter_files, list) else [])
    if (len(artifact_manifests) != 1
            or producer.get("adapter_artifact_manifest_sha256")
            != artifact_manifests[0].get("sha256")):
        raise DurableRunnerError("producer evidence root adapter mismatch")
    projection = {"run_id": run_id, "revision": state["revision"], "status": "complete",
                  "inputs": dict(inputs), "outputs": outputs,
                  "progress_sha256": sha256_bytes(progress_raw),
                  "producer_evidence_root_sha256": sha256_bytes(producer_raw)}
    root = {"schema_version": "airi.behavior-final-evidence-root.v1", "run_id": run_id,
            "producer_evidence_root_sha256": sha256_bytes(producer_raw),
            "checkpoint_index_sha256": sha256_bytes(index_raw),
            "latest_event_sha256": latest["event_sha256"],
            "completed_progress_sha256": sha256_bytes(progress_raw),
            "state_projection": projection,
            "state_projection_sha256": sha256_bytes(canonical_bytes(projection))}
    path = run_dir / "final-evidence-root.json"
    publish_new_bytes(path, canonical_bytes(root), "final evidence root")
    return {"relative_path": path.name, "sha256": sha256_file(path),
            "state_projection_sha256": root["state_projection_sha256"]}


def _quarantine_runtime_artifact(run_dir: Path, path: Path, label: str) -> None:
    if not os.path.lexists(path):
        return
    quarantine = run_dir / "quarantine" / "runtime-artifacts"
    quarantine.mkdir(parents=True, exist_ok=True)
    if path.resolve().anchor.lower() != quarantine.resolve().anchor.lower():
        raise DurableRunnerError("runtime artifact quarantine must stay on one volume")
    safe_label = re.sub(r"[^A-Za-z0-9._-]", "_", label)[:80] or "artifact"
    target = quarantine / f"{safe_label}.{uuid.uuid4().hex}.interrupted"
    _replace_write_through(path, target)
    _fsync_directory(quarantine)


def _verify_recoverable_training_report(report_path: Path, output_path: Path,
                                        artifact_manifest_sha256: str,
                                        inputs: Mapping[str, str],
                                        trainer_args: Sequence[str],
                                        progress: Mapping[str, Any]) -> dict[str, Any]:
    report = _load_json(report_path)
    if report_path.read_bytes() != canonical_bytes(report):
        raise DurableRunnerError("interrupted training report is not canonical")
    required = {
        "mode", "steps", "optimizer_steps", "adapter_dir",
        "adapter_artifact_manifest_sha256", "dataset_sha256",
        "model_weight_sha256", "seed", "training_authorization",
        "adoption_authorized", "t3_status",
    }
    if not required.issubset(report):
        raise DurableRunnerError("interrupted training report schema is incomplete")
    try:
        report_output = Path(str(report["adapter_dir"])).resolve()
    except (OSError, ValueError) as exc:
        raise DurableRunnerError("interrupted training report output path is invalid") from exc
    if (report_output != output_path.resolve()
            or report["adapter_artifact_manifest_sha256"] != artifact_manifest_sha256
            or report["dataset_sha256"] != inputs["dataset_sha256"]
            or (inputs["model_weight_sha256"]
                and report["model_weight_sha256"] != inputs["model_weight_sha256"])
            or report["training_authorization"] is not True
            or report["adoption_authorized"] is not False
            or report["t3_status"] != "pending"
            or not isinstance(report["steps"], int)
            or isinstance(report["steps"], bool)
            or report["steps"] <= 0
            or not isinstance(report["optimizer_steps"], int)
            or isinstance(report["optimizer_steps"], bool)
            or report["optimizer_steps"] <= 0):
        raise DurableRunnerError("interrupted training report identity is invalid")
    expected_steps = _argument_value(trainer_args, "--max-steps")
    expected_seed = _argument_value(trainer_args, "--seed")
    if expected_steps is not None and report["steps"] != int(expected_steps):
        raise DurableRunnerError("interrupted training report step count differs")
    if expected_seed is not None and report["seed"] != int(expected_seed):
        raise DurableRunnerError("interrupted training report seed differs")
    if (progress.get("status") != "completed"
            or progress.get("pending_microbatches") != 0
            or progress.get("microsteps_completed") != report["steps"]
            or progress.get("optimizer_steps") != report["optimizer_steps"]):
        raise DurableRunnerError("completed progress receipt does not match final report")
    return report


def _reconcile_interrupted_final_artifacts(
        state: dict[str, Any], run_dir: Path, run_id: str,
        trainer_args: Sequence[str], inputs: Mapping[str, str],
        output_path: Path, report_path: Path | None) -> bool:
    """Promote a fully receipted child completion or quarantine every partial."""
    temporary_output = output_path.with_name(output_path.name + ".tmp")
    if os.path.lexists(temporary_output):
        _quarantine_runtime_artifact(
            run_dir, temporary_output, f"{output_path.name}.staging")
    if report_path is not None:
        for temporary_report in report_path.parent.glob(f".{report_path.name}.*.tmp"):
            _quarantine_runtime_artifact(
                run_dir, temporary_report, f"{report_path.name}.staging")

    output_exists = os.path.lexists(output_path)
    report_exists = report_path is not None and os.path.lexists(report_path)
    if not output_exists and not report_exists:
        return False
    complete_candidate = output_exists and (report_path is None or report_exists)
    try:
        if not complete_candidate:
            raise DurableRunnerError("interrupted final artifacts are incomplete")
        progress = _load_progress(run_dir, run_id)
        if progress is None:
            raise DurableRunnerError("interrupted final artifacts lack progress")
        checkpoint = resolve_resume_checkpoint(run_dir, run_id, inputs)
        checkpoint_spec = importlib.util.spec_from_file_location(
            "_airi_recovery_checkpoint",
            Path(__file__).with_name("behavior_training_checkpoint.py"))
        if checkpoint_spec is None or checkpoint_spec.loader is None:
            raise DurableRunnerError(
                "adapter artifact verifier could not be loaded")
        checkpoint_module = importlib.util.module_from_spec(checkpoint_spec)
        checkpoint_spec.loader.exec_module(checkpoint_module)
        try:
            artifact = checkpoint_module.verify_artifact_directory(
                output_path, checkpoint["pins"], run_id)
        except checkpoint_module.CheckpointError as exc:
            raise DurableRunnerError(
                "interrupted adapter artifact manifest is invalid") from exc
        if report_path is not None:
            _verify_recoverable_training_report(
                report_path, output_path, artifact["manifest_sha256"],
                inputs, trainer_args, progress)
        elif progress.get("status") != "completed":
            raise DurableRunnerError("interrupted output lacks completed progress")

        # This receipt is published by the recovery supervisor, not the stale
        # supervisor that originally recorded the interrupted state.  Preserve
        # its trainer identity so pause recovery can prove both lifecycles.
        recovery_snapshot = _process_snapshot(os.getpid())
        if recovery_snapshot is None:
            recovery_snapshot = {
                "pid": os.getpid(), "creation_time_utc": utc_now(),
                "executable_path": sys.executable,
                "command_line": "durable-runner-redacted",
            }
        state["runner"] = _process_record(recovery_snapshot)
        state["revision"] += 1
        state["updated_at_utc"] = utc_now()
        state["status"] = "complete"
        state["progress"] = {key: progress[key] for key in (
            "epoch", "next_batch_index", "microsteps_completed",
            "optimizer_steps", "pending_microbatches")}
        state["checkpoint"] = _checkpoint_from_progress(progress)
        state["heartbeat"] = {
            "sequence": int(state["heartbeat"]["sequence"]) + 1,
            "at_utc": utc_now(), "phase": "complete",
        }
        state["outputs"] = {
            "adapter": _artifact_receipt(str(output_path)),
            "report": _artifact_receipt(str(report_path)) if report_path else None,
        }
        state["terminal"] = {
            "exit_code": 0, "reason": "recovered-complete-artifacts",
            "at_utc": utc_now(),
        }
        _validate_completed_outputs(state)
        _write_state(run_dir, state)
        return True
    except DurableRunnerError:
        if output_exists:
            _quarantine_runtime_artifact(
                run_dir, output_path, f"{output_path.name}.partial")
        if report_exists and report_path is not None:
            _quarantine_runtime_artifact(
                run_dir, report_path, f"{report_path.name}.partial")
        return False


def _is_recoverable_final_state(state: Mapping[str, Any] | None) -> bool:
    if not state:
        return False
    if state.get("status") == "interrupted":
        return True
    terminal = state.get("terminal")
    return bool(
        state.get("status") == "failed"
        and isinstance(terminal, dict)
        and isinstance(terminal.get("reason"), str)
        and terminal["reason"].startswith("supervisor-"))


@contextlib.contextmanager
def exclusive_run_lock(run_dir: Path):
    lock_path = run_dir / "runner.lock"
    stream: BinaryIO = lock_path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt  # noqa: PLC0415
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
                os.fsync(stream.fileno())
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise DurableRunnerError("another durable runner owns this run directory") from exc
        else:
            import fcntl  # noqa: PLC0415
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise DurableRunnerError("another durable runner owns this run directory") from exc
        yield
    finally:
        if not stream.closed:
            if os.name == "nt":
                import msvcrt  # noqa: PLC0415
                with contextlib.suppress(OSError):
                    stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl  # noqa: PLC0415
                with contextlib.suppress(OSError):
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            stream.close()


def _base_state(args: argparse.Namespace, command: Sequence[str],
                base_command_sha256: str, inputs: Mapping[str, str],
                logs: Mapping[str, Any], outputs: Mapping[str, Any], status: str,
                previous: Mapping[str, Any] | None) -> dict[str, Any]:
    created = previous["created_at_utc"] if previous else utc_now()
    revision = int(previous["revision"]) + 1 if previous else 0
    runner_snapshot = _process_snapshot(os.getpid())
    if runner_snapshot is None:
        runner_snapshot = {"pid": os.getpid(), "creation_time_utc": created,
                           "executable_path": sys.executable,
                           "command_line": "durable-runner-redacted"}
    return {
        "schema_version": RUN_STATE_SCHEMA,
        "revision": revision,
        "run_id": args.run_id,
        "status": status,
        "created_at_utc": created,
        "updated_at_utc": utc_now(),
        "runner": _process_record(runner_snapshot),
        "trainer": None,
        "inputs": dict(inputs),
        "command": {
            "canonical_sha256": sha256_bytes(canonical_bytes(list(command))),
            "base_canonical_sha256": base_command_sha256,
            "runner_source_sha256": sha256_file(Path(__file__)),
            "trainer_source_sha256": sha256_file(args.trainer),
        },
        "progress": {"epoch": 0, "next_batch_index": 0, "microsteps_completed": 0,
                     "optimizer_steps": 0, "pending_microbatches": 0},
        "heartbeat": {"sequence": 0, "at_utc": utc_now(), "phase": status},
        "checkpoint": None,
        "logs": dict(logs),
        "outputs": dict(outputs),
        "terminal": None,
    }


def _write_state(run_dir: Path, state: dict[str, Any]) -> None:
    validate_run_state(state)
    current = run_dir / "run-state.json"
    previous = run_dir / "run-state.prev.json"
    anchor = _load_run_state_anchor(run_dir)
    if anchor is None:
        if current.is_file() or previous.is_file():
            raise DurableRunnerError("existing run-state receipt lacks an anchor")
    elif anchor["run_id"] != state["run_id"]:
        raise DurableRunnerError("run-state anchor belongs to a different run_id")
    elif current.is_file() and not _state_receipt_if_matches(current, anchor, anchor["current"]):
        # A torn/current competitor must never be rotated into predecessor.
        # Keep only an exact anchor-authorized predecessor for the replacement.
        _quarantine_file(run_dir, current, "run-state")
        if previous.is_file() and not (
                _state_receipt_if_matches(previous, anchor, anchor["current"])
                or _state_receipt_if_matches(previous, anchor, anchor["previous"])):
            _quarantine_file(run_dir, previous, "run-state-prev")
    elif anchor is not None and previous.is_file() and not (
            _state_receipt_if_matches(previous, anchor, anchor["current"])
            or _state_receipt_if_matches(previous, anchor, anchor["previous"])):
        # A stale/forged predecessor is not allowed to become the anchor's
        # retained history during an otherwise normal current rotation.
        _quarantine_file(run_dir, previous, "run-state-prev")

    atomic_write_json(current, state, keep_previous=True)
    current_sha = sha256_file(current)
    previous_receipt = None
    if previous.is_file():
        previous_state = validate_run_state(_load_json(previous))
        previous_receipt = {"sha256": sha256_file(previous), "revision": previous_state["revision"]}
    atomic_write_json(run_dir / "run-state.anchor.json", {
        "schema_version": RUN_STATE_ANCHOR_SCHEMA, "run_id": state["run_id"],
        "current": {"sha256": current_sha, "revision": state["revision"]},
        "previous": previous_receipt,
    }, keep_previous=False)


def _update_runtime_state(state: dict[str, Any], run_dir: Path, progress: dict[str, Any] | None,
                          stdout_log: Path, stderr_log: Path, phase: str,
                          *, persist: bool = True) -> None:
    state["revision"] += 1
    state["updated_at_utc"] = utc_now()
    state["status"] = phase
    state["heartbeat"] = {
        "sequence": int(state["heartbeat"]["sequence"]) + 1,
        "at_utc": utc_now(), "phase": phase,
    }
    if progress:
        recorded = state["progress"]
        if (progress["microsteps_completed"] < recorded["microsteps_completed"]
                or progress["optimizer_steps"] < recorded["optimizer_steps"]
                or progress["epoch"] < recorded["epoch"]):
            raise DurableRunnerError("trainer progress moved backwards")
        if (progress["epoch"] == recorded["epoch"]
                and progress["next_batch_index"] < recorded["next_batch_index"]):
            raise DurableRunnerError("trainer next_batch_index moved backwards within an epoch")
        recorded_checkpoint = state.get("checkpoint")
        incoming_checkpoint = _checkpoint_from_progress(progress)
        if recorded_checkpoint is not None and incoming_checkpoint is None:
            raise DurableRunnerError("trainer checkpoint reference disappeared")
        if recorded_checkpoint is not None and incoming_checkpoint is not None:
            old_generation = recorded_checkpoint["relative_path"]
            new_generation = incoming_checkpoint["relative_path"]
            if old_generation == new_generation:
                if recorded_checkpoint != incoming_checkpoint:
                    raise DurableRunnerError("checkpoint reference mutated for an existing generation")
            elif new_generation < old_generation:
                raise DurableRunnerError("checkpoint generation moved backwards")
        state["progress"] = {key: progress[key] for key in (
            "epoch", "next_batch_index", "microsteps_completed", "optimizer_steps",
            "pending_microbatches")}
        state["checkpoint"] = incoming_checkpoint
    state["logs"] = {"stdout": _log_receipt(run_dir, stdout_log),
                      "stderr": _log_receipt(run_dir, stderr_log)}
    if persist:
        _write_state(run_dir, state)


def _pause_request_exists(run_dir: Path) -> bool:
    return (run_dir / "control" / "pause.request.json").is_file()


def _prearm_first_optimizer_boundary(run_dir: Path, run_id: str) -> str:
    """Durably publish a fresh-run pause request before the trainer can start."""

    control = run_dir / "control"
    control.mkdir(parents=True, exist_ok=True)
    request_path = control / "pause.request.json"
    if request_path.exists():
        raise DurableRunnerError("fresh prearm refuses an existing pause request")
    request_id = f"prearm-{uuid.uuid4().hex}"
    request = {
        "schema_version": "airi.behavior-pause-request.v1",
        "run_id": run_id,
        "request_id": request_id,
    }
    publish_new_bytes(request_path, canonical_bytes(request), "fresh prearm pause request")
    # Verify via the same strict reader used by the normal pause/ack flow.
    if _load_pause_request_path(request_path, run_id)["request_id"] != request_id:
        raise DurableRunnerError("fresh prearm pause request verification failed")
    return request_id


def _load_pause_request_path(path: Path, run_id: str) -> dict[str, Any]:
    request = _load_json(path)
    if (set(request) != {"schema_version", "run_id", "request_id"}
            or request["schema_version"] != "airi.behavior-pause-request.v1"
            or request["run_id"] != run_id
            or not isinstance(request["request_id"], str)
            or not RUN_ID.fullmatch(request["request_id"])):
        raise DurableRunnerError("safe pause request identity is invalid")
    return request


def _load_pause_request(run_dir: Path, run_id: str) -> dict[str, Any]:
    return _load_pause_request_path(
        run_dir / "control" / "pause.request.json", run_id)


def _validate_safe_pause(run_dir: Path, run_id: str,
                         checkpoint: Mapping[str, Any] | None,
                         progress: Mapping[str, Any] | None,
                         expected_inputs: Mapping[str, str]) -> dict[str, Any]:
    request = _load_pause_request(run_dir, run_id)
    ack_path = run_dir / "control" / "pause.ack.json"
    if not ack_path.is_file() or checkpoint is None or progress is None:
        raise DurableRunnerError("safe pause exited without ack/checkpoint")
    ack = _load_json(ack_path)
    required = {"schema_version", "run_id", "request_id", "checkpoint_manifest_sha256",
                "checkpoint_relative_path", "acknowledged_at_utc", "safe_to_power_off"}
    if set(ack) != required or ack["schema_version"] != PAUSE_ACK_SCHEMA:
        raise DurableRunnerError("safe pause ack schema mismatch")
    if (ack["run_id"] != run_id or ack["request_id"] != request["request_id"]
            or ack["safe_to_power_off"] is not True
            or progress["pending_microbatches"] != 0):
        raise DurableRunnerError("safe pause ack identity mismatch")
    if (ack["checkpoint_manifest_sha256"] != checkpoint["manifest_sha256"]
            or ack["checkpoint_relative_path"] != checkpoint["relative_path"]):
        raise DurableRunnerError("safe pause ack checkpoint mismatch")
    validated = validate_checkpoint_reference(run_dir, checkpoint)
    manifest = validated["manifest"]
    if manifest["run_id"] != run_id:
        raise DurableRunnerError("safe pause checkpoint run_id mismatch")
    pins = manifest["pins"]
    for key in ("dataset_sha256", "model_weight_sha256", "trainer_source_sha256"):
        if pins.get(key) != expected_inputs.get(key):
            raise DurableRunnerError(f"safe pause checkpoint input pin mismatch: {key}")
    payload = manifest["payload"]
    return {
        "schema_version": CHECKPOINT_VERIFICATION_SCHEMA,
        "checkpoint_relative_path": checkpoint["relative_path"],
        "checkpoint_manifest_sha256": checkpoint["manifest_sha256"],
        "checkpoint_payload_sha256": payload["sha256"],
        "checkpoint_payload_bytes": payload["bytes"],
        "canonical_pins_sha256": sha256_bytes(checkpoint_canonical_bytes(pins)),
    }


def _archive_accepted_pause_control(
        run_dir: Path, run_id: str,
        expected_inputs: Mapping[str, str]) -> bool:
    control = run_dir / "control"
    accepted_path = control / "resume.accepted.json"
    request_path = control / "pause.request.json"
    ack_path = control / "pause.ack.json"
    history = control / "history"
    live_request_id: str | None = None
    if request_path.is_file():
        live_request_id = _load_pause_request_path(request_path, run_id)["request_id"]
    if ack_path.is_file():
        live_ack = _load_json(ack_path)
        ack_request_id = live_ack.get("request_id") if isinstance(live_ack, dict) else None
        if (not isinstance(ack_request_id, str)
                or (live_request_id is not None and ack_request_id != live_request_id)):
            raise DurableRunnerError("live pause controls have competing request ids")
        live_request_id = ack_request_id
    accepted_source = accepted_path if accepted_path.is_file() else None
    if accepted_source is None and live_request_id is not None:
        history_candidate = history / f"{live_request_id}.resume-accepted.json"
        if history_candidate.is_file():
            accepted_source = history_candidate
    if accepted_source is None:
        return False
    accepted = _load_json(accepted_source)
    accepted_keys = {"schema_version", "run_id", "request_id",
                     "checkpoint_relative_path", "checkpoint_manifest_sha256"}
    if (set(accepted) != accepted_keys
            or accepted["schema_version"] != RESUME_ACCEPTED_SCHEMA
            or accepted["run_id"] != run_id
            or not isinstance(accepted["request_id"], str)
            or not RUN_ID.fullmatch(accepted["request_id"])
            or not isinstance(accepted["checkpoint_relative_path"], str)
            or not isinstance(accepted["checkpoint_manifest_sha256"], str)):
        raise DurableRunnerError("resume acceptance receipt is invalid")
    accepted_checkpoint = validate_checkpoint_reference(run_dir, {
        "relative_path": accepted["checkpoint_relative_path"],
        "manifest_sha256": accepted["checkpoint_manifest_sha256"],
    })
    manifest = accepted_checkpoint["manifest"]
    if manifest["run_id"] != run_id:
        raise DurableRunnerError("accepted checkpoint run_id mismatch")
    for key in ("dataset_sha256", "model_weight_sha256", "trainer_source_sha256"):
        expected = expected_inputs.get(key, "")
        if expected and manifest["pins"].get(key) != expected:
            raise DurableRunnerError(f"accepted checkpoint input pin mismatch: {key}")
    history.mkdir(parents=True, exist_ok=True)
    request_id = accepted["request_id"]
    if live_request_id is not None and live_request_id != request_id:
        raise DurableRunnerError("live pause controls do not match acceptance history")
    request_history = history / f"{request_id}.request.json"
    ack_history = history / f"{request_id}.ack.json"
    request_source = request_path if request_path.is_file() else request_history
    ack_source = ack_path if ack_path.is_file() else ack_history
    if not request_source.is_file() or not ack_source.is_file():
        raise DurableRunnerError("accepted pause controls are incomplete")
    request = _load_pause_request_path(request_source, run_id)
    ack = _load_json(ack_source)
    ack_keys = {"schema_version", "run_id", "request_id", "checkpoint_manifest_sha256",
                "checkpoint_relative_path", "acknowledged_at_utc", "safe_to_power_off"}
    if (set(ack) != ack_keys or ack["schema_version"] != PAUSE_ACK_SCHEMA
            or request["request_id"] != request_id
            or ack["run_id"] != run_id or ack["request_id"] != request_id
            or ack["safe_to_power_off"] is not True
            or ack["checkpoint_relative_path"] != accepted["checkpoint_relative_path"]
            or ack["checkpoint_manifest_sha256"] != accepted["checkpoint_manifest_sha256"]):
        raise DurableRunnerError("accepted pause controls do not match checkpoint")
    for source, target in (
            (request_path, request_history),
            (ack_path, ack_history),
            (accepted_path, history / f"{request_id}.resume-accepted.json")):
        if source.is_file():
            if target.exists():
                if source.read_bytes() != target.read_bytes():
                    raise DurableRunnerError("pause control history target differs")
                source.unlink()
                _fsync_directory(source.parent)
            else:
                _replace_write_through(source, target)
    _fsync_directory(history)
    return True


def _archive_unacknowledged_pause_request(run_dir: Path, run_id: str) -> None:
    """Preserve a pre-ack pause request without replaying it after a power cut."""
    control = run_dir / "control"
    request_path = control / "pause.request.json"
    request = _load_pause_request_path(request_path, run_id)
    history = control / "history"
    history.mkdir(parents=True, exist_ok=True)
    target = history / f"{request['request_id']}.unacknowledged.request.json"
    if target.exists():
        raise DurableRunnerError("unacknowledged pause request history already exists")
    _replace_write_through(request_path, target)
    _fsync_directory(history)


def _stop_child(process: subprocess.Popen[bytes], timeout_seconds: float = 10.0) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout_seconds)


def _verified_source_snapshot(run_dir: Path, trainer: Path) -> tuple[Path, str | None]:
    """Execute run-local bytes so post-hash pathname replacement cannot win."""
    source = _read_regular_file_snapshot(trainer, "trainer")
    digest = sha256_bytes(source)
    directory = run_dir / "source-snapshot"
    snapshot = directory / trainer.name
    helper_source = trainer.parent / "behavior_training_checkpoint.py"
    helper = directory / helper_source.name
    if directory.exists():
        if _read_regular_file_snapshot(snapshot, "trainer snapshot") != source:
            raise DurableRunnerError("existing trainer snapshot does not match pinned source")
        return snapshot, sha256_file(helper) if helper.exists() else None
    directory.mkdir(parents=True, exist_ok=False)
    publish_new_bytes(snapshot, source, "trainer snapshot")
    helper_digest = None
    if helper_source.is_file():
        helper_bytes = _read_regular_file_snapshot(helper_source, "checkpoint helper")
        helper_digest = sha256_bytes(helper_bytes)
        publish_new_bytes(helper, helper_bytes, "checkpoint helper snapshot")
    if sha256_file(snapshot) != digest:
        raise DurableRunnerError("trainer snapshot byte verification failed")
    return snapshot, helper_digest


def run_supervisor(args: argparse.Namespace) -> int:
    run_dir = validate_local_run_dir(args.run_dir, create=False)
    if not RUN_ID.fullmatch(args.run_id):
        raise DurableRunnerError("run_id is invalid")
    if args.pause_at_first_optimizer_boundary and args.resume_interrupted:
        raise DurableRunnerError("fresh prearm cannot be used with --resume-interrupted")
    if (args.pause_at_first_optimizer_boundary
            and not getattr(args, "_prearm_run_dir_created", False)
            and os.path.lexists(run_dir)):
        raise DurableRunnerError("fresh prearm requires an absent run directory")
    if args.pause_at_first_optimizer_boundary and any(
            os.path.lexists(path) for path in (
                run_dir / "run-state.json", run_dir / "run-state.prev.json",
                run_dir / "control")):
        raise DurableRunnerError("fresh prearm refuses pre-existing run/control state")
    python = validate_local_path(args.python, "pinned Python")
    trainer = validate_local_path(args.trainer, "trainer")
    working_directory = validate_local_path(args.working_directory, "working directory")
    if not python.is_file() or not trainer.is_file():
        raise DurableRunnerError("pinned Python/trainer path is missing")
    if not working_directory.is_dir():
        raise DurableRunnerError("working directory is missing")
    trainer_args = list(args.trainer_args)
    if trainer_args and trainer_args[0] == "--":
        trainer_args.pop(0)
    _validate_trainer_arguments(trainer_args)
    # Init adapter provenance and --resume-from-checkpoint coexist: the pins
    # a checkpoint commits to include init_mode, so a resume must re-supply it.
    _ensure_argument(trainer_args, "--run-dir", str(run_dir))
    _ensure_argument(trainer_args, "--run-id", args.run_id)
    _ensure_argument(trainer_args, "--checkpoint-every-optimizer-steps",
                     str(args.checkpoint_every_optimizer_steps))
    base_command_sha256 = sha256_bytes(canonical_bytes(
        [str(python), str(trainer), *trainer_args]))
    dataset_sha = _argument_value(trainer_args, "--dataset-sha256", required=True)
    model_sha = _argument_value(trainer_args, "--model-sha256") or ""
    dataset_value = _argument_value(trainer_args, "--dataset", required=True)
    model_value = _argument_value(trainer_args, "--model-dir", required=True)
    output_value = _argument_value(trainer_args, "--output", required=True)
    report_value = _argument_value(trainer_args, "--report")
    dataset_path = validate_local_path(Path(dataset_value or ""), "dataset")
    model_path = validate_local_path(Path(model_value or ""), "model directory")
    if not dataset_path.is_file() or not model_path.is_dir():
        raise DurableRunnerError("dataset/model trainer paths are invalid")
    output_path = validate_local_path(Path(output_value or ""), "adapter output")
    report_path = (validate_local_path(Path(report_value), "report output")
                   if report_value else None)
    runtime_anchor = run_dir.resolve().anchor.lower()
    # Dataset/model are immutable, SHA-pinned read-only inputs and may reside
    # on other fixed local volumes.  Only mutable publication targets must
    # share the run volume so their staged promotion remains atomic.
    if (output_path.resolve().anchor.lower() != runtime_anchor
            or (report_path is not None
                and report_path.resolve().anchor.lower() != runtime_anchor)):
        raise DurableRunnerError("run directory and final artifacts must share one volume")
    trainer_source_sha256 = sha256_file(trainer)
    helper_source = trainer.parent / "behavior_training_checkpoint.py"
    helper_source_sha256 = sha256_file(helper_source) if helper_source.is_file() else None
    manifest_identity = validate_input_manifest_content(
        args.input_manifest_path, args.input_manifest_sha256, trainer_args,
        trainer_source_sha256, dataset_sha or "", model_sha,
        args.checkpoint_every_optimizer_steps, helper_source_sha256)
    inputs = {"dataset_sha256": dataset_sha or "", "model_weight_sha256": model_sha,
              "input_manifest_path": manifest_identity["path"],
              "input_manifest_sha256": manifest_identity["sha256"],
              "input_manifest_training_config_sha256": manifest_identity["training_config_sha256"],
              "trainer_source_sha256": trainer_source_sha256}
    if manifest_identity["schema_version"] == "airi.behavior-input-manifest.v3":
        initial = manifest_identity["initial_adapter"]
        inputs.update({
            "init_mode": manifest_identity["init_mode"],
            "init_adapter_dir": initial["directory"] if initial else "",
            "init_adapter_model_sha256": (next((row["sha256"] for row in initial["files"]
                                                 if row["path"] == "adapter_model.safetensors"), "")
                                          if initial else ""),
            "init_adapter_config_sha256": (next((row["sha256"] for row in initial["files"]
                                                  if row["path"] == "adapter_config.json"), "")
                                           if initial else ""),
            "init_adapter_artifact_manifest_sha256": (initial["artifact_manifest"]["sha256"]
                                                        if initial else ""),
        })
    for key, value in inputs.items():
        if key in {"input_manifest_path", "init_mode", "init_adapter_dir"}:
            continue
        if value and not HEX64.fullmatch(value):
            raise DurableRunnerError("input SHA-256 is invalid")

    run_dir.mkdir(parents=True, exist_ok=True)
    trainer, snapshot_helper_source_sha256 = _verified_source_snapshot(run_dir, trainer)
    # The helper digest is a run-state input even when a synthetic test trainer
    # has no helper sibling; production manifests require the nonempty pin.
    inputs["checkpoint_helper_source_sha256"] = snapshot_helper_source_sha256 or ""
    previous, source = load_run_state_with_previous(run_dir)
    if previous and previous["run_id"] != args.run_id:
        raise DurableRunnerError("run directory belongs to a different run_id")
    if previous and process_matches(previous.get("runner")):
        raise DurableRunnerError("the recorded durable runner is still alive")
    if previous and process_matches(previous.get("trainer")):
        raise DurableRunnerError("orphan trainer is still alive; refusing duplicate launch")
    if previous and previous["status"] in {"running", "starting", "checkpointing",
                                           "pause-requested", "resuming"}:
        previous = dict(previous)
        previous["revision"] += 1
        previous["status"] = "interrupted"
        previous["updated_at_utc"] = utc_now()
        previous["terminal"] = {"exit_code": None, "reason": "process-missing",
                                "at_utc": utc_now(), "recovered_from": source}
        _write_state(run_dir, previous)
    if previous and previous["status"] == "complete":
        try:
            _validate_completed_outputs(previous)
        except DurableRunnerError as exc:
            previous = dict(previous)
            previous["revision"] += 1
            previous["status"] = "failed"
            previous["updated_at_utc"] = utc_now()
            previous["terminal"] = {
                "exit_code": None, "reason": "completed-artifact-integrity-mismatch",
                "at_utc": utc_now(),
            }
            _write_state(run_dir, previous)
            raise DurableRunnerError(
                "completed artifact receipt failed revalidation") from exc
        raise DurableRunnerError("completed run artifacts remain verified; resume refused")
    if (previous and args.resume_interrupted
            and _is_recoverable_final_state(previous)
            and _reconcile_interrupted_final_artifacts(
                previous, run_dir, args.run_id, trainer_args, inputs,
                output_path, report_path)):
        return 0
    if output_path.exists() or (report_path is not None and report_path.exists()):
        raise DurableRunnerError("final output/report must be absent before training")
    if previous and not args.resume_interrupted:
        raise DurableRunnerError("existing run requires explicit --resume-interrupted")
    resume_checkpoint: dict[str, Any] | None = None
    requires_resume_acceptance = False
    if args.resume_interrupted:
        if previous is None:
            raise DurableRunnerError("resume requires an existing run-state")
        if previous["status"] not in {"interrupted", "paused-safe", "failed"}:
            raise DurableRunnerError("existing run-state is not resumable")
        if previous["inputs"] != inputs:
            raise DurableRunnerError("resume inputs differ from the recorded run")
        if previous["command"].get("runner_source_sha256") != sha256_file(Path(__file__)):
            raise DurableRunnerError("runner source changed since the recorded run")
        if previous["command"].get("base_canonical_sha256",
                                   previous["command"].get("canonical_sha256")) != base_command_sha256:
            raise DurableRunnerError("resume trainer command differs from the recorded run")
        checkpoint = resolve_resume_checkpoint(run_dir, args.run_id, inputs)
        resume_checkpoint = checkpoint
        control = run_dir / "control"
        request_exists = (control / "pause.request.json").is_file()
        ack_exists = (control / "pause.ack.json").is_file()
        accepted_exists = (control / "resume.accepted.json").is_file()
        archived_accepted = _archive_accepted_pause_control(
            run_dir, args.run_id, inputs)
        if accepted_exists and not archived_accepted:
            raise DurableRunnerError("resume acceptance receipt disappeared")
        if archived_accepted:
            request_exists = (control / "pause.request.json").is_file()
            ack_exists = (control / "pause.ack.json").is_file()
            if request_exists or ack_exists:
                raise DurableRunnerError("accepted pause controls were not fully archived")
        elif request_exists and ack_exists:
            pause_progress = _load_progress(run_dir, args.run_id)
            pause_verification = _validate_safe_pause(
                run_dir, args.run_id,
                {key: checkpoint[key] for key in ("relative_path", "manifest_sha256")},
                pause_progress, inputs)
            if (previous["status"] == "paused-safe"
                    and previous["terminal"].get("checkpoint_verification")
                    != pause_verification):
                raise DurableRunnerError(
                    "paused-safe terminal checkpoint verification receipt mismatch")
            requires_resume_acceptance = True
        elif request_exists:
            if previous["status"] == "paused-safe":
                raise DurableRunnerError("paused-safe resume is missing its pause ack")
            _archive_unacknowledged_pause_request(run_dir, args.run_id)
        elif ack_exists:
            raise DurableRunnerError("resume has an orphan pause ack")
        _ensure_argument(trainer_args, "--resume-from-checkpoint", checkpoint["absolute_path"])
        # The supervisor re-binds initial-adapter provenance on every durable
        # resume and keeps the flags on the resumed command: the trainer uses
        # them only for identity and checkpoint pins, never to reinitialize
        # weights over restored checkpoint state.

    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = logs_dir / "trainer.stdout.log"
    stderr_log = logs_dir / "trainer.stderr.log"
    command = [str(python), str(trainer), *trainer_args]
    logs = {"stdout": _log_receipt(run_dir, stdout_log),
            "stderr": _log_receipt(run_dir, stderr_log)}
    outputs = {"adapter": {"path": str(output_path)},
               "report": {"path": str(report_path)} if report_path else None}
    state = _base_state(args, command, base_command_sha256, inputs, logs, outputs,
                        "resuming" if args.resume_interrupted else "starting", previous)
    if args.pause_at_first_optimizer_boundary:
        _prearm_first_optimizer_boundary(run_dir, args.run_id)
    _write_state(run_dir, state)

    trainer_process: subprocess.Popen[bytes] | None = None
    held_inputs: list[_HeldRegularInput] = []
    try:
        with (stdout_log.open("ab", buffering=0) as stdout_stream,
              stderr_log.open("ab", buffering=0) as stderr_stream):
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            # This is deliberately adjacent to Popen: validation and launch use
            # the same held descriptors, leaving no path re-open window.
            held_inputs = _hold_training_inputs(
                dataset_path, dataset_sha or "", model_path,
                manifest_identity["model_inventory"], manifest_identity["initial_adapter"])
            trainer_process = subprocess.Popen(
                command, cwd=str(working_directory), stdout=stdout_stream,
                stderr=stderr_stream, stdin=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            snapshot = None
            for _ in range(20):
                snapshot = _process_snapshot(trainer_process.pid)
                if snapshot is not None:
                    break
                time.sleep(0.05)
            if snapshot is None:
                raise DurableRunnerError("trainer process identity could not be captured")
            state["trainer"] = _process_record(snapshot)
            _update_runtime_state(state, run_dir, _load_progress(run_dir, args.run_id),
                                  stdout_log, stderr_log, "running")
            resume_accepted = _archive_accepted_pause_control(
                run_dir, args.run_id, inputs)
            while trainer_process.poll() is None:
                phase = "pause-requested" if _pause_request_exists(run_dir) else "running"
                progress = _load_progress(run_dir, args.run_id)
                _update_runtime_state(
                    state, run_dir, progress, stdout_log, stderr_log, phase)
                if not resume_accepted:
                    resume_accepted = _archive_accepted_pause_control(
                        run_dir, args.run_id, inputs)
                time.sleep(args.heartbeat_seconds)
            exit_code = int(trainer_process.returncode)

        # Do this before accepting progress or promoting terminal output
        # receipts.  A child that mutates/replaces an input never gets a
        # verified-complete terminal state.
        _verify_held_training_inputs(held_inputs)

        if not resume_accepted:
            resume_accepted = _archive_accepted_pause_control(
                run_dir, args.run_id, inputs)
        if (requires_resume_acceptance and exit_code in {0, SAFE_PAUSE_EXIT_CODE}
                and not resume_accepted):
            raise DurableRunnerError(
                "trainer exited without a full-pin resume acceptance receipt")

        progress = _load_progress(run_dir, args.run_id)
        checkpoint = _checkpoint_from_progress(progress)
        checkpoint_verification = None
        if exit_code == SAFE_PAUSE_EXIT_CODE:
            checkpoint_verification = _validate_safe_pause(
                run_dir, args.run_id, checkpoint, progress, inputs)
            terminal_status = "paused-safe"
            reason = "safe-optimizer-boundary"
        elif exit_code == 0:
            adapter_receipt = _artifact_receipt(str(output_path))
            report_receipt = _artifact_receipt(
                str(report_path) if report_path else None)
            if (not adapter_receipt or adapter_receipt.get("kind") == "missing"
                    or (report_path and (not report_receipt
                                         or report_receipt.get("kind") == "missing"))):
                exit_code = 2
                terminal_status = "failed"
                reason = "terminal-artifact-missing"
            else:
                state["outputs"] = {
                    "adapter": adapter_receipt, "report": report_receipt}
                terminal_status = "complete"
                reason = "trainer-complete"
        else:
            terminal_status = "failed"
            reason = "trainer-nonzero-exit"
        _update_runtime_state(
            state, run_dir, progress, stdout_log, stderr_log,
            terminal_status, persist=False)
        state["terminal"] = {
            "exit_code": exit_code, "reason": reason, "at_utc": utc_now()}
        if checkpoint_verification is not None:
            state["terminal"]["checkpoint_verification"] = checkpoint_verification
        if terminal_status == "complete" and (run_dir / "producer-evidence-root.json").is_file():
            state["terminal"]["final_evidence_root"] = _bind_final_evidence_root(
                run_dir, args.run_id, state, progress or {}, inputs)
        _write_state(run_dir, state)
        return exit_code
    except BaseException as exc:
        if trainer_process is not None:
            with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                _stop_child(trainer_process)
        try:
            progress = _load_progress(run_dir, args.run_id)
        except DurableRunnerError:
            progress = None
        status = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        reason = ("supervisor-interrupted" if status == "interrupted"
                  else f"supervisor-{type(exc).__name__.lower()}")
        with contextlib.suppress(Exception):
            _update_runtime_state(
                state, run_dir, progress, stdout_log, stderr_log,
                status, persist=False)
            state["terminal"] = {
                "exit_code": (trainer_process.returncode
                              if trainer_process is not None else None),
                "reason": reason, "at_utc": utc_now(),
            }
            _write_state(run_dir, state)
        if isinstance(exc, (DurableRunnerError, KeyboardInterrupt)):
            raise
        raise DurableRunnerError("supervisor failed before terminal receipt") from exc
    finally:
        for held_input in reversed(held_inputs):
            held_input.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Durable AIRI behavior-training supervisor")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--trainer", type=Path, required=True)
    parser.add_argument("--working-directory", type=Path, required=True)
    parser.add_argument("--input-manifest-path", type=Path, required=True)
    parser.add_argument("--input-manifest-sha256", required=True)
    parser.add_argument("--checkpoint-every-optimizer-steps", type=int, default=5)
    parser.add_argument("--heartbeat-seconds", type=float, default=10.0)
    parser.add_argument("--resume-interrupted", action="store_true")
    parser.add_argument("--pause-at-first-optimizer-boundary", action="store_true")
    parser.add_argument("trainer_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if (not math.isfinite(args.heartbeat_seconds)
            or args.heartbeat_seconds <= 0 or args.heartbeat_seconds > 15):
        raise DurableRunnerError("heartbeat must be in (0, 15] seconds")
    if args.checkpoint_every_optimizer_steps <= 0:
        raise DurableRunnerError("checkpoint interval must be positive")
    if args.pause_at_first_optimizer_boundary and args.resume_interrupted:
        raise DurableRunnerError("fresh prearm cannot be used with --resume-interrupted")
    # Validate the immutable manifest before creating the run directory or lock.
    run_dir = validate_local_run_dir(args.run_dir, create=False)
    if args.pause_at_first_optimizer_boundary and os.path.lexists(run_dir):
        raise DurableRunnerError("fresh prearm requires an absent run directory")
    preflight_trainer_args = list(args.trainer_args)
    if preflight_trainer_args and preflight_trainer_args[0] == "--":
        preflight_trainer_args.pop(0)
    _validate_trainer_arguments(preflight_trainer_args)
    preflight_trainer = validate_local_path(args.trainer, "trainer")
    if not preflight_trainer.is_file():
        raise DurableRunnerError("trainer path is missing")
    preflight_helper = preflight_trainer.parent / "behavior_training_checkpoint.py"
    if not preflight_helper.is_file():
        raise DurableRunnerError("checkpoint helper path is missing")
    # Preflight refusal only: the manifest must validate before the run lock,
    # including adapter-init runs, which now keep their init flags on a resumed
    # command so the checkpoint's exact pins still match (see run_supervisor).
    validate_input_manifest_content(
        args.input_manifest_path, args.input_manifest_sha256,
        preflight_trainer_args, sha256_file(preflight_trainer),
        _argument_value(preflight_trainer_args, "--dataset-sha256", required=True) or "",
        _argument_value(preflight_trainer_args, "--model-sha256") or "",
        args.checkpoint_every_optimizer_steps, sha256_file(preflight_helper))
    if args.pause_at_first_optimizer_boundary:
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise DurableRunnerError(
                "fresh prearm run directory appeared during preflight") from exc
        args._prearm_run_dir_created = True
    else:
        run_dir.mkdir(parents=True, exist_ok=True)
    with exclusive_run_lock(run_dir):
        return run_supervisor(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DurableRunnerError as exc:
        print(f"durable training runner refused: {exc}", file=sys.stderr)
        raise SystemExit(2)
