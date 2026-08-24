from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
COMMITMENT_PATH = HERE / 'fixtures' / 'commitments' / 'airi_e2_c2_blind_commitment.json'
POLICY_PATH = HERE / 'fixtures' / 'commitments' / 'airi_e2_c2_metric_policy.json'
EXPECTED_ROLES = {
    'identity_unknown_and_donation_ritual',
    'long_continuity_and_stale_transition',
    'factual_grounding_and_complete_show_arc',
}
EXPECTED_SEEDS = [73, 89, 97, 20260824]
EXPECTED_ARMS = ['baseline', 'e2', 'e2-c2']
PUBLIC_HASHES = {
    'd6cdd694e76ac4017ca1cdebb60ba09c337efa6a1813ce9c00c91b03d4ffcc9c',
    '0d558c0ce3e019569673ed96f4f171e3464e1e044028e7de6b7ede9d5b8085d6',
    '22692a9d24f25cbb6877c297ffc23c93e7d0a74028ddff5072b899e648583760',
    'c2ae8a2db00f8f0ed8bd4ee4d909bde965bcbf18dd359b8dbaf340f4c65a57b1',
    '4e0f018729857b8f4648496298abf2f358a1ad19098f2927d6ec1356809a9897',
    'ddb43f03f88dacff70ebd8a6221274e51348e01e9fe542153139c0330bd52b61',
}


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def test_commitment_freezes_the_v3_root_and_the_36_report_e2c2_matrix():
    commitment = _read(COMMITMENT_PATH)
    assert commitment['schema_version'] == 'airi.e2-c2-blind-commitment.v1'
    assert commitment['root_id'] == 'airi-e2-c2-blind-freeze-20260824-v3'
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


def test_consumed_v1_and_v2_blind_roots_are_not_resealed():
    seal = _load('seal_e2c2_blind_for_commitment_test', 'seal_e2c2_blind.py')
    commitment = _read(COMMITMENT_PATH)
    commitment_text = COMMITMENT_PATH.read_text(encoding='utf-8')
    assert set(seal.SUPERSEDED_ROOT_IDS) == {
        'airi-e2-c1-blind-freeze-20260824-000430',
        'airi-e2-c1-blind-freeze-20260824-v2',
    }
    assert len(seal.SUPERSEDED_HASHES) == 12
    for root_id in seal.SUPERSEDED_ROOT_IDS:
        assert commitment['root_id'] != root_id
        assert root_id not in commitment_text
    for item in commitment['fixtures']:
        assert item['raw_sha256'] not in seal.SUPERSEDED_HASHES
        assert item['canonical_sha256'] not in seal.SUPERSEDED_HASHES


def test_superseded_pins_match_the_e2c1_test_and_repo_commitment_sources():
    seal = _load('seal_e2c2_blind_for_pin_test', 'seal_e2c2_blind.py')
    e2c1_test_text = (HERE / 'test_e2_c1_blind_commitment.py').read_text(encoding='utf-8')
    e2c1_commitment = _read(HERE / 'fixtures' / 'commitments' / 'airi_e2_c1_blind_commitment.json')
    v1_hashes = {value for value in seal.SUPERSEDED_HASHES if value in e2c1_test_text}
    assert len(v1_hashes) == 6, 'v1 hash pins must match test_e2_c1_blind_commitment.py exactly'
    v2_hashes = {item[key] for item in e2c1_commitment['fixtures']
                 for key in ('raw_sha256', 'canonical_sha256')}
    assert v2_hashes <= seal.SUPERSEDED_HASHES


