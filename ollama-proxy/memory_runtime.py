"""Async, fail-soft lifecycle wrapper around :mod:`airi_memory`.

This module deliberately has no proxy import: it is safe to import in unit
tests and can be attached to either of the proxy entry points.
"""
from __future__ import annotations

import asyncio
import copy
from collections import deque
import hashlib
import json
import os
import time
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlsplit

from airi_memory import (
    JOURNAL_RECALL_WINDOW_MESSAGES,
    MemoryStore,
    RetrievalResult,
    assemble_context,
    render_memory_placeholders,
)
from benchmark_memory_track import parse_stage_a
from memory_prompts import STAGE_A_SCHEMA, STAGE_A_CONVERSATION_SYSTEM_PROMPT, STAGE_B_DECISION_SYSTEM_PROMPT
from memory_stage_b import compile_decisions, decision_schema_for_items, format_stage_b_input, parse_stage_b_decisions
from latency_trace import emit_latency_event
from memory_extraction_provider import (
    ExtractionUnavailableError,
    MemoryExtractionProvider,
    approved_base_url,
)


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() in {"1", "true", "yes", "on"}:
        return True
    if value.lower() in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _positive(name: str, default: int, *, minimum: int = 1) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        result = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def _display_name(name: str, default: str = "") -> str:
    value = (os.getenv(name, default) or "").strip()
    if len(value) > 80 or any(ord(character) < 32 for character in value):
        raise ValueError(f"{name} must be a single display name of at most 80 characters")
    return value


@dataclass(frozen=True)
class MemoryConfig:
    enabled: bool = False
    db_path: str = str(Path(__file__).resolve().parent / "runtime" / "airi-memory.sqlite3")
    session_id: str = "primary"
    embed_model: Optional[str] = None
    embed_device: str = "auto"
    cache: bool = True
    extraction_threshold: int = 3
    extraction_batch_messages: int = 60
    extraction_batch_chars: int = 24000
    retrieve_timeout_ms: int = 150
    shutdown_flush_timeout_ms: int = 3000
    upstream_url: str = "http://127.0.0.1:11434"
    extraction_model: str = ""
    extraction_num_ctx: int = 8192
    extraction_num_gpu: int = 0
    extraction_keep_alive: str = "5m"
    extraction_provider: str = "ollama"
    allow_external_extraction: bool = False
    extraction_base_url: str = ""
    extraction_api_key: str = ""
    extraction_max_tokens: int = 2048
    extraction_seed: int = 42
    user_display_name: str = ""
    character_name: str = "아이리"
    canon_bundle_path: str = ""
    usage_ledger_path: str = ""

    @classmethod
    def from_env(cls) -> "MemoryConfig":
        model = os.getenv("AIRI_MEMORY_EMBED_MODEL", "").strip() or None
        device = os.getenv("AIRI_MEMORY_EMBED_DEVICE", "auto").lower().strip()
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("AIRI_MEMORY_EMBED_DEVICE must be cpu, cuda, or auto")
        configured_session = os.getenv("AIRI_MEMORY_SESSION")
        session = (configured_session.strip() if configured_session else f"broadcast-{uuid.uuid4().hex}")
        if not session:
            raise ValueError("AIRI_MEMORY_SESSION must not be empty")
        provider = os.getenv("AIRI_MEMORY_EXTRACTION_PROVIDER", "ollama").lower().strip()
        if provider not in {"ollama", "openai", "anthropic"}:
            raise ValueError("AIRI_MEMORY_EXTRACTION_PROVIDER must be ollama, openai, or anthropic")
        allowlist = frozenset(host.strip().lower() for host in os.getenv(
            "AIRI_MEMORY_EXTERNAL_EXTRACTION_ALLOWLIST", "").split(",") if host.strip())
        defaults = {"openai": "https://api.openai.com/v1", "anthropic": "https://api.anthropic.com/v1"}
        base_url = ""
        api_key = ""
        if provider in defaults:
            base_url = approved_base_url(provider, os.getenv(
                f"AIRI_MEMORY_{provider.upper()}_BASE_URL", defaults[provider]), allowlist)
            api_key = os.getenv(f"{provider.upper()}_API_KEY", "").strip()
        return cls(
            enabled=_bool("AIRI_MEMORY_ENABLED", False),
            db_path=os.getenv("AIRI_MEMORY_DB", str(Path(__file__).resolve().parent / "runtime" / "airi-memory.sqlite3")),
            session_id=session, embed_model=model, embed_device=device, cache=_bool("AIRI_MEMORY_CACHE", True),
            extraction_threshold=_positive("AIRI_MEMORY_EXTRACTION_THRESHOLD", 3, minimum=2),
            extraction_batch_messages=_positive("AIRI_MEMORY_EXTRACTION_BATCH_MESSAGES", 60, minimum=2),
            extraction_batch_chars=_positive("AIRI_MEMORY_EXTRACTION_BATCH_CHARS", 24000, minimum=1000),
            retrieve_timeout_ms=_positive("AIRI_MEMORY_RETRIEVE_TIMEOUT_MS", 150),
            shutdown_flush_timeout_ms=_positive("AIRI_MEMORY_SHUTDOWN_FLUSH_TIMEOUT_MS", 3000),
            upstream_url=(
                os.getenv("AIRI_MEMORY_EXTRACTION_UPSTREAM")
                or os.getenv("AIRI_MEMORY_UPSTREAM")
                or "http://127.0.0.1:11434"
            ).rstrip("/"),
            extraction_model=os.getenv("AIRI_MEMORY_EXTRACTION_MODEL", "").strip(),
            extraction_num_ctx=_positive("AIRI_MEMORY_EXTRACTION_NUM_CTX", 8192, minimum=128),
            extraction_num_gpu=_positive("AIRI_MEMORY_EXTRACTION_NUM_GPU", 0, minimum=0),
            extraction_keep_alive=os.getenv("AIRI_MEMORY_EXTRACTION_KEEP_ALIVE", "5m").strip() or "5m",
            extraction_provider=provider,
            allow_external_extraction=_bool("AIRI_MEMORY_ALLOW_EXTERNAL_EXTRACTION", False),
            extraction_base_url=base_url,
            extraction_api_key=api_key,
            extraction_max_tokens=_positive("AIRI_MEMORY_EXTRACTION_MAX_TOKENS", 2048, minimum=64),
            extraction_seed=_positive("AIRI_MEMORY_EXTRACTION_SEED", 42, minimum=0),
            user_display_name=_display_name("AIRI_MEMORY_USER_NAME"),
            character_name=_display_name("AIRI_MEMORY_CHARACTER_NAME", "아이리"),
            canon_bundle_path=os.getenv("AIRI_MEMORY_CANON_BUNDLE", "").strip(),
            usage_ledger_path=os.getenv(
                "AIRI_USAGE_LEDGER_PATH",
                str(Path(__file__).resolve().parent / "runtime" / "provider-usage.sqlite3"),
            ).strip(),
        )


