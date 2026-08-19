"""Synthesize the behavior-SFT pending queue — deterministic, review-gated, never trainable as-is.

The measured failures this targets are behaviors, not knowledge: briefed facts
used in 7% of turns, three refusals of an explicit instruction, register drift.
Each record teaches one behavior in the exact shape the runtime produces it —
fact_recall pairs carry the director briefing verbatim in the format the
simulation injects, so the model learns to read the actual operational memo.

Everything is enumerated from the config table (no magic values, no RNG), and
every answer must pass the broadcast register scorer before it is written: a
polite-register violation in a training answer would train the exact defect the
gates exist to catch. Output records are `pending`/`training_eligible: false` —
the human-review CLI and the trainer's verification gate stand between this
file and any actual training, same as the style pipeline.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "behavior_synthesis_config_v1.json"
SCHEMA_PATH = HERE / "seed" / "airi_behavior_pending_record.schema.json"
DEFAULT_OUTPUT = HERE / "seed" / "airi_behavior_seed_pending.jsonl"

sys.path.insert(0, str(HERE.parent / "eval" / "broadcast_chat"))
import run_broadcast_chat_ab as ab  # noqa: E402


class BehaviorSynthesisError(ValueError):
    """Fail closed on a malformed config or an answer the gates would reject."""


def _jongseong(word: str) -> bool:
    """True when the final Hangul syllable carries a batchim."""
    for character in reversed(word.strip()):
        code = ord(character)
        if 0xAC00 <= code <= 0xD7A3:
            return (code - 0xAC00) % 28 != 0
    return False


_PARTICLE_TOKENS = {
    "{j_ya}": ("이야", "야"),
    "{j_eun}": ("은", "는"),
    "{j_i}": ("이", "가"),
    "{j_rago}": ("이라고", "라고"),
}


def apply_particles(template: str, value: str) -> str:
    """Fill {value}, then resolve each particle token from the word before it.

    A particle agrees with whatever it attaches to — "별명{j_eun}" needs
    별명's batchim (은) while "{value}{j_ya}" needs the value's — so tokens
    are resolved left to right against the text rendered so far.
    """
    text = template.replace("{value}", value)
    rendered: list[str] = []
    position = 0
    while position < len(text):
        for token, (with_batchim, without_batchim) in _PARTICLE_TOKENS.items():
            if text.startswith(token, position):
                rendered.append(with_batchim if _jongseong("".join(rendered)) else without_batchim)
                position += len(token)
                break
        else:
            rendered.append(text[position])
            position += 1
    return "".join(rendered)


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != "airi.behavior-synthesis-config.v1":
        raise BehaviorSynthesisError("unexpected config schema")
    if config.get("synthetic_only") is not True:
        raise BehaviorSynthesisError("config must be synthetic_only")
    return config


def validate_answer(answer: str, config: dict[str, Any]) -> None:
    """Reject any answer the broadcast register gate would flag."""
    minimum = int(config["answer_min_chars"])
    maximum = int(config["answer_max_chars"])
    if not minimum <= len(answer) <= maximum:
        raise BehaviorSynthesisError(f"answer length {len(answer)} outside [{minimum},{maximum}]: {answer!r}")
    score = ab.score_response(answer)
    if "v_polite_response" in score.get("violations", []):
        raise BehaviorSynthesisError(f"polite register in training answer: {answer!r}")


def iter_records(config: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Enumerate every (behavior, prompt, answer) triple the config defines."""
    directive = config["briefing_directive"]

    for fact in config["fact_recall"]["facts"]:
        for value in fact["values"]:
            statement = apply_particles(fact["statement"], value)
            briefing = directive.format(statement=statement)
            for question_index, question in enumerate(fact["questions"]):
                answer = apply_particles(
                    fact["answers"][question_index % len(fact["answers"])], value)
                yield {"behavior": "fact_recall", "briefing": briefing,
                       "prompt": question, "answer": answer,
                       "template": f"fact:{fact['slot']}:q{question_index}"}

    for scenario in config["addressee"]["scenarios"]:
        for index, prompt in enumerate(scenario["prompts"]):
            yield {"behavior": "addressee", "briefing": "",
                   "prompt": prompt,
                   "answer": scenario["answers"][index % len(scenario["answers"])],
                   "template": f"addressee:{scenario['name']}:p{index}"}

    for index, pair in enumerate(config["register"]["pairs"]):
        yield {"behavior": "register", "briefing": "",
               "prompt": pair["prompt"], "answer": pair["answer"],
               "template": f"register:p{index}"}

    for item_index, item in enumerate(config["substance"]["items"]):
        for answer_index, answer in enumerate(item["answers"]):
            yield {"behavior": "substance", "briefing": "",
                   "prompt": item["prompt"], "answer": answer,
                   "template": f"substance:i{item_index}:a{answer_index}"}


def synthesize(config: dict[str, Any]) -> list[dict[str, Any]]:
    split_cycle = list(config["split_cycle"])
    records: list[dict[str, Any]] = []
    counters: dict[str, int] = {}
    for entry in iter_records(config):
        validate_answer(entry["answer"], config)
        behavior = entry["behavior"]
        counters[behavior] = counters.get(behavior, 0) + 1
        index = counters[behavior]
        records.append({
            "id": f"bseed-{behavior}-{index:04d}",
            "split": split_cycle[(len(records)) % len(split_cycle)],
            "behavior": behavior,
            "briefing": entry["briefing"],
            "prompt": entry["prompt"],
            "answer": entry["answer"],
            "partition": {"tier": "S1", "group": f"bpending-{behavior.replace(chr(95), chr(45))}-{index:04d}"},
            "review": {"status": "pending", "reviewer": "", "approved_at": ""},
            "provenance": {"synthetic": True, "source": "behavior-synthesizer-v1",
                           "template": entry["template"]},
            "training_eligible": False,
        })
    identifiers = [record["id"] for record in records]
    if len(set(identifiers)) != len(identifiers):
        raise BehaviorSynthesisError("duplicate record id")
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="behavior-SFT pending queue synthesizer")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stats-only", action="store_true", help="쓰지 않고 내용 없는 집계만 출력")
    args = parser.parse_args(argv)

    records = synthesize(load_config())
    counts: dict[str, int] = {}
    for record in records:
        counts[record["behavior"]] = counts.get(record["behavior"], 0) + 1
    splits = {split: sum(1 for record in records if record["split"] == split)
              for split in ("train", "dev", "test")}
    summary = {"total": len(records), "behaviors": counts, "splits": splits,
               "training_eligible": False, "review_status": "pending"}
    if not args.stats_only:
        payload = "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")) for record in records) + "\n"
        args.output.write_text(payload, encoding="utf-8", newline="\n")
        summary["output"] = str(args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
