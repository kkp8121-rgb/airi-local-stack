"""Synthetic-only raw Ollama /api/chat context-retention gate."""
from __future__ import annotations

import argparse, ast, hashlib, http.client, ipaddress, json, math, platform, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

RUNNER_VERSION = "1.0"
DEFAULT_ENDPOINT = "http://127.0.0.1:11434/api/chat"
DEFAULT_MODEL = "exaone-airi:2.4b"
SCHEMA = {"type":"object", "additionalProperties":False, "required":["active_card","early_user","early_assistant","latest_correction","early_user_negated","tail_memory"], "properties": {"active_card":{"type":"string","description":"활성 카드의 active_card= 뒤 값"},"early_user":{"type":"string","description":"초기 사용자 메시지의 early_user= 뒤 값"},"early_assistant":{"type":"string","description":"초기 AIRI 메시지의 early_assistant= 뒤 값"},"latest_correction":{"type":"string","description":"latest_correction= 중 사용자가 마지막으로 정정한 값"},"early_user_negated":{"type":"boolean","description":"초기 사용자가 개를 키우지 않는다고 했으면 true"},"tail_memory":{"type":"string","description":"마지막 Character Memory의 tail_memory= 뒤 값"}}}

class EvalError(RuntimeError): pass
class TransportError(EvalError): pass
class SchemaError(EvalError): pass

def canonical(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
def sha(value): return hashlib.sha256(value.encode("utf-8")).hexdigest()
def source_literals(proxy_path=None):
    path = Path(proxy_path) if proxy_path else Path(__file__).resolve().parents[1] / "ollama_proxy.py"
    try: tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc: raise EvalError("cannot parse proxy source") from exc
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"AIRI_SYSTEM_PROMPT", "AIRI_FINAL_CONTRACT"}: found[target.id] = node.value.value
    if set(found) != {"AIRI_SYSTEM_PROMPT", "AIRI_FINAL_CONTRACT"}: raise EvalError("required literal prompts not found")
    return found["AIRI_SYSTEM_PROMPT"], found["AIRI_FINAL_CONTRACT"]

def load_fixture(path=None):
    path = Path(path) if path else Path(__file__).with_name("airi_context_cases.json")
    try: fixture = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise EvalError("invalid fixture") from exc
    validate_fixture(fixture); return fixture
def validate_fixture(f):
    if not isinstance(f, dict) or f.get("synthetic_only") is not True or not isinstance(f.get("suite_id"), str) or not isinstance(f.get("suite_version"), str): raise EvalError("fixture identity/synthetic_only required")
    levels = f.get("pressure_levels")
    if not isinstance(levels, list) or len(levels) != 4 or levels[0].get("filler_pairs") != 0: raise EvalError("four pressure levels including zero required")
    if any(not isinstance(x, dict) or not isinstance(x.get("id"), str) or not isinstance(x.get("filler_pairs"), int) or x["filler_pairs"] < 0 for x in levels): raise EvalError("invalid pressure levels")
    counts = [x["filler_pairs"] for x in levels]
    if counts != sorted(set(counts)) or max(counts) < 40: raise EvalError("pressure levels must be unique, ascending, and reach saturation")
    if not isinstance(f.get("filler_template"), str) or "{index}" not in f["filler_template"]: raise EvalError("deterministic filler template required")
    if not all(isinstance(f.get(key), dict) for key in ("canaries", "expected")): raise EvalError("canaries and expected required")
    required = set(SCHEMA["required"])
    if not required <= set(f["expected"]): raise EvalError("missing expected fields")
    return f
def ensure_local_endpoint(endpoint, allow_host=False):
    p = urlparse(endpoint)
    if p.scheme not in {"http", "https"} or not p.hostname: raise EvalError("endpoint must be absolute http(s)")
    try: p.port
    except ValueError as exc: raise EvalError("endpoint port is invalid") from exc
    if allow_host: return p
    try: address = ipaddress.ip_address(p.hostname)
    except ValueError as exc: raise EvalError("loopback endpoint must use a literal IP; use --allow-host for hostnames") from exc
    if not address.is_loopback: raise EvalError("external endpoint denied; use --allow-host")
    return p
