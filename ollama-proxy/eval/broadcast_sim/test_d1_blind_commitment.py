from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
COMMITMENT_PATH = HERE / 'fixtures' / 'commitments' / 'airi_d1_blind_commitment.json'
POLICY_PATH = HERE / 'fixtures' / 'commitments' / 'airi_d1_metric_policy.json'
E2C2_POLICY_PATH = HERE / 'fixtures' / 'commitments' / 'airi_e2_c2_metric_policy.json'
EXPECTED_ROLES = {
    'identity_unknown_and_donation_ritual',
    'long_continuity_and_stale_transition',
    'factual_grounding_and_complete_show_arc',
}
EXPECTED_SEEDS = [73, 89, 97, 20260824]
EXPECTED_ARMS = ['baseline', 'e2', 'e2-c1', 'e2-c2']
PUBLIC_HASHES = {
    'd6cdd694e76ac4017ca1cdebb60ba09c337efa6a1813ce9c00c91b03d4ffcc9c',
    '0d558c0ce3e019569673ed96f4f171e3464e1e044028e7de6b7ede9d5b8085d6',
    '22692a9d24f25cbb6877c297ffc23c93e7d0a74028ddff5072b899e648583760',
    'c2ae8a2db00f8f0ed8bd4ee4d909bde965bcbf18dd359b8dbaf340f4c65a57b1',
    '4e0f018729857b8f4648496298abf2f358a1ad19098f2927d6ec1356809a9897',
    'ddb43f03f88dacff70ebd8a6221274e51348e01e9fe542153139c0330bd52b61',
}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _verifier():
    return _load('verify_d1_frozen_contract_for_test',
                 HERE.parents[1] / 'training' / 'verify_d1_frozen_contract.py')


def _seal():
    return _load('seal_blind_for_d1_commitment_test', HERE / 'seal_e2c2_blind.py')


def test_commitment_freezes_the_v4_root_and_the_48_report_four_arm_matrix():
    commitment = _read(COMMITMENT_PATH)
    assert commitment['schema_version'] == 'airi.d1-blind-commitment.v1'
    assert commitment['root_id'] == 'airi-d1-blind-freeze-20260825-v4'
    assert commitment['seeds'] == EXPECTED_SEEDS
    assert commitment['arms'] == EXPECTED_ARMS
    assert commitment['expected_matrix_reports'] == 48
    assert len(commitment['arms']) * len(commitment['fixtures']) * len(commitment['seeds']) == 48
    assert {item['logical_role'] for item in commitment['fixtures']} == EXPECTED_ROLES
    assert all(item['raw_sha256'] not in PUBLIC_HASHES and item['canonical_sha256'] not in PUBLIC_HASHES
               for item in commitment['fixtures'])
    assert commitment['pre_result_attestation'] == {
        'blind_bodies_sealed': True, 'correction_data_path_disjoint': True,
        'old_public_fixture_reused': False, 'old_report_selection_rationale_reused': False,
        'response_viewed': False, 'thresholds_frozen': True,
    }


def test_every_consumed_blind_root_v1_v2_v3_is_barred_from_reseal():
    seal = _seal()
    commitment = _read(COMMITMENT_PATH)
    text = COMMITMENT_PATH.read_text(encoding='utf-8')
    generation = seal.GENERATIONS['d1']
    root_ids = set(seal.SUPERSEDED_ROOT_IDS) | set(generation['extra_superseded_root_ids'])
    hashes = seal.SUPERSEDED_HASHES | generation['extra_superseded_hashes']
    assert root_ids == {
        'airi-e2-c1-blind-freeze-20260824-000430',
        'airi-e2-c1-blind-freeze-20260824-v2',
        'airi-e2-c2-blind-freeze-20260824-v3',
    }
    assert len(hashes) == 18
    for root_id in root_ids:
        assert commitment['root_id'] != root_id
        assert root_id not in text
    for item in commitment['fixtures']:
        assert item['raw_sha256'] not in hashes
        assert item['canonical_sha256'] not in hashes