class SentenceTransformerEmbedder:
    """Local-only sentence-transformers adapter, loaded only during startup."""
    def __init__(self, model_name: str, device: str = "auto"):
        from sentence_transformers import SentenceTransformer  # optional dependency
        resolved_model = model_name
        if not Path(model_name).exists():
            from huggingface_hub import snapshot_download
            resolved_model = snapshot_download(repo_id=model_name, local_files_only=True)
        kwargs: dict[str, Any] = {"local_files_only": True}
        if device != "auto":
            kwargs["device"] = device
        self.model = SentenceTransformer(resolved_model, **kwargs)
        self.fingerprint = f"{model_name}@{Path(resolved_model).name}"
        self.dimension = int(self.model.get_sentence_embedding_dimension())
        self._lock = threading.Lock()

    def encode(self, texts: list[str]):
        with self._lock:
            return self.model.encode(texts, normalize_embeddings=True, batch_size=min(16, max(1, len(texts))))


class NullMemoryRuntime:
    async def startup(self) -> None: pass
    async def shutdown(self) -> None: pass
    async def retrieve(self, *args: Any, **kwargs: Any) -> RetrievalResult: return RetrievalResult()
    def assemble_payload_context(self, payload: dict[str, Any], original_messages: Iterable[dict[str, Any]], **kwargs: Any) -> dict[str, Any]: return copy.deepcopy(payload)
    async def schedule_completed_turn(self, *args: Any, **kwargs: Any) -> str: return "disabled"
    async def prepare_payload_context(self, payload: dict[str, Any], original_messages: Iterable[dict[str, Any]],
                                      session: str | None = None, question: str = "", current_turn: int = 0,
                                      trace_id: str = "", projected_message_count: int | None = None) -> tuple[dict[str, Any], RetrievalResult]:
        return copy.deepcopy(payload), RetrievalResult()
    async def health(self) -> dict[str, int | bool | str]: return {"enabled": False, "ready": False, "embedder": False, "extraction_enabled": False, "extraction_isolated": False, "extraction_ready": False, "extraction_availability": "unconfigured", "extraction_retrying": False, "extraction_retry_sessions": 0, "provider": "ollama", "external_approved": False, "configured": False, "schema": 0, "data_version": 0, "pending": 0}
    status = health