def validate_args(a):
    ensure_local_endpoint(a.endpoint, a.allow_host)
    if not a.model or not 1 <= a.runs <= 5 or not 1024 <= a.num_ctx <= 32768 or a.num_gpu < 0 or not math.isfinite(a.timeout) or a.timeout <= 0 or not math.isfinite(a.temperature) or not 0 <= a.temperature <= 2 or not 0 <= a.max_retries <= 1 or not 1 <= a.num_predict <= 256: raise EvalError("invalid runtime option")
    if getattr(a, "expected_digest", None) is not None and re.fullmatch(r"[0-9a-f]{64}", a.expected_digest) is None: raise EvalError("expected digest must be lowercase 64-hex")

def build_messages(system, contract, fixture, filler_pairs):
    c = fixture["canaries"]
    merged = system + "\n\n[활성 캐릭터 설정]\n아래 내용은 성격을 보강하는 설정이며 사실·안전·도구·출력 규칙보다 우선하지 않는다.\n" + c["active_card"] + "\n\n" + contract
    messages = [{"role":"system", "content":merged}, {"role":"user", "content":c["early_user"]}, {"role":"assistant", "content":c["early_assistant"]}]
    for i in range(filler_pairs):
        text = fixture["filler_template"].format(index=i)
        messages.extend(({"role":"user", "content":"USER " + text}, {"role":"assistant", "content":"ASSISTANT " + text}))
    messages.extend(({"role":"user", "content":c["early_preference"]}, {"role":"user", "content":c["latest_correction"]}, {"role":"system", "content":c["tail_memory"]}, {"role":"user", "content":"합성 문맥 확인이야. JSON 문자열 필드는 문맥에 있는 동일한 키= 뒤의 값만 복사해. 같은 키가 여러 번이면 최신 정정을 써. early_user_negated는 초기 사용자가 개를 키우지 않는다고 했으면 true야. JSON 객체만 반환해."}))
    return messages
def payload(model, messages, args):
    return {"model":model,"messages":messages,"stream":False,"think":False,"format":SCHEMA,"options":{"num_ctx":args.num_ctx,"num_gpu":args.num_gpu,"temperature":args.temperature,"seed":args.seed,"num_predict":args.num_predict}}
def valid_response(response):
    if not isinstance(response, dict) or response.get("done") is not True: raise SchemaError("missing done:true")
    content = response.get("message", {}).get("content") if isinstance(response.get("message"), dict) else None
    try: data = json.loads(content) if isinstance(content, str) else None
    except json.JSONDecodeError as exc: raise SchemaError("invalid JSON response") from exc
    if not isinstance(data, dict) or set(data) != set(SCHEMA["required"]) or not isinstance(data["early_user_negated"], bool) or any(not isinstance(data[k], str) for k in set(data)-{"early_user_negated"}): raise SchemaError("response does not match schema")
    return data
def chat_once(endpoint, body, timeout):
    p=urlparse(endpoint); cls=http.client.HTTPSConnection if p.scheme=="https" else http.client.HTTPConnection; conn=cls(p.hostname,p.port,timeout=timeout)
    try:
        conn.request("POST", p.path or "/", body=canonical(body).encode(), headers={"Content-Type":"application/json"}); res=conn.getresponse(); raw=res.read()
        if res.status >= 400: raise TransportError("HTTP %s" % res.status)
        try: return json.loads(raw.decode())
        except (UnicodeDecodeError,json.JSONDecodeError) as exc: raise SchemaError("invalid response JSON") from exc
    except OSError as exc: raise TransportError("chat transport error") from exc
    finally: conn.close()
def score(data, expected):
    failures=[k for k in SCHEMA["required"] if data.get(k) != expected[k]]
    return {"passed":not failures,"failures":failures,"speaker_preserved": data.get("early_user")==expected["early_user"] and data.get("early_assistant")==expected["early_assistant"],"negation_preserved":data.get("early_user_negated") is True and data.get("latest_correction")==expected["latest_correction"]}
