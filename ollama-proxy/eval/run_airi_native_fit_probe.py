"""Fail-closed, local-only native Transformers fit probe for AIRI P1 models.

This module deliberately validates every pinned snapshot artifact before it
imports Transformers.  Reports contain hashes and measurements only; prompts,
model output, and filesystem locations are never persisted.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from model_usage_manifest import canonical_sha256, file_sha256, validate_manifest


REPORT_SCHEMA = "airi.native-transformers-fit-probe.v1"
SUPPORTED_CANDIDATES = {"midm-2.0-mini-instruct", "granite-3.3-2b-instruct"}
SYSTEM_PROMPT = "You are AIRI, a helpful local AI companion."
USER_PROMPT = "Give a short, friendly greeting."


class ProbeError(ValueError):
    """Raised when a native probe cannot proceed safely."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        staged = Path(handle.name)
    os.replace(staged, path)


def _safe_relative_artifact_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ProbeError("manifest artifact path is not a safe relative path")
    return candidate


def _require_local_snapshot(snapshot_path: str | Path) -> Path:
    if isinstance(snapshot_path, str) and ("://" in snapshot_path or snapshot_path.startswith("hf:")):
        raise ProbeError("snapshot path must be a local directory")
    snapshot = Path(snapshot_path).expanduser()
    if not snapshot.is_absolute():
        raise ProbeError("snapshot path must be absolute and local")
    try:
        resolved = snapshot.resolve(strict=True)
    except OSError as exc:
        raise ProbeError("snapshot path must be an existing local directory") from exc
    if not resolved.is_dir():
        raise ProbeError("snapshot path must be an existing local directory")
    return resolved


def _verify_snapshot(manifest: Mapping[str, Any], snapshot_path: str | Path) -> dict[str, Any]:
    """Verify all small artifacts and all selected weight files before imports."""
    snapshot = _require_local_snapshot(snapshot_path)
    checked: list[dict[str, Any]] = []
    root_text = str(snapshot)
    for artifact in manifest["artifacts"]:
        relative = _safe_relative_artifact_path(artifact["path"])
        try:
            target = (snapshot / relative).resolve(strict=True)
        except OSError as exc:
            raise ProbeError("required snapshot artifact is missing") from exc
        if not target.is_file() or (str(target) != root_text and not str(target).startswith(root_text + os.sep)):
            raise ProbeError("required snapshot artifact is not a local file")
        actual = file_sha256(target)
        if actual != artifact["sha256"]:
            raise ProbeError("snapshot artifact SHA-256 mismatch")
        checked.append({"kind": artifact["kind"], "sha256": actual, "size": target.stat().st_size})
    weights = [item for item in checked if item["kind"] == "weight"]
    if not weights:
        raise ProbeError("manifest has no selected weight files")
    return {
        "snapshot_path_sha256": hashlib.sha256(str(snapshot).encode("utf-8")).hexdigest(),
        "artifact_count": len(checked),
        "weight_count": len(weights),
        "artifacts": checked,
    }


def _candidate_options(candidate_id: str) -> tuple[dict[str, Any], str, bool]:
    if candidate_id == "midm-2.0-mini-instruct":
        return ({"do_sample": True, "temperature": 0.8, "top_k": 20, "top_p": 0.75, "repetition_penalty": 1}, "official_manifest_generation_defaults", False)
    if candidate_id == "granite-3.3-2b-instruct":
        return ({"do_sample": False}, "transformers_greedy_default_due_official_unknown", True)
    raise ProbeError("candidate is not supported by this native probe")


def _ram_snapshot() -> dict[str, Any]:
    try:
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong), ("page_file_total", ctypes.c_ulonglong), ("page_file_avail", ctypes.c_ulonglong), ("virtual_total", ctypes.c_ulonglong), ("virtual_avail", ctypes.c_ulonglong), ("extended", ctypes.c_ulonglong)]
        status = MemoryStatus(); status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return {"status": "observed", "total_bytes": status.total, "free_bytes": status.avail}
    except (AttributeError, OSError):
        pass
    return {"status": "unavailable"}


def _gpu_snapshot(torch: Any) -> dict[str, Any]:
    if not torch.cuda.is_available():
        return {"status": "unavailable", "devices": []}
    devices = []
    for index in range(torch.cuda.device_count()):
        free, total = torch.cuda.mem_get_info(index)
        devices.append({"index": index, "total_bytes": total, "free_bytes": free, "allocated_bytes": torch.cuda.memory_allocated(index), "reserved_bytes": torch.cuda.memory_reserved(index), "max_allocated_bytes": torch.cuda.max_memory_allocated(index), "max_reserved_bytes": torch.cuda.max_memory_reserved(index)})
    return {"status": "observed", "devices": devices}


