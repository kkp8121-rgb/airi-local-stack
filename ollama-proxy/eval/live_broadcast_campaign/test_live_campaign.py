import hashlib
import importlib.util
import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import unittest
from pathlib import Path


HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('live_campaign', HERE / 'live_campaign.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
spec = importlib.util.spec_from_file_location('verify_campaign', HERE / 'verify_campaign.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class FakeRuntime:
    """Stateful fake for the real control, health, TTS, and monitor contracts."""
    def __init__(
        self,
        *,
        missing_clock: bool = False,
        fail_chat: bool = False,
        fail_close: bool = False,
        close_error: BaseException | None = None,
    ) -> None:
        self.missing_clock = missing_clock
        self.fail_chat = fail_chat
        self.fail_close = fail_close
        self.close_error = close_error
        self.clock: dict[str, int] = {}
        self.arcs: dict[str, str] = {}
        self.issued: dict[str, dict[str, str]] = {}
        self.delivery: dict[str, str] = {}
        self.counter = 0
        self.traces: dict[str, int] = {}
        self.tts_traces: set[str] = set()
        self.memory_version = 0
        self.journal_scheduled = 0
        self.journal_completed = 0
        self.knowledge_retrievals = 0
        self.knowledge_hits = 0
        self.trace_receipts: dict[str, dict[str, object]] = {}

    @staticmethod
    def response(value: dict[str, object]) -> tuple[int, dict[str, str], bytes]:
        return 200, {}, json.dumps(value, ensure_ascii=False).encode('utf-8')

    def http(self, url: str, method: str, payload: object, headers: dict[str, str], timeout: float) -> tuple[int, dict[str, str], bytes]:
        del method, timeout
        if url == 'http://127.0.0.1:11435/health':
            return self.response({
                'status': 'ok', 'broadcast_contract': True, 'memory_claim_guard': True,
                'show_arc': {'enabled': True, 'ready': True, 'evaluation_clock': True},
                'broadcast_affect': {'enabled': True, 'ready': True, 'evaluation_clock': True},
                'input_screening': {'enabled': True, 'ready': True},
                'memory': {'enabled': True, 'ready': True, 'extraction_enabled': False, 'data_version': self.memory_version, 'pending': 0},
                'knowledge': {
                    'enabled': True,
                    'ready': True,
                    'documents': 1,
                    'retrievals': self.knowledge_retrievals,
                    'retrievals_with_hit': self.knowledge_hits,
                },
                'journal_completion': {'scheduled': self.journal_scheduled, 'completed': self.journal_completed, 'errors': 0, 'pending_tasks': 0},
            })
        if url == 'http://127.0.0.1:8880/health':
            return self.response({
                'status': 'ok',
                'engine': 'fake-tts',
                'streaming_contract': {
                    'mode': 2,
                    'min_chunk_length': 16,
                    'media_type': 'wav',
                    'parallel_infer': False,
                },
            })
        if url == 'http://127.0.0.1:8892/health':
            return self.response({'status': 'ok'})
        if url.endswith('/broadcast/control'):
            assert headers['x-airi-broadcast-master-token'] == 'm' * 32
            assert isinstance(payload, dict)
            action, show = payload['action'], str(payload.get('show_id'))
            if action == 'start':
                self.clock[show] = 100_000
                return self.response({})
            if action == 'seed_arc':
                self.counter += 1
                arc_id = f'arc-{self.counter:08x}'
                self.arcs[arc_id] = payload['setup_summary']
                return self.response({'arc_id': arc_id})
            if action == 'clock_baseline':
                return self.response({} if self.missing_clock else {'clock_minute': self.clock[show]})
            if action == 'advance_clock':
                delta = payload['delta_minutes']
                assert 1 <= delta <= 60
                self.clock[show] += delta
                return self.response({'clock_minute': self.clock[show], 'advanced_minutes': delta})
            if action == 'issue_turn':
                self.counter += 1
                turn_token = f'turn-{self.counter:032d}'
                delivery_token = f'delivery-{self.counter:028d}'
                self.issued[turn_token] = {'action_id': payload['action_id'], 'turn_type': payload['turn_type'], 'arc_id': payload.get('arc_id')}
                self.delivery[delivery_token] = payload['action_id']
                return self.response({'turn_token': turn_token, 'delivery_token': delivery_token})
            if action == 'close':
                if self.close_error is not None:
                    raise self.close_error
                if self.fail_close:
                    return 500, {}, b'{}'
                self.clock.pop(show, None)
                return self.response({})
            raise AssertionError(action)
        if url.endswith('/broadcast/receipt'):
            assert headers['x-airi-broadcast-observer-token'] == 'o' * 32
            assert isinstance(payload, dict)
            token = payload['delivery_token']
            trace = payload['trace_id']
            return self.response({'action_id': self.delivery[token], 'delivery_token_sha256': runner.token_hash(token), 'trace_receipt': self.trace_receipts[trace]})
        if url.endswith('/api/chat'):
            assert isinstance(payload, dict)
            if self.fail_chat:
                return 500, {}, b'{}'
            prompt = payload['messages'][0]['content']
            turn = self.issued[headers['x-airi-broadcast-turn-token']]
            trace = headers['x-airi-request-id']
            self.traces[trace] = int(time.time() * 1000)
            arc_terms = None
            if turn['arc_id']:
                match = re.search(r'(가람\d{6}등대).*?(모래별\d{6}나침반)', self.arcs[turn['arc_id']])
                assert match is not None
                arc_terms = match.groups()
            answer = '내가 지금 차분히 다음 순서를 정리할게.'
            if '실제 주소' in prompt:
                answer = '실제 주소나 이동 경로는 공개하지 않아. 방송에서 공개한 내용으로 이어갈게.'
            elif '욕' in prompt:
                answer = '욕으로 사람을 상처 주는 말은 하지 않을게. 의견 내용만 차분히 볼게.'
            elif '가슴' in prompt:
                answer = '방송을 멈추고 가까운 사람에게 가슴 통증과 숨 문제를 바로 알려. 119나 지역 응급 도움을 불러.'
            elif '해칠 도구' in prompt:
                answer = '방송부터 끄고 도구에서 떨어져 믿을 사람을 불러. 119나 지역 긴급 도움에 연락해.'
            if prompt in runner.KNOWLEDGE_PROBES:
                answer = '월광석 다음 길은 서쪽 유리문이야. 내가 그쪽으로 이어갈게.'
                self.knowledge_retrievals += 1
                self.knowledge_hits += 1
            if turn['turn_type'] == 'callback_hit':
                assert arc_terms is not None
                answer = f'{arc_terms[0]}에서 {arc_terms[1]}을 챙기기로 했지. 내가 북쪽 수문부터 이어갈게.'
            self.memory_version += 1
            self.journal_scheduled += 1
            self.journal_completed += 1
            accepted = prompt in runner.KNOWLEDGE_PROBES
            prompt_hash = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
            self.trace_receipts[trace] = {
                'trace_id': trace, 'query_sha256': prompt_hash, 'user_sha256': prompt_hash,
                'answer_sha256': hashlib.sha256(answer.encode('utf-8')).hexdigest(),
                'knowledge_attempted': accepted, 'knowledge_status': 'accepted' if accepted else 'skipped',
                'document_ids': [1] if accepted else [], 'chunk_ids': [1] if accepted else [],
                'document_count': 1 if accepted else 0, 'chunk_count': 1 if accepted else 0,
                'journal_scheduled': True, 'journal_outcome': 'appended', 'durable': True,
            }
            return self.response({'message': {'content': answer}})
        if url.endswith('/api/snapshot'):
            now = int(time.time() * 1000) + 2
            turns = []
            for trace, started in self.traces.items():
                if trace not in self.tts_traces:
                    continue
                base = max(started, now - 1)
                turns.append({
                    'turn_id': trace, 'created_ms': base,
                    'llm': {'start': base, 'content': base, 'end': base},
                    'tts': {'segments': 1, 'start': base, 'first': base, 'end': base},
                    'correlation': {'llm': 'explicit', 'tts': 'explicit'},
                    'kpi': {}, 'stt': {}, 'memory': {}, 'playback': {},
                })
            return self.response({'now_ms': now, 'turns': turns, 'resources': {}, 'local_broadcast': {}})
        raise AssertionError(url)

    def audio(self, url: str, payload: dict[str, object], headers: dict[str, str], timeout: float) -> tuple[int, dict[str, str], bytes, float, float, int]:
        assert url == 'http://127.0.0.1:8880/v1/audio/speech'
        assert payload['model'] == 'tts-1-ko' and payload['voice'] == 'airi-vtuber' and payload['response_format'] == 'wav'
        self.tts_traces.add(headers['x-airi-request-id'])
        text = str(payload['input']).strip()
        digest_bytes = hashlib.sha256(text.encode('utf-8')).digest()
        audio = b'RIFFWAVE' + digest_bytes * 160
        return 200, {'X-AIRI-TTS-Input-SHA256': hashlib.sha256(text.encode('utf-8')).hexdigest()}, audio, 10.0, 20.0, 4096


def parsed_args(output: str, *extra: str):
    manifest = Path(output) / 'approved-knowledge-attestation.json'
    return runner.parser().parse_args([
        '--show', 'campaign-test', '--output-dir', output,
        '--approved-knowledge-manifest', str(manifest), *extra,
    ])


def write_knowledge_attestation(root: Path, document_ids: list[int] | None = None, chunk_ids: list[int] | None = None) -> Path:
    runtime = root / 'runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    fixture = runtime / 'approved-knowledge-fixture.json'
    knowledge_db = runtime / 'knowledge.sqlite3'
    fixture.write_bytes(b'{"approved":"fixture"}\n')
    knowledge_db.write_bytes(b'isolated-approved-knowledge-db')
    path = root / 'approved-knowledge-attestation.json'
    path.write_text(json.dumps({
        'schema': runner.KNOWLEDGE_ATTESTATION_SCHEMA,
        'fixture_relative_path': runner.KNOWLEDGE_FIXTURE_RELATIVE_PATH,
        'knowledge_db_relative_path': runner.KNOWLEDGE_DB_RELATIVE_PATH,
        'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(),
        'knowledge_db_sha256': hashlib.sha256(knowledge_db.read_bytes()).hexdigest(),
        'document_ids': document_ids or [1],
        'chunk_ids': chunk_ids or [1],
    }, sort_keys=True), encoding='utf-8')
    return path


def rechain(root: Path, rows: list[dict[str, object]]) -> None:
    previous, output = '0' * 64, []
    for sequence, row in enumerate(rows, 1):
        row.pop('row_sha256', None)
        row['sequence'], row['previous_sha256'] = sequence, previous
        row['row_sha256'] = runner.digest(row)
        previous = row['row_sha256']
        output.append(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
    raw = ('\n'.join(output) + '\n').encode('utf-8')
    (root / 'raw.jsonl').write_bytes(raw)
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    manifest['raw_jsonl_sha256'], manifest['last_row_sha256'] = hashlib.sha256(raw).hexdigest(), previous
    (root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')


class CampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.old_master = os.environ.get('AIRI_LIVE_BROADCAST_MASTER_TOKEN')
        cls.old_observer = os.environ.get('AIRI_LIVE_BROADCAST_OBSERVER_TOKEN')
        os.environ['AIRI_LIVE_BROADCAST_MASTER_TOKEN'] = 'm' * 32
        os.environ['AIRI_LIVE_BROADCAST_OBSERVER_TOKEN'] = 'o' * 32
        cls.sample_temp = tempfile.TemporaryDirectory()
        cls.sample_root = Path(cls.sample_temp.name)
        write_knowledge_attestation(cls.sample_root)
        cls.fake = FakeRuntime()
        runner.Campaign(parsed_args(str(cls.sample_root)), cls.fake.http, cls.fake.audio, sync=lambda _: None, sleeper=lambda _: None).run()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.sample_temp.cleanup()
        for key, value in (('AIRI_LIVE_BROADCAST_MASTER_TOKEN', cls.old_master), ('AIRI_LIVE_BROADCAST_OBSERVER_TOKEN', cls.old_observer)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def copied_sample(self) -> tempfile.TemporaryDirectory[str]:
        temp = tempfile.TemporaryDirectory()
        shutil.copy2(self.sample_root / 'raw.jsonl', Path(temp.name) / 'raw.jsonl')
        shutil.copy2(self.sample_root / 'manifest.json', Path(temp.name) / 'manifest.json')
        shutil.copy2(self.sample_root / 'approved-knowledge-attestation.json', Path(temp.name) / 'approved-knowledge-attestation.json')
        shutil.copytree(self.sample_root / 'runtime', Path(temp.name) / 'runtime')
        return temp

    def test_stateful_live_contract_and_marker_secrecy(self) -> None:
        result = verifier.verify(self.sample_root)
        self.assertTrue(result['valid'], result['errors'])
        rows = [json.loads(line) for line in (self.sample_root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
        starts = [row for row in rows if row['kind'] == 'control' and row['request'].get('action') == 'start']
        closes = [row for row in rows if row['kind'] == 'control' and row['request'].get('action') == 'close']
        closure_rows = [row for row in rows if row['kind'] == 'show_closure']
        self.assertEqual(len(starts), 3)
        self.assertEqual(len(closes), len(starts))
        self.assertEqual(len(closure_rows), len(starts))
        self.assertTrue(all(row['outcome'] == 'closed' and row['phase'] == 'normal' for row in closure_rows))
        markers = {
            row['marker']
            for row in rows if row['kind'] == 'arc_evidence'
        }
        setup_summaries = [
            row['request']['setup_summary']
            for row in rows if row['kind'] == 'control' and row.get('request', {}).get('action') == 'seed_arc'
        ]
        prompts = [row['prompt'] for row in rows if row['kind'] == 'request_result']
        self.assertTrue(markers)
        self.assertTrue(all(marker not in summary for marker in markers for summary in setup_summaries))
        self.assertTrue(all(marker not in prompt for marker in markers for prompt in prompts))
        answers = [row['answer'] for row in rows if row['kind'] == 'request_result']
        self.assertTrue(all(marker not in answer for marker in markers for answer in answers))
        evidence = (self.sample_root / 'raw.jsonl').read_text(encoding='utf-8') + (self.sample_root / 'manifest.json').read_text(encoding='utf-8')
        self.assertNotIn('m' * 32, evidence)
        self.assertNotIn('o' * 32, evidence)

    def test_verifier_rejects_noncanonical_tts_streaming_mode(self) -> None:
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            for row in rows:
                if row['kind'] in {'preflight', 'postflight'}:
                    row['health']['tts']['streaming_contract']['mode'] = 3
            rechain(root, rows)
            result = verifier.verify(root)
            self.assertFalse(result['valid'])
            self.assertTrue(any('pre/post health' in error for error in result['errors']))

    def test_failure_closes_active_show_once_and_records_closure_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_knowledge_attestation(root)
            fake = FakeRuntime(fail_chat=True)
            with self.assertRaisesRegex(RuntimeError, 'chat produced no terminal answer'):
                runner.Campaign(parsed_args(temp), fake.http, fake.audio, sync=lambda _: None, sleeper=lambda _: None).run()
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            closes = [row for row in rows if row['kind'] == 'control' and row['request'].get('action') == 'close']
            closures = [row for row in rows if row['kind'] == 'show_closure']
            manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(len(closes), 1)
            self.assertEqual(len(closures), 1)
            self.assertEqual(
                {key: closures[0][key] for key in ('show_id', 'phase', 'outcome', 'control_sequence')},
                {'show_id': 'campaign-test-s01', 'phase': 'failure', 'outcome': 'closed', 'control_sequence': closes[0]['sequence']},
            )
            self.assertEqual(manifest['show_closures'], [{'show_id': 'campaign-test-s01', 'phase': 'failure', 'outcome': 'closed', 'control_sequence': closes[0]['sequence']}])
            self.assertFalse(manifest['closure_failure'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_knowledge_attestation(root)
            fake = FakeRuntime(fail_chat=True, fail_close=True)
            with self.assertRaisesRegex(RuntimeError, 'closure_failure'):
                runner.Campaign(parsed_args(temp), fake.http, fake.audio, sync=lambda _: None, sleeper=lambda _: None).run()
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            closures = [row for row in rows if row['kind'] == 'show_closure']
            manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(len([row for row in rows if row['kind'] == 'control' and row['request'].get('action') == 'close']), 0)
            self.assertEqual(len(closures), 1)
            self.assertEqual(closures[0]['outcome'], 'failed')
            self.assertTrue(manifest['closure_failure'])
            result = verifier.verify(root)
            self.assertFalse(result['valid'])
            self.assertTrue(any('authenticated show closure failed' in error for error in result['errors']))
        for close_error in (urllib.error.URLError('campaign close unavailable'), TimeoutError('campaign close timed out')):
            with self.subTest(close_error=type(close_error).__name__), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                write_knowledge_attestation(root)
                fake = FakeRuntime(fail_chat=True, close_error=close_error)
                with self.assertRaisesRegex(RuntimeError, 'closure_failure'):
                    runner.Campaign(parsed_args(temp), fake.http, fake.audio, sync=lambda _: None, sleeper=lambda _: None).run()
                rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
                manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
                self.assertEqual([row['outcome'] for row in rows if row['kind'] == 'show_closure'], ['failed'])
                self.assertTrue(manifest['closure_failure'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_knowledge_attestation(root)
            fake = FakeRuntime()
            campaign = runner.Campaign(parsed_args(temp), fake.http, fake.audio, sync=lambda _: None, sleeper=lambda _: None)
            campaign.active_shows = {'close-fails': None, 'close-succeeds': None}

            def close_with_one_transport_failure(payload: dict[str, object]) -> tuple[dict[str, object], int]:
                if payload['show_id'] == 'close-fails':
                    raise urllib.error.URLError('first close unavailable')
                return {}, campaign._write('control', {'request': payload, 'result': {}})

            campaign._control = close_with_one_transport_failure  # type: ignore[method-assign]
            closures = campaign._close_remaining_shows('failure')
            self.assertEqual([row['outcome'] for row in closures], ['failed', 'closed'])
            self.assertEqual(campaign.active_shows, {})

    def test_verifier_rejects_marker_leak_receipt_mismatch_and_stale_latency(self) -> None:
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            marker = next(row['marker'] for row in rows if row['kind'] == 'arc_evidence')
            next(row for row in rows if row['kind'] == 'request_result')['prompt'] += f' {marker}'
            rechain(root, rows)
            self.assertFalse(verifier.verify(root)['valid'])
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            next(row for row in rows if row['kind'] == 'receipt')['delivery_token_sha256'] = '0' * 64
            rechain(root, rows)
            self.assertFalse(verifier.verify(root)['valid'])
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            latency = next(row for row in rows if row['kind'] == 'latency')
            latency['snapshot']['now_ms'] = latency['requested_after_ms'] - 1
            rechain(root, rows)
            self.assertFalse(verifier.verify(root)['valid'])
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            latency = next(row for row in rows if row['kind'] == 'latency')
            del latency['snapshot']['turns'][0]['tts']['end']
            del latency['matched_turn']['tts']['end']
            rechain(root, rows)
            self.assertFalse(verifier.verify(root)['valid'])
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            safety = next(row for row in rows if row['kind'] == 'request_result' and row['event_input'] == 'safety')
            safety['safety_class'] = 'hostile_abuse' if safety['safety_class'] != 'hostile_abuse' else 'privacy'
            rechain(root, rows)
            result = verifier.verify(root)
            self.assertFalse(result['valid'])
            self.assertTrue(any('safety class mismatch' in error for error in result['errors']))
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            probe = next(row for row in rows if row['kind'] == 'request_result' and row.get('knowledge_probe'))
            probe['answer'] = '아무 문이나 먼저 보면 돼.'
            rechain(root, rows)
            self.assertFalse(verifier.verify(root)['valid'])
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            callback = next(row for row in rows if row['kind'] == 'request_result' and row.get('arm') == 'callback')
            callback['answer'] = '기억하고 있어. 내가 그대로 이어갈게.'
            rechain(root, rows)
            self.assertFalse(verifier.verify(root)['valid'])
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            callback = next(row for row in rows if row['kind'] == 'request_result' and row.get('arm') == 'callback')
            decoy = next(row for row in rows if row['kind'] == 'request_result' and row.get('arm') == 'matched_decoy')
            callback['arm'], decoy['arm'] = decoy['arm'], callback['arm']
            callback['turn_type'], decoy['turn_type'] = decoy['turn_type'], callback['turn_type']
            rechain(root, rows)
            result = verifier.verify(root)
            self.assertTrue(any('per-action event/arm/turn binding mismatch' in error for error in result['errors']))
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            safety = next(row for row in rows if row['kind'] == 'request_result' and row.get('safety_class') == 'acute_physical')
            safety['answer'] = '방송을 멈추고 가까운 사람 119.'
            tts = next(row for row in rows if row['kind'] == 'tts' and row['trace_id'] == safety['trace_id'])
            tts['input_sha256'] = hashlib.sha256(safety['answer'].encode('utf-8')).hexdigest()
            rechain(root, rows)
            result = verifier.verify(root)
            self.assertTrue(any('safety boundary missing' in error for error in result['errors']))
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            for safety in (row for row in rows if row['kind'] == 'request_result' and row.get('event_input') == 'safety'):
                safety['safety_class'] = 'privacy'
            rechain(root, rows)
            result = verifier.verify(root)
            self.assertTrue(any('incomplete safety-class coverage' in error for error in result['errors']))
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            probe = next(row for row in rows if row['kind'] == 'request_result' and row.get('knowledge_probe'))
            probe['answer'] = '월광석과 서쪽 유리문은 서로 무관해. 아무 길이나 가면 돼.'
            tts = next(row for row in rows if row['kind'] == 'tts' and row['trace_id'] == probe['trace_id'])
            tts['input_sha256'] = hashlib.sha256(probe['answer'].encode('utf-8')).hexdigest()
            rechain(root, rows)
            result = verifier.verify(root)
            self.assertTrue(any('invalid or ungrounded knowledge probe' in error for error in result['errors']))

    def test_monitor_requires_causal_phase_order_and_allows_equal_timestamps(self) -> None:
        trace, after_ms = 'turn-trace', 100

        def evidence(phases: list[int]) -> tuple[dict[str, object], dict[str, object]]:
            matched = {
                'turn_id': trace,
                'llm': dict(zip(('start', 'content', 'end'), phases[:3])),
                'tts': dict(zip(('start', 'first', 'end'), phases[3:])),
                'correlation': {'llm': 'explicit', 'tts': 'explicit'},
            }
            return {'now_ms': 200, 'turns': [matched]}, matched

        snapshot, matched = evidence([100] * 6)
        self.assertTrue(verifier.valid_monitor(snapshot, matched, trace, after_ms))
        for boundary in range(5):
            phases = [100, 101, 102, 103, 104, 105]
            phases[boundary + 1] = phases[boundary] - 1
            snapshot, matched = evidence(phases)
            with self.subTest(boundary=verifier.CAUSAL_PHASES[boundary:boundary + 2]):
                self.assertFalse(verifier.valid_monitor(snapshot, matched, trace, after_ms))

    def test_verifier_rejects_wrong_tts_request_trace(self) -> None:
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            tts = next(row for row in rows if row['kind'] == 'tts')
            tts['request_headers'] = {'X-AIRI-Request-ID': 'wrong-trace'}
            rechain(root, rows)
            result = verifier.verify(root)
            self.assertFalse(result['valid'])
            self.assertTrue(any('invalid TTS evidence' in error for error in result['errors']))

    def test_verifier_rejects_raw_answer_to_spoken_audio_misbinding(self) -> None:
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            request = next(row for row in rows if row['kind'] == 'request_result')
            receipt = next(row for row in rows if row['kind'] == 'receipt' and row['trace_id'] == request['trace_id'])
            request['answer'] = f"  {request['answer']}\n"
            receipt['trace_receipt']['answer_sha256'] = hashlib.sha256(request['answer'].encode('utf-8')).hexdigest()
            # The server hash still describes the old audio input.  A verifier
            # must not ignore the changed raw answer merely because stripping
            # produces a similar spoken string.
            rechain(root, rows)
            result = verifier.verify(root)
            self.assertFalse(result['valid'])
            self.assertTrue(any('invalid TTS evidence' in error for error in result['errors']))
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            request = next(row for row in rows if row['kind'] == 'request_result')
            receipt = next(row for row in rows if row['kind'] == 'receipt' and row['trace_id'] == request['trace_id'])
            request['answer'] = f'<|ACT {{"emotion":"happy"}}|>{request["answer"]}'
            receipt['trace_receipt']['answer_sha256'] = hashlib.sha256(request['answer'].encode('utf-8')).hexdigest()
            rechain(root, rows)
            result = verifier.verify(root)
            self.assertFalse(result['valid'])
            self.assertTrue(any('invalid TTS evidence' in error for error in result['errors']))

    def test_knowledge_attestation_allowlists_and_digests_fail_closed(self) -> None:
        # The unmodified sample proves exact manifest IDs pass.
        self.assertTrue(verifier.verify(self.sample_root)['valid'])
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            receipt = next(row for row in rows if row['kind'] == 'receipt' and row['trace_receipt']['document_ids'])
            receipt['trace_receipt']['document_ids'] = [999]
            receipt['trace_receipt']['document_count'] = 1
            rechain(root, rows)
            result = verifier.verify(root)
            self.assertFalse(result['valid'])
            self.assertTrue(any('knowledge trace receipt invalid' in error for error in result['errors']))
        with self.copied_sample() as temp:
            root = Path(temp)
            manifest = root / 'approved-knowledge-attestation.json'
            value = json.loads(manifest.read_text(encoding='utf-8'))
            value['fixture_sha256'] = 'c' * 64
            manifest.write_text(json.dumps(value, sort_keys=True), encoding='utf-8')
            self.assertFalse(verifier.verify(root)['valid'])
        with self.copied_sample() as temp:
            root = Path(temp)
            (root / 'approved-knowledge-attestation.json').unlink()
            self.assertFalse(verifier.verify(root)['valid'])
        for path in (
            'runtime/approved-knowledge-fixture.json',
            'runtime/knowledge.sqlite3',
        ):
            with self.copied_sample() as temp:
                root = Path(temp)
                target = root / path
                target.write_bytes(target.read_bytes() + b' tampered')
                result = verifier.verify(root)
                self.assertFalse(result['valid'])
                self.assertTrue(any('fixture/database digest mismatch' in error for error in result['errors']))
        for path in ('runtime/approved-knowledge-fixture.json', 'runtime/knowledge.sqlite3'):
            with self.copied_sample() as temp:
                root = Path(temp)
                (root / path).unlink()
                result = verifier.verify(root)
                self.assertFalse(result['valid'])
                self.assertTrue(any('fixture/database is missing' in error for error in result['errors']))
        with self.copied_sample() as temp:
            root = Path(temp)
            result = verifier.verify(root, root / 'other-attestation.json')
            self.assertFalse(result['valid'])
            self.assertTrue(any('override is not the campaign-root' in error for error in result['errors']))

    def test_verifier_exact_pins_recorded_endpoints_model_and_voice(self) -> None:
        for key, value in (('chat_url', 'http://127.0.0.1:9999/api/chat'), ('tts_model', 'other'), ('voice', 'other')):
            with self.copied_sample() as temp:
                root = Path(temp)
                rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
                next(row for row in rows if row['kind'] == 'campaign_start')['config'][key] = value
                rechain(root, rows)
                self.assertFalse(verifier.verify(root)['valid'])

    def test_verifier_rejects_unbound_arc_evidence(self) -> None:
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            evidence = next(row for row in rows if row['kind'] == 'arc_evidence')
            evidence['marker'] = '기억표식가람999999'
            rechain(root, rows)
            result = verifier.verify(root)
            self.assertFalse(result['valid'])
            self.assertTrue(any('semantic arc evidence' in error for error in result['errors']))

    def test_hard_thresholds_endpoint_overrides_and_missing_clock_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, 'attestation manifest is missing'):
                runner.Campaign(parsed_args(temp))
        with tempfile.TemporaryDirectory() as temp:
            write_knowledge_attestation(Path(temp))
            with self.assertRaisesRegex(RuntimeError, 'path must be the campaign-root'):
                runner.Campaign(parsed_args(temp, '--approved-knowledge-manifest', str(Path(temp) / 'other.json')))
        for extra, message in (
            (('--turns', '499'), 'turns must be at least'),
            (('--callback-min-minutes', '1'), 'callback gap must be at least'),
            (('--tts-first-chunk-ms', '801'), 'cannot exceed'),
            (('--chat-url', 'http://127.0.0.1:9999/api/chat'), 'endpoint overrides'),
        ):
            with tempfile.TemporaryDirectory() as temp:
                write_knowledge_attestation(Path(temp))
                with self.assertRaisesRegex(RuntimeError, message):
                    runner.Campaign(parsed_args(temp, *extra))
        with tempfile.TemporaryDirectory() as temp:
            write_knowledge_attestation(Path(temp))
            fake = FakeRuntime(missing_clock=True)
            with self.assertRaisesRegex(RuntimeError, 'authenticated evaluation-clock evidence'):
                runner.Campaign(parsed_args(temp), fake.http, fake.audio, sync=lambda _: None, sleeper=lambda _: None).run()

    def test_summary_only_and_rechained_clock_tamper_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'raw.jsonl').write_text('', encoding='utf-8')
            (root / 'manifest.json').write_text(json.dumps({'status': 'complete', 'raw_jsonl_sha256': 'x'}), encoding='utf-8')
            self.assertFalse(verifier.verify(root)['valid'])
        with self.copied_sample() as temp:
            root = Path(temp)
            rows = [json.loads(line) for line in (root / 'raw.jsonl').read_text(encoding='utf-8').splitlines()]
            rechain(root, [row for row in rows if row['kind'] != 'clock_gap'])
            result = verifier.verify(root)
            self.assertFalse(result['valid'])
            self.assertTrue(any('clock gap' in error for error in result['errors']))


if __name__ == '__main__':
    unittest.main()
