import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent));import build_airi_final_actual_results as b
ROOT=Path(__file__).parent;M=sorted((ROOT/'model-usage-manifests').glob('*.json'))
def index(path='unknown'):
 c=json.loads(M[0].read_text())['candidate_id'];return {'schema_version':b.INDEX_SCHEMA,'rows':[{'candidate_id':c,'profile':'common','stage':'P7','kind':'actual','status':'complete','reason':'','report_path':path}]}
class Tests(unittest.TestCase):
 def test_deterministic_unknown_separate_benchmark(self):
  x=b.build(M,index());self.assertEqual('unknown',x['rows'][0]['developer_benchmark']);self.assertEqual(x,b.build(list(reversed(M)),index()))
 def test_p6_rejects_dialogue_and_counts_safe_packet(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'p.json';p.write_text(json.dumps({'samples':[{'status':'actually_run','rubric':{'helpfulness':''}}]}));q=index(str(p));q['rows'][0]['stage']='P6';x=b.build(M,q);self.assertEqual(1,x['rows'][0]['report']['p6_sample_count'])
   p.write_text(json.dumps({'samples':[{'dialogue':[]}]}))
   with self.assertRaises(b.FinalResultsError):b.build(M,q)
 def test_raw_report_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'r.json';p.write_text(json.dumps({'raw_response':'x'}))
   with self.assertRaises(b.FinalResultsError):b.build(M,index(str(p)))
if __name__=='__main__':unittest.main()
