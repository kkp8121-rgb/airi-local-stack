"""Content-safe, local-only P1 Ollama fit probe for AIRI candidate manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from model_usage_manifest import canonical_sha256, file_sha256, validate_manifest


REPORT_SCHEMA = "airi.ollama-model-fit-probe.v1"
LOOPBACK_ENDPOINTS = {
    "http://127.0.0.1:11434",
    "http://localhost:11434",
    "http://127.0.0.1:11437",
    "http://localhost:11437",
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PROMPT = "안녕하세요 AIRI. 오늘 할 수 있는 짧고 차분한 응원 한 문장만 말해 주세요."
Transport = Callable[[str, str, Mapping[str, Any] | None], Any]
Runner = Callable[[list[str]], str]


class ProbeError(ValueError):
    """Raised for unsafe probe inputs or failed required observations."""


class HttpProbeError(ProbeError):
    """An Ollama HTTP response explicitly rejected a request."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        staged = Path(handle.name)
    os.replace(staged, path)


def _http_transport(method: str, url: str, body: Mapping[str, Any] | None) -> Any:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read().decode("utf-8")
            if body is not None and body.get("stream") is True:
                items = [json.loads(line) for line in raw.splitlines() if line.strip()]
                terminal = next((item for item in reversed(items) if item.get("done") is True), None)
                if terminal is None:
                    raise ProbeError("stream ended without done=true")
                terminal = dict(terminal)
                terminal["response"] = "".join(str(item.get("response", "")) for item in items)
                first = next((index for index, item in enumerate(items) if item.get("response")), None)
                terminal["stream_first_content_item"] = first
                return terminal
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise HttpProbeError(f"HTTP {exc.code}: {detail[:500]}") from exc


def _command(command: list[str]) -> str:
    return subprocess.run(command, capture_output=True, check=False, text=True, timeout=15).stdout.strip()


def _safe_json(transport: Transport, method: str, endpoint: str, route: str, body: Mapping[str, Any] | None = None) -> Any:
    return transport(method, endpoint + route, body)


def _gpu_snapshot(run: Runner) -> dict[str, Any]:
    fields = "name,driver_version,memory.total,memory.used,memory.free"
    try:
        rows = run(["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"])
        devices = []
        for row in rows.splitlines():
            values = [part.strip() for part in row.split(",")]
            if len(values) == 5:
                devices.append({
                    "name": values[0],
                    "driver": values[1],
                    "total_mib": int(values[2]),
                    "used_mib": int(values[3]),
                    "free_mib": int(values[4]),
                })
        return {"status": "observed", "devices": devices}
    except (OSError, subprocess.SubprocessError):
        return {"status": "unavailable", "devices": []}


def _ram_snapshot() -> dict[str, Any]:
    if os.name != "nt":
        return {"status": "unavailable"}
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


def _runtime_refs(show: Mapping[str, Any]) -> dict[str, Any]:
    details = show.get("details", {}) if isinstance(show.get("details"), dict) else {}
    model_info = show.get("model_info", {}) if isinstance(show.get("model_info"), dict) else {}
    config = show.get("parameters", "")
    return {
        "digest": show.get("digest"),
        "quantization": details.get("quantization_level") or model_info.get("general.quantization_version"),
        "family": details.get("family"),
        "parameter_size": details.get("parameter_size"),
        "template_sha256": hashlib.sha256(str(show.get("template", "")).encode()).hexdigest(),
        "config_sha256": hashlib.sha256(str(config).encode()).hexdigest(),
        "modelfile_sha256": hashlib.sha256(str(show.get("modelfile", "")).encode()).hexdigest(),
    }


def _safe_ps(value: Any) -> dict[str, Any]:
    models = value.get("models", []) if isinstance(value, dict) else []
    safe = []
    for item in models:
        if not isinstance(item, dict):
            continue
        details = item.get("details", {}) if isinstance(item.get("details"), dict) else {}
        safe.append({
            "name": item.get("name"),
            "digest": item.get("digest"),
            "size": item.get("size"),
            "size_vram": item.get("size_vram"),
            "context_length": item.get("context_length"),
            "details": {
                key: details.get(key)
                for key in ("format", "family", "families", "parameter_size", "quantization_level")
            },
        })
    return {"models": safe}


def _weights(manifest: Mapping[str, Any]) -> int:
    return sum(int(item["size"]) for item in manifest["artifacts"] if item["kind"] == "weight")


