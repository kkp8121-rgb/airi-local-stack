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
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterable
import unicodedata


CONSENT_SCHEMA = "airi.chat-replay-consent.v1"
REPORT_SCHEMA = "airi.chat-replay-report.v1"
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
    required = {
        "schema_version", "authorization", "authorization_basis",
        "authorized_at", "purposes", "expires_at", "delete_by", "revoked",
        "source_sha256", "provenance_sha256", "excluded_creator_names",
    }
    if set(sidecar) != required or sidecar["schema_version"] != CONSENT_SCHEMA:
        raise ReplayAuthorizationError("consent sidecar has unsupported fields")
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


def import_private_replay(
    export_path: Path,
    consent_path: Path,
    provenance_path: Path,
    *,
    now: datetime | None = None,
) -> list[ReplayEvent]:
    """Read a consent-bound local export and return redacted, memory-only events."""
    export_bytes = _read_export_bytes(export_path)
    consent = authorize_capture(
        consent_path, export_path, provenance_path,
        now=now, export_bytes=export_bytes,
    )
    source = _load_lines(export_bytes)
    first_timestamp: int | None = None
    previous_timestamp: int | None = None
    seen: dict[tuple[str, str], int] = {}
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
        text = redact_text(item["text"], [*forbidden, *event_identity_values])
        if first_timestamp is None:
            first_timestamp = timestamp
        gap_ms = 0 if previous_timestamp is None else timestamp - previous_timestamp
        previous_timestamp = timestamp
        duplicate_of = seen.get((kind, text))
        if duplicate_of is None:
            seen[(kind, text)] = seq
        eligible = kind != "system_noise" and duplicate_of is None
        output.append(ReplayEvent(seq, timestamp - first_timestamp, _bucket(gap_ms), kind, text, duplicate_of, eligible))
    return output


def run_replay(
    events: Iterable[ReplayEvent],
    responder: Callable[[str, ReplayEvent], str] | None = None,
    review_sink: Callable[[ReplayEvent, str], None] | None = None,
) -> dict[str, Any]:
    """Deterministically replay prepared events without sleeping or retaining responses."""
    replay = list(events)
    kinds = Counter(event.event_kind for event in replay)
    timing_buckets = Counter(event.timing_bucket for event in replay)
    delivered = 0
    responses = 0
    response_rows: list[dict[str, Any]] = []
    for event in replay:
        if not event.selection_eligible:
            continue
        delivered += 1
        if responder is not None:
            response = responder(event.model_text, event)
            if not isinstance(response, str):
                raise ReplayFormatError("responder must return text")
            responses += 1
            response_rows.append({
                "seq": event.seq,
                "response_char_count": len(response),
                "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
            })
            if review_sink is not None:
                review_sink(event, response)
    structural = [{"seq": item.seq, "offset_ms": item.offset_ms, "timing_bucket": item.timing_bucket, "event_kind": item.event_kind, "duplicate_of_seq": item.duplicate_of_seq, "selection_eligible": item.selection_eligible} for item in replay]
    five_second_windows = Counter(item.offset_ms // 5_000 for item in replay)
    return {
        "schema_version": REPORT_SCHEMA,
        "event_count": len(replay),
        "event_kinds": dict(sorted(kinds.items())),
        "timing_buckets": dict(sorted(timing_buckets.items())),
        "duplicate_count": sum(item.duplicate_of_seq is not None for item in replay),
        "noise_count": kinds["system_noise"],
        "delivered_count": delivered,
        "response_count": responses,
        "response_rows": response_rows,
        "max_events_per_5s_window": max(five_second_windows.values(), default=0),
        "structural_sha256": hashlib.sha256(_canonical(structural)).hexdigest(),
    }
