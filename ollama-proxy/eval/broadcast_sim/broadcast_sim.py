"""Deterministic first-broadcast chat stream and the pickup rules that consume it.

The point of this module is that everything a network run would make unrepeatable
lives here instead: who is in chat, when they type, which message AIRI reaches for
in a given five-second window, and how the resulting reply is scored. A seed and
the pinned fixture reproduce a byte-identical stream, so two memory arms differ
only in the proxy behaviour under test.

Timing is virtual. One "second" here is a position in the stream, not wall clock,
so a CPU-speed model does not change which messages were available to pick.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any, Iterable, Sequence


HERE = Path(__file__).resolve().parent
FIXTURE_PATH = HERE / "first_broadcast_v1.json"
FIXTURE_SCHEMA_VERSION = "airi.broadcast-sim-fixture.v1"
STREAM_SCHEMA_VERSION = "airi.broadcast-sim-stream.v1"
REPORT_SCHEMA_VERSION = "airi.broadcast-sim-report.v1"
MEMORY_ARMS = ("off", "on", "seeded")
KINDS = (
    "donation", "continuity_callback", "continuity_seed", "memory_seed",
    "memory_probe", "opinion", "question", "reaction", "offtopic",
)


class BroadcastSimError(ValueError):
    """Fail-closed error for a malformed fixture or stream."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_of(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------
