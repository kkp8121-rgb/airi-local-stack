import json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent));import build_airi_combined_intelligence_review_packet as builder
ROOT=Path(__file__).parent;FIXTURE=ROOT/'airi_broadcast_intelligence_cases.json'
class Tests(unittest.TestCase):
 def files(self,d):
  ids=builder.fixture_ids(FIXTURE);paths=[]
  for c in builder.REQUIRED:
   p=Path(d)/(c+'.json');p.write_text(json.dumps({'schema_version':builder.RAW_SCHEMA,'candidate_id':c,'profile':'common','rows':[{'case_id':i,'prompt':'안녕','response':'반가워'} for i in ids]}),encoding='utf-8');paths.append(p)
  return paths
 def test_five_by_twelve_blind_and_deterministic(self):
  with tempfile.TemporaryDirectory() as d:
   p,k=builder.build(self.files(d),FIXTURE,'seed');again=builder.build(list(reversed(self.files(d))),FIXTURE,'seed')[0]
  self.assertEqual(p,again);self.assertEqual(5,len(p['samples']));self.assertTrue(all(len(x['dialogue'])==12 for x in p['samples']));self.assertNotIn('candidate_id',json.dumps(p));self.assertNotIn('prompt',json.dumps(k));self.assertIn('candidate_id',json.dumps(k))
 def test_rejects_missing_or_wrong_case_set(self):
  with tempfile.TemporaryDirectory() as d:
   paths=self.files(d);x=json.loads(paths[0].read_text());x['rows'].pop();paths[0].write_text(json.dumps(x))
   with self.assertRaises(builder.PacketError):builder.build(paths,FIXTURE,'seed')
if __name__=='__main__':unittest.main()
