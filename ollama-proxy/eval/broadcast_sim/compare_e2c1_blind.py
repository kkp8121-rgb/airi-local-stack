#!/usr/bin/env python3
"""Fail-closed comparator for the frozen E2-C1 blind broadcast matrix.

Consumes the 36 reports the T3 matrix launcher writes under ``-MatrixProfile
e2c1`` and publishes exactly one verdict file that applies the frozen metric
policy.  Nothing here authorizes adoption: the verdict always carries
``adoption_authorized: false``, and a winner is only ever named when every
frozen gate passes.

Three of the policy's ``zero_violations`` names -- privacy, localhost_exposure,
external_provider_without_opt_in -- have no field in
``airi.broadcast-sim-report.v1``.  They are environment invariants the launcher
verifies before any report exists, so this comparator refuses to run without an
explicit launcher attestation instead of inventing a report-shaped proxy.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Sequence

SCHEMA_VERSION = 'airi.e2-c1-blind-comparison.v1'
REPORT_SCHEMA_VERSION = 'airi.broadcast-sim-report.v1'
ENVIRONMENT_ATTESTATION_SCHEMA_VERSION = 'airi.e2-c1-environment-attestation.v1'
CANDIDATE_ARM = 'e2-c1'
REFERENCE_ARM = 'e2'
VERIFIER_PATH = Path(__file__).resolve().parents[2] / 'training' / 'verify_e2_c1_frozen_contract.py'
EPSILON = 1e-9

SETTINGS = ('contract', 'briefing', 'acts', 'briefing_evidence',
            'live_broadcast_context', 'history_turns', 'protocol', 'author_format')

# Policy axis name -> where the rate lives inside a report summary.
AXIS_SUMMARY_PATHS: dict[str, tuple[str, ...]] = {
    'topic_anchored': ('topic_anchored',),
    'viewer_fact_usage': ('viewer_fact_usage',),
    'memory_probe': ('memory_probe',),
    'long_callback': ('continuity', 'long_callback_30m'),
    'complete_show_arc': ('continuity', 'complete_arc'),
    'donation_callout_correct': ('donation_callout_correct',),
}

# Weighted-score component name -> policy axis name.
COMPONENT_AXES = {
    'topic_anchor': 'topic_anchored',
    'fact_grounded_usage': 'viewer_fact_usage',
    'memory_probe': 'memory_probe',
    'long_callback': 'long_callback',
    'complete_show_arc': 'complete_show_arc',
}

REPORT_DERIVED_VIOLATIONS = ('transport', 'polite', 'invented_handle')
ATTESTED_VIOLATIONS = ('privacy', 'localhost_exposure', 'external_provider_without_opt_in')

DONATION_COMPOSITE = 'donation_name_addressee_thanks_message_engagement_composite'

# Perfect-rate metric -> the commitment fixture role whose rows carry it.
PERFECT_RATE_ROLES = {
    'unknown_identity_safe': 'identity_unknown_and_donation_ritual',
    DONATION_COMPOSITE: 'identity_unknown_and_donation_ritual',
    'stale_transition_clean': 'long_continuity_and_stale_transition',
    'decoy_fact_use': 'factual_grounding_and_complete_show_arc',
}

# Perfect-rate metric -> the row fields it is derived from, quoted verbatim in
# the fail-closed error when no report supplies them.
PERFECT_RATE_FIELDS = {
    'unknown_identity_safe': "rows[].probe_hit + rows[].invented_handles",
    DONATION_COMPOSITE: ("rows[].kind=='donation' + callout_correct + addressee_required_met"
                         " + addressee_forbidden_hits + shared_tokens"),
    'stale_transition_clean': ("rows[].arc_event_type=='topic_transition' + arc_required_met"
                               " + arc_forbidden_hits"),
    'decoy_fact_use': "rows[].addressee_forbidden_hits / rows[].arc_forbidden_hits",
}


class BlindComparisonError(ValueError):
    """Fail-closed error: the comparison could not be carried out as frozen."""


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes().decode('utf-8'))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BlindComparisonError(f'{label} is unreadable: {path}') from exc
    if not isinstance(value, dict):
        raise BlindComparisonError(f'{label} is not a JSON object: {path}')
    return value


def raw_sha256(path: Path, label: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise BlindComparisonError(f'{label} is unreadable: {path}') from exc


def load_frozen_verifier() -> Any:
    """Import the repository's frozen-contract verifier for its shape assertions."""
    spec = importlib.util.spec_from_file_location('verify_e2_c1_frozen_contract', VERIFIER_PATH)
    if spec is None or spec.loader is None:
        raise BlindComparisonError(f'frozen contract verifier is unavailable: {VERIFIER_PATH}')
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - import failure is environmental
        raise BlindComparisonError(f'frozen contract verifier failed to import: {exc}') from exc
    if not hasattr(module, 'policy') or not hasattr(module, 'commitment'):
        raise BlindComparisonError('frozen contract verifier lacks policy/commitment assertions')
    return module


