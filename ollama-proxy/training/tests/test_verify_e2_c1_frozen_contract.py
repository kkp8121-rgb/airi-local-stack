import sys
import hashlib
import importlib.util
import json
import tempfile
import copy
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))
import verify_e2_c1_frozen_contract as frozen

def rendered_source():
    spec=importlib.util.spec_from_file_location('e2_c1_semantic_fixture',HERE/'synthesize_broadcast_e2_c1.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    return module.build_correction()

def row(ident='x',split='train',target='answer'):
    return {'id':ident,'split':split,'scenario_group':'g','semantic_family':'identity_noninvention','messages':[{'role':'user','content':'q'},{'role':'assistant','content':target}],'target':target}

class FrozenContractTests(unittest.TestCase):
    def test_semantic_and_korean_grammar_mutations_fail_closed(self):
        source=rendered_source()
        frozen.semantics(source)
        unknown=copy.deepcopy(source)
        row=next(x for x in unknown if x['semantic_family']=='unknown_identity')
        row['target']=row['required_token'];row['messages'][-1]['content']=row['target']
        with self.assertRaisesRegex(frozen.FrozenContractError,'identity safety'):frozen.semantics(unknown)
        donation=copy.deepcopy(source)
        row=next(x for x in donation if x['semantic_family']=='donation_ritual')
        row['target']=row['target'].replace('고마워','반가워');row['messages'][-1]['content']=row['target']
        with self.assertRaisesRegex(frozen.FrozenContractError,'donation semantics'):frozen.semantics(donation)
        factual=copy.deepcopy(source)
        row=next(x for x in factual if x['semantic_family']=='factual_grounding')
        row['target']+=' '+row['decoy_tokens'][0];row['messages'][-1]['content']=row['target']
        with self.assertRaisesRegex(frozen.FrozenContractError,'semantic metadata'):frozen.semantics(factual)
        grammar=copy.deepcopy(source);grammar[0]['messages'][-2]['content']+=' “간식”는'
        with self.assertRaisesRegex(frozen.FrozenContractError,'quoted josa'):frozen.semantics(grammar)
        self.assertEqual(frozen.josa('바다',('으로','로')),'로')
        self.assertEqual(frozen.josa('길',('으로','로')),'로')
        self.assertEqual(frozen.josa('구름',('으로','로')),'으로')
        grammar=copy.deepcopy(source);grammar[0]['messages'][-2]['content']+=' “구름”로'
        with self.assertRaisesRegex(frozen.FrozenContractError,'quoted josa'):frozen.semantics(grammar)
        grammar=copy.deepcopy(source);grammar[0]['messages'][-2]['content']+=' “길”으로'
        with self.assertRaisesRegex(frozen.FrozenContractError,'quoted josa'):frozen.semantics(grammar)

    def test_source_chat_pair_requires_exact_metadata_and_target(self):
        source=row();chat={k:v for k,v in source.items() if k!='target'}
        self.assertEqual(frozen.pair([source],[chat])['x'],source)
        chat['split']='dev'
        with self.assertRaises(frozen.FrozenContractError):frozen.pair([source],[chat])
        chat['split']='train';source['target']='other'
        with self.assertRaises(frozen.FrozenContractError):frozen.pair([source],[chat])
        source['target']='answer'; chat=copy.deepcopy(chat); chat['messages'][0]['content']='tampered metadata-free message'
        with self.assertRaises(frozen.FrozenContractError):frozen.pair([source],[chat])
    def test_replay_and_receipt_fault_primitives_fail_closed(self):
        with self.assertRaises(frozen.FrozenContractError):frozen.receipt({'files':{'replay':{'size':1,'sha256':'0'*64}}},'replay',b'xx')
        with self.assertRaises(frozen.FrozenContractError):frozen.receipt({'files':{'replay':{'size':2,'sha256':hashlib.sha256(b'xx').hexdigest(),'extra':True}}},'replay',b'xx')
        with self.assertRaises(frozen.FrozenContractError):frozen.assistant({'messages':[{'role':'user','content':'q'}]})
    def test_replay_order_split_group_source_and_family_mutations_fail_closed(self):
        families={'briefing_topic':35,'donation_isolation':30,'grounding':20,'memory_known':40,'memory_unknown':20,'natural_broadcast':15}
        rows=[]
        for family,count in families.items():
            for index in range(count):
                rows.append({'id':f'train-{family}-{index}','split':'train','scenario_group':f'train-{family}-{index}','semantic_family':family})
        for split in ('dev','test'):
            for index in range(20):
                rows.append({'id':f'{split}-{index}','split':split,'scenario_group':f'{split}-{index}','semantic_family':'briefing_topic'})
        by_id={item['id']:item for item in rows}
        splits={split:[item['id'] for item in rows if item['split']==split] for split in frozen.SPLITS}
        replay={'schema_version':'airi.broadcast-e2-c1-replay-manifest.v1','version':4,'selection_seed':4201,
                'source':{'path':'airi_broadcast_continuity_v4.jsonl','sha256':frozen.PINS['v4_source_sha256'],'chat_sha256':frozen.PINS['v4_chat_sha256']},
                'split_counts':{'train':160,'dev':20,'test':20},'train_family_counts':families,
                'selected_ids':[ident for split in frozen.SPLITS for ident in splits[split]],'splits':splits}
        self.assertEqual(frozen.validate_replay(replay,rows,by_id),replay['selected_ids'])
        wrong_order=copy.deepcopy(replay);wrong_order['selected_ids'][:2]=reversed(wrong_order['selected_ids'][:2])
        with self.assertRaises(frozen.FrozenContractError):frozen.validate_replay(wrong_order,rows,by_id)
        wrong_split=copy.deepcopy(replay);wrong_split['splits']['train'][0],wrong_split['splits']['dev'][0]=wrong_split['splits']['dev'][0],wrong_split['splits']['train'][0];wrong_split['selected_ids']=[ident for split in frozen.SPLITS for ident in wrong_split['splits'][split]]
        with self.assertRaises(frozen.FrozenContractError):frozen.validate_replay(wrong_split,rows,by_id)
        partial=copy.deepcopy(rows);partial.append({'id':'unselected-sibling','split':'train','scenario_group':rows[0]['scenario_group'],'semantic_family':rows[0]['semantic_family']})
        with self.assertRaises(frozen.FrozenContractError):frozen.validate_replay(replay,partial,{item['id']:item for item in partial})
        wrong_source=copy.deepcopy(replay);wrong_source['source']['sha256']='0'*64
        with self.assertRaises(frozen.FrozenContractError):frozen.validate_replay(wrong_source,rows,by_id)
        wrong_family=copy.deepcopy(replay);wrong_family['train_family_counts']['briefing_topic']+=1
        with self.assertRaises(frozen.FrozenContractError):frozen.validate_replay(wrong_family,rows,by_id)
    def test_policy_mutations_are_rejected(self):
        good={'schema_version':'airi.e2-c1-blind-metric-policy.v1','status':'frozen_pre_result','additive_candidate_gate_vs_e2':{'topic_anchor':{'metric':'topic_anchored','minimum':.55,'minimum_delta':-.02},'fact_grounded_usage':{'metric':'viewer_fact_usage','minimum':.4,'minimum_delta':.1},'memory':{'metric':'memory_probe','minimum':.5,'minimum_delta':.15},'long_callback':{'metric':'long_callback','minimum':.5,'minimum_delta':.2},'complete_show_arc':{'metric':'complete_show_arc','minimum':.75,'minimum_delta':.2}},'weighted_score':{'components':{'topic_anchor':.15,'fact_grounded_usage':.25,'memory_probe':.2,'long_callback':.2,'complete_show_arc':.2},'weights_sum':1.0,'hard_gates_are_not_score_compensable':True},'selection':{'unique_top_score_margin_strictly_greater_than':.02,'e2_c1_minimum_weighted_score_delta_vs_e2':.08,'e2_c1_minimum_improved_additive_axes':4},'operational_adoption':{'always':False,'default':False}}
        with self.assertRaises(frozen.FrozenContractError):frozen.policy(good)
        with self.assertRaises(frozen.FrozenContractError):frozen.policy({'hard_gates':{}})
    def test_sealed_manifest_and_receipt_bindings_fail_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); fixtures=[]
            mapping=[('identity_unknown_and_donation_ritual.json','identity_unknown_and_donation_ritual'),('long_continuity_and_stale_transition.json','long_continuity_and_stale_transition'),('factual_grounding_and_complete_show_arc.json','factual_grounding_and_complete_show_arc')]
            for i,(name,role) in enumerate(mapping):
                body={'schema':'fixture','id':i}; data=json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode();(root/name).write_bytes(data)
                fixtures.append({'filename':name,'logical_role':role,'size_bytes':len(data),'raw_sha256':hashlib.sha256(data).hexdigest(),'canonical_sha256':hashlib.sha256(frozen.canon(body)).hexdigest()})
            att={'blind_bodies_sealed':True,'correction_data_path_disjoint':True,'old_public_fixture_reused':False,'old_report_selection_rationale_reused':False,'response_viewed':False,'thresholds_frozen':True}
            commit={'schema_version':'airi.e2-c1-blind-commitment.v1','root_id':'airi-e2-c1-blind-freeze-20260824-000430','fixture_schema_version':'airi.broadcast-sim-fixture.v1','canonicalization':{'algorithm':"utf-8 JSON: sort_keys=true, separators=(',', ':'), ensure_ascii=false",'canonicalization_schema_version':'airi.broadcast-sim-canonical-json.v1'},'seeds':[73,89,97,20260824],'arms':['baseline','e2','e2-c1'],'expected_matrix_reports':36,'fixtures':fixtures,'pre_result_attestation':att}
            sealed={'schema_version':'airi.e2-c1-blind-sealed-manifest.v1','root_id':commit['root_id'],'canonicalization':commit['canonicalization']['algorithm'],'fixtures':fixtures,'response_viewed':False}; sealed_bytes=json.dumps(sealed).encode();(root/'sealed_manifest.json').write_bytes(sealed_bytes)
            receipt={'schema_version':'airi.e2-c1-blind-validation-receipt.v1','root_id':commit['root_id'],'sealed_manifest_raw_sha256':hashlib.sha256(sealed_bytes).hexdigest(),'validation':{'status':'PASS','fixture_schema_validator':'airi.broadcast-sim-fixture.v1','canonicalization':commit['canonicalization']['algorithm'],'fixture_count':3,'seed_count':4,'arm_count':3,'expected_report_count':36,'public_raw_or_canonical_hash_collision':False,'body_output':False},'attestation':att};(root/'validation_receipt.json').write_text(json.dumps(receipt))
            frozen.commitment(commit,root)
            receipt['validation']['status']='FAIL';(root/'validation_receipt.json').write_text(json.dumps(receipt))
            with self.assertRaises(frozen.FrozenContractError):frozen.commitment(commit,root)
            receipt['validation']['status']='PASS';receipt['extra']=True;(root/'validation_receipt.json').write_text(json.dumps(receipt))
            with self.assertRaises(frozen.FrozenContractError):frozen.commitment(commit,root)
if __name__=='__main__':unittest.main()
