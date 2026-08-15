"""Shared, strict custody contract for AIRI-minimized YouTube live exports."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any
import unicodedata

from chat_replay import (
    MAX_EXPORT_BYTES,
    MAX_REPLAY_EVENTS,
    MAX_SAFE_INTEGER,
    ReplayAuthorizationError,
    _BIDI,
    _DISALLOWED_CONTROL,
    _canonical,
)


SOURCE_SCHEMA = "airi.youtube-live-api-minimized.v1"
RECEIPT_SCHEMA = "airi.youtube-live-capture-receipt.v1"
ENVELOPE_SCHEMA = "airi.authorized-provider-export.v1"
RECEIPT_HMAC_DOMAIN = b"airi.youtube-live-capture-receipt.v1\0"
MAX_ACTUAL_OVERRUN_MS = 60_000
_LOWER_HEX = re.compile(r"[0-9a-f]{64}")
_HEADER_KEYS = frozenset({
    "record_type", "schema_version", "provider", "channel_id", "exporter_id",
    "source_schema", "exported_at_ms",
})
_EVENT_KEYS = frozenset({
    "record_type", "provider", "channel_id", "occurred_at_ms",
    "source_type", "text",
})
_RECEIPT_KEYS = frozenset({
    "schema_version", "status", "requested_duration_seconds",
    "actual_duration_ms", "event_count", "source_type_counts", "batches",
    "retries", "duplicates", "prestart", "invalid", "bundle_hmac_sha256",
})


def _safe_integer(value: Any, minimum: int = 0, maximum: int = MAX_SAFE_INTEGER) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _safe_text(value: Any, maximum: int = 4_000) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and value == unicodedata.normalize("NFC", value)
        and _BIDI.search(value) is None
        and _DISALLOWED_CONTROL.search(value) is None
        and all(
            unicodedata.category(char) not in {"Cc", "Cf", "Cs"}
            for char in value
        )
    )


def receipt_hmac(identity_key: bytes, export_bytes: bytes, consent: dict[str, Any], receipt: dict[str, Any]) -> str:
    """Authenticate exact JSONL, canonical consent, and every receipt field."""
    unsigned = dict(receipt)
    unsigned.pop("bundle_hmac_sha256", None)
    payload = (
        RECEIPT_HMAC_DOMAIN
        + _canonical(unsigned)
        + b"\0"
        + _canonical(consent)
        + b"\0"
        + export_bytes
    )
    return hmac.new(identity_key, payload, hashlib.sha256).hexdigest()


def _parse_export_counts(export_bytes: bytes) -> tuple[int, dict[str, int]]:
    if not 1 <= len(export_bytes) <= MAX_EXPORT_BYTES:
        raise ReplayAuthorizationError("capture export size is invalid")
    try:
        records = [json.loads(line) for line in export_bytes.decode("utf-8").splitlines()]
    except (UnicodeError, json.JSONDecodeError):
        raise ReplayAuthorizationError("capture export is invalid") from None
    if not 301 <= len(records) <= MAX_REPLAY_EVENTS + 1:
        raise ReplayAuthorizationError("capture export event count is invalid")
    header = records[0]
    if (
        not isinstance(header, dict)
        or set(header) != _HEADER_KEYS
        or header.get("record_type") != "header"
        or header.get("schema_version") != ENVELOPE_SCHEMA
        or header.get("provider") != "youtube"
        or header.get("source_schema") != SOURCE_SCHEMA
        or not _safe_text(header.get("channel_id"), 128)
        or not _safe_text(header.get("exporter_id"), 128)
        or not _safe_integer(header.get("exported_at_ms"))
    ):
        raise ReplayAuthorizationError("capture export header is invalid")
    counts = {"text": 0, "donation": 0, "system": 0}
    previous: int | None = None
    for event in records[1:]:
        source_type = event.get("source_type") if isinstance(event, dict) else None
        text = event.get("text") if isinstance(event, dict) else None
        if (
            not isinstance(event, dict)
            or set(event) != _EVENT_KEYS
            or event.get("record_type") != "event"
            or event.get("provider") != "youtube"
            or event.get("channel_id") != header.get("channel_id")
            or source_type not in counts
            or not _safe_integer(event.get("occurred_at_ms"))
            or previous is not None and event["occurred_at_ms"] < previous
            or source_type == "text" and not _safe_text(text)
            or source_type != "text" and text is not None
        ):
            raise ReplayAuthorizationError("capture export event is invalid")
        counts[source_type] += 1
        previous = event["occurred_at_ms"]
    return len(records) - 1, counts


def verify_capture_receipt(export_bytes: bytes, consent: dict[str, Any], receipt: dict[str, Any], identity_key: bytes) -> None:
    """Fail closed unless the minimized export, consent, and receipt cohere."""
    event_count, counts = _parse_export_counts(export_bytes)
    requested = receipt.get("requested_duration_seconds") if isinstance(receipt, dict) else None
    reported_counts = receipt.get("source_type_counts") if isinstance(receipt, dict) else None
    if (
        not isinstance(consent, dict)
        or not isinstance(receipt, dict)
        or set(receipt) != _RECEIPT_KEYS
        or receipt.get("schema_version") != RECEIPT_SCHEMA
        or receipt.get("status") != "complete"
        or not _safe_integer(requested, 1_800, 7_200)
        or not _safe_integer(
            receipt.get("actual_duration_ms"),
            requested * 1_000,
            requested * 1_000 + MAX_ACTUAL_OVERRUN_MS,
        )
        or receipt.get("event_count") != event_count
        or not isinstance(reported_counts, dict)
        or set(reported_counts) != set(counts)
        or any(not _safe_integer(reported_counts[name], 0, event_count) for name in counts)
        or reported_counts != counts
        or not _safe_integer(receipt.get("batches"), 1, 20_000)
        or not _safe_integer(
            receipt.get("retries"),
            0,
            (receipt.get("batches", 0) + 1) * 2,
        )
        or not _safe_integer(receipt.get("duplicates"), 0, 40_000)
        or not _safe_integer(receipt.get("prestart"), 0, 40_000)
        or not _safe_integer(receipt.get("invalid"), 0, 0)
        or _LOWER_HEX.fullmatch(receipt.get("bundle_hmac_sha256", "")) is None
        or not isinstance(identity_key, bytes)
        or len(identity_key) < 32
    ):
        raise ReplayAuthorizationError("capture receipt is invalid")
    expected = receipt_hmac(identity_key, export_bytes, consent, receipt)
    if not hmac.compare_digest(receipt["bundle_hmac_sha256"], expected):
        raise ReplayAuthorizationError("capture receipt HMAC is invalid")
