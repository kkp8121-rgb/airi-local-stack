"""SQLite persistence for the AIRI memory layer.

Schema is the tech reference §3 table set (memory / fact_subject /
extraction_job) plus the two additions the proxy needs to actually run it:

- `conversation_turn` - the turns the `extracted_up_to_msg` watermark points
  into. The reference assumed the host app already owned a chat message table;
  this proxy has none, so the watermark needs its own queue to advance over.
- `memory.is_true` - the rag_cache epistemic firewall (audit §3-2). Retrieval
  filters it at the query level rather than trusting a prompt to do it.

Everything is standard-library sqlite3 in WAL mode. Connections are
thread-local because retrieval runs in a worker thread (asyncio.to_thread) so
the caller can put a hard timebox on it.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

KIND_ENTITY = "entity"
KIND_FACT = "fact"
KIND_RELATION = "relation"
CONFIDENCE_VALUES = ("knows", "heard", "believes")
STATUS_ACTIVE = "active"
STATUS_SUPERSEDED = "superseded"

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS memory (
      id INTEGER PRIMARY KEY,
      session_id TEXT,
      source TEXT,
      kind TEXT,
      subtype TEXT,
      name TEXT,
      content TEXT NOT NULL,
      source_id INTEGER,
      target_id INTEGER,
      confidence TEXT DEFAULT 'knows',
      heard_from INTEGER,
      turn_range_start INTEGER,
      turn_range_end INTEGER,
      story_day INTEGER,
      time_of_day TEXT,
      status TEXT DEFAULT 'active',
      superseded_by INTEGER,
      content_hash TEXT,
      vector BLOB,
      is_true INTEGER DEFAULT 1,
      created_at REAL
    )
    """,
    "CREATE TABLE IF NOT EXISTS fact_subject (fact_id INTEGER, entity_id INTEGER)",
    """
    CREATE TABLE IF NOT EXISTS extraction_job (
      session_id TEXT PRIMARY KEY,
      extracted_up_to_msg INTEGER DEFAULT 0,
      pending_msgs INTEGER DEFAULT 0,
      fail_count INTEGER DEFAULT 0,
      last_error TEXT,
      last_extraction_ts REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_turn (
      id INTEGER PRIMARY KEY,
      session_id TEXT,
      user_text TEXT,
      assistant_text TEXT,
      created_at REAL
    )
    """,
    "CREATE INDEX IF NOT EXISTS memory_lookup ON memory (session_id, kind, subtype, status)",
    "CREATE INDEX IF NOT EXISTS memory_hash ON memory (content_hash)",
    "CREATE INDEX IF NOT EXISTS fact_subject_fact ON fact_subject (fact_id)",
    "CREATE INDEX IF NOT EXISTS fact_subject_entity ON fact_subject (entity_id)",
    "CREATE INDEX IF NOT EXISTS conversation_turn_session ON conversation_turn (session_id, id)",
)

# Columns added after the first release. Older files are upgraded in place so a
# restart never has to drop memories to pick up a schema change.
ADDED_COLUMNS = {
    "memory": (("is_true", "INTEGER DEFAULT 1"), ("created_at", "REAL")),
    "extraction_job": (("last_extraction_ts", "REAL"),),
}


