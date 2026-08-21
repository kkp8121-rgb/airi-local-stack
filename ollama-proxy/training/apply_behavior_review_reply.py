"""Apply an operator's complete, queue-bound behavior review reply.

The click form lists only rejections and rewrites. Every other item is approved
only after the reply proves it came from the exact current pending queue.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from behavior_answer_gate import BehaviorAnswerGateError, validate_behavior_answer

DEFAULT_PENDING = HERE / "seed" / "airi_behavior_seed_pending.jsonl"
DEFAULT_OUTPUT = HERE / "seed" / "airi_behavior_reviewed.jsonl"
_HEADER_RE = re.compile(r"^\[AIRI 행동 SFT 검수 회신 .+? queue=([0-9a-f]{12})\]$", re.M)
_REJECTED_RE = re.compile(r"^rejected=(.+)$", re.M)
_REWRITE_RE = re.compile(r"^rewrite:\s*(bseed-[a-z_]+-[0-9]{4})\s*=>\s*(.*)$", re.M)
_APPROVED_RE = re.compile(r"^approved=(\d+)/(\d+)$", re.M)


class ReviewReplyError(ValueError):
    """Fail closed on an ambiguous, incomplete, stale, or invalid reply."""


def queue_digest(pending_path: Path) -> str:
    """Return 12 SHA-256 hex characters for LF-normalized UTF-8 queue text."""
    text = pending_path.read_text(encoding="utf-8")
    canonical = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:12]


def parse_reply(reply: str) -> dict[str, object]:
    header = _HEADER_RE.search(reply)
    if not header:
        raise ReviewReplyError("최신 검수 폼에서 회신을 다시 만들어 붙여 넣어 주세요.")
    if "(미결정" in reply:
        raise ReviewReplyError("미결정 항목이 남아 있다 — 전건 결정 후 다시 회신할 것")
    approved_match = _APPROVED_RE.search(reply)
    if not approved_match:
        raise ReviewReplyError("approved=N/M 줄이 없다")
    rejected_match = _REJECTED_RE.search(reply)
    rejected = [] if not rejected_match else [item.strip() for item in rejected_match.group(1).split(",") if item.strip()]
    rewrites: dict[str, str] = {}
    for match in _REWRITE_RE.finditer(reply):
        record_id, answer = match.group(1), match.group(2).strip()
        if record_id in rewrites:
            raise ReviewReplyError("수정 항목 ID가 중복되었다")
        rewrites[record_id] = answer
    if len(rejected) != len(set(rejected)):
        raise ReviewReplyError("거부 항목 ID가 중복되었다")
    if set(rejected) & set(rewrites):
        raise ReviewReplyError("같은 ID를 거부와 수정에 함께 쓸 수 없다")
    return {"queue_sha": header.group(1), "approved_count": int(approved_match.group(1)),
            "total": int(approved_match.group(2)), "rejected": rejected, "rewrites": rewrites}


def apply_reply(records: list[dict], reply: dict[str, object], reviewer: str,
                approved_at: str, queue_sha: str) -> tuple[list[dict], dict[str, int]]:
    if not reviewer.strip() or not approved_at.strip():
        raise ReviewReplyError("reviewer와 approved_at은 비워 둘 수 없다")
    if not queue_sha or reply.get("queue_sha") != queue_sha:
        raise ReviewReplyError("최신 검수 폼에서 회신을 다시 만들어 붙여 넣어 주세요.")
    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)):
        raise ReviewReplyError("대기열에 중복 ID가 있어 적용할 수 없다")
    known = set(ids)
    rejected = set(reply["rejected"])  # type: ignore[arg-type]
    rewrites: dict[str, str] = reply["rewrites"]  # type: ignore[assignment]
    unknown = (rejected | set(rewrites)) - known
    if unknown:
        raise ReviewReplyError(f"회신이 미지의 id를 참조한다: {sorted(unknown)[:5]}")
    if len(records) != reply["total"]:
        raise ReviewReplyError("최신 검수 폼에서 회신을 다시 만들어 붙여 넣어 주세요.")
    expected = len(records) - len(rejected) - len(rewrites)
    if reply["approved_count"] != expected:
        raise ReviewReplyError(f"approved 수가 예외 목록과 안 맞는다 (기대 {expected})")

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
            try:
                validate_behavior_answer(record, answer, minimum=1, maximum=160)
            except BehaviorAnswerGateError as exc:
                raise ReviewReplyError(f"{record_id} 수정 답변이 게이트를 통과하지 못한다: {exc}") from exc
            entry["answer"] = answer
            entry["provenance"]["template"] += "+operator-rewrite"
            counts["rewritten"] += 1
        else:
            counts["approved"] += 1
        entry["review"] = {"status": "approved", "reviewer": reviewer.strip(), "approved_at": approved_at.strip()}
        entry["training_eligible"] = True
        reviewed.append(entry)
    return reviewed, counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="apply the operator review reply")
    parser.add_argument("--pending", type=Path, default=DEFAULT_PENDING)
    parser.add_argument("--reply", type=Path, required=True, help="폼 회신 텍스트 파일")
    parser.add_argument("--reviewer", required=True, help="검수자 식별자")
    parser.add_argument("--approved-at", required=True, help="검수 시점")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    records = [json.loads(line) for line in args.pending.read_text(encoding="utf-8").splitlines() if line.strip()]
    reply = parse_reply(args.reply.read_text(encoding="utf-8"))
    reviewed, counts = apply_reply(records, reply, args.reviewer, args.approved_at, queue_digest(args.pending))
    payload = "\n".join(json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for entry in reviewed) + "\n"
    args.output.write_text(payload, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    print(json.dumps({"output": str(args.output), "sha256": digest, "records": len(reviewed), **counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
