"""Build a canonical, non-replacing input manifest for durable AIRI training."""

from __future__ import annotations

import argparse
import json
import math
import os
import stat
import sys
from pathlib import Path
from typing import Any, Sequence

import durable_training_runner as durable


class ManifestBuildError(RuntimeError):
    """Fail-closed manifest construction error."""


def _require_pinned_file(path: Path, expected_sha256: str, label: str) -> tuple[Path, str]:
    if not durable.HEX64.fullmatch(expected_sha256):
        raise ManifestBuildError(f"{label} SHA-256 is invalid")
    resolved = durable.validate_local_path(path, label)
    try:
        actual = durable.sha256_bytes(durable._read_regular_file_snapshot(resolved, label))
    except durable.DurableRunnerError as exc:
        raise ManifestBuildError(f"{label} is not a regular file") from exc
    if actual != expected_sha256:
        raise ManifestBuildError(f"{label} SHA-256 does not match its bytes")
    return resolved, actual


def _training_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "mode": args.mode,
        "seed": args.seed,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "lora_dropout": args.lora_dropout,
        "learning_rate": args.learning_rate,
        "max_steps": args.max_steps,
        "batch_size": args.batch_size,
        "gradient_accumulation": args.gradient_accumulation,
        "max_seq_len": args.max_seq_len,
        "checkpoint_every_optimizer_steps": args.checkpoint_every_optimizer_steps,
        "deterministic_validation": bool(args.deterministic_validation),
        "init_mode": ("adapter-weights-only" if args.init_adapter_dir else "fresh-lora"),
    }


def _trainer_arguments(config: dict[str, Any], initial_adapter: dict[str, Any] | None = None,
                       initial_adapter_dir: Path | None = None) -> list[str]:
    values = [
        "--mode", str(config["mode"]),
        "--seed", str(config["seed"]),
        "--lora-r", str(config["lora_r"]),
        "--lora-alpha", str(config["lora_alpha"]),
        "--lora-dropout", str(config["lora_dropout"]),
        "--learning-rate", str(config["learning_rate"]),
        "--max-steps", str(config["max_steps"]),
        "--batch-size", str(config["batch_size"]),
        "--gradient-accumulation", str(config["gradient_accumulation"]),
        "--max-seq-len", str(config["max_seq_len"]),
    ]
    if config["deterministic_validation"]:
        values.append("--deterministic-validation")
    if config["init_mode"] == "adapter-weights-only":
        if initial_adapter is None or initial_adapter_dir is None:
            raise ManifestBuildError("adapter initialization arguments require explicit provenance")
        values.extend(("--init-adapter-dir", str(initial_adapter_dir),
                       "--init-adapter-model-sha256", initial_adapter["model_sha256"],
                       "--init-adapter-config-sha256", initial_adapter["config_sha256"],
                       "--init-adapter-artifact-manifest-sha256",
                       initial_adapter["artifact_manifest_sha256"]))
    return values


