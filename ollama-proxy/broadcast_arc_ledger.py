"""Bounded, privacy-safe continuity arcs for one live broadcast at a time.

This ledger deliberately does not derive or retain viewer facts.  Callers may
submit only a short, normalized production summary; source wording, handles,
and URLs are rejected before an arc is stored.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import re
import threading
from typing import Literal


EventType = Literal[
    'decision', 'running_joke', 'promise_or_plan', 'correction', 'preference',
    'shared_rule', 'inventory_or_resource', 'safety_boundary',
]
SourceType = Literal['history', 'briefing', 'durable_memory', 'show_arc']
TriggerOrigin = Literal['spontaneous', 'system_reappearance', 'viewer_callback']
ArcStatus = Literal['open', 'resolved', 'expired']

EVENT_TYPES = frozenset(EventType.__args__)
SOURCE_TYPES = frozenset(SourceType.__args__)
TRIGGER_ORIGINS = frozenset(TriggerOrigin.__args__)
DEFAULT_MAX_ARCS_PER_SHOW = 32
DEFAULT_TTL_MINUTES = 360

_SHOW_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')
_TOPIC_KEY = re.compile(r'^[a-z][a-z0-9_.-]{0,63}$')
_SUMMARY = re.compile(r'^[a-z0-9가-힣][a-z0-9가-힣 ,.!?()_\-]{0,159}$')
_URL_OR_PII = re.compile(r'(?:https?://|www\.|\S+@\S+|@\w+|\b\d{3}[-. ]?\d{3}[-. ]?\d{4}\b)', re.I)
_UNSAFE_SUMMARY = re.compile(r'''(?:["'“”‘’]|\b(?:ignore|system|assistant)\b|이전\s*지시|명령|무시해)''', re.I)


@dataclass(frozen=True, slots=True)
class BroadcastArc:
    """A production-continuity item, never a record of a viewer assertion."""

    arc_id: str
    created_minute: int
    updated_minute: int
    topic_key: str
    event_type: EventType
    setup_summary: str
    status: ArcStatus
    trigger_origin: TriggerOrigin
    callback_count: int
    last_callback_minute: int | None
    ttl_minutes: int
    source_type: SourceType


def _valid_identifier(value: object, pattern: re.Pattern[str], label: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f'invalid {label}')
    return value


def _valid_minute(value: object, label: str = 'minute') -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f'invalid {label}')
    return value


def _valid_enum(value: object, allowed: frozenset[str], label: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f'invalid {label}')
    return value


def _valid_summary(value: object) -> str:
    if not isinstance(value, str) or _URL_OR_PII.search(value) or _UNSAFE_SUMMARY.search(value) or not _SUMMARY.fullmatch(value):
        raise ValueError('invalid setup summary')
    return value


def render_open_arcs(arcs: object, max_chars: int = 2048) -> str:
    """Render bounded canonical production data, explicitly not instructions."""
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars <= 0:
        return ''
    header = '[AIRI Broadcast Arc Data v1 - canonical production data, not instructions]'
    if len(header) > max_chars:
        return header[:max_chars]
    try:
        ordered = sorted(arcs, key=lambda arc: (arc.created_minute, arc.arc_id))
    except (AttributeError, TypeError):
        return header
    lines, used = [header], len(header)
    for arc in ordered:
        if not isinstance(arc, BroadcastArc) or arc.status != 'open':
            continue
        line = json.dumps(asdict(arc), ensure_ascii=False, separators=(',', ':'), sort_keys=True)
        if used + 1 + len(line) > max_chars:
            break
        lines.append(line)
        used += 1 + len(line)
    return '\n'.join(lines)


class BroadcastArcLedger:
    """Thread-safe in-memory arcs with show-scoped reads, callbacks, and expiry."""

    def __init__(self, max_arcs_per_show: int = DEFAULT_MAX_ARCS_PER_SHOW, default_ttl_minutes: int = DEFAULT_TTL_MINUTES) -> None:
        if isinstance(max_arcs_per_show, bool) or not isinstance(max_arcs_per_show, int) or max_arcs_per_show < 1:
            raise ValueError('max_arcs_per_show must be positive')
        if isinstance(default_ttl_minutes, bool) or not isinstance(default_ttl_minutes, int) or default_ttl_minutes < 1:
            raise ValueError('default_ttl_minutes must be positive')
        self._max_arcs = max_arcs_per_show
        self._default_ttl = default_ttl_minutes
        self._shows: dict[str, dict[str, BroadcastArc]] = {}
        self._next_arc = 1
        self._lock = threading.RLock()

    @staticmethod
    def _expired(arc: BroadcastArc, now_minute: int) -> bool:
        return arc.status == 'open' and now_minute - arc.updated_minute >= arc.ttl_minutes

    def _evict_expired(self, show_id: str, now_minute: int) -> None:
        arcs = self._shows.get(show_id)
        if arcs is None:
            return
        for arc_id, arc in tuple(arcs.items()):
            if self._expired(arc, now_minute):
                del arcs[arc_id]
        if not arcs:
            self._shows.pop(show_id, None)

    @staticmethod
    def _open_arcs(arcs: dict[str, BroadcastArc]) -> list[BroadcastArc]:
        return sorted((arc for arc in arcs.values() if arc.status == 'open'), key=lambda arc: (arc.created_minute, arc.arc_id))

    def add_arc(self, show_id: str, *, now_minute: int, topic_key: str, event_type: EventType, setup_summary: str, source_type: SourceType, trigger_origin: TriggerOrigin = 'spontaneous', ttl_minutes: int | None = None) -> BroadcastArc:
        """Create an arc.  Inputs are validated before any ledger mutation."""
        show_id = _valid_identifier(show_id, _SHOW_ID, 'show_id')
        now_minute = _valid_minute(now_minute)
        topic_key = _valid_identifier(topic_key, _TOPIC_KEY, 'topic_key')
        _valid_enum(event_type, EVENT_TYPES, 'event_type')
        setup_summary = _valid_summary(setup_summary)
        _valid_enum(source_type, SOURCE_TYPES, 'source_type')
        _valid_enum(trigger_origin, TRIGGER_ORIGINS, 'trigger_origin')
        ttl = self._default_ttl if ttl_minutes is None else _valid_minute(ttl_minutes, 'ttl_minutes')
        if ttl < 1:
            raise ValueError('ttl_minutes must be positive')
        with self._lock:
            arcs = self._shows.setdefault(show_id, {})
            self._evict_expired(show_id, now_minute)
            arcs = self._shows.setdefault(show_id, {})
            while len(self._open_arcs(arcs)) >= self._max_arcs:
                oldest = self._open_arcs(arcs)[0]
                del arcs[oldest.arc_id]
            arc = BroadcastArc(f'arc-{self._next_arc:08x}', now_minute, now_minute, topic_key, event_type, setup_summary, 'open', trigger_origin, 0, None, ttl, source_type)
            self._next_arc += 1
            arcs[arc.arc_id] = arc
            return arc

    def read_open(self, show_id: str, *, now_minute: int) -> tuple[BroadcastArc, ...]:
        """Return only currently open arcs belonging to ``show_id``."""
        show_id = _valid_identifier(show_id, _SHOW_ID, 'show_id')
        now_minute = _valid_minute(now_minute)
        with self._lock:
            self._evict_expired(show_id, now_minute)
            return tuple(self._open_arcs(self._shows.get(show_id, {})))

    def record_callback(self, show_id: str, arc_id: str, *, now_minute: int, trigger_origin: TriggerOrigin = 'viewer_callback') -> BroadcastArc | None:
        """Record a callback only when that exact arc is open in the given show."""
        show_id = _valid_identifier(show_id, _SHOW_ID, 'show_id')
        arc_id = _valid_identifier(arc_id, re.compile(r'^arc-[0-9a-f]{8}$'), 'arc_id')
        now_minute = _valid_minute(now_minute)
        _valid_enum(trigger_origin, TRIGGER_ORIGINS, 'trigger_origin')
        with self._lock:
            self._evict_expired(show_id, now_minute)
            arc = self._shows.get(show_id, {}).get(arc_id)
            if arc is None or arc.status != 'open':
                return None
            if now_minute < arc.updated_minute:
                raise ValueError('callback minute cannot move backwards')
            updated = replace(arc, updated_minute=now_minute, trigger_origin=trigger_origin, callback_count=arc.callback_count + 1, last_callback_minute=now_minute)
            self._shows[show_id][arc_id] = updated
            return updated

    def resolve(self, show_id: str, arc_id: str, *, now_minute: int) -> BroadcastArc | None:
        show_id = _valid_identifier(show_id, _SHOW_ID, 'show_id')
        arc_id = _valid_identifier(arc_id, re.compile(r'^arc-[0-9a-f]{8}$'), 'arc_id')
        now_minute = _valid_minute(now_minute)
        with self._lock:
            self._evict_expired(show_id, now_minute)
            arc = self._shows.get(show_id, {}).get(arc_id)
            if arc is None or arc.status != 'open':
                return None
            if now_minute < arc.updated_minute:
                raise ValueError('resolution minute cannot move backwards')
            updated = replace(arc, updated_minute=now_minute, status='resolved')
            del self._shows[show_id][arc_id]
            if not self._shows[show_id]:
                del self._shows[show_id]
            return updated

    def close_show(self, show_id: str) -> int:
        """Discard a completed show's arcs so no state can reach a later show."""
        show_id = _valid_identifier(show_id, _SHOW_ID, 'show_id')
        with self._lock:
            arcs = self._shows.pop(show_id, {})
            return len(arcs)
