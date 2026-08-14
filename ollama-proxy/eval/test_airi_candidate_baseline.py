from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_airi_candidate_baseline import RunnerError, run_baseline


HERE = Path(__file__).parent
DIGEST = "b" * 64


class FakeTransport:
    def __init__(self, *, digest: str = DIGEST) -> None:
        self.digest, self.loaded, self.calls = digest, True, []

    def __call__(self, method: str, url: str, body: dict | None):
        self.calls.append((method, url, body))
        if url.endswith("/api/tags"): return {"models": [{"name": "candidate:test", "digest": self.digest}]}
        if url.endswith("/api/show"): return {"digest": self.digest, "template": "template", "parameters": "parameters", "modelfile": "FROM C:\\private", "details": {"family": "qwen"}}
        if url.endswith("/api/ps"): return {"models": [{"name": "candidate:test"}]} if self.loaded else {"models": []}
        if url.endswith("/api/generate"): self.loaded = False; return {"done": True}
        return iter(({"model": "candidate:test", "message": {"content": "ok"}}, {"model": "candidate:test", "message": {"content": "!"}, "done": True, "eval_count": 2, "eval_duration": 100000000}))


class CandidateBaselineTests(unittest.TestCase):
    def _manifest(self, folder: Path) -> Path:
        path = folder / "manifest.json"; path.write_bytes((HERE / "model-usage-manifests" / "qwen3-4b.json").read_bytes()); return path

    def test_exact_digest_and_16_by_3_stream_contract_is_content_free(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw); fake = FakeTransport(); output = folder / "report.json"
            result = run_baseline(manifest_path=self._manifest(folder), model="candidate:test", expected_digest=DIGEST, report_path=output, transport=fake)
            saved = json.loads(output.read_text(encoding="utf-8"))
            chats = [body for _, url, body in fake.calls if url.endswith("/api/chat")]
            self.assertEqual(result["status"], "complete"); self.assertEqual(len(chats), 48); self.assertEqual(len(saved["cases"]), 16)
            self.assertTrue(all(body["stream"] is True and body["options"] == {"num_ctx": 2048, "temperature": 0, "seed": 42, "num_predict": 256} and body["think"] is False for body in chats))
            self.assertEqual(saved["cases"][0]["runs"][0]["response"]["char_count"], 3); self.assertTrue(saved["cleanup"]["unloaded"])
            raw_report = output.read_text(encoding="utf-8"); self.assertNotIn("ok!", raw_report); self.assertNotIn("C:\\private", raw_report)

    def test_digest_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(RunnerError): run_baseline(manifest_path=self._manifest(Path(raw)), model="candidate:test", expected_digest=DIGEST, report_path=Path(raw) / "report.json", transport=FakeTransport(digest="c" * 64))

    def test_atomic_error_report_on_missing_stream_terminal(self) -> None:
        class Broken(FakeTransport):
            def __call__(self, method, url, body):
                if url.endswith("/api/chat"): return iter(({"message": {"content": "hidden"}},))
                return super().__call__(method, url, body)
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw); output = folder / "report.json"
            result = run_baseline(manifest_path=self._manifest(folder), model="candidate:test", expected_digest=DIGEST, report_path=output, transport=Broken())
            self.assertEqual(result["status"], "error"); self.assertTrue(output.exists()); self.assertIn("without done", result["error"])


if __name__ == "__main__":
    unittest.main()
