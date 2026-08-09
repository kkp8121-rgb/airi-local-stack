"""Local, fail-soft post-turn evaluator for bounded character state.

It is deliberately an observer: it cannot select speech, actions, tools, or
safety outcomes.  Work is scheduled only after a completed assistant turn.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit

import httpx

from character_state import CharacterStateRuntime


_FIELDS = frozenset({
    "current_topic", "dialogue_goal", "user_interest", "airi_interest",
    "emotion", "emotion_reason", "relationship_stage", "intimacy_evidence",
    "previous_answer_satisfied",
})
_TEXT_FIELDS = _FIELDS - {"intimacy_evidence", "previous_answer_satisfied"}
_KEEP_ALIVE_RE = re.compile(r"^(?:-1|0|[1-9][0-9]*(?:ms|s|m|h))$")


def state_update_schema(evidence_limit: int = 8) -> dict[str, Any]:
    """Ollama ``format`` schema and parser share this single field contract."""
    nullable_text = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    return {
        "type": "object", "additionalProperties": False,
        "required": sorted(_FIELDS),
        "properties": {
            **{field: nullable_text for field in _TEXT_FIELDS},
            "intimacy_evidence": {"anyOf": [{"type": "array", "items": {"type": "string"}, "maxItems": evidence_limit}, {"type": "null"}]},
            "previous_answer_satisfied": {"anyOf": [{"type": "boolean"}, {"type": "string", "enum": ["unknown"]}, {"type": "null"}]},
        },
    }


def _truthy(name: str, default: bool = False) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


def _bounded_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(high, max(low, value))


def _ollama_keep_alive(name: str, default: str = "30m") -> str:
    value = os.getenv(name, default).strip()
    return value if _KEEP_ALIVE_RE.fullmatch(value) else default


def is_loopback_url(value: str) -> bool:
    """Accept only explicit http loopback upstreams, never external hosts."""
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1", "localhost"}
            and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
        )
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class CharacterStateEvaluatorConfig:
    enabled: bool = False
    provider: str = "ollama"
    model: str = "exaone-airi:2.4b"
    upstream: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 15.0
    num_ctx: int = 2048
    # Match the foreground local chat default.  Setting the evaluator to CPU
    # while chat is GPU-resident makes Ollama repeatedly evict/reload runners.
    num_gpu: int = 999
    keep_alive: str = "30m"
    temperature: float = 0.2
    max_tokens: int = 320
    # Give a just-finished foreground turn a quiet period before this
    # best-effort observer competes for Ollama's single local runner.
    idle_delay_seconds: float = 6.0
    shutdown_timeout_seconds: float = 2.0

    @classmethod
    def from_env(cls, *, default_upstream: str = "http://127.0.0.1:11434") -> "CharacterStateEvaluatorConfig":
        upstream = os.getenv("AIRI_CHARACTER_EVALUATOR_UPSTREAM", default_upstream).rstrip("/")
        try:
            timeout = float(os.getenv("AIRI_CHARACTER_EVALUATOR_TIMEOUT_SECONDS", "15"))
        except ValueError:
            timeout = 15.0
        try:
            temperature = float(os.getenv("AIRI_CHARACTER_EVALUATOR_TEMPERATURE", "0.2"))
        except ValueError:
            temperature = 0.2
        try:
            idle_delay = float(os.getenv("AIRI_CHARACTER_EVALUATOR_IDLE_DELAY_SECONDS", "6"))
        except ValueError:
            idle_delay = 6.0
        return cls(
            enabled=_truthy("AIRI_CHARACTER_EVALUATOR_ENABLED"),
            provider=os.getenv("AIRI_CHARACTER_EVALUATOR_PROVIDER", "ollama").strip().lower(),
            model=os.getenv("AIRI_CHARACTER_EVALUATOR_MODEL", "exaone-airi:2.4b").strip()[:128],
            upstream=upstream,
            timeout_seconds=min(60.0, max(1.0, timeout)),
            num_ctx=_bounded_int("AIRI_CHARACTER_EVALUATOR_NUM_CTX", 2048, 512, 4096),
            num_gpu=_bounded_int("AIRI_CHARACTER_EVALUATOR_NUM_GPU", 999, 0, 999),
            keep_alive=_ollama_keep_alive("AIRI_CHARACTER_EVALUATOR_KEEP_ALIVE"),
            temperature=min(1.0, max(0.0, temperature)),
            max_tokens=_bounded_int("AIRI_CHARACTER_EVALUATOR_MAX_TOKENS", 320, 64, 512),
            idle_delay_seconds=min(30.0, max(0.0, idle_delay)),
            shutdown_timeout_seconds=min(10.0, max(0.1, timeout / 5)),
        )

    @property
    def configured(self) -> bool:
        return self.provider == "ollama" and bool(self.model) and is_loopback_url(self.upstream)


def parse_state_update(raw: str, *, text_limit: int = 240, evidence_limit: int = 8) -> dict[str, Any] | None:
    """Parse exactly the allow-listed JSON object; malformed data is neutral."""
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(value, dict) or set(value) != _FIELDS:
        return None
    result: dict[str, Any] = {}
    for field in _TEXT_FIELDS:
        item = value[field]
        if item is not None and not isinstance(item, str):
            return None
        if isinstance(item, str):
            compact = " ".join(item.split())[:text_limit]
            if compact:
                result[field] = compact
    evidence = value["intimacy_evidence"]
    if evidence is not None and (not isinstance(evidence, list) or len(evidence) > evidence_limit):
        return None
    if isinstance(evidence, list):
        if not all(isinstance(item, str) for item in evidence):
            return None
        result["intimacy_evidence"] = [" ".join(item.split())[:text_limit] for item in evidence if " ".join(item.split())][:evidence_limit]
    satisfied = value["previous_answer_satisfied"]
    if satisfied not in (None, True, False, "unknown"):
        return None
    if satisfied is not None:
        result["previous_answer_satisfied"] = satisfied
    return result


class CharacterStateEvaluator:
    def __init__(self, state: CharacterStateRuntime, config: CharacterStateEvaluatorConfig | None = None) -> None:
        self.state, self.config = state, config or CharacterStateEvaluatorConfig.from_env()
        self._client: httpx.AsyncClient | None = None
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._latest: dict[str, tuple[str, str, int, dict[str, Any]]] = {}
        self._delay_events: dict[str, asyncio.Event] = {}
        self._delaying_sessions: set[str] = set()
        self._gate = asyncio.Semaphore(1)
        self._stopping = False
        self._last_status = "disabled" if not self.config.enabled else "unconfigured"

    async def startup(self) -> None:
        if self.config.enabled and self.config.configured and not self._stopping:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self.config.timeout_seconds))
            self._last_status = "ready"

    def schedule_completed_turn(self, session_id: str, user_text: str, assistant_text: str, *, state_version: int | None = None, state_snapshot: Mapping[str, Any] | None = None) -> None:
        """Non-blocking, latest-turn-wins scheduling with one worker/session."""
        if self._stopping or self._client is None or not user_text or not assistant_text:
            return
        # Evaluator bookkeeping is bounded independently of state storage.
        # A flood of one-shot headers must not create unbounded background work.
        if session_id not in self._latest and session_id not in self._tasks:
            if len(set(self._latest) | set(self._tasks)) >= self.state.max_sessions:
                self._last_status = "capacity"
                return
        if state_snapshot is None:
            state_snapshot = self.state.snapshot_if_present(session_id)
        if state_snapshot is None:
            self._last_status = "stale"
            return
        # The caller snapshot is state context, not arbitrary durable history.
        captured = dict(state_snapshot)
        if state_version is None:
            state_version = captured.get("version")
        if isinstance(state_version, bool) or not isinstance(state_version, int):
            return
        self._latest[session_id] = (user_text, assistant_text, state_version, captured)
        # Wake an in-progress debounce immediately.  The worker will discard
        # its older turn before it can issue an HTTP request.
        event = self._delay_events.get(session_id)
        if event is not None:
            event.set()
        task = self._tasks.get(session_id)
        if task is None or task.done():
            self._start_task(session_id)

    def _start_task(self, session_id: str) -> None:
        task = asyncio.create_task(self._drain(session_id))
        self._tasks[session_id] = task
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        task.add_done_callback(lambda done, sid=session_id: self._task_finished(sid, done))

    def _task_finished(self, session_id: str, done: asyncio.Task[None]) -> None:
        """Close the drain-exit/schedule race without another queue layer."""
        if self._tasks.get(session_id) is not done:
            return
        self._delaying_sessions.discard(session_id)
        if not self._stopping and session_id in self._latest:
            self._start_task(session_id)
        else:
            self._tasks.pop(session_id, None)
            self._delay_events.pop(session_id, None)

    def _prompt(self, snapshot: Mapping[str, Any], user_text: str, assistant_text: str) -> str:
        # State and current completed turn are bounded separately to avoid any history replay.
        return (
            "Return only one JSON object with exactly these keys: current_topic, dialogue_goal, "
            "user_interest, airi_interest, emotion, emotion_reason, relationship_stage, "
            "intimacy_evidence, previous_answer_satisfied. Values: strings or null; "
            "intimacy_evidence list of short strings or null; previous_answer_satisfied true/false/unknown/null. "
            "Describe state only. Do not make safety, speech, action, tool, or response decisions.\n"
            + json.dumps({"state": snapshot, "user": user_text[:1024], "assistant": assistant_text[:1536]}, ensure_ascii=False, separators=(",", ":"))
        )

    async def _drain(self, session_id: str) -> None:
        while not self._stopping:
            turn = self._latest.pop(session_id, None)
            if turn is None:
                return
            if await self._debounce(session_id):
                # A newer completed turn arrived while this one was cooling
                # down.  Coalesce to it and restart the full quiet period.
                continue
            await self._evaluate(session_id, *turn)

    async def _debounce(self, session_id: str) -> bool:
        """Wait for foreground idleness; return true when a turn supersedes it."""
        delay = self.config.idle_delay_seconds
        if delay <= 0:
            return False
        # A newer turn can arrive after _drain() popped the old tuple but
        # before this coroutine creates/clears its wake event.  Check the
        # latest slot on both sides of clear() so that narrow race cannot make
        # an obsolete turn occupy Ollama after the quiet period.
        if session_id in self._latest:
            return True
        event = self._delay_events.setdefault(session_id, asyncio.Event())
        event.clear()
        if session_id in self._latest:
            return True
        self._delaying_sessions.add(session_id)
        self._last_status = "debouncing"
        try:
            await asyncio.wait_for(event.wait(), timeout=delay)
            return True
        except asyncio.TimeoutError:
            return session_id in self._latest
        finally:
            self._delaying_sessions.discard(session_id)

    async def _evaluate(self, session_id: str, user_text: str, assistant_text: str, scheduled_version: int, snapshot: Mapping[str, Any]) -> None:
        client = self._client
        if client is None or self._stopping:
            return
        self._last_status = "running"
        try:
            async with self._gate:
                if self._stopping:
                    return
                response = await client.post(
                    f"{self.config.upstream}/api/chat",
                    json={"model": self.config.model, "stream": False, "keep_alive": self.config.keep_alive, "format": state_update_schema(self.state.evidence_limit), "messages": [{"role": "user", "content": self._prompt(snapshot, user_text, assistant_text)}], "options": {"num_ctx": self.config.num_ctx, "num_gpu": self.config.num_gpu, "temperature": self.config.temperature, "num_predict": self.config.max_tokens}},
                )
                response.raise_for_status()
                payload = response.json()
                message = payload.get("message", {}) if isinstance(payload, Mapping) else {}
                update = parse_state_update(message.get("content") if isinstance(message, Mapping) else None, text_limit=self.state.text_limit, evidence_limit=self.state.evidence_limit)
                if self._stopping or update is None:
                    self._last_status = "malformed"
                    return
                if self.state.version_if_present(session_id) != scheduled_version:
                    self._last_status = "stale"
                    return
                self.state.apply_model_state_update(session_id, update)
                self._last_status = "ok"
        except asyncio.CancelledError:
            raise
        except httpx.TimeoutException:
            self._last_status = "timeout"
        except Exception:
            self._last_status = "error"

    async def shutdown(self) -> None:
        self._stopping = True
        tasks = list(self._background_tasks)
        self._latest.clear()
        self._delay_events.clear()
        self._delaying_sessions.clear()
        self._tasks.clear()
        if tasks:
            for task in tasks:
                task.cancel()
            _done, pending = await asyncio.wait(tasks, timeout=self.config.shutdown_timeout_seconds)
            if pending:
                for task in tasks:
                    task.cancel()
                # A cancellation-ignoring task must not make shutdown hang;
                # it remains in _background_tasks until its callback runs.
                await asyncio.wait(pending, timeout=0.05)
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._last_status = "stopped"

    async def interrupt_for_chat(self) -> None:
        """Release shared local-Ollama capacity before a foreground chat turn."""
        if not self._background_tasks and not self._latest:
            return
        tasks = list(self._background_tasks)
        # Clear first: cancelled callbacks cannot restart stale work or remove
        # a later completion task for the same session.
        self._latest.clear()
        self._delay_events.clear()
        self._delaying_sessions.clear()
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        self._last_status = "interrupted"
        # Give cooperative HTTP cancellation a short chance to leave Ollama's
        # queue, while keeping non-cooperative tasks tracked for shutdown.
        await asyncio.wait(tasks, timeout=0.05)

    def health(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "configured": self.config.configured,
            "ready": self._client is not None and not self._stopping,
            "num_gpu": self.config.num_gpu,
            "keep_alive": self.config.keep_alive,
            "idle_delay_seconds": self.config.idle_delay_seconds,
            "pending": len(self._latest),
            "delaying": len(self._delaying_sessions),
            "running": sum(not task.done() for task in self._background_tasks),
            "last_status": self._last_status,
        }
