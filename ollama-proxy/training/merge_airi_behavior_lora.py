"""Fail-closed, local-only merger for a pinned AIRI behavior LoRA adapter.

This tool deliberately does not authorize adoption.  It only produces a
reproducible merged checkpoint and the mechanical evidence needed for a later
T3 decision.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_TARGET_TENSOR = "model.layers.0.self_attn.q_proj.weight"
DEFAULT_NON_TARGET_TENSOR = "model.embed_tokens.weight"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
NETWORK_PATH_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
ADAPTER_EVIDENCE_FIELDS = (
    "peft_type", "task_type", "r", "lora_alpha", "lora_dropout", "bias",
    "target_modules", "use_dora", "use_rslora", "inference_mode",
)


class MergeError(ValueError):
    """Raised when a merge cannot meet the immutable local contract."""


def require_local_path(value: str | Path, label: str, *, must_exist: bool = True) -> Path:
    """Return an absolute local path, rejecting URLs and UNC/network paths."""
    text = str(value)
    if (text.startswith(("\\\\", "//")) or NETWORK_PATH_RE.match(text)
            and not re.match(r"^[A-Za-z]:[\\/]", text)):
        raise MergeError(f"{label} must be a local path, not a URL or network path")
    path = Path(text).expanduser()
    if must_exist and path.is_symlink():
        raise MergeError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=must_exist)
    except OSError as exc:
        raise MergeError(f"{label} cannot be resolved locally") from exc
    if must_exist and not resolved.exists():
        raise MergeError(f"{label} does not exist")
    return resolved


def require_sha256(path: Path, expected: str, label: str) -> str:
    if not SHA256_RE.fullmatch(expected):
        raise MergeError(f"{label} sha256 pin must be 64 lowercase hexadecimal characters")
    if not path.is_file():
        raise MergeError(f"{label} must be a regular file")
    with path.open("rb") as handle:
        actual = hashlib.file_digest(handle, "sha256").hexdigest()
    if actual != expected:
        raise MergeError(f"{label} sha256 mismatch")
    return actual


def top_level_artifact_manifest(directory: Path) -> tuple[str, list[dict[str, Any]]]:
    """Hash every top-level input artifact, rejecting aliases and hidden trees."""
    if not directory.is_dir() or directory.is_symlink():
        raise MergeError("artifact input must be a real local directory")
    artifacts: list[dict[str, Any]] = []
    for entry in sorted(directory.iterdir(), key=lambda item: item.name):
        if entry.is_symlink() or entry.is_dir() or not entry.is_file():
            raise MergeError("input artifacts must be top-level regular files; symlinks/subdirectories are refused")
        with entry.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        artifacts.append({"name": entry.name, "size": entry.stat().st_size, "sha256": digest})
    if not artifacts:
        raise MergeError("input artifact directory must not be empty")
    canonical = json.dumps(artifacts, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest(), artifacts


def require_artifact_manifest(directory: Path, expected: str, label: str) -> tuple[str, list[dict[str, Any]]]:
    if not SHA256_RE.fullmatch(expected):
        raise MergeError(f"{label} manifest sha256 pin must be 64 lowercase hexadecimal characters")
    actual, artifacts = top_level_artifact_manifest(directory)
    if actual != expected:
        raise MergeError(f"{label} artifact manifest sha256 mismatch")
    return actual, artifacts


def merged_artifact_digest(stage: Path) -> tuple[str, int]:
    """Return the sole unsharded published weight artifact's streaming digest."""
    matches = [path for path in stage.glob("model.safetensors") if path.is_file()]
    if len(matches) != 1:
        raise MergeError("merged output must contain exactly one model.safetensors file")
    artifact = matches[0]
    size = artifact.stat().st_size
    if size <= 0:
        raise MergeError("merged model.safetensors must be non-empty")
    with artifact.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest(), size


