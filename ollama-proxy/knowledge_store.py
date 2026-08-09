"""Local, approved-only knowledge retrieval, separate from personal memory."""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

MAX_CONTENT_CHARS = 24_000
MAX_QUERY_CHARS = 800
MAX_METADATA_CHARS = 300
MAX_ANSWER_SUMMARY_CHARS = 400
MAX_ALIASES = 16
CHUNK_CHARS = 700
CHUNK_OVERLAP = 100
_BIDI = re.compile(r"[\u202a-\u202e\u2066-\u2069]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INJECTION = re.compile(r"(?:ignore\s+(?:all\s+)?previous|system\s+prompt|developer\s+message|<\|(?:act|call|delay)|jailbreak)", re.I)
Embedder = Callable[[str], Sequence[float]]

# These are deliberately limited to common grammatical particles/endings.  We
# retain the original token too, so names and short words are never discarded.
_KOREAN_SUFFIXES = (
    "에게서는", "한테서는", "으로서는", "에서는", "으로는", "에게는",
    "한테는", "에서도", "으로도", "로서는", "로는", "에는", "와는",
    "과는", "으로", "에서", "에게", "한테", "들의", "은", "는", "이",
    "가", "을", "를", "의", "에", "와", "과", "도", "만", "로", "며",
    "다", "요",
)
_QUERY_STOP_TERMS = frozenset({
    "뭐", "무엇", "무슨", "어떤", "어떻게", "왜", "보통", "하는", "하며",
    "있는", "있어", "거야", "게임이야", "말고", "공식", "서비스", "게임",
    "정보", "사실", "하나", "알려", "설명",
})


def _tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    result: list[str] = []
    for token in re.findall(r"[0-9a-z가-힣]+", normalized):
        result.append(token)
        if any("가" <= char <= "힣" for char in token):
            # Korean particles can be layered (for example ``게임에서는``).
            # Keep the literal word and add at most two conservative stems so
            # FTS can match a title/alias written without the particle.
            stem = token
            for _ in range(2):
                suffix = next((item for item in _KOREAN_SUFFIXES
                               if stem.endswith(item) and len(stem) - len(item) >= 2), None)
                if suffix is None:
                    break
                stem = stem[:-len(suffix)]
                result.append(stem)
    return list(dict.fromkeys(result))


def _search_text(title: str, source: str, content: str, aliases: Sequence[str] = (), answer_summary: str | None = None) -> str:
    """Raw fields plus normalized lexical variants for FTS5's CJK tokenizer."""
    raw = f"{title} {' '.join(aliases)} {source} {answer_summary or ''} {content}"
    return " ".join(_tokens(raw))


def _aliases(value: Any) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, (list, tuple)) or len(value) > MAX_ALIASES:
        raise KnowledgeInputError("aliases must be a bounded list")
    cleaned = tuple(_clean(item, field="alias", limit=80) for item in value)
    if len(set(alias.casefold() for alias in cleaned)) != len(cleaned):
        raise KnowledgeInputError("aliases must be unique")
    return cleaned


def _stored_aliases(value: Any) -> tuple[str, ...]:
    try:
        parsed = json.loads(str(value or "[]"))
        return tuple(item for item in parsed if isinstance(item, str)) if isinstance(parsed, list) else ()
    except json.JSONDecodeError:
        return ()


def _fts_or_query(terms: Sequence[str]) -> str:
    # Terms originate from our unicode tokenization; quotes prevent FTS syntax
    # from turning a user query into operators or column selectors.
    return " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)


class KnowledgeInputError(ValueError):
    """An unapproved or unsafe local knowledge record."""