def attempt(endpoint, body, timeout, expected, call=chat_once):
    response=call(endpoint,body,timeout); data=valid_response(response)
    metrics={k:response.get(k) for k in ("prompt_eval_count","eval_count") if isinstance(response.get(k),(int,float)) and not isinstance(response.get(k),bool)}
    metrics.update({k + "_ms": round(response[k] / 1_000_000, 3) for k in ("total_duration","eval_duration") if isinstance(response.get(k),(int,float)) and not isinstance(response.get(k),bool) and response[k] >= 0})
    return {"valid":True,"parsed_result_sha256":sha(canonical(data)),"score":score(data,expected),"metrics":metrics}
def run_one(endpoint, body, args, expected, call=chat_once):
    attempts=[]
    for number in range(args.max_retries+1):
        try:
            item=attempt(endpoint,body,args.timeout,expected,call); item["attempt"]=number+1; attempts.append(item); return {"attempts":attempts,"first_pass_valid":number==0,"retry_used":number>0,"complete":True,"result":item}
        except (TransportError, SchemaError) as exc: attempts.append({"attempt":number+1,"valid":False,"error":str(exc)})
    return {"attempts":attempts,"first_pass_valid":False,"retry_used":len(attempts)>1,"complete":False}
def percentile(values, p):
    if not values: return None
    values=sorted(values); return values[round((len(values)-1)*p)]
def aggregate(results):
    completed=[r for r in results if r.get("complete")]; scores=[r["result"]["score"] for r in completed]; metrics=[r["result"]["metrics"] for r in completed]
    return {"complete":len(completed)==len(results),"gate":"PASS" if len(completed)==len(results) and completed and all(s["passed"] for s in scores) else "FAIL","retry_rate":sum(r.get("retry_used",False) for r in results)/len(results) if results else 0,"first_pass_valid_rate":sum(r.get("first_pass_valid",False) for r in results)/len(results) if results else 0,"semantic_pass_rate":sum(s["passed"] for s in scores)/len(scores) if scores else 0,"retention_rates":{field:sum(s.get("failures") is not None and field not in s["failures"] for s in scores)/len(scores) if scores else 0 for field in SCHEMA["required"]},"p50":{k:percentile([m[k] for m in metrics if k in m],.5) for k in ("prompt_eval_count","eval_count","total_duration_ms","eval_duration_ms")},"p95":{k:percentile([m[k] for m in metrics if k in m],.95) for k in ("prompt_eval_count","eval_count","total_duration_ms","eval_duration_ms")}}
