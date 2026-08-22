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
PROGRESS_SCHEMA = "airi.behavior-training-progress.v1"
CHECKPOINT_INDEX_SCHEMA = "airi.behavior-checkpoint-index.v1"
PAUSE_ACK_SCHEMA = "airi.behavior-pause-ack.v1"
RESUME_ACCEPTED_SCHEMA = "airi.behavior-resume-accepted.v1"
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
                       separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
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
    return dict(value)


def _quarantine_file(run_dir: Path, path: Path, label: str) -> Path:
    payload = path.read_bytes() if path.is_file() else b""
    quarantine = run_dir / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    target = quarantine / (
        f"{label}.corrupt.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}."
        f"{sha256_bytes(payload)[:12]}.json"
    )
    _replace_write_through(path, target)
    _fsync_directory(quarantine)
    return target


def load_run_state_with_previous(run_dir: Path) -> tuple[dict[str, Any] | None, str | None]:
    current = run_dir / "run-state.json"
    previous = run_dir / "run-state.prev.json"
    if current.is_file():
        try:
            return validate_run_state(_load_json(current)), "current"
        except DurableRunnerError:
            _quarantine_file(run_dir, current, "run-state")
    if previous.is_file():
        try:
            return validate_run_state(_load_json(previous)), "previous"
        except DurableRunnerError:
            _quarantine_file(run_dir, previous, "run-state-prev")
            raise
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


def validate_local_run_dir(value: Path) -> Path:
    resolved = _reject_remote_or_reparse_path(value, "run directory")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def validate_local_path(value: Path, label: str) -> Path:
    return _reject_remote_or_reparse_path(value, label)


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
    if not path.is_file() or path.is_symlink():
        raise CheckpointIntegrityError("checkpoint payload file is missing or linked")
    if path.stat().st_size != payload["bytes"] or sha256_file(path) != payload["sha256"]:
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
    if not manifest_path.is_file() or sha256_file(manifest_path) != digest:
        raise CheckpointIntegrityError("checkpoint manifest integrity mismatch")
    try:
        manifest = _load_json(manifest_path)
    except DurableRunnerError as exc:
        raise CheckpointIntegrityError("checkpoint manifest JSON is invalid") from exc
    expected_manifest = canonical_bytes(manifest)
    if manifest_path.read_bytes() != expected_manifest:
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


def _load_checkpoint_index_with_previous(run_dir: Path) -> dict[str, Any]:
    checkpoints = run_dir / "checkpoints"
    for name, label in (("checkpoint-index.json", "checkpoint-index"),
                        ("checkpoint-index.prev.json", "checkpoint-index-prev")):
        path = checkpoints / name
        if not path.is_file():
            continue
        try:
            index = _load_json(path)
            if (set(index) != {"schema_version", "latest", "previous"}
                    or index["schema_version"] != CHECKPOINT_INDEX_SCHEMA):
                raise DurableRunnerError("checkpoint index schema mismatch")
            for position in ("latest", "previous"):
                reference = index[position]
                if reference is None:
                    continue
                if (not isinstance(reference, dict)
                        or set(reference) != {"relative_path", "manifest_sha256"}
                        or not isinstance(reference["relative_path"], str)
                        or not re.fullmatch(r"checkpoint-[0-9]{8}", reference["relative_path"])
                        or not isinstance(reference["manifest_sha256"], str)
                        or not HEX64.fullmatch(reference["manifest_sha256"])):
                    raise DurableRunnerError("checkpoint index reference is invalid")
            return index
        except DurableRunnerError:
            _quarantine_file(run_dir, path, label)
    raise DurableRunnerError("no valid checkpoint index is available")


def resolve_resume_checkpoint(run_dir: Path, run_id: str,
                              expected_inputs: Mapping[str, str]) -> dict[str, Any]:
    index = _load_checkpoint_index_with_previous(run_dir)
    for name in ("latest", "previous"):
        reference = index.get(name)
        if reference is None:
            continue
        try:
            validated = validate_checkpoint_reference(run_dir, reference)
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
    required_keys = {
        "schema_version", "run_id", "status", "epoch", "next_batch_index",
        "microsteps_completed", "optimizer_steps", "pending_microbatches",
        "checkpoint", "updated_at_utc",
    }
    if set(value) != required_keys:
        raise DurableRunnerError("trainer progress keys do not match the v1 schema")
    if value.get("schema_version") != PROGRESS_SCHEMA or value.get("run_id") != run_id:
        raise DurableRunnerError("trainer progress identity mismatch")
    counters = ("epoch", "next_batch_index", "microsteps_completed",
                "optimizer_steps", "pending_microbatches")
    if any(not isinstance(value[key], int) or isinstance(value[key], bool)
           or value[key] < 0 for key in counters):
        raise DurableRunnerError("trainer progress counters are invalid")
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


