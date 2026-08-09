"""Strict, offline contract shared by the local topic-review tools."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from topic_board import (
    CONTROL_RE, HONORIFIC_ENDING_RE, MAX_BROADCAST_LINE_CHARS, MAX_SUMMARY_CHARS, MAX_TITLE_CHARS,
    SPEAKER_LABEL_RE, TOPIC_ID_RE, UNSAFE_TEXT_RE, _parse_time,
)

TOPIC_REVIEW_ROOT = Path(__file__).resolve().parent / "topic-review"
RUNTIME_ROOT = Path(__file__).resolve().parent / "runtime"
PENDING_FIELDS = {"pending_schema_version", "id", "title", "source", "source_url", "published_at", "summary", "broadcast_line", "expires_at", "review"}
REVIEW_FIELDS = {"status", "reviewer", "reviewed_at"}
DECISION_FIELDS = {"id", "record_sha256", "decision", "source_verified", "published_at_verified", "summary_grounded", "broadcast_line_verified", "expires_at_verified", "notes", "reviewer", "reviewed_at"}
DECISIONS = {"approve", "rewrite", "reject"}
MAX_SOURCE_URL_CHARS = 2048
MAX_REVIEW_TEXT_CHARS = 500


class TopicReviewError(ValueError):
    """A deliberately content-free local review gate failure."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def record_sha256(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(record)).hexdigest()


def _absolute_local(path: str | Path) -> Path:
    raw = str(path).strip()
    if not raw or raw.startswith(("\\\\", "//")):
        raise TopicReviewError("invalid local path")
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise TopicReviewError("invalid local path")
    return candidate


def _under(path: Path, root: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=False))
    except (OSError, RuntimeError, ValueError) as exc:
        raise TopicReviewError("invalid local path") from exc
    return resolved


