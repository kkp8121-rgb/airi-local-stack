#!/usr/bin/env python3
"""Local-only, adapter-only AIRI QLoRA scaffold with a repeated strict gate."""
from __future__ import annotations

# Set fail-closed offline and telemetry controls before *any* third-party import.
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["DISABLE_TELEMETRY"] = "1"
os.environ["WANDB_DISABLED"] = "true"
os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"

import argparse
import ctypes
import hashlib
import json
import platform
import re
import stat
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from verify_airi_style_dataset import (
    CATEGORY_TAXONOMY,
    MIN_REVIEWED_COUNT,
    POLICY_VERSION,
    RFC3339_RE,
    REPORT_FIELDS,
    SCHEMA_VERSION,
    GateError,
    VerificationResult,
    sha256_file,
    verify_reviewed_dataset,
)

LICENSE_ACK = "I_HAVE_REVIEWED_AND_ACCEPTED_MODEL_LICENSE"
MIN_VRAM_BYTES = 8 * 1024**3
EXPECTED_PARAMETER_MIN = 1_500_000_000
EXPECTED_PARAMETER_MAX = 3_500_000_000
HEX_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
REMOTE_DRIVE = 4
ALLOWED_OUTPUT_FILES = {"adapter_config.json", "adapter_model.safetensors", "README.md", "training-metadata.json", "success-manifest.json", "FAILED.txt"}


class TrainingRefused(RuntimeError):
    pass


def _sha256(value: str, label: str) -> str:
    value = value.strip().lower()
    if not HEX_SHA256.fullmatch(value): raise TrainingRefused(f"{label} must be a SHA-256 hex digest")
    return value


def _is_within(child: Path, parent: Path) -> bool:
    try: child.relative_to(parent); return True
    except ValueError: return False


def reject_network_path(path: Path, label: str) -> Path:
    raw = str(path)
    if raw.startswith(("\\\\", "//")): raise TrainingRefused(f"{label}: UNC/network paths are prohibited")
    expanded = path.expanduser()
    if expanded.is_symlink(): raise TrainingRefused(f"{label}: symlink paths are prohibited")
    if os.name == "nt" and expanded.drive:
        try:
            kind = ctypes.windll.kernel32.GetDriveTypeW(f"{expanded.drive}\\")
        except (AttributeError, OSError) as exc:
            raise TrainingRefused(f"{label}: cannot prove drive is local") from exc
        if kind == REMOTE_DRIVE: raise TrainingRefused(f"{label}: mapped network drives are prohibited")
    return expanded.resolve()


def local_hf_model_dir(value: str) -> Path:
    if "://" in value or value.lower().startswith("ollama:") or value.lower().endswith(".gguf") or re.fullmatch(r"[^\\/:]+:[^\\/]+", value):
        raise TrainingRefused("--model-dir must be a local Hugging Face directory; remote IDs, Ollama tags, and GGUF are refused")
    path = reject_network_path(Path(value), "model directory")
    if not path.is_dir() or path.is_symlink() or not (path / "config.json").is_file():
        raise TrainingRefused("--model-dir must be a local, non-symlink Hugging Face snapshot containing config.json")
    items = list(path.rglob("*")); files = [item for item in items if item.is_file()]
    if not files or any(item.is_symlink() for item in items) or any(item.suffix.casefold() == ".gguf" for item in files):
        raise TrainingRefused("model snapshot must have regular non-GGUF files only")
    return path


def snapshot_hash(directory: Path) -> str:
    digest = hashlib.sha256()
    items = list(directory.rglob("*"))
    if any(item.is_symlink() for item in items): raise TrainingRefused("model snapshot contains a symlink")
    files = sorted(item for item in items if item.is_file())
    if not files: raise TrainingRefused("model snapshot is empty")
    for item in files:
        if item.is_symlink(): raise TrainingRefused(f"model snapshot contains a symlink: {item}")
        digest.update(item.relative_to(directory).as_posix().encode("utf-8") + b"\0")
        digest.update(sha256_file(item).encode("ascii") + b"\n")
    return digest.hexdigest()


