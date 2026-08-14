from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from model_usage_manifest import canonical_sha256
from run_airi_model_fit_probe import ProbeError, run_probe


ROOT = Path(__file__).parent
SOURCE_MANIFEST = ROOT / "model-usage-manifests" / "qwen3-4b.json"
DIGEST = "a" * 64


class FakeTransport:
    def __init__(self, *, loaded: bool = True, bad_generation: bool = False) -> None:
        self.loaded, self.bad_generation, self.requests = loaded, bad_generation, []

    def __call__(self, method: str, url: str, body: dict | None) -> dict:
        self.requests.append((method, url, body))
        if url.endswith("/api/version"): return {"version": "0.test"}
        if url.endswith("/api/tags"): return {"models": [{"name": "test:model", "digest": DIGEST, "size": 1}]}
        if url.endswith("/api/show"): return {"digest": DIGEST, "template": "x", "parameters": "y", "modelfile": "FROM C:\\secret"}
        if url.endswith("/api/ps"): return {"models": [{"name": "test:model", "details": {"family": "test", "parent_model": "C:\\secret"}}]} if self.loaded else {"models": []}
        if body and body.get("keep_alive") == 0: self.loaded = False; return {"done": True}
        if self.bad_generation: return {"model": "wrong", "done": False, "response": "secret"}
        return {"model": "test:model", "done": True, "response": "안녕", "eval_count": 2, "eval_duration": 100000000}


class FitProbeTests(unittest.TestCase):
    def _manifest(self, directory: Path) -> Path:
        target = directory / "manifest.json"; target.write_bytes(SOURCE_MANIFEST.read_bytes()); return target

    def test_rejects_external_endpoint_and_digest(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = self._manifest(Path(raw))
            with self.assertRaises(ProbeError): run_probe(manifest_path=path, model="test:model", expected_digest=DIGEST, endpoint="http://example.com:11434", report_path=Path(raw) / "out.json")
            with self.assertRaises(ProbeError): run_probe(manifest_path=path, model="test:model", expected_digest="bad", report_path=Path(raw) / "out.json")

    def test_complete_content_free_hashes_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw); manifest = self._manifest(directory); report_path = directory / "out.json"; fake = FakeTransport()
            result = run_probe(manifest_path=manifest, model="test:model", expected_digest=DIGEST, report_path=report_path, transport=fake, run=lambda _: "GPU, 1, 10, 2, 8")
            saved = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "complete"); self.assertTrue(saved["cleanup"]["unloaded"])
            self.assertEqual(saved["manifest"]["file_sha256"], hashlib.sha256(manifest.read_bytes()).hexdigest())
            self.assertEqual(saved["manifest"]["canonical_sha256"], canonical_sha256(json.loads(manifest.read_text())))
            self.assertNotIn("안녕", report_path.read_text(encoding="utf-8")); self.assertNotIn("C:\\secret", report_path.read_text(encoding="utf-8"))
            request = next(body for _, url, body in fake.requests if url.endswith("/api/generate") and body and "options" in body)
            self.assertEqual(request["options"], {"num_ctx": 2048, "temperature": 0, "seed": 42, "num_predict": 64})
            self.assertTrue(request["stream"])

    def test_incomplete_response_is_error_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw); report_path = directory / "out.json"
            result = run_probe(manifest_path=self._manifest(directory), model="test:model", expected_digest=DIGEST, report_path=report_path, transport=FakeTransport(bad_generation=True))
            self.assertEqual(result["status"], "error"); self.assertIn("generation response", result["error"])


if __name__ == "__main__":
    unittest.main()
