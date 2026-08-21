"""Verify the reviewed extraction dataset and export it as chat-format SFT JSONL.

This is the last data-side step before the GPU: it re-checks every eligibility
condition (approved review, human reviewer, span-contract task) and assembles
the exact Stage A call the span run makes — system prompt from
``stage_a_prompt_for_contract``, user message from ``stage_a_user_input``, both
imported rather than restated so the training distribution cannot drift away
from the served one.

The assistant target keeps its ``evidence`` fields: quoting the span is not a
formatting detail but the contract itself, since ``parse_stage_a_span`` drops
any item whose quote the turns do not contain. Every target is re-verified here
against its own turns, so a record that lost its evidence between review and
export fails the export instead of teaching a fabrication.

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
DEFAULT_REVIEWED = HERE / "seed" / "airi_extraction_reviewed.jsonl"
DEFAULT_OUTPUT = HERE / "seed" / "airi_extraction_sft.jsonl"

sys.path.insert(0, str(HERE.parent))
from benchmark_memory_track import (  # noqa: E402
    ValidationError, parse_stage_a_span, stage_a_prompt_for_contract, stage_a_user_input)

STAGE_A_CONTRACT = "conversation-v3-span"
EXPECTED_TASK = "stage_a_span"
SPLITS = ("train", "dev", "test")


class ExtractionExportError(ValueError):
    """Fail closed on anything that is not a fully reviewed, span-verified record."""


def verify_record(record: dict) -> None:
    review = record.get("review") or {}
    record_id = record.get("id")
    if not isinstance(record_id, str) or not record_id.strip():
        raise ExtractionExportError("id 가 비어 있거나 문자열이 아니다")
    if record.get("split") not in SPLITS:
        raise ExtractionExportError(
            f"{record_id}: split 이 허용 도메인 {SPLITS} 밖이다 ({record.get('split')})")
    if record.get("training_eligible") is not True:
        raise ExtractionExportError(f"{record_id}: training_eligible 아님")
    if review.get("status") != "approved" or not str(review.get("reviewer", "")).strip():
        raise ExtractionExportError(f"{record.get('id')}: 승인·검수자 누락")
    if not str(review.get("approved_at", "")).strip():
        raise ExtractionExportError(f"{record.get('id')}: 검수 시점 누락")
    if record.get("task") != EXPECTED_TASK:
        raise ExtractionExportError(
            f"{record.get('id')}: task 가 {EXPECTED_TASK} 아님 ({record.get('task')})")
    try:
        parsed = json.loads(record["target"])
        survivors, dropped = parse_stage_a_span(parsed, record["turns"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ExtractionExportError(f"{record.get('id')}: target 을 읽을 수 없다: {exc}") from exc
    except ValidationError as exc:
        raise ExtractionExportError(f"{record.get('id')}: target 스팬 스키마 위반: {exc}") from exc
    if dropped or len(survivors["extracted"]) != len(parsed["extracted"]):
        raise ExtractionExportError(
            f"{record.get('id')}: 근거 인용 {dropped}건이 turns 원문과 맞지 않는다")


def assemble_messages(record: dict) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": stage_a_prompt_for_contract(STAGE_A_CONTRACT)},
        {"role": "user", "content": stage_a_user_input(record["character"], record["turns"])},
        {"role": "assistant", "content": record["target"]},
    ]


def export(reviewed_path: Path) -> tuple[list[dict], dict[str, object]]:
    records = [json.loads(line) for line in
               reviewed_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        raise ExtractionExportError("검수 데이터가 비어 있다")
    rows: list[dict] = []
    scenes: dict[str, int] = {}
    seen_ids: set[str] = set()
    for record in records:
        verify_record(record)
        record_id = record["id"]
        if record_id in seen_ids:
            raise ExtractionExportError(f"{record_id}: id 중복")
        seen_ids.add(record_id)
        scenes[record["scene"]] = scenes.get(record["scene"], 0) + 1
        rows.append({"id": record_id, "split": record["split"],
                     "scene": record["scene"],
                     "messages": assemble_messages(record)})
    summary = {
        "records": len(rows),
        "scenes": scenes,
        "splits": {split: sum(1 for row in rows if row["split"] == split) for split in SPLITS},
        "stage_a_contract": STAGE_A_CONTRACT,
        "system_prompt_sha256": hashlib.sha256(
            stage_a_prompt_for_contract(STAGE_A_CONTRACT).encode("utf-8")).hexdigest(),
    }
    return rows, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="reviewed extraction dataset → chat SFT export")
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
