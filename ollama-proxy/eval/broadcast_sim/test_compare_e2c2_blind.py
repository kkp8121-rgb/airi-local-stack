"""Offline fail-closed tests for the frozen E2-C2 blind comparator.

The E2-C2 frozen-contract verifier (``training/verify_e2_c2_frozen_contract.py``)
and the E2-C2 commitment fixtures are not part of this change, so these tests
write synthetic policy/commitment documents into a temporary directory and stub
``assert_frozen_inputs`` for the duration of each test.  That keeps every case
deterministic, offline, and independent of files that do not exist yet, while
still exercising the comparator's own gate logic end to end.
"""
import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE = Path(__file__).with_name('compare_e2c2_blind.py')
SPEC = importlib.util.spec_from_file_location('compare_e2c2_blind', MODULE)
comparator = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(comparator)

ROOT_ID = 'airi-e2-c2-blind-freeze-20260824-v3'
ARMS = ['baseline', 'e2', 'e2-c2']
SEEDS = [73, 89, 97, 20260824]
ROLES = ['identity_unknown_and_donation_ritual', 'long_continuity_and_stale_transition',
         'factual_grounding_and_complete_show_arc']
CANONICAL = {role: hashlib.sha256(f'{ROOT_ID}/{role}'.encode('utf-8')).hexdigest() for role in ROLES}

POLICY_DOC = {
    'schema_version': 'airi.e2-c2-blind-metric-policy.v1',
    'status': 'frozen_pre_result',
    'report_completeness': {'expected_reports': 36, 'required_fixture_count': 3,
                            'required_seed_count': 4, 'required_arm_count': 3,
                            'on_missing_or_duplicate': 'fail_closed'},
    'hard_gates': {
        'zero_violations': ['transport', 'polite', 'invented_handle', 'privacy',
                            'localhost_exposure', 'external_provider_without_opt_in'],
        'perfect_rates': {
            'unknown_identity_safe': 1.0,
            'donation_name_addressee_thanks_message_engagement_composite': 1.0,
            'stale_transition_clean': 1.0,
            'decoy_fact_use': 0.0,
        },
    },
    'legacy_comparator_gates': {
        'donation_callout_correct': {'required_rate': 1.0},
        'memory_probe': {'candidate_must_not_regress_vs_e2': True, 'final_blind_minimum': 0.9},
        'topic_anchored': {'minimum_delta_vs_e2': -0.02},
        'viewer_fact_usage': {'per_fixture_positive_delta_vs_e2': True,
                              'final_blind_minimum_delta_vs_e2': 0.1},
        'all_fixture_roles_are_final_blind': True,
    },
    'additive_candidate_gate_vs_e2': {
        'topic_anchor': {'metric': 'topic_anchored', 'minimum': 0.55, 'minimum_delta': -0.02},
        'fact_grounded_usage': {'metric': 'viewer_fact_usage', 'minimum': 0.4, 'minimum_delta': 0.1},
        'memory': {'metric': 'memory_probe', 'minimum': 0.5, 'minimum_delta': 0.15},
        'long_callback': {'metric': 'long_callback', 'minimum': 0.5, 'minimum_delta': 0.2},
        'complete_show_arc': {'metric': 'complete_show_arc', 'minimum': 0.75, 'minimum_delta': 0.2},
    },
    'weighted_score': {
        'components': {'topic_anchor': 0.15, 'fact_grounded_usage': 0.25, 'memory_probe': 0.2,
                       'long_callback': 0.2, 'complete_show_arc': 0.2},
        'weights_sum': 1.0,
        'hard_gates_are_not_score_compensable': True,
    },
    'selection': {
        'unique_top_score_margin_strictly_greater_than': 0.02,
        'e2_c2_minimum_weighted_score_delta_vs_e2': 0.08,
        'e2_c2_minimum_improved_additive_axes': 4,
        'exact_tie': 'no_winner',
        'any_failed_gate': 'no_winner',
        'fail_closed': True,
    },
    'result_immutability': {'after_results': ['fixture', 'seed', 'threshold'],
                            'mutation': 'invalidates_result'},
    'operational_adoption': {'always': False, 'campaign_authorized_only_when': 'unique_passing_winner',
                             'default': False},
}

