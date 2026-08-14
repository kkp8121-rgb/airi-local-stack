"""Strict offline native A/B rehearsal for the two pinned Korean candidates.

Preflight is deliberately complete before importing any ML library.
"""
from __future__ import annotations

import argparse, gc, hashlib, json, os, platform, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from model_usage_manifest import canonical_sha256, file_sha256, validate_manifest

FIXTURE = Path(__file__).with_name('airi_native_broadcast_rehearsal_cases_v1.json')
MANIFESTS = Path(__file__).with_name('model-usage-manifests')
CAP = 2048
MAX_NEW = 128
CANDIDATES = {
    'midm-2.0-mini-instruct': {'revision': '383eb221c52a32278f1985257b264ade8d982e60', 'transformers': '4.48.2', 'eos': 2, 'remote': False},
    'motif-2.6b-v1.1-lc': {'revision': '70bf316e166f2a256b1068e35c8310541a6a06bc', 'transformers': '4.51.3', 'eos': [219395, 219405], 'remote': True},
}

class RehearsalError(RuntimeError): pass


class FirstTokenTimer:
    """Measure model-level first-token time without changing generated text."""

    def __init__(self, request_started: float) -> None:
        self.request_started = request_started
        self.prompt_seen = False
        self.first_token_seconds: float | None = None

    def put(self, _value: Any) -> None:
        # Transformers streams the complete prompt once before generated tokens.
        if not self.prompt_seen:
            self.prompt_seen = True
            return
        if self.first_token_seconds is None:
            self.first_token_seconds = time.monotonic() - self.request_started

    def end(self) -> None:
        return None

def _sha(value: bytes | str) -> str:
    return hashlib.sha256(value.encode('utf-8') if isinstance(value, str) else value).hexdigest()
def _now() -> str: return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
def _canonical(value: Any) -> str: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
def _atomic_write(path: str | Path, value: Mapping[str, Any]) -> None:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=target.name + '.', suffix='.tmp', dir=target.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)

def load_fixture(path: str | Path = FIXTURE) -> tuple[dict[str, Any], str]:
    raw = Path(path).read_bytes(); data = json.loads(raw.decode('utf-8'))
    cases = data.get('cases') if isinstance(data, dict) else None
    if data.get('schema_version') != 'airi.native-broadcast-rehearsal-cases.v1' or data.get('synthetic_only') is not True or not isinstance(data.get('system_message'), str) or not isinstance(cases, list) or len(cases) != 16:
        raise RehearsalError('fixture is not the required 16-case synthetic suite')
    ids = [case.get('id') for case in cases if isinstance(case, dict)]
    if len(ids) != 16 or len(set(ids)) != 16: raise RehearsalError('fixture case ids are invalid')
    return data, _sha(raw)

def case_messages(fixture: Mapping[str, Any], case: Mapping[str, Any]) -> list[dict[str, str]]:
    messages = [{'role': 'system', 'content': fixture['system_message']}]
    for message in case.get('history', []):
        if not isinstance(message, dict) or message.get('role') not in ('user', 'assistant') or not isinstance(message.get('content'), str): raise RehearsalError('invalid synthetic history')
        messages.append({'role': message['role'], 'content': message['content']})
    if not isinstance(case.get('user'), str): raise RehearsalError('invalid fixture prompt')
    messages.append({'role': 'user', 'content': case['user']})
    return messages

def _is_reparse(path: Path) -> bool:
    try: return path.is_symlink() or bool(path.stat(follow_symlinks=False).st_file_attributes & 0x400)
    except AttributeError: return path.is_symlink()
def verify_snapshot(manifest: Mapping[str, Any], snapshot_path: str | Path) -> dict[str, Any]:
    root = Path(snapshot_path)
    if not root.is_dir() or _is_reparse(root): raise RehearsalError('snapshot directory is unsafe')
    expected = {str(item['path']).replace('\\', '/') : item for item in manifest['artifacts']}
    actual: set[str] = set()
    for item in root.rglob('*'):
        if _is_reparse(item): raise RehearsalError('snapshot contains link or reparse point')
        if item.is_file(): actual.add(item.relative_to(root).as_posix())
    if actual != set(expected): raise RehearsalError('snapshot files do not exactly match manifest')
    for relative, artifact in expected.items():
        file = root / relative
        if file.stat().st_size != artifact['size'] or file_sha256(file) != artifact['sha256']: raise RehearsalError('snapshot artifact verification failed')
    return {'file_count': len(actual), 'manifest_sha256': canonical_sha256(manifest)}

