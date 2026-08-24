from __future__ import annotations

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
COMMITMENT_PATH = HERE / 'fixtures' / 'commitments' / 'airi_e2_c1_blind_commitment.json'
POLICY_PATH = HERE / 'fixtures' / 'commitments' / 'airi_e2_c1_metric_policy.json'
EXPECTED_ROLES = {
    'identity_unknown_and_donation_ritual',
    'long_continuity_and_stale_transition',
    'factual_grounding_and_complete_show_arc',
}
EXPECTED_SEEDS = [73, 89, 97, 20260824]
EXPECTED_ARMS = ['baseline', 'e2', 'e2-c1']
# v1 blind root (airi-e2-c1-blind-freeze-20260824-000430).  Its three bodies were
# English, so Korean-first input screening rejected every generated viewer chat and
# no arm could produce a report.  Pinned here so a silent revert to the unrunnable
# root is caught rather than re-sealed.
SUPERSEDED_ROOT_ID = 'airi-e2-c1-blind-freeze-20260824-000430'
SUPERSEDED_HASHES = {
    'fdf0a26a976542e9a47d9b1f0b5d24d31d571bf4b48b7930806f04be12f26162',
    '62accd68e1b40d7c57f6b3b85a61dc9bc24696dc121c80b5fb152e8bf0ca912d',
    '71010d62b9b609370521912d434777d7759cd862dbd2c9e82447adc0ea9b2fee',
    '3a33a467f3997a780b3ce17393af5c85d0d58577f9005615507888fec2cbeab5',
    '13b433cf26da8ab4f938dd9886d664b681971663c8f70ba1bebde17707868e40',
    'd021b6b3f2026c12b961472eca98af1322b800843567e745bba706db38401e30',
}
PUBLIC_HASHES = {
    'd6cdd694e76ac4017ca1cdebb60ba09c337efa6a1813ce9c00c91b03d4ffcc9c',
    '0d558c0ce3e019569673ed96f4f171e3464e1e044028e7de6b7ede9d5b8085d6',
    '22692a9d24f25cbb6877c297ffc23c93e7d0a74028ddff5072b899e648583760',
    'c2ae8a2db00f8f0ed8bd4ee4d909bde965bcbf18dd359b8dbaf340f4c65a57b1',
    '4e0f018729857b8f4648496298abf2f358a1ad19098f2927d6ec1356809a9897',
    'ddb43f03f88dacff70ebd8a6221274e51348e01e9fe542153139c0330bd52b61',
}


def _load_sim():
    spec = importlib.util.spec_from_file_location('e2_c1_broadcast_sim', HERE / 'broadcast_sim.py')
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _canonical_sha(value: dict) -> str:
    return hashlib.sha256(_load_sim().canonical_bytes(value)).hexdigest()


def _validate_inventory(root: Path, commitment: dict) -> list[dict]:
    if commitment['schema_version'] != 'airi.e2-c1-blind-commitment.v1':
        raise ValueError('unexpected commitment schema')
    fixtures = commitment['fixtures']
    if {item['logical_role'] for item in fixtures} != EXPECTED_ROLES or len(fixtures) != 3:
        raise ValueError('unexpected blind fixture roles')
    if commitment['seeds'] != EXPECTED_SEEDS or commitment['arms'] != EXPECTED_ARMS:
        raise ValueError('unfrozen evaluation matrix')
    if commitment['expected_matrix_reports'] != len(fixtures) * len(EXPECTED_SEEDS) * len(EXPECTED_ARMS):
        raise ValueError('matrix count mismatch')
    seen = []
    for item in fixtures:
        path = root / item['filename']
        raw = path.read_bytes()
        value = json.loads(raw)
        if len(raw) != item['size_bytes'] or hashlib.sha256(raw).hexdigest() != item['raw_sha256']:
            raise ValueError('sealed raw hash mismatch')
        if _canonical_sha(value) != item['canonical_sha256']:
            raise ValueError('sealed canonical hash mismatch')
        seen.append({'filename': item['filename'], 'raw_sha256': item['raw_sha256']})
    return seen


