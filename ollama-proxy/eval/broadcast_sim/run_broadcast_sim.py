"""Replay a synthetic 100-viewer first broadcast against the local proxy.

The stream, the pickup order, and the scoring live in `broadcast_sim.py`; this file
only does I/O. Given the same seed every arm sees the identical chat, so a memory
arm's numbers can be read as a difference in the proxy, not in the crowd.

Two input formats are supported on purpose. `runtime` sends exactly what
`chat-ingress/airi-event.mjs` sends today — `[YouTube] {text}`, with no author —
so any nickname in a reply is invented rather than recalled. `named` prefixes the
handle as a greybox probe of what a name-carrying client would change. Default is
`runtime`, because that is the path that actually exists.

`--replay-chat` swaps the generated crowd for a pseudonymized capture of real
viewer chat: same stream shape, same pickup rules, same scoring — only the
messages come from a file instead of the fixture's templates, so the answers can
be handed to a human rater instead of a lexical heuristic.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import secrets
import sys
import time
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
# ollama_proxy 의 파이프라인 실패 안내 문구와 바이트로 같아야 오류율이 의미를
# 갖는다. 침묵 폴백(FALLBACK_POOL)과 달리 이 응답은 모델 발화가 아예 없었다는
# 뜻이라 어떤 축으로도 채점할 수 없다.
# deterministic_utterance_layer.BRIEFING_EVIDENCE_MARKER 와 바이트로 같아야 한다
# (후원 마커와 같은 방식으로 하드코딩하고 AST 대조 테스트로 고정한다). 마커 뒤
# 전체가 이 턴의 증거이며, 마커가 없으면 계층은 예전처럼 system 을 전부 제외한다.
BRIEFING_EVIDENCE_BLOCK_MARKER = "[턴 근거 메모]"
SERVICE_ERROR_POOL = (
    "답을 만들다가 문제가 생겼어. 다시 말해줘.",
    "답이 너무 늦어서 잠깐 멈췄어. 다시 말해줘.",
    "답이 늦어져서 잠깐 멈췄어.",
)
DEFAULT_BASE_URL = "http://127.0.0.1:11435/v1"
DEFAULT_MODEL = "midm-airi:2.0-mini"
DEFAULT_HISTORY_TURNS = 8
SESSION_HEADER = "x-airi-session-id"
# 디렉터→프록시 근거 신호. 프록시의 absence 폴백은 요청 히스토리만 보므로,
# 시스템 프롬프트에 넣은 브리핑에 회상 재료가 있다는 사실을 이 헤더로 알린다.
BRIEFING_EVIDENCE_HEADER = "x-airi-briefing-evidence"
BRIEFING_EVIDENCE_MEMORY = "memory"
LIVE_CONTEXT_ENV_MASTER = "AIRI_LIVE_BROADCAST_MASTER_TOKEN"
LIVE_CONTEXT_ENV_OBSERVER = "AIRI_LIVE_BROADCAST_OBSERVER_TOKEN"
DONATION_CONTINUATION_CONTRACT = (
    "[후원 본문 이어말하기]\n"
    "후원자 호명과 감사 의례는 결정론 렌더러가 이미 먼저 말해. "
    "이름이나 감사를 반복하지 말고, 현재 후원 메시지의 내용에 대한 본답변만 이어서 말해. "
    "입력과 방송 맥락에 있는 사실을 받아 자기 판단과 이유를 자연스럽게 밝힌 뒤 방송 흐름으로 돌아와."
)
# 프록시 결정론 계층(P5)이 후원 턴 본문 끝에 붙이는 고정 감사 문장. 실제 발화에는
# 남기고, 되먹임 사본에서만 떼어낸다 — 감사 문구가 히스토리에 쌓이면 모델이 이후
# 질문에도 감사로 답한다(사람 평가 run 04 실측: 이어진 질문 23건이 "고마워.").
DONATION_ECHO_THANKS = "후원 고마워!"


TRANSCRIPT_WINDOW_MS = 45_000
TRANSCRIPT_MAX_CHARS = 400
TRANSCRIPT_CUE_USER = "[방송] 진행 멘트"
TRANSCRIPT_ROW_KEYS = ("start_ms", "end_ms", "text")


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


def read_journal_failure_state(transport: Any, health_url: str) -> dict[str, object]:
    """Return only content-free journal diagnostics after a live turn fails."""
    try:
        response = transport.client.get(health_url, timeout=5.0)
        response.raise_for_status()
        health = response.json()
        journal = health.get("journal_completion") if isinstance(health, dict) else None
        if not isinstance(journal, dict):
            return {}
        result: dict[str, object] = {}
        for key in ("errors", "pending_tasks", "last_error_type", "last_outcome"):
            value = journal.get(key)
            if type(value) in {int, str} or value is None:
                result[key] = value
        return result
    except Exception:
        return {}


def read_model_digest(transport: Any, health_url: str) -> str | None:
    """Content-free model identity from ``/health`` (``chat_model.digest.digest``).

    Returns ``None`` when the proxy does not advertise a 64-hex digest; the
    comparator treats that as a missing confounder and fails closed.
    """
    try:
        response = transport.client.get(health_url, timeout=5.0)
        response.raise_for_status()
        health = response.json()
        chat_model = health.get("chat_model") if isinstance(health, dict) else None
        digest = chat_model.get("digest") if isinstance(chat_model, dict) else None
        value = digest.get("digest") if isinstance(digest, dict) else None
    except Exception:
        return None
    if not isinstance(value, str) or len(value) != 64 or set(value) - set("0123456789abcdef"):
        return None
    return value


def verify_live_contract(transport: Any, health_url: str, contract: str) -> bool:
    """Fail closed unless the live proxy advertises the requested contract."""
    try:
        response = transport.client.get(health_url, timeout=5.0)
        response.raise_for_status()
        health = response.json()
        advertised = health.get("broadcast_contract")
        immediate_ack = health.get("immediate_ack")
    except Exception as exc:
        raise RuntimeError("live broadcast contract health verification failed") from exc
    expected = contract == "on"
    if type(advertised) is not bool or advertised is not expected:
        raise RuntimeError("live broadcast contract does not match --contract")
    if immediate_ack != "marker":
        raise RuntimeError("live broadcast context requires immediate_ack=marker")
    return True


def format_user_content(message: dict[str, Any], author_format: str) -> str:
    if author_format == "named":
        marker = "[후원] " if message["kind"] == "donation" else ""
        return f"{ab.USER_PREFIX}{marker}{message['author']}: {message['text']}"
    return f"{ab.USER_PREFIX}{message['text']}"


def live_context_for_turn(fixture: dict[str, Any], beat: dict[str, Any], briefing: str, donation: bool) -> dict[str, object]:
    """The runner is a capability client: it sends structured context, never a prompt."""
    return {
        "schema_version": 1,
        "topic_title": fixture["topic"]["title"],
        "segment_label": beat["label"],
        "situation": beat["airi_cue"],
        "briefing": briefing,
        "donation_continuation": donation,
    }


def broadcast_control_url(base_url: str, receipt: bool = False) -> str:
    """Return the capability endpoint from a possibly versioned chat base URL."""
    parts = urlsplit(base_url)
    endpoint = "/v1/airi/broadcast/receipt" if receipt else "/v1/airi/broadcast/control"
    return urlunsplit((parts.scheme, parts.netloc, endpoint, "", ""))


def _broadcast_control(
    transport: Any, base_url: str, token: str, payload: dict[str, object], *, receipt: bool = False,
) -> tuple[int, dict[str, object]]:
    response = transport.client.post(
        broadcast_control_url(base_url, receipt), json=payload,
        headers={"x-airi-broadcast-observer-token" if receipt else "x-airi-broadcast-master-token": token},
    )
    if response.status_code >= 300 and not (receipt and response.status_code == 202):
        # The status is content-free but essential for distinguishing a
        # durability wait (202) from auth, schema, or runtime-state rejection.
        reason = str(
            getattr(response, "headers", {}).get("x-airi-broadcast-reject", "")
        )
        suffix = f", reason={reason}" if reason else ""
        expected_answer = str(
            getattr(response, "headers", {}).get(
                "x-airi-broadcast-expected-answer-sha256", ""
            )
        )
        if re.fullmatch(r"[0-9a-f]{64}", expected_answer):
            supplied = payload.get("answer_sha256")
            suffix += f", expected_answer_sha256={expected_answer}, supplied_answer_sha256={supplied}"
        raise RuntimeError(
            f"live broadcast capability unavailable (status={response.status_code}{suffix})"
        )
    result = response.json()
    if not isinstance(result, dict):
        raise RuntimeError("invalid live broadcast capability response")
    return response.status_code, result


def live_turn_type(pick: dict[str, Any]) -> str:
    """Map fixture kinds to the closed runtime vocabulary."""
    kind = pick["effective_kind"]
    if kind == "donation":
        return "donation"
    if pick.get("aggregate_expected"):
        return "batched_chat"
    if kind in {"question", "memory_probe"}:
        return "chat_question"
    if kind == "reaction":
        return "chat_teasing"
    return "selected_chat"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def receipt_answer_from_attested_stream(record: dict[str, Any], raw: str) -> tuple[str, bool]:
    """Bind the receipt to the response-specific ACK contract on the wire.

    ``AIRI_IMMEDIATE_ACK=marker`` is a process default, not a promise that
    every successful response branch prepends a marker.  The response header
    is authoritative: remove exactly one renderer-owned marker when it says
    ``marker`` and otherwise preserve the terminal dialogue byte-for-byte
    apart from the same outer whitespace canonicalization used by journaling.
    """
    meta = record.get("transport_meta")
    if type(meta) is not dict:
        raise RuntimeError("live broadcast receipt requires an attested stream")
    mode = meta.get("immediate_ack")
    if mode == "marker":
        match = ab.ACT_MARKER.match(raw)
        if match is None:
            raise RuntimeError("live broadcast marker stream is missing its leading marker")
        return raw[match.end():].strip(), True
    if mode in {"false", "silent"}:
        return raw.strip(), False
    raise RuntimeError(
        "live broadcast receipt has an unknown immediate ACK contract "
        f"(mode={mode!r}, streaming={meta.get('streaming')!r}, "
        f"status={meta.get('status_code')!r})"
    )


def _temporary_headers(transport: Any, values: dict[str, str]):
    """Set per-turn headers without letting capability tokens leak to later calls."""
    headers = transport.client.headers
    previous = {key: headers.get(key) for key in values}

    class _Headers:
        def __enter__(self):
            headers.update(values)

        def __exit__(self, *_args):
            for key, old_value in previous.items():
                if old_value is None:
                    headers.pop(key, None)
                else:
                    headers[key] = old_value

    return _Headers()


class LiveInputScreened(RuntimeError):
    """The proxy's input screening consumed this turn before any capability claim.

    A synthetic fixture never carries screenable input, so the matrix treats
    this as fatal.  Replayed real chat does (profanity, privacy), and there the
    block is the production outcome: the message is consumed without an
    answer and the show goes on.
    """

    def __init__(self, category: str) -> None:
        super().__init__(
            "live broadcast fixture input was rejected before capability claim "
            f"(category={category})"
        )
        self.category = category


def run_live_capability_turn(
    transport: Any, live_broadcast: dict[str, str], *, model: str,
    messages: list[dict[str, str]], user_content: str, max_tokens: int,
    timeout: float, action_id: str, trace_id: str, turn_type: str,
    broadcast_context: dict[str, object] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Issue, execute, and durably receipt-bind one live user-only turn."""
    issue: dict[str, object] = {
        "action": "issue_turn", "show_id": live_broadcast["show_id"],
        "action_id": action_id, "turn_type": turn_type,
        "required_delivery": "renderer",
    }
    if broadcast_context is not None:
        issue["broadcast_context"] = broadcast_context
    _, capability = _broadcast_control(
        transport, live_broadcast["base_url"], live_broadcast["master_token"], issue,
    )
    turn_token = capability.get("turn_token")
    delivery_token = capability.get("delivery_token")
    if not isinstance(turn_token, str) or not isinstance(delivery_token, str):
        raise RuntimeError("invalid live broadcast turn capability")
    with _temporary_headers(transport, {
        "x-airi-broadcast-turn-token": turn_token,
        "x-airi-request-id": trace_id,
    }):
        record = ab.call_once(transport, model=model, messages=messages,
                              max_tokens=max_tokens, timeout=timeout)
    raw = record.get("response", "") or ""
    if not record.get("ok"):
        failure = str(record.get("failure") or "unknown")
        raise RuntimeError(
            f"live broadcast chat did not produce a terminal answer (failure={failure})"
        )
    transport_meta = record.get("transport_meta")
    if (
        isinstance(transport_meta, dict)
        and transport_meta.get("input_screened") == "blocked"
    ):
        category = str(transport_meta.get("input_screen_category") or "unknown")
        raise LiveInputScreened(category)
    # The public OpenAI stream opens with one renderer-owned ACT marker.
    # Durable memory stores the remaining public dialogue. Remove only that
    # attested prefix: scoring may discard additional ACT-like strings, but a
    # receipt must stay byte-bound to what actually crossed the public wire.
    receipt_answer, marker_stripped = receipt_answer_from_attested_stream(record, raw)
    if not receipt_answer:
        raise RuntimeError("live broadcast chat produced no substantive answer")
    record["receipt_binding"] = {
        "schema": "airi.attested-stream-answer.v1",
        "leading_marker_stripped": marker_stripped,
    }
    receipt = {
        "delivery_token": delivery_token,
        "delivery_status": "delivered" if record.get("ok") else "failed",
        "required_delivery": "renderer", "trace_id": trace_id,
        "query_sha256": sha256_text(user_content),
        "user_sha256": sha256_text(user_content),
        "answer_sha256": sha256_text(receipt_answer),
    }
    # Local SQLite/journal flush can lag the streamed answer under the full
    # T3 stack. Keep the gate bounded, but allow the receipt to become durable
    # before declaring a false runtime failure.
    deadline = time.monotonic() + 30.0
    while True:
        try:
            status, _ = _broadcast_control(
                transport, live_broadcast["base_url"],
                live_broadcast["observer_token"], receipt, receipt=True,
            )
        except RuntimeError as exc:
            # A receipt can cross the endpoint between the 202 pending seam
            # and the durable journal write.  Treat only this explicit,
            # content-free durability reason as retryable within the existing
            # bounded deadline; all auth/schema/runtime failures remain fatal.
            if "reason=journal_pending" in str(exc) and time.monotonic() < deadline:
                time.sleep(0.05)
                continue
            state: dict[str, object] = {}
            try:
                response = transport.client.get(
                    proxy_health_url(live_broadcast["base_url"]), timeout=5.0,
                )
                health = response.json()
                broadcast = health.get("show_arc") if isinstance(health, dict) else None
                if isinstance(broadcast, dict):
                    for key in (
                        "active_shows", "active_tokens", "issued_active",
                        "claimed_active", "injected_active", "tombstones",
                        "cancelled", "rejected_receipts", "errors",
                    ):
                        value = broadcast.get(key)
                        if isinstance(value, (bool, int, float)) or value is None:
                            state[key] = value
            except Exception:
                pass
            suffix = (
                f", broadcast_state={json.dumps(state, sort_keys=True)}"
                if state else ""
            )
            raise RuntimeError(f"{exc}{suffix}") from exc
        if status == 200:
            return record, bool(record.get("ok"))
        if status != 202 or time.monotonic() >= deadline:
            raise RuntimeError("live broadcast receipt did not become durable")
        time.sleep(0.05)


