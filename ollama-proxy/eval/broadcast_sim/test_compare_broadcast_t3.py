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

    def report(self, **changes):
        summary = {
            'turns': 2, 'transport_failures': 0,
            'donation_callout_correct': {'hits': 1, 'of': 1},
            'memory_probe': {'hits': 1, 'of': 1},
            'topic_anchored': {'hits': 2, 'of': 2},
            'viewer_fact_usage': {'hits': 0, 'of': 2},
        }
        value = {'fixture_sha256': self.sha, 'seed': 7, 'contract': 'on', 'briefing': 'on',
                 'acts': 'on', 'briefing_evidence': 'on', 'live_broadcast_context': 'on',
                 'history_turns': 8, 'protocol': 'operational', 'author_format': 'runtime',
                 'live_contract_verified': True, 'summary': summary,
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

    def passing_pair(self):
        self.put(self.base, 'x.json', self.report())
        candidate = self.report(); candidate['summary']['viewer_fact_usage'] = {'hits': 1, 'of': 2}
        self.put(self.candidate, 'x.json', candidate)

    def test_pass(self):
        self.passing_pair(); self.assertEqual(self.compare_reports()['status'], 'pass')

    def test_missing_pair(self):
        self.put(self.base, 'x.json', self.report()); self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_duplicate(self):
        self.passing_pair(); self.put(self.base, 'y.json', self.report()); self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_fixture_hash_drift(self):
        self.passing_pair(); (self.root / 'fixture.json').write_text('{}', encoding='utf-8'); self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_settings_mismatch(self):
        self.passing_pair(); changed = self.report(contract='off'); changed['summary']['viewer_fact_usage'] = {'hits': 1, 'of': 2}; self.put(self.candidate, 'x.json', changed); self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_transport_failure(self):
        self.passing_pair(); bad = self.report(summary={'transport_failures': 1, 'viewer_fact_usage': {'hits': 1, 'of': 2}}); self.put(self.candidate, 'x.json', bad); self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_donation_regression(self):
        self.passing_pair(); bad = self.report(summary={'donation_callout_correct': {'hits': 0, 'of': 1}, 'viewer_fact_usage': {'hits': 1, 'of': 2}}); self.put(self.candidate, 'x.json', bad); self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_invented_handle(self):
        self.passing_pair(); bad = self.report(); bad['summary']['viewer_fact_usage'] = {'hits': 1, 'of': 2}; bad['rows'][0]['invented_handles'] = ['redacted']; self.put(self.candidate, 'x.json', bad); self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_memory_regression(self):
        self.passing_pair(); bad = self.report(summary={'memory_probe': {'hits': 0, 'of': 1}, 'viewer_fact_usage': {'hits': 1, 'of': 2}}); self.put(self.candidate, 'x.json', bad); self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_topic_regression(self):
        self.passing_pair(); bad = self.report(summary={'topic_anchored': {'hits': 1, 'of': 2}, 'viewer_fact_usage': {'hits': 1, 'of': 2}}); self.put(self.candidate, 'x.json', bad); self.assertEqual(self.compare_reports()['status'], 'fail')

    def test_fact_gain_shortfall(self):
        self.put(self.base, 'x.json', self.report()); self.put(self.candidate, 'x.json', self.report()); self.assertEqual(self.compare_reports()['status'], 'fail')

    @unittest.skipUnless(list(Path.cwd().rglob('*r4*.json')), 'no local r4 report')
    def test_current_r4_fails_if_present(self):
        # Kept deliberately independent of report location/contents: a lone r4 report
        # cannot satisfy the paired, complete fixture set required by this comparator.
        r4 = next(Path.cwd().rglob('*r4*.json'))
        self.put(self.base, 'r4.json', json.loads(r4.read_text(encoding='utf-8')))
        self.assertEqual(self.compare_reports()['status'], 'fail')


if __name__ == '__main__':
    unittest.main()
