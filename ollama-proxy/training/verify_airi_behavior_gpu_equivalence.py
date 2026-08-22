"""Fail-closed, offline evidence verifier for two completed CUDA QLoRA runs.

This program deliberately never starts a service or a CUDA workload.  Its PASS
receipt is an auditable comparison of already durable local run evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import importlib.util
import json
import math
import os
import re
import stat
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


EVENT_SCHEMA = "airi.behavior-checkpoint-event.v2"
TRANSACTION_INDEX_SCHEMA = "airi.behavior-checkpoint-index.v2"
PRODUCER_EVIDENCE_ROOT_SCHEMA = "airi.behavior-producer-evidence-root.v1"
FINAL_EVIDENCE_ROOT_SCHEMA = "airi.behavior-final-evidence-root.v1"
RECEIPT_SCHEMA = "airi.behavior-gpu-equivalence-receipt.v1"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_GENERATION = re.compile(r"checkpoint-[0-9]{8}")
MAX_NORMAL_INTERVAL_SECONDS = 600.0
MIN_NORMAL_INTERVALS = 4
MAX_CHECKPOINT_PUBLISH_SECONDS = 600.0
WALL_MONOTONIC_SKEW_SECONDS = 5.0
COMPARATOR_SCHEMA = "airi.recursive-checkpoint-state-exact.v1"
_EVIDENCE_CUT: dict[Path, bytes] | None = None


class EquivalenceError(ValueError):
    """The supplied evidence is absent, non-local, or not equivalent."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    if _EVIDENCE_CUT is not None:
        return _sha256_bytes(_evidence_bytes(path, "evidence file"))
    return _sha256_bytes(_read_regular_file_snapshot(path, "evidence file")[1])


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_new_receipt(path: Path, value: Mapping[str, Any]) -> None:
    """Publish a fresh receipt atomically without ever replacing another file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _require_local_fixed_path(path.parent, "receipt parent")
    if path.parent.is_symlink():
        raise EquivalenceError("receipt parent cannot be linked")
    encoded = _canonical(dict(value))
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        if temporary.read_bytes() != encoded:
            raise EquivalenceError("receipt staging verification failed")
        if os.name == "nt":
            import ctypes  # noqa: PLC0415
            move_file = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
            move_file.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
            move_file.restype = ctypes.c_int
            # MOVEFILE_WRITE_THROUGH without REPLACE_EXISTING: a concurrent
            # creator wins and is never overwritten or deleted by this verifier.
            if not move_file(str(temporary), str(path), 0x8):
                error = ctypes.get_last_error()
                raise EquivalenceError(
                    f"fresh receipt publication failed with Windows error {error}")
        else:
            os.link(temporary, path)
            _fsync_directory(path.parent)
            temporary.unlink()
            _fsync_directory(path.parent)
        if path.read_bytes() != encoded:
            raise EquivalenceError("receipt atomic verification failed")
    except FileExistsError as exc:
        raise EquivalenceError("receipt path was created concurrently") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _require_local_fixed_path(path: Path, label: str) -> None:
    absolute = path.expanduser().absolute()
    rendered = str(path)
    if (rendered.startswith(("\\\\", "//"))
            or re.match(r"^[A-Za-z][A-Za-z0-9+.\-]+:[\\/]", rendered)):
        raise EquivalenceError(f"{label} must use a local fixed volume")
    if os.name == "nt":
        import ctypes  # noqa: PLC0415
        root = absolute.anchor
        if not root or ctypes.windll.kernel32.GetDriveTypeW(root) != 3:
            raise EquivalenceError(f"{label} must use a local fixed volume")
    probe = absolute
    while not os.path.lexists(probe):
        parent = probe.parent
        if parent == probe:
            raise EquivalenceError(f"{label} has no inspectable local ancestor")
        probe = parent
    for candidate in (probe, *probe.parents):
        try:
            attributes = getattr(os.lstat(candidate), "st_file_attributes", 0)
        except OSError as exc:
            raise EquivalenceError(f"{label} ancestor cannot be inspected") from exc
        if candidate.is_symlink() or attributes & 0x400:
            raise EquivalenceError(f"{label} cannot traverse a reparse point")


def _local_dir(value: Path, label: str) -> Path:
    absolute = value.expanduser().absolute()
    _require_local_fixed_path(absolute, label)
    path = absolute.resolve(strict=True)
    if not path.is_dir() or path.is_symlink():
        raise EquivalenceError(f"{label} must be a local regular directory")
    return path


def _local_file(value: Path, label: str, *, absent: bool = False) -> Path:
    absolute = value.expanduser().absolute()
    _require_local_fixed_path(absolute, label)
    path = absolute.resolve(strict=False)
    if path.exists() or os.path.lexists(path):
        if not path.is_file() or path.is_symlink():
            raise EquivalenceError(f"{label} must be a local regular file")
        return path.resolve(strict=True)
    if absent:
        return path
    raise EquivalenceError(f"{label} is missing")


def _read_regular_file_snapshot(value: Path, label: str) -> tuple[Path, bytes]:
    """Open, type-check, and read one regular-file handle exactly once."""

    absolute = value.expanduser().absolute()
    # Validate ancestry, then classify the target through this one handle.
    # Calling _local_file here would lstat the target before reopening it.
    _require_local_fixed_path(absolute.parent, f"{label} parent")
    path = absolute.parent.resolve(strict=True) / absolute.name
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
        handle = create_file(str(path), 0x80000000, 0x1 | 0x2, None, 3, 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise EquivalenceError(f"{label} is missing or cannot be opened safely")
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
            raise EquivalenceError(f"{label} handle cannot be classified")
        if info.attributes & 0x400:
            kernel.CloseHandle(handle)
            raise EquivalenceError(f"{label} must be a local regular file")
        try:
            descriptor = msvcrt.open_osfhandle(handle, flags)
        except OSError as exc:
            kernel.CloseHandle(handle)
            raise EquivalenceError(f"{label} handle cannot be adopted safely") from exc
        try:
            with os.fdopen(descriptor, "rb") as stream:
                return path, stream.read()
        except OSError as exc:
            raise EquivalenceError(f"{label} is missing or unreadable") from exc
    try:
        descriptor = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise EquivalenceError(f"{label} is missing or cannot be opened safely") from exc
    try:
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode)
                or getattr(metadata, "st_file_attributes", 0) & 0x400):
            raise EquivalenceError(f"{label} must be a local regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            return path, handle.read()
    finally:
        os.close(descriptor)


def _evidence_bytes(path: Path, label: str) -> bytes:
    """Return a process-wide immutable evidence cut while a PASS is assembled."""

    global _EVIDENCE_CUT
    if _EVIDENCE_CUT is None:
        return _read_regular_file_snapshot(path, label)[1]
    key = path.expanduser().absolute()
    if key in _EVIDENCE_CUT:
        return _EVIDENCE_CUT[key]
    resolved, raw = _read_regular_file_snapshot(path, label)
    _EVIDENCE_CUT[key] = raw
    _EVIDENCE_CUT.setdefault(resolved, raw)
    return raw


def _json_file(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = _evidence_bytes(path, label)
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EquivalenceError(f"{label} is not valid JSON") from exc
    try:
        canonical = _canonical(value)
    except (TypeError, ValueError) as exc:
        raise EquivalenceError(f"{label} contains non-canonical values") from exc
    if not isinstance(value, dict) or raw != canonical:
        raise EquivalenceError(f"{label} is not canonical JSON")
    return value


def _load_module(filename: str, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    if spec is None or spec.loader is None:
        raise EquivalenceError(f"cannot load committed durability module: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _completed_run(run_dir: Path) -> dict[str, Any]:
    runner = _load_module("durable_training_runner.py", "airi_equivalence_runner")
    try:
        state = _json_file(
            _local_file(run_dir / "run-state.json", "run-state"), "run-state")
        runner.validate_run_state(state)
    except Exception as exc:  # module errors are intentionally converted to refusal
        raise EquivalenceError("run-state cannot be verified by durability module") from exc
    if not isinstance(state, dict) or state.get("status") != "complete":
        raise EquivalenceError("run-state is not terminal complete")
    terminal = state.get("terminal")
    progress = state.get("progress")
    inputs = state.get("inputs")
    if (not isinstance(terminal, dict) or terminal.get("exit_code") != 0
            or not isinstance(progress, dict) or progress.get("pending_microbatches") != 0
            or not isinstance(inputs, dict) or not inputs):
        raise EquivalenceError("completed run-state terminal/progress/input pins are invalid")
    outputs = state.get("outputs")
    if (not isinstance(outputs, dict) or set(outputs) != {"adapter", "report"}
            or not isinstance(outputs.get("adapter"), dict)
            or not isinstance(outputs["adapter"].get("path"), str)):
        raise EquivalenceError("completed run outputs schema is invalid")
    return state


def _input_manifest_binding(state: Mapping[str, Any], expected_sha256: str,
                            expected_training_config_sha256: str) -> dict[str, str]:
    """Re-verify the completed run's durable manifest identity and bytes."""
    inputs = state.get("inputs")
    required = {"dataset_sha256", "model_weight_sha256", "trainer_source_sha256",
                "input_manifest_path", "input_manifest_sha256",
                "input_manifest_training_config_sha256", "checkpoint_helper_source_sha256"}
    if not isinstance(inputs, dict) or set(inputs) != required:
        raise EquivalenceError("completed run input manifest identity is malformed")
    recorded_path = inputs.get("input_manifest_path")
    recorded_sha256 = inputs.get("input_manifest_sha256")
    recorded_training_config_sha256 = inputs.get("input_manifest_training_config_sha256")
    if (not isinstance(recorded_path, str) or not recorded_path
            or not isinstance(recorded_sha256, str)
            or not _HEX64.fullmatch(recorded_sha256)
            or not isinstance(recorded_training_config_sha256, str)
            or not _HEX64.fullmatch(recorded_training_config_sha256)):
        raise EquivalenceError("completed run input manifest identity is malformed")
    manifest_path, raw = _read_regular_file_snapshot(
        Path(recorded_path), "completed run input manifest")
    canonical_path = str(manifest_path)
    if recorded_path != canonical_path:
        raise EquivalenceError("completed run input manifest path is not canonical")
    # Keep hash, UTF-8 decoding, canonical equality and all pins bound to one
    # byte snapshot; reopening here would reintroduce a path-replacement race.
    if _EVIDENCE_CUT is not None:
        _EVIDENCE_CUT[manifest_path] = raw
    actual_sha256 = _sha256_bytes(raw)
    if actual_sha256 != recorded_sha256 or actual_sha256 != expected_sha256:
        raise EquivalenceError("completed run input manifest bytes differ from the controlled target")
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EquivalenceError("completed run input manifest is not valid UTF-8 JSON") from exc
    try:
        if not isinstance(manifest, dict) or raw != _canonical(manifest):
            raise EquivalenceError("completed run input manifest is not canonical JSON")
    except (TypeError, ValueError) as exc:
        raise EquivalenceError("completed run input manifest contains non-canonical values") from exc
    required_manifest = {"schema_version", "dataset_sha256", "model_weight_sha256",
                         "trainer_source_sha256", "training_config", "training_config_sha256",
                         "checkpoint_helper_source_sha256", "model_inventory"}
    if (set(manifest) != required_manifest
            or manifest.get("schema_version") != "airi.behavior-input-manifest.v2"):
        raise EquivalenceError("completed run input manifest schema mismatch")
    config = manifest.get("training_config")
    config_keys = {"mode", "seed", "lora_r", "lora_alpha", "lora_dropout",
                   "learning_rate", "max_steps", "batch_size",
                   "gradient_accumulation", "max_seq_len",
                   "checkpoint_every_optimizer_steps", "deterministic_validation"}
    if not isinstance(config, dict) or set(config) != config_keys:
        raise EquivalenceError("completed run input manifest training configuration schema mismatch")
    if config.get("mode") not in {"cuda-qlora", "cpu-smoke"}:
        raise EquivalenceError("completed run input manifest training mode is invalid")
    for key in ("seed", "lora_r", "lora_alpha", "max_steps", "batch_size",
                "gradient_accumulation", "max_seq_len",
                "checkpoint_every_optimizer_steps"):
        if (not isinstance(config.get(key), int) or isinstance(config[key], bool)
                or config[key] <= 0):
            raise EquivalenceError("completed run input manifest training configuration is invalid")
    for key in ("lora_dropout", "learning_rate"):
        if not isinstance(config.get(key), float) or not math.isfinite(config[key]):
            raise EquivalenceError("completed run input manifest training configuration is non-finite")
    if (not 0 <= config["lora_dropout"] < 1 or config["learning_rate"] <= 0
            or not isinstance(config.get("deterministic_validation"), bool)):
        raise EquivalenceError("completed run input manifest training configuration is invalid")
    config_sha256 = _sha256_bytes(_canonical(config))
    if (not isinstance(manifest.get("training_config_sha256"), str)
            or not _HEX64.fullmatch(manifest["training_config_sha256"])
            or manifest["training_config_sha256"] != config_sha256):
        raise EquivalenceError("completed run input manifest training config hash is invalid")
    for key in ("dataset_sha256", "model_weight_sha256", "trainer_source_sha256"):
        if (not isinstance(manifest.get(key), str) or not _HEX64.fullmatch(manifest[key])
                or manifest[key] != inputs.get(key)):
            raise EquivalenceError(f"completed run input manifest pin differs: {key}")
    helper = manifest.get("checkpoint_helper_source_sha256")
    if (not isinstance(helper, str) or not _HEX64.fullmatch(helper)
            or helper != inputs.get("checkpoint_helper_source_sha256")):
        raise EquivalenceError("completed run input manifest checkpoint helper pin differs")
    inventory = manifest.get("model_inventory")
    if not isinstance(inventory, list) or not inventory:
        raise EquivalenceError("completed run input manifest model inventory is invalid")
    seen: set[str] = set()
    for row in inventory:
        if (not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}
                or not isinstance(row.get("path"), str) or not row["path"]
                or Path(row["path"]).is_absolute() or ".." in Path(row["path"]).parts
                or row["path"] in seen or not isinstance(row.get("bytes"), int)
                or isinstance(row["bytes"], bool) or row["bytes"] < 0
                or not isinstance(row.get("sha256"), str) or not _HEX64.fullmatch(row["sha256"])):
            raise EquivalenceError("completed run input manifest model inventory row is invalid")
        seen.add(row["path"])
    if (recorded_training_config_sha256 != config_sha256
            or config_sha256 != expected_training_config_sha256):
        raise EquivalenceError("completed run input manifest training config differs from the controlled target")
    return {"path": canonical_path, "sha256": actual_sha256,
            "training_config_sha256": recorded_training_config_sha256}


