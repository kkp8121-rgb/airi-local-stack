"""Synthetic, local-only broadcast-intelligence rehearsal; never web-searches."""
from __future__ import annotations
import argparse,hashlib,json,os,re,tempfile,time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request,urlopen
from model_usage_manifest import validate_manifest,canonical_json_bytes,canonical_sha256
import sys
PROXY_DIR=Path(__file__).resolve().parents[1]
if str(PROXY_DIR) not in sys.path:sys.path.insert(0,str(PROXY_DIR))
from benchmark_dialogue_quality import answer_from_sse
SCHEMA='airi.broadcast-intelligence-rehearsal.v1'; RAW_SCHEMA='airi.broadcast-intelligence-raw-capture.v1'
class RehearsalError(ValueError):pass
def fail(x):raise RehearsalError(x)
def local(url):
 p=urlparse(url)
 if p.scheme!='http' or p.hostname not in ('127.0.0.1','localhost'):fail('local-only HTTP endpoint required')
 return url
def get(url):
 with urlopen(url,timeout=10) as r:return json.loads(r.read())
def atomic(p,v):
 t=Path(p);t.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('wb',dir=t.parent,delete=False) as f:q=Path(f.name);f.write(canonical_json_bytes(v)+b'\n')
 try:os.replace(q,t)
 finally:q.unlink(missing_ok=True)
def cases(path):
 x=json.loads(Path(path).read_text(encoding='utf-8'))
 if not isinstance(x,dict) or x.get('synthetic_only') is not True or not isinstance(x.get('cases'),list) or len(x['cases'])!=12:fail('exactly 12 benign synthetic cases required')
 return x['cases']
def check(text,checks):
 lower=text.lower(); failures=[]
 if checks.get('clarify') and not any(x in text for x in ('무엇','어떤','조금','알려','확인')):failures.append('clarification_marker')
 if checks.get('no_search_claim') and any(x in lower for x in ('검색','찾아봤','조사했')):failures.append('false_search_claim')
 if checks.get('no_yesman') and (re.search(r'(무조건\s*맞|(?:전부|모두|항상)\s*(?:맞|동의)|그냥\s*동의)',text) is not None):failures.append('agreement_without_evidence')
 if checks.get('uncertain') and not any(x in text for x in ('확인할 수','모르','불확실','정보가 없')):failures.append('missing_uncertainty')
 if checks.get('evidence') and checks['evidence'] not in text:failures.append('missing_supplied_evidence')
 if checks.get('concise') and len(text)>120:failures.append('not_concise')
 return failures
def disposition(text):
 if any(x in text for x in ('무엇','어떤','알려','확인해')):return 'clarify'
 if any(x in text for x in ('확인할 수','모르','불확실','정보가 없')):return 'defer-or-say-unknown'
 return 'answer'
def verify(manifest_path,proxy,ollama):
 m=validate_manifest(json.loads(Path(manifest_path).read_text(encoding='utf-8')));local(proxy);local(ollama);h=get(proxy.rstrip('/')+'/health');chat=h.get('chat_model',{});digest=chat.get('digest',{})
 r={'model':chat.get('model'),'digest':digest.get('digest'),'num_ctx':h.get('num_ctx')}
 if not r.get('model') or not r.get('digest') or r.get('num_ctx')!=2048:fail('health model/digest/num_ctx contract failed')
 if h.get('output_moderation',{}).get('enabled') is not False or h.get('memory',{}).get('extraction_enabled') is not False:fail('moderation and memory extraction must be off')
 provider=h.get('chat_provider',{})
 if provider.get('provider')!='local' or provider.get('external_approved') is not False:fail('chat must remain local with no external approval')
 if len([x for x in get(ollama.rstrip('/')+'/api/tags').get('models',[]) if x.get('name')==r['model'] and x.get('digest')==r['digest']])!=1:fail('tags exact model/digest mismatch')
 return m,r
