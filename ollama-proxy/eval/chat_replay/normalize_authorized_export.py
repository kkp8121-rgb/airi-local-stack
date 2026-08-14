#!/usr/bin/env python3
"""Offline normalisation for explicitly authorised provider-safe envelopes.

This deliberately accepts only AIRI's provider-approved envelope, not a
provider API response.  It has no provider adapters and makes no requests.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any
import unicodedata

from chat_replay import (
    MAX_EXPORT_BYTES,
    MAX_SAFE_INTEGER,
    SOURCE_SLOTS,
    ReplayAuthorizationError,
    ReplayFormatError,
    _BIDI,
    _canonical,
    _DISALLOWED_CONTROL,
    _parse_utc,
    authorize_capture,
    redact_text,
)
from replay_local_io import _secure_inside, write_atomic_json, write_atomic_jsonl


ENVELOPE_SCHEMA = "airi.authorized-provider-export.v1"
ALLOWLIST_SCHEMA = "airi.provider-channel-allowlist.v1"
PROVIDERS = frozenset({"chzzk", "soop", "youtube"})
SOURCE_TYPES = frozenset({"text", "donation", "system"})
_HEADER_KEYS = frozenset({
    "record_type", "schema_version", "provider", "channel_id", "exporter_id",
    "source_schema", "exported_at_ms",
})
_EVENT_KEYS = frozenset({
    "record_type", "provider", "channel_id", "occurred_at_ms", "source_type", "text",
})
_ALLOWLIST_KEYS = frozenset({"schema_version", "entries"})
_ALLOWLIST_ENTRY_KEYS = frozenset({
    "provider", "channel_id", "exporter_id", "source_schema",
    "authorization_ref_sha256", "source_slot", "provider_binding_hmac",
    "not_after", "enabled",
})
_DONATION_TEXT = "[후원 이벤트]"
_SYSTEM_TEXT = "[시스템 메시지]"
HERE = Path(__file__).resolve().parent
RECEIPT_SCHEMA = "airi.authorized-provider-normalization-receipt.v1"
_RECEIPT_KEYS = frozenset({
    "schema_version", "provider", "source_slot", "phase",
    "normalization_hmac_sha256", "input_event_count", "output_event_count",
})


def _safe_integer(value: Any) -> bool:
    return type(value) is int and 0 <= value <= MAX_SAFE_INTEGER


def _safe_string(value: Any, maximum: int) -> bool:
    return (
        isinstance(value, str) and 1 <= len(value) <= maximum
        and value == unicodedata.normalize("NFC", value)
        and _BIDI.search(value) is None and _DISALLOWED_CONTROL.search(value) is None
        and all(unicodedata.category(character) not in {"Cs", "Cc", "Cf"} for character in value)
    )


def _read_source(path: Path) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ReplayAuthorizationError("authorized export is unreadable") from exc
    if not 1 <= len(raw) <= MAX_EXPORT_BYTES:
        raise ReplayAuthorizationError("authorized export size is outside the local replay limit")
    return raw


def _load_jsonl(raw: bytes) -> list[dict[str, Any]]:
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise ReplayFormatError("authorized export is not UTF-8") from exc
    if not 2 <= len(lines) <= 20_001:
        raise ReplayFormatError("authorized export must contain a header and 1..20000 events")
    result = []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReplayFormatError("authorized export contains invalid JSONL") from exc
        if not isinstance(item, dict):
            raise ReplayFormatError("authorized export records must be objects")
        result.append(item)
    return result


def _validate_header(value: dict[str, Any]) -> tuple[str, str, str]:
    if set(value) != _HEADER_KEYS or value.get("record_type") != "header":
        raise ReplayFormatError("authorized export header has unsupported fields")
    if value.get("schema_version") != ENVELOPE_SCHEMA or value.get("source_schema") != "provider-approved-envelope.v1":
        raise ReplayFormatError("authorized export header schema is unsupported")
    provider = value.get("provider")
    if provider not in PROVIDERS or not _safe_string(value.get("channel_id"), 256) or not _safe_string(value.get("exporter_id"), 128):
        raise ReplayFormatError("authorized export header identity is invalid")
    if not _safe_integer(value.get("exported_at_ms")):
        raise ReplayFormatError("authorized export timestamp is invalid")
    return provider, value["channel_id"], value["exporter_id"]


def _load_allowlist(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReplayAuthorizationError("local channel allowlist is unreadable") from exc
    if len(raw) < 1 or len(raw) > 64 * 1024 or not isinstance(value, dict) or set(value) != _ALLOWLIST_KEYS or value.get("schema_version") != ALLOWLIST_SCHEMA or not isinstance(value.get("entries"), list) or not 1 <= len(value["entries"]) <= 100:
        raise ReplayAuthorizationError("local channel allowlist has unsupported fields")
    return value


def read_identity_key(path: Path) -> bytes:
    try:
        value = path.read_bytes()
    except OSError as exc:
        raise ReplayAuthorizationError("local provider identity key is unreadable") from exc
    if not 32 <= len(value) <= 1_024:
        raise ReplayAuthorizationError("local provider identity key must contain 32..1024 bytes")
    return value


def provider_binding_hmac(
    key: bytes,
    *,
    provider: str,
    channel_id: str,
    exporter_id: str,
    source_schema: str,
    authorization_ref_sha256: str,
    source_slot: str,
) -> str:
    fields = (
        "airi.provider-channel-binding.v1", provider, channel_id, exporter_id,
        source_schema, authorization_ref_sha256, source_slot,
    )
    return hmac.new(key, "\0".join(fields).encode("utf-8"), hashlib.sha256).hexdigest()


def _authorize_allowlist(
    allowlist_path: Path,
    identity_key_path: Path,
    header: dict[str, Any],
    consent: dict[str, Any],
    now: datetime,
) -> bytes:
    profile = consent.get("capture_profile")
    if not isinstance(profile, dict):
        raise ReplayAuthorizationError("authorized provider export requires consent v2 capture profile")
    identity_key = read_identity_key(identity_key_path)
    matches = []
    for entry in _load_allowlist(allowlist_path)["entries"]:
        if not isinstance(entry, dict) or set(entry) != _ALLOWLIST_ENTRY_KEYS:
            raise ReplayAuthorizationError("local channel allowlist entry has unsupported fields")
        if not (
            entry.get("provider") in PROVIDERS
            and _safe_string(entry.get("channel_id"), 256)
            and _safe_string(entry.get("exporter_id"), 128)
            and entry.get("source_schema") == "provider-approved-envelope.v1"
            and isinstance(entry.get("authorization_ref_sha256"), str)
            and len(entry["authorization_ref_sha256"]) == 64
            and all(char in "0123456789abcdef" for char in entry["authorization_ref_sha256"])
            and entry.get("source_slot") in SOURCE_SLOTS
            and isinstance(entry.get("provider_binding_hmac"), str)
            and len(entry["provider_binding_hmac"]) == 64
            and all(char in "0123456789abcdef" for char in entry["provider_binding_hmac"])
            and type(entry.get("enabled")) is bool
        ):
            raise ReplayAuthorizationError("local channel allowlist entry is invalid")
        expected_binding = provider_binding_hmac(
            identity_key,
            provider=entry["provider"],
            channel_id=entry["channel_id"],
            exporter_id=entry["exporter_id"],
            source_schema=entry["source_schema"],
            authorization_ref_sha256=entry["authorization_ref_sha256"],
            source_slot=entry["source_slot"],
        )
        if not hmac.compare_digest(entry["provider_binding_hmac"], expected_binding):
            raise ReplayAuthorizationError("local channel allowlist binding is invalid")
        expires = _parse_utc(entry.get("not_after"))
        if entry["not_after"].endswith("Z") is False:
            raise ReplayAuthorizationError("local channel allowlist expiry must use UTC Z")
        if entry["provider"] == header["provider"] and entry["channel_id"] == header["channel_id"] and entry["exporter_id"] == header["exporter_id"] and entry["source_schema"] == header["source_schema"] and entry["source_slot"] == profile["source_slot"]:
            matches.append((entry, expires))
    if len(matches) != 1:
        raise ReplayAuthorizationError("local channel allowlist requires exactly one matching entry")
    entry, expires = matches[0]
    if not entry["enabled"] or expires <= now or entry["authorization_ref_sha256"] != consent["provenance_sha256"] or not hmac.compare_digest(entry["provider_binding_hmac"], profile["provider_binding_hmac"]):
        raise ReplayAuthorizationError("local channel allowlist does not authorize this capture")
    return identity_key


def _normalized_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n" for row in rows)


def normalization_receipt_hmac(
    key: bytes,
    normalized: bytes,
    *,
    provider: str,
    source_slot: str,
    phase: str,
    provider_binding: str,
    input_event_count: int,
    output_event_count: int,
) -> str:
    metadata = {
        "provider": provider,
        "source_slot": source_slot,
        "phase": phase,
        "provider_binding_hmac": provider_binding,
        "input_event_count": input_event_count,
        "output_event_count": output_event_count,
    }
    payload = (
        b"airi.authorized-provider-normalization.v1\0"
        + _canonical(metadata) + b"\0" + normalized
    )
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def verify_normalization_receipt(
    normalized_export_path: Path,
    consent_path: Path,
    provenance_path: Path,
    receipt_path: Path,
    identity_key_path: Path,
    *,
    expected_event_count: int,
    now: datetime | None = None,
) -> dict[str, str]:
    normalized = _read_source(normalized_export_path)
    consent = authorize_capture(
        consent_path, normalized_export_path, provenance_path,
        now=now, export_bytes=normalized,
    )
    profile = consent.get("capture_profile")
    if not isinstance(profile, dict):
        raise ReplayAuthorizationError("normalized replay requires consent v2")
    try:
        raw_receipt = receipt_path.read_bytes()
        receipt = json.loads(raw_receipt.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReplayAuthorizationError("normalization receipt is unreadable") from exc
    if (
        not 1 <= len(raw_receipt) <= 64 * 1024
        or not isinstance(receipt, dict)
        or set(receipt) != _RECEIPT_KEYS
        or receipt.get("schema_version") != RECEIPT_SCHEMA
        or receipt.get("provider") not in PROVIDERS
        or receipt.get("source_slot") != profile["source_slot"]
        or receipt.get("phase") != profile["phase"]
        or type(receipt.get("input_event_count")) is not int
        or type(receipt.get("output_event_count")) is not int
        or receipt["input_event_count"] != expected_event_count
        or receipt["output_event_count"] != expected_event_count
        or not isinstance(receipt.get("normalization_hmac_sha256"), str)
        or len(receipt["normalization_hmac_sha256"]) != 64
    ):
        raise ReplayAuthorizationError("normalization receipt is invalid")
    identity_key = read_identity_key(identity_key_path)
    expected = normalization_receipt_hmac(
        identity_key,
        normalized,
        provider=receipt["provider"],
        source_slot=receipt["source_slot"],
        phase=receipt["phase"],
        provider_binding=profile["provider_binding_hmac"],
        input_event_count=receipt["input_event_count"],
        output_event_count=receipt["output_event_count"],
    )
    if not hmac.compare_digest(receipt["normalization_hmac_sha256"], expected):
        raise ReplayAuthorizationError("normalization receipt HMAC is invalid")
    return {"source_slot": profile["source_slot"], "phase": profile["phase"]}


def normalize_authorized_export(
    export_path: Path,
    consent_path: Path,
    provenance_path: Path,
    allowlist_path: Path,
    identity_key_path: Path,
    *,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Return rows, consent rebound to normalized bytes, and a content-free receipt.

    The local allowlist is an operator control, not evidence of issuer identity.
    """
    raw = _read_source(export_path)
    consent = authorize_capture(consent_path, export_path, provenance_path, now=now, export_bytes=raw)
    current = now or datetime.now(timezone.utc)
    records = _load_jsonl(raw)
    provider, channel_id, exporter_id = _validate_header(records[0])
    header = records[0]
    identity_key = _authorize_allowlist(
        allowlist_path, identity_key_path, header, consent, current,
    )
    rows: list[dict[str, Any]] = []
    previous: int | None = None
    kind_map = {"text": "chat", "donation": "donation", "system": "noise"}
    for item in records[1:]:
        if set(item) != _EVENT_KEYS or item.get("record_type") != "event":
            raise ReplayFormatError("authorized export event has unsupported fields")
        if item.get("provider") != provider or item.get("channel_id") != channel_id:
            raise ReplayFormatError("authorized export event identity does not match header")
        timestamp = item.get("occurred_at_ms")
        source_type = item.get("source_type")
        text = item.get("text")
        if not _safe_integer(timestamp) or previous is not None and timestamp < previous or source_type not in SOURCE_TYPES:
            raise ReplayFormatError("authorized export event timing or type is invalid")
        if text is None:
            if source_type == "text":
                raise ReplayFormatError("text events require text")
            model_text = _DONATION_TEXT if source_type == "donation" else _SYSTEM_TEXT
        elif not _safe_string(text, 4_000):
            raise ReplayFormatError("authorized export event text is invalid")
        elif source_type == "donation":
            # The event kind is useful for flow analysis; donor wording, names,
            # amounts, and currency are not required and never reach the model.
            model_text = _DONATION_TEXT
        else:
            model_text = redact_text(
                text,
                [*consent["excluded_creator_names"], channel_id, exporter_id],
            )
        rows.append({"timestamp_ms": timestamp, "kind": kind_map[source_type], "text": model_text})
        previous = timestamp
    normalized = _normalized_bytes(rows)
    derived = dict(consent)
    derived["source_sha256"] = hashlib.sha256(normalized).hexdigest()
    event_count = len(records) - 1
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "provider": provider,
        "source_slot": consent["capture_profile"]["source_slot"],
        "phase": consent["capture_profile"]["phase"],
        "normalization_hmac_sha256": normalization_receipt_hmac(
            identity_key,
            normalized,
            provider=provider,
            source_slot=consent["capture_profile"]["source_slot"],
            phase=consent["capture_profile"]["phase"],
            provider_binding=consent["capture_profile"]["provider_binding_hmac"],
            input_event_count=event_count,
            output_event_count=len(rows),
        ),
        "input_event_count": event_count,
        "output_event_count": len(rows),
    }
    return rows, derived, receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize an explicitly authorized provider-safe export offline.",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--consent", required=True, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--allowlist", required=True, type=Path)
    parser.add_argument("--identity-key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--derived-consent-output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None, *, now: datetime | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    intake = HERE / "local-replay-intake"
    reports = HERE / "reports"
    input_paths = (
        args.input, args.consent, args.provenance, args.allowlist,
        args.identity_key,
    )
    output_paths = (args.output, args.derived_consent_output)
    if any(not _secure_inside(path, intake) for path in input_paths):
        parser.error("all normalizer inputs must stay inside local-replay-intake")
    if any(not _secure_inside(path, intake) for path in output_paths):
        parser.error("normalized export and derived consent must stay inside local-replay-intake")
    if not _secure_inside(args.receipt, reports):
        parser.error("normalization receipt must stay inside the ignored reports directory")
    normalized_inputs = {str(path.absolute()).casefold() for path in input_paths}
    if any(str(path.absolute()).casefold() in normalized_inputs for path in output_paths):
        parser.error("normalizer outputs must not overwrite source custody inputs")
    if str(args.output.absolute()).casefold() == str(args.derived_consent_output.absolute()).casefold():
        parser.error("normalized export and derived consent outputs must differ")
    rows, derived, receipt = normalize_authorized_export(
        args.input, args.consent, args.provenance, args.allowlist,
        args.identity_key, now=now,
    )
    # Individual atomic replacements are fail-closed as a bundle: a partial
    # write cannot pass the derived source hash on a later replay.
    write_atomic_jsonl(args.output, rows, intake)
    write_atomic_json(args.derived_consent_output, derived, intake)
    write_atomic_json(args.receipt, receipt, reports)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
