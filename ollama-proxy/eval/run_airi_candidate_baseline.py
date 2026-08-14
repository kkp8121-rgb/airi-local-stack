"""Content-safe P2 raw Ollama baseline runner for one AIRI candidate at a time."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse

from model_usage_manifest import canonical_sha256, file_sha256, validate_manifest
from run_airi_baseline import build_case_system_prompt, load_system_prompt


REPORT_SCHEMA = "airi.ollama-candidate-baseline.v1"
FIXTURE = Path(__file__).with_name("airi_baseline_cases.json")
ENDPOINT = "http://127.0.0.1:11434"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
CONTROL_RE = re.compile(r"<\|(?:ACT|CALL|DELAY)\b.*?\|>", re.I | re.S)
EMOJI_RE = re.compile(r"[\u2600-\u27BF\uFE0F\U0001F1E6-\U0001FAFF]")
MARKDOWN_RE = re.compile(r"(?:^\s{0,3}#{1,6}\s|```|`|\*\*|__|\[[^\]]+\]\([^)]+\))", re.M)
Transport = Callable[[str, str, Mapping[str, Any] | None], Any]


class RunnerError(RuntimeError):
    pass


class HttpError(RunnerError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _atomic(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(report, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        staged = Path(handle.name)
    os.replace(staged, path)


def _require_loopback(endpoint: str) -> None:
    parsed = urlparse(endpoint)
    if parsed.scheme != "http" or parsed.netloc not in {
        "127.0.0.1:11434",
        "localhost:11434",
        "127.0.0.1:11437",
        "localhost:11437",
    } or parsed.path not in {"", "/"}:
        raise RunnerError("endpoint must be an approved local Ollama-compatible loopback")


def _request(transport: Transport, method: str, endpoint: str, path: str, body: Mapping[str, Any] | None = None) -> Any:
    return transport(method, endpoint + path, body)


def local_ollama_transport(method: str, url: str, body: Mapping[str, Any] | None) -> Any:
    """Minimal stdlib transport; chat streams become an iterator of NDJSON objects."""
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method=method, headers={"Content-Type": "application/json"})
    try:
        response = urllib.request.urlopen(request, timeout=180)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise HttpError(f"HTTP {exc.code}; response_sha256={_hash(detail)}") from exc
    if url.endswith("/api/chat"):
        def events() -> Iterable[Mapping[str, Any]]:
            with response:
                for line in response:
                    if line.strip():
                        try: yield json.loads(line.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise RunnerError("invalid Ollama NDJSON stream") from exc
        return events()
    with response:
        try: return json.loads(response.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise RunnerError("invalid Ollama JSON response") from exc


def _fixture(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes(); fixture = json.loads(raw.decode("utf-8"))
    cases = fixture.get("cases") if isinstance(fixture, dict) else None
    if fixture.get("synthetic_only") is not True or not isinstance(cases, list) or len(cases) != 16:
        raise RunnerError("baseline fixture must be immutable synthetic 16-case suite")
    if any(not isinstance(case, dict) or not isinstance(case.get("messages"), list) or not isinstance(case.get("checks"), dict) for case in cases):
        raise RunnerError("baseline fixture has invalid case structure")
    return fixture, hashlib.sha256(raw).hexdigest()


def _score(text: str, checks: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[str] = []; lower = text.lower()
    if checks.get("required_any") and not any(str(item).lower() in lower for item in checks["required_any"]): failures.append("required_any")
    if any(str(item).lower() in lower for item in checks.get("forbidden_any", [])): failures.append("forbidden_any")
    if checks.get("no_control_tokens") and CONTROL_RE.search(text): failures.append("no_control_tokens")
    if checks.get("no_emoji") and EMOJI_RE.search(text): failures.append("no_emoji")
    if checks.get("no_markdown") and MARKDOWN_RE.search(text): failures.append("no_markdown")
    if isinstance(checks.get("max_chars"), int) and len(text) > checks["max_chars"]: failures.append("max_chars")
    sentences = len([part for part in re.split(r"[.!?]+", text) if part.strip()])
    if isinstance(checks.get("max_sentences"), int) and sentences > checks["max_sentences"]: failures.append("max_sentences")
    return {"passed": not failures, "failures": failures, "char_count": len(text), "sentence_count": sentences, "question_count": text.count("?")}


def _timing(final: Mapping[str, Any], started: float, first: float | None) -> dict[str, Any]:
    count, duration = final.get("eval_count"), final.get("eval_duration")
    return {"wall_ttft_seconds": first, "wall_total_seconds": time.monotonic() - started, "eval_count": count, "eval_duration_ns": duration, "tokens_per_second": count / (duration / 1_000_000_000) if isinstance(count, int) and count > 0 and isinstance(duration, int) and duration > 0 else None}


def _read_stream(events: Iterable[Mapping[str, Any]], expected_model: str) -> tuple[str, dict[str, Any]]:
    started = time.monotonic(); first: float | None = None; chunks: list[str] = []; terminal: Mapping[str, Any] | None = None
    for event in events:
        if not isinstance(event, dict): raise RunnerError("stream event must be an object")
        message = event.get("message", {})
        content = message.get("content", "") if isinstance(message, dict) else ""
        if not isinstance(content, str): raise RunnerError("stream content must be text")
        if content and first is None: first = time.monotonic() - started
        chunks.append(content)
        if event.get("done") is True: terminal = event
    if terminal is None: raise RunnerError("stream ended without done:true")
    if terminal.get("model") != expected_model: raise RunnerError("stream terminal model mismatch")
    return "".join(chunks), _timing(terminal, started, first)


def _thinking_disabled_common(manifest: Mapping[str, Any]) -> bool:
    thinking = manifest.get("thinking")
    common = manifest["profiles"]["common"]["supported_options"]
    common_disabled = isinstance(common, dict) and common.get("enable_thinking") is False
    return isinstance(thinking, dict) and (
        common_disabled
        or thinking.get("airi") is False
        or (thinking.get("default") is True and thinking.get("airi_enable_thinking") is False)
    )


def _safe_show(show: Mapping[str, Any]) -> dict[str, Any]:
    details = show.get("details", {}) if isinstance(show.get("details"), dict) else {}
    model_info = show.get("model_info", {}) if isinstance(show.get("model_info"), dict) else {}
    raw = json.dumps(show, ensure_ascii=False, sort_keys=True)
    return {"digest": show.get("digest"), "details": {key: details.get(key) for key in ("format", "family", "families", "parameter_size", "quantization_level") if key in details}, "blob_refs": sorted(set(re.findall(r"sha256:[0-9a-fA-F]{16,}", raw))), "template_sha256": _hash(str(show.get("template", ""))), "parameters_sha256": _hash(str(show.get("parameters", ""))), "modelfile_sha256": _hash(str(show.get("modelfile", ""))), "config_sha256": _hash(json.dumps(model_info, ensure_ascii=False, sort_keys=True))}


def run_baseline(*, manifest_path: str | Path, model: str, expected_digest: str, report_path: str | Path, endpoint: str = ENDPOINT, repetitions: int = 3, fixture_path: str | Path = FIXTURE, transport: Transport, cleanup_polls: int = 3, resume: bool = False, num_predict: int = 256) -> dict[str, Any]:
    """Run sequential raw chat baseline trials and persist an atomic content-safe report."""
    _require_loopback(endpoint)
    if not HEX64.fullmatch(expected_digest): raise RunnerError("expected_digest must be lowercase 64-hex")
    if not 1 <= repetitions <= 10: raise RunnerError("repetitions must be 1..10")
    if not isinstance(num_predict, int) or not 1 <= num_predict <= 2048: raise RunnerError("num_predict must be 1..2048")
    manifest_file = Path(manifest_path); manifest = validate_manifest(json.loads(manifest_file.read_text(encoding="utf-8")))
    fixture, fixture_digest = _fixture(Path(fixture_path))
    system_prompt = load_system_prompt()
    tags = _request(transport, "GET", endpoint, "/api/tags")
    installed = next((item for item in tags.get("models", []) if isinstance(item, dict) and item.get("name") == model), None)
    if not isinstance(installed, dict) or installed.get("digest") != expected_digest: raise RunnerError("/api/tags exact model digest mismatch")
    report_file = Path(report_path)
    options = {"num_ctx": 2048, "temperature": 0, "seed": 42, "num_predict": num_predict}
    identity = {"candidate_id": manifest["candidate_id"], "profile": "common", "model": model, "expected_digest": expected_digest, "manifest": {"file_sha256": file_sha256(manifest_file), "canonical_sha256": canonical_sha256(manifest)}, "fixture": {"sha256": fixture_digest, "case_count": 16, "repetitions": repetitions}, "system_prompt_sha256": _hash(system_prompt), "requested_options": options, "requested_thinking": "disabled" if _thinking_disabled_common(manifest) else "not_applicable_or_unknown"}
    if resume and report_file.is_file():
        prior = json.loads(report_file.read_text(encoding="utf-8"))
        if not isinstance(prior, dict) or prior.get("schema_version") != REPORT_SCHEMA:
            raise RunnerError("resume report schema mismatch")
        if any(prior.get(key) != value for key, value in identity.items()):
            raise RunnerError("resume report identity mismatch")
        completed = prior.get("cases")
        if not isinstance(completed, list) or len(completed) > len(fixture["cases"]):
            raise RunnerError("resume report cases are invalid")
        for index, saved in enumerate(completed):
            if not isinstance(saved, dict) or saved.get("id") != fixture["cases"][index]["id"] or not isinstance(saved.get("runs"), list) or len(saved["runs"]) != repetitions:
                raise RunnerError("resume report is not an exact completed-case prefix")
        report = prior
        report.pop("error", None); report.pop("finished_at", None)
        report["status"] = "incomplete"
        report.setdefault("resume", {})["count"] = int(report.get("resume", {}).get("count", 0)) + 1
        report["resume"]["last_resumed_at"] = _now()
    else:
        report = {"schema_version": REPORT_SCHEMA, "status": "incomplete", "started_at": _now(), **identity, "applied_options": [], "unsupported_options": [], "cases": [], "stages": {"tags": {"digest": installed["digest"]}}}
    _atomic(report_file, report)
    try:
        show = _request(transport, "POST", endpoint, "/api/show", {"name": model})
        if not isinstance(show, dict) or show.get("digest") not in {None, expected_digest}: raise RunnerError("/api/show model digest conflicts with /api/tags binding")
        report["stages"]["show"] = _safe_show(show)
        think = _thinking_disabled_common(manifest)
        for case in fixture["cases"][len(report["cases"]):]:
            case_system = build_case_system_prompt(system_prompt, case)
            samples = []
            for index in range(repetitions):
                payload: dict[str, Any] = {"model": model, "stream": True, "messages": [{"role": "system", "content": case_system}, *case["messages"]], "options": options}
                if think: payload["think"] = False
                try:
                    text, timing = _read_stream(_request(transport, "POST", endpoint, "/api/chat", payload), model)
                except HttpError as exc:
                    report["unsupported_options"] = list(options)
                    report["status"] = "error"; report["error"] = str(exc); _atomic(report_file, report); return report
                samples.append({"run": index + 1, "response": {"char_count": len(text), "sha256": _hash(text)}, "checks": _score(text, case["checks"]), "timing": timing})
                report["applied_options"] = sorted(options)
            failures = sorted({item for sample in samples for item in sample["checks"]["failures"]})
            report["cases"].append({"id": case["id"], "category": case["category"], "case_system_prompt_sha256": _hash(case_system), "checks": {"passed": not failures, "failures": failures}, "runs": samples})
            _atomic(report_file, report)
        _request(transport, "POST", endpoint, "/api/generate", {"model": model, "keep_alive": 0, "stream": False, "prompt": ""})
        unloaded = False
        for _ in range(cleanup_polls):
            ps = _request(transport, "GET", endpoint, "/api/ps")
            if model not in {entry.get("name") for entry in ps.get("models", []) if isinstance(entry, dict)}: unloaded = True; break
        report["cleanup"] = {"requested_keep_alive_zero": True, "unloaded": unloaded}
        report["status"] = "complete" if unloaded else "error"
    except (HttpError, OSError, ValueError, RunnerError, TypeError) as exc:
        report["status"] = "error"; report["error"] = str(exc)
    report["finished_at"] = _now(); _atomic(report_file, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True); parser.add_argument("--model", required=True); parser.add_argument("--expected-digest", required=True); parser.add_argument("--report", required=True)
    parser.add_argument("--endpoint", default=ENDPOINT); parser.add_argument("--repetitions", type=int, default=3); parser.add_argument("--num-predict", type=int, default=256)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    result = run_baseline(manifest_path=args.manifest, model=args.model, expected_digest=args.expected_digest, report_path=args.report, endpoint=args.endpoint, repetitions=args.repetitions, transport=local_ollama_transport, resume=args.resume, num_predict=args.num_predict)
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