def assert_frozen_inputs(policy: dict[str, Any], commitment: dict[str, Any]) -> None:
    verifier = load_frozen_verifier()
    try:
        verifier.policy(policy)
        verifier.commitment(commitment, None)
    except Exception as exc:
        raise BlindComparisonError(f'frozen policy/commitment shape rejected: {exc}') from exc


def load_environment_attestation(path: Path, root_id: str) -> dict[str, Any]:
    """The three non-report zero_violations must be attested, never assumed."""
    document = read_json(path, 'environment attestation')
    if document.get('schema_version') != ENVIRONMENT_ATTESTATION_SCHEMA_VERSION:
        raise BlindComparisonError('environment attestation schema_version is not '
                                   f'{ENVIRONMENT_ATTESTATION_SCHEMA_VERSION}')
    if document.get('root_id') != root_id:
        raise BlindComparisonError('environment attestation root_id does not match the commitment')
    if document.get('run_count') != 36:
        raise BlindComparisonError('environment attestation run_count is not 36')
    violations = document.get('zero_violations')
    if not isinstance(violations, dict) or set(violations) != set(ATTESTED_VIOLATIONS):
        raise BlindComparisonError('environment attestation must name exactly '
                                   f'{sorted(ATTESTED_VIOLATIONS)}; these metrics have no field in '
                                   f'{REPORT_SCHEMA_VERSION}')
    for name in ATTESTED_VIOLATIONS:
        if type(violations[name]) is not int or violations[name] < 0:
            raise BlindComparisonError(f'environment attestation {name} is not a violation count')
    return document


def expected_report_paths(reports_dir: Path, commitment: dict[str, Any]) -> dict[tuple[str, str, int], Path]:
    """Report naming mirrors the T3 launcher: reports/<arm>/<arm>-<key>-<seed>.json."""
    planned: dict[tuple[str, str, int], Path] = {}
    for arm in commitment['arms']:
        for fixture in commitment['fixtures']:
            role = fixture['logical_role']
            for seed in commitment['seeds']:
                planned[(arm, role, seed)] = reports_dir / arm / f'{arm}-{role}-{seed}.json'
    return planned


def discover_reports(reports_dir: Path, commitment: dict[str, Any]) -> dict[tuple[str, str, int], dict[str, Any]]:
    if not reports_dir.is_dir():
        raise BlindComparisonError(f'reports directory missing: {reports_dir}')
    planned = expected_report_paths(reports_dir, commitment)
    expected = int(commitment['expected_matrix_reports'])
    if len(planned) != expected:
        raise BlindComparisonError(f'commitment plans {len(planned)} reports, not {expected}')
    present = sorted(path for path in reports_dir.rglob('*.json') if path.is_file())
    allowed = {path.resolve() for path in planned.values()}
    unexpected = [path for path in present if path.resolve() not in allowed]
    if unexpected:
        raise BlindComparisonError('unexpected report file: '
                                   f'{unexpected[0].relative_to(reports_dir).as_posix()}')
    if len(present) != expected:
        raise BlindComparisonError(f'expected {expected} reports, found {len(present)}')
    loaded: dict[tuple[str, str, int], dict[str, Any]] = {}
    for key, path in planned.items():
        if not path.is_file():
            raise BlindComparisonError(f'missing report: {path.relative_to(reports_dir).as_posix()}')
        loaded[key] = read_json(path, 'report')
    return loaded


