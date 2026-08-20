"""Apply the operator's review reply to the extraction pending queue.

The click-form reply lists only exceptions — rejections and rewrites — so this
applier treats every remaining record as approved, but only once the reply
proves the review was complete: any "(미결정" marker rejects the whole reply,
because a truncated undecided list would make approval-by-omission ambiguous.

Rewritten targets pass the same span verification the synthesizer applied:
``parse_stage_a_span`` must return every item with zero drops against that
record's own turns. A quote the turns do not contain, or a name outside its own
evidence, is exactly the fabrication the span contract exists to make
impossible — accepting it by hand would train the model to produce it. One
failing rewrite rejects the whole reply rather than silently dropping a record.

Output records carry the reviewer attribution and become
``training_eligible: true`` — this is the single point where eligibility flips,
and it requires an explicit human reviewer id on the command line.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_PENDING = HERE / "seed" / "airi_extraction_seed_pending.jsonl"
DEFAULT_OUTPUT = HERE / "seed" / "airi_extraction_reviewed.jsonl"

sys.path.insert(0, str(HERE.parent))
from benchmark_memory_track import ValidationError, parse_stage_a_span  # noqa: E402

REPLY_HEADER = "[AIRI 추출 SFT 검수 회신"

_REJECTED_RE = re.compile(r"^rejected=(.+)$", re.M)
_REWRITE_RE = re.compile(r"^rewrite:\s*(xseed-[a-z_]+-[0-9]{4})\s*=>\s*(.+)$", re.M)
_APPROVED_RE = re.compile(r"^approved=(\d+)/(\d+)$", re.M)
# 헤더 형식 확장: `... 회신 <날짜> queue=<sha256 앞 12자>]` — 큐 결속(Minor 9) 파싱용.
_QUEUE_RE = re.compile(r"queue=([0-9a-f]{12})\]")


class ReviewReplyError(ValueError):
    """Fail closed on an ambiguous, incomplete, or gate-violating reply."""


def queue_digest(pending_path: Path) -> str:
    """Pending 큐 파일 내용의 sha256 단축(12자).

    회신이 어느 큐 스냅샷을 검수했는지 결속하는 값이다 — 큐가 재생성되면
    (레코드 수·id 가 우연히 같더라도) 이 값이 달라져 구 회신이 새 큐에
    적용되는 사고를 apply_reply 가 잡아낼 수 있다 (Task 2 리뷰 Minor 9).
    """
    return hashlib.sha256(pending_path.read_bytes()).hexdigest()[:12]


def parse_reply(reply: str) -> dict[str, object]:
    if REPLY_HEADER not in reply:
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
    queue_match = _QUEUE_RE.search(reply)
    return {"approved_count": int(approved_match.group(1)),
            "total": int(approved_match.group(2)),
            "rejected": rejected, "rewrites": rewrites,
            "queue_sha": queue_match.group(1) if queue_match else None}


def verify_rewritten_target(record_id: str, target: str, turns: str) -> str:
    """Re-run the synthesizer's own gate on a hand-written target.

    Returns the canonical serialization so a reviewed record is byte-identical
    to a synthesized one carrying the same items.
    """
    if not target:
        raise ReviewReplyError(f"{record_id} 수정 target 이 비어 있다")
    try:
        parsed = json.loads(target)
    except json.JSONDecodeError as exc:
        raise ReviewReplyError(f"{record_id} 수정 target 이 JSON 이 아니다: {exc}") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("extracted"), list):
        raise ReviewReplyError(f'{record_id} 수정 target 은 {{"extracted":[...]}} 형태여야 한다')
    try:
        survivors, dropped = parse_stage_a_span(
            json.loads(json.dumps(parsed, ensure_ascii=False)), turns)
    except ValidationError as exc:
        raise ReviewReplyError(f"{record_id} 수정 target 이 스팬 스키마를 위반한다: {exc}") from exc
    if dropped or len(survivors["extracted"]) != len(parsed["extracted"]):
        raise ReviewReplyError(
            f"{record_id} 수정 target 의 근거 인용 {dropped}건이 turns 원문과 맞지 않는다 "
            "— evidence 는 원문의 정확한 부분 문자열이어야 하고 모든 이름이 그 안에 있어야 한다")
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


_STALE_FORM_HINT = ("폼이 갱신되었습니다 — 최신 폼"
                    "(AIRI-EXTRACTION-REVIEW-FORM-2026-08-20.html)으로 다시 검수해 주세요")


def apply_reply(records: list[dict], reply: dict[str, object],
                reviewer: str, approved_at: str,
                queue_sha: str) -> tuple[list[dict], dict[str, int]]:
    """``queue_sha``(현재 큐의 sha256 단축 12자, ``queue_digest()`` 로 계산)로 회신을
    그 큐 스냅샷에 결속한다(Task 2 리뷰 Minor 9).

    이 인자는 필수다 — 레포의 fail-closed 원칙상 큐 결속을 조용히 건너뛸 수 있는
    우회 경로(선택적 인자·기본값)를 두지 않는다. 회신에 queue= 세그먼트가 없거나
    (구 형식 회신) 값이 현재 큐와 다르면(큐가 재생성됨) 무조건 거부한다.
    """
    reply_queue_sha = reply.get("queue_sha")
    if reply_queue_sha is None:
        raise ReviewReplyError(f"회신 헤더에 큐 sha가 없다 — {_STALE_FORM_HINT}")
    if reply_queue_sha != queue_sha:
        raise ReviewReplyError(
            f"회신의 큐 sha({reply_queue_sha})가 현재 큐({queue_sha})와 다르다 "
            f"— 큐가 재생성됐다, {_STALE_FORM_HINT}")
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
            entry["target"] = verify_rewritten_target(
                record_id, rewrites[record_id], record["turns"])
            entry["provenance"]["template"] += "+operator-rewrite"
            counts["rewritten"] += 1
        else:
            counts["approved"] += 1
        entry["review"] = {"status": "approved", "reviewer": reviewer, "approved_at": approved_at}
        entry["training_eligible"] = True
        reviewed.append(entry)
    return reviewed, counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="apply the operator extraction review reply")
    parser.add_argument("--pending", type=Path, default=DEFAULT_PENDING)
    parser.add_argument("--reply", type=Path, required=True, help="폼 회신 텍스트 파일")
    parser.add_argument("--reviewer", required=True, help="검수자 식별자 (사람)")
    parser.add_argument("--approved-at", required=True, help="검수 시점, 예: 2026-08-20")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if not args.reviewer.strip():
        raise SystemExit("reviewer 는 비울 수 없다")

    records = [json.loads(line) for line in
               args.pending.read_text(encoding="utf-8").splitlines() if line.strip()]
    reply = parse_reply(args.reply.read_text(encoding="utf-8"))
    reviewed, counts = apply_reply(records, reply, args.reviewer.strip(), args.approved_at.strip(),
                                    queue_digest(args.pending))

    payload = "\n".join(json.dumps(entry, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")) for entry in reviewed) + "\n"
    args.output.write_text(payload, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    print(json.dumps({"output": str(args.output), "sha256": digest,
                      "records": len(reviewed), **counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