def strip_donation_ritual(body: str, opener: str) -> str:
    """의례를 뺀, 모델이 실제로 이어 말한 본문만 남긴다(되먹임 사본 전용)."""
    text = body or ""
    if opener and text.startswith(opener):
        text = text[len(opener):]
    if text.rstrip().endswith(DONATION_ECHO_THANKS):
        text = text.rstrip()[: -len(DONATION_ECHO_THANKS)]
    return text.strip()


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
    live_broadcast: dict[str, str] | None = None,
    tolerate_screened: bool = False,
    replay_transcript: Sequence[dict[str, Any]] | None = None,
    transcript_window_ms: int = TRANSCRIPT_WINDOW_MS,
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
    screened = 0
    # 해제(release) 관측성: 이 arm 이 근거 헤더를 실제로 쓸 때만 기준값을 잡는다.
    last_bypass_total: int | None = None
    if health_url and briefing_evidence == "on":
        last_bypass_total = read_absence_bypasses(transport, health_url)

    if pre_session_seeds:
        # 이전 세션에서 이미 들은 사실로 만든다 — 방송 시작 전에 한 번 오간다.
        for probe in fixture.get("memory_probes", []):
            beat = fixture["topic"]["beats"][0]
            content = f"{ab.USER_PREFIX}{probe['seed_text']}"
            if live_broadcast:
                seed_index = int(probe.get("probe_index", len(transcript)))
                record, _ = run_live_capability_turn(
                    transport, live_broadcast, model=model,
                    messages=[{"role": "user", "content": content}], user_content=content,
                    max_tokens=max_tokens, timeout=timeout,
                    action_id=f"preseed-{seed_index}-{secrets.token_hex(8)}",
                    trace_id=f"{live_broadcast['show_id']}.preseed.{seed_index}.{secrets.token_hex(8)}",
                    turn_type="chat_question",
                )
                if not record.get("ok"):
                    raise RuntimeError("live broadcast pre-session chat failed")
            else:
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
        briefing_text = ""
        carried_evidence = False
        if briefing == "on":
            echo_safe = sim.blank_degenerate_echo(
                answered_picks, FALLBACK_POOL + DEGENERATE_ECHO_PREFIXES)
            briefing_text, carried_evidence = sim.build_turn_briefing_with_evidence(
                fixture, stream, pick, echo_safe)
            # 브리핑은 이 턴이 실제로 받은 회수 재료다. 프록시 결정론 계층이
            # 계약 산문과 구분해 증거 풀에 넣을 수 있도록 프록시가 정의한
            # 마커를 앞에 붙인다(마커 뒤 전체가 증거).
            system_content += "\n\n" + BRIEFING_EVIDENCE_BLOCK_MARKER + "\n" + briefing_text
        signalled = briefing_evidence == "on" and carried_evidence
        set_briefing_evidence_header(transport, signalled)
        user_content = format_user_content(message, author_format)

        deterministic_act = None
        record: dict[str, Any] = {}
        raw = ""
        opener = ""
        donation_opener = ""
        released: bool | None = None
        if acts == "on" and pick["effective_kind"] == "donation":
            # P2-1: 호명·감사 의례는 승인된 결정론 렌더러가 소유하고,
            # 후원의 실제 내용은 모델이 이어 말한다. 의례만 말하고 끝내던 경로는
            # 한국 방송에서 필요한 "감사 → 본답변 → 흐름 복귀"를 만들 수 없었다.
            closer_index = int(message.get("donation_index", 0)) % len(thank_renderer.THANK_CALLOUT_CLOSERS)
            donation_opener = thank_renderer.render_thank_callout_text(message["author"], closer_index)
            deterministic_act = "thank_renderer"
        if acts == "on" and pick.get("aggregate_expected") and openers:
            # P2-2: 여론임을 먼저 결정론으로 짚고, 내용은 모델이 잇는다.
            labels = {wave["tag"]: wave.get("label", wave["tag"])
                      for wave in fixture.get("opinion_waves", [])}
            opener = openers[wave_counter % len(openers)].format(
                주제=labels.get(message.get("tag"), "이"))
            wave_counter += 1
        kept = history[-history_turns:] if history_turns > 0 else []
        turn_system_content = system_content
        if donation_opener:
            turn_system_content += "\n\n" + DONATION_CONTINUATION_CONTRACT
        messages = [] if live_broadcast else [{"role": "system", "content": turn_system_content}]
        for past_user, past_assistant in kept:
            messages.extend(({"role": "user", "content": past_user},
                             {"role": "assistant", "content": past_assistant}))
        own_recent_speech = ""
        if replay_transcript and message.get("offset_ms") is not None:
            # S6 (2026-08-26): replayed chat reacts to what the streamer just
            # said on screen.  Supply that speech as AIRI's own most recent
            # line, paired with a neutral cue, so the reaction has a referent.
            own_recent_speech = transcript_window_text(
                replay_transcript, int(message["offset_ms"]), transcript_window_ms)
            if own_recent_speech:
                messages.extend(({"role": "user", "content": TRANSCRIPT_CUE_USER},
                                 {"role": "assistant", "content": own_recent_speech}))
        messages.append({"role": "user", "content": user_content})

        live_trace_id = None
        live_action_id = None
        live_receipt_bound = False
        if live_broadcast:
            live_action_id = f"turn-{pick['turn_index']}-{secrets.token_hex(8)}"
            live_trace_id = f"{live_broadcast['show_id']}.{pick['turn_index']}.{secrets.token_hex(8)}"
            live_type = live_turn_type(pick)
            try:
                record, live_receipt_bound = run_live_capability_turn(
                    transport, live_broadcast, model=model, messages=messages,
                    user_content=user_content, max_tokens=max_tokens, timeout=timeout,
                    action_id=live_action_id, trace_id=live_trace_id,
                    turn_type=live_type,
                    broadcast_context=live_context_for_turn(
                        fixture, beat, briefing_text, bool(donation_opener),
                    ),
                )
            except LiveInputScreened as exc:
                if not tolerate_screened:
                    raise RuntimeError(
                        f"live turn failed (turn_index={pick['turn_index']}, turn_type={live_type}): {exc}"
                    ) from exc
                # 실제 채팅 재생: 스크리닝 차단은 운영 결과 그 자체다. 답 없이 소비된
                # 턴으로 기록하고 다음 픽업으로 간다.
                screened += 1
                transcript.append({
                    "stage": "screened", "turn_index": pick["turn_index"], "minute": message["minute"],
                    "beat": beat["id"], "kind": pick["effective_kind"], "author": message["author"],
                    "chat": message["text"], "category": exc.category,
                })
                continue
            except RuntimeError as exc:
                journal_state = read_journal_failure_state(transport, health_url) if health_url else {}
                suffix = f", journal_state={json.dumps(journal_state, sort_keys=True)}" if journal_state else ""
                raise RuntimeError(
                    f"live turn failed (turn_index={pick['turn_index']}, turn_type={live_type}{suffix}): {exc}"
                ) from exc
            raw = record.get("response", "") or ""
            if not record.get("ok"):
                raise RuntimeError("live broadcast chat failed")
        else:
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
        if donation_opener:
            body = f"{donation_opener} {body}".strip() if body else donation_opener
        elif opener:
            body = f"{opener} {body}".strip() if body else opener
            deterministic_act = "wave_opener"
        elif guard_fired:
            deterministic_act = "memory_guard"

        fact_tokens = None
        token_pool: set[str] = set()
        if briefing == "on":
            for item in sim.select_viewer_lines(fixture, stream, pick):
                token_pool |= sim._tokens(item["text"])
            # 디렉터가 조립한 브리핑(build_turn_briefing_with_evidence)은 "방금
            # 흐름"·"직전 후원" 줄에서 roster handle을 저자로 직접 이름 붙인다.
            # 그 handle은 이 턴이 실제로 받은 근거인데도 위 select_viewer_lines
            # 만으로는 안 잡혀, 모델이 브리핑이 방금 알려준 이름을 그대로
            # 이어 부르면 invented_handles로 오판됐다 — 판정 입력 범위를 이
            # 턴에 실제로 실렸던 브리핑 본문까지 넓힌다. 게이트 정의는 그대로.
            token_pool |= {handle for handle in roster if handle and handle in briefing_text}
        # 프록시가 AIRI_HANDLE_GROUNDING_GUARD=on 으로 떠 있을 때만 채워지는
        # 신호다. 디렉터의 손수 조립 브리핑은 이미 briefing_fact_tokens로
        # 반영되지만, 라이브 memory 검색이 실제로 회수한 시청자 handle은
        # 디렉터도 모른다 — E2-C1 진단에서 확인된 invented_handle 회귀의
        # 실제 원인. 게이트 정의(무엇이 위반인가)는 그대로 두고, 판정 입력
        # 범위만 이 턴에 실제로 존재했던 근거로 넓힌다.
        memory_grounding_pool = (record.get("handle_grounding") or {}).get("memory_pool") or ""
        if memory_grounding_pool:
            token_pool |= {
                handle for handle in roster if handle and handle in memory_grounding_pool
            }
        if token_pool:
            fact_tokens = sorted(token_pool)
        register = ab.score_response(body)
        row = sim.score_turn(pick, body, beat=beat, fallback_pool=FALLBACK_POOL,
                             roster_handles=roster, drift_terms=drift_terms,
                             service_error_pool=SERVICE_ERROR_POOL,
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
            "live_broadcast_context": bool(live_broadcast),
            "live_action_id": live_action_id,
            "live_trace_id": live_trace_id,
            "live_receipt_bound": live_receipt_bound,
            "own_speech_chars": len(own_recent_speech),
        })
        rows.append(row)
        transcript.append({
            "stage": "turn", "turn_index": pick["turn_index"], "minute": message["minute"],
            "beat": beat["id"], "kind": pick["effective_kind"], "author": message["author"],
            "chat": message["text"], "user_sent": user_content, "airi": body, "raw": raw,
            "own_recent_speech": own_recent_speech,
            "deterministic_act": deterministic_act,
            "backlog_size": pick["backlog_size"], "backlog_ids": pick["backlog_ids"],
        })
        # Task 13 → run 04: 의례는 대화가 아니다. 렌더러 호명을 되먹이면 이후 턴이
        # 그 이름을 재호명했고(Task 9 실측 19턴 중 16건), 감사 문구까지 되먹이자
        # 모델이 뒤이은 질문 23건에 "고마워."로 답했다(사람 평가 run 04). 실제
        # 발화(트랜스크립트·채점)는 그대로 두고, 후원 턴은 히스토리에 아예 넣지
        # 않으며 브리핑 "방금 흐름"에는 모델이 이어 말한 본문만 남긴다.
        if deterministic_act == "thank_renderer" or body.rstrip().endswith(DONATION_ECHO_THANKS):
            answered_picks.append({**pick, "response": strip_donation_ritual(body, donation_opener)})
        else:
            history.append((user_content, body))
            answered_picks.append({**pick, "response": body})

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
    summary["screened_inputs"] = screened
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
                             service_error_pool=SERVICE_ERROR_POOL,
                             briefing_fact_tokens=fact_tokens)
        carried = previous.get(turn_index, {})
        row.update({key: carried[key] for key in
                    ("beat", "backlog_size", "briefing_evidence", "briefing_evidence_released",
                     "polite_violation", "banmal", "ttft_ms", "complete_ms", "failure",
                     "live_broadcast_context", "live_action_id", "live_trace_id", "live_receipt_bound")
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
        elif entry["stage"] == "screened":
            lines += [f"### T{entry['turn_index']:02d} · {entry['minute']}분 · {entry['beat']} · "
                      f"{entry['kind']} · 입력 스크리닝 차단({entry['category']})", "",
                      f"**{entry['author']}**: {entry['chat']}", "", "**AIRI**: (차단 — 응답 없음)", ""]
        else:
            head = (f"### T{entry['turn_index']:02d} · {entry['minute']}분 · {entry['beat']} · "
                    f"{entry['kind']} · 대기 {entry['backlog_size']}건")
            lines += [head, "", f"**{entry['author']}**: {entry['chat']}", "",
                      f"**AIRI**: {entry['airi'] or '(빈 응답)'}", ""]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 실제 채팅 재생 (--replay-chat)
# ---------------------------------------------------------------------------
# 가명화된 실제 시청자 채팅을 템플릿 생성 스트림 대신 흘려보낸다. 스트림의 모양은
# broadcast_sim.generate_stream 이 만드는 것과 바이트 수준으로 같은 계약이어야
# 픽업·브리핑·채점이 손대지 않고 그대로 돈다 — 여기서는 난수도 아키타입 템플릿도
# 쓰지 않고 파일에 적힌 순서와 시각만 따른다.
REPLAY_ARCHETYPE = "replay"
REPLAY_ROW_KEYS = ("source", "video_ref", "offset_ms", "author", "kind", "text")
REPLAY_ROW_KINDS = ("chat", "donation")
# 후원 의례 채점(score_turn 의 addressee_*)이 재생에서도 성립하도록, 후원 행에는
# 픽스처 후원과 같은 모양의 검사를 붙인다.
REPLAY_DONATION_REQUIRED_ANY = ("고마워", "감사")
# 이 금액(원) 미만의 후원은 평범한 채팅으로 받는다 — 의례를 돌리지 않는다. 실제
# 채팅 재생 run 04 에서 치즈 한 건 한 건이 전부 "donation" 으로 들어와 99턴 중
# 35턴이 호명+감사 의례가 됐고, 대부분은 농담을 실은 1,000원짜리였다(사람 평가:
# "템플릿 오발동"). 금액을 읽을 수 없는 라벨도 같은 이유로 소액 취급한다 —
# 의례는 확실히 큰 후원일 때만 나가야 한다.
REPLAY_DONATION_RITUAL_MIN_AMOUNT = 5000
# 물음표 없이도 질문인 한국어 종결. 있는 그대로의 시청자 채팅은 문장부호를 자주
# 뺀다 — 물음표만 보면 대부분의 질문이 reaction 으로 떨어진다.
REPLAY_QUESTION_TAIL_RE = re.compile(
    r"(나요|가요|까요|을까|어때|뭐야|뭐임|뭐냐|왜|어디|언제|누구|몇)\s*[?？]?$"
)
_HANGUL_BASE = 0xAC00
_HANGUL_SYLLABLES = 11_172
_HANGUL_FINAL_RIEUL = 8


def _has_rieul_final(char: str) -> bool:
    """True for a composed Hangul syllable whose final consonant is ㄹ."""
    code = ord(char) - _HANGUL_BASE
    return 0 <= code < _HANGUL_SYLLABLES and code % 28 == _HANGUL_FINAL_RIEUL


def looks_like_question(text: str) -> bool:
    """Conservative question heuristic for a capture that carries no labels."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    if stripped.endswith(("?", "？")):
        return True
    if REPLAY_QUESTION_TAIL_RE.search(stripped) is not None:
        return True
    # "될까/할까" 같은 의문형은 조합형 한글에 자모 "ㄹ까" 로 적히지 않는다 —
    # 앞 음절의 종성을 직접 본다("그러니까" 처럼 종성이 없는 꼴은 제외된다).
    return len(stripped) >= 2 and stripped.endswith("까") and _has_rieul_final(stripped[-2])


def load_transcript_segments(path: Path) -> list[dict[str, Any]]:
    """Read streamer speech segments (absolute VOD ms) produced by local STT."""
    segments: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"transcript row {line_no} is not JSON: {exc}") from exc
            if not isinstance(record, dict) or any(key not in record for key in TRANSCRIPT_ROW_KEYS):
                raise SystemExit(f"transcript row {line_no} must have {TRANSCRIPT_ROW_KEYS}")
            start, end = record["start_ms"], record["end_ms"]
            if type(start) is not int or type(end) is not int or start < 0 or end < start:
                raise SystemExit(f"transcript row {line_no} has invalid start_ms/end_ms")
            text = str(record["text"]).strip()
            if text:
                segments.append({"start_ms": start, "end_ms": end, "text": text})
    segments.sort(key=lambda seg: (seg["end_ms"], seg["start_ms"]))
    return segments


def transcript_window_text(
    segments: Sequence[dict[str, Any]], offset_ms: int, window_ms: int = TRANSCRIPT_WINDOW_MS,
) -> str:
    """Speech that ended within ``window_ms`` before the chat, newest last."""
    chosen = [seg["text"] for seg in segments
              if seg["end_ms"] <= offset_ms and seg["end_ms"] >= offset_ms - window_ms]
    text = " ".join(chosen)
    if len(text) > TRANSCRIPT_MAX_CHARS:
        text = "…" + text[-TRANSCRIPT_MAX_CHARS:]
    return text


def replay_donation_amount(label: object) -> int | None:
    """Chzzk 의 평문 숫자 ``amount_label`` 만 금액으로 읽는다(그 외는 None).

    YouTube 의 "₩5,000" 이나 "5,000원" 처럼 통화·구분자가 섞인 라벨은 캡처마다
    표기가 달라 신뢰할 수 없으므로 파싱하지 않는다.
    """
    text = str(label or "").strip()
    if not text or not text.isascii() or not text.isdigit():
        return None
    return int(text)


def load_replay_rows(
    path: Path,
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
    max_messages: int | None = None,
) -> list[dict[str, Any]]:
    """Read the pseudonymized capture, failing closed on anything malformed.

    The window bounds are read against the *original* offsets, so a cut can be
    described with the timestamps the capture itself carries; rebasing happens
    afterwards in ``build_replay_stream``.
    """
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"replay row {line_no} is not JSON: {exc}") from exc
        if not isinstance(record, dict):
            raise SystemExit(f"replay row {line_no} is not an object")
        missing = [key for key in REPLAY_ROW_KEYS if key not in record]
        if missing:
            raise SystemExit(f"replay row {line_no} is missing {missing}")
        if record["kind"] not in REPLAY_ROW_KINDS:
            raise SystemExit(f"replay row {line_no} has an unknown kind: {record['kind']!r}")
        if type(record["offset_ms"]) is not int or record["offset_ms"] < 0:
            raise SystemExit(f"replay row {line_no} offset_ms must be a non-negative integer")
        if not str(record["author"]).strip() or not str(record["text"]).strip():
            raise SystemExit(f"replay row {line_no} needs both a pseudonym and text")
        rows.append(record)
    # 같은 offset 을 가진 행은 파일에 적힌 순서를 유지한다(안정 정렬).
    rows.sort(key=lambda row: int(row["offset_ms"]))
    if start_ms is not None:
        rows = [row for row in rows if int(row["offset_ms"]) >= start_ms]
    if end_ms is not None:
        rows = [row for row in rows if int(row["offset_ms"]) <= end_ms]
    if max_messages is not None:
        rows = rows[:max_messages]
    if not rows:
        raise SystemExit("replay window contains no messages")
    return rows


def replay_span_minutes(rows: Sequence[dict[str, Any]]) -> int:
    """Broadcast minutes the rebased capture spans — always covering the last row."""
    span_ms = int(rows[-1]["offset_ms"]) - int(rows[0]["offset_ms"])
    minutes = max(1, math.ceil(span_ms / 60_000))
    if span_ms >= minutes * 60_000:
        # 마지막 메시지가 정확히 분 경계에 있으면 plan_pickups 의 마지막 창
        # (t_ms < window_end)이 그 메시지를 보지 못한다 — 한 분을 더 준다.
        minutes += 1
    return minutes


def replay_viewers(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """One roster entry per pseudonym, in first-appearance order."""
    handles: list[str] = []
    seen: set[str] = set()
    for row in rows:
        handle = str(row["author"])
        if handle not in seen:
            seen.add(handle)
            handles.append(handle)
    return [{"handle": handle, "archetype": REPLAY_ARCHETYPE, "weight": 1} for handle in handles]


def build_replay_fixture(
    fixture: dict[str, Any], rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """A copy of the fixture that knows this capture's roster and its real span.

    ``score_turn`` reads the roster to tell a recalled handle from an invented
    one, and a fixture committed to the repository must not carry pseudonyms
    from a real stream — so the roster is assembled here at run time and then
    validated exactly like a fixture read from disk.
    """
    merged = copy.deepcopy(fixture)
    existing = {viewer["handle"] for viewer in merged["viewers"]}
    merged["viewers"] = list(merged["viewers"]) + [
        viewer for viewer in replay_viewers(rows) if viewer["handle"] not in existing
    ]
    minutes = replay_span_minutes(rows)
    if minutes > int(merged["rates"]["broadcast_minutes"]):
        merged["rates"]["broadcast_minutes"] = minutes
        merged["topic"]["beats"][-1]["end_minute"] = minutes
    return sim.validate_fixture(merged)


def build_replay_stream(
    fixture: dict[str, Any],
    rows: Sequence[dict[str, Any]],
    *,
    path: Path,
    seed: int,
) -> dict[str, Any]:
    """Assemble the stream the runner consumes, without generating any chat."""
    base_ms = int(rows[0]["offset_ms"])
    donation_index = 0
    donation_ritual = 0
    donation_small = 0
    messages: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        t_ms = int(row["offset_ms"]) - base_ms
        text = str(row["text"])
        message: dict[str, Any] = {
            "author": str(row["author"]),
            "archetype": REPLAY_ARCHETYPE,
            "kind": "reaction",
            "text": text,
            "minute": t_ms // 60_000,
            "t_ms": t_ms,
            "offset_ms": int(row["offset_ms"]),
            "id": f"m{index:04d}",
        }
        if row["kind"] == "donation":
            label = str(row.get("amount_label") or "")
            amount = replay_donation_amount(label)
            if amount is not None and amount >= REPLAY_DONATION_RITUAL_MIN_AMOUNT:
                message.update({
                    "kind": "donation",
                    "amount_label": label,
                    "checks": {"required_any": list(REPLAY_DONATION_REQUIRED_ANY), "forbidden": []},
                    "donation_index": donation_index,
                })
                donation_index += 1
                donation_ritual += 1
            else:
                # 소액 치즈는 평범한 채팅으로 받되, 팁을 실었다는 사실은 남긴다.
                message.update({"donation_small": True, "amount_label": label})
                if looks_like_question(text):
                    message["kind"] = "question"
                donation_small += 1
        elif looks_like_question(text):
            message["kind"] = "question"
        messages.append(message)
    return {
        "schema_version": sim.STREAM_SCHEMA_VERSION,
        "seed": seed,
        "fixture_sha256": sim.sha256_of(fixture),
        "topic_title": fixture["topic"]["title"],
        "broadcast_minutes": replay_span_minutes(rows),
        "messages": messages,
        # 원문은 리포트에도 저장소에도 남기지 않는다 — 출처·규모·파일 해시만 남긴다.
        "replay": {
            "path_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "message_count": len(messages),
            "source": ",".join(sorted({str(row["source"]) for row in rows})),
            "donation_ritual": donation_ritual,
            "donation_small": donation_small,
        },
    }


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
    parser.add_argument("--replay-chat", type=Path, default=None,
                        help="가명화된 실제 채팅 JSONL 을 템플릿 생성 채팅 대신 재생한다 (--fixture 필수)")
    parser.add_argument("--replay-start-ms", type=int, default=None,
                        help="재생 구간 시작 (원본 offset_ms 기준, 포함)")
    parser.add_argument("--replay-end-ms", type=int, default=None,
                        help="재생 구간 끝 (원본 offset_ms 기준, 포함)")
    parser.add_argument("--replay-transcript", type=Path, default=None,
                        help="스트리머 발화 STT JSONL(start_ms/end_ms/text, VOD 절대 ms). 픽업 직전 구간을 AIRI 자신의 직전 발화로 공급한다 (--replay-chat 필수)")
    parser.add_argument("--replay-transcript-window-ms", type=int, default=TRANSCRIPT_WINDOW_MS,
                        help="픽업 시각 이전 몇 ms의 발화를 공급할지 (기본 45000)")
    parser.add_argument("--replay-max-messages", type=int, default=None,
                        help="재생할 최대 메시지 수 (구간을 자른 뒤 앞에서부터)")
    parser.add_argument("--stream-only", action="store_true", help="모델 호출 없이 스트림/픽업만 낸다")
    parser.add_argument("--rescore", type=Path, help="기존 리포트를 모델 호출 없이 재채점한다")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--live-broadcast-context", choices=("off", "on"), default="off",
                        help="require authenticated production broadcast context capabilities")
    args = parser.parse_args(argv)

    if args.live_broadcast_context == "on" and (
        not os.environ.get(LIVE_CONTEXT_ENV_MASTER)
        or not os.environ.get(LIVE_CONTEXT_ENV_OBSERVER)
    ):
        raise SystemExit("live broadcast context requires configured capability tokens")
    if args.live_broadcast_context == "on" and (args.stream_only or args.rescore):
        raise SystemExit("live broadcast context requires scored live chat turns")
    if args.replay_chat and (args.stream_only or args.rescore):
        # 재생은 사람이 읽을 응답을 얻으려고 도는 것이고, 재채점은 결정론 스트림을
        # seed 로 되살리는 경로다 — 둘은 같은 실행에서 성립하지 않는다.
        raise SystemExit("replay chat requires a scored run (not --stream-only/--rescore)")
    if args.replay_chat and not args.fixture:
        raise SystemExit("replay chat requires an explicit --fixture")

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
    replay_transcript: list[dict[str, Any]] | None = None
    if args.replay_transcript is not None and not args.replay_chat:
        raise SystemExit("--replay-transcript requires --replay-chat")
    if args.replay_chat:
        replay_rows = load_replay_rows(
            args.replay_chat, start_ms=args.replay_start_ms, end_ms=args.replay_end_ms,
            max_messages=args.replay_max_messages,
        )
        fixture = build_replay_fixture(fixture, replay_rows)
        stream = build_replay_stream(fixture, replay_rows, path=args.replay_chat, seed=args.seed)
        if args.replay_transcript is not None:
            replay_transcript = load_transcript_segments(args.replay_transcript)
            stream["replay_transcript"] = {
                "path_sha256": hashlib.sha256(args.replay_transcript.read_bytes()).hexdigest(),
                "segments": len(replay_transcript),
                "window_ms": int(args.replay_transcript_window_ms),
            }
    else:
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

    # A production live-broadcast measurement must exercise the SSE path that
    # carries the response-specific ACK attestation.  Auto fallback to a
    # buffered request would change both TTFT semantics and receipt framing,
    # so fail closed on a streaming error instead of silently changing modes.
    transport = ab.HttpTransport(
        args.base_url,
        args.token,
        stream_mode="on" if args.live_broadcast_context == "on" else "auto",
    )
    session_id = args.session_id or f"broadcast-sim-{args.memory_arm}-{args.seed}"
    transport.client.headers[SESSION_HEADER] = session_id
    live_broadcast: dict[str, str] | None = None
    live_contract_verified: bool | None = None
    primary_error: BaseException | None = None
    model_digest: str | None = None
    try:
        if args.live_broadcast_context == "on":
            # Read capability secrets only at the invocation boundary.  They are
            # deliberately excluded from reports, transcripts, and diagnostics.
            master_token = os.environ[LIVE_CONTEXT_ENV_MASTER]
            observer_token = os.environ[LIVE_CONTEXT_ENV_OBSERVER]
            live_contract_verified = verify_live_contract(
                transport, proxy_health_url(args.base_url), args.contract,
            )
            if args.memory_arm == "seeded":
                # Memory seeds must persist in the same session, but must not
                # consume affect/turn state from the scored show.
                preseed_show_id = f"broadcast-sim-preseed-{args.seed}-{secrets.token_hex(8)}"
                preseed_broadcast = {
                    "base_url": args.base_url, "master_token": master_token,
                    "observer_token": observer_token, "show_id": preseed_show_id,
                }
                _broadcast_control(
                    transport, args.base_url, master_token,
                    {"action": "start", "show_id": preseed_show_id},
                )
                preseed_error: BaseException | None = None
                try:
                    # Empty picks make this an isolated, receipt-bound memory
                    # setup pass. The shared client preserves x-airi-session-id.
                    run_arm(
                        transport, fixture, stream, (),
                        model=args.model, contract=args.contract, protocol=args.protocol,
                        author_format=args.author_format, history_turns=args.history_turns,
                        max_tokens=args.max_tokens, timeout=args.timeout,
                        pre_session_seeds=True, briefing=args.briefing, acts=args.acts,
                        briefing_evidence=args.briefing_evidence,
                        health_url=proxy_health_url(args.base_url),
                        live_broadcast=preseed_broadcast,
                    )
                except BaseException as exc:
                    preseed_error = exc
                    raise
                finally:
                    try:
                        _broadcast_control(
                            transport, args.base_url, master_token,
                            {"action": "close", "show_id": preseed_show_id},
                        )
                    except Exception:
                        if preseed_error is None:
                            raise
            show_id = f"broadcast-sim-{args.seed}-{secrets.token_hex(8)}"
            _broadcast_control(
                transport, args.base_url, master_token,
                {"action": "start", "show_id": show_id},
            )
            live_broadcast = {
                "base_url": args.base_url, "master_token": master_token,
                "observer_token": observer_token, "show_id": show_id,
            }
        result = run_arm(
            transport, fixture, stream, picks,
            model=args.model, contract=args.contract, protocol=args.protocol,
            author_format=args.author_format, history_turns=args.history_turns,
            max_tokens=args.max_tokens, timeout=args.timeout,
            pre_session_seeds=args.memory_arm == "seeded" and live_broadcast is None,
            briefing=args.briefing,
            acts=args.acts,
            briefing_evidence=args.briefing_evidence,
            health_url=proxy_health_url(args.base_url),
            live_broadcast=live_broadcast,
            tolerate_screened=bool(args.replay_chat),
            replay_transcript=replay_transcript,
            transcript_window_ms=int(args.replay_transcript_window_ms),
        )
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        try:
            if live_broadcast is not None:
                try:
                    _broadcast_control(
                        transport, live_broadcast["base_url"], live_broadcast["master_token"],
                        {"action": "close", "show_id": live_broadcast["show_id"]},
                    )
                except Exception:
                    # Preserve the causal model/control error, but never turn a
                    # successful run into a report when its show could not close.
                    if primary_error is None:
                        raise
        finally:
            if primary_error is None:
                # R2 F6: bind the report to the model the proxy actually served.
                model_digest = read_model_digest(transport, proxy_health_url(args.base_url))
            transport.close()

    payload = {
        "schema_version": sim.REPORT_SCHEMA_VERSION,
        "topic_title": stream["topic_title"],
        "model": args.model,
        "model_digest": model_digest,
        "max_tokens": args.max_tokens,
        "memory_arm": args.memory_arm,
        "briefing": args.briefing,
        "acts": args.acts,
        "briefing_evidence": args.briefing_evidence,
        "live_broadcast_context": args.live_broadcast_context,
        "live_contract_verified": live_contract_verified,
        "live_contract_mode": args.contract if live_contract_verified is not None else None,
        "live_arc_lifecycle_tested": False,
        "live_arc_lifecycle_note": "long campaign owns callback_hit/miss coverage",
        "session_id": session_id,
        "contract": args.contract,
        "contract_version": BROADCAST_CONTRACT_VERSION if args.contract == "on" else None,
        "protocol": args.protocol,
        "author_format": args.author_format,
        "seed": args.seed,
        "fixture_sha256": stream["fixture_sha256"],
        "stream_messages": len(stream["messages"]),
        "replay": stream.get("replay"),
        "replay_transcript": stream.get("replay_transcript"),
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