def _synthetic_fixture() -> dict:
    return {
        'schema_version': 'airi.broadcast-sim-fixture.v1', 'synthetic_only': True,
        'topic': {'title': 'temporary', 'signature_greeting': 'temporary', 'beats': [
            {'id': 'open', 'start_minute': 0, 'end_minute': 2, 'label': 'open', 'airi_cue': 'open', 'anchors': ['open']},
        ]},
        'viewers': [{'handle': 'one', 'archetype': 'supporter'}, {'handle': 'two', 'archetype': 'supporter'}],
        'archetypes': {'supporter': {'kind': 'reaction', 'templates': ['ok']}, 'offtopic_chatter': {'kind': 'offtopic', 'templates': ['off']}},
        'rates': {'broadcast_minutes': 2, 'window_seconds': 5, 'turn_cooldown_seconds': 5,
                  'messages_per_minute_min': 1, 'messages_per_minute_max': 1, 'active_viewers_min': 2,
                  'active_viewers_max': 2, 'opinion_aggregate_threshold': 2, 'pending_stale_seconds': 10},
        'pickup_priority': ['reaction'], 'continuity_arcs': [],
    }


def test_canonicalizer_and_temp_synthetic_fixture_are_accepted():
    sim = _load_sim()
    fixture = _synthetic_fixture()
    assert sim.validate_fixture(fixture) == fixture
    reordered = {'topic': fixture['topic'], **{key: value for key, value in fixture.items() if key != 'topic'}}
    assert sim.canonical_bytes(fixture) == sim.canonical_bytes(reordered)


def test_commitment_is_only_a_sealed_inventory_and_freezes_the_36_report_matrix():
    commitment = _read(COMMITMENT_PATH)
    assert commitment['root_id'] == 'airi-e2-c1-blind-freeze-20260824-v2'
    assert commitment['seeds'] == EXPECTED_SEEDS
    assert commitment['arms'] == EXPECTED_ARMS
    assert commitment['expected_matrix_reports'] == 36
    assert {item['logical_role'] for item in commitment['fixtures']} == EXPECTED_ROLES
    assert all(item['raw_sha256'] not in PUBLIC_HASHES and item['canonical_sha256'] not in PUBLIC_HASHES
               for item in commitment['fixtures'])
    assert commitment['pre_result_attestation'] == {
        'blind_bodies_sealed': True, 'correction_data_path_disjoint': True,
        'old_public_fixture_reused': False, 'old_report_selection_rationale_reused': False,
        'response_viewed': False, 'thresholds_frozen': True,
    }


def test_unrunnable_v1_blind_root_is_not_re_sealed():
    commitment = _read(COMMITMENT_PATH)
    assert commitment['root_id'] != SUPERSEDED_ROOT_ID
    assert SUPERSEDED_ROOT_ID not in COMMITMENT_PATH.read_text(encoding='utf-8')
    assert all(item['raw_sha256'] not in SUPERSEDED_HASHES
               and item['canonical_sha256'] not in SUPERSEDED_HASHES
               for item in commitment['fixtures'])


