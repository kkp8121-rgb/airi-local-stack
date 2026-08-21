import hashlib
import importlib.util
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


MODULE = Path(__file__).with_name('full_stack_broadcast_gate.py')
SPEC = importlib.util.spec_from_file_location('full_stack_broadcast_gate', MODULE)
gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gate)

DIGEST = 'a' * 64


def bundle():
    common = lambda run: {'run_id': run, 'captured_at': '2026-08-21T00:00:00Z', 'model_digest': DIGEST}
    runtime = common('runtime-run') | {'evidence': {
        'before_health_sha256': '1' * 64, 'after_health_sha256': '2' * 64, 'chat_model': 'airi-local', 'chat_digest': DIGEST,
        'memory': {'enabled': True, 'ready': True, 'retrieval_delta': 1, 'journal_delta': 1},
        'knowledge': {'enabled': True, 'ready': True, 'retrieval_delta': 1, 'relevant_retrieval_delta': 1},
        'continuity_observation_delta': 1, 'broadcast_contract_on': True,
        'memory_claim_guard_on': True, 'immediate_ack_marker': True,
        'character_state_session_delta': 1,
        'show_arc': {'enabled': True, 'ready': True, 'seed_delta': 3, 'callback_delta': 6},
        'affect': {'enabled': True, 'ready': True, 'event_delta': 1, 'snapshot_delta': 1, 'expression_delta': 1},
        'input_safety_state': 'enabled_ready', 'output_safety_state': 'enabled_ready'}}
    broadcast = common('broadcast-run') | {'evidence': {
        'duration_minutes': 180, 'seeds': [{'seed_id': 'one', 'turns': 500, 'arcs': 12}, {'seed_id': 'two', 'turns': 500, 'arcs': 12}, {'seed_id': 'three', 'turns': 500, 'arcs': 12}],
        'callback_gaps_minutes': [90] * 6, 'complete_arc_recall': .90,
        'wrong_or_forbidden_callbacks': 0, 'cross_show_leakage': 0,
        'self_led_initiative': .30, 'cta_rate': .45, 'meta_leaks': 0}}
    training = common('training-run') | {'evidence': {
        'cuda': True, 'base_digest': 'b' * 64, 'adapter_digest': 'c' * 64,
        'export_digest': 'd' * 64, 'dataset_digest': 'e' * 64,
        'dataset_reviewed_airi_original': True,
        'splits': {'train_rows': 200, 'dev_rows': 1, 'test_rows': 1, 'group_leakage': 0, 'duplicate_targets': 0, 'heldout_reference_overlap': 0},
        'official_transcript_training': False, 'qlora_metrics': {'loss': 0.1}}}
    tts = common('tts-run') | {'evidence': {
        'engine': 'GPT-SoVITS v2ProPlus', 'first_4096_byte_ms': [800] * 7,
        'playback_start_evidence': True, 'render_evidence': True,
        'latency_spans_ms': {'llm_start': 1, 'llm_content': 2, 'llm_end': 3, 'tts_start': 4, 'tts_first': 5, 'tts_end': 6}}}
    safety = common('safety-run') | {'evidence': {
        'prerequisites_closed': False, 'user_approved': False, 'greybox_span': False,
        'greybox_taxonomy': False, 'greybox_alias': False, 'greybox_briefing_evidence': False,
        'external_services': False, 'training_artifact_promotion': False, 'user_approval': False}}
    return {'runtime_activation': runtime, 'long_broadcast': broadcast, 'model_training': training, 'tts_latency': tts, 'safety_activation': safety}


def write_bundle(folder, values, mutate_manifest=None):
    artifacts = []
    for category, value in values.items():
        relative = category + '.json'
        raw = json.dumps(value, allow_nan=True).encode()
        (folder / relative).write_bytes(raw)
        artifacts.append({'category': category, 'path': relative, 'sha256': hashlib.sha256(raw).hexdigest(),
                          'run_id': value['run_id'], 'captured_at': value['captured_at'], 'model_digest': DIGEST})
    manifest = {'schema_version': gate.SCHEMA_VERSION, 'model_digest': DIGEST, 'artifacts': artifacts}
    if mutate_manifest:
        mutate_manifest(manifest)
    target = folder / 'manifest.json'
    target.write_text(json.dumps(manifest), encoding='utf-8')
    return target


