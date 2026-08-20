"""Replay a synthetic 100-viewer first broadcast against the local proxy.

The stream, the pickup order, and the scoring live in `broadcast_sim.py`; this file
only does I/O. Given the same seed every arm sees the identical chat, so a memory
arm's numbers can be read as a difference in the proxy, not in the crowd.

Two input formats are supported on purpose. `runtime` sends exactly what
`chat-ingress/airi-event.mjs` sends today — `[YouTube] {text}`, with no author —
so any nickname in a reply is invented rather than recalled. `named` prefixes the
handle as a greybox probe of what a name-carrying client would change. Default is
`runtime`, because that is the path that actually exists.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlsplit, urlunsplit

import broadcast_sim as sim


HERE = Path(__file__).resolve().parent
CHAT_DIR = HERE.parent / "broadcast_chat"
sys.path.insert(0, str(CHAT_DIR))
import run_broadcast_chat_ab as ab  # noqa: E402

sys.path.insert(0, str(HERE.parent.parent))
from broadcast_contract import BROADCAST_CONTRACT_VERSION, apply_broadcast_contract  # noqa: E402
from memory_claim_guard import guard_memory_claim  # noqa: E402

import importlib.util as _importlib_util  # noqa: E402

_THANK_SPEC = _importlib_util.spec_from_file_location(
    "sim_thank_renderer", HERE.parent / "affect_broadcast" / "must_act_realization.py")
assert _THANK_SPEC is not None and _THANK_SPEC.loader is not None
thank_renderer = _importlib_util.module_from_spec(_THANK_SPEC)
_THANK_SPEC.loader.exec_module(thank_renderer)

# 브리핑에 되먹이면 안 되는 결정론 문구 가족 — absence 폴백·기억 가드·
# 오류 안내. 침묵 폴백 풀(FALLBACK_POOL)과 합쳐 에코 차단에 쓴다.
DEGENERATE_ECHO_PREFIXES = (
    "아직 기록", "아직 그건", "음… 그건 확실하게 기억 안 나",
    "답이 늦어져서", "답을 만들다가", "답이 너무 늦어서",
)

# ollama_proxy 의 침묵 폴백 풀과 같은 문구여야 폴백률이 의미를 갖는다.
FALLBACK_POOL = (
    "음, 잠깐만.",
    "어, 그건 잠깐 생각해 볼게.",
    "잠깐, 나 정리 좀 하고!",
    "음… 뭐라고 하지?",
    "아, 잠깐 헷갈렸어.",
    "그건 좀 있다가 다시 말해 줄게.",
)
DEFAULT_BASE_URL = "http://127.0.0.1:11435/v1"
DEFAULT_MODEL = "midm-airi:2.0-mini"
DEFAULT_HISTORY_TURNS = 8
SESSION_HEADER = "x-airi-session-id"
# 디렉터→프록시 근거 신호. 프록시의 absence 폴백은 요청 히스토리만 보므로,
# 시스템 프롬프트에 넣은 브리핑에 회상 재료가 있다는 사실을 이 헤더로 알린다.
BRIEFING_EVIDENCE_HEADER = "x-airi-briefing-evidence"
BRIEFING_EVIDENCE_MEMORY = "memory"


def build_system_content(fixture: dict[str, Any], beat: dict[str, Any], contract: str) -> str:
    """A/B 러너의 시스템 문구에 고정 주제 블록을 덧붙인다."""
    base = apply_broadcast_contract(ab.build_system_content(), contract == "on")
    topic = fixture["topic"]
    return (
        f"{base}\n\n[오늘 방송]\n"
        f"- 주제: {topic['title']}\n"
        f"- 지금 구간: {beat['label']}\n"
        f"- 상황: {beat['airi_cue']}\n"
        "- 주제에서 벗어난 채팅에는 짧게 받아치고 주제로 돌아와."
    )


def set_briefing_evidence_header(transport: Any, attach: bool) -> None:
    """이번 턴 요청에만 근거 신호를 싣는다 — 세션 헤더와 같은 자리에서 다룬다."""
    if attach:
        transport.client.headers[BRIEFING_EVIDENCE_HEADER] = BRIEFING_EVIDENCE_MEMORY
    else:
        transport.client.headers.pop(BRIEFING_EVIDENCE_HEADER, None)


def proxy_health_url(base_url: str) -> str:
    """Root ``/health`` URL for a proxy base URL that may carry a path (``/v1``).

    The chat endpoint lives under a versioned path (``/v1/chat/completions``);
    the health telemetry ``ollama_proxy.py`` serves does not.
    """
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, "/health", "", ""))


def read_absence_bypasses(transport: Any, health_url: str) -> int | None:
    """Read the proxy's cumulative absence-guard-release counter, or None.

    Minor 2 (Task 1 review): the row only knew whether *this* turn attached
    the evidence header (``briefing_evidence``); whether the absence guard
    actually released because of it lived only as a cumulative total on the
    proxy (``/health`` → ``briefing_evidence.absence_bypasses``), content-free
    by design (ollama_proxy.py 무수정 — no per-request marker was added).
    Turns in this runner are answered strictly sequentially, so diffing that
    total immediately before and after one signalled turn attributes any
    increase to that turn, as long as nothing else talks to the same proxy
    process concurrently during the run.
    """
    try:
        response = transport.client.get(health_url, timeout=5.0)
        response.raise_for_status()
        return int(response.json()["briefing_evidence"]["absence_bypasses"])
    except Exception:
        return None


def format_user_content(message: dict[str, Any], author_format: str) -> str:
    if author_format == "named":
        marker = "[후원] " if message["kind"] == "donation" else ""
        return f"{ab.USER_PREFIX}{marker}{message['author']}: {message['text']}"
    return f"{ab.USER_PREFIX}{message['text']}"


def run_arm(
    transport: Any,
    fixture: dict[str, Any],
    stream: dict[str, Any],
    picks: Sequence[dict[str, Any]],
    *,
    model: str,
    contract: str,
    protocol: str,
    author_format: str,
    history_turns: int,
    max_tokens: int,
    timeout: float,
    pre_session_seeds: bool,
    briefing: str = "off",
    acts: str = "off",
    briefing_evidence: str = "off",
    health_url: str | None = None,
) -> dict[str, Any]:
    roster = [viewer["handle"] for viewer in fixture["viewers"]]
    drift_terms = sorted(sim.offtopic_terms(fixture))
    openers = list(fixture.get("aggregation_openers", []))
    guard_fallback = fixture.get("memory_guard_fallback", "")
    history: list[tuple[str, str]] = []
    rows: list[dict[str, Any]] = []
    transcript: list[dict[str, Any]] = []
    answered_picks: list[dict[str, Any]] = []
    wave_counter = 0
    failures = 0
    # 해제(release) 관측성: 이 arm 이 근거 헤더를 실제로 쓸 때만 기준값을 잡는다.
    last_bypass_total: int | None = None
    if health_url and briefing_evidence == "on":
        last_bypass_total = read_absence_bypasses(transport, health_url)

    if pre_session_seeds:
        # 이전 세션에서 이미 들은 사실로 만든다 — 방송 시작 전에 한 번 오간다.
        for probe in fixture.get("memory_probes", []):
            beat = fixture["topic"]["beats"][0]
            content = f"{ab.USER_PREFIX}{probe['seed_text']}"
            record = ab.call_once(
                transport, model=model,
                messages=[{"role": "system", "content": build_system_content(fixture, beat, contract)},
                          {"role": "user", "content": content}],
                max_tokens=max_tokens, timeout=timeout,
            )
            body = ab.scoring_body(record, record.get("response", "") or "", protocol)
            transcript.append({"stage": "pre_session", "user": content, "airi": body})

    transcript.append({"stage": "scripted_opening", "airi": fixture["topic"]["signature_greeting"]})

    for pick in picks:
        message = pick["message"]
        beat = sim.beat_at(fixture, message["minute"])
        system_content = build_system_content(fixture, beat, contract)
        carried_evidence = False
        if briefing == "on":
            echo_safe = sim.blank_degenerate_echo(
                answered_picks, FALLBACK_POOL + DEGENERATE_ECHO_PREFIXES)
            briefing_text, carried_evidence = sim.build_turn_briefing_with_evidence(
                fixture, stream, pick, echo_safe)
            system_content += "\n\n" + briefing_text
        signalled = briefing_evidence == "on" and carried_evidence
        set_briefing_evidence_header(transport, signalled)
        user_content = format_user_content(message, author_format)

        deterministic_act = None
        record: dict[str, Any] = {}
        raw = ""
        opener = ""
        released: bool | None = None
        if acts == "on" and pick["effective_kind"] == "donation":
            # P2-1: 후원 감사는 승인된 결정론 렌더러가 말한다 — 자유 생성 0.
            closer_index = int(message.get("donation_index", 0)) % len(thank_renderer.THANK_CALLOUT_CLOSERS)
            body = thank_renderer.render_thank_callout_text(message["author"], closer_index)
            deterministic_act = "thank_renderer"
        else:
            if acts == "on" and pick.get("aggregate_expected") and openers:
                # P2-2: 여론임을 먼저 결정론으로 짚고, 내용은 모델이 잇는다.
                labels = {wave["tag"]: wave.get("label", wave["tag"])
                          for wave in fixture.get("opinion_waves", [])}
                opener = openers[wave_counter % len(openers)].format(
                    주제=labels.get(message.get("tag"), "이"))
                wave_counter += 1
            kept = history[-history_turns:] if history_turns > 0 else []
            messages = [{"role": "system", "content": system_content}]
            for past_user, past_assistant in kept:
                messages.extend(({"role": "user", "content": past_user},
                                 {"role": "assistant", "content": past_assistant}))
            messages.append({"role": "user", "content": user_content})

            record = ab.call_once(transport, model=model, messages=messages,
                                  max_tokens=max_tokens, timeout=timeout)
            raw = record.get("response", "") or ""
            body = ab.scoring_body(record, raw, protocol)
            if not record.get("ok"):
                failures += 1
            if signalled and health_url and last_bypass_total is not None:
                current_bypass_total = read_absence_bypasses(transport, health_url)
                if current_bypass_total is not None:
                    released = current_bypass_total > last_bypass_total
                    last_bypass_total = current_bypass_total
            guard_fired = False
            if acts == "on" and guard_fallback:
                # P2-3: 근거 없는 "응, 기억해" 단정을 정직한 회피로 교체.
                body, guard_fired = guard_memory_claim(message["text"], body, guard_fallback)
            if opener:
                body = f"{opener} {body}".strip() if body else opener
                deterministic_act = "wave_opener"
            elif guard_fired:
                deterministic_act = "memory_guard"

        fact_tokens = None
        if briefing == "on":
            token_pool: set[str] = set()
            for item in sim.select_viewer_lines(fixture, stream, pick):
                token_pool |= sim._tokens(item["text"])
            fact_tokens = sorted(token_pool)
        register = ab.score_response(body)
        row = sim.score_turn(pick, body, beat=beat, fallback_pool=FALLBACK_POOL,
                             roster_handles=roster, drift_terms=drift_terms,
                             briefing_fact_tokens=fact_tokens)
        row.update({
            "beat": beat["id"],
            "backlog_size": pick["backlog_size"],
            "briefing_evidence": signalled,
            "briefing_evidence_released": released,
            "deterministic_act": deterministic_act,
            "polite_violation": "v_polite_response" in register.get("violations", []),
            "banmal": bool(register.get("markers", {}).get("banmal")),
            "ttft_ms": record.get("ttft_ms"),
            "complete_ms": record.get("complete_ms"),
            "failure": record.get("failure"),
        })
        rows.append(row)
        transcript.append({
            "stage": "turn", "turn_index": pick["turn_index"], "minute": message["minute"],
            "beat": beat["id"], "kind": pick["effective_kind"], "author": message["author"],
            "chat": message["text"], "user_sent": user_content, "airi": body, "raw": raw,
            "deterministic_act": deterministic_act,
            "backlog_size": pick["backlog_size"], "backlog_ids": pick["backlog_ids"],
        })
        # Task 13: 렌더러가 부른 이름이 되먹여지면 이후 모델 턴이 그 이름을 재호명한다
        # (Task 9 실측 19턴 중 16건). 실제 발화(트랜스크립트·채점)는 그대로 두고,
        # 히스토리·브리핑으로 되먹이는 사본만 이름 없는 A4.2 v1 문구로 치환한다.
        fed_response = thank_renderer._TEMPLATES["thank"] if deterministic_act == "thank_renderer" else body
        history.append((user_content, fed_response))
        answered_picks.append({**pick, "response": fed_response})

    transcript.append({"stage": "scripted_closing", "airi": "오늘 여기까지야. 와줘서 고마워, 다음에 또 보자!"})
    summary = sim.summarize_turns(rows)
    summary["polite_violation"] = {"hits": sum(1 for row in rows if row["polite_violation"]), "of": len(rows)}
    summary["banmal"] = {"hits": sum(1 for row in rows if row["banmal"]), "of": len(rows)}
    release_observed = [row for row in rows if row.get("briefing_evidence_released") is not None]
    summary["briefing_evidence_release"] = {
        "hits": sum(1 for row in release_observed if row["briefing_evidence_released"]),
        "of": len(release_observed),
    }
    summary["transport_failures"] = failures
    return {"summary": summary, "rows": rows, "transcript": transcript}


def rescore_report(payload: dict[str, Any], fixture_path: Path | None = None) -> dict[str, Any]:
    """Re-run scoring over a finished report's transcript, spending no model time.

    The stream is deterministic, so the picks — and with them every check the
    scorer needs — are rebuilt from the recorded seed rather than stored twice.
    This exists so a scoring change can be applied to arms that already ran,
    instead of leaving them incomparable.
    """
    fixture = sim.load_fixture(fixture_path) if fixture_path else sim.load_fixture()
    stream = sim.generate_stream(fixture, seed=payload["seed"])
    if stream["fixture_sha256"] != payload["fixture_sha256"]:
        raise SystemExit("픽스처가 그때와 다르다 — 재채점하면 arm 비교가 깨진다")
    picks = {pick["turn_index"]: pick for pick in sim.plan_pickups(stream, fixture)}
    roster = [viewer["handle"] for viewer in fixture["viewers"]]
    drift_terms = sorted(sim.offtopic_terms(fixture))
    bodies = {entry["turn_index"]: entry["airi"] for entry in payload["transcript"]
              if entry["stage"] == "turn"}
    previous = {row["turn_index"]: row for row in payload["rows"]}
    rows = []
    for turn_index in sorted(bodies):
        pick = picks[turn_index]
        beat = sim.beat_at(fixture, pick["message"]["minute"])
        fact_tokens = None
        if payload.get("briefing") == "on":
            token_pool: set[str] = set()
            for item in sim.select_viewer_lines(fixture, stream, pick):
                token_pool |= sim._tokens(item["text"])
            fact_tokens = sorted(token_pool)
        row = sim.score_turn(pick, bodies[turn_index], beat=beat, fallback_pool=FALLBACK_POOL,
                             roster_handles=roster, drift_terms=drift_terms,
                             briefing_fact_tokens=fact_tokens)
        carried = previous.get(turn_index, {})
        row.update({key: carried[key] for key in
                    ("beat", "backlog_size", "briefing_evidence", "briefing_evidence_released",
                     "polite_violation", "banmal", "ttft_ms", "complete_ms", "failure")
                    if key in carried})
        rows.append(row)
    summary = sim.summarize_turns(rows)
    summary["polite_violation"] = {"hits": sum(1 for row in rows if row.get("polite_violation")), "of": len(rows)}
    summary["banmal"] = {"hits": sum(1 for row in rows if row.get("banmal")), "of": len(rows)}
    release_observed = [row for row in rows if row.get("briefing_evidence_released") is not None]
    summary["briefing_evidence_release"] = {
        "hits": sum(1 for row in release_observed if row["briefing_evidence_released"]),
        "of": len(release_observed),
    }
    summary["transport_failures"] = payload["summary"].get("transport_failures")
    return {**payload, "summary": summary, "rows": rows, "rescored": True}


def render_packet(payload: dict[str, Any]) -> str:
    """사람이 원문을 읽고 판단할 수 있게 전체 대화를 그대로 편다."""
    lines = [f"# 방송 시뮬레이션 원문 검토 packet — {payload['topic_title']}", ""]
    lines += [
        f"- arm: `{payload['memory_arm']}` | 계약: `{payload['contract']}` | 입력형식: `{payload['author_format']}`",
        f"- 모델: `{payload['model']}` | seed: `{payload['seed']}` | 턴: {payload['summary']['turns']}",
        f"- 채팅 총 {payload['stream_messages']}건 중 픽업 {payload['summary']['turns']}건",
        "",
        "> 채점은 전부 어휘 휴리스틱이다. 아래 원문이 근거이고 수치는 요약일 뿐이다.",
        "",
    ]
    for entry in payload["transcript"]:
        if entry["stage"] == "scripted_opening":
            lines += ["## 오프닝 (대본)", "", f"**AIRI**: {entry['airi']}", ""]
        elif entry["stage"] == "scripted_closing":
            lines += ["## 클로징 (대본)", "", f"**AIRI**: {entry['airi']}", ""]
        elif entry["stage"] == "pre_session":
            lines += [f"- (이전 세션) **시청자**: {entry['user']}", f"  **AIRI**: {entry['airi']}", ""]
        else:
            head = (f"### T{entry['turn_index']:02d} · {entry['minute']}분 · {entry['beat']} · "
                    f"{entry['kind']} · 대기 {entry['backlog_size']}건")
            lines += [head, "", f"**{entry['author']}**: {entry['chat']}", "",
                      f"**AIRI**: {entry['airi'] or '(빈 응답)'}", ""]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="100-viewer first-broadcast simulation")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--token", default=None)
    parser.add_argument("--memory-arm", choices=sim.MEMORY_ARMS, default="off")
    parser.add_argument("--session-id", default=None, help="proxy 의 x-airi-session-id 값")
    parser.add_argument("--contract", choices=("off", "on"), default="on")
    parser.add_argument("--protocol", choices=("raw", "operational"), default="operational")
    parser.add_argument("--author-format", choices=("runtime", "named"), default="runtime")
    parser.add_argument("--fixture", type=Path, default=None,
                        help="대체 픽스처 경로 (기본: first_broadcast_v1.json)")
    parser.add_argument("--seed", type=int, default=20260818)
    parser.add_argument("--max-turns", type=int, default=None)
    parser.add_argument("--history-turns", type=int, default=DEFAULT_HISTORY_TURNS)
    parser.add_argument("--max-tokens", type=int, default=220)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--briefing", choices=("off", "on"), default="off",
                        help="P1 쇼 러너 턴 브리핑 조립 (기본 off = 기존과 동일)")
    parser.add_argument("--acts", choices=("off", "on"), default="off",
                        help="P2 결정론 발화 (thank 렌더러·여론 오프너·기억 가드)")
    parser.add_argument("--briefing-evidence", choices=("off", "on"), default="off",
                        help="브리핑에 회상 재료가 실린 턴에 근거 신호 헤더 부착 (기본 off = 기존과 동일)")
    parser.add_argument("--stream-only", action="store_true", help="모델 호출 없이 스트림/픽업만 낸다")
    parser.add_argument("--rescore", type=Path, help="기존 리포트를 모델 호출 없이 재채점한다")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--packet", type=Path)
    args = parser.parse_args(argv)

    if args.rescore:
        payload = rescore_report(json.loads(args.rescore.read_text(encoding="utf-8")),
                                 fixture_path=args.fixture)
        output = json.dumps(payload, ensure_ascii=False, indent=2)
        (args.report or args.rescore).write_text(output + "\n", encoding="utf-8")
        if args.packet:
            args.packet.write_text(render_packet(payload), encoding="utf-8")
        print(json.dumps({"rescored": payload["summary"]}, ensure_ascii=False, indent=2))
        return 0

    fixture = sim.load_fixture(args.fixture) if args.fixture else sim.load_fixture()
    stream = sim.generate_stream(fixture, seed=args.seed)
    picks = sim.plan_pickups(stream, fixture, max_turns=args.max_turns)

    if args.stream_only:
        payload = {"schema_version": sim.REPORT_SCHEMA_VERSION, "mode": "stream_only", "seed": args.seed,
                   "fixture_sha256": stream["fixture_sha256"], "stream_messages": len(stream["messages"]),
                   "picks": [{"turn_index": pick["turn_index"], "kind": pick["effective_kind"],
                              "minute": pick["message"]["minute"], "author": pick["message"]["author"],
                              "text": pick["message"]["text"], "backlog_size": pick["backlog_size"]}
                             for pick in picks]}
        output = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.report:
            args.report.write_text(output + "\n", encoding="utf-8")
        print(output)
        return 0

    transport = ab.HttpTransport(args.base_url, args.token)
    session_id = args.session_id or f"broadcast-sim-{args.memory_arm}-{args.seed}"
    transport.client.headers[SESSION_HEADER] = session_id
    try:
        result = run_arm(
            transport, fixture, stream, picks,
            model=args.model, contract=args.contract, protocol=args.protocol,
            author_format=args.author_format, history_turns=args.history_turns,
            max_tokens=args.max_tokens, timeout=args.timeout,
            pre_session_seeds=args.memory_arm == "seeded",
            briefing=args.briefing,
            acts=args.acts,
            briefing_evidence=args.briefing_evidence,
            health_url=proxy_health_url(args.base_url),
        )
    finally:
        transport.close()

    payload = {
        "schema_version": sim.REPORT_SCHEMA_VERSION,
        "topic_title": stream["topic_title"],
        "model": args.model,
        "memory_arm": args.memory_arm,
        "briefing": args.briefing,
        "acts": args.acts,
        "briefing_evidence": args.briefing_evidence,
        "session_id": session_id,
        "contract": args.contract,
        "contract_version": BROADCAST_CONTRACT_VERSION if args.contract == "on" else None,
        "protocol": args.protocol,
        "author_format": args.author_format,
        "seed": args.seed,
        "fixture_sha256": stream["fixture_sha256"],
        "stream_messages": len(stream["messages"]),
        "history_turns": args.history_turns,
        **result,
    }
    output = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(output + "\n", encoding="utf-8")
    if args.packet:
        args.packet.write_text(render_packet(payload), encoding="utf-8")
    print(json.dumps({"summary": payload["summary"], "report": str(args.report or ""),
                      "packet": str(args.packet or "")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
