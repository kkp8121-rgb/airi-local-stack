import os
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_broadcast_runtime import (
    BRIEFING_EVIDENCE_MARKER,
    BROADCAST_BRIEFING_HEADER,
    BroadcastControlError,
    LiveBroadcastRuntime,
    render_broadcast_context,
)


MASTER = 'm' * 32
OBSERVER = 'o' * 32


class LiveBroadcastRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.runtime = LiveBroadcastRuntime(True, MASTER, OBSERVER)
        self.runtime.master_control({'action': 'start', 'show_id': 'show-a'})
        self.arc = self.runtime.master_control({
            'action': 'seed_arc', 'show_id': 'show-a', 'topic_key': 'topic',
            'event_type': 'running_joke', 'setup_summary': 'safe production setup',
        })['arc_id']
        self.trace_counter = 0

    def issue(self, action_id='action-a', turn_type='donation', **changes):
        request = {
            'action': 'issue_turn', 'show_id': 'show-a', 'action_id': action_id,
            'turn_type': turn_type, 'required_delivery': 'renderer',
        }
        if turn_type in {'callback_hit', 'callback_miss'}:
            request['arc_id'] = self.arc
        request.update(changes)
        return self.runtime.master_control(request)

    def inject(self, capability):
        self.trace_counter += 1
        capability['_trace_id'] = f'test-trace-{self.trace_counter}'
        notes = self.runtime.claim_turn(capability['turn_token'], screening_ready=True, trace_id=capability['_trace_id'])
        self.assertIsNotNone(notes)
        self.assertIn('airi_affect_expression', notes[1])
        self.assertTrue(self.runtime.confirm_injected(capability['turn_token']))

    def receipt(self, capability, status='delivered', delivery='renderer'):
        trace = capability['_trace_id']
        digest = hashlib.sha256(trace.encode('utf-8')).hexdigest()
        return self.runtime.observer_receipt({
            'delivery_token': capability['delivery_token'], 'delivery_status': status,
            'required_delivery': delivery, 'trace_id': trace, 'query_sha256': digest,
            'user_sha256': digest, 'answer_sha256': digest,
        }, receipt_validator=lambda *_: {'trace_id': trace, 'durable': True})

    def test_both_authorities_required_and_env_is_scrubbed(self):
        self.assertFalse(LiveBroadcastRuntime(True, MASTER).ready)
        self.assertFalse(LiveBroadcastRuntime(True, MASTER, MASTER).ready)
        old_master = os.environ.pop('AIRI_LIVE_BROADCAST_MASTER_TOKEN', None)
        old_observer = os.environ.pop('AIRI_LIVE_BROADCAST_OBSERVER_TOKEN', None)
        old_enabled = os.environ.pop('AIRI_LIVE_BROADCAST_ENABLED', None)
        try:
            os.environ['AIRI_LIVE_BROADCAST_ENABLED'] = 'on'
            os.environ['AIRI_LIVE_BROADCAST_MASTER_TOKEN'] = MASTER
            os.environ['AIRI_LIVE_BROADCAST_OBSERVER_TOKEN'] = OBSERVER
            runtime = LiveBroadcastRuntime.from_env()
            self.assertTrue(runtime.ready)
            self.assertNotIn('AIRI_LIVE_BROADCAST_MASTER_TOKEN', os.environ)
            self.assertNotIn('AIRI_LIVE_BROADCAST_OBSERVER_TOKEN', os.environ)
        finally:
            os.environ.pop('AIRI_LIVE_BROADCAST_ENABLED', None)
            if old_master is not None:
                os.environ['AIRI_LIVE_BROADCAST_MASTER_TOKEN'] = old_master
            if old_observer is not None:
                os.environ['AIRI_LIVE_BROADCAST_OBSERVER_TOKEN'] = old_observer
            if old_enabled is not None:
                os.environ['AIRI_LIVE_BROADCAST_ENABLED'] = old_enabled

    def test_default_off_and_screening_off_are_inert(self):
        runtime = LiveBroadcastRuntime(False, MASTER, OBSERVER)
        self.assertFalse(runtime.ready)
        self.assertIsNone(runtime.claim_turn('a' * 32, screening_ready=True, trace_id='disabled-trace'))
        capability = self.issue()
        self.assertIsNone(self.runtime.claim_turn(capability['turn_token'], screening_ready=False, trace_id='screening-off-trace'))
        self.assertEqual(self.runtime.health()['claimed'], 0)
        with self.assertRaises(BroadcastControlError):
            self.runtime.master_control({
                'action': 'advance_clock', 'show_id': 'show-a', 'delta_minutes': 1,
            })

    def test_explicit_evaluation_clock_attests_long_callback_gap(self):
        runtime = LiveBroadcastRuntime(
            True, MASTER, OBSERVER, evaluation_clock=True,
        )
        runtime.master_control({'action': 'start', 'show_id': 'clock-show'})
        arc = runtime.master_control({
            'action': 'seed_arc', 'show_id': 'clock-show',
            'topic_key': 'late.callback', 'event_type': 'promise_or_plan',
            'setup_summary': '후반부에 첫 선택의 이유를 다시 확인한다',
        })['arc_id']
        first = runtime.master_control({
            'action': 'advance_clock', 'show_id': 'clock-show',
            'delta_minutes': 60,
        })
        second = runtime.master_control({
            'action': 'advance_clock', 'show_id': 'clock-show',
            'delta_minutes': 31,
        })
        self.assertEqual((first['advanced_minutes'], second['advanced_minutes']), (60, 91))
        capability = runtime.master_control({
            'action': 'issue_turn', 'show_id': 'clock-show',
            'action_id': 'late-callback', 'turn_type': 'callback_hit',
            'required_delivery': 'renderer', 'arc_id': arc,
        })
        self.assertIsNotNone(runtime.claim_turn(capability['turn_token'], screening_ready=True, trace_id='clock-trace'))
        self.assertTrue(runtime.confirm_injected(capability['turn_token']))
        digest = hashlib.sha256(b'clock-trace').hexdigest()
        runtime.observer_receipt({
            'delivery_token': capability['delivery_token'], 'delivery_status': 'delivered', 'required_delivery': 'renderer',
            'trace_id': 'clock-trace', 'query_sha256': digest, 'user_sha256': digest, 'answer_sha256': digest,
        }, receipt_validator=lambda *_: {'trace_id': 'clock-trace', 'durable': True})
        self.assertEqual(runtime.health()['advanced_minutes'], 91)

    def test_evaluation_clock_exposes_authenticated_baseline_only_when_enabled(self):
        runtime = LiveBroadcastRuntime(
            True, MASTER, OBSERVER, evaluation_clock=True,
        )
        runtime.master_control({'action': 'start', 'show_id': 'baseline-show'})
        baseline = runtime.master_control({
            'action': 'clock_baseline', 'show_id': 'baseline-show',
        })
        self.assertIs(type(baseline['clock_minute']), int)
        with self.assertRaises(BroadcastControlError):
            self.runtime.master_control({
                'action': 'clock_baseline', 'show_id': 'show-a',
            })

    def test_claim_inject_and_terminal_receipt(self):
        capability = self.issue()
        self.inject(capability)
        receipt = self.receipt(capability)
        self.assertEqual(receipt['action_id'], 'action-a')
        self.assertRegex(receipt['delivery_token_sha256'], r'^[0-9a-f]{64}$')
        health = self.runtime.health()
        self.assertEqual((health['active_tokens'], health['claimed'], health['injected']), (0, 1, 1))
        self.assertEqual(health['terminal'], 1)

    def test_normal_broadcast_inputs_all_drive_typed_affect_events(self):
        before = self.runtime.health()['mapped_outcomes']
        for index, turn_type in enumerate(
            ('donation', 'subscription', 'selected_chat', 'batched_chat', 'screen_event', 'greeting'),
            1,
        ):
            capability = self.issue(
                action_id=f'typed-event-{index}', turn_type=turn_type,
            )
            self.inject(capability)
            self.receipt(capability)
        self.assertEqual(self.runtime.health()['mapped_outcomes'] - before, 6)

    def test_out_of_order_receipt_does_not_poison_delivery_token(self):
        capability = self.issue()
        trace = 'out-of-order-trace'
        digest = hashlib.sha256(trace.encode('utf-8')).hexdigest()
        with self.assertRaises(BroadcastControlError) as raised:
            self.runtime.observer_receipt({
                'delivery_token': capability['delivery_token'], 'delivery_status': 'delivered', 'required_delivery': 'renderer',
                'trace_id': trace, 'query_sha256': digest, 'user_sha256': digest, 'answer_sha256': digest,
            })
        self.assertEqual(raised.exception.receipt_category, 'capability_lifecycle')
        self.inject(capability)
        self.receipt(capability, 'failed')
        self.assertEqual(self.runtime.health()['active_tokens'], 0)

    def test_missing_or_mismatched_trace_proof_does_not_consume_capability(self):
        capability = self.issue()
        self.inject(capability)
        trace = capability['_trace_id']
        digest = hashlib.sha256(trace.encode('utf-8')).hexdigest()
        payload = {
            'delivery_token': capability['delivery_token'], 'delivery_status': 'delivered', 'required_delivery': 'renderer',
            'trace_id': trace, 'query_sha256': digest, 'user_sha256': digest, 'answer_sha256': digest,
        }
        with self.assertRaises(BroadcastControlError):
            self.runtime.observer_receipt(payload, receipt_validator=lambda *_: None)
        self.assertEqual(self.runtime.health()['active_tokens'], 1)
        payload['trace_id'] = 'foreign-trace'
        with self.assertRaises(BroadcastControlError):
            self.runtime.observer_receipt(payload, receipt_validator=lambda *_: {'durable': True})
        self.assertEqual(self.runtime.health()['active_tokens'], 1)
        self.receipt(capability)

    def test_knowledge_bound_receipt_requires_validator_approval(self):
        capability = self.issue()
        self.trace_counter += 1
        capability['_trace_id'] = 'knowledge-trace'
        self.assertIsNotNone(self.runtime.claim_turn(capability['turn_token'], screening_ready=True, trace_id='knowledge-trace', knowledge_required=True))
        self.assertTrue(self.runtime.confirm_injected(capability['turn_token']))
        trace, digest = 'knowledge-trace', hashlib.sha256(b'knowledge-trace').hexdigest()
        payload = {'delivery_token': capability['delivery_token'], 'delivery_status': 'delivered', 'required_delivery': 'renderer', 'trace_id': trace, 'query_sha256': digest, 'user_sha256': digest, 'answer_sha256': digest}
        with self.assertRaises(BroadcastControlError):
            self.runtime.observer_receipt(payload, receipt_validator=lambda *_: None)
        self.receipt(capability)

    def test_receipt_cannot_rebind_required_delivery(self):
        capability = self.issue()
        self.inject(capability)
        trace = capability['_trace_id']
        digest = hashlib.sha256(trace.encode('utf-8')).hexdigest()
        with self.assertRaises(BroadcastControlError) as raised:
            self.runtime.observer_receipt({
                'delivery_token': capability['delivery_token'], 'delivery_status': 'delivered', 'required_delivery': 'tts',
                'trace_id': trace, 'query_sha256': digest, 'user_sha256': digest, 'answer_sha256': digest,
            })
        self.assertEqual(raised.exception.receipt_category, 'capability_lifecycle')
        self.receipt(capability, 'cancelled')

    def test_sequential_lifecycle_rejections_remain_coarse(self):
        trace, digest = 'lifecycle-trace', hashlib.sha256(b'lifecycle-trace').hexdigest()
        for index in range(300):
            capability = self.issue(action_id=f'lifecycle-{index}')
            with self.assertRaises(BroadcastControlError) as raised:
                self.runtime.observer_receipt({
                    'delivery_token': capability['delivery_token'], 'delivery_status': 'delivered', 'required_delivery': 'renderer',
                    'trace_id': trace, 'query_sha256': digest, 'user_sha256': digest, 'answer_sha256': digest,
                })
            self.assertEqual(raised.exception.receipt_category, 'capability_lifecycle')
            self.runtime.cancel_turn(capability['turn_token'])
        self.assertEqual(self.runtime.health()['active_tokens'], 0)

    def test_callback_uses_only_selected_arc_and_hit_resolves(self):
        other = self.runtime.master_control({
            'action': 'seed_arc', 'show_id': 'show-a', 'topic_key': 'other',
            'event_type': 'running_joke', 'setup_summary': 'other safe setup',
        })['arc_id']
        capability = self.issue(turn_type='callback_hit')
        capability['_trace_id'] = 'callback-trace'
        notes = self.runtime.claim_turn(capability['turn_token'], screening_ready=True, trace_id=capability['_trace_id'])
        self.assertIn(self.arc, notes[0])
        self.assertIn('safe production setup', notes[0])
        self.assertNotIn(other, notes[0])
        self.assertNotIn('기억표식', notes[0])
        self.assertTrue(self.runtime.confirm_injected(capability['turn_token']))
        self.receipt(capability)
        self.assertEqual(self.runtime.health()['callback_hits'], 1)

    def test_opaque_audit_marker_is_rejected_before_any_model_arc_note(self):
        with self.assertRaises(BroadcastControlError):
            self.runtime.master_control({
                'action': 'seed_arc',
                'show_id': 'show-a',
                'topic_key': 'opaque-marker',
                'event_type': 'running_joke',
                'setup_summary': '자연스러운 요약. 기억표식가람010001',
            })

    def test_callback_miss_keeps_lifecycle_binding_without_model_arc_exposure(self):
        capability = self.issue(turn_type='callback_miss')
        capability['_trace_id'] = 'callback-miss-trace'
        notes = self.runtime.claim_turn(capability['turn_token'], screening_ready=True, trace_id=capability['_trace_id'])
        self.assertIsNotNone(notes)
        self.assertEqual(notes[0], '')
        self.assertTrue(self.runtime.confirm_injected(capability['turn_token']))
        self.receipt(capability)
        self.assertEqual(self.runtime.health()['callback_misses'], 1)

    def test_broadcast_context_is_closed_versioned_and_server_rendered(self):
        context = {
            'schema_version': 1,
            'topic_title': '유리 성 탐색',
            'segment_label': '북쪽 수문 확인',
            'situation': '채팅의 단서를 비교하는 중',
            'briefing': BROADCAST_BRIEFING_HEADER + '\n- 이전 선택: 등대 확인',
            'donation_continuation': True,
        }
        capability = self.issue(broadcast_context=context)
        notes = self.runtime.claim_turn(
            capability['turn_token'], screening_ready=True, trace_id='context-trace',
        )
        self.assertIsNotNone(notes)
        self.assertIn('[오늘 방송]', notes.context_note)
        self.assertIn(context['briefing'], notes.context_note)
        self.assertIn('[후원 본문 이어말하기]', notes.context_note)
        self.assertEqual(notes.context_note.count('[오늘 방송]'), 1)
        self.assertNotIn(BRIEFING_EVIDENCE_MARKER, notes.context_note)
        self.runtime.cancel_turn(capability['turn_token'])

        marked_capability = self.issue(
            action_id='marked-context', broadcast_context=context,
        )
        marked_notes = self.runtime.claim_turn(
            marked_capability['turn_token'], screening_ready=True,
            trace_id='marked-context-trace', deterministic_layer=True,
        )
        self.assertIsNotNone(marked_notes)
        self.assertIn(
            BRIEFING_EVIDENCE_MARKER + '\n' + BROADCAST_BRIEFING_HEADER,
            marked_notes.context_note,
        )
        self.assertEqual(render_broadcast_context(context), notes.context_note)
        self.runtime.cancel_turn(marked_capability['turn_token'])

        for change in (
            {'schema_version': 2},
            {'schema_version': True},
            {'briefing': '햤더 없는 브리핑'},
            {'donation_continuation': 1},
            {'unknown': 'field'},
        ):
            invalid = dict(context)
            invalid.update(change)
            with self.assertRaises(BroadcastControlError):
                self.issue(
                    action_id=f'invalid-context-{len(self.runtime._tombstones)}-{len(change)}',
                    broadcast_context=invalid,
                )

    def test_failed_partial_cancelled_and_unknown_are_terminal_inert(self):
        for index, status in enumerate(('failed', 'partial', 'cancelled', 'unknown')):
            capability = self.issue(f'action-{index}')
            self.inject(capability)
            self.receipt(capability, status)
        health = self.runtime.health()
        self.assertEqual((health['active_tokens'], health['callback_hits'], health['callback_misses']), (0, 0, 0))

    def test_action_aba_and_show_isolation(self):
        capability = self.issue()
        self.runtime.cancel_turn(capability['turn_token'])
        with self.assertRaises(BroadcastControlError):
            self.issue()
        self.runtime.master_control({'action': 'start', 'show_id': 'show-b'})
        self.runtime.master_control({'action': 'close', 'show_id': 'show-a'})
        self.assertEqual(self.runtime.health()['active_shows'], 1)

    def test_exact_turn_schema_rejects_viewer_data_and_bad_arc_binding(self):
        with self.assertRaises(BroadcastControlError):
            self.issue(text='viewer data')
        with self.assertRaises(BroadcastControlError):
            self.issue(arc_id=self.arc)
        with self.assertRaises(BroadcastControlError):
            self.issue(turn_type='callback_hit', arc_id='arc-ffffffff')

    def test_ten_thousand_sequential_terminal_turns_do_not_exhaust(self):
        for index in range(10_000):
            capability = self.issue(f'a{index}', 'greeting')
            self.inject(capability)
            self.receipt(capability, 'cancelled')
        self.assertEqual(self.runtime.health()['active_tokens'], 0)

    def test_tombstone_bound_is_global_across_shows(self):
        runtime = LiveBroadcastRuntime(True, MASTER, OBSERVER)
        for show_index in range(16):
            runtime.master_control({'action': 'start', 'show_id': f'show-{show_index}'})
        for index in range(10_500):
            runtime._tombstone(f'show-{index % 16}', f'action-{index}')
        self.assertEqual(runtime.health()['tombstones'], 10_240)


if __name__ == '__main__':
    unittest.main()