class FullStackBroadcastGateTests(unittest.TestCase):
    def validate(self, values=None, mutate_manifest=None):
        with tempfile.TemporaryDirectory() as temp:
            report = gate.validate_manifest(write_bundle(Path(temp), values or bundle(), mutate_manifest))
        return report

    def test_valid_synthetic_bundle_passes(self):
        self.assertTrue(self.validate()['pass'])

    def test_missing_required_category_fails(self):
        values = bundle(); del values['tts_latency']
        report = self.validate(values)
        self.assertFalse(report['pass'])

    def test_unwired_runtime_fails(self):
        values = bundle(); values['runtime_activation']['evidence']['memory']['ready'] = False
        self.assertFalse(self.validate(values)['pass'])

    def test_missing_latency_telemetry_fails(self):
        values = bundle(); values['tts_latency']['evidence']['latency_spans_ms']['tts_first'] = 0
        self.assertFalse(self.validate(values)['pass'])

    def test_short_run_fails(self):
        values = bundle(); values['long_broadcast']['evidence']['duration_minutes'] = 179
        self.assertFalse(self.validate(values)['pass'])

    def test_premature_greybox_activation_fails(self):
        values = bundle(); values['safety_activation']['evidence']['greybox_span'] = True
        self.assertFalse(self.validate(values)['pass'])

    def test_digest_mismatch_fails(self):
        values = bundle(); values['runtime_activation']['model_digest'] = 'f' * 64
        self.assertFalse(self.validate(values)['pass'])

    def test_nan_fails(self):
        values = bundle(); values['model_training']['evidence']['qlora_metrics']['loss'] = float('nan')
        self.assertFalse(self.validate(values)['pass'])

    def test_reused_artifact_fails(self):
        def reuse(manifest):
            manifest['artifacts'][1]['path'] = manifest['artifacts'][0]['path']
            manifest['artifacts'][1]['sha256'] = manifest['artifacts'][0]['sha256']
        self.assertFalse(self.validate(mutate_manifest=reuse)['pass'])

    def test_path_traversal_fails(self):
        def traversal(manifest):
            manifest['artifacts'][0]['path'] = '../runtime_activation.json'
        report = self.validate(mutate_manifest=traversal)
        self.assertEqual(report['failures'][0]['code'], 'artifact_path_outside_bundle')

    def test_symlink_artifact_fails_when_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            manifest_path = write_bundle(folder, bundle())
            target = folder / 'linked.json'
            try:
                target.symlink_to(folder / 'runtime_activation.json')
            except (OSError, NotImplementedError):
                self.skipTest('symlinks are unavailable on this platform')
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            manifest['artifacts'][0]['path'] = 'linked.json'
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            self.assertEqual(gate.validate_manifest(manifest_path)['failures'][0]['code'], 'artifact_path_outside_bundle')

    def test_duplicate_seed_fails(self):
        values = bundle(); values['long_broadcast']['evidence']['seeds'][2]['seed_id'] = 'one'
        self.assertFalse(self.validate(values)['pass'])

    def test_unchanged_health_digests_fail(self):
        values = bundle(); values['runtime_activation']['evidence']['after_health_sha256'] = '1' * 64
        self.assertFalse(self.validate(values)['pass'])

    def test_disabled_safety_state_fails(self):
        values = bundle(); values['runtime_activation']['evidence']['input_safety_state'] = 'disabled'
        self.assertFalse(self.validate(values)['pass'])

    def test_training_leakage_fails(self):
        values = bundle(); values['model_training']['evidence']['splits']['group_leakage'] = 1
        self.assertFalse(self.validate(values)['pass'])

    def test_report_never_echoes_raw_content_or_path(self):
        values = bundle(); values['long_broadcast']['evidence']['duration_minutes'] = 1
        report = self.validate(values)
        self.assertNotIn('broadcast-run', json.dumps(report))
        self.assertNotIn('.json', json.dumps(report))


if __name__ == '__main__':
    unittest.main()
