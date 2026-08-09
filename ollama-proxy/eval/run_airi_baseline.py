"""Synthetic-only, local baseline evaluator for an Ollama AIRI model."""
from __future__ import annotations

import argparse
import ast
import hashlib
import http.client
import json
import os
import platform
import re
import shutil
import socket
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

RUNNER_VERSION = "0.3.4"
DEFAULT_ENDPOINT = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "exaone-airi:2.4b"
ACTIVE_CARD_MAX_CHARS = 4096
CONTROL_RE = re.compile(r"<\|(?:ACT|CALL|DELAY)\b.*?\|>", re.I | re.S)
MALFORMED_CONTROL_RE = re.compile(r"<\|(?:ACT|CALL|DELAY)\b[^\r\n]{0,2048}\|>?", re.I)
TOOL_CLAIM_RE = re.compile(r"(?:파일|컴퓨터|검색|도구).{0,16}(?:삭제했|지웠|실행했|완료했|찾았)")
EMOJI_RE = re.compile(r"[\u2600-\u27BF\uFE0F\U0001F1E6-\U0001FAFF]")
MARKDOWN_RE = re.compile(r"(?:^\s{0,3}#{1,6}\s|```|`|\*\*|__|\[[^\]]+\]\([^)]+\))", re.M)
STAGE_DIRECTION_RE = re.compile(r"(?:\[[^\]\n]{0,80}\]|\([^\)\n]{0,80}\)|（[^）\n]{0,80}）)")
EMOTICON_RE = re.compile(r"(?:(?:[:;=8xX][-^']?[)(DPp/\\|])|(?:\^[._^]*\^)|(?:[ㅎㅋㅠㅜ]{2,}))")


class EvalError(RuntimeError):
    pass


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def runtime_metadata(endpoint, runtime_config):
    """Return only reproducibility inputs that are safe to include in a report."""
    parsed = ensure_local_endpoint(endpoint)
    version_url = parsed._replace(path="/api/version", params="", query="", fragment="").geturl()
    version_response = request_json(version_url, method="GET")
    ollama_version = version_response.get("version") if isinstance(version_response, dict) else None
    if not isinstance(ollama_version, str):
        raise EvalError("Ollama version metadata is missing a version string")
    return {
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runner_version": RUNNER_VERSION,
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
        },
        "ollama_version": ollama_version,
        "runtime_config": runtime_config,
    }


def runtime_sha256(metadata):
    """Hash the canonical, privacy-safe runtime fingerprint inputs."""
    return sha256_text(canonical_json(metadata))


def load_system_prompt(proxy_path=None):
    """Extract literal AIRI_SYSTEM_PROMPT through AST; never import the proxy."""
    proxy_path = Path(proxy_path) if proxy_path else Path(__file__).resolve().parents[1] / "ollama_proxy.py"
    try:
        tree = ast.parse(proxy_path.read_text(encoding="utf-8"), filename=str(proxy_path))
    except (OSError, SyntaxError) as exc:
        raise EvalError("cannot safely load AIRI system prompt") from exc
    # Read the effective module assignment without importing the proxy.
    for node in reversed(tree.body):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "AIRI_SYSTEM_PROMPT" for t in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    raise EvalError("AIRI_SYSTEM_PROMPT literal not found in proxy")


def validate_fixture(fixture):
    if not isinstance(fixture, dict) or fixture.get("synthetic_only") is not True:
        raise EvalError("fixture must declare synthetic_only: true")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or not 8 <= len(cases) <= 20:
        raise EvalError("fixture requires 8 to 20 cases")
    ids = set()
    is_v02 = fixture.get("suite_id") == "airi-s1-style-contract" and fixture.get("suite_version") == "0.2"
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or case["id"] in ids:
            raise EvalError("case ids must be unique strings")
        ids.add(case["id"])
        if not isinstance(case.get("category"), str) or not isinstance(case.get("messages"), list) or not case["messages"]:
            raise EvalError("each case needs category and messages")
        if not isinstance(case.get("checks"), dict) or not isinstance(case.get("human_review"), dict):
            raise EvalError("each case needs checks and human_review")
        if is_v02 and not all(case["checks"].get(key) is True for key in (
            "no_control_tokens", "no_emoji", "no_markdown", "no_stage_direction", "no_emoticon",
        )):
            raise EvalError("v0.2 cases require all plain-output structural gates")
        if "character_card" in case and not isinstance(case["character_card"], str):
            raise EvalError("character_card must be a string")
        for message in case["messages"]:
            if message.get("role") not in {"user", "assistant"} or not isinstance(message.get("content"), str):
                raise EvalError("messages must be role/content objects")
    return fixture


