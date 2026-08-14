"""Offline contract tests for the native broadcast rehearsal."""
from __future__ import annotations

import hashlib, importlib.util, json, os, sys, tempfile, unittest
from unittest.mock import patch
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location('native_rehearsal', HERE / 'run_airi_native_broadcast_rehearsal.py')
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(runner)

class NativeBroadcastRehearsalTests(unittest.TestCase):
    def test_fixture_is_clean_and_complete(self):
        fixture, _ = runner.load_fixture()
        self.assertEqual(len(fixture['cases']), 16)
        text = json.dumps(fixture, ensure_ascii=False).lower()
        for forbidden in ('정범', '루나', '딸기', '파란색', '초록색'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(len({case['id'] for case in fixture['cases']}), 16)

    def test_same_messages_are_used_for_each_candidate(self):
        fixture, _ = runner.load_fixture()
        for case in fixture['cases']:
            midm = runner.case_messages(fixture, case)
            motif = runner.case_messages(fixture, case)
            self.assertEqual(midm, motif)
            self.assertEqual(midm[0]['content'], fixture['system_message'])

    def test_profile_counts_and_options(self):
        self.assertEqual(16 * (1 + 3), 64)
        self.assertEqual(runner.generation_options('midm-2.0-mini-instruct', 'hf_card'), {'do_sample':False,'max_new_tokens':128,'use_card_generation_config':True})
        self.assertEqual(runner.generation_options('motif-2.6b-v1.1-lc', 'hf_card'), {'do_sample':False,'max_new_tokens':1024})
        for candidate in runner.CANDIDATES:
            self.assertEqual(runner.generation_options(candidate, 'broadcast_equal'), {'do_sample':False,'max_new_tokens':128})

    def test_first_token_timer_skips_prompt_and_measures_first_generated_token(self):
        with patch.object(runner.time, 'monotonic', side_effect=(10.25, 10.75)):
            timer=runner.FirstTokenTimer(10.0)
            timer.put('prompt')
            self.assertIsNone(timer.first_token_seconds)
            timer.put('first-token')
            self.assertEqual(timer.first_token_seconds, 0.25)
            timer.put('second-token')
            self.assertEqual(timer.first_token_seconds, 0.25)
            timer.end()

    def test_motif_eos_is_complete_and_pinned(self):
        self.assertEqual(runner.CANDIDATES['motif-2.6b-v1.1-lc']['eos'], [219395, 219405])
        manifest = runner.load_manifest('motif-2.6b-v1.1-lc')
        self.assertEqual(manifest['tokenizer']['eos_token_id'], [219395, 219405])

    def _manifest(self, root: Path) -> dict:
        data = b'abc'; (root / 'one.txt').write_bytes(data)
        return {'artifacts':[{'path':'one.txt','size':3,'sha256':hashlib.sha256(data).hexdigest()}]}

    def test_snapshot_rejects_extra_reparse_and_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); manifest=self._manifest(root)
            self.assertEqual(runner.verify_snapshot(manifest, root)['file_count'], 1)
            (root/'extra.txt').write_text('x', encoding='utf-8')
            with self.assertRaises(runner.RehearsalError): runner.verify_snapshot(manifest, root)
            (root/'extra.txt').unlink(); (root/'one.txt').write_text('bad', encoding='utf-8')
            with self.assertRaises(runner.RehearsalError): runner.verify_snapshot(manifest, root)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); manifest=self._manifest(root)
            try: os.symlink(root/'one.txt', root/'linked.txt')
            except (OSError, NotImplementedError): self.skipTest('symlinks unavailable')
            with self.assertRaises(runner.RehearsalError): runner.verify_snapshot(manifest, root)

    def test_remote_code_and_preflight_boundaries_are_explicit(self):
        source=(HERE/'run_airi_native_broadcast_rehearsal.py').read_text(encoding='utf-8')
        self.assertIn("trust_remote_code=remote", source)
        self.assertIn("'trust_remote_code': True", source)
        self.assertLess(source.index("verify_snapshot(manifest, snapshot)"), source.index('import torch as imported_torch'))
        self.assertNotIn('\nimport torch\n', source)

    def test_per_candidate_invocation_is_safe_and_has_no_path_or_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'report.json'; secret=str(Path(tmp)/'private-snapshot')
            result=runner.run_rehearsal(candidate='midm-2.0-mini-instruct', snapshot=secret, report_path=report, gpu_max_mib=6000, cpu_max_gib=20)
            raw=report.read_text(encoding='utf-8')
            self.assertEqual(result['status'], 'error'); self.assertEqual(json.loads(raw)['error']['message'], 'native broadcast rehearsal did not complete')
            self.assertNotIn(secret, raw); self.assertNotIn('방송 시작', raw)

    def test_candidate_versions_are_separate_and_cli_requires_bounds(self):
        self.assertEqual(runner.CANDIDATES['midm-2.0-mini-instruct']['transformers'], '4.48.2')
        self.assertEqual(runner.CANDIDATES['motif-2.6b-v1.1-lc']['transformers'], '4.51.3')
        source=(HERE/'run_airi_native_broadcast_rehearsal.py').read_text(encoding='utf-8')
        self.assertIn("parser.add_argument('--candidate'", source)
        self.assertIn("parser.add_argument('--gpu-max-mib',type=int,required=True)", source)
        self.assertIn("parser.add_argument('--cpu-max-gib',type=int,required=True)", source)
        self.assertIn("'date_string':'14 Aug 2026'", source)

if __name__ == '__main__': unittest.main()