def _initial_adapter(args: argparse.Namespace) -> dict[str, Any] | None:
    values = (args.init_adapter_dir, args.init_adapter_model_sha256,
              args.init_adapter_config_sha256, args.init_adapter_artifact_manifest_sha256)
    if not any(value is not None for value in values):
        return None
    if any(value is None for value in values):
        raise ManifestBuildError("init adapter flags must be supplied together")
    directory = durable.validate_local_path(args.init_adapter_dir, "init adapter directory")
    if not directory.is_dir():
        raise ManifestBuildError("init adapter directory is missing")
    pins = {
        "model_sha256": args.init_adapter_model_sha256,
        "config_sha256": args.init_adapter_config_sha256,
        "artifact_manifest_sha256": args.init_adapter_artifact_manifest_sha256,
    }
    for label, digest in pins.items():
        if not durable.HEX64.fullmatch(digest):
            raise ManifestBuildError(f"init adapter {label} is invalid")
    try:
        artifact_bytes = durable._read_regular_file_snapshot(
            directory / "artifact-manifest.json", "init adapter artifact manifest")
        if durable.sha256_bytes(artifact_bytes) != pins["artifact_manifest_sha256"]:
            raise ManifestBuildError("init adapter artifact manifest SHA-256 does not match its bytes")
        artifact = json.loads(artifact_bytes.decode("utf-8"))
    except (durable.DurableRunnerError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestBuildError("init adapter artifact manifest is invalid") from exc
    if artifact_bytes != durable.canonical_bytes(artifact):
        raise ManifestBuildError("init adapter artifact manifest is not canonical")
    if (set(artifact) != {"schema_version", "run_id", "pins", "files"}
            or artifact.get("schema_version") != "airi.behavior-adapter-artifact.v1"
            or not isinstance(artifact.get("run_id"), str) or not artifact["run_id"]
            or not isinstance(artifact.get("pins"), dict)
            or not durable.HEX64.fullmatch(str(artifact["pins"].get("model_weight_sha256", "")))):
        raise ManifestBuildError("init adapter artifact schema is invalid")
    if artifact["pins"]["model_weight_sha256"] != args.model_sha256:
        raise ManifestBuildError("init adapter base model pin does not match training model")
    files = artifact.get("files")
    if not isinstance(files, list) or not files:
        raise ManifestBuildError("init adapter artifact inventory is invalid")
    seen: set[str] = set()
    declared: list[dict[str, Any]] = []
    for row in files:
        if (not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}
                or not isinstance(row["path"], str) or not row["path"] or row["path"] in seen
                or Path(row["path"]).is_absolute() or ".." in Path(row["path"]).parts
                or not isinstance(row["bytes"], int) or row["bytes"] < 0
                or not durable.HEX64.fullmatch(str(row["sha256"]))):
            raise ManifestBuildError("init adapter artifact inventory row is invalid")
        seen.add(row["path"])
        payload = durable._read_regular_file_snapshot(directory / row["path"], "init adapter file")
        if len(payload) != row["bytes"] or durable.sha256_bytes(payload) != row["sha256"]:
            raise ManifestBuildError("init adapter artifact inventory does not match disk")
        declared.append(dict(row))
    try:
        durable._validate_closed_model_inventory(directory, [
            *declared,
            {"path": "artifact-manifest.json", "bytes": len(artifact_bytes),
             "sha256": durable.sha256_bytes(artifact_bytes)},
        ])
    except durable.DurableRunnerError as exc:
        raise ManifestBuildError("init adapter artifact inventory is not closed") from exc
    for filename, pin in (("adapter_model.safetensors", "model_sha256"),
                          ("adapter_config.json", "config_sha256")):
        row = next((item for item in declared if item["path"] == filename), None)
        if row is None or row["sha256"] != pins[pin]:
            raise ManifestBuildError(f"init adapter {filename} pin does not match inventory")
    return {"run_id": artifact["run_id"], **pins, "files": declared}


def _closed_model_inventory(model_root: Path) -> list[dict[str, Any]]:
    """Hash every regular model-tree file and reject links/reparse entries."""
    pending = [model_root]
    files: list[Path] = []
    reparse_attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as scan:
                entries = sorted(scan, key=lambda entry: entry.name)
        except OSError as exc:
            raise ManifestBuildError("model inventory cannot be enumerated") from exc
        for entry in entries:
            path = Path(entry.path)
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as exc:
                raise ManifestBuildError("model inventory entry cannot be inspected") from exc
            if (entry.is_symlink()
                    or bool(getattr(metadata, "st_file_attributes", 0) & reparse_attribute)):
                raise ManifestBuildError("model inventory cannot contain links or reparse points")
            if entry.is_dir(follow_symlinks=False):
                pending.append(path)
            elif entry.is_file(follow_symlinks=False):
                files.append(path)
            else:
                raise ManifestBuildError("model inventory entries must be regular files or directories")

    inventory: list[dict[str, Any]] = []
    for candidate in sorted(files, key=lambda path: path.relative_to(model_root).as_posix()):
        payload = durable._read_regular_file_snapshot(candidate, "model inventory file")
        inventory.append({
            "path": candidate.relative_to(model_root).as_posix(),
            "bytes": len(payload),
            "sha256": durable.sha256_bytes(payload),
        })
    return inventory


