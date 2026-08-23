#!/usr/bin/env python3
"""Read-only, fail-closed E2-C1 repository-freeze verifier."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path

SPLITS=('train','dev','test')
FILES={'correction':'seed/airi_broadcast_e2_c1_correction.jsonl','correction_chat':'seed/airi_broadcast_e2_c1_correction_chat.jsonl','mixture':'seed/airi_broadcast_e2_c1_mixture.jsonl','mixture_chat':'seed/airi_broadcast_e2_c1_mixture_chat.jsonl','replay_manifest':'seed/airi_broadcast_e2_c1_replay_manifest.json','dataset':'seed/airi_broadcast_e2_c1_dataset_manifest.json'}
FAMILIES={'identity_noninvention':(56,8,8),'unknown_identity':(48,8,8),'long_callback':(52,8,8),'donation_ritual':(52,8,8),'stale_transition':(40,8,8),'factual_grounding':(40,8,8),'complete_show_arc':(40,8,8),'safety_regression':(24,8,8)}
PINS={'base_model_sha256':'394b6624de810fd0630ba451c31b3530cc26444ba0e1fa7d98842b6af6e8f506','e2_adapter_model_sha256':'2a72292c1f8b8a2b6551c7c842a63e130b4aba2ec119483c8d66d07384895c5b','e2_adapter_config_sha256':'e01129ea8e2237ef0dc297ffd3ea902a75f28d1b3ee2c34eee0b275d6a0382b0','e2_adapter_artifact_sha256':'70998cffe99a489e99272e41e264d5775ff221402dce9fbc63a7a74741747195','e2_report_sha256':'628d640f17c7c1cb161b14c512e148b7dade0d721f0cb37a0748ee458fd6aa4c','v4_source_sha256':'43f9c1ed1abf1d32c94329de81d8ba9ddef93f560ef914814d34e0520eeba2ed','v4_chat_sha256':'96cc223ca5915355394480b60b459d9d039ffad4b47304974c5d939d4686eb44'}
class FrozenContractError(ValueError):pass
def sha(x):return hashlib.sha256(x).hexdigest()
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
def read(p):
    if p.is_symlink() or not p.is_file():raise FrozenContractError('file')
    return p.read_bytes()
def rows(p):
    raw=read(p)
    if b'\r' in raw or not raw.endswith(b'\n'):raise FrozenContractError('line ending')
    try:x=[json.loads(i) for i in raw.splitlines()]
    except Exception as e:raise FrozenContractError('jsonl') from e
    if not x or any(not isinstance(i,dict) for i in x):raise FrozenContractError('rows')
    return x,raw
def obj(p):
    try:x=json.loads(read(p))
    except Exception as e:raise FrozenContractError('json') from e
    if not isinstance(x,dict):raise FrozenContractError('object')
    return x
def assistant(x):
    m=x.get('messages')
    if not isinstance(m,list) or not m or any(not isinstance(a,dict) or set(a)!={'role','content'} or not isinstance(a['content'],str) for a in m) or m[-1]['role']!='assistant':raise FrozenContractError('messages')
    return m[-1]['content']
def pair(source,chat,target=True):
    if len(source)!=len(chat):raise FrozenContractError('parity')
    found={}
    for a,b in zip(source,chat):
        ks=('id','split','scenario_group','semantic_family')
        source_without_target={k:v for k,v in a.items() if k!='target'}
        if any(not isinstance(a.get(k),str) or a[k]!=b.get(k) for k in ks) or source_without_target!=b or a['id'] in found:raise FrozenContractError('row parity')
        if target and (not isinstance(a.get('target'),str) or assistant(a)!=a['target'] or assistant(b)!=a['target']):raise FrozenContractError('target')
        found[a['id']]=a
    return found
JOSA_PAIRS={'은':('은','는'),'는':('은','는'),'이':('이','가'),'가':('이','가'),'을':('을','를'),'를':('을','를'),'과':('과','와'),'와':('과','와'),'이라면':('이라면','라면'),'라면':('이라면','라면')}
JOSA_RE=re.compile(r'“([^”]+)”(이라면|라면|은|는|이|가|을|를|과|와)(?=\s|[.,!?])')
def josa(value,pair):
    for char in reversed(value):
        if '\uac00'<=char<='\ud7a3':return pair[0] if (ord(char)-0xAC00)%28 else pair[1]
    raise FrozenContractError('josa value')
def semantics(source):
    identity={'identity_noninvention','unknown_identity'}; tokens={x.get('required_token') for x in source if x.get('semantic_family') in identity}
    if None in tokens or '' in tokens:raise FrozenContractError('identity token')
    for x in source:
        family=x.get('semantic_family');target=x.get('target');required=x.get('required_token');facts=x.get('fact_tokens');updates=x.get('updated_tokens');decoys=x.get('decoy_tokens')
        if family not in FAMILIES or not isinstance(target,str) or not isinstance(required,str) or not required or any(not isinstance(v,list) or any(not isinstance(i,str) or not i for i in v) for v in (facts,updates,decoys)) or required not in target or any(i not in target for i in facts+updates) or any(i in target for i in decoys):raise FrozenContractError('semantic metadata')
        if family in identity:
            cues=('확인되지','근거','없어','보이지 않아','남아 있지 않아','확인할 수 없어','알 수 없어')
            if {i for i in tokens if i in target}!={required} or not any(i in target for i in cues):raise FrozenContractError('identity safety')
        if family=='donation_ritual' and (f'{required}님' not in target or '고마워' not in target):raise FrozenContractError('donation semantics')
        if family=='complete_show_arc' and '|' in target:raise FrozenContractError('show arc semantics')
        if re.search(r'(요|습니다|세요|죠)(?:[.!?]|$)',target):raise FrozenContractError('polite target')
    visible='\n'.join(i['content'] for x in source for i in x['messages'])
    for value,actual in JOSA_RE.findall(visible):
        if actual!=josa(value,JOSA_PAIRS[actual]):raise FrozenContractError('quoted josa')
    for pattern in (r'“[^”]*적혀 있어”라고 적혀 있어',r'처음 꺼낸 “[^”]+”[이가] “[^”]+”까지 이어졌어',r'“[^”]+”에서 출발해 “[^”]+”까지 모았어',r'”(?:야|였)',r'\?\.',r'\.\.',r'구름(?:를|가)',r'주제는 .* 제목을 붙여 줘야'):
        if re.search(pattern,visible):raise FrozenContractError('Korean grammar')
def receipt(man,name,data):
    x=man.get('files',{}).get(name)
    if not isinstance(x,dict) or set(x)!={'size','sha256'} or type(x.get('size')) is not int or x.get('size')!=len(data) or not isinstance(x.get('sha256'),str) or len(x['sha256'])!=64 or any(c not in '0123456789abcdef' for c in x['sha256']) or x.get('sha256')!=sha(data):raise FrozenContractError('receipt')
def training(man):
    c=man.get('training_contract'); want={'candidate':'E2-C1','init_mode':'adapter-weights-only','seed':42,'batch_size':1,'gradient_accumulation_steps':16,'max_seq_length':2048,'max_microsteps':512,'max_optimizer_steps':32,'learning_rate':1e-5,'lora_r':8,'lora_alpha':16,'lora_dropout':.05,'adam_beta1':.9,'adam_beta2':.999,'adam_epsilon':1e-8,'weight_decay':.01,'scheduler':'LambdaLR','scheduler_factor':1,'checkpoint_every_optimizer_steps':3}
    if not isinstance(c,dict) or set(c)!=set(want)|set(PINS)|{'forbidden'} or any(c.get(k)!=v for k,v in want.items()) or any(c.get(k)!=v for k,v in PINS.items()) or c.get('forbidden')!=['direct trainer','checkpoint optimizer resume','checkpoint scheduler resume','checkpoint RNG resume','checkpoint cursor resume']:raise FrozenContractError('training')
def policy(p):
    add={'topic_anchor':{'metric':'topic_anchored','minimum':.55,'minimum_delta':-.02},'fact_grounded_usage':{'metric':'viewer_fact_usage','minimum':.4,'minimum_delta':.1},'memory':{'metric':'memory_probe','minimum':.5,'minimum_delta':.15},'long_callback':{'metric':'long_callback','minimum':.5,'minimum_delta':.2},'complete_show_arc':{'metric':'complete_show_arc','minimum':.75,'minimum_delta':.2}}
    weights={'topic_anchor':.15,'fact_grounded_usage':.25,'memory_probe':.2,'long_callback':.2,'complete_show_arc':.2}; w=p.get('weighted_score',{}); s=p.get('selection',{}); o=p.get('operational_adoption',{})
    hard={'zero_violations':['transport','polite','invented_handle','privacy','localhost_exposure','external_provider_without_opt_in'],'perfect_rates':{'unknown_identity_safe':1.0,'donation_name_addressee_thanks_message_engagement_composite':1.0,'stale_transition_clean':1.0,'decoy_fact_use':0.0}}
    axes={'donation_callout':'donation_callout_correct','memory_probe':'memory_probe','topic_anchored':'topic_anchored','viewer_fact_usage':'viewer_fact_usage'}
    legacy={'donation_callout_correct':{'required_rate':1.0},'memory_probe':{'candidate_must_not_regress_vs_e2':True,'final_blind_minimum':.9},'topic_anchored':{'minimum_delta_vs_e2':-.02},'viewer_fact_usage':{'per_fixture_positive_delta_vs_e2':True,'final_blind_minimum_delta_vs_e2':.1},'all_fixture_roles_are_final_blind':True}
    selection={'unique_top_score_margin_strictly_greater_than':.02,'e2_c1_minimum_weighted_score_delta_vs_e2':.08,'e2_c1_minimum_improved_additive_axes':4,'exact_tie':'no_winner','any_failed_gate':'no_winner','fail_closed':True}
    imm={'after_results':['fixture','seed','threshold'],'mutation':'invalidates_result'}; operational={'always':False,'campaign_authorized_only_when':'unique_passing_winner','default':False}; completeness={'expected_reports':36,'required_fixture_count':3,'required_seed_count':4,'required_arm_count':3,'on_missing_or_duplicate':'fail_closed'}
    keys={'schema_version','status','report_completeness','hard_gates','retained_comparator_axes','legacy_comparator_gates','additive_candidate_gate_vs_e2','weighted_score','selection','result_immutability','operational_adoption'}
    if set(p)!=keys or set(w)!={'components','weights_sum','hard_gates_are_not_score_compensable'} or p.get('schema_version')!='airi.e2-c1-blind-metric-policy.v1' or p.get('status')!='frozen_pre_result' or p.get('report_completeness')!=completeness or p.get('hard_gates')!=hard or p.get('retained_comparator_axes')!=axes or p.get('legacy_comparator_gates')!=legacy or p.get('additive_candidate_gate_vs_e2')!=add or w.get('components')!=weights or w.get('weights_sum')!=1.0 or w.get('hard_gates_are_not_score_compensable') is not True or s!=selection or p.get('result_immutability')!=imm or o!=operational:raise FrozenContractError('policy')
def commitment(c,external):
    attest={'blind_bodies_sealed':True,'correction_data_path_disjoint':True,'old_public_fixture_reused':False,'old_report_selection_rationale_reused':False,'response_viewed':False,'thresholds_frozen':True}
    fs=c.get('fixtures'); mapping=[('identity_unknown_and_donation_ritual.json','identity_unknown_and_donation_ritual'),('long_continuity_and_stale_transition.json','long_continuity_and_stale_transition'),('factual_grounding_and_complete_show_arc.json','factual_grounding_and_complete_show_arc')]
    canonical={'algorithm':"utf-8 JSON: sort_keys=true, separators=(',', ':'), ensure_ascii=false",'canonicalization_schema_version':'airi.broadcast-sim-canonical-json.v1'}
    if set(c)!={'schema_version','root_id','fixture_schema_version','canonicalization','seeds','arms','expected_matrix_reports','fixtures','pre_result_attestation'} or c.get('schema_version')!='airi.e2-c1-blind-commitment.v1' or c.get('root_id')!='airi-e2-c1-blind-freeze-20260824-000430' or c.get('fixture_schema_version')!='airi.broadcast-sim-fixture.v1' or c.get('canonicalization')!=canonical or c.get('seeds')!=[73,89,97,20260824] or c.get('arms')!=['baseline','e2','e2-c1'] or c.get('expected_matrix_reports')!=36 or c.get('pre_result_attestation')!=attest or not isinstance(fs,list) or len(fs)!=3 or [(x.get('filename'),x.get('logical_role')) for x in fs]!=mapping:raise FrozenContractError('commitment')
    names=[]
    for f in fs:
        if set(f)!={'filename','logical_role','size_bytes','raw_sha256','canonical_sha256'} or not isinstance(f['filename'],str) or '/' in f['filename'] or '\\' in f['filename'] or not isinstance(f['size_bytes'],int) or f['size_bytes']<=0 or any(not isinstance(f[k],str) or len(f[k])!=64 or any(ch not in '0123456789abcdef' for ch in f[k]) for k in ('raw_sha256','canonical_sha256')):raise FrozenContractError('commitment fixture')
        names.append(f['filename'])
    if len(set(names))!=3:raise FrozenContractError('commitment fixture')
    if external:
        if external.is_symlink() or {x.name for x in external.iterdir()}!=set(names)|{'sealed_manifest.json','validation_receipt.json'}:raise FrozenContractError('blind inventory')
        for f in fs:
            raw=read(external/f['filename'])
            if len(raw)!=f['size_bytes'] or sha(raw)!=f['raw_sha256'] or sha(canon(json.loads(raw)))!=f['canonical_sha256']:raise FrozenContractError('blind hash')
        sealed=obj(external/'sealed_manifest.json');receipt=obj(external/'validation_receipt.json')
        if set(sealed)!={'schema_version','root_id','canonicalization','fixtures','response_viewed'} or sealed.get('schema_version')!='airi.e2-c1-blind-sealed-manifest.v1' or sealed.get('root_id')!=c['root_id'] or sealed.get('canonicalization')!=c['canonicalization']['algorithm'] or sealed.get('fixtures')!=fs or sealed.get('response_viewed') is not False:raise FrozenContractError('sealed manifest')
        validation=receipt.get('validation');attestation=receipt.get('attestation')
        required={'status':'PASS','fixture_schema_validator':c['fixture_schema_version'],'canonicalization':c['canonicalization']['algorithm'],'fixture_count':3,'seed_count':4,'arm_count':3,'expected_report_count':36,'public_raw_or_canonical_hash_collision':False,'body_output':False}
        if set(receipt)!={'schema_version','root_id','sealed_manifest_raw_sha256','validation','attestation'} or receipt.get('schema_version')!='airi.e2-c1-blind-validation-receipt.v1' or receipt.get('root_id')!=c['root_id'] or receipt.get('sealed_manifest_raw_sha256')!=sha(read(external/'sealed_manifest.json')) or validation!=required or attestation!=c['pre_result_attestation']:raise FrozenContractError('blind receipt')
def validate_replay(replay,v4,v):
    splits=replay.get('splits',{});ids=[i for s in SPLITS for i in splits.get(s,[])]
    families={'briefing_topic':35,'donation_isolation':30,'grounding':20,'memory_known':40,'memory_unknown':20,'natural_broadcast':15}
    source={'path':'airi_broadcast_continuity_v4.jsonl','sha256':PINS['v4_source_sha256'],'chat_sha256':PINS['v4_chat_sha256']}
    replay_keys={'schema_version','selected_ids','selection_seed','source','split_counts','splits','train_family_counts','version'}
    if set(replay)!=replay_keys or replay.get('schema_version')!='airi.broadcast-e2-c1-replay-manifest.v1' or replay.get('version')!=4 or replay.get('selection_seed')!=4201 or replay.get('source')!=source or set(splits)!=set(SPLITS) or replay.get('split_counts')!={'train':160,'dev':20,'test':20} or len(ids)!=200 or len(set(ids))!=200 or replay.get('selected_ids')!=ids or any(i not in v or v[i]['split']!=s for s in SPLITS for i in splits[s]) or replay.get('train_family_counts')!=families:raise FrozenContractError('replay')
    selected=set(ids)
    if any(any(y['id'] not in selected for y in v4 if y['scenario_group']==x['scenario_group']) for x in (v[i] for i in ids)) or {f:sum(v[i]['semantic_family']==f for i in splits['train']) for f in families}!=families:raise FrozenContractError('replay groups')
    return ids
def verify(repo_root=None,external_blind_root=None):
    root=(repo_root or Path(__file__).resolve().parents[2]).resolve(); t=root/'ollama-proxy/training'; p={k:t/v for k,v in FILES.items()}; source,sb=rows(p['correction']); chat,cb=rows(p['correction_chat']); mix,mb=rows(p['mixture']); mixchat,mcb=rows(p['mixture_chat']); man=obj(p['dataset']); rb=read(p['replay_manifest']); replay=json.loads(rb)
    manifest_keys={'counts','encoding','files','immutable_v4','line_endings','provenance','schema_version','selection_seed','trailing_newline','train_ratio','training_contract','training_input'}
    if set(man)!=manifest_keys or set(man.get('files',{}))!={'correction','correction_chat','mixture','mixture_chat','replay','replay_manifest'}:raise FrozenContractError('file inventory')
    for k,b in [('correction',sb),('correction_chat',cb),('mixture',mb),('mixture_chat',mcb),('replay_manifest',rb)]:receipt(man,k,b)
    if man.get('training_input')!={'path':'airi_broadcast_e2_c1_mixture_chat.jsonl','size':len(mcb),'sha256':sha(mcb)}:raise FrozenContractError('training input')
    expected_counts={'correction':{'train':352,'dev':64,'test':64},'replay':{'train':160,'dev':20,'test':20},'mixture':{'train':512,'dev':84,'test':84}}
    if man.get('schema_version')!='airi.broadcast-e2-c1-dataset-manifest.v1' or man.get('encoding')!='UTF-8' or man.get('line_endings')!='LF' or man.get('trailing_newline') is not True or man.get('selection_seed')!=4201 or man.get('counts')!=expected_counts or man.get('immutable_v4')!={'source_sha256':PINS['v4_source_sha256'],'chat_sha256':PINS['v4_chat_sha256']} or man.get('train_ratio')!={'correction':352,'replay':160,'ratio':'11:5'}:raise FrozenContractError('manifest')
    training(man); c=pair(source,chat); m=pair(mix,mixchat); semantics(source)
    if len(c)!=480 or len(m)!=680 or tuple(sum(x['split']==s for x in source) for s in SPLITS)!=(352,64,64) or tuple(sum(x['split']==s for x in mix) for s in SPLITS)!=(512,84,84):raise FrozenContractError('counts')
    gs={}
    for x in source:gs.setdefault(x['scenario_group'],[]).append(x)
    if len(gs)!=120 or any(len(v)!=4 or len({x['split'] for x in v})!=1 for v in gs.values()) or any(tuple(sum(x['semantic_family']==f and x['split']==s for x in source) for s in SPLITS)!=q for f,q in FAMILIES.items()):raise FrozenContractError('groups')
    v4,vb=rows(t/'seed/airi_broadcast_continuity_v4.jsonl');v4c,vcb=rows(t/'seed/airi_broadcast_continuity_v4_chat.jsonl')
    if sha(vb)!=PINS['v4_source_sha256'] or sha(vcb)!=PINS['v4_chat_sha256']:raise FrozenContractError('v4')
    v=pair(v4,v4c);ids=validate_replay(replay,v4,v);splits=replay['splits']
    derived=b''.join(json.dumps(v[i],sort_keys=True,ensure_ascii=False).encode()+b'\n' for i in ids);receipt(man,'replay',derived)
    provenance={**{i:'correction' for i in c},**{i:'replay' for i in ids}}
    if set(m)!=set(c)|set(ids) or man.get('provenance')!=provenance or any(m[i]!=(c[i] if i in c else v[i]) for i in m) or any(i in splits['dev']+splits['test'] for i,x in m.items() if x['split']=='train') or sum(i in c and x['split']=='train' for i,x in m.items())!=352 or sum(i in set(ids) and x['split']=='train' for i,x in m.items())!=160:raise FrozenContractError('mixture')
    policy(obj(t/'../eval/broadcast_sim/fixtures/commitments/airi_e2_c1_metric_policy.json'));commitment(obj(t/'../eval/broadcast_sim/fixtures/commitments/airi_e2_c1_blind_commitment.json'),external_blind_root)
    return {'status':'pass','counts':{'correction':480,'replay':200,'mixture':680},'hashes':{'mixture_chat':sha(mcb)}}
def run_cli(argv=None,output=None):
    q=argparse.ArgumentParser();q.add_argument('--repo-root',type=Path);q.add_argument('--external-blind-root',type=Path)
    try:r=verify(**vars(q.parse_args(argv)))
    except Exception:print('{"status":"fail"}',file=output or sys.stdout);return 2
    print(json.dumps(r,sort_keys=True,separators=(',',':')),file=output or sys.stdout);return 0
if __name__=='__main__':raise SystemExit(run_cli())