def expected_exaone_config(model_dir: Path) -> dict[str, Any]:
    try: config = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise TrainingRefused("model config.json is unreadable") from exc
    if not isinstance(config, dict): raise TrainingRefused("model config must be an object")
    model_type, architectures = config.get("model_type"), config.get("architectures")
    if not isinstance(model_type, str) or "exaone" not in model_type.casefold() or not isinstance(architectures, list) or not any(isinstance(item, str) and "exaone" in item.casefold() and "causallm" in item.casefold() for item in architectures):
        raise TrainingRefused("model snapshot is not an expected EXAONE causal-LM architecture")
    fields = ("hidden_size", "num_hidden_layers", "num_attention_heads", "intermediate_size", "vocab_size")
    if any(not isinstance(config.get(name), int) for name in fields): raise TrainingRefused("model config lacks required EXAONE 2.4B shape fields")
    hidden, layers, heads, intermediate, vocab = (config[name] for name in fields)
    if not (2048 <= hidden <= 4096 and 20 <= layers <= 48 and 16 <= heads <= 64 and hidden % heads == 0 and hidden * 2 <= intermediate <= hidden * 6 and 30_000 <= vocab <= 300_000):
        raise TrainingRefused("model config lies outside the supported EXAONE 2.4B architecture range")
    estimate = layers * (4 * hidden * hidden + 3 * hidden * intermediate) + vocab * hidden
    if not EXPECTED_PARAMETER_MIN <= estimate <= EXPECTED_PARAMETER_MAX:
        raise TrainingRefused("model config's estimated parameter count is outside the EXAONE 2.4B range")
    return {"model_type": model_type, "architectures": architectures, "hidden_size": hidden, "num_hidden_layers": layers, "num_attention_heads": heads, "intermediate_size": intermediate, "vocab_size": vocab, "estimated_parameter_count": estimate}


@contextmanager
def advisory_snapshot_lock(paths: list[Path]) -> Iterator[None]:
    """Cooperative local lock plus before/after hashing; lock failure is a refusal."""
    handles: list[Any] = []
    try:
        for path in sorted(set(paths)):
            handle = path.open("rb")
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBRLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            handles.append(handle)
        yield
    except OSError as exc:
        raise TrainingRefused("could not acquire an advisory local snapshot lock") from exc
    finally:
        for handle in reversed(handles):
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError: pass
            handle.close()


def _closed_gate_report(path: Path, expected_hash: str, verified: VerificationResult) -> None:
    if not path.is_file() or path.is_symlink(): raise TrainingRefused("gate report must be a regular local file")
    if sha256_file(path) != expected_hash: raise TrainingRefused("gate report hash does not match --expected-gate-report-sha256")
    if path.stat().st_mode & stat.S_IWUSR: raise TrainingRefused("gate report must be read-only")
    try: report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise TrainingRefused("gate report is invalid JSON") from exc
    if not isinstance(report, dict) or set(report) != REPORT_FIELDS: raise TrainingRefused("gate report has an open or invalid schema")
    expected = verified.report_payload
    stable = set(REPORT_FIELDS) - {"created_at"}
    if any(report.get(key) != expected.get(key) for key in stable) or report.get("schema_version") != SCHEMA_VERSION or report.get("policy_version") != POLICY_VERSION or report.get("immutable") is not True or report.get("gate") != "approved":
        raise TrainingRefused("gate report does not exactly bind the newly re-verified dataset, manifest, fixtures, policy, reviewers, and thresholds")
    if not isinstance(report["created_at"], str) or not RFC3339_RE.fullmatch(report["created_at"]):
        raise TrainingRefused("gate report created_at is invalid")


