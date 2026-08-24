#!/usr/bin/env python3
"""Offline validator and sealer for the E2-C2 retained blind root (fixtures v3).

The E2-C1 blind v1 root shipped English-only bodies that Korean-first input
screening rejected at run time, so sealing now requires the stream-only
evidence this module produces: every deterministically generated chat message
must carry Hangul, with zero model calls.  The module also enforces the E2-C2
authoring contract: the new fixtures must not reuse correction-data proper
nouns, public fixture handles or hashes, or any superseded blind root's
fixture hashes (v1 and v2 are both consumed and must never be resealed).

Fixture bodies never enter the repository: this CLI reads a staging directory
outside the repo and seals into an external output root.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

HERE = Path(__file__).resolve().parent
SEALED_SCHEMA_VERSION = 'airi.e2-c2-blind-sealed-manifest.v1'
RECEIPT_SCHEMA_VERSION = 'airi.e2-c2-blind-validation-receipt.v1'
FIXTURE_SCHEMA_VERSION = 'airi.broadcast-sim-fixture.v1'
CANONICALIZATION = "utf-8 JSON: sort_keys=true, separators=(',', ':'), ensure_ascii=false"
EXPECTED_FIXTURES = (
    ('identity_unknown_and_donation_ritual.json', 'identity_unknown_and_donation_ritual'),
    ('long_continuity_and_stale_transition.json', 'long_continuity_and_stale_transition'),
    ('factual_grounding_and_complete_show_arc.json', 'factual_grounding_and_complete_show_arc'),
)
SEEDS = (73, 89, 97, 20260824)
ARMS = ('baseline', 'e2', 'e2-c2')
MIN_HANGUL_CHARS = 800
HANGUL = re.compile('[가-힣]')
PUBLIC_FIXTURE_FILES = (
    'first_broadcast_v1.json', 'second_broadcast_v1.json',
    'third_long_broadcast_heldout_v1.json', 'long_broadcast_continuity_v1.json',
)
# Consumed blind roots.  Their root ids and fixture hashes (raw and canonical)
# must never appear again; hashes are commitments, not bodies, so pinning them
# here keeps the repository body-free.
SUPERSEDED_ROOT_IDS = (
    'airi-e2-c1-blind-freeze-20260824-000430',
    'airi-e2-c1-blind-freeze-20260824-v2',
)
SUPERSEDED_HASHES = frozenset({
    # v1 (English-defect root)
    'fdf0a26a976542e9a47d9b1f0b5d24d31d571bf4b48b7930806f04be12f26162',
    '62accd68e1b40d7c57f6b3b85a61dc9bc24696dc121c80b5fb152e8bf0ca912d',
    '71010d62b9b609370521912d434777d7759cd862dbd2c9e82447adc0ea9b2fee',
    '3a33a467f3997a780b3ce17393af5c85d0d58577f9005615507888fec2cbeab5',
    '13b433cf26da8ab4f938dd9886d664b681971663c8f70ba1bebde17707868e40',
    'd021b6b3f2026c12b961472eca98af1322b800843567e745bba706db38401e30',
    # v2 (consumed by the E2-C1 matrix)
    '221000487646ad1e6b8b93e2d7dbad9bbbffd33b41516d1b168d3bc33483fb3d',
    '17ab77e9f1c9aed37926d68d8827542a9ab7e37226674e22e482b0cab78fd504',
    '98c66f212317872dff11bc353cb7dd12017bf78a75925e7c4657e3a74b2fa7f7',
    '16174f8729ee9a33ca0b323f6e919795d66918e8be8bfd1adecdbceabb1dae1d',
    'c90e976b145c0c2401af2d30fbe7bdbab7aebb5620370c166ef3098d54f81b1d',
    'a19886918a23090834ed1105374890c44192e1b2716451a8f2db1d3a2ab9c1db',
})


class BlindSealError(ValueError):
    """Fail-closed error: the staging fixtures cannot be sealed as-is."""


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise BlindSealError(f'required module is unavailable: {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_broadcast_sim() -> Any:
    return _load_module('broadcast_sim_for_seal', HERE / 'broadcast_sim.py')


def load_correction_proper_nouns() -> frozenset[str]:
    module = _load_module('synthesize_broadcast_e2_c1_for_seal',
                          HERE.parents[1] / 'training' / 'synthesize_broadcast_e2_c1.py')
    nouns = set(module._HANDLES) | set(module._UNKNOWN_HANDLES) | set(module._DONORS)
    if len(nouns) < 40:
        raise BlindSealError('correction proper noun inventory is implausibly small')
    return frozenset(nouns)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture_handles(fixture: dict[str, Any]) -> set[str]:
    return {viewer['handle'] for viewer in fixture['viewers']}


def fixture_templates(fixture: dict[str, Any]) -> set[str]:
    return {template for archetype in fixture['archetypes'].values()
            for template in archetype['templates']}


def check_hangul(fixture: dict[str, Any], filename: str) -> int:
    text = json.dumps(fixture, ensure_ascii=False)
    total = len(HANGUL.findall(text))
    if total < MIN_HANGUL_CHARS:
        raise BlindSealError(f'{filename}: only {total} Hangul characters (< {MIN_HANGUL_CHARS})')
    for template in sorted(fixture_templates(fixture)):
        if not HANGUL.search(template):
            raise BlindSealError(f'{filename}: archetype template has no Hangul: {template!r}')
    return total


def check_stream_language(sim: Any, fixture: dict[str, Any], filename: str,
                          seeds: Sequence[int]) -> int:
    """Deterministic stream generation only -- zero model calls by construction."""
    messages = 0
    for seed in seeds:
        stream = sim.generate_stream(fixture, seed=seed)
        entries = stream.get('messages') if isinstance(stream, dict) else None
        if not entries:
            raise BlindSealError(f'{filename}: seed {seed} generated no stream messages')
        for entry in entries:
            text = str(entry.get('text', ''))
            if not HANGUL.search(text):
                raise BlindSealError(f'{filename}: seed {seed} generated a non-Hangul '
                                     f'chat message: {text[:60]!r}')
        messages += len(entries)
    return messages


def check_proper_noun_collisions(fixture: dict[str, Any], filename: str,
                                 correction_nouns: Iterable[str],
                                 correction_text: str) -> None:
    text = json.dumps(fixture, ensure_ascii=False)
    for noun in sorted(correction_nouns):
        if noun in text:
            raise BlindSealError(f'{filename}: correction proper noun appears in fixture: {noun}')
    for handle in sorted(fixture_handles(fixture)):
        if handle in correction_text:
            raise BlindSealError(f'{filename}: fixture handle appears in correction data: {handle}')


def check_public_collisions(fixture: dict[str, Any], raw: bytes, filename: str,
                            public_dir: Path) -> None:
    raw_hash = sha256_hex(raw)
    canonical_hash = sha256_hex(canonical_bytes(fixture))
    handles = fixture_handles(fixture)
    for public_name in PUBLIC_FIXTURE_FILES:
        public_path = public_dir / public_name
        public_raw = public_path.read_bytes()
        public_fixture = json.loads(public_raw.decode('utf-8'))
        if raw_hash in (sha256_hex(public_raw), sha256_hex(canonical_bytes(public_fixture))) \
                or canonical_hash in (sha256_hex(public_raw), sha256_hex(canonical_bytes(public_fixture))):
            raise BlindSealError(f'{filename}: hash collides with public fixture {public_name}')
        overlap = handles & fixture_handles(public_fixture)
        if overlap:
            raise BlindSealError(f'{filename}: handle reused from public fixture '
                                 f'{public_name}: {sorted(overlap)[:3]}')


def check_superseded(fixture: dict[str, Any], raw: bytes, filename: str,
                     superseded_roots: Sequence[Path]) -> None:
    raw_hash = sha256_hex(raw)
    canonical_hash = sha256_hex(canonical_bytes(fixture))
    if raw_hash in SUPERSEDED_HASHES or canonical_hash in SUPERSEDED_HASHES:
        raise BlindSealError(f'{filename}: hash matches a superseded (v1/v2) blind fixture')
    text = json.dumps(fixture, ensure_ascii=False)
    for root_id in SUPERSEDED_ROOT_IDS:
        if root_id in text:
            raise BlindSealError(f'{filename}: names a superseded blind root: {root_id}')
    handles = fixture_handles(fixture)
    templates = fixture_templates(fixture)
    for root in superseded_roots:
        for old_name, _role in EXPECTED_FIXTURES:
            old_path = root / old_name
            if not old_path.is_file():
                raise BlindSealError(f'superseded root is incomplete: {old_path}')
            old_fixture = json.loads(old_path.read_bytes().decode('utf-8'))
            old_text = json.dumps(old_fixture, ensure_ascii=False)
            reused_handles = {handle for handle in handles if handle in old_text}
            reused_handles |= handles & fixture_handles(old_fixture)
            if reused_handles:
                raise BlindSealError(f'{filename}: handle reused from superseded root '
                                     f'{root.name}: {sorted(reused_handles)[:3]}')
            reused_templates = templates & fixture_templates(old_fixture)
            if reused_templates:
                raise BlindSealError(f'{filename}: archetype template reused from superseded '
                                     f'root {root.name}: {sorted(reused_templates)[:2]}')


def validate_staging(staging_dir: Path, superseded_roots: Sequence[Path],
                     public_dir: Path | None = None,
                     correction_nouns: Iterable[str] | None = None,
                     correction_text: str | None = None,
                     sim: Any | None = None) -> list[dict[str, Any]]:
    """Validate all three staged fixtures and return their commitment pins."""
    sim = sim if sim is not None else load_broadcast_sim()
    public_dir = public_dir if public_dir is not None else HERE
    if correction_nouns is None:
        correction_nouns = load_correction_proper_nouns()
    if correction_text is None:
        correction_path = HERE.parents[1] / 'training' / 'seed' / 'airi_broadcast_e2_c1_mixture.jsonl'
        if not correction_path.is_file():
            raise BlindSealError(f'correction mixture is unavailable: {correction_path}')
        correction_text = correction_path.read_text(encoding='utf-8')

    entries = sorted(path.name for path in staging_dir.iterdir())
    expected_names = sorted(name for name, _role in EXPECTED_FIXTURES)
    if entries != expected_names:
        raise BlindSealError(f'staging directory must hold exactly {expected_names}, found {entries}')

    all_handles: dict[str, str] = {}
    pins: list[dict[str, Any]] = []
    for filename, role in EXPECTED_FIXTURES:
        raw = (staging_dir / filename).read_bytes()
        try:
            fixture = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BlindSealError(f'{filename}: not valid UTF-8 JSON') from exc
        sim.validate_fixture(fixture)
        check_hangul(fixture, filename)
        check_stream_language(sim, fixture, filename, SEEDS)
        check_proper_noun_collisions(fixture, filename, correction_nouns, correction_text)
        check_public_collisions(fixture, raw, filename, public_dir)
        check_superseded(fixture, raw, filename, superseded_roots)
        for handle in fixture_handles(fixture):
            if handle in all_handles and all_handles[handle] != filename:
                raise BlindSealError(f'handle {handle} appears in both {all_handles[handle]} '
                                     f'and {filename}')
            all_handles[handle] = filename
        pins.append({
            'filename': filename,
            'logical_role': role,
            'size_bytes': len(raw),
            'raw_sha256': sha256_hex(raw),
            'canonical_sha256': sha256_hex(canonical_bytes(fixture)),
        })
    return pins


def seal(staging_dir: Path, output_root: Path, root_id: str,
         superseded_roots: Sequence[Path]) -> dict[str, Any]:
    if not re.fullmatch(r'airi-e2-c2-blind-freeze-[0-9]{8}(-[0-9a-z]+)?', root_id):
        raise BlindSealError(f'root_id does not follow the e2-c2 freeze naming: {root_id}')
    if output_root.exists():
        raise BlindSealError(f'output root already exists (sealing is no-overwrite): {output_root}')
    pins = validate_staging(staging_dir, superseded_roots)

    sealed_manifest = {
        'schema_version': SEALED_SCHEMA_VERSION,
        'root_id': root_id,
        'canonicalization': CANONICALIZATION,
        'fixtures': pins,
        'response_viewed': False,
    }
    sealed_bytes = canonical_bytes(sealed_manifest)
    receipt = {
        'schema_version': RECEIPT_SCHEMA_VERSION,
        'root_id': root_id,
        'sealed_manifest_raw_sha256': sha256_hex(sealed_bytes),
        'validation': {
            'status': 'PASS',
            'fixture_schema_validator': FIXTURE_SCHEMA_VERSION,
            'canonicalization': CANONICALIZATION,
            'fixture_count': len(EXPECTED_FIXTURES),
            'seed_count': len(SEEDS),
            'arm_count': len(ARMS),
            'expected_report_count': len(EXPECTED_FIXTURES) * len(SEEDS) * len(ARMS),
            'public_raw_or_canonical_hash_collision': False,
            'correction_proper_noun_collision': False,
            'superseded_hash_collision': False,
            'body_output': False,
        },
        'language_validation': {'hangul_stream_check': 'pass', 'model_calls': 0},
        'attestation': {
            'blind_bodies_sealed': True,
            'correction_data_path_disjoint': True,
            'old_public_fixture_reused': False,
            'old_report_selection_rationale_reused': False,
            'response_viewed': False,
            'thresholds_frozen': True,
        },
    }

    output_root.mkdir(parents=True, exist_ok=False)
    for filename, _role in EXPECTED_FIXTURES:
        (output_root / filename).write_bytes((staging_dir / filename).read_bytes())
    (output_root / 'sealed_manifest.json').write_bytes(sealed_bytes)
    (output_root / 'validation_receipt.json').write_bytes(canonical_bytes(receipt))

    for pin in pins:
        sealed_raw = (output_root / pin['filename']).read_bytes()
        if sha256_hex(sealed_raw) != pin['raw_sha256'] or len(sealed_raw) != pin['size_bytes']:
            raise BlindSealError(f"sealed copy differs from staging: {pin['filename']}")
    return {
        'root_id': root_id,
        'sealed_manifest_raw_sha256': sha256_hex(sealed_bytes),
        'validation_receipt_raw_sha256': sha256_hex(canonical_bytes(receipt)),
        'fixtures': pins,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Validate and seal the E2-C2 retained blind root')
    parser.add_argument('--staging-dir', type=Path, required=True)
    parser.add_argument('--output-root', type=Path)
    parser.add_argument('--root-id', type=str)
    parser.add_argument('--superseded-root', type=Path, action='append', default=[],
                        help='Consumed blind root to check for content reuse (repeatable)')
    parser.add_argument('--check', action='store_true',
                        help='Validate the staging fixtures without sealing')
    args = parser.parse_args(argv)
    try:
        if args.check:
            pins = validate_staging(args.staging_dir, args.superseded_root)
            print(json.dumps({'status': 'pass', 'fixtures': pins}, ensure_ascii=False, indent=2))
            return 0
        if not args.output_root or not args.root_id:
            parser.error('--output-root and --root-id are required unless --check is used')
        result = seal(args.staging_dir, args.output_root, args.root_id, args.superseded_root)
        print(json.dumps({'status': 'sealed', **result}, ensure_ascii=False, indent=2))
        return 0
    except BlindSealError as exc:
        print(f'SEAL-FAIL: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