def review_input_path(path: str | Path) -> Path:
    candidate = _absolute_local(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise TopicReviewError("invalid local file")
    return _under(candidate, TOPIC_REVIEW_ROOT)


def review_output_path(path: str | Path) -> Path:
    candidate = _absolute_local(path)
    parent = candidate.parent
    if parent.is_symlink() or not parent.is_dir():
        raise TopicReviewError("invalid local file")
    try:
        parent.resolve(strict=True).relative_to(TOPIC_REVIEW_ROOT.resolve(strict=False))
    except (OSError, RuntimeError, ValueError) as exc:
        raise TopicReviewError("invalid local path") from exc
    if candidate.exists() and (candidate.is_symlink() or not candidate.is_file()):
        raise TopicReviewError("invalid local file")
    return candidate.resolve(strict=False)


def runtime_output_path(path: str | Path) -> Path:
    candidate = _absolute_local(path)
    parent = candidate.parent
    if parent.is_symlink() or not parent.is_dir():
        raise TopicReviewError("invalid output path")
    try:
        if parent.resolve(strict=True) != RUNTIME_ROOT.resolve(strict=False):
            raise TopicReviewError("invalid output path")
    except (OSError, RuntimeError) as exc:
        raise TopicReviewError("invalid output path") from exc
    if candidate.exists() and (candidate.is_symlink() or not candidate.is_file()):
        raise TopicReviewError("invalid output path")
    return candidate.resolve(strict=False)


def _text(value: Any, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TopicReviewError("invalid text")
    text = value.strip()
    if len(text) > limit or CONTROL_RE.search(text) or UNSAFE_TEXT_RE.search(text):
        raise TopicReviewError("invalid text")
    return text


def _time(value: Any) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise TopicReviewError("invalid time")
    try:
        return _parse_time(value)
    except (TypeError, ValueError) as exc:
        raise TopicReviewError("invalid time") from exc


def _broadcast_line(value: Any, title: str, summary: str) -> str:
    line = _text(value, MAX_BROADCAST_LINE_CHARS)
    if (len(line) < 12 or not re.search(r"[가-힣]", line) or "?" in line
            or not re.search(r"[.!。！]\Z", line) or SPEAKER_LABEL_RE.search(line)
            or HONORIFIC_ENDING_RE.search(line)):
        raise TopicReviewError("invalid broadcast line")
    reference = title + " " + summary
    new_numbers = set(re.findall(r"\d+", line)) - set(re.findall(r"\d+", reference))
    anchors = set(re.findall(r"[가-힣A-Za-z]{3,}|\d+", reference))
    if new_numbers or not any(anchor in line for anchor in anchors):
        raise TopicReviewError("invalid broadcast line")
    return line


def validate_pending_record(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict) or set(row) != PENDING_FIELDS or type(row.get("pending_schema_version")) is not int or row.get("pending_schema_version") != 1:
        raise TopicReviewError("invalid pending record")
    if not isinstance(row["id"], str) or not TOPIC_ID_RE.fullmatch(row["id"]):
        raise TopicReviewError("invalid pending record")
    title = _text(row["title"], MAX_TITLE_CHARS)
    source = _text(row["source"], MAX_TITLE_CHARS)
    source_url = _text(row["source_url"], MAX_SOURCE_URL_CHARS)
    parsed = urlsplit(source_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise TopicReviewError("invalid source url")
    summary = _text(row["summary"], MAX_SUMMARY_CHARS)
    broadcast = _broadcast_line(row["broadcast_line"], title, summary)
    published, expires = _time(row["published_at"]), _time(row["expires_at"])
    if published >= expires:
        raise TopicReviewError("invalid time range")
    if not isinstance(row["review"], dict) or set(row["review"]) != REVIEW_FIELDS or row["review"] != {"status": "pending", "reviewer": "", "reviewed_at": ""}:
        raise TopicReviewError("invalid pending review")
    return {**row, "title": title, "source": source, "source_url": source_url, "summary": summary, "broadcast_line": broadcast}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise TopicReviewError("unreadable local file") from exc
    rows = []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TopicReviewError("invalid jsonl") from exc
        if not isinstance(row, dict):
            raise TopicReviewError("invalid jsonl")
        rows.append(row)
    return rows


def load_pending(path: str | Path) -> list[dict[str, Any]]:
    rows, seen = [], set()
    for raw in read_jsonl(review_input_path(path)):
        row = validate_pending_record(raw)
        if row["id"] in seen:
            raise TopicReviewError("duplicate pending record")
        seen.add(row["id"]); rows.append(row)
    return rows


def validate_decision(row: Any, pending_by_id: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if not isinstance(row, dict) or set(row) != DECISION_FIELDS or row.get("id") not in pending_by_id:
        raise TopicReviewError("invalid decision")
    if not isinstance(row["record_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["record_sha256"]):
        raise TopicReviewError("invalid decision")
    if row["record_sha256"] != record_sha256(pending_by_id[row["id"]]):
        raise TopicReviewError("stale decision")
    if row["decision"] not in DECISIONS or not all(type(row[key]) is bool for key in ("source_verified", "published_at_verified", "summary_grounded", "broadcast_line_verified", "expires_at_verified")):
        raise TopicReviewError("invalid decision")
    notes = row["notes"]
    reviewer = _text(row["reviewer"], MAX_REVIEW_TEXT_CHARS)
    if _time(row["reviewed_at"]) > datetime.now(timezone.utc):
        raise TopicReviewError("invalid decision")
    if not isinstance(notes, str) or len(notes) > MAX_REVIEW_TEXT_CHARS or CONTROL_RE.search(notes) or UNSAFE_TEXT_RE.search(notes):
        raise TopicReviewError("invalid decision")
    if row["decision"] in {"rewrite", "reject"} and not notes.strip():
        raise TopicReviewError("invalid decision")
    if row["decision"] == "approve" and not all(row[key] for key in ("source_verified", "published_at_verified", "summary_grounded", "broadcast_line_verified", "expires_at_verified")):
        raise TopicReviewError("invalid approval")
    return {**row, "reviewer": reviewer, "notes": notes.strip()}


def load_decisions(path: str | Path, pending: Sequence[Mapping[str, Any]], *, allow_missing: bool = False) -> list[dict[str, Any]]:
    try:
        resolved = review_input_path(path)
    except TopicReviewError:
        if allow_missing:
            candidate = review_output_path(path)
            if not candidate.exists():
                return []
        raise
    pending_by_id = {row["id"]: row for row in pending}
    rows, seen = [], set()
    for raw in read_jsonl(resolved):
        row = validate_decision(raw, pending_by_id)
        if row["id"] in seen:
            raise TopicReviewError("duplicate decision")
        seen.add(row["id"]); rows.append(row)
    return rows


def atomic_write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temp = Path(handle.name)
            for row in rows:
                handle.write(canonical_json(row) + b"\n")
            handle.flush(); os.fsync(handle.fileno())
        if review_output_path(path) != path:
            raise TopicReviewError("invalid local path")
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()