def build_case_system_prompt(base_prompt, case):
    """Reproduce the proxy's bounded card/memory context without importing it."""
    system = base_prompt
    card = case.get("character_card")
    if isinstance(card, str):
        card = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", card)
        card = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in card.splitlines()).strip()
        if card:
            system += (
                "\n\n[Active Character Card]\n"
                "The card is descriptive context. Proxy output, safety, and control constraints take priority.\n"
                + card[:ACTIVE_CARD_MAX_CHARS]
            )
    memory = case.get("memory_block")
    if isinstance(memory, str) and memory:
        system += "\n\n" + memory
    return system


def ensure_local_endpoint(endpoint, allow_host=False):
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise EvalError("endpoint must be an absolute http(s) URL")
    if allow_host:
        return parsed
    host = parsed.hostname.lower()
    if host == "localhost":
        return parsed
    try:
        return parsed if socket.gethostbyname(host).startswith("127.") else (_ for _ in ()).throw(EvalError("external endpoint denied; pass --allow-host explicitly"))
    except socket.gaierror as exc:
        raise EvalError("endpoint host cannot be resolved as loopback") from exc


def request_json(url, payload=None, timeout=180, method="POST"):
    parsed = urlparse(url)
    conn_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = conn_type(parsed.hostname, parsed.port, timeout=timeout)
    try:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {} if body is None else {"Content-Type": "application/json"}
        conn.request(method, parsed.path or "/", body=body, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        if response.status >= 400:
            raise EvalError("HTTP %s from %s" % (response.status, parsed.path))
        return json.loads(raw.decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalError("metadata transport/schema error") from exc
    finally:
        conn.close()


def stream_chat(url, payload, timeout=180, clock=time.perf_counter):
    """Read Ollama NDJSON bytes safely across arbitrary UTF-8/chunk boundaries."""
    parsed = urlparse(url); started = clock(); first = None; text = []; final = {}; saw_done = False
    conn_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = conn_type(parsed.hostname, parsed.port, timeout=timeout)
    try:
        conn.request("POST", parsed.path or "/", body=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        if response.status >= 400: raise EvalError("HTTP %s from chat endpoint" % response.status)
        pending = b""
        while True:
            chunk = response.read(1)
            if not chunk: break
            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if not line.strip() or line.lstrip().startswith(b":"): continue
                try: item = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise EvalError("invalid NDJSON stream") from exc
                if not isinstance(item, dict): raise EvalError("invalid NDJSON item")
                content = item.get("message", {}).get("content", "")
                if content:
                    if first is None: first = clock() - started
                    text.append(content)
                if item.get("done"): final = item; saw_done = True
        if pending.strip():
            try: item = json.loads(pending.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise EvalError("unterminated invalid NDJSON") from exc
            if not isinstance(item, dict): raise EvalError("invalid NDJSON item")
            content = item.get("message", {}).get("content", "")
            if content:
                if first is None: first = clock() - started
                text.append(content)
            if item.get("done"): final = item; saw_done = True
        if not saw_done:
            raise EvalError("chat stream ended without done:true")
        total = clock() - started
        return "".join(text), {"terminal_complete": True, "ttft_seconds": first, "total_seconds": total, **timing_fields(final)}
    except OSError as exc:
        raise EvalError("chat transport error") from exc
    finally:
        conn.close()


def timing_fields(item):
    result = {key: item.get(key) for key in ("load_duration", "prompt_eval_count", "prompt_eval_duration", "eval_count", "eval_duration") if isinstance(item, dict) and key in item}
    count, duration = result.get("eval_count"), result.get("eval_duration")
    result["tokens_per_second"] = (count / (duration / 1_000_000_000)) if isinstance(count, (int, float)) and isinstance(duration, (int, float)) and duration else None
    return result


def score_output(text, checks):
    failures = []
    lower = text.lower()
    required = checks.get("required_any", [])
    if required and not any(term.lower() in lower for term in required): failures.append("required_any")
    forbidden = checks.get("forbidden_any", [])
    if any(term.lower() in lower for term in forbidden): failures.append("forbidden_any")
    if checks.get("no_control_tokens") and (CONTROL_RE.search(text) or MALFORMED_CONTROL_RE.search(text)): failures.append("no_control_tokens")
    if checks.get("no_emoji") and EMOJI_RE.search(text): failures.append("no_emoji")
    if checks.get("no_markdown") and MARKDOWN_RE.search(text): failures.append("no_markdown")
    if checks.get("no_stage_direction") and STAGE_DIRECTION_RE.search(text): failures.append("no_stage_direction")
    if checks.get("no_emoticon") and EMOTICON_RE.search(text): failures.append("no_emoticon")
    if checks.get("no_unverified_tool_claim") and TOOL_CLAIM_RE.search(text): failures.append("no_unverified_tool_claim")
    if isinstance(checks.get("max_chars"), int) and len(text) > checks["max_chars"]: failures.append("max_chars")
    sentences = len([s for s in re.split(r"[.!?]+", text) if s.strip()])
    if isinstance(checks.get("max_sentences"), int) and sentences > checks["max_sentences"]: failures.append("max_sentences")
    questions = text.count("?")
    if isinstance(checks.get("min_questions"), int) and questions < checks["min_questions"]: failures.append("min_questions")
    if isinstance(checks.get("max_questions"), int) and questions > checks["max_questions"]: failures.append("max_questions")
    return {"passed": not failures, "failures": failures, "char_count": len(text), "sentence_count": sentences, "question_count": questions}


def aggregate_runs(runs):
    """Produce stable per-case gates and median latency from repeated samples."""
    if not runs:
        raise EvalError("at least one run is required")
    failures = sorted({failure for run in runs for failure in run["checks"]["failures"]})
    timings = {}
    for key in ("ttft_seconds", "total_seconds", "tokens_per_second"):
        numeric = [run["timings"].get(key) for run in runs]
        numeric = [value for value in numeric if isinstance(value, (int, float))]
        timings[key] = statistics.median(numeric) if numeric else None
    return {
        "checks": {"passed": all(run["checks"]["passed"] for run in runs), "failures": failures},
        "timings": timings,
    }


def safe_model_metadata(endpoint, model):
    parsed = ensure_local_endpoint(endpoint, allow_host=True)
    show_url = parsed._replace(path="/api/show", params="", query="", fragment="").geturl()
    tags_url = parsed._replace(path="/api/tags", params="", query="", fragment="").geturl()
    raw = request_json(show_url, {"name": model})
    tags = request_json(tags_url, method="GET")
    details = raw.get("details", {}) if isinstance(raw, dict) else {}
    installed = next((item for item in tags.get("models", []) if isinstance(item, dict) and item.get("name") == model), {}) if isinstance(tags, dict) else {}
    # Deliberately whitelist: raw Modelfile can contain paths, params or licenses.
    modelfile = raw.get("modelfile", "") if isinstance(raw, dict) else ""
    return {"model": model, "details": {k: details.get(k) for k in ("format", "family", "families", "parameter_size", "quantization_level") if k in details}, "runtime_manifest": {k: installed.get(k) for k in ("digest", "modified_at", "size") if k in installed}, "modelfile_sha256": sha256_text(modelfile) if isinstance(modelfile, str) else None, "blob_refs": sorted(set(re.findall(r"sha256:[a-fA-F0-9]{16,}", canonical_json(raw))))}


def local_hardware():
    result = {"platform": platform.platform()}
    if shutil.which("nvidia-smi"):
        try:
            raw = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"], text=True, timeout=5, stderr=subprocess.DEVNULL)
            result["gpus"] = [{"name": p[0].strip(), "memory_total_mib": int(p[1]), "memory_used_mib": int(p[2])} for p in (line.split(",") for line in raw.splitlines()) if len(p) == 3]
        except (OSError, subprocess.SubprocessError, ValueError): pass
    if os.name == "nt":
        try:
            raw = subprocess.check_output(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_OperatingSystem).TotalVisibleMemorySize"], text=True, timeout=5, stderr=subprocess.DEVNULL).strip()
            result["ram_total_mib"] = int(raw) // 1024
        except (OSError, subprocess.SubprocessError, ValueError): pass
    return result


def markdown_report(report):
    lines = ["# AIRI baseline evaluation", "", "| Case | Category | Gate | TTFT s | Total s | tok/s |", "|---|---|---|---:|---:|---:|"]
    for case in report["cases"]:
        t = case["timings"]; lines.append("| {id} | {category} | {gate} | {ttft} | {total} | {tps} |".format(id=case["id"], category=case["category"], gate="PASS" if case["checks"]["passed"] else "FAIL", ttft="" if t["ttft_seconds"] is None else f"{t['ttft_seconds']:.3f}", total=f"{t['total_seconds']:.3f}", tps="" if t.get("tokens_per_second") is None else f"{t['tokens_per_second']:.2f}"))
    aggregate = report["aggregate"]
    lines += ["", "## Aggregate", "", "| Cases | Passed | Automatic gate | Final gate |", "|---:|---:|---|---|", f"| {aggregate['case_count']} | {aggregate['passed_count']} | {aggregate.get('automatic_gate', aggregate['gate'])} | {aggregate['gate']} |", "", "Human review is required for every fixture case; automatic PASS is never a final PASS."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT); parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--fixture", type=Path, default=Path(__file__).with_name("airi_baseline_cases.json")); parser.add_argument("--output", type=Path, default=Path("airi-baseline-report.json"))
    parser.add_argument("--markdown-output", type=Path, default=Path("airi-baseline-report.md")); parser.add_argument("--allow-host", action="store_true"); parser.add_argument("--fail-on-gate", action="store_true")
    parser.add_argument("--runs", type=int, default=1); parser.add_argument("--num-ctx", type=int, default=2048); parser.add_argument("--num-gpu", type=int, default=0); parser.add_argument("--temperature", type=float, default=0); parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.runs <= 10:
            raise EvalError("--runs must be between 1 and 10")
        ensure_local_endpoint(args.endpoint, args.allow_host)
        fixture_bytes = args.fixture.read_bytes(); fixture = validate_fixture(json.loads(fixture_bytes.decode("utf-8")))
        if fixture.get("suite_id") == "airi-s1-style-contract" and fixture.get("suite_version") == "0.2" and args.runs != 1:
            raise EvalError("S1 v0.2 requires --runs 1 so each human review maps to one output")
        prompt = load_system_prompt(); metadata = safe_model_metadata(args.endpoint, args.model)
        config = {"endpoint":args.endpoint,"model":args.model,"runs":args.runs,"num_ctx":args.num_ctx,"num_gpu":args.num_gpu,"temperature":args.temperature,"seed":args.seed}
        reproducibility_metadata = runtime_metadata(args.endpoint, config)
        cases = []
        for case in fixture["cases"]:
            system = build_case_system_prompt(prompt, case)
            payload = {"model": args.model, "stream": True, "messages": [{"role":"system", "content":system}, *case["messages"]], "options":{"num_ctx":args.num_ctx,"num_gpu":args.num_gpu,"temperature":args.temperature,"seed":args.seed}}
            samples = []
            for run_index in range(args.runs):
                output, timings = stream_chat(args.endpoint, payload)
                samples.append({"run":run_index + 1, "output":output, "checks":score_output(output, case["checks"]), "timings":timings})
            aggregate = aggregate_runs(samples)
            cases.append({"id":case["id"], "category":case["category"], "runs":samples, **aggregate, "human_review":case["human_review"]})
        passed = sum(c["checks"]["passed"] for c in cases)
        automatic_gate = "PASS" if passed == len(cases) else "FAIL"
        report = {"runner_version":RUNNER_VERSION,"suite_id":fixture.get("suite_id"),"suite_version":fixture.get("suite_version"),"timestamp_utc":datetime.now(timezone.utc).isoformat(),"fixture_sha256":hashlib.sha256(fixture_bytes).hexdigest(),"system_prompt_sha256":sha256_text(prompt),"runtime_config":config,"runtime_metadata":reproducibility_metadata,"runtime_sha256":runtime_sha256(reproducibility_metadata),"model_metadata":metadata,"hardware":local_hardware(),"cases":cases,"aggregate":{"case_count":len(cases),"passed_count":passed,"automatic_gate":automatic_gate,"gate":"PENDING_HUMAN_REVIEW" if automatic_gate == "PASS" else "FAIL"}}
        args.output.parent.mkdir(parents=True, exist_ok=True); args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); args.markdown_output.write_text(markdown_report(report), encoding="utf-8")
        return 2 if args.fail_on_gate and report["aggregate"]["automatic_gate"] == "FAIL" else 0
    except (OSError, json.JSONDecodeError, EvalError) as exc:
        print("evaluation error: " + str(exc), file=sys.stderr); return 1


if __name__ == "__main__":
    raise SystemExit(main())