def run_probe(*, manifest_path: str | Path, snapshot_path: str | Path, report_path: str | Path, gpu_max_mib: int, cpu_max_gib: int) -> dict[str, Any]:
    """Run one bounded probe and always atomically write a content-free report."""
    report_file = Path(report_path)
    report: dict[str, Any] = {"schema_version": REPORT_SCHEMA, "status": "incomplete", "started_at": _utc_now(), "stages": {}}
    try:
        if not isinstance(gpu_max_mib, int) or not isinstance(cpu_max_gib, int) or gpu_max_mib < 1 or cpu_max_gib < 1:
            raise ProbeError("gpu_max_mib and cpu_max_gib must be positive integers")
        manifest_file = Path(manifest_path)
        raw_manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest = validate_manifest(raw_manifest)
        if manifest["candidate_id"] not in SUPPORTED_CANDIDATES:
            raise ProbeError("candidate is not supported by this native probe")
        if manifest["remote_code"]["required"]:
            raise ProbeError("remote-code-required manifests are refused")
        options, sampling_basis, granite_thinking_false = _candidate_options(manifest["candidate_id"])
        report.update({
            "candidate_id": manifest["candidate_id"],
            "profile": "native",
            "manifest": {"file_sha256": file_sha256(manifest_file), "canonical_sha256": canonical_sha256(manifest), "exact_revision": manifest["exact_revision"]},
            "sampling_basis": sampling_basis,
        })
        report["stages"]["preflight"] = _verify_snapshot(manifest, snapshot_path)
        max_memory = {0: f"{gpu_max_mib}MiB", "cpu": f"{cpu_max_gib}GiB"}
        report["runtime_request"] = {"device_map": "auto", "max_memory": {"0": max_memory[0], "cpu": max_memory["cpu"]}, "dtype": "bfloat16", "local_files_only": True, "trust_remote_code": False, "low_cpu_mem_usage": True, "use_cache": True, "max_new_tokens": 16}
        os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1"})
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer

        snapshot = _require_local_snapshot(snapshot_path)
        report["stages"]["runtime_pre"] = {"versions": {"python": __import__("sys").version.split()[0], "torch": torch.__version__, "transformers": transformers.__version__}, "gpu": _gpu_snapshot(torch), "ram": _ram_snapshot()}
        tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False)
        model = AutoModelForCausalLM.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False, dtype=torch.bfloat16, device_map="auto", max_memory=max_memory, low_cpu_mem_usage=True)
        raw_device_map = getattr(model, "hf_device_map", {})
        report["stages"]["model_layout"] = {
            "hf_device_map_present": isinstance(raw_device_map, Mapping),
            "module_count_by_device": dict(
                sorted(Counter(str(value) for value in raw_device_map.values()).items())
            ) if isinstance(raw_device_map, Mapping) else {},
        }
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": USER_PROMPT}]
        template_options = {"add_generation_prompt": True, "return_tensors": "pt", "return_dict": True}
        if granite_thinking_false:
            template_options["thinking"] = False
        encoded = tokenizer.apply_chat_template(messages, **template_options)
        encoded.pop("token_type_ids", None)
        device = model.get_input_embeddings().weight.device
        encoded = {key: value.to(device) for key, value in encoded.items()}
        torch.cuda.reset_peak_memory_stats() if torch.cuda.is_available() else None
        started = time.monotonic(); synchronized = False
        if torch.cuda.is_available(): torch.cuda.synchronize(); synchronized = True
        generated = model.generate(
            **encoded,
            max_new_tokens=16,
            use_cache=True,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
            **options,
        )
        if torch.cuda.is_available(): torch.cuda.synchronize()
        elapsed = time.monotonic() - started
        input_token_count = encoded["input_ids"].shape[-1]
        new_tokens = generated[0][input_token_count:]
        output = tokenizer.decode(new_tokens, skip_special_tokens=True)
        report["stages"]["generation"] = {"status": "complete", "input_token_count": int(input_token_count), "output": {"char_count": len(output), "sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(), "token_count": int(new_tokens.shape[-1])}, "timing": {"wall_seconds": elapsed, "cuda_synchronized": synchronized}, "requested_template": {"system_and_user": True, "add_generation_prompt": True, "thinking": False if granite_thinking_false else "not_requested"}, "requested_generation": {**options, "max_new_tokens": 16}}
        report["stages"]["runtime_post"] = {"gpu": _gpu_snapshot(torch), "ram": _ram_snapshot()}
        del generated, encoded, model, tokenizer
        gc.collect()
        if torch.cuda.is_available(): torch.cuda.empty_cache()
        report["cleanup"] = {"gc_collected": True, "cuda_empty_cache": bool(torch.cuda.is_available())}
        report["status"] = "complete"
    except Exception as exc:  # Report failures without exposing local paths or output.
        report["status"] = "error"
        report["error"] = type(exc).__name__ + ": " + str(exc).replace(str(snapshot_path), "<snapshot>").replace(str(manifest_path), "<manifest>")
    report["finished_at"] = _utc_now()
    _atomic_write(report_file, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True); parser.add_argument("--snapshot", required=True); parser.add_argument("--report", required=True)
    parser.add_argument("--gpu-max-mib", type=int, required=True); parser.add_argument("--cpu-max-gib", type=int, required=True)
    args = parser.parse_args(argv)
    result = run_probe(manifest_path=args.manifest, snapshot_path=args.snapshot, report_path=args.report, gpu_max_mib=args.gpu_max_mib, cpu_max_gib=args.cpu_max_gib)
    print(json.dumps({"status": result["status"]}))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