def _artifact_dir(state: Mapping[str, Any], explicit: Path | None, label: str) -> Path:
    if explicit is not None:
        return _local_dir(explicit, label)
    receipt = state.get("outputs", {}).get("adapter") if isinstance(state.get("outputs"), dict) else None
    if not isinstance(receipt, dict) or not isinstance(receipt.get("path"), str):
        raise EquivalenceError(f"{label} must be supplied when run-state has no adapter receipt")
    return _local_dir(Path(receipt["path"]), label)


def _verify_artifact_snapshot(directory: Path, pins: Mapping[str, Any],
                              run_id: str) -> dict[str, Any]:
    """Validate the closed adapter inventory from one immutable evidence cut."""

    directory = _local_dir(directory, "adapter artifact")
    manifest_path = _local_file(directory / "artifact-manifest.json", "adapter artifact manifest")
    manifest = _json_file(manifest_path, "adapter artifact manifest")
    if (set(manifest) != {"schema_version", "run_id", "pins", "files"}
            or manifest.get("schema_version") != "airi.behavior-adapter-artifact.v1"
            or manifest.get("run_id") != run_id or manifest.get("pins") != dict(pins)
            or not isinstance(manifest.get("files"), list) or not manifest["files"]):
        raise EquivalenceError("adapter artifact manifest schema, run_id, or pins mismatch")
    listed: set[str] = set()
    file_bytes: dict[str, bytes] = {}
    for entry in manifest["files"]:
        if (not isinstance(entry, dict) or set(entry) != {"path", "bytes", "sha256"}
                or not isinstance(entry.get("path"), str) or not entry["path"]
                or Path(entry["path"]).is_absolute() or ".." in Path(entry["path"]).parts
                or entry["path"] in listed or not isinstance(entry.get("bytes"), int)
                or entry["bytes"] < 0 or not isinstance(entry.get("sha256"), str)
                or not _HEX64.fullmatch(entry["sha256"])):
            raise EquivalenceError("adapter artifact file entry is invalid")
        listed.add(entry["path"])
        path = _local_file(directory / Path(entry["path"]), "adapter artifact file")
        data = _evidence_bytes(path, "adapter artifact file")
        if len(data) != entry["bytes"] or _sha256_bytes(data) != entry["sha256"]:
            raise EquivalenceError("adapter artifact file integrity mismatch")
        file_bytes[entry["path"]] = data
    entries = list(directory.rglob("*"))
    if any(path.is_symlink()
           or getattr(os.lstat(path), "st_file_attributes", 0) & 0x400
           for path in entries):
        raise EquivalenceError("adapter artifact inventory contains a linked entry")
    actual = {path.relative_to(directory).as_posix() for path in entries
              if path.is_file() and path.name != "artifact-manifest.json"}
    if actual != listed:
        raise EquivalenceError("adapter artifact file inventory mismatch")
    return {"manifest": manifest, "manifest_sha256": _sha256_bytes(_canonical(manifest)),
            "files": file_bytes}


