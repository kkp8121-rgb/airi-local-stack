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
KINDS = ("donation", "memory_seed", "memory_probe", "opinion", "question", "reaction", "offtopic")


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
        planned.sort(key=lambda item: 0 if item["kind"] in ("donation", "memory_probe") else 1)
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


AGGREGATE_MARKERS = ("다들", "여러", "많이", "다 같이", "모두", "전부", "너희", "여기저기")


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
    drift_terms: Sequence[str] = (),
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
        "anchor_hit": [anchor for anchor in anchors if anchor in text],
        "shared_tokens": sorted(shared),
        # 두 축을 따로 본다. `topic_anchored` 는 "방송 주제에 붙어 있나"라는
        # 엄격한 신호라 "응원할게"→"고마워!" 같은 정상 반응도 False 가 된다.
        # `drift` 는 입력에 없던 딴소리 어휘를 스스로 꺼냈을 때만 True 다.
        "topic_anchored": bool(shared) or any(anchor in text for anchor in anchors),
        "drift": sorted((_tokens(text) & set(drift_terms)) - _tokens(message["text"])),
    }

    called = [handle for handle in roster_handles if handle and handle in text]
    row["called_handles"] = called
    row["callout_count"] = sum(text.count(handle) for handle in called)
    # 입력에 없던 시청자 이름을 부르면 그건 호명이 아니라 발명이다.
    row["invented_handles"] = [handle for handle in called if handle not in message["text"] and handle != message["author"]]
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
    return {
        "turns": len(rows),
        "empty": sum(1 for row in rows if row["empty"]),
        "fallback": rate(rows, "is_fallback"),
        "topic_anchored": rate(rows, "topic_anchored"),
        "drift_turns": sum(1 for row in rows if row["drift"]),
        "addressee": rate([row for row in rows if row.get("addressee_ok") is not None], "addressee_ok"),
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
