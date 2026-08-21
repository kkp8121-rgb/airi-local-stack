"""Fail-closed, content-free comparator for paired broadcast T3 reports."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

SETTINGS = ('contract', 'briefing', 'acts', 'briefing_evidence',
            'live_broadcast_context', 'history_turns', 'protocol', 'author_format')
REQUIRED_METRICS = ('donation_callout_correct', 'memory_probe',
                    'topic_anchored', 'viewer_fact_usage')


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'{path.name}: report is not an object')
    return value


def load_manifest(path: Path) -> list[dict[str, Any]]:
    manifest = read_json(path)
    fixtures = manifest.get('fixtures')
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError('manifest has no fixtures')
    required = {'filename', 'creation_order', 'role', 'raw_sha256', 'canonical_sha256'}
    if any(not isinstance(item, dict) or required - item.keys() for item in fixtures):
        raise ValueError('manifest fixture fields are incomplete')
    if len({item['filename'] for item in fixtures}) != len(fixtures):
        raise ValueError('manifest filenames are not unique')
    return fixtures


def verify_fixture_files(manifest_path: Path, fixtures: list[dict[str, Any]]) -> list[str]:
    reasons = []
    for fixture in fixtures:
        path = manifest_path.parent / fixture['filename']
        try:
            raw = path.read_bytes()
            parsed = json.loads(raw.decode('utf-8'))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            reasons.append(f'fixture unreadable: {fixture["filename"]}')
            continue
        if hashlib.sha256(raw).hexdigest() != fixture['raw_sha256']:
            reasons.append(f'fixture raw hash drift: {fixture["filename"]}')
        if canonical_sha(parsed) != fixture['canonical_sha256']:
            reasons.append(f'fixture canonical hash drift: {fixture["filename"]}')
    return reasons


def reports_in(directory: Path) -> list[tuple[Path, dict[str, Any]]]:
    if not directory.is_dir():
        raise ValueError(f'report directory missing: {directory}')
    found = sorted(directory.rglob('*.json'))
    if not found:
        raise ValueError(f'no reports in {directory}')
    return [(path, read_json(path)) for path in found]


def rate(metric: Any, label: str) -> tuple[int, int]:
    if not isinstance(metric, dict) or not isinstance(metric.get('hits'), int) or not isinstance(metric.get('of'), int):
        raise ValueError(f'missing metric: {label}')
    hits, total = metric['hits'], metric['of']
    if hits < 0 or total < 0 or hits > total:
        raise ValueError(f'invalid metric: {label}')
    return hits, total


def validate_report(report: dict[str, Any], allowed: set[str]) -> tuple[str, int]:
    sha, seed = report.get('fixture_sha256'), report.get('seed')
    if not isinstance(sha, str) or sha not in allowed or not isinstance(seed, int):
        raise ValueError('unmanifested fixture or missing seed')
    if report.get('live_contract_verified') is not True:
        raise ValueError('live contract was not verified')
    summary, rows = report.get('summary'), report.get('rows')
    if not isinstance(summary, dict) or not isinstance(rows, list) or not rows:
        raise ValueError('missing summary or rows')
    if summary.get('transport_failures') != 0:
        raise ValueError('transport failures are nonzero')
    if not all(name in report for name in SETTINGS):
        raise ValueError('missing settings')
    for name in REQUIRED_METRICS:
        rate(summary.get(name), name)
    indexes, ids = set(), set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('turn_index'), int):
            raise ValueError('row missing turn index')
        if row['turn_index'] in indexes:
            raise ValueError('duplicate turn index')
        indexes.add(row['turn_index'])
        message_id = row.get('message_id', row.get('id'))
        if message_id is not None:
            if message_id in ids:
                raise ValueError('duplicate message id')
            ids.add(message_id)
        if row.get('polite_violation') is True or row.get('invented_handles'):
            raise ValueError('polite violation or invented handle')
    if summary.get('turns') not in (None, len(rows)):
        raise ValueError('turn count mismatch')
    return sha, seed


def compare(base_dir: Path, candidate_dir: Path, manifest_path: Path,
            output: Path, phase: str | None = None, fixture: str | None = None) -> dict[str, Any]:
    reasons: list[str] = []
    try:
        fixtures = load_manifest(manifest_path)
        reasons.extend(verify_fixture_files(manifest_path, fixtures))
        if phase:
            fixtures = [x for x in fixtures if x['role'] == phase]
        if fixture:
            fixtures = [x for x in fixtures if x['filename'] == fixture or x['canonical_sha256'] == fixture]
        if not fixtures:
            raise ValueError('selection contains no manifest fixtures')
        allowed = {x['canonical_sha256'] for x in fixtures}
        maps: list[dict[tuple[str, int], dict[str, Any]]] = []
        for directory in (base_dir, candidate_dir):
            grouped = {}
            for _path, report in reports_in(directory):
                key = validate_report(report, allowed)
                if key in grouped:
                    raise ValueError('duplicate fixture/seed report')
                grouped[key] = report
            maps.append(grouped)
        base, candidate = maps
        if set(base) != set(candidate):
            raise ValueError('base/candidate paired key sets differ')
        present = {sha for sha, _seed in base}
        if present != allowed:
            raise ValueError('missing or extra manifest fixture')
        aggregate = {name: {'base_hits': 0, 'base_of': 0, 'candidate_hits': 0, 'candidate_of': 0}
                     for name in REQUIRED_METRICS}
        calibration_fact_deltas = []
        final_fact_deltas = []
        for key in sorted(base):
            left, right = base[key], candidate[key]
            if any(left[name] != right[name] for name in SETTINGS):
                raise ValueError('settings mismatch')
            if len(left['rows']) != len(right['rows']):
                raise ValueError('turn count differs')
            left_rows = {row['turn_index']: row for row in left['rows']}
            right_rows = {row['turn_index']: row for row in right['rows']}
            if set(left_rows) != set(right_rows):
                raise ValueError('turn indices differ')
            for turn in left_rows:
                a, b = left_rows[turn], right_rows[turn]
                for field in ('message_id', 'id'):
                    if field in a or field in b:
                        if a.get(field) != b.get(field):
                            raise ValueError('message ids differ')
            role = next(x['role'] for x in fixtures if x['canonical_sha256'] == key[0])
            for name in REQUIRED_METRICS:
                bh, bo = rate(left['summary'][name], name); ch, co = rate(right['summary'][name], name)
                aggregate[name]['base_hits'] += bh; aggregate[name]['base_of'] += bo
                aggregate[name]['candidate_hits'] += ch; aggregate[name]['candidate_of'] += co
            bh, bo = rate(left['summary']['viewer_fact_usage'], 'viewer_fact_usage')
            ch, co = rate(right['summary']['viewer_fact_usage'], 'viewer_fact_usage')
            if bo != co or bo == 0:
                raise ValueError('fact usage denominator missing or unequal')
            delta = ch / co - bh / bo
            (final_fact_deltas if role == 'final_blind' else calibration_fact_deltas).append(delta)
            for name, threshold in (('donation_callout_correct', 1.0), ('memory_probe', None)):
                hits, total = rate(right['summary'][name], name)
                if name == 'donation_callout_correct' and total and hits != total:
                    reasons.append('candidate donation callout is not perfect')
                if name == 'memory_probe' and total:
                    base_rate = rate(left['summary'][name], name)[0] / rate(left['summary'][name], name)[1]
                    if hits / total < base_rate or (role == 'final_blind' and hits / total < .90):
                        reasons.append('candidate memory gate failed')
            bt = rate(left['summary']['topic_anchored'], 'topic_anchored'); ct = rate(right['summary']['topic_anchored'], 'topic_anchored')
            if bt[1] != ct[1] or ct[0] / ct[1] < bt[0] / bt[1] - .02:
                reasons.append('candidate topic regression exceeds 0.02')
        fact = aggregate['viewer_fact_usage']
        overall_delta = fact['candidate_hits'] / fact['candidate_of'] - fact['base_hits'] / fact['base_of']
        if any(delta <= 0 for delta in calibration_fact_deltas):
            reasons.append('calibration fixture fact usage lacks positive delta')
        if overall_delta < .10:
            reasons.append('overall fact usage gain below 0.10')
        if any(delta < .10 for delta in final_fact_deltas):
            reasons.append('final blind fact usage gain below 0.10')
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        reasons.append(str(exc))
        aggregate = {}
    result = {'schema_version': 'airi.broadcast-sim-t3-comparison.v1',
              'status': 'pass' if not reasons else 'fail', 'adoption_authorized': False,
              'paired_reports': 0 if reasons and not aggregate else len(locals().get('base', {})),
              'aggregate_numerators': aggregate, 'reasons': sorted(set(reasons))}
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.t3-', suffix='.json', dir=output.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump(result, handle, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            handle.write('\n')
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-reports', type=Path, required=True)
    parser.add_argument('--candidate-reports', type=Path, required=True)
    parser.add_argument('--fixture-manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase', choices=('calibration_regression', 'final_blind'))
    parser.add_argument('--fixture')
    args = parser.parse_args(argv)
    result = compare(args.base_reports, args.candidate_reports, args.fixture_manifest,
                     args.output, args.phase, args.fixture)
    print(json.dumps({'status': result['status'], 'adoption_authorized': False}, separators=(',', ':')))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
