"""Privacy-safe live memory smoke for the local AIRI proxy.

The report contains booleans and timings only.  It never prints the session
ID, nickname, full prompt, or model response.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import time
import urllib.request
import uuid


def stream_answer(endpoint: str, model: str, text: str, session_id: str) -> tuple[str, float, bool]:
    payload = {
        "model": model,
        "stream": True,
        "messages": [{"role": "user", "content": text}],
    }
    request = urllib.request.Request(
        endpoint,
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        {"Content-Type": "application/json", "x-airi-session-id": session_id},
    )
    started = time.perf_counter()
    parts: list[str] = []
    act_exposed = False
    with urllib.request.urlopen(request, timeout=120) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", "replace").strip()
            if not line.startswith("data: ") or line[6:] == "[DONE]":
                continue
            try:
                delta = json.loads(line[6:])["choices"][0]["delta"].get("content", "")
            except (KeyError, IndexError, TypeError, json.JSONDecodeError):
                continue
            if isinstance(delta, str):
                parts.append(delta)
                act_exposed = act_exposed or "<|ACT" in delta or "ACT {" in delta
    return "".join(parts), round((time.perf_counter() - started) * 1000, 1), act_exposed


def memory_counts(db_path: Path) -> dict[str, int]:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT role, COUNT(*) FROM conversation_message GROUP BY role"
        ).fetchall()
        counts = {str(role): int(count) for role, count in rows}
        counts["system"] = int(
            connection.execute(
                "SELECT COUNT(*) FROM conversation_message WHERE role='system'"
            ).fetchone()[0]
        )
        return counts
    finally:
        connection.close()


def run(endpoint: str, model: str, db_path: Path) -> dict[str, object]:
    nickname = "감자"
    remembered_prompt = "내 별명은 감자야. 기억해줘."
    recall_prompt = "나중에 내 별명이 뭐라고 했지?"
    session = f"memory-smoke-{uuid.uuid4().hex}"
    first, first_ms, first_act = stream_answer(endpoint, model, remembered_prompt, session)
    time.sleep(2.0)
    second, second_ms, second_act = stream_answer(endpoint, model, recall_prompt, session)
    fresh, fresh_ms, fresh_act = stream_answer(
        endpoint, model, recall_prompt, f"memory-smoke-fresh-{uuid.uuid4().hex}"
    )
    return {
        "same_session_recalled": nickname in second,
        "fresh_session_asked_without_invention": (
            "어떻게 부르면" in fresh or "기록이 없어" in fresh
        ),
        "act_exposed": first_act or second_act or fresh_act,
        "first_ms": first_ms,
        "recall_ms": second_ms,
        "fresh_ms": fresh_ms,
        "db_role_counts": memory_counts(db_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:11435/v1/chat/completions")
    parser.add_argument("--model", default="exaone-airi:2.4b")
    parser.add_argument("--db", default="../runtime/airi-memory.sqlite3")
    args = parser.parse_args()
    result = run(args.endpoint, args.model, Path(args.db).resolve())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if (
        result["same_session_recalled"]
        and result["fresh_session_asked_without_invention"]
        and result["db_role_counts"].get("system") == 0
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
