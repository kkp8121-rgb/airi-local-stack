from __future__ import annotations

import ast
import hashlib
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_affect_broadcast_eval as legacy
import run_guarded_delta_eval as guarded


SECRET = b'x' * 32
COMPARISON_ID = '0123456789abcdef0123456789abcdef'
FIXED_IDS = (
    'first-23', 'teasing-02', 'teasing-04', 'teasing-05', 'teasing-12',
    'teasing-17', 'game-17', 'game-20', 'correction-02', 'correction-03',
    'correction-04', 'correction-07', 'correction-08', 'correction-12',
    'correction-15', 'correction-17', 'callback-04', 'callback-11',
    'callback-20', 'fatigue-09', 'fatigue-23', 'fatigue-24',
)


class GuardedDeltaEvalTests(unittest.TestCase):
    @contextmanager
    def _custody(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = guarded.LOCAL_RESULTS_DIR, guarded.LOCAL_OPERATOR_KEYS_DIR
            guarded.LOCAL_RESULTS_DIR = root / 'local-results'
            guarded.LOCAL_OPERATOR_KEYS_DIR = root / 'local-operator-keys'
            try:
                self._bundle(root)
                yield root
            finally:
                guarded.LOCAL_RESULTS_DIR, guarded.LOCAL_OPERATOR_KEYS_DIR = old

    def _bundle(self, root: Path) -> None:
        fixture = legacy.load_fixture()
        acts = {item['turn_id']: item['expected_reply_act'] for item in legacy.load_reply_act_fixture(fixture=fixture)['entries']}
        rows = []
        for scenario in fixture['scenarios']:
            for turn in scenario['turns']:
                if turn['selected_message'] is not None:
                    rows.append({'scenario_id': scenario['id'], 'turn_id': turn['id'], 'expected_reply_act': acts[turn['id']], 'off': 'off-' + turn['id'], 'reply_act': 'reply-' + turn['id'], 'affect_only': 'affect-' + turn['id']})
        execution = {
            'status': 'triplet_transport_complete', 'selected_turn_count': 122,
            'model_call_count': 366, 'response_count_by_arm': {arm: 122 for arm in legacy.CONDITIONS},
            'response_char_count_by_arm': {arm: sum(len(row[arm]) for row in rows) for arm in legacy.CONDITIONS},
            'health_profile_sha256': hashlib.sha256(legacy.canonical_bytes(legacy._expected_health_profile(legacy.EVAL_PROFILE))).hexdigest(),
            'private_responses': rows, 'execution_order_offset': 3,
        }
        packet = legacy.build_private_review_packet(fixture, execution, {'a': 'off', 'b': 'reply_act', 'c': 'affect_only'})
        report = legacy.public_report(fixture, legacy.EVAL_PROFILE, execution)
        receipt = {'schema_version': 'airi.affect-broadcast-local-run-receipt.v1', 'local_only': True, 'integrity_scope': 'canonical_sha256_of_report_and_blinded_review_packet', 'authenticity_claim': 'none_hostile_local_environment_not_addressed', 'artifact_sha256': {'public-report.json': hashlib.sha256(guarded.canonical_bytes(report)).hexdigest(), 'private-review-packet.json': hashlib.sha256(guarded.canonical_bytes(packet)).hexdigest()}, 'private_arm_key_custody': 'separate_operator_only_not_receipt_bound'}
        source = root / 'local-results' / 'source'; source.mkdir(parents=True)
        for name, value in {'public-report.json': report, 'private-review-packet.json': packet, 'local-run-receipt.json': receipt}.items():
            (source / name).write_bytes(guarded.canonical_bytes(value))
        keys = root / 'local-operator-keys'; keys.mkdir()
        (keys / 'source.json').write_bytes(guarded.canonical_bytes(legacy.build_private_arm_key({'a': 'off', 'b': 'reply_act', 'c': 'affect_only'}, 3)))

    def _read_source(self):
        source = guarded.LOCAL_RESULTS_DIR / 'source'
        values = {name: json.loads((source / name).read_text(encoding='utf-8')) for name in guarded.SOURCE_NAMES}
        values['private-arm-key.json'] = json.loads((guarded.LOCAL_OPERATOR_KEYS_DIR / 'source.json').read_text(encoding='utf-8'))
        return values

    def _write_source(self, values, *, rehash=False):
        if rehash:
            values['local-run-receipt.json']['artifact_sha256'] = {
                name: hashlib.sha256(guarded.canonical_bytes(values[name])).hexdigest()
                for name in ('public-report.json', 'private-review-packet.json')
            }
        source = guarded.LOCAL_RESULTS_DIR / 'source'
        for name in guarded.SOURCE_NAMES:
            (source / name).write_bytes(guarded.canonical_bytes(values[name]))
        (guarded.LOCAL_OPERATOR_KEYS_DIR / 'source.json').write_bytes(guarded.canonical_bytes(values['private-arm-key.json']))

    def _compose(self):
        return guarded.compose('source', 'out', secret=SECRET, comparison_id=COMPARISON_ID)

    def test_fixed_ids_order_and_sole_deescalation(self):
        fixed = guarded._eligible(legacy.load_fixture())
        self.assertEqual(tuple(fixed), FIXED_IDS)
        self.assertEqual([turn_id for turn_id, item in fixed.items() if item['expected_act'] == 'deescalate'], ['fatigue-09'])

    def test_compose_fixed_templates_and_control_bytes(self):
        with self._custody():
            report, packet, key = self._compose()
            source = guarded.load_source_bundle('source')
        self.assertEqual([row['turn_id'] for row in packet['rows']], list(FIXED_IDS))
        self.assertEqual(len(key['guarded_arm_a_turn_ids']), 11)
        for row in packet['rows']:
            rendered = guarded.realization.render_must_act(row['expected_reply_act'], oracle_context={'emergency_context': True} if row['turn_id'] == 'fatigue-09' else None)['text']
            self.assertIn(rendered, (row['response_a'], row['response_b']))
            self.assertNotIn('{', rendered)  # fixed artifacts are literal prose, not JSON.
            control = row['response_b'] if row['turn_id'] in key['guarded_arm_a_turn_ids'] else row['response_a']
            self.assertEqual(control, source['packet']['rows'][[r['turn_id'] for r in source['packet']['rows']].index(row['turn_id'])]['response_b'])
        guarded.validate_output(report, packet, key, source['raw_hashes'], source)

    def test_all_mapping_permutations_only_documented_one_passes(self):
        from itertools import permutations
        with self._custody():
            for mapping in permutations(legacy.CONDITIONS):
                values = self._read_source(); values['private-arm-key.json']['arm_mapping'] = dict(zip(('a', 'b', 'c'), mapping)); self._write_source(values)
                if mapping == ('off', 'reply_act', 'affect_only'):
                    guarded.load_source_bundle('source')
                else:
                    with self.assertRaises(guarded.EvalError): guarded.load_source_bundle('source')

    def test_source_mapping_offset_bool_and_extra_rejected(self):
        for mutation in (lambda k: k.__setitem__('execution_order_offset', 1), lambda k: k.__setitem__('execution_order_offset', True), lambda k: k.__setitem__('extra', 1)):
            with self._custody():
                values = self._read_source(); mutation(values['private-arm-key.json']); self._write_source(values)
                with self.assertRaises(guarded.EvalError): guarded.load_source_bundle('source')

    def test_source_report_bool_int_and_rehashed_receipt_rejected(self):
        for field, value in (('local_only', 1), ('model_call_count', True)):
            with self._custody():
                values = self._read_source(); values['public-report.json'][field] = value; self._write_source(values, rehash=True)
                with self.assertRaises(guarded.EvalError): guarded.load_source_bundle('source')

    def test_source_packet_custody_tampering_rehashed_rejected(self):
        changes = (
            lambda row: row['context'].__setitem__('x', 'tampered'),
            lambda row: row.__setitem__('selected_message', 'tampered'),
            lambda row: row['review_a'].__setitem__('notes', 'tampered'),
            lambda row: row.__setitem__('response_b', 'tampered'),
            lambda row: row['expected_reply_act'].__setitem__('act', 'thank'),
        )
        for change in changes:
            with self._custody():
                values = self._read_source(); change(values['private-review-packet.json']['rows'][0]); self._write_source(values, rehash=True)
                with self.assertRaises(guarded.EvalError): guarded.load_source_bundle('source')

    def test_source_packet_order_tampering_rehashed_rejected(self):
        with self._custody():
            values = self._read_source()
            rows = values['private-review-packet.json']['rows']
            rows[0], rows[1] = rows[1], rows[0]
            self._write_source(values, rehash=True)
            with self.assertRaises(guarded.EvalError): guarded.load_source_bundle('source')

    def test_receipt_literal_hash_and_key_tamper_rejected(self):
        for mutate in (
            lambda v: v['local-run-receipt.json'].__setitem__('integrity_scope', 'x'),
            lambda v: v['local-run-receipt.json']['artifact_sha256'].__setitem__('public-report.json', '0' * 64),
            lambda v: v['private-arm-key.json'].__setitem__('local_only', False),
        ):
            with self._custody():
                values = self._read_source(); mutate(values); self._write_source(values)
                with self.assertRaises(guarded.EvalError): guarded.load_source_bundle('source')

    def test_verify_source_unchanged(self):
        with self._custody():
            bundle = guarded.load_source_bundle('source')
            (bundle['source'] / 'public-report.json').write_bytes(b'{}')
            with self.assertRaises(guarded.EvalError): guarded.verify_source_unchanged(bundle)

    def test_output_hmac_bound_guarded_set_and_content(self):
        with self._custody():
            report, packet, key = self._compose()
            original = set(key['guarded_arm_a_turn_ids'])
            alternate = sorted(set(FIXED_IDS) - set(key['guarded_arm_a_turn_ids']))[:11]
            key['guarded_arm_a_turn_ids'] = alternate
            for row in packet['rows']:
                was_a = row['turn_id'] in original
                rendered = guarded.realization.render_must_act(row['expected_reply_act'], oracle_context={'emergency_context': True} if row['turn_id'] == 'fatigue-09' else None)['text']
                control = row['response_b'] if was_a else row['response_a']
                now_a = row['turn_id'] in set(alternate)
                row['response_a'], row['response_b'] = (rendered, control) if now_a else (control, rendered)
            packet['run_binding'] = guarded._hmac(SECRET, 'packet-binding', [packet['comparison_id'], [row['turn_id'] for row in packet['rows']]])
            projection = {k: v for k, v in packet.items() if k != 'rows'} | {'rows': [{k: v for k, v in row.items() if not k.startswith('review_')} for row in packet['rows']]}
            key['packet_projection_hmac'] = guarded._hmac(SECRET, 'packet-projection', projection)
            key['report_hmac'] = guarded._hmac(SECRET, 'report', report)
            with self.assertRaises(guarded.EvalError): guarded.validate_output(report, packet, key)

    def test_human_route_injected_and_resigned_rejected(self):
        with self._custody():
            report, packet, key = self._compose()
            source = guarded.load_source_bundle('source')['packet']['rows']
            human = next(row for row in source if row['turn_id'] == 'fatigue-10')
            packet['rows'].append({
                'scenario_id': human['scenario_id'], 'turn_id': human['turn_id'], 'prior_airi': human['prior_airi'],
                'context': human['context'], 'selected_message': human['selected_message'], 'expected_reply_act': human['expected_reply_act'],
                'response_a': human['response_b'], 'response_b': human['response_b'],
                'review_a': guarded._blank_review(), 'review_b': guarded._blank_review(),
            })
            packet['run_binding'] = guarded._hmac(SECRET, 'packet-binding', [packet['comparison_id'], [row['turn_id'] for row in packet['rows']]])
            projection = {k: v for k, v in packet.items() if k != 'rows'} | {'rows': [{k: v for k, v in row.items() if not k.startswith('review_')} for row in packet['rows']]}
            key['packet_projection_hmac'] = guarded._hmac(SECRET, 'packet-projection', projection); key['report_hmac'] = guarded._hmac(SECRET, 'report', report)
            with self.assertRaises(guarded.EvalError): guarded.validate_output(report, packet, key)

    def test_main_compose_failure_aborts_both_reservations(self):
        with self._custody():
            with mock.patch.object(guarded, 'compose', side_effect=guarded.EvalError('compose failed')), mock.patch.object(sys, 'argv', ['guarded', '--source-run', 'source', '--output-run', 'out']):
                with self.assertRaises(guarded.EvalError): guarded.main()
            self.assertFalse((guarded.LOCAL_RESULTS_DIR / '.guarded-delta-out').exists())
            self.assertFalse((guarded.LOCAL_OPERATOR_KEYS_DIR / '.guarded-delta-key-out').exists())

    def test_report_contract_bool_wrong_secret_and_hmac_rejected(self):
        for mutate in (
            lambda r, k: r.__setitem__('method', 'other'), lambda r, k: r['coverage'].__setitem__('guarded_in_a', True),
            lambda r, k: k.__setitem__('comparison_secret_hex', '0' * 64), lambda r, k: k.__setitem__('report_hmac', '0' * 64),
        ):
            with self._custody():
                report, packet, key = self._compose(); mutate(report, key)
                with self.assertRaises(guarded.EvalError): guarded.validate_output(report, packet, key)

    def test_publish_happy_path_has_separate_key_and_sanitized_artifacts(self):
        with self._custody():
            bundle = guarded.load_source_bundle('source'); report, packet, key = guarded.compose('source', 'out', secret=SECRET, comparison_id=COMPARISON_ID, bundle=bundle)
            reservation = guarded.reserve('out'); target = guarded.publish(reservation, report, packet, key, bundle)
            receipt = json.loads((target / 'local-run-receipt.json').read_text(encoding='utf-8'))
            self.assertTrue(target.is_dir()); self.assertTrue((guarded.LOCAL_OPERATOR_KEYS_DIR / 'out.json').is_file())
            self.assertEqual(receipt['artifact_sha256']['public-report.json'], hashlib.sha256((target / 'public-report.json').read_bytes()).hexdigest())
            self.assertNotIn('response_a', (target / 'public-report.json').read_text(encoding='utf-8'))
            self.assertNotIn('response_a', (target / 'local-run-receipt.json').read_text(encoding='utf-8'))
            self.assertNotIn('response_a', (guarded.LOCAL_OPERATOR_KEYS_DIR / 'out.json').read_text(encoding='utf-8'))

    def test_publish_foreign_key_race_survives_rollback(self):
        with self._custody():
            bundle = guarded.load_source_bundle('source'); report, packet, key = guarded.compose('source', 'out', secret=SECRET, comparison_id=COMPARISON_ID, bundle=bundle); reservation = guarded.reserve('out')
            real_rename = guarded.os.rename
            def race(src, dst):
                if Path(dst) == reservation['key']:
                    reservation['key'].write_text('foreign', encoding='utf-8'); raise FileExistsError('race')
                return real_rename(src, dst)
            with mock.patch.object(guarded.os, 'rename', side_effect=race), self.assertRaises(guarded.EvalError): guarded.publish(reservation, report, packet, key, bundle)
            self.assertEqual(reservation['key'].read_text(encoding='utf-8'), 'foreign')

    def test_publish_second_rename_failure_removes_only_owned_key(self):
        with self._custody():
            bundle = guarded.load_source_bundle('source'); report, packet, key = guarded.compose('source', 'out', secret=SECRET, comparison_id=COMPARISON_ID, bundle=bundle); reservation = guarded.reserve('out')
            real_rename = guarded.os.rename; calls = []
            def fail_second(src, dst):
                calls.append((Path(src), Path(dst)))
                if len(calls) == 2: raise OSError('second rename')
                return real_rename(src, dst)
            with mock.patch.object(guarded.os, 'rename', side_effect=fail_second), self.assertRaises(guarded.EvalError): guarded.publish(reservation, report, packet, key, bundle)
            self.assertFalse(reservation['target'].exists()); self.assertFalse(reservation['stage'].exists()); self.assertFalse(reservation['key_stage'].exists()); self.assertFalse(reservation['key'].exists())

    def test_reserve_existing_target_stages_and_key_rejected(self):
        for parent, name in (('local-results', 'out'), ('local-results', '.guarded-delta-out'), ('local-operator-keys', 'out.json'), ('local-operator-keys', '.guarded-delta-key-out')):
            with self._custody() as root:
                path = root / parent / name; path.mkdir() if '.' in name and not name.endswith('.json') else path.write_text('x', encoding='utf-8')
                with self.assertRaises(guarded.EvalError): guarded.reserve('out')

    def test_abort_removes_both_reservations_after_compose_failure(self):
        with self._custody():
            reservation = guarded.reserve('out'); guarded.abort(reservation)
            self.assertFalse(reservation['stage'].exists()); self.assertFalse(reservation['key_stage'].exists())

    def test_name_duplicate_bom_noncanonical_and_oversize_rejected(self):
        for name in ('../x', 'x/y', 'CON', 'NUL', 'a.b', ''):
            with self.assertRaises(guarded.EvalError): guarded._safe_name(name)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'x.json'
            for raw in (b'{"a":1,"a":2}', b'\xef\xbb\xbf{}', b'{ "a":1}', b'{"x":"123"}'):
                path.write_bytes(raw)
                with self.assertRaises(guarded.EvalError): guarded.read_canonical_json(path, 4 if raw.endswith(b'123"}') else 99)

    def test_blank_reviews_are_independent(self):
        left, right = guarded._blank_review(), guarded._blank_review()
        left['notes'] = 'operator note'
        self.assertIsNone(right['notes'])

    def test_symlink_source_file_and_root_rejected_when_supported(self):
        with self._custody() as root:
            try:
                os.symlink(guarded.LOCAL_RESULTS_DIR / 'source', guarded.LOCAL_RESULTS_DIR / 'link-source', target_is_directory=True)
            except (OSError, NotImplementedError): self.skipTest('symlink privilege unavailable')
            with self.assertRaises(guarded.EvalError): guarded.load_source_bundle('link-source')
            os.symlink(guarded.LOCAL_RESULTS_DIR / 'source' / 'public-report.json', guarded.LOCAL_RESULTS_DIR / 'source' / 'linked.json')
            self.assertTrue((guarded.LOCAL_RESULTS_DIR / 'source' / 'linked.json').is_symlink())
            old = guarded.LOCAL_RESULTS_DIR; guarded.LOCAL_RESULTS_DIR = guarded.LOCAL_RESULTS_DIR / 'link-source'
            try:
                with self.assertRaises(guarded.EvalError): guarded.load_source_bundle('source')
            finally: guarded.LOCAL_RESULTS_DIR = old

    def test_purity_and_legacy_contract(self):
        tree = ast.parse((HERE / 'run_guarded_delta_eval.py').read_text(encoding='utf-8'))
        banned = {'socket', 'requests', 'urllib', 'httpx', 'subprocess', 'time', 'random'}
        imports = {node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        imports |= {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertFalse(imports & banned); self.assertEqual(legacy.CONDITIONS, ('off', 'affect_only', 'reply_act')); self.assertEqual(122 * 3, 366)

    def test_tracked_review_summary_is_content_free_and_arithmetically_bound(self):
        summary = json.loads((HERE / 'guarded_delta_review_summary_2026-08-17.json').read_text(encoding='utf-8'))
        self.assertEqual(set(summary), {
            'schema_version', 'date', 'source_commit', 'source_artifacts', 'method',
            'historical_source_authenticity', 'comparison_rows', 'composition', 'review',
            'reviewer_metrics', 'pooled_metrics', 'paired_preference_consensus',
            'act_consensus', 'result', 'limitations',
        })
        self.assertEqual(summary['schema_version'], 'airi.affect-broadcast-guarded-delta-review-summary.v1')
        self.assertEqual(summary['comparison_rows'], 22)
        self.assertEqual(summary['composition'], {'model_calls': 0, 'network_calls': 0})
        self.assertEqual(set(summary['source_artifacts']), {
            'guarded_public_report_sha256', 'guarded_blank_review_packet_sha256',
        })
        self.assertEqual(set(summary['review']), {
            'reviewer_count', 'reviewer_type', 'review_contract_version',
            'reviewer_model_identity', 'locked_review_record_sha256',
            'review_process_attestation', 'packet_only_before_lock_attested',
            'operator_key_access_before_lock_attested', 'condition_identity_blinding',
            'condition_inference_confidence', 'human_review_completed',
        })
        self.assertFalse(summary['review']['human_review_completed'])
        self.assertEqual(summary['review']['reviewer_count'], len(summary['reviewer_metrics']))
        self.assertEqual(len(summary['review']['condition_inference_confidence']), len(summary['reviewer_metrics']))
        self.assertEqual(set(summary['result']), {
            'guarded_delta_preference_signal', 'operational_adoption',
            'quality_safety_gate', 'pending_prerequisites',
        })
        self.assertFalse(summary['result']['operational_adoption'])
        self.assertEqual(summary['result']['quality_safety_gate'], 'fail')
        self.assertEqual(set(summary['pooled_metrics']), {'denominator', 'guarded', 'control', 'preference'})
        self.assertEqual(summary['pooled_metrics']['denominator'], 44)
        self.assertEqual(set(summary['pooled_metrics']['preference']), {'guarded', 'control', 'tie'})
        for condition in ('guarded', 'control'):
            self.assertEqual(set(summary['pooled_metrics'][condition]), {
                'act', 'grounding', 'continuity', 'non_pathological', 'safety_privacy', 'all_pass',
            })
        reviewer_ids = set()
        for reviewer in summary['reviewer_metrics']:
            self.assertEqual(set(reviewer), {'reviewer_id', 'guarded', 'control', 'preference'})
            self.assertNotIn(reviewer['reviewer_id'], reviewer_ids)
            reviewer_ids.add(reviewer['reviewer_id'])
            self.assertEqual(set(reviewer['preference']), {'guarded', 'control', 'tie'})
            self.assertEqual(sum(reviewer['preference'].values()), summary['comparison_rows'])
            for condition in ('guarded', 'control'):
                self.assertEqual(set(reviewer[condition]), {
                    'act', 'grounding', 'continuity', 'non_pathological', 'safety_privacy', 'all_pass',
                })
                for value in reviewer[condition].values():
                    self.assertIs(type(value), int)
                    self.assertGreaterEqual(value, 0)
                    self.assertLessEqual(value, summary['comparison_rows'])
        for condition in ('guarded', 'control'):
            for metric in ('act', 'grounding', 'continuity', 'non_pathological', 'safety_privacy', 'all_pass'):
                self.assertEqual(
                    summary['pooled_metrics'][condition][metric],
                    sum(reviewer[condition][metric] for reviewer in summary['reviewer_metrics']),
                )
        for preference in ('guarded', 'control', 'tie'):
            self.assertEqual(
                summary['pooled_metrics']['preference'][preference],
                sum(reviewer['preference'][preference] for reviewer in summary['reviewer_metrics']),
            )
        self.assertEqual(sum(summary['pooled_metrics']['preference'].values()), 44)
        self.assertEqual(set(summary['paired_preference_consensus']), {
            'guarded_preferred_by_both', 'control_preferred_by_both',
            'one_tie_one_control', 'other_disagreement',
        })
        self.assertEqual(sum(summary['paired_preference_consensus'].values()), summary['comparison_rows'])
        self.assertEqual(
            sum(item['rows'] for item in summary['act_consensus'].values()),
            summary['comparison_rows'],
        )
        for item in summary['act_consensus'].values():
            self.assertEqual(set(item), {'rows', 'guarded', 'control', 'mixed_or_tie'})
            self.assertEqual(
                item['guarded'] + item['control'] + item['mixed_or_tie'],
                item['rows'],
            )
        for digest in summary['source_artifacts'].values():
            self.assertRegex(digest, r'^[0-9a-f]{64}$')
        serialized = json.dumps(summary, ensure_ascii=False, sort_keys=True)
        self.assertNotIn('response_a', serialized)
        self.assertNotIn('response_b', serialized)
        fixture = legacy.load_fixture()
        for scenario in fixture['scenarios']:
            for turn in scenario['turns']:
                for field in ('prior_airi', 'selected_message'):
                    if turn[field]:
                        self.assertNotIn(turn[field], serialized)


if __name__ == '__main__':
    unittest.main()
