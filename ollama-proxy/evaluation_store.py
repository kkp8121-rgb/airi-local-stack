"""Explicit-consent, local-only storage for human evaluation records.

This module deliberately has no model, network, or logging dependencies.  It is
an audit/review queue, not a training pipeline.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = 1
RATINGS = frozenset(("good", "bad", "revise"))
ORIGINS = frozenset(("synthetic", "user_approved"))
REVIEW_STATUSES = frozenset(("needs_review", "approved", "rejected"))
REASON_TAGS = frozenset((
    "persona_drift", "honorific", "repeat", "memory_error", "tool_lie",
    "too_long", "no_response", "safety", "other",
))
MAX_MESSAGES = 64
MAX_TEXT = 16_000
MAX_PROMPT_HASH = 256
MAX_PAYLOAD_BYTES = 128_000
MAX_EXPORT_RECORDS = 1_000
DEFAULT_MAX_RECORDS = 10_000
MAX_CONFIGURED_RECORDS = 1_000_000


class EvaluationStoreError(Exception):
    """A safe failure from the optional evaluation subsystem."""


class EvaluationValidationError(EvaluationStoreError):
    """Input was not acceptable for local evaluation storage."""


class EvaluationDisabledError(EvaluationStoreError):
    """Evaluation collection was not explicitly enabled."""


@dataclass(frozen=True)
class EvaluationConfig:
    enabled: bool = False
    db_path: str = "runtime/airi-evaluations.sqlite3"
    max_records: int = DEFAULT_MAX_RECORDS

    @classmethod
    def from_env(cls) -> "EvaluationConfig":
        # Only this exact spelling opts collection in; values such as "1" are
        # intentionally not sufficient to enable retention of conversations.
        raw_max_records = os.environ.get("AIRI_EVAL_MAX_RECORDS", str(DEFAULT_MAX_RECORDS))
        try:
            max_records = int(raw_max_records)
        except ValueError as exc:
            raise EvaluationStoreError("Evaluation store configuration is invalid.") from exc
        if not 1 <= max_records <= MAX_CONFIGURED_RECORDS:
            raise EvaluationStoreError("Evaluation store configuration is invalid.")
        return cls(
            enabled=os.environ.get("AIRI_EVAL_ENABLED", "").strip().lower() == "true",
            db_path=os.environ.get("AIRI_EVAL_DB", "runtime/airi-evaluations.sqlite3"),
            max_records=max_records,
        )


def _fail() -> None:
    # Never interpolate user-supplied text into an exception: callers may log it.
    raise EvaluationValidationError("Invalid evaluation record.")


def _text(value: Any, *, limit: int = MAX_TEXT, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        _fail()
    return value


def _messages(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value or len(value) > MAX_MESSAGES:
        _fail()
    clean: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping) or item.get("role") not in {"user", "assistant"}:
            _fail()
        # Copy only the permitted representation: identifiers/tool data cannot
        # accidentally be persisted or exported through this API.
        clean.append({"role": item["role"], "content": _text(item.get("content"))})
    return clean


def _tags(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > len(REASON_TAGS):
        _fail()
    if any(not isinstance(tag, str) or tag not in REASON_TAGS for tag in value):
        _fail()
    return sorted(set(value))


def _provenance(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("origin") not in ORIGINS:
        _fail()
    model = _text(value.get("model"), limit=512)
    model_version = _text(value.get("model_version"), limit=512)
    prompt_hash = _text(value.get("system_prompt_sha256"), limit=MAX_PROMPT_HASH)
    memory_version = value.get("memory_schema_version")
    if not isinstance(memory_version, int) or isinstance(memory_version, bool) or memory_version < 0:
        _fail()
    dataset_version = _text(value.get("dataset_version"), limit=256)
    return {
        "origin": value["origin"], "model": model, "model_version": model_version,
        "system_prompt_sha256": prompt_hash, "memory_schema_version": memory_version,
        "dataset_version": dataset_version,
    }


class EvaluationStore:
    """Thread-safe SQLite implementation; each operation has its own connection."""

    def __init__(self, config: EvaluationConfig | None = None):
        self.config = config or EvaluationConfig.from_env()
        if (
            not isinstance(self.config.max_records, int)
            or isinstance(self.config.max_records, bool)
            or not 1 <= self.config.max_records <= MAX_CONFIGURED_RECORDS
        ):
            raise EvaluationStoreError("Evaluation store configuration is invalid.")
        self._lock = threading.RLock()
        if self.config.enabled:
            try:
                Path(self.config.db_path).parent.mkdir(parents=True, exist_ok=True)
                with self._db() as db:
                    db.execute("CREATE TABLE IF NOT EXISTS evaluation_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                    row = db.execute("SELECT value FROM evaluation_meta WHERE key = 'schema_version'").fetchone()
                    if row is None:
                        db.execute("INSERT INTO evaluation_meta(key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
                    elif row[0] != str(SCHEMA_VERSION):
                        raise EvaluationStoreError("Evaluation store schema is unsupported.")
                    db.execute("""CREATE TABLE IF NOT EXISTS evaluation_records (
                        id TEXT PRIMARY KEY, created_at TEXT NOT NULL, kind TEXT NOT NULL,
                        review_status TEXT NOT NULL, data_json TEXT NOT NULL
                    )""")
                    db.execute("CREATE INDEX IF NOT EXISTS evaluation_records_review ON evaluation_records(review_status, created_at, id)")
            except EvaluationStoreError:
                raise
            except (OSError, sqlite3.Error) as exc:
                raise EvaluationStoreError("Evaluation store is unavailable.") from exc

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.config.db_path, timeout=5, isolation_level="DEFERRED")

    @contextmanager
    def _db(self, *, immediate: bool = False) -> Any:
        """Commit/rollback and close every connection, including on Windows."""
        connection = self._connect()
        try:
            with connection:
                if immediate:
                    connection.execute("BEGIN IMMEDIATE")
                yield connection
        finally:
            connection.close()

    def _enabled(self) -> None:
        if not self.config.enabled:
            raise EvaluationDisabledError("Evaluation collection is disabled.")

    def _add(self, kind: str, payload: Mapping[str, Any], provenance: Mapping[str, Any]) -> dict[str, str]:
        self._enabled()
        if not isinstance(payload, Mapping) or payload.get("consent") is not True:
            _fail()
        reason_tags = _tags(payload.get("reason_tags", []))
        data: dict[str, Any] = {
            "messages": _messages(payload.get("messages")), "reason_tags": reason_tags,
            "provenance": _provenance(provenance),
        }
        if kind == "rating":
            rating = payload.get("rating")
            if rating not in RATINGS:
                _fail()
            correction = _text(payload.get("correction"), required=False)
            if rating == "revise" and correction is None:
                _fail()
            if rating in {"bad", "revise"} and not reason_tags:
                _fail()
            data.update({"response": _text(payload.get("response")), "rating": rating, "correction": correction})
        else:
            if not reason_tags:
                _fail()
            data.update({"chosen": _text(payload.get("chosen")), "rejected": _text(payload.get("rejected"))})
            if data["chosen"] == data["rejected"]:
                _fail()
        encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            _fail()
        record_id, created_at = str(uuid.uuid4()), datetime.now(timezone.utc).isoformat(timespec="microseconds")
        try:
            with self._lock, self._db(immediate=True) as db:
                count = db.execute("SELECT COUNT(*) FROM evaluation_records").fetchone()[0]
                if count >= self.config.max_records:
                    raise EvaluationStoreError("Evaluation store capacity is full.")
                db.execute("INSERT INTO evaluation_records VALUES (?, ?, ?, ?, ?)",
                           (record_id, created_at, kind, "needs_review", encoded))
        except EvaluationStoreError:
            raise
        except sqlite3.Error as exc:
            raise EvaluationStoreError("Evaluation store write failed.") from exc
        return {"id": record_id, "status": "needs_review"}

    def add_rating(self, payload: Mapping[str, Any], provenance: Mapping[str, Any]) -> dict[str, str]:
        return self._add("rating", payload, provenance)

    def add_preference(self, payload: Mapping[str, Any], provenance: Mapping[str, Any]) -> dict[str, str]:
        return self._add("preference", payload, provenance)

    def review(self, record_id: str, status: str) -> dict[str, str]:
        self._enabled()
        if not isinstance(record_id, str) or not _is_uuid(record_id) or status not in REVIEW_STATUSES - {"needs_review"}:
            _fail()
        try:
            with self._lock, self._db() as db:
                row = db.execute("SELECT review_status FROM evaluation_records WHERE id = ?", (record_id,)).fetchone()
                if row is None:
                    raise EvaluationValidationError("Evaluation record was not found.")
                if row[0] != "needs_review":
                    raise EvaluationValidationError("Evaluation record review transition is invalid.")
                db.execute("UPDATE evaluation_records SET review_status = ? WHERE id = ?", (status, record_id))
        except EvaluationStoreError:
            raise
        except sqlite3.Error as exc:
            raise EvaluationStoreError("Evaluation store review failed.") from exc
        return {"id": record_id, "status": status}

    def delete(self, record_id: str) -> bool:
        self._enabled()
        if not isinstance(record_id, str) or not _is_uuid(record_id):
            _fail()
        try:
            with self._lock, self._db() as db:
                return db.execute("DELETE FROM evaluation_records WHERE id = ?", (record_id,)).rowcount == 1
        except sqlite3.Error as exc:
            raise EvaluationStoreError("Evaluation store delete failed.") from exc

    def export_records(self, approved_only: bool = True, limit: int = MAX_EXPORT_RECORDS,
                       offset: int = 0) -> list[dict[str, Any]]:
        self._enabled()
        if (not isinstance(approved_only, bool)
                or not isinstance(limit, int) or isinstance(limit, bool)
                or not 1 <= limit <= MAX_EXPORT_RECORDS
                or not isinstance(offset, int) or isinstance(offset, bool)
                or not 0 <= offset <= 1_000_000):
            _fail()
        query = "SELECT id, created_at, kind, review_status, data_json FROM evaluation_records"
        args: tuple[Any, ...] = ()
        if approved_only:
            query += " WHERE review_status = ?"
            args = ("approved",)
        # UUID order is random when a test clock or coarse external source
        # gives multiple records the same timestamp. SQLite rowid preserves
        # the transaction insertion order and makes paged exports repeatable.
        query += " ORDER BY created_at ASC, rowid ASC LIMIT ? OFFSET ?"
        args += (limit, offset)
        try:
            with self._lock, self._db() as db:
                rows = db.execute(query, args).fetchall()
        except sqlite3.Error as exc:
            raise EvaluationStoreError("Evaluation store export failed.") from exc
        return [{"id": row[0], "created_at": row[1], "kind": row[2], "review_status": row[3], **json.loads(row[4])} for row in rows]

    def health(self) -> dict[str, Any]:
        if not self.config.enabled:
            return {"enabled": False, "schema_version": SCHEMA_VERSION, "counts": {}}
        try:
            with self._lock, self._db() as db:
                counts = {status: 0 for status in sorted(REVIEW_STATUSES)}
                for status, count in db.execute("SELECT review_status, COUNT(*) FROM evaluation_records GROUP BY review_status"):
                    counts[status] = count
            return {
                "enabled": True,
                "schema_version": SCHEMA_VERSION,
                "counts": counts,
                "total": sum(counts.values()),
                "max_records": self.config.max_records,
            }
        except sqlite3.Error as exc:
            raise EvaluationStoreError("Evaluation store health check failed.") from exc


class NullEvaluationStore:
    """Drop-in disabled store, useful when the optional feature is not configured."""

    def _disabled(self, *args: Any, **kwargs: Any) -> Any:
        raise EvaluationDisabledError("Evaluation collection is disabled.")

    add_rating = _disabled
    add_preference = _disabled
    review = _disabled
    delete = _disabled
    export_records = _disabled

    def health(self) -> dict[str, Any]:
        return {"enabled": False, "schema_version": SCHEMA_VERSION, "counts": {}}


def _is_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value.lower()
    except (ValueError, AttributeError):
        return False
