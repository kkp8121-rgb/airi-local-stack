"""Behavior LoRA trainer — CUDA QLoRA for production, a bounded CPU smoke for plumbing.

This is the T2-b counterpart of the behavior data pipeline. It consumes a
locally generated chat-format export pinned by SHA-256. Authorization and
review provenance stay explicit in the dataset rather than being inferred by
the trainer; the trainer never invents a human-review claim. Labels mask
everything before the assistant turn, so the model learns only the authorized
assistant target rather than the prompt itself.

Two modes, deliberately asymmetric:

- ``cuda-qlora`` is the production path — 4-bit NF4 via bitsandbytes,
  adapter-only output, CUDA required. This box is GPU-less, so that path is
  exercised on the codex machine; everything up to the backward pass is shared
  code verified here.
- ``cpu-smoke`` exists to validate the pipeline, not the model: it hard-caps
  samples and steps, runs a plain LoRA on whatever tiny local model it is
  given, and asserts the loss actually fell. Its output directory is suffixed
  ``-SMOKE`` and its report says it is not a training authorization.

Like the style trainer, it is local-only: model paths must be local
directories, never hub names or network paths.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import os
import re
import sys
import random
import stat
import time
from datetime import UTC, datetime
from collections import Counter
from pathlib import Path
from typing import Any

# Tests load this file by path; direct script execution has the same parent on
# sys.path, so make that relationship explicit without requiring a package.
if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent))
from behavior_training_checkpoint import (
    CheckpointError, atomic_json, load_generation, publish_artifact_directory,
    publish_checkpoint,
)

CPU_SMOKE_MAX_SAMPLES = 16
CPU_SMOKE_MAX_STEPS = 20
DEFAULTS = {
    "lora_r": 16, "lora_alpha": 32, "lora_dropout": 0.05,
    "learning_rate": 2e-4, "max_steps": 300, "batch_size": 2,
    "gradient_accumulation": 8, "max_seq_len": 1024,
}


class BehaviorTrainingError(ValueError):
    """Fail closed on anything that is not a pinned, reviewed, local setup."""


class PauseRequested(SystemExit):
    """A verified checkpoint made it safe for the durable runner to stop."""


CONTROL_SCHEMA_VERSION = 1
CHECKPOINT_EVENT_SCHEMA = "airi.behavior-checkpoint-event.v1"
DETERMINISTIC_CUBLAS_WORKSPACE = ":4096:8"


def _file_sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _prepare_deterministic_validation(enabled: bool) -> None:
    if not enabled:
        return
    existing = os.environ.get("CUBLAS_WORKSPACE_CONFIG")
    if existing not in {None, DETERMINISTIC_CUBLAS_WORKSPACE}:
        raise BehaviorTrainingError(
            "deterministic validation requires CUBLAS_WORKSPACE_CONFIG=:4096:8")
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = DETERMINISTIC_CUBLAS_WORKSPACE


def _configure_deterministic_validation(torch: Any, enabled: bool) -> None:
    if not enabled:
        return
    _prepare_deterministic_validation(True)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cuda.matmul.allow_tf32 = False


def _publish_checkpoint_event(
        run_dir: Path, run_id: str, generation: str, reason: str,
        microsteps_completed: int, optimizer_steps: int, pending_microbatches: int,
        publish_started_at_utc: str, checkpoint_durable_at_utc: str,
        publish_elapsed_ns: int, published: dict[str, Any], pins: dict[str, Any]) -> dict[str, Any]:
    """Bind wall-clock timing to a fully verified, durably indexed generation."""
    if (not re.fullmatch(r"checkpoint-[0-9]{8}", generation)
            or reason not in {"interval", "safe-pause", "epoch-tail", "epoch-complete"}
            or microsteps_completed < 0 or optimizer_steps < 0
            or pending_microbatches != 0 or publish_elapsed_ns < 0):
        raise BehaviorTrainingError("checkpoint event identity or progress is invalid")
    index_path = run_dir / "checkpoints" / "checkpoint-index.json"
    try:
        index_bytes = index_path.read_bytes()
        index = json.loads(index_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BehaviorTrainingError("checkpoint event cannot read durable index") from exc
    if index_bytes != _canonical_json_bytes(index):
        raise BehaviorTrainingError("checkpoint event index is not canonical")
    latest = index.get("latest") if isinstance(index, dict) else None
    manifest_sha256 = published.get("manifest_sha256")
    manifest = published.get("manifest")
    payload = manifest.get("payload") if isinstance(manifest, dict) else None
    if (not isinstance(latest, dict)
            or latest.get("relative_path") != generation
            or latest.get("manifest_sha256") != manifest_sha256
            or not isinstance(payload, dict)
            or not re.fullmatch(r"[0-9a-f]{64}", str(payload.get("sha256", "")))):
        raise BehaviorTrainingError("checkpoint event does not match durable generation")
    event = {
        "schema_version": CHECKPOINT_EVENT_SCHEMA,
        "run_id": run_id,
        "generation": generation,
        "reason": reason,
        "microsteps_completed": microsteps_completed,
        "optimizer_steps": optimizer_steps,
        "pending_microbatches": pending_microbatches,
        "publish_started_at_utc": publish_started_at_utc,
        "checkpoint_durable_at_utc": checkpoint_durable_at_utc,
        "publish_elapsed_ns": publish_elapsed_ns,
        "checkpoint_manifest_sha256": manifest_sha256,
        "checkpoint_payload_sha256": payload["sha256"],
        "checkpoint_index_sha256": hashlib.sha256(index_bytes).hexdigest(),
        "checkpoint_index": index,
        "pins_sha256": hashlib.sha256(_canonical_json_bytes(pins)).hexdigest(),
    }
    event_path = run_dir / "checkpoint-events" / f"{generation}.json"
    if os.path.lexists(event_path):
        raise BehaviorTrainingError("checkpoint event generation already exists")
    atomic_json(event_path, event)
    encoded = _canonical_json_bytes(event)
    if event_path.read_bytes() != encoded:
        raise BehaviorTrainingError("checkpoint event publication verification failed")
    return {"relative_path": event_path.relative_to(run_dir).as_posix(),
            "sha256": hashlib.sha256(encoded).hexdigest(), "event": event}


def _source_pins(args: argparse.Namespace, model_dir: Path, tokenizer: Any) -> dict[str, Any]:
    """Pins are intentionally exact: a resume never quietly changes inputs."""
    import torch

    tokenizer_files = sorted(path for path in model_dir.iterdir()
                             if path.is_file() and ("token" in path.name or path.name in {"special_tokens_map.json", "config.json"}))
    weights = sorted(model_dir.glob("*.safetensors"))
    local_weight = _file_sha256(weights[0]) if len(weights) == 1 else "cpu-smoke-weight-unavailable"
    versions = {"python": sys.version.split()[0], "torch": torch.__version__,
                "transformers": importlib.metadata.version("transformers"),
                "peft": importlib.metadata.version("peft")}
    cuda_identity = None
    quantization = None
    if args.mode == "cuda-qlora":
        versions["bitsandbytes"] = importlib.metadata.version("bitsandbytes")
        properties = torch.cuda.get_device_properties(0)
        cuda_identity = {
            "torch_cuda_runtime": torch.version.cuda,
            "device_name": properties.name,
            "device_capability": list(torch.cuda.get_device_capability(0)),
            "total_memory_bytes": int(properties.total_memory),
        }
        quantization = {"load_in_4bit": True, "quant_type": "nf4",
                        "double_quant": True, "compute_dtype": "bfloat16"}
    return {
        "dataset_sha256": args.dataset_sha256,
        "model_weight_sha256": args.model_sha256 if args.mode == "cuda-qlora" else local_weight,
        "model_config_sha256": _file_sha256(model_dir / "config.json"),
        "tokenizer_files": {path.name: _file_sha256(path) for path in tokenizer_files},
        "trainer_source_sha256": _file_sha256(Path(__file__)),
        "versions": versions,
        "cuda_identity": cuda_identity,
        "quantization": quantization,
        "config": {key: getattr(args, key) for key in ("mode", "seed", "lora_r", "lora_alpha", "lora_dropout", "learning_rate", "max_steps", "batch_size", "gradient_accumulation", "max_seq_len", "checkpoint_every_optimizer_steps", "deterministic_validation")},
        "determinism": {
            "validation_enabled": bool(args.deterministic_validation),
            "algorithms_enabled": bool(torch.are_deterministic_algorithms_enabled()),
            "cudnn_deterministic": bool(torch.backends.cudnn.deterministic),
            "cudnn_benchmark": bool(torch.backends.cudnn.benchmark),
            "cudnn_allow_tf32": bool(torch.backends.cudnn.allow_tf32),
            "cuda_matmul_allow_tf32": bool(torch.backends.cuda.matmul.allow_tf32),
            "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
        },
        "tokenizer_class": tokenizer.__class__.__name__,
        "order_strategy": "seeded-scenario-group-then-row-shuffle.v1",
    }


def _progress(run_dir: Path | None, value: dict[str, Any]) -> None:
    if run_dir is not None:
        path = run_dir / "progress.json"
        previous: dict[str, Any] = {}
        if path.exists():
            try:
                previous = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BehaviorTrainingError("existing progress is invalid") from exc
        atomic_json(run_dir / "progress.json", {
            "schema_version": "airi.behavior-training-progress.v1",
            "run_id": value.get("run_id", previous.get("run_id")), "status": value.get("status", previous.get("status")),
            "epoch": value.get("epoch", previous.get("epoch", 0)), "next_batch_index": value.get("next_batch_index", previous.get("next_batch_index", 0)),
            "microsteps_completed": value.get("microsteps_completed", value.get("microsteps", previous.get("microsteps_completed", 0))),
            "optimizer_steps": value.get("optimizer_steps", previous.get("optimizer_steps", 0)),
            "pending_microbatches": value.get("pending_microbatches", previous.get("pending_microbatches", 0)),
            "checkpoint": value.get("checkpoint", previous.get("checkpoint")),
            "updated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        })


def _pause_request(run_dir: Path | None, run_id: str | None) -> str | None:
    if run_dir is None:
        return None
    path = run_dir / "control" / "pause.request.json"
    if not path.exists():
        return None
    try:
        request = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BehaviorTrainingError("invalid pause request") from exc
    if set(request) != {"schema_version", "run_id", "request_id"} or request["schema_version"] != "airi.behavior-pause-request.v1":
        raise BehaviorTrainingError("pause request schema mismatch")
    if request["run_id"] != run_id or not isinstance(request["request_id"], str) or not request["request_id"]:
        raise BehaviorTrainingError("pause request identity mismatch")
    accepted_path = run_dir / "control" / "resume.accepted.json"
    if accepted_path.exists():
        try:
            accepted = json.loads(accepted_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BehaviorTrainingError("invalid resume acceptance receipt") from exc
        required = {"schema_version", "run_id", "request_id",
                    "checkpoint_relative_path", "checkpoint_manifest_sha256"}
        if (set(accepted) != required
                or accepted["schema_version"] != "airi.behavior-resume-accepted.v1"
                or accepted["run_id"] != run_id
                or accepted["request_id"] != request["request_id"]
                or not isinstance(accepted["checkpoint_relative_path"], str)
                or not isinstance(accepted["checkpoint_manifest_sha256"], str)):
            raise BehaviorTrainingError("resume acceptance identity mismatch")
        return None
    ack = run_dir / "control" / "pause.ack.json"
    if ack.exists():
        existing = json.loads(ack.read_text(encoding="utf-8"))
        if existing.get("request_id") != request["request_id"]:
            raise BehaviorTrainingError("competing pause request ids")
    return request["request_id"]


def _accept_resumed_pause_control(run_dir: Path, run_id: str,
                                  checkpoint_relative_path: str,
                                  checkpoint_manifest_sha256: str) -> None:
    control = run_dir / "control"
    request_path = control / "pause.request.json"
    ack_path = control / "pause.ack.json"
    request_exists = os.path.lexists(request_path)
    ack_exists = os.path.lexists(ack_path)
    if not request_exists and not ack_exists:
        return
    if (request_exists != ack_exists or not request_path.is_file()
            or not ack_path.is_file() or request_path.is_symlink()
            or ack_path.is_symlink()):
        raise BehaviorTrainingError("resumed pause control is incomplete")
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        ack = json.loads(ack_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BehaviorTrainingError("resumed pause control is invalid") from exc
    if (set(request) != {"schema_version", "run_id", "request_id"}
            or request["schema_version"] != "airi.behavior-pause-request.v1"
            or request["run_id"] != run_id
            or not isinstance(request["request_id"], str)
            or not request["request_id"]):
        raise BehaviorTrainingError("resumed pause request identity mismatch")
    ack_keys = {"schema_version", "run_id", "request_id", "checkpoint_manifest_sha256",
                "checkpoint_relative_path", "acknowledged_at_utc", "safe_to_power_off"}
    if (set(ack) != ack_keys
            or ack["schema_version"] != "airi.behavior-pause-ack.v1"
            or ack["run_id"] != run_id
            or ack["request_id"] != request["request_id"]
            or ack["checkpoint_relative_path"] != checkpoint_relative_path
            or ack["checkpoint_manifest_sha256"] != checkpoint_manifest_sha256
            or ack["safe_to_power_off"] is not True):
        raise BehaviorTrainingError("resumed pause ack does not match checkpoint")
    atomic_json(control / "resume.accepted.json", {
        "schema_version": "airi.behavior-resume-accepted.v1",
        "run_id": run_id,
        "request_id": request["request_id"],
        "checkpoint_relative_path": checkpoint_relative_path,
        "checkpoint_manifest_sha256": checkpoint_manifest_sha256,
    })


V4_SCHEMA_VERSION = "airi.broadcast-continuity.v4"


def is_v4_row(row: dict[str, Any]) -> bool:
    """The schema version is the sole v4 marker; do not infer authorization."""
    return row.get("schema_version") == V4_SCHEMA_VERSION


def _v4_tokens(row: dict[str, Any]) -> set[str]:
    """Return explicitly supplied fact/update/decoy tokens for leak checks."""
    tokens: set[str] = set()
    for field in ("fact_tokens", "updated_tokens", "decoy_tokens"):
        value = row.get(field)
        if value is None:
            continue
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise BehaviorTrainingError(f"{row.get('id')}: {field} must be a list of non-empty strings")
        tokens.update(value)
    for field in ("fact_token", "updated_token", "decoy_token"):
        value = row.get(field)
        if value is None:
            continue
        if not isinstance(value, str) or not value:
            raise BehaviorTrainingError(f"{row.get('id')}: {field} must be a non-empty string")
        tokens.add(value)
    required = row.get("required_token")
    if required is not None:
        tokens.add(required)
    return tokens


def validate_v4_metadata(rows: list[dict[str, Any]]) -> None:
    """Validate v4 export provenance and reject split leakage before training."""
    id_counts = Counter(row.get("id") for row in rows if isinstance(row.get("id"), str))
    group_splits: dict[str, str] = {}
    token_splits: dict[str, str] = {}
    for row in rows:
        if not is_v4_row(row):
            continue
        identifier = row.get("id")
        if not isinstance(identifier, str) or not identifier or id_counts[identifier] != 1:
            raise BehaviorTrainingError("v4 rows require globally unique non-empty string ids")
        for field in ("scenario_group", "semantic_family", "evidence_surface"):
            if not isinstance(row.get(field), str) or not row[field]:
                raise BehaviorTrainingError(f"{identifier}: v4 {field} must be a non-empty string")
        required = row.get("required_token")
        if required is not None and (not isinstance(required, str) or not required):
            raise BehaviorTrainingError(f"{identifier}: required_token must be a non-empty string or null")
        review = row.get("review")
        if review != {"user_aggregate_authorized": True, "adoption_authorized": False}:
            raise BehaviorTrainingError(f"{identifier}: v4 review must be aggregate-authorized and adoption false")
        split = row["split"]
        group = row["scenario_group"]
        previous = group_splits.setdefault(group, split)
        if previous != split:
            raise BehaviorTrainingError(f"{identifier}: scenario_group crosses splits")
        for token in _v4_tokens(row):
            previous = token_splits.setdefault(token, split)
            if previous != split:
                raise BehaviorTrainingError(f"{identifier}: v4 fact/update/decoy token crosses splits")


def epoch_group_order(rows: list[dict[str, Any]], seed: int, epoch: int) -> list[dict[str, Any]]:
    """Deterministically shuffle groups, then their rows, for one epoch."""
    if epoch < 0:
        raise BehaviorTrainingError("epoch must be non-negative")
    groups: dict[str, list[dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        group = row.get("scenario_group") if is_v4_row(row) else None
        group_key = f"v4:{group}" if group else f"row:{index}"
        groups.setdefault(group_key, []).append(row)
    rng = random.Random(f"airi-behavior-groups:{seed}")
    group_keys = sorted(groups)
    rng.shuffle(group_keys)
    if len(group_keys) > 1:
        offset = epoch % len(group_keys)
        group_keys = group_keys[offset:] + group_keys[:offset]
    ordered: list[dict[str, Any]] = []
    for group_key in group_keys:
        members = list(groups[group_key])
        member_rng = random.Random(f"airi-behavior-rows:{seed}:{epoch}:{group_key}")
        member_rng.shuffle(members)
        if len(members) > 1:
            offset = epoch % len(members)
            members = members[offset:] + members[:offset]
        ordered.extend(members)
    return ordered


def snapshot_trainable_state(model: Any) -> dict[str, Any]:
    """Keep just one CPU adapter snapshot, never a base-model copy."""
    return {name: parameter.detach().cpu().clone()
            for name, parameter in model.named_parameters() if parameter.requires_grad}


def restore_trainable_state(model: Any, state: dict[str, Any]) -> None:
    for name, parameter in model.named_parameters():
        if parameter.requires_grad:
            parameter.data.copy_(state[name].to(device=parameter.device, dtype=parameter.dtype))


def consider_best_state(best: dict[str, Any] | None, loss: float, step: int, epoch: int,
                        model: Any) -> dict[str, Any]:
    """Pure selection policy around a bounded trainable-parameter snapshot."""
    if best is None or loss < best["loss"]:
        return {"loss": float(loss), "step": step, "epoch": epoch,
                "state": snapshot_trainable_state(model)}
    return best


def flush_epoch_accumulation(optimizer: Any, pending_microbatches: int) -> int:
    """Apply a trailing accumulated gradient before evaluating an epoch."""
    if pending_microbatches:
        optimizer.step()
        optimizer.zero_grad()
        return 1
    return 0


def reject_network_path(path: Path, label: str) -> Path:
    text = str(path)
    # Path()가 "hf://org"를 "hf:\org"로 정규화해 "://" 검사가 새므로,
    # 2자 이상 스킴 + 구분자를 거부한다(1글자 "C:"는 드라이브라 허용).
    if text.startswith(("\\\\", "//")) or re.match(r"^[A-Za-z][A-Za-z0-9+.\-]+:[\\/]", text):
        raise BehaviorTrainingError(f"{label} must be a local path")
    absolute = path.expanduser().absolute()
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
            raise BehaviorTrainingError(f"{label} cannot traverse a reparse point")
    if os.name == "nt":
        import ctypes  # noqa: PLC0415
        if ctypes.WinDLL("kernel32").GetDriveTypeW(str(absolute.anchor)) != 3:
            raise BehaviorTrainingError(f"{label} must use a local fixed volume")
    resolved = absolute.resolve()
    if resolved == Path(resolved.anchor):
        raise BehaviorTrainingError(f"{label} cannot be a volume root")
    return resolved


def require_local_model_dir(value: str) -> Path:
    """A model is a local directory snapshot, never a hub name."""
    path = reject_network_path(Path(value), "model dir")
    if not path.is_dir() or not (path / "config.json").is_file():
        raise BehaviorTrainingError("model dir must be a local directory with config.json")
    return path


def verify_model_weight_sha256(model_dir: Path, expected_sha256: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise BehaviorTrainingError("cuda-qlora requires a lowercase model weight sha256 pin")
    weights = sorted(model_dir.glob("*.safetensors"))
    if len(weights) != 1:
        raise BehaviorTrainingError("model dir must contain exactly one safetensors weight file")
    with weights[0].open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if digest != expected_sha256:
        raise BehaviorTrainingError(
            f"model weight sha256 mismatch: expected {expected_sha256[:12]}…, "
            f"got {digest[:12]}…")
    return digest


def load_pinned_dataset(dataset_path: Path, expected_sha256: str) -> list[dict[str, Any]]:
    dataset_path = reject_network_path(dataset_path, "dataset")
    if not dataset_path.is_file() or dataset_path.is_symlink():
        raise BehaviorTrainingError("dataset must be a local regular file")
    payload = dataset_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_sha256:
        raise BehaviorTrainingError(
            f"dataset sha256 mismatch: expected {expected_sha256[:12]}…, got {digest[:12]}…")
    rows = [json.loads(line) for line in payload.decode("utf-8").splitlines() if line.strip()]
    if not rows:
        raise BehaviorTrainingError("dataset is empty")
    for row in rows:
        if row.get("split") not in {"train", "dev", "test"}:
            raise BehaviorTrainingError(f"{row.get('id')}: split must be train/dev/test")
        messages = row.get("messages")
        max_messages = 16 if is_v4_row(row) else 10
        if not isinstance(messages, list) or not 3 <= len(messages) <= max_messages:
            raise BehaviorTrainingError(
                f"{row.get('id')}: messages must be a bounded runtime conversation shape")
        roles = [message.get("role") if isinstance(message, dict) else None
                 for message in messages]
        runtime_shape = (
            roles[0] == "system"
            and roles[-2:] == ["user", "assistant"]
            and all(role in {"system", "user", "assistant"} for role in roles)
        )
        if not runtime_shape or not all(
            isinstance(message, dict)
            and isinstance(message.get("content"), str)
            and message["content"]
            for message in messages
        ):
            raise BehaviorTrainingError(
                f"{row.get('id')}: messages must be a bounded runtime conversation shape")
        for message in messages:
            keys = set(message)
            if is_v4_row(row) and keys != {"role", "content"}:
                raise BehaviorTrainingError(f"{row.get('id')}: v4 native messages allow only role/content")
            if keys not in ({"role", "content"}, {"role", "name", "content"}):
                raise BehaviorTrainingError(f"{row.get('id')}: message keys are outside the runtime schema")
            if "name" in message and (
                message["role"] != "system"
                or message["name"] not in {
                    "airi_request_local", "airi_broadcast_arc", "airi_broadcast_affect"
                }
            ):
                raise BehaviorTrainingError(f"{row.get('id')}: reserved system message name is invalid")
        if str(row.get("behavior", "")).startswith("affect_") and not any(
            message.get("name") == "airi_request_local" for message in messages
        ):
            raise BehaviorTrainingError(
                f"{row.get('id')}: affect message must be the request-local system note")
    validate_v4_metadata(rows)
    return rows


def render_pair(tokenizer: Any, messages: list[dict[str, str]]) -> tuple[str, str]:
    """Return (prompt_text, full_text); labels later mask the prompt part."""
    if getattr(tokenizer, "chat_template", None):
        prompt = tokenizer.apply_chat_template(
            messages[:-1], tokenize=False, add_generation_prompt=True)
        full = tokenizer.apply_chat_template(messages, tokenize=False)
    else:
        prompt = "".join(f"<|{m['role']}|>\n{m['content']}\n" for m in messages[:-1]) + "<|assistant|>\n"
        full = prompt + messages[-1]["content"] + "\n"
    if not full.startswith(prompt):
        # 템플릿이 접두 관계를 깨면 마스킹 경계를 신뢰할 수 없다.
        raise BehaviorTrainingError("chat template does not render prompt as a prefix of full text")
    return prompt, full


def encode_example(tokenizer: Any, messages: list[dict[str, str]], max_seq_len: int) -> dict[str, list[int]]:
    prompt, full = render_pair(tokenizer, messages)
    prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
    full_ids = tokenizer(full, add_special_tokens=False)["input_ids"]
    if len(full_ids) > max_seq_len:
        raise BehaviorTrainingError(
            f"runtime-shaped sample needs {len(full_ids)} tokens, above max_seq_len={max_seq_len}; "
            "raise the bound or shorten the source without truncating the assistant target")
    labels = [-100] * min(len(prompt_ids), len(full_ids)) + full_ids[len(prompt_ids):]
    labels = labels[: len(full_ids)]
    if all(label == -100 for label in labels):
        raise BehaviorTrainingError("assistant span was truncated away; raise max_seq_len")
    return {"input_ids": full_ids, "labels": labels}


def run_training(args: argparse.Namespace) -> dict[str, Any]:
    _prepare_deterministic_validation(args.deterministic_validation)
    import torch  # noqa: PLC0415 — heavy import stays inside the entrypoint
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer

    _configure_deterministic_validation(torch, args.deterministic_validation)

    for name in ("lora_r", "lora_alpha", "max_steps", "batch_size",
                 "gradient_accumulation", "max_seq_len"):
        if getattr(args, name) <= 0:
            raise BehaviorTrainingError(f"{name} must be positive")
    if not 0 <= args.lora_dropout < 1 or args.learning_rate <= 0:
        raise BehaviorTrainingError("dropout/learning-rate contract failure")

    all_rows = load_pinned_dataset(args.dataset, args.dataset_sha256)
    split_counts = Counter(row["split"] for row in all_rows)
    rows = [row for row in all_rows if row["split"] == "train"]
    if not rows:
        raise BehaviorTrainingError("dataset has no train split")
    model_dir = require_local_model_dir(args.model_dir)
    output = reject_network_path(Path(args.output), "output")
    report_path = reject_network_path(args.report, "report") if args.report else None
    run_dir = reject_network_path(Path(args.run_dir), "run dir") if args.run_dir else None
    if args.mode == "cuda-qlora" and (run_dir is None or not args.run_id):
        raise BehaviorTrainingError("cuda-qlora requires --run-dir and --run-id for durable checkpoints")
    if run_dir is not None:
        # Dataset/model are immutable, SHA-pinned read-only inputs.  The run,
        # adapter and report are the mutable publication set that must share
        # one volume for same-volume atomic promotion.
        run_anchor = run_dir.anchor.casefold()
        if (output.anchor.casefold() != run_anchor
                or (report_path is not None
                    and report_path.anchor.casefold() != run_anchor)):
            raise BehaviorTrainingError(
                "run directory and final artifacts must share one fixed volume")
    if args.resume_from_checkpoint and run_dir is None:
        raise BehaviorTrainingError("--resume-from-checkpoint requires --run-dir")

    if args.mode == "cpu-smoke":
        rows = rows[:CPU_SMOKE_MAX_SAMPLES]
        max_steps = min(args.max_steps, CPU_SMOKE_MAX_STEPS)
        output = output.with_name(output.name + "-SMOKE")
        device = "cpu"
        quantization = None
    else:
        if not torch.cuda.is_available():
            raise BehaviorTrainingError("cuda-qlora requires CUDA; use cpu-smoke only for plumbing")
        if not split_counts.get("dev") or not split_counts.get("test"):
            raise BehaviorTrainingError("cuda-qlora requires non-empty dev and test holdouts")
        from transformers import BitsAndBytesConfig
        quantization = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16)
        verified_model_sha256 = verify_model_weight_sha256(
            model_dir, args.model_sha256)
        max_steps = args.max_steps
        device = "cuda"

    if output.exists():
        raise BehaviorTrainingError("output path already exists; use a fresh adapter directory")
    if report_path is not None and report_path.exists():
        raise BehaviorTrainingError("report path already exists; use a fresh receipt path")
    if run_dir is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "control").mkdir(exist_ok=True)
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    pins = _source_pins(args, model_dir, tokenizer)
    model_kwargs: dict[str, Any] = {"local_files_only": True}
    if quantization is not None:
        model_kwargs["quantization_config"] = quantization
        model_kwargs["device_map"] = {"": 0}
    model = AutoModelForCausalLM.from_pretrained(str(model_dir), **model_kwargs)
    if quantization is None:
        model = model.to(device)
        cpu_weights = sorted(model_dir.glob("*.safetensors"))
        verified_model_sha256 = (_file_sha256(cpu_weights[0]) if len(cpu_weights) == 1
                                 else "cpu-smoke-weight-unavailable")
    else:
        # QLoRA needs frozen k-bit parameters and input gradients; checkpointing
        # is what keeps a 2.3B, 48-layer model within the supported 8 GiB card.
        model = prepare_model_for_kbit_training(
            model, use_gradient_checkpointing=True)
        model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(
        r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=args.lora_dropout,
        task_type="CAUSAL_LM", target_modules="all-linear"))

    encoded = [encode_example(tokenizer, row["messages"], args.max_seq_len) for row in rows]
    dev_rows = [row for row in all_rows if row["split"] == "dev"]
    encoded_dev = [encode_example(tokenizer, row["messages"], args.max_seq_len)
                   for row in dev_rows]
    pad_id = tokenizer.pad_token_id

    def batches(examples: list[dict[str, list[int]]]):
        for start in range(0, len(examples), args.batch_size):
            chunk = examples[start:start + args.batch_size]
            width = max(len(example["input_ids"]) for example in chunk)
            input_ids = torch.tensor(
                [example["input_ids"] + [pad_id] * (width - len(example["input_ids"]))
                 for example in chunk])
            labels = torch.tensor(
                [example["labels"] + [-100] * (width - len(example["labels"]))
                 for example in chunk])
            attention = torch.tensor(
                [[1] * len(example["input_ids"])
                 + [0] * (width - len(example["input_ids"]))
                 for example in chunk]
            )
            yield input_ids.to(device), labels.to(device), attention.to(device)

    def dev_loss() -> float:
        if not encoded_dev:
            raise BehaviorTrainingError("dev evaluation requested without a dev split")
        was_training = model.training
        model.eval()
        total_loss = 0.0
        total_tokens = 0
        with torch.no_grad():
            for input_ids, labels, attention in batches(encoded_dev):
                result = model(input_ids=input_ids, labels=labels, attention_mask=attention)
                tokens = int((labels != -100).sum().item())
                total_loss += float(result.loss.detach()) * tokens
                total_tokens += tokens
        if was_training:
            model.train()
        if not total_tokens:
            raise BehaviorTrainingError("dev split has no assistant target tokens")
        return total_loss / total_tokens

    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    optimizer = torch.optim.AdamW(
        (parameter for parameter in model.parameters() if parameter.requires_grad),
        lr=args.learning_rate)
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda _step: 1.0)
    model.train()
    losses: list[float] = []
    dev_loss_history: list[dict[str, Any]] = []
    best_state: dict[str, Any] | None = None
    encoded_by_row = {id(row): example for row, example in zip(rows, encoded)}
    step = 0
    epoch = 0
    batch_cursor = 0
    pending_microbatches = 0
    optimizer_steps = 0
    checkpoint_generation = 0
    if args.resume_from_checkpoint:
        try:
            requested = args.resume_from_checkpoint.resolve()
            checkpoint_root = (run_dir / "checkpoints").resolve()
            if requested.parent != checkpoint_root or requested.name.startswith("."):
                raise BehaviorTrainingError("resume checkpoint must be an exact generation under run-dir/checkpoints")
            loaded = load_generation(run_dir, requested.name, pins, args.run_id)
        except CheckpointError as exc:
            raise BehaviorTrainingError(f"cannot resume checkpoint: {exc}") from exc
        state = torch.load(io.BytesIO(loaded["payload"]), map_location="cpu", weights_only=False)
        if state.get("run_id") != args.run_id or state.get("pending_microbatches") != 0:
            raise BehaviorTrainingError("resume state is not an optimizer boundary for this run")
        restore_trainable_state(model, state["trainable_state"])
        optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])
        random.setstate(state["python_rng"])
        torch.set_rng_state(state["torch_rng"])
        if torch.cuda.is_available() and state.get("cuda_rng") is not None:
            torch.cuda.set_rng_state_all(state["cuda_rng"])
        losses = state["losses"]
        dev_loss_history = state["dev_loss_history"]
        best_state = state["best_state"]
        step, epoch, batch_cursor = state["step"], state["epoch"], state["batch_cursor"]
        optimizer_steps, checkpoint_generation = state["optimizer_steps"], state["checkpoint_generation"]
        reconstructed_order = hashlib.sha256("\n".join(
            row["id"] for row in epoch_group_order(rows, args.seed, epoch)).encode()).hexdigest()
        if state.get("row_order_hash") != reconstructed_order or state.get("seed") != args.seed:
            raise BehaviorTrainingError("resume deterministic row order mismatch")
        _accept_resumed_pause_control(
            run_dir, args.run_id, requested.name, loaded["manifest_sha256"])

    def checkpoint(reason: str) -> None:
        nonlocal checkpoint_generation
        if run_dir is None:
            return
        if pending_microbatches != 0:
            raise BehaviorTrainingError("checkpoint requested outside optimizer boundary")
        checkpoint_generation += 1
        publish_started_at_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        publish_started_ns = time.perf_counter_ns()
        state = {"run_id": args.run_id, "trainable_state": snapshot_trainable_state(model),
                 "optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict(),
                 "python_rng": random.getstate(), "torch_rng": torch.get_rng_state(),
                 "cuda_rng": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
                 "epoch": epoch, "batch_cursor": batch_cursor, "step": step,
                 "pending_microbatches": pending_microbatches, "optimizer_steps": optimizer_steps,
                 "checkpoint_generation": checkpoint_generation, "losses": losses,
                 "dev_loss_history": dev_loss_history, "best_state": best_state,
                 "row_order_hash": hashlib.sha256("\n".join(row["id"] for row in epoch_group_order(rows, args.seed, epoch)).encode()).hexdigest(),
                 "seed": args.seed}
        buffer = io.BytesIO()
        torch.save(state, buffer)
        generation = f"checkpoint-{checkpoint_generation:08d}"
        published = publish_checkpoint(run_dir, args.run_id, generation, buffer.getvalue(), pins)
        checkpoint_durable_at_utc = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        checkpoint_event = _publish_checkpoint_event(
            run_dir, args.run_id, generation, reason, step, optimizer_steps,
            pending_microbatches, publish_started_at_utc, checkpoint_durable_at_utc,
            time.perf_counter_ns() - publish_started_ns, published, pins)
        reference = {"relative_path": generation, "manifest_sha256": published["manifest_sha256"]}
        _progress(run_dir, {"run_id": args.run_id,
                            "status": "checkpointed", "safe_to_power_off": True,
                            "epoch": epoch, "next_batch_index": batch_cursor,
                            "optimizer_steps": optimizer_steps, "microsteps": step,
                            "pending_microbatches": pending_microbatches, "checkpoint": reference,
                            "checkpoint_event": checkpoint_event})
        request_id = _pause_request(run_dir, args.run_id)
        if request_id:
            atomic_json(run_dir / "control" / "pause.ack.json", {
                "schema_version": "airi.behavior-pause-ack.v1", "run_id": args.run_id,
                "request_id": request_id, "checkpoint_manifest_sha256": published["manifest_sha256"],
                "checkpoint_relative_path": generation,
                "acknowledged_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "safe_to_power_off": True})
            _progress(run_dir, {"run_id": args.run_id,
                                "status": "paused-safe", "safe_to_power_off": True,
                                "epoch": epoch, "next_batch_index": batch_cursor,
                                "optimizer_steps": optimizer_steps, "microsteps": step,
                                "pending_microbatches": 0, "checkpoint": reference})
            raise PauseRequested(75)
    while step < max_steps:
        ordered = epoch_group_order(rows, args.seed, epoch)
        epoch_examples = [encoded_by_row[id(row)] for row in ordered]
        epoch_batches = list(batches(epoch_examples))
        if batch_cursor > len(epoch_batches):
            raise BehaviorTrainingError("resume batch cursor exceeds deterministic epoch")
        completed_epoch = True
        for cursor in range(batch_cursor, len(epoch_batches)):
            input_ids, labels, attention = epoch_batches[cursor]
            if step >= max_steps:
                completed_epoch = False
                break
            loss = model(input_ids=input_ids, labels=labels, attention_mask=attention).loss
            (loss / args.gradient_accumulation).backward()
            step += 1
            pending_microbatches += 1
            batch_cursor = cursor + 1
            losses.append(float(loss.detach()))
            if pending_microbatches == args.gradient_accumulation:
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
                optimizer_steps += 1
                pending_microbatches = 0
                _progress(run_dir, {"schema_version": CONTROL_SCHEMA_VERSION, "run_id": args.run_id,
                                    "status": "running", "safe_to_power_off": False,
                                    "optimizer_steps": optimizer_steps, "microsteps": step})
                pause_pending = _pause_request(run_dir, args.run_id) is not None
                if (optimizer_steps % args.checkpoint_every_optimizer_steps == 0
                        or pause_pending):
                    checkpoint("safe-pause" if pause_pending else "interval")
        # Selection must observe a post-optimizer model.  Flush both a normal
        # epoch tail and the final partial epoch rather than carrying gradients
        # across their evaluation boundary.
        flushed = flush_epoch_accumulation(optimizer, pending_microbatches)
        if flushed:
            scheduler.step()
        optimizer_steps += flushed
        pending_microbatches = 0
        if flushed:
            _progress(run_dir, {"schema_version": CONTROL_SCHEMA_VERSION, "run_id": args.run_id,
                                "status": "running", "safe_to_power_off": False,
                                "optimizer_steps": optimizer_steps, "microsteps": step})
            checkpoint("epoch-tail")
        # CUDA selects on every full epoch and the final partial epoch. CPU
        # deliberately records that it made no selection to keep smoke bounded.
        if args.mode == "cuda-qlora" and (completed_epoch or step == max_steps):
            current_dev_loss = dev_loss()
            record = {"epoch": epoch + 1, "step": step, "loss": current_dev_loss}
            dev_loss_history.append(record)
            best_state = consider_best_state(best_state, current_dev_loss, step, epoch + 1, model)
        epoch += 1
        batch_cursor = 0
        # Persist the evaluated epoch/best-selection state too.  This is also
        # the safe-pause seam for a request that arrives during dev evaluation.
        checkpoint("epoch-complete")

    if best_state is not None:
        restore_trainable_state(model, best_state["state"])

    first = sum(losses[:3]) / min(3, len(losses))
    last = sum(losses[-3:]) / min(3, len(losses))
    if args.mode == "cpu-smoke" and not last < first:
        raise BehaviorTrainingError(
            f"smoke loss did not fall ({first:.3f} -> {last:.3f}); the pipeline is suspect")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.with_name(output.name + ".tmp")
    if temporary_output.exists():
        raise BehaviorTrainingError("temporary adapter output already exists")
    temporary_output.mkdir()
    model.save_pretrained(str(temporary_output))
    artifact = publish_artifact_directory(
        temporary_output, output,
        args.run_id or f"standalone-{args.dataset_sha256[:16]}", pins)
    trainable = sum(parameter.numel() for parameter in model.parameters()
                    if parameter.requires_grad)
    total = sum(parameter.numel() for parameter in model.parameters())
    summary = {
        "mode": args.mode,
        "dataset_samples": len(all_rows),
        "split_counts": dict(sorted(split_counts.items())),
        "training_samples": len(rows),
        "samples": len(rows), "steps": max_steps,
        "optimizer_steps": optimizer_steps,
        "checkpoint_every_optimizer_steps": args.checkpoint_every_optimizer_steps,
        "deterministic_validation": bool(args.deterministic_validation),
        "determinism": pins["determinism"],
        "order_strategy": "seeded-scenario-group-then-row-shuffle",
        "order_seed": args.seed,
        "dev_loss_history": dev_loss_history,
        "selected_dev_step": best_state["step"] if best_state is not None else None,
        "selected_dev_epoch": best_state["epoch"] if best_state is not None else None,
        "selected_dev_loss": best_state["loss"] if best_state is not None else None,
        "loss_first3_mean": round(first, 4), "loss_last3_mean": round(last, 4),
        "adapter_dir": str(output),
        "adapter_artifact_manifest_sha256": artifact["manifest_sha256"],
        "dataset_sha256": args.dataset_sha256,
        "model_weight_sha256": verified_model_sha256,
        "trainable_parameters": trainable,
        "total_parameters_visible": total,
        "peak_cuda_memory_bytes": (
            int(torch.cuda.max_memory_allocated()) if device == "cuda" else 0),
        "torch_version": torch.__version__,
        "python_version": sys.version.split()[0],
        "transformers_version": importlib.metadata.version("transformers"),
        "peft_version": importlib.metadata.version("peft"),
        "bitsandbytes_version": (
            importlib.metadata.version("bitsandbytes")
            if args.mode == "cuda-qlora" else None
        ),
        "seed": args.seed,
        "training_authorization": args.mode == "cuda-qlora",
        "adoption_authorized": False,
        "t3_status": "pending",
        "note": ("plumbing smoke only — NOT a trained adapter"
                 if args.mode == "cpu-smoke" else "adapter must pass the T3 gate before adoption"),
    }
    if report_path is not None:
        atomic_json(report_path, summary)
    _progress(run_dir, {"schema_version": CONTROL_SCHEMA_VERSION, "run_id": args.run_id,
                        "status": "completed", "safe_to_power_off": True,
                        "optimizer_steps": optimizer_steps, "microsteps": step})
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AIRI behavior LoRA trainer")
    parser.add_argument("--dataset", type=Path, required=True, help="chat-format export JSONL")
    parser.add_argument("--dataset-sha256", required=True, help="익스포터가 출력한 sha256 핀")
    parser.add_argument("--model-dir", required=True, help="로컬 HF 스냅샷 디렉터리 (허브 이름 불가)")
    parser.add_argument("--output", required=True, help="어댑터 출력 디렉터리")
    parser.add_argument("--model-sha256", default="",
                        help="cuda-qlora에서 요구하는 단일 safetensors SHA-256")
    parser.add_argument("--report", type=Path,
                        help="선택적 원자적 JSON 학습 영수증 경로")
    parser.add_argument("--mode", choices=["cuda-qlora", "cpu-smoke"], required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--run-dir", type=Path,
                        help="durable checkpoint/control directory (required for cuda-qlora)")
    parser.add_argument("--run-id", help="immutable durable-run identity (required for cuda-qlora)")
    parser.add_argument("--checkpoint-every-optimizer-steps", type=int, default=5)
    parser.add_argument("--resume-from-checkpoint", type=Path,
                        help="exact immutable generation directory under run-dir/checkpoints")
    parser.add_argument("--deterministic-validation", action="store_true",
                        help="fail closed on nondeterministic CUDA operations for equivalence proof")
    for key, value in DEFAULTS.items():
        flag = "--" + key.replace("_", "-")
        parser.add_argument(flag, type=type(value), default=value)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.checkpoint_every_optimizer_steps <= 0:
        raise BehaviorTrainingError("checkpoint-every-optimizer-steps must be positive")
    try:
        summary = run_training(args)
    except PauseRequested as exc:
        return int(exc.code)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