def _assert_train_rows(rows: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        source, group = row["provenance"]["source"].casefold(), row["partition"]["group"].casefold()
        if row["review"]["status"] != "approved" or row["training_eligible"] is not True:
            raise TrainingRefused(f"record {index} was not explicitly approved and eligible")
        if row["id"].startswith("seed-") or any(term in source or term in group for term in ("seed", "pending", "reserved")):
            raise TrainingRefused(f"record {index} is seed/reserved material")
        if row["split"] == "train":
            if row["partition"]["tier"] != "S1": raise TrainingRefused(f"record {index}: only S1 train records may reach the trainer")
            selected.append(row)
    if not selected: raise TrainingRefused("re-verified dataset has no S1 training records")
    return selected


def _validate_options(args: argparse.Namespace) -> None:
    if args.license_approved != LICENSE_ACK: raise TrainingRefused("explicit local model-license acknowledgement is required")
    if not (64 <= args.max_length <= 1024): raise TrainingRefused("max-length must be 64..1024")
    if args.batch_size != 1: raise TrainingRefused("batch-size is fixed to 1 for the 8GiB safety envelope")
    if not (1 <= args.gradient_accumulation_steps <= 64): raise TrainingRefused("gradient-accumulation-steps must be 1..64")
    if not (4 <= args.lora_rank <= 32): raise TrainingRefused("lora-rank must be 4..32")
    if not (0 < args.epochs <= 3 and 0 < args.learning_rate <= 0.0002): raise TrainingRefused("epochs/learning-rate exceed the safe cap")
    if not (0 <= args.seed <= 2**32 - 1 and 0 <= args.data_seed <= 2**32 - 1): raise TrainingRefused("seed/data-seed are out of range")


def _preflight_cuda(torch: Any, config: dict[str, Any]) -> dict[str, Any]:
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise TrainingRefused("exactly one visible CUDA device is required; CPU/multi-device fallback is refused")
    free, total = torch.cuda.mem_get_info(0)
    model_aware_minimum = max(MIN_VRAM_BYTES, int(config["estimated_parameter_count"] * 0.75) + 2 * 1024**3)
    if total < MIN_VRAM_BYTES or free < model_aware_minimum:
        raise TrainingRefused("insufficient total/free VRAM for the EXAONE 2.4B 4-bit safety envelope")
    driver = getattr(torch._C, "_cuda_getDriverVersion", lambda: None)()
    return {"cuda_device": torch.cuda.get_device_name(0), "cuda_runtime": torch.version.cuda, "cuda_driver": driver, "vram_total_bytes": total, "vram_free_bytes": free, "model_aware_minimum_free_bytes": model_aware_minimum, "torch": torch.__version__}


def _assert_hash_contract(expected: dict[Path, str], model_dir: Path, expected_model_hash: str) -> None:
    for path, digest in expected.items():
        if sha256_file(path) != digest: raise TrainingRefused(f"TOCTOU detected: {path.name} changed after gate verification")
    if snapshot_hash(model_dir) != expected_model_hash: raise TrainingRefused("TOCTOU detected: model snapshot changed")


def _new_output_and_stage(output: Path, protected: list[Path]) -> tuple[Path, Path]:
    output = reject_network_path(output, "output directory")
    if output.exists() or output.is_symlink(): raise TrainingRefused("final output directory must not exist; no overwrite or resume is permitted")
    if not output.parent.is_dir() or output.parent.is_symlink(): raise TrainingRefused("output parent must be an existing local directory")
    for path in protected:
        if _is_within(output, path) or _is_within(path, output): raise TrainingRefused("output must not be an ancestor/descendant of the model or review artifacts")
    stage = output.parent / f".{output.name}.staging-{uuid.uuid4().hex}"
    try: stage.mkdir(mode=0o700)
    except OSError as exc: raise TrainingRefused("exclusive staging directory creation failed") from exc
    return output, stage


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _adapter_hashes(stage: Path) -> dict[str, str]:
    files = sorted(item for item in stage.rglob("*") if item.is_file())
    if any(item.is_dir() for item in stage.iterdir()) or any(item.name not in ALLOWED_OUTPUT_FILES for item in files):
        raise TrainingRefused("adapter staging contains unexpected files; base-weight copies are prohibited")
    if not (stage / "adapter_config.json").is_file() or not (stage / "adapter_model.safetensors").is_file():
        raise TrainingRefused("PEFT did not produce the required safe adapter-only files")
    return {item.relative_to(stage).as_posix(): sha256_file(item) for item in files if item.name != "success-manifest.json"}


def train(args: argparse.Namespace) -> None:
    _validate_options(args)
    dataset = reject_network_path(args.dataset, "dataset")
    manifest = reject_network_path(args.review_manifest, "review manifest")
    c0_fixture = reject_network_path(args.c0_fixture, "C0 fixture")
    s1_fixture = reject_network_path(args.s1_fixture, "S1 fixture")
    gate_report = reject_network_path(args.gate_report, "gate report")
    model_dir = local_hf_model_dir(args.model_dir)
    expected_dataset_hash = _sha256(args.expected_dataset_sha, "expected dataset hash")
    expected_model_hash = _sha256(args.expected_model_snapshot_sha, "expected model snapshot hash")
    expected_report_hash = _sha256(args.expected_gate_report_sha256, "expected gate report hash")
    stage: Path | None = None
    try:
        protected = [dataset, manifest, c0_fixture, s1_fixture, gate_report, model_dir]
        output, stage = _new_output_and_stage(args.output_dir, protected)
        lock_files = [dataset, manifest, c0_fixture, s1_fixture, gate_report, *[item for item in model_dir.rglob("*") if item.is_file()]]
        with advisory_snapshot_lock(lock_files):
            config = expected_exaone_config(model_dir)
            verified = verify_reviewed_dataset(dataset, manifest, c0_fixture, s1_fixture)
            if verified.dataset_sha256 != expected_dataset_hash: raise TrainingRefused("dataset hash does not match the expected reviewed snapshot")
            _closed_gate_report(gate_report, expected_report_hash, verified)
            training_rows = _assert_train_rows(verified.rows)
            contract = {dataset: verified.dataset_sha256, manifest: verified.manifest_sha256, c0_fixture: verified.c0_fixture_sha256, s1_fixture: verified.s1_fixture_sha256, gate_report: expected_report_hash}
            if snapshot_hash(model_dir) != expected_model_hash: raise TrainingRefused("model snapshot hash does not match the expected local EXAONE snapshot")

            # These imports remain after the offline/telemetry environment has been forced above.
            import bitsandbytes
            import datasets
            import peft
            import torch
            import transformers
            from datasets import Dataset
            from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, Trainer, TrainingArguments, default_data_collator, set_seed

            runtime = _preflight_cuda(torch, config)
            torch.use_deterministic_algorithms(True)
            torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
            set_seed(args.seed)
            tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True, trust_remote_code=False)
            if tokenizer.pad_token is None: tokenizer.pad_token = tokenizer.eos_token
            quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16)
            model = AutoModelForCausalLM.from_pretrained(str(model_dir), local_files_only=True, trust_remote_code=False, quantization_config=quant, torch_dtype=torch.float16, device_map={"": 0})
            hf_device_map = getattr(model, "hf_device_map", {"": 0})
            if not isinstance(hf_device_map, dict) or not hf_device_map or any(value != 0 for value in hf_device_map.values()):
                raise TrainingRefused("model load placed weights on CPU/disk/another device; refusing fallback")
            model.config.use_cache = False
            model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
            model = get_peft_model(model, LoraConfig(r=args.lora_rank, lora_alpha=args.lora_rank * 2, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM", target_modules="all-linear"))
            def tokenize(item: dict[str, Any]) -> dict[str, Any]:
                text = "User: " + item["prompt"] + "\nAIRI: " + item["answer"] + tokenizer.eos_token
                encoded = tokenizer(text, truncation=True, max_length=args.max_length)
                encoded["labels"] = encoded["input_ids"].copy(); return encoded
            encoded = Dataset.from_list(training_rows).map(tokenize, remove_columns=list(training_rows[0]))
            metadata = {"policy_version": POLICY_VERSION, "created_at": datetime.now(timezone.utc).isoformat(), "adapter_only": True, "base_weights_copied": False, "base_weights_merged": False, "license_acknowledged": True, "dataset_sha256": expected_dataset_hash, "model_snapshot_sha256": expected_model_hash, "gate_report_sha256": expected_report_hash, "review_manifest_sha256": verified.manifest_sha256, "c0_fixture_sha256": verified.c0_fixture_sha256, "s1_fixture_sha256": verified.s1_fixture_sha256, "model_config": config, "effective_parameters": {"seed": args.seed, "data_seed": args.data_seed, "full_determinism": True, "lora_rank": args.lora_rank, "lora_alpha": args.lora_rank * 2, "lora_dropout": 0.05, "max_length": args.max_length, "batch_size": args.batch_size, "gradient_accumulation_steps": args.gradient_accumulation_steps, "epochs": args.epochs, "learning_rate": args.learning_rate, "quantization": "NF4 + double quant + fp16", "compute_dtype": "float16", "gradient_checkpointing": True, "target_modules": "all-linear", "device_map": {"": 0}}, "libraries": {"torch": torch.__version__, "transformers": transformers.__version__, "datasets": datasets.__version__, "peft": peft.__version__, "bitsandbytes": bitsandbytes.__version__}, "runtime": runtime, "python": sys.version, "platform": platform.platform()}
            _write_json(stage / "training-metadata.json", metadata)
            trainer = Trainer(model=model, args=TrainingArguments(output_dir=str(stage), num_train_epochs=args.epochs, per_device_train_batch_size=args.batch_size, gradient_accumulation_steps=args.gradient_accumulation_steps, learning_rate=args.learning_rate, fp16=True, tf32=False, seed=args.seed, data_seed=args.data_seed, full_determinism=True, dataloader_num_workers=0, logging_steps=5, save_strategy="no", report_to=[]), train_dataset=encoded, data_collator=default_data_collator)
            trainer.train()
            _assert_hash_contract(contract, model_dir, expected_model_hash)
            model.save_pretrained(str(stage), safe_serialization=True)  # PEFT adapter files only; no base save/merge.
            adapter_hashes = _adapter_hashes(stage)
            success = {"status": "success", "created_at": datetime.now(timezone.utc).isoformat(), "adapter_only": True, "adapter_sha256": adapter_hashes, "input_hashes": {"dataset": expected_dataset_hash, "model_snapshot": expected_model_hash, "gate_report": expected_report_hash, "review_manifest": verified.manifest_sha256, "c0_fixture": verified.c0_fixture_sha256, "s1_fixture": verified.s1_fixture_sha256}}
            _write_json(stage / "success-manifest.json", success)
            _assert_hash_contract(contract, model_dir, expected_model_hash)
            os.replace(stage, output)  # Atomic local promotion; final output did not exist.
            stage = None
    except Exception as exc:
        if stage is not None and stage.exists():
            try: _write_json(stage / "FAILED.txt", {"status": "failed", "at": datetime.now(timezone.utc).isoformat(), "reason": str(exc)})
            except OSError: pass
        if isinstance(exc, TrainingRefused): raise
        if isinstance(exc, GateError): raise TrainingRefused(f"strict review gate rejected input: {exc}") from exc
        raise TrainingRefused(f"training failed before publication; staging was retained: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Local, reviewed, adapter-only EXAONE 2.4B QLoRA scaffold.")
    parser.add_argument("--dataset", type=Path, required=True); parser.add_argument("--review-manifest", type=Path, required=True)
    parser.add_argument("--c0-fixture", type=Path, required=True); parser.add_argument("--s1-fixture", type=Path, required=True)
    parser.add_argument("--gate-report", type=Path, required=True); parser.add_argument("--model-dir", required=True); parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-dataset-sha", required=True); parser.add_argument("--expected-model-snapshot-sha", required=True); parser.add_argument("--expected-gate-report-sha256", required=True)
    parser.add_argument("--license-approved", default="")
    parser.add_argument("--seed", type=int, default=20260808); parser.add_argument("--data-seed", type=int, default=20260808)
    parser.add_argument("--lora-rank", type=int, default=16); parser.add_argument("--max-length", type=int, default=512); parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--epochs", type=float, default=1.0); parser.add_argument("--learning-rate", type=float, default=0.0001); parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    args = parser.parse_args()
    try: train(args)
    except TrainingRefused as exc: print(f"REFUSED: {exc}", file=sys.stderr); return 2
    return 0


if __name__ == "__main__": raise SystemExit(main())
