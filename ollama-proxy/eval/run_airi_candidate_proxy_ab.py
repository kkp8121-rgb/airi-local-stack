"""Content-safe, local-only P5 proxy A→B/B→A candidate runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
import time
import urllib.request
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlsplit

PROXY_DIR = Path(__file__).resolve().parents[1]
if str(PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(PROXY_DIR))
from model_usage_manifest import canonical_sha256, file_sha256, validate_manifest
from benchmark_dialogue_quality import SYNTHETIC_CORPUS, answer_from_sse, violation_flags

REPORT_SCHEMA = "airi.candidate-proxy-ab.v1"
PROXY = "http://127.0.0.1:11435/v1/chat/completions"
OLLAMA = "http://127.0.0.1:11434"
ORIGIN = "local-quality-probe"
Transport = Callable[[str, str, Mapping[str, Any] | None, Mapping[str, str]], Any]

class ProbeError(RuntimeError): pass

def _now() -> str: return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
def _hash(value: str) -> str: return hashlib.sha256(value.encode()).hexdigest()
def _p(values: list[float], f: float) -> float | None: return round(sorted(values)[max(0, math.ceil(len(values)*f)-1)], 6) if values else None

def _atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as out:
        json.dump(value, out, ensure_ascii=False, sort_keys=True, separators=(",", ":")); out.write("\n"); staged = Path(out.name)
    os.replace(staged, path)

def _local(url: str, *, completion: bool = False) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.query or parsed.fragment or (completion and parsed.path != "/v1/chat/completions"):
        raise ProbeError("endpoint must be an exact local HTTP endpoint")

def stdlib_transport(method: str, url: str, payload: Mapping[str, Any] | None, headers: Mapping[str, str]) -> Any:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    request = urllib.request.Request(url, data=body, method=method, headers=dict(headers))
    response = urllib.request.urlopen(request, timeout=180)
    if url.endswith("/v1/chat/completions"):
        with response: return list(response)
    with response: return json.loads(response.read().decode())

def _binding(transport: Transport, proxy: str, ollama: str, model: str, digest: str) -> dict[str, Any]:
    health = transport("GET", proxy.rsplit("/v1/", 1)[0] + "/health", None, {})
    observed = health.get("chat_model", {}).get("model") if isinstance(health, dict) else None
    if observed != model: raise ProbeError("proxy health does not verify requested candidate binding")
    tags = transport("GET", ollama + "/api/tags", None, {})
    matching = [x for x in tags.get("models", []) if isinstance(x, dict) and x.get("name") == model] if isinstance(tags, dict) else []
    if len(matching) != 1 or matching[0].get("digest") != digest: raise ProbeError("Ollama tag digest binding is not exact")
    # Whitelist only production assertions, never arbitrary health content.
    if health.get("num_ctx") != 2048: raise ProbeError("proxy production num_ctx is not 2048")
    sampling = health.get("ollama_sampling_defaults")
    expected_sampling = {"temperature": 0.45, "top_p": 0.9, "repeat_penalty": 1.05}
    if not isinstance(sampling, dict) or any(sampling.get(key) != value for key, value in expected_sampling.items()):
        raise ProbeError("proxy production sampling does not match the AIRI contract")
    for feature in ("memory", "knowledge", "evaluation", "character_state_evaluator"):
        state = health.get(feature)
        if isinstance(state, dict) and state.get("enabled") is True:
            raise ProbeError(f"proxy {feature} must be disabled for isolated P5")
    moderation = health.get("output_moderation")
    if not isinstance(moderation, dict) or moderation.get("enabled") is not False:
        raise ProbeError("proxy output moderation must remain off for this comparison")
    return {"proxy_model": observed, "ollama_digest": digest, "production_num_ctx": 2048, "production_sampling": expected_sampling, "personal_state_disabled": True, "output_moderation": False}

def _stream(transport: Transport, proxy: str, model: str, prompt: str) -> tuple[str, dict[str, float | None]]:
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream", "X-AIRI-Turn-Origin": ORIGIN}
    payload = {"model": model, "stream": True, "messages": [{"role": "user", "content": prompt}]}
    started = time.monotonic(); chunks = transport("POST", proxy, payload, headers); first: float | None = None; buffered = []
    for chunk in chunks:
        if first is None and (b"content" in chunk if isinstance(chunk, bytes) else "content" in chunk): first = time.monotonic() - started
        buffered.append(chunk)
    answer, _, controls = answer_from_sse(buffered); elapsed = time.monotonic() - started
    # OpenAI stream usage is optional; estimate only from terminal-visible chars is forbidden, so tok/s is unknown.
    return answer, {"ttft_seconds": first, "total_seconds": elapsed, "tokens_per_second": None, "control_chunks_excluded": float(controls)}

def run_ab(*, manifest_path: str | Path, model: str, expected_digest: str, report_path: str | Path, proxy_endpoint: str = PROXY, ollama_endpoint: str = OLLAMA, transport: Transport = stdlib_transport, resume: bool = False) -> dict[str, Any]:
    """Run one candidate against an already-running local production proxy only."""
    _local(proxy_endpoint, completion=True); _local(ollama_endpoint)
    if len(expected_digest) != 64 or any(c not in "0123456789abcdef" for c in expected_digest): raise ProbeError("expected digest must be lowercase 64-hex")
    source = Path(manifest_path); manifest = validate_manifest(json.loads(source.read_text(encoding="utf-8")))
    target = Path(report_path)
    identity = {"candidate_id": manifest["candidate_id"], "profile": "common", "model": model, "manifest": {"file_sha256": file_sha256(source), "canonical_sha256": canonical_sha256(manifest)}, "contract": {"cases": 6, "repetitions": 10, "orders": ["A->B", "B->A"], "turns": 120, "test_origin": ORIGIN, "memory_journal_mutation": False}}
    if resume and target.is_file():
        report = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(report, dict) or report.get("schema_version") != REPORT_SCHEMA or any(report.get(key) != value for key, value in identity.items()):
            raise ProbeError("resume report identity mismatch")
        existing = report.get("turns")
        if not isinstance(existing, list) or len(existing) > 120:
            raise ProbeError("resume report turns are invalid")
        report.pop("error", None); report.pop("finished_at", None); report["status"] = "incomplete"
        report["resume_count"] = int(report.get("resume_count", 0)) + 1
    else:
        report = {"schema_version": REPORT_SCHEMA, "status": "incomplete", "started_at": _now(), **identity, "turns": []}
    _atomic(target, report)
    try:
        report["preflight"] = _binding(transport, proxy_endpoint, ollama_endpoint, model, expected_digest)
        expected_turns = []
        for repetition in range(1, 11):
            for order in ("A->B", "B->A"):
                ordered_cases = SYNTHETIC_CORPUS if order == "A->B" else tuple(reversed(SYNTHETIC_CORPUS))
                for case in ordered_cases:
                    expected_turns.append((repetition, order, case))
        for index, saved in enumerate(report["turns"]):
            repetition, order, case = expected_turns[index]
            if not isinstance(saved, dict) or (saved.get("repetition"), saved.get("order"), saved.get("case_id")) != (repetition, order, case["id"]):
                raise ProbeError("resume report is not an exact completed-turn prefix")
        for repetition, order, case in expected_turns[len(report["turns"]):]:
                    answer, timing = _stream(transport, proxy_endpoint, model, case["prompt"])
                    report["turns"].append({"case_id": case["id"], "repetition": repetition, "order": order, "response": {"char_count": len(answer), "sha256": _hash(answer)}, "structural": {"passed": not violation_flags(case, answer), "failure_types": violation_flags(case, answer)}, "timing": timing})
                    _atomic(target, report)
        total = [t["timing"]["total_seconds"] for t in report["turns"]]; ttft = [t["timing"]["ttft_seconds"] for t in report["turns"] if isinstance(t["timing"]["ttft_seconds"], float)]
        report["aggregate"] = {"turn_count": len(report["turns"]), "structural_pass_count": sum(t["structural"]["passed"] for t in report["turns"]), "latency": {"ttft_p50": _p(ttft,.5), "ttft_p95": _p(ttft,.95), "total_p50": _p(total,.5), "total_p95": _p(total,.95), "tokens_per_second_p50": None, "tokens_per_second_p95": None}}
        report["status"] = "complete"
    except Exception as exc:
        report["status"] = "error"; report["error"] = {"type": type(exc).__name__, "message": "proxy A/B did not complete"}
    report["finished_at"] = _now(); _atomic(target, report); return report

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--manifest",required=True); p.add_argument("--model",required=True); p.add_argument("--expected-digest",required=True); p.add_argument("--report",required=True); p.add_argument("--proxy-endpoint",default=PROXY); p.add_argument("--ollama-endpoint",default=OLLAMA); p.add_argument("--resume",action="store_true"); a=p.parse_args(argv)
    return 0 if run_ab(manifest_path=a.manifest,model=a.model,expected_digest=a.expected_digest,report_path=a.report,proxy_endpoint=a.proxy_endpoint,ollama_endpoint=a.ollama_endpoint,resume=a.resume)["status"] == "complete" else 1
if __name__ == "__main__": raise SystemExit(main())
