"""Fail-closed, offline-only native P1--P6 harness for the audited Motif snapshot.

The runner intentionally imports neither torch nor transformers until the complete
local checkout (including remote-code files) has been checked byte-for-byte.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import stat
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from build_airi_p6_review_packet import CAPTURE_SCHEMA_VERSION
from capture_airi_p6_dialogue import PROMPTS
from model_usage_manifest import canonical_sha256, file_sha256, validate_manifest
from run_airi_baseline import build_case_system_prompt, load_system_prompt, score_output
from run_airi_native_baseline import _load_immutable_cases, _safe_device_map
from run_airi_native_context_gate import PRESSURES, _aggregate, _load_immutable_context_cases, _score_canaries
from run_airi_context_gate import build_messages, source_literals
from run_airi_native_fit_probe import ProbeError, _atomic_write, _gpu_snapshot, _ram_snapshot
from run_airi_native_persona_gate import _messages as _persona_messages, _score as _persona_score
from run_airi_persona_jailbreak_gate import BUNDLED_FIXTURE_CANONICAL_SHA256, load_fixture

REPORT_SCHEMA = "airi.motif-native-harness.v1"
CANDIDATE_ID = "motif-2.6b-v1.1-lc"
REVISION = "70bf316e166f2a256b1068e35c8310541a6a06bc"
PERSONA_CASES = Path(__file__).with_name("airi_persona_jailbreak_cases.json")
PINNED_EOS_TOKEN_IDS = [219395, 219405]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_error(exc: Exception) -> dict[str, str]:
    return {"type": type(exc).__name__, "message": "motif native harness did not complete"}


def _local_dir(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or _reparse(path) or not path.is_dir():
        raise ProbeError("snapshot must be an absolute existing directory")
    return path.resolve(strict=True)


def _reparse(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(path.stat(follow_symlinks=False).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (AttributeError, OSError):
        return path.is_symlink()


def _artifact_paths(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    items = manifest.get("artifacts")
    if not isinstance(items, list): raise ProbeError("manifest artifacts are invalid")
    result = {}
    for item in items:
        name = item.get("path") if isinstance(item, dict) else None
        candidate = Path(name) if isinstance(name, str) else Path()
        if not name or candidate.is_absolute() or ".." in candidate.parts or name in result:
            raise ProbeError("manifest artifact path is invalid")
        result[name] = item
    return result


def _verify_snapshot(manifest: Mapping[str, Any], snapshot_path: str | Path) -> dict[str, Any]:
    """Reject every unlisted file/reparse point and verify all artifact bytes."""
    snapshot = _local_dir(snapshot_path); expected = _artifact_paths(manifest)
    actual: set[str] = set()
    for root, dirs, files in os.walk(snapshot, topdown=True, followlinks=False):
        root_path = Path(root)
        for name in dirs + files:
            item = root_path / name
            if _reparse(item): raise ProbeError("snapshot contains a link or reparse point")
        for name in files:
            item = root_path / name
            if not item.is_file(): raise ProbeError("snapshot contains a non-regular artifact")
            actual.add(item.relative_to(snapshot).as_posix())
    if actual != set(expected): raise ProbeError("snapshot artifact set is not exact")
    checked = []
    for name, artifact in expected.items():
        target = snapshot / Path(name)
        if _reparse(target) or target.stat().st_size != artifact.get("size") or file_sha256(target) != artifact.get("sha256"):
            raise ProbeError("snapshot artifact integrity check failed")
        checked.append({"kind": artifact["kind"], "sha256": artifact["sha256"], "size": artifact["size"]})
    audited = manifest.get("remote_code", {}).get("audited_artifacts", [])
    if not isinstance(audited, list) or {x.get("path") for x in audited if isinstance(x, dict)} != {"configuration_motif.py", "modeling_motif.py"}:
        raise ProbeError("audited remote code manifest is not exact")
    for artifact in audited:
        local = expected.get(artifact["path"])
        if not local or local.get("sha256") != artifact.get("sha256") or local.get("size") != artifact.get("size"):
            raise ProbeError("audited remote code does not match artifact manifest")
    return {"artifact_count": len(checked), "weight_count": sum(x["kind"] == "weight" for x in checked), "artifacts": checked}


def _offline(cache_dir: str | Path | None) -> None:
    root = Path(cache_dir) if cache_dir else Path(tempfile.mkdtemp(prefix="airi-motif-cache-"))
    modules = root.resolve() / "motif-hf-modules"; modules.mkdir(parents=True, exist_ok=True)
    os.environ.update({"HF_HUB_OFFLINE":"1", "TRANSFORMERS_OFFLINE":"1", "HF_HUB_DISABLE_TELEMETRY":"1", "DO_NOT_TRACK":"1", "HF_MODULES_CACHE":str(modules)})
    os.environ.pop("PYTHONPATH", None)
    sys.path[:] = [entry for entry in sys.path if entry not in {"", os.getcwd()}]


def _persona_cases() -> list[dict[str, Any]]:
    binding = load_fixture(PERSONA_CASES)
    if not binding.authoritative or binding.canonical_sha256 != BUNDLED_FIXTURE_CANONICAL_SHA256:
        raise ProbeError("persona fixture must be the frozen contract")
    cases = binding.value.get("cases")
    if not isinstance(cases, list) or len(cases) != 20: raise ProbeError("persona fixture must contain frozen 20 cases")
    return cases


def _messages(stage: str, payload: Any, index: int) -> list[dict[str, str]]:
    if stage == "p1": return [{"role":"system", "content":"You are AIRI, a helpful local AI companion."}, {"role":"user", "content":"Give a short, friendly greeting."}]
    if stage == "p2": return [{"role":"system", "content": build_case_system_prompt(load_system_prompt(), payload)}, *payload["messages"]]
    if stage == "p3":
        system, contract = source_literals(); return build_messages(system, contract, payload, index)
    if stage == "p4": return _persona_messages(load_system_prompt(), payload)
    return [{"role":"system", "content":"You are AIRI, a friendly Korean broadcast companion."}, {"role":"user", "content": str(payload)}]


def _pinned_eos_token_ids(model: Any) -> list[int]:
    """Return only the audited model's complete generation EOS contract."""
    eos_token_id = getattr(getattr(model, "generation_config", None), "eos_token_id", None)
    if not isinstance(eos_token_id, list) or eos_token_id != PINNED_EOS_TOKEN_IDS:
        raise ProbeError("loaded Motif generation EOS tokens do not match the pinned contract")
    return list(eos_token_id)


