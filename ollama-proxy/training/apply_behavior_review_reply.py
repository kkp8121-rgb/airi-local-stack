"""Apply the operator's review reply to the behavior pending queue.

The click-form reply lists only exceptions — rejections and rewrites — so this
applier treats every remaining record as approved, but only once the reply
proves the review was complete: any "(미결정" marker rejects the whole reply,
because a truncated undecided list would make approval-by-omission ambiguous.

Rewritten answers pass the same register gate as synthesized ones; a polite
rewrite would smuggle in the exact defect the gates exist to catch. Output
records carry the reviewer attribution and become `training_eligible: true` —
this is the single point where eligibility flips, and it requires an explicit
human reviewer id on the command line.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_PENDING = HERE / "seed" / "airi_behavior_seed_pending.jsonl"
DEFAULT_OUTPUT = HERE / "seed" / "airi_behavior_reviewed.jsonl"

sys.path.insert(0, str(HERE.parent / "eval" / "broadcast_chat"))
import run_broadcast_chat_ab as ab  # noqa: E402

_REJECTED_RE = re.compile(r"^rejected=(.+)$", re.M)
_REWRITE_RE = re.compile(r"^rewrite:\s*(bseed-[a-z_]+-[0-9]{4})\s*=>\s*(.+)$", re.M)
_APPROVED_RE = re.compile(r"^approved=(\d+)/(\d+)$", re.M)


class ReviewReplyError(ValueError):
    """Fail closed on an ambiguous, incomplete, or gate-violating reply."""


def parse_reply(reply: str) -> dict[str, object]:
    if "[AIRI 행동 SFT 검수 회신" not in reply:
        raise ReviewReplyError("회신 헤더가 없다 — 폼의 [회신 만들기] 출력을 그대로 붙일 것")
    if "(미결정" in reply:
        raise ReviewReplyError("미결정 항목이 남아 있다 — 전건 결정 후 다시 회신할 것")
    approved_match = _APPROVED_RE.search(reply)
    if not approved_match:
        raise ReviewReplyError("approved=N/M 줄이 없다")
    rejected: list[str] = []
    rejected_match = _REJECTED_RE.search(reply)
    if rejected_match:
        rejected = [item.strip() for item in rejected_match.group(1).split(",") if item.strip()]
    rewrites = {match.group(1): match.group(2).strip() for match in _REWRITE_RE.finditer(reply)}
    return {"approved_count": int(approved_match.group(1)),
            "total": int(approved_match.group(2)),
            "rejected": rejected, "rewrites": rewrites}


def apply_reply(records: list[dict], reply: dict[str, object],
                reviewer: str, approved_at: str) -> tuple[list[dict], dict[str, int]]:
    known = {record["id"] for record in records}
    rejected = set(reply["rejected"])  # type: ignore[arg-type]
    rewrites: dict[str, str] = reply["rewrites"]  # type: ignore[assignment]
    unknown = (rejected | set(rewrites)) - known
    if unknown:
        raise ReviewReplyError(f"회신이 미지의 id를 참조한다: {sorted(unknown)[:5]}")
    if len(records) != reply["total"]:
        raise ReviewReplyError(
            f"회신 총계 {reply['total']} ≠ 큐 {len(records)} — 폼과 큐 버전이 어긋났다")
    expected_approved = len(records) - len(rejected) - len(rewrites)
    if reply["approved_count"] != expected_approved:
        raise ReviewReplyError(
            f"approved={reply['approved_count']} 이 예외 목록과 안 맞는다 (기대 {expected_approved})")

    reviewed: list[dict] = []
    counts = {"approved": 0, "rewritten": 0, "rejected": 0}
    for record in records:
        record_id = record["id"]
        if record_id in rejected:
            counts["rejected"] += 1
            continue
        entry = json.loads(json.dumps(record, ensure_ascii=False))
        if record_id in rewrites:
            answer = rewrites[record_id]
            if not answer:
                raise ReviewReplyError(f"{record_id} 수정 답변이 비어 있다")
            score = ab.score_response(answer)
            if "v_polite_response" in score.get("violations", []) or \
                    not score.get("markers", {}).get("banmal"):
                raise ReviewReplyError(f"{record_id} 수정 답변이 반말 게이트를 통과하지 못한다: {answer!r}")
            if len(answer) > 160:
                raise ReviewReplyError(f"{record_id} 수정 답변이 160자를 넘는다")
            entry["answer"] = answer
            entry["provenance"]["template"] += "+operator-rewrite"
            counts["rewritten"] += 1
        else:
            counts["approved"] += 1
        entry["review"] = {"status": "approved", "reviewer": reviewer, "approved_at": approved_at}
        entry["training_eligible"] = True
        reviewed.append(entry)
    return reviewed, counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="apply the operator review reply")
    parser.add_argument("--pending", type=Path, default=DEFAULT_PENDING)
    parser.add_argument("--reply", type=Path, required=True, help="폼 회신 텍스트 파일")
    parser.add_argument("--reviewer", required=True, help="검수자 식별자 (사람)")
    parser.add_argument("--approved-at", required=True, help="검수 시점, 예: 2026-08-19")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if not args.reviewer.strip():
        raise SystemExit("reviewer 는 비울 수 없다")

    records = [json.loads(line) for line in
               args.pending.read_text(encoding="utf-8").splitlines() if line.strip()]
    reply = parse_reply(args.reply.read_text(encoding="utf-8"))
    reviewed, counts = apply_reply(records, reply, args.reviewer.strip(), args.approved_at.strip())

    payload = "\n".join(json.dumps(entry, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")) for entry in reviewed) + "\n"
    args.output.write_text(payload, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    print(json.dumps({"output": str(args.output), "sha256": digest,
                      "records": len(reviewed), **counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
