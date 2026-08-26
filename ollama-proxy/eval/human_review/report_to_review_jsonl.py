"""방송 시뮬레이션 리포트를 사람 평가용 JSONL 로 바꾸는 오프라인 변환기.

`run_broadcast_sim.py --replay-chat` 이 낸 리포트의 트랜스크립트에서 turn 단계만
뽑아 `export_session_dialogue.py` 와 같은 행 모양으로 옮긴다. 그러면 실제 시청자
채팅에 대한 AIRI 응답도 `build_rating_sheet.py` 가 그대로 평가지로 만들 수 있다.

리포트에는 실제 채팅 원문이 들어 있으므로, 저장소 트리 안으로 쓰는 것은
내보내기 도구와 같은 규칙으로 거부한다(`--allow-repo-path` 로만 우회).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# 저장소 밖 쓰기 규칙은 한 곳에만 둔다 — 복제하면 한쪽만 느슨해진다.
from export_session_dialogue import is_inside_repo  # noqa: E402

HASH_PREFIX_CHARS = 16


def content_hash(text: str) -> str:
    """내보내기 JSONL 의 ``*_hash`` 자리를 채우는 짧은 내용 해시."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:HASH_PREFIX_CHARS]


def build_rows(report: dict[str, Any], session_id: str) -> list[dict[str, Any]]:
    """리포트 트랜스크립트의 turn 항목을 평가지 행으로 옮긴다.

    대본 오프닝/클로징과 사전 세션 시드는 시청자 발화가 아니므로 제외한다.
    """
    transcript = report.get("transcript")
    if not isinstance(transcript, list):
        raise ValueError("report has no transcript list")
    rows: list[dict[str, Any]] = []
    for entry in transcript:
        if not isinstance(entry, dict) or entry.get("stage") != "turn":
            continue
        missing = [key for key in ("turn_index", "chat", "airi") if key not in entry]
        if missing:
            raise ValueError(f"transcript turn is missing {missing}")
        user = str(entry["chat"])
        assistant = str(entry["airi"] or "")
        rows.append(
            {
                "session_id": session_id,
                "turn_no": int(entry["turn_index"]),
                "user": user,
                "assistant": assistant,
                "user_hash": content_hash(user),
                "assistant_hash": content_hash(assistant),
            }
        )
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="방송 시뮬레이션 리포트를 사람 평가용 JSONL 로 변환한다.",
    )
    parser.add_argument("--report", required=True, help="run_broadcast_sim.py 가 낸 리포트 JSON.")
    parser.add_argument("--output", required=True, help="출력 JSONL 경로.")
    parser.add_argument(
        "--allow-repo-path",
        action="store_true",
        help="저장소 트리 안으로 쓰는 것을 명시적으로 허용한다(권장하지 않음).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    report_path = Path(args.report)
    if not report_path.is_file():
        print(f"error: report not found: {report_path}", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    if is_inside_repo(output_path) and not args.allow_repo_path:
        print(
            "error: refusing to write real dialogue inside the repository tree; "
            "choose a path outside the repo or pass --allow-repo-path",
            file=sys.stderr,
        )
        return 1

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ValueError("report is not an object")
        rows = build_rows(report, report_path.stem)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: invalid report: {exc}", file=sys.stderr)
        return 1
    if not rows:
        print("error: report contains no scored turns", file=sys.stderr)
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"session={report_path.stem} turns={len(rows)} output={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
