#!/usr/bin/env python3
"""Prepare an offline, local-only authorization bundle for YouTube capture.

This tool deliberately does not discover broadcasts, contact YouTube, or infer
permission.  It only turns an operator's already-recorded decision and local
custody artifacts into the two documents consumed by the collector/normalizer.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any
import unicodedata

from chat_replay import CAPTURE_PHASES, MAX_REPLAY_EVENTS, SOURCE_SLOTS, _BIDI, _DISALLOWED_CONTROL
from collect_youtube_live_export import AUTH_SCHEMA
from normalize_authorized_export import ALLOWLIST_SCHEMA, provider_binding_hmac
from replay_local_io import HERE, _secure_inside
from youtube_live_capture_contract import SOURCE_SCHEMA


REQUEST_SCHEMA = "airi.youtube-live-capture-preparation-request.v1"
INTAKE = HERE / "local-replay-intake"
AUTHORIZATION_NAME = "capture.authorization.json"
ALLOWLIST_NAME = "provider-channel-allowlist.json"
_REQUEST_KEYS = frozenset({"schema_version", "operator_decision", "capture", "custody"})
_DECISION_KEYS = frozenset({"authorization", "authorization_basis", "authorized_at", "expires_at", "delete_by", "revoked", "purposes"})
_CAPTURE_KEYS = frozenset({"provider", "video_id", "channel_id", "exporter_id", "source_slot", "phase", "duration_seconds", "max_events", "excluded_creator_names"})
_CUSTODY_KEYS = frozenset({"provenance_file", "identity_key_file"})
_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_LOCAL_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_UTC_Z = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z")


class PreparationError(ValueError):
    """A sanitized failure suitable for command-line output."""


def _safe_text(value: Any, maximum: int = 100) -> bool:
    return (
        isinstance(value, str) and 1 <= len(value) <= maximum
        and value == unicodedata.normalize("NFC", value)
        and _BIDI.search(value) is None and _DISALLOWED_CONTROL.search(value) is None
        and all(unicodedata.category(char) not in {"Cc", "Cf", "Cs"} for char in value)
    )


def _parse_z(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or _UTC_Z.fullmatch(value) is None:
        raise PreparationError(f"{field} must use UTC Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise PreparationError(f"{field} is invalid") from None


def _relative_custody_path(value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise PreparationError(f"{field} must be a normalized local custody path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise PreparationError(f"{field} must be a normalized local custody path")
    if not relative.parts or relative.parts[0] != "local-replay-intake":
        raise PreparationError(f"{field} must be under local replay intake")
    candidate = HERE.joinpath(*relative.parts)
    if not _secure_inside(candidate, INTAKE):
        raise PreparationError(f"{field} is unsafe")
    return candidate


def _read_bounded(path: Path, maximum: int, label: str) -> bytes:
    if not _secure_inside(path, INTAKE):
        raise PreparationError(f"{label} is unsafe")
    try:
        size = path.stat().st_size
        if not 1 <= size <= maximum:
            raise PreparationError(f"{label} size is outside the limit")
        raw = path.read_bytes()
    except PreparationError:
        raise
    except OSError:
        raise PreparationError(f"{label} is unreadable") from None
    if len(raw) != size:
        raise PreparationError(f"{label} changed while reading")
    return raw


def _resolve_existing(path: Path, label: str) -> Path:
    if not _secure_inside(path, INTAKE):
        raise PreparationError(f"{label} is unsafe")
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        raise PreparationError(f"{label} is unreadable") from None
    if not _secure_inside(resolved, INTAKE) or not resolved.is_file():
        raise PreparationError(f"{label} is unsafe")
    return resolved


def _require_distinct_files(paths: tuple[Path, str], *others: tuple[Path, str]) -> None:
    all_paths = (paths, *others)
    for index, (path, label) in enumerate(all_paths):
        for other, other_label in all_paths[index + 1:]:
            try:
                same = os.path.samefile(path, other)
            except OSError:
                raise PreparationError("local custody files are unreadable") from None
            if same:
                raise PreparationError(f"{label} and {other_label} must be distinct")


def _load_request(request_path: Path, now: datetime) -> tuple[dict[str, Any], bytes, bytes]:
    raw = _read_bounded(request_path, 64 * 1024, "local request")
    try:
        request = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise PreparationError("local request is invalid") from None
    if not isinstance(request, dict) or set(request) != _REQUEST_KEYS or request.get("schema_version") != REQUEST_SCHEMA:
        raise PreparationError("local request fields are unsupported")
    decision, capture, custody = request.get("operator_decision"), request.get("capture"), request.get("custody")
    if not isinstance(decision, dict) or set(decision) != _DECISION_KEYS or not isinstance(capture, dict) or set(capture) != _CAPTURE_KEYS or not isinstance(custody, dict) or set(custody) != _CUSTODY_KEYS:
        raise PreparationError("local request fields are unsupported")
    if decision.get("authorization") != "authorized" or decision.get("authorization_basis") not in {"creator_or_platform_written_permission", "operator_owned_broadcast"} or decision.get("revoked") is not False or decision.get("purposes") != ["local_replay_evaluation"]:
        raise PreparationError("operator decision is unsupported")
    if capture.get("provider") != "youtube" or capture.get("source_slot") not in SOURCE_SLOTS or capture.get("phase") not in CAPTURE_PHASES or type(capture.get("duration_seconds")) is not int or not 1_800 <= capture["duration_seconds"] <= 7_200 or type(capture.get("max_events")) is not int or not 300 <= capture["max_events"] <= MAX_REPLAY_EVENTS:
        raise PreparationError("capture request is unsupported")
    for field, pattern in (("video_id", _VIDEO_ID), ("channel_id", _LOCAL_ID), ("exporter_id", _LOCAL_ID)):
        if not isinstance(capture.get(field), str) or pattern.fullmatch(capture[field]) is None:
            raise PreparationError("capture identity is invalid")
    names = capture.get("excluded_creator_names")
    if not isinstance(names, list) or not 1 <= len(names) <= 100 or not all(_safe_text(item) for item in names) or len(set(names)) != len(names):
        raise PreparationError("capture redaction terms are invalid")
    authorized_at = _parse_z(decision.get("authorized_at"), "authorized_at")
    expires_at = _parse_z(decision.get("expires_at"), "expires_at")
    delete_by = _parse_z(decision.get("delete_by"), "delete_by")
    end = now + timedelta(seconds=capture["duration_seconds"])
    if authorized_at > now or expires_at <= end or delete_by <= end or delete_by > now + timedelta(days=30):
        raise PreparationError("operator decision does not cover the capture")
    provenance_path = _resolve_existing(
        _relative_custody_path(custody.get("provenance_file"), "provenance_file"),
        "local provenance",
    )
    identity_path = _resolve_existing(
        _relative_custody_path(custody.get("identity_key_file"), "identity_key_file"),
        "local identity key",
    )
    _require_distinct_files((request_path, "local request"), (provenance_path, "local provenance"), (identity_path, "local identity key"))
    provenance = _read_bounded(provenance_path, 1024 * 1024, "local provenance")
    identity_key = _read_bounded(identity_path, 1_024, "local identity key")
    if not 32 <= len(identity_key) <= 1_024:
        raise PreparationError("local identity key is invalid")
    return request, provenance, identity_key


def _write_fsynced_json(path: Path, value: object) -> None:
    encoded = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def _fresh_output(output_dir: Path) -> Path:
    candidate = Path(os.path.abspath(output_dir))
    if candidate.exists() or not _secure_inside(candidate, INTAKE) or candidate == INTAKE:
        raise PreparationError("output directory must be a fresh local intake directory")
    parent = candidate.parent
    if not parent.exists() or not parent.is_dir() or not _secure_inside(parent, INTAKE):
        raise PreparationError("output directory parent is unsafe")
    return candidate


def _create_lock(target: Path) -> Path:
    lock = target.parent / ("." + target.name + ".capture-preparation.lock")
    if not _secure_inside(lock, INTAKE):
        raise PreparationError("output directory parent is unsafe")
    created = False
    try:
        with lock.open("xb") as handle:
            created = True
            handle.write(b"local capture preparation lock\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        raise PreparationError("output directory is already being prepared") from None
    except OSError:
        if created:
            try:
                lock.unlink(missing_ok=True)
            except OSError:
                pass
        raise PreparationError("output directory lock could not be created") from None
    return lock


def prepare_youtube_live_capture(request_path: Path, output_dir: Path, *, now: datetime | None = None) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    """Create the collector authorization and one-entry normalizer allowlist."""
    current = now if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise PreparationError("preparation clock must be UTC")
    request_file = _resolve_existing(Path(os.path.abspath(request_path)), "local request")
    target = _fresh_output(output_dir)
    lock: Path | None = _create_lock(target)
    try:
        request, provenance, identity_key = _load_request(request_file, current)
    except Exception:
        try:
            lock.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    decision, capture = request["operator_decision"], request["capture"]
    provenance_sha256 = hashlib.sha256(provenance).hexdigest()
    binding = provider_binding_hmac(identity_key, provider="youtube", channel_id=capture["channel_id"], exporter_id=capture["exporter_id"], source_schema=SOURCE_SCHEMA, authorization_ref_sha256=provenance_sha256, source_slot=capture["source_slot"])
    authorization = {"schema_version": AUTH_SCHEMA, **decision, "provenance_sha256": provenance_sha256, **capture, "provider_binding_hmac": binding}
    not_after = (
        decision["expires_at"]
        if _parse_z(decision["expires_at"], "expires_at") <= _parse_z(decision["delete_by"], "delete_by")
        else decision["delete_by"]
    )
    allowlist = {"schema_version": ALLOWLIST_SCHEMA, "entries": [{"provider": "youtube", "channel_id": capture["channel_id"], "exporter_id": capture["exporter_id"], "source_schema": SOURCE_SCHEMA, "authorization_ref_sha256": provenance_sha256, "source_slot": capture["source_slot"], "provider_binding_hmac": binding, "not_after": not_after, "enabled": True}]}
    stage: Path | None = None
    try:
        stage = Path(tempfile.mkdtemp(prefix=".capture-preparation-", dir=target.parent))
        if not _secure_inside(stage, INTAKE):
            raise PreparationError("temporary output directory is unsafe")
        _write_fsynced_json(stage / AUTHORIZATION_NAME, authorization)
        _write_fsynced_json(stage / ALLOWLIST_NAME, allowlist)
        _fsync_directory(stage)
        if target.exists() or not _secure_inside(target, INTAKE) or not _secure_inside(stage, INTAKE):
            raise PreparationError("output directory became unsafe")
        os.rename(stage, target)
        stage = None
        try:
            _fsync_directory(target.parent)
        except OSError:
            pass
    except PreparationError:
        raise
    except OSError:
        raise PreparationError("local bundle publication failed") from None
    finally:
        try:
            if stage is not None:
                for name in (AUTHORIZATION_NAME, ALLOWLIST_NAME):
                    try:
                        (stage / name).unlink(missing_ok=True)
                    except Exception:
                        pass
                try:
                    stage.rmdir()
                except Exception:
                    pass
        finally:
            if lock is not None:
                try:
                    lock.unlink(missing_ok=True)
                except Exception:
                    pass
    return target, authorization, allowlist


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare an offline local YouTube capture authorization bundle.")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        prepare_youtube_live_capture(args.request, args.output_dir)
    except PreparationError as exc:
        parser.error(str(exc))
    print("prepared local capture bundle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