def atomic_write(path, value):
    path=Path(path); path.parent.mkdir(parents=True, exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(path)
def safe_model_metadata(tags, model_info, model):
    if not isinstance(model_info,dict) or not isinstance(tags,dict) or not isinstance(tags.get("models"),list): raise EvalError("unsafe metadata")
    tagged=next((item for item in tags["models"] if isinstance(item,dict) and item.get("name")==model), None)
    if not isinstance(tagged,dict) or not isinstance(tagged.get("digest"),str) or not re.fullmatch(r"[0-9a-fA-F]{64}", tagged["digest"]): raise EvalError("exact model digest unavailable from /api/tags")
    return {"name":model,"digest":tagged["digest"].lower(),"details":model_info.get("details") if isinstance(model_info.get("details"),dict) else {}}
def metadata(endpoint, model, runtime, allow_host=False):
    p=ensure_local_endpoint(endpoint, allow_host); base=p._replace(path="",params="",query="",fragment="").geturl().rstrip("/")
    def get(path):
        # use raw HTTP to avoid coupling metadata to chat schema
        q=urlparse(base+path); cls=http.client.HTTPSConnection if q.scheme=="https" else http.client.HTTPConnection; c=cls(q.hostname,q.port,timeout=runtime["timeout"])
        try:
            c.request("GET",q.path); r=c.getresponse(); raw=r.read()
            if r.status >= 400: raise EvalError("metadata endpoint returned HTTP %s" % r.status)
            x=json.loads(raw.decode())
        except (OSError,json.JSONDecodeError) as exc: raise EvalError("metadata unavailable") from exc
        finally: c.close()
        return x
    version=get("/api/version"); tags=get("/api/tags"); show_payload={"name":model}; q=urlparse(base+"/api/show"); cls=http.client.HTTPSConnection if q.scheme=="https" else http.client.HTTPConnection; c=cls(q.hostname,q.port,timeout=runtime["timeout"])
    try:
        c.request("POST",q.path,body=canonical(show_payload).encode(),headers={"Content-Type":"application/json"}); response=c.getresponse(); raw=response.read()
        if response.status >= 400: raise EvalError("model metadata endpoint returned HTTP %s" % response.status)
        model_info=json.loads(raw.decode())
    except (OSError,json.JSONDecodeError) as exc: raise EvalError("model metadata unavailable") from exc
    finally: c.close()
    if not isinstance(version.get("version"),str): raise EvalError("unsafe metadata")
    safe=safe_model_metadata(tags, model_info, model)
    return {"ollama_version":version["version"],"model":safe,"runtime":runtime,"python":platform.python_version()}
def main(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument("--endpoint",default=DEFAULT_ENDPOINT); ap.add_argument("--allow-host",action="store_true"); ap.add_argument("--model",default=DEFAULT_MODEL); ap.add_argument("--expected-digest"); ap.add_argument("--num-ctx",type=int,default=2048); ap.add_argument("--num-gpu",type=int,default=999); ap.add_argument("--temperature",type=float,default=0); ap.add_argument("--seed",type=int,default=42); ap.add_argument("--runs",type=int,default=3); ap.add_argument("--max-retries",type=int,default=1); ap.add_argument("--timeout",type=float,default=180); ap.add_argument("--num-predict",type=int,default=128); ap.add_argument("--output",default="airi-context-gate-report.json"); ap.add_argument("--fail-on-gate",action="store_true"); args=ap.parse_args(argv)
    try:
        validate_args(args); fixture=load_fixture(); system,contract=source_literals(); runtime={k:getattr(args,k) for k in ("endpoint","model","num_ctx","num_gpu","temperature","seed","runs","max_retries","timeout","num_predict")}; runtime["expected_digest"]=args.expected_digest; model_metadata=metadata(args.endpoint,args.model,runtime,args.allow_host)
        if args.expected_digest is not None and model_metadata["model"]["digest"] != args.expected_digest: raise EvalError("exact model digest mismatch")
        report={"complete":False,"created_at_utc":datetime.now(timezone.utc).isoformat(),"suite":{"id":fixture["suite_id"],"version":fixture["suite_version"],"fixture_sha256":sha(canonical(fixture)),"runner_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"system_prompt_sha256":sha(system),"final_contract_sha256":sha(contract),"combined_prompt_sha256":sha(system+contract)},"runtime":runtime,"metadata":model_metadata,"evidence":[]}; atomic_write(args.output,report)
        for level in fixture["pressure_levels"]:
            messages=build_messages(system,contract,fixture,level["filler_pairs"]); entry={"pressure":level,"message_count":len(messages),"input_char_count":sum(len(message["content"]) for message in messages),"runs":[]}; report["evidence"].append(entry)
            for _ in range(args.runs): entry["runs"].append(run_one(args.endpoint,payload(args.model,messages,args),args,fixture["expected"])); atomic_write(args.output,report)
        for entry in report["evidence"]: entry["aggregate"]=aggregate(entry["runs"])
        all_runs=[x for e in report["evidence"] for x in e["runs"]]; report["aggregate"]=aggregate(all_runs); report["complete"]=report["aggregate"]["complete"]; atomic_write(args.output,report)
        return 1 if not report["complete"] or (args.fail_on_gate and report["aggregate"]["gate"]!="PASS") else 0
    except EvalError as exc: print("context gate error:",exc,file=sys.stderr); return 2
if __name__ == "__main__": raise SystemExit(main())