def load_manifest(candidate: str, manifest_path: str | Path | None = None) -> dict[str, Any]:
    if candidate not in CANDIDATES: raise RehearsalError('only Midm and Motif are supported')
    file = Path(manifest_path) if manifest_path else MANIFESTS / f'{candidate}.json'
    manifest = validate_manifest(json.loads(file.read_text(encoding='utf-8')))
    expected = CANDIDATES[candidate]
    if manifest['candidate_id'] != candidate or manifest['exact_revision'] != expected['revision'] or manifest['remote_code']['required'] != expected['remote']:
        raise RehearsalError('manifest is not the exact audited candidate')
    if manifest['tokenizer']['eos_token_id'] != expected['eos']: raise RehearsalError('manifest EOS does not match pinned expectation')
    if candidate == 'motif-2.6b-v1.1-lc' and {a['path'] for a in manifest['remote_code']['audited_artifacts']} != {'configuration_motif.py', 'modeling_motif.py'}: raise RehearsalError('Motif audited remote-code pair is incomplete')
    return manifest

def generation_options(candidate: str, profile: str) -> dict[str, Any]:
    """The card-faithful method and the equal broadcast comparison method."""
    if profile not in ('hf_card', 'broadcast_equal'): raise RehearsalError('invalid profile')
    if profile == 'broadcast_equal': return {'do_sample': False, 'max_new_tokens': 128}
    if candidate == 'midm-2.0-mini-instruct':
        return {'do_sample': False, 'max_new_tokens': 128, 'use_card_generation_config': True}
    return {'do_sample': False, 'max_new_tokens': 1024}

def _ram() -> dict[str, int]:
    try:
        import psutil
        return {'available_bytes': psutil.virtual_memory().available, 'used_bytes': psutil.virtual_memory().used}
    except Exception: return {}
def _gpu(torch: Any) -> dict[str, int]:
    if not torch.cuda.is_available(): return {}
    return {'allocated_bytes': torch.cuda.memory_allocated(), 'reserved_bytes': torch.cuda.memory_reserved(), 'peak_allocated_bytes': torch.cuda.max_memory_allocated()}