def metric_pair(container: Any, label: str) -> tuple[int, int]:
    if not isinstance(container, dict) or type(container.get('hits')) is not int or type(container.get('of')) is not int:
        raise BlindComparisonError(f'report metric is missing or malformed: {label}')
    hits, total = container['hits'], container['of']
    if hits < 0 or total < 0 or hits > total:
        raise BlindComparisonError(f'report metric is out of range: {label}')
    return hits, total


def summary_metric(summary: dict[str, Any], path: Sequence[str], label: str) -> tuple[int, int]:
    cursor: Any = summary
    for step in path:
        if not isinstance(cursor, dict) or step not in cursor:
            raise BlindComparisonError(f'report metric is missing: {label}')
        cursor = cursor[step]
    return metric_pair(cursor, label)


def validate_report(report: dict[str, Any], key: tuple[str, str, int], canonical: str,
                    settings: dict[str, Any] | None) -> dict[str, Any]:
    arm, role, seed = key
    label = f'{arm}/{role}/{seed}'
    if report.get('schema_version') != REPORT_SCHEMA_VERSION:
        raise BlindComparisonError(f'{label}: report schema_version is not {REPORT_SCHEMA_VERSION}')
    if type(report.get('seed')) is not int or report['seed'] != seed:
        raise BlindComparisonError(f'{label}: report seed does not match its filename')
    if report.get('fixture_sha256') != canonical:
        raise BlindComparisonError(f'{label}: report fixture_sha256 is not the committed blind fixture')
    if report.get('live_contract_verified') is not True:
        raise BlindComparisonError(f'{label}: live contract was not verified')
    missing = [name for name in SETTINGS if name not in report]
    if missing:
        raise BlindComparisonError(f'{label}: report is missing settings {missing}')
    observed = {name: report[name] for name in SETTINGS}
    if settings is not None and observed != settings:
        raise BlindComparisonError(f'{label}: report settings differ from the rest of the matrix')
    summary, rows = report.get('summary'), report.get('rows')
    if not isinstance(summary, dict) or not isinstance(rows, list) or not rows:
        raise BlindComparisonError(f'{label}: report has no summary or rows')
    indexes: set[int] = set()
    for row in rows:
        if not isinstance(row, dict) or type(row.get('turn_index')) is not int:
            raise BlindComparisonError(f'{label}: row is missing an integer turn_index')
        if row['turn_index'] in indexes:
            raise BlindComparisonError(f'{label}: duplicate turn_index in one report')
        indexes.add(row['turn_index'])
    if summary.get('turns') not in (None, len(rows)):
        raise BlindComparisonError(f'{label}: summary turn count does not match the rows')
    return observed


def report_violations(report: dict[str, Any], label: str) -> dict[str, int]:
    summary = report['summary']
    transport = summary.get('transport_failures')
    if type(transport) is not int or transport < 0:
        raise BlindComparisonError(f'{label}: summary.transport_failures is not a count')
    polite_hits, _polite_of = metric_pair(summary.get('polite_violation'), f'{label}: polite_violation')
    invented = summary.get('invented_handle_turns')
    if type(invented) is not int or invented < 0:
        raise BlindComparisonError(f'{label}: summary.invented_handle_turns is not a count')
    return {'transport': transport, 'polite': polite_hits, 'invented_handle': invented}


def derive_unknown_identity_safe(rows: Sequence[dict[str, Any]]) -> tuple[int, int]:
    """Identity fixture: a memory probe answered from its expected safe cues and
    without naming a viewer the input never named."""
    hits = total = 0
    for row in rows:
        if 'probe_hit' not in row:
            continue
        if 'invented_handles' not in row:
            raise BlindComparisonError("unknown_identity_safe: row lacks 'invented_handles'")
        total += 1
        if bool(row['probe_hit']) and not row['invented_handles']:
            hits += 1
    return hits, total