def runtime_path(path: str | Path, runtime_dir: str | Path) -> Path:
    """Resolve a local path and require it to remain directly under runtime_dir."""
    raw = str(path)
    if raw.startswith("\\\\") or raw.startswith("//"):
        raise KnowledgeInputError("UNC paths are not allowed")
    root = Path(runtime_dir).resolve()
    candidate = Path(path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise KnowledgeInputError("path must be inside the configured runtime directory") from exc
    return candidate


def _clean(value: Any, *, field: str, limit: int) -> str:
    if not isinstance(value, str):
        raise KnowledgeInputError(f"{field} must be text")
    text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text or len(text) > limit or _BIDI.search(text) or _CONTROL.search(text) or _INJECTION.search(text):
        raise KnowledgeInputError(f"unsafe or invalid {field}")
    return text


def _optional_timestamp(value: Any, field: str) -> str | None:
    if value in (None, ""):
        return None
    text = _clean(value, field=field, limit=64)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KnowledgeInputError(f"invalid {field}") from exc
    return text


def validate_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the compact approved JSON schema without retaining raw input."""
    if not isinstance(raw, Mapping):
        raise KnowledgeInputError("record must be an object")
    if raw.get("approved") is not True:
        raise KnowledgeInputError("record must set approved: true")
    content = _clean(raw.get("content"), field="content", limit=MAX_CONTENT_CHARS)
    supplied_hash = raw.get("content_sha256")
    if supplied_hash not in (None, ""):
        if not isinstance(supplied_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", supplied_hash):
            raise KnowledgeInputError("invalid content_sha256")
        actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if supplied_hash.casefold() != actual_hash:
            raise KnowledgeInputError("content_sha256 does not match content")
    return {
        "source": _clean(raw.get("source"), field="source", limit=MAX_METADATA_CHARS),
        "title": _clean(raw.get("title"), field="title", limit=MAX_METADATA_CHARS),
        "aliases": _aliases(raw.get("aliases")),
        "answer_summary": None if raw.get("answer_summary") is None else _clean(raw.get("answer_summary"), field="answer_summary", limit=MAX_ANSWER_SUMMARY_CHARS),
        "version": _clean(str(raw.get("version", "unknown")), field="version", limit=MAX_METADATA_CHARS),
        "published_at": _optional_timestamp(raw.get("published_at"), "published_at"),
        # This is the date our local summary was checked, not an assertion
        # about when the remote source was published.
        "reviewed_at": _optional_timestamp(raw.get("reviewed_at"), "reviewed_at"),
        "expires_at": _optional_timestamp(raw.get("expires_at"), "expires_at"),
        "provenance": _clean(raw.get("provenance", "local-approved"), field="provenance", limit=MAX_METADATA_CHARS),
        "content": content,
    }


def chunk_text(content: str) -> list[str]:
    """Deterministically normalize and overlap bounded chunks."""
    normalized = re.sub(r"[ \t]+", " ", content)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if len(normalized) <= CHUNK_CHARS:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + CHUNK_CHARS, len(normalized))
        if end < len(normalized):
            boundary = max(normalized.rfind("\n", start + CHUNK_CHARS // 2, end), normalized.rfind(" ", start + CHUNK_CHARS // 2, end))
            if boundary > start:
                end = boundary
        chunks.append(normalized[start:end].strip())
        if end == len(normalized):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


@dataclass(frozen=True)
class KnowledgeHit:
    source: str
    title: str
    version: str
    published_at: str | None
    provenance: str
    content: str
    score: float
    # Appended defaults retain compatibility with callers using the original
    # seven positional fields while exposing why a result was selected.
    method: str = "lexical"
    matched_terms: tuple[str, ...] = ()
    lexical_score: float | None = None
    semantic_score: float | None = None
    answer_summary: str | None = None
    reviewed_at: str | None = None


class KnowledgeStore:
    """Separate SQLite/FTS5 store for approved public/topic knowledge only."""

    def __init__(self, db_path: str | Path, *, runtime_dir: str | Path, embedder: Embedder | None = None):
        self.runtime_dir = Path(runtime_dir).resolve()
        self.db_path = runtime_path(db_path, self.runtime_dir)
        self.embedder = embedder

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _db(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._db() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY, source TEXT NOT NULL, title TEXT NOT NULL, version TEXT NOT NULL,
                published_at TEXT, reviewed_at TEXT, expires_at TEXT, content_hash TEXT NOT NULL, provenance TEXT NOT NULL,
                aliases TEXT NOT NULL DEFAULT '[]', answer_summary TEXT, updated_at TEXT NOT NULL, UNIQUE(source, title)
              );
              CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                ordinal INTEGER NOT NULL, content TEXT NOT NULL, embedding_json TEXT, UNIQUE(document_id, ordinal)
              );
              CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(content, chunk_id UNINDEXED);
              CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts_v2 USING fts5(
                title, source, content, search_text, chunk_id UNINDEXED
              );
              CREATE INDEX IF NOT EXISTS chunks_document_ordinal ON chunks(document_id, ordinal);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(documents)")}
            if "aliases" not in columns:
                db.execute("ALTER TABLE documents ADD COLUMN aliases TEXT NOT NULL DEFAULT '[]'")
            if "answer_summary" not in columns:
                db.execute("ALTER TABLE documents ADD COLUMN answer_summary TEXT")
            if "reviewed_at" not in columns:
                db.execute("ALTER TABLE documents ADD COLUMN reviewed_at TEXT")
            # Keep the original content-only FTS table untouched: it may be
            # used by a previous runtime.  This table is reconstructible from
            # the authoritative documents/chunks tables and backfills v1 DBs.
            missing = db.execute("""SELECT c.id,c.content,d.title,d.source,d.aliases,d.answer_summary FROM chunks c
                JOIN documents d ON d.id=c.document_id
                WHERE NOT EXISTS (SELECT 1 FROM chunks_fts_v2 f WHERE f.chunk_id=CAST(c.id AS TEXT))""").fetchall()
            for row in missing:
                db.execute("INSERT INTO chunks_fts_v2(title,source,content,search_text,chunk_id) VALUES (?,?,?,?,?)",
                           (row["title"], row["source"], row["content"], _search_text(row["title"], row["source"], row["content"], _stored_aliases(row["aliases"]), row["answer_summary"]), str(row["id"])))

    @staticmethod
    def _embedding(embedder: Embedder | None, text: str) -> list[float] | None:
        if embedder is None:
            return None
        try:
            vector = [float(value) for value in embedder(text)]
            return vector if vector and all(math.isfinite(value) for value in vector) else None
        except Exception:
            return None

    def ingest(self, raw: Mapping[str, Any]) -> str:
        record = validate_record(raw)
        self.initialize()
        digest = hashlib.sha256(record["content"].encode("utf-8")).hexdigest()
        aliases_json = json.dumps(record["aliases"], ensure_ascii=False)
        now = datetime.now(timezone.utc).isoformat()
        chunks = chunk_text(record["content"])
        with self._db() as db:
            old = db.execute("SELECT * FROM documents WHERE source=? AND title=?", (record["source"], record["title"])).fetchone()
            if old and old["content_hash"] == digest:
                unchanged = (
                    old["version"] == record["version"]
                    and old["published_at"] == record["published_at"]
                    and old["reviewed_at"] == record["reviewed_at"]
                    and old["expires_at"] == record["expires_at"]
                    and old["provenance"] == record["provenance"]
                    and old["aliases"] == aliases_json
                    and old["answer_summary"] == record["answer_summary"]
                )
                if unchanged:
                    return "duplicate"
                db.execute(
                    "UPDATE documents SET version=?,published_at=?,reviewed_at=?,expires_at=?,provenance=?,aliases=?,answer_summary=?,updated_at=? WHERE id=?",
                    (record["version"], record["published_at"], record["reviewed_at"], record["expires_at"], record["provenance"], aliases_json, record["answer_summary"], now, old["id"]),
                )
                indexed = db.execute("SELECT id,content FROM chunks WHERE document_id=? ORDER BY ordinal", (old["id"],)).fetchall()
                for row in indexed:
                    db.execute("DELETE FROM chunks_fts_v2 WHERE chunk_id=?", (str(row["id"]),))
                    db.execute(
                        "INSERT INTO chunks_fts_v2(title,source,content,search_text,chunk_id) VALUES (?,?,?,?,?)",
                        (record["title"], record["source"], row["content"], _search_text(record["title"], record["source"], row["content"], record["aliases"], record["answer_summary"]), str(row["id"])),
                    )
                return "updated"
            if old:
                ids = [row[0] for row in db.execute("SELECT id FROM chunks WHERE document_id=?", (old["id"],))]
                for chunk_id in ids:
                    db.execute("DELETE FROM chunks_fts WHERE chunk_id=?", (str(chunk_id),))
                    db.execute("DELETE FROM chunks_fts_v2 WHERE chunk_id=?", (str(chunk_id),))
                db.execute("DELETE FROM chunks WHERE document_id=?", (old["id"],))
                db.execute("UPDATE documents SET version=?, published_at=?, reviewed_at=?, expires_at=?, content_hash=?, provenance=?, aliases=?, answer_summary=?, updated_at=? WHERE id=?",
                           (record["version"], record["published_at"], record["reviewed_at"], record["expires_at"], digest, record["provenance"], aliases_json, record["answer_summary"], now, old["id"]))
                document_id, status = int(old["id"]), "updated"
            else:
                cursor = db.execute("INSERT INTO documents(source,title,version,published_at,reviewed_at,expires_at,content_hash,provenance,aliases,answer_summary,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                    (record["source"], record["title"], record["version"], record["published_at"], record["reviewed_at"], record["expires_at"], digest, record["provenance"], aliases_json, record["answer_summary"], now))
                document_id, status = int(cursor.lastrowid), "inserted"
            for ordinal, content in enumerate(chunks):
                embedding = self._embedding(self.embedder, content)
                cursor = db.execute("INSERT INTO chunks(document_id,ordinal,content,embedding_json) VALUES (?,?,?,?)",
                                    (document_id, ordinal, content, json.dumps(embedding) if embedding is not None else None))
                db.execute("INSERT INTO chunks_fts(content,chunk_id) VALUES (?,?)", (content, str(cursor.lastrowid)))
                db.execute("INSERT INTO chunks_fts_v2(title,source,content,search_text,chunk_id) VALUES (?,?,?,?,?)",
                           (record["title"], record["source"], content, _search_text(record["title"], record["source"], content, record["aliases"], record["answer_summary"]), str(cursor.lastrowid)))
        return status

    @staticmethod
    def _active_clause() -> str:
        return "(d.expires_at IS NULL OR d.expires_at > ?)"

    def _retrieve_legacy(self, query: str, *, top_k: int = 4, max_chars: int = 1600) -> list[KnowledgeHit]:
        if not 1 <= top_k <= 20 or not 64 <= max_chars <= 12_000:
            raise ValueError("invalid retrieval limits")
        query = _clean(query, field="query", limit=MAX_QUERY_CHARS)
        self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        hits: dict[int, tuple[sqlite3.Row, float]] = {}
        terms = " ".join(re.findall(r"[\w가-힣]{2,}", query))
        if terms:
            try:
                with self._db() as db:
                    rows = db.execute(f"SELECT c.*,d.source,d.title,d.version,d.published_at,d.reviewed_at,d.provenance,bm25(chunks_fts) AS rank FROM chunks_fts JOIN chunks c ON c.id=CAST(chunks_fts.chunk_id AS INTEGER) JOIN documents d ON d.id=c.document_id WHERE chunks_fts MATCH ? AND {self._active_clause()} ORDER BY rank LIMIT ?", (terms, now, top_k * 3)).fetchall()
                    for row in rows:
                        hits[int(row["id"])] = (row, 1.0 / (1.0 + abs(float(row["rank"]))))
            except sqlite3.Error:
                pass
        # FTS5's built-in tokenizer does not segment every CJK word. Keep FTS5
        # as the primary lexical index and use this bounded local fallback only
        # when it produced no candidates.
        if not hits:
            with self._db() as db:
                rows = db.execute(f"SELECT c.*,d.source,d.title,d.version,d.published_at,d.reviewed_at,d.provenance FROM chunks c JOIN documents d ON d.id=c.document_id WHERE instr(c.content, ?) > 0 AND {self._active_clause()} ORDER BY c.id LIMIT ?", (query, now, top_k * 3)).fetchall()
            for row in rows:
                hits[int(row["id"])] = (row, 0.5)
        query_vector = self._embedding(self.embedder, query)
        if query_vector is not None:
            with self._db() as db:
                rows = db.execute(f"SELECT c.*,d.source,d.title,d.version,d.published_at,d.reviewed_at,d.provenance FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.embedding_json IS NOT NULL AND {self._active_clause()}", (now,)).fetchall()
            for row in rows:
                try:
                    vector = json.loads(row["embedding_json"])
                    dot = sum(a * b for a, b in zip(query_vector, vector))
                    norm = math.sqrt(sum(a * a for a in query_vector) * sum(b * b for b in vector))
                    score = dot / norm if norm else 0.0
                    if score > 0:
                        previous = hits.get(int(row["id"]))
                        hits[int(row["id"])] = (row, max(score, previous[1] if previous else 0.0))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
        selected: list[KnowledgeHit] = []
        used = 0
        for row, score in sorted(hits.values(), key=lambda item: (-item[1], item[0]["id"])):
            remaining = max_chars - used
            if remaining < 32:
                break
            content = row["content"][:remaining].rstrip()
            selected.append(KnowledgeHit(row["source"], row["title"], row["version"], row["published_at"], row["provenance"], content, round(score, 6), reviewed_at=row["reviewed_at"]))
            used += len(content)
            if len(selected) >= top_k:
                break
        return selected

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 4,
        max_chars: int = 1600,
        allow_semantic: bool = True,
    ) -> list[KnowledgeHit]:
        if not 1 <= top_k <= 20 or not 64 <= max_chars <= 12_000:
            raise ValueError("invalid retrieval limits")
        query = _clean(query, field="query", limit=MAX_QUERY_CHARS)
        self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        # One-character Korean particles/counters are extremely common and
        # cannot identify a document.  Treating ``한`` alone as lexical proof
        # previously routed an unrelated desk scene to a game summary.
        terms = [
            term for term in _tokens(query)
            if len(term) >= 2 and term not in _QUERY_STOP_TERMS
        ]
        lexical: dict[int, tuple[sqlite3.Row, float, tuple[str, ...]]] = {}
        if terms:
            try:
                with self._db() as db:
                    rows = db.execute(f"""SELECT c.*,d.source,d.title,d.version,d.published_at,d.reviewed_at,d.provenance,d.aliases,d.answer_summary,
                        bm25(chunks_fts_v2,4.0,2.0,1.0,0.5) AS rank FROM chunks_fts_v2
                        JOIN chunks c ON c.id=CAST(chunks_fts_v2.chunk_id AS INTEGER)
                        JOIN documents d ON d.id=c.document_id
                        WHERE chunks_fts_v2 MATCH ? AND {self._active_clause()} ORDER BY rank ASC LIMIT ?""",
                        (_fts_or_query(terms), now, top_k * 8)).fetchall()
                for row in rows:
                    aliases = _stored_aliases(row["aliases"])
                    all_terms = set(_tokens(f"{row['title']} {' '.join(aliases)} {row['source']} {row['answer_summary'] or ''} {row['content']}"))
                    matched = tuple(term for term in terms if term in all_terms)
                    if not matched:
                        continue
                    coverage = len(matched) / len(terms)
                    title_terms = set(_tokens(f"{row['title']} {' '.join(aliases)} {row['source']}"))
                    content_terms = set(_tokens(row["content"]))
                    title_matched = tuple(term for term in matched if term in title_terms)
                    # A reviewed title/alias/source anchor is authoritative.
                    # Otherwise require two distinct informative terms from
                    # the content; one generic word is not enough to select a
                    # pre-written answer_summary that bypasses generation.
                    if not title_matched and len(set(matched)) < 2:
                        continue
                    placement = sum(1.0 if term in title_terms else .45 if term in content_terms else .15 for term in matched) / len(terms)
                    # FTS5 BM25 is lower-is-better (normally negative here).
                    # Convert its magnitude to a monotonic positive tie-break:
                    # a more negative/better rank must receive a larger bonus.
                    bm25_strength = max(0.0, -float(row["rank"]))
                    bm25_score = bm25_strength / (1.0 + bm25_strength)
                    lexical[int(row["id"])] = (row, coverage * 3 + placement + bm25_score * .1, matched)
            except sqlite3.Error:
                pass
        # Exact substring fallback covers legacy databases/text created with a
        # tokenizer that cannot represent the query script.  It is deliberately
        # exact (not a broad scan score), so generic queries do not gain noise.
        if not lexical:
            with self._db() as db:
                rows = db.execute(f"SELECT c.*,d.source,d.title,d.version,d.published_at,d.reviewed_at,d.provenance,d.answer_summary FROM chunks c JOIN documents d ON d.id=c.document_id WHERE (instr(c.content,?)>0 OR instr(d.title,?)>0 OR instr(d.source,?)>0 OR instr(d.answer_summary,?)>0) AND {self._active_clause()} ORDER BY c.id LIMIT ?", (query, query, query, query, now, top_k * 3)).fetchall()
            for row in rows:
                lexical[int(row["id"])] = (row, 1.0, (query,))
        semantic: dict[int, tuple[sqlite3.Row, float]] = {}
        # Lexical evidence is authoritative and the runtime accepts only its
        # top result. Avoid an unnecessary GPU embedding call once such an
        # anchor exists; this also keeps foreground chat out of model queues.
        query_vector = None if lexical or not allow_semantic else self._embedding(self.embedder, query)
        if query_vector is not None:
            with self._db() as db:
                rows = db.execute(f"SELECT c.*,d.source,d.title,d.version,d.published_at,d.reviewed_at,d.provenance,d.answer_summary FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.embedding_json IS NOT NULL AND {self._active_clause()}", (now,)).fetchall()
            for row in rows:
                try:
                    vector = json.loads(row["embedding_json"])
                    norm = math.sqrt(sum(a*a for a in query_vector) * sum(b*b for b in vector))
                    score = sum(a*b for a, b in zip(query_vector, vector)) / norm if norm else 0.0
                    if score > 0 and int(row["id"]) not in lexical:
                        semantic[int(row["id"])] = (row, score)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
        ranked = [(row, score, "lexical", matched, score, None) for row, score, matched in sorted(lexical.values(), key=lambda x: (-x[1], x[0]["id"]))]
        ranked += [(row, score, "semantic", (), None, score) for row, score in sorted(semantic.values(), key=lambda x: (-x[1], x[0]["id"]))]
        selected: list[KnowledgeHit] = []
        used = 0
        for row, score, method, matched, lexical_score, semantic_score in ranked:
            remaining = max_chars - used
            if remaining < 32:
                break
            content = row["content"][:remaining].rstrip()
            selected.append(KnowledgeHit(row["source"], row["title"], row["version"], row["published_at"], row["provenance"], content, round(score, 6), method, matched, lexical_score, semantic_score, row["answer_summary"], row["reviewed_at"]))
            used += len(content)
            if len(selected) >= top_k:
                break
        return selected

    def health(self) -> dict[str, int | bool]:
        """Privacy-safe health; never includes source names, paths, or content."""
        try:
            self.initialize()
            with self._db() as db:
                return {"ok": True, "documents": int(db.execute("SELECT count(*) FROM documents").fetchone()[0]),
                        "chunks": int(db.execute("SELECT count(*) FROM chunks").fetchone()[0]), "semantic": bool(self.embedder)}
        except sqlite3.Error:
            return {"ok": False, "documents": 0, "chunks": 0, "semantic": bool(self.embedder)}

    def reindex_missing(self, limit: int = 128) -> int:
        """Bounded local backfill for chunks ingested before an embedder existed."""
        if self.embedder is None or not 1 <= limit <= 512:
            return 0
        self.initialize()
        with self._db() as db:
            rows = db.execute("SELECT id,content FROM chunks WHERE embedding_json IS NULL ORDER BY id LIMIT ?", (limit,)).fetchall()
            updated = 0
            for row in rows:
                vector = self._embedding(self.embedder, row["content"])
                if vector is not None:
                    db.execute("UPDATE chunks SET embedding_json=? WHERE id=?", (json.dumps(vector), row["id"]))
                    updated += 1
            return updated
