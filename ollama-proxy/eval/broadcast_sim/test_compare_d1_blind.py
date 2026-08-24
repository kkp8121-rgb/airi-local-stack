"""Offline fail-closed tests for the frozen D1 four-arm blind comparator.

The D1 frozen-contract verifier (``training/verify_d1_frozen_contract.py``) and
the D1 commitment fixtures are not part of this change, so these tests write
synthetic policy/commitment documents into a temporary directory and stub
``assert_frozen_inputs`` for the duration of each test.  That keeps every case
deterministic, offline, and independent of files that do not exist yet, while
still exercising the comparator's own per-arm gate logic end to end.

Two selection branches cannot be reached with the frozen threshold values: an
arm that clears every additive ``minimum_delta`` already carries a weighted
score delta of at least 0.132 (> 0.08) and improves at least four axes, because
only ``topic_anchor`` has a non-positive ``minimum_delta``.  Those two branches
are therefore exercised with a policy variant that *raises* the selection
threshold; no frozen threshold is ever relaxed here.
"""
import copy
import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE = Path(__file__).with_name('compare_d1_blind.py')
SPEC = importlib.util.spec_from_file_location('compare_d1_blind', MODULE)
comparator = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(comparator)

ROOT_ID = 'airi-d1-blind-freeze-20260825-v1'
ARMS = ['baseline', 'e2', 'e2-c1', 'e2-c2']
SEEDS = [73, 89, 97, 20260824]
ROLES = ['identity_unknown_and_donation_ritual', 'long_continuity_and_stale_transition',
         'factual_grounding_and_complete_show_arc']
CANONICAL = {role: hashlib.sha256(f'{ROOT_ID}/{role}'.encode('utf-8')).hexdigest() for role in ROLES}