def _bind_completed_output_receipts(state: Mapping[str, Any], directory: Path,
                                    artifact: Mapping[str, Any]) -> None:
    outputs = state["outputs"]
    adapter = outputs["adapter"]
    if not isinstance(adapter, dict) or adapter.get("path") != str(directory) or adapter.get("kind") != "directory":
        raise EquivalenceError("completed adapter output receipt is invalid")
    files = dict(artifact["files"])
    files["artifact-manifest.json"] = _evidence_bytes(
        directory / "artifact-manifest.json", "adapter artifact manifest")
    rows = [{"path": name, "size": len(data), "sha256": _sha256_bytes(data)}
            for name, data in sorted(files.items(), key=lambda item: Path(item[0]))]
    expected_adapter = {"path": str(directory), "kind": "directory", "files": rows,
                        "manifest_sha256": _sha256_bytes(_canonical(rows))}
    if adapter != expected_adapter:
        raise EquivalenceError("completed adapter output receipt differs from evidence cut")
    report = outputs.get("report")
    if report is None:
        return
    if not isinstance(report, dict) or report.get("kind") != "file" or not isinstance(report.get("path"), str):
        raise EquivalenceError("completed report output receipt is invalid")
    path = _local_file(Path(report["path"]), "training report")
    data = _evidence_bytes(path, "training report")
    expected_report = {"path": str(path), "kind": "file", "size": len(data),
                       "sha256": _sha256_bytes(data)}
    if report != expected_report:
        raise EquivalenceError("completed report output receipt differs from evidence cut")


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EquivalenceError("event timestamp is invalid")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise EquivalenceError("event timestamp is invalid") from exc


def _verify_generation_snapshot(run_dir: Path, generation: str,
                                pins: Mapping[str, Any] | None,
                                run_id: str) -> dict[str, Any]:
    """Verify checkpoint bytes from the same evidence cut used by the receipt."""

    manifest_path = run_dir / "checkpoints" / generation / "manifest.json"
    manifest = _json_file(_local_file(manifest_path, "checkpoint manifest"),
                          "checkpoint manifest")
    if (set(manifest) != {"schema_version", "generation", "run_id", "payload", "pins"}
            or manifest.get("schema_version") != 1
            or manifest.get("generation") != generation
            or manifest.get("run_id") != run_id):
        raise EquivalenceError("checkpoint manifest schema or identity mismatch")
    payload = manifest.get("payload")
    if (not isinstance(payload, dict) or set(payload) != {"name", "bytes", "sha256"}
            or payload.get("name") != "state.pt" or not isinstance(payload.get("bytes"), int)
            or payload["bytes"] < 1 or not isinstance(payload.get("sha256"), str)
            or not _HEX64.fullmatch(payload["sha256"])):
        raise EquivalenceError("checkpoint payload schema mismatch")
    data = _evidence_bytes(
        _local_file(manifest_path.parent / payload["name"], "checkpoint payload"),
        "checkpoint payload")
    if len(data) != payload["bytes"] or _sha256_bytes(data) != payload["sha256"]:
        raise EquivalenceError("checkpoint payload integrity mismatch")
    if pins is not None and manifest.get("pins") != dict(pins):
        raise EquivalenceError("checkpoint exact pins mismatch")
    return {"manifest": manifest, "payload": data,
            "manifest_sha256": _sha256_bytes(_canonical(manifest))}


def _events(run_dir: Path, run_id: str, pins: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[float]]:
    directory = run_dir / "checkpoint-events"
    if not directory.is_dir() or directory.is_symlink():
        raise EquivalenceError("checkpoint event directory is missing")
    files = sorted(directory.glob("checkpoint-????????.json"))
    if not files or len(files) != len(list(directory.iterdir())):
        raise EquivalenceError("checkpoint events must be the complete immutable event inventory")
    events: list[dict[str, Any]] = []
    required = {"schema_version", "run_id", "generation", "reason", "microsteps_completed",
                "optimizer_steps", "pending_microbatches", "publish_started_at_utc",
                "checkpoint_durable_at_utc", "publish_elapsed_ns", "checkpoint_manifest_sha256",
                "checkpoint_payload_sha256", "checkpoint_payload_progress", "pins_sha256",
                "previous_event_sha256", "previous_index_sha256", "training_elapsed_ns"}
    previous_raw: bytes | None = None
    previous_elapsed = 0
    for expected_number, path in enumerate(files, start=1):
        event = _json_file(_local_file(path, "checkpoint event"), "checkpoint event")
        if set(event) != required or event.get("schema_version") != EVENT_SCHEMA or event.get("run_id") != run_id:
            raise EquivalenceError("checkpoint event schema or identity mismatch")
        generation = event.get("generation")
        expected_generation = f"checkpoint-{expected_number:08d}"
        if (not isinstance(generation, str) or not _GENERATION.fullmatch(generation)
                or generation != expected_generation or path.stem != generation):
            raise EquivalenceError("checkpoint event generation sequence is invalid")
        if (not isinstance(event.get("reason"), str)
                or any(not isinstance(event.get(key), int) or isinstance(event[key], bool)
                       for key in ("microsteps_completed", "optimizer_steps", "pending_microbatches",
                                   "publish_elapsed_ns", "training_elapsed_ns"))
                or event.get("pending_microbatches") != 0
                or event["microsteps_completed"] < 0 or event["optimizer_steps"] < 0
                or event["publish_elapsed_ns"] < 0 or event["training_elapsed_ns"] < 0
                or not isinstance(event.get("checkpoint_payload_progress"), dict)):
            raise EquivalenceError("checkpoint event progress fields are invalid")
        if event["reason"] not in {"interval", "safe-pause", "epoch-tail", "epoch-complete"}:
            raise EquivalenceError("checkpoint event reason is invalid")
        started, durable = _timestamp(event["publish_started_at_utc"]), _timestamp(event["checkpoint_durable_at_utc"])
        if durable < started:
            raise EquivalenceError("checkpoint event durable timestamp precedes start")
        wall_seconds = (durable - started).total_seconds()
        monotonic_seconds = event["publish_elapsed_ns"] / 1_000_000_000
        if (not math.isfinite(wall_seconds) or not math.isfinite(monotonic_seconds)
                or wall_seconds < 0 or monotonic_seconds < 0
                or wall_seconds > MAX_CHECKPOINT_PUBLISH_SECONDS
                or monotonic_seconds > MAX_CHECKPOINT_PUBLISH_SECONDS
                or abs(wall_seconds - monotonic_seconds) > WALL_MONOTONIC_SKEW_SECONDS):
            raise EquivalenceError(
                "checkpoint event wall/monotonic timing is inconsistent or unbounded")
        for key in ("checkpoint_manifest_sha256", "checkpoint_payload_sha256", "pins_sha256"):
            if not isinstance(event.get(key), str) or not _HEX64.fullmatch(event[key]):
                raise EquivalenceError("checkpoint event hash is invalid")
        previous = event.get("previous_event_sha256")
        if ((previous_raw is None and previous is not None)
                or (previous_raw is not None and previous != _sha256_bytes(previous_raw))):
            raise EquivalenceError("checkpoint event retained hash chain is broken")
        if event["training_elapsed_ns"] < previous_elapsed:
            raise EquivalenceError("checkpoint event cumulative training elapsed moved backwards")
        if (event["previous_index_sha256"] is not None
                and (not isinstance(event["previous_index_sha256"], str)
                     or not _HEX64.fullmatch(event["previous_index_sha256"]))):
            raise EquivalenceError("checkpoint event predecessor index hash is invalid")
        generation_dir = run_dir / "checkpoints" / generation
        # Rotation legitimately archives older generations.  When its immutable
        # directory remains, re-verify it using the committed verifier; when it
        # has been rotated out, preserve the event receipt as the evidence.
        if generation_dir.is_dir() and not generation_dir.is_symlink():
            try:
                verified = _verify_generation_snapshot(run_dir, generation, pins, run_id)
            except Exception as exc:
                raise EquivalenceError("checkpoint event generation fails committed verifier") from exc
            if (verified["manifest_sha256"] != event["checkpoint_manifest_sha256"]
                    or verified["manifest"]["payload"]["sha256"] != event["checkpoint_payload_sha256"]):
                raise EquivalenceError("checkpoint event hashes do not match durable generation")
        payload_progress = event["checkpoint_payload_progress"]
        if (set(payload_progress) != {"microsteps_completed", "optimizer_steps", "pending_microbatches"}
                or any(not isinstance(payload_progress.get(key), int)
                       or isinstance(payload_progress[key], bool) for key in payload_progress)
                or any(payload_progress.get(key) != event.get(key) for key in payload_progress)):
            raise EquivalenceError("checkpoint event payload progress does not match event progress")
        if _sha256_bytes(_canonical(dict(pins))) != event["pins_sha256"]:
            raise EquivalenceError("checkpoint event hashes do not match durable evidence")
        events.append(event)
        previous_raw = _evidence_bytes(path, "checkpoint event")
        previous_elapsed = event["training_elapsed_ns"]
    normal = [event for event in events if event["reason"] == "interval"]
    if not normal:
        raise EquivalenceError("no normal checkpoint intervals are available")
    # Wall time is adjustable.  The production trainer carries one cumulative
    # monotonic clock across resume, so interval evidence is its consecutive
    # deltas (including startup-to-first publication).
    intervals = []
    elapsed = 0
    for event in events:
        current = event["training_elapsed_ns"]
        if event["reason"] == "interval":
            intervals.append((current - elapsed + event["publish_elapsed_ns"]) / 1_000_000_000)
        elapsed = current
    if any(not math.isfinite(value) or value < 0 for value in intervals):
        raise EquivalenceError("normal checkpoint timestamps moved backwards")
    return events, intervals


