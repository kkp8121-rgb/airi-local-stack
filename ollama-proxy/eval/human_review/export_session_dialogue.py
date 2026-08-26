"""실제 대화 세션을 사람 평가용 JSONL 로 내보내는 오프라인 도구.

프록시 메모리 DB(`conversation_message`)를 **읽기 전용**으로 열어 turn 단위
user/assistant 쌍만 추출한다. 실제 대화는 저장소에 남기지 않는 것이 원칙이라
기본적으로 리포지토리 트리 안으로는 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from typing import Sequence
from urllib.request import pathname2url

REPO_ROOT = Path(__file__).resolve().parents[3]
DIALOGUE_ROLES = ("user", "assistant")


def open_readonly(db_path: Path) -> sqlite3.Connection:
    """DB 를 read-only URI 로 연다. 평가 도구가 실제 대화를 변형하지 못하게 한다."""
    uri = "file:" + pathname2url(str(db_path)) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_sessions(conn: sqlite3.Connection) -> list[dict]:
    """세션 목록(대화 내용 없이 개수만)을 반환한다."""
    rows = conn.execute(
        "SELECT m.session_id AS session_id,"
        " COUNT(DISTINCT m.turn_no) AS turn_count,"
        " COALESCE(a.latest_turn, MAX(m.turn_no)) AS latest_turn"
        " FROM conversation_message AS m"
        " LEFT JOIN session_activity AS a ON a.session_id = m.session_id"
        " WHERE m.role IN ('user','assistant')"
        " GROUP BY m.session_id ORDER BY m.session_id"
    ).fetchall()
    return [
        {
            "session_id": row["session_id"],
            "turn_count": int(row["turn_count"]),
            "latest_turn": int(row["latest_turn"]),
        }
        for row in rows
    ]


def export_turns(
    conn: sqlite3.Connection,
    session_id: str,
    since_turn: int | None = None,
    limit_turns: int | None = None,
) -> tuple[list[dict], int]:
    """(완성된 turn 행, 건너뛴 불완전 turn 수)를 반환한다."""
    sql = (
        "SELECT turn_no, role, content, content_hash FROM conversation_message"
        " WHERE session_id = ? AND role IN ('user','assistant')"
    )
    params: list[object] = [session_id]
    if since_turn is not None:
        sql += " AND turn_no >= ?"
        params.append(since_turn)
    sql += " ORDER BY turn_no ASC, role ASC, id ASC"

    pairs: dict[int, dict[str, sqlite3.Row]] = {}
    for row in conn.execute(sql, params):
        pairs.setdefault(int(row["turn_no"]), {})[str(row["role"])] = row

    rows: list[dict] = []
    skipped = 0
    for turn_no in sorted(pairs):
        sides = pairs[turn_no]
        if "user" not in sides or "assistant" not in sides:
            skipped += 1
            continue
        if limit_turns is not None and len(rows) >= limit_turns:
            break
        rows.append(
            {
                "session_id": session_id,
                "turn_no": turn_no,
                "user": sides["user"]["content"],
                "assistant": sides["assistant"]["content"],
                "user_hash": sides["user"]["content_hash"],
                "assistant_hash": sides["assistant"]["content_hash"],
            }
        )
    return rows, skipped


def is_inside_repo(path: Path) -> bool:
    """출력 경로가 저장소 트리 안인지 판정한다(존재하지 않는 경로도 허용)."""
    resolved = Path(path).resolve()
    return resolved == REPO_ROOT or REPO_ROOT in resolved.parents


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="프록시 메모리 DB에서 실제 대화 turn 을 JSONL 로 내보낸다.",
    )
    parser.add_argument("--db", required=True, help="메모리 SQLite 경로(읽기 전용으로 연다).")
    parser.add_argument("--session", default=None, help="내보낼 session_id.")
    parser.add_argument("--all-sessions", action="store_true", help="모든 세션을 내보낸다.")
    parser.add_argument("--since-turn", type=int, default=None, help="이 turn_no 이상만 내보낸다.")
    parser.add_argument("--limit-turns", type=int, default=None, help="세션당 최대 turn 수.")
    parser.add_argument("--output", default=None, help="출력 JSONL 경로.")
    parser.add_argument("--list", action="store_true", help="세션 목록만 출력한다.")
    parser.add_argument(
        "--allow-repo-path",
        action="store_true",
        help="저장소 트리 안으로 쓰는 것을 명시적으로 허용한다(권장하지 않음).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"error: memory DB not found: {db_path}", file=sys.stderr)
        return 1

    if args.list:
        with closing(open_readonly(db_path)) as conn:
            sessions = list_sessions(conn)
        for session in sessions:
            print(
                f"{session['session_id']}\tturns={session['turn_count']}"
                f"\tlatest_turn={session['latest_turn']}"
            )
        print(f"sessions={len(sessions)}")
        return 0

    if not args.output:
        print("error: --output is required unless --list is given", file=sys.stderr)
        return 1
    if bool(args.session) == bool(args.all_sessions):
        print("error: give exactly one of --session or --all-sessions", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    if is_inside_repo(output_path) and not args.allow_repo_path:
        print(
            "error: refusing to write real dialogue inside the repository tree; "
            "choose a path outside the repo or pass --allow-repo-path",
            file=sys.stderr,
        )
        return 1

    with closing(open_readonly(db_path)) as conn:
        if args.all_sessions:
            session_ids = [session["session_id"] for session in list_sessions(conn)]
        else:
            session_ids = [str(args.session)]
        exported: list[dict] = []
        skipped_total = 0
        for session_id in session_ids:
            rows, skipped = export_turns(conn, session_id, args.since_turn, args.limit_turns)
            exported.extend(rows)
            skipped_total += skipped

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in exported:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(
        f"sessions={len(session_ids)} turns={len(exported)} "
        f"skipped_incomplete={skipped_total} output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
