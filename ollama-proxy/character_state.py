"""Small, bounded per-session character-state runtime.

This module deliberately records observations; it does not select dialogue,
actions, or proactive behaviour.  Callers may feed ``prompt_block`` to a model
as compact context and may apply a model-produced, allow-listed state update.
"""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import json
import threading
import time
from typing import Any, Callable, Mapping, Optional


class CharacterStateRuntime:
    """Thread-safe, in-memory LRU store for short-lived character state.

    ``silence_ms`` means elapsed time since the latest user observation.  It is
    calculated when a snapshot or prompt is requested, rather than relying on
    a background worker.
    """

    _TEXT_FIELDS = frozenset({
        "current_topic", "dialogue_goal", "user_interest", "airi_interest",
        "emotion", "emotion_reason", "relationship_stage", "last_question",
        "last_action", "last_tool_result", "repeat_intent",
    })
    _MODEL_TEXT_FIELDS = frozenset({
        "current_topic", "dialogue_goal", "user_interest", "airi_interest",
        "emotion", "emotion_reason", "relationship_stage",
    })
    _MODEL_BOOL_FIELDS = frozenset({"previous_answer_satisfied"})
    _MODEL_LIST_FIELDS = frozenset({"intimacy_evidence"})

    def __init__(
        self,
        max_sessions: int = 256,
        evidence_limit: int = 8,
        clock: Optional[Callable[[], float]] = None,
        text_limit: int = 240,
        tool_result_limit: int = 320,
    ) -> None:
        if max_sessions < 1 or evidence_limit < 1 or text_limit < 16 or tool_result_limit < 16:
            raise ValueError("state limits must be positive and practical")
        self.max_sessions = max_sessions
        self.evidence_limit = evidence_limit
        self.text_limit = text_limit
        self.tool_result_limit = tool_result_limit
        self._clock = clock or time.time
        self._sessions: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def _session_id(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("session_id must be a non-empty string")
        return value.strip()[:128]

    @staticmethod
    def _now(value: Optional[float], clock: Callable[[], float]) -> float:
        candidate = clock() if value is None else value
        if isinstance(candidate, bool) or not isinstance(candidate, (int, float)):
            raise ValueError("now must be a numeric timestamp")
        return float(candidate)

    @staticmethod
    def _compact(value: Any, limit: int) -> Optional[str]:
        if not isinstance(value, str):
            return None
        value = " ".join(value.split())
        if not value:
            return None
        return value[:limit]

    def _blank(self, now: float) -> dict[str, Any]:
        return {
            "current_topic": None, "dialogue_goal": None, "user_interest": None,
            "airi_interest": None, "emotion": None, "emotion_reason": None,
            "relationship_stage": None, "intimacy_evidence": [], "last_question": None,
            "last_action": None, "last_tool_result": None, "repeat_intent": None,
            "previous_answer_satisfied": "unknown", "silence_ms": 0,
            "silence_before_turn_ms": 0,
            "last_user_at": None, "last_assistant_at": None, "last_proactive_at": None,
            "version": 0, "updated_at": now,
        }

    def _get(self, session_id: str, now: float) -> dict[str, Any]:
        state = self._sessions.get(session_id)
        if state is None:
            state = self._blank(now)
            self._sessions[session_id] = state
            while len(self._sessions) > self.max_sessions:
                self._sessions.popitem(last=False)
        else:
            self._sessions.move_to_end(session_id)
        return state

    @staticmethod
    def _touch(state: dict[str, Any], now: float) -> None:
        state["version"] += 1
        state["updated_at"] = now

    def observe_user(
        self, session_id: str, text: str, repeat_intent: Optional[str] = None,
        repeat_count: Optional[int] = None, now: Optional[float] = None,
    ) -> dict[str, Any]:
        """Record a user turn; ``repeat_count`` is accepted as observation only."""
        del repeat_count  # Counts must never create deterministic response rules.
        sid, at = self._session_id(session_id), self._now(now, self._clock)
        topic, intent = self._compact(text, self.text_limit), self._compact(repeat_intent, self.text_limit)
        with self._lock:
            state = self._get(sid, at)
            previous_user_at = state["last_user_at"]
            state["silence_before_turn_ms"] = (
                max(0, int((at - previous_user_at) * 1000))
                if previous_user_at is not None
                else 0
            )
            if topic is not None:
                state["current_topic"] = topic
                state["last_question"] = topic
            state["repeat_intent"] = intent
            if intent is not None:
                state["previous_answer_satisfied"] = False
            else:
                # Without explicit/similar-repeat feedback, do not pretend to
                # know whether the immediately preceding answer satisfied the
                # user. A model-owned update may later replace this value.
                state["previous_answer_satisfied"] = "unknown"
            state["last_user_at"] = at
            state["silence_ms"] = 0
            self._touch(state, at)
            return self._snapshot(state, at)

    def observe_assistant(
        self, session_id: str, text: str, *, emotion: Optional[str] = None,
        emotion_reason: Optional[str] = None, action: Optional[str] = None,
        tool_result: Optional[str] = None, proactive: bool = False,
        satisfied: Optional[bool] = None, now: Optional[float] = None,
    ) -> dict[str, Any]:
        """Record actual assistant output/execution metadata without choosing it."""
        sid, at = self._session_id(session_id), self._now(now, self._clock)
        with self._lock:
            state = self._get(sid, at)
            # The assistant text is intentionally not retained as
            # ``last_question``: that field is an actual user observation.
            # Keeping the parameter makes the completion boundary explicit
            # without duplicating the full answer in short state.
            del text
            for field, value in (("emotion", emotion), ("emotion_reason", emotion_reason), ("last_action", action)):
                compact = self._compact(value, self.text_limit)
                if compact is not None:
                    state[field] = compact
            result = self._compact(tool_result, self.tool_result_limit)
            if result is not None:
                state["last_tool_result"] = result
            if isinstance(satisfied, bool):
                state["previous_answer_satisfied"] = satisfied
            state["last_assistant_at"] = at
            if proactive:
                state["last_proactive_at"] = at
            self._touch(state, at)
            return self._snapshot(state, at)

    def apply_model_state_update(
        self, session_id: str, mapping: Mapping[str, Any], now: Optional[float] = None,
    ) -> dict[str, Any]:
        """Apply only valid model-owned fields; unknown/invalid values are ignored."""
        if not isinstance(mapping, Mapping):
            raise ValueError("mapping must implement Mapping")
        sid, at = self._session_id(session_id), self._now(now, self._clock)
        with self._lock:
            state = self._get(sid, at)
            changed = False
            for field in self._MODEL_TEXT_FIELDS:
                if field in mapping:
                    value = self._compact(mapping[field], self.text_limit)
                    if value is not None:
                        state[field], changed = value, True
            if "previous_answer_satisfied" in mapping and isinstance(mapping["previous_answer_satisfied"], (bool, str)):
                value = mapping["previous_answer_satisfied"]
                if isinstance(value, bool) or value == "unknown":
                    state["previous_answer_satisfied"], changed = value, True
            if "intimacy_evidence" in mapping and isinstance(mapping["intimacy_evidence"], (list, tuple)):
                evidence = [self._compact(item, self.text_limit) for item in mapping["intimacy_evidence"]]
                state["intimacy_evidence"] = [item for item in evidence if item is not None][-self.evidence_limit:]
                changed = True
            if changed:
                self._touch(state, at)
            return self._snapshot(state, at)

    def _snapshot(self, state: dict[str, Any], now: float) -> dict[str, Any]:
        result = deepcopy(state)
        last_user = result["last_user_at"]
        result["silence_ms"] = max(0, int((now - last_user) * 1000)) if last_user is not None else 0
        return result

    def snapshot(self, session_id: str) -> dict[str, Any]:
        sid, at = self._session_id(session_id), self._now(None, self._clock)
        with self._lock:
            return self._snapshot(self._get(sid, at), at)

    def snapshot_if_present(self, session_id: str) -> Optional[dict[str, Any]]:
        """Read a state without creating it or changing its LRU position."""
        sid, at = self._session_id(session_id), self._now(None, self._clock)
        with self._lock:
            state = self._sessions.get(sid)
            return self._snapshot(state, at) if state is not None else None

    def version_if_present(self, session_id: str) -> Optional[int]:
        """Read only the current version; absent/evicted sessions stay absent."""
        sid = self._session_id(session_id)
        with self._lock:
            state = self._sessions.get(sid)
            return state["version"] if state is not None else None

    def prompt_block(self, session_id: str) -> str:
        """Return bounded metadata without duplicating raw user dialogue.

        ``current_topic`` and ``last_question`` are direct compact copies of a
        user turn. The dialogue itself is already available through foreground
        projection, so serializing those fields as a system message both leaks
        content across trust roles and spends prompt budget twice.
        """
        state = self.snapshot(session_id)
        # Model-owned text/list fields can echo a user turn even when the
        # evaluator was asked to summarize it. Keep them in internal state for
        # versioned evaluation, but never promote them into a trusted system
        # message. Only controlled enums/actions and numeric timing leave.
        fields = {key: state[key] for key in (
            "last_action", "repeat_intent", "previous_answer_satisfied",
            "silence_ms", "silence_before_turn_ms", "last_user_at", "last_assistant_at",
            "last_proactive_at", "version",
        )}
        return "[Character State] " + json.dumps(fields, ensure_ascii=False, separators=(",", ":"))

    def health(self) -> dict[str, int | bool]:
        """Privacy-safe capacity telemetry; session ids and text never leave."""
        with self._lock:
            return {
                "enabled": True,
                "sessions": len(self._sessions),
                "max_sessions": self.max_sessions,
                "evidence_limit": self.evidence_limit,
            }
