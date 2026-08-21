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

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "eval" / "broadcast_chat"))
import run_broadcast_chat_ab as ab  # noqa: E402

from affect_expression import render_affect_expression_contract  # noqa: E402
from affect_state import (  # noqa: E402
    initial_state,
    reduce_affect,
    render_continuity_snapshot,
    validate_state,
)
from behavior_answer_gate import (  # noqa: E402
    BehaviorAnswerGateError, validate_behavior_answer,
)


class BehaviorExportError(ValueError):
    """Fail closed on anything that is not a fully reviewed, gated record."""


def verify_record(record: dict) -> None:
    record_id = record.get("id")
    if not isinstance(record_id, str) or not record_id.strip():
        raise BehaviorExportError("record id 누락")
    if record.get("split") not in {"train", "dev", "test"}:
        raise BehaviorExportError(f"{record_id}: split 계약 위반")
    if not isinstance(record.get("behavior"), str) or not record["behavior"]:
        raise BehaviorExportError(f"{record_id}: behavior 누락")
    review = record.get("review") or {}
    if record.get("training_eligible") is not True:
        raise BehaviorExportError(f"{record.get('id')}: training_eligible 아님")
    if review.get("status") != "approved" or not str(review.get("reviewer", "")).strip():
        raise BehaviorExportError(f"{record.get('id')}: 승인·검수자 누락")
    if not str(review.get("approved_at", "")).strip():
        raise BehaviorExportError(f"{record.get('id')}: 검수 시점 누락")
    answer = record.get("answer") or ""
    try:
        validate_behavior_answer(record, answer)
    except BehaviorAnswerGateError as error:
        raise BehaviorExportError(f"{record_id}: 답변 게이트 실패: {error}") from error
    affect_state = record.get("affect_state")
    affect_prompt = record.get("affect_prompt")
    if (affect_state is None) != (affect_prompt is None):
        raise BehaviorExportError(f"{record_id}: affect state/prompt 짝이 불완전하다")
    if affect_state is not None:
        try:
            clean = validate_state(affect_state)
            replayed = initial_state()
            events = record.get("affect_events")
            if not isinstance(events, list):
                raise ValueError("affect events are missing")
            for event in events:
                replayed = reduce_affect(replayed, event)
            expected = (
                render_continuity_snapshot(clean) + "\n\n"
                + render_affect_expression_contract(clean)
            )
        except Exception as error:
            raise BehaviorExportError(f"{record_id}: affect state 계약 위반") from error
        if replayed != clean:
            raise BehaviorExportError(f"{record_id}: affect events/state 재생 결과가 어긋난다")
        if record["behavior"] != f"affect_{clean['primary']}":
            raise BehaviorExportError(f"{record_id}: behavior와 affect primary가 어긋난다")
        if (record.get("briefing") or "").strip():
            raise BehaviorExportError(f"{record_id}: affect 레코드는 briefing을 함께 쓰지 않는다")
        if affect_prompt != expected:
            raise BehaviorExportError(f"{record_id}: affect prompt가 현행 선택기와 어긋난다")


def assemble_messages(record: dict) -> list[dict[str, str]]:
    system_content = ab.build_system_content()
    briefing = (record.get("briefing") or "").strip()
    if briefing:
        system_content += "\n\n" + briefing
    messages = [{"role": "system", "content": system_content}]
    affect_prompt = record.get("affect_prompt")
    if affect_prompt:
        messages.append({
            "role": "system", "name": "airi_request_local",
            "content": affect_prompt,
        })
    messages.extend((
        {"role": "user", "content": ab.USER_PREFIX + record["prompt"]},
        {"role": "assistant", "content": record["answer"]},
    ))
    return messages


def export(reviewed_path: Path) -> tuple[list[dict], dict[str, object]]:
    records = [json.loads(line) for line in
               reviewed_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        raise BehaviorExportError("검수 데이터가 비어 있다")
    rows: list[dict] = []
    behaviors: dict[str, int] = {}
    seen_ids: set[str] = set()
    for record in records:
        verify_record(record)
        if record["id"] in seen_ids:
            raise BehaviorExportError(f"duplicate record id: {record['id']}")
        seen_ids.add(record["id"])
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


def export_many(reviewed_paths: list[Path]) -> tuple[list[dict], dict[str, object]]:
    if not reviewed_paths:
        raise BehaviorExportError("검수 데이터 경로가 비어 있다")
    combined: list[dict] = []
    seen_ids: set[str] = set()
    behaviors: dict[str, int] = {}
    for path in reviewed_paths:
        rows, _summary = export(path)
        for row in rows:
            if row["id"] in seen_ids:
                raise BehaviorExportError(f"duplicate record id across datasets: {row['id']}")
            seen_ids.add(row["id"])
            combined.append(row)
            behavior = row["behavior"]
            behaviors[behavior] = behaviors.get(behavior, 0) + 1
    return combined, {
        "records": len(combined),
        "behaviors": behaviors,
        "splits": {
            split: sum(1 for row in combined if row["split"] == split)
            for split in ("train", "dev", "test")
        },
        "system_prompt_sha256": hashlib.sha256(
            ab.build_system_content().encode("utf-8")
        ).hexdigest(),
        "reviewed_sources": [str(path) for path in reviewed_paths],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="reviewed behavior dataset → chat SFT export")
    parser.add_argument("--reviewed", type=Path, action="append")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    reviewed_paths = args.reviewed or [DEFAULT_REVIEWED]
    rows, summary = export_many(reviewed_paths)
    payload = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")) for row in rows) + "\n"
    args.output.write_text(payload, encoding="utf-8", newline="\n")
    summary["output"] = str(args.output)
    summary["sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
