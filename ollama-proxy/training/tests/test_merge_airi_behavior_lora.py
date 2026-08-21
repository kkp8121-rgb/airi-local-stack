import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("merge_airi_behavior_lora_test",
                                              HERE / "merge_airi_behavior_lora.py")
assert SPEC is not None and SPEC.loader is not None
merger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(merger)


class MergeContractTests(unittest.TestCase):
    def test_sha_pin_and_network_paths_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / "model.safetensors"
            payload.write_bytes(b"pinned-local-weights")
            digest = hashlib.sha256(payload.read_bytes()).hexdigest()
            self.assertEqual(merger.require_sha256(payload, digest, "base"), digest)
            with self.assertRaises(merger.MergeError):
                merger.require_sha256(payload, "0" * 64, "base")
        for path in ("https://example.invalid/model", "hf://org/model", r"\\server\share\model"):
            with self.assertRaises(merger.MergeError):
                merger.require_local_path(path, "input", must_exist=False)

    def test_evidence_is_content_free_and_non_authorizing(self) -> None:
        evidence = merger.build_evidence(
            base_sha256="a" * 64, adapter_sha256="b" * 64,
            base_artifact_manifest_sha256="d" * 64, adapter_artifact_manifest_sha256="e" * 64,
            merged_model_sha256="c" * 64, merged_model_size_bytes=123,
            target_tensor="model.layers.0.self_attn.q_proj.weight",
            non_target_tensor="model.embed_tokens.weight",
            target_metrics={"dtype": "bfloat16", "finite": True, "nonzero_elements": 3,
                            "max_abs_delta": 0.25, "l2_delta": 0.3},
            adapter_config={"peft_type": "LORA", "r": 16},
        )
        self.assertFalse(evidence["adoption_authorized"])
        self.assertEqual(evidence["t3_status"], "pending")
        self.assertNotIn("C:\\", json.dumps(evidence))
        changed = dict(evidence)
        changed["input_paths_recorded"] = True
        with self.assertRaises(merger.MergeError):
            merger.validate_evidence(changed)

    def test_probe_shaped_adapter_config_omits_base_path_but_keeps_hyperparameters(self) -> None:
        raw_config = {
            "base_model_name_or_path": r"D:\models\pinned-airi-base",
            "peft_type": "LORA", "task_type": "CAUSAL_LM", "r": 16,
            "lora_alpha": 32, "lora_dropout": 0.05, "bias": "none",
            "target_modules": ["v_proj", "q_proj"], "use_dora": False,
            "use_rslora": False, "inference_mode": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            adapter = Path(tmp)
            (adapter / "adapter_config.json").write_text(json.dumps(raw_config), encoding="utf-8")
            safe_config = merger.load_adapter_config(adapter)
        self.assertNotIn("base_model_name_or_path", safe_config)
        self.assertEqual(safe_config["target_modules"], ["q_proj", "v_proj"])
        evidence = merger.build_evidence(
            base_sha256="a" * 64, adapter_sha256="b" * 64,
            base_artifact_manifest_sha256="d" * 64, adapter_artifact_manifest_sha256="e" * 64,
            merged_model_sha256="c" * 64, merged_model_size_bytes=123,
            target_tensor="target", non_target_tensor="non-target",
            target_metrics={"dtype": "bfloat16", "finite": True, "nonzero_elements": 1,
                            "max_abs_delta": 1.0, "l2_delta": 1.0},
            adapter_config=safe_config,
        )
        encoded = json.dumps(evidence, ensure_ascii=False)
        self.assertNotIn(r"D:\models", encoded)
        self.assertEqual(evidence["adapter_config"]["lora_alpha"], 32)
        self.assertEqual(evidence["base_model_path"],
                         {"omitted": True, "bound_by": "base_model_safetensors_sha256"})

    def test_merged_artifact_digest_is_pinned_and_evidence_rejects_base_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            artifact = stage / "model.safetensors"
            artifact.write_bytes(b"merged-bf16-weights")
            digest, size = merger.merged_artifact_digest(stage)
        self.assertEqual(digest, hashlib.sha256(b"merged-bf16-weights").hexdigest())
        self.assertEqual(size, len(b"merged-bf16-weights"))
        with self.assertRaises(merger.MergeError):
            merger.build_evidence(
                base_sha256="a" * 64, adapter_sha256="b" * 64,
                base_artifact_manifest_sha256="d" * 64, adapter_artifact_manifest_sha256="e" * 64,
                merged_model_sha256="a" * 64, merged_model_size_bytes=size,
                target_tensor="target", non_target_tensor="non-target",
                target_metrics={"dtype": "bfloat16", "finite": True, "nonzero_elements": 1,
                                "max_abs_delta": 1.0, "l2_delta": 1.0}, adapter_config={},
            )

    def test_artifact_manifest_pins_probe_layout_and_detects_non_weight_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base, adapter = root / "base", root / "adapter"
            base.mkdir()
            adapter.mkdir()
            files = {
                base / "model.safetensors": b"base-weight-pin",
                base / "config.json": b'{"model_type":"qwen"}',
                base / "tokenizer.json": b'{"version":"1"}',
                adapter / "adapter_model.safetensors": b"adapter-weight-pin",
                adapter / "adapter_config.json": b'{"peft_type":"LORA"}',
            }
            for path, payload in files.items():
                path.write_bytes(payload)
            base_manifest, _ = merger.top_level_artifact_manifest(base)
            adapter_manifest, _ = merger.top_level_artifact_manifest(adapter)
            self.assertEqual(merger.require_artifact_manifest(base, base_manifest, "base")[0], base_manifest)
            self.assertEqual(merger.require_artifact_manifest(adapter, adapter_manifest, "adapter")[0], adapter_manifest)
            base_weight = hashlib.sha256((base / "model.safetensors").read_bytes()).hexdigest()
            adapter_weight = hashlib.sha256((adapter / "adapter_model.safetensors").read_bytes()).hexdigest()
            for changed in (base / "config.json", base / "tokenizer.json", adapter / "adapter_config.json"):
                original = changed.read_bytes()
                changed.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
                expected = base_manifest if changed.parent == base else adapter_manifest
                with self.assertRaises(merger.MergeError):
                    merger.require_artifact_manifest(changed.parent, expected, "probe")
                changed.write_bytes(original)
            self.assertEqual(hashlib.sha256((base / "model.safetensors").read_bytes()).hexdigest(), base_weight)
            self.assertEqual(hashlib.sha256((adapter / "adapter_model.safetensors").read_bytes()).hexdigest(), adapter_weight)

    def test_artifact_manifest_refuses_subdirectories_and_symlink_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.json").write_bytes(b"{}")
            (root / "nested").mkdir()
            with self.assertRaises(merger.MergeError):
                merger.top_level_artifact_manifest(root)
            (root / "nested").rmdir()
            alias = root / "alias"
            alias.write_bytes(b"not-an-alias")
            with mock.patch.object(Path, "is_symlink", autospec=True,
                                   side_effect=lambda path: path.name == "alias"):
                with self.assertRaises(merger.MergeError):
                    merger.top_level_artifact_manifest(root)

    def test_base_load_kwargs_force_bfloat16(self) -> None:
        fake_torch = SimpleNamespace(bfloat16=object())
        kwargs = merger.base_model_load_kwargs(fake_torch)
        self.assertIs(kwargs["torch_dtype"], fake_torch.bfloat16)
        self.assertTrue(kwargs["low_cpu_mem_usage"])
        self.assertTrue(kwargs["local_files_only"])

    def test_existing_output_and_non_sibling_temp_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "published"
            output.mkdir()
            with self.assertRaises(merger.MergeError):
                merger.prepare_publication(output, root)
            output.rmdir()
            foreign = root / "foreign"
            foreign.mkdir()
            with self.assertRaises(merger.MergeError):
                merger.prepare_publication(output, foreign)

    def test_atomic_publish_failure_leaves_no_output_and_stage_is_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output, stage = merger.prepare_publication(root / "published", root)
            (stage / "marker").write_text("staged", encoding="utf-8")
            with mock.patch.object(os, "replace", side_effect=OSError("disk failure")):
                with self.assertRaises(merger.MergeError):
                    merger.publish_staged_output(stage, output)
            self.assertFalse(output.exists())
            self.assertTrue(stage.exists())


if __name__ == "__main__":
    unittest.main()