def content_hash(kind: str, subtype: str, name: str, content: str) -> str:
    """Stable identity of one memory item - the reference's single truth for dedup."""
    payload = "|".join(
        part.strip() for part in (kind or "", subtype or "", name or "", content or "")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class MemoryStore:
    """Thread-local sqlite3 handles over one memory database file."""

    def __init__(self, db_path: Path | str, *, busy_timeout_ms: int = 3000) -> None:
        self.db_path = Path(db_path)
        self.busy_timeout_ms = busy_timeout_ms
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ setup

    def connect(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            return connection
        if self.db_path.parent and str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False so shutdown can close a connection that a
        # retrieval worker thread opened; each thread still gets its own handle.
        connection = sqlite3.connect(
            str(self.db_path),
            timeout=self.busy_timeout_ms / 1000.0,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(f"PRAGMA busy_timeout = {int(self.busy_timeout_ms)}")
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.Error:
            # A read-only volume or an in-memory database cannot do WAL; the
            # layer still works, it just loses the concurrency headroom.
            pass
        self._local.connection = connection
        with self._lock:
            self._connections.append(connection)
        return connection

    def ensure_schema(self) -> None:
        """Idempotent migration: safe to run on every boot, old files included."""
        connection = self.connect()
        with connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            for table, columns in ADDED_COLUMNS.items():
                existing = {
                    row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
                }
                for column, declaration in columns:
                    if column not in existing:
                        connection.execute(
                            f"ALTER TABLE {table} ADD COLUMN {column} {declaration}"
                        )

    def close(self) -> None:
        with self._lock:
            connections, self._connections = self._connections, []
        for connection in connections:
            try:
                connection.close()
            except sqlite3.Error:
                pass
        self._local = threading.local()

    # ----------------------------------------------------------------- writes

    def insert_memory(
        self,
        *,
        session_id: str | None,
        source: str,
        kind: str,
        subtype: str,
        content: str,
        name: str | None = None,
        source_ref: int | None = None,
        target_ref: int | None = None,
        confidence: str = "knows",
        heard_from: int | None = None,
        turn_range: tuple[int | None, int | None] = (None, None),
        story_day: int | None = None,
        time_of_day: str | None = None,
        is_true: bool = True,
        vector: bytes | None = None,
    ) -> tuple[int, bool]:
        """Insert one row. Returns (row id, inserted) - False means hash dedup hit."""
        digest = content_hash(kind, subtype, name or "", content)
        connection = self.connect()
        existing = connection.execute(
            "SELECT id FROM memory WHERE content_hash = ? AND status = ? "
            "AND (session_id IS ? OR session_id = ?) LIMIT 1",
            (digest, STATUS_ACTIVE, session_id, session_id),
        ).fetchone()
        if existing is not None:
            return int(existing["id"]), False
        if confidence not in CONFIDENCE_VALUES:
            confidence = "knows"
        with connection:
            cursor = connection.execute(
                "INSERT INTO memory (session_id, source, kind, subtype, name, content, "
                "source_id, target_id, confidence, heard_from, turn_range_start, "
                "turn_range_end, story_day, time_of_day, status, superseded_by, "
                "content_hash, vector, is_true, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    session_id,
                    source,
                    kind,
                    subtype,
                    name,
                    content,
                    source_ref,
                    target_ref,
                    confidence,
                    heard_from,
                    turn_range[0],
                    turn_range[1],
                    story_day,
                    time_of_day,
                    STATUS_ACTIVE,
                    None,
                    digest,
                    vector,
                    1 if is_true else 0,
                    time.time(),
                ),
            )
        return int(cursor.lastrowid), True

    def update_memory(
        self,
        row_id: int,
        *,
        content: str | None = None,
        subtype: str | None = None,
        name: str | None = None,
        vector: bytes | None = None,
        turn_range: tuple[int | None, int | None] | None = None,
    ) -> None:
        connection = self.connect()
        row = connection.execute("SELECT * FROM memory WHERE id = ?", (row_id,)).fetchone()
        if row is None:
            return
        new_content = content if content is not None else row["content"]
        new_subtype = subtype if subtype is not None else row["subtype"]
        new_name = name if name is not None else row["name"]
        digest = content_hash(row["kind"], new_subtype or "", new_name or "", new_content)
        start, end = (
            turn_range if turn_range is not None
            else (row["turn_range_start"], row["turn_range_end"])
        )
        with connection:
            connection.execute(
                "UPDATE memory SET content = ?, subtype = ?, name = ?, content_hash = ?, "
                "vector = ?, turn_range_start = ?, turn_range_end = ? WHERE id = ?",
                (
                    new_content,
                    new_subtype,
                    new_name,
                    digest,
                    vector if vector is not None else row["vector"],
                    start,
                    end,
                    row_id,
                ),
            )

    def supersede(self, row_id: int, replacement_id: int | None = None) -> None:
        """History-preserving delete: the row stays, it just stops being active."""
        connection = self.connect()
        with connection:
            connection.execute(
                "UPDATE memory SET status = ?, superseded_by = ? WHERE id = ?",
                (STATUS_SUPERSEDED, replacement_id, row_id),
            )

    def link_fact_subject(self, fact_id: int, entity_id: int) -> None:
        connection = self.connect()
        with connection:
            connection.execute(
                "INSERT INTO fact_subject (fact_id, entity_id) "
                "SELECT ?, ? WHERE NOT EXISTS "
                "(SELECT 1 FROM fact_subject WHERE fact_id = ? AND entity_id = ?)",
                (fact_id, entity_id, fact_id, entity_id),
            )

    # ------------------------------------------------------------ turn queue

    def append_turn(self, session_id: str, user_text: str, assistant_text: str) -> int:
        connection = self.connect()
        with connection:
            cursor = connection.execute(
                "INSERT INTO conversation_turn (session_id, user_text, assistant_text, created_at)"
                " VALUES (?,?,?,?)",
                (session_id, user_text, assistant_text, time.time()),
            )
            connection.execute(
                "INSERT INTO extraction_job (session_id, extracted_up_to_msg, pending_msgs) "
                "VALUES (?, 0, 0) ON CONFLICT(session_id) DO NOTHING",
                (session_id,),
            )
            connection.execute(
                "UPDATE extraction_job SET pending_msgs = pending_msgs + 1 WHERE session_id = ?",
                (session_id,),
            )
        return int(cursor.lastrowid)

    def job(self, session_id: str) -> sqlite3.Row | None:
        return self.connect().execute(
            "SELECT * FROM extraction_job WHERE session_id = ?", (session_id,)
        ).fetchone()

    def watermark(self, session_id: str) -> int:
        row = self.job(session_id)
        return int(row["extracted_up_to_msg"]) if row is not None else 0

    def pending_turns(self, session_id: str, limit: int = 200) -> list[sqlite3.Row]:
        return list(
            self.connect().execute(
                "SELECT * FROM conversation_turn WHERE session_id = ? AND id > ? "
                "ORDER BY id ASC LIMIT ?",
                (session_id, self.watermark(session_id), limit),
            )
        )

    def latest_turn_id(self, session_id: str) -> int:
        row = self.connect().execute(
            "SELECT MAX(id) AS last FROM conversation_turn WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["last"]) if row is not None and row["last"] is not None else 0

    def advance_watermark(self, session_id: str, up_to: int) -> None:
        connection = self.connect()
        with connection:
            connection.execute(
                "INSERT INTO extraction_job (session_id, extracted_up_to_msg) VALUES (?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET extracted_up_to_msg = excluded.extracted_up_to_msg",
                (session_id, up_to),
            )
            connection.execute(
                "UPDATE extraction_job SET fail_count = 0, last_error = NULL, "
                "last_extraction_ts = ?, pending_msgs = "
                "(SELECT COUNT(*) FROM conversation_turn WHERE session_id = ? AND id > ?) "
                "WHERE session_id = ?",
                (time.time(), session_id, up_to, session_id),
            )

    def record_failure(self, session_id: str, error: str) -> int:
        """Leave the watermark alone so the batch retries; count the attempt."""
        connection = self.connect()
        with connection:
            connection.execute(
                "INSERT INTO extraction_job (session_id, fail_count, last_error) VALUES (?, 1, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET fail_count = fail_count + 1, "
                "last_error = excluded.last_error",
                (session_id, error[:500]),
            )
        row = self.job(session_id)
        return int(row["fail_count"]) if row is not None else 1

    # ------------------------------------------------------------------ reads

    def active_rows(
        self,
        session_id: str | None,
        *,
        kind: str | None = None,
        subtypes: Sequence[str] | None = None,
        exclude_subtypes: Sequence[str] | None = None,
    ) -> list[sqlite3.Row]:
        """Active, truthful rows in session scope (session rows + global canon).

        `is_true = 0` is filtered here rather than downstream: the epistemic
        firewall is a query-level guarantee, not a prompt instruction.
        """
        clauses = ["status = ?", "COALESCE(is_true, 1) != 0", "(session_id IS NULL OR session_id = ?)"]
        params: list[object] = [STATUS_ACTIVE, session_id]
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if subtypes:
            clauses.append(f"subtype IN ({','.join('?' * len(subtypes))})")
            params.extend(subtypes)
        if exclude_subtypes:
            clauses.append(f"COALESCE(subtype, '') NOT IN ({','.join('?' * len(exclude_subtypes))})")
            params.extend(exclude_subtypes)
        return list(
            self.connect().execute(
                f"SELECT * FROM memory WHERE {' AND '.join(clauses)} ORDER BY id DESC", params
            )
        )

    def entity_names(self, session_id: str | None) -> list[sqlite3.Row]:
        return list(
            self.connect().execute(
                "SELECT id, name FROM memory WHERE kind = ? AND status = ? "
                "AND COALESCE(is_true, 1) != 0 AND name IS NOT NULL AND name != '' "
                "AND (session_id IS NULL OR session_id = ?)",
                (KIND_ENTITY, STATUS_ACTIVE, session_id),
            )
        )

    def find_entity(self, session_id: str | None, name: str) -> sqlite3.Row | None:
        return self.connect().execute(
            "SELECT * FROM memory WHERE kind = ? AND status = ? AND name = ? "
            "AND (session_id IS NULL OR session_id = ?) ORDER BY id DESC LIMIT 1",
            (KIND_ENTITY, STATUS_ACTIVE, name, session_id),
        ).fetchone()

    def relations_for(
        self, session_id: str | None, entity_ids: Iterable[int], limit: int
    ) -> list[sqlite3.Row]:
        ids = [int(value) for value in entity_ids]
        if not ids or limit <= 0:
            return []
        placeholders = ",".join("?" * len(ids))
        return list(
            self.connect().execute(
                f"SELECT * FROM memory WHERE kind = ? AND status = ? AND COALESCE(is_true, 1) != 0 "
                f"AND (session_id IS NULL OR session_id = ?) "
                f"AND (source_id IN ({placeholders}) OR target_id IN ({placeholders})) "
                f"ORDER BY id DESC LIMIT ?",
                (KIND_RELATION, STATUS_ACTIVE, session_id, *ids, *ids, limit),
            )
        )

    def facts_for_subjects(
        self, session_id: str | None, entity_ids: Iterable[int], limit: int
    ) -> list[sqlite3.Row]:
        ids = [int(value) for value in entity_ids]
        if not ids or limit <= 0:
            return []
        placeholders = ",".join("?" * len(ids))
        return list(
            self.connect().execute(
                f"SELECT m.* FROM memory m JOIN fact_subject fs ON fs.fact_id = m.id "
                f"WHERE m.kind = ? AND m.status = ? AND COALESCE(m.is_true, 1) != 0 "
                f"AND (m.session_id IS NULL OR m.session_id = ?) "
                f"AND fs.entity_id IN ({placeholders}) "
                f"GROUP BY m.id ORDER BY m.id DESC LIMIT ?",
                (KIND_FACT, STATUS_ACTIVE, session_id, *ids, limit),
            )
        )

    def stats(self) -> dict[str, object]:
        connection = self.connect()
        rows = connection.execute(
            "SELECT COUNT(*) AS total FROM memory WHERE status = ?", (STATUS_ACTIVE,)
        ).fetchone()
        pending = connection.execute(
            "SELECT COUNT(*) AS pending FROM conversation_turn ct "
            "LEFT JOIN extraction_job ej ON ej.session_id = ct.session_id "
            "WHERE ct.id > COALESCE(ej.extracted_up_to_msg, 0)"
        ).fetchone()
        last = connection.execute(
            "SELECT MAX(last_extraction_ts) AS ts FROM extraction_job"
        ).fetchone()
        return {
            "rows": int(rows["total"]) if rows is not None else 0,
            "pending_jobs": int(pending["pending"]) if pending is not None else 0,
            "last_extraction_ts": (last["ts"] if last is not None else None),
        }