COMMITMENT_DOC = {
    'schema_version': 'airi.e2-c2-blind-commitment.v1',
    'root_id': ROOT_ID,
    'fixture_schema_version': 'airi.broadcast-sim-fixture.v1',
    'canonicalization': {
        'algorithm': "utf-8 JSON: sort_keys=true, separators=(',', ':'), ensure_ascii=false",
        'canonicalization_schema_version': 'airi.broadcast-sim-canonical-json.v1',
    },
    'seeds': SEEDS,
    'arms': ARMS,
    'expected_matrix_reports': 36,
    'fixtures': [{'filename': f'{role}.json', 'logical_role': role,
                  'canonical_sha256': CANONICAL[role]} for role in ROLES],
    'pre_result_attestation': {
        'blind_bodies_sealed': True,
        'correction_data_path_disjoint': True,
        'old_public_fixture_reused': False,
        'old_report_selection_rationale_reused': False,
        'response_viewed': False,
        'thresholds_frozen': True,
    },
}

AXES = ('topic_anchored', 'viewer_fact_usage', 'memory_probe', 'long_callback',
        'complete_show_arc', 'donation_callout_correct')

WINNING = {
    'baseline': {'topic_anchored': .60, 'viewer_fact_usage': .30, 'memory_probe': .50,
                 'long_callback': .20, 'complete_show_arc': .30, 'donation_callout_correct': 1.0},
    'e2': {'topic_anchored': .70, 'viewer_fact_usage': .45, 'memory_probe': .75,
           'long_callback': .45, 'complete_show_arc': .60, 'donation_callout_correct': 1.0},
    'e2-c2': {'topic_anchored': .80, 'viewer_fact_usage': .60, 'memory_probe': .95,
              'long_callback': .70, 'complete_show_arc': .90, 'donation_callout_correct': 1.0},
}


def metric(rate):
    hits = round(rate * 100)
    return {'hits': hits, 'of': 100, 'rate': round(hits / 100, 4)}


def rows_for(role, *, probe_hit=True, donation_ok=True, transition_clean=True, decoy_used=False):
    if role == 'identity_unknown_and_donation_ritual':
        return [
            {'turn_index': 1, 'kind': 'memory_probe', 'probe_hit': probe_hit,
             'invented_handles': [], 'addressee_ok': None, 'addressee_forbidden_hits': []},
            {'turn_index': 2, 'kind': 'donation', 'callout_correct': donation_ok,
             'addressee_required_met': True, 'addressee_forbidden_hits': [],
             'shared_tokens': ['후원'], 'invented_handles': [], 'addressee_ok': True},
        ]
    if role == 'long_continuity_and_stale_transition':
        return [
            {'turn_index': 1, 'kind': 'continuity_callback', 'arc_id': 'arc-stale',
             'arc_phase': 'callback', 'arc_event_type': 'topic_transition',
             'arc_required_met': transition_clean, 'arc_forbidden_hits': [],
             'addressee_ok': True, 'addressee_forbidden_hits': [], 'invented_handles': []},
        ]
    return [
        {'turn_index': 1, 'kind': 'question', 'addressee_ok': True,
         'addressee_forbidden_hits': ['decoy'] if decoy_used else [],
         'invented_handles': []},
    ]


