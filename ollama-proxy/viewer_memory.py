"""Privacy-bounded, opt-in viewer memory storage.

The store accepts only already-pseudonymized transport identifiers.  It never
accepts chat text, raw provider identifiers, donation amounts, or free-form
provenance.  Construction is inert unless ``enabled=True`` and importing this
module creates no database or global runtime object.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import unicodedata
from typing import Any, Iterator


SCHEMA_VERSION = 1
OWNERSHIP_TOKEN = "airi-viewer-memory-dedicated/v1"
SQLITE_BUSY_TIMEOUT_MS = 5_000
MAX_DISPLAY_NAME_CODEPOINTS = 80
MAX_DISPLAY_NAME_HISTORY = 5
MAX_FACT_VALUE_CODEPOINTS = 160
DEFAULT_TIER1_CAP = 20
DEFAULT_TIER2_CAP = 50
DEFAULT_CALLBACK_COOLDOWN_SECONDS = 6 * 60 * 60
DEFAULT_EVENT_RETENTION_SECONDS = 730 * 24 * 60 * 60
DEFAULT_INACTIVE_RETENTION_SECONDS = 365 * 24 * 60 * 60
MAX_FACT_TTL_SECONDS = 90 * 24 * 60 * 60
MAX_FUTURE_SKEW_SECONDS = 30

_TOKEN = r"[A-Za-z0-9_-]{43}"
_VIEWER_KEY = re.compile(rf"^viewer:v1:{_TOKEN}$")
_EVENT_KEY = re.compile(rf"^yt:v1:{_TOKEN}$")
_BROADCAST_KEY = re.compile(rf"^broadcast:v1:{_TOKEN}$")
_BIDI = re.compile("[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f]")
_FACT_TYPES = frozenset({"interest", "status"})
_PROVENANCE = frozenset({"viewer_explicit", "operator_reviewed"})

_DDL = (
    ("table", "viewer_memory_owner", "viewer_memory_owner", """CREATE TABLE viewer_memory_owner (
      singleton INTEGER PRIMARY KEY CHECK(singleton=1), ownership_token TEXT NOT NULL,
      schema_version INTEGER NOT NULL, schema_signature TEXT NOT NULL)"""),
    ("table", "viewer", "viewer", """CREATE TABLE viewer (
      viewer_key TEXT PRIMARY KEY, display_name TEXT NOT NULL, first_seen REAL NOT NULL,
      last_seen REAL NOT NULL, visit_count INTEGER NOT NULL DEFAULT 0 CHECK(visit_count >= 0),
      tier INTEGER NOT NULL DEFAULT 3 CHECK(tier IN (1,2,3)), last_callback_at REAL)"""),
    ("table", "viewer_name", "viewer_name", """CREATE TABLE viewer_name (
      id INTEGER PRIMARY KEY, viewer_key TEXT NOT NULL REFERENCES viewer(viewer_key) ON DELETE CASCADE,
      display_name TEXT NOT NULL, first_seen REAL NOT NULL, last_seen REAL NOT NULL,
      use_count INTEGER NOT NULL DEFAULT 1 CHECK(use_count > 0), UNIQUE(viewer_key, display_name))"""),
    ("table", "visit", "visit", """CREATE TABLE visit (
      viewer_key TEXT NOT NULL REFERENCES viewer(viewer_key) ON DELETE CASCADE, broadcast_key TEXT NOT NULL,
      first_seen REAL NOT NULL, last_seen REAL NOT NULL, event_count INTEGER NOT NULL DEFAULT 1 CHECK(event_count > 0),
      PRIMARY KEY(viewer_key, broadcast_key))"""),
    # Automatic inactivity expiry severs the viewer link but retains the
    # bounded event pseudonym through its longer dedupe window. Explicit
    # deletion removes linked rows first in the same transaction.
    ("table", "observed_event", "observed_event", """CREATE TABLE observed_event (
      event_key TEXT PRIMARY KEY, viewer_key TEXT REFERENCES viewer(viewer_key) ON DELETE SET NULL,
      observation_sha256 TEXT NOT NULL, observed_at REAL NOT NULL)"""),
    ("table", "viewer_fact", "viewer_fact", """CREATE TABLE viewer_fact (
      id INTEGER PRIMARY KEY, viewer_key TEXT NOT NULL REFERENCES viewer(viewer_key) ON DELETE CASCADE,
      fact_type TEXT NOT NULL CHECK(fact_type IN ('interest','status')), value TEXT NOT NULL,
      provenance TEXT NOT NULL CHECK(provenance IN ('viewer_explicit','operator_reviewed')),
      observed_at REAL NOT NULL, expires_at REAL NOT NULL CHECK(expires_at > observed_at), last_callback_at REAL,
      UNIQUE(viewer_key, fact_type, value, provenance, observed_at))"""),
    ("table", "donation_aggregate", "donation_aggregate", """CREATE TABLE donation_aggregate (
      viewer_key TEXT NOT NULL REFERENCES viewer(viewer_key) ON DELETE CASCADE, broadcast_key TEXT NOT NULL,
      event_count INTEGER NOT NULL DEFAULT 0 CHECK(event_count >= 0), last_observed_at REAL NOT NULL,
      PRIMARY KEY(viewer_key, broadcast_key))"""),
    ("index", "ix_viewer_tier", "viewer", "CREATE INDEX ix_viewer_tier ON viewer(tier,last_seen DESC)"),
    ("index", "ix_viewer_name_recent", "viewer_name", "CREATE INDEX ix_viewer_name_recent ON viewer_name(viewer_key,last_seen DESC,id DESC)"),
    ("index", "ix_event_observed", "observed_event", "CREATE INDEX ix_event_observed ON observed_event(observed_at)"),
    ("index", "ix_fact_candidate", "viewer_fact", "CREATE INDEX ix_fact_candidate ON viewer_fact(viewer_key,expires_at,fact_type,observed_at DESC)"),
)


def _canonical_sql(value: str) -> str:
    """Normalize SQL syntax whitespace/case without touching quoted literals."""
    output: list[str] = []
    index = 0
    pending_space = False
    while index < len(value):
        character = value[index]
        if character == "'":
            if pending_space and output and output[-1] not in "(,":
                output.append(" ")
            pending_space = False
            output.append(character)
            index += 1
            while index < len(value):
                output.append(value[index])
                if value[index] == "'":
                    if index + 1 < len(value) and value[index + 1] == "'":
                        output.append(value[index + 1])
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            continue
        if character.isspace():
            pending_space = True
            index += 1
            continue
        if character == ";" and not value[index + 1:].strip():
            index += 1
            continue
        if character in "(),":
            while output and output[-1] == " ":
                output.pop()
            output.append(character)
            pending_space = False
        else:
            if pending_space and output and output[-1] not in "(,":
                output.append(" ")
            output.append(character.casefold())
            pending_space = False
        index += 1
    return "".join(output).strip()


SCHEMA_SIGNATURE = hashlib.sha256(
    "\n".join(f"{kind}:{name}:{table}:{_canonical_sql(sql)}" for kind, name, table, sql in _DDL).encode()
).hexdigest()


@dataclass(frozen=True)
class ViewerObservation:
    event_key: str
    viewer_key: str
    broadcast_key: str
    display_name: str
    observed_at: float
    donation: bool = False

    @classmethod
    def from_wire(cls, record: Any) -> "ViewerObservation":
        """Admit the exact B1a observation sidecar shape, never chat text."""
        expected = {"eventId", "viewerKey", "displayName", "kind", "publishedAtMs", "broadcastKey"}
        if type(record) is not dict or set(record) != expected:
            raise ValueError("wire observation must contain exactly the typed observation keys")
        if record["kind"] != "text":
            raise ValueError("wire observation kind must be text")
        milliseconds = record["publishedAtMs"]
        if (isinstance(milliseconds, bool) or not isinstance(milliseconds, int)
                or milliseconds < 0 or milliseconds > 9_007_199_254_740_991):
            raise ValueError("publishedAtMs must be a non-negative safe integer")
        return cls(
            event_key=record["eventId"], viewer_key=record["viewerKey"],
            broadcast_key=record["broadcastKey"], display_name=record["displayName"],
            observed_at=milliseconds / 1000, donation=False,
        )


@dataclass(frozen=True)
class ViewerFactInput:
    viewer_key: str
    fact_type: str
    value: str
    provenance: str
    observed_at: float
    expires_at: float


@dataclass(frozen=True)
class CallbackCandidate:
    """Untrusted typed data for a future policy/renderer, never prompt-ready text."""

    viewer_key: str
    display_name: str
    fact_id: int
    fact_type: str
    value: str
    provenance: str
    observed_at: float
    expires_at: float


def _key(value: Any, pattern: re.Pattern[str], label: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"{label} must be a versioned 43-character base64url pseudonym")
    return value


def _time(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite non-negative timestamp")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{label} must be a finite non-negative timestamp")
    return result


def _bounded_text(value: Any, maximum: int, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError(f"{label} contains an unpaired Unicode surrogate")
    normalized = " ".join(unicodedata.normalize("NFC", value).strip().split())
    if (not normalized or len(normalized) > maximum or _CONTROL.search(normalized)
            or _BIDI.search(normalized)):
        raise ValueError(f"{label} is empty, unsafe, or exceeds {maximum} code points")
    return normalized


class ViewerMemoryStore:
    """Separate SQLite viewer store. Disabled by default and fail closed."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        enabled: bool = False,
        tier1_cap: int = DEFAULT_TIER1_CAP,
        tier2_cap: int = DEFAULT_TIER2_CAP,
        display_name_history: int = MAX_DISPLAY_NAME_HISTORY,
        callback_cooldown_seconds: float = DEFAULT_CALLBACK_COOLDOWN_SECONDS,
        event_retention_seconds: float = DEFAULT_EVENT_RETENTION_SECONDS,
        inactive_retention_seconds: float = DEFAULT_INACTIVE_RETENTION_SECONDS,
    ):
        self.enabled = enabled is True
        self.path = str(path) if path is not None else ""
        if not self.enabled:
            return
        if not self.path:
            raise ValueError("enabled viewer memory requires a separate database path")
        if type(tier1_cap) is not int or not 10 <= tier1_cap <= 20:
            raise ValueError("tier1_cap must be between 10 and 20")
        if type(tier2_cap) is not int or not 30 <= tier2_cap <= 50:
            raise ValueError("tier2_cap must be between 30 and 50")
        if type(display_name_history) is not int or not 1 <= display_name_history <= 10:
            raise ValueError("display_name_history must be between 1 and 10")
        self.tier_caps = {1: tier1_cap, 2: tier2_cap}
        self.display_name_history = display_name_history
        self.callback_cooldown_seconds = _time(callback_cooldown_seconds, "callback_cooldown_seconds")
        self.event_retention_seconds = _time(event_retention_seconds, "event_retention_seconds")
        self.inactive_retention_seconds = _time(inactive_retention_seconds, "inactive_retention_seconds")
        if self.event_retention_seconds < self.inactive_retention_seconds:
            raise ValueError("event retention must be at least inactive viewer retention")
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        try:
            connection.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error:
            pass
        return connection

    @contextmanager
    def _session(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            if immediate:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        connection = sqlite3.connect(self.path, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
                ).fetchall()
                if existing:
                    self._validate_owned_schema(connection, existing)
                else:
                    for _kind, _name, _table, sql in _DDL:
                        connection.execute(sql)
                    connection.execute(
                        "INSERT INTO viewer_memory_owner(singleton,ownership_token,schema_version,schema_signature) "
                        "VALUES (1,?,?,?)", (OWNERSHIP_TOKEN, SCHEMA_VERSION, SCHEMA_SIGNATURE),
                    )
                    self._validate_owned_schema(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            try:
                connection.execute("PRAGMA journal_mode=WAL")
            except sqlite3.Error:
                pass
        finally:
            connection.close()

    @staticmethod
    def _validate_owned_schema(connection: sqlite3.Connection, rows: Any = None) -> None:
        if rows is None:
            rows = connection.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
            ).fetchall()
        actual = {(row["type"], row["name"], row["tbl_name"]): _canonical_sql(row["sql"] or "") for row in rows}
        expected = {(kind, name, table): _canonical_sql(sql) for kind, name, table, sql in _DDL}
        if actual != expected:
            raise RuntimeError("database is not a pristine dedicated viewer-memory store")
        owner = connection.execute(
            "SELECT singleton,ownership_token,schema_version,schema_signature FROM viewer_memory_owner"
        ).fetchall()
        if len(owner) != 1 or tuple(owner[0]) != (1, OWNERSHIP_TOKEN, SCHEMA_VERSION, SCHEMA_SIGNATURE):
            raise RuntimeError("viewer-memory ownership or schema marker mismatch")

    @staticmethod
    def _observation(observation: ViewerObservation) -> tuple[ViewerObservation, str]:
        if type(observation) is not ViewerObservation:
            raise ValueError("observation must be a ViewerObservation")
        event_key = _key(observation.event_key, _EVENT_KEY, "event_key")
        viewer_key = _key(observation.viewer_key, _VIEWER_KEY, "viewer_key")
        broadcast_key = _key(observation.broadcast_key, _BROADCAST_KEY, "broadcast_key")
        display_name = _bounded_text(observation.display_name, MAX_DISPLAY_NAME_CODEPOINTS, "display_name")
        observed_at = _time(observation.observed_at, "observed_at")
        if type(observation.donation) is not bool:
            raise ValueError("donation must be an explicit boolean")
        normalized = ViewerObservation(event_key, viewer_key, broadcast_key, display_name, observed_at, observation.donation)
        payload = json.dumps(normalized.__dict__, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return normalized, hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def observe(self, observation: ViewerObservation, *, now: float) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled"}
        item, digest = self._observation(observation)
        now = _time(now, "now")
        if item.observed_at > now + MAX_FUTURE_SKEW_SECONDS:
            raise ValueError("observation is too far in the future")
        with self._session(immediate=True) as connection:
            prior = connection.execute(
                "SELECT observation_sha256 FROM observed_event WHERE event_key=?",
                (item.event_key,),
            ).fetchone()
            if prior is not None:
                if prior["observation_sha256"] != digest:
                    raise ValueError("event_key collision with a different observation")
                return {"status": "duplicate", "new_visit": False}

            viewer = connection.execute(
                "SELECT first_seen,last_seen FROM viewer WHERE viewer_key=?", (item.viewer_key,)
            ).fetchone()
            if viewer is None:
                connection.execute(
                    "INSERT INTO viewer(viewer_key,display_name,first_seen,last_seen) VALUES (?,?,?,?)",
                    (item.viewer_key, item.display_name, item.observed_at, item.observed_at),
                )
            else:
                connection.execute(
                    "UPDATE viewer SET display_name=CASE WHEN ? >= last_seen THEN ? ELSE display_name END,"
                    "first_seen=MIN(first_seen,?),last_seen=MAX(last_seen,?) WHERE viewer_key=?",
                    (item.observed_at, item.display_name, item.observed_at, item.observed_at, item.viewer_key),
                )
            connection.execute(
                "INSERT INTO observed_event(event_key,viewer_key,observation_sha256,observed_at) VALUES (?,?,?,?)",
                (item.event_key, item.viewer_key, digest, item.observed_at),
            )
            existing_visit = connection.execute(
                "SELECT 1 FROM visit WHERE viewer_key=? AND broadcast_key=?",
                (item.viewer_key, item.broadcast_key),
            ).fetchone()
            if existing_visit is None:
                connection.execute(
                    "INSERT INTO visit(viewer_key,broadcast_key,first_seen,last_seen,event_count) VALUES (?,?,?,?,1)",
                    (item.viewer_key, item.broadcast_key, item.observed_at, item.observed_at),
                )
                connection.execute("UPDATE viewer SET visit_count=visit_count+1 WHERE viewer_key=?", (item.viewer_key,))
            else:
                connection.execute(
                    "UPDATE visit SET first_seen=MIN(first_seen,?),last_seen=MAX(last_seen,?),event_count=event_count+1 "
                    "WHERE viewer_key=? AND broadcast_key=?",
                    (item.observed_at, item.observed_at, item.viewer_key, item.broadcast_key),
                )
            connection.execute(
                "INSERT INTO viewer_name(viewer_key,display_name,first_seen,last_seen,use_count) VALUES (?,?,?,?,1) "
                "ON CONFLICT(viewer_key,display_name) DO UPDATE SET "
                "first_seen=MIN(first_seen,excluded.first_seen),last_seen=MAX(last_seen,excluded.last_seen),use_count=use_count+1",
                (item.viewer_key, item.display_name, item.observed_at, item.observed_at),
            )
            connection.execute(
                "DELETE FROM viewer_name WHERE viewer_key=? AND id NOT IN "
                "(SELECT id FROM viewer_name WHERE viewer_key=? ORDER BY last_seen DESC,id DESC LIMIT ?)",
                (item.viewer_key, item.viewer_key, self.display_name_history),
            )
            if item.donation:
                connection.execute(
                    "INSERT INTO donation_aggregate(viewer_key,broadcast_key,event_count,last_observed_at) VALUES (?,?,1,?) "
                    "ON CONFLICT(viewer_key,broadcast_key) DO UPDATE SET "
                    "event_count=event_count+1,last_observed_at=MAX(last_observed_at,excluded.last_observed_at)",
                    (item.viewer_key, item.broadcast_key, item.observed_at),
                )
            return {"status": "observed", "new_visit": existing_visit is None}

    def set_tier(self, viewer_key: str, tier: int) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled"}
        viewer_key = _key(viewer_key, _VIEWER_KEY, "viewer_key")
        if type(tier) is not int or tier not in (1, 2, 3):
            raise ValueError("tier must be 1, 2, or 3")
        with self._session(immediate=True) as connection:
            current = connection.execute("SELECT tier FROM viewer WHERE viewer_key=?", (viewer_key,)).fetchone()
            if current is None:
                raise KeyError("unknown viewer")
            if current[0] == tier:
                return {"status": "unchanged", "tier": tier}
            if tier in self.tier_caps:
                count = int(connection.execute("SELECT COUNT(*) FROM viewer WHERE tier=?", (tier,)).fetchone()[0])
                if count >= self.tier_caps[tier]:
                    raise ValueError(f"tier {tier} population cap reached")
            connection.execute("UPDATE viewer SET tier=? WHERE viewer_key=?", (tier, viewer_key))
            return {"status": "updated", "tier": tier}

    def record_fact(self, fact: ViewerFactInput, *, now: float) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "disabled"}
        if type(fact) is not ViewerFactInput:
            raise ValueError("fact must be a ViewerFactInput")
        viewer_key = _key(fact.viewer_key, _VIEWER_KEY, "viewer_key")
        if fact.fact_type not in _FACT_TYPES:
            raise ValueError("fact_type must be interest or status")
        value = _bounded_text(fact.value, MAX_FACT_VALUE_CODEPOINTS, "fact value")
        if fact.provenance not in _PROVENANCE:
            raise ValueError("fact provenance is not an approved explicit source")
        observed_at = _time(fact.observed_at, "observed_at")
        expires_at = _time(fact.expires_at, "expires_at")
        now = _time(now, "now")
        if observed_at > now + MAX_FUTURE_SKEW_SECONDS:
            raise ValueError("fact observation is too far in the future")
        if expires_at <= observed_at:
            raise ValueError("expires_at must be later than observed_at")
        if expires_at - observed_at > MAX_FACT_TTL_SECONDS:
            raise ValueError("fact lifetime must not exceed 90 days")
        with self._session(immediate=True) as connection:
            if not connection.execute("SELECT 1 FROM viewer WHERE viewer_key=?", (viewer_key,)).fetchone():
                raise KeyError("unknown viewer")
            cursor = connection.execute(
                "INSERT OR IGNORE INTO viewer_fact(viewer_key,fact_type,value,provenance,observed_at,expires_at) "
                "VALUES (?,?,?,?,?,?)",
                (viewer_key, fact.fact_type, value, fact.provenance, observed_at, expires_at),
            )
            return {"status": "recorded" if cursor.rowcount == 1 else "duplicate"}

    def claim_callback_candidate(self, viewer_key: str, *, now: float) -> CallbackCandidate | None:
        if not self.enabled:
            return None
        viewer_key = _key(viewer_key, _VIEWER_KEY, "viewer_key")
        now = _time(now, "now")
        cutoff = now - self.callback_cooldown_seconds
        with self._session(immediate=True) as connection:
            viewer = connection.execute(
                "SELECT display_name,last_callback_at FROM viewer WHERE viewer_key=?", (viewer_key,)
            ).fetchone()
            if viewer is None or (viewer["last_callback_at"] is not None and viewer["last_callback_at"] > cutoff):
                return None
            fact = connection.execute(
                "SELECT id,fact_type,value,provenance,observed_at,expires_at FROM viewer_fact "
                "WHERE viewer_key=? AND observed_at<=? AND expires_at>? AND (last_callback_at IS NULL OR last_callback_at<=?) "
                "ORDER BY CASE fact_type WHEN 'interest' THEN 0 ELSE 1 END,observed_at DESC,id DESC LIMIT 1",
                (viewer_key, now, now, cutoff),
            ).fetchone()
            if fact is None:
                return None
            connection.execute("UPDATE viewer SET last_callback_at=? WHERE viewer_key=?", (now, viewer_key))
            connection.execute("UPDATE viewer_fact SET last_callback_at=? WHERE id=?", (now, fact["id"]))
            return CallbackCandidate(
                viewer_key, viewer["display_name"], int(fact["id"]), fact["fact_type"], fact["value"],
                fact["provenance"], float(fact["observed_at"]), float(fact["expires_at"]),
            )

    def delete_viewer(self, viewer_key: str) -> bool:
        if not self.enabled:
            return False
        viewer_key = _key(viewer_key, _VIEWER_KEY, "viewer_key")
        with self._session(immediate=True) as connection:
            exists = connection.execute("SELECT 1 FROM viewer WHERE viewer_key=?", (viewer_key,)).fetchone()
            if exists is None:
                return False
            connection.execute("DELETE FROM observed_event WHERE viewer_key=?", (viewer_key,))
            connection.execute("DELETE FROM viewer WHERE viewer_key=?", (viewer_key,))
            return True

    def prune(self, *, now: float) -> dict[str, int | str]:
        if not self.enabled:
            return {"status": "disabled", "facts": 0, "events": 0, "viewers": 0}
        now = _time(now, "now")
        with self._session(immediate=True) as connection:
            facts = connection.execute("DELETE FROM viewer_fact WHERE expires_at<=?", (now,)).rowcount
            events = connection.execute(
                "DELETE FROM observed_event WHERE observed_at<?", (max(0.0, now - self.event_retention_seconds),)
            ).rowcount
            viewers = connection.execute(
                "DELETE FROM viewer WHERE last_seen<?",
                (max(0.0, now - self.inactive_retention_seconds),),
            ).rowcount
            return {"status": "pruned", "facts": facts, "events": events, "viewers": viewers}

    def health(self) -> dict[str, int | bool]:
        if not self.enabled:
            return {"enabled": False, "ready": False, "schema": 0, "viewers": 0, "visits": 0, "facts": 0, "donations": 0}
        try:
            with self._session() as connection:
                counts = {
                    "viewers": "viewer", "visits": "visit", "facts": "viewer_fact",
                }
                result = {name: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for name, table in counts.items()}
                result["donations"] = int(connection.execute(
                    "SELECT COALESCE(SUM(event_count),0) FROM donation_aggregate"
                ).fetchone()[0])
                return {"enabled": True, "ready": True, "schema": SCHEMA_VERSION, **result}
        except sqlite3.Error:
            return {"enabled": True, "ready": False, "schema": SCHEMA_VERSION, "viewers": 0, "visits": 0, "facts": 0, "donations": 0}
