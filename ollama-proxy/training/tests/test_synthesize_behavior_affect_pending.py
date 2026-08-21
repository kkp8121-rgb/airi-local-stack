from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from behavior_answer_gate import BehaviorAnswerGateError, validate_behavior_answer
from synthesize_behavior_affect_pending import (DEFAULT_OUTPUT, load_config,
                                                  synthesize)
from affect_expression import render_affect_expression_contract
from affect_state import initial_state, reduce_affect, render_continuity_snapshot


class AffectPendingSynthesisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = synthesize(load_config())

    def test_exact_counts_splits_and_quotas(self):
        self.assertEqual(len(self.records), 120)
        self.assertEqual({s: sum(x['split'] == s for x in self.records) for s in ('train', 'dev', 'test')}, {'train': 90, 'dev': 15, 'test': 15})
        counts = {p: sum(x['behavior'] == f'affect_{p}' for x in self.records) for p in load_config()['profiles']['counts']}
        self.assertEqual(counts['playful_annoyed'], 16)
        self.assertEqual(counts['concerned'], 16)
        self.assertTrue(all(value == 8 for key, value in counts.items() if key not in ('playful_annoyed', 'concerned')))
        for primary in counts:
            rows = [x for x in self.records if x['behavior'] == f'affect_{primary}']
            for offset in range(0, len(rows), 8):
                self.assertEqual([x['split'] for x in rows[offset:offset + 8]], ['train'] * 6 + ['dev', 'test'])

    def test_committed_file_is_generator_output_and_unique(self):
        committed = [json.loads(line) for line in DEFAULT_OUTPUT.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(committed, self.records)
        self.assertEqual(len({x['prompt'] for x in self.records}), 120)
        self.assertEqual(len({x['answer'].strip() for x in self.records}), 120)

    def test_reducer_and_prompt_are_exact(self):
        for row in self.records:
            state = initial_state()
            for event in row['affect_events']:
                state = reduce_affect(state, event)
            self.assertEqual(state, row['affect_state'])
            self.assertEqual(row['affect_state']['primary'], row['behavior'][7:])
            self.assertEqual(row['affect_prompt'], render_continuity_snapshot(state) + '\n\n' + render_affect_expression_contract(state))

    def test_gate_passes_and_rejects_mutations(self):
        for row in self.records:
            validate_behavior_answer(row, row['answer'], 1, 160)
        sample = dict(self.records[0])
        sample['must_include_any'] = ['없는문구']
        with self.assertRaises(BehaviorAnswerGateError): validate_behavior_answer(sample, sample['answer'])
        bad = dict(self.records[0])
        with self.assertRaises(BehaviorAnswerGateError): validate_behavior_answer(bad, 'airi_state 바보야')
        acute = next(x for x in self.records if x['safety_class'] == 'acute_physical')
        with self.assertRaises(BehaviorAnswerGateError): validate_behavior_answer(acute, '진단을 받아봐')
        moderation = next(x for x in self.records if x['safety_class'] == 'moderation_boundary')
        with self.assertRaises(BehaviorAnswerGateError): validate_behavior_answer(moderation, '119에 연락해')

    def test_schema_shape_and_fixture_overlap(self):
        schema = json.loads((HERE / 'seed' / 'airi_behavior_affect_pending_record.schema.json').read_text(encoding='utf-8'))
        self.assertFalse(schema['additionalProperties'])
        for name in ('affect_events', 'affect_state', 'affect_prompt', 'safety_class', 'humor_target', 'must_include_any', 'must_not_include'):
            self.assertIn(name, schema['required'])
        existing = [json.loads(line) for line in (HERE / 'seed' / 'airi_behavior_seed_pending.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertFalse({x['prompt'] for x in existing} & {x['prompt'] for x in self.records})
        self.assertFalse({x['answer'].strip() for x in existing} & {x['answer'].strip() for x in self.records})
        fixture = json.loads((HERE.parent / 'eval' / 'affect_broadcast' / 'synthetic_affect_broadcast_v1.json').read_text(encoding='utf-8'))
        strings, stack = set(), [fixture]
        while stack:
            current = stack.pop()
            if isinstance(current, str):
                strings.add(current)
            elif isinstance(current, dict):
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)
        self.assertFalse(strings & {x['prompt'] for x in self.records})
        self.assertFalse(strings & {x['answer'].strip() for x in self.records})


if __name__ == '__main__':
    unittest.main()