def test_metric_policy_thresholds_are_the_e2c1_values_with_no_relaxation():
    policy = _read(POLICY_PATH)
    e2c1_policy = _read(HERE / 'fixtures' / 'commitments' / 'airi_e2_c1_metric_policy.json')
    assert policy['schema_version'] == 'airi.e2-c2-blind-metric-policy.v1'
    assert policy['status'] == 'frozen_pre_result'
    for shared_key in ('report_completeness', 'hard_gates', 'retained_comparator_axes',
                       'legacy_comparator_gates', 'additive_candidate_gate_vs_e2',
                       'weighted_score', 'result_immutability', 'operational_adoption'):
        assert policy[shared_key] == e2c1_policy[shared_key], shared_key
    selection = dict(policy['selection'])
    e2c1_selection = dict(e2c1_policy['selection'])
    assert selection.pop('e2_c2_minimum_weighted_score_delta_vs_e2') == \
        e2c1_selection.pop('e2_c1_minimum_weighted_score_delta_vs_e2')
    assert selection.pop('e2_c2_minimum_improved_additive_axes') == \
        e2c1_selection.pop('e2_c1_minimum_improved_additive_axes')
    assert selection == e2c1_selection


def test_frozen_verifier_accepts_the_repo_commitment_and_policy_shapes():
    verifier = _load_verifier()
    verifier.policy(_read(POLICY_PATH))
    verifier.commitment(_read(COMMITMENT_PATH), None)


def test_frozen_verifier_rejects_tampering():
    verifier = _load_verifier()
    policy = _read(POLICY_PATH)
    policy['additive_candidate_gate_vs_e2']['complete_show_arc']['minimum'] = 0.5
    with pytest.raises(verifier.FrozenContractError):
        verifier.policy(policy)
    commitment = _read(COMMITMENT_PATH)
    commitment['seeds'] = [1, 2, 3, 4]
    with pytest.raises(verifier.FrozenContractError):
        verifier.commitment(commitment, None)
    commitment = _read(COMMITMENT_PATH)
    commitment['fixtures'][0]['raw_sha256'] = \
        '221000487646ad1e6b8b93e2d7dbad9bbbffd33b41516d1b168d3bc33483fb3d'
    with pytest.raises(verifier.FrozenContractError, match='superseded'):
        verifier.commitment(commitment, None)


def test_no_body_or_external_path_leaks_into_repo_contracts():
    commitment_text = COMMITMENT_PATH.read_text(encoding='utf-8')
    policy_text = POLICY_PATH.read_text(encoding='utf-8')
    for text in (commitment_text, policy_text):
        assert 'D:\\' not in text and 'D:/' not in text
        assert '"viewers"' not in text and '"topic"' not in text and '"archetypes"' not in text
    assert 'root_id' in commitment_text


def _load_verifier():
    path = HERE.parents[1] / 'training' / 'verify_e2_c2_frozen_contract.py'
    spec = importlib.util.spec_from_file_location('verify_e2_c2_frozen_contract_for_test', path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_e2c2_training_contract_is_the_designed_dose_correction():
    verifier = _load_verifier()
    contract = verifier.TRAINING_CONTRACT
    assert contract['candidate'] == 'E2-C2'
    assert contract['init_mode'] == 'adapter-weights-only'
    assert contract['max_microsteps'] == 1536
    assert contract['max_optimizer_steps'] == 96
    assert contract['learning_rate'] == 2e-5
    # Everything else must equal the frozen E2-C1 values.
    assert (contract['seed'], contract['batch_size'], contract['gradient_accumulation_steps'],
            contract['max_seq_length']) == (42, 1, 16, 2048)
    assert (contract['lora_r'], contract['lora_alpha'], contract['lora_dropout']) == (8, 16, 0.05)
    assert contract['scheduler'] == 'LambdaLR' and contract['scheduler_factor'] == 1
    assert contract['checkpoint_every_optimizer_steps'] == 3
    assert verifier.FORBIDDEN == ['direct trainer', 'checkpoint optimizer resume',
                                  'checkpoint scheduler resume', 'checkpoint RNG resume',
                                  'checkpoint cursor resume']
    verifier.training_config(dict(verifier.RUNNER_TRAINING_CONFIG))
    broken = dict(verifier.RUNNER_TRAINING_CONFIG)
    broken['max_steps'] = 512
    with pytest.raises(verifier.FrozenContractError, match='max_steps'):
        verifier.training_config(broken)
