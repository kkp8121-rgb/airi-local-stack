import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE = Path(__file__).with_name('compare_broadcast_t3.py')
SPEC = importlib.util.spec_from_file_location('compare_broadcast_t3', MODULE)
comparator = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(comparator)

SEEDS = (7, 8, 9, 10)
BASE_DIGEST = 'a' * 64
CANDIDATE_DIGEST = 'b' * 64


class ComparatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / 'base'; self.candidate = self.root / 'candidate'
        self.base.mkdir(); self.candidate.mkdir()
        fixture = {'synthetic': True, 'version': 1}
        fixture_path = self.root / 'fixture.json'
        fixture_path.write_text(json.dumps(fixture), encoding='utf-8')
        raw = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
        canonical = comparator.canonical_sha(fixture)
        self.manifest = self.root / 'manifest.json'
        self.manifest.write_text(json.dumps({'fixtures': [{'filename': 'fixture.json', 'creation_order': 1,
            'role': 'final_blind', 'raw_sha256': raw, 'canonical_sha256': canonical}]}), encoding='utf-8')
        self.sha = canonical

    def tearDown(self): self.temp.cleanup()

    def report(self, seed=SEEDS[0], candidate=False, **changes):
        summary = {
            'turns': 2, 'transport_failures': 0,
            'donation_callout_correct': {'hits': 1, 'of': 1},
            'memory_probe': {'hits': 1, 'of': 1},
            'topic_anchored': {'hits': 2, 'of': 2},
            'viewer_fact_usage': {'hits': 1 if candidate else 0, 'of': 2},
        }
        value = {'fixture_sha256': self.sha, 'seed': seed, 'contract': 'on', 'briefing': 'on',
                 'acts': 'on', 'briefing_evidence': 'on', 'live_broadcast_context': 'on',
                 'history_turns': 8, 'protocol': 'operational', 'author_format': 'runtime',
                 'live_contract_verified': True, 'summary': summary,
                 'model': 'cand:one' if candidate else 'base:one',
                 'model_digest': CANDIDATE_DIGEST if candidate else BASE_DIGEST,
                 'memory_arm': 'seeded', 'contract_version': 'v1', 'max_tokens': 220,
                 'rows': [{'turn_index': 1, 'message_id': 'a', 'polite_violation': False, 'invented_handles': []},
                          {'turn_index': 2, 'message_id': 'b', 'polite_violation': False, 'invented_handles': []}]}
        for key, item in changes.items():
            if key == 'summary': value['summary'].update(item)
            else: value[key] = item
        return value

    def put(self, directory, name, report):
        (directory / name).write_text(json.dumps(report), encoding='utf-8')

    def compare_reports(self):
        return comparator.compare(self.base, self.candidate, self.manifest, self.root / 'out.json')

    def passing_pair(self, seeds=SEEDS):
        for seed in seeds:
            self.put(self.base, f'x-{seed}.json', self.report(seed))
            self.put(self.candidate, f'x-{seed}.json', self.report(seed, candidate=True))

    def replace_candidate(self, **changes):
        self.put(self.candidate, f'x-{SEEDS[0]}.json', self.report(candidate=True, **changes))

    def assert_fails_with(self, reason):
        result = self.compare_reports()
        self.assertEqual(result['status'], 'fail')
        self.assertTrue(any(reason in item for item in result['reasons']), result['reasons'])

    def test_pass(self):
        self.passing_pair(); self.assertEqual(self.compare_reports()['status'], 'pass')

    def test_missing_pair(self):
        for seed in SEEDS: self.put(self.base, f'x-{seed}.json', self.report(seed))
        self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_duplicate(self):
        self.passing_pair(); self.put(self.base, 'y.json', self.report()); self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_fixture_hash_drift(self):
        self.passing_pair(); (self.root / 'fixture.json').write_text('{}', encoding='utf-8'); self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_settings_mismatch(self):
        self.passing_pair(); self.replace_candidate(contract='off'); self.assert_fails_with('settings mismatch')

    def test_transport_failure(self):
        self.passing_pair(); self.replace_candidate(summary={'transport_failures': 1}); self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_donation_regression(self):
        self.passing_pair(); self.replace_candidate(summary={'donation_callout_correct': {'hits': 0, 'of': 1}}); self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_invented_handle(self):
        self.passing_pair(); bad = self.report(candidate=True); bad['rows'][0]['invented_handles'] = ['redacted']
        self.put(self.candidate, f'x-{SEEDS[0]}.json', bad); self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_memory_regression(self):
        self.passing_pair(); self.replace_candidate(summary={'memory_probe': {'hits': 0, 'of': 1}}); self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_topic_regression(self):
        self.passing_pair(); self.replace_candidate(summary={'topic_anchored': {'hits': 1, 'of': 2}}); self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_fact_gain_shortfall(self):
        for seed in SEEDS:
            self.put(self.base, f'x-{seed}.json', self.report(seed))
            self.put(self.candidate, f'x-{seed}.json', self.report(seed, candidate=True, summary={'viewer_fact_usage': {'hits': 0, 'of': 2}}))
        self.assertEqual(self.compare_reports()['status'], 'fail')

    # R2 F5: seed floor per fixture is fail-closed.
    def test_three_seeds_fail_seed_floor(self):
        self.assertEqual(comparator.MIN_SEEDS_PER_FIXTURE, 4)
        self.passing_pair(seeds=SEEDS[:3]); self.assert_fails_with('seed count below minimum 4')

    # R2 F6: confounders must be exact across every paired report.
    def test_max_tokens_mismatch_fails(self):
        self.passing_pair(); self.replace_candidate(max_tokens=512); self.assert_fails_with('confounder fields differ')

    def test_memory_arm_mismatch_fails(self):
        self.passing_pair()
        for seed in SEEDS: self.put(self.candidate, f'x-{seed}.json', self.report(seed, candidate=True, memory_arm='off'))
        self.assert_fails_with('differ between base and candidate')

    def test_contract_version_mismatch_fails(self):
        self.passing_pair()
        for seed in SEEDS: self.put(self.candidate, f'x-{seed}.json', self.report(seed, candidate=True, contract_version='v2'))
        self.assert_fails_with('differ between base and candidate')

    def test_digest_drift_within_one_arm_fails(self):
        self.passing_pair(); self.replace_candidate(model_digest='c' * 64); self.assert_fails_with('differ within one report directory')

    def test_same_digest_on_both_sides_fails(self):
        self.passing_pair()
        for seed in SEEDS: self.put(self.candidate, f'x-{seed}.json', self.report(seed, candidate=True, model_digest=BASE_DIGEST))
        self.assert_fails_with('share one model digest')

    def test_missing_or_malformed_confounder_fields_fail_closed(self):
        for field, value in (('max_tokens', None), ('model_digest', None), ('memory_arm', None),
                             ('contract_version', None), ('max_tokens', '220'), ('model_digest', 'A' * 64)):
            with self.subTest(field=field, value=value):
                self.passing_pair()
                bad = self.report(candidate=True)
                if value is None: bad.pop(field)
                else: bad[field] = value
                self.put(self.candidate, f'x-{SEEDS[0]}.json', bad)
                self.assert_fails_with(field)

    @unittest.skipUnless(list(MODULE.parent.rglob('*r4*.json')), 'no local r4 report')
    def test_current_r4_fails_if_present(self):
        # Kept deliberately independent of report location/contents: a lone r4 report
        # cannot satisfy the paired, complete fixture set required by this comparator.
        r4 = next(MODULE.parent.rglob('*r4*.json'))
        self.put(self.base, 'r4.json', json.loads(r4.read_text(encoding='utf-8')))
        self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_pass_result_records_provenance_for_full_run(self):
        self.passing_pair()
        result = self.compare_reports()
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['phase'], 'all')
        self.assertEqual(result['fixtures_compared'], ['fixture.json'])
        self.assertEqual(result['seeds_by_fixture'], {'fixture.json': sorted(SEEDS)})

    def test_phase_filter_is_recorded_instead_of_all(self):
        self.passing_pair()
        result = comparator.compare(self.base, self.candidate, self.manifest,
                                     self.root / 'out-phase.json', phase='final_blind')
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['phase'], 'final_blind')
        self.assertEqual(result['fixtures_compared'], ['fixture.json'])
        self.assertEqual(result['seeds_by_fixture'], {'fixture.json': sorted(SEEDS)})


if __name__ == '__main__':
    unittest.main()
