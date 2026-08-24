#!/usr/bin/env python3
"""Read-only, fail-closed D1 repository-freeze verifier.

D1 trains nothing: it evaluates the four already-packaged arms (baseline, e2,
e2-c1, e2-c2) against a fresh blind (v4) with the deterministic utterance
layer and the handle-grounding guard both ON.  What this module freezes is
therefore the evaluation contract, not a training recipe: the D1 metric policy
(threshold values identical to the E2-C2 policy, plus the 4-arm ``arm_rules``
and the renamed delta-gated selection keys), the D1 blind commitment, and the
rule that every consumed blind root (v1, v2, v3) can never be resealed.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

ROOT_ID = 'airi-d1-blind-freeze-20260825-v4'
ARMS = ['baseline', 'e2', 'e2-c1', 'e2-c2']
REFERENCE_ARM = 'e2'
DELTA_GATED_ARMS = ['e2-c1', 'e2-c2']
SEEDS = [73, 89, 97, 20260824]
EXPECTED_REPORTS = 48
COMMITMENT_SCHEMA = 'airi.d1-blind-commitment.v1'
POLICY_SCHEMA = 'airi.d1-blind-metric-policy.v1'
SEALED_SCHEMA = 'airi.d1-blind-sealed-manifest.v1'
RECEIPT_SCHEMA = 'airi.d1-blind-validation-receipt.v1'

# The runtime layers the D1 matrix measures with; the launcher attests both and
# the comparator refuses a verdict without them.
REQUIRED_RUNTIME_LAYERS = ('handle_grounding_guard', 'deterministic_utterance_layer')


class FrozenContractError(ValueError):
    pass


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise FrozenContractError(f'required module is unavailable: {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _e2c1():
    return _load('verify_e2_c1_frozen_contract_for_d1', HERE / 'verify_e2_c1_frozen_contract.py')


def _seal_module():
    return _load('seal_blind_for_d1_verify',
                 HERE.parents[1] / 'ollama-proxy' / 'eval' / 'broadcast_sim' / 'seal_e2c2_blind.py')


def policy(p) -> None:
    """Validate the D1 metric policy: E2-C2 values plus the 4-arm rules."""
    add = {'topic_anchor': {'metric': 'topic_anchored', 'minimum': .55, 'minimum_delta': -.02},
           'fact_grounded_usage': {'metric': 'viewer_fact_usage', 'minimum': .4, 'minimum_delta': .1},
           'memory': {'metric': 'memory_probe', 'minimum': .5, 'minimum_delta': .15},
           'long_callback': {'metric': 'long_callback', 'minimum': .5, 'minimum_delta': .2},
           'complete_show_arc': {'metric': 'complete_show_arc', 'minimum': .75, 'minimum_delta': .2}}
    weights = {'topic_anchor': .15, 'fact_grounded_usage': .25, 'memory_probe': .2,
               'long_callback': .2, 'complete_show_arc': .2}
    hard = {'zero_violations': ['transport', 'polite', 'invented_handle', 'privacy',
                                'localhost_exposure', 'external_provider_without_opt_in'],
            'perfect_rates': {'unknown_identity_safe': 1.0,
                              'donation_name_addressee_thanks_message_engagement_composite': 1.0,
                              'stale_transition_clean': 1.0, 'decoy_fact_use': 0.0}}
    axes = {'donation_callout': 'donation_callout_correct', 'memory_probe': 'memory_probe',
            'topic_anchored': 'topic_anchored', 'viewer_fact_usage': 'viewer_fact_usage'}
    legacy = {'donation_callout_correct': {'required_rate': 1.0},
              'memory_probe': {'candidate_must_not_regress_vs_e2': True, 'final_blind_minimum': .9},
              'topic_anchored': {'minimum_delta_vs_e2': -.02},
              'viewer_fact_usage': {'per_fixture_positive_delta_vs_e2': True,
                                    'final_blind_minimum_delta_vs_e2': .1},
              'all_fixture_roles_are_final_blind': True}
    selection = {'unique_top_score_margin_strictly_greater_than': .02,
                 'delta_gated_minimum_weighted_score_delta_vs_e2': .08,
                 'delta_gated_minimum_improved_additive_axes': 4,
                 'exact_tie': 'no_winner', 'any_failed_gate': 'no_winner', 'fail_closed': True}
    imm = {'after_results': ['fixture', 'seed', 'threshold'], 'mutation': 'invalidates_result'}
    operational = {'always': False, 'campaign_authorized_only_when': 'unique_passing_winner',
                   'default': False}
    completeness = {'expected_reports': EXPECTED_REPORTS, 'required_fixture_count': 3,
                    'required_seed_count': 4, 'required_arm_count': 4,
                    'on_missing_or_duplicate': 'fail_closed'}
    arm_rules = {'reference_arm': REFERENCE_ARM, 'delta_gated_arms': DELTA_GATED_ARMS}
    keys = {'schema_version', 'status', 'report_completeness', 'arm_rules', 'hard_gates',
            'retained_comparator_axes', 'legacy_comparator_gates', 'additive_candidate_gate_vs_e2',
            'weighted_score', 'selection', 'result_immutability', 'operational_adoption'}
    w = p.get('weighted_score', {})
    if (set(p) != keys or set(w) != {'components', 'weights_sum', 'hard_gates_are_not_score_compensable'}
            or p.get('schema_version') != POLICY_SCHEMA or p.get('status') != 'frozen_pre_result'
            or p.get('report_completeness') != completeness or p.get('arm_rules') != arm_rules
            or p.get('hard_gates') != hard or p.get('retained_comparator_axes') != axes
            or p.get('legacy_comparator_gates') != legacy
            or p.get('additive_candidate_gate_vs_e2') != add or w.get('components') != weights
            or w.get('weights_sum') != 1.0 or w.get('hard_gates_are_not_score_compensable') is not True
            or p.get('selection') != selection or p.get('result_immutability') != imm
            or p.get('operational_adoption') != operational):
        raise FrozenContractError('policy')


def commitment(c, external) -> None:
    """Validate the D1 blind commitment and, when given, its sealed root."""
    seal = _seal_module()
    e2c1 = _e2c1()
    attest = {'blind_bodies_sealed': True, 'correction_data_path_disjoint': True,
              'old_public_fixture_reused': False, 'old_report_selection_rationale_reused': False,
              'response_viewed': False, 'thresholds_frozen': True}
    mapping = [('identity_unknown_and_donation_ritual.json', 'identity_unknown_and_donation_ritual'),
               ('long_continuity_and_stale_transition.json', 'long_continuity_and_stale_transition'),
               ('factual_grounding_and_complete_show_arc.json', 'factual_grounding_and_complete_show_arc')]
    canonical = {'algorithm': "utf-8 JSON: sort_keys=true, separators=(',', ':'), ensure_ascii=false",
                 'canonicalization_schema_version': 'airi.broadcast-sim-canonical-json.v1'}
    fs = c.get('fixtures')
    if (set(c) != {'schema_version', 'root_id', 'fixture_schema_version', 'canonicalization', 'seeds',
                   'arms', 'expected_matrix_reports', 'fixtures', 'pre_result_attestation'}
            or c.get('schema_version') != COMMITMENT_SCHEMA or c.get('root_id') != ROOT_ID
            or c.get('fixture_schema_version') != 'airi.broadcast-sim-fixture.v1'
            or c.get('canonicalization') != canonical or c.get('seeds') != SEEDS
            or c.get('arms') != ARMS or c.get('expected_matrix_reports') != EXPECTED_REPORTS
            or c.get('pre_result_attestation') != attest or not isinstance(fs, list) or len(fs) != 3
            or [(x.get('filename'), x.get('logical_role')) for x in fs] != mapping):
        raise FrozenContractError('commitment')
    superseded_root_ids = tuple(seal.SUPERSEDED_ROOT_IDS) + tuple(
        seal.GENERATIONS['d1']['extra_superseded_root_ids'])
    superseded_hashes = seal.SUPERSEDED_HASHES | seal.GENERATIONS['d1']['extra_superseded_hashes']
    if c['root_id'] in superseded_root_ids:
        raise FrozenContractError('superseded root reseal')
    names = []
    for f in fs:
        if (set(f) != {'filename', 'logical_role', 'size_bytes', 'raw_sha256', 'canonical_sha256'}
                or not isinstance(f['filename'], str) or '/' in f['filename'] or '\\' in f['filename']
                or not isinstance(f['size_bytes'], int) or f['size_bytes'] <= 0
                or any(not isinstance(f[k], str) or len(f[k]) != 64
                       or any(ch not in '0123456789abcdef' for ch in f[k])
                       for k in ('raw_sha256', 'canonical_sha256'))):
            raise FrozenContractError('commitment fixture')
        if f['raw_sha256'] in superseded_hashes or f['canonical_sha256'] in superseded_hashes:
            raise FrozenContractError('superseded fixture hash reseal')
        names.append(f['filename'])
    if len(set(names)) != 3:
        raise FrozenContractError('commitment fixture')
    if external:
        external = Path(external)
        if external.is_symlink() or {x.name for x in external.iterdir()} != \
                set(names) | {'sealed_manifest.json', 'validation_receipt.json'}:
            raise FrozenContractError('blind inventory')
        for f in fs:
            raw = e2c1.read(external / f['filename'])
            if (len(raw) != f['size_bytes'] or e2c1.sha(raw) != f['raw_sha256']
                    or e2c1.sha(e2c1.canon(json.loads(raw))) != f['canonical_sha256']):
                raise FrozenContractError('blind hash')
        sealed = e2c1.obj(external / 'sealed_manifest.json')
        receipt = e2c1.obj(external / 'validation_receipt.json')
        if (set(sealed) != {'schema_version', 'root_id', 'canonicalization', 'fixtures', 'response_viewed'}
                or sealed.get('schema_version') != SEALED_SCHEMA or sealed.get('root_id') != c['root_id']
                or sealed.get('canonicalization') != c['canonicalization']['algorithm']
                or sealed.get('fixtures') != fs or sealed.get('response_viewed') is not False):
            raise FrozenContractError('sealed manifest')
        validation = receipt.get('validation')
        attestation = receipt.get('attestation')
        required = {'status': 'PASS', 'fixture_schema_validator': c['fixture_schema_version'],
                    'canonicalization': c['canonicalization']['algorithm'], 'fixture_count': 3,
                    'seed_count': 4, 'arm_count': 4, 'expected_report_count': EXPECTED_REPORTS,
                    'public_raw_or_canonical_hash_collision': False,
                    'correction_proper_noun_collision': False,
                    'superseded_hash_collision': False, 'body_output': False}
        language = {'hangul_stream_check': 'pass', 'model_calls': 0}
        if (set(receipt) != {'schema_version', 'root_id', 'sealed_manifest_raw_sha256', 'validation',
                             'language_validation', 'attestation'}
                or receipt.get('schema_version') != RECEIPT_SCHEMA or receipt.get('root_id') != c['root_id']
                or receipt.get('sealed_manifest_raw_sha256') != e2c1.sha(e2c1.read(external / 'sealed_manifest.json'))
                or validation != required or receipt.get('language_validation') != language
                or attestation != c['pre_result_attestation']):
            raise FrozenContractError('blind receipt')


def verify(repo_root=None, external_blind_root=None):
    e2c1 = _e2c1()
    root = (repo_root or HERE.parents[1]).resolve()
    commitments = root / 'ollama-proxy' / 'eval' / 'broadcast_sim' / 'fixtures' / 'commitments'
    policy(e2c1.obj(commitments / 'airi_d1_metric_policy.json'))
    commitment(e2c1.obj(commitments / 'airi_d1_blind_commitment.json'), external_blind_root)
    return {'status': 'pass', 'generation': 'D1', 'root_id': ROOT_ID, 'arms': ARMS,
            'expected_reports': EXPECTED_REPORTS,
            'required_runtime_layers': list(REQUIRED_RUNTIME_LAYERS)}


def run_cli(argv=None, output=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path)
    parser.add_argument('--external-blind-root', type=Path)
    args = parser.parse_args(argv)
    stream = output if output is not None else sys.stdout
    try:
        result = verify(repo_root=args.repo_root, external_blind_root=args.external_blind_root)
    except FrozenContractError as exc:
        print(json.dumps({'status': 'fail', 'error': str(exc)}, ensure_ascii=False), file=stream)
        return 1
    print(json.dumps(result, ensure_ascii=False), file=stream)
    return 0


if __name__ == '__main__':
    raise SystemExit(run_cli())
