"""Pinned, offline native Transformers P3 raw-context gate for AIRI."""

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
from run_airi_context_gate import SCHEMA, build_messages, source_literals, validate_fixture
from run_airi_native_baseline import _safe_device_map
from run_airi_native_fit_probe import (
    ProbeError, SUPPORTED_CANDIDATES, _atomic_write, _candidate_options,
    _gpu_snapshot, _ram_snapshot, _require_local_snapshot, _utc_now,
    _verify_snapshot,
)


REPORT_SCHEMA = "airi.native-transformers-context-gate.v1"
# Attestation re-pinned to LF-normalized bytes (was attested off a CRLF-smudged working copy).
CONTEXT_CASES_SHA256 = "a606c88ec99a7f2c074922e2567c74b794d692cdb361d92ce761d7fe0861ddbb"
DEFAULT_CASES = Path(__file__).with_name("airi_context_cases.json")
PRESSURES = (0, 8, 20, 48)


def _load_immutable_context_cases(path: str | Path = DEFAULT_CASES) -> tuple[dict[str, Any], str]:
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != CONTEXT_CASES_SHA256:
        raise ProbeError("context cases must match the immutable pinned fixture")
    fixture = json.loads(raw.decode("utf-8"))
    try:
        validate_fixture(fixture)
    except Exception as exc:
        raise ProbeError("context fixture is invalid") from exc
    observed = tuple(level.get("filler_pairs") for level in fixture["pressure_levels"])
    if observed != PRESSURES:
        raise ProbeError("context fixture must use pressures 0, 8, 20, 48")
    return fixture, digest


def _score_canaries(output: str, expected: Mapping[str, Any]) -> dict[str, Any]:
    """Parse only to compare canaries; never return generated response content."""
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        return {"valid_json": False, "canary_matches": {key: False for key in SCHEMA["required"]}, "passed": False}
    if not isinstance(value, dict) or set(value) != set(SCHEMA["required"]):
        return {"valid_json": False, "canary_matches": {key: False for key in SCHEMA["required"]}, "passed": False}
    matches = {key: value.get(key) == expected[key] for key in SCHEMA["required"]}
    return {"valid_json": True, "canary_matches": matches, "passed": all(matches.values())}