POLICY_DOC = {
    'schema_version': 'airi.d1-blind-metric-policy.v1',
    'status': 'frozen_pre_result',
    'report_completeness': {'expected_reports': 48, 'required_fixture_count': 3,
                            'required_seed_count': 4, 'required_arm_count': 4,
                            'on_missing_or_duplicate': 'fail_closed'},
    'arm_rules': {'reference_arm': 'e2', 'delta_gated_arms': ['e2-c1', 'e2-c2']},
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
        'delta_gated_minimum_weighted_score_delta_vs_e2': 0.08,
        'delta_gated_minimum_improved_additive_axes': 4,
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
    'schema_version': 'airi.d1-blind-commitment.v1',
    'root_id': ROOT_ID,
    'fixture_schema_version': 'airi.broadcast-sim-fixture.v1',
    'canonicalization': {
        'algorithm': "utf-8 JSON: sort_keys=true, separators=(',', ':'), ensure_ascii=false",
        'canonicalization_schema_version': 'airi.broadcast-sim-canonical-json.v1',
    },
    'seeds': SEEDS,
    'arms': ARMS,
    'expected_matrix_reports': 48,
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

# Deterministic-utterance-layer world: every arm clears the hard gates and the
# additive minimums, the untrained baseline scores highest, and the two trained
# arms still clear their delta gates.
BASELINE_WINS = {
    'baseline': {'topic_anchored': .90, 'viewer_fact_usage': .80, 'memory_probe': .95,
                 'long_callback': .90, 'complete_show_arc': .95, 'donation_callout_correct': 1.0},
    'e2': {'topic_anchored': .70, 'viewer_fact_usage': .45, 'memory_probe': .75,
           'long_callback': .50, 'complete_show_arc': .75, 'donation_callout_correct': 1.0},
    'e2-c1': {'topic_anchored': .75, 'viewer_fact_usage': .60, 'memory_probe': .90,
              'long_callback': .70, 'complete_show_arc': .95, 'donation_callout_correct': 1.0},
    'e2-c2': {'topic_anchored': .80, 'viewer_fact_usage': .60, 'memory_probe': .95,
              'long_callback': .70, 'complete_show_arc': .95, 'donation_callout_correct': 1.0},
}

# A trained arm on top: e2-c1 mirrors e2 (all deltas zero, so it is ineligible)
# and cannot crowd the margin.
CANDIDATE_ON_TOP = {
    'baseline': {'topic_anchored': .60, 'viewer_fact_usage': .42, 'memory_probe': .50,
                 'long_callback': .50, 'complete_show_arc': .75, 'donation_callout_correct': 1.0},
    'e2': dict(BASELINE_WINS['e2']),
    'e2-c1': dict(BASELINE_WINS['e2']),
    'e2-c2': dict(BASELINE_WINS['e2-c2']),
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


class D1BlindComparatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.reports = self.root / 'reports'
        self.output = self.root / 'comparisons' / 'd1-blind.json'
        self.attestation = self.root / 'evidence' / 'environment-attestation.json'
        self.policy = self.root / 'commitments' / 'airi_d1_metric_policy.json'
        self.commitment = self.root / 'commitments' / 'airi_d1_blind_commitment.json'
        self.policy.parent.mkdir(parents=True, exist_ok=True)
        self.policy.write_text(json.dumps(POLICY_DOC), encoding='utf-8')
        self.commitment.write_text(json.dumps(COMMITMENT_DOC), encoding='utf-8')
        # The D1 frozen-contract verifier does not exist yet; its shape
        # assertions are out of scope for this comparator's gate logic.
        patcher = mock.patch.object(comparator, 'assert_frozen_inputs', lambda policy, commitment: None)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.write_attestation()
        self.addCleanup(self.temp.cleanup)

    def write_attestation(self, *, remove=(), **overrides):
        document = {
            'schema_version': 'airi.d1-environment-attestation.v1',
            'root_id': ROOT_ID, 'run_count': 48,
            'zero_violations': {'privacy': 0, 'localhost_exposure': 0,
                                'external_provider_without_opt_in': 0},
            'handle_grounding_guard': 'on',
            'deterministic_utterance_layer': 'on',
            'verified_by': 'run-airi-broadcast-t3-matrix.ps1',
        }
        document.update(overrides)
        for name in remove:
            document.pop(name, None)
        self.attestation.parent.mkdir(parents=True, exist_ok=True)
        self.attestation.write_text(json.dumps(document), encoding='utf-8')

    def write_policy_variant(self, **selection_overrides):
        document = copy.deepcopy(POLICY_DOC)
        document['selection'].update(selection_overrides)
        path = self.root / 'commitments' / 'variant-policy.json'
        path.write_text(json.dumps(document), encoding='utf-8')
        return path

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

    def run_compare(self, policy=None, output=None):
        return comparator.compare(self.reports, policy or self.policy, self.commitment,
                                  output or self.output, self.attestation)

    # (a) every arm passes the hard gates; the untrained baseline still wins.
    def test_untrained_arm_can_win_when_all_arms_pass(self):
        self.write_matrix(BASELINE_WINS)
        verdict = self.run_compare()
        self.assertEqual(verdict['status'], 'pass')
        self.assertEqual(verdict['winner'], 'baseline')
        self.assertIsNone(verdict['no_winner_reason'])
        self.assertFalse(verdict['adoption_authorized'])
        self.assertEqual(verdict['schema_version'], 'airi.d1-blind-comparison.v1')
        self.assertEqual(verdict['report_count'], 48)
        self.assertEqual(verdict['arms'], ARMS)
        self.assertEqual(verdict['reference_arm'], 'e2')
        self.assertEqual(verdict['delta_gated_arms'], ['e2-c1', 'e2-c2'])
        self.assertEqual(verdict['gates']['failed'], [])
        self.assertEqual(verdict['improved_additive_axes_vs_e2'], {'e2-c1': 5, 'e2-c2': 5})
        self.assertAlmostEqual(verdict['scores']['baseline'], .895, places=6)
        self.assertAlmostEqual(verdict['scores']['e2'], .6175, places=6)
        self.assertAlmostEqual(verdict['scores']['e2-c1'], .7725, places=6)
        self.assertAlmostEqual(verdict['scores']['e2-c2'], .79, places=6)
        self.assertAlmostEqual(verdict['score_margin'], .105, places=6)
        published = json.loads(self.output.read_text(encoding='utf-8'))
        self.assertEqual(published['winner'], 'baseline')

    def test_delta_gates_apply_only_to_the_trained_arms(self):
        self.write_matrix(BASELINE_WINS)
        verdict = self.run_compare()
        per_arm = verdict['gates']['per_arm']
        self.assertEqual(sorted(per_arm), sorted(ARMS))
        for arm in ('baseline', 'e2'):
            self.assertFalse([name for name in per_arm[arm] if name.startswith('legacy.')])
            self.assertNotIn('delta_vs_e2', per_arm[arm]['additive.memory'])
            self.assertNotIn('minimum_delta', per_arm[arm]['additive.memory'])
        for arm in ('e2-c1', 'e2-c2'):
            self.assertTrue(per_arm[arm]['legacy.viewer_fact_usage']['passed'])
            self.assertTrue(per_arm[arm]['additive.memory']['delta_gated'])
            self.assertEqual(per_arm[arm]['additive.memory']['minimum_delta'], 0.15)
            self.assertIn('delta_vs_e2', per_arm[arm]['additive.memory'])
        self.assertEqual(verdict['gates']['failed'], [])

    # (b) a trained arm tops the score but misses its weighted-score delta.
    def test_delta_gated_top_arm_below_score_delta_gets_no_winner(self):
        self.write_matrix(CANDIDATE_ON_TOP)
        policy = self.write_policy_variant(delta_gated_minimum_weighted_score_delta_vs_e2=0.5)
        verdict = self.run_compare(policy=policy)
        self.assertEqual(verdict['status'], 'pass')
        self.assertIsNone(verdict['winner'])
        self.assertIn('e2-c2 weighted score delta', verdict['no_winner_reason'])
        self.assertIn('0.5', verdict['no_winner_reason'])
        self.assertAlmostEqual(verdict['scores']['e2-c2'], .79, places=6)
        published = json.loads(self.output.read_text(encoding='utf-8'))
        self.assertIsNone(published['winner'])
        self.assertFalse(published['adoption_authorized'])

    def test_delta_gated_top_arm_below_improved_axis_count_gets_no_winner(self):
        profiles = {arm: dict(CANDIDATE_ON_TOP[arm]) for arm in ARMS}
        profiles['e2-c2']['topic_anchored'] = .69
        self.write_matrix(profiles)
        policy = self.write_policy_variant(delta_gated_minimum_improved_additive_axes=5)
        verdict = self.run_compare(policy=policy)
        self.assertIsNone(verdict['winner'])
        self.assertEqual(verdict['improved_additive_axes_vs_e2']['e2-c2'], 4)
        self.assertIn('improved 4 additive axes', verdict['no_winner_reason'])

    # (c) one arm's violation removes only that arm from eligibility.
    def test_invented_handle_removes_only_that_arm_from_eligibility(self):
        def mutate(arm, role, seed, report):
            if arm == 'e2-c1' and role == 'factual_grounding_and_complete_show_arc':
                report['summary']['invented_handle_turns'] = 1
            return report

        self.write_matrix(BASELINE_WINS, mutate)
        verdict = self.run_compare()
        self.assertIn('e2-c1:zero_violations.invented_handle', verdict['gates']['failed'])
        self.assertEqual(verdict['gates']['failed'], ['e2-c1:zero_violations.invented_handle'])
        self.assertEqual(verdict['violation_counts']['e2-c1']['invented_handle'], 4)
        self.assertEqual(verdict['violation_counts']['e2-c2']['invented_handle'], 0)
        self.assertEqual(verdict['winner'], 'baseline')
        self.assertIsNone(verdict['no_winner_reason'])

    def test_no_arm_eligible_lists_every_failed_arm_gate(self):
        def mutate(arm, role, seed, report):
            report['summary']['transport_failures'] = 1
            return report

        self.write_matrix(BASELINE_WINS, mutate)
        verdict = self.run_compare()
        self.assertIsNone(verdict['winner'])
        self.assertEqual(sorted(f'{arm}:zero_violations.transport' for arm in ARMS),
                         [name for name in verdict['gates']['failed']
                          if name.endswith('zero_violations.transport')])
        self.assertIn('e2-c2:zero_violations.transport', verdict['no_winner_reason'])

    # (g) the runner-up may be ineligible and still deny the margin.
    def test_margin_counts_ineligible_arms(self):
        profiles = {arm: dict(BASELINE_WINS[arm]) for arm in ARMS}
        profiles['e2-c1'] = {'topic_anchored': .90, 'viewer_fact_usage': .78, 'memory_probe': .95,
                             'long_callback': .90, 'complete_show_arc': .95,
                             'donation_callout_correct': 1.0}

        def mutate(arm, role, seed, report):
            if arm == 'e2-c1' and role == 'long_continuity_and_stale_transition':
                report['summary']['invented_handle_turns'] = 2
            return report

        self.write_matrix(profiles, mutate)
        verdict = self.run_compare()
        self.assertIsNone(verdict['winner'])
        self.assertIn('e2-c1:zero_violations.invented_handle', verdict['gates']['failed'])
        self.assertAlmostEqual(verdict['scores']['e2-c1'], .89, places=6)
        self.assertAlmostEqual(verdict['score_margin'], .005, places=6)
        self.assertIn('margin', verdict['no_winner_reason'])

    def test_exact_tie_between_eligible_arms_gets_no_winner(self):
        profiles = {arm: dict(BASELINE_WINS[arm]) for arm in ARMS}
        profiles['baseline'] = dict(BASELINE_WINS['e2-c2'])
        self.write_matrix(profiles)
        verdict = self.run_compare()
        self.assertIsNone(verdict['winner'])
        self.assertIn('tie', verdict['no_winner_reason'])
        self.assertIn('e2-c2', verdict['no_winner_reason'])

    def test_perfect_rate_failure_is_scoped_to_its_arm(self):
        def mutate(arm, role, seed, report):
            if arm == 'e2-c2' and role == 'identity_unknown_and_donation_ritual' and seed == SEEDS[0]:
                report['rows'] = rows_for(role, probe_hit=False)
            return report

        self.write_matrix(BASELINE_WINS, mutate)
        verdict = self.run_compare()
        self.assertEqual(verdict['gates']['failed'], ['e2-c2:perfect_rates.unknown_identity_safe'])
        self.assertEqual(verdict['perfect_rates']['e2-c2']['unknown_identity_safe'], .75)
        self.assertEqual(verdict['perfect_rates']['e2-c1']['unknown_identity_safe'], 1.0)
        self.assertEqual(verdict['winner'], 'baseline')

    def test_attested_violation_fails_every_arm(self):
        self.write_matrix(BASELINE_WINS)
        self.write_attestation(zero_violations={'privacy': 1, 'localhost_exposure': 0,
                                                'external_provider_without_opt_in': 0})
        verdict = self.run_compare()
        self.assertIsNone(verdict['winner'])
        for arm in ARMS:
            self.assertIn(f'{arm}:zero_violations.privacy', verdict['gates']['failed'])
            self.assertEqual(verdict['gates']['per_arm'][arm]['zero_violations.privacy']['source'],
                             'launcher_environment_attestation')

    # (d) / (e) attestation is the only source for the non-report invariants.
    def test_missing_deterministic_utterance_layer_fails_closed(self):
        self.write_matrix(BASELINE_WINS)
        self.write_attestation(remove=('deterministic_utterance_layer',))
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        self.assertIn("deterministic_utterance_layer == 'on'", str(caught.exception))
        self.assertFalse(self.output.exists())
        self.write_attestation(deterministic_utterance_layer='off')
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        self.assertIn("deterministic_utterance_layer == 'on'", str(caught.exception))

    def test_missing_handle_grounding_guard_fails_closed(self):
        self.write_matrix(BASELINE_WINS)
        self.write_attestation(remove=('handle_grounding_guard',))
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        self.assertIn("handle_grounding_guard == 'on'", str(caught.exception))
        self.assertFalse(self.output.exists())

    def test_attestation_run_count_must_match_the_commitment(self):
        self.write_matrix(BASELINE_WINS)
        self.write_attestation(run_count=36)
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        self.assertIn('run_count is not 48', str(caught.exception))
        self.assertFalse(self.output.exists())

    def test_attestation_is_bound_to_the_commitment_root(self):
        self.write_matrix(BASELINE_WINS)
        self.write_attestation(root_id='airi-other-root')
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        self.assertIn('root_id', str(caught.exception))

    # (f) completeness.
    def test_missing_report_fails_closed(self):
        def mutate(arm, role, seed, report):
            if arm == 'e2-c1' and role == ROLES[1] and seed == SEEDS[2]:
                return None
            return report

        self.write_matrix(BASELINE_WINS, mutate)
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        self.assertIn('reports', str(caught.exception))
        self.assertFalse(self.output.exists())

    def test_duplicate_report_file_fails_closed(self):
        self.write_matrix(BASELINE_WINS)
        source = self.reports / 'e2' / f'e2-{ROLES[0]}-{SEEDS[0]}.json'
        shutil.copyfile(source, source.with_name('e2-copy.json'))
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        self.assertIn('unexpected report file', str(caught.exception))
        self.assertFalse(self.output.exists())

    # (h) the policy's arm roles must match the comparator's frozen constants.
    def test_arm_rules_mismatch_fails_closed(self):
        self.write_matrix(BASELINE_WINS)
        document = copy.deepcopy(POLICY_DOC)
        document['arm_rules']['reference_arm'] = 'baseline'
        path = self.root / 'commitments' / 'bad-reference.json'
        path.write_text(json.dumps(document), encoding='utf-8')
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare(policy=path)
        self.assertIn('reference_arm', str(caught.exception))

        document = copy.deepcopy(POLICY_DOC)
        document['arm_rules']['delta_gated_arms'] = ['e2-c2']
        path = self.root / 'commitments' / 'bad-delta-arms.json'
        path.write_text(json.dumps(document), encoding='utf-8')
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare(policy=path)
        self.assertIn('delta_gated_arms', str(caught.exception))

        document = copy.deepcopy(POLICY_DOC)
        document.pop('arm_rules')
        path = self.root / 'commitments' / 'no-arm-rules.json'
        path.write_text(json.dumps(document), encoding='utf-8')
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare(policy=path)
        self.assertIn('arm_rules', str(caught.exception))
        self.assertFalse(self.output.exists())

    # Report validation.
    def test_report_settings_mismatch_fails_closed(self):
        def mutate(arm, role, seed, report):
            if arm == 'e2-c2' and role == ROLES[2] and seed == SEEDS[3]:
                report['history_turns'] = 12
            return report

        self.write_matrix(BASELINE_WINS, mutate)
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        self.assertIn('settings differ', str(caught.exception))
        self.assertFalse(self.output.exists())

    def test_duplicate_turn_index_fails_closed(self):
        def mutate(arm, role, seed, report):
            if arm == 'baseline' and role == ROLES[0] and seed == SEEDS[1]:
                report['rows'][1]['turn_index'] = 1
            return report

        self.write_matrix(BASELINE_WINS, mutate)
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        self.assertIn('duplicate turn_index', str(caught.exception))

    def test_report_bound_to_its_committed_fixture(self):
        def mutate(arm, role, seed, report):
            if arm == 'e2' and role == ROLES[0] and seed == SEEDS[1]:
                report['fixture_sha256'] = 'f' * 64
            return report

        self.write_matrix(BASELINE_WINS, mutate)
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        self.assertIn('committed blind fixture', str(caught.exception))

    def test_underivable_perfect_rate_names_metric_and_field(self):
        def mutate(arm, role, seed, report):
            if role == 'long_continuity_and_stale_transition':
                report['rows'] = [{'turn_index': 1, 'kind': 'question', 'addressee_ok': None,
                                   'addressee_forbidden_hits': [], 'invented_handles': []}]
            return report

        self.write_matrix(BASELINE_WINS, mutate)
        with self.assertRaises(comparator.BlindComparisonError) as caught:
            self.run_compare()
        message = str(caught.exception)
        self.assertIn('stale_transition_clean', message)
        self.assertIn('arc_event_type', message)
        self.assertFalse(self.output.exists())

    def test_refuses_to_overwrite_existing_verdict(self):
        self.write_matrix(BASELINE_WINS)
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text('{}', encoding='utf-8')
        with self.assertRaises(comparator.BlindComparisonError):
            self.run_compare()
        self.assertEqual(self.output.read_text(encoding='utf-8'), '{}')

    def test_cli_exit_codes(self):
        self.write_matrix(BASELINE_WINS)
        argv = ['--reports-dir', str(self.reports), '--policy', str(self.policy),
                '--commitment', str(self.commitment), '--output', str(self.output),
                '--environment-attestation', str(self.attestation)]
        self.assertEqual(comparator.main(argv), 0)
        self.assertEqual(comparator.main(argv + []), 2)

    def test_expected_model_manifest_sha256_is_enforced(self):
        self.write_matrix(BASELINE_WINS)
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
