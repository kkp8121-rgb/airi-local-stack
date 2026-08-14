from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from capture_airi_p6_dialogue import PROMPTS, CaptureError, capture_dialogue
from build_airi_p6_review_packet import CAPTURE_SCHEMA_VERSION


ROOT = Path(__file__).parent
MANIFEST = ROOT / "model-usage-manifests" / "midm-2.0-mini-instruct.json"
DIGEST = "a" * 64


class FakeTransport:
    def __init__(self) -> None: self.calls = []
    def __call__(self, endpoint, body):
        self.calls.append(body)
        if body["messages"] == []: return {"model": "test:model", "digest": DIGEST}
        return {"done": True, "message": {"content": "안녕하세요. 오늘도 즐거운 방송이에요."}}


class CaptureP6Tests(unittest.TestCase):
    def test_native_requires_pinned_snapshot_bounds_before_imports(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "capture.json"
            with self.assertRaisesRegex(CaptureError, "requires snapshot"):
                capture_dialogue(manifest_path=MANIFEST, output_path=target, profile="native")

    def test_unsupported_native_candidate_is_explicitly_unrunnable(self) -> None:
        other = ROOT / "model-usage-manifests" / "qwen3-4b.json"
        with tempfile.TemporaryDirectory() as raw:
            result = capture_dialogue(manifest_path=other, output_path=Path(raw) / "capture.json", profile="native")
            self.assertEqual(result["status"], "unrunnable")
            self.assertEqual(result["reasons"], ["NATIVE_CANDIDATE_UNSUPPORTED"])

    def test_native_snapshot_fails_before_transformers_load(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw); snapshot = directory / "snapshot"; snapshot.mkdir()
            with self.assertRaisesRegex(CaptureError, "snapshot preflight"):
                capture_dialogue(manifest_path=MANIFEST, output_path=directory / "capture.json", profile="native", snapshot_path=snapshot, gpu_max_mib=1, cpu_max_gib=1)

    def test_common_runs_exactly_twenty_benign_turns(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fake = FakeTransport(); target = Path(raw) / "capture.json"
            result = capture_dialogue(manifest_path=MANIFEST, output_path=target, profile="common", model="test:model", expected_digest=DIGEST, transport=fake)
            self.assertEqual(result["status"], "actually_run"); self.assertEqual(len(result["turns"]), 20); self.assertEqual(result["turns"][0]["prompt"], PROMPTS[0])
            self.assertEqual(len(fake.calls), 21); self.assertEqual(json.loads(target.read_text(encoding="utf-8")), result)

    def test_mismatched_digest_and_proxy_semantics_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "capture.json"; fake = FakeTransport()
            with self.assertRaisesRegex(CaptureError, "digest"):
                capture_dialogue(manifest_path=MANIFEST, output_path=target, profile="common", model="test:model", expected_digest="b" * 64, transport=fake)
            with self.assertRaisesRegex(CaptureError, "test-origin"):
                capture_dialogue(manifest_path=MANIFEST, output_path=target, profile="common", model="test:model", expected_digest=DIGEST, mode="proxy", transport=fake)


if __name__ == "__main__":
    unittest.main()
