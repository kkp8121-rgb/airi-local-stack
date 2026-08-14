"""Experimental, localhost-only Ollama-shaped server for the pinned Motif snapshot.

This is a Transformers runtime, not an Ollama model or conversion.  It refuses
network paths and verifies the complete pinned snapshot (including audited
remote-code files) before importing Torch or Transformers.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse

from model_usage_manifest import canonical_json_bytes, canonical_sha256, file_sha256, validate_manifest


TAG = "motif-airi:2.6b-v1.1-lc-nf4"
CANDIDATE_ID = "motif-2.6b-v1.1-lc"
REPOSITORY = "Motif-Technologies/Motif-2.6b-v1.1-LC"
REVISION = "70bf316e166f2a256b1068e35c8310541a6a06bc"
NUM_CTX = 2048
DEFAULT_PORT = 11437
QUANTIZATION = {
    "load_in_4bit": True, "bnb_4bit_quant_type": "nf4",
    "bnb_4bit_compute_dtype": "bfloat16", "bnb_4bit_use_double_quant": True,
}
# These are deliberately an explicit runtime compatibility lock, rather than a
# claim that Motif is an Ollama-native artifact.
DEPENDENCY_LOCK = {"accelerate": "1.6.0", "bitsandbytes": "0.45.5", "torch": "2.5.1+cu121", "transformers": "4.51.3"}
OFFLINE_ENV = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1"}
_HEX = re.compile(r"^[0-9a-f]{64}$")


class MotifBackendError(ValueError):
    """A safe-to-return backend contract error."""


class GenerationResult:
    """Content plus safe counters; prompts never leave the request handler."""
    def __init__(self, content: str, prompt_eval_count: int, eval_count: int, eval_duration: int) -> None:
        self.content = content
        self.prompt_eval_count = prompt_eval_count
        self.eval_count = eval_count
        self.eval_duration = eval_duration


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        staged = Path(handle.name)
        handle.write(canonical_json_bytes(value) + b"\n")
    try:
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def _safe_snapshot(path: str | Path) -> Path:
    value = Path(path)
    if not value.is_absolute() or "://" in str(path) or str(path).startswith("hf:"):
        raise MotifBackendError("snapshot must be an absolute local directory")
    if _is_link_or_reparse(value):
        raise MotifBackendError("snapshot must not be a link or reparse point")
    try:
        resolved = value.resolve(strict=True)
    except OSError as exc:
        raise MotifBackendError("snapshot must be an existing local directory") from exc
    if not resolved.is_dir() or resolved.is_symlink():
        raise MotifBackendError("snapshot must be an existing non-symlink directory")
    return resolved


def _relative_path(value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise MotifBackendError("pinned artifact path is invalid")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise MotifBackendError("pinned artifact path is invalid")
    return path


def _is_link_or_reparse(path: Path) -> bool:
    """Windows junctions are reparse points but not always ``Path.is_symlink``."""
    try:
        stat_result = path.lstat()
    except OSError as exc:
        raise MotifBackendError("snapshot entry cannot be inspected") from exc
    return path.is_symlink() or bool(getattr(stat_result, "st_file_attributes", 0) & 0x400)


def _reject_links_or_reparse_points(root: Path) -> None:
    """Walk every entry so an unpinned junction cannot escape the snapshot."""
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            children = list(directory.iterdir())
        except OSError as exc:
            raise MotifBackendError("snapshot directory cannot be inspected") from exc
        for child in children:
            if _is_link_or_reparse(child):
                raise MotifBackendError("snapshot contains a link or reparse point")
            if child.is_dir():
                pending.append(child)


def _load_manifest(path: str | Path) -> tuple[dict[str, Any], str, str]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        manifest = validate_manifest(raw)
    except Exception as exc:
        raise MotifBackendError("manifest validation failed") from exc
    if manifest["candidate_id"] != CANDIDATE_ID or manifest["repo_id"] != REPOSITORY or manifest["exact_revision"] != REVISION:
        raise MotifBackendError("manifest is not the exact pinned Motif candidate")
    if not manifest["remote_code"]["required"]:
        raise MotifBackendError("Motif audited remote code declaration is required")
    canonical = canonical_sha256(manifest)
    return manifest, file_sha256(path), canonical


def verify_snapshot(manifest: Mapping[str, Any], snapshot_path: str | Path) -> dict[str, Any]:
    """Hash every manifest and audited-code artifact without importing ML code."""
    snapshot = _safe_snapshot(snapshot_path)
    _reject_links_or_reparse_points(snapshot)
    required = list(manifest["artifacts"])
    audited = list(manifest["remote_code"]["audited_artifacts"])
    by_path = {item["path"]: item for item in required}
    if len(by_path) != len(required):
        raise MotifBackendError("pinned snapshot artifact paths must be unique")
    expected_paths = set(by_path)
    actual_paths: set[str] = set()
    for directory, _directories, files in os.walk(snapshot, topdown=True, followlinks=False):
        root_path = Path(directory)
        for name in files:
            target = root_path / name
            if not target.is_file():
                raise MotifBackendError("snapshot contains a non-regular artifact")
            actual_paths.add(target.relative_to(snapshot).as_posix())
    if actual_paths != expected_paths:
        raise MotifBackendError("snapshot artifact set is not exact")
    for item in audited:
        existing = by_path.get(item["path"])
        if existing is None or any(existing[field] != item[field] for field in ("path", "size", "sha256")):
            raise MotifBackendError("audited code is not identically pinned in manifest artifacts")
    checked: list[dict[str, Any]] = []
    root = str(snapshot)
    for item in required:
        relative = _relative_path(item["path"])
        try:
            target = (snapshot / relative).resolve(strict=True)
        except OSError as exc:
            raise MotifBackendError("required pinned snapshot artifact is missing") from exc
        if _is_link_or_reparse(target) or not target.is_file() or (str(target) != root and not str(target).startswith(root + os.sep)):
            raise MotifBackendError("required pinned snapshot artifact is unsafe")
        if target.stat().st_size != item["size"] or file_sha256(target) != item["sha256"]:
            raise MotifBackendError("required pinned snapshot artifact hash mismatch")
        checked.append({"kind": item["kind"], "sha256": item["sha256"], "size": item["size"]})
    if not any(item["kind"] == "weight" for item in checked):
        raise MotifBackendError("pinned snapshot contains no weights")
    return {"artifact_count": len(checked), "audited_code_count": len(audited), "artifacts": checked}


def runtime_digest(manifest_canonical_sha256: str) -> str:
    if not isinstance(manifest_canonical_sha256, str) or not _HEX.fullmatch(manifest_canonical_sha256):
        raise MotifBackendError("manifest canonical digest must be 64 lowercase hex")
    return hashlib.sha256(canonical_json_bytes({"manifest_canonical_sha256": manifest_canonical_sha256, "dependency_lock": DEPENDENCY_LOCK, "quantization": QUANTIZATION, "tag": TAG})).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class MotifBackend:
    def __init__(self, *, manifest_path: str | Path, snapshot_path: str | Path, gpu_max_mib: int = 6144, cpu_max_gib: int = 8, report_path: str | Path | None = None, loader: Callable[..., tuple[Any, Any, Any]] | None = None, version_resolver: Callable[[str], str] | None = None) -> None:
        if not isinstance(gpu_max_mib, int) or not isinstance(cpu_max_gib, int) or gpu_max_mib < 1 or cpu_max_gib < 1:
            raise MotifBackendError("memory bounds must be positive integers")
        self.manifest, self.manifest_file_sha256, self.manifest_canonical_sha256 = _load_manifest(manifest_path)
        self.snapshot = _safe_snapshot(snapshot_path)
        self.preflight = verify_snapshot(self.manifest, self.snapshot)
        self.digest = runtime_digest(self.manifest_canonical_sha256)
        self.max_memory = {0: f"{gpu_max_mib}MiB", "cpu": f"{cpu_max_gib}GiB"}
        self.report_path = Path(report_path) if report_path else None
        self.loader = loader
        self.version_resolver = version_resolver or importlib.metadata.version
        self.model: Any = None; self.tokenizer: Any = None; self.torch: Any = None
        self._generation_lock = threading.RLock()
        self._report("ready")

    def _report(self, status: str, error: str | None = None) -> None:
        if self.report_path is None:
            return
        report: dict[str, Any] = {"schema_version": "airi.motif-local-backend-audit.v1", "status": status, "finished_at": _utc_now(), "candidate_id": CANDIDATE_ID, "exact_revision": REVISION, "manifest_file_sha256": self.manifest_file_sha256, "manifest_canonical_sha256": self.manifest_canonical_sha256, "runtime_digest": self.digest, "preflight": self.preflight, "dependency_lock": DEPENDENCY_LOCK, "quantization": QUANTIZATION}
        if error:
            report["error"] = error
        _atomic_write(self.report_path, report)

    def provenance(self) -> dict[str, Any]:
        return {"candidate_id": CANDIDATE_ID, "repo_id": REPOSITORY, "exact_revision": REVISION, "manifest_file_sha256": self.manifest_file_sha256, "manifest_canonical_sha256": self.manifest_canonical_sha256, "runtime": "transformers-local-nf4-not-ollama-native", "dependency_lock": DEPENDENCY_LOCK, "quantization": QUANTIZATION, "num_ctx": NUM_CTX}

    def _load(self) -> None:
        if self.model is not None:
            return
        verify_snapshot(self.manifest, self.snapshot)  # closes the preflight/load TOCTOU window
        os.environ.update(OFFLINE_ENV)
        self._verify_dependency_lock()
        try:
            if self.loader is not None:
                self.model, self.tokenizer, self.torch = self.loader(self.snapshot, self.max_memory, QUANTIZATION)
            else:
                import torch
                from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
                quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
                tokenizer = AutoTokenizer.from_pretrained(self.snapshot, local_files_only=True, trust_remote_code=False, use_safetensors=True)
                model = AutoModelForCausalLM.from_pretrained(self.snapshot, local_files_only=True, trust_remote_code=True, quantization_config=quant, torch_dtype=torch.bfloat16, device_map="auto", max_memory=self.max_memory, attn_implementation="eager", offload_buffers=True, low_cpu_mem_usage=True, use_safetensors=True)
                self.model, self.tokenizer, self.torch = model, tokenizer, torch
        except Exception as exc:
            self.cleanup()
            self._report("error", "runtime load failed: " + type(exc).__name__)
            raise MotifBackendError("local Motif runtime load failed") from exc
        self._report("loaded")

    def _verify_dependency_lock(self) -> None:
        observed: dict[str, str] = {}
        for package, expected in DEPENDENCY_LOCK.items():
            try:
                observed[package] = self.version_resolver(package)
            except Exception as exc:
                raise MotifBackendError("required local runtime dependency is not installed") from exc
            if observed[package] != expected:
                raise MotifBackendError("installed runtime dependency versions do not match the pinned lock")

    def cleanup(self) -> None:
        with self._generation_lock:
            self.model = None; self.tokenizer = None
            torch = self.torch; self.torch = None
            gc.collect()
            if torch is not None:
                try:
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except (AttributeError, RuntimeError):
                    pass
            self._report("ready")

    def _generation_options(self, body: Mapping[str, Any]) -> dict[str, Any]:
        options = body.get("options", {})
        if not isinstance(options, Mapping):
            raise MotifBackendError("options must be an object")
        supported = {"temperature", "top_p", "repeat_penalty", "num_predict", "num_ctx", "seed", "num_gpu", "repeat_last_n"}
        unknown = sorted(set(options) - supported)
        if unknown:
            raise MotifBackendError("unsupported option: " + unknown[0])
        if body.get("think", False) is not False:
            raise MotifBackendError("unsupported think mode: Motif has no AIRI reasoning mode")
        if "format" in body and body["format"] is not None:
            raise MotifBackendError("unsupported format: constrained decoding is unavailable")
        if "repeat_last_n" in options or "repeat_last_n" in body:
            raise MotifBackendError("unsupported option: repeat_last_n")
        result: dict[str, Any] = {"do_sample": False}
        temperature = options.get("temperature", body.get("temperature", 0))
        top_p = options.get("top_p", body.get("top_p", 1))
        repeat = options.get("repeat_penalty", body.get("repeat_penalty", 1))
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in (temperature, top_p, repeat)):
            raise MotifBackendError("temperature, top_p, and repeat_penalty must be numbers")
        if temperature < 0 or top_p <= 0 or top_p > 1 or repeat <= 0:
            raise MotifBackendError("temperature/top_p/repeat_penalty out of range")
        if temperature > 0:
            result.update({"do_sample": True, "temperature": float(temperature), "top_p": float(top_p)})
        result["repetition_penalty"] = float(repeat)
        limit = options.get("num_predict", body.get("num_predict", 256))
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= NUM_CTX:
            raise MotifBackendError("num_predict must be an integer from 1 to 2048")
        context = options.get("num_ctx", body.get("num_ctx", NUM_CTX))
        if not isinstance(context, int) or isinstance(context, bool) or not 1 <= context <= NUM_CTX:
            raise MotifBackendError("num_ctx must be an integer from 1 to 2048")
        if limit > context:
            raise MotifBackendError("num_predict exceeds effective num_ctx")
        num_gpu = options.get("num_gpu", body.get("num_gpu", 999))
        if not isinstance(num_gpu, int) or isinstance(num_gpu, bool) or num_gpu != 999:
            raise MotifBackendError("num_gpu must be 999 (device_map=auto)")
        result["max_new_tokens"] = limit
        result["num_ctx"] = context
        seed = options.get("seed", body.get("seed"))
        if seed is not None:
            if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= 2 ** 31 - 1:
                raise MotifBackendError("seed must be an integer from 0 to 2147483647")
            result["seed"] = seed
        return result

    def _apply_seed(self, options: Mapping[str, Any]) -> None:
        if "seed" not in options:
            return
        torch = self.torch
        if torch is None:
            raise MotifBackendError("local Motif runtime did not expose Torch for seeded generation")
        try:
            torch.manual_seed(options["seed"])
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(options["seed"])
        except Exception as exc:
            raise MotifBackendError("could not apply requested local seed") from exc

    def chat(self, body: Mapping[str, Any]) -> GenerationResult:
        if body.get("model") not in (None, TAG):
            raise MotifBackendError("requested model is not available")
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            raise MotifBackendError("messages must be a non-empty array")
        if any(not isinstance(item, Mapping) or item.get("role") not in {"system", "user", "assistant"} or not isinstance(item.get("content"), str) for item in messages):
            raise MotifBackendError("messages must contain role and string content")
        options = self._generation_options(body)
        with self._generation_lock:
            self._load()
            self._apply_seed(options)
            try:
                started = time.monotonic_ns()
                if hasattr(self.model, "generate_text"):
                    content = str(self.model.generate_text(messages, options))
                    return GenerationResult(content, 0, 0, time.monotonic_ns() - started)
                encoded = self.tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt")
                input_count = int(encoded.shape[-1])
                if input_count + options["max_new_tokens"] > options["num_ctx"]:
                    raise MotifBackendError("encoded prompt plus requested completion exceeds effective num_ctx")
                device = self.model.get_input_embeddings().weight.device
                generation_options = {key: value for key, value in options.items() if key not in {"seed", "num_ctx"}}
                generated = self.model.generate(encoded.to(device), pad_token_id=self.tokenizer.pad_token_id, eos_token_id=self.tokenizer.eos_token_id, **generation_options)
                tokens = generated[0][input_count:]
                return GenerationResult(self.tokenizer.decode(tokens, skip_special_tokens=True), input_count, int(tokens.shape[-1]), time.monotonic_ns() - started)
            except Exception as exc:
                if isinstance(exc, MotifBackendError):
                    raise
                raise MotifBackendError("local Motif generation failed") from exc

    def generate(self, body: Mapping[str, Any]) -> GenerationResult:
        prompt = body.get("prompt")
        if not isinstance(prompt, str):
            raise MotifBackendError("prompt must be a string")
        return self.chat({**body, "messages": [{"role": "user", "content": prompt}]})


def _json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def make_handler(backend: MotifBackend) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return
        def _send(self, status: int, value: Mapping[str, Any]) -> None:
            data = _json(value); self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        def _body(self) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0")); raw = self.rfile.read(length)
                value = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                raise MotifBackendError("request body must be JSON")
            if not isinstance(value, dict): raise MotifBackendError("request body must be an object")
            return value
        def do_GET(self) -> None:
            if self.path == "/api/version": self._send(200, {"version": "motif-transformers-local/experimental"})
            elif self.path == "/api/tags": self._send(200, {"models": [{"name": TAG, "model": TAG, "digest": backend.digest, "details": {"family": "motif", "format": "transformers-nf4", "parameter_size": "2.6B"}, "provenance": backend.provenance()}]})
            elif self.path == "/api/ps": self._send(200, {"models": ([{"name": TAG, "model": TAG, "digest": backend.digest, "size_vram": 0}] if backend.model is not None else [])})
            else: self._send(404, {"error": "not found"})
        def do_POST(self) -> None:
            try:
                body = self._body()
                if self.path == "/api/show":
                    if body.get("name") not in (None, TAG): raise MotifBackendError("requested model is not available")
                    self._send(200, {"modelfile": "# Transformers local runtime; not Ollama-native", "digest": backend.digest, "parameters": "num_ctx 2048\ntemperature 0\ntop_p 1\nrepeat_penalty 1", "template": "official pinned tokenizer chat template", "details": {"family": "motif", "format": "transformers-nf4"}, "model_info": {**backend.provenance(), "template_sha256": backend.manifest["template"]["sha256"]}})
                    if body.get("keep_alive") == 0: backend.cleanup()
                    return
                if self.path == "/api/chat":
                    result = backend.chat(body); response_key = "message"
                elif self.path == "/api/generate":
                    result = backend.generate(body); response_key = "response"
                else: self._send(404, {"error": "not found"}); return
                elapsed = result.eval_duration
                request_options = body.get("options", {})
                requested_seed = request_options.get("seed", body.get("seed")) if isinstance(request_options, Mapping) else None
                keep_alive_zero = body.get("keep_alive") == 0
                if body.get("stream", True) is False:
                    payload: dict[str, Any] = {"model": TAG, "done": True, "total_duration": elapsed, "eval_duration": result.eval_duration, "prompt_eval_count": result.prompt_eval_count, "eval_count": result.eval_count}
                    if isinstance(requested_seed, int) and not isinstance(requested_seed, bool): payload["seed"] = requested_seed
                    payload[response_key] = result.content if response_key == "response" else {"role": "assistant", "content": result.content}
                    self._send(200, payload)
                else:
                    self.send_response(200); self.send_header("Content-Type", "application/x-ndjson"); self.end_headers()
                    initial: dict[str, Any] = {"model": TAG, "done": False}
                    initial[response_key] = result.content if response_key == "response" else {"role": "assistant", "content": result.content}
                    terminal: dict[str, Any] = {"model": TAG, "done": True, "total_duration": elapsed, "eval_duration": result.eval_duration, "prompt_eval_count": result.prompt_eval_count, "eval_count": result.eval_count}
                    if isinstance(requested_seed, int) and not isinstance(requested_seed, bool): terminal["seed"] = requested_seed
                    terminal[response_key] = "" if response_key == "response" else {"role": "assistant", "content": ""}
                    self.wfile.write(_json(initial) + b"\n")
                    self.wfile.write(_json(terminal) + b"\n"); self.wfile.flush()
                if keep_alive_zero: backend.cleanup()
            except MotifBackendError as exc:
                self._send(400, {"error": str(exc)})
    return Handler


def serve(*, host: str, port: int, backend: MotifBackend) -> ThreadingHTTPServer:
    if host != "127.0.0.1":
        raise MotifBackendError("Motif backend binds only to 127.0.0.1")
    return ThreadingHTTPServer((host, port), make_handler(backend))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True); parser.add_argument("--snapshot", required=True); parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1"); parser.add_argument("--gpu-max-mib", type=int, default=6144); parser.add_argument("--cpu-max-gib", type=int, default=8); parser.add_argument("--audit-report")
    args = parser.parse_args(argv)
    backend = MotifBackend(manifest_path=args.manifest, snapshot_path=args.snapshot, gpu_max_mib=args.gpu_max_mib, cpu_max_gib=args.cpu_max_gib, report_path=args.audit_report)
    server = serve(host=args.host, port=args.port, backend=backend)
    try: server.serve_forever()
    finally: backend.cleanup(); server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