def _aggregate(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        raise ProbeError("context run has no samples")
    fields = SCHEMA["required"]
    return {
        "passed": all(sample["canaries"]["passed"] for sample in samples),
        "valid_json_rate": sum(sample["canaries"]["valid_json"] for sample in samples) / len(samples),
        "canary_match_rates": {field: sum(sample["canaries"]["canary_matches"][field] for sample in samples) / len(samples) for field in fields},
        "median_wall_seconds": statistics.median(sample["timing"]["wall_seconds"] for sample in samples),
    }


def run_context_gate(*, manifest_path: str | Path, snapshot_path: str | Path, report_path: str | Path, gpu_max_mib: int, cpu_max_gib: int, repetitions: int = 3, cases_path: str | Path = DEFAULT_CASES) -> dict[str, Any]:
    """Load once, then run the four raw context pressures three times each."""
    report: dict[str, Any] = {"schema_version": REPORT_SCHEMA, "status": "incomplete", "started_at": _utc_now(), "stages": {}}
    report_file = Path(report_path)
    try:
        if not isinstance(repetitions, int) or not 1 <= repetitions <= 5:
            raise ProbeError("repetitions must be an integer from 1 through 5")
        if not isinstance(gpu_max_mib, int) or not isinstance(cpu_max_gib, int) or gpu_max_mib < 1 or cpu_max_gib < 1:
            raise ProbeError("gpu_max_mib and cpu_max_gib must be positive integers")
        fixture, fixture_digest = _load_immutable_context_cases(cases_path)
        system, contract = source_literals()
        manifest_file = Path(manifest_path)
        manifest = validate_manifest(json.loads(manifest_file.read_text(encoding="utf-8")))
        if manifest["candidate_id"] not in SUPPORTED_CANDIDATES:
            raise ProbeError("candidate is not supported by this native context gate")
        if manifest["remote_code"]["required"]:
            raise ProbeError("remote-code-required manifests are refused")
        options, sampling_basis, granite_thinking_false = _candidate_options(manifest["candidate_id"])
        report.update({"candidate_id": manifest["candidate_id"], "manifest": {"file_sha256": file_sha256(manifest_file), "canonical_sha256": canonical_sha256(manifest), "exact_revision": manifest["exact_revision"]}, "fixture": {"sha256": fixture_digest, "pressures": list(PRESSURES), "repetitions": repetitions}, "airi_prompt": {"system_sha256": hashlib.sha256(system.encode("utf-8")).hexdigest(), "final_contract_sha256": hashlib.sha256(contract.encode("utf-8")).hexdigest()}, "sampling_basis": sampling_basis, "requested_generation": {**options, "max_new_tokens": 128, "seeds_by_repetition": [42 + number for number in range(repetitions)]}})
        report["stages"]["preflight"] = _verify_snapshot(manifest, snapshot_path)
        max_memory: dict[Any, str] = {0: f"{gpu_max_mib}MiB", "cpu": f"{cpu_max_gib}GiB"}
        report["runtime_request"] = {"device_map": "auto", "max_memory": {"0": max_memory[0], "cpu": max_memory["cpu"]}, "dtype": "bfloat16", "local_files_only": True, "trust_remote_code": False, "low_cpu_mem_usage": True, "use_cache": True, "max_new_tokens": 128, "official_template": {"add_generation_prompt": True, "thinking": False if granite_thinking_false else "not_requested"}}
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
        evidence = []
        for level in fixture["pressure_levels"]:
            messages = build_messages(system, contract, fixture, level["filler_pairs"])
            samples = []
            for run_index in range(repetitions):
                torch.manual_seed(42 + run_index)
                if torch.cuda.is_available(): torch.cuda.manual_seed_all(42 + run_index)
                template_options = {"add_generation_prompt": True, "return_tensors": "pt", "return_dict": True}
                if granite_thinking_false:
                    template_options["thinking"] = False
                encoded = tokenizer.apply_chat_template(messages, **template_options)
                encoded.pop("token_type_ids", None)
                device = model.get_input_embeddings().weight.device
                encoded = {key: value.to(device) for key, value in encoded.items()}
                if torch.cuda.is_available(): torch.cuda.synchronize()
                started = time.monotonic()
                generated = model.generate(**encoded, max_new_tokens=128, use_cache=True, pad_token_id=tokenizer.pad_token_id, eos_token_id=tokenizer.eos_token_id, **options)
                if torch.cuda.is_available(): torch.cuda.synchronize()
                elapsed = time.monotonic() - started
                input_count = encoded["input_ids"].shape[-1]
                output = tokenizer.decode(generated[0][input_count:], skip_special_tokens=True)
                samples.append({"run": run_index + 1, "seed": 42 + run_index, "input_token_count": int(input_count), "output": {"sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(), "char_count": len(output), "token_count": int(generated.shape[-1] - input_count)}, "canaries": _score_canaries(output, fixture["expected"]), "timing": {"wall_seconds": elapsed}})
                del generated, encoded
            evidence.append({"pressure": {"id": level["id"], "filler_pairs": level["filler_pairs"]}, "message_count": len(messages), "samples": samples, "aggregate": _aggregate(samples)})
        report["evidence"] = evidence
        report["aggregate"] = {"pressure_count": len(evidence), "passed_pressure_count": sum(entry["aggregate"]["passed"] for entry in evidence), "gate": "PASS" if all(entry["aggregate"]["passed"] for entry in evidence) else "FAIL"}
        report["stages"]["runtime_post"] = {"gpu": _gpu_snapshot(torch), "ram": _ram_snapshot()}
        del model, tokenizer
        gc.collect()
        if torch.cuda.is_available(): torch.cuda.empty_cache()
        report["cleanup"] = {"gc_collected": True, "cuda_empty_cache": bool(torch.cuda.is_available())}
        report["status"] = "complete"
    except Exception as exc:
        report["status"] = "error"
        report["error"] = {"type": type(exc).__name__, "message": "native context gate did not complete"}
    report["finished_at"] = _utc_now()
    _atomic_write(report_file, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True); parser.add_argument("--snapshot", required=True); parser.add_argument("--report", required=True)
    parser.add_argument("--gpu-max-mib", type=int, required=True); parser.add_argument("--cpu-max-gib", type=int, required=True); parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args(argv)
    result = run_context_gate(manifest_path=args.manifest, snapshot_path=args.snapshot, report_path=args.report, gpu_max_mib=args.gpu_max_mib, cpu_max_gib=args.cpu_max_gib, repetitions=args.repetitions)
    print(json.dumps({"status": result["status"]}))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