def derive_donation_composite(rows: Sequence[dict[str, Any]]) -> tuple[int, int]:
    """Donation ritual: name (callout_correct), addressee (no forbidden hit),
    thanks (the fixture's required_any met) and message engagement (the reply
    shares content tokens with the donation message)."""
    required = ('callout_correct', 'addressee_required_met', 'addressee_forbidden_hits', 'shared_tokens')
    hits = total = 0
    for row in rows:
        if row.get('kind') != 'donation':
            continue
        missing = [name for name in required if name not in row]
        if missing:
            raise BlindComparisonError(f'{DONATION_COMPOSITE}: donation row lacks {missing}')
        total += 1
        if (bool(row['callout_correct']) and bool(row['addressee_required_met'])
                and not row['addressee_forbidden_hits'] and bool(row['shared_tokens'])):
            hits += 1
    return hits, total


def derive_stale_transition_clean(rows: Sequence[dict[str, Any]]) -> tuple[int, int]:
    """Stale transition: the topic-transition arc turn met its required pattern
    and tripped none of its forbidden (stale-topic) patterns."""
    hits = total = 0
    for row in rows:
        if row.get('arc_event_type') != 'topic_transition':
            continue
        for name in ('arc_required_met', 'arc_forbidden_hits'):
            if name not in row:
                raise BlindComparisonError(f'stale_transition_clean: transition row lacks {name!r}')
        total += 1
        if bool(row['arc_required_met']) and not row['arc_forbidden_hits']:
            hits += 1
    return hits, total


def derive_decoy_fact_use(rows: Sequence[dict[str, Any]]) -> tuple[int, int]:
    """Factual grounding: a turn whose message carried checks used a forbidden
    (decoy) pattern.  This rate must be zero."""
    hits = total = 0
    for row in rows:
        checked = row.get('addressee_ok') is not None or 'arc_forbidden_hits' in row
        if not checked:
            continue
        if 'addressee_forbidden_hits' not in row:
            raise BlindComparisonError("decoy_fact_use: checked row lacks 'addressee_forbidden_hits'")
        total += 1
        if row['addressee_forbidden_hits'] or row.get('arc_forbidden_hits'):
            hits += 1
    return hits, total


PERFECT_RATE_DERIVATIONS: dict[str, Callable[[Sequence[dict[str, Any]]], tuple[int, int]]] = {
    'unknown_identity_safe': derive_unknown_identity_safe,
    DONATION_COMPOSITE: derive_donation_composite,
    'stale_transition_clean': derive_stale_transition_clean,
    'decoy_fact_use': derive_decoy_fact_use,
}


def ratio(pair: tuple[int, int], label: str) -> float:
    hits, total = pair
    if total <= 0:
        raise BlindComparisonError(f'no report supplies a denominator for {label}')
    return hits / total


def optional_ratio(pair: tuple[int, int]) -> float | None:
    """A per-fixture axis may legitimately have no denominator on one role."""
    hits, total = pair
    return None if total <= 0 else round(hits / total, 6)


def rounded(value: float) -> float:
    return round(value, 6)


