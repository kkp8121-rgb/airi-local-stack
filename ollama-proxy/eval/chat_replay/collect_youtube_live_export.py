#!/usr/bin/env python3
"""Capture an explicitly authorized YouTube live chat into local custody.

The module performs no import-time I/O. Production requests use only the
official YouTube Data API over direct TLS; tests inject an offline transport.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Callable
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

from chat_replay import (
    CAPTURE_PHASES,
    MAX_EXPORT_BYTES,
    MAX_REPLAY_EVENTS,
    MAX_SAFE_INTEGER,
    SOURCE_SLOTS,
    ReplayAuthorizationError,
    ReplayFormatError,
    _BIDI,
    _DISALLOWED_CONTROL,
    _parse_utc,
)
from normalize_authorized_export import provider_binding_hmac, read_identity_key
from replay_local_io import _secure_inside
from youtube_live_capture_contract import (
    MAX_ACTUAL_OVERRUN_MS,
    RECEIPT_SCHEMA,
    SOURCE_SCHEMA,
    receipt_hmac,
    verify_capture_receipt as _verify_capture_receipt,
)


HERE = Path(__file__).resolve().parent
AUTH_SCHEMA = "airi.youtube-live-capture-authorization.v1"
ENVELOPE_SCHEMA = "airi.authorized-provider-export.v1"
API_ORIGIN = "https://www.googleapis.com"
API_PREFIX = "/youtube/v3/"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_BATCHES = 20_000
MAX_PAGE_ITEMS = 200
MAX_PAGE_TOKEN_CHARS = 1_024
MAX_SEEN_IDS = 40_000
MAX_REQUEST_SECONDS = 30.0
MAX_RETRIES_PER_REQUEST = 2
MAX_BACKOFF_SECONDS = 2.0
MAX_WAIT_SLICE_SECONDS = 0.25
MAX_FUTURE_SKEW_MS = 5 * 60 * 1_000

_AUTH_KEYS = frozenset({
    "schema_version", "authorization", "authorization_basis",
    "authorized_at", "expires_at", "delete_by", "revoked", "purposes",
    "provenance_sha256", "provider", "video_id", "channel_id",
    "exporter_id", "source_slot", "phase", "duration_seconds",
    "max_events", "excluded_creator_names", "provider_binding_hmac",
})
_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_LOCAL_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_LOWER_HEX = re.compile(r"[0-9a-f]{64}")
_API_KEY = re.compile(r"[A-Za-z0-9_-]{1,512}")
_DONATION_TYPES = frozenset({
    "fanFundingEvent", "giftEvent", "giftMembershipReceivedEvent",
    "memberMilestoneChatEvent", "membershipGiftingEvent", "newSponsorEvent",
    "superChatEvent", "superStickerEvent",
})


class CaptureError(ReplayAuthorizationError):
    """A sanitized local/provider capture failure."""


class TransientTransportError(CaptureError):
    """A sanitized provider failure that may be retried."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _build_direct_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
    )


_OPENER = _build_direct_opener()


def _safe_text(value: Any, maximum: int = 4_000) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= maximum
        and value == unicodedata.normalize("NFC", value)
        and _BIDI.search(value) is None
        and _DISALLOWED_CONTROL.search(value) is None
        and all(unicodedata.category(char) not in {"Cc", "Cf", "Cs"} for char in value)
    )


def _safe_integer(value: Any, minimum: int = 0, maximum: int = MAX_SAFE_INTEGER) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _read_wall_ms(clock: Callable[[], int]) -> int:
    try:
        value = clock()
    except Exception:
        raise CaptureError("capture wall clock failed") from None
    if not _safe_integer(value):
        raise CaptureError("capture wall clock is invalid")
    return value


def _read_monotonic(clock: Callable[[], float]) -> float:
    try:
        value = clock()
    except Exception:
        raise CaptureError("capture monotonic clock failed") from None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
    ):
        raise CaptureError("capture monotonic clock is invalid")
    return float(value)


