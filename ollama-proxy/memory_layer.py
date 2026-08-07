"""Long-term memory layer for the AIRI proxy (track M2).

Two paths that never touch each other:

- Real time (per turn, LLM calls = 0): gate -> one embedding -> brute-force
  cosine + decay re-rank -> `[Character Memory]` block. Hard timeboxed, and
  every failure mode returns an empty block instead of an error, because the
  operating rule from the reference is that memory must never block speech.
- Background (batch, latency irrelevant): completed turns queue behind the
  `extracted_up_to_msg` watermark; once `extraction_batch_turns` have piled up
  a worker runs Stage A (and Stage B when there are candidates) through the
  existing llm_backends adapters and writes the result to SQLite.

The extraction worker only starts when the real server entry point asks for it
(`start(run_worker=True)` from ollama_proxy.main), so importing the app under a
test client can never spawn an extraction subprocess.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from llm_backends import build_backend
from memory_embed import FAKE_MODE, build_embedder
from memory_extract import (
    STAGE_A_SYSTEM_PROMPT,
    STAGE_B_SYSTEM_PROMPT,
    ExtractionApplier,
    build_stage_a_user_message,
    build_stage_b_user_message,
    parse_stage_a,
    parse_stage_b,
    select_candidates,
)
from memory_retrieve import RetrievalCaps, format_memory_block, needs_retrieval, retrieve
from memory_store import MemoryStore

MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = MODULE_DIR / "memory-data" / "airi-memory.db"

# Every tunable lives here, not in the code that reads it. The cap numbers are
# the reference §2 values; changing them is a config edit, not a patch.
DEFAULT_MEMORY_CONFIG: dict[str, object] = {
    "enabled": True,
    "db_path": None,
    "session_id": "default",
    "character_name": "아이리",
    "user_name": "사용자",
    "embed_mode": "fake",
    "embed_model": "nlpai-lab/KURE-v1",
    "extraction_provider": "codex-cli",
    "extraction_fallback_provider": "ollama",
    "extraction_batch_turns": 6,
    "extraction_max_failures": 5,
    "extraction_poll_seconds": 5.0,
    "extraction_overrides": {
        "max_tokens": 2048,
        "timeout_s": {"connect": 5.0, "read": 180.0, "write": 30.0},
        "codex_prompt_header": "",
    },
    "retrieval_timebox_ms": 150,
    "caps": {
        "traits": 8,
        "moments": 5,
        "scene_facts_raw": 20,
        "scene_facts_final": 8,
        "one_hop_relations": 5,
        "one_hop_facts": 3,
        "alpha": 0.7,
        "beta": 0.3,
        "lambda": 0.05,
    },
}

_FALSE_VALUES = {"0", "off", "false", "no"}


def _log(status: str, **fields: object) -> None:
    print(
        json.dumps({"event": "memory", "status": status, **fields}, ensure_ascii=False),
        flush=True,
    )


def _deep_merge(base: dict[str, object], override: Mapping[str, object]) -> dict[str, object]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged


def memory_config(llm_config: Mapping[str, object] | None = None) -> dict[str, object]:
    """Defaults <- llm_modes.json `memory` section <- environment overrides."""
    section = (llm_config or {}).get("memory")
    config = _deep_merge(
        DEFAULT_MEMORY_CONFIG, section if isinstance(section, Mapping) else {}
    )
    enabled_env = os.environ.get("AIRI_MEMORY_ENABLED", "").strip().lower()
    if enabled_env:
        config["enabled"] = enabled_env not in _FALSE_VALUES
    db_env = os.environ.get("AIRI_MEMORY_DB", "").strip()
    if db_env:
        config["db_path"] = db_env
    embed_env = os.environ.get("AIRI_EMBED_MODE", "").strip().lower()
    if embed_env:
        config["embed_mode"] = embed_env
    return config


def resolve_extraction_mode(
    llm_config: Mapping[str, object], provider: str
) -> dict[str, object] | None:
    """Reuse an existing llm_modes entry rather than duplicating a mode table.

    `provider` may name a mode key ("cloud") or a provider ("codex-cli").
    """
    modes = llm_config.get("modes")
    modes = modes if isinstance(modes, Mapping) else {}
    wanted = (provider or "").strip().lower()
    if not wanted:
        return None
    entry = modes.get(wanted)
    if isinstance(entry, Mapping):
        return dict(entry)
    for mode_config in modes.values():
        if not isinstance(mode_config, Mapping):
            continue
        if str(mode_config.get("provider", "")).strip().lower() == wanted:
            return dict(mode_config)
    return None


class MemoryLayer:
    """Facade the proxy talks to. Every public method is failure-tolerant."""

    def __init__(
        self,
        llm_config: Mapping[str, object] | None = None,
        *,
        extraction_caller=None,
    ) -> None:
        self.llm_config = dict(llm_config or {})
        self.config = memory_config(self.llm_config)
        self.enabled = bool(self.config.get("enabled", True))
        self.session_id = str(self.config.get("session_id") or "default")
        self.character_name = str(self.config.get("character_name") or "아이리")
        self.user_name = str(self.config.get("user_name") or "사용자")
        self.embed_mode_requested = str(self.config.get("embed_mode") or FAKE_MODE)
        self.caps = RetrievalCaps.from_config(self.config.get("caps"))
        self.batch_turns = max(1, int(self.config.get("extraction_batch_turns", 6)))
        self.max_failures = max(1, int(self.config.get("extraction_max_failures", 5)))
        self.poll_seconds = float(self.config.get("extraction_poll_seconds", 5.0))
        self.timebox_s = max(0.001, float(self.config.get("retrieval_timebox_ms", 150)) / 1000.0)
        db_path = self.config.get("db_path") or DEFAULT_DB_PATH
        self.store = MemoryStore(db_path)
        self._embedder = None
        self._extraction_caller = extraction_caller
        self._http_client = None
        self._worker: asyncio.Task | None = None
        self._warmup: asyncio.Task | None = None
        # asyncio only holds a weak reference to a running task, so a
        # fire-and-forget write has to be kept alive by someone.
        self._pending: set[asyncio.Task] = set()
        self._wake = asyncio.Event()
        self._started = False

    # ------------------------------------------------------------- lifecycle

    def start(self, *, run_worker: bool = False) -> None:
        """Open the DB and (optionally) start the background extractor."""
        if not self.enabled:
            _log("disabled")
            return
        try:
            self.store.ensure_schema()
            self._started = True
        except Exception as exc:
            self.enabled = False
            _log("start_failed", error_type=type(exc).__name__, error=str(exc)[:200])
            return
        _log(
            "ready",
            db=str(self.store.db_path),
            embed_mode=self.embed_mode_requested,
            worker=bool(run_worker),
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._warmup = loop.create_task(asyncio.to_thread(self._ensure_embedder))
        self._warmup.add_done_callback(_swallow)
        if run_worker and os.environ.get("AIRI_MEMORY_EXTRACTION", "").strip().lower() not in _FALSE_VALUES:
            self._worker = loop.create_task(self._worker_loop())

    async def aclose(self) -> None:
        if self._pending:
            await asyncio.gather(*list(self._pending), return_exceptions=True)
        for task in (self._worker, self._warmup):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._worker = None
        self._warmup = None
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except Exception:
                pass
            self._http_client = None
        self.store.close()
        self._started = False

    def _ensure_embedder(self):
        if self._embedder is None:
            self._embedder = build_embedder(
                self.embed_mode_requested, str(self.config.get("embed_model") or "")
            )
        return self._embedder

    @property
    def embed_mode(self) -> str:
        return self._embedder.mode if self._embedder is not None else self.embed_mode_requested

    # --------------------------------------------------------- write path

    def record_turn_sync(self, user_text: str, assistant_text: str) -> int:
        if not (self.enabled and self._started):
            return 0
        text = (user_text or "").strip()
        if not text:
            return 0
        return self.store.append_turn(self.session_id, text, (assistant_text or "").strip())

    def record_turn(self, user_text: str, assistant_text: str) -> None:
        """Fire and forget: the turn is already spoken, nothing may raise here."""
        if not (self.enabled and self._started):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                self.record_turn_sync(user_text, assistant_text)
            except Exception as exc:
                _log("record_failed", error_type=type(exc).__name__)
            return

        async def write() -> None:
            try:
                await asyncio.to_thread(self.record_turn_sync, user_text, assistant_text)
                self._wake.set()
            except Exception as exc:
                _log("record_failed", error_type=type(exc).__name__)

        task = loop.create_task(write())
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        task.add_done_callback(_swallow)

    # ---------------------------------------------------------- read path

    def memory_block_sync(self, user_text: str) -> str:
        """Gate -> retrieve -> serialize. Returns "" whenever there is nothing."""
        embedder = self._ensure_embedder()
        names = [str(row["name"]) for row in self.store.entity_names(self.session_id)]
        if not needs_retrieval(user_text, names):
            return ""
        result = retrieve(
            self.store,
            embedder,
            self.caps,
            session_id=self.session_id,
            question=user_text,
            current_turn=self.store.latest_turn_id(self.session_id),
        )
        return format_memory_block(
            result, char_name=self.character_name, user_name=self.user_name
        )

    async def memory_block(self, user_text: str) -> str:
        """Timeboxed read. A slow disk or a cold model yields "" and a log line.

        The work runs in a worker thread so the budget is a real deadline: a
        sync scan could not be interrupted once it started.
        """
        if not (self.enabled and self._started) or not (user_text or "").strip():
            return ""
        started = time.perf_counter()
        try:
            block = await asyncio.wait_for(
                asyncio.to_thread(self.memory_block_sync, user_text), timeout=self.timebox_s
            )
        except (asyncio.TimeoutError, TimeoutError):
            _log("retrieval_timebox", budget_ms=int(self.timebox_s * 1000))
            return ""
        except Exception as exc:
            _log("retrieval_failed", error_type=type(exc).__name__, error=str(exc)[:200])
            return ""
        if block:
            _log(
                "retrieved",
                chars=len(block),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                embed_mode=self.embed_mode,
            )
        return block

    # -------------------------------------------------------- extraction

    async def _worker_loop(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.poll_seconds)
            except (asyncio.TimeoutError, TimeoutError):
                pass
            except asyncio.CancelledError:
                raise
            self._wake.clear()
            try:
                await self.run_extraction_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _log("worker_error", error_type=type(exc).__name__, error=str(exc)[:200])

    async def run_extraction_once(self, *, force: bool = False) -> dict[str, object]:
        """Run one Stage A(+B) batch if enough turns have piled up."""
        if not (self.enabled and self._started):
            return {"status": "disabled"}
        pending = await asyncio.to_thread(self.store.pending_turns, self.session_id)
        if not pending or (len(pending) < self.batch_turns and not force):
            return {"status": "waiting", "pending": len(pending)}
        batch = pending[: self.batch_turns] if not force else pending
        turn_ids = [int(row["id"]) for row in batch]
        turns = [
            {"user_text": row["user_text"], "assistant_text": row["assistant_text"]}
            for row in batch
        ]

        stage_a_message = build_stage_a_user_message(self.character_name, turns)
        started = time.perf_counter()
        raw_a = ""
        try:
            raw_a = await self._call_extraction_llm(STAGE_A_SYSTEM_PROMPT, stage_a_message)
            items = parse_stage_a(raw_a)
        except Exception as exc:
            return await self._hold_batch(exc, turn_ids, stage="A", raw=raw_a)

        if not items:
            await asyncio.to_thread(self.store.advance_watermark, self.session_id, turn_ids[-1])
            _log("extracted", turns=len(batch), items=0, stage_b=False)
            return {"status": "empty", "turns": len(batch)}

        # Stage B only pays for itself when there is something to reconcile
        # against; a candidate-free batch takes the reference's fast path.
        candidates = await asyncio.to_thread(self._select_candidates, items)
        operations: list[Mapping[str, object]] = []
        stage_b_used = False
        if candidates:
            try:
                raw_b = await self._call_extraction_llm(
                    STAGE_B_SYSTEM_PROMPT, build_stage_b_user_message(items, candidates)
                )
                operations = parse_stage_b(raw_b)
                stage_b_used = True
            except Exception as exc:
                # Stage A already produced usable items, so holding the batch
                # would only spend the extraction LLM twice on the same turns.
                # Degrade to the ADD-only path instead; content_hash dedup is
                # what keeps duplicates out either way.
                _log("stage_b_failed", error_type=type(exc).__name__, error=str(exc)[:300])

        summary = await asyncio.to_thread(
            self._apply_batch, items, turn_ids, operations if stage_b_used else None, candidates
        )
        await asyncio.to_thread(self.store.advance_watermark, self.session_id, turn_ids[-1])
        _log(
            "extracted",
            turns=len(batch),
            items=len(items),
            stage_b=stage_b_used,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            **summary,
        )
        return {
            "status": "ok",
            "turns": len(batch),
            "items": len(items),
            "stage_b": stage_b_used,
            **summary,
        }

    def _select_candidates(
        self, items: Sequence[Mapping[str, object]]
    ) -> list[dict[str, object]]:
        return select_candidates(self.store, self._ensure_embedder(), self.session_id, items)

    def _apply_batch(
        self,
        items: Sequence[Mapping[str, object]],
        turn_ids: Sequence[int],
        operations: Sequence[Mapping[str, object]] | None,
        candidates: Sequence[Mapping[str, object]],
    ) -> dict[str, int]:
        applier = ExtractionApplier(
            self.store, self._ensure_embedder(), session_id=self.session_id, turn_ids=turn_ids
        )
        if operations is None:
            return applier.apply_items(items)
        return applier.apply_operations(operations, items, candidates)

    async def _hold_batch(
        self, exc: Exception, turn_ids: Sequence[int], *, stage: str, raw: str
    ) -> dict[str, object]:
        """Leave the watermark put so the batch retries; dead-letter at N fails."""
        fail_count = await asyncio.to_thread(
            self.store.record_failure, self.session_id, f"stage {stage}: {exc}"
        )
        _log(
            "extraction_failed",
            stage=stage,
            error_type=type(exc).__name__,
            error=str(exc)[:300],
            fail_count=fail_count,
            raw=(raw or "")[:600],
        )
        if fail_count >= self.max_failures:
            await asyncio.to_thread(self.store.advance_watermark, self.session_id, turn_ids[-1])
            _log("extraction_skipped", stage=stage, turns=len(turn_ids), fail_count=fail_count)
            return {"status": "skipped", "fail_count": fail_count}
        return {"status": "held", "fail_count": fail_count}

    async def _call_extraction_llm(self, system_prompt: str, user_message: str) -> str:
        if self._extraction_caller is not None:
            return await self._extraction_caller(system_prompt, user_message)
        providers = [
            str(self.config.get("extraction_provider") or ""),
            str(self.config.get("extraction_fallback_provider") or ""),
        ]
        errors: list[str] = []
        for provider in [value for value in providers if value]:
            mode_config = resolve_extraction_mode(self.llm_config, provider)
            if mode_config is None:
                errors.append(f"{provider}: no matching mode")
                continue
            overrides = self.config.get("extraction_overrides")
            if isinstance(overrides, Mapping):
                mode_config = _deep_merge(mode_config, overrides)
            try:
                return await self._stream_to_text(mode_config, system_prompt, user_message)
            except Exception as exc:
                errors.append(f"{provider}: {type(exc).__name__}: {exc}")
                _log("extraction_provider_failed", provider=provider, error=str(exc)[:200])
        raise RuntimeError("; ".join(errors) or "no extraction provider configured")

    async def _stream_to_text(
        self, mode_config: Mapping[str, object], system_prompt: str, user_message: str
    ) -> str:
        backend = build_backend(mode_config, self._client())
        chunks: list[str] = []
        async for delta in backend.stream_completion(
            system_prompt, [{"role": "user", "content": user_message}], memory_block=""
        ):
            chunks.append(delta)
        return "".join(chunks)

    def _client(self):
        """Private httpx client: extraction must not share the speech path's."""
        if self._http_client is None:
            import httpx  # noqa: PLC0415 - only the background path needs it

            self._http_client = httpx.AsyncClient()
        return self._http_client

    # -------------------------------------------------------------- health

    def health(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "enabled": bool(self.enabled),
            "embed_mode": self.embed_mode,
            "rows": 0,
            "pending_jobs": 0,
            "last_extraction_ts": None,
        }
        if not (self.enabled and self._started):
            return payload
        try:
            payload.update(self.store.stats())
        except Exception as exc:
            payload["error"] = type(exc).__name__
        return payload


def _swallow(task: asyncio.Task) -> None:
    if not task.cancelled():
        task.exception()
