import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from build_airi_ab_summary import *
from model_usage_manifest import canonical_sha256,validate_manifest
ROOT=Path(__file__).parent; MANIFESTS=sorted((ROOT/'model-usage-manifests').glob('*.json'))
def classes(): return {'schema_version':CLASSIFICATION_SCHEMA_VERSION,'rows':[{'candidate_id':json.loads(m.read_text())['candidate_id'],'profile':p,'stage':s,'status':'not_run','reason':'NOT_RUN'} for m in MANIFESTS for p in PROFILES for s in STAGES]}
class Tests(unittest.TestCase):
 def test_matrix_deterministic_and_pending_human(self):
  with tempfile.TemporaryDirectory() as d:
   x=build_summary(MANIFESTS,d,classes());self.assertEqual(60,len(x['rows']));self.assertTrue(x['p6_human_review_pending']);self.assertEqual(x,build_summary(list(reversed(MANIFESTS)),d,classes()))
 def test_missing_and_duplicate_classification_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   x=classes();x['rows'].pop()
   with self.assertRaises(ABSummaryValidationError):build_summary(MANIFESTS,d,x)
   x=classes();x['rows'].append(x['rows'][0])
   with self.assertRaises(ABSummaryValidationError):build_summary(MANIFESTS,d,x)
 def test_result_metrics_and_raw_text_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   m=MANIFESTS[0];doc=json.loads(m.read_text());c=doc['candidate_id']; result={'schema_version':RESULT_SCHEMA_VERSION,'candidate_id':c,'profile':'native','stage':'P0','manifest_file_sha256':hashlib.sha256(m.read_bytes()).hexdigest(),'manifest_canonical_sha256':canonical_sha256(validate_manifest(doc)),'runtime_digest':'abc','gate':True,'counts':{'case_count':2},'metrics':{'p50_ms':3}}
   Path(d,'a.json').write_text(json.dumps(result));x=classes();x['rows']=[r for r in x['rows'] if not(r['candidate_id']==c and r['profile']=='native' and r['stage']=='P0')];summary=build_summary(MANIFESTS,d,x);row=next(row for row in summary['rows'] if (row['candidate_id'],row['profile'],row['stage'])==(c,'native','P0'));self.assertEqual('actual',row['status']);self.assertEqual(3,row['metrics']['p50_ms'])
   result['metrics']={'raw_response':'bad'};Path(d,'a.json').write_text(json.dumps(result))
   with self.assertRaises(ABSummaryValidationError):build_summary(MANIFESTS,d,x)
if __name__=='__main__':unittest.main()