def require_input_layout(base_model_dir: Path, adapter_dir: Path,
                         base_sha256: str, adapter_sha256: str) -> tuple[str, str]:
    if not (base_model_dir / "config.json").is_file():
        raise MergeError("base model directory must contain config.json")
    if not (adapter_dir / "adapter_config.json").is_file():
        raise MergeError("adapter directory must contain adapter_config.json")
    return (
        require_sha256(base_model_dir / "model.safetensors", base_sha256, "base model.safetensors"),
        require_sha256(adapter_dir / "adapter_model.safetensors", adapter_sha256,
                       "adapter adapter_model.safetensors"),
    )


def prepare_publication(output_dir: str | Path, temporary_dir: str | Path | None) -> tuple[Path, Path]:
    """Create a fresh sibling staging directory suitable for atomic publishing."""
    output = require_local_path(output_dir, "output", must_exist=False)
    if output.exists():
        raise MergeError("output path already exists; refusing to overwrite it")
    parent = output.parent
    if not parent.is_dir():
        raise MergeError("output parent must already exist as a local directory")
    temp_parent = require_local_path(temporary_dir or parent, "temporary directory")
    if not temp_parent.is_dir():
        raise MergeError("temporary directory must be a directory")
    # A directory rename is atomic only within its parent.  Reject a tempting
    # cross-directory copy fallback rather than weakening publication safety.
    if temp_parent != parent:
        raise MergeError("temporary directory must equal the output parent for atomic publication")
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.merge-", dir=parent))
    return output, stage


