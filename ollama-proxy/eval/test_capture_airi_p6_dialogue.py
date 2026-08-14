from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from capture_airi_p6_dialogue import PROMPTS, CaptureError, _proxy_transport, capture_dialogue
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


class Response:
    def __init__(self, payload=b"{}", chunks=()): self.payload = payload; self.chunks = chunks
    def __enter__(self): return self
    def __exit__(self, *unused): return False
    def read(self): return self.payload
    def __iter__(self): return iter(self.chunks)


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
            with self.assertRaisesRegex(CaptureError, "nonpersistent"):
                capture_dialogue(manifest_path=MANIFEST, output_path=target, profile="common", model="test:model", expected_digest=DIGEST, mode="proxy", transport=fake, proxy_test_origin=True)

    def test_proxy_transport_parses_sse_and_uses_configured_ollama(self) -> None:
        responses = [
            Response(json.dumps({"chat_model": {"model": "test:model"}}).encode()),
            Response(json.dumps({"models": [{"name": "test:model", "digest": DIGEST}]}).encode()),
            Response(chunks=(
                b'data: {"choices":[{"delta":{"content":"hello "}}]}\n\n',
                b'data: {"choices":[{"delta":{"content":"world"}}]}\n\n',
            )),
        ]
        with patch("capture_airi_p6_dialogue.urllib.request.urlopen", side_effect=responses) as opened:
            provenance = _proxy_transport("http://127.0.0.1:11438/v1/chat/completions", {"model": "test:model", "messages": [], "options": {"airi_p6_provenance_only": True}}, ollama_endpoint="http://127.0.0.1:11437/api/tags")
            result = _proxy_transport("http://127.0.0.1:11438/v1/chat/completions", {"model": "test:model", "messages": [{"role": "user", "content": "x"}]}, ollama_endpoint="http://127.0.0.1:11437/api/tags")
        self.assertEqual(provenance["digest"], DIGEST)
        self.assertEqual(result["message"]["content"], "hello world")
        self.assertEqual(opened.call_args_list[1].args[0], "http://127.0.0.1:11437/api/tags")
        request = opened.call_args_list[2].args[0]
        self.assertTrue(json.loads(request.data.decode())["stream"])
        self.assertEqual(request.get_header("Accept"), "text/event-stream")

    def test_proxy_endpoint_safety_and_assertions(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "capture.json"; fake = FakeTransport()
            capture_dialogue(manifest_path=MANIFEST, output_path=target, profile="common", model="test:model", expected_digest=DIGEST, endpoint="http://127.0.0.1:11438/v1/chat/completions", ollama_endpoint="http://127.0.0.1:11437/api/tags", mode="proxy", transport=fake, proxy_test_origin=True, proxy_nonpersistent=True)
            self.assertTrue(all(call["stream"] is True for call in fake.calls[1:]))
            with self.assertRaisesRegex(CaptureError, "literal loopback"):
                capture_dialogue(manifest_path=MANIFEST, output_path=target, profile="common", model="test:model", expected_digest=DIGEST, endpoint="http://example.com:11438/v1/chat/completions", mode="proxy", transport=fake, proxy_test_origin=True, proxy_nonpersistent=True)
            with self.assertRaisesRegex(CaptureError, "literal loopback"):
                capture_dialogue(manifest_path=MANIFEST, output_path=target, profile="common", model="test:model", expected_digest=DIGEST, endpoint="http://127.0.0.1:11438/v1/chat/completions", ollama_endpoint="http://example.com:11437/api/tags", mode="proxy", transport=fake, proxy_test_origin=True, proxy_nonpersistent=True)


if __name__ == "__main__":
    unittest.main()