def test_v3_superseded_pins_match_the_shipped_e2c2_commitment():
    seal = _seal()
    v3_commitment = _read(HERE / 'fixtures' / 'commitments' / 'airi_e2_c2_blind_commitment.json')
    v3_hashes = {item[key] for item in v3_commitment['fixtures']
                 for key in ('raw_sha256', 'canonical_sha256')}
    assert v3_hashes <= seal.GENERATIONS['d1']['extra_superseded_hashes']


def test_policy_thresholds_equal_the_e2c2_values_with_no_relaxation():
    policy = _read(POLICY_PATH)
    previous = _read(E2C2_POLICY_PATH)
    assert policy['schema_version'] == 'airi.d1-blind-metric-policy.v1'
    assert policy['status'] == 'frozen_pre_result'
    for shared_key in ('hard_gates', 'retained_comparator_axes', 'legacy_comparator_gates',
                       'additive_candidate_gate_vs_e2', 'weighted_score', 'result_immutability',
                       'operational_adoption'):
        assert policy[shared_key] == previous[shared_key], shared_key
    selection = dict(policy['selection'])
    previous_selection = dict(previous['selection'])
    assert selection.pop('delta_gated_minimum_weighted_score_delta_vs_e2') == \
        previous_selection.pop('e2_c2_minimum_weighted_score_delta_vs_e2')
    assert selection.pop('delta_gated_minimum_improved_additive_axes') == \
        previous_selection.pop('e2_c2_minimum_improved_additive_axes')
    assert selection == previous_selection
    # Only the report-count shape widens from three arms to four.
    assert policy['report_completeness']['expected_reports'] == 48
    assert policy['report_completeness']['required_arm_count'] == 4
    assert policy['report_completeness']['on_missing_or_duplicate'] == 'fail_closed'
    assert policy['arm_rules'] == {'reference_arm': 'e2', 'delta_gated_arms': ['e2-c1', 'e2-c2']}


def test_frozen_verifier_accepts_the_repo_commitment_and_policy():
    verifier = _verifier()
    verifier.policy(_read(POLICY_PATH))
    verifier.commitment(_read(COMMITMENT_PATH), None)


def test_frozen_verifier_rejects_tampering():
    verifier = _verifier()
    policy = _read(POLICY_PATH)
    policy['additive_candidate_gate_vs_e2']['memory']['minimum'] = 0.1
    with pytest.raises(verifier.FrozenContractError):
        verifier.policy(policy)
    policy = _read(POLICY_PATH)
    policy['arm_rules']['delta_gated_arms'] = ['e2-c2']
    with pytest.raises(verifier.FrozenContractError):
        verifier.policy(policy)
    commitment = _read(COMMITMENT_PATH)
    commitment['arms'] = ['baseline', 'e2', 'e2-c2']
    with pytest.raises(verifier.FrozenContractError):
        verifier.commitment(commitment, None)
    commitment = _read(COMMITMENT_PATH)
    commitment['fixtures'][0]['raw_sha256'] = \
        '99945ebb2cbffd1b831e73ec10e29271eb9b3c1daac3bb3a5d959ce1e2a65b61'
    with pytest.raises(verifier.FrozenContractError, match='superseded'):
        verifier.commitment(commitment, None)


def test_no_body_or_external_path_leaks_into_repo_contracts():
    for path in (COMMITMENT_PATH, POLICY_PATH):
        text = path.read_text(encoding='utf-8')
        assert 'D:\\' not in text and 'D:/' not in text
        assert '"viewers"' not in text and '"topic"' not in text and '"archetypes"' not in text


def test_required_runtime_layers_are_pinned_for_the_matrix():
    verifier = _verifier()
    assert verifier.REQUIRED_RUNTIME_LAYERS == (
        'handle_grounding_guard', 'deterministic_utterance_layer')