def collect(reports: dict[tuple[str, str, int], dict[str, Any]], commitment: dict[str, Any],
            ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    arms = list(commitment['arms'])
    roles = [fixture['logical_role'] for fixture in commitment['fixtures']]
    per_role = {arm: {role: {axis: [0, 0] for axis in AXIS_SUMMARY_PATHS} for role in roles} for arm in arms}
    violations = {arm: {name: 0 for name in REPORT_DERIVED_VIOLATIONS} for arm in arms}
    perfect = {arm: {name: [0, 0] for name in PERFECT_RATE_ROLES} for arm in arms}
    for (arm, role, seed), report in sorted(reports.items()):
        label = f'{arm}/{role}/{seed}'
        summary, rows = report['summary'], report['rows']
        for axis, path in AXIS_SUMMARY_PATHS.items():
            hits, total = summary_metric(summary, path, f'{label}: {axis}')
            per_role[arm][role][axis][0] += hits
            per_role[arm][role][axis][1] += total
        for name, count in report_violations(report, label).items():
            violations[arm][name] += count
        for name, metric_role in PERFECT_RATE_ROLES.items():
            if metric_role != role:
                continue
            hits, total = PERFECT_RATE_DERIVATIONS[name](rows)
            perfect[arm][name][0] += hits
            perfect[arm][name][1] += total
    return per_role, violations, perfect


def pooled(per_role: dict[str, Any], arm: str, axis: str) -> tuple[int, int]:
    hits = sum(per_role[arm][role][axis][0] for role in per_role[arm])
    total = sum(per_role[arm][role][axis][1] for role in per_role[arm])
    return hits, total


def perfect_ratio(pair: tuple[int, int], name: str) -> float:
    """Fail closed naming the metric and the exact row fields it needs."""
    hits, total = pair
    if total <= 0:
        raise BlindComparisonError(f'no report supplies a denominator for {name}; '
                                   f'required report fields: {PERFECT_RATE_FIELDS[name]}')
    return hits / total


def perfect_rate_ok(pair: tuple[int, int], expected: float, label: str) -> bool:
    hits, total = pair
    perfect_ratio(pair, label)
    if expected == 1.0:
        return hits == total
    if expected == 0.0:
        return hits == 0
    return abs(hits / total - expected) < EPSILON


def evaluate(reports: dict[tuple[str, str, int], dict[str, Any]], policy: dict[str, Any],
             commitment: dict[str, Any], attestation: dict[str, Any]) -> dict[str, Any]:
    arms = list(commitment['arms'])
    roles = [fixture['logical_role'] for fixture in commitment['fixtures']]
    per_role, violations, perfect = collect(reports, commitment)

    rates = {arm: {axis: rounded(ratio(pooled(per_role, arm, axis), f'{arm}: {axis}'))
                   for axis in AXIS_SUMMARY_PATHS} for arm in arms}
    perfect_rates = {arm: {name: rounded(perfect_ratio(tuple(perfect[arm][name]), name))
                           for name in sorted(PERFECT_RATE_ROLES)} for arm in arms}
    weights = policy['weighted_score']['components']
    scores = {arm: rounded(sum(weights[component] * rates[arm][axis]
                               for component, axis in COMPONENT_AXES.items())) for arm in arms}
    deltas = {arm: {axis: rounded(rates[arm][axis] - rates[REFERENCE_ARM][axis])
                    for axis in AXIS_SUMMARY_PATHS} for arm in arms}

    hard: dict[str, Any] = {}
    for name in REPORT_DERIVED_VIOLATIONS:
        hard[f'zero_violations.{name}'] = {
            'source': 'reports', 'candidate_violations': violations[CANDIDATE_ARM][name],
            'passed': violations[CANDIDATE_ARM][name] == 0,
        }
    for name in ATTESTED_VIOLATIONS:
        count = attestation['zero_violations'][name]
        hard[f'zero_violations.{name}'] = {
            'source': 'launcher_environment_attestation', 'candidate_violations': count,
            'passed': count == 0,
        }
    for name, expected in sorted(policy['hard_gates']['perfect_rates'].items()):
        hard[f'perfect_rates.{name}'] = {
            'source': 'reports', 'expected': expected,
            'candidate_rate': perfect_rates[CANDIDATE_ARM][name],
            'passed': perfect_rate_ok(tuple(perfect[CANDIDATE_ARM][name]), expected, name),
        }

    legacy_policy = policy['legacy_comparator_gates']
    legacy: dict[str, Any] = {}
    donation = rates[CANDIDATE_ARM]['donation_callout_correct']
    legacy['donation_callout_correct'] = {
        'candidate_rate': donation, 'required_rate': legacy_policy['donation_callout_correct']['required_rate'],
        'passed': abs(donation - legacy_policy['donation_callout_correct']['required_rate']) < EPSILON,
    }
    memory_floor = legacy_policy['memory_probe']['final_blind_minimum']
    legacy['memory_probe'] = {
        'candidate_rate': rates[CANDIDATE_ARM]['memory_probe'],
        'reference_rate': rates[REFERENCE_ARM]['memory_probe'],
        'final_blind_minimum': memory_floor,
        'passed': (rates[CANDIDATE_ARM]['memory_probe'] >= rates[REFERENCE_ARM]['memory_probe'] - EPSILON
                   and rates[CANDIDATE_ARM]['memory_probe'] >= memory_floor - EPSILON),
    }
    topic_floor = legacy_policy['topic_anchored']['minimum_delta_vs_e2']
    legacy['topic_anchored'] = {
        'delta_vs_e2': deltas[CANDIDATE_ARM]['topic_anchored'], 'minimum_delta_vs_e2': topic_floor,
        'passed': deltas[CANDIDATE_ARM]['topic_anchored'] >= topic_floor - EPSILON,
    }
    fact_floor = legacy_policy['viewer_fact_usage']['final_blind_minimum_delta_vs_e2']
    per_fixture = {}
    for role in roles:
        candidate = ratio(tuple(per_role[CANDIDATE_ARM][role]['viewer_fact_usage']),
                          f'{CANDIDATE_ARM}/{role}: viewer_fact_usage')
        reference = ratio(tuple(per_role[REFERENCE_ARM][role]['viewer_fact_usage']),
                          f'{REFERENCE_ARM}/{role}: viewer_fact_usage')
        per_fixture[role] = rounded(candidate - reference)
    legacy['viewer_fact_usage'] = {
        'delta_vs_e2': deltas[CANDIDATE_ARM]['viewer_fact_usage'],
        'per_fixture_delta_vs_e2': per_fixture, 'final_blind_minimum_delta_vs_e2': fact_floor,
        'passed': (all(value > EPSILON for value in per_fixture.values())
                   and deltas[CANDIDATE_ARM]['viewer_fact_usage'] >= fact_floor - EPSILON),
    }

    additive: dict[str, Any] = {}
    improved = 0
    for name, gate in sorted(policy['additive_candidate_gate_vs_e2'].items()):
        axis = gate['metric']
        candidate, delta = rates[CANDIDATE_ARM][axis], deltas[CANDIDATE_ARM][axis]
        passed = candidate >= gate['minimum'] - EPSILON and delta >= gate['minimum_delta'] - EPSILON
        if delta > EPSILON:
            improved += 1
        additive[name] = {'metric': axis, 'candidate_rate': candidate, 'delta_vs_e2': delta,
                          'minimum': gate['minimum'], 'minimum_delta': gate['minimum_delta'],
                          'improved_vs_e2': delta > EPSILON, 'passed': passed}

    failed = sorted([name for name, gate in hard.items() if not gate['passed']]
                    + [f'legacy.{name}' for name, gate in legacy.items() if not gate['passed']]
                    + [f'additive.{name}' for name, gate in additive.items() if not gate['passed']])

    selection = policy['selection']
    ordered = sorted(arms, key=lambda arm: (-scores[arm], arm))
    top, runner_up = ordered[0], ordered[1]
    margin = rounded(scores[top] - scores[runner_up])
    candidate_delta = rounded(scores[CANDIDATE_ARM] - scores[REFERENCE_ARM])

    winner: str | None = None
    reason: str | None = None
    if failed:
        reason = 'failed gates: ' + ', '.join(failed)
    elif margin <= selection['unique_top_score_margin_strictly_greater_than'] + EPSILON:
        reason = (f'top score margin {margin} does not exceed '
                  f'{selection["unique_top_score_margin_strictly_greater_than"]}')
    elif top == CANDIDATE_ARM and candidate_delta < selection['e2_c1_minimum_weighted_score_delta_vs_e2'] - EPSILON:
        reason = (f'e2-c1 weighted score delta {candidate_delta} is below '
                  f'{selection["e2_c1_minimum_weighted_score_delta_vs_e2"]}')
    elif top == CANDIDATE_ARM and improved < selection['e2_c1_minimum_improved_additive_axes']:
        reason = (f'e2-c1 improved {improved} additive axes, below '
                  f'{selection["e2_c1_minimum_improved_additive_axes"]}')
    else:
        winner = top

    return {
        'schema_version': SCHEMA_VERSION,
        'status': 'pass',
        'adoption_authorized': False,
        'root_id': commitment['root_id'],
        'report_count': len(reports),
        'arms': arms,
        'candidate_arm': CANDIDATE_ARM,
        'reference_arm': REFERENCE_ARM,
        'axis_rates': rates,
        'per_fixture_axis_rates': {arm: {role: {axis: optional_ratio(tuple(per_role[arm][role][axis]))
                                                for axis in sorted(AXIS_SUMMARY_PATHS)}
                                         for role in roles} for arm in arms},
        'deltas_vs_e2': deltas,
        'violation_counts': violations,
        'perfect_rates': perfect_rates,
        'gates': {'hard': hard, 'legacy': legacy, 'additive': additive, 'failed': failed},
        'scores': scores,
        'score_margin': margin,
        'improved_additive_axes_vs_e2': improved,
        'winner': winner,
        'no_winner_reason': reason,
    }


def publish(output: Path, verdict: dict[str, Any]) -> None:
    if output.exists():
        raise BlindComparisonError(f'verdict already exists: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    handle_fd, temporary = tempfile.mkstemp(prefix='.e2c1-', suffix='.json', dir=output.parent)
    try:
        with os.fdopen(handle_fd, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump(verdict, handle, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            handle.write('\n')
        if output.exists():
            raise BlindComparisonError(f'verdict already exists: {output}')
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def compare(reports_dir: Path, policy_path: Path, commitment_path: Path, output: Path,
            environment_attestation: Path,
            expected_model_manifest_sha256: str | None = None) -> dict[str, Any]:
    if output.exists():
        raise BlindComparisonError(f'verdict already exists: {output}')
    policy = read_json(policy_path, 'metric policy')
    commitment = read_json(commitment_path, 'blind commitment')
    assert_frozen_inputs(policy, commitment)
    attestation = load_environment_attestation(environment_attestation, commitment['root_id'])
    model_manifest_sha256 = None
    if expected_model_manifest_sha256 is not None:
        manifest_path = reports_dir.parent / 'evidence' / 'model-manifest.json'
        model_manifest_sha256 = raw_sha256(manifest_path, 'model manifest')
        if model_manifest_sha256 != expected_model_manifest_sha256:
            raise BlindComparisonError('retained model manifest SHA-256 differs from the expected value')
    completeness = policy['report_completeness']
    if (len(commitment['fixtures']) != completeness['required_fixture_count']
            or len(commitment['seeds']) != completeness['required_seed_count']
            or len(commitment['arms']) != completeness['required_arm_count']):
        raise BlindComparisonError('commitment shape does not match the policy report completeness')
    reports = discover_reports(reports_dir, commitment)
    if len(reports) != completeness['expected_reports']:
        raise BlindComparisonError(f'expected {completeness["expected_reports"]} reports')
    canonical = {fixture['logical_role']: fixture['canonical_sha256'] for fixture in commitment['fixtures']}
    settings: dict[str, Any] | None = None
    for key in sorted(reports):
        settings = validate_report(reports[key], key, canonical[key[1]], settings)
    verdict = evaluate(reports, policy, commitment, attestation)
    verdict['policy_sha256'] = raw_sha256(policy_path, 'metric policy')
    verdict['commitment_sha256'] = raw_sha256(commitment_path, 'blind commitment')
    verdict['environment_attestation_sha256'] = raw_sha256(environment_attestation,
                                                           'environment attestation')
    verdict['model_manifest_sha256'] = model_manifest_sha256
    publish(output, verdict)
    return verdict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Frozen E2-C1 blind matrix comparator')
    parser.add_argument('--reports-dir', type=Path, required=True)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--commitment', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--environment-attestation', type=Path, required=True)
    parser.add_argument('--expected-model-manifest-sha256')
    args = parser.parse_args(argv)
    try:
        verdict = compare(args.reports_dir, args.policy, args.commitment, args.output,
                          args.environment_attestation, args.expected_model_manifest_sha256)
    except BlindComparisonError as exc:
        print(json.dumps({'status': 'fail', 'adoption_authorized': False, 'reason': str(exc)},
                         ensure_ascii=False, separators=(',', ':')), file=sys.stderr)
        return 2
    print(json.dumps({'status': verdict['status'], 'winner': verdict['winner'],
                      'adoption_authorized': False}, ensure_ascii=False, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
