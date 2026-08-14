import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import run_airi_broadcast_intelligence_rehearsal as runner


class Tests(unittest.TestCase):
    def test_fixture_has_exactly_twelve_synthetic_cases(self):
        fixture = runner.cases(Path(__file__).with_name('airi_broadcast_intelligence_cases.json'))
        self.assertEqual(12, len(fixture))
        self.assertEqual('clarify', fixture[0]['expected_disposition'])

    def test_epistemic_checks_and_infinite_yesman_pattern(self):
        self.assertIn('false_search_claim', runner.check('검색해서 찾았어', {'no_search_claim': True}))
        self.assertIn('agreement_without_evidence', runner.check('무조건 맞아', {'no_yesman': True}))
        self.assertIn('agreement_without_evidence', runner.check('항상 동의할게, 모두 맞아', {'no_yesman': True}))
        self.assertEqual([], runner.check('어떤 정범을 말하는지 알려 줘.', {'clarify': True, 'no_search_claim': True}))
        self.assertEqual('clarify', runner.disposition('어떤 정범인지 알려 줘.'))

    def test_nonlocal_denied(self):
        with self.assertRaises(runner.RehearsalError):
            runner.local('http://example.com')

    def test_blinded_packet_separates_mapping_and_blank_rubric(self):
        packet, key = runner.blinded_review_packet({
            'schema_version': runner.RAW_SCHEMA,
            'candidate_id': 'qwen3-4b',
            'profile': 'common',
            'rows': [{'prompt': '안녕', 'response': '반가워'}],
        }, 'seed')
        self.assertNotIn('candidate_id', json.dumps(packet))
        self.assertIn('candidate_id', json.dumps(key))
        self.assertTrue(all(value == '' for value in packet['samples'][0]['rubric'].values()))

    def test_run_case_uses_streaming_sse_and_never_requests_nonstream_json(self):
        requests = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def __iter__(self):
                return iter((
                    b'data: {"choices":[{"delta":{"content":"first "}}]}\n\n',
                    b'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n',
                    b'data: [DONE]\n\n',
                ))

        def fake_urlopen(request, timeout):
            requests.append(request)
            self.assertEqual(180, timeout)
            return Response()

        with patch.object(runner, 'urlopen', side_effect=fake_urlopen):
            text, _ = runner.run_case('http://127.0.0.1:11435', {'model': 'local-model'}, {'prompt': 'hello'})

        self.assertEqual('first answer', text)
        self.assertEqual(1, len(requests))
        payload = json.loads(requests[0].data.decode('utf-8'))
        self.assertIs(True, payload['stream'])
        self.assertNotIn(False, [payload['stream']])
        self.assertEqual('text/event-stream', requests[0].get_header('Accept'))
        self.assertEqual('local-quality-probe', requests[0].get_header('X-airi-turn-origin'))


if __name__ == '__main__':
    unittest.main()
