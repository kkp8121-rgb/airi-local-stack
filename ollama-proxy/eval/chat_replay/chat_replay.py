#!/usr/bin/env python3
"""Local-only, privacy-bounded chat replay preparation and evaluation.

This module intentionally has no provider adapter, persistence, or default
network transport.  Real exports are read into memory, redacted before a
possible model callback, and are never copied to reports.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
from pathlib import Path
import re
from typing import Any, Callable, Iterable
import unicodedata


CONSENT_SCHEMA = "airi.chat-replay-consent.v1"
CONSENT_SCHEMA_V2 = "airi.chat-replay-consent.v2"
REPORT_SCHEMA = "airi.chat-replay-report.v2"
FIXTURE_SCHEMA = "airi.chat-replay-fixture.v1"
ALLOWED_KINDS = frozenset({"chat", "donation_callout", "system_noise"})
ALLOWED_AUTHORIZATION_BASES = frozenset({
    "creator_or_platform_written_permission",
    "operator_owned_broadcast",
})
_URL = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>]+")
_HANDLE = re.compile(r"(?<![\w@])@[A-Za-z0-9_.-]{2,64}")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]{1,64}@[A-Z0-9.-]{1,253}\.[A-Z]{2,63}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+82[- .]?)?0?1[016789][-. ]?\d{3,4}[-. ]?\d{4}(?!\d)")
_RRN = re.compile(r"(?<!\d)\d{6}[- ]?[1-8]\d{6}(?!\d)")
_AMOUNT = re.compile(
    r"(?i)(?<![\w\d])(?:₩\s*)?\d{1,9}(?:,\d{3})*(?:\s*(?:원|krw|별풍선|개))|"
    r"(?<![\w\d])(?:usd\s*|\$\s*)\d{1,7}(?:\.\d{1,2})?"
)
_SPACE = re.compile(r"\s+")
_BIDI = re.compile(r"[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_DISALLOWED_CONTROL = re.compile(r"[\u0000-\u0008\u000e-\u001f\u007f-\u009f]")
MAX_EXPORT_BYTES = 32 * 1024 * 1024
MAX_CONSENT_BYTES = 64 * 1024
MAX_PROVENANCE_BYTES = 1024 * 1024
MAX_SAFE_INTEGER = 9_007_199_254_740_991
BURST_EVENTS_PER_5S = 5
SOURCE_SLOTS = ("channel_a", "channel_b", "channel_c")
CAPTURE_PHASES = ("opening", "middle", "topic_transition", "game_transition")
SURFACE_SIGNAL_ORDER = (
    "question_mark",
    "laughter_run",
    "correction_marker",
    "emphasis",
    "donation",
    "noise",
    "source_text_repeat",
)
ALLOWED_RESPONSE_OUTCOMES = frozenset({
    "normal",
    "epistemic_live_state",
    "epistemic_agreement",
    "epistemic_reference",
    "epistemic_other",
    "serious_safety",
    "input_screened",
})
_QUESTION_MARK = re.compile(r"[?？]")
_LAUGHTER_RUN = re.compile(r"(?:ㅋ{2,}|ㅎ{2,})")
_CORRECTION_MARKER = re.compile(
    r"(?:^|[\s,.!?])(?:아니(?!면)|정정|잘못|취소)(?:$|[\s,.!?])|(?:^|\s)말고(?:$|\s)"
)
_EMPHASIS = re.compile(r"[!！?？]{2,}|(?:^|\s)(?:진짜|완전|대박|헐)(?:$|[\s!！])")
_PRIVATE_FIELDS = frozenset({
    "viewer_id", "viewerId", "provider_id", "providerId", "message_id",
    "messageId", "scope_id", "scopeId", "display_name", "displayName",
    "author_display_name", "authorDisplayName", "profile_url", "profileUrl",
    "author_id", "authorId", "user_id", "userId", "user_nickname",
    "userNickname", "channel", "channel_id", "channelId", "channel_name",
    "creator", "creator_id", "creatorId", "creator_name",
})
_REQUIRED_EVENT_FIELDS = frozenset({"timestamp_ms", "kind", "text"})
_ALLOWED_EVENT_FIELDS = _REQUIRED_EVENT_FIELDS | _PRIVATE_FIELDS


class ReplayAuthorizationError(ValueError):
    """The local export is not authorized for this use."""


class ReplayFormatError(ValueError):
    """The input is not a bounded platform-neutral replay export."""


@dataclass(frozen=True)
class ReplayEvent:
    seq: int
    offset_ms: int
    timing_bucket: str
    event_kind: str
    model_text: str
    duplicate_of_seq: int | None
    selection_eligible: bool
    surface_signals: tuple[str, ...]


@dataclass(frozen=True)
class ReplayResponse:
    text: str
    outcome: str = "normal"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if len(raw) < 1 or len(raw) > MAX_CONSENT_BYTES:
            raise ReplayAuthorizationError("consent sidecar size is outside the limit")
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReplayAuthorizationError("consent sidecar is unreadable") from exc
    if not isinstance(value, dict):
        raise ReplayAuthorizationError("consent sidecar must be an object")
    return value


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ReplayAuthorizationError("consent timestamp must be UTC ISO-8601")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayAuthorizationError("consent timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ReplayAuthorizationError("consent timestamp must be UTC")
    return parsed


def _read_export_bytes(export_path: Path) -> bytes:
    try:
        size = export_path.stat().st_size
        if size < 1 or size > MAX_EXPORT_BYTES:
            raise ReplayAuthorizationError("export size is outside the local replay limit")
        value = export_path.read_bytes()
        if len(value) < 1 or len(value) > MAX_EXPORT_BYTES:
            raise ReplayAuthorizationError("export size is outside the local replay limit")
        return value
    except OSError as exc:
        raise ReplayAuthorizationError("export is unreadable") from exc


def _read_provenance_bytes(provenance_path: Path) -> bytes:
    try:
        value = provenance_path.read_bytes()
    except OSError as exc:
        raise ReplayAuthorizationError("provenance record is unreadable") from exc
    if len(value) < 1 or len(value) > MAX_PROVENANCE_BYTES:
        raise ReplayAuthorizationError("provenance record size is outside the limit")
    return value


def authorize_capture(
    consent_path: Path,
    export_path: Path,
    provenance_path: Path,
    *,
    now: datetime | None = None,
    export_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Fail closed unless an explicit, current local authorization binds export bytes."""
    sidecar = _read_json(consent_path)
    base_required = {
        "schema_version", "authorization", "authorization_basis",
        "authorized_at", "purposes", "expires_at", "delete_by", "revoked",
        "source_sha256", "provenance_sha256", "excluded_creator_names",
    }
    schema = sidecar.get("schema_version")
    required = (
        base_required | {"capture_profile"}
        if schema == CONSENT_SCHEMA_V2 else base_required
    )
    if set(sidecar) != required or schema not in {CONSENT_SCHEMA, CONSENT_SCHEMA_V2}:
        raise ReplayAuthorizationError("consent sidecar has unsupported fields")
    if schema == CONSENT_SCHEMA_V2:
        profile = sidecar["capture_profile"]
        if (
            not isinstance(profile, dict)
            or set(profile) != {"source_slot", "phase", "provider_binding_hmac"}
            or profile.get("source_slot") not in SOURCE_SLOTS
            or profile.get("phase") not in CAPTURE_PHASES
            or not isinstance(profile.get("provider_binding_hmac"), str)
            or re.fullmatch(r"[0-9a-f]{64}", profile["provider_binding_hmac"]) is None
        ):
            raise ReplayAuthorizationError("consent capture profile is invalid")
    if sidecar["authorization"] != "authorized" or sidecar["revoked"] is not False:
        raise ReplayAuthorizationError("capture authorization is absent or revoked")
    if sidecar["authorization_basis"] not in ALLOWED_AUTHORIZATION_BASES:
        raise ReplayAuthorizationError("capture authorization basis is not sufficient")
    if not isinstance(sidecar["purposes"], list) or "local_replay_evaluation" not in sidecar["purposes"]:
        raise ReplayAuthorizationError("consent does not permit local replay evaluation")
    if (
        not isinstance(sidecar["excluded_creator_names"], list)
        or not 1 <= len(sidecar["excluded_creator_names"]) <= 100
        or not all(
            isinstance(x, str) and 1 <= len(x.strip()) <= 100
            and _BIDI.search(x) is None
            and _DISALLOWED_CONTROL.search(x) is None
            and all(unicodedata.category(character) != "Cs" for character in x)
            for x in sidecar["excluded_creator_names"]
        )
    ):
        raise ReplayAuthorizationError("consent must declare creator-name exclusions")
    if not isinstance(sidecar["source_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", sidecar["source_sha256"]):
        raise ReplayAuthorizationError("consent source hash is invalid")
    if not isinstance(sidecar["provenance_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", sidecar["provenance_sha256"]):
        raise ReplayAuthorizationError("consent provenance hash is invalid")
    source_hash = hashlib.sha256(
        export_bytes if export_bytes is not None else _read_export_bytes(export_path)
    ).hexdigest()
    if source_hash != sidecar["source_sha256"]:
        raise ReplayAuthorizationError("consent sidecar does not bind this export")
    provenance_hash = hashlib.sha256(_read_provenance_bytes(provenance_path)).hexdigest()
    if provenance_hash != sidecar["provenance_sha256"]:
        raise ReplayAuthorizationError("consent sidecar does not bind this provenance record")
    current = now or datetime.now(timezone.utc)
    authorized_at = _parse_utc(sidecar["authorized_at"])
    if authorized_at > current:
        raise ReplayAuthorizationError("capture authorization is future-dated")
    if _parse_utc(sidecar["expires_at"]) <= current:
        raise ReplayAuthorizationError("capture authorization has expired")
    if _parse_utc(sidecar["delete_by"]) <= current:
        raise ReplayAuthorizationError("capture retention deadline has passed")
    return sidecar


def redact_text(value: Any, forbidden_names: Iterable[str]) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 4_000:
        raise ReplayFormatError("event text must be a non-empty bounded string")
    if _BIDI.search(value) or _DISALLOWED_CONTROL.search(value) or any(
        unicodedata.category(character) == "Cs" for character in value
    ):
        raise ReplayFormatError("event text contains unsafe Unicode")
    text = unicodedata.normalize("NFC", value)
    for name in forbidden_names:
        if name:
            text = re.sub(
                re.escape(unicodedata.normalize("NFC", name)),
                "[이름 삭제]",
                text,
                flags=re.IGNORECASE,
            )
    text = _URL.sub("[링크 삭제]", text)
    text = _EMAIL.sub("[개인정보 삭제]", text)
    text = _HANDLE.sub("[사용자 언급 삭제]", text)
    text = _PHONE.sub("[개인정보 삭제]", text)
    text = _RRN.sub("[개인정보 삭제]", text)
    text = _AMOUNT.sub("[금액 삭제]", text)
    text = _SPACE.sub(" ", text).strip()
    if not text:
        return "[삭제된 채팅]"
    return text[:1_000]


def _bucket(offset_ms: int) -> str:
    if offset_ms < 1_000:
        return "under_1s"
    if offset_ms < 5_000:
        return "1s_to_5s"
    if offset_ms < 15_000:
        return "5s_to_15s"
    return "15s_plus"


def _surface_signals(
    text: str, kind: str, *, duplicate: bool,
) -> tuple[str, ...]:
    present = {
        "question_mark": bool(_QUESTION_MARK.search(text)),
        "laughter_run": bool(_LAUGHTER_RUN.search(text)),
        "correction_marker": bool(_CORRECTION_MARKER.search(text)),
        "emphasis": bool(_EMPHASIS.search(text)),
        "donation": kind == "donation_callout",
        "noise": kind == "system_noise",
        "source_text_repeat": duplicate,
    }
    return tuple(signal for signal in SURFACE_SIGNAL_ORDER if present[signal])


def _nearest_rank(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _load_lines(export_bytes: bytes) -> list[dict[str, Any]]:
    try:
        lines = export_bytes.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise ReplayFormatError("export is unreadable") from exc
    if not lines or len(lines) > 20_000:
        raise ReplayFormatError("export must contain 1..20000 JSONL events")
    events: list[dict[str, Any]] = []
    for number, line in enumerate(lines, 1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReplayFormatError(f"line {number} is not JSON") from exc
        if not isinstance(item, dict):
            raise ReplayFormatError(f"line {number} must be an object")
        events.append(item)
    return events


def load_private_replay(
    export_path: Path,
    consent_path: Path,
    provenance_path: Path,
    *,
    now: datetime | None = None,
) -> tuple[list[ReplayEvent], dict[str, str] | None]:
    """Read an authorized export and return memory-only events plus a bounded profile."""
    export_bytes = _read_export_bytes(export_path)
    consent = authorize_capture(
        consent_path, export_path, provenance_path,
        now=now, export_bytes=export_bytes,
    )
    source = _load_lines(export_bytes)
    first_timestamp: int | None = None
    previous_timestamp: int | None = None
    seen_source_text: dict[tuple[str, str], int] = {}
    output: list[ReplayEvent] = []
    forbidden = consent["excluded_creator_names"]
    for seq, item in enumerate(source, 1):
        if (
            not _REQUIRED_EVENT_FIELDS.issubset(item)
            or not set(item).issubset(_ALLOWED_EVENT_FIELDS)
            or type(item["timestamp_ms"]) is not int
        ):
            raise ReplayFormatError(f"line {seq} has missing or unsupported event fields")
        timestamp = item["timestamp_ms"]
        if (
            timestamp < 0
            or timestamp > MAX_SAFE_INTEGER
            or (previous_timestamp is not None and timestamp < previous_timestamp)
        ):
            raise ReplayFormatError(f"line {seq} timestamps must be monotonic non-negative integers")
        raw_kind = item["kind"]
        kind = {"donation": "donation_callout", "noise": "system_noise"}.get(raw_kind, raw_kind)
        if kind not in ALLOWED_KINDS:
            raise ReplayFormatError(f"line {seq} has unsupported kind")
        # These values are used only as one-pass redaction targets.  They are
        # never copied to ReplayEvent, the report, or a model callback.
        event_identity_values = [
            value for key, value in item.items()
            if key in _PRIVATE_FIELDS and isinstance(value, str) and value.strip()
        ]
        source_text = item["text"]
        text = redact_text(source_text, [*forbidden, *event_identity_values])
        if first_timestamp is None:
            first_timestamp = timestamp
        gap_ms = 0 if previous_timestamp is None else timestamp - previous_timestamp
        previous_timestamp = timestamp
        # Detect repeated source wording before redaction. Different source
        # messages may collapse to the same placeholders and must not be
        # misreported or suppressed as exact repeats.
        duplicate_of = seen_source_text.get((kind, source_text))
        if duplicate_of is None:
            seen_source_text[(kind, source_text)] = seq
        eligible = kind != "system_noise" and duplicate_of is None
        output.append(ReplayEvent(
            seq,
            timestamp - first_timestamp,
            _bucket(gap_ms),
            kind,
            text,
            duplicate_of,
            eligible,
            _surface_signals(text, kind, duplicate=duplicate_of is not None),
        ))
    private_profile = consent.get("capture_profile")
    public_profile = (
        {
            "source_slot": private_profile["source_slot"],
            "phase": private_profile["phase"],
        }
        if isinstance(private_profile, dict) else None
    )
    return output, public_profile


def import_private_replay(
    export_path: Path,
    consent_path: Path,
    provenance_path: Path,
    *,
    now: datetime | None = None,
) -> list[ReplayEvent]:
    """Compatibility wrapper returning only redacted, memory-only events."""
    events, _ = load_private_replay(
        export_path, consent_path, provenance_path, now=now,
    )
    return events


def _rolling_5s_counts(replay: list[ReplayEvent]) -> list[int]:
    """Counts for half-open [event, event + 5000ms) windows."""
    counts: list[int] = []
    right = 0
    for left, event in enumerate(replay):
        right = max(right, left)
        while right < len(replay) and replay[right].offset_ms - event.offset_ms < 5_000:
            right += 1
        counts.append(right - left)
    return counts


def run_replay(
    events: Iterable[ReplayEvent],
    responder: Callable[[str, ReplayEvent], str | ReplayResponse] | None = None,
    review_sink: Callable[[ReplayEvent, str], None] | None = None,
    *,
    capture_profile: dict[str, str] | None = None,
    report_hmac_key: bytes | None = None,
) -> dict[str, Any]:
    """Deterministically replay prepared events without sleeping or retaining responses."""
    replay = list(events)
    if any(
        event.seq != index
        or event.offset_ms < 0
        or (index > 1 and event.offset_ms < replay[index - 2].offset_ms)
        or event.event_kind not in ALLOWED_KINDS
        or event.surface_signals != _surface_signals(
            event.model_text,
            event.event_kind,
            duplicate=event.duplicate_of_seq is not None,
        )
        for index, event in enumerate(replay, 1)
    ):
        raise ReplayFormatError("prepared replay order or surface signals are invalid")
    if capture_profile is not None and (
        not isinstance(capture_profile, dict)
        or set(capture_profile) != {"source_slot", "phase"}
        or capture_profile.get("source_slot") not in SOURCE_SLOTS
        or capture_profile.get("phase") not in CAPTURE_PHASES
    ):
        raise ReplayFormatError("capture profile is invalid")
    if responder is not None and (
        not isinstance(report_hmac_key, bytes) or len(report_hmac_key) < 32
    ):
        raise ReplayFormatError("model replay requires a local report HMAC key")
    kinds = Counter(event.event_kind for event in replay)
    timing_buckets = Counter(event.timing_bucket for event in replay)
    surface_signals = Counter(
        signal for event in replay for signal in event.surface_signals
    )
    adjacent_signal_pairs: Counter[str] = Counter()
    for previous, current in zip(replay, replay[1:]):
        previous_signals = previous.surface_signals or ("none",)
        current_signals = current.surface_signals or ("none",)
        adjacent_signal_pairs.update(
            f"{left}->{right}"
            for left in previous_signals
            for right in current_signals
        )
    delivered = 0
    responses = 0
    response_rows: list[dict[str, Any]] = []
    response_outcomes: Counter[str] = Counter()
    outcomes_by_signal: dict[str, Counter[str]] = {}
    for event in replay:
        if not event.selection_eligible:
            continue
        delivered += 1
        if responder is not None:
            result = responder(event.model_text, event)
            if isinstance(result, str):
                response = result
                outcome = "normal"
            elif isinstance(result, ReplayResponse):
                response = result.text
                outcome = result.outcome
            else:
                raise ReplayFormatError("responder must return text or ReplayResponse")
            if not isinstance(response, str) or outcome not in ALLOWED_RESPONSE_OUTCOMES:
                raise ReplayFormatError("responder returned an invalid bounded outcome")
            responses += 1
            response_outcomes[outcome] += 1
            for signal in event.surface_signals or ("none",):
                outcomes_by_signal.setdefault(signal, Counter())[outcome] += 1
            response_rows.append({
                "seq": event.seq,
                "outcome": outcome,
                "response_char_count": len(response),
                "response_hmac_sha256": hmac.new(
                    report_hmac_key,
                    b"airi.chat-replay-response.v1\0"
                    + str(event.seq).encode("ascii") + b"\0"
                    + response.encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest(),
            })
            if review_sink is not None:
                review_sink(event, response)
    structural = [{"seq": item.seq, "offset_ms": item.offset_ms, "timing_bucket": item.timing_bucket, "event_kind": item.event_kind, "duplicate_of_seq": item.duplicate_of_seq, "selection_eligible": item.selection_eligible, "surface_signals": item.surface_signals} for item in replay]
    five_second_windows = Counter(item.offset_ms // 5_000 for item in replay)
    rolling_5s_counts = _rolling_5s_counts(replay)
    gaps = [
        current.offset_ms - previous.offset_ms
        for previous, current in zip(replay, replay[1:])
    ]
    duration_ms = replay[-1].offset_ms if replay else 0
    repeat_clusters = Counter(
        item.duplicate_of_seq or item.seq for item in replay
    )
    repeated_sizes = [size for size in repeat_clusters.values() if size > 1]
    event_count = len(replay)
    duplicate_count = sum(item.duplicate_of_seq is not None for item in replay)
    noise_count = kinds["system_noise"]
    eligible_count = sum(item.selection_eligible for item in replay)
    return {
        "schema_version": REPORT_SCHEMA,
        "event_count": event_count,
        "event_kinds": dict(sorted(kinds.items())),
        "timing_buckets": dict(sorted(timing_buckets.items())),
        "duplicate_count": duplicate_count,
        "noise_count": noise_count,
        "delivered_count": delivered,
        "response_count": responses,
        "response_rows": response_rows,
        "response_outcome_counts": dict(sorted(response_outcomes.items())),
        "outcome_by_surface_signal": {
            signal: dict(sorted(counts.items()))
            for signal, counts in sorted(outcomes_by_signal.items())
        },
        "surface_signal_counts": dict(sorted(surface_signals.items())),
        "adjacent_event_count": max(event_count - 1, 0),
        "adjacent_signal_pair_counts": dict(sorted(adjacent_signal_pairs.items())),
        "max_events_in_rolling_5s": max(rolling_5s_counts, default=0),
        "capture_profile": capture_profile,
        "flow": {
            "duration_ms": duration_ms,
            "gap_p50_ms": _nearest_rank(gaps, 0.50),
            "gap_p95_ms": _nearest_rank(gaps, 0.95),
            "gap_max_ms": max(gaps, default=None),
            "interarrival_rate_per_minute": (
                round((event_count - 1) * 60_000 / duration_ms, 6)
                if event_count > 1 and duration_ms > 0 else None
            ),
            "active_fixed_5s_bins": len(five_second_windows),
            "rolling_5s_burst_threshold": BURST_EVENTS_PER_5S,
            "rolling_5s_burst_start_count": sum(
                count >= BURST_EVENTS_PER_5S
                for count in rolling_5s_counts
            ),
            "duplicate_rate": _ratio(duplicate_count, event_count),
            "noise_rate": _ratio(noise_count, event_count),
            "eligible_rate": _ratio(eligible_count, event_count),
            "repeat_cluster_count": len(repeated_sizes),
            "max_repeat_cluster_size": max(repeated_sizes, default=0),
        },
        "structural_sha256": hashlib.sha256(_canonical({
            "capture_profile": capture_profile,
            "events": structural,
        })).hexdigest(),
    }