def run_probe(*, manifest_path: str | Path, model: str, expected_digest: str, endpoint: str = "http://127.0.0.1:11434", report_path: str | Path, num_ctx: int = 2048, num_predict: int = 64, request_think_false: bool = False, transport: Transport = _http_transport, run: Runner = _command, cleanup_polls: int = 3) -> dict[str, Any]:
    """Run one bounded local probe and atomically persist incremental content-free status."""
    if endpoint not in LOOPBACK_ENDPOINTS:
        raise ProbeError("endpoint must be an exact loopback literal")
    if not HEX64.fullmatch(expected_digest):
        raise ProbeError("expected_digest must be lowercase 64-hex")
    if not 1 <= num_ctx <= 2048 or not 1 <= num_predict <= 128:
        raise ProbeError("num_ctx must be <= 2048 and num_predict must be 1..128")
    source = Path(manifest_path)
    manifest = validate_manifest(json.loads(source.read_text(encoding="utf-8")))
    if manifest["profiles"]["common"] is None:
        raise ProbeError("manifest common profile is required")
    report_file = Path(report_path)
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA, "status": "incomplete", "started_at": _utc_now(),
        "candidate_id": manifest["candidate_id"], "profile": "common", "model": model,
        "expected_digest": expected_digest,
        "manifest": {"file_sha256": file_sha256(source), "canonical_sha256": canonical_sha256(manifest)},
        "native_feasibility": {"weight_total_bytes": _weights(manifest), "gpu": _gpu_snapshot(run), "official_quantization_path": manifest["quantization"]["official_artifacts"]},
        "windows_ram": _ram_snapshot(), "stages": {},
    }
    _canonical_write(report_file, report)
    try:
        pre_version = _safe_json(transport, "GET", endpoint, "/api/version")
        pre_tags = _safe_json(transport, "GET", endpoint, "/api/tags")
        pre_ps = _safe_json(transport, "GET", endpoint, "/api/ps")
        matches = [entry for entry in pre_tags.get("models", []) if isinstance(entry, dict) and entry.get("name") == model]
        if len(matches) != 1 or matches[0].get("digest") != expected_digest:
            raise ProbeError("/api/tags digest does not match expected_digest")
        report["stages"]["pre"] = {
            "version": pre_version,
            "tag": {
                key: matches[0].get(key)
                for key in ("name", "digest", "size")
            },
            "ps": _safe_ps(pre_ps),
            "gpu": _gpu_snapshot(run),
            "windows_ram": _ram_snapshot(),
        }
        show = _safe_json(transport, "POST", endpoint, "/api/show", {"name": model})
        if show.get("digest") not in {None, expected_digest}:
            raise ProbeError("/api/show digest does not match expected_digest")
        report["stages"]["show"] = {"runtime_refs": _runtime_refs(show)}
        options: dict[str, Any] = {"num_ctx": num_ctx, "temperature": 0, "seed": 42, "num_predict": num_predict}
        request = {"model": model, "prompt": PROMPT, "stream": True, "options": options}
        if request_think_false:
            request["think"] = False
        started = time.monotonic()
        try:
            response = _safe_json(transport, "POST", endpoint, "/api/generate", request)
        except HttpProbeError as exc:
            report["stages"]["generation"] = {"status": "http_error", "error": str(exc), "requested_options": options, "unsupported_options": list(options)}
            raise
        elapsed = time.monotonic() - started
        text = response.get("response")
        if response.get("model") != model or response.get("done") is not True or not isinstance(text, str):
            raise ProbeError("generation response must have exact model, done=true, and text")
        eval_count, eval_duration = response.get("eval_count"), response.get("eval_duration")
        prompt_count, prompt_duration = response.get("prompt_eval_count"), response.get("prompt_eval_duration")
        load_duration = response.get("load_duration")
        measured_ttft = None
        if all(isinstance(value, int) and value >= 0 for value in (load_duration, prompt_duration)):
            measured_ttft = (load_duration + prompt_duration) / 1_000_000_000
        report["stages"]["generation"] = {
            "status": "complete",
            "requested_options": {**options, "think": False if request_think_false else "not_requested"},
            "unsupported_options": [],
            "response": {"char_count": len(text), "sha256": hashlib.sha256(text.encode()).hexdigest()},
            "timing": {
                "estimated_ttft_seconds": measured_ttft,
                "wall_total_seconds": elapsed,
                "load_duration_ns": load_duration,
                "prompt_eval_count": prompt_count,
                "prompt_eval_duration_ns": prompt_duration,
                "eval_count": eval_count,
                "eval_duration_ns": eval_duration,
                "tokens_per_second": (eval_count / (eval_duration / 1_000_000_000)) if isinstance(eval_count, int) and eval_count > 0 and isinstance(eval_duration, int) and eval_duration > 0 else None,
            },
        }
        report["stages"]["post"] = {
            "version": _safe_json(transport, "GET", endpoint, "/api/version"),
            "show": {"runtime_refs": _runtime_refs(_safe_json(transport, "POST", endpoint, "/api/show", {"name": model}))},
            "ps": _safe_ps(_safe_json(transport, "GET", endpoint, "/api/ps")),
            "gpu": _gpu_snapshot(run),
            "windows_ram": _ram_snapshot(),
        }
        _safe_json(transport, "POST", endpoint, "/api/generate", {"model": model, "keep_alive": 0, "stream": False, "prompt": ""})
        unloaded = False
        for _ in range(cleanup_polls):
            ps = _safe_json(transport, "GET", endpoint, "/api/ps")
            if model not in {entry.get("name") for entry in ps.get("models", []) if isinstance(entry, dict)}:
                unloaded = True; break
        report["cleanup"] = {"requested_keep_alive_zero": True, "unloaded": unloaded}
        report["status"] = "complete" if unloaded else "error"
    except (OSError, KeyError, ProbeError, ValueError) as exc:
        report["status"] = "error"
        report["error"] = str(exc)
    report["finished_at"] = _utc_now()
    _canonical_write(report_file, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True); parser.add_argument("--model", required=True)
    parser.add_argument("--expected-digest", required=True); parser.add_argument("--report", required=True)
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434"); parser.add_argument("--num-ctx", type=int, default=2048)
    parser.add_argument("--num-predict", type=int, default=64); parser.add_argument("--think-false", action="store_true")
    args = parser.parse_args(argv)
    result = run_probe(manifest_path=args.manifest, model=args.model, expected_digest=args.expected_digest, endpoint=args.endpoint, report_path=args.report, num_ctx=args.num_ctx, num_predict=args.num_predict, request_think_false=args.think_false)
    print(json.dumps({"status": result["status"], "report": str(args.report)}))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
