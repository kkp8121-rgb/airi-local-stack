"""Deterministic, synthetic production-context projection gate for Ollama."""
from __future__ import annotations

import argparse, copy, hashlib, http.client, ipaddress, json, math, os, re, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

EVAL_DIR = Path(__file__).resolve().parent
PROXY_DIR = EVAL_DIR.parent
PROJECT_ROOT = PROXY_DIR.parent
if str(PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(PROXY_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from continuity_ledger import CONTINUITY_LEDGER_MESSAGE_NAME, ContinuityLedgerRuntime
from memory_runtime import assemble_payload_context_from_snapshot
from ollama_proxy import ACTIVE_CARD_MESSAGE_NAME, inject_response_language, inject_response_mode, native_chat_stream_body, transform_body

RUNNER_VERSION = "2.0"
DEFAULT_ENDPOINT = "http://127.0.0.1:11434/api/chat"
FIELDS = ("card_marker", "ledger_active_color", "ledger_pet_negated", "ledger_corrected_color", "memory_marker", "dialogue_marker", "dropped_holdout_seen")
FIELD_SCHEMAS = {
    "card_marker": {"type": "string", "description": "보이는 Active Character Card의 표식 값"},
    "ledger_active_color": {"type": "string", "description": "보이는 AIRI Continuity Data의 현재 favorite.color 값"},
    "ledger_pet_negated": {"type": "boolean", "description": "보이는 AIRI Continuity Data의 반려동물 negated polarity"},
    "ledger_corrected_color": {"type": "string", "description": "보이는 AIRI Continuity Data의 수정된 favorite.color 값"},
    "memory_marker": {"type": "string", "description": "보이는 Character Memory 시스템 블록의 표식 값(user/assistant 제외)"},
    "dialogue_marker": {"type": "string", "description": "보존된 user/assistant 대화의 반복 표식 값(시스템 블록 제외)"},
    "dropped_holdout_seen": {"type": "boolean", "description": "보이는 현재 입력의 오래된 holdout 표식 여부"},
}
def ordered_schema(field_order=FIELDS):
    return {"type": "object", "additionalProperties": False, "required": list(field_order), "properties": {field: FIELD_SCHEMAS[field] for field in field_order}}
SCHEMA = ordered_schema()

class EvalError(RuntimeError): pass
class TransportError(EvalError): pass
class SchemaError(EvalError): pass

def canonical(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
def sha(value): return hashlib.sha256(value.encode("utf-8")).hexdigest()
def load_fixture(path=None):
    try: value = json.loads(Path(path or EVAL_DIR / "airi_production_context_cases.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise EvalError("invalid fixture") from exc
    return validate_fixture(value)
def validate_fixture(value):
    if not isinstance(value, dict) or value.get("suite_version") != RUNNER_VERSION or value.get("synthetic_only") is not True or value.get("pressure_levels") != [0, 8, 20, 48] or value.get("runs") != 3:
        raise EvalError("fixture requires exactly pressures 0,8,20,48 and three runs")
    if (not isinstance(value.get("canaries"), dict)
            or not isinstance(value.get("current_query"), str)
            or not value["current_query"].strip()
            or set(FIELDS) != set(value.get("expected", {}))):
        raise EvalError("fixture canaries/expected schema invalid")
    return value
def ensure_local_endpoint(endpoint, allow_host=False):
    parsed = urlparse(endpoint)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment
            or parsed.path.rstrip("/") != "/api/chat"):
        raise EvalError("endpoint must be an absolute /api/chat URL without credentials, query, or fragment")
    try: parsed.port
    except ValueError as exc: raise EvalError("endpoint port is invalid") from exc
    if allow_host: return parsed
    try: address = ipaddress.ip_address(parsed.hostname)
    except ValueError as exc: raise EvalError("loopback endpoint must use literal IP; use --allow-host") from exc
    if not address.is_loopback: raise EvalError("endpoint must be loopback; use --allow-host")
    return parsed
def validate_args(args):
    ensure_local_endpoint(args.endpoint, args.allow_host)
    if (not isinstance(args.model, str) or not args.model.strip()
            or not re.fullmatch(r"[1-9][0-9]*[smh]", args.keep_alive)
            or not math.isfinite(args.timeout) or not 0 < args.timeout <= 3600
            or not math.isfinite(args.temperature) or not 0 <= args.temperature <= 2
            or not 512 <= args.num_ctx <= 32768 or not 1 <= args.num_predict <= 512
            or not 0 <= args.num_gpu <= 999 or not 0 <= args.seed <= 2_147_483_647
            or args.runs < 1):
        raise EvalError("invalid runtime range")
def build_original(fixture, pressure):
    c = fixture["canaries"]
    messages = [
        {"role":"system", "content":c["active_card"]},
        {"role":"user", "content":c["continuity_fact"]},
        {"role":"assistant", "content":"ACK_EARLY_FACT"},
        {"role":"user", "content":c["korean_pet_negation"]},
        {"role":"assistant", "content":"ACK_EARLY_PET"},
        {"role":"user", "content":c["correction"]},
        {"role":"assistant", "content":"ACK_CORRECTION"},
        {"role":"user", "content":c["dropped_holdout"]},
        {"role":"assistant", "content":"ACK_DROPPED_HOLDOUT"},
    ]
    for index in range(pressure):
        filler = fixture["filler_template"].format(index=index)
        messages.extend(({"role":"user", "content":"U " + filler}, {"role":"assistant", "content":"A " + filler}))
    messages.extend((
        {"role":"user", "content":c["bridge"] + " 계획의 첫 연결을 기억해."},
        {"role":"assistant", "content":c["bridge"] + " 계획의 첫 연결을 확인했어."},
        {"role":"user", "content":c["bridge"] + " 계획의 두 번째 연결도 이어가자."},
        {"role":"assistant", "content":c["bridge"] + " 계획의 두 번째 연결까지 이어졌어."},
        {"role":"user", "content":fixture["current_query"]},
    ))
    return messages
def base_payload(messages, args, schema=SCHEMA):
    return {"model":args.model, "messages":messages, "stream":False, "format":schema, "think":False, "keep_alive":args.keep_alive, "options":{"num_ctx":args.num_ctx, "temperature":args.temperature, "seed":args.seed, "num_predict":args.num_predict}}
def pipeline(fixture, pressure, args, *, field_order=FIELDS, schema=None):
    original = build_original(fixture, pressure); before = copy.deepcopy(original)
    # Use the same stateful runtime as an explicit production session, but a
    # fresh bounded instance per synthetic case so the gate has no cross-run
    # state and never touches the memory runtime, store, DB, or user data.
    ledger = ContinuityLedgerRuntime(max_sessions=1).observe("synthetic-production-gate", original)
    body = json.dumps(base_payload(original, args, schema or ordered_schema(field_order)), ensure_ascii=False, separators=(",", ":")).encode()
    transformed, *_ = transform_body(
        "/api/chat", body, continuity_block=ledger,
        num_ctx=args.num_ctx, num_gpu=args.num_gpu,
    )
    prepared = json.loads(transformed)
    projected_message_count = sum(
        isinstance(message, dict) and message.get("role") != "system"
        for message in prepared.get("messages", [])
    )
    if projected_message_count != 5:
        raise EvalError("production foreground projection no longer retains the expected two pairs and current user")
    assembled = assemble_payload_context_from_snapshot(
        prepared, original, latest_turn=99, extraction_watermark=0,
        projected_message_count=projected_message_count,
        memory_block=fixture["canaries"]["tail_memory"],
    )
    localized = inject_response_language(json.dumps(assembled, ensure_ascii=False, separators=(",", ":")).encode(), "한국어")
    localized = inject_response_mode(localized, fixture["current_query"])
    native = json.loads(native_chat_stream_body(
        localized, apply_sampling_defaults=False,
        num_ctx=args.num_ctx, num_gpu=args.num_gpu,
    ))
    # The converter is shared with the streaming proxy path. The gate itself
    # needs one complete JSON object for strict scoring, so its direct CLI hop
    # requests the equivalent non-streaming Ollama response.
    native["stream"] = False
    if original != before: raise EvalError("original input mutated")
    messages = assembled["messages"]; native_messages = native["messages"]
    named = [m.get("name") for m in messages if isinstance(m, dict) and m.get("name")]
    native_text = "\n".join(str(m.get("content", "")) for m in native_messages if isinstance(m, dict))
    occurrence_counts = {
        "card_marker": native_text.count(fixture["canaries"]["active_card"]),
        "memory_marker": native_text.count(fixture["canaries"]["tail_memory"]),
        "continuity_ledger": native_text.count("[AIRI Continuity Data v1"),
        "ledger_corrected_color": native_text.count(fixture["expected"]["ledger_corrected_color"]),
        "dialogue_marker": native_text.count(fixture["expected"]["dialogue_marker"]),
        "holdout": native_text.count(fixture["canaries"]["dropped_holdout"]),
    }
    structural = {
        "original_unchanged": True,
        "named_once": named.count(ACTIVE_CARD_MESSAGE_NAME) == 1 and named.count(CONTINUITY_LEDGER_MESSAGE_NAME) == 1,
        "private_names_stripped": all("name" not in m for m in native_messages if isinstance(m, dict)),
        "static_first": bool(native_messages) and native_messages[0].get("role") == "system",
        "order": _ordered(native_messages),
        "latest_user_last": native_messages[-1].get("role") == "user",
        "projected_two_pairs": [m.get("role") for m in messages[1:6]] == ["user", "assistant", "user", "assistant", "system"],
        "filler_absent": "SYNTHETIC_PRESSURE_" not in native_text,
        "holdout_absent": occurrence_counts["holdout"] == 0,
        "required_once": all(occurrence_counts[key] == 1 for key in ("card_marker", "memory_marker", "continuity_ledger", "ledger_corrected_color")),
        "dialogue_retained": occurrence_counts["dialogue_marker"] == 4,
    }
    return {
        "original": original,
        "ledger": ledger,
        "prepared": messages,
        "native": native,
        "prepared_hash": sha(canonical(messages)),
        "native_messages_hash": sha(canonical(native_messages)),
        "native_hash": sha(canonical(native)),
        "occurrence_counts": occurrence_counts,
        "structural": structural,
    }
def _ordered(messages):
    text = [str(m.get("content", "")) for m in messages if isinstance(m, dict)]
    memory = next((i for i,x in enumerate(text) if "[Character Memory]" in x), -1); card = next((i for i,x in enumerate(text) if "Active Character Card" in x), -1); ledger = next((i for i,x in enumerate(text) if "AIRI Continuity Data v1" in x), -1)
    return 0 <= memory < card < ledger
def valid_response(response):
    try: data = json.loads(response["message"]["content"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc: raise SchemaError("malformed schema response") from exc
    if not isinstance(data, dict) or response.get("done") is not True or set(data) != set(FIELDS) or not isinstance(data.get("ledger_pet_negated"), bool) or not isinstance(data.get("dropped_holdout_seen"), bool) or any(not isinstance(data.get(k), str) for k in FIELDS if k not in {"ledger_pet_negated", "dropped_holdout_seen"}): raise SchemaError("response schema mismatch")
    return data
def score(data, expected):
    failures = [field for field in FIELDS if data.get(field) != expected[field]]
    return {"passed": not failures, "field_score": {field: field not in failures for field in FIELDS}, "failures": failures}
def percentile(values, fraction):
    values=sorted(float(value) for value in values if isinstance(value, (int, float)) and math.isfinite(value))
    if not values: return None
    rank=max(0, math.ceil(fraction * len(values)) - 1)
    return round(values[rank], 3)
def chat_once(endpoint, body, timeout):
    p = urlparse(endpoint); conn = (http.client.HTTPSConnection if p.scheme == "https" else http.client.HTTPConnection)(p.hostname, p.port, timeout=timeout)
    try:
        wire_body = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        conn.request("POST", p.path or "/api/chat", body=wire_body, headers={"Content-Type":"application/json"}); response = conn.getresponse(); raw = response.read()
        if response.status >= 400: raise TransportError("HTTP %s" % response.status)
        return json.loads(raw.decode())
    except OSError as exc: raise TransportError("transport failure") from exc
    except json.JSONDecodeError as exc: raise SchemaError("malformed transport JSON") from exc
    finally: conn.close()
def metadata(endpoint, model, timeout):
    """Small read-only live metadata record; never used by offline tests."""
    p=urlparse(endpoint); base=f"{p.scheme}://{p.netloc}"
    def request_json(method, path, body=None):
        q=urlparse(base + path); conn=(http.client.HTTPSConnection if q.scheme == "https" else http.client.HTTPConnection)(q.hostname,q.port,timeout=timeout)
        try:
            encoded = canonical(body).encode() if body is not None else None
            headers = {"Content-Type": "application/json"} if encoded is not None else {}
            conn.request(method, q.path, body=encoded, headers=headers); response=conn.getresponse(); raw=response.read()
            if response.status >= 400: raise EvalError("metadata HTTP %s" % response.status)
            return json.loads(raw.decode())
        except (OSError, json.JSONDecodeError) as exc: raise EvalError("metadata unavailable") from exc
        finally: conn.close()
    version=request_json("GET", "/api/version")
    tags=request_json("GET", "/api/tags")
    tagged=next((item for item in tags.get("models", []) if isinstance(item,dict) and item.get("name") == model), {})
    digest=tagged.get("digest")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise EvalError("exact model tag/digest is unavailable")
    shown=request_json("POST", "/api/show", {"model": model, "verbose": False})
    details=shown.get("details") if isinstance(shown.get("details"), dict) else {}
    return {
        "ollama_version":version.get("version"),
        "model_digest":digest,
        "model_size_bytes":tagged.get("size"),
        "family":details.get("family"),
        "parameter_size":details.get("parameter_size"),
        "quantization_level":details.get("quantization_level"),
        "template_sha256":sha(str(shown.get("template", ""))),
    }
def run_one(endpoint, native, args, expected, transport=chat_once):
    attempts=[]
    for number in range(2):
        try:
            response=transport(endpoint, native, args.timeout); data=valid_response(response)
            metrics={"prompt_eval_count":response.get("prompt_eval_count"),"eval_count":response.get("eval_count")}
            for key in ("prompt_eval_duration", "eval_duration", "total_duration"):
                value = response.get(key)
                metrics[key.removesuffix("_duration") + "_duration_ms"] = round(value / 1_000_000, 3) if isinstance(value, int) and value >= 0 else None
            content=response["message"]["content"]
            return {"complete":True,"retry_used":number > 0,"attempts":attempts + [{"attempt":number+1,"valid":True}],"raw_response_content":content,"raw_response_sha256":sha(content),"parsed_result":data,"parsed_result_sha256":sha(canonical(data)),"score":score(data, expected),"metrics":metrics}
        except (TransportError, SchemaError) as exc: attempts.append({"attempt":number+1,"valid":False,"error":str(exc)})
    return {"complete":False,"retry_used":True,"attempts":attempts}
def aggregate(runs):
    completed=[r for r in runs if r["complete"]]; structural=all(r.get("structural_pass", False) for r in runs); semantic=bool(completed) and len(completed)==len(runs) and all(r["score"]["passed"] for r in completed)
    output_hashes=[r.get("raw_response_sha256") for r in completed]
    parsed_hashes=[r.get("parsed_result_sha256") for r in completed]
    total_ms=[r.get("metrics", {}).get("total_duration_ms") for r in completed]
    prompt_counts=[r.get("metrics", {}).get("prompt_eval_count") for r in completed]
    return {"structural_pass":structural,"semantic_pass":semantic,"gate_pass":structural and semantic,"complete":len(completed)==len(runs),"runs":len(runs),"completed_runs":len(completed),"retry_runs":sum(bool(r.get("retry_used")) for r in runs),"deterministic_raw_output":bool(output_hashes) and len(set(output_hashes)) == 1,"deterministic_parsed_output":bool(parsed_hashes) and len(set(parsed_hashes)) == 1,"prompt_eval_count_min":min(prompt_counts) if prompt_counts and all(isinstance(value,int) for value in prompt_counts) else None,"prompt_eval_count_max":max(prompt_counts) if prompt_counts and all(isinstance(value,int) for value in prompt_counts) else None,"total_duration_ms_p50":percentile(total_ms, .5),"total_duration_ms_p95":percentile(total_ms, .95),"field_pass_rates":{f:sum(r["score"]["field_score"][f] for r in completed)/len(completed) if completed else 0 for f in FIELDS}}
def atomic_write(path, value):
    path=Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, dir=path.parent, suffix=".tmp") as handle: json.dump(value, handle, ensure_ascii=False, indent=2); temporary=Path(handle.name)
    os.replace(temporary, path)
def source_hashes():
    return {name: hashlib.sha256((PROXY_DIR / name).read_bytes()).hexdigest() for name in ("ollama_proxy.py", "memory_runtime.py", "airi_memory.py", "foreground_context.py", "continuity_ledger.py", "character_state.py")}
def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument("--endpoint",default=DEFAULT_ENDPOINT); ap.add_argument("--allow-host",action="store_true"); ap.add_argument("--model",default="midm-airi:2.0-mini"); ap.add_argument("--runs",type=int,default=3); ap.add_argument("--num-ctx",type=int,default=2048); ap.add_argument("--num-gpu",type=int,default=999); ap.add_argument("--temperature",type=float,default=0); ap.add_argument("--seed",type=int,default=42); ap.add_argument("--num-predict",type=int,default=128); ap.add_argument("--keep-alive",default="5m"); ap.add_argument("--timeout",type=float,default=180); ap.add_argument("--output",default="airi-production-context-report.json"); ap.add_argument("--fail-on-gate",action="store_true"); args=ap.parse_args(argv)
    try:
        validate_args(args); fixture_path=EVAL_DIR / "airi_production_context_cases.json"; fixture=load_fixture(fixture_path); report={"version":RUNNER_VERSION,"timestamp_utc":datetime.now(timezone.utc).isoformat(),"endpoint":args.endpoint,"model":args.model,"metadata":metadata(args.endpoint,args.model,args.timeout),"fixture_sha256":sha(canonical(fixture)),"fixture_file_sha256":hashlib.sha256(fixture_path.read_bytes()).hexdigest(),"runner_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"production_source_sha256":source_hashes(),"configuration":vars(args),"authoritative":args.runs == 3,"pressures":[]}; all_runs=[]
        for pressure in fixture["pressure_levels"]:
            item={"pressure":pressure,"runs":[]}; baseline=None
            for _ in range(args.runs):
                state=pipeline(fixture, pressure, args); result=run_one(args.endpoint, state["native"], args, fixture["expected"]); result["structural_pass"]=all(state["structural"].values()) and (baseline is None or state["native_hash"] == baseline); baseline=state["native_hash"] if baseline is None else baseline; result["transformation_ledger"]={"original_messages":len(state["original"]),"prepared_messages":len(state["prepared"]),"native_messages":len(state["native"]["messages"]),"prepared_hash":state["prepared_hash"],"native_messages_hash":state["native_messages_hash"],"native_hash":state["native_hash"],"roles":[m.get("role") for m in state["native"]["messages"]],"input_chars":sum(len(str(m.get("content", ""))) for m in state["original"]),"prepared_chars":sum(len(str(m.get("content", ""))) for m in state["prepared"]),"native_chars":sum(len(str(m.get("content", ""))) for m in state["native"]["messages"]),"occurrence_counts":state["occurrence_counts"],"canary_booleans":state["structural"],"native_contract":{"model":state["native"].get("model"),"options":state["native"].get("options"),"format":state["native"].get("format"),"think":state["native"].get("think"),"stream":state["native"].get("stream"),"keep_alive":state["native"].get("keep_alive")}}; item["runs"].append(result); all_runs.append(result)
            item["aggregate"]=aggregate(item["runs"]); report["pressures"].append(item)
        hashes=[r["transformation_ledger"]["native_hash"] for r in all_runs]; report["cross_pressure_native_hash_equal"]=len(set(hashes)) == 1
        for r in all_runs: r["structural_pass"] = r["structural_pass"] and report["cross_pressure_native_hash_equal"]
        for item in report["pressures"]: item["aggregate"] = aggregate(item["runs"])
        report["aggregate"]=aggregate(all_runs)
        report["aggregate"]["authoritative_gate_pass"] = bool(
            report["authoritative"] and report["aggregate"]["gate_pass"]
        )
        atomic_write(args.output, report)
        return 1 if args.fail_on_gate and not report["aggregate"]["authoritative_gate_pass"] else 0
    except EvalError as exc: print("production context gate error:", exc, file=sys.stderr); return 2
if __name__ == "__main__": raise SystemExit(main())
