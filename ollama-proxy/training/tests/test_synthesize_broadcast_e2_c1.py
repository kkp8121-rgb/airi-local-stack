import copy
import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('e2_c1', HERE / 'synthesize_broadcast_e2_c1.py')
builder = importlib.util.module_from_spec(spec); assert spec and spec.loader
sys.modules[spec.name] = builder; spec.loader.exec_module(builder)


class E2C1BuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = builder.build_all()
        cls.correction = [json.loads(x) for x in cls.rendered['correction'].splitlines()]
        cls.mixture = [json.loads(x) for x in cls.rendered['mixture'].splitlines()]
        cls.v4 = builder._read_jsonl(builder.V4_SOURCE)
        cls.replay = [x for x in cls.mixture if not x['id'].startswith('e2c1-')]

    def test_exact_counts_groups_and_ratio(self):
        self.assertEqual(len(self.correction), 480)
        self.assertEqual(len(self.mixture), 680)
        self.assertEqual(builder.Counter(x['split'] for x in self.mixture), {'train': 512, 'dev': 84, 'test': 84})
        self.assertEqual(builder.Counter(x['semantic_family'] for x in self.correction), {name: spec[0] for name, spec in builder.CORRECTION.items()})
        builder.validate_correction(self.correction); builder.validate_mixture(self.correction, self.replay)

    def test_natural_correction_diversity_and_markers(self):
        forbidden = ('correction=', 'view=', '근거-', '혼동-', 'e2c1-', '이번에는')
        self.assertFalse(any(token in message['content'] for row in self.correction for message in row['messages'] for token in forbidden))
        visible = '\n'.join(message['content'] for row in self.correction for message in row['messages'])
        self.assertNotRegex(visible, r'(이름|지난 이야기|새 댓글|방송 소재) (메모|소문) \d+')
        self.assertNotRegex(visible, r'(별빛손님|달빛모서리|노을책장|초록찻잔)\d+')
        groups = builder._groups(self.correction)
        self.assertTrue(all(len({row['messages'][-2]['content'] for row in group}) == 4 and len({row['target'] for row in group}) == 4 for group in groups.values()))
        for family in builder.CORRECTION:
            rows = [row for row in self.correction if row['semantic_family'] == family]
            self.assertGreaterEqual(len({builder._skeleton(row['messages'][-2]['content']) for row in rows}), 8)
            self.assertGreaterEqual(len({builder._skeleton(row['target']) for row in rows}), 8)
        self.assertTrue(all('분 전' in row['messages'][-2]['content'] and row['fact_tokens'][0] in row['target'] for row in self.correction if row['semantic_family'] == 'long_callback'))
        self.assertTrue(all(row['required_token'] in row['target'] and row['fact_tokens'] == [row['required_token']]
                            for row in self.correction if row['semantic_family'] in ('identity_noninvention', 'unknown_identity')))
        self.assertTrue(all(f"{row['required_token']}님" in row['target'] and '고마워' in row['target'] and all(token in row['target'] for token in [*row['fact_tokens'], *row['updated_tokens']]) for row in self.correction if row['semantic_family'] == 'donation_ritual'))
        self.assertTrue(all(not any(token in row['target'] for token in row['decoy_tokens']) for row in self.correction if row['semantic_family'] == 'factual_grounding'))
        self.assertTrue(all('|' not in row['target'] and all(token in row['target'] for token in row['fact_tokens']) for row in self.correction if row['semantic_family'] == 'complete_show_arc'))
        self.assertTrue(all(all(token in row['target'] for token in [*row['fact_tokens'], *row['updated_tokens']]) for row in self.correction if row['semantic_family'] in ('long_callback', 'stale_transition')))
        self.assertTrue(all(row['required_token'] in row['target'] and row['fact_tokens'] == [row['required_token']]
                            for row in self.correction if row['semantic_family'] == 'safety_regression'))
        self.assertFalse(any(builder.re.search(r'(요|습니다|세요|죠)(?:[.!?]|$)', row['target']) for row in self.correction))

    def test_korean_particle_and_collocation_contract(self):
        self.assertEqual(builder._quoted_josa('간식', '은', '는'), '“간식”은')
        self.assertEqual(builder._quoted_josa('간식', '을', '를'), '“간식”을')
        self.assertEqual(builder._quoted_josa('간식', '과', '와'), '“간식”과')
        self.assertEqual(builder._quoted_josa('접기', '은', '는'), '“접기”는')
        self.assertEqual(builder._quoted_josa('접기', '을', '를'), '“접기”를')
        self.assertEqual(builder._quoted_josa('접기', '과', '와'), '“접기”와')
        self.assertEqual(builder._quoted_josa('뭐가 좋아?', '이라면', '라면'), '“뭐가 좋아?”라면')
        visible = '\n'.join(message['content'] for row in self.correction for message in row['messages'])
        self.assertEqual(builder._quoted_josa_mismatches(visible), [])
        for pattern in (
            r'“[^”]*적혀 있어”라고 적혀 있어',
            r'처음 꺼낸 “[^”]+”[이가] “[^”]+”까지 이어졌어',
            r'“[^”]+”에서 출발해 “[^”]+”까지 모았어',
            r'”(?:야|였)', r'\?\.', r'\.\.', r'구름(?:를|가)',
            r'주제는 .* 제목을 붙여 줘야',
        ):
            self.assertNotRegex(visible, pattern)

    def test_replay_quota_and_object_equality(self):
        builder.validate_replay(self.replay, self.v4)
        self.assertEqual(builder.Counter(x['semantic_family'] for x in self.replay if x['split'] == 'train'), builder.REPLAY_TRAIN)
        original = {x['id']: x for x in self.v4}
        self.assertTrue(all(x == original[x['id']] for x in self.replay))

    def test_regeneration_and_check_bytes(self):
        self.assertEqual(self.rendered, builder.build_all())
        self.assertEqual(hashlib.sha256(self.rendered['correction'].encode()).hexdigest(), hashlib.sha256(builder._jsonl(self.correction).encode()).hexdigest())
        manifest = json.loads(self.rendered['dataset_manifest'])
        self.assertEqual(manifest['training_contract']['candidate'], 'E2-C1')
        self.assertEqual(manifest['training_contract']['init_mode'], 'adapter-weights-only')
        self.assertEqual(manifest['training_contract']['max_optimizer_steps'], 32)
        self.assertEqual(set(manifest['files']), {'correction', 'correction_chat', 'mixture', 'mixture_chat', 'replay', 'replay_manifest'})
        self.assertEqual(manifest['training_input'], {
            'path': builder.OUTPUTS['mixture_chat'].name, **manifest['files']['mixture_chat']})
        self.assertEqual(manifest['files']['replay_manifest'], {
            'size': len(self.rendered['replay_manifest'].encode()),
            'sha256': hashlib.sha256(self.rendered['replay_manifest'].encode()).hexdigest()})
        for name, content in self.rendered.items():
            self.assertEqual(builder.OUTPUTS[name].read_bytes(), content.encode())
        self.assertEqual(builder.main(['--check']), 0)

    def test_tamper_and_collision_fail_closed(self):
        tampered = copy.deepcopy(self.correction); tampered[0]['target'] = tampered[1]['target']; tampered[0]['messages'][-1]['content'] = tampered[0]['target']
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            builder.validate_correction(tampered)
        replay = copy.deepcopy(self.replay); replay[0]['target'] += ' 변경'
        with self.assertRaisesRegex(ValueError, 'equality'):
            builder.validate_replay(replay, self.v4)
        leaked = copy.deepcopy(self.correction)
        source = next(row for row in leaked if row['split'] == 'test' and row['fact_tokens'])
        destination = next(row for row in leaked if row['split'] == 'train')
        destination['decoy_tokens'] = [source['fact_tokens'][0]]
        with self.assertRaisesRegex(ValueError, 'leakage'):
            builder.validate_correction(leaked)
        with self.assertRaisesRegex(ValueError, 'public fixture literal'):
            builder.validate_correction(self.correction, public_fixture_literals=['자연스러운 한국어 방송 반말'])


if __name__ == '__main__':
    unittest.main()