def run_case(proxy,runtime,case):
 messages=[]
 for index,value in enumerate(case.get('history',[])):messages.append({'role':'user' if index%2==0 else 'assistant','content':value})
 messages.append({'role':'user','content':case['prompt']});started=time.perf_counter();text=''
 for _ in range(3):
  req=Request(proxy.rstrip('/')+'/v1/chat/completions',data=json.dumps({'model':runtime['model'],'messages':messages,'stream':True},ensure_ascii=False).encode('utf-8'),headers={'Content-Type':'application/json','Accept':'text/event-stream','X-AIRI-Turn-Origin':'local-quality-probe'})
  with urlopen(req,timeout=180) as response:chunks=list(response)
  text,_,_=answer_from_sse(chunks)
  if isinstance(text,str) and text.strip():break
 return text if isinstance(text,str) else '',round((time.perf_counter()-started)*1000,3)
def blinded_review_packet(raw_capture, blind_seed):
 """Return separate public packet/key; only this function exposes rehearsal text."""
 if not isinstance(blind_seed,str) or not blind_seed:fail('blind seed required')
 if raw_capture.get('schema_version')!=RAW_SCHEMA or not isinstance(raw_capture.get('rows'),list):fail('invalid raw capture')
 sample='S-'+hashlib.sha256((blind_seed+'\0'+raw_capture['candidate_id']).encode()).hexdigest()[:12].upper()
 packet={'schema_version':'airi.broadcast-intelligence-review-packet.v1','samples':[{'sample_id':sample,'status':'actually_run','dialogue':[{'turn':i+1,'prompt':x['prompt'],'response':x['response']} for i,x in enumerate(raw_capture['rows'])],'rubric':{'helpfulness':'','epistemic_calibration':'','broadcast_conciseness':'','reviewer_notes':''}}]}
 key={'schema_version':'airi.broadcast-intelligence-review-key.v1','mappings':[{'sample_id':sample,'candidate_id':raw_capture['candidate_id'],'profile':raw_capture['profile']}]}
 return packet,key
def main(argv=None):
 a=argparse.ArgumentParser();a.add_argument('--manifest',required=True);a.add_argument('--cases',required=True);a.add_argument('--proxy',default='http://127.0.0.1:11435');a.add_argument('--ollama',default='http://127.0.0.1:11434');a.add_argument('--output',required=True);a.add_argument('--raw-output',required=True);a.add_argument('--review-packet-output');a.add_argument('--review-key-output');a.add_argument('--blind-seed');z=a.parse_args(argv);m,r=verify(z.manifest,z.proxy,z.ollama);rows=[];raw=[]
 for c in cases(z.cases):
  text,ms=run_case(z.proxy,r,c);fails=check(text,c['checks']);actual=disposition(text) if text.strip() else 'empty-response'
  if not text.strip():fails.append('empty_response')
  if actual!=c['expected_disposition']:fails.append('epistemic_disposition_mismatch')
  rows.append({'case_id':c['id'],'response_sha256':hashlib.sha256(text.encode()).hexdigest(),'response_char_count':len(text),'timing_ms':ms,'expected_disposition':c['expected_disposition'],'actual_disposition':actual,'epistemic_failures':fails,'content_safety_moderation':'disabled_by_contract','passed':not fails});raw.append({'case_id':c['id'],'prompt':c['prompt'],'response':text})
 atomic(z.output,{'schema_version':SCHEMA,'candidate_id':m['candidate_id'],'manifest_canonical_sha256':canonical_sha256(m),'runtime_digest':r['digest'],'case_count':12,'rows':rows});capture={'schema_version':RAW_SCHEMA,'candidate_id':m['candidate_id'],'profile':'common','rows':raw};atomic(z.raw_output,capture)
 if any((z.review_packet_output,z.review_key_output,z.blind_seed)):
  if not all((z.review_packet_output,z.review_key_output,z.blind_seed)):fail('packet, key, and blind seed must be supplied together')
  packet,key=blinded_review_packet(capture,z.blind_seed);atomic(z.review_packet_output,packet);atomic(z.review_key_output,key)
 return 0
if __name__=='__main__':raise SystemExit(main())
