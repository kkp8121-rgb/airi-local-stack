"""Fail-closed, opt-in live-broadcast capability boundary."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import os
import re
import secrets
import threading
import time
from typing import Any, NamedTuple

from affect_expression import render_affect_expression_contract
from affect_state import AffectStateRuntime, AffectValidationError, EVENT_SCHEMA_VERSION, reduce_affect, render_continuity_snapshot
from broadcast_affect_event_mapper import BROADCAST_AFFECT_OUTCOME_CANDIDATE_SCHEMA_VERSION, BroadcastAffectMappingError, map_broadcast_outcome_candidate
from broadcast_arc_ledger import BroadcastArcLedger, render_open_arcs
from deterministic_utterance_layer import BRIEFING_EVIDENCE_MARKER

_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')
_TRACE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$')
_TOKEN = re.compile(r'^[A-Za-z0-9_-]{32,128}$')
_OPAQUE_AUDIT_MARKER = re.compile(r'기억표식[가-힣]+\d{6}')
_MAX_SHOWS, _MAX_CAPABILITIES, _MAX_TOMBSTONES, _CAPABILITY_TTL_SECONDS = 16, 256, 10_240, 300
_MAX_CLOCK_STEP_MINUTES = 60
_TERMINAL_STATUSES = frozenset(('delivered', 'failed', 'partial', 'cancelled', 'unknown'))
_ARC_TURNS = frozenset(('callback_hit', 'callback_miss'))
_TURN_TYPES = frozenset(('donation', 'subscription', 'selected_chat', 'batched_chat', 'screen_event', 'greeting', 'topic_transition', 'game_success', 'game_failure', 'chat_question', 'chat_teasing', 'chat_correction', 'chat_concern', 'moderation', 'safety', 'callback_hit', 'callback_miss', 'silence', 'response_repair'))
_DELIVERIES = frozenset(('renderer', 'tts'))
_BROADCAST_CONTEXT_KEYS = frozenset((
    'schema_version', 'topic_title', 'segment_label', 'situation', 'briefing',
    'donation_continuation',
))
_BROADCAST_CONTEXT_LIMITS = {
    'topic_title': 120, 'segment_label': 120, 'situation': 300, 'briefing': 2048,
}
BROADCAST_BRIEFING_HEADER = '[턴 브리핑 — 방송 스태프가 주는 메모야. 자연스럽게 참고만 해.]'
DONATION_CONTINUATION_CONTRACT = (
    "[후원 본문 이어말하기]\n"
    "후원자 호명과 감사 의례는 결정론 렌더러가 이미 먼저 말해. "
    "이름이나 감사를 반복하지 말고, 현재 후원 메시지의 내용에 대한 본답변만 이어서 말해. "
    "입력과 방송 맥락에 있는 사실을 받아 자기 판단과 이유를 자연스럽게 밝힌 뒤 방송 흐름으로 돌아와."
)
_PRE_EVENTS = {
    'donation': ('director_delivery', 'donation_acknowledged'), 'topic_transition': ('director_delivery', 'topic_open'),
    'subscription': ('director_delivery', 'donation_acknowledged'),
    'selected_chat': ('screened_chat', 'chat_question'),
    'batched_chat': ('screened_chat', 'chat_question'),
    'screen_event': ('director_delivery', 'topic_open'),
    'greeting': ('director_delivery', 'topic_open'),
    'chat_question': ('screened_chat', 'chat_question'), 'chat_teasing': ('screened_chat', 'chat_teasing'),
    'chat_correction': ('screened_chat', 'chat_correction'), 'chat_concern': ('screened_chat', 'chat_concern'),
    'moderation': ('proxy_terminal_output', 'moderation_block'), 'safety': ('proxy_terminal_output', 'safety_override'),
    'silence': ('silence_observer', 'silence'),
}
_POST_EVENTS = {
    'callback_hit': ('director_delivery', 'callback_hit'), 'callback_miss': ('director_delivery', 'callback_miss'),
    'game_success': ('game_telemetry', 'game_success'), 'game_failure': ('game_telemetry', 'game_failure'),
    'response_repair': ('proxy_terminal_output', 'response_repair'),
}


class BroadcastControlError(ValueError):
    """A fixed error for every untrusted control or observer failure."""

    def __init__(self, message: str = 'invalid broadcast request', *, receipt_category: str | None = None) -> None:
        super().__init__(message)
        self.receipt_category = receipt_category


def _invalid(*, receipt_category: str | None = None) -> BroadcastControlError:
    return BroadcastControlError('invalid broadcast request', receipt_category=receipt_category)


@dataclass(slots=True)
class _Capability:
    show_id: str
    action_id: str
    turn_type: str
    required_delivery: str
    arc_id: str | None
    delivery_token: str
    state: str
    issued_at: float
    trace_id: str | None = None
    knowledge_required: bool = False
    turn_index: int | None = None
    preview_state: dict[str, Any] | None = None
    context_note: str = ''
    deterministic_context_note: str = ''


class BroadcastNotes(NamedTuple):
    """Authenticated, server-rendered notes for one claimed broadcast turn."""
    arc_note: str
    affect_note: str
    context_note: str


def render_broadcast_context(value: object, *, briefing_evidence_marker: bool = False) -> str:
    """Validate the closed v1 wire shape and produce bounded model context."""
    if type(briefing_evidence_marker) is not bool:
        raise _invalid()
    if type(value) is not dict or set(value) != _BROADCAST_CONTEXT_KEYS:
        raise _invalid()
    if type(value.get('schema_version')) is not int or value['schema_version'] != 1:
        raise _invalid()
    for key, limit in _BROADCAST_CONTEXT_LIMITS.items():
        item = value.get(key)
        if not isinstance(item, str) or '\0' in item or len(item) > limit:
            raise _invalid()
        if key != 'briefing' and not item:
            raise _invalid()
    if type(value['donation_continuation']) is not bool:
        raise _invalid()
    briefing = value['briefing']
    if briefing and briefing.splitlines()[0] != BROADCAST_BRIEFING_HEADER:
        raise _invalid()
    note = (
        '[오늘 방송]\n'
        f"- 주제: {value['topic_title']}\n"
        f"- 지금 구간: {value['segment_label']}\n"
        f"- 상황: {value['situation']}\n"
        '- 주제에서 벗어난 채팅에는 짧게 반응하고 현재 주제로 돌아와.'
    )
    if briefing:
        note += '\n\n'
        if briefing_evidence_marker:
            note += BRIEFING_EVIDENCE_MARKER + '\n'
        note += briefing
    if value['donation_continuation']:
        note += '\n\n' + DONATION_CONTINUATION_CONTRACT
    if len(note) > 4096:
        raise _invalid()
    return note


# Kept private as a compatibility alias for any out-of-tree control adapters.
_render_broadcast_context = render_broadcast_context


class LiveBroadcastRuntime:
    """Server-owned shows and bounded one-shot turn/delivery capabilities."""
    def __init__(
        self,
        enabled: bool,
        master_token: str | None = None,
        observer_token: str | None = None,
        *,
        evaluation_clock: bool = False,
    ) -> None:
        self.enabled = (
            enabled
            and all(
                isinstance(token, str) and _TOKEN.fullmatch(token)
                for token in (master_token, observer_token)
            )
            and master_token != observer_token
        )
        self._master_token = master_token if self.enabled else None
        self._observer_token = observer_token if self.enabled else None
        self._ledger, self._affect = BroadcastArcLedger(), AffectStateRuntime(max_sessions=_MAX_SHOWS)
        self._shows: dict[str, int] = {}
        self.evaluation_clock = self.enabled and evaluation_clock
        self._clock_offsets: dict[str, int] = {}
        self._turn_tokens: dict[str, _Capability] = {}
        self._delivery_tokens: dict[str, _Capability] = {}
        # This replay fence is process-wide. A per-show limit would silently
        # multiply the advertised bound by _MAX_SHOWS.
        self._tombstones: OrderedDict[tuple[str, str], None] = OrderedDict()
        self._lock = threading.RLock()
        self._counters = {key: 0 for key in ('seeds', 'reads', 'injections', 'callback_hits', 'callback_misses', 'rejected_controls', 'rejected_receipts', 'errors', 'affect_events', 'mapped_outcomes', 'rejected_outcomes', 'snapshots_injected', 'expressions_injected', 'missing_snapshots', 'issued', 'claimed', 'injected', 'terminal', 'expired')}

    @classmethod
    def from_env(cls) -> 'LiveBroadcastRuntime':
        master = os.environ.pop('AIRI_LIVE_BROADCAST_MASTER_TOKEN', None)
        observer = os.environ.pop('AIRI_LIVE_BROADCAST_OBSERVER_TOKEN', None)
        evaluation_clock = os.environ.pop('AIRI_LIVE_BROADCAST_EVAL_CLOCK', 'off') == 'on'
        return cls(
            os.getenv('AIRI_LIVE_BROADCAST_ENABLED') == 'on',
            master,
            observer,
            evaluation_clock=evaluation_clock,
        )

    @property
    def ready(self) -> bool:
        return self.enabled and self._master_token is not None and self._observer_token is not None

    def ready_for_chat(self, screening_ready: bool) -> bool:
        return self.ready and screening_ready

    def authorize_master(self, token: object) -> bool:
        return self.ready and isinstance(token, str) and secrets.compare_digest(token, self._master_token or '')

    def authorize_observer(self, token: object) -> bool:
        return self.ready and isinstance(token, str) and secrets.compare_digest(token, self._observer_token or '')

    def reject_control(self, receipt: bool = False) -> None:
        with self._lock:
            self._counters['rejected_receipts' if receipt else 'rejected_controls'] += 1

    def _show(self, value: object) -> str:
        if not isinstance(value, str) or not _ID.fullmatch(value) or value not in self._shows:
            raise _invalid()
        return value

    def _next_turn(self, show_id: str) -> int:
        self._shows[show_id] += 1
        return self._shows[show_id]

    def _now_minute(self, show_id: str) -> int:
        return int(time.monotonic() // 60) + self._clock_offsets.get(show_id, 0)

    def _tombstone(self, show_id: str, action_id: str) -> None:
        key = (show_id, action_id)
        self._tombstones[key] = None
        self._tombstones.move_to_end(key)
        while len(self._tombstones) > _MAX_TOMBSTONES:
            self._tombstones.popitem(last=False)

    def _remove_capability(self, cap: _Capability, *, expired: bool = False) -> None:
        for token, candidate in tuple(self._turn_tokens.items()):
            if candidate is cap:
                del self._turn_tokens[token]
        self._delivery_tokens.pop(cap.delivery_token, None)
        self._tombstone(cap.show_id, cap.action_id)
        self._counters['terminal'] += 1
        if expired:
            self._counters['expired'] += 1

    def _sweep(self) -> None:
        now = time.monotonic()
        for cap in tuple(self._turn_tokens.values()):
            if now - cap.issued_at >= _CAPABILITY_TTL_SECONDS:
                self._remove_capability(cap, expired=True)

    def _mapped_event(self, pair: tuple[str, str], turn_index: int) -> dict[str, Any]:
        try:
            return map_broadcast_outcome_candidate({'schema_version': BROADCAST_AFFECT_OUTCOME_CANDIDATE_SCHEMA_VERSION, 'evidence': pair[0], 'outcome': pair[1], 'delivery_status': 'delivered', 'turn_index': turn_index})
        except BroadcastAffectMappingError as exc:
            self._counters['errors'] += 1
            raise _invalid() from exc

    def _apply_mapped(self, show_id: str, pair: tuple[str, str], turn_index: int) -> dict[str, Any]:
        try:
            event = self._mapped_event(pair, turn_index)
            result = self._affect.apply_event(show_id, event)
            self._counters['affect_events'] += 1
            self._counters['mapped_outcomes'] += 1
            return result
        except (AffectValidationError, ValueError, TypeError) as exc:
            self._counters['errors'] += 1
            raise _invalid() from exc

    def _apply_start(self, show_id: str) -> None:
        event = {'schema_version': EVENT_SCHEMA_VERSION, 'source': 'broadcast_director', 'kind': 'broadcast_start', 'appraisal': {'goal_congruence': 0, 'agency': 'none', 'control': 1, 'novelty': 1, 'social_tone': 'neutral'}, 'weight': 1, 'turn_index': self._next_turn(show_id)}
        try:
            self._affect.apply_event(show_id, event)
            self._counters['affect_events'] += 1
        except (AffectValidationError, ValueError, TypeError) as exc:
            self._counters['errors'] += 1
            raise _invalid() from exc

    def master_control(self, payload: object) -> dict[str, Any]:
        try:
            if not self.ready or type(payload) is not dict or not isinstance(payload.get('action'), str):
                raise _invalid()
            with self._lock:
                self._sweep()
                action = payload['action']
                if action == 'start' and set(payload) == {'action', 'show_id'}:
                    show_id = payload['show_id']
                    if not isinstance(show_id, str) or not _ID.fullmatch(show_id) or show_id in self._shows or len(self._shows) >= _MAX_SHOWS:
                        raise _invalid()
                    self._shows[show_id] = 0
                    self._clock_offsets[show_id] = 0
                    self._apply_start(show_id)
                    return {}
                if action == 'seed_arc' and set(payload) == {'action', 'show_id', 'topic_key', 'event_type', 'setup_summary'}:
                    show_id = self._show(payload['show_id'])
                    if not isinstance(payload['setup_summary'], str) or _OPAQUE_AUDIT_MARKER.search(payload['setup_summary']) is not None:
                        raise _invalid()
                    arc = self._ledger.add_arc(show_id, now_minute=self._now_minute(show_id), topic_key=payload['topic_key'], event_type=payload['event_type'], setup_summary=payload['setup_summary'], source_type='show_arc')
                    self._apply_mapped(show_id, ('director_delivery', 'topic_open'), self._next_turn(show_id))
                    self._counters['seeds'] += 1
                    return {'arc_id': arc.arc_id}
                if action == 'advance_clock' and set(payload) == {'action', 'show_id', 'delta_minutes'}:
                    show_id = self._show(payload['show_id'])
                    delta = payload['delta_minutes']
                    if (
                        not self.evaluation_clock
                        or isinstance(delta, bool)
                        or not isinstance(delta, int)
                        or not 1 <= delta <= _MAX_CLOCK_STEP_MINUTES
                    ):
                        raise _invalid()
                    self._clock_offsets[show_id] += delta
                    return {
                        'clock_minute': self._now_minute(show_id),
                        'advanced_minutes': self._clock_offsets[show_id],
                    }
                if action == 'clock_baseline' and set(payload) == {'action', 'show_id'}:
                    show_id = self._show(payload['show_id'])
                    if not self.evaluation_clock:
                        raise _invalid()
                    return {'clock_minute': self._now_minute(show_id)}
                if action == 'issue_turn':
                    return self._issue(payload)
                if action == 'close' and set(payload) == {'action', 'show_id'}:
                    self._close(self._show(payload['show_id']))
                    return {}
                raise _invalid()
        except BroadcastControlError:
            self._counters['rejected_controls'] += 1
            raise
        except Exception as exc:
            self._counters['rejected_controls'] += 1
            self._counters['errors'] += 1
            raise _invalid() from exc

    def _issue(self, payload: dict[str, Any]) -> dict[str, str]:
        allowed = {'action', 'show_id', 'action_id', 'turn_type', 'required_delivery'}
        turn_type = payload.get('turn_type')
        if turn_type in _ARC_TURNS:
            allowed.add('arc_id')
        if 'broadcast_context' in payload:
            allowed.add('broadcast_context')
        if set(payload) != allowed:
            raise _invalid()
        show_id, action_id, delivery = self._show(payload.get('show_id')), payload.get('action_id'), payload.get('required_delivery')
        if not isinstance(action_id, str) or not _ID.fullmatch(action_id) or turn_type not in _TURN_TYPES or delivery not in _DELIVERIES:
            raise _invalid()
        if (show_id, action_id) in self._tombstones or any(cap.show_id == show_id and cap.action_id == action_id for cap in self._turn_tokens.values()) or len(self._turn_tokens) >= _MAX_CAPABILITIES:
            raise _invalid()
        arc_id = payload.get('arc_id') if turn_type in _ARC_TURNS else None
        context_note = ''
        deterministic_context_note = ''
        if 'broadcast_context' in payload:
            context_note = render_broadcast_context(payload['broadcast_context'])
            deterministic_context_note = render_broadcast_context(
                payload['broadcast_context'], briefing_evidence_marker=True,
            )
        if turn_type in _ARC_TURNS:
            if not isinstance(arc_id, str) or not any(
                arc.arc_id == arc_id
                for arc in self._ledger.read_open(show_id, now_minute=self._now_minute(show_id))
            ):
                raise _invalid()
        turn_token, delivery_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        cap = _Capability(
            show_id, action_id, turn_type, delivery, arc_id, delivery_token,
            'issued', time.monotonic(), context_note=context_note,
            deterministic_context_note=deterministic_context_note,
        )
        self._turn_tokens[turn_token], self._delivery_tokens[delivery_token] = cap, cap
        self._counters['issued'] += 1
        return {'turn_token': turn_token, 'delivery_token': delivery_token}

    def claim_turn(self, token: object, *, screening_ready: bool, trace_id: str,
                   knowledge_required: bool = False,
                   deterministic_layer: bool = False) -> BroadcastNotes | None:
        if (
            not self.ready_for_chat(screening_ready) or not isinstance(token, str) or not _TOKEN.fullmatch(token)
            or not isinstance(trace_id, str) or not _TRACE_ID.fullmatch(trace_id)
            or type(knowledge_required) is not bool or type(deterministic_layer) is not bool
        ):
            return None
        with self._lock:
            self._sweep()
            cap = self._turn_tokens.get(token)
            if cap is None or cap.state != 'issued' or cap.show_id not in self._shows:
                return None
            # One in-flight turn per show prevents cancelled or out-of-order
            # capabilities from creating a hidden affect turn gap.
            if any(candidate.show_id == cap.show_id and candidate.state in {'claimed', 'injected'} for candidate in self._turn_tokens.values()):
                return None
            arcs = () if cap.arc_id is None else tuple(arc for arc in self._ledger.read_open(cap.show_id, now_minute=self._now_minute(cap.show_id)) if arc.arc_id == cap.arc_id)
            if cap.arc_id is not None and not arcs:
                self._remove_capability(cap)
                return None
            cap.state, cap.turn_index, cap.trace_id, cap.knowledge_required = 'claimed', self._next_turn(cap.show_id), trace_id, knowledge_required
            snapshot = self._affect.snapshot_if_present(cap.show_id)
            if snapshot is None:
                self._counters['missing_snapshots'] += 1
                self._remove_capability(cap)
                return None
            if cap.turn_type in _PRE_EVENTS:
                try:
                    cap.preview_state = reduce_affect(snapshot, self._mapped_event(_PRE_EVENTS[cap.turn_type], cap.turn_index))
                except (AffectValidationError, ValueError, TypeError):
                    self._remove_capability(cap)
                    return None
            else:
                cap.preview_state = snapshot
            self._counters['claimed'] += 1
            self._counters['reads'] += 1
            # A matched decoy must retain its authenticated arc binding for the
            # post-delivery lifecycle, while exposing no arc data to the model.
            arc_note = '' if cap.turn_type == 'callback_miss' else render_open_arcs(arcs)
            return BroadcastNotes(
                arc_note,
                render_continuity_snapshot(cap.preview_state) + '\n' + render_affect_expression_contract(cap.preview_state),
                cap.deterministic_context_note if deterministic_layer else cap.context_note,
            )

    def confirm_injected(self, token: object) -> bool:
        if not isinstance(token, str):
            return False
        with self._lock:
            cap = self._turn_tokens.get(token)
            if cap is None or cap.state != 'claimed':
                return False
            if cap.turn_type in _PRE_EVENTS and cap.turn_index is not None:
                self._apply_mapped(cap.show_id, _PRE_EVENTS[cap.turn_type], cap.turn_index)
            cap.state = 'injected'
            for key in ('injected', 'injections', 'snapshots_injected', 'expressions_injected'):
                self._counters[key] += 1
            return True

    def cancel_turn(self, token: object) -> None:
        if isinstance(token, str):
            with self._lock:
                cap = self._turn_tokens.get(token)
                if cap is not None:
                    if cap.state == 'claimed' and cap.turn_index == self._shows.get(cap.show_id):
                        self._shows[cap.show_id] -= 1
                    self._remove_capability(cap)

    def observer_receipt(self, payload: object, *, receipt_validator: Any = None) -> dict[str, object]:
        try:
            required = {'delivery_token', 'delivery_status', 'required_delivery', 'trace_id', 'query_sha256', 'user_sha256', 'answer_sha256'}
            if not self.ready or type(payload) is not dict or set(payload) != required:
                raise _invalid()
            delivery_token, status, delivery, trace_id = payload['delivery_token'], payload['delivery_status'], payload['required_delivery'], payload['trace_id']
            hashes = tuple(payload[key] for key in ('query_sha256', 'user_sha256', 'answer_sha256'))
            if not isinstance(delivery_token, str) or not _TOKEN.fullmatch(delivery_token) or status not in _TERMINAL_STATUSES or delivery not in _DELIVERIES or not isinstance(trace_id, str) or not _TRACE_ID.fullmatch(trace_id) or any(not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value) for value in hashes):
                raise _invalid()
            with self._lock:
                self._sweep()
                cap = self._delivery_tokens.get(delivery_token)
                if cap is None or cap.state != 'injected' or cap.turn_index is None or delivery != cap.required_delivery or trace_id != cap.trace_id:
                    # The wire shape has already been fully authenticated and
                    # validated.  Keep lifecycle diagnostics deliberately
                    # coarse so a local observer cannot probe capability state.
                    raise _invalid(receipt_category='capability_lifecycle')
                if not callable(receipt_validator):
                    raise _invalid()
                evidence = receipt_validator(trace_id, hashes, cap.knowledge_required)
                if not isinstance(evidence, dict):
                    raise _invalid()
                if status == 'delivered':
                    try:
                        self._delivered(cap, now_minute=self._now_minute(cap.show_id))
                    except BroadcastControlError as exc:
                        if exc.receipt_category is None:
                            raise _invalid(receipt_category='delivery_transition') from exc
                        raise
                receipt = {
                    'action_id': cap.action_id,
                    'delivery_token_sha256': hashlib.sha256(
                        delivery_token.encode('utf-8')
                    ).hexdigest(),
                }
                receipt['trace_receipt'] = evidence
                self._remove_capability(cap)
                return receipt
        except BroadcastControlError:
            self._counters['rejected_receipts'] += 1
            raise
        except Exception as exc:
            self._counters['rejected_receipts'] += 1
            self._counters['errors'] += 1
            raise _invalid() from exc

    def _delivered(self, cap: _Capability, *, now_minute: int) -> None:
        if cap.turn_type in _ARC_TURNS and not any(
            arc.arc_id == cap.arc_id
            for arc in self._ledger.read_open(cap.show_id, now_minute=now_minute)
        ):
            raise _invalid()
        pair = _POST_EVENTS.get(cap.turn_type)
        if pair is not None:
            self._apply_mapped(cap.show_id, pair, cap.turn_index or 0)
        if cap.turn_type == 'callback_hit':
            arc = self._ledger.record_callback(cap.show_id, cap.arc_id or '', now_minute=now_minute)
            if arc is None:
                raise _invalid()
            self._ledger.resolve(cap.show_id, arc.arc_id, now_minute=now_minute)
            self._counters['callback_hits'] += 1
        elif cap.turn_type == 'callback_miss':
            self._counters['callback_misses'] += 1

    def _close(self, show_id: str) -> None:
        self._ledger.close_show(show_id)
        self._affect.reset_session(show_id)
        del self._shows[show_id]
        self._clock_offsets.pop(show_id, None)
        for cap in tuple(self._turn_tokens.values()):
            if cap.show_id == show_id:
                self._remove_capability(cap)
        for key in tuple(self._tombstones):
            if key[0] == show_id:
                del self._tombstones[key]

    def health(self) -> dict[str, int | bool]:
        with self._lock:
            try:
                self._sweep()
                state_counts = {state: 0 for state in ('issued', 'claimed', 'injected')}
                for cap in self._turn_tokens.values():
                    state_counts[cap.state] += 1
                return {
                    'enabled': self.enabled, 'ready': self.ready,
                    'evaluation_clock': self.evaluation_clock,
                    'advanced_minutes': sum(self._clock_offsets.values()),
                    'active_shows': len(self._shows), 'active_tokens': len(self._turn_tokens),
                    'issued_active': state_counts['issued'], 'claimed_active': state_counts['claimed'],
                    'injected_active': state_counts['injected'],
                    'tombstones': len(self._tombstones), **self._counters,
                }
            except Exception:
                self._counters['errors'] += 1
                return {'enabled': self.enabled, 'ready': False, 'evaluation_clock': False, 'advanced_minutes': 0, 'active_shows': 0, 'active_tokens': 0, 'issued_active': 0, 'claimed_active': 0, 'injected_active': 0, 'tombstones': 0, **self._counters}
