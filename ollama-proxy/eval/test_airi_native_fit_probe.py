from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_airi_native_fit_probe import _candidate_options, _verify_snapshot, run_probe


ROOT = Path(__file__).parent
MANIFEST = ROOT / "model-usage-manifests" / "midm-2.0-mini-instruct.json"


class NativeFitPreflightTests(unittest.TestCase):
    def _minimal_manifest(self, directory: Path, *, remote: bool = False, candidate: str = "midm-2.0-mini-instruct") -> tuple[dict, Path]:
        source = json.loads(MANIFEST.read_text(encoding="utf-8")); source["candidate_id"] = candidate
        if candidate != "midm-2.0-mini-instruct": source["repo_id"] = "unsupported/repo"
        payload = b"small"; digest = hashlib.sha256(payload).hexdigest()
        source["artifacts"] = [{"path": "config.json", "kind": "repository_file", "source_url": f"https://huggingface.co/K-intelligence/Midm-2.0-Mini-Instruct/resolve/{source['exact_revision']}/config.json", "sha256": digest, "size": len(payload), "method": "downloaded_sha256"}, {"path": "model.safetensors", "kind": "weight", "source_url": f"https://huggingface.co/K-intelligence/Midm-2.0-Mini-Instruct/resolve/{source['exact_revision']}/model.safetensors", "sha256": digest, "size": len(payload), "method": "huggingface_lfs_sha256"}]
        snapshot = directory / "snapshot"; snapshot.mkdir(); (snapshot / "config.json").write_bytes(payload); (snapshot / "model.safetensors").write_bytes(payload)
        source["remote_code"]["required"] = remote
        if remote:
            code = b"# audited\n"; code_hash = hashlib.sha256(code).hexdigest()
            (snapshot / "modeling_test.py").write_bytes(code)
            source["remote_code"]["audited_artifacts"] = [{"path": "modeling_test.py", "kind": "repository_file", "source_url": f"https://huggingface.co/K-intelligence/Midm-2.0-Mini-Instruct/resolve/{source['exact_revision']}/modeling_test.py", "sha256": code_hash, "size": len(code), "method": "downloaded_sha256"}]
        path = directory / "manifest.json"; path.write_text(json.dumps(source), encoding="utf-8")
        return source, path

    def test_snapshot_detects_mutated_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw); manifest, _ = self._minimal_manifest(directory)
            (directory / "snapshot" / "config.json").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                _verify_snapshot(manifest, directory / "snapshot")

    def test_options_are_candidate_specific(self) -> None:
        midm, basis, thinking = _candidate_options("midm-2.0-mini-instruct")
        self.assertEqual(midm["top_k"], 20); self.assertEqual(basis, "official_manifest_generation_defaults"); self.assertFalse(thinking)
        granite, basis, thinking = _candidate_options("granite-3.3-2b-instruct")
        self.assertEqual(granite, {"do_sample": False}); self.assertEqual(basis, "transformers_greedy_default_due_official_unknown"); self.assertTrue(thinking)

    def test_remote_code_refusal_writes_content_free_atomic_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw); _, manifest = self._minimal_manifest(directory, remote=True); report = directory / "out.json"
            result = run_probe(manifest_path=manifest, snapshot_path=directory / "snapshot", report_path=report, gpu_max_mib=1, cpu_max_gib=1)
            saved = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "error"); self.assertIn("remote-code-required", saved["error"])
            self.assertNotIn(str(directory / "snapshot"), report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
