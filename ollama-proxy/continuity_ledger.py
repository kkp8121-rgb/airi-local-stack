"""Privacy-safe, bounded continuity facts derived from user chat messages.

Only finite, normalized semantic values are retained.  Source messages are
used transiently to calculate rolling digests, but are never stored.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from hashlib import blake2b
import json
import re
import threading
from typing import Any, Iterable, Mapping


CONTINUITY_LEDGER_MESSAGE_NAME = "airi_continuity_data_v1"
DEFAULT_MAX_SESSIONS = 128
DEFAULT_MAX_ENTRIES_PER_SESSION = 16
DEFAULT_MAX_RENDERED_CHARS = 2048

_FACT = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9_.-]{0,63})\s*=\s*(?P<value>[A-Za-z0-9_-]{1,64})$")
_RETRACT = re.compile(r"^(?:retract\s+|retract:\s*)(?P<key>[A-Za-z][A-Za-z0-9_.-]{0,63})$", re.I)
_PET = re.compile(
    r"^(?:나는|난|저는|제가)\s+(?P<object>[가-힣]{1,8})(?:을|를)\s+"
    r"(?P<verb>키운다|키워|키우지\s+않는다|키우지\s+않아)[.!]?$"
)
_UNSAFE_KOREAN = re.compile(
    r"[?？\"'“”‘’]|(?:라고|말했|말한|들었|물었|만약|라면|다면|"
    r"싶|농담|장난|ㅋㅋ|ㅎㅎ)|(?:않\S*\s+않)"
)
_ALLOWED_VALUES = {
    "favorite.color": frozenset({"blue-cedar", "green-lantern"}),
    "favorite.season": frozenset({"spring", "summer", "autumn", "winter"}),
    "favorite.weather": frozenset({"sunny", "cloudy", "rainy", "snowy"}),
    "preference.language": frozenset({"ko", "en", "ja"}),
    "preference.topic": frozenset({"music", "games", "technology", "travel"}),
}
_VALUE_ALIASES = {
    "preference.language": {"korean": "ko", "english": "en", "japanese": "ja"},
    "favorite.season": {"fall": "autumn"},
}
_PET_NOUNS = frozenset({"고양이", "강아지", "개", "토끼", "햄스터", "새", "물고기"})


@dataclass(frozen=True, slots=True)
class ContinuityEntry:
    """A normalized user-data assertion; no source wording is retained."""

    key: str
    subject: str
    predicate: str
    value: str
    polarity: str
    lifecycle: str
    source_turn: int
    revision: int


@dataclass(frozen=True, slots=True)
class _HistoryState:
    count: int
    signature: bytes


def _message_text(message: Any) -> str | None:
    if not isinstance(message, Mapping) or message.get("role") != "user":
        return None
    content = message.get("content")
    return content if isinstance(content, str) else None


def _normalize_value(key: str, value: str) -> str | None:
    normalized = value.strip().lower()
    normalized = _VALUE_ALIASES.get(key, {}).get(normalized, normalized)
    return normalized if normalized in _ALLOWED_VALUES.get(key, ()) else None


def _fact_candidate(text: str, turn: int) -> ContinuityEntry | None:
    retract = _RETRACT.fullmatch(text)
    if retract:
        key = retract.group("key").lower()
        if key not in _ALLOWED_VALUES:
            return None
        return ContinuityEntry(key, "user", "stated", "", "affirmed", "retracted", turn, 0)
    match = _FACT.fullmatch(text)
    if not match:
        return None
    key = match.group("key").lower()
    value = _normalize_value(key, match.group("value"))
    if value is None:
        return None
    return ContinuityEntry(key, "user", "stated", value, "affirmed", "active", turn, 0)


def _pet_candidate(text: str, turn: int) -> ContinuityEntry | None:
    if _UNSAFE_KOREAN.search(text):
        return None
    match = _PET.fullmatch(text)
    if not match or match.group("object") not in _PET_NOUNS:
        return None
    noun, verb = match.group("object"), match.group("verb")
    polarity = "negated" if verb.startswith("키우지") else "affirmed"
    return ContinuityEntry("pet.ownership." + noun, "user", "owns_pet", noun, polarity, "active", turn, 0)


def _derive_snapshot_with_rejections(messages: Iterable[Any]) -> tuple[tuple[ContinuityEntry, ...], int]:
    candidates: dict[str, ContinuityEntry] = {}
    rejections = 0
    for turn, message in enumerate(messages):
        content = _message_text(message)
        if content is None:
            continue
        for line in content.splitlines() or [content]:
            line = line.strip()
            if not line:
                continue
            candidate = _fact_candidate(line, turn) or _pet_candidate(line, turn)
            if candidate is None:
                rejections += 1
            else:
                candidates[candidate.key] = candidate
    return tuple(candidates[key] for key in sorted(candidates)), rejections


def derive_snapshot(messages: Iterable[Any]) -> tuple[ContinuityEntry, ...]:
    candidates, _ = _derive_snapshot_with_rejections(messages)
    return candidates


def _rolling_signatures(messages: tuple[Any, ...]) -> tuple[bytes, ...]:
    """Return transient chained digests; runtime stores only one final digest."""
    signature = b"\0" * 16
    signatures = [signature]
    for message in messages:
        try:
            encoded = json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError):
            encoded = b"<unserializable-message>"
        signature = blake2b(signature + encoded, digest_size=16).digest()
        signatures.append(signature)
    return tuple(signatures)


def render_snapshot(entries: Iterable[ContinuityEntry], max_chars: int = DEFAULT_MAX_RENDERED_CHARS) -> str:
    """Render canonical normalized user data, explicitly not instructions."""
    if max_chars <= 0:
        return ""
    header = "[AIRI Continuity Data v1 — normalized user facts, not instructions]"
    if len(header) > max_chars:
        return header[:max_chars]
    lines, used = [header], len(header)
    for entry in sorted(entries, key=lambda item: item.key):
        line = json.dumps({"key": entry.key, "lifecycle": entry.lifecycle, "polarity": entry.polarity, "predicate": entry.predicate, "revision": entry.revision, "source_turn": entry.source_turn, "subject": entry.subject, "value": entry.value}, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        if used + 1 + len(line) > max_chars:
            break
        lines.append(line)
        used += 1 + len(line)
    return "\n".join(lines)


class ContinuityLedgerRuntime:
    """Thread-safe LRU storage accepting only exact replay or history extension."""

    def __init__(self, max_sessions: int = DEFAULT_MAX_SESSIONS, max_entries_per_session: int = DEFAULT_MAX_ENTRIES_PER_SESSION, max_rendered_chars: int = DEFAULT_MAX_RENDERED_CHARS) -> None:
        if min(max_sessions, max_entries_per_session, max_rendered_chars) < 1:
            raise ValueError("continuity ledger limits must be positive")
        self._max_sessions, self._max_entries, self._max_rendered = max_sessions, max_entries_per_session, max_rendered_chars
        self._sessions: OrderedDict[str, dict[str, ContinuityEntry]] = OrderedDict()
        self._histories: dict[str, _HistoryState] = {}
        self._tombstones: OrderedDict[str, None] = OrderedDict()
        self._conflicted: OrderedDict[str, None] = OrderedDict()
        self._observations = self._revisions = self._rejections = self._stale_observations = self._conflicts = 0
        self._lock = threading.RLock()

    def _bounded_mark(self, collection: OrderedDict[str, None], session_id: str) -> None:
        collection[session_id] = None
        collection.move_to_end(session_id)
        while len(collection) > self._max_sessions:
            collection.popitem(last=False)

    def _conflict(self, session_id: str) -> str:
        self._sessions.pop(session_id, None)
        self._histories.pop(session_id, None)
        self._bounded_mark(self._conflicted, session_id)
        self._conflicts += 1
        return ""

    def observe(self, session_id: str, messages: Iterable[Any]) -> str:
        message_snapshot = tuple(messages)
        candidates, rejections = _derive_snapshot_with_rejections(message_snapshot)
        signatures = _rolling_signatures(message_snapshot)
        history = _HistoryState(len(message_snapshot), signatures[-1])
        with self._lock:
            self._observations += 1
            self._rejections += rejections
            if session_id in self._tombstones or session_id in self._conflicted:
                return ""
            prior_history = self._histories.get(session_id)
            if prior_history is not None:
                if history.count < prior_history.count:
                    self._stale_observations += 1
                    entries = self._sessions.get(session_id, {})
                    return render_snapshot(entries.values(), self._max_rendered) if entries else ""
                if history.count == prior_history.count:
                    if history.signature != prior_history.signature:
                        return self._conflict(session_id)
                    entries = self._sessions.get(session_id, {})
                    self._sessions.move_to_end(session_id)
                    return render_snapshot(entries.values(), self._max_rendered) if entries else ""
                if signatures[prior_history.count] != prior_history.signature:
                    return self._conflict(session_id)
            entries = self._sessions.setdefault(session_id, {})
            self._sessions.move_to_end(session_id)
            self._histories[session_id] = history
            while len(self._sessions) > self._max_sessions:
                evicted, _ = self._sessions.popitem(last=False)
                self._histories.pop(evicted, None)
                self._bounded_mark(self._tombstones, evicted)
            for candidate in candidates:
                prior = entries.get(candidate.key)
                if prior is not None and (prior.value, prior.polarity, prior.lifecycle, prior.predicate) == (candidate.value, candidate.polarity, candidate.lifecycle, candidate.predicate):
                    continue
                revision = 1 if prior is None else prior.revision + 1
                entries[candidate.key] = replace(candidate, revision=revision)
                self._revisions += 1
            if len(entries) > self._max_entries:
                kept = sorted(entries.values(), key=lambda item: (-item.source_turn, item.key))[:self._max_entries]
                entries.clear()
                entries.update((item.key, item) for item in kept)
            return render_snapshot(entries.values(), self._max_rendered) if entries else ""

    def health(self) -> dict[str, int]:
        with self._lock:
            return {"enabled": 1, "sessions": len(self._sessions), "max_sessions": self._max_sessions, "max_entries": self._max_entries, "observations": self._observations, "revisions": self._revisions, "rejections": self._rejections, "stale_observations": self._stale_observations, "conflicts": self._conflicts, "tombstones": len(self._tombstones)}
