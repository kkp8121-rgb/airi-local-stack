"""Offline unit tests for the E2-C2 blind sealer's fail-closed checks.

The real seal run reads external roots and the gitignored correction corpus;
these tests inject synthetic stand-ins through validate_staging()'s explicit
parameters so CI never needs those paths.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent


def _load_seal():
    spec = importlib.util.spec_from_file_location('seal_e2c2_blind_under_test',
                                                  HERE / 'seal_e2c2_blind.py')
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_sim():
    spec = importlib.util.spec_from_file_location('broadcast_sim_for_seal_test',
                                                  HERE / 'broadcast_sim.py')
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture(handle_prefix: str) -> dict:
    """A minimal valid Korean fixture accepted by validate_fixture()."""
    handles = [f'{handle_prefix}첫손님', f'{handle_prefix}둘째손님']
    return {
        'schema_version': 'airi.broadcast-sim-fixture.v1',
        'synthetic_only': True,
        'topic': {'title': '합성 검증 방송', 'signature_greeting': '합성 인사말이야',
                  'beats': [{'id': 'open', 'start_minute': 0, 'end_minute': 2,
                             'label': '열기', 'airi_cue': '열고 있어', 'anchors': ['열기']}]},
        'viewers': [{'handle': handles[0], 'archetype': 'supporter'},
                    {'handle': handles[1], 'archetype': 'supporter'}],
        'archetypes': {'supporter': {'kind': 'reaction', 'templates': ['좋아 보인다 ' + handle_prefix]},
                       'offtopic_chatter': {'kind': 'offtopic', 'templates': ['딴 얘기 ' + handle_prefix]}},
        'rates': {'broadcast_minutes': 2, 'window_seconds': 5, 'turn_cooldown_seconds': 5,
                  'messages_per_minute_min': 1, 'messages_per_minute_max': 1,
                  'active_viewers_min': 2, 'active_viewers_max': 2,
                  'opinion_aggregate_threshold': 2, 'pending_stale_seconds': 10},
        'pickup_priority': ['reaction'],
        'continuity_arcs': [],
        # Pad Hangul volume above the sealing floor without changing behavior.
        'note': '합성 전용 대본. ' + ('가나다라마바사아자차카타파하 ' * 70),
    }


def _staging(tmp_path: Path, seal) -> Path:
    staging = tmp_path / 'staging'
    staging.mkdir()
    for index, (filename, _role) in enumerate(seal.EXPECTED_FIXTURES):
        body = _fixture(('직조', '신호', '가마')[index])
        (staging / filename).write_text(json.dumps(body, ensure_ascii=False, indent=2),
                                        encoding='utf-8')
    return staging


def _public_dir(tmp_path: Path, seal) -> Path:
    public = tmp_path / 'public'
    public.mkdir()
    for name in seal.PUBLIC_FIXTURE_FILES:
        (public / name).write_text(json.dumps(_fixture('공개' + name[:3]), ensure_ascii=False),
                                   encoding='utf-8')
    return public


def _validate(seal, staging, tmp_path, **overrides):
    keywords = {
        'superseded_roots': [],
        'correction_nouns': ['달빛모서리', '별빛산책', '구름연못'],
        'correction_text': '교정 데이터 표본 문장',
        'sim': _load_sim(),
    }
    keywords.update(overrides)
    if 'public_dir' not in keywords:
        keywords['public_dir'] = _public_dir(tmp_path, seal)
    return seal.validate_staging(staging, **keywords)


def test_valid_synthetic_staging_passes_and_returns_three_pins(tmp_path):
    seal = _load_seal()
    staging = _staging(tmp_path, seal)
    pins = _validate(seal, staging, tmp_path)
    assert [pin['logical_role'] for pin in pins] == [role for _name, role in seal.EXPECTED_FIXTURES]
    assert all(len(pin['raw_sha256']) == 64 and len(pin['canonical_sha256']) == 64 for pin in pins)


def test_missing_or_extra_staging_file_fails_closed(tmp_path):
    seal = _load_seal()
    staging = _staging(tmp_path, seal)
    (staging / 'extra.json').write_text('{}', encoding='utf-8')
    with pytest.raises(seal.BlindSealError, match='exactly'):
        _validate(seal, staging, tmp_path)


def test_non_hangul_template_fails_closed(tmp_path):
    seal = _load_seal()
    staging = _staging(tmp_path, seal)
    name = seal.EXPECTED_FIXTURES[0][0]
    body = json.loads((staging / name).read_text(encoding='utf-8'))
    body['archetypes']['supporter']['templates'] = ['looks great']
    (staging / name).write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(seal.BlindSealError, match='no Hangul'):
        _validate(seal, staging, tmp_path)


def test_hangul_floor_fails_closed(tmp_path):
    seal = _load_seal()
    staging = _staging(tmp_path, seal)
    name = seal.EXPECTED_FIXTURES[0][0]
    body = json.loads((staging / name).read_text(encoding='utf-8'))
    body['note'] = '짧은 대본'
    (staging / name).write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(seal.BlindSealError, match='Hangul characters'):
        _validate(seal, staging, tmp_path)


def test_correction_proper_noun_collision_fails_closed(tmp_path):
    seal = _load_seal()
    staging = _staging(tmp_path, seal)
    with pytest.raises(seal.BlindSealError, match='correction proper noun'):
        _validate(seal, staging, tmp_path, correction_nouns=['직조첫손님'])


def test_fixture_handle_inside_correction_text_fails_closed(tmp_path):
    seal = _load_seal()
    staging = _staging(tmp_path, seal)
    with pytest.raises(seal.BlindSealError, match='appears in correction data'):
        _validate(seal, staging, tmp_path, correction_text='… 직조첫손님 이 언급된 교정 행 …')


def test_public_handle_reuse_fails_closed(tmp_path):
    seal = _load_seal()
    staging = _staging(tmp_path, seal)
    public = _public_dir(tmp_path, seal)
    first_public = public / seal.PUBLIC_FIXTURE_FILES[0]
    body = json.loads(first_public.read_text(encoding='utf-8'))
    body['viewers'][0]['handle'] = '직조첫손님'
    first_public.write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(seal.BlindSealError, match='public fixture'):
        _validate(seal, staging, tmp_path, public_dir=public)


def test_superseded_content_reuse_fails_closed(tmp_path):
    seal = _load_seal()
    staging = _staging(tmp_path, seal)
    old_root = tmp_path / 'old-root'
    old_root.mkdir()
    for index, (filename, _role) in enumerate(seal.EXPECTED_FIXTURES):
        old_body = _fixture(('직조', '옛신호', '옛가마')[index])  # first shares the 직조 handles
        (old_root / filename).write_text(json.dumps(old_body, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(seal.BlindSealError, match='superseded'):
        _validate(seal, staging, tmp_path, superseded_roots=[old_root])


def test_superseded_root_id_mention_fails_closed(tmp_path):
    seal = _load_seal()
    staging = _staging(tmp_path, seal)
    name = seal.EXPECTED_FIXTURES[0][0]
    body = json.loads((staging / name).read_text(encoding='utf-8'))
    body['note'] += ' airi-e2-c1-blind-freeze-20260824-v2'
    (staging / name).write_text(json.dumps(body, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(seal.BlindSealError, match='superseded blind root'):
        _validate(seal, staging, tmp_path)


def test_seal_refuses_existing_output_root_and_bad_root_id(tmp_path, monkeypatch):
    seal = _load_seal()
    staging = _staging(tmp_path, seal)
    existing = tmp_path / 'root-exists'
    existing.mkdir()
    with pytest.raises(seal.BlindSealError, match='no-overwrite'):
        seal.seal(staging, existing, 'airi-e2-c2-blind-freeze-20260824-v9', [])
    with pytest.raises(seal.BlindSealError, match='naming'):
        seal.seal(staging, tmp_path / 'root-new', 'my-random-root', [])
