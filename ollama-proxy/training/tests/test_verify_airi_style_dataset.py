"""Regression tests only; training is never invoked."""
import json, sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_airi_style_dataset import CATEGORY_TAXONOMY, GateError, canonical_sha256, prompt_sha256, sha256_file, verify_reviewed_dataset
from validate_airi_style_pending import validate_decisions, validate_pending_dataset
from train_airi_style_qlora import TrainingRefused, _assert_train_rows
def row(i,split,category): return {"id":f"style-{i:03d}","split":split,"category":category,"prompt":f"주제 {i}을 말해줘","answer":"좋아 핵심만 말할게","partition":{"tier":"S1","group":f"reviewed-{i:03d}"},"review":{"status":"approved","reviewer":"reviewer-alex","approved_at":"2026-08-08T00:00:00Z"},"provenance":{"synthetic":True,"source":"curated-synthetic"},"training_eligible":True}
def fixture(tier):
 p=f"fixture {tier} 확인";a="확인했어";return {"schema_version":1,"suite_id":"airi-c0-s1-evaluation","suite_version":"1.0","tier":tier,"case_id":f"{tier.lower()}-case-001","group":f"{tier.lower()}-holdout-001","prompt":p,"answer":a,"prompt_sha256":prompt_sha256(p),"example_sha256":canonical_sha256({"prompt":p,"answer":a})}
def bundle(t):
 rows=[row(i,"train" if i<160 else "dev" if i<180 else "test",CATEGORY_TAXONOMY[i%6]) for i in range(200)];d=t/"reviewed.jsonl";d.write_text("\n".join(json.dumps(x,ensure_ascii=False) for x in rows)+"\n",encoding="utf8")
 m=t/"manifest.json";m.write_text(json.dumps({"schema_version":3,"policy_version":"airi-style-qlora/v3","dataset_sha256":sha256_file(d),"human_approved":True,"approved_by":"reviewer-alex","approved_at":"2026-08-08T00:00:00Z","reviewed_record_count":200,"categories":list(CATEGORY_TAXONOMY),"reviewer_provenance":{"review_program":"independent-review","dataset_author":"author-kim","fixture_owner":"fixture-lee","independent_review":True,"reviewers":[{"id":"reviewer-alex","role":"senior-reviewer","affiliation":"quality-team"}]}},ensure_ascii=False),encoding="utf8");c=t/"c0.jsonl";s=t/"s1.jsonl";c.write_text(json.dumps(fixture("C0"))+"\n");s.write_text(json.dumps(fixture("S1"))+"\n");return rows,d,m,c,s
def test_production_v3_shape_balance_split_and_s1_only(tmp_path):
 _,d,m,c,s=bundle(tmp_path);r=verify_reviewed_dataset(d,m,c,s);assert r.report_payload["splits"]=={"dev":20,"test":20,"train":160}
def test_production_rejects_pending_and_c0(tmp_path):
 rows,d,m,c,s=bundle(tmp_path);rows[0]["review"]["status"]="pending";d.write_text("\n".join(json.dumps(x) for x in rows));
 with pytest.raises(GateError):verify_reviewed_dataset(d,m,c,s)
 rows[0]["review"]["status"]="approved";rows[0]["partition"]["tier"]="C0";d.write_text("\n".join(json.dumps(x) for x in rows))
 manifest=json.loads(m.read_text(encoding="utf8"));manifest["dataset_sha256"]=sha256_file(d);m.write_text(json.dumps(manifest),encoding="utf8")
 with pytest.raises(GateError,match="S1"):verify_reviewed_dataset(d,m,c,s)
def test_pending_seed_passes_pending_gate_while_production_and_trainer_reject():
 p=Path(__file__).resolve().parents[1]/"seed"/"airi_style_seed_pending.jsonl";assert validate_pending_dataset(p)["record_count"]==200
 with pytest.raises(GateError):verify_reviewed_dataset(p,p,p,p)
 rows=[json.loads(x) for x in p.read_text(encoding="utf8").splitlines()]
 with pytest.raises(TrainingRefused):_assert_train_rows((rows[0],))
def test_pending_rejects_approved_eligible_duplicate_private_and_questions(tmp_path):
 p=Path(__file__).resolve().parents[1]/"seed"/"airi_style_seed_pending.jsonl";rows=[json.loads(x) for x in p.read_text(encoding="utf8").splitlines()];bad=tmp_path/"bad.jsonl"
 rows[0]["review"]["status"]="approved";bad.write_text("\n".join(json.dumps(x) for x in rows));
 with pytest.raises(GateError):validate_pending_dataset(bad)
 rows[0]["review"]={"status":"pending","reviewer":"","approved_at":""};rows[1]["id"]=rows[0]["id"];bad.write_text("\n".join(json.dumps(x) for x in rows));
 with pytest.raises(GateError,match="duplicate"):validate_pending_dataset(bad)
 rows[1]["id"]="seed-002";rows[1]["prompt"]="a@b.com";bad.write_text("\n".join(json.dumps(x) for x in rows));
 with pytest.raises(GateError):validate_pending_dataset(bad)
 rows[1]["prompt"]="그냥 말해";
 for i,x in enumerate(rows[:11]):x["answer"]=f"구체적으로 어떤 장면이었어 {i}?"
 bad.write_text("\n".join(json.dumps(x) for x in rows));
 with pytest.raises(GateError,match="exceed"):validate_pending_dataset(bad)

def test_decision_approval_requires_voice_no_counselor_tone_and_safety(tmp_path):
 p=Path(__file__).resolve().parents[1]/"seed"/"airi_style_seed_pending.jsonl";rows=[json.loads(x) for x in p.read_text(encoding="utf8").splitlines()]
 decision={"id":rows[0]["id"],"decision":"approve","vtuber_voice":True,"counselor_tone":False,"safety_truth":True,"notes":"independent review","reviewer":"reviewer-alex","reviewed_at":"2026-08-09T00:00:00Z"}
 sidecar=tmp_path/"decisions.jsonl";sidecar.write_text(json.dumps(decision,ensure_ascii=False)+"\n",encoding="utf8");validate_decisions(sidecar,{rows[0]["id"]})
 decision["counselor_tone"]=True;sidecar.write_text(json.dumps(decision,ensure_ascii=False)+"\n",encoding="utf8")
 with pytest.raises(GateError,match="approval requires"):validate_decisions(sidecar,{rows[0]["id"]})
