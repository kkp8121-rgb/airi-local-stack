"""Offline contract tests for the Motif-only native harness."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import run_airi_motif_native as runner


HERE = Path(__file__).parent
MANIFEST = HERE / "model-usage-manifests" / "motif-2.6b-v1.1-lc.json"


class _Cuda:
    def is_available(self): return False


class _Weight: device = "embedding-device"
class _Embedding: weight = _Weight()
class _Model:
    hf_device_map = {"model": 0}
    generation_config = types.SimpleNamespace(eos_token_id=[219395, 219405])
    def get_input_embeddings(self): return _Embedding()


class _Tokenizer:
    pad_token_id = 0; eos_token_id = 1


class MotifNativeTests(unittest.TestCase):
    def test_exact_snapshot_rejects_extra_file(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); artifacts = []
            for name, kind in (("weights.safetensors", "weight"), ("configuration_motif.py", "repository_file"), ("modeling_motif.py", "repository_file")):
                target = root / name; target.write_text("x")
                artifacts.append({"path":name,"kind":kind,"size":1,"sha256":hashlib.sha256(b"x").hexdigest()})
            by_path = {item["path"]: item for item in artifacts}
            manifest = {"artifacts":artifacts, "remote_code":{"audited_artifacts":[by_path["configuration_motif.py"], by_path["modeling_motif.py"]]}}
            self.assertEqual(runner._verify_snapshot(manifest, root)["artifact_count"], 3)
            (root / "unlisted_module.py").write_text("x")
            with self.assertRaisesRegex(runner.ProbeError, "artifact set is not exact"):
                runner._verify_snapshot(manifest, root)

    def test_hash_and_audit_reject_mismatch(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for name in ("configuration_motif.py", "modeling_motif.py"):
                (root / name).write_text("x")
            item = {"path":"configuration_motif.py","kind":"repository_file","size":1,"sha256":hashlib.sha256(b"x").hexdigest()}
            other = {"path":"modeling_motif.py","kind":"repository_file","size":1,"sha256":hashlib.sha256(b"x").hexdigest()}
            manifest={"artifacts":[item,other],"remote_code":{"audited_artifacts":[{**item,"kind":"audited_python"},{**other,"kind":"audited_python","sha256":"0"*64}]}}
            with self.assertRaises(runner.ProbeError): runner._verify_snapshot(manifest, root)

    def test_loader_kwargs_and_p2_call_count_are_pinned(self):
        calls=[]
        class TokenLoader:
            @staticmethod
            def from_pretrained(*args, **kwargs): calls.append(("tokenizer", kwargs)); return _Tokenizer()
        class ModelLoader:
            @staticmethod
            def from_pretrained(*args, **kwargs): calls.append(("model", kwargs)); return _Model()
        fake_torch=types.SimpleNamespace(__version__="fake", bfloat16="bf16", cuda=_Cuda())
        fake_transformers=types.ModuleType("transformers"); fake_transformers.__version__="fake"; fake_transformers.AutoTokenizer=TokenLoader; fake_transformers.AutoModelForCausalLM=ModelLoader
        manifest=json.loads(MANIFEST.read_text())
        with tempfile.TemporaryDirectory() as raw, patch.object(runner, "_verify_snapshot", return_value={"artifact_count":1}), patch.object(runner, "_generate", return_value=("answer", 1, .01)), patch.object(runner, "_load_immutable_cases", return_value=([{"id":str(n),"messages":[{"role":"user","content":"x"}],"checks":{}} for n in range(16)], "fixture")), patch.object(runner, "load_system_prompt", return_value="system"), patch.dict(sys.modules, {"torch":fake_torch,"transformers":fake_transformers}):
            root=Path(raw); output=root/"out.json"; result=runner.run_motif(stage="p2",manifest_path=MANIFEST,snapshot_path=root,report_path=output,cache_dir=root/"cache")
        self.assertEqual(result["status"], "complete"); self.assertEqual(result["counts"]["run_count"], 48)
        tokenizer_kwargs=dict(calls)["tokenizer"]; model_kwargs=dict(calls)["model"]; self.assertFalse(tokenizer_kwargs["trust_remote_code"]); self.assertTrue(model_kwargs["trust_remote_code"]); self.assertTrue(model_kwargs["use_safetensors"]); self.assertEqual(model_kwargs["attn_implementation"], "eager"); self.assertEqual(model_kwargs["torch_dtype"], "bf16")

    def test_generate_uses_full_pinned_model_eos_list(self):
        calls = []
        class Value:
            shape = (1, 2)
            def to(self, _device): return self
        class Generated:
            shape = (1, 3)
            def __getitem__(self, _index): return [1, 2, 3]
        class Tokenizer(_Tokenizer):
            def apply_chat_template(self, *_args, **_kwargs): return {"input_ids": Value()}
            def decode(self, _tokens, **_kwargs): return "answer"
        class Model(_Model):
            def generate(self, **kwargs): calls.append(kwargs); return Generated()
        runner._generate(types.SimpleNamespace(cuda=_Cuda()), Tokenizer(), Model(), [{"role": "user", "content": "x"}], runner._pinned_eos_token_ids(Model()))
        self.assertEqual(calls[0]["eos_token_id"], [219395, 219405])
        self.assertEqual(calls[0]["pad_token_id"], 0)

    def test_singular_or_mismatched_model_eos_is_rejected(self):
        for eos_token_id in (219395, [219395], [219395, 219406]):
            with self.subTest(eos_token_id=eos_token_id):
                model = _Model(); model.generation_config = types.SimpleNamespace(eos_token_id=eos_token_id)
                with self.assertRaisesRegex(runner.ProbeError, "EOS tokens"):
                    runner._pinned_eos_token_ids(model)

    def test_p3_and_p4_counts_and_aggregates(self):
        class Loader:
            @staticmethod
            def from_pretrained(*args, **kwargs): return _Tokenizer() if kwargs.get("use_fast") else _Model()
        # Separate loaders retain the exact model/tokenizer return types.
        fake=types.SimpleNamespace(__version__="fake",AutoTokenizer=types.SimpleNamespace(from_pretrained=lambda *a,**k:_Tokenizer()),AutoModelForCausalLM=types.SimpleNamespace(from_pretrained=lambda *a,**k:_Model()))
        torch=types.SimpleNamespace(__version__="fake",bfloat16="bf16",cuda=_Cuda())
        context={"pressure_levels":[{"id":str(p),"filler_pairs":p} for p in runner.PRESSURES],"expected":{"mode":"x","request_id":"x","marker":"x"}}
        p4=[{"id":str(n),"prompt":"x","required_signals":[],"forbidden_signals":[],"language":"ko","category":"safe"} for n in range(20)]
        with tempfile.TemporaryDirectory() as raw, patch.object(runner,"_verify_snapshot",return_value={}), patch.object(runner,"_generate",return_value=("{}",1,.01)), patch.object(runner,"_load_immutable_context_cases",return_value=(context,"ctx")), patch.object(runner,"build_messages",return_value=[{"role":"user","content":"x"}]), patch.object(runner,"_persona_cases",return_value=p4), patch.object(runner,"load_system_prompt",return_value="system"), patch.dict(sys.modules,{"torch":torch,"transformers":fake}):
            root=Path(raw); p3=runner.run_motif(stage="p3",manifest_path=MANIFEST,snapshot_path=root,report_path=root/"p3.json",cache_dir=root/"cache"); p4_result=runner.run_motif(stage="p4",manifest_path=MANIFEST,snapshot_path=root,report_path=root/"p4.json",cache_dir=root/"cache")
        self.assertEqual(p3["counts"]["run_count"],12); self.assertEqual(len(p3["aggregate"]["pressures"]),4)
        self.assertEqual(p4_result["counts"]["run_count"],20); self.assertEqual(p4_result["aggregate"]["passed_count"],20)

    def test_non_p6_contains_no_plaintext_and_cleanup_failure_is_safe(self):
        with tempfile.TemporaryDirectory() as raw, patch.object(runner, "_verify_snapshot", side_effect=runner.ProbeError("secret C:\\private")), patch.object(runner.gc, "collect", side_effect=RuntimeError("cleanup")):
            output=Path(raw)/"out.json"; result=runner.run_motif(stage="p1",manifest_path=MANIFEST,snapshot_path=raw,report_path=output)
            self.assertEqual(result["status"], "error"); self.assertNotIn("private", output.read_text())

    def test_p6_is_exact_builder_capture_shape(self):
        with tempfile.TemporaryDirectory() as raw, patch.object(runner, "_verify_snapshot", return_value={}), patch.object(runner, "_generate", return_value=("안녕하세요, 반가워요.", 2, .01)), patch.dict(sys.modules, {"torch":types.SimpleNamespace(__version__="fake",bfloat16="bf16",cuda=_Cuda()), "transformers":types.SimpleNamespace(__version__="fake",AutoTokenizer=types.SimpleNamespace(from_pretrained=lambda *a,**k:_Tokenizer()),AutoModelForCausalLM=types.SimpleNamespace(from_pretrained=lambda *a,**k:_Model()))}):
            output=Path(raw)/"p6.json"; result=runner.run_motif(stage="p6",manifest_path=MANIFEST,snapshot_path=raw,report_path=output,cache_dir=Path(raw)/"cache")
        self.assertEqual(set(result), {"schema_version","candidate_id","profile","status","manifest_file_sha256","manifest_canonical_sha256","turns","reasons"}); self.assertEqual(len(result["turns"]), 20)


if __name__ == "__main__": unittest.main()