def _load_safetensors(payload: bytes) -> Mapping[str, Any]:
    try:
        from safetensors.torch import load_file
    except ImportError as exc:
        raise EquivalenceError("safetensors is required to compare adapter tensors") from exc
    try:
        from safetensors.torch import load
        return load(payload)
    except ImportError:
        # Older safetensors releases expose only the pathname API; fail closed
        # rather than reopening an evidence path outside this immutable cut.
        raise EquivalenceError("safetensors byte loader is required to compare adapter tensors")


def _tensor_report(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    if set(left) != set(right):
        raise EquivalenceError("adapter safetensor names differ")
    max_abs = max_rel = 0.0
    for name in sorted(left):
        a, b = left[name], right[name]
        if tuple(a.shape) != tuple(b.shape) or str(a.dtype) != str(b.dtype):
            raise EquivalenceError(f"adapter tensor metadata differs: {name}")
        try:
            difference = (a.detach().cpu().to(dtype=a.dtype) - b.detach().cpu().to(dtype=a.dtype)).abs()
            current_abs = float(difference.max().item()) if difference.numel() else 0.0
            denominator = b.detach().cpu().abs().clamp_min(1e-30)
            current_rel = float((difference / denominator).max().item()) if difference.numel() else 0.0
        except Exception as exc:
            raise EquivalenceError(f"adapter tensor is not numerically comparable: {name}") from exc
        max_abs, max_rel = max(max_abs, current_abs), max(max_rel, current_rel)
        import torch
        left_tensor, right_tensor = a.detach().cpu(), b.detach().cpu()
        if not torch.equal(left_tensor, right_tensor):
            raise EquivalenceError(f"adapter tensor is not exactly equal: {name}")
    return {"tensor_names": sorted(left), "tensor_count": len(left), "max_abs_diff": max_abs,
            "max_rel_diff": max_rel, "mode": "exact"}


def _normalise_state(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalise_state(item) for key, item in value.items()
                if key not in {"run_id", "checkpoint_generation", "training_elapsed_ns"}}
    if isinstance(value, list):
        return [_normalise_state(item) for item in value]
    return value


def _compare_state(left: Any, right: Any, path: str = "state") -> None:
    if isinstance(left, dict) and isinstance(right, dict):
        ignored = {"run_id", "checkpoint_generation", "training_elapsed_ns"}
        left_keys = set(left) - ignored
        right_keys = set(right) - ignored
        if left_keys != right_keys:
            raise EquivalenceError(f"latest checkpoint state keys differ at {path}")
        for key in sorted(left_keys):
            _compare_state(left[key], right[key], f"{path}.{key}")
        return
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        if type(left) is not type(right) or len(left) != len(right):
            raise EquivalenceError(f"latest checkpoint sequence differs at {path}")
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            _compare_state(left_item, right_item, f"{path}[{index}]")
        return
    if hasattr(left, "shape") and hasattr(left, "dtype"):
        if not hasattr(right, "shape") or tuple(left.shape) != tuple(right.shape) or str(left.dtype) != str(right.dtype):
            raise EquivalenceError(f"latest checkpoint tensor metadata differs at {path}")
        import torch
        left_tensor, right_tensor = left.detach().cpu(), right.detach().cpu()
        if not torch.equal(left_tensor, right_tensor):
            raise EquivalenceError(f"latest checkpoint tensor differs at {path}")
        return
    if isinstance(left, float) and isinstance(right, float):
        if left != right:
            raise EquivalenceError(f"latest checkpoint float differs at {path}")
        return
    if type(left) is not type(right) or left != right:
        raise EquivalenceError(f"latest checkpoint value differs at {path}")


def _latest_verified_generation(run_dir: Path, run_id: str) -> dict[str, Any]:
    index = _json_file(_local_file(
        run_dir / "checkpoints" / "checkpoint-index.json", "checkpoint index"),
        "checkpoint index")
    latest = index.get("latest")
    if (set(index) != {"schema_version", "run_id", "latest", "previous", "previous_index_sha256"}
            or index.get("schema_version") != TRANSACTION_INDEX_SCHEMA or index.get("run_id") != run_id
            or not isinstance(latest, dict)
            or set(latest) != {"relative_path", "manifest_sha256", "event_relative_path", "event_sha256"}
            or not isinstance(latest.get("relative_path"), str)):
        raise EquivalenceError("latest checkpoint index entry is invalid")
    for position in ("latest", "previous"):
        entry = index.get(position)
        if entry is None:
            continue
        if (not isinstance(entry, dict)
                or set(entry) != {"relative_path", "manifest_sha256", "event_relative_path", "event_sha256"}
                or not isinstance(entry.get("relative_path"), str)
                or not _GENERATION.fullmatch(entry["relative_path"])
                or entry.get("event_relative_path") != f"checkpoint-events/{entry['relative_path']}.json"
                or not all(isinstance(entry.get(key), str) and _HEX64.fullmatch(entry[key])
                           for key in ("manifest_sha256", "event_sha256"))):
            raise EquivalenceError("checkpoint index transaction entry is invalid")
    previous_index_sha = index.get("previous_index_sha256")
    if previous_index_sha is not None and (not isinstance(previous_index_sha, str)
                                           or not _HEX64.fullmatch(previous_index_sha)):
        raise EquivalenceError("checkpoint index predecessor hash is invalid")
    index_raw = _evidence_bytes(run_dir / "checkpoints" / "checkpoint-index.json", "checkpoint index")
    if not isinstance(latest.get("event_relative_path"), str) or not _HEX64.fullmatch(str(latest.get("event_sha256"))):
        raise EquivalenceError("latest checkpoint index lacks an event receipt")
    event_path = run_dir / latest["event_relative_path"]
    event_raw = _evidence_bytes(_local_file(event_path, "latest checkpoint event"), "latest checkpoint event")
    if _sha256_bytes(event_raw) != latest["event_sha256"]:
        raise EquivalenceError("latest checkpoint index event bytes differ")
    try:
        verified = _verify_generation_snapshot(
            run_dir, latest["relative_path"], None, run_id)
    except Exception as exc:
        raise EquivalenceError("latest checkpoint fails committed verification") from exc
    if verified["manifest_sha256"] != latest.get("manifest_sha256"):
        raise EquivalenceError("latest checkpoint index hash differs")
    return {**verified, "index": index, "index_sha256": _sha256_bytes(index_raw),
            "event_sha256": latest["event_sha256"]}


def _bind_current_index_event(run_dir: Path, latest: Mapping[str, Any],
                              event: Mapping[str, Any]) -> None:
    """Authenticate the non-circular final index over the already-published event."""
    index = latest.get("index")
    if not isinstance(index, dict) or not isinstance(index.get("latest"), dict):
        raise EquivalenceError("current checkpoint index is unavailable")
    current = index["latest"]
    if (current.get("relative_path") != event.get("generation")
            or current.get("manifest_sha256") != event.get("checkpoint_manifest_sha256")
            or current.get("event_sha256") != latest.get("event_sha256")):
        raise EquivalenceError("current checkpoint index does not bind the final event")
    previous = index.get("previous")
    if ((previous is None and event.get("previous_event_sha256") is not None)
            or (previous is not None and previous.get("event_sha256") != event.get("previous_event_sha256"))):
        raise EquivalenceError("current checkpoint index predecessor event differs")
    previous_sha = index.get("previous_index_sha256")
    if previous_sha != event.get("previous_index_sha256"):
        raise EquivalenceError("current checkpoint index predecessor hash differs")
    previous_path = run_dir / "checkpoints" / "checkpoint-index.prev.json"
    if previous_sha is None:
        if (previous is not None or event.get("previous_event_sha256") is not None
                or os.path.lexists(previous_path)):
            raise EquivalenceError("current checkpoint index has an unexpected predecessor")
        return
    if previous is None or event.get("previous_event_sha256") is None:
        raise EquivalenceError("current checkpoint index predecessor presence is inconsistent")
    previous_raw = _evidence_bytes(_local_file(previous_path, "previous checkpoint index"),
                                   "previous checkpoint index")
    if _sha256_bytes(previous_raw) != previous_sha:
        raise EquivalenceError("retained previous checkpoint index bytes differ")
    previous_index = _json_file(previous_path, "previous checkpoint index")
    if (set(previous_index) != {"schema_version", "run_id", "latest", "previous", "previous_index_sha256"}
            or previous_index.get("schema_version") != TRANSACTION_INDEX_SCHEMA
            or previous_index.get("run_id") != index.get("run_id")
            or previous_index.get("latest") != previous):
        raise EquivalenceError("retained previous checkpoint index lineage is invalid")
    for position in ("latest", "previous"):
        entry = previous_index.get(position)
        if entry is None:
            continue
        if (not isinstance(entry, dict)
                or set(entry) != {"relative_path", "manifest_sha256", "event_relative_path", "event_sha256"}
                or not isinstance(entry.get("relative_path"), str)
                or not _GENERATION.fullmatch(entry["relative_path"])
                or entry.get("event_relative_path") != f"checkpoint-events/{entry['relative_path']}.json"
                or not all(isinstance(entry.get(key), str) and _HEX64.fullmatch(entry[key])
                           for key in ("manifest_sha256", "event_sha256"))):
            raise EquivalenceError("retained previous checkpoint index entry is invalid")


def _latest_checkpoint_state(run_dir: Path, events: list[dict[str, Any]]) -> Any:
    index = _json_file(_local_file(run_dir / "checkpoints" / "checkpoint-index.json", "checkpoint index"), "checkpoint index")
    latest = index.get("latest")
    if not isinstance(latest, dict) or not isinstance(latest.get("relative_path"), str):
        raise EquivalenceError("latest checkpoint index entry is invalid")
    generation = latest["relative_path"]
    path = _local_file(
        run_dir / "checkpoints" / generation / "state.pt",
        "latest checkpoint state")
    try:
        import torch
        return torch.load(io.BytesIO(_evidence_bytes(path, "latest checkpoint state")),
                          map_location="cpu", weights_only=True)
    except Exception as exc:
        raise EquivalenceError("latest checkpoint state cannot be loaded on CPU") from exc


def _require_runner_progress_projection(state: Mapping[str, Any],
                                        progress: Mapping[str, Any]) -> None:
    expected = {key: progress.get(key) for key in (
        "epoch", "next_batch_index", "microsteps_completed", "optimizer_steps",
        "pending_microbatches")}
    if state.get("progress") != expected:
        raise EquivalenceError("completed run-state progress differs from completed progress projection")


def _closed_producer_evidence(state: Mapping[str, Any], run_dir: Path,
                              latest: Mapping[str, Any], last_event: Mapping[str, Any]) -> dict[str, Any]:
    """Require the producer and runner terminal receipts to name one evidence cut."""
    terminal = state.get("terminal")
    final_receipt = terminal.get("final_evidence_root") if isinstance(terminal, dict) else None
    if (not isinstance(final_receipt, dict)
            or set(final_receipt) != {"relative_path", "sha256", "state_projection_sha256"}
            or final_receipt.get("relative_path") != "final-evidence-root.json"
            or not all(isinstance(final_receipt.get(key), str) and _HEX64.fullmatch(final_receipt[key])
                       for key in ("sha256", "state_projection_sha256"))):
        raise EquivalenceError("completed run lacks a final producer evidence receipt")
    final_path = _local_file(run_dir / final_receipt["relative_path"], "final evidence root")
    final_raw = _evidence_bytes(final_path, "final evidence root")
    if _sha256_bytes(final_raw) != final_receipt["sha256"]:
        raise EquivalenceError("terminal final evidence receipt bytes differ")
    final = _json_file(final_path, "final evidence root")
    expected_final = {"schema_version", "run_id", "producer_evidence_root_sha256",
                      "checkpoint_index_sha256", "latest_event_sha256",
                      "completed_progress_sha256", "state_projection", "state_projection_sha256"}
    if set(final) != expected_final or final.get("schema_version") != FINAL_EVIDENCE_ROOT_SCHEMA:
        raise EquivalenceError("final evidence root schema mismatch")
    producer_path = _local_file(run_dir / "producer-evidence-root.json", "producer evidence root")
    producer_raw = _evidence_bytes(producer_path, "producer evidence root")
    producer = _json_file(producer_path, "producer evidence root")
    expected_producer = {"schema_version", "run_id", "checkpoint_index_sha256", "latest_checkpoint",
                         "adapter_artifact_manifest_sha256", "report_sha256", "progress"}
    if set(producer) != expected_producer or producer.get("schema_version") != PRODUCER_EVIDENCE_ROOT_SCHEMA:
        raise EquivalenceError("producer evidence root schema mismatch")
    progress_path = _local_file(run_dir / "progress.json", "completed progress")
    progress_raw = _evidence_bytes(progress_path, "completed progress")
    progress = _json_file(progress_path, "completed progress")
    required_progress = {"schema_version", "run_id", "status", "epoch", "next_batch_index",
                         "microsteps_completed", "optimizer_steps", "pending_microbatches",
                         "checkpoint", "updated_at_utc", "training_elapsed_ns"}
    if set(progress) != required_progress or progress.get("run_id") != state.get("run_id") or progress.get("status") != "completed":
        raise EquivalenceError("completed progress schema or identity is invalid")
    counters = {key: progress.get(key) for key in ("microsteps_completed", "optimizer_steps",
                                                     "pending_microbatches", "training_elapsed_ns")}
    if (any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counters.values())
            or counters["pending_microbatches"] != 0
            or producer.get("progress") != counters
            or any(last_event.get(key) != counters[key] for key in counters)):
        raise EquivalenceError("checkpoint event, completed progress, and run-state progress disagree")
    _require_runner_progress_projection(state, progress)
    if (producer.get("run_id") != state.get("run_id") or final.get("run_id") != state.get("run_id")
            or producer.get("checkpoint_index_sha256") != latest.get("index_sha256")
            or producer.get("latest_checkpoint") != latest.get("index", {}).get("latest")
            or final.get("producer_evidence_root_sha256") != _sha256_bytes(producer_raw)
            or final.get("checkpoint_index_sha256") != latest.get("index_sha256")
            or final.get("latest_event_sha256") != latest.get("event_sha256")
            or final.get("completed_progress_sha256") != _sha256_bytes(progress_raw)):
        raise EquivalenceError("producer evidence roots do not bind the current evidence generation")
    output_report = state.get("outputs", {}).get("report") if isinstance(state.get("outputs"), dict) else None
    if ((output_report is None and producer.get("report_sha256") is not None)
            or (isinstance(output_report, dict)
                and producer.get("report_sha256") != output_report.get("sha256"))):
        raise EquivalenceError("producer evidence root report receipt differs from final state")
    projection = final.get("state_projection")
    if (not isinstance(projection, dict)
            or _sha256_bytes(_canonical(projection)) != final.get("state_projection_sha256")
            or final.get("state_projection_sha256") != final_receipt["state_projection_sha256"]
            or projection.get("run_id") != state.get("run_id") or projection.get("status") != "complete"
            or projection.get("inputs") != state.get("inputs") or projection.get("outputs") != state.get("outputs")
            or projection.get("progress_sha256") != _sha256_bytes(progress_raw)
            or projection.get("producer_evidence_root_sha256") != _sha256_bytes(producer_raw)):
        raise EquivalenceError("final evidence root state projection is not closed")
    return {"producer_evidence_root_sha256": _sha256_bytes(producer_raw),
            "final_evidence_root_sha256": _sha256_bytes(final_raw),
            "completed_progress_sha256": _sha256_bytes(progress_raw),
            "adapter_artifact_manifest_sha256": producer["adapter_artifact_manifest_sha256"],
            "report_sha256": producer["report_sha256"]}