def validate_fixture(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != FIXTURE_SCHEMA_VERSION:
        raise BroadcastSimError("unexpected fixture schema")
    if value.get("synthetic_only") is not True:
        raise BroadcastSimError("fixture must be marked synthetic_only")
    viewers = value.get("viewers")
    if not isinstance(viewers, list) or len(viewers) < 2:
        raise BroadcastSimError("fixture needs a viewer roster")
    handles = [viewer["handle"] for viewer in viewers]
    if len(set(handles)) != len(handles):
        raise BroadcastSimError("duplicate viewer handle")
    archetypes = value.get("archetypes") or {}
    unknown = {viewer["archetype"] for viewer in viewers} - set(archetypes)
    if unknown:
        raise BroadcastSimError(f"viewer references unknown archetype: {sorted(unknown)}")
    for name, archetype in archetypes.items():
        if archetype.get("kind") not in KINDS or not archetype.get("templates"):
            raise BroadcastSimError(f"archetype {name} is malformed")
    beats = (value.get("topic") or {}).get("beats") or []
    if not beats or beats[0]["start_minute"] != 0:
        raise BroadcastSimError("topic beats must start at minute 0")
    for earlier, later in zip(beats, beats[1:]):
        if earlier["end_minute"] != later["start_minute"]:
            raise BroadcastSimError("topic beats must be contiguous")
    rates = value.get("rates") or {}
    required = ("broadcast_minutes", "window_seconds", "turn_cooldown_seconds", "messages_per_minute_min",
                "messages_per_minute_max", "active_viewers_min", "active_viewers_max",
                "opinion_aggregate_threshold", "pending_stale_seconds")
    missing = [key for key in required if key not in rates]
    if missing:
        raise BroadcastSimError(f"rates table is missing: {missing}")
    if beats[-1]["end_minute"] != rates["broadcast_minutes"]:
        raise BroadcastSimError("beats must cover the whole broadcast")
    if rates["messages_per_minute_min"] > rates["messages_per_minute_max"]:
        raise BroadcastSimError("message rate bounds are inverted")
    if list(value.get("pickup_priority") or []) and not set(value["pickup_priority"]) <= set(KINDS):
        raise BroadcastSimError("pickup_priority names an unknown kind")
    arcs = value.get("continuity_arcs") or []
    if not isinstance(arcs, list):
        raise BroadcastSimError("continuity_arcs must be a list")
    arc_ids: set[str] = set()
    handle_set = set(handles)
    for arc in arcs:
        if not isinstance(arc, dict):
            raise BroadcastSimError("continuity arc must be an object")
        arc_id = arc.get("id")
        if not isinstance(arc_id, str) or not re.fullmatch(r"arc-[a-z0-9-]+", arc_id):
            raise BroadcastSimError("continuity arc id is malformed")
        if arc_id in arc_ids:
            raise BroadcastSimError(f"duplicate continuity arc id: {arc_id}")
        arc_ids.add(arc_id)
        if arc.get("author") not in handle_set:
            raise BroadcastSimError(f"continuity arc {arc_id} references an unknown author")
        seed_minute = arc.get("seed_minute")
        callback_minute = arc.get("callback_minute")
        if not isinstance(seed_minute, int) or not isinstance(callback_minute, int):
            raise BroadcastSimError(f"continuity arc {arc_id} minutes must be integers")
        if not 0 <= seed_minute < callback_minute < int(rates["broadcast_minutes"]):
            raise BroadcastSimError(f"continuity arc {arc_id} minute order is invalid")
        if not str(arc.get("seed_text", "")).strip() or not str(arc.get("callback_text", "")).strip():
            raise BroadcastSimError(f"continuity arc {arc_id} needs seed and callback text")
        expected_source = arc.get("expected_source")
        if expected_source not in {"history", "briefing", "durable_memory", "show_arc"}:
            raise BroadcastSimError(f"continuity arc {arc_id} expected_source is invalid")
        if arc.get("event_type") not in {
            "donation", "subscription", "selected_chat", "batched_chat",
            "game", "watchalong", "correction", "tease", "topic_transition",
        }:
            raise BroadcastSimError(f"continuity arc {arc_id} event_type is invalid")
        for phase in ("seed_checks", "callback_checks"):
            checks = arc.get(phase)
            if not isinstance(checks, dict) or not checks.get("required_any"):
                raise BroadcastSimError(f"continuity arc {arc_id} {phase} needs required_any")
            if not all(isinstance(pattern, str) and pattern for pattern in checks["required_any"]):
                raise BroadcastSimError(f"continuity arc {arc_id} {phase} patterns are malformed")
            forbidden = checks.get("forbidden", [])
            if not isinstance(forbidden, list) or not all(
                isinstance(pattern, str) and pattern for pattern in forbidden
            ):
                raise BroadcastSimError(f"continuity arc {arc_id} {phase} forbidden is malformed")
    return value


def load_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    return validate_fixture(json.loads(path.read_text(encoding="utf-8")))


def beat_at(fixture: dict[str, Any], minute: int) -> dict[str, Any]:
    for beat in fixture["topic"]["beats"]:
        if beat["start_minute"] <= minute < beat["end_minute"]:
            return beat
    return fixture["topic"]["beats"][-1]


# ---------------------------------------------------------------------------
# 스트림 생성
# ---------------------------------------------------------------------------
def _weighted_sample(rng: random.Random, viewers: Sequence[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    """Sample without replacement, favouring the chattier handles."""
    pool = list(viewers)
    chosen: list[dict[str, Any]] = []
    for _ in range(min(count, len(pool))):
        weights = [max(1, int(viewer.get("weight", 1))) for viewer in pool]
        pick = rng.choices(range(len(pool)), weights=weights, k=1)[0]
        chosen.append(pool.pop(pick))
    return chosen


def generate_stream(fixture: dict[str, Any], seed: int = 20260818) -> dict[str, Any]:
    """Build the whole broadcast's chat as one ordered, timestamped list."""
    rng = random.Random(seed)
    rates = fixture["rates"]
    viewers = fixture["viewers"]
    minutes = int(rates["broadcast_minutes"])
    burst_minutes = set(rates.get("burst_minutes") or [])
    donation_by_minute = {int(item["minute"]): item for item in fixture.get("donations", [])}
    waves_by_minute = {int(item["minute"]): item for item in fixture.get("opinion_waves", [])}
    probes = list(fixture.get("memory_probes", []))
    seeds_by_minute: dict[int, list[dict[str, Any]]] = {}
    probes_by_minute: dict[int, list[dict[str, Any]]] = {}
    probe_authors = _weighted_sample(
        rng, [viewer for viewer in viewers if viewer["archetype"] == "deep_follower"], len(probes)
    ) or _weighted_sample(rng, viewers, len(probes))
    for index, probe in enumerate(probes):
        author = probe_authors[index % len(probe_authors)]["handle"]
        seeds_by_minute.setdefault(int(probe["seed_minute"]), []).append({**probe, "author": author, "index": index})
        probes_by_minute.setdefault(int(probe["minute"]), []).append({**probe, "author": author, "index": index})
    arc_seeds_by_minute: dict[int, list[dict[str, Any]]] = {}
    arc_callbacks_by_minute: dict[int, list[dict[str, Any]]] = {}
    for arc in fixture.get("continuity_arcs", []):
        gap_minutes = int(arc["callback_minute"]) - int(arc["seed_minute"])
        shared = {
            "author": arc["author"],
            "arc_id": arc["id"],
            "arc_event_type": arc["event_type"],
            "arc_gap_minutes": gap_minutes,
            "arc_expected_source": arc["expected_source"],
        }
        arc_seeds_by_minute.setdefault(int(arc["seed_minute"]), []).append({
            **shared, "text": arc["seed_text"], "checks": arc["seed_checks"],
        })
        arc_callbacks_by_minute.setdefault(int(arc["callback_minute"]), []).append({
            **shared, "text": arc["callback_text"], "checks": arc["callback_checks"],
        })

    active = _weighted_sample(rng, viewers, rng.randint(int(rates["active_viewers_min"]), int(rates["active_viewers_max"])))
    messages: list[dict[str, Any]] = []
    donation_index = 0

    for minute in range(minutes):
        churn = int(rates.get("active_churn_per_minute", 0))
        for _ in range(churn):
            if len(active) > int(rates["active_viewers_min"]):
                active.pop(rng.randrange(len(active)))
            candidates = [viewer for viewer in viewers if viewer not in active]
            if candidates and len(active) < int(rates["active_viewers_max"]):
                active.append(_weighted_sample(rng, candidates, 1)[0])

        planned: list[dict[str, Any]] = []
        if minute in donation_by_minute:
            donation = donation_by_minute[minute]
            author = _weighted_sample(rng, active, 1)[0]
            planned.append({
                "author": author["handle"], "archetype": author["archetype"], "kind": "donation",
                "text": donation["message"], "amount_label": donation.get("amount_label", ""),
                "checks": donation.get("checks", {}), "donation_index": donation_index,
            })
            donation_index += 1
        for entry in seeds_by_minute.get(minute, []):
            planned.append({"author": entry["author"], "archetype": "deep_follower", "kind": "memory_seed",
                            "text": entry["seed_text"], "probe_index": entry["index"]})
        for entry in probes_by_minute.get(minute, []):
            planned.append({"author": entry["author"], "archetype": "deep_follower", "kind": "memory_probe",
                            "text": entry["probe_text"], "expect_any": list(entry["expect_any"]),
                            "probe_index": entry["index"]})
        for entry in arc_seeds_by_minute.get(minute, []):
            planned.append({**entry, "archetype": "continuity", "kind": "continuity_seed",
                            "arc_phase": "seed"})
        for entry in arc_callbacks_by_minute.get(minute, []):
            planned.append({**entry, "archetype": "continuity", "kind": "continuity_callback",
                            "arc_phase": "callback"})
        if minute in waves_by_minute:
            wave = waves_by_minute[minute]
            size = min(int(rates.get("opinion_wave_size", 3)), len(active))
            for offset, author in enumerate(_weighted_sample(rng, active, size)):
                planned.append({"author": author["handle"], "archetype": author["archetype"], "kind": "opinion",
                                "text": wave["templates"][offset % len(wave["templates"])], "tag": wave["tag"],
                                "aggregate_markers": list(wave.get("aggregate_markers", []))})

        base = rng.randint(int(rates["messages_per_minute_min"]), int(rates["messages_per_minute_max"]))
        if minute in burst_minutes:
            base *= int(rates.get("burst_multiplier", 1))
        for _ in range(max(0, base - len(planned))):
            author = _weighted_sample(rng, active, 1)[0]
            archetype = fixture["archetypes"][author["archetype"]]
            kind = archetype["kind"]
            templates = archetype["templates"]
            if kind != "offtopic" and rng.random() < float(rates.get("offtopic_ratio", 0.0)):
                kind, templates = "offtopic", fixture["archetypes"]["offtopic_chatter"]["templates"]
            planned.append({"author": author["handle"], "archetype": author["archetype"], "kind": kind,
                            "text": templates[rng.randrange(len(templates))]})

        rng.shuffle(planned)
        # 후원·기억 프로브는 분 안에서 앞쪽에 두어 픽업 창을 확보한다.
        planned.sort(key=lambda item: 0 if item["kind"] in (
            "donation", "memory_probe", "continuity_seed", "continuity_callback",
        ) else 1)
        span = 60_000 // max(1, len(planned))
        for position, item in enumerate(planned):
            offset = position * span + rng.randrange(0, max(1, span // 2))
            messages.append({**item, "minute": minute, "t_ms": minute * 60_000 + offset})

    messages.sort(key=lambda item: item["t_ms"])
    for index, message in enumerate(messages):
        message["id"] = f"m{index:04d}"
    return {
        "schema_version": STREAM_SCHEMA_VERSION,
        "seed": seed,
        "fixture_sha256": sha256_of(fixture),
        "topic_title": fixture["topic"]["title"],
        "broadcast_minutes": minutes,
        "messages": messages,
    }


# ---------------------------------------------------------------------------
# 픽업
# ---------------------------------------------------------------------------
def effective_kind(message: dict[str, Any], pending: Sequence[dict[str, Any]], threshold: int) -> str:
    """A lone wave message is just a question; a wave is only a wave in numbers."""
    if message["kind"] != "opinion":
        return message["kind"]
    same = sum(1 for other in pending if other.get("tag") and other["tag"] == message.get("tag"))
    return "opinion" if same >= threshold else "question"


def choose_pickup(pending: Sequence[dict[str, Any]], priority: Sequence[str], threshold: int) -> dict[str, Any] | None:
    """Highest-priority kind wins; within a kind the oldest message wins."""
    if not pending:
        return None
    ranked = {kind: index for index, kind in enumerate(priority)}
    best: tuple[int, int, dict[str, Any]] | None = None
    for message in pending:
        kind = effective_kind(message, pending, threshold)
        rank = ranked.get(kind, len(ranked))
        key = (rank, message["t_ms"])
        if best is None or key < (best[0], best[1]):
            best = (rank, message["t_ms"], message)
    return best[2] if best else None


def plan_pickups(stream: dict[str, Any], fixture: dict[str, Any], *, max_turns: int | None = None) -> list[dict[str, Any]]:
    """Walk the stream in fixed windows and decide what AIRI reads out, and when.

    A turn occupies the stream for ``turn_cooldown_seconds`` of virtual time, which
    is what creates a real backlog: messages keep arriving while AIRI is talking.
    """
    rates = fixture["rates"]
    window_ms = int(rates["window_seconds"]) * 1000
    cooldown_ms = int(rates["turn_cooldown_seconds"]) * 1000
    stale_ms = int(rates["pending_stale_seconds"]) * 1000
    threshold = int(rates["opinion_aggregate_threshold"])
    priority = list(fixture.get("pickup_priority") or KINDS)
    total_ms = int(stream["broadcast_minutes"]) * 60_000

    messages = list(stream["messages"])
    cursor = 0
    pending: list[dict[str, Any]] = []
    picks: list[dict[str, Any]] = []
    busy_until = 0
    dropped_stale = 0

    for window_start in range(0, total_ms, window_ms):
        window_end = window_start + window_ms
        while cursor < len(messages) and messages[cursor]["t_ms"] < window_end:
            pending.append(messages[cursor])
            cursor += 1
        fresh = [item for item in pending if window_end - item["t_ms"] <= stale_ms]
        dropped_stale += len(pending) - len(fresh)
        pending = fresh
        if window_start < busy_until or not pending:
            continue
        chosen = choose_pickup(pending, priority, threshold)
        if chosen is None:
            continue
        kind = effective_kind(chosen, pending, threshold)
        backlog = [item for item in pending if item["id"] != chosen["id"]]
        wave_size = sum(1 for item in pending if chosen.get("tag") and item.get("tag") == chosen.get("tag"))
        picks.append({
            "turn_index": len(picks) + 1,
            "window_start_ms": window_start,
            "message": chosen,
            "effective_kind": kind,
            "backlog_size": len(backlog),
            "backlog_ids": [item["id"] for item in backlog],
            "wave_size": wave_size,
            "aggregate_expected": kind == "opinion",
        })
        pending = backlog
        busy_until = window_end + cooldown_ms
        if max_turns is not None and len(picks) >= max_turns:
            break
    for pick in picks:
        pick["dropped_stale_total"] = dropped_stale
    return picks


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[0-9a-z가-힣]+", (text or "").lower()) if len(token) >= 2}


# 승인된 집계 오프너 풀(2026-08-19)의 표지어 "많네"·"몰리"를 포함한다.
AGGREGATE_MARKERS = ("다들", "여러", "많이", "다 같이", "모두", "전부", "너희", "여기저기", "많네", "몰리")


# 한국어 조사·어미 굴절("별명"↔"별명은", "새벽두시야"↔"새벽두시였지") 때문에
# 완전일치는 관련 발언을 놓친다 — journal recall bm25 수리와 같은 교훈.
# 공통 접두가 2자 이상이고 짧은 쪽의 6할 이상이면 같은 어간으로 본다.
_TOKEN_MATCH_MIN_PREFIX = 2
_TOKEN_MATCH_RATIO = 0.6


def _token_match(left: str, right: str) -> bool:
    prefix = 0
    for a, b in zip(left, right):
        if a != b:
            break
        prefix += 1
    return prefix >= _TOKEN_MATCH_MIN_PREFIX and prefix >= _TOKEN_MATCH_RATIO * min(len(left), len(right))


def _matching_tokens(candidates: set[str], references: set[str]) -> set[str]:
    return {token for token in candidates
            if any(_token_match(token, reference) for reference in references)}


def select_viewer_lines(
    fixture: dict[str, Any],
    stream: dict[str, Any],
    pick: dict[str, Any],
) -> list[dict[str, Any]]:
    """Pick this viewer's earlier lines for the briefing — relevance before recency.

    Recency alone loses the one line that matters (measured on T21: the planted
    fact was pushed out by two later "아까 그 얘기 더 해줘"). Lines sharing a
    token with the current message fill the budget first — the deterministic
    twin of journal recall's relevance-first principle — and any remaining slots
    take the newest lines.
    """
    return [item for item, _relevant in select_viewer_lines_tagged(fixture, stream, pick)]


def select_viewer_lines_tagged(
    fixture: dict[str, Any],
    stream: dict[str, Any],
    pick: dict[str, Any],
) -> list[tuple[dict[str, Any], bool]]:
    """Like ``select_viewer_lines`` but marks which lines matched by relevance."""
    config = fixture.get("briefing") or {}
    budget = int(config.get("max_viewer_lines", 2))
    message = pick["message"]
    earlier = [item for item in stream["messages"]
               if item["author"] == message["author"] and item["t_ms"] < message["t_ms"]]
    probe_tokens = _tokens(message["text"])
    relevant = [item for item in earlier
                if _matching_tokens(_tokens(item["text"]), probe_tokens)][-budget:]
    chosen = list(relevant)
    for item in reversed(earlier):
        if len(chosen) >= budget:
            break
        if item not in chosen:
            chosen.append(item)
    marked = {id(item) for item in relevant}
    return [(item, id(item) in marked)
            for item in sorted(chosen, key=lambda entry: entry["t_ms"])]


def blank_degenerate_echo(
    prior_picks: Sequence[dict[str, Any]],
    block_prefixes: Sequence[str],
) -> list[dict[str, Any]]:
    """Blank responses that must never be echoed back into a briefing.

    The eight-character floor misses fixed fallback lines like "아직 기록이
    없어." (11 chars), and echoing those teaches the model the very pattern
    the briefing exists to break (measured on T35). The caller supplies the
    deterministic families it knows about — the silence pool, the memory
    guard line, the absence fallbacks.
    """
    prefixes = tuple(prefix for prefix in block_prefixes if prefix)
    sanitized = []
    for prior in prior_picks:
        response = (prior.get("response") or "").strip()
        if response.startswith(prefixes):
            prior = {**prior, "response": ""}
        sanitized.append(prior)
    return sanitized


def build_turn_briefing(
    fixture: dict[str, Any],
    stream: dict[str, Any],
    pick: dict[str, Any],
    prior_picks: Sequence[dict[str, Any]],
) -> str:
    """Assemble the show-runner briefing for one turn — deterministic, zero LLM calls.

    Everything here is information the director already holds at pickup time:
    what this viewer said earlier in the broadcast, what AIRI just answered,
    how the backlog leans, and any donation still in the air. This is the P1
    counterpart of the seeded-arm measurement: the model talks when its context
    holds material, so the director's job is to put material there every turn.
    """
    return build_turn_briefing_with_evidence(fixture, stream, pick, prior_picks)[0]


def build_turn_briefing_with_evidence(
    fixture: dict[str, Any],
    stream: dict[str, Any],
    pick: dict[str, Any],
    prior_picks: Sequence[dict[str, Any]],
) -> tuple[str, bool]:
    """Like ``build_turn_briefing`` but also reports whether it carried recall.

    "Recall material" means a line from this viewer's earlier history that is
    actually *relevant* to the current message (the same relevance tag
    ``select_viewer_lines_tagged`` computes for the directive-vs-memo wording
    choice above) — not just any earlier line this viewer happened to say.
    Narrowed 2026-08-20 (Task 1 review Minor 1): the proxy's own absence-gate
    precedent only treats a *memory-shaped* utterance in history as evidence
    (``MEMORY_QUERY_RE`` against the request history), so "this viewer said
    literally anything before" was a broader bar than the signal it mirrors —
    a recency-filled filler line (no token overlap with the current message)
    must not count. This is a director-side narrowing only; the proxy's
    ``X-AIRI-Briefing-Evidence`` header contract is unchanged (still a bare
    token check).

    The flag is returned from the point that already knows the answer; reading
    it back out of the finished string would silently break on any wording
    change.
    """
    config = fixture.get("briefing") or {}
    max_viewer_lines = int(config.get("max_viewer_lines", 2))
    max_recent_picks = int(config.get("max_recent_picks", 2))
    max_line_chars = int(config.get("max_line_chars", 40))
    donation_window_ms = int(config.get("recent_donation_window_ms", 120_000))
    min_echo_chars = int(config.get("min_echo_response_chars", 8))

    message = pick["message"]
    clip = lambda text: text if len(text) <= max_line_chars else text[: max_line_chars - 1] + "…"
    lines = ["[턴 브리핑 — 방송 스태프가 주는 메모야. 자연스럽게 참고만 해.]"]

    earlier = [item for item in stream["messages"]
               if item["author"] == message["author"] and item["t_ms"] < message["t_ms"]]
    lines.append(f"- 지금 말한 시청자: {message['author']}"
                 + (f" (이번 방송 {len(earlier) + 1}번째 발언)" if earlier else " (첫 발언)"))
    directive = config.get(
        "relevant_line_directive",
        "- 이 시청자가 아까 \"{line}\"라고 했어. 지금 그 얘기를 묻는 거니까 그 내용을 그대로 써서 답해.",
    )
    viewer_lines = select_viewer_lines_tagged(fixture, stream, pick)
    for item, relevant in viewer_lines:
        if relevant:
            # 수동 메모("아까 한 말")는 7%밖에 안 쓰였다 — 관련 줄은 무엇을
            # 하라는 지시형으로 바꿔 활용을 직접 요구한다(P1 마지막 지렛대).
            lines.append(directive.format(line=clip(item["text"])))
        else:
            lines.append(f"- 이 시청자가 아까 한 말: \"{clip(item['text'])}\"")

    for prior in list(prior_picks)[-max_recent_picks:]:
        prior_message = prior["message"]
        response = (prior.get("response") or "").strip()
        flow = f"- 방금 흐름: {prior_message['author']} \"{clip(prior_message['text'])}\""
        # 짧은 저품질 응답을 되먹이면 모델이 그 문형을 따라 한다(T35 실측 —
        # "아직 기록 없어" 전염).  내용이 있는 응답만 에코한다.
        if len(response) >= min_echo_chars:
            flow += f" → 나: \"{clip(response)}\""
        lines.append(flow)

    backlog_ids = set(pick.get("backlog_ids") or [])
    if backlog_ids:
        by_id = {item["id"]: item for item in stream["messages"]}
        tags: dict[str, int] = {}
        for backlog_id in backlog_ids:
            tag = by_id.get(backlog_id, {}).get("tag")
            if tag:
                tags[tag] = tags.get(tag, 0) + 1
        labels = {wave["tag"]: wave.get("label", wave["tag"]) for wave in fixture.get("opinion_waves", [])}
        wave_note = "".join(f", {labels.get(tag, tag)} 요청 {count}건" for tag, count in sorted(tags.items()))
        lines.append(f"- 대기 채팅 {len(backlog_ids)}건{wave_note}")

    for prior in reversed(list(prior_picks)):
        prior_message = prior["message"]
        if prior_message["kind"] == "donation" and message["t_ms"] - prior_message["t_ms"] <= donation_window_ms:
            lines.append(f"- 직전 후원: {prior_message['author']} \"{clip(prior_message['text'])}\"")
            break
    narrow_evidence = any(relevant for _item, relevant in viewer_lines)
    return "\n".join(lines), narrow_evidence


def offtopic_terms(fixture: dict[str, Any]) -> set[str]:
    """Words that only ever appear in the off-topic template pool."""
    chatter = fixture["archetypes"]["offtopic_chatter"]["templates"]
    on_topic = set()
    for name, archetype in fixture["archetypes"].items():
        if name == "offtopic_chatter":
            continue
        for template in archetype["templates"]:
            on_topic |= _tokens(template)
    for beat in fixture["topic"]["beats"]:
        on_topic |= _tokens(" ".join(beat.get("anchors", [])))
    terms: set[str] = set()
    for template in chatter:
        terms |= _tokens(template)
    return terms - on_topic


def score_turn(
    pick: dict[str, Any],
    body: str,
    *,
    beat: dict[str, Any],
    fallback_pool: Sequence[str],
    roster_handles: Sequence[str],
    service_error_pool: Sequence[str] = (),
    drift_terms: Sequence[str] = (),
    briefing_fact_tokens: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Score one reply against the message it answered. Lexical and conservative.

    Every check here can be wrong in both directions — a topical reply that shares
    no tokens reads as drift, and a name that merely looks like a handle reads as a
    callout. These are review aids, not verdicts.
    """
    message = pick["message"]
    text = (body or "").strip()
    anchors = list(beat.get("anchors", []))
    shared = _tokens(text) & _tokens(message["text"])
    row: dict[str, Any] = {
        "turn_index": pick["turn_index"],
        "message_id": message["id"],
        "kind": pick["effective_kind"],
        "author": message["author"],
        "chars": len(text),
        "empty": not text,
        "is_fallback": text in set(fallback_pool),
        # A pipeline failure is not a silence fallback.  `fallback_pool` holds
        # only the proxy's deliberate "let me think" lines, so three blind
        # rounds reported `fallback` 0/108 while a third of every arm's turns
        # were actually the proxy's error dialogue.  Count it separately: an
        # error turn cannot be scored for anything, and a metric whose
        # denominator is mostly errors is not a measurement.
        "service_error": text in set(service_error_pool),
        "anchor_hit": [anchor for anchor in anchors if anchor in text],
        "shared_tokens": sorted(shared),
        # 두 축을 따로 본다. `topic_anchored` 는 "방송 주제에 붙어 있나"라는
        # 엄격한 신호라 "응원할게"→"고마워!" 같은 정상 반응도 False 가 된다.
        # `drift` 는 입력에 없던 딴소리 어휘를 스스로 꺼냈을 때만 True 다.
        "topic_anchored": bool(shared) or any(anchor in text for anchor in anchors),
        "drift": sorted((_tokens(text) & set(drift_terms)) - _tokens(message["text"])),
    }
    # P1-3 시청자 사실 활용: 브리핑이 준 과거 발언의 고유 토큰(지금 채팅에는
    # 없는 것)을 응답이 실제로 집어 썼는가.  브리핑이 줄 게 없던 턴은 None.
    if briefing_fact_tokens is None:
        row["fact_usage"] = None
    else:
        message_tokens = _tokens(message["text"])
        fact_tokens = {token for token in briefing_fact_tokens
                       if not _matching_tokens({token}, message_tokens)}
        used = _matching_tokens(_tokens(text), fact_tokens)
        row["fact_usage"] = bool(used) if fact_tokens else None
        row["fact_tokens_used"] = sorted(used)

    called = [handle for handle in roster_handles if handle and handle in text]
    row["called_handles"] = called
    row["callout_count"] = sum(text.count(handle) for handle in called)
    # 입력에도 브리핑 근거에도 없던 시청자 이름을 부르면 발명이다. 별명이나
    # 고유명사가 우연히 roster handle과 같은 경우, 브리핑에서 실제로 회수한
    # 토큰까지 발명으로 세면 fact_usage와 invented_handle이 동시에 참이 되는
    # 모순된 게이트가 된다.
    grounded_callouts = set(row.get("fact_tokens_used", ()))
    row["invented_handles"] = [
        handle for handle in called
        if handle not in message["text"]
        and handle != message["author"]
        and not _matching_tokens({handle}, grounded_callouts)
    ]
    row["callout_correct"] = called == [message["author"]] and row["callout_count"] == 1

    checks = message.get("checks") or {}
    forbidden = [pattern for pattern in checks.get("forbidden", []) if re.search(pattern, text)]
    required = checks.get("required_any", [])
    row["addressee_forbidden_hits"] = forbidden
    row["addressee_required_met"] = (not required) or any(re.search(pattern, text) for pattern in required)
    row["addressee_ok"] = (not forbidden) and row["addressee_required_met"] if (checks and text) else None

    if message["kind"] == "memory_probe":
        expect = message.get("expect_any", [])
        row["probe_expect"] = list(expect)
        row["probe_hit"] = any(token in text for token in expect)
    if message["kind"] in {"continuity_seed", "continuity_callback"}:
        checks = message.get("checks") or {}
        required = list(checks.get("required_any") or [])
        forbidden = list(checks.get("forbidden") or [])
        phase = message["arc_phase"]
        row.update({
            "arc_id": message["arc_id"],
            "arc_phase": phase,
            "arc_event_type": message["arc_event_type"],
            "arc_gap_minutes": message["arc_gap_minutes"],
            "arc_expected_source": message["arc_expected_source"],
            "arc_required_met": any(re.search(pattern, text) for pattern in required),
            "arc_forbidden_hits": [pattern for pattern in forbidden if re.search(pattern, text)],
        })
        row[f"arc_{phase}_hit"] = row["arc_required_met"] and not row["arc_forbidden_hits"]
    if pick.get("aggregate_expected"):
        markers = message.get("aggregate_markers", [])
        row["wave_size"] = pick.get("wave_size")
        row["wave_topic_answered"] = any(marker in text for marker in markers)
        row["wave_plurality_marked"] = any(marker in text for marker in AGGREGATE_MARKERS)
    return row


def summarize_turns(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the per-turn rows; every rate carries its own denominator."""
    def rate(selected: Sequence[dict[str, Any]], key: str) -> dict[str, Any]:
        scored = [row for row in selected if row.get(key) is not None]
        hits = sum(1 for row in scored if row[key])
        return {"hits": hits, "of": len(scored),
                "rate": round(hits / len(scored), 4) if scored else None}

    donations = [row for row in rows if row["kind"] == "donation"]
    probes = [row for row in rows if "probe_hit" in row]
    waves = [row for row in rows if "wave_topic_answered" in row]
    chars = sorted(row["chars"] for row in rows)
    summary = {
        "turns": len(rows),
        "empty": sum(1 for row in rows if row["empty"]),
        "fallback": rate(rows, "is_fallback"),
        "service_error": rate(rows, "service_error"),
        "topic_anchored": rate(rows, "topic_anchored"),
        "drift_turns": sum(1 for row in rows if row["drift"]),
        "addressee": rate([row for row in rows if row.get("addressee_ok") is not None], "addressee_ok"),
        "viewer_fact_usage": rate([row for row in rows if row.get("fact_usage") is not None], "fact_usage"),
        "donation_callout_correct": rate(donations, "callout_correct"),
        "invented_handle_turns": sum(1 for row in rows if row["invented_handles"]),
        "memory_probe": rate(probes, "probe_hit"),
        "opinion_topic_answered": rate(waves, "wave_topic_answered"),
        "opinion_plurality_marked": rate(waves, "wave_plurality_marked"),
        "chars_p50": chars[len(chars) // 2] if chars else None,
        "chars_p95": chars[min(len(chars) - 1, int(len(chars) * 0.95))] if chars else None,
        "kind_counts": {kind: sum(1 for row in rows if row["kind"] == kind) for kind in KINDS
                        if any(row["kind"] == kind for row in rows)},
    }
    arc_rows = [row for row in rows if row.get("arc_id")]
    seeds = [row for row in arc_rows if row.get("arc_phase") == "seed"]
    callbacks = [row for row in arc_rows if row.get("arc_phase") == "callback"]
    by_arc: dict[str, dict[str, dict[str, Any]]] = {}
    for row in arc_rows:
        by_arc.setdefault(row["arc_id"], {})[row["arc_phase"]] = row
    complete = [
        phases for phases in by_arc.values()
        if "seed" in phases and "callback" in phases
    ]
    long_callbacks = [row for row in callbacks if int(row["arc_gap_minutes"]) >= 30]
    ultra_callbacks = [row for row in callbacks if int(row["arc_gap_minutes"]) >= 90]
    summary["continuity"] = {
        "seed_response": rate(seeds, "arc_seed_hit"),
        "callback": rate(callbacks, "arc_callback_hit"),
        "long_callback_30m": rate(long_callbacks, "arc_callback_hit"),
        "ultra_callback_90m": rate(ultra_callbacks, "arc_callback_hit"),
        "complete_arc": {
            "hits": sum(
                bool(phases["seed"].get("arc_seed_hit"))
                and bool(phases["callback"].get("arc_callback_hit"))
                for phases in complete
            ),
            "of": len(complete),
            "rate": round(sum(
                bool(phases["seed"].get("arc_seed_hit"))
                and bool(phases["callback"].get("arc_callback_hit"))
                for phases in complete
            ) / len(complete), 4) if complete else None,
        },
        "forbidden_hit_turns": sum(bool(row.get("arc_forbidden_hits")) for row in arc_rows),
        "expected_source_counts": {
            source: sum(row.get("arc_expected_source") == source for row in callbacks)
            for source in ("history", "briefing", "durable_memory", "show_arc")
            if any(row.get("arc_expected_source") == source for row in callbacks)
        },
        "event_type_counts": {
            event_type: sum(row.get("arc_event_type") == event_type for row in callbacks)
            for event_type in sorted({row.get("arc_event_type") for row in callbacks})
            if event_type
        },
    }
    return summary


def priority_violations(picks: Sequence[dict[str, Any]], priority: Sequence[str], threshold: int) -> list[dict[str, Any]]:
    """A pick is a violation when a strictly higher-priority message was waiting."""
    ranked = {kind: index for index, kind in enumerate(priority)}
    violations = []
    for pick in picks:
        chosen_rank = ranked.get(pick["effective_kind"], len(ranked))
        for waiting in pick.get("backlog", []):
            if ranked.get(waiting["kind"], len(ranked)) < chosen_rank:
                violations.append({"turn_index": pick["turn_index"], "chosen": pick["message"]["id"],
                                   "skipped": waiting["id"]})
                break
    return violations
