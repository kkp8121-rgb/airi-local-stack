"""Fail-closed, offline evidence verifier for two completed CUDA QLoRA runs.

This program deliberately never starts a service or a CUDA workload.  Its PASS
receipt is an auditable comparison of already durable local run evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


EVENT_SCHEMA = "airi.behavior-checkpoint-event.v1"
RECEIPT_SCHEMA = "airi.behavior-gpu-equivalence-receipt.v1"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_GENERATION = re.compile(r"checkpoint-[0-9]{8}")
MAX_NORMAL_INTERVAL_SECONDS = 600.0
MIN_NORMAL_INTERVALS = 4
MAX_CHECKPOINT_PUBLISH_SECONDS = 600.0
WALL_MONOTONIC_SKEW_SECONDS = 5.0
COMPARATOR_SCHEMA = "airi.recursive-checkpoint-state-exact.v1"


class EquivalenceError(ValueError):
    """The supplied evidence is absent, non-local, or not equivalent."""


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


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


def _json_file(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EquivalenceError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict) or raw != _canonical(value):
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
        runner._validate_completed_outputs(state)
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
    return state


def _artifact_dir(state: Mapping[str, Any], explicit: Path | None, label: str) -> Path:
    if explicit is not None:
        return _local_dir(explicit, label)
    receipt = state.get("outputs", {}).get("adapter") if isinstance(state.get("outputs"), dict) else None
    if not isinstance(receipt, dict) or not isinstance(receipt.get("path"), str):
        raise EquivalenceError(f"{label} must be supplied when run-state has no adapter receipt")
    return _local_dir(Path(receipt["path"]), label)


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EquivalenceError("event timestamp is invalid")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise EquivalenceError("event timestamp is invalid") from exc


def _events(run_dir: Path, run_id: str, pins: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[float]]:
    checkpoint = _load_module("behavior_training_checkpoint.py", "airi_equivalence_checkpoint")
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
                "checkpoint_payload_sha256", "checkpoint_index_sha256", "checkpoint_index", "pins_sha256"}
    for expected_number, path in enumerate(files, start=1):
        event = _json_file(_local_file(path, "checkpoint event"), "checkpoint event")
        if set(event) != required or event.get("schema_version") != EVENT_SCHEMA or event.get("run_id") != run_id:
            raise EquivalenceError("checkpoint event schema or identity mismatch")
        generation = event.get("generation")
        expected_generation = f"checkpoint-{expected_number:08d}"
        if (not isinstance(generation, str) or not _GENERATION.fullmatch(generation)
                or generation != expected_generation or path.stem != generation):
            raise EquivalenceError("checkpoint event generation sequence is invalid")
        if (not isinstance(event.get("reason"), str) or not isinstance(event.get("microsteps_completed"), int)
                or not isinstance(event.get("optimizer_steps"), int) or event.get("pending_microbatches") != 0
                or not isinstance(event.get("publish_elapsed_ns"), int) or event["publish_elapsed_ns"] < 0
                or not isinstance(event.get("checkpoint_index"), dict)):
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
        for key in ("checkpoint_manifest_sha256", "checkpoint_payload_sha256", "checkpoint_index_sha256", "pins_sha256"):
            if not isinstance(event.get(key), str) or not _HEX64.fullmatch(event[key]):
                raise EquivalenceError("checkpoint event hash is invalid")
        generation_dir = run_dir / "checkpoints" / generation
        # Rotation legitimately archives older generations.  When its immutable
        # directory remains, re-verify it using the committed verifier; when it
        # has been rotated out, preserve the event receipt as the evidence.
        if generation_dir.is_dir() and not generation_dir.is_symlink():
            try:
                verified = checkpoint.verify_generation(run_dir, generation, dict(pins), run_id)
            except Exception as exc:
                raise EquivalenceError("checkpoint event generation fails committed verifier") from exc
            if (verified["manifest_sha256"] != event["checkpoint_manifest_sha256"]
                    or verified["manifest"]["payload"]["sha256"] != event["checkpoint_payload_sha256"]):
                raise EquivalenceError("checkpoint event hashes do not match durable generation")
        snapshot_latest = event["checkpoint_index"].get("latest")
        if (not isinstance(snapshot_latest, dict)
                or snapshot_latest.get("relative_path") != generation
                or snapshot_latest.get("manifest_sha256") != event["checkpoint_manifest_sha256"]):
            raise EquivalenceError("checkpoint event index snapshot does not name its generation")
        if (_sha256_bytes(_canonical(event["checkpoint_index"])) != event["checkpoint_index_sha256"]
                or _sha256_bytes(_canonical(dict(pins))) != event["pins_sha256"]):
            raise EquivalenceError("checkpoint event hashes do not match durable evidence")
        events.append(event)
    normal = [event for event in events if event["reason"] == "interval"]
    if not normal:
        raise EquivalenceError("no normal checkpoint intervals are available")
    durable_times = [_timestamp(event["checkpoint_durable_at_utc"]) for event in normal]
    # Conservative: include process startup-to-first publication only when the
    # state has a parseable creation timestamp; otherwise the first interval is omitted.
    intervals: list[float] = []
    try:
        created = _timestamp(_json_file(_local_file(run_dir / "run-state.json", "run-state"), "run-state")["created_at_utc"])
        intervals.append((durable_times[0] - created).total_seconds())
    except (EquivalenceError, KeyError):
        pass
    intervals.extend((right - left).total_seconds()
                     for left, right in zip(durable_times, durable_times[1:]))
    if any(not math.isfinite(value) or value < 0 for value in intervals):
        raise EquivalenceError("normal checkpoint timestamps moved backwards")
    return events, intervals


def _load_safetensors(path: Path) -> Mapping[str, Any]:
    try:
        from safetensors.torch import load_file
    except ImportError as exc:
        raise EquivalenceError("safetensors is required to compare adapter tensors") from exc
    return load_file(str(path), device="cpu")


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
                if key not in {"run_id", "checkpoint_generation"}}
    if isinstance(value, list):
        return [_normalise_state(item) for item in value]
    return value


def _compare_state(left: Any, right: Any, path: str = "state") -> None:
    if isinstance(left, dict) and isinstance(right, dict):
        left_keys = set(left) - {"run_id", "checkpoint_generation"}
        right_keys = set(right) - {"run_id", "checkpoint_generation"}
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
    checkpoint = _load_module("behavior_training_checkpoint.py", "airi_equivalence_latest")
    index = _json_file(_local_file(
        run_dir / "checkpoints" / "checkpoint-index.json", "checkpoint index"),
        "checkpoint index")
    latest = index.get("latest")
    if (not isinstance(latest, dict) or set(latest) != {"relative_path", "manifest_sha256"}
            or not isinstance(latest.get("relative_path"), str)):
        raise EquivalenceError("latest checkpoint index entry is invalid")
    try:
        verified = checkpoint.verify_generation(
            run_dir, latest["relative_path"], expected_run_id=run_id)
    except Exception as exc:
        raise EquivalenceError("latest checkpoint fails committed verification") from exc
    if verified["manifest_sha256"] != latest.get("manifest_sha256"):
        raise EquivalenceError("latest checkpoint index hash differs")
    return verified


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
        return torch.load(path, map_location="cpu", weights_only=True)
    except Exception as exc:
        raise EquivalenceError("latest checkpoint state cannot be loaded on CPU") from exc


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
                       tensor_loader: Callable[[Path], Mapping[str, Any]] = _load_safetensors,
                       state_loader: Callable[[Path, list[dict[str, Any]]], Any] = _latest_checkpoint_state) -> dict[str, Any]:
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
    resumed_events, _resumed_intervals = _events(resumed_dir, resumed["run_id"], pins)
    for label, events, latest in (
            ("baseline", baseline_events, baseline_latest),
            ("safe-pause/resume", resumed_events, resumed_latest)):
        latest_manifest = latest["manifest"]
        latest_payload = latest_manifest.get("payload") if isinstance(latest_manifest, dict) else None
        last_event = events[-1]
        if (last_event.get("generation") != latest_manifest.get("generation")
                or last_event.get("checkpoint_manifest_sha256") != latest["manifest_sha256"]
                or not isinstance(latest_payload, dict)
                or last_event.get("checkpoint_payload_sha256") != latest_payload.get("sha256")):
            raise EquivalenceError(
                f"{label} latest checkpoint lacks its exact durable event receipt")
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
    intervals = baseline_intervals
    if (len(intervals) < MIN_NORMAL_INTERVALS or not intervals
            or max(intervals) > MAX_NORMAL_INTERVAL_SECONDS):
        raise EquivalenceError("normal checkpoint interval evidence is insufficient or exceeds maximum")
    checkpoint = _load_module("behavior_training_checkpoint.py", "airi_equivalence_artifact")
    left_dir = _artifact_dir(baseline, baseline_adapter_dir, "baseline adapter")
    right_dir = _artifact_dir(resumed, resumed_adapter_dir, "resumed adapter")
    try:
        left_artifact = checkpoint.verify_artifact_directory(left_dir, dict(pins), baseline["run_id"])
        right_artifact = checkpoint.verify_artifact_directory(right_dir, dict(pins), resumed["run_id"])
    except Exception as exc:
        raise EquivalenceError("adapter artifact manifest verification failed") from exc
    baseline_report = _report_fields(baseline, left_artifact["manifest_sha256"], pins)
    resumed_report = _report_fields(resumed, right_artifact["manifest_sha256"], pins)
    if baseline_report != resumed_report:
        raise EquivalenceError("semantically relevant training report fields differ")
    left_weights, right_weights = left_dir / "adapter_model.safetensors", right_dir / "adapter_model.safetensors"
    report = _tensor_report(
        tensor_loader(_local_file(left_weights, "baseline safetensors")),
        tensor_loader(_local_file(right_weights, "resumed safetensors")))
    baseline_state = state_loader(baseline_dir, baseline_events)
    resumed_state = state_loader(resumed_dir, resumed_events)
    _compare_state(baseline_state, resumed_state)
    output = _local_file(receipt_path, "receipt", absent=True)
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
            "run_state_sha256": _sha256_file(baseline_dir / "run-state.json"),
            "adapter_manifest_sha256": left_artifact["manifest_sha256"],
            "latest_checkpoint_manifest_sha256": baseline_latest["manifest_sha256"],
            "latest_checkpoint_payload_sha256": baseline_payload_sha,
            "event_count": len(baseline_events),
        },
        "safe_pause_resume": {
            "run_id": resumed["run_id"],
            "run_state_sha256": _sha256_file(resumed_dir / "run-state.json"),
            "adapter_manifest_sha256": right_artifact["manifest_sha256"],
            "latest_checkpoint_manifest_sha256": resumed_latest["manifest_sha256"],
            "latest_checkpoint_payload_sha256": resumed_payload_sha,
            "event_count": len(resumed_events), "pause_history": pause_history,
            "safe_pause_event": {
                "generation": safe_pause_event["generation"],
                "checkpoint_manifest_sha256": safe_pause_event["checkpoint_manifest_sha256"],
                "microsteps_completed": safe_pause_event["microsteps_completed"],
                "optimizer_steps": safe_pause_event["optimizer_steps"],
                "pending_microbatches": safe_pause_event["pending_microbatches"],
            },
        },
        "input_pins_sha256": _sha256_bytes(_canonical(pins)),
        "expected_bindings": {
            "input_manifest_sha256": expected_input_manifest_sha256,
            "training_config_sha256": expected_training_config_sha256,
            "seed": expected_seed,
            "batch_size": expected_batch_size,
            "gradient_accumulation": expected_gradient_accumulation,
            "safe_pause_microsteps": expected_safe_pause_microsteps,
            "safe_pause_optimizer_step": expected_safe_pause_optimizer_step,
        },
        "max_normal_interval_seconds": max(intervals),
        "normal_interval_count": len(intervals),
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
