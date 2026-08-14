from __future__ import annotations

import hashlib
import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import run_airi_motif_local_backend as motif


SOURCE_MANIFEST = Path(__file__).parent / "model-usage-manifests" / "motif-2.6b-v1.1-lc.json"


class FakeModel:
    def __init__(self) -> None:
        self.calls: list[tuple[list[dict], dict]] = []

    def generate_text(self, messages: list[dict], options: dict) -> str:
        self.calls.append((messages, options))
        return "hello from fake"


class FakeTorch:
    class _Cuda:
        def __init__(self, parent: "FakeTorch") -> None: self.parent = parent
        def is_available(self) -> bool: return True
        def manual_seed_all(self, seed: int) -> None: self.parent.cuda_seeds.append(seed)
    def __init__(self) -> None:
        self.seeds: list[int] = []; self.cuda_seeds: list[int] = []; self.cuda = self._Cuda(self)
    def manual_seed(self, seed: int) -> None: self.seeds.append(seed)


class MotifLocalBackendTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path]:
        root.mkdir(parents=True, exist_ok=True)
        manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
        snapshot = root / "snapshot"; snapshot.mkdir()
        for index, artifact in enumerate(manifest["artifacts"]):
            payload = ("artifact-%d" % index).encode("ascii")
            target = snapshot / artifact["path"]; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(payload)
            artifact["sha256"] = hashlib.sha256(payload).hexdigest(); artifact["size"] = len(payload)
        by_path = {item["path"]: item for item in manifest["artifacts"]}
        for audit in manifest["remote_code"]["audited_artifacts"]:
            audit["sha256"] = by_path[audit["path"]]["sha256"]; audit["size"] = by_path[audit["path"]]["size"]
        path = root / "manifest.json"; path.write_text(json.dumps(manifest), encoding="utf-8")
        return path, snapshot

    def _backend(self, root: Path) -> tuple[motif.MotifBackend, FakeModel, list]:
        manifest, snapshot = self._fixture(root); calls: list = []; model = FakeModel()
        fake_torch = FakeTorch(); model.fake_torch = fake_torch
        def loader(actual_snapshot, max_memory, quantization):
            calls.append((actual_snapshot, max_memory, quantization)); return model, object(), fake_torch
        return motif.MotifBackend(manifest_path=manifest, snapshot_path=snapshot, gpu_max_mib=6000, cpu_max_gib=8, report_path=root / "audit.json", loader=loader, version_resolver=lambda package: motif.DEPENDENCY_LOCK[package]), model, calls

    def _request(self, port: int, method: str, path: str, body: dict | None = None) -> tuple[int, bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        data = json.dumps(body).encode() if body is not None else None
        connection.request(method, path, body=data, headers={"Content-Type": "application/json"} if data else {})
        response = connection.getresponse(); result = response.status, response.read(); connection.close(); return result

    def test_loopback_identity_and_no_load_before_chat(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            backend, _, calls = self._backend(Path(raw))
            self.assertEqual(motif.TAG, "motif-airi:2.6b-v1.1-lc-nf4")
            self.assertRegex(backend.digest, r"^[0-9a-f]{64}$")
            self.assertEqual(backend.digest, motif.runtime_digest(backend.manifest_canonical_sha256))
            self.assertFalse(calls)
            with self.assertRaisesRegex(motif.MotifBackendError, "127.0.0.1"):
                motif.serve(host="0.0.0.0", port=0, backend=backend)
            report = (Path(raw) / "audit.json").read_text(encoding="utf-8")
            self.assertNotIn(str(Path(raw) / "snapshot"), report)

    def test_contract_streaming_options_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            backend, model, calls = self._backend(Path(raw)); server = motif.serve(host="127.0.0.1", port=0, backend=backend)
            thread = threading.Thread(target=server.serve_forever); thread.start()
            try:
                status, data = self._request(server.server_port, "GET", "/api/tags")
                tags = json.loads(data); self.assertEqual(status, 200); self.assertEqual(tags["models"][0]["digest"], backend.digest); self.assertNotIn("snapshot", data.decode())
                status, data = self._request(server.server_port, "POST", "/api/chat", {"model": motif.TAG, "stream": True, "keep_alive": 0, "messages": [{"role": "user", "content": "hi"}], "options": {"temperature": 0, "top_p": 1, "repeat_penalty": 1}})
                rows = [json.loads(line) for line in data.splitlines()]
                self.assertEqual(status, 200); self.assertEqual(rows[-1]["done"], True); self.assertEqual(rows[-1]["message"]["content"], ""); self.assertEqual(rows[0]["message"]["content"], "hello from fake")
                self.assertIsInstance(rows[-1]["total_duration"], int); self.assertEqual(rows[-1]["eval_count"], 0); self.assertEqual(rows[-1]["prompt_eval_count"], 0); self.assertEqual(rows[-1]["eval_duration"], rows[-1]["total_duration"])
                self.assertEqual(len(calls), 1); self.assertEqual(model.calls[0][1]["do_sample"], False); self.assertIsNone(backend.model)
                status, data = self._request(server.server_port, "GET", "/api/ps")
                self.assertEqual(status, 200); self.assertEqual(json.loads(data)["models"], [])
                status, data = self._request(server.server_port, "POST", "/api/show", {"name": motif.TAG, "keep_alive": 0})
                shown = json.loads(data); self.assertEqual(status, 200); self.assertEqual(shown["model_info"]["runtime"], "transformers-local-nf4-not-ollama-native"); self.assertEqual(shown["digest"], backend.digest)
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def test_invalid_seed_is_explicit_and_does_not_load(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            backend, _, calls = self._backend(Path(raw)); server = motif.serve(host="127.0.0.1", port=0, backend=backend)
            thread = threading.Thread(target=server.serve_forever); thread.start()
            try:
                status, data = self._request(server.server_port, "POST", "/api/chat", {"model": motif.TAG, "messages": [{"role": "user", "content": "hi"}], "options": {"seed": "invalid"}})
                self.assertEqual(status, 400); self.assertIn("seed must", json.loads(data)["error"]); self.assertFalse(calls)
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def test_seed_and_generate_contract(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            backend, model, _ = self._backend(Path(raw)); server = motif.serve(host="127.0.0.1", port=0, backend=backend)
            thread = threading.Thread(target=server.serve_forever); thread.start()
            try:
                status, data = self._request(server.server_port, "POST", "/api/generate", {"model": motif.TAG, "prompt": "safe prompt", "stream": False, "options": {"seed": 7, "num_ctx": 2048, "num_predict": 4}})
                value = json.loads(data)
                self.assertEqual(status, 200); self.assertEqual(value["response"], "hello from fake"); self.assertEqual(value["eval_count"], 0); self.assertEqual(value["seed"], 7)
                self.assertEqual(model.fake_torch.seeds, [7]); self.assertEqual(model.fake_torch.cuda_seeds, [7])
                status, data = self._request(server.server_port, "POST", "/api/generate", {"prompt": "x", "options": {"seed": -1}})
                self.assertEqual(status, 400); self.assertIn("seed must", json.loads(data)["error"])
                status, data = self._request(server.server_port, "POST", "/api/chat", {"messages": [{"role": "user", "content": "x"}], "options": {"num_ctx": 4, "num_predict": 5}})
                self.assertEqual(status, 400); self.assertIn("num_predict exceeds", json.loads(data)["error"])
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def test_option_allowlist_num_gpu_think_and_format(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            backend, model, _ = self._backend(Path(raw)); server = motif.serve(host="127.0.0.1", port=0, backend=backend)
            thread = threading.Thread(target=server.serve_forever); thread.start()
            try:
                valid = {"messages": [{"role": "user", "content": "hi"}], "think": False, "format": None, "options": {"num_gpu": 999, "num_predict": 2}}
                status, _ = self._request(server.server_port, "POST", "/api/chat", valid)
                self.assertEqual(status, 200); self.assertEqual(model.calls[-1][1]["max_new_tokens"], 2)
                for extra, expected in (({"options": {"unknown": 1}}, "unsupported option"), ({"options": {"num_gpu": 1}}, "num_gpu must"), ({"think": True}, "unsupported think"), ({"format": "json"}, "unsupported format")):
                    status, data = self._request(server.server_port, "POST", "/api/chat", {"messages": [{"role": "user", "content": "hi"}], **extra})
                    self.assertEqual(status, 400); self.assertIn(expected, json.loads(data)["error"])
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def test_snapshot_failure_happens_before_loader_and_report_has_no_path(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); manifest, snapshot = self._fixture(root); (snapshot / "config.json").write_bytes(b"changed")
            loaded = []
            with self.assertRaisesRegex(motif.MotifBackendError, "hash mismatch"):
                motif.MotifBackend(manifest_path=manifest, snapshot_path=snapshot, loader=lambda *_: loaded.append(True))
            self.assertEqual(loaded, [])

    def test_snapshot_rejects_unlisted_file_before_loader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); manifest, snapshot = self._fixture(root)
            (snapshot / "unlisted_module.py").write_text("raise RuntimeError('must not import')", encoding="utf-8")
            loaded = []
            with self.assertRaisesRegex(motif.MotifBackendError, "artifact set is not exact"):
                motif.MotifBackend(manifest_path=manifest, snapshot_path=snapshot, loader=lambda *_: loaded.append(True))
            self.assertEqual(loaded, [])

    def test_separate_loopback_port_is_the_cli_default(self) -> None:
        self.assertEqual(motif.DEFAULT_PORT, 11437)

    def test_audited_code_and_dependency_lock_fail_closed_before_loader(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); manifest, snapshot = self._fixture(root)
            value = json.loads(manifest.read_text(encoding="utf-8")); value["remote_code"]["audited_artifacts"][0]["size"] += 1; manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(motif.MotifBackendError, "identically pinned"):
                motif.MotifBackend(manifest_path=manifest, snapshot_path=snapshot, loader=lambda *_: self.fail("must not load"), version_resolver=lambda package: motif.DEPENDENCY_LOCK[package])
            manifest, snapshot = self._fixture(root / "second")
            backend = motif.MotifBackend(manifest_path=manifest, snapshot_path=snapshot, loader=lambda *_: self.fail("must not load"), version_resolver=lambda _package: "wrong")
            with self.assertRaisesRegex(motif.MotifBackendError, "pinned lock"):
                backend.chat({"messages": [{"role": "user", "content": "P5 compatible request"}]})


if __name__ == "__main__":
    unittest.main()