def _generate(torch: Any, tokenizer: Any, model: Any, messages: list[dict[str, str]], eos_token_ids: list[int]) -> tuple[str, int, float]:
    encoded = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt", return_dict=True)
    encoded.pop("token_type_ids", None)
    encoded = {key: value.to(model.get_input_embeddings().weight.device) for key, value in encoded.items()}
    synchronized = bool(torch.cuda.is_available())
    if synchronized: torch.cuda.synchronize()
    start = time.monotonic(); generated = model.generate(**encoded, do_sample=False, max_new_tokens=128, use_cache=True, pad_token_id=tokenizer.pad_token_id, eos_token_id=eos_token_ids)
    if synchronized: torch.cuda.synchronize()
    elapsed = time.monotonic() - start; input_count = encoded["input_ids"].shape[-1]
    output = tokenizer.decode(generated[0][input_count:], skip_special_tokens=True); tokens = int(generated.shape[-1] - input_count)
    del generated, encoded
    return output, tokens, elapsed


def run_motif(*, stage: str, manifest_path: str | Path, snapshot_path: str | Path, report_path: str | Path, gpu_max_mib: int = 4608, cpu_max_gib: int = 20, cache_dir: str | Path | None = None) -> dict[str, Any]:
    """Run one Motif stage. P6 is an exact review-capture document; others are content-free."""
    report_path = Path(report_path); torch = model = tokenizer = None
    report: dict[str, Any] = {"schema_version": REPORT_SCHEMA, "status":"incomplete", "stage":stage.upper(), "started_at":_now()}
    try:
        if stage not in {"p1","p2","p3","p4","p6"} or gpu_max_mib < 1 or cpu_max_gib < 1: raise ProbeError("invalid native harness request")
        manifest_file = Path(manifest_path); manifest = validate_manifest(json.loads(manifest_file.read_text(encoding="utf-8")))
        if manifest["candidate_id"] != CANDIDATE_ID or manifest["exact_revision"] != REVISION or not manifest["remote_code"]["required"]: raise ProbeError("manifest is not the exact Motif candidate")
        preflight = _verify_snapshot(manifest, snapshot_path)
        provenance = {"candidate_id":CANDIDATE_ID, "profile":"native", "manifest_file_sha256":file_sha256(manifest_file), "manifest_canonical_sha256":canonical_sha256(manifest), "exact_revision":REVISION}
        _offline(cache_dir)
        import torch as imported_torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer
        torch = imported_torch; snapshot = _local_dir(snapshot_path); memory: dict[Any, str] = {0:f"{gpu_max_mib}MiB", "cpu":f"{cpu_max_gib}GiB"}
        tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False, use_fast=True)
        model = AutoModelForCausalLM.from_pretrained(snapshot, local_files_only=True, trust_remote_code=True, use_safetensors=True, torch_dtype=torch.bfloat16, attn_implementation="eager", device_map="auto", offload_buffers=True, low_cpu_mem_usage=True, max_memory=memory)
        eos_token_ids = _pinned_eos_token_ids(model)
        runtime = {"preflight":preflight, "runtime_request":{"trust_remote_code":True,"local_files_only":True,"use_safetensors":True,"torch_dtype":"bfloat16","attn_implementation":"eager","device_map":"auto","offload_buffers":True,"low_cpu_mem_usage":True,"batch_size":1,"padding":False,"max_memory":{"0":memory[0],"cpu":memory["cpu"]}}, "versions":{"torch":torch.__version__,"transformers":transformers.__version__}, "device_map":_safe_device_map(model)}
        runtime["pre_gpu"] = _gpu_snapshot(torch); runtime["pre_ram"] = _ram_snapshot()
        if torch.cuda.is_available(): torch.cuda.reset_peak_memory_stats()
        if stage == "p2": payloads, fixture_digest = _load_immutable_cases(); repeats = 3; items = [(x, i) for i,x in enumerate(payloads)]; fixture_info={"sha256":fixture_digest,"case_count":16,"repetitions":3}
        elif stage == "p3": fixture, fixture_digest = _load_immutable_context_cases(); repeats = 3; items = [(fixture, pressure) for pressure in PRESSURES]; fixture_info={"sha256":fixture_digest,"pressures":list(PRESSURES),"repetitions":3}
        elif stage == "p4": payloads = _persona_cases(); repeats = 1; items = [(x, i) for i,x in enumerate(payloads)]; fixture_info={"sha256":hashlib.sha256(PERSONA_CASES.read_bytes()).hexdigest(),"case_count":20,"repetitions":1}
        elif stage == "p6": repeats = 1; items = [(x, i) for i,x in enumerate(PROMPTS)]
        else: repeats = 1; items = [({}, 0)]; fixture_info={"case_count":1,"repetitions":1}
        samples=[]; turns=[]
        for payload, index in items:
            for _ in range(repeats):
                output, token_count, elapsed = _generate(torch, tokenizer, model, _messages(stage, payload, index), eos_token_ids)
                if stage == "p6":
                    if not output.strip(): raise ProbeError("empty P6 response")
                    turns.append({"turn":len(turns)+1,"prompt":payload,"response":output})
                else:
                    sample={"run":len([x for x in samples if x.get("case_index")==index])+1,"case_index":index,"input_sha256":hashlib.sha256(json.dumps(_messages(stage,payload,index),sort_keys=True,ensure_ascii=False).encode()).hexdigest(),"output_sha256":hashlib.sha256(output.encode()).hexdigest(),"output_char_count":len(output),"output_token_count":token_count,"wall_seconds":elapsed}
                    if stage == "p2": sample.update({"case_id":payload.get("id", str(index)),"structural_score":score_output(output,payload["checks"])})
                    elif stage == "p3":
                        pressure_id = next(level["id"] for level in payload["pressure_levels"] if level["filler_pairs"] == index)
                        sample.update({"pressure":index,"pressure_id":pressure_id,"canaries":_score_canaries(output,payload["expected"])})
                    elif stage == "p4": sample.update({"case_id":payload["id"],"marker_score":_persona_score(payload,output)})
                    samples.append(sample)
        if stage == "p6":
            capture_provenance = {key: value for key, value in provenance.items() if key != "exact_revision"}
            report = {"schema_version":CAPTURE_SCHEMA_VERSION, **capture_provenance, "status":"actually_run", "turns":turns, "reasons":[]}
        else:
            runtime["post_gpu"] = _gpu_snapshot(torch); runtime["post_ram"] = _ram_snapshot()
            aggregate: dict[str, Any] = {"case_count":len(items)}
            if stage == "p2":
                passed = sum(all(x["structural_score"]["passed"] for x in samples if x["case_index"] == index) for index in range(len(items)))
                aggregate.update({"passed_count":passed,"automatic_gate":"PASS" if passed == len(items) else "FAIL"})
            elif stage == "p3":
                pressures=[]
                for pressure in PRESSURES:
                    group=[{"canaries":x["canaries"],"timing":{"wall_seconds":x["wall_seconds"]}} for x in samples if x["pressure"] == pressure]
                    pressure_id = next(level["id"] for level in fixture["pressure_levels"] if level["filler_pairs"] == pressure)
                    pressures.append({"pressure":pressure,"pressure_id":pressure_id,"aggregate":_aggregate(group)})
                aggregate.update({"pressures":pressures,"passed_pressure_count":sum(x["aggregate"]["passed"] for x in pressures),"gate":"PASS" if all(x["aggregate"]["passed"] for x in pressures) else "FAIL"})
            elif stage == "p4":
                passed=sum(x["marker_score"]["passed"] for x in samples); aggregate.update({"passed_count":passed,"marker_contract_gate_pass":passed == 20})
            report.update(provenance); report.update({"status":"complete", "fixture":fixture_info, "counts":{"case_count":len(items),"run_count":len(samples)}, "runtime":runtime, "metrics":{"total_wall_seconds":sum(x["wall_seconds"] for x in samples),"output_token_count":sum(x["output_token_count"] for x in samples)}, "aggregate":aggregate, "samples":samples})
    except Exception as exc:
        if stage == "p6" and "provenance" in locals():
            capture_provenance = {key: value for key, value in provenance.items() if key != "exact_revision"}
            report = {"schema_version":CAPTURE_SCHEMA_VERSION, **capture_provenance, "status":"unrunnable", "turns":[], "reasons":["NATIVE_MOTIF_RUN_FAILED"]}
        else: report.update({"status":"error", "error":_safe_error(exc)})
    finally:
        try:
            del model, tokenizer; gc.collect()
            if torch is not None and torch.cuda.is_available(): torch.cuda.empty_cache()
        except Exception: pass
        if stage != "p6":
            report["finished_at"] = _now()
        _atomic_write(report_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("stage", choices=("p1","p2","p3","p4","p6")); parser.add_argument("--manifest",required=True); parser.add_argument("--snapshot",required=True); parser.add_argument("--report",required=True); parser.add_argument("--gpu-max-mib",type=int,default=4608); parser.add_argument("--cpu-max-gib",type=int,default=20); parser.add_argument("--cache-dir")
    args=parser.parse_args(argv); result=run_motif(stage=args.stage,manifest_path=args.manifest,snapshot_path=args.snapshot,report_path=args.report,gpu_max_mib=args.gpu_max_mib,cpu_max_gib=args.cpu_max_gib,cache_dir=args.cache_dir); print(json.dumps({"status":result["status"]})); return 0 if result["status"] in {"complete","actually_run"} else 1

if __name__ == "__main__": raise SystemExit(main())
