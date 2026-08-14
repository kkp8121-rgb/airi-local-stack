"""Offline regression tests for model_usage_manifest."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from model_usage_manifest import (CANDIDATES, SCHEMA_VERSION, ManifestValidationError,
                                  canonical_sha256, validate_complete_set, validate_manifest)


def manifest(candidate_id="qwen3-4b"):
    repo_id = CANDIDATES[candidate_id]
    artifact = {"path": "config.json", "kind": "config", "source_url": f"https://huggingface.co/{repo_id}/resolve/{'a' * 40}/config.json", "sha256": "b" * 64, "size": 1, "method": "snapshot_download"}
    return {"schema_version": SCHEMA_VERSION, "candidate_id": candidate_id, "repo_id": repo_id, "exact_revision": "a" * 40, "retrieved_at": "2026-08-13T00:00:00Z", "official_model_info": f"https://huggingface.co/api/models/{repo_id}", "license": {"declared": "Apache-2.0", "license_files": ["LICENSE"], "notice": "unknown", "public_broadcast_status": "allowed", "evaluation_allowed": True}, "libraries": {"transformers": "4.51.0", "torch": "unknown", "accelerate": "unknown", "minimums": {"transformers": "4.51.0"}}, "remote_code": {"required": False, "audited_artifacts": [], "findings": {"imports": "not required", "network": "not required", "shell": "not required", "telemetry": "not required", "filesystem": "not required", "dynamic_execution": "not required", "serialization": "not required"}}, "tokenizer": {"chat_template": "known"}, "template": {"add_generation_prompt": True}, "system_role": {"supported": True}, "thinking": {"default": False}, "generation": {"temperature": 0}, "context": {"num_ctx": 2048}, "runtime": {"dtype": "unknown"}, "quantization": {"path": "unknown"}, "engine_support": {"ollama": "unknown"}, "artifacts": [artifact], "status": "READY", "reasons": [], "profiles": {"native": {"supported_options": {"temperature": 0}, "unsupported": ["top_k"]}, "common": {"supported_options": {"seed": 42}, "unsupported": []}}}


class ModelUsageManifestTests(unittest.TestCase):
    def test_valid_and_canonical_order(self):
        first = manifest()
        second = dict(reversed(list(first.items())))
        self.assertEqual(validate_manifest(first)["candidate_id"], "qwen3-4b")
        self.assertEqual(canonical_sha256(first), canonical_sha256(second))

    def test_rejects_mutable_revision_duplicate_and_unknown_fields(self):
        bad = manifest(); bad["exact_revision"] = "main"
        with self.assertRaises(ManifestValidationError): validate_manifest(bad)
        duplicate = [manifest(), manifest()]
        with self.assertRaises(ManifestValidationError): validate_complete_set(duplicate)
        bad = manifest(); bad["surprise"] = True
        with self.assertRaises(ManifestValidationError): validate_manifest(bad)

    def test_remote_code_and_profile_collision_are_rejected(self):
        bad = manifest(); bad["remote_code"]["required"] = True
        with self.assertRaises(ManifestValidationError): validate_manifest(bad)

    def test_complete_set_requires_each_fixed_candidate_once(self):
        complete = [manifest(candidate_id) for candidate_id in CANDIDATES]
        self.assertEqual(len(validate_complete_set(complete)), 6)
        with self.assertRaises(ManifestValidationError):
            validate_complete_set(complete[:-1])
        bad = manifest(); bad["profiles"]["native"]["unsupported"] = ["temperature"]
        with self.assertRaises(ManifestValidationError): validate_manifest(bad)

    def test_broadcast_p0_exception_and_cli_atomic_summary(self):
        p0 = manifest(); p0["license"]["public_broadcast_status"] = "blocked"
        self.assertEqual(validate_manifest(p0)["status"], "READY")
        bad = copy.deepcopy(p0); bad["license"]["evaluation_allowed"] = False
        with self.assertRaises(ManifestValidationError): validate_manifest(bad)
        with tempfile.TemporaryDirectory() as directory:
            good_path = Path(directory) / "good.json"; bad_path = Path(directory) / "bad.json"
            good_path.write_text(json.dumps(p0), encoding="utf-8"); bad_path.write_text("{}", encoding="utf-8")
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("model_usage_manifest.py")), str(bad_path), str(good_path)], capture_output=True, text=True, check=False)
            summary = json.loads(result.stdout)
            self.assertEqual(result.returncode, 1); self.assertFalse(summary["valid"])
            self.assertEqual([item["path"] for item in summary["results"]], sorted([str(bad_path), str(good_path)]))


if __name__ == "__main__":
    unittest.main()