def _parse_z(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CaptureError(f"{field} must use UTC Z")
    try:
        return _parse_utc(value)
    except ReplayAuthorizationError:
        raise CaptureError(f"{field} is invalid") from None


def _read_bounded(path: Path, maximum: int, label: str) -> bytes:
    try:
        size = path.stat().st_size
        if not 1 <= size <= maximum:
            raise CaptureError(f"{label} size is outside the limit")
        raw = path.read_bytes()
    except CaptureError:
        raise
    except OSError:
        raise CaptureError(f"{label} is unreadable") from None
    if len(raw) != size:
        raise CaptureError(f"{label} changed while reading")
    return raw


def _load_authorization(
    path: Path,
    provenance_path: Path,
    identity_key: bytes,
    start: datetime,
) -> dict[str, Any]:
    raw = _read_bounded(path, 64 * 1024, "local authorization")
    proof = _read_bounded(provenance_path, 1024 * 1024, "local provenance")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise CaptureError("local authorization is invalid") from None
    if (
        not isinstance(value, dict)
        or set(value) != _AUTH_KEYS
        or value.get("schema_version") != AUTH_SCHEMA
        or value.get("authorization") != "authorized"
        or value.get("authorization_basis") not in {
            "creator_or_platform_written_permission", "operator_owned_broadcast",
        }
        or value.get("revoked") is not False
        or value.get("purposes") != ["local_replay_evaluation"]
        or value.get("provider") != "youtube"
        or value.get("source_slot") not in SOURCE_SLOTS
        or value.get("phase") not in CAPTURE_PHASES
        or not _safe_integer(value.get("duration_seconds"), 1_800, 7_200)
        or not _safe_integer(value.get("max_events"), 300, MAX_REPLAY_EVENTS)
    ):
        raise CaptureError("local authorization fields are unsupported")
    for field, pattern in (
        ("video_id", _VIDEO_ID),
        ("channel_id", _LOCAL_ID),
        ("exporter_id", _LOCAL_ID),
    ):
        if not isinstance(value.get(field), str) or pattern.fullmatch(value[field]) is None:
            raise CaptureError("local authorization identity is invalid")
    excluded = value.get("excluded_creator_names")
    if (
        not isinstance(excluded, list)
        or not 1 <= len(excluded) <= 100
        or not all(_safe_text(item, 100) for item in excluded)
    ):
        raise CaptureError("local redaction terms are invalid")
    provenance_hash = hashlib.sha256(proof).hexdigest()
    if (
        value.get("provenance_sha256") != provenance_hash
        or _LOWER_HEX.fullmatch(value.get("provider_binding_hmac", "")) is None
    ):
        raise CaptureError("local authorization hashes are invalid")
    authorized_at = _parse_z(value.get("authorized_at"), "authorized_at")
    expires_at = _parse_z(value.get("expires_at"), "expires_at")
    delete_by = _parse_z(value.get("delete_by"), "delete_by")
    planned_end = start + timedelta(seconds=value["duration_seconds"])
    if (
        authorized_at > start
        or expires_at <= planned_end
        or delete_by <= planned_end
        or delete_by > start + timedelta(days=30)
    ):
        raise CaptureError("local authorization does not cover the full capture")
    expected = provider_binding_hmac(
        identity_key,
        provider="youtube",
        channel_id=value["channel_id"],
        exporter_id=value["exporter_id"],
        source_schema=SOURCE_SCHEMA,
        authorization_ref_sha256=provenance_hash,
        source_slot=value["source_slot"],
    )
    if not hmac.compare_digest(value["provider_binding_hmac"], expected):
        raise CaptureError("local authorization binding is invalid")
    return value


def _validate_provider_url(url: str) -> None:
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception:
        raise CaptureError("provider URL is invalid") from None
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.googleapis.com"
        or parsed.port not in {None, 443}
        or not parsed.path.startswith(API_PREFIX)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise CaptureError("provider URL is invalid")


def official_fetch_json(url: str, timeout: float) -> dict[str, Any]:
    """Fetch one bounded official response without leaking its credential URL."""
    _validate_provider_url(url)
    try:
        with _OPENER.open(
            urllib.request.Request(url, headers={"Accept": "application/json"}),
            timeout=timeout,
        ) as response:
            if response.geturl() != url:
                raise CaptureError("provider redirect refused")
            status = getattr(response, "status", 200)
            if not _safe_integer(status, 200, 299):
                if status == 429 or 500 <= status <= 599:
                    raise TransientTransportError("provider is temporarily unavailable")
                raise CaptureError("provider request was rejected")
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except (CaptureError, TransientTransportError):
        raise
    except urllib.error.HTTPError as exc:
        try:
            exc.close()
        except Exception:
            pass
        if exc.code == 429 or 500 <= exc.code <= 599:
            raise TransientTransportError("provider is temporarily unavailable") from None
        raise CaptureError("provider request was rejected") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise TransientTransportError("provider transport failed") from None
    except Exception:
        raise CaptureError("provider request failed") from None
    if not isinstance(body, bytes) or len(body) > MAX_RESPONSE_BYTES:
        raise CaptureError("provider response exceeds the limit")
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise CaptureError("provider response is invalid") from None
    if not isinstance(value, dict):
        raise CaptureError("provider response is invalid")
    return value


def _url(endpoint: str, params: dict[str, str]) -> str:
    if endpoint not in {"videos", "liveChat/messages"}:
        raise CaptureError("provider endpoint is invalid")
    return f"{API_ORIGIN}{API_PREFIX}{endpoint}?{urllib.parse.urlencode(params, safe='')}"


def _timestamp_ms(value: Any) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ReplayFormatError("provider timestamp is invalid")
    try:
        parsed = _parse_utc(value)
    except ReplayAuthorizationError:
        raise ReplayFormatError("provider timestamp is invalid") from None
    milliseconds = int(parsed.timestamp() * 1_000)
    if not _safe_integer(milliseconds):
        raise ReplayFormatError("provider timestamp is invalid")
    return milliseconds


def _json_line(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"


def _receipt_hmac(identity_key: bytes, export_bytes: bytes, consent: dict[str, Any], receipt: dict[str, Any]) -> str:
    return receipt_hmac(identity_key, export_bytes, consent, receipt)


def verify_capture_receipt(export_bytes: bytes, consent: dict[str, Any], receipt: dict[str, Any], identity_key: bytes) -> None:
    """Strictly verify the exact minimized export and its consent custody."""
    try:
        _verify_capture_receipt(export_bytes, consent, receipt, identity_key)
    except ReplayAuthorizationError as exc:
        raise CaptureError(str(exc)) from None


def collect_youtube_live_export(
    authorization_path: Path,
    provenance_path: Path,
    identity_key_path: Path,
    api_key_path: Path,
    *,
    fetch_json: Callable[[str, float], dict[str, Any]],
    monotonic: Callable[[], float] = time.monotonic,
    wall_time_ms: Callable[[], int] = lambda: int(time.time() * 1_000),
    sleep: Callable[[float], None] = time.sleep,
    abort_checker: Callable[[], bool] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Capture one complete authorized interval or fail without returning output."""
    start_ms = _read_wall_ms(wall_time_ms)
    started = _read_monotonic(monotonic)
    start = datetime.fromtimestamp(start_ms / 1_000, timezone.utc)
    identity_key = read_identity_key(identity_key_path)
    authorization = _load_authorization(
        authorization_path,
        provenance_path,
        identity_key,
        start,
    )
    api_raw = _read_bounded(api_key_path, 1_024, "local API key")
    try:
        api_key = api_raw.decode("ascii").strip()
    except UnicodeError:
        raise CaptureError("local API key is invalid") from None
    if _API_KEY.fullmatch(api_key) is None:
        raise CaptureError("local API key is invalid")
    deadline = started + authorization["duration_seconds"]
    capture_end_ms = start_ms + authorization["duration_seconds"] * 1_000
    expires_at = _parse_z(authorization["expires_at"], "expires_at")
    delete_by = _parse_z(authorization["delete_by"], "delete_by")
    counters = {"retries": 0}

    def check_active(*, allow_deadline: bool = False) -> float:
        if abort_checker is not None:
            try:
                aborted = abort_checker()
            except Exception:
                raise CaptureError("capture abort check failed") from None
            if type(aborted) is not bool:
                raise CaptureError("capture abort check is invalid")
            if aborted:
                raise CaptureError("capture aborted")
        current_wall = datetime.fromtimestamp(_read_wall_ms(wall_time_ms) / 1_000, timezone.utc)
        if current_wall >= expires_at or current_wall >= delete_by:
            raise CaptureError("capture authorization expired during collection")
        remaining = deadline - _read_monotonic(monotonic)
        if remaining < (-MAX_ACTUAL_OVERRUN_MS / 1_000) or (remaining < 0 and not allow_deadline) or remaining == 0 and not allow_deadline:
            raise CaptureError("capture deadline expired")
        return max(0.0, remaining)

    def wait_bounded(seconds: float) -> None:
        remaining_wait = max(0.0, seconds)
        while remaining_wait > 0:
            remaining = check_active()
            duration = min(remaining_wait, remaining, MAX_WAIT_SLICE_SECONDS)
            if duration <= 0:
                raise CaptureError("capture deadline expired")
            try:
                sleep(duration)
            except Exception:
                raise CaptureError("capture wait failed") from None
            remaining_wait -= duration
        check_active(allow_deadline=True)

    def get(endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        for attempt in range(MAX_RETRIES_PER_REQUEST + 1):
            remaining = check_active()
            url = _url(endpoint, {**params, "key": api_key})
            try:
                response = fetch_json(url, min(MAX_REQUEST_SECONDS, remaining))
            except TransientTransportError:
                if attempt == MAX_RETRIES_PER_REQUEST:
                    raise CaptureError("provider retry limit reached") from None
                counters["retries"] += 1
                wait_bounded(min(2 ** attempt, MAX_BACKOFF_SECONDS))
                continue
            except (CaptureError, ReplayFormatError):
                raise
            except Exception:
                raise CaptureError("provider adapter failed") from None
            check_active(allow_deadline=True)
            if not isinstance(response, dict):
                raise CaptureError("provider response is invalid")
            return response
        raise AssertionError("unreachable retry state")

    video = get("videos", {
        "part": "snippet,liveStreamingDetails",
        "fields": "items(id,snippet/channelId,liveStreamingDetails/activeLiveChatId)",
        "id": authorization["video_id"],
    })
    if set(video) != {"items"} or not isinstance(video["items"], list) or len(video["items"]) != 1:
        raise CaptureError("video response is unsupported")
    video_item = video["items"][0]
    if (
        not isinstance(video_item, dict)
        or set(video_item) != {"id", "snippet", "liveStreamingDetails"}
        or video_item.get("id") != authorization["video_id"]
        or not isinstance(video_item.get("snippet"), dict)
        or set(video_item["snippet"]) != {"channelId"}
        or video_item["snippet"].get("channelId") != authorization["channel_id"]
        or not isinstance(video_item.get("liveStreamingDetails"), dict)
        or set(video_item["liveStreamingDetails"]) != {"activeLiveChatId"}
        or not _safe_text(video_item["liveStreamingDetails"].get("activeLiveChatId"), 256)
    ):
        raise CaptureError("video is not the authorized live broadcast")
    live_chat_id = video_item["liveStreamingDetails"]["activeLiveChatId"]
    header = {
        "record_type": "header",
        "schema_version": ENVELOPE_SCHEMA,
        "provider": "youtube",
        "channel_id": authorization["channel_id"],
        "exporter_id": authorization["exporter_id"],
        "source_schema": SOURCE_SCHEMA,
        "exported_at_ms": start_ms,
    }
    rows = [header]
    encoded_bytes = len(_json_line(header))
    seen: set[str] = set()
    previous_timestamp: int | None = None
    batches = duplicates = prestart = 0
    page_token: str | None = None

    while _read_monotonic(monotonic) < deadline:
        if batches >= MAX_BATCHES:
            raise CaptureError("provider batch limit reached")
        response = get("liveChat/messages", {
            "part": "snippet",
            "fields": (
                "nextPageToken,pollingIntervalMillis,offlineAt,"
                "items(id,snippet(type,publishedAt,textMessageDetails/messageText))"
            ),
            "liveChatId": live_chat_id,
            "maxResults": str(MAX_PAGE_ITEMS),
            **({"pageToken": page_token} if page_token is not None else {}),
        })
        allowed_top = {"items", "pollingIntervalMillis", "nextPageToken", "offlineAt"}
        if (
            not {"items", "pollingIntervalMillis", "nextPageToken"} <= set(response) <= allowed_top
            or response.get("offlineAt") is not None
            or not isinstance(response["items"], list)
            or len(response["items"]) > MAX_PAGE_ITEMS
            or not _safe_integer(response["pollingIntervalMillis"], 0, 60_000)
            or not _safe_text(response["nextPageToken"], MAX_PAGE_TOKEN_CHARS)
        ):
            raise CaptureError("live chat response is unsupported or ended")
        batches += 1
        for message in response["items"]:
            if (
                not isinstance(message, dict)
                or set(message) != {"id", "snippet"}
                or not isinstance(message.get("id"), str)
                or not 1 <= len(message["id"]) <= 256
                or not isinstance(message.get("snippet"), dict)
            ):
                raise CaptureError("live chat message is unsupported")
            message_id = message["id"]
            if message_id in seen:
                duplicates += 1
                continue
            if len(seen) >= MAX_SEEN_IDS:
                raise CaptureError("provider message identity limit reached")
            seen.add(message_id)
            snippet = message["snippet"]
            message_type = snippet.get("type")
            expected_snippet = (
                {"type", "publishedAt", "textMessageDetails"}
                if message_type == "textMessageEvent"
                else {"type", "publishedAt"}
            )
            if set(snippet) != expected_snippet or not isinstance(message_type, str):
                raise CaptureError("live chat snippet is unsupported")
            timestamp = _timestamp_ms(snippet.get("publishedAt"))
            if (
                timestamp > _read_wall_ms(wall_time_ms) + MAX_FUTURE_SKEW_MS
                or previous_timestamp is not None and timestamp < previous_timestamp
            ):
                raise ReplayFormatError("provider timestamps regressed or are future-dated")
            previous_timestamp = timestamp
            if timestamp < start_ms:
                prestart += 1
                continue
            if timestamp > capture_end_ms:
                continue
            if message_type == "textMessageEvent":
                details = snippet["textMessageDetails"]
                if not isinstance(details, dict) or set(details) != {"messageText"}:
                    raise CaptureError("live chat text details are unsupported")
                text = details.get("messageText")
                if not _safe_text(text):
                    raise ReplayFormatError("unsafe provider message text")
                source_type = "text"
            elif message_type in _DONATION_TYPES:
                source_type, text = "donation", None
            else:
                source_type, text = "system", None
            if len(rows) - 1 >= authorization["max_events"]:
                raise CaptureError("event limit reached")
            event = {
                "record_type": "event",
                "provider": "youtube",
                "channel_id": authorization["channel_id"],
                "occurred_at_ms": timestamp,
                "source_type": source_type,
                "text": text,
            }
            encoded_event = _json_line(event)
            if encoded_bytes + len(encoded_event) > MAX_EXPORT_BYTES:
                raise CaptureError("export byte limit reached")
            rows.append(event)
            encoded_bytes += len(encoded_event)
        page_token = response["nextPageToken"]
        remaining = max(0.0, deadline - _read_monotonic(monotonic))
        wait_bounded(min(response["pollingIntervalMillis"] / 1_000, remaining))

    check_active(allow_deadline=True)
    if len(rows) - 1 < 300:
        raise CaptureError("capture has fewer than 300 events")
    export_bytes = b"".join(_json_line(row) for row in rows)
    actual_duration_ms = int((_read_monotonic(monotonic) - started) * 1_000)
    if not authorization["duration_seconds"] * 1_000 <= actual_duration_ms <= authorization["duration_seconds"] * 1_000 + MAX_ACTUAL_OVERRUN_MS:
        raise CaptureError("capture scheduler exceeded the permitted final overrun")
    consent = {
        "schema_version": "airi.chat-replay-consent.v2",
        "authorization": "authorized",
        "authorization_basis": authorization["authorization_basis"],
        "authorized_at": authorization["authorized_at"],
        "purposes": ["local_replay_evaluation"],
        "expires_at": authorization["expires_at"],
        "delete_by": authorization["delete_by"],
        "revoked": False,
        "source_sha256": hashlib.sha256(export_bytes).hexdigest(),
        "provenance_sha256": authorization["provenance_sha256"],
        "excluded_creator_names": authorization["excluded_creator_names"],
        "capture_profile": {
            "source_slot": authorization["source_slot"],
            "phase": authorization["phase"],
            "provider_binding_hmac": authorization["provider_binding_hmac"],
        },
    }
    counts = {
        source_type: sum(row.get("source_type") == source_type for row in rows[1:])
        for source_type in ("text", "donation", "system")
    }
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "complete",
        "requested_duration_seconds": authorization["duration_seconds"],
        "actual_duration_ms": actual_duration_ms,
        "event_count": len(rows) - 1,
        "source_type_counts": counts,
        "batches": batches,
        "retries": counters["retries"],
        "duplicates": duplicates,
        "prestart": prestart,
        "invalid": 0,
        "bundle_hmac_sha256": "",
    }
    receipt["bundle_hmac_sha256"] = _receipt_hmac(identity_key, export_bytes, consent, receipt)
    verify_capture_receipt(export_bytes, consent, receipt, identity_key)
    return rows, consent, receipt


def _commit_bundle(entries: list[tuple[Path, bytes, Path]]) -> None:
    """Stage every payload and roll back ordinary replacement failures."""
    staged: list[tuple[Path, Path, Path]] = []
    backups: list[tuple[Path, Path | None]] = []
    try:
        for target, payload, parent in entries:
            if not 1 <= len(payload) <= MAX_EXPORT_BYTES or not _secure_inside(target, parent):
                raise CaptureError("unsafe output payload or path")
            target.parent.mkdir(parents=True, exist_ok=True)
            if not _secure_inside(target, parent):
                raise CaptureError("output path became unsafe")
            with tempfile.NamedTemporaryFile("wb", dir=target.parent, delete=False) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            staged.append((target, temporary, parent))
        for target, temporary, parent in staged:
            if not _secure_inside(target, parent):
                raise CaptureError("output path became unsafe")
            backup: Path | None = None
            if target.exists():
                with tempfile.NamedTemporaryFile("wb", dir=target.parent, delete=False) as handle:
                    backup = Path(handle.name)
                os.replace(target, backup)
            backups.append((target, backup))
            os.replace(temporary, target)
    except Exception:
        for target, backup in reversed(backups):
            try:
                target.unlink(missing_ok=True)
                if backup is not None:
                    os.replace(backup, target)
            except OSError:
                pass
        raise
    finally:
        for _, temporary, _ in staged:
            temporary.unlink(missing_ok=True)
        for _, backup in backups:
            if backup is not None:
                backup.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture one explicitly authorized YouTube live interval.",
    )
    parser.add_argument("--authorization", required=True, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--identity-key", required=True, type=Path)
    parser.add_argument("--api-key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--consent-output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    intake = HERE / "local-replay-intake"
    reports = HERE / "reports"
    input_paths = (
        args.authorization, args.provenance, args.identity_key, args.api_key,
    )
    output_paths = (args.output, args.consent_output)
    if any(not _secure_inside(path, intake) for path in (*input_paths, *output_paths)):
        parser.error("capture inputs and private outputs must stay in local-replay-intake")
    if not _secure_inside(args.receipt, reports):
        parser.error("capture receipt must stay in the ignored reports directory")
    all_paths = (*input_paths, *output_paths, args.receipt)
    if len({str(path.absolute()).casefold() for path in all_paths}) != len(all_paths):
        parser.error("capture paths must not collide")
    rows, consent, receipt = collect_youtube_live_export(
        *input_paths,
        fetch_json=official_fetch_json,
    )
    export_bytes = b"".join(_json_line(row) for row in rows)
    consent_bytes = (
        json.dumps(consent, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    receipt_bytes = (
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    identity_key = read_identity_key(args.identity_key)
    verify_capture_receipt(export_bytes, consent, receipt, identity_key)
    _commit_bundle([
        (args.output, export_bytes, intake),
        (args.consent_output, consent_bytes, intake),
        (args.receipt, receipt_bytes, reports),
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
