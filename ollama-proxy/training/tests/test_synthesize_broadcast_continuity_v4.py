from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[1]

def load():
    spec = importlib.util.spec_from_file_location('broadcast_continuity_v4', HERE / 'synthesize_broadcast_continuity_v4.py')
    module = importlib.util.module_from_spec(spec); assert spec and spec.loader
    sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return module

builder = load()

EXPECTED_SOURCE_SHA256 = '43f9c1ed1abf1d32c94329de81d8ba9ddef93f560ef914814d34e0520eeba2ed'
EXPECTED_CHAT_SHA256 = '96cc223ca5915355394480b60b459d9d039ffad4b47304974c5d939d4686eb44'

def fake_fixture(root: Path) -> Path:
    names = ['one.json', 'two.json', 'three.json']
    fixtures = []
    for index, name in enumerate(names, 1):
        path = root / name
        path.write_text('{}', encoding='utf-8')
        raw = path.read_bytes()
        canonical = json.dumps(json.loads(raw.decode()), ensure_ascii=False, sort_keys=True,
                               separators=(',', ':')).encode()
        fixtures.append({'filename': name, 'creation_order': index,
                         'role': 'final_blind' if index == 3 else 'calibration_regression',
                         'raw_sha256': __import__('hashlib').sha256(raw).hexdigest(),
                         'canonical_sha256': __import__('hashlib').sha256(canonical).hexdigest()})
    manifest = root / 't3_fixture_manifest_v2.json'
    manifest.write_text(json.dumps({'fixtures': fixtures}), encoding='utf-8')
    return root

def refresh_fixture_manifest(root: Path) -> None:
    manifest = root / 't3_fixture_manifest_v2.json'
    data = json.loads(manifest.read_text(encoding='utf-8'))
    for item in data['fixtures']:
        path = root / item['filename']; raw = path.read_bytes()
        canonical = json.dumps(json.loads(raw.decode()), ensure_ascii=False, sort_keys=True,
                               separators=(',', ':')).encode()
        item['raw_sha256'] = __import__('hashlib').sha256(raw).hexdigest()
        item['canonical_sha256'] = __import__('hashlib').sha256(canonical).hexdigest()
    manifest.write_text(json.dumps(data), encoding='utf-8')

def card(family: str, number: int, split: str, views: int) -> dict:
    token = f'증거{family}{number}'
    unknown = family == 'memory_unknown'
    result_views = []
    for index in range(views):
        coherent_family = family in ('memory_known', 'briefing_topic',
                                     'donation_isolation', 'grounding')
        required = None if unknown or family == 'natural_broadcast' else (
            token if coherent_family else f'{token}_{index}')
        surface = f'근거 내용 {required}' if required else f'알 수 없는 빈 근거 {number} {index}'
        memory_family = family in ('memory_known', 'memory_unknown')
        memory_ids = ('memory', 'journal', 'briefing', 'distracted')
        memory_surfaces = ('character_memory', 'delayed_journal',
                           'authenticated_briefing', 'distracted_memory')
        view_id = memory_ids[index] if memory_family else f'view-{index}'
        evidence_surface = memory_surfaces[index] if memory_family else surface
        evidence = (f'이 시청자가 전에 {required}라고 말했다.' if required
                    else f'다른 시청자가 미끼{number}_{index}라고 말했다.')
        memory_block = evidence if memory_family and index in (0, 3) else (f'memory only {required}' if required and not memory_family else '')
        briefing_lines = [evidence] if memory_family and index == 2 else []
        journal_messages = ([{'role': 'user', 'content': evidence}]
                            if memory_family and index == 1 else [])
        target = (f'그 부분은 아직 단서가 부족해서 단정하지 않을게. 다음 흐름을 더 살펴볼게 {number} {index}.' if unknown
                  else (f'지금 말은 바로 받아들였어. 한 가지 판단과 구체적인 반응을 더 붙여 방송 대화를 자연스럽고 충분한 길이로 이어갈게 {number} {index}.' if family == 'natural_broadcast'
                        else (f'네가 말한 답은 {required}였지. 다음 선택도 그 흐름에서 살펴보면 되겠어 {number} {index}.' if memory_family
                              else f'{required} 쪽이 지금 이야기의 핵심으로 보여. 다음 선택도 그 흐름에서 살펴볼게 {number} {index}.')))
        if index == 0:
            target = target[:-1] + '?'
        result_views.append({'view_id': view_id, 'category': f'{family}-{index}', 'evidence_surface': evidence_surface,
            'affect_outcome': {'evidence': 'screened_chat', 'outcome': 'chat_question'}, 'history': [],
            'briefing_lines': briefing_lines, 'memory_block': memory_block,
            'journal_messages': journal_messages,
            'current_user': (f'내가 전에 말한 답이 뭐였지 {number} {index}' if memory_family else f'지금은 어떻게 볼까 {number} {index}'), 'target': target, 'required_token': required,
            'updated_token': None, 'decoy_tokens': [f'미끼{number}_{index}'], 'forbidden_tokens': [f'금지{number}_{index}'],
            'roster_handles': [f'별명{number}_{index}'], 'donation_continuation': family == 'donation_isolation'})
    return {'schema': builder.CARD_SCHEMA, 'group_id': f'{family}-{number}', 'split': split, 'family': family,
            'topic_title': f'고유주제{family}{number}', 'segment_label': '정리 구간', 'situation': '대화 정리 중', 'views': result_views}