def _base_state(args: argparse.Namespace, command: Sequence[str], inputs: Mapping[str, str],
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
    atomic_write_json(run_dir / "run-state.json", state, keep_previous=True)


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
                         progress: Mapping[str, Any] | None) -> None:
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
    validate_checkpoint_reference(run_dir, checkpoint)


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


def run_supervisor(args: argparse.Namespace) -> int:
    run_dir = validate_local_run_dir(args.run_dir)
    if not RUN_ID.fullmatch(args.run_id):
        raise DurableRunnerError("run_id is invalid")
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
    _ensure_argument(trainer_args, "--run-dir", str(run_dir))
    _ensure_argument(trainer_args, "--run-id", args.run_id)
    _ensure_argument(trainer_args, "--checkpoint-every-optimizer-steps",
                     str(args.checkpoint_every_optimizer_steps))
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
    inputs = {"dataset_sha256": dataset_sha or "", "model_weight_sha256": model_sha,
              "input_manifest_sha256": args.input_manifest_sha256 or "",
              "trainer_source_sha256": sha256_file(trainer)}
    for value in inputs.values():
        if value and not HEX64.fullmatch(value):
            raise DurableRunnerError("input SHA-256 is invalid")

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
        requested_command = [str(python), str(trainer), *trainer_args]
        requested_command_sha = sha256_bytes(canonical_bytes(requested_command))
        if previous["command"].get("canonical_sha256") != requested_command_sha:
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
            _validate_safe_pause(
                run_dir, args.run_id,
                {key: checkpoint[key] for key in ("relative_path", "manifest_sha256")},
                pause_progress)
            requires_resume_acceptance = True
        elif request_exists:
            if previous["status"] == "paused-safe":
                raise DurableRunnerError("paused-safe resume is missing its pause ack")
            _archive_unacknowledged_pause_request(run_dir, args.run_id)
        elif ack_exists:
            raise DurableRunnerError("resume has an orphan pause ack")
        _ensure_argument(trainer_args, "--resume-from-checkpoint", checkpoint["absolute_path"])

    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_log = logs_dir / "trainer.stdout.log"
    stderr_log = logs_dir / "trainer.stderr.log"
    command = [str(python), str(trainer), *trainer_args]
    logs = {"stdout": _log_receipt(run_dir, stdout_log),
            "stderr": _log_receipt(run_dir, stderr_log)}
    outputs = {"adapter": {"path": str(output_path)},
               "report": {"path": str(report_path)} if report_path else None}
    state = _base_state(args, command, inputs, logs, outputs,
                        "resuming" if args.resume_interrupted else "starting", previous)
    _write_state(run_dir, state)

    trainer_process: subprocess.Popen[bytes] | None = None
    try:
        with (stdout_log.open("ab", buffering=0) as stdout_stream,
              stderr_log.open("ab", buffering=0) as stderr_stream):
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
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

        if not resume_accepted:
            resume_accepted = _archive_accepted_pause_control(
                run_dir, args.run_id, inputs)
        if (requires_resume_acceptance and exit_code in {0, SAFE_PAUSE_EXIT_CODE}
                and not resume_accepted):
            raise DurableRunnerError(
                "trainer exited without a full-pin resume acceptance receipt")

        progress = _load_progress(run_dir, args.run_id)
        checkpoint = _checkpoint_from_progress(progress)
        if exit_code == SAFE_PAUSE_EXIT_CODE:
            _validate_safe_pause(run_dir, args.run_id, checkpoint, progress)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Durable AIRI behavior-training supervisor")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--trainer", type=Path, required=True)
    parser.add_argument("--working-directory", type=Path, required=True)
    parser.add_argument("--input-manifest-sha256", default="")
    parser.add_argument("--checkpoint-every-optimizer-steps", type=int, default=5)
    parser.add_argument("--heartbeat-seconds", type=float, default=10.0)
    parser.add_argument("--resume-interrupted", action="store_true")
    parser.add_argument("trainer_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.heartbeat_seconds <= 0 or args.heartbeat_seconds > 15:
        raise DurableRunnerError("heartbeat must be in (0, 15] seconds")
    if args.checkpoint_every_optimizer_steps <= 0:
        raise DurableRunnerError("checkpoint interval must be positive")
    with exclusive_run_lock(validate_local_run_dir(args.run_dir)):
        return run_supervisor(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DurableRunnerError as exc:
        print(f"durable training runner refused: {exc}", file=sys.stderr)
        raise SystemExit(2)
