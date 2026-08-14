"""P7 common render probe. It neither starts/stops nor switches services."""
from __future__ import annotations
import argparse, hashlib, json, os, socket, subprocess, tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen
from model_usage_manifest import validate_manifest, canonical_json_bytes, canonical_sha256, file_sha256

SCHEMA_VERSION='airi.p7-common-render-probe.v1'
PROMPTS=('안녕하세요, 오늘도 함께해요.','짧고 따뜻하게 인사해 주세요.','비가 오면 우산을 챙겨요.','천천히 숨을 고르고 시작해요.','방송에서 자연스럽게 답해 주세요.')
class P7Error(ValueError): pass
def load_json(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def loopback(url):
 p=urlparse(url)
 if p.scheme not in ('http','https') or p.hostname not in ('127.0.0.1','localhost'):raise P7Error('loopback endpoint required')
 return p
def get_json(url):
 with urlopen(url,timeout=10) as r:return json.loads(r.read())
def port_open(host,port):
 try:
  with socket.create_connection((host,port),timeout=1):return True
 except OSError:return False
def percentile(values,p):
 if not values:return 'unknown'
 values=sorted(values);i=(len(values)-1)*p;lo=int(i);hi=min(lo+1,len(values)-1);return round(values[lo]+(values[hi]-values[lo])*(i-lo),6)
def verify_environment(manifest_path,proxy_url,ollama_url,asar_path,source_root,meter_path,runtime_model,expected_digest):
 manifest=validate_manifest(load_json(manifest_path));loopback(proxy_url);loopback(ollama_url)
 if not isinstance(expected_digest,str) or len(expected_digest)!=64 or any(c not in '0123456789abcdef' for c in expected_digest):raise P7Error('expected digest must be lowercase 64-hex')
 health=get_json(proxy_url.rstrip('/')+'/health'); chat=health.get('chat_model',{}); digest=chat.get('digest',{})
 required={'model':chat.get('model'),'digest':digest.get('digest'),'num_ctx':health.get('num_ctx')}
 if required!={'model':runtime_model,'digest':expected_digest,'num_ctx':2048}:raise P7Error('health exact runtime model/digest/num_ctx2048 mismatch')
 moderation=health.get('output_moderation',{}); memory=health.get('memory',{}); provider=health.get('chat_provider',{})
 if moderation.get('enabled') is not False or memory.get('extraction_enabled') is not False:raise P7Error('moderation and memory extraction must be false')
 if provider.get('provider')!='local' or provider.get('external_approved') is not False:raise P7Error('chat provider must be local with no external approval')
 tags=get_json(ollama_url.rstrip('/')+'/api/tags'); matches=[m for m in tags.get('models',[]) if isinstance(m,dict) and m.get('name')==runtime_model and m.get('digest')==expected_digest]
 if len(matches)!=1:raise P7Error('Ollama tags missing exact model and digest')
 if not port_open('127.0.0.1',9880) or port_open('127.0.0.1',8890) or port_open('127.0.0.1',11436):raise P7Error('TTS must listen and STT/extraction must be closed')
 for p in (source_root,meter_path,asar_path):
  if not Path(p).exists():raise P7Error(f'missing required path: {p}')
 return manifest,required,file_sha256(asar_path)
def run_measure(script,prompt,source_root,command_runner):
 result=command_runner(['powershell','-NoProfile','-File',str(script),'-Text',prompt,'-SourceRoot',str(source_root),'-Threshold','0.003'])
 if isinstance(result,bytes):result=result.decode()
 data=json.loads(result)
 if data.get('ok') is not True or not all(isinstance(data.get(k),(int,float)) for k in ('first_region_after_completion_ms','completed_ms','playback_started_ms')):raise P7Error('measurement must return successful numeric render/completion/playback metrics')
 return {'render_ms':data['first_region_after_completion_ms'],'completion_ms':data['completed_ms'],'playback_started_ms':data['playback_started_ms']}
def atomic(path,value):
 target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile('wb',dir=target.parent,delete=False) as f:tmp=Path(f.name);f.write(canonical_json_bytes(value)+b'\n')
 try:os.replace(tmp,target)
 finally:tmp.unlink(missing_ok=True)
def build_report(manifest,manifest_sha,runtime,asar_before,source_revision,rows,limitation,status='incomplete',asar_after='pending'):
 return {'schema_version':SCHEMA_VERSION,'status':status,'candidate_id':manifest['candidate_id'],'profile':'common','manifest_file_sha256':manifest_sha,'manifest_canonical_sha256':canonical_sha256(manifest),'exact_revision':manifest['exact_revision'],'source_revision':source_revision,'runtime':runtime,'asar':{'before_sha256':asar_before,'after_sha256':asar_after,'unchanged':asar_before==asar_after if asar_after!='pending' else 'pending'},'game_or_concurrent_load_limitation':limitation,'prompt_count':10,'rows':rows,'metrics':{'render_ms':{'p50':percentile([x['render_ms'] for x in rows],.5),'p95':percentile([x['render_ms'] for x in rows],.95)},'completion_ms':{'p50':percentile([x['completion_ms'] for x in rows],.5),'p95':percentile([x['completion_ms'] for x in rows],.95)}}}
def main(argv=None):
 a=argparse.ArgumentParser();a.add_argument('--manifest',required=True);a.add_argument('--runtime-model',required=True);a.add_argument('--expected-digest',required=True);a.add_argument('--proxy-url',default='http://127.0.0.1:11435');a.add_argument('--ollama-url',default='http://127.0.0.1:11434');a.add_argument('--asar',required=True);a.add_argument('--source-root',required=True);a.add_argument('--source-revision',required=True);a.add_argument('--meter-path',required=True);a.add_argument('--measure-script',required=True);a.add_argument('--output',required=True);a.add_argument('--limitation',required=True);a.add_argument('--resume',action='store_true');z=a.parse_args(argv)
 if len(z.source_revision)!=40 or any(c not in '0123456789abcdef' for c in z.source_revision):raise P7Error('source revision must be full lowercase commit SHA')
 m,r,pre=verify_environment(z.manifest,z.proxy_url,z.ollama_url,z.asar,z.source_root,z.meter_path,z.runtime_model,z.expected_digest);manifest_sha=file_sha256(z.manifest);rows=[]
 identity={'candidate_id':m['candidate_id'],'manifest_file_sha256':manifest_sha,'runtime':r,'source_revision':z.source_revision}
 if z.resume and Path(z.output).exists():
  prior=load_json(z.output)
  if any(prior.get(k)!=v for k,v in identity.items()):raise P7Error('resume identity mismatch')
  rows=prior.get('rows',[])
 done={x.get('trial') for x in rows};runner=lambda args:subprocess.check_output(args,text=True)
 for trial,prompt in enumerate(PROMPTS+tuple(reversed(PROMPTS)),1):
  h=hashlib.sha256(prompt.encode()).hexdigest()
  if trial in done:continue
  rows.append({'trial':trial,'prompt_sha256':h,**run_measure(z.measure_script,prompt,z.source_root,runner)});atomic(z.output,build_report(m,manifest_sha,r,pre,z.source_revision,rows,z.limitation))
 post=file_sha256(z.asar)
 if post!=pre:raise P7Error('asar changed during probe')
 if len(rows)!=10:raise P7Error('exactly 10 render measurements are required')
 atomic(z.output,build_report(m,manifest_sha,r,pre,z.source_revision,rows,z.limitation,'complete',post));return 0
if __name__=='__main__':raise SystemExit(main())