def cards():
    result = []
    for family, (count, per_group, allocation) in builder.FAMILIES.items():
        n = 0
        for split, amount in zip(builder.SPLITS, allocation):
            for _ in range(amount): result.append(card(family, n, split, per_group)); n += 1
    return result

class BroadcastContinuityV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = cards()
        cls.temp = tempfile.TemporaryDirectory(); cls.root = fake_fixture(Path(cls.temp.name))
        # The compact fixture deliberately repeats prose; corpus-style gates
        # are covered separately with a focused negative below.
        with mock.patch.object(builder, '_validate_corpus_style'):
            cls.rows = builder.build_records(cls.cards, fixture_root=cls.root)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_exhaustive_quotas_splits_and_group_isolation(self):
        self.assertEqual(len(self.rows), 1000)
        self.assertEqual(Counter(x['split'] for x in self.rows), {'train': 800, 'dev': 100, 'test': 100})
        self.assertEqual(Counter(x['semantic_family'] for x in self.rows), {key: count * per for key, (count, per, _) in builder.FAMILIES.items()})
        self.assertEqual(sum(x['semantic_family'] == 'memory_known' for x in self.rows), 4 * sum(x['semantic_family'] == 'memory_unknown' for x in self.rows))
        parts = {path.stem.removeprefix('airi_broadcast_continuity_v4_cards_')
                 for path in builder.CARD_PATHS}
        self.assertEqual(set(builder.PARTITION_CONTRACTS), parts)

    def test_native_runtime_shape_and_real_seams(self):
        row = self.rows[0]
        self.assertEqual(row['schema_version'], builder.SCHEMA_VERSION)
        self.assertEqual(row['review'], builder.REVIEW)
        self.assertEqual(row['messages'][-1]['role'], 'assistant')
        self.assertTrue(all(set(x) == {'role', 'content'} for x in row['messages']))
        self.assertEqual(row['messages'][-2]['role'], 'user')
        self.assertTrue(row['messages'][-2]['content'].startswith('[YouTube] '))

    def test_closed_schema_and_missing_card_files_fail(self):
        broken = copy.deepcopy(self.cards[0]); broken['extra'] = True
        with self.assertRaisesRegex(ValueError, 'closed card'): builder.validate_card(broken)
        placeholder = copy.deepcopy(self.cards[0]); placeholder['views'][0]['target'] = '별빛은(는) 답이야.'
        with self.assertRaisesRegex(ValueError, 'placeholder or meta'): builder.validate_card(placeholder)
        awkward_owner = copy.deepcopy(self.cards[0]); awkward_owner['views'][0]['memory_block'] = '시청자 네가 전에 이 사실을 말했다.'
        with self.assertRaisesRegex(ValueError, 'placeholder or meta'): builder.validate_card(awkward_owner)
        affect = copy.deepcopy(self.cards[0]); affect['views'][0]['affect_outcome']['evidence'] = '설명문'
        with self.assertRaisesRegex(ValueError, 'affect outcome'): builder.validate_card(affect)
        with self.assertRaisesRegex(ValueError, 'partitioned'): builder.load_cards([Path('missing')] * len(builder.CARD_PATHS))

    def test_hard_gates_fail_closed(self):
        duplicate = copy.deepcopy(self.rows); duplicate[-1]['target'] = duplicate[-2]['target']
        with self.assertRaisesRegex(ValueError, 'duplicate'): builder.validate_records(duplicate, fixture_root=self.root)
        leak = copy.deepcopy(self.rows); leak[0]['target'] = leak[0]['target'][:-1] + ' ' + leak[0]['required_token'] + '.'
        with self.assertRaisesRegex(ValueError, 'duplicate|required token'): builder._validate_target(leak[0])
        donation = next(x for x in self.rows if x['semantic_family'] == 'donation_isolation')
        donation['target'] = f"{donation['required_token']} 고마워. 지금 메시지의 내용만 이어서 차분하게 살펴보고, 방송 주제에서 중요한 판단도 하나 더 붙일게."
        with self.assertRaisesRegex(ValueError, 'donation'): builder._validate_target(donation)
        donation_owner = copy.deepcopy(next(
            x for x in self.rows if x['semantic_family'] == 'donation_isolation'
        ))
        donation_owner['_view']['current_user'] = '내가 앞에서 고른 이름이 뭐였지?'
        donation_owner['_view']['memory_block'] = (
            f"시청자가 {donation_owner['required_token']}을 골랐다고 말했다."
        )
        donation_owner['_view']['briefing_lines'] = []
        donation_owner['_view']['journal_messages'] = []
        donation_owner['target'] = (
            f"답은 {donation_owner['required_token']}이야. "
            '앞에서 나온 선택과 이어지는 이름이라 지금 흐름에도 자연스럽게 붙어.'
        )
        with self.assertRaisesRegex(ValueError, 'viewer memory binding'):
            builder._validate_target(donation_owner)
        polite = copy.deepcopy(next(x for x in self.rows if x['semantic_family'] == 'briefing_topic'))
        polite['target'] = f"정답은 {polite['required_token']}이에요. 지금 흐름에서도 그 기준으로 이어가면 됩니다."
        with self.assertRaisesRegex(ValueError, 'target register'):
            builder._validate_target(polite)
        shallow = copy.deepcopy(next(x for x in self.rows if x['semantic_family'] == 'briefing_topic'))
        shallow['_view']['current_user'] = '길' * 60
        shallow['target'] = f"{shallow['required_token']}이 정답이야. 지금 흐름을 그 기준으로 차분하게 이어갈게."
        with self.assertRaisesRegex(ValueError, 'short-input response depth'):
            builder._validate_target(shallow)
        ungrounded = copy.deepcopy(next(
            x for x in self.rows if x['semantic_family'] == 'grounding'
        ))
        ungrounded['required_token'] = None
        ungrounded['fact_tokens'] = []
        ungrounded['_view']['required_token'] = None
        ungrounded['_view']['decoy_tokens'] = []
        ungrounded['decoy_tokens'] = []
        ungrounded['target'] = (
            '지금 보이는 정보만으로 우승자를 단정할게. '
            '결과 화면은 없어도 분위기만 보고 충분히 맞힐 수 있어.'
        )
        with self.assertRaisesRegex(ValueError, 'ungrounded grounding certainty'):
            builder._validate_target(ungrounded)
        false_action = copy.deepcopy(next(
            x for x in self.rows if x['semantic_family'] == 'briefing_topic'
        ))
        false_action['target'] = (
            f"정답은 {false_action['required_token']}야. "
            '내가 네 계정에 저장해 둘게, 다음에 물으면 방송 밖에서도 바로 꺼내 줄 수 있어.'
        )
        with self.assertRaisesRegex(ValueError, 'unsafe target'):
            builder._validate_target(false_action)
        owned = copy.deepcopy(next(x for x in self.rows if x['semantic_family'] == 'memory_known'))
        owned['_view']['current_user'] = '내가 전에 말한 답이 뭐였지?'
        owned['_view']['memory_block'] = f"이 시청자가 전에 {owned['required_token']}라고 말했다."
        owned['target'] = f"네가 말한 답은 {owned['required_token']}였지. 그 얘기부터 자연스럽게 이어가면 되겠다."
        builder._validate_target(owned)
        owned['target'] = f"내가 말한 답은 {owned['required_token']}였지. 그 얘기부터 자연스럽게 이어가면 되겠다."
        with self.assertRaisesRegex(ValueError, 'self-claim|binding'):
            builder._validate_target(owned)
        memory_card = copy.deepcopy(next(card for card in self.cards if card['family'] == 'memory_known'))
        memory_card['views'][1]['view_id'] = 'memory'
        with self.assertRaisesRegex(ValueError, 'memory surface coverage'):
            builder.validate_card(memory_card)
        memory_card = copy.deepcopy(next(card for card in self.cards if card['family'] == 'memory_known'))
        misplaced = memory_card['views'][1]
        misplaced['memory_block'] = f"잘못된 메모리 위치에 {misplaced['required_token']} 증거가 있다."
        misplaced['journal_messages'][0]['content'] = '저널에는 관련 없는 다른 정보만 있다.'
        with self.assertRaisesRegex(ValueError, 'memory evidence topology'):
            builder.validate_card(memory_card)
        incoherent = copy.deepcopy(next(card for card in self.cards if card['family'] == 'briefing_topic'))
        incoherent['views'][1]['required_token'] = '서로 다른 사실'
        with self.assertRaisesRegex(ValueError, 'scenario fact coherence'):
            builder.validate_card(incoherent)
        with self.assertRaisesRegex(ValueError, 'cross-group fact token reuse'):
            builder._validate_fact_group_isolation([
                {'scenario_group': 'first', 'required_token': '같은 사실'},
                {'scenario_group': 'second', 'required_token': '같은 사실'},
            ])
        for token, target in (
            ('토마토', '토마토을 골랐어.'),
            ('물뿌리개', '물뿌리개이 있어.'),
            ('레몬차', '레몬차과 함께해.'),
        ):
            with self.assertRaisesRegex(ValueError, 'required token josa'):
                builder._validate_required_josa(token, target)
        builder._validate_required_josa('토마토', '토마토를 골랐어.')
        builder._validate_required_josa('바질', '바질이 필요해.')

    def test_fixture_contamination_fails_closed(self):
        structural = {
            'kind': 'donation',
            'expected_source': 'history',
            'pickup_priority': ['briefing'],
            'prompt': '실제로 비교해야 할 고유한 방송 문장',
        }
        self.assertEqual(
            builder._fixture_content_leaves(structural),
            ['실제로 비교해야 할 고유한 방송 문장'],
        )
        (self.root / 'one.json').write_text(json.dumps({'probe': self.cards[0]['topic_title']}), encoding='utf-8')
        refresh_fixture_manifest(self.root)
        with mock.patch.object(builder, '_validate_corpus_style'):
            with self.assertRaisesRegex(ValueError, 'contamination'): builder.validate_records(self.rows, fixture_root=self.root)
        (self.root / 'one.json').write_text('{}', encoding='utf-8')
        refresh_fixture_manifest(self.root)

    def test_template_spam_fails_closed(self):
        repeated = copy.deepcopy(self.rows[:9])
        for row in repeated:
            row['target'] = '같은 말을 그대로 반복하는 기계 문장이라 방송 흐름이 전혀 살아나지 않아.'
        with self.assertRaisesRegex(ValueError, 'repeated ngram or skeleton'):
            builder._validate_corpus_style(repeated)
        slotted = []
        for index in range(3):
            slotted.append({
                'target': f'주제{index} 얘기는 말이 많지 않아도 기분을 천천히 바꿔 줘. 오늘은 남은 장면부터 이어 가자.',
                'required_token': None,
                'fact_tokens': [], 'updated_tokens': [], 'decoy_tokens': [],
                '_view': {'roster_handles': []},
                '_card': {'topic_title': f'주제{index}', 'segment_label': f'구간{index}'},
            })
        with self.assertRaisesRegex(ValueError, 'repeated ngram or skeleton'):
            builder._validate_corpus_style(slotted)

        decorative = [
            {
                'semantic_family': 'memory_known',
                'target': f'답은 표식{i}야. 화면에 작은 조명이 떠오르는 느낌이야.',
            }
            for i in range(17)
        ]
        with self.assertRaisesRegex(ValueError, 'memory decorative filler cap'):
            builder._validate_family_style(decorative)
        with self.assertRaisesRegex(ValueError, 'question ending range'):
            builder._validate_question_ratio(['답이야.'] * 100)
        builder._validate_question_ratio(['답이야?'] * 5 + ['답이야.'] * 95)
        with self.assertRaisesRegex(ValueError, 'question ending range'):
            builder._validate_question_ratio(['답이야?'] * 36 + ['답이야.'] * 64)

    def test_chat_export_and_serialization_hide_author_cards(self):
        chat = builder.export_chat(self.rows)
        self.assertEqual(len(chat), 1000); self.assertEqual(chat[0]['review'], builder.REVIEW)
        self.assertEqual(chat[0]['schema_version'], builder.SCHEMA_VERSION)
        self.assertIn('scenario_group', chat[0]); self.assertIn('updated_tokens', chat[0])
        encoded = builder.render_jsonl(self.rows)
        self.assertNotIn('"_card"', encoded); self.assertEqual(len(encoded.splitlines()), 1000)

    def test_finalized_default_outputs_are_pinned_and_reproducible(self):
        rows = builder.build_records(builder.load_cards())
        source = builder.render_jsonl(rows)
        chat = builder.render_jsonl(builder.export_chat(rows))
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), EXPECTED_SOURCE_SHA256)
        self.assertEqual(hashlib.sha256(chat.encode()).hexdigest(), EXPECTED_CHAT_SHA256)
        self.assertEqual(builder.DEFAULT_SOURCE.read_text(encoding='utf-8'), source)
        self.assertEqual(builder.DEFAULT_CHAT.read_text(encoding='utf-8'), chat)

if __name__ == '__main__': unittest.main()
