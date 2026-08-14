"""Build a deterministic, content-safe P0--P4 AIRI A/B aggregate."""
from __future__ import annotations
import argparse, json, os, tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence
from model_usage_manifest import CANDIDATES, canonical_json_bytes, canonical_sha256, file_sha256, validate_complete_set

SCHEMA_VERSION = 'airi.ab-summary.v1'
CLASSIFICATION_SCHEMA_VERSION = 'airi.ab-classification.v1'
RESULT_SCHEMA_VERSION = 'airi.ab-stage-result.v1'
STAGES = ('P0', 'P1', 'P2', 'P3', 'P4')
PROFILES = ('native', 'common')
STATUSES = {'actual', 'blocked', 'unrunnable', 'not_run'}
FORBIDDEN = ('raw', 'text', 'prompt', 'response', 'message', 'score', 'winner', 'human', 'ranking')

class ABSummaryValidationError(ValueError): pass
def _fail(s): raise ABSummaryValidationError(s)
def _load(p):
    try: return json.loads(Path(p).read_text(encoding='utf-8'))
    except Exception as e: _fail(f'{p}: invalid JSON: {e}')
def _safe(v, path='value'):
    if isinstance(v, dict):
        if any(not isinstance(k,str) or any(x in k.lower() for x in FORBIDDEN) for k in v): _fail(f'{path}: raw text or human-score-bearing key')
        return {k:_safe(v[k], f'{path}.{k}') for k in sorted(v)}
    if isinstance(v,list): return [_safe(x,path) for x in v]
    if v is None or isinstance(v,(str,int,float,bool)): return v
    _fail(f'{path}: invalid value')
def _manifests(paths):
    if len(paths)!=6: _fail('exactly six manifests required')
    docs=validate_complete_set([_load(p) for p in paths]); out={}
    for p,d in zip(paths,docs): out[d['candidate_id']]={'file_sha256':file_sha256(p),'canonical_sha256':canonical_sha256(d),'exact_revision':d['exact_revision'],'quantization':d['quantization']}
    return out
def _classification(d):
    if not isinstance(d,dict) or set(d)!={'schema_version','rows'} or d['schema_version']!=CLASSIFICATION_SCHEMA_VERSION: _fail('invalid classification schema')
    out={}
    for x in d['rows']:
        if not isinstance(x,dict) or set(x)!={'candidate_id','profile','stage','status','reason'}: _fail('invalid classification row')
        k=(x['candidate_id'],x['profile'],x['stage'])
        if k[0] not in CANDIDATES or k[1] not in PROFILES or k[2] not in STAGES or x['status'] not in STATUSES-{'actual'} or not isinstance(x['reason'],str) or not x['reason']: _fail('invalid classification value')
        if k in out: _fail('duplicate classification')
        out[k]={'status':x['status'],'reason':x['reason']}
    return out
def _results(directory, manifests):
    out={}
    for p in sorted(Path(directory).glob('*.json')):
        x=_load(p); req={'schema_version','candidate_id','profile','stage','manifest_file_sha256','manifest_canonical_sha256','runtime_digest','gate','counts','metrics'}
        if not isinstance(x,dict): continue
        if set(x)!=req or x.get('schema_version')!=RESULT_SCHEMA_VERSION:
            if {'candidate_id','profile','stage'}.issubset(x): _fail(f'{p}: invalid or raw-text-bearing result schema')
            continue
        k=(x['candidate_id'],x['profile'],x['stage'])
        if k[0] not in manifests or k[1] not in PROFILES or k[2] not in STAGES: _fail(f'{p}: unknown candidate/profile/stage')
        m=manifests[k[0]]
        if x['manifest_file_sha256']!=m['file_sha256'] or x['manifest_canonical_sha256']!=m['canonical_sha256']: _fail(f'{p}: manifest mismatch')
        if k in out: _fail('duplicate result')
        out[k]={'status':'actual','reason':'ACTUAL_RESULT','runtime_digest':_safe(x['runtime_digest']),'gate':_safe(x['gate']),'counts':_safe(x['counts']),'metrics':_safe(x['metrics'])}
    return out
def build_summary(manifest_paths, results_dir, classification):
    manifests=_manifests(manifest_paths); classes=_classification(classification); results=_results(results_dir,manifests); rows=[]
    expected={(c,p,s) for c in CANDIDATES for p in PROFILES for s in STAGES}
    for k in sorted(expected):
        if k in results:
            if k in classes:_fail('result and classification conflict')
            v=results[k]
        else:
            if k not in classes:_fail(f'missing classification for {k[0]}/{k[1]}/{k[2]}')
            v={**classes[k],'runtime_digest':'unknown','gate':'unknown','counts':{},'metrics':{}}
        c,p,s=k; rows.append({'candidate_id':c,'profile':p,'stage':s,**v,'provenance':manifests[c],'developer_benchmark':'unknown','human_review_pending':True})
    return {'schema_version':SCHEMA_VERSION,'rows':rows,'p6_human_review_pending':True}
def write_atomic(path, value):
    t=Path(path); t.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('wb',dir=t.parent,delete=False) as f: tmp=Path(f.name);f.write(canonical_json_bytes(value)+b'\n')
    try: os.replace(tmp,t)
    finally: tmp.unlink(missing_ok=True)
def main(argv=None):
    a=argparse.ArgumentParser();a.add_argument('--manifest',action='append',required=True);a.add_argument('--results-dir',required=True);a.add_argument('--classification',required=True);a.add_argument('--output',required=True);z=a.parse_args(argv)
    try: write_atomic(z.output,build_summary(z.manifest,z.results_dir,_load(z.classification)))
    except ABSummaryValidationError as e:a.error(str(e))
    return 0
if __name__=='__main__':raise SystemExit(main())
