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
import json
import re
import sys
import random
from collections import Counter
from pathlib import Path
from typing import Any

CPU_SMOKE_MAX_SAMPLES = 16
CPU_SMOKE_MAX_STEPS = 20
DEFAULTS = {
    "lora_r": 16, "lora_alpha": 32, "lora_dropout": 0.05,
    "learning_rate": 2e-4, "max_steps": 300, "batch_size": 2,
    "gradient_accumulation": 8, "max_seq_len": 1024,
}


class BehaviorTrainingError(ValueError):
    """Fail closed on anything that is not a pinned, reviewed, local setup."""


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
    return path


def require_local_model_dir(value: str) -> Path:
    """A model is a local directory snapshot, never a hub name."""
    path = Path(value)
    reject_network_path(path, "model dir")
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
    import torch  # noqa: PLC0415 — heavy import stays inside the entrypoint
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer

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
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model_kwargs: dict[str, Any] = {"local_files_only": True}
    if quantization is not None:
        model_kwargs["quantization_config"] = quantization
        model_kwargs["device_map"] = {"": 0}
    model = AutoModelForCausalLM.from_pretrained(str(model_dir), **model_kwargs)
    if quantization is None:
        model = model.to(device)
        verified_model_sha256 = "cpu-smoke-not-pinned"
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
    model.train()
    losses: list[float] = []
    dev_loss_history: list[dict[str, Any]] = []
    best_state: dict[str, Any] | None = None
    encoded_by_row = {id(row): example for row, example in zip(rows, encoded)}
    step = 0
    epoch = 0
    pending_microbatches = 0
    optimizer_steps = 0
    while step < max_steps:
        ordered = epoch_group_order(rows, args.seed, epoch)
        epoch_examples = [encoded_by_row[id(row)] for row in ordered]
        completed_epoch = True
        for input_ids, labels, attention in batches(epoch_examples):
            if step >= max_steps:
                completed_epoch = False
                break
            loss = model(input_ids=input_ids, labels=labels, attention_mask=attention).loss
            (loss / args.gradient_accumulation).backward()
            step += 1
            pending_microbatches += 1
            if pending_microbatches == args.gradient_accumulation:
                optimizer.step()
                optimizer.zero_grad()
                optimizer_steps += 1
                pending_microbatches = 0
            losses.append(float(loss.detach()))
        # Selection must observe a post-optimizer model.  Flush both a normal
        # epoch tail and the final partial epoch rather than carrying gradients
        # across their evaluation boundary.
        optimizer_steps += flush_epoch_accumulation(optimizer, pending_microbatches)
        pending_microbatches = 0
        # CUDA selects on every full epoch and the final partial epoch. CPU
        # deliberately records that it made no selection to keep smoke bounded.
        if args.mode == "cuda-qlora" and (completed_epoch or step == max_steps):
            current_dev_loss = dev_loss()
            record = {"epoch": epoch + 1, "step": step, "loss": current_dev_loss}
            dev_loss_history.append(record)
            best_state = consider_best_state(best_state, current_dev_loss, step, epoch + 1, model)
        epoch += 1

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
    temporary_output.replace(output)
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
        "order_strategy": "seeded-scenario-group-then-row-shuffle",
        "order_seed": args.seed,
        "dev_loss_history": dev_loss_history,
        "selected_dev_step": best_state["step"] if best_state is not None else None,
        "selected_dev_epoch": best_state["epoch"] if best_state is not None else None,
        "selected_dev_loss": best_state["loss"] if best_state is not None else None,
        "loss_first3_mean": round(first, 4), "loss_last3_mean": round(last, 4),
        "adapter_dir": str(output),
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
    if args.report is not None:
        report = reject_network_path(args.report, "report")
        report.parent.mkdir(parents=True, exist_ok=True)
        temporary = report.with_name(report.name + ".tmp")
        temporary.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n")
        temporary.replace(report)
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
    for key, value in DEFAULTS.items():
        flag = "--" + key.replace("_", "-")
        parser.add_argument(flag, type=type(value), default=value)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_training(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
