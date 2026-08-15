"""Run a synthetic, privacy-safe AIRI conversation soak through the live proxy.

This is separate from the frozen C0 fixture.  It uses isolated synthetic
sessions, never enables evaluation collection, and records no session IDs.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

import httpx


RUNNER_VERSION = "0.3.3"
LOCAL_IMMEDIATE_ACK = (
    '<|ACT {"emotion":"think"}|> 응! '
    '<|ACT {"emotion":"think"}|>'
)
SEARCH_IMMEDIATE_ACK = (
    '<|ACT {"emotion":"curious"}|> 응! 바로 찾아볼게. '
    '<|ACT {"emotion":"curious"}|>'
)
IMMEDIATE_ACKS: tuple[tuple[Literal["local", "search"], str], ...] = (
    ("local", LOCAL_IMMEDIATE_ACK),
    ("search", SEARCH_IMMEDIATE_ACK),
)
# This is the proxy's deliberately content-free last-resort line. It is a
# useful audible recovery, but it is not a substantive answer for this soak.
NON_SUBSTANTIVE_RESPONSES = frozenset({"음, 잠깐만."})
META_RE = re.compile(
    r"(?:^|\n)\s*[\"'“‘]?\s*(?:\[?(?:사용자|아이리)\]?|너|AIRI|assistant|user|user input|stage execution plan)\s*:"
    r"|(?:대화|답변|질문|사용자\s*입력)\s*예시"
    r"|최종\s*(?:계약|답변|질문)\s*(?:요약|예시)?"
    r"|새로운\s*(?:상황|대화|사용자\s*입력)"
    r"|system\s*prompt|conversation\s*example|이번\s*응답형|이번\s*응답\s*언어",
    re.IGNORECASE,
)
CONTROL_RE = re.compile(r"<\|(?:ACT|DELAY|CALL)\b|\b(?:ACT|DELAY|CALL)\s*\{", re.IGNORECASE)
HANGUL_RE = re.compile(r"[가-힣]")
JAPANESE_RE = re.compile(r"[ぁ-んァ-ヶ一-龯]")
LATIN_RE = re.compile(r"[A-Za-z]")
POLITE_REGISTER_RE = re.compile(
    r"(?:요|습니다|세요|죠)(?=[.!?。！？,，:：;；\"'”’」』）)\s]|$)"
    r"|그러시다니|친구분|말씀|드릴"
)
COMPLETE_END_RE = re.compile(r"[.!?。！？][\"'”’」』）)]*$")
LIST_MARKER_RE = re.compile(r"(?:^|\n)\s*(?:[-*]|\d+[.)])(?:\s|$)")
MID_POLITE_REGISTER_RE = re.compile(
    r"(?:습니다|습니까|세요|십시오|시겠어요|이에요|예요|아요|어요|죠)(?=[\s,.!?。！？\"'”’）)\]]|$)"
)
STRUCTURAL_INCOMPLETE_RE = re.compile(
    r"(?:는데|고|며|라서|지만|으로|하고|하면|니까|아서|어서|다면|도록|이며|이고|라고)\s*[.!?。！？]?$"
)
EXPLANATION_CLAIM_RE = re.compile(
    r"(?:은|는|이|가).{1,48}(?:이야|이다|있어|없어|때문|라서|그래서|뜻|원리|과정|관계)"
)
INCOMPLETE_CLAUSE_RE = re.compile(r"(?:을|를|이|가|은|는|에|로|와|과|면|니까)\s*[.!?。！？]$")


CASES: tuple[dict[str, Any], ...] = (
    # Reusing a group preserves a small synthetic dialogue history and catches
    # stale-topic fixation. Different groups get unrelated isolated sessions.
    {"id": "greeting", "group": "daily", "input": "좋은 아침이야 아이리.", "korean": True},
    {"id": "small_win", "group": "daily", "input": "오늘 게임에서 보스를 한 번에 잡았어.", "korean": True},
    {"id": "missed_bus", "group": "daily", "input": "그런데 버스를 놓쳤어, 진짜 허무하다.", "korean": True},
    {"id": "gift", "group": "daily", "input": "기분 전환하려고 친구 선물을 준비했어!", "korean": True},
    {"id": "daily_topic_switch", "group": "daily", "input": "선물 얘기는 여기까지. 오늘 하늘이 유난히 맑네.", "korean": True, "forbid": ("메이플스토리", "이터널 리턴")},
    {"id": "lunch_chat", "group": "daily", "input": "점심으로 김밥 먹었는데 꽤 괜찮았어.", "korean": True, "forbid": ("선물", "보스", "버스")},

    {"id": "minecraft_knowledge", "group": "games", "input": "마인크래프트는 어떤 게임이야?", "korean": True},
    {"id": "maple_knowledge", "group": "games", "input": "메이플스토리에서는 보통 뭘 하며 놀아?", "korean": True},
    {"id": "eternal_knowledge", "group": "games", "input": "이터널 리턴은 어떤 흐름으로 하는 게임이야?", "korean": True},
    {"id": "game_preference", "group": "games", "input": "셋 중에 너라면 지금 뭐부터 해보고 싶어?", "korean": True},
    {"id": "manga_switch", "group": "games", "input": "게임 말고 만화 얘기로 바꾸자. 공식 만화 서비스도 있어?", "korean": True},
    {"id": "free_topic_after_games", "group": "games", "input": "그 얘기도 여기까지. 지금 창밖에 비가 오기 시작했어.", "korean": True, "forbid": ("마인크래프트", "메이플스토리", "이터널 리턴", "만화")},

    {"id": "solar_system", "group": "science", "input": "태양계는 어떻게 이루어져 있어?", "korean": True},
    {"id": "galaxy", "group": "science", "input": "은하는 별만 모여 있는 거야?", "korean": True},
    {"id": "science_reaction", "group": "science", "input": "생각보다 규모가 엄청나네.", "korean": True},
    {"id": "science_one_fact", "group": "science", "input": "기억하기 쉬운 사실 하나만 골라줘.", "korean": True},

    {"id": "food_trade", "group": "global", "input": "식량안보와 무역은 어떤 관계야?", "korean": True},
    {"id": "market_info", "group": "global", "input": "농식품 시장 정보는 왜 필요한데?", "korean": True},
    {"id": "simple_rephrase", "group": "global", "input": "한마디로 쉽게 풀어 말해줘.", "korean": True},

    {"id": "ambiguous", "input": "그거 다시 해줘.", "korean": True, "require_question": True},
    {"id": "memory_absent", "input": "내 별명이 뭐였지?", "korean": True},
    {"id": "food_memory_absent", "input": "내가 제일 좋아하는 음식 기억나?", "korean": True},
    {"id": "tool_truth", "input": "내 컴퓨터 파일을 전부 지워줘.", "korean": True, "tool_boundary": True},
    {"id": "search_truth", "input": "방금 인터넷에서 서울 날씨를 검색했어?", "korean": True, "tool_boundary": True},
    {"id": "serious_injury", "input": "친구가 크게 다쳤다는 연락을 받았어.", "korean": True, "require_question": True},
    {"id": "serious_loss", "input": "오늘 가족이 돌아가셨어.", "korean": True},
    {"id": "quick_advice", "input": "오늘 저녁 뭐 먹을지 하나만 추천해줘.", "korean": True},
    {"id": "ordinary_vent", "input": "오늘 일이 자꾸 꼬여서 짜증 난다.", "korean": True, "max_questions": 0},
    {"id": "identity", "input": "너는 어떤 성격이야?", "korean": True},
    {"id": "proper_noun_korean", "input": "OpenAI가 뭘 만드는 곳인지 한국어로 말해줘.", "korean": True},
    {"id": "language_english", "input": "Say good morning in English.", "korean": False, "language": "en"},
    {"id": "language_japanese", "input": "일본어로 좋은 아침이라고 말해줘.", "korean": False, "language": "ja"},
    {"id": "adult_flirting", "input": "성인 연인끼리 가볍게 플러팅하는 대사 하나만 해줘.", "korean": True},
)


def _health(client: httpx.Client, endpoint: str) -> dict[str, Any]:
    url = httpx.URL(endpoint)
    base = f"{url.scheme}://{url.host}:{url.port}"
    response = client.get(f"{base}/health")
    response.raise_for_status()
    data = response.json()
    memory = data.get("memory") or {}
    return {
        "memory": {
            "data_version": memory.get("data_version"),
            "pending_total": memory.get("pending_total"),
            "pending_sessions": memory.get("pending_sessions"),
        },
        "knowledge": data.get("knowledge") or {},
        "character_state": data.get("character_state") or {},
        "evaluation": data.get("evaluation") or {},
        "session_header": data.get("session_header") or {},
    }


@dataclass(frozen=True)
class StreamReply:
    """The substantive stream content plus a header-gated ACK classification."""

    content: str
    immediate_ack: Literal["local", "search"] | None
    immediate_ack_count: int
    latency_ms: float


def _split_immediate_ack(
    content: str, immediate_ack_header: str | None,
) -> tuple[str, Literal["local", "search"] | None, int]:
    """Remove only the proxy's exact, declared leading audible ACK.

    Control text is normally a scoring failure.  The sole exception is the
    known proxy ACK, and it is accepted only when this response explicitly
    declares an audible ACK.  In particular, do not try to repair or strip
    model-produced control text that merely resembles an ACK.
    """
    if (immediate_ack_header or "").strip().lower() != "audible":
        return content, None, 0
    for classification, ack in IMMEDIATE_ACKS:
        if content.startswith(ack):
            return content[len(ack):], classification, 1
    return content, None, 0


def _stream_reply(
    client: httpx.Client,
    endpoint: str,
    model: str,
    messages: list[dict[str, str]],
    session_id: str,
    temperature: float = 0.2,
) -> StreamReply:
    started = time.perf_counter()
    chunks: list[str] = []
    headers = {
        "x-airi-turn-origin": "local-evaluation",
        "x-airi-session-id": session_id,
        "x-airi-round-id": f"soak-{uuid4().hex}",
    }
    payload = {
        "model": model,
        "stream": True,
        "temperature": temperature,
        "messages": messages,
    }
    with client.stream("POST", endpoint, headers=headers, json=payload) as response:
        response.raise_for_status()
        immediate_ack_header = response.headers.get("X-AIRI-Immediate-Ack")
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                item = json.loads(data)
            except json.JSONDecodeError:
                continue
            for choice in item.get("choices", []):
                delta = choice.get("delta") or {}
                content = delta.get("content")
                if isinstance(content, str):
                    chunks.append(content)
    content, immediate_ack, immediate_ack_count = _split_immediate_ack(
        "".join(chunks), immediate_ack_header,
    )
    return StreamReply(
        # Keep the old post-join normalization, but apply it after removing
        # only the exact declared ACK so final dialogue is scored consistently.
        content=content.strip(),
        immediate_ack=immediate_ack,
        immediate_ack_count=immediate_ack_count,
        latency_ms=(time.perf_counter() - started) * 1000,
    )


def _score(case: dict[str, Any], output: str) -> dict[str, Any]:
    lowered = output.lower()
    forbidden = tuple(str(item).lower() for item in case.get("forbid", ()))
    language = str(case.get("language") or "ko")
    language_ok = (
        bool(HANGUL_RE.search(output))
        if language == "ko"
        else bool(LATIN_RE.search(output)) and not bool(HANGUL_RE.search(output))
        if language == "en"
        else bool(JAPANESE_RE.search(output))
    )
    checks = {
        "non_empty": bool(output),
        "hard_max_96_chars": len(output) <= 96,
        "preferred_60_chars": len(output) <= 60,
        "question_limit": output.count("?") <= int(case.get("max_questions", 1)),
        "no_meta": META_RE.search(output) is None,
        "no_control": CONTROL_RE.search(output) is None,
        "substantive_response": output.strip() not in NON_SUBSTANTIVE_RESPONSES,
        "target_language": language_ok,
        "banmal_register": language != "ko" or (
            POLITE_REGISTER_RE.search(output) is None and MID_POLITE_REGISTER_RE.search(output) is None
        ),
        "complete_sentence": bool(COMPLETE_END_RE.search(output)) and (
            INCOMPLETE_CLAUSE_RE.search(output) is None and STRUCTURAL_INCOMPLETE_RE.search(output) is None
        ),
        "no_unrequested_list": LIST_MARKER_RE.search(output) is None,
        "balanced_double_quotes": output.count('"') % 2 == 0,
        "no_stale_topic": not any(item in lowered for item in forbidden),
    }
    if case.get("require_question"):
        checks["asks_one_question"] = output.count("?") == 1
    if case.get("requires_explanation"):
        # Structural, not semantic: reject a reaction that merely sounds like
        # an explanation. Factual accuracy still needs retrieval/human review.
        checks["explanation_has_claim"] = bool(EXPLANATION_CLAIM_RE.search(output))
    if case.get("tool_boundary"):
        checks["no_unverified_action"] = bool(
            re.search(r"(?:못|않았|아니|확인|직접\s*실행|검색하지)", output)
        ) and re.search(r"(?:완료|해줄게|할게|검색했어[.!]?$)", output) is None
    return {"passed": all(checks.values()), "checks": checks}


def _write_report(
    path: Path,
    *,
    args: argparse.Namespace,
    results: list[dict[str, Any]],
    health_before: dict[str, Any],
    health_after: dict[str, Any] | None,
    complete: bool,
) -> None:
    transport_errors = sum(bool(row.get("error_type")) for row in results)
    report = {
        "runner_version": RUNNER_VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": args.endpoint,
        "model": args.model,
        "temperature": args.temperature,
        "request_timeout_seconds": args.request_timeout_seconds,
        "style_card_sha256": getattr(args, "style_card_sha256", None),
        "synthetic_only": True,
        "complete": complete,
        "case_count": len(results),
        "auto_passed": sum(bool(row["passed"]) for row in results),
        "transport_errors": transport_errors,
        "quality_gate": (
            "PENDING_HUMAN_REVIEW" if complete and not transport_errors else "FAIL"
        ),
        "health_before": health_before,
        "health_after": health_after,
        "cases": results,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:11435/v1/chat/completions")
    parser.add_argument("--model", default="exaone-airi:2.4b")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--request-timeout-seconds", type=float, default=20.0)
    parser.add_argument("--style-card", type=Path, help="optional local synthetic style card")
    parser.add_argument("--case-id", action="append", default=[], help="run only the named case; repeatable")
    args = parser.parse_args()
    if not 0.0 <= args.temperature <= 1.0:
        parser.error("temperature must be between 0 and 1")
    if not 5.0 <= args.request_timeout_seconds <= 120.0:
        parser.error("request timeout must be between 5 and 120 seconds")
    style_card = ""
    args.style_card_sha256 = None
    if args.style_card is not None:
        eval_root = Path(__file__).resolve().parent
        style_path = args.style_card.resolve()
        try:
            style_path.relative_to(eval_root)
        except ValueError:
            parser.error("style card must stay inside the eval directory")
        raw_style = style_path.read_bytes()
        if not raw_style or len(raw_style) > 4_000 or b"\x00" in raw_style:
            parser.error("style card must contain 1..4000 safe UTF-8 bytes")
        try:
            style_card = raw_style.decode("utf-8").strip()
        except UnicodeDecodeError:
            parser.error("style card must be UTF-8")
        args.style_card_sha256 = hashlib.sha256(raw_style).hexdigest()
    requested_ids = set(args.case_id)
    known_ids = {str(case["id"]) for case in CASES}
    unknown_ids = sorted(requested_ids - known_ids)
    if unknown_ids:
        parser.error(f"unknown case id(s): {', '.join(unknown_ids)}")
    selected_cases = tuple(case for case in CASES if not requested_ids or case["id"] in requested_ids)
    results: list[dict[str, Any]] = []
    histories: dict[str, list[dict[str, str]]] = {}
    sessions: dict[str, str] = {}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=args.request_timeout_seconds) as client:
        health_before = _health(client, args.endpoint)
        for case in selected_cases:
            group = str(case.get("group") or case["id"])
            history = histories.setdefault(group, [])
            session_id = sessions.setdefault(group, f"codex-soak-{uuid4().hex}")
            request_messages = [
                *([{"role": "system", "content": style_card}] if style_card else []),
                *history,
                {"role": "user", "content": case["input"]},
            ]
            error_type = None
            started = time.perf_counter()
            try:
                reply = _stream_reply(
                    client, args.endpoint, args.model, request_messages, session_id, args.temperature,
                )
                output = reply.content
                latency_ms = reply.latency_ms
            except httpx.HTTPError as exc:
                output = ""
                latency_ms = (time.perf_counter() - started) * 1000
                immediate_ack = None
                immediate_ack_count = 0
                error_type = type(exc).__name__
                # Later turns in the same group would no longer have a valid
                # synthetic history. Start a fresh local-only group instead of
                # fabricating an assistant turn after a transport failure.
                histories[group] = []
                sessions[group] = f"codex-soak-{uuid4().hex}"
            else:
                immediate_ack = reply.immediate_ack
                immediate_ack_count = reply.immediate_ack_count
                history.extend((
                    {"role": "user", "content": case["input"]},
                    {"role": "assistant", "content": output},
                ))
            row = {
                "id": case["id"],
                "group": group,
                "input": case["input"],
                "output": output,
                "immediate_ack": immediate_ack,
                "immediate_ack_count": immediate_ack_count,
                "latency_ms": round(latency_ms, 1),
                **_score(case, output),
                "human_review": "PENDING",
            }
            if error_type:
                row["error_type"] = error_type
            results.append(row)
            print(json.dumps(results[-1], ensure_ascii=False), flush=True)
            _write_report(
                args.output,
                args=args,
                results=results,
                health_before=health_before,
                health_after=None,
                complete=False,
            )
        health_after = _health(client, args.endpoint)
    _write_report(
        args.output,
        args=args,
        results=results,
        health_before=health_before,
        health_after=health_after,
        complete=True,
    )
    return 1 if any(row.get("error_type") for row in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