def build_manifest(args: argparse.Namespace) -> tuple[dict[str, Any], bytes]:
    if min(
        args.seed, args.lora_r, args.lora_alpha, args.max_steps, args.batch_size,
        args.gradient_accumulation, args.max_seq_len,
        args.checkpoint_every_optimizer_steps,
    ) <= 0:
        raise ManifestBuildError("positive training configuration values are required")
    if (not math.isfinite(args.lora_dropout) or not math.isfinite(args.learning_rate)
            or not 0 <= args.lora_dropout < 1 or args.learning_rate <= 0):
        raise ManifestBuildError("dropout/learning-rate contract failure")

    _, dataset_sha256 = _require_pinned_file(
        args.dataset, args.dataset_sha256, "dataset")
    _, model_sha256 = _require_pinned_file(
        args.model_weight, args.model_sha256, "model weight")
    trainer = durable.validate_local_path(args.trainer, "trainer")
    try:
        trainer_sha256 = durable.sha256_bytes(
            durable._read_regular_file_snapshot(trainer, "trainer"))
    except durable.DurableRunnerError as exc:
        raise ManifestBuildError("trainer is not a regular file") from exc
    config = _training_config(args)
    initial_adapter = _initial_adapter(args)
    helper = trainer.parent / "behavior_training_checkpoint.py"
    try:
        helper_sha256 = durable.sha256_bytes(
            durable._read_regular_file_snapshot(helper, "checkpoint helper"))
    except durable.DurableRunnerError as exc:
        raise ManifestBuildError("checkpoint helper is not a regular file") from exc
    model_root = durable.validate_local_path(args.model_weight.parent, "model directory")
    inventory = _closed_model_inventory(model_root)
    if not inventory or not any(row["path"] == "config.json" for row in inventory):
        raise ManifestBuildError("model inventory lacks config.json")
    config_sha256 = durable.sha256_bytes(durable.canonical_bytes(config))
    manifest = {
        "schema_version": "airi.behavior-input-manifest.v3",
        "dataset_sha256": dataset_sha256,
        "model_weight_sha256": model_sha256,
        "trainer_source_sha256": trainer_sha256,
        "checkpoint_helper_source_sha256": helper_sha256,
        "model_inventory": inventory,
        "training_config": config,
        "training_config_sha256": config_sha256,
        "initial_adapter": initial_adapter,
    }
    return manifest, durable.canonical_bytes(manifest)


def _publish_nonreplacing(target: Path, payload: bytes) -> str:
    resolved = durable.validate_local_path(target, "input manifest output")
    parent = durable.validate_local_path(resolved.parent, "input manifest output parent")
    if not parent.is_dir():
        raise ManifestBuildError("input manifest output parent must already exist")
    try:
        durable.publish_new_bytes(resolved, payload, "input manifest output")
    except durable.DurableRunnerError as exc:
        if os.path.lexists(resolved):
            raise ManifestBuildError("input manifest output already exists") from exc
        raise ManifestBuildError("input manifest non-replacing publication failed") from exc
    published = durable._read_regular_file_snapshot(resolved, "input manifest output")
    digest = durable.sha256_bytes(published)
    if published != payload or digest != durable.sha256_bytes(payload):
        raise ManifestBuildError("published input manifest failed byte verification")
    return digest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a canonical durable AIRI behavior-training input manifest")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--dataset-sha256", required=True)
    parser.add_argument("--model-weight", type=Path, required=True)
    parser.add_argument("--model-sha256", required=True)
    parser.add_argument("--trainer", type=Path, required=True)
    parser.add_argument("--mode", choices=["cuda-qlora", "cpu-smoke"], required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--lora-r", type=int, required=True)
    parser.add_argument("--lora-alpha", type=int, required=True)
    parser.add_argument("--lora-dropout", type=float, required=True)
    parser.add_argument("--learning-rate", type=float, required=True)
    parser.add_argument("--max-steps", type=int, required=True)
    parser.add_argument("--batch-size", type=int, required=True)
    parser.add_argument("--gradient-accumulation", type=int, required=True)
    parser.add_argument("--max-seq-len", type=int, required=True)
    parser.add_argument("--checkpoint-every-optimizer-steps", type=int, required=True)
    parser.add_argument("--deterministic-validation", action="store_true")
    parser.add_argument("--init-adapter-dir", type=Path)
    parser.add_argument("--init-adapter-model-sha256")
    parser.add_argument("--init-adapter-config-sha256")
    parser.add_argument("--init-adapter-artifact-manifest-sha256")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest, payload = build_manifest(args)
    digest = _publish_nonreplacing(args.output, payload)
    durable.validate_input_manifest_content(
        args.output, digest, _trainer_arguments(
            manifest["training_config"], manifest["initial_adapter"], args.init_adapter_dir),
        manifest["trainer_source_sha256"], manifest["dataset_sha256"],
        manifest["model_weight_sha256"],
        manifest["training_config"]["checkpoint_every_optimizer_steps"],
        manifest["checkpoint_helper_source_sha256"],
    )
    receipt = {
        "schema_version": "airi.behavior-input-manifest-build-receipt.v1",
        "path": str(args.output.resolve()),
        "sha256": digest,
        "training_config_sha256": manifest["training_config_sha256"],
    }
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ManifestBuildError, durable.DurableRunnerError) as exc:
        print(f"input manifest build refused: {exc}", file=sys.stderr)
        raise SystemExit(2)
