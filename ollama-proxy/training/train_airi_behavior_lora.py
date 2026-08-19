"""Behavior LoRA trainer — CUDA QLoRA for production, a bounded CPU smoke for plumbing.

This is the T2-b counterpart of the behavior data pipeline. It consumes the
chat-format export (`export_behavior_chat_dataset.py`) pinned by SHA-256, so
nothing that skipped the human-review path can reach a training run. Labels
mask everything before the assistant turn: the model learns to produce the
reviewed answer given the exact operational prompt shape, not to imitate the
prompt itself.

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
import json
import re
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
        messages = row.get("messages")
        if (not isinstance(messages, list) or len(messages) != 3
                or [m.get("role") for m in messages] != ["system", "user", "assistant"]
                or not all(isinstance(m.get("content"), str) and m["content"] for m in messages)):
            raise BehaviorTrainingError(f"{row.get('id')}: messages must be system/user/assistant")
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
    full_ids = tokenizer(full, add_special_tokens=False)["input_ids"][:max_seq_len]
    labels = [-100] * min(len(prompt_ids), len(full_ids)) + full_ids[len(prompt_ids):]
    labels = labels[: len(full_ids)]
    if all(label == -100 for label in labels):
        raise BehaviorTrainingError("assistant span was truncated away; raise max_seq_len")
    return {"input_ids": full_ids, "labels": labels}


def run_training(args: argparse.Namespace) -> dict[str, Any]:
    import torch  # noqa: PLC0415 — heavy import stays inside the entrypoint
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    rows = load_pinned_dataset(args.dataset, args.dataset_sha256)
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
        from transformers import BitsAndBytesConfig
        quantization = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16)
        max_steps = args.max_steps
        device = "cuda"

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
    model = get_peft_model(model, LoraConfig(
        r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=args.lora_dropout,
        task_type="CAUSAL_LM", target_modules="all-linear"))

    encoded = [encode_example(tokenizer, row["messages"], args.max_seq_len) for row in rows]
    pad_id = tokenizer.pad_token_id

    def batches():
        while True:
            for start in range(0, len(encoded), args.batch_size):
                chunk = encoded[start:start + args.batch_size]
                width = max(len(example["input_ids"]) for example in chunk)
                input_ids = torch.tensor(
                    [example["input_ids"] + [pad_id] * (width - len(example["input_ids"]))
                     for example in chunk])
                labels = torch.tensor(
                    [example["labels"] + [-100] * (width - len(example["labels"]))
                     for example in chunk])
                attention = (input_ids != pad_id).long()
                yield input_ids.to(device), labels.to(device), attention.to(device)

    optimizer = torch.optim.AdamW(
        (parameter for parameter in model.parameters() if parameter.requires_grad),
        lr=args.learning_rate)
    model.train()
    losses: list[float] = []
    iterator = batches()
    for step in range(max_steps):
        input_ids, labels, attention = next(iterator)
        loss = model(input_ids=input_ids, labels=labels, attention_mask=attention).loss
        (loss / args.gradient_accumulation).backward()
        if (step + 1) % args.gradient_accumulation == 0 or step + 1 == max_steps:
            optimizer.step()
            optimizer.zero_grad()
        losses.append(float(loss.detach()))

    first = sum(losses[:3]) / min(3, len(losses))
    last = sum(losses[-3:]) / min(3, len(losses))
    if args.mode == "cpu-smoke" and not last < first:
        raise BehaviorTrainingError(
            f"smoke loss did not fall ({first:.3f} -> {last:.3f}); the pipeline is suspect")

    output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output))
    return {
        "mode": args.mode,
        "samples": len(rows), "steps": max_steps,
        "loss_first3_mean": round(first, 4), "loss_last3_mean": round(last, 4),
        "adapter_dir": str(output),
        "dataset_sha256": args.dataset_sha256,
        "training_authorization": args.mode == "cuda-qlora",
        "note": ("plumbing smoke only — NOT a trained adapter"
                 if args.mode == "cpu-smoke" else "adapter must pass the T3 gate before adoption"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AIRI behavior LoRA trainer")
    parser.add_argument("--dataset", type=Path, required=True, help="chat-format export JSONL")
    parser.add_argument("--dataset-sha256", required=True, help="익스포터가 출력한 sha256 핀")
    parser.add_argument("--model-dir", required=True, help="로컬 HF 스냅샷 디렉터리 (허브 이름 불가)")
    parser.add_argument("--output", required=True, help="어댑터 출력 디렉터리")
    parser.add_argument("--mode", choices=["cuda-qlora", "cpu-smoke"], required=True)
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