def test_metric_policy_is_complete_fail_closed_and_preserves_existing_comparator_axes():
    policy = _read(POLICY_PATH)
    assert policy['schema_version'] == 'airi.e2-c1-blind-metric-policy.v1'
    assert policy['report_completeness']['expected_reports'] == 36
    assert policy['report_completeness']['on_missing_or_duplicate'] == 'fail_closed'
    assert set(policy['hard_gates']['zero_violations']) == {
        'transport', 'polite', 'invented_handle', 'privacy', 'localhost_exposure', 'external_provider_without_opt_in'}
    assert policy['hard_gates']['perfect_rates'] == {
        'unknown_identity_safe': 1.0, 'donation_name_addressee_thanks_message_engagement_composite': 1.0,
        'stale_transition_clean': 1.0, 'decoy_fact_use': 0.0}
    assert policy['retained_comparator_axes'] == {
        'donation_callout': 'donation_callout_correct', 'memory_probe': 'memory_probe',
        'topic_anchored': 'topic_anchored', 'viewer_fact_usage': 'viewer_fact_usage'}
    assert policy['legacy_comparator_gates'] == {
        'donation_callout_correct': {'required_rate': 1.0},
        'memory_probe': {'candidate_must_not_regress_vs_e2': True, 'final_blind_minimum': 0.9},
        'topic_anchored': {'minimum_delta_vs_e2': -0.02},
        'viewer_fact_usage': {'per_fixture_positive_delta_vs_e2': True, 'final_blind_minimum_delta_vs_e2': 0.1},
        'all_fixture_roles_are_final_blind': True}
    assert policy['additive_candidate_gate_vs_e2'] == {
        'topic_anchor': {'metric': 'topic_anchored', 'minimum': 0.55, 'minimum_delta': -0.02},
        'fact_grounded_usage': {'metric': 'viewer_fact_usage', 'minimum': 0.4, 'minimum_delta': 0.1},
        'memory': {'metric': 'memory_probe', 'minimum': 0.5, 'minimum_delta': 0.15},
        'long_callback': {'metric': 'long_callback', 'minimum': 0.5, 'minimum_delta': 0.2},
        'complete_show_arc': {'metric': 'complete_show_arc', 'minimum': 0.75, 'minimum_delta': 0.2}}
    assert sum(policy['weighted_score']['components'].values()) == pytest.approx(1.0)
    assert policy['weighted_score']['weights_sum'] == 1.0
    assert policy['weighted_score']['components'] == {
        'topic_anchor': 0.15, 'fact_grounded_usage': 0.25, 'memory_probe': 0.2,
        'long_callback': 0.2, 'complete_show_arc': 0.2}
    assert policy['weighted_score']['hard_gates_are_not_score_compensable'] is True
    assert policy['selection']['unique_top_score_margin_strictly_greater_than'] == 0.02
    assert policy['selection']['e2_c1_minimum_weighted_score_delta_vs_e2'] == 0.08
    assert policy['selection']['e2_c1_minimum_improved_additive_axes'] == 4
    assert policy['selection']['exact_tie'] == 'no_winner'
    assert policy['operational_adoption']['always'] is False


def test_no_body_or_external_path_leaks_into_repo_contracts():
    commitment_text = COMMITMENT_PATH.read_text(encoding='utf-8')
    policy_text = POLICY_PATH.read_text(encoding='utf-8')
    for text in (commitment_text, policy_text):
        assert 'D:\\' not in text and 'D:/' not in text
        assert '"viewers"' not in text and '"topic"' not in text and '"archetypes"' not in text
    assert 'root_id' in commitment_text


def test_inventory_validator_rejects_tampered_raw_or_canonical_hash(tmp_path: Path):
    commitment = _read(COMMITMENT_PATH)
    fixture = _synthetic_fixture()
    raw = json.dumps(fixture, ensure_ascii=False, indent=2).encode('utf-8')
    (tmp_path / 'one.json').write_bytes(raw)
    local = deepcopy(commitment)
    local['fixtures'] = []
    for index, role in enumerate(sorted(EXPECTED_ROLES), 1):
        filename = f'fixture-{index}.json'
        (tmp_path / filename).write_bytes(raw)
        local['fixtures'].append({'filename': filename, 'logical_role': role, 'size_bytes': len(raw),
                                  'raw_sha256': hashlib.sha256(raw).hexdigest(),
                                  'canonical_sha256': _canonical_sha(fixture)})
    local['fixtures'][0]['raw_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='sealed raw hash mismatch'):
        _validate_inventory(tmp_path, local)
    local['fixtures'][0]['raw_sha256'] = hashlib.sha256(raw).hexdigest()
    local['fixtures'][0]['canonical_sha256'] = '1' * 64
    with pytest.raises(ValueError, match='sealed canonical hash mismatch'):
        _validate_inventory(tmp_path, local)
