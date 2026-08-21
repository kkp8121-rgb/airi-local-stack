import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import broadcast_sim as sim  # noqa: E402


FIXTURE_PATH = HERE / 'third_long_broadcast_heldout_v1.json'
SEEDS = (44, 55, 66, 20260822)
CANONICAL_SHA256 = 'ddb43f03f88dacff70ebd8a6221274e51348e01e9fe542153139c0330bd52b61'
REFERENCE_PATHS = (
    HERE / 'first_broadcast_v1.json',
    HERE / 'second_broadcast_v1.json',
    HERE / 'long_broadcast_continuity_v1.json',
    ROOT / 'training' / 'seed' / 'airi_broadcast_behavior_v2.jsonl',
    ROOT / 'training' / 'seed' / 'airi_broadcast_behavior_v2_part_a.json',
    ROOT / 'training' / 'seed' / 'airi_broadcast_behavior_v2_part_b.json',
    ROOT / 'training' / 'seed' / 'airi_broadcast_behavior_v2_part_c.json',
    ROOT / 'training' / 'seed' / 'airi_broadcast_continuity_v3.jsonl',
    ROOT / 'training' / 'seed' / 'airi_broadcast_continuity_v3_cards_a.json',
    ROOT / 'training' / 'seed' / 'airi_broadcast_continuity_v3_cards_b.json',
    ROOT / 'training' / 'seed' / 'airi_broadcast_continuity_v3_cards_c.json',
)


def normalized(text: str) -> str:
    return re.sub(r'[^\w]+', '', text.lower())


def tokens(text: str) -> set[str]:
    return set(re.findall(r'\w+', text.lower()))


def leaf_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from leaf_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from leaf_strings(item)


def content_strings(fixture):
    """Only viewer-facing lexical material, excluding shared schema vocabulary."""
    topic = fixture['topic']
    yield topic['title']
    yield topic['signature_greeting']
    for beat in topic['beats']:
        yield beat['label']
        yield beat['airi_cue']
        yield from beat['anchors']
    for archetype in fixture['archetypes'].values():
        yield from archetype['templates']
    for wave in fixture.get('opinion_waves', []):
        yield wave['tag']
        yield wave['label']
        yield from wave['templates']
        yield from wave['aggregate_markers']
    for donation in fixture.get('donations', []):
        yield donation['message']
    for probe in fixture.get('memory_probes', []):
        yield probe['seed_text']
        yield probe['probe_text']
        yield from probe['expect_any']
    for arc in fixture.get('continuity_arcs', []):
        yield arc['id']
        yield arc['seed_text']
        yield arc['callback_text']
        yield from arc['seed_checks']['required_any']
        yield from arc['callback_checks']['required_any']
        yield from arc['seed_checks'].get('forbidden', [])
        yield from arc['callback_checks'].get('forbidden', [])
    for viewer in fixture['viewers']:
        yield viewer['handle']


class ThirdLongBroadcastHeldoutFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads(FIXTURE_PATH.read_text(encoding='utf-8'))
        cls.fixture = sim.load_fixture(FIXTURE_PATH)
        cls.reference_texts = {
            path: path.read_text(encoding='utf-8').lower()
            for path in REFERENCE_PATHS if path.exists()
        }

    def test_schema_canonical_hash_and_required_shape(self):
        self.assertEqual(self.fixture['rates']['broadcast_minutes'], 180)
        self.assertEqual(hashlib.sha256(sim.canonical_bytes(self.raw)).hexdigest(), CANONICAL_SHA256)
        self.assertEqual(len(self.fixture['viewers']), 24)
        self.assertGreaterEqual(sum(v['archetype'] == 'deep_follower' for v in self.fixture['viewers']), 3)
        self.assertIn('offtopic_chatter', self.fixture['archetypes'])
        self.assertEqual([(b['start_minute'], b['end_minute']) for b in self.fixture['topic']['beats']],
                         [(0, 25), (25, 65), (65, 110), (110, 150), (150, 180)])
        self.assertEqual([d['minute'] for d in self.fixture['donations']], [17, 67, 127, 169])
        self.assertEqual([w['minute'] for w in self.fixture['opinion_waves']], [53, 113, 163])

    def test_continuity_design_has_required_gaps_sources_and_event_distribution(self):
        arcs = self.fixture['continuity_arcs']
        gaps = [arc['callback_minute'] - arc['seed_minute'] for arc in arcs]
        self.assertEqual(len(arcs), 12)
        self.assertTrue(all(gap >= 30 for gap in gaps))
        self.assertGreaterEqual(sum(gap >= 90 for gap in gaps), 6)
        self.assertEqual(
            {source: sum(a['expected_source'] == source for a in arcs)
             for source in ('history', 'briefing', 'durable_memory', 'show_arc')},
            {'history': 3, 'briefing': 3, 'durable_memory': 3, 'show_arc': 3},
        )
        self.assertGreaterEqual(len({arc['event_type'] for arc in arcs}), 8)
        positives = [arc['callback_checks']['required_any'][0] for arc in arcs]
        forbidden = [arc['callback_checks']['forbidden'][0] for arc in arcs]
        self.assertEqual(len(positives), len(set(positives)))
        self.assertEqual(len(forbidden), len(set(forbidden)))

    def test_streams_and_pickups_are_deterministic_and_preserve_all_required_turns(self):
        expected_arcs = {(arc['id'], phase) for arc in self.fixture['continuity_arcs'] for phase in ('seed', 'callback')}
        expected_donations = {d['minute'] for d in self.fixture['donations']}
        expected_probes = {p['minute'] for p in self.fixture['memory_probes']}
        expected_waves = {w['minute'] for w in self.fixture['opinion_waves']}
        for seed in SEEDS:
            with self.subTest(seed=seed):
                stream = sim.generate_stream(self.fixture, seed=seed)
                self.assertEqual(sim.canonical_bytes(stream), sim.canonical_bytes(sim.generate_stream(self.fixture, seed=seed)))
                picks = sim.plan_pickups(stream, self.fixture)
                self.assertEqual(
                    {(p['message'].get('arc_id'), p['message'].get('arc_phase')) for p in picks if p['message'].get('arc_id')},
                    expected_arcs,
                )
                picked = [p['message'] for p in picks]
                self.assertTrue(expected_donations <= {m['minute'] for m in picked if m['kind'] == 'donation'})
                self.assertTrue(expected_probes <= {m['minute'] for m in picked if m['kind'] == 'memory_probe'})
                self.assertTrue(expected_waves <= {m['minute'] for m in picked if m['kind'] == 'opinion'})

    def test_positive_and_forbidden_callback_scoring(self):
        picks = sim.plan_pickups(sim.generate_stream(self.fixture, seed=SEEDS[-1]), self.fixture)
        roster = [viewer['handle'] for viewer in self.fixture['viewers']]
        arcs = {arc['id']: arc for arc in self.fixture['continuity_arcs']}
        rows = []
        for pick in picks:
            message = pick['message']
            if message.get('arc_id'):
                checks = arcs[message['arc_id']][f"{message['arc_phase']}_checks"]
                rows.append(sim.score_turn(pick, checks['required_any'][0], beat=sim.beat_at(self.fixture, message['minute']), fallback_pool=(), roster_handles=roster))
        summary = sim.summarize_turns(rows)['continuity']
        self.assertEqual(summary['seed_response']['hits'], 12)
        self.assertEqual(summary['callback']['hits'], 12)
        self.assertEqual(summary['forbidden_hit_turns'], 0)
        callback = next(p for p in picks if p['message'].get('arc_id') == 'arc-screen-direct-sun' and p['message'].get('arc_phase') == 'callback')
        wrong = sim.score_turn(callback, '백엽상은 직사광을 받게 열어 둬', beat=sim.beat_at(self.fixture, 44), fallback_pool=(), roster_handles=roster)
        self.assertTrue(wrong['arc_required_met'])
        self.assertTrue(wrong['arc_forbidden_hits'])
        self.assertFalse(wrong['arc_callback_hit'])

    def test_contamination_guards_against_existing_fixtures_and_training_sources(self):
        self.assertTrue(self.reference_texts)
        current_leaves = {normalized(value) for value in content_strings(self.raw) if normalized(value)}
        for path, text in self.reference_texts.items():
            parsed = json.loads(path.read_text(encoding='utf-8')) if path.suffix == '.json' else None
            values = content_strings(parsed) if isinstance(parsed, dict) and 'topic' in parsed else leaf_strings(parsed)
            reference_leaves = {normalized(value) for value in values if normalized(value)} if parsed is not None else set()
            with self.subTest(reference=path.name):
                self.assertFalse(current_leaves & reference_leaves)

        protected = {'외딴섬', '기상관측소', '백엽상', '우량계', '기압계', '층적운', '권운띠', '풍배도', '돌풍선', '감우지', '전문부호', '일지봉인'}
        for text in self.reference_texts.values():
            self.assertFalse(any(term in text for term in protected))

        aliases = [viewer['handle'] for viewer in self.fixture['viewers']]
        identifiers = [arc['id'] for arc in self.fixture['continuity_arcs']]
        fact_tokens = ['새롬별', '보랏실고리', '다래곶']
        for text in self.reference_texts.values():
            self.assertFalse(any(item.lower() in text for item in aliases + identifiers + fact_tokens))

        prompt_leaves = [value for value in content_strings(self.raw) if len(tokens(value)) >= 2]
        current_fourgrams = {tuple(sorted(window)) for line in prompt_leaves for words in [re.findall(r'\w+', line.lower())]
                            for window in (words[i:i + 4] for i in range(max(0, len(words) - 3)))}
        current_token_set = set().union(*(tokens(line) for line in prompt_leaves))
        for text in self.reference_texts.values():
            words = re.findall(r'\w+', text.lower())
            reference_fourgrams = {tuple(sorted(words[i:i + 4])) for i in range(max(0, len(words) - 3))}
            self.assertFalse(current_fourgrams & reference_fourgrams)
            reference_tokens = tokens(text)
            jaccard = len(current_token_set & reference_tokens) / len(current_token_set | reference_tokens)
            self.assertLessEqual(jaccard, 0.20)


if __name__ == '__main__':
    unittest.main()