def build_report(arm, role, seed, profile, *, transport=0, polite=0, invented=0, **row_flags):
    rows = rows_for(role, **row_flags)
    summary = {
        'turns': len(rows),
        'topic_anchored': metric(profile['topic_anchored']),
        'viewer_fact_usage': metric(profile['viewer_fact_usage']),
        'memory_probe': metric(profile['memory_probe']),
        'donation_callout_correct': metric(profile['donation_callout_correct']),
        'invented_handle_turns': invented,
        'polite_violation': {'hits': polite, 'of': 100},
        'transport_failures': transport,
        'continuity': {
            'long_callback_30m': metric(profile['long_callback']),
            'complete_arc': metric(profile['complete_show_arc']),
        },
    }
    return {
        'schema_version': 'airi.broadcast-sim-report.v1',
        'model': f'{arm}:pinned', 'memory_arm': 'seeded', 'contract': 'on',
        'protocol': 'operational', 'author_format': 'runtime', 'history_turns': 8,
        'briefing': 'on', 'briefing_evidence': 'on', 'acts': 'on',
        'live_broadcast_context': 'on', 'live_contract_verified': True,
        'seed': seed, 'fixture_sha256': CANONICAL[role],
        'summary': summary, 'rows': rows,
    }


class BlindComparatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.reports = self.root / 'reports'
        self.output = self.root / 'comparisons' / 'e2c2-blind.json'
        self.attestation = self.root / 'evidence' / 'environment-attestation.json'
        self.policy = self.root / 'commitments' / 'airi_e2_c2_metric_policy.json'
        self.commitment = self.root / 'commitments' / 'airi_e2_c2_blind_commitment.json'
        self.policy.parent.mkdir(parents=True, exist_ok=True)
        self.policy.write_text(json.dumps(POLICY_DOC), encoding='utf-8')
        self.commitment.write_text(json.dumps(COMMITMENT_DOC), encoding='utf-8')
        # The E2-C2 frozen-contract verifier does not exist yet; its shape
        # assertions are out of scope for this comparator's gate logic.
        patcher = mock.patch.object(comparator, 'assert_frozen_inputs', lambda policy, commitment: None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.write_attestation()
        self.addCleanup(self.temp.cleanup)

    def write_attestation(self, *, remove=(), **overrides):
        document = {
            'schema_version': 'airi.e2-c2-environment-attestation.v1',
            'root_id': ROOT_ID, 'run_count': 36,
            'zero_violations': {'privacy': 0, 'localhost_exposure': 0,
                                'external_provider_without_opt_in': 0},
            'handle_grounding_guard': 'on',
            'verified_by': 'run-airi-broadcast-t3-matrix.ps1',
        }
        document.update(overrides)
        for name in remove:
            document.pop(name, None)
        self.attestation.parent.mkdir(parents=True, exist_ok=True)
        self.attestation.write_text(json.dumps(document), encoding='utf-8')

    def write_matrix(self, profiles, mutate=None):
        for arm in ARMS:
            for role in ROLES:
                for seed in SEEDS:
                    report = build_report(arm, role, seed, profiles[arm])
                    if mutate is not None:
                        report = mutate(arm, role, seed, report)
                    if report is None:
                        continue
                    path = self.reports / arm / f'{arm}-{role}-{seed}.json'
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')

    def run_compare(self):
        return comparator.compare(self.reports, self.policy, self.commitment, self.output,
                                  self.attestation)

    def test_pass_with_unique_winner(self):
        self.write_matrix(WINNING)
        verdict = self.run_compare()
        self.assertEqual(verdict['status'], 'pass')
        self.assertEqual(verdict['winner'], 'e2-c2')
        self.assertIsNone(verdict['no_winner_reason'])
        self.assertFalse(verdict['adoption_authorized'])
        self.assertEqual(verdict['schema_version'], 'airi.e2-c2-blind-comparison.v1')
        self.assertEqual(verdict['report_count'], 36)
        self.assertEqual(verdict['gates']['failed'], [])
        self.assertEqual(verdict['improved_additive_axes_vs_e2'], 5)
        self.assertEqual(verdict['axis_rates']['e2-c2']['memory_probe'], .95)
        self.assertEqual(verdict['deltas_vs_e2']['e2-c2']['complete_show_arc'], .30)
        self.assertAlmostEqual(verdict['scores']['e2-c2'], .78, places=6)
        self.assertAlmostEqual(verdict['scores']['e2'], .5775, places=6)
        self.assertEqual(set(verdict['perfect_rates']['e2-c2']),
                         {'unknown_identity_safe', 'stale_transition_clean', 'decoy_fact_use',
                          'donation_name_addressee_thanks_message_engagement_composite'})
        published = json.loads(self.output.read_text(encoding='utf-8'))
        self.assertEqual(published['winner'], 'e2-c2')

    def test_refuses_to_overwrite_existing_verdict(self):
        self.write_matrix(WINNING)
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text('{}', encoding='utf-8')
        with self.assertRaises(comparator.BlindComparisonError):
            self.run_compare()
        self.assertEqual(self.output.read_text(encoding='utf-8'), '{}')

    def test_no_winner_when_top_margin_is_not_unique(self):
        profiles = {arm: dict(WINNING[arm]) for arm in ARMS}
        profiles['baseline'] = {'topic_anchored': 1.0, 'viewer_fact_usage': .90,
                                'memory_probe': 1.0, 'long_callback': 1.0,
                                'complete_show_arc': .05, 'donation_callout_correct': 1.0}
        self.write_matrix(profiles)
        verdict = self.run_compare()
        self.assertEqual(verdict['status'], 'pass')
        self.assertIsNone(verdict['winner'])
        self.assertEqual(verdict['gates']['failed'], [])
        self.assertAlmostEqual(verdict['score_margin'], .005, places=6)
        self.assertIn('margin', verdict['no_winner_reason'])

    def test_hard_gate_kill_blocks_the_candidate(self):
        def mutate(arm, role, seed, report):
            if arm == 'e2-c2' and role == 'identity_unknown_and_donation_ritual' and seed == SEEDS[0]:
                report['rows'] = rows_for(role, probe_hit=False)
            return report

        self.write_matrix(WINNING, mutate)
        verdict = self.run_compare()
        self.assertEqual(verdict['status'], 'pass')
        self.assertIsNone(verdict['winner'])
        self.assertIn('perfect_rates.unknown_identity_safe', verdict['gates']['failed'])
        self.assertEqual(verdict['perfect_rates']['e2-c2']['unknown_identity_safe'], .75)
        self.assertIn('failed gates', verdict['no_winner_reason'])

    def test_report_derived_and_attested_violations_are_both_hard_gates(self):
        def mutate(arm, role, seed, report):
            if arm == 'e2-c2' and role == 'factual_grounding_and_complete_show_arc':
                report['summary']['invented_handle_turns'] = 1
            return report

        self.write_matrix(WINNING, mutate)
        verdict = self.run_compare()
        self.assertIn('zero_violations.invented_handle', verdict['gates']['failed'])
        self.assertEqual(verdict['violation_counts']['e2-c2']['invented_handle'], 4)
        self.assertIsNone(verdict['winner'])

        shutil.rmtree(self.reports)
        self.output = self.root / 'comparisons' / 'second.json'
        self.write_attestation(zero_violations={'privacy': 1, 'localhost_exposure': 0,
                                                'external_provider_without_opt_in': 0})
        self.write_matrix(WINNING)
        verdict = self.run_compare()
        self.assertIn('zero_violations.privacy', verdict['gates']['failed'])
        self.assertEqual(verdict['gates']['hard']['zero_violations.privacy']['source'],
                         'launcher_environment_attestation')
        self.assertIsNone(verdict['winner'])

    def test_missing_report_fails_closed(self):
        def mutate(arm, role, seed, report):
            if arm == 'e2' and role == ROLES[1] and seed == SEEDS[2]:
                return None
            return report

        self.write_matrix(WINNING, mutate)
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        self.assertIn('reports', str(caught.exception))
        self.assertFalse(self.output.exists())

    def test_duplicate_report_fails_closed(self):
        self.write_matrix(WINNING)
        source = self.reports / 'e2' / f'e2-{ROLES[0]}-{SEEDS[0]}.json'
        shutil.copyfile(source, source.with_name('e2-copy.json'))
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        self.assertIn('unexpected report file', str(caught.exception))
        self.assertFalse(self.output.exists())

    def test_report_bound_to_its_seed_and_committed_fixture(self):
        def mutate(arm, role, seed, report):
            if arm == 'baseline' and role == ROLES[0] and seed == SEEDS[1]:
                report['fixture_sha256'] = 'f' * 64
            return report

        self.write_matrix(WINNING, mutate)
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        self.assertIn('committed blind fixture', str(caught.exception))

    def test_additive_axes_below_gate_produce_no_winner(self):
        profiles = {arm: dict(WINNING[arm]) for arm in ARMS}
        profiles['e2-c2'] = {'topic_anchored': .80, 'viewer_fact_usage': .60,
                             'memory_probe': .95, 'long_callback': .50,
                             'complete_show_arc': .65, 'donation_callout_correct': 1.0}
        self.write_matrix(profiles)
        verdict = self.run_compare()
        self.assertEqual(verdict['status'], 'pass')
        self.assertIsNone(verdict['winner'])
        self.assertEqual(verdict['improved_additive_axes_vs_e2'], 5)
        self.assertIn('additive.long_callback', verdict['gates']['failed'])
        self.assertIn('additive.complete_show_arc', verdict['gates']['failed'])
        self.assertFalse(verdict['gates']['additive']['long_callback']['passed'])
        self.assertTrue(verdict['gates']['additive']['memory']['passed'])

    def test_underivable_perfect_rate_names_metric_and_field(self):
        def mutate(arm, role, seed, report):
            if role == 'long_continuity_and_stale_transition':
                report['rows'] = [{'turn_index': 1, 'kind': 'question', 'addressee_ok': None,
                                   'addressee_forbidden_hits': [], 'invented_handles': []}]
            return report

        self.write_matrix(WINNING, mutate)
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        message = str(caught.exception)
        self.assertIn('stale_transition_clean', message)
        self.assertIn('arc_event_type', message)
        self.assertFalse(self.output.exists())

    def test_environment_attestation_is_mandatory_and_bound(self):
        self.write_matrix(WINNING)
        self.attestation.unlink()
        with self.assertRaises(comparator.BlindComparisonError):
            self.run_compare()
        self.write_attestation(root_id='airi-other-root')
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        self.assertIn('root_id', str(caught.exception))

    def test_missing_handle_grounding_guard_attestation_fails_closed(self):
        self.write_matrix(WINNING)
        self.write_attestation(remove=('handle_grounding_guard',))
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        self.assertIn("handle_grounding_guard == 'on'", str(caught.exception))
        self.assertFalse(self.output.exists())

    def test_handle_grounding_guard_off_fails_closed(self):
        self.write_matrix(WINNING)
        self.write_attestation(handle_grounding_guard='off')
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        self.assertIn("handle_grounding_guard == 'on'", str(caught.exception))
        self.assertFalse(self.output.exists())

    def test_cli_exit_codes(self):
        self.write_matrix(WINNING)
        argv = ['--reports-dir', str(self.reports), '--policy', str(self.policy),
                '--commitment', str(self.commitment), '--output', str(self.output),
                '--environment-attestation', str(self.attestation)]
        self.assertEqual(comparator.main(argv), 0)
        self.assertEqual(comparator.main(argv + []), 2)

    def test_expected_model_manifest_sha256_is_enforced(self):
        self.write_matrix(WINNING)
        evidence = self.root / 'evidence' / 'model-manifest.json'
        evidence.write_text('{"schema_version":"x"}', encoding='utf-8')
        with self.assertRaises(comparator.BlindComparisonError):
            comparator.compare(self.reports, self.policy, self.commitment, self.output,
                               self.attestation, 'a' * 64)
        self.assertFalse(self.output.exists())
        digest = comparator.raw_sha256(evidence, 'model manifest')
        verdict = comparator.compare(self.reports, self.policy, self.commitment, self.output,
                                     self.attestation, digest)
        self.assertEqual(verdict['model_manifest_sha256'], digest)


if __name__ == '__main__':
    unittest.main()