def run_rehearsal(*, candidate: str, snapshot: str | Path, report_path: str | Path, manifest_path: str | Path | None = None, gpu_max_mib: int, cpu_max_gib: int, fixture_path: str | Path = FIXTURE) -> dict[str, Any]:
    """Run one exact candidate in its own pinned Python environment."""
    report: dict[str, Any] = {'schema_version':'airi.native-broadcast-rehearsal.v1','status':'incomplete','started_at':_now(), 'candidate_id': candidate}
    model = tokenizer = torch = None
    try:
        if candidate not in CANDIDATES or not isinstance(gpu_max_mib, int) or not isinstance(cpu_max_gib, int) or gpu_max_mib < 1 or cpu_max_gib < 1:
            raise RehearsalError('candidate and positive explicit memory bounds are required')
        fixture, fixture_hash = load_fixture(fixture_path)
        manifest = load_manifest(candidate, manifest_path)
        snapshot = Path(snapshot); snapshot_preflight = verify_snapshot(manifest, snapshot)
        report['preflight'] = {'fixture_sha256': fixture_hash, 'case_count': 16, 'snapshot': snapshot_preflight, 'runtime_deviation': 'BF16 device_map=auto with bounded CPU offload is used instead of model.cuda() for the local 8GB GPU'}
        os.environ.update({'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1','DO_NOT_TRACK':'1'})
        import torch as imported_torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer, GenerationConfig
        torch = imported_torch
        if torch.__version__ != '2.5.1+cu121' or __import__('accelerate').__version__ != '1.6.0' or transformers.__version__ != CANDIDATES[candidate]['transformers']:
            raise RehearsalError('runtime library versions are not pinned')
        if torch.cuda.is_available() and gpu_max_mib > torch.cuda.get_device_properties(0).total_memory // (1024 * 1024):
            raise RehearsalError('GPU memory bound exceeds physical CUDA memory')
        max_memory = {0:f'{gpu_max_mib}MiB', 'cpu':f'{cpu_max_gib}GiB'}; remote = CANDIDATES[candidate]['remote']
        tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=remote)
        model_options = {'local_files_only': True, 'trust_remote_code': True, 'torch_dtype': torch.bfloat16, 'device_map': 'auto', 'max_memory': max_memory, 'low_cpu_mem_usage': True, 'use_safetensors': True}
        if remote: model_options['_attn_implementation'] = 'eager'
        model = AutoModelForCausalLM.from_pretrained(snapshot, **model_options)
        eos = model.generation_config.eos_token_id
        if eos != CANDIDATES[candidate]['eos']: raise RehearsalError('loaded model EOS differs from pinned expectation')
        runs=[]
        for profile, repetitions in (('hf_card',1),('broadcast_equal',3)):
            options=generation_options(candidate, profile)
            for case in fixture['cases']:
                messages=case_messages(fixture, case); message_hash=_sha(_canonical(messages))
                for repeat in range(repetitions):
                    request_started=time.monotonic()
                    seed=42+repeat; torch.manual_seed(seed)
                    if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed); torch.cuda.reset_peak_memory_stats()
                    encoded=tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors='pt', return_dict=True, **({'date_string':'14 Aug 2026'} if candidate == 'midm-2.0-mini-instruct' else {})); encoded.pop('token_type_ids',None)
                    device=model.get_input_embeddings().weight.device; encoded={k:v.to(device) for k,v in encoded.items()}; input_tokens=int(encoded['input_ids'].shape[-1])
                    card_cap=options['max_new_tokens']; runtime_cap=min(card_cap, CAP-input_tokens)
                    if runtime_cap < 1: raise RehearsalError('broadcast token cap exceeded')
                    generation_kwargs=dict(options); generation_kwargs.pop('use_card_generation_config',None); generation_kwargs['max_new_tokens']=runtime_cap
                    if options.get('use_card_generation_config'):
                        card_config=GenerationConfig.from_pretrained(snapshot, local_files_only=True); card_config.max_new_tokens=card_cap; generation_kwargs['generation_config']=card_config
                    vram_before, ram_before=_gpu(torch), _ram()
                    if torch.cuda.is_available(): torch.cuda.synchronize()
                    generation_started=time.monotonic(); first_token_timer=FirstTokenTimer(request_started)
                    generated=model.generate(**encoded, use_cache=True, pad_token_id=tokenizer.pad_token_id, eos_token_id=eos, streamer=first_token_timer, **generation_kwargs)
                    if torch.cuda.is_available(): torch.cuda.synchronize()
                    generation_finished=time.monotonic(); total_elapsed=generation_finished-request_started; generation_elapsed=generation_finished-generation_started; vram_after, ram_after=_gpu(torch), _ram(); ids=generated[0][input_tokens:]; output=tokenizer.decode(ids, skip_special_tokens=True); output_tokens=int(ids.shape[-1]); last=int(ids[-1]) if output_tokens else None; eos_values=eos if isinstance(eos,list) else [eos]
                    runs.append({'case_id':case['id'],'category':case['category'],'profile':profile,'run':repeat+1,'seed':seed,'message_sha256':message_hash,'input_tokens':input_tokens,'output_tokens':output_tokens,'total_tokens':input_tokens+output_tokens,'output':output,'output_sha256':_sha(output),'char_count':len(output),'ttft_seconds':first_token_timer.first_token_seconds,'preparation_seconds':generation_started-request_started,'generation_seconds':generation_elapsed,'latency_seconds':total_elapsed,'tokens_per_second':output_tokens/generation_elapsed if generation_elapsed and output_tokens else None,'finish_reason':'eos' if last in eos_values else 'length','end_token_id':last,'generation_options':options,'official_card_max_new_tokens':card_cap,'runtime_max_new_tokens':runtime_cap,'runtime_total_token_cap':CAP,'vram_before':vram_before,'ram_before':ram_before,'vram_after':vram_after,'ram_after':ram_after})
        report['candidate']={'manifest_file_sha256':file_sha256(Path(manifest_path)) if manifest_path else file_sha256(MANIFESTS/f'{candidate}.json'),'manifest_canonical_sha256':canonical_sha256(manifest),'revision':manifest['exact_revision'],'template_sha256':manifest['template']['sha256'],'template_date_string':'14 Aug 2026' if candidate == 'midm-2.0-mini-instruct' else None,'generation_config_sha256':_sha(_canonical(model.generation_config.to_dict())),'eos_token_id':eos,'runtime':{'torch':torch.__version__,'transformers':transformers.__version__,'accelerate':__import__('accelerate').__version__},'runs':runs}; report['status']='complete'
    except Exception as exc:
        report['status']='error'; report['error']={'type':type(exc).__name__,'message':'native broadcast rehearsal did not complete'}
    finally:
        if model is not None: del model
        if tokenizer is not None: del tokenizer
        gc.collect()
        if torch is not None and torch.cuda.is_available(): torch.cuda.empty_cache()
        report['finished_at']=_now(); _atomic_write(report_path, report)
    return report

def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--candidate',choices=sorted(CANDIDATES),required=True); parser.add_argument('--snapshot',required=True); parser.add_argument('--manifest'); parser.add_argument('--report',required=True); parser.add_argument('--gpu-max-mib',type=int,required=True); parser.add_argument('--cpu-max-gib',type=int,required=True); args=parser.parse_args(argv)
    result=run_rehearsal(candidate=args.candidate,snapshot=args.snapshot,manifest_path=args.manifest,report_path=args.report,gpu_max_mib=args.gpu_max_mib,cpu_max_gib=args.cpu_max_gib); print(json.dumps({'status':result['status']})); return 0 if result['status']=='complete' else 1
if __name__ == '__main__': raise SystemExit(main())
