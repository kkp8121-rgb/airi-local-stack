"""Blind five successful synthetic broadcast-intelligence captures for review."""
from __future__ import annotations
import argparse,hashlib,json,os,tempfile
from pathlib import Path
from typing import Sequence

RAW_SCHEMA='airi.broadcast-intelligence-raw-capture.v1'
PACKET_SCHEMA='airi.combined-intelligence-review-packet.v1'
KEY_SCHEMA='airi.combined-intelligence-review-key.v1'
REQUIRED={'midm-2.0-mini-instruct','ministral-3-3b-instruct-2512-bf16','qwen3-4b','phi-4-mini-instruct','granite-3.3-2b-instruct'}

class PacketError(ValueError): pass
def fail(x):raise PacketError(x)
def load(path):
 try:return json.loads(Path(path).read_text(encoding='utf-8'))
 except Exception as e:fail(f'{path}: invalid JSON: {e}')
def fixture_ids(path):
 x=load(path)
 if not isinstance(x,dict) or x.get('synthetic_only') is not True or not isinstance(x.get('cases'),list) or len(x['cases'])!=12:fail('safe synthetic fixture with exactly 12 cases required')
 ids=[c.get('id') for c in x['cases'] if isinstance(c,dict)]
 if len(ids)!=12 or len(set(ids))!=12 or any(not isinstance(i,str) or not i for i in ids):fail('fixture case identifiers invalid')
 return ids
def captures(paths,ids):
 if len(paths)!=5:fail('exactly five capture paths required')
 result={}
 for p in paths:
  x=load(p)
  if not isinstance(x,dict) or set(x)!={'schema_version','candidate_id','profile','rows'} or x.get('schema_version')!=RAW_SCHEMA:fail('invalid raw capture schema')
  c=x['candidate_id']
  if c not in REQUIRED or x.get('profile')!='common' or c in result:fail('unexpected, non-common, or duplicate capture')
  rows=x.get('rows')
  if not isinstance(rows,list) or len(rows)!=12:fail('capture must have 12 successful rows')
  checked=[]
  for row in rows:
   if not isinstance(row,dict) or set(row)!={'case_id','prompt','response'} or not all(isinstance(row.get(k),str) for k in ('case_id','prompt','response')) or not row['case_id'] or not row['prompt']:fail('capture row must contain only case_id/nonempty-prompt/string-response')
   checked.append(row)
  if [r['case_id'] for r in checked]!=ids:fail('capture case IDs must exactly match synthetic fixture order')
  result[c]=checked
 if set(result)!=REQUIRED:fail('exact non-Motif five candidate set required')
 return result
def atomic(path,value):
 target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=target.parent,delete=False) as f:tmp=Path(f.name);json.dump(value,f,ensure_ascii=False,sort_keys=True,separators=(',',':'));f.write('\n')
 try:os.replace(tmp,target)
 finally:tmp.unlink(missing_ok=True)
def build(capture_paths,fixture_path,seed):
 if not isinstance(seed,str) or not seed:fail('non-empty seed required')
 ids=fixture_ids(fixture_path);by_candidate=captures(capture_paths,ids)
 ordered=sorted(REQUIRED,key=lambda c:hashlib.sha256((seed+'\0'+c).encode()).hexdigest());samples=[];mappings=[]
 for index,candidate in enumerate(ordered):
  sample_id='I-'+hashlib.sha256((seed+'\0'+candidate).encode()).hexdigest()[:12].upper()
  samples.append({'sample_id':sample_id,'order':index+1,'dialogue':[{'turn':i+1,'prompt':r['prompt'],'response':r['response']} for i,r in enumerate(by_candidate[candidate])],'rubric':{'helpfulness':'','epistemic_calibration':'','evidence_use':'','broadcast_conciseness':'','reviewer_notes':''}})
  mappings.append({'sample_id':sample_id,'candidate_id':candidate,'profile':'common'})
 return {'schema_version':PACKET_SCHEMA,'blind_seed_sha256':hashlib.sha256(seed.encode()).hexdigest(),'sample_count':5,'turns_per_sample':12,'samples':samples},{'schema_version':KEY_SCHEMA,'blind_seed_sha256':hashlib.sha256(seed.encode()).hexdigest(),'mappings':sorted(mappings,key=lambda x:x['sample_id'])}
def main(argv:Sequence[str]|None=None):
 a=argparse.ArgumentParser();a.add_argument('--capture',action='append',required=True);a.add_argument('--fixture',required=True);a.add_argument('--seed',required=True);a.add_argument('--packet-output',required=True);a.add_argument('--key-output',required=True);z=a.parse_args(argv)
 try:p,k=build(z.capture,z.fixture,z.seed);atomic(z.packet_output,p);atomic(z.key_output,k)
 except PacketError as e:a.error(str(e))
 return 0
if __name__=='__main__':raise SystemExit(main())