def publish_staged_output(stage: Path, output: Path) -> None:
    if output.exists():
        raise MergeError("output path appeared during merge; refusing to overwrite it")
    try:
        os.replace(stage, output)
    except OSError as exc:
        raise MergeError("atomic publication failed; output was not published") from exc


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def load_adapter_config(adapter_dir: Path) -> dict[str, Any]:
    try:
        config = json.loads((adapter_dir / "adapter_config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MergeError("adapter_config.json must be valid UTF-8 JSON") from exc
    if not isinstance(config, dict):
        raise MergeError("adapter_config.json must contain an object")
    return sanitize_adapter_config(config)


def sanitize_adapter_config(config: dict[str, Any]) -> dict[str, Any]:
    """Keep only merge-relevant, non-location adapter parameters in evidence."""
    safe: dict[str, Any] = {}
    for field in ADAPTER_EVIDENCE_FIELDS:
        if field not in config:
            continue
        value = config[field]
        if field == "target_modules":
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise MergeError("adapter target_modules must be a string or string list")
            safe[field] = sorted(value)
        elif field in {"peft_type", "task_type", "bias"}:
            if not isinstance(value, str):
                raise MergeError(f"adapter {field} must be a string")
            safe[field] = value
        elif field in {"r", "lora_alpha", "lora_dropout"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise MergeError(f"adapter {field} must be numeric")
            safe[field] = value
        elif not isinstance(value, bool):
            raise MergeError(f"adapter {field} must be boolean")
        else:
            safe[field] = value
    return safe


def base_model_load_kwargs(torch: Any) -> dict[str, Any]:
    """Keep the pinned base precision; implicit dtype selection is unsafe here."""
    return {"local_files_only": True, "trust_remote_code": False,
            "torch_dtype": torch.bfloat16, "low_cpu_mem_usage": True}


def build_evidence(*, base_sha256: str, adapter_sha256: str,
                   base_artifact_manifest_sha256: str, adapter_artifact_manifest_sha256: str,
                   merged_model_sha256: str, merged_model_size_bytes: int,
                   target_tensor: str, non_target_tensor: str,
                   target_metrics: dict[str, Any], adapter_config: dict[str, Any]) -> dict[str, Any]:
    """Create content-free evidence; input paths are intentionally excluded."""
    evidence = {
        "schema_version": 1,
        "operation": "peft-safe-merge",
        "input_paths_recorded": False,
        "base_model_safetensors_sha256": base_sha256,
        "adapter_model_safetensors_sha256": adapter_sha256,
        "base_artifact_manifest_sha256": base_artifact_manifest_sha256,
        "adapter_artifact_manifest_sha256": adapter_artifact_manifest_sha256,
        "merged_model_safetensors_sha256": merged_model_sha256,
        "merged_model_size_bytes": merged_model_size_bytes,
        "base_model_path": {"omitted": True, "bound_by": "base_model_safetensors_sha256"},
        "versions": {"python": os.sys.version.split()[0], "torch": package_version("torch"),
                     "transformers": package_version("transformers"), "peft": package_version("peft")},
        "tensors": {"target": {"name": target_tensor, **target_metrics},
                    "non_target": {"name": non_target_tensor, "dtype": "bfloat16",
                                   "exactly_unchanged": True}},
        "adapter_config": adapter_config,
        "adoption_authorized": False,
        "t3_status": "pending",
    }
    validate_evidence(evidence)
    return evidence


def validate_evidence(evidence: dict[str, Any]) -> None:
    """Guard against accidentally recording an absolute input location."""
    encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    if evidence.get("input_paths_recorded") is not False:
        raise MergeError("evidence must explicitly exclude input paths")
    if evidence.get("adoption_authorized") is not False or evidence.get("t3_status") != "pending":
        raise MergeError("evidence must retain non-authorizing T3-pending status")
    merged_sha = evidence.get("merged_model_safetensors_sha256")
    if not isinstance(merged_sha, str) or not SHA256_RE.fullmatch(merged_sha):
        raise MergeError("evidence must contain the merged model sha256")
    if merged_sha == evidence.get("base_model_safetensors_sha256"):
        raise MergeError("merged model bytes must differ from the pinned base")
    if isinstance(evidence.get("merged_model_size_bytes"), bool) or not isinstance(
            evidence.get("merged_model_size_bytes"), int) or evidence["merged_model_size_bytes"] <= 0:
        raise MergeError("evidence must contain a positive merged model byte size")
    for field in ("base_artifact_manifest_sha256", "adapter_artifact_manifest_sha256"):
        if not isinstance(evidence.get(field), str) or not SHA256_RE.fullmatch(evidence[field]):
            raise MergeError(f"evidence must contain {field}")
    if re.search(r"(?:[A-Za-z]:[\\/]|\\\\|//)", encoded):
        raise MergeError("evidence must not contain absolute or network paths")
    target = evidence.get("tensors", {}).get("target", {})
    if not target.get("finite") or int(target.get("nonzero_elements", 0)) <= 0:
        raise MergeError("evidence must prove a finite, nonzero target delta")
    if evidence.get("tensors", {}).get("non_target", {}).get("exactly_unchanged") is not True:
        raise MergeError("evidence must prove the non-target tensor is unchanged")
    if target.get("dtype") != "bfloat16" or evidence.get("tensors", {}).get("non_target", {}).get("dtype") != "bfloat16":
        raise MergeError("evidence must attest BF16 target and non-target tensors")


def verify_merge_tensors(torch: Any, base_state: dict[str, Any], merged_state: dict[str, Any],
                         target_name: str, non_target_name: str) -> dict[str, Any]:
    for name in (target_name, non_target_name):
        if name not in base_state or name not in merged_state:
            raise MergeError(f"required tensor is absent: {name}")
    base_target, merged_target = base_state[target_name], merged_state[target_name]
    if tuple(base_target.shape) != tuple(merged_target.shape):
        raise MergeError("target tensor shape changed during merge")
    base_non_target = base_state[non_target_name].detach().cpu().contiguous()
    merged_non_target = merged_state[non_target_name].detach().cpu().contiguous()
    tensors = (base_target, merged_target, base_non_target, merged_non_target)
    if any(tensor.dtype != torch.bfloat16 for tensor in tensors):
        raise MergeError("pinned base and merged target/non-target tensors must remain BF16")
    delta = merged_target.detach().to(dtype=torch.float32, device="cpu") - base_target.detach().to(dtype=torch.float32, device="cpu")
    finite = bool(torch.isfinite(delta).all().item())
    nonzero = int(torch.count_nonzero(delta).item())
    if not finite or nonzero == 0:
        raise MergeError("target tensor delta must be finite and nonzero")
    byte_identical = (
        base_non_target.dtype == merged_non_target.dtype
        and tuple(base_non_target.shape) == tuple(merged_non_target.shape)
        and torch.equal(base_non_target, merged_non_target)
        and torch.equal(base_non_target.view(torch.uint8), merged_non_target.view(torch.uint8))
    )
    if not byte_identical:
        raise MergeError("non-target tensor changed during merge")
    return {"dtype": "bfloat16", "finite": finite, "nonzero_elements": nonzero,
            "max_abs_delta": float(delta.abs().max().item()),
            "l2_delta": float(torch.linalg.vector_norm(delta).item())}


def merge(args: argparse.Namespace) -> Path:
    """Load only local pinned artifacts, merge once, validate, then publish atomically."""
    base_dir = require_local_path(args.base_model_dir, "base model directory")
    adapter_dir = require_local_path(args.adapter_dir, "adapter directory")
    if not base_dir.is_dir() or not adapter_dir.is_dir():
        raise MergeError("base model and adapter inputs must be directories")
    base_sha, adapter_sha = require_input_layout(base_dir, adapter_dir, args.base_model_sha256,
                                                  args.adapter_sha256)
    base_manifest_sha, _ = require_artifact_manifest(
        base_dir, args.base_artifact_manifest_sha256, "base model")
    adapter_manifest_sha, _ = require_artifact_manifest(
        adapter_dir, args.adapter_artifact_manifest_sha256, "adapter")
    output, stage = prepare_publication(args.output_dir, args.temporary_dir)
    try:
        import torch  # heavy imports belong only in the real merge path
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        base_model = AutoModelForCausalLM.from_pretrained(str(base_dir), **base_model_load_kwargs(torch))
        tokenizer = AutoTokenizer.from_pretrained(str(base_dir), local_files_only=True,
                                                   trust_remote_code=False)
        base_state = {name: tensor.detach().cpu().clone()
                      for name, tensor in base_model.state_dict().items()
                      if name in {args.target_tensor, args.non_target_tensor}}
        peft_model = PeftModel.from_pretrained(base_model, str(adapter_dir), local_files_only=True)
        merged_model = peft_model.merge_and_unload(safe_merge=True)
        merged_state = merged_model.state_dict()
        metrics = verify_merge_tensors(torch, base_state, merged_state, args.target_tensor,
                                       args.non_target_tensor)
        merged_model.save_pretrained(str(stage), safe_serialization=True)
        tokenizer.save_pretrained(str(stage))
        merged_sha, merged_size = merged_artifact_digest(stage)
        evidence = build_evidence(base_sha256=base_sha, adapter_sha256=adapter_sha,
                                  base_artifact_manifest_sha256=base_manifest_sha,
                                  adapter_artifact_manifest_sha256=adapter_manifest_sha,
                                  merged_model_sha256=merged_sha,
                                  merged_model_size_bytes=merged_size,
                                  target_tensor=args.target_tensor,
                                  non_target_tensor=args.non_target_tensor,
                                  target_metrics=metrics,
                                  adapter_config=load_adapter_config(adapter_dir))
        (stage / "merge-evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        publish_staged_output(stage, output)
        return output
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely merge a pinned local AIRI behavior LoRA adapter")
    parser.add_argument("--base-model-dir", required=True)
    parser.add_argument("--adapter-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--temporary-dir", help="must be the output directory's existing parent")
    parser.add_argument("--base-model-sha256", required=True)
    parser.add_argument("--adapter-sha256", required=True)
    parser.add_argument("--base-artifact-manifest-sha256", required=True)
    parser.add_argument("--adapter-artifact-manifest-sha256", required=True)
    parser.add_argument("--target-tensor", default=DEFAULT_TARGET_TENSOR)
    parser.add_argument("--non-target-tensor", default=DEFAULT_NON_TARGET_TENSOR)
    return parser.parse_args(argv)


def main() -> int:
    try:
        output = merge(parse_args())
    except MergeError as exc:
        print(f"merge refused: {exc}", file=os.sys.stderr)
        return 2
    print(f"merged checkpoint published: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