def _report_fields(state: Mapping[str, Any], artifact_manifest_sha256: str,
                   pins: Mapping[str, Any]) -> dict[str, Any]:
    outputs = state.get("outputs")
    receipt = outputs.get("report") if isinstance(outputs, dict) else None
    if not isinstance(receipt, dict) or not isinstance(receipt.get("path"), str):
        raise EquivalenceError("completed run lacks a report receipt")
    report = _json_file(_local_file(Path(receipt["path"]), "training report"), "training report")
    required = {"mode", "steps", "optimizer_steps", "checkpoint_every_optimizer_steps",
                "deterministic_validation", "determinism", "adapter_artifact_manifest_sha256",
                "dataset_sha256", "model_weight_sha256", "seed", "training_authorization",
                "adoption_authorized", "t3_status"}
    if not required.issubset(report) or report["mode"] != "cuda-qlora" or report["training_authorization"] is not True or report["adoption_authorized"] is not False or report["t3_status"] != "pending":
        raise EquivalenceError("training report semantic fields are invalid")
    if (report["adapter_artifact_manifest_sha256"] != artifact_manifest_sha256
            or report["dataset_sha256"] != pins.get("dataset_sha256")
            or report["model_weight_sha256"] != pins.get("model_weight_sha256")
            or not isinstance(report["steps"], int) or not isinstance(report["optimizer_steps"], int)
            or report["steps"] <= 0 or report["optimizer_steps"] <= 0
            or report["deterministic_validation"] is not True
            or report["determinism"] != pins.get("determinism")):
        raise EquivalenceError("training report identity fields are invalid")
    # The artifact-manifest hash intentionally differs because each durable
    # artifact contains its own run_id; it is validated above but is not a
    # behavioral comparison field.
    return {key: value for key, value in report.items()
            if key not in {"adapter_dir", "adapter_artifact_manifest_sha256",
                           "peak_cuda_memory_bytes"}}


