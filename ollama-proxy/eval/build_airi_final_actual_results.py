"""Build the final content-free AIRI actual-results table from an explicit index."""
from __future__ import annotations
import argparse,json,os,tempfile
from pathlib import Path
from typing import Any
from model_usage_manifest import CANDIDATES,canonical_json_bytes,canonical_sha256,file_sha256,validate_complete_set

SCHEMA_VERSION='airi.final-actual-results.v1'; INDEX_SCHEMA='airi.final-actual-results-index.v1'
STAGES={'P1','P2','P3','P4','P5','P6','P7','aux_thinking'}; PROFILES={'native','common'}; KINDS={'actual','synthesized','unit','human_pending'}
FORBIDDEN=('raw','dialogue','prompt','response','message','content','reviewer_notes','score','key','mapping')
class FinalResultsError(ValueError):pass
def fail(x):raise FinalResultsError(x)
def load(p):
 try:return json.loads(Path(p).read_text(encoding='utf-8'))
 except Exception as e:fail(f'{p}: invalid JSON: {e}')
def safe(v,path='report'):
 if isinstance(v,dict):
  if any(not isinstance(k,str) or any(f in k.lower() for f in FORBIDDEN) for k in v):fail(f'{path}: content-bearing or human-score key')
  return {k:safe(v[k],f'{path}.{k}') for k in sorted(v)}
 if isinstance(v,list):return [safe(x,path) for x in v]
 if v is None or isinstance(v,(str,int,float,bool)):return v
 fail(f'{path}: unsupported value')
def manifests(paths):
 if len(paths)!=6:fail('six manifests required')
 docs=validate_complete_set([load(x) for x in paths]);return {d['candidate_id']:{'file_sha256':file_sha256(p),'canonical_sha256':canonical_sha256(d),'exact_revision':d['exact_revision']} for p,d in zip(paths,docs)}
def parse_index(doc):
 if not isinstance(doc,dict) or set(doc)!={'schema_version','rows'} or doc['schema_version']!=INDEX_SCHEMA or not isinstance(doc['rows'],list):fail('invalid declared index')
 out=[];seen=set()
 for x in doc['rows']:
  req={'candidate_id','profile','stage','kind','status','reason','report_path'}
  if not isinstance(x,dict) or set(x)!=req:fail('invalid index row')
  k=(x['candidate_id'],x['profile'],x['stage'])
  if k in seen or k[0] not in CANDIDATES or k[1] not in PROFILES or k[2] not in STAGES or x['kind'] not in KINDS or not isinstance(x['status'],str) or not isinstance(x['reason'],str):fail('duplicate or invalid index row')
  seen.add(k);out.append(x)
 return out
def summarize(report,stage,candidate,profile,provenance):
 if not isinstance(report,dict):fail('report must be an object')
 for name, expected in (('candidate_id',candidate),('profile',profile),('exact_revision',provenance['exact_revision']),('manifest_canonical_sha256',provenance['canonical_sha256'])):
  if name in report and report[name]!=expected:fail(f'report {name} mismatch')
 if stage=='P6':
  if not isinstance(report,dict) or 'samples' not in report or not isinstance(report['samples'],list):fail('P6 requires public packet samples only')
  samples=report['samples'];
  for s in samples:
   if not isinstance(s,dict) or 'dialogue' in s or 'candidate_id' in s or 'profile' in s:fail('P6 packet must not contain dialogue or mapping')
  return {'p6_sample_count':len(samples),'p6_status_counts':{s.get('status','unknown'):sum(1 for q in samples if q.get('status','unknown')==s.get('status','unknown')) for s in samples},'p6_blank_human_rubric':all(all(v=='' for v in s.get('rubric',{}).values()) for s in samples)}
 return safe(report)
def build(manifest_paths,index_doc):
 prov=manifests(manifest_paths); rows=[]
 for item in parse_index(index_doc):
  c=item['candidate_id']; report_path=item['report_path']; report={}
  if report_path!='unknown':
   report=load(report_path); report=summarize(report,item['stage'],c,item['profile'],prov[c])
  rows.append({'candidate_id':c,'profile':item['profile'],'stage':item['stage'],'kind':item['kind'],'status':item['status'],'reason':item['reason'] or 'unknown','provenance':prov[c],'developer_benchmark':'unknown','quality':'unknown','context':'unknown','safety':'unknown','latency':'unknown','resource':'unknown','failures':[],'report':report})
 return {'schema_version':SCHEMA_VERSION,'rows':sorted(rows,key=lambda x:(x['candidate_id'],x['profile'],x['stage']))}
def atomic(path,v):
 t=Path(path);t.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('wb',dir=t.parent,delete=False) as f:q=Path(f.name);f.write(canonical_json_bytes(v)+b'\n')
 try:os.replace(q,t)
 finally:q.unlink(missing_ok=True)
def main(argv=None):
 a=argparse.ArgumentParser();a.add_argument('--manifest',action='append',required=True);a.add_argument('--index',required=True);a.add_argument('--output',required=True);z=a.parse_args(argv)
 try:atomic(z.output,build(z.manifest,load(z.index)))
 except FinalResultsError as e:a.error(str(e))
 return 0
if __name__=='__main__':raise SystemExit(main())
