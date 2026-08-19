"""Verify the reviewed behavior dataset and export it as chat-format SFT JSONL.

This is the last data-side step before the GPU: it re-checks every eligibility
condition (approved review, human reviewer, register gate, schema fields) and
assembles the exact conversation the runtime produces — system prompt equals
the broadcast system content, with the record's briefing appended for
fact_recall exactly the way the simulation injects it, user equals the chat
line with the runtime `[YouTube] ` prefix, assistant equals the reviewed
answer. Training on any other shape would teach a distribution the proxy never
serves.

The export refuses pending or unattributed records, so the only path from
synthesis to this file runs through the operator's review reply.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_REVIEWED = HERE / "seed" / "airi_behavior_reviewed.jsonl"
DEFAULT_OUTPUT = HERE / "seed" / "airi_behavior_chat_sft.jsonl"

sys.path.insert(0, str(HERE.parent / "eval" / "broadcast_chat"))
import run_broadcast_chat_ab as ab  # noqa: E402


class BehaviorExportError(ValueError):
    """Fail closed on anything that is not a fully reviewed, gated record."""


def verify_record(record: dict) -> None:
    review = record.get("review") or {}
    if record.get("training_eligible") is not True:
        raise BehaviorExportError(f"{record.get('id')}: training_eligible 아님")
    if review.get("status") != "approved" or not str(review.get("reviewer", "")).strip():
        raise BehaviorExportError(f"{record.get('id')}: 승인·검수자 누락")
    if not str(review.get("approved_at", "")).strip():
        raise BehaviorExportError(f"{record.get('id')}: 검수 시점 누락")
    answer = record.get("answer") or ""
    score = ab.score_response(answer)
    if "v_polite_response" in score.get("violations", []) or \
            not score.get("markers", {}).get("banmal"):
        raise BehaviorExportError(f"{record.get('id')}: 반말 게이트 실패: {answer!r}")


def assemble_messages(record: dict) -> list[dict[str, str]]:
    system_content = ab.build_system_content()
    briefing = (record.get("briefing") or "").strip()
    if briefing:
        system_content += "\n\n" + briefing
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": ab.USER_PREFIX + record["prompt"]},
        {"role": "assistant", "content": record["answer"]},
    ]


def export(reviewed_path: Path) -> tuple[list[dict], dict[str, object]]:
    records = [json.loads(line) for line in
               reviewed_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        raise BehaviorExportError("검수 데이터가 비어 있다")
    rows: list[dict] = []
    behaviors: dict[str, int] = {}
    for record in records:
        verify_record(record)
        behaviors[record["behavior"]] = behaviors.get(record["behavior"], 0) + 1
        rows.append({"id": record["id"], "split": record["split"],
                     "behavior": record["behavior"],
                     "messages": assemble_messages(record)})
    summary = {
        "records": len(rows),
        "behaviors": behaviors,
        "splits": {split: sum(1 for row in rows if row["split"] == split)
                   for split in ("train", "dev", "test")},
        "system_prompt_sha256": hashlib.sha256(
            ab.build_system_content().encode("utf-8")).hexdigest(),
    }
    return rows, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="reviewed behavior dataset → chat SFT export")
    parser.add_argument("--reviewed", type=Path, default=DEFAULT_REVIEWED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    rows, summary = export(args.reviewed)
    payload = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")) for row in rows) + "\n"
    args.output.write_text(payload, encoding="utf-8", newline="\n")
    summary["output"] = str(args.output)
    summary["sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
