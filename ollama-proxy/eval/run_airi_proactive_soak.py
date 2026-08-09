from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx


RUNNER_VERSION = "0.3.0"
META_RE = re.compile(
    r"(?:^|\n)\s*[\"'“‘]?\s*(?:너|사용자|아이리|AIRI|assistant|user)\s*:"
    r"|(?:질문|대화\s*예시|답변\s*예시|시나리오|상황\s*설정|user input|stage execution|system prompt)"
    r"|(?:내부\s*자동방송\s*작업|자동방송\s*대사\s*계약|위\s*승인\s*토픽)",
    re.IGNORECASE,
)
CONTROL_RE = re.compile(r"<\|(?:ACT|CALL|DELAY)\b|\b(?:ACT|CALL|DELAY)\s*\{", re.IGNORECASE)
HANGUL_RE = re.compile(r"[가-힣]")
COMPLETE_RE = re.compile(r"[.!?。！？][\"'”’」』）)]*$")


def _health(client: httpx.Client, base: str) -> dict[str, object]:
    response = client.get(f"{base}/health")
    response.raise_for_status()
    data = response.json()
    return {
        "topic": data.get("topic_board", {}),
        "knowledge": data.get("knowledge", {}),
        "memory_data_version": (data.get("memory") or {}).get("data_version"),
        "session_header": data.get("session_header", {}),
    }


def _reply(client: httpx.Client, endpoint: str, model: str) -> tuple[str, float]:
    started = time.perf_counter()
    chunks: list[str] = []
    opaque = uuid4().hex
    headers = {
        "x-airi-turn-origin": "local-proactive",
        "x-airi-session-id": f"proactive-soak-{opaque}",
        "x-airi-round-id": f"proactive-soak-{opaque}",
    }
    payload = {"model": model, "stream": True, "temperature": 0.2, "messages": []}
    with client.stream("POST", endpoint, headers=headers, json=payload) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            raw = line[6:]
            if raw == "[DONE]":
                break
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            for choice in item.get("choices", []):
                content = (choice.get("delta") or {}).get("content")
                if isinstance(content, str):
                    chunks.append(content)
    return "".join(chunks).strip(), (time.perf_counter() - started) * 1000


def _score(output: str) -> dict[str, bool]:
    return {
        "non_empty": bool(output),
        "korean_first": bool(HANGUL_RE.search(output)),
        "minimum_12_chars": len(output) >= 12,
        "preferred_60_chars": len(output) <= 60,
        "no_question": "?" not in output,
        "complete_sentence": bool(COMPLETE_RE.search(output)),
        "no_meta": META_RE.search(output) is None,
        "no_control": CONTROL_RE.search(output) is None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:11435/v1/chat/completions")
    parser.add_argument("--model", default="exaone-airi:2.4b")
    parser.add_argument("--runs", type=int, default=6)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.runs <= 20:
        parser.error("runs must be between 1 and 20")
    endpoint = httpx.URL(args.endpoint)
    if endpoint.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("endpoint must be loopback")
    base = f"{endpoint.scheme}://{endpoint.host}:{endpoint.port}"
    rows: list[dict[str, object]] = []
    with httpx.Client(timeout=45.0) as client:
        before = _health(client, base)
        for index in range(args.runs):
            output, latency_ms = _reply(client, args.endpoint, args.model)
            checks = _score(output)
            row = {
                "index": index + 1,
                "output": output,
                "latency_ms": round(latency_ms, 1),
                "passed": all(checks.values()),
                "checks": checks,
                "human_review": "PENDING",
            }
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        after = _health(client, base)
    report = {
        "runner_version": RUNNER_VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "synthetic_only": True,
        "runs": args.runs,
        "auto_passed": sum(bool(row["passed"]) for row in rows),
        "quality_gate": "PENDING_HUMAN_REVIEW",
        "health_before": before,
        "health_after": after,
        "cases": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
