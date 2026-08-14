from __future__ import annotations
import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from run_airi_candidate_proxy_ab import ProbeError, run_ab
HERE=Path(__file__).parent; DIGEST="d"*64
class Fake:
 def __init__(self, good=True): self.calls=[]; self.good=good
 def __call__(self,m,u,p,h):
  self.calls.append((m,u,p,h))
  if u.endswith('/health'): return {"chat_model":{"model":"candidate:test" if self.good else "wrong"},"num_ctx":2048,"ollama_sampling_defaults":{"temperature":.45,"top_p":.9,"repeat_penalty":1.05},"memory":{"enabled":False},"knowledge":{"enabled":False},"evaluation":{"enabled":False},"character_state_evaluator":{"enabled":False},"output_moderation":{"enabled":False}}
  if u.endswith('/api/tags'): return {"models":[{"name":"candidate:test","digest":DIGEST}]}
  return [b'data: {"choices":[{"delta":{"content":"fine"}}]}\n\n',b'data: [DONE]\n\n']
class Tests(unittest.TestCase):
 def manifest(self,d):
  p=d/'m.json';p.write_bytes((HERE/'model-usage-manifests'/'qwen3-4b.json').read_bytes());return p
 def test_120_content_free_order_headers(self):
  with tempfile.TemporaryDirectory() as x:
   d=Path(x);f=Fake();r=run_ab(manifest_path=self.manifest(d),model='candidate:test',expected_digest=DIGEST,report_path=d/'r.json',transport=f); raw=(d/'r.json').read_text(); posts=[v for v in f.calls if v[1].endswith('completions')]
   self.assertEqual(r['status'],'complete');self.assertEqual(len(posts),120);self.assertEqual([r['turns'][0]['order'],r['turns'][6]['order']],['A->B','B->A']);self.assertEqual([r['turns'][0]['case_id'],r['turns'][6]['case_id']],['meal_recommendation','second_person_question']);self.assertTrue(all(v[2]['stream'] and v[3]['X-AIRI-Turn-Origin']=='local-quality-probe' for v in posts));self.assertNotIn('fine',raw)
 def test_unverifiable_binding_fails_closed(self):
  with tempfile.TemporaryDirectory() as x:
   d=Path(x);r=run_ab(manifest_path=self.manifest(d),model='candidate:test',expected_digest=DIGEST,report_path=d/'r.json',transport=Fake(False));self.assertEqual(r['status'],'error')
 def test_external_proxy_is_rejected(self):
  with tempfile.TemporaryDirectory() as x:
   with self.assertRaises(ProbeError):run_ab(manifest_path=self.manifest(Path(x)),model='candidate:test',expected_digest=DIGEST,report_path=Path(x)/'r.json',proxy_endpoint='http://example.com/v1/chat/completions',transport=Fake())
if __name__=='__main__':unittest.main()