class MemoryRuntime:
    def __init__(self, config: MemoryConfig | None = None, *, http_client: Any = None):
        self.config = config or MemoryConfig.from_env()
        self.http_client, self.store = http_client, None
        self.extraction_provider = MemoryExtractionProvider(self.config, http_client)
        self._tasks: set[asyncio.Task[Any]] = set()
        self._scheduled: set[str] = set()
        self._scheduled_order: list[str] = []
        self._sessions: set[str] = set()
        self._snapshotted: set[str] = set()
        self._implicit_session = self.config.session_id
        self._implicit_claimed = False
        self._trace_sessions: dict[str, str] = {}
        self._trace_session_order: list[str] = []
        self._extracting: set[str] = set()
        self._extract_tasks: dict[str, asyncio.Task[Any]] = {}
        self._extract_dirty: set[str] = set()
        self._extract_force: set[str] = set()
        self._extraction_retry_task: asyncio.Task[Any] | None = None
        self._extraction_retry_sessions: dict[str, tuple[str, bool]] = {}
        self._extraction_retry_delay = 1.0
        self._snapshot_lock = asyncio.Lock()
        self._session_resolution_lock = asyncio.Lock()
        self._extraction_semaphore = asyncio.Semaphore(1)
        self._started = False
        self._stopping = False

    @classmethod
    def from_env(cls, **kwargs: Any) -> "MemoryRuntime | NullMemoryRuntime":
        config = MemoryConfig.from_env()
        return cls(config, **kwargs) if config.enabled else NullMemoryRuntime()

    async def startup(self) -> None:
        if self._started:
            return
        self._stopping = False
        self._implicit_session = self.config.session_id
        self._implicit_claimed = False
        if self.config.extraction_model and self.config.extraction_provider == "ollama":
            endpoint = urlsplit(self.config.upstream_url)
            if endpoint.scheme != "http" or endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("memory extraction upstream must be a local HTTP loopback service")
        Path(self.config.db_path).parent.mkdir(parents=True, exist_ok=True)
        embedder = None
        if self.config.embed_model:
            try:
                embedder = await asyncio.to_thread(SentenceTransformerEmbedder, self.config.embed_model, self.config.embed_device)
            except Exception:
                embedder = None
        self.store = await asyncio.to_thread(MemoryStore, self.config.db_path, embedder, self.config.cache)
        if embedder is not None:
            await asyncio.to_thread(
                self.store.ensure_embedding_contract,
                embedder.fingerprint,
                embedder.dimension,
            )
        if self.config.canon_bundle_path:
            bundle_path = Path(self.config.canon_bundle_path).resolve()
            if not bundle_path.is_file():
                raise ValueError("AIRI_MEMORY_CANON_BUNDLE must point to a JSON file")
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            await asyncio.to_thread(self.store.ingest_canon_bundle, bundle)
        await asyncio.to_thread(self.store.reset_extraction_failures)
        await self._ensure_session(self.config.session_id)
        self._started = True
        if self.extraction_provider.can_extract:
            available = await self.extraction_provider.preflight(force=True)
            pending_sessions = await asyncio.to_thread(
                self.store.pending_extraction_sessions
            )
            for sid in pending_sessions:
                self._sessions.add(sid)
                if available:
                    self._schedule_extraction(sid, "startup")
                else:
                    self._schedule_extraction_retry(sid, "startup")

    async def _ensure_session(self, session_id: str) -> None:
        if not self.store or session_id in self._snapshotted:
            return
        async with self._snapshot_lock:
            if session_id in self._snapshotted:
                return
            await asyncio.to_thread(self.store.canon_snapshot, session_id)
            self._snapshotted.add(session_id)
            self._sessions.add(session_id)

    async def _resolve_session(self, explicit_session: str | None,
                               messages: Iterable[dict[str, Any]], trace_id: str) -> str:
        """Resolve a header session or compare ordered completed-turn tails."""
        # Headers are authoritative: their history is adopted only into that
        # exact scope, never used for implicit-session recovery.
        if explicit_session:
            sid = explicit_session
            completed: deque[tuple[int, str, str]] = deque(maxlen=60)
            pending_user = ""
            incoming_ordinal = 0
            for message in messages:
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                if not isinstance(content, str) or not content:
                    continue
                if message.get("role") == "user":
                    pending_user = content
                    incoming_ordinal += 1
                elif message.get("role") == "assistant" and pending_user:
                    completed.append((incoming_ordinal, pending_user, content))
                    pending_user = ""
            if self.store and completed:
                # A mismatch is deliberately fail-closed inside the store;
                # context preparation remains fail-soft for the proxy.
                try:
                    await asyncio.to_thread(self.store.adopt_explicit_turn_tail, sid, completed, 60)
                except ValueError:
                    pass
            if trace_id:
                self._trace_sessions[trace_id] = sid
                self._trace_session_order.append(trace_id)
                if len(self._trace_session_order) > 2048:
                    self._trace_sessions.pop(self._trace_session_order.pop(0), None)
            return sid
        message_list = list(messages)
        completed: list[tuple[int, str, str]] = []
        pending_user = ""
        incoming_ordinal = 0
        for message in message_list:
            content = message.get("content")
            if not isinstance(content, str) or not content:
                continue
            if message.get("role") == "user":
                pending_user = content
                incoming_ordinal += 1
            elif message.get("role") == "assistant" and pending_user:
                completed.append((incoming_ordinal, pending_user, content))
                pending_user = ""
        incoming_turn_hashes = [
            (hashlib.sha256(user.encode()).hexdigest(), hashlib.sha256(assistant.encode()).hexdigest())
            for _turn, user, assistant in completed
        ]
        incoming_user_hashes = [pair[0] for pair in incoming_turn_hashes]
        async with self._session_resolution_lock:
            sid = self._implicit_session
            latest = await asyncio.to_thread(self.store.latest_turn, sid) if self.store else 0
            recovered = None
            # 1) Exact current-session pair tail (same process only).
            if latest and self._implicit_claimed:
                recent = await asyncio.to_thread(self.store.recent_turn_hashes, sid)
                width = min(len(recent), len(incoming_turn_hashes))
                if width and recent[-width:] == incoming_turn_hashes[-width:]:
                    recovered = sid
            # 2) Current-session user-only suffix, guarded by global ambiguity.
            if (not recovered and latest and self._implicit_claimed
                    and len(incoming_user_hashes) >= 3 and len(set(incoming_user_hashes)) >= 2):
                candidate = await asyncio.to_thread(self.store.find_session_by_user_tail, incoming_user_hashes,
                                                    min_turns=3, min_distinct=2)
                if candidate == sid:
                    recovered = sid
            # 3) Cold/global exact pair tail.
            if not recovered and len(incoming_turn_hashes) >= 2:
                recovered = await asyncio.to_thread(self.store.find_session_by_turn_tail, incoming_turn_hashes, min_turns=2)
            # 4) Cold/global canonical-user suffix.
            if not recovered and len(incoming_user_hashes) >= 4 and len(set(incoming_user_hashes)) >= 3:
                recovered = await asyncio.to_thread(self.store.find_session_by_user_tail, incoming_user_hashes,
                                                    min_turns=4, min_distinct=3)
            if recovered:
                sid = recovered
            else:
                # Keep the configured, empty base for a first request that
                # has no completed turns; there is nothing to bootstrap yet.
                sid = (self._implicit_session if not completed and not latest and not self._implicit_claimed
                       else f"{self.config.session_id}-{uuid.uuid4().hex}")
                if self.store and completed:
                    await asyncio.to_thread(self.store.bootstrap_turns_if_empty, sid, completed, 60)
            self._implicit_session = sid
            self._implicit_claimed = True
        if trace_id:
            self._trace_sessions[trace_id] = sid
            self._trace_session_order.append(trace_id)
            if len(self._trace_session_order) > 2048:
                self._trace_sessions.pop(self._trace_session_order.pop(0), None)
        return sid

    def _emit(self, phase: str, trace_id: str, duration: float | None = None, **meta: int | float | bool) -> None:
        try:
            emit_latency_event("memory", phase, trace_id or "memory", duration_ms=duration, meta=meta)
        except Exception:
            pass

    async def retrieve(self, session: str | None, question: str, current_turn: int = 0,
                       attendees: Optional[Iterable[str]] = None, trace_id: str = "",
                       journal_retained_turns: Optional[Iterable[int]] = None,
                       journal_recall_allowed: bool = True) -> RetrievalResult:
        if not self.store:
            return RetrievalResult()
        sid = session or self._implicit_session
        await self._ensure_session(sid)
        start = time.perf_counter(); self._emit("retrieve_start", trace_id, session_default=bool(not session))
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self.store.retrieve, sid, question, current_turn, attendees,
                                  journal_retained_turns, journal_recall_allowed),
                self.config.retrieve_timeout_ms / 1000,
            )
            self._emit("retrieve_end", trace_id, (time.perf_counter()-start)*1000, gate=result.gate, cache_hit=result.cache_hit)
            return result
        except Exception as exc:
            self._emit("error", trace_id, (time.perf_counter()-start)*1000, timeout=isinstance(exc, asyncio.TimeoutError), retrieval=True)
            return RetrievalResult()

    def assemble_payload_context(self, payload: dict[str, Any], original_messages: Iterable[dict[str, Any]], *,
                                 extraction_watermark: int, memory_block: str = "", system_intro: Any = None,
                                 static_prompt: Any = None,
                                 journal_messages: Iterable[dict[str, Any]] = ()) -> dict[str, Any]:
        """Copy transformed payload; assemble against untouched original turns."""
        out = copy.deepcopy(payload)
        transformed = out.get("messages", [])
        if static_prompt is None and isinstance(transformed, list) and transformed:
            static_prompt = transformed[0]  # AIRI prompt remains first.
        # assemble_context preserves its first system argument at the front;
        # AIRI's static identity therefore always precedes any optional intro.
        out["messages"] = assemble_context(static_prompt, system_intro, original_messages, extraction_watermark,
                                           memory_block, journal_messages)
        return out

    async def prepare_payload_context(self, payload: dict[str, Any], original_messages: Iterable[dict[str, Any]],
                                      session: str | None = None, question: str = "", current_turn: int = 0,
                                      trace_id: str = "", projected_message_count: int | None = None) -> tuple[dict[str, Any], RetrievalResult]:
        """Fail-soft facade for proxies; callers never need to access the store."""
        if not self.store:
            return copy.deepcopy(payload), RetrievalResult()
        # Upstream history does not carry journal ids.  Derive the same stable
        # turn numbering used by the journal.  Align a truncated client tail so
        # its last (current) user message is latest_journal_turn + 1.
        raw_messages = [message for message in original_messages if isinstance(message, dict)]
        sid = await self._resolve_session(session, raw_messages, trace_id)
        await self._ensure_session(sid)
        user_count = sum(message.get("role") == "user" for message in raw_messages)
        latest_turn = await asyncio.to_thread(self.store.latest_turn, sid)
        non_system = [message for message in raw_messages if message.get("role") != "system"]
        # A complete client tail ends with an assistant and is entirely
        # journal-resident already; a request tail ends with the new user turn
        # which has not yet been appended.  This keeps forwarded IDs aligned
        # in both cases so journal recall cannot quote a short full history.
        has_current_user = bool(non_system and non_system[-1].get("role") == "user")
        turn = max(0, latest_turn + (1 if has_current_user else 0) - user_count)
        original: list[dict[str, Any]] = []
        decorated_by_source: dict[int, dict[str, Any]] = {}
        for message in raw_messages:
            if not isinstance(message, dict) or message.get("role") == "system":
                continue
            item = copy.deepcopy(message)
            if item.get("role") == "user":
                turn += 1
            item["id"] = turn if turn else 1
            original.append(item)
            decorated_by_source[id(message)] = item
        try:
            state = await asyncio.to_thread(self.store.job_state_readonly, sid)
            eligible = [item for item in original if int(item.get("id", 0)) > int(state["extracted_up_to_msg"])]
            # Always tell journal recall which turns are already forwarded.
            # A client can legitimately send only the current turn while this
            # stable session has much older pending journal evidence.
            retained_turns = [int(item["id"]) for item in eligible[-60:]]
            result = await self.retrieve(sid, question, max(current_turn, latest_turn + 1),
                                         attendees=None, trace_id=trace_id,
                                         journal_retained_turns=retained_turns,
                                         journal_recall_allowed=bool(retained_turns))
            rendered_block = render_memory_placeholders(
                result.block,
                user_name=self.config.user_display_name,
                char_name=self.config.character_name,
            )
            # The raw list remains authoritative above for session adoption,
            # IDs, retrieval and journal gating.  Assemble only the request's
            # foreground suffix so memory cannot restore a dropped topic.
            # Direct runtime callers retain the historical API behavior; the
            # proxy always supplies its already-projected suffix.
            if projected_message_count is None:
                foreground = original
            else:
                # Projection is always a trailing non-system suffix.  Use its
                # bounded count rather than Python object identity: the proxy
                # parses the original and transformed JSON independently, so
                # equivalent message dictionaries are different objects.
                retained = max(0, min(int(projected_message_count), len(original)))
                foreground = original[-retained:] if retained else []
            return self.assemble_payload_context(payload, foreground, extraction_watermark=int(state["extracted_up_to_msg"]),
                                                 memory_block=rendered_block,
                                                 journal_messages=result.journal_messages), result
        except Exception:
            return copy.deepcopy(payload), RetrievalResult()

    async def schedule_completed_turn(self, session: str | None, user: str, assistant: str, turn_no: int,
                                      trace_id: str = "", history: Optional[Iterable[dict[str, Any]]] = None) -> str:
        if not self.store or not user or not assistant:
            return "disabled"
        sid = session or self._trace_sessions.get(trace_id)
        if not sid:
            sid = await self._resolve_session(None, history or (), trace_id)
        await self._ensure_session(sid)
        content_digest = hashlib.sha256(f"{user}\0{assistant}".encode()).hexdigest()
        # Correlation IDs are expected to be unique, but a renderer restart or
        # integration bug must not let one reused ID discard a different
        # completed turn. The content digest preserves exact replay
        # idempotency while keeping distinct dialogue appendable.
        stable_part = f"{trace_id}\0{content_digest}" if trace_id else content_digest
        key = f"{sid}\0{stable_part}"
        if key in self._scheduled:
            return "duplicate"
        self._scheduled.add(key)
        self._scheduled_order.append(key)
        if len(self._scheduled_order) > 2048:
            self._scheduled.discard(self._scheduled_order.pop(0))
        try:
            await asyncio.to_thread(self.store.append_turn, sid, user, assistant, turn_no)
            state = await asyncio.to_thread(self.store.job_state, sid)
            if self.extraction_provider.can_extract and state["pending_msgs"] >= self.config.extraction_threshold and state["fail_count"] < 5:
                self._schedule_extraction(sid, trace_id)
            return "appended"
        except Exception:
            self._scheduled.discard(key)
            raise

    def _track(self, task: asyncio.Task[Any]) -> None:
        self._tasks.add(task); task.add_done_callback(self._tasks.discard)

    def _schedule_extraction_retry(self, sid: str, trace_id: str, *, force: bool = False) -> None:
        """Coalesce unavailable sessions behind one bounded exponential backoff."""
        if self._stopping:
            return
        previous = self._extraction_retry_sessions.get(sid)
        self._extraction_retry_sessions[sid] = (
            trace_id or (previous[0] if previous else "retry"),
            force or bool(previous and previous[1]),
        )
        self._start_extraction_retry_task()

    def _start_extraction_retry_task(self) -> None:
        existing = self._extraction_retry_task
        if self._stopping or not self._extraction_retry_sessions or (existing and not existing.done()):
            return

        async def recover() -> None:
            while self._extraction_retry_sessions and not self._stopping:
                await asyncio.sleep(self._extraction_retry_delay)
                if self._stopping:
                    return
                if not await self.extraction_provider.preflight(force=True):
                    self._extraction_retry_delay = min(60.0, self._extraction_retry_delay * 2)
                    continue
                pending = list(self._extraction_retry_sessions.items())
                self._extraction_retry_sessions.clear()
                # Reset happens only after an extraction succeeds.  A cloud
                # provider has no probe by design, so treating config-ready as
                # recovery here would otherwise retry a failing API every 1s.
                self._extraction_retry_delay = min(
                    60.0, self._extraction_retry_delay * 2
                )
                for retry_sid, (retry_trace, retry_force) in pending:
                    self._schedule_extraction(retry_sid, retry_trace, force=retry_force)
                return

        task = asyncio.create_task(recover())
        self._extraction_retry_task = task
        self._track(task)

        def release(done: asyncio.Task[Any]) -> None:
            if self._extraction_retry_task is done:
                self._extraction_retry_task = None
            if self._extraction_retry_sessions and not self._stopping:
                self._start_extraction_retry_task()

        task.add_done_callback(release)

    def _schedule_extraction(self, sid: str, trace_id: str, *, force: bool = False) -> asyncio.Task[Any]:
        existing = self._extract_tasks.get(sid)
        if existing is not None and not existing.done():
            self._extract_dirty.add(sid)
            if force:
                self._extract_force.add(sid)
            return existing
        self._extract_dirty.discard(sid)
        effective_force = force or sid in self._extract_force
        self._extract_force.discard(sid)
        task = asyncio.create_task(self._extract(sid, trace_id, force=effective_force))
        self._extract_tasks[sid] = task
        self._track(task)
        def release(done: asyncio.Task[Any]) -> None:
            if self._extract_tasks.get(sid) is done:
                self._extract_tasks.pop(sid, None)
            # A trigger arriving after the worker's final state read is retained
            # as a dirty bit and starts exactly one successor drain.
            if sid in self._extract_dirty and not self._stopping:
                next_force = sid in self._extract_force
                self._schedule_extraction(sid, trace_id, force=next_force)
        task.add_done_callback(release)
        return task

    async def _chat_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        return await self.extraction_provider.chat_json(system, user, schema)

    @staticmethod
    def _turns(rows: list[Any], max_chars: int | None = None) -> str:
        contents = [str(row["content"]) for row in rows]
        if max_chars is not None and sum(map(len, contents)) > max_chars:
            # Preserve the beginning and end of both sides of an oversized turn.
            # This keeps one poison turn from blocking every later extraction.
            per_row = max(1, max_chars // max(1, len(contents)))
            clipped: list[str] = []
            for content in contents:
                if len(content) <= per_row:
                    clipped.append(content)
                    continue
                head = max(1, (per_row - 1) // 2)
                tail = max(0, per_row - head - 1)
                clipped.append(content[:head] + "…" + (content[-tail:] if tail else ""))
            contents = clipped
        return "<turns>" + "\n".join(
            f'[{row["turn_no"]}:{row["role"]}] {content}'
            for row, content in zip(rows, contents)
        ) + "</turns>"

    async def _extract(self, sid: str, trace_id: str, *, force: bool = False) -> None:
        """Serialize the local extractor and drain bounded message batches."""
        async with self._extraction_semaphore:
            while self.store:
                before = await asyncio.to_thread(self.store.job_state, sid)
                eligible = before["pending_msgs"] > 0 if force else before["pending_msgs"] >= self.config.extraction_threshold
                if before["fail_count"] >= 5 or not eligible:
                    return
                await self._extract_batch(sid, trace_id, force=force)
                after = await asyncio.to_thread(self.store.job_state, sid)
                if after["pending_msgs"] >= before["pending_msgs"]:
                    return

    async def _extract_batch(self, sid: str, trace_id: str, *, force: bool = False) -> None:
        if not self.store or not self.extraction_provider.can_extract:
            return
        if sid in self._extracting:
            return
        self._extracting.add(sid)
        started = time.perf_counter()
        self._emit("extract_start", trace_id, session_default=bool(sid == self.config.session_id), force=force)
        try:
            state = await asyncio.to_thread(self.store.job_state, sid)
            if state["fail_count"] >= 5 or (not force and state["pending_msgs"] < self.config.extraction_threshold):
                return
            rows = await asyncio.to_thread(
                self.store.unextracted_complete_turns,
                sid,
                self.config.extraction_batch_messages,
                self.config.extraction_batch_chars,
            )
            if not rows:
                return
            stage_a_input = "<character>name: 아이리; scope: conversation</character>" + self._turns(
                rows, self.config.extraction_batch_chars
            )
            parsed_a = parse_stage_a(await self._chat_json(STAGE_A_CONVERSATION_SYSTEM_PROMPT, stage_a_input, STAGE_A_SCHEMA))
            ids, watermark = [r["id"] for r in rows], rows[-1]["turn_no"]
            extracted = parsed_a["extracted"]
            if not extracted:
                await asyncio.to_thread(self.store.extraction_success, sid, ids, watermark, 0)
                self._extraction_retry_sessions.pop(sid, None)
                self._extraction_retry_delay = 1.0
                self._emit("extract_end", trace_id, (time.perf_counter()-started)*1000, extracted=0, operations=0)
                return
            candidates, aliases = await asyncio.to_thread(self.store.build_stage_b_candidates, sid, extracted, 5)
            prompt = format_stage_b_input(extracted, candidates)
            parsed_b = parse_stage_b_decisions(await self._chat_json(
                STAGE_B_DECISION_SYSTEM_PROMPT, prompt, decision_schema_for_items(extracted, candidates)))
            operations = compile_decisions(extracted, candidates, parsed_b["decisions"])
            await asyncio.to_thread(
                self.store.apply_extraction_batch,
                sid,
                operations,
                aliases,
                ids,
                watermark,
                0,
                extracted,
            )
            self._extraction_retry_sessions.pop(sid, None)
            self._extraction_retry_delay = 1.0
            self._emit("extract_end", trace_id, (time.perf_counter()-started)*1000, extracted=len(extracted), operations=len(operations))
        except ExtractionUnavailableError:
            self._extract_dirty.discard(sid)
            self._extract_force.discard(sid)
            self._emit("error", trace_id, (time.perf_counter()-started)*1000, extraction=True, unavailable=True, force=force)
            self._schedule_extraction_retry(sid, trace_id, force=force)
        except Exception:
            self._emit("error", trace_id, (time.perf_counter()-started)*1000, extraction=True, force=force)
            try:
                await asyncio.to_thread(self.store.job_failure, sid, "extraction failure")
            except Exception:
                pass
        finally:
            self._extracting.discard(sid)

    async def shutdown(self) -> None:
        self._stopping = True
        deadline = time.monotonic() + self.config.shutdown_flush_timeout_ms / 1000
        async def finish_tasks() -> bool:
            while self._tasks:
                tasks = list(self._tasks)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    await asyncio.sleep(0)
                    return False
                _done, pending = await asyncio.wait(tasks, timeout=remaining)
                if pending:
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    await asyncio.sleep(0)
                    return False
                await asyncio.sleep(0)
            return True

        # Finish an existing coalesced worker first. During stopping its callback
        # cannot resurrect a dirty successor after cancellation.
        drained = await finish_tasks()
        self._extract_dirty.clear()
        self._extract_force.clear()
        if drained and self.store and time.monotonic() < deadline:
            # Force flush handles the final 1--2 pending journal messages too.
            for sid in self._sessions | {self.config.session_id}:
                try:
                    state = await asyncio.to_thread(self.store.job_state, sid)
                    if self.extraction_provider.can_extract and state["pending_msgs"] and state["fail_count"] < 5:
                        self._schedule_extraction(sid, "shutdown", force=True)
                except Exception:
                    continue
            await finish_tasks()
        # Defensive final sweep: no runtime task may outlive the shared client.
        leftovers = list(self._tasks)
        for task in leftovers:
            task.cancel()
        if leftovers:
            await asyncio.gather(*leftovers, return_exceptions=True)
        self._extract_dirty.clear()
        self._extract_force.clear()
        self._extraction_retry_sessions.clear()
        self._extraction_retry_task = None
        self._started = False

    async def health(self, session: str | None = None) -> dict[str, Any]:
        """A privacy-safe operational snapshot; no session/content/path is exposed."""
        extraction_isolated = bool(self.config.extraction_provider == "ollama" and self.config.extraction_model and self.config.upstream_url != "http://127.0.0.1:11434")
        provider_health = {
            "provider": self.config.extraction_provider,
            "external_approved": bool(
                self.extraction_provider.is_external
                and self.config.allow_external_extraction
            ),
            "configured": self.extraction_provider.configured,
            "extraction_provider": self.config.extraction_provider,
            "extraction_external_approved": bool(
                self.extraction_provider.is_external
                and self.config.allow_external_extraction
            ),
            "extraction_configured": self.extraction_provider.configured,
        }
        extraction_ready = False
        if self.extraction_provider.is_external:
            extraction_ready = self.extraction_provider.runtime_ready
        elif self.extraction_provider.can_extract:
            extraction_ready = await self.extraction_provider.preflight(force=True)
        retry_health = {
            "extraction_availability": self.extraction_provider.availability,
            "extraction_retrying": bool(
                self._extraction_retry_task and not self._extraction_retry_task.done()
            ),
            "extraction_retry_sessions": len(self._extraction_retry_sessions),
        }
        if not self.store:
            return {"enabled": True, "ready": False, "embedder": False, "extraction_enabled": self.extraction_provider.can_extract, "extraction_isolated": extraction_isolated, "extraction_ready": extraction_ready, "schema": 1, "data_version": 0, "pending": 0, "pending_total": 0, "pending_sessions": 0, "journal_recall_window_messages": JOURNAL_RECALL_WINDOW_MESSAGES, **provider_health, **retry_health}
        try:
            journal_health = await asyncio.to_thread(self.store.journal_health, session or self._implicit_session)
            store_health = await asyncio.to_thread(self.store.health)
            return {"enabled": True, "ready": bool(store_health["ok"]), "embedder": bool(self.store.embedder), "extraction_enabled": self.extraction_provider.can_extract, "extraction_isolated": extraction_isolated, "extraction_ready": extraction_ready, "schema": 1, "data_version": int(store_health["data_version"]), "journal_recall_window_messages": JOURNAL_RECALL_WINDOW_MESSAGES, **journal_health, **provider_health, **retry_health}
        except Exception:
            return {"enabled": True, "ready": False, "embedder": bool(self.store.embedder), "extraction_enabled": self.extraction_provider.can_extract, "extraction_isolated": extraction_isolated, "extraction_ready": extraction_ready, "schema": 1, "data_version": 0, "pending": 0, "pending_total": 0, "pending_sessions": 0, "journal_recall_window_messages": JOURNAL_RECALL_WINDOW_MESSAGES, **provider_health, **retry_health}

    status = health
