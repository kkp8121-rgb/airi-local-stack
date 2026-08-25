"""Pinned, offline-only native Transformers P2 baseline runner for AIRI."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any, Mapping

from model_usage_manifest import canonical_sha256, file_sha256, validate_manifest
from run_airi_baseline import (
    build_case_system_prompt,
    load_system_prompt,
    score_output,
)
from run_airi_native_fit_probe import (
    ProbeError, SUPPORTED_CANDIDATES, _atomic_write, _candidate_options,
    _gpu_snapshot, _ram_snapshot, _require_local_snapshot, _utc_now,
    _verify_snapshot,
)


REPORT_SCHEMA = "airi.native-transformers-baseline.v1"
# Pinned to the committed fixture blob (a7412af, unchanged since).  The
# previous value never matched any committed revision of the file, so the
# "immutable" gate had been failing closed since 565cc65 (2026-08-14).
CASES_SHA256 = "95309e101e30009ec12a9edb4d047e69a46aec42c2f46df0a8b70962225dc3be"
DEFAULT_CASES = Path(__file__).with_name("airi_baseline_cases.json")


def _load_immutable_cases(path: str | Path = DEFAULT_CASES) -> tuple[list[dict[str, Any]], str]:
    source = Path(path)
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != CASES_SHA256:
        raise ProbeError("baseline cases must match the immutable pinned fixture")
    fixture = json.loads(raw.decode("utf-8"))
    cases = fixture.get("cases") if isinstance(fixture, dict) else None
    if fixture.get("schema_version") != 1 or fixture.get("synthetic_only") is not True or not isinstance(cases, list) or len(cases) != 16:
        raise ProbeError("baseline fixture must be the 16-case synthetic suite")
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(ids) != 16 or len(set(ids)) != 16 or not all(isinstance(item, str) and item for item in ids):
        raise ProbeError("baseline fixture case ids are invalid")
    return cases, digest


def _case_messages(case: Mapping[str, Any], system_prompt: str) -> list[dict[str, str]]:
    messages = case.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ProbeError("baseline fixture has invalid messages")
    system = build_case_system_prompt(system_prompt, case)
    safe = [{"role": "system", "content": system}]
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {"user", "assistant"} or not isinstance(message.get("content"), str):
            raise ProbeError("baseline fixture message is invalid")
        safe.append({"role": message["role"], "content": message["content"]})
    return safe


def _safe_device_map(model: Any) -> dict[str, Any]:
    mapping = getattr(model, "hf_device_map", {})
    if not isinstance(mapping, dict):
        return {"entry_count": 0, "device_counts": {}}
    counts: dict[str, int] = {}
    for device in mapping.values():
        key = str(device) if isinstance(device, (int, str)) and str(device) in {"cpu", "disk", "0", "1", "2", "3"} else "other"
        counts[key] = counts.get(key, 0) + 1
    return {"entry_count": len(mapping), "device_counts": dict(sorted(counts.items()))}


def _case_summary(case: Mapping[str, Any], samples: list[dict[str, Any]]) -> dict[str, Any]:
    failures = sorted({failure for sample in samples for failure in sample["structural_score"]["failures"]})
    totals = [sample["timing"]["wall_seconds"] for sample in samples]
    return {
        "id": case["id"], "category": case["category"],
        "runs": samples,
        "structural_score": {"passed": not failures, "failures": failures},
        "timing": {"median_wall_seconds": statistics.median(totals)},
    }


def run_baseline(*, manifest_path: str | Path, snapshot_path: str | Path, report_path: str | Path, gpu_max_mib: int, cpu_max_gib: int, repetitions: int = 3, cases_path: str | Path = DEFAULT_CASES) -> dict[str, Any]:
    """Load one exact local model and evaluate all immutable baseline cases."""
    report: dict[str, Any] = {"schema_version": REPORT_SCHEMA, "status": "incomplete", "started_at": _utc_now(), "stages": {}}
    report_file = Path(report_path)
    try:
        if not isinstance(repetitions, int) or not 1 <= repetitions <= 10:
            raise ProbeError("repetitions must be an integer from 1 through 10")
        if not isinstance(gpu_max_mib, int) or not isinstance(cpu_max_gib, int) or gpu_max_mib < 1 or cpu_max_gib < 1:
            raise ProbeError("gpu_max_mib and cpu_max_gib must be positive integers")
        cases, cases_digest = _load_immutable_cases(cases_path)
        system_prompt = load_system_prompt()
        manifest_file = Path(manifest_path)
        manifest = validate_manifest(json.loads(manifest_file.read_text(encoding="utf-8")))
        if manifest["candidate_id"] not in SUPPORTED_CANDIDATES:
            raise ProbeError("candidate is not supported by this native baseline")
        if manifest["remote_code"]["required"]:
            raise ProbeError("remote-code-required manifests are refused")
        options, sampling_basis, granite_thinking_false = _candidate_options(manifest["candidate_id"])
        report.update({"candidate_id": manifest["candidate_id"], "manifest": {"file_sha256": file_sha256(manifest_file), "canonical_sha256": canonical_sha256(manifest), "exact_revision": manifest["exact_revision"]}, "fixture": {"sha256": cases_digest, "case_count": len(cases), "repetitions": repetitions}, "system_prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(), "sampling_basis": sampling_basis, "requested_generation": {**options, "max_new_tokens": 64, "seeds_by_repetition": [42 + index for index in range(repetitions)]}})
        report["stages"]["preflight"] = _verify_snapshot(manifest, snapshot_path)
        max_memory: dict[Any, str] = {0: f"{gpu_max_mib}MiB", "cpu": f"{cpu_max_gib}GiB"}
        report["runtime_request"] = {"device_map": "auto", "max_memory": {"0": max_memory[0], "cpu": max_memory["cpu"]}, "dtype": "bfloat16", "local_files_only": True, "trust_remote_code": False, "low_cpu_mem_usage": True, "use_cache": True, "max_new_tokens": 64}
        os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1"})
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer

        snapshot = _require_local_snapshot(snapshot_path)
        report["stages"]["runtime_pre"] = {"versions": {"python": __import__("sys").version.split()[0], "torch": torch.__version__, "transformers": transformers.__version__}, "gpu": _gpu_snapshot(torch), "ram": _ram_snapshot()}
        tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False)
        model = AutoModelForCausalLM.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False, dtype=torch.bfloat16, device_map="auto", max_memory=max_memory, low_cpu_mem_usage=True)
        report["stages"]["loaded"] = {"hf_device_map": _safe_device_map(model)}
        torch.cuda.reset_peak_memory_stats() if torch.cuda.is_available() else None
        results = []
        for case in cases:
            if not isinstance(case.get("id"), str) or not isinstance(case.get("category"), str) or not isinstance(case.get("checks"), dict):
                raise ProbeError("baseline fixture case is invalid")
            samples = []
            for run_index in range(repetitions):
                torch.manual_seed(42 + run_index)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(42 + run_index)
                template_options = {"add_generation_prompt": True, "return_tensors": "pt", "return_dict": True}
                if granite_thinking_false:
                    template_options["thinking"] = False
                messages = _case_messages(case, system_prompt)
                encoded = tokenizer.apply_chat_template(messages, **template_options)
                encoded.pop("token_type_ids", None)
                device = model.get_input_embeddings().weight.device
                encoded = {key: value.to(device) for key, value in encoded.items()}
                if torch.cuda.is_available(): torch.cuda.synchronize()
                started = time.monotonic()
                generated = model.generate(**encoded, max_new_tokens=64, use_cache=True, pad_token_id=tokenizer.pad_token_id, eos_token_id=tokenizer.eos_token_id, **options)
                if torch.cuda.is_available(): torch.cuda.synchronize()
                elapsed = time.monotonic() - started
                input_count = encoded["input_ids"].shape[-1]
                output = tokenizer.decode(generated[0][input_count:], skip_special_tokens=True)
                score = score_output(output, case["checks"])
                samples.append({"run": run_index + 1, "seed": 42 + run_index, "output": {"sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(), "char_count": len(output), "token_count": int(generated.shape[-1] - input_count)}, "structural_score": score, "timing": {"wall_seconds": elapsed}})
                del generated, encoded
            summary = _case_summary(case, samples)
            summary["case_system_prompt_sha256"] = hashlib.sha256(messages[0]["content"].encode("utf-8")).hexdigest()
            results.append(summary)
        report["cases"] = results
        passed = sum(1 for result in results if result["structural_score"]["passed"])
        report["aggregate"] = {"case_count": len(results), "passed_count": passed, "automatic_gate": "PASS" if passed == len(results) else "FAIL", "human_review_required": True}
        report["stages"]["runtime_post"] = {"gpu": _gpu_snapshot(torch), "ram": _ram_snapshot()}
        del model, tokenizer
        gc.collect()
        if torch.cuda.is_available(): torch.cuda.empty_cache()
        report["cleanup"] = {"gc_collected": True, "cuda_empty_cache": bool(torch.cuda.is_available())}
        report["status"] = "complete"
    except Exception as exc:
        report["status"] = "error"
        # Library exceptions can echo prompts or local paths; retain only a safe class.
        report["error"] = {"type": type(exc).__name__, "message": "native baseline did not complete"}
    report["finished_at"] = _utc_now()
    _atomic_write(report_file, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True); parser.add_argument("--snapshot", required=True); parser.add_argument("--report", required=True)
    parser.add_argument("--gpu-max-mib", type=int, required=True); parser.add_argument("--cpu-max-gib", type=int, required=True); parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args(argv)
    result = run_baseline(manifest_path=args.manifest, snapshot_path=args.snapshot, report_path=args.report, gpu_max_mib=args.gpu_max_mib, cpu_max_gib=args.cpu_max_gib, repetitions=args.repetitions)
    print(json.dumps({"status": result["status"]}))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