def _bind_producer_output_hashes(label: str, state: Mapping[str, Any],
                                 artifact: Mapping[str, Any],
                                 evidence: Mapping[str, Any]) -> None:
    """Close producer-root output hashes over the verifier's byte snapshots."""
    report_receipt = state.get("outputs", {}).get("report") if isinstance(state.get("outputs"), dict) else None
    if (evidence.get("adapter_artifact_manifest_sha256") != artifact.get("manifest_sha256")
            or not isinstance(report_receipt, dict)
            or evidence.get("report_sha256") != report_receipt.get("sha256")):
        raise EquivalenceError(
            f"{label} producer evidence root output receipts differ from verified evidence")


def _safe_pause_history(run_dir: Path, run_id: str,
                        events: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    control = run_dir / "control"
    history = control / "history"
    for name in ("pause.request.json", "pause.ack.json", "resume.accepted.json"):
        if os.path.lexists(control / name):
            raise EquivalenceError(
                "safe-pause/resume run retains ambiguous live control evidence")
    if (not control.is_dir() or control.is_symlink()
            or {entry.name for entry in control.iterdir()} != {"history"}):
        raise EquivalenceError("safe-pause control inventory is not closed")
    history = _local_dir(history, "pause history")
    entries = list(history.iterdir())
    if any(not entry.is_file() or entry.is_symlink() for entry in entries):
        raise EquivalenceError("pause history contains a non-regular entry")
    requests = sorted(history.glob("*.request.json"))
    if len(requests) != 1:
        raise EquivalenceError("safe-pause/resume run must retain exactly one pause history triple")
    expected_names: set[str] = set()
    event_refs = {(event["generation"], event["checkpoint_manifest_sha256"])
                  for event in events if event["reason"] == "safe-pause"}
    inventory: list[dict[str, str]] = []
    for request_path in requests:
        request_id = request_path.name.removesuffix(".request.json")
        ack_path = history / f"{request_id}.ack.json"
        accepted_path = history / f"{request_id}.resume-accepted.json"
        expected_names.update({request_path.name, ack_path.name, accepted_path.name})
        request = _json_file(_local_file(request_path, "pause history request"), "pause history request")
        ack = _json_file(_local_file(ack_path, "pause history ack"), "pause history ack")
        accepted = _json_file(_local_file(accepted_path, "pause history acceptance"), "pause history acceptance")
        if (request != {"schema_version": "airi.behavior-pause-request.v1",
                        "run_id": run_id, "request_id": request_id}
                or set(ack) != {"schema_version", "run_id", "request_id",
                                "checkpoint_manifest_sha256", "checkpoint_relative_path",
                                "acknowledged_at_utc", "safe_to_power_off"}
                or set(accepted) != {"schema_version", "run_id", "request_id",
                                     "checkpoint_manifest_sha256", "checkpoint_relative_path"}
                or ack.get("schema_version") != "airi.behavior-pause-ack.v1"
                or accepted.get("schema_version") != "airi.behavior-resume-accepted.v1"
                or ack.get("run_id") != run_id or accepted.get("run_id") != run_id
                or ack.get("request_id") != request_id or accepted.get("request_id") != request_id
                or ack.get("safe_to_power_off") is not True
                or ack.get("checkpoint_relative_path") != accepted.get("checkpoint_relative_path")
                or ack.get("checkpoint_manifest_sha256") != accepted.get("checkpoint_manifest_sha256")
                or (ack.get("checkpoint_relative_path"), ack.get("checkpoint_manifest_sha256"))
                not in event_refs):
            raise EquivalenceError("safe-pause history does not bind an accepted checkpoint event")
        for path in (request_path, ack_path, accepted_path):
            inventory.append({"path": path.relative_to(run_dir).as_posix(),
                              "sha256": _sha256_file(path)})
    if {entry.name for entry in entries} != expected_names:
        raise EquivalenceError("pause history contains orphan or unexpected evidence")
    return inventory


def _require_no_safe_pause_evidence(run_dir: Path,
                                    events: Sequence[Mapping[str, Any]]) -> None:
    """An uninterrupted baseline must not retain any pause control evidence."""
    if any(event["reason"] == "safe-pause" for event in events):
        raise EquivalenceError("uninterrupted baseline contains a safe-pause event")
    control = run_dir / "control"
    if not os.path.lexists(control):
        return
    _require_local_fixed_path(control, "baseline control")
    if (not control.is_dir() or control.is_symlink()
            or any(control.iterdir())):
        raise EquivalenceError("uninterrupted baseline retains safe-pause control evidence")


def verify_equivalence(baseline_run_dir: Path, resumed_run_dir: Path, receipt_path: Path, *,
                       baseline_adapter_dir: Path | None = None, resumed_adapter_dir: Path | None = None,
                       expected_microsteps: int, expected_optimizer_steps: int,
                       expected_checkpoint_every_optimizer_steps: int,
                       expected_input_manifest_sha256: str,
                       expected_training_config_sha256: str,
                       expected_seed: int, expected_batch_size: int,
                       expected_gradient_accumulation: int,
                       expected_safe_pause_microsteps: int,
                       expected_safe_pause_optimizer_step: int,
                       tensor_loader: Callable[[bytes], Mapping[str, Any]] = _load_safetensors,
                       state_loader: Callable[[Path, list[dict[str, Any]]], Any] = _latest_checkpoint_state) -> dict[str, Any]:
    global _EVIDENCE_CUT
    _EVIDENCE_CUT = {}
    # These hooks made synthetic unit fixtures capable of manufacturing an
    # otherwise publishable PASS.  They remain visible only to fail closed for
    # callers using the old API; production always uses committed byte loaders.
    if tensor_loader is not _load_safetensors or state_loader is not _latest_checkpoint_state:
        raise EquivalenceError("non-production injected evidence loaders cannot publish a PASS")
    if (expected_microsteps <= 0 or expected_optimizer_steps <= 0
            or expected_checkpoint_every_optimizer_steps <= 0 or expected_seed <= 0
            or expected_batch_size <= 0 or expected_gradient_accumulation <= 0
            or expected_safe_pause_microsteps <= 0
            or expected_safe_pause_optimizer_step <= 0
            or expected_safe_pause_microsteps
            != expected_safe_pause_optimizer_step * expected_gradient_accumulation):
        raise EquivalenceError("controlled run arguments are invalid")
    if (not isinstance(expected_input_manifest_sha256, str)
            or not _HEX64.fullmatch(expected_input_manifest_sha256)
            or not isinstance(expected_training_config_sha256, str)
            or not _HEX64.fullmatch(expected_training_config_sha256)):
        raise EquivalenceError("controlled input or training config SHA-256 is invalid")
    baseline_dir, resumed_dir = _local_dir(baseline_run_dir, "baseline run"), _local_dir(resumed_run_dir, "resumed run")
    if baseline_dir == resumed_dir:
        raise EquivalenceError("baseline and resumed runs must be distinct")
    baseline, resumed = _completed_run(baseline_dir), _completed_run(resumed_dir)
    baseline_manifest = _input_manifest_binding(
        baseline, expected_input_manifest_sha256, expected_training_config_sha256)
    resumed_manifest = _input_manifest_binding(
        resumed, expected_input_manifest_sha256, expected_training_config_sha256)
    if baseline_manifest["path"] != resumed_manifest["path"]:
        raise EquivalenceError("completed runs bind different canonical input manifest paths")
    if baseline.get("inputs") != resumed.get("inputs"):
        raise EquivalenceError("completed run input pins differ")
    if baseline["inputs"].get("input_manifest_sha256") != expected_input_manifest_sha256:
        raise EquivalenceError("completed run input manifest differs from the controlled target")
    for state in (baseline, resumed):
        progress = state["progress"]
        if (progress.get("microsteps_completed") != expected_microsteps
                or progress.get("optimizer_steps") != expected_optimizer_steps):
            raise EquivalenceError("completed run progress differs from the controlled target")
    baseline_latest = _latest_verified_generation(baseline_dir, baseline["run_id"])
    resumed_latest = _latest_verified_generation(resumed_dir, resumed["run_id"])
    pins = baseline_latest["manifest"]["pins"]
    if pins != resumed_latest["manifest"]["pins"]:
        raise EquivalenceError("full checkpoint pins differ")
    config = pins.get("config") if isinstance(pins, dict) else None
    determinism = pins.get("determinism") if isinstance(pins, dict) else None
    expected_determinism = {
        "validation_enabled": True,
        "algorithms_enabled": True,
        "cudnn_deterministic": True,
        "cudnn_benchmark": False,
        "cudnn_allow_tf32": False,
        "cuda_matmul_allow_tf32": False,
        "cublas_workspace_config": ":4096:8",
    }
    cuda_identity = pins.get("cuda_identity") if isinstance(pins, dict) else None
    quantization = pins.get("quantization") if isinstance(pins, dict) else None
    if (not isinstance(config, dict) or config.get("mode") != "cuda-qlora"
            or config.get("max_steps") != expected_microsteps
            or config.get("checkpoint_every_optimizer_steps") != expected_checkpoint_every_optimizer_steps
            or config.get("seed") != expected_seed
            or config.get("batch_size") != expected_batch_size
            or config.get("gradient_accumulation") != expected_gradient_accumulation
            or config.get("deterministic_validation") is not True
            or determinism != expected_determinism
            or not isinstance(cuda_identity, dict)
            or set(cuda_identity) != {"torch_cuda_runtime", "device_name",
                                      "device_capability", "total_memory_bytes"}
            or not isinstance(cuda_identity.get("torch_cuda_runtime"), str)
            or not cuda_identity["torch_cuda_runtime"]
            or not isinstance(cuda_identity.get("device_name"), str)
            or not cuda_identity["device_name"]
            or not isinstance(cuda_identity.get("device_capability"), list)
            or len(cuda_identity["device_capability"]) != 2
            or not all(isinstance(value, int) and value >= 0
                       for value in cuda_identity["device_capability"])
            or not isinstance(cuda_identity.get("total_memory_bytes"), int)
            or cuda_identity["total_memory_bytes"] <= 0
            or quantization != {"load_in_4bit": True, "quant_type": "nf4",
                                "double_quant": True,
                                "compute_dtype": "bfloat16"}):
        raise EquivalenceError("controlled CUDA determinism or checkpoint interval pins are invalid")
    if _sha256_bytes(_canonical(config)) != expected_training_config_sha256:
        raise EquivalenceError("full checkpoint training config differs from the controlled target")
    for key in ("dataset_sha256", "model_weight_sha256", "trainer_source_sha256"):
        if baseline["inputs"].get(key) != pins.get(key):
            raise EquivalenceError(f"run-state and full checkpoint pin differ: {key}")
    baseline_events, baseline_intervals = _events(baseline_dir, baseline["run_id"], pins)
    resumed_events, resumed_intervals = _events(resumed_dir, resumed["run_id"], pins)
    closed_evidence: dict[str, dict[str, str]] = {}
    for label, state, events, latest in (
            ("baseline", baseline, baseline_events, baseline_latest),
            ("safe-pause/resume", resumed, resumed_events, resumed_latest)):
        latest_manifest = latest["manifest"]
        latest_payload = latest_manifest.get("payload") if isinstance(latest_manifest, dict) else None
        last_event = events[-1]
        expected_checkpoint = {"relative_path": latest_manifest.get("generation"),
                               "manifest_sha256": latest["manifest_sha256"]}
        if (last_event.get("generation") != latest_manifest.get("generation")
                or last_event.get("checkpoint_manifest_sha256") != latest["manifest_sha256"]
                or not isinstance(latest_payload, dict)
                or last_event.get("checkpoint_payload_sha256") != latest_payload.get("sha256")
                or state.get("checkpoint") != expected_checkpoint):
            raise EquivalenceError(
                f"{label} run-state/latest checkpoint lacks its exact durable event receipt")
    _require_no_safe_pause_evidence(baseline_dir, baseline_events)
    safe_pause_events = [event for event in resumed_events if event["reason"] == "safe-pause"]
    if len(safe_pause_events) != 1:
        raise EquivalenceError("safe-pause/resume run must retain exactly one safe-pause event")
    safe_pause_event = safe_pause_events[0]
    if (safe_pause_event.get("microsteps_completed") != expected_safe_pause_microsteps
            or safe_pause_event.get("optimizer_steps") != expected_safe_pause_optimizer_step
            or safe_pause_event.get("pending_microbatches") != 0):
        raise EquivalenceError("safe-pause event progress differs from the controlled target")
    pause_history = _safe_pause_history(resumed_dir, resumed["run_id"], resumed_events)
    for label, intervals in (("baseline", baseline_intervals),
                             ("safe-pause/resume", resumed_intervals)):
        if (len(intervals) < MIN_NORMAL_INTERVALS or not intervals
                or max(intervals) > MAX_NORMAL_INTERVAL_SECONDS):
            raise EquivalenceError(
                f"{label} normal checkpoint interval evidence is insufficient or exceeds maximum")
    for label, events, latest, directory in (("baseline", baseline_events, baseline_latest, baseline_dir),
                                             ("safe-pause/resume", resumed_events, resumed_latest, resumed_dir)):
        _bind_current_index_event(directory, latest, events[-1])
    for label, events in (("baseline", baseline_events),
                          ("safe-pause/resume", resumed_events)):
        final_event = events[-1]
        if (final_event.get("microsteps_completed") != expected_microsteps
                or final_event.get("optimizer_steps") != expected_optimizer_steps
                or final_event.get("pending_microbatches") != 0):
            raise EquivalenceError(f"{label} final checkpoint event progress differs from the controlled target")
    for label, state, events, latest, directory in (
            ("baseline", baseline, baseline_events, baseline_latest, baseline_dir),
            ("safe-pause/resume", resumed, resumed_events, resumed_latest, resumed_dir)):
        closed_evidence[label] = _closed_producer_evidence(state, directory, latest, events[-1])
    left_dir = _artifact_dir(baseline, baseline_adapter_dir, "baseline adapter")
    right_dir = _artifact_dir(resumed, resumed_adapter_dir, "resumed adapter")
    try:
        left_artifact = _verify_artifact_snapshot(left_dir, pins, baseline["run_id"])
        right_artifact = _verify_artifact_snapshot(right_dir, pins, resumed["run_id"])
    except Exception as exc:
        raise EquivalenceError("adapter artifact manifest verification failed") from exc
    if "outputs" in baseline:
        _bind_completed_output_receipts(baseline, left_dir, left_artifact)
    if "outputs" in resumed:
        _bind_completed_output_receipts(resumed, right_dir, right_artifact)
    for label, artifact, state in (("baseline", left_artifact, baseline),
                                   ("safe-pause/resume", right_artifact, resumed)):
        _bind_producer_output_hashes(label, state, artifact, closed_evidence[label])
    baseline_report = _report_fields(baseline, left_artifact["manifest_sha256"], pins)
    resumed_report = _report_fields(resumed, right_artifact["manifest_sha256"], pins)
    if baseline_report != resumed_report:
        raise EquivalenceError("semantically relevant training report fields differ")
    if (baseline_report.get("steps") != expected_microsteps
            or baseline_report.get("optimizer_steps") != expected_optimizer_steps
            or baseline_report.get("checkpoint_every_optimizer_steps")
            != expected_checkpoint_every_optimizer_steps):
        raise EquivalenceError("training report progress differs from the controlled target")
    try:
        left_weights = left_artifact["files"]["adapter_model.safetensors"]
        right_weights = right_artifact["files"]["adapter_model.safetensors"]
    except KeyError as exc:
        raise EquivalenceError("adapter artifact lacks adapter_model.safetensors") from exc
    report = _tensor_report(
        tensor_loader(left_weights), tensor_loader(right_weights))
    baseline_state = state_loader(baseline_dir, baseline_events)
    resumed_state = state_loader(resumed_dir, resumed_events)
    _compare_state(baseline_state, resumed_state)
    output = _local_file(receipt_path, "receipt", absent=True)
    # The evidence receipt must never become evidence inside either run or an
    # explicit/derived adapter tree (including its control/checkpoint/log trees).
    protected = [baseline_dir, resumed_dir, left_dir, right_dir]
    if any(output.is_relative_to(root) for root in protected):
        raise EquivalenceError("receipt path must be outside all run and adapter evidence trees")
    if output.parent.exists() and output.parent.is_symlink():
        raise EquivalenceError("receipt parent cannot be linked")
    if output.exists() or os.path.lexists(output):
        raise EquivalenceError("receipt path must be fresh")
    baseline_payload_sha = baseline_latest["manifest"]["payload"]["sha256"]
    resumed_payload_sha = resumed_latest["manifest"]["payload"]["sha256"]
    evidence = {
        "schema_version": RECEIPT_SCHEMA, "pass": True,
        "adoption_authorized": False,
        "baseline": {
            "run_id": baseline["run_id"],
            "run_state_sha256": _sha256_bytes(_evidence_bytes(
                baseline_dir / "run-state.json", "run-state")),
            "adapter_manifest_sha256": left_artifact["manifest_sha256"],
            "latest_checkpoint_manifest_sha256": baseline_latest["manifest_sha256"],
            "latest_checkpoint_payload_sha256": baseline_payload_sha,
            "event_count": len(baseline_events),
            "evidence_generation": closed_evidence["baseline"],
        },
        "safe_pause_resume": {
            "run_id": resumed["run_id"],
            "run_state_sha256": _sha256_bytes(_evidence_bytes(
                resumed_dir / "run-state.json", "run-state")),
            "adapter_manifest_sha256": right_artifact["manifest_sha256"],
            "latest_checkpoint_manifest_sha256": resumed_latest["manifest_sha256"],
            "latest_checkpoint_payload_sha256": resumed_payload_sha,
            "event_count": len(resumed_events), "pause_history": pause_history,
            "evidence_generation": closed_evidence["safe-pause/resume"],
            "safe_pause_event": {
                "generation": safe_pause_event["generation"],
                "checkpoint_manifest_sha256": safe_pause_event["checkpoint_manifest_sha256"],
                "microsteps_completed": safe_pause_event["microsteps_completed"],
                "optimizer_steps": safe_pause_event["optimizer_steps"],
                "pending_microbatches": safe_pause_event["pending_microbatches"],
            },
        },
        "input_pins_sha256": _sha256_bytes(_canonical(pins)),
        "input_manifest": baseline_manifest,
        "expected_bindings": {
            "input_manifest_sha256": expected_input_manifest_sha256,
            "training_config_sha256": expected_training_config_sha256,
            "seed": expected_seed,
            "batch_size": expected_batch_size,
            "gradient_accumulation": expected_gradient_accumulation,
            "safe_pause_microsteps": expected_safe_pause_microsteps,
            "safe_pause_optimizer_step": expected_safe_pause_optimizer_step,
        },
        "max_normal_interval_seconds": max(max(baseline_intervals), max(resumed_intervals)),
        "normal_interval_count": min(len(baseline_intervals), len(resumed_intervals)),
        "normal_interval_gate_seconds": MAX_NORMAL_INTERVAL_SECONDS,
        "normal_interval_gate_count": MIN_NORMAL_INTERVALS,
        "comparison": report, "report_fields": baseline_report,
        "comparator": {
            "schema_version": COMPARATOR_SCHEMA,
            "source_sha256": _sha256_file(Path(__file__)),
            "exact": True, "atol": 0.0, "rtol": 0.0,
            "checkpoint_loader_weights_only": True,
        },
    }
    try:
        _atomic_new_receipt(output, evidence)
    except Exception as exc:
        if isinstance(exc, EquivalenceError):
            raise
        raise EquivalenceError("receipt atomic publication failed") from exc
    return evidence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run-dir", type=Path, required=True)
    parser.add_argument("--safe-pause-resume-run-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--baseline-adapter-dir", type=Path)
    parser.add_argument("--safe-pause-resume-adapter-dir", type=Path)
    parser.add_argument("--expected-microsteps", type=int, required=True)
    parser.add_argument("--expected-optimizer-steps", type=int, required=True)
    parser.add_argument("--expected-checkpoint-every-optimizer-steps", type=int, required=True)
    parser.add_argument("--expected-input-manifest-sha256", required=True)
    parser.add_argument("--expected-training-config-sha256", required=True)
    parser.add_argument("--expected-seed", type=int, required=True)
    parser.add_argument("--expected-batch-size", type=int, required=True)
    parser.add_argument("--expected-gradient-accumulation", type=int, required=True)
    parser.add_argument("--expected-safe-pause-microsteps", type=int, required=True)
    parser.add_argument("--expected-safe-pause-optimizer-step", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        verify_equivalence(args.baseline_run_dir, args.safe_pause_resume_run_dir, args.receipt,
                           baseline_adapter_dir=args.baseline_adapter_dir, resumed_adapter_dir=args.safe_pause_resume_adapter_dir,
                           expected_microsteps=args.expected_microsteps,
                           expected_optimizer_steps=args.expected_optimizer_steps,
                           expected_checkpoint_every_optimizer_steps=args.expected_checkpoint_every_optimizer_steps,
                           expected_input_manifest_sha256=args.expected_input_manifest_sha256,
                           expected_training_config_sha256=args.expected_training_config_sha256,
                           expected_seed=args.expected_seed,
                           expected_batch_size=args.expected_batch_size,
                           expected_gradient_accumulation=args.expected_gradient_accumulation,
                           expected_safe_pause_microsteps=args.expected_safe_pause_microsteps,
                           expected_safe_pause_optimizer_step=args.expected_safe_pause_optimizer_step)
    except EquivalenceError as exc:
        print(f"GPU equivalence verification refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
