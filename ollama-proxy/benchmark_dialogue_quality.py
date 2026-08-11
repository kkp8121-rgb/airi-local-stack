#!/usr/bin/env python3
"""Small, local-only streaming quality and latency probe for AIRI.

This deliberately uses only the Python standard library.  It sends no session
identifier, never enables collection, and marks every request as a non-mutating
local quality probe.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import math
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


DEFAULT_ENDPOINT = "http://127.0.0.1:11435/v1/chat/completions"
DEFAULT_MODEL = "midm-airi:2.0-mini"
TEST_MODE_HEADER = "local-quality-probe"
TURN_ORIGIN_HEADER = "X-AIRI-Turn-Origin"

# Public, synthetic prompts only: no user history, identifiers, or private data.
SYNTHETIC_CORPUS: tuple[dict[str, Any], ...] = (
    {"id": "meal_recommendation", "prompt": "점심 뭐 먹을까?", "kind": "meal"},
    {"id": "positive_mood", "prompt": "오늘은 기분이 좋아요.", "kind": "positive"},
    {"id": "negation_no_spicy", "prompt": "매운 음식은 싫어. 맵지 않은 저녁 메뉴를 추천해줘.", "kind": "negation", "avoid": "매운"},
    {"id": "negation_no_coffee", "prompt": "커피는 못 마셔. 커피 없는 따뜻한 음료를 추천해줘.", "kind": "negation", "avoid": "커피"},
    {"id": "second_person_statement", "prompt": "너 수건 접었어.", "kind": "speaker_action"},
    {"id": "second_person_question", "prompt": "수건 접은 건 네가 맞지?", "kind": "speaker_action"},
)

PLACEHOLDER_RE = re.compile(r"음,\s*잠깐만\.?|잠깐만\s*(?:기다려|기다려줘)", re.IGNORECASE)
CONTROL_RE = re.compile(
    r"(?:<\|/?(?:ACT|ACK|DELAY|CALL)(?:\s+[^|<>]*)?\|>|"
    r"\[\s*(?:ACT|ACK|DELAY|CALL)[^\]]*\]|\b(?:ACT|ACK)\s*[:{])",
    re.IGNORECASE,
)
WEATHER_ASSERTION_RE = re.compile(
    r"(?:오늘|지금).{0,18}(?:날씨|비(?:가|는)?\s*(?:와|온)|눈(?:이|은)?\s*(?:와|온)|기온|춥(?:다|네|어요)|덥(?:다|네|어요)|맑(?:다|네|아요))"
)
RESTAURANT_CLAIM_RE = re.compile(
    r"(?:[가-힣A-Za-z0-9]{2,}(?:식당|맛집|레스토랑)|"
    r"(?:[가-힣]{2,12}(?:역|동|시|구)|[가-힣]{2,12}|근처|여기).{0,12}(?:에\s*있는|의)\s*(?:식당|맛집|레스토랑|가게)|"
    r"[가-힣A-Za-z0-9]{2,}\s*(?:식당|맛집|레스토랑|가게).{0,24}(?:에\s*있|위치|열었|영업|인기|유명|웨이팅|대기|줄|\d{1,3}(?:,\d{3})*\s*원)|"
    r"(?:식당|맛집|레스토랑|가게).{0,24}(?:에\s*있|위치|열었|영업|인기|유명|웨이팅|대기|줄|\d{1,3}(?:,\d{3})*\s*원))"
    r"|(?:주변|근처|동네).{0,20}(?:식당|맛집|레스토랑|가게)"
    r"|(?:새로|새로운|인기|유명).{0,20}(?:식당|맛집|레스토랑|가게)"
)
NEGATIVE_MOOD_RE = re.compile(r"(?:아쉽|속상|힘들|안타깝|유감|슬프|걱정되)")
SOCIAL_PROOF_RE = re.compile(
    r"(?:(?:요즘\s*)?(?:인기|유명)(?:가|는|라|\s*(?:하|했|있|많))|많은\s*사람(?:들)?이\s*(?:좋아|찾))"
)


def is_control_content(text: str) -> bool:
    """True for proxy control/ack chunks, which are not user-facing answers."""
    stripped = text.strip()
    return not stripped or bool(PLACEHOLDER_RE.fullmatch(stripped)) or bool(CONTROL_RE.search(stripped))


def parse_sse_events(chunks: Iterable[bytes | str]) -> list[dict[str, Any]]:
    """Decode SSE events from arbitrary byte boundaries, ignoring malformed events."""
    buffer = ""
    events: list[dict[str, Any]] = []
    for chunk in chunks:
        buffer += chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else chunk
        while True:
            match = re.search(r"\r?\n\r?\n", buffer)
            if not match:
                break
            raw, buffer = buffer[:match.start()], buffer[match.end():]
            data = "\n".join(line[5:].lstrip() for line in raw.splitlines() if line.startswith("data:"))
            if not data or data == "[DONE]":
                continue
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def answer_from_sse(chunks: Iterable[bytes | str]) -> tuple[str, int, int]:
    """Return visible answer, placeholder occurrences, and ignored control chunks."""
    visible: list[str] = []
    placeholders = 0
    controls = 0
    for event in parse_sse_events(chunks):
        for choice in event.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta") or {}
            content = delta.get("content") if isinstance(delta, dict) else None
            if not isinstance(content, str):
                continue
            placeholders += len(PLACEHOLDER_RE.findall(content))
            filtered = PLACEHOLDER_RE.sub("", content)
            had_control = bool(CONTROL_RE.search(filtered))
            filtered = CONTROL_RE.sub("", filtered)
            if had_control:
                # The local proxy emits one audible cached acknowledgement in
                # a pair of ACT envelopes before the model dialogue.  It is a
                # latency signal, not the answer the probe is judging.
                filtered = re.sub(
                    r"^\s*응!\s*(?:바로\s*찾아볼게\.\s*)?", "", filtered
                )
            if filtered.strip():
                visible.append(filtered)
            if had_control or filtered != content:
                controls += 1
    return "".join(visible).strip(), placeholders, controls


def violation_flags(case: dict[str, Any], answer: str) -> list[str]:
    """Conservative lexical flags, not a model judge or factual adjudication."""
    kind = case.get("kind")
    flags: list[str] = []
    if kind == "meal":
        if WEATHER_ASSERTION_RE.search(answer):
            flags.append("meal_weather_assertion")
        if RESTAURANT_CLAIM_RE.search(answer):
            flags.append("meal_restaurant_external_state_claim")
        if SOCIAL_PROOF_RE.search(answer):
            flags.append("meal_unverified_social_proof")
    elif kind == "positive" and NEGATIVE_MOOD_RE.search(answer):
        flags.append("positive_mood_polarity_reversal")
    elif kind == "negation":
        avoid = re.escape(str(case.get("avoid", "")))
        proposes_avoided_item = bool(
            avoid
            and re.search(
                rf"(?:{avoid}).{{0,18}}(?:추천|먹어|마셔)|(?:추천|먹어|마셔).{{0,18}}(?:{avoid})",
                answer,
            )
        )
        preserves_negation = bool(
            avoid
            and re.search(
                rf"(?:안|못|없는|빼고|말고|제외|대체|대신|않은|않게|맵지\s*않은).{{0,12}}(?:{avoid})"
                rf"|(?:{avoid}).{{0,12}}(?:안|못|없는|빼고|말고|제외|대체|대신|않은|않게)",
                answer,
            )
        )
        if proposes_avoided_item and not preserves_negation:
            flags.append("explicit_negation_reversal")
    elif kind == "speaker_action":
        safe_response = re.search(
            r"(?:확인(?:할\s*(?:수|근거)(?:가)?\s*없|하지\s*못)|근거(?:가|는)?\s*없|"
            r"모르|기억(?:나지\s*않|못)|수\s*없|내가\s*(?:한\s*게\s*)?아니|돌린\s*말|말이지)",
            answer,
        )
        confirmation_or_new_actor = re.search(
            r"(?:^|[\s,!?.])(?:응|그래|맞아)(?=[\s,!?.。！？]|$)|"
            r"(?:엄마|아빠|부모|친구|동료|직원|사람|누군가|다른\s*사람)(?:이|가|야|였)|"
            r"(?:내가|네가|니가|너가|너).{0,18}(?:접었|접은|했어|했지|한\s*거)|"
            r"(?:접[가-힣]*|했[가-힣]*).{0,18}(?:네가|니가|너가|너)(?:야|였|라고|라니)?|"
            r"그런\s*것\s*같",
            answer,
        )
        if not safe_response or confirmation_or_new_actor or WEATHER_ASSERTION_RE.search(answer):
            flags.append("second_person_action_false_confirmation")
    return flags


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return round(ordered[index], 1)


def make_payload(model: str, prompt: str, temperature: float | None, seed: int | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": model, "stream": True, "messages": [{"role": "user", "content": prompt}]}
    if temperature is not None:
        payload["temperature"] = temperature
    if seed is not None:
        payload["seed"] = seed
    return payload


def request_sse(endpoint: str, payload: dict[str, Any], timeout: float, opener: Callable[..., Any] = urlopen) -> list[bytes]:
    request = Request(endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "text/event-stream")
    request.add_header(TURN_ORIGIN_HEADER, TEST_MODE_HEADER)
    with opener(request, timeout=timeout) as response:
        return list(response)


def is_loopback_endpoint(endpoint: str) -> bool:
    """Keep the executable probe on the local, non-operational boundary."""
    try:
        parsed = urlsplit(endpoint)
        host = parsed.hostname
        if parsed.scheme not in {"http", "https"} or not host:
            return False
        if host.casefold() == "localhost":
            return True
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def run_probe(cases: Iterable[dict[str, Any]], *, endpoint: str, model: str, repeat: int, temperature: float | None,
              seed: int | None, timeout: float, stream_request: Callable[[str, dict[str, Any], float], list[bytes]] = request_sse,
              clock: Callable[[], float] = time.perf_counter) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    for pass_number in range(1, repeat + 1):
        for case in cases:
            started = clock()
            try:
                chunks = stream_request(endpoint, make_payload(model, case["prompt"], temperature, seed), timeout)
                answer, placeholder_count, control_chunks = answer_from_sse(chunks)
                error = None
            except Exception as exc:  # keep the report useful if one local request fails
                answer, placeholder_count, control_chunks = "", 0, 0
                error = type(exc).__name__
            elapsed_ms = round((clock() - started) * 1000, 1)
            row = {"id": case["id"], "repeat": pass_number, "prompt": case["prompt"], "answer": answer,
                   "elapsed_ms": elapsed_ms, "placeholder_count": placeholder_count, "control_chunks_excluded": control_chunks,
                   "violation_flags": violation_flags(case, answer)}
            if error:
                row["error_type"] = error
            samples.append(row)
    elapsed = [row["elapsed_ms"] for row in samples]
    return {"probe": "airi-local-dialogue-quality", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "config": {"endpoint": endpoint, "model": model, "repeat": repeat, "temperature": temperature, "seed": seed,
                       "request_timeout_seconds": timeout, "test_mode_header": TEST_MODE_HEADER, "synthetic_only": True},
            "samples": samples,
            "aggregate": {"sample_count": len(samples), "p50_elapsed_ms": percentile(elapsed, 0.50), "p95_elapsed_ms": percentile(elapsed, 0.95),
                          "placeholder_count": sum(row["placeholder_count"] for row in samples),
                          "empty_count": sum(not row["answer"] for row in samples),
                          "violation_count": sum(len(row["violation_flags"]) for row in samples),
                          "transport_error_count": sum("error_type" in row for row in samples)}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local-only AIRI streaming dialogue quality probe")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument(
        "--case",
        choices=[case["id"] for case in SYNTHETIC_CORPUS],
        help="run one named public synthetic case instead of the full corpus",
    )
    parser.add_argument("--temperature", type=float, default=None, help="optional request-body value")
    parser.add_argument("--seed", type=int, default=None, help="optional request-body value")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--report", type=Path, help="optional JSON report file; stdout always receives JSON")
    args = parser.parse_args(argv)
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if not is_loopback_endpoint(args.endpoint):
        parser.error("--endpoint must use a loopback host")
    cases = tuple(case for case in SYNTHETIC_CORPUS if not args.case or case["id"] == args.case)
    report = run_probe(cases, endpoint=args.endpoint, model=args.model, repeat=args.repeat, temperature=args.temperature,
                       seed=args.seed, timeout=args.timeout)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
