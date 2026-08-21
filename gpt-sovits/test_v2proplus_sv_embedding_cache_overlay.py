from __future__ import annotations
import threading
import unittest
import numpy as np
from v2proplus_sv_embedding_cache_overlay import CacheContext, SpeakerEmbeddingCache, install_for_tts

class Tensor:
    def __init__(self, values):
        self.values=np.asarray(values,dtype=np.float16); self.shape=self.values.shape; self.dtype=self.values.dtype; self.device='cuda:0'; self._version=0
    def detach(self): return self
    def contiguous(self): return self
    def cpu(self): return self
    def numpy(self): return self.values
    def data_ptr(self): return self.values.__array_interface__['data'][0]

def ctx(**changes):
    values=dict(ref_audio_path='ref.wav',aux_ref_audio_paths=(),device='cuda:0',precision='torch.float16',model_identity=1); values.update(changes)
    return CacheContext(**values)

class CacheTests(unittest.TestCase):
    def test_fake_tts_hook_caches_repeat_without_changing_output(self):
        class Config: device='cuda:0'
        class Model:
            def __init__(self): self.calls=0
            def compute_embedding3(self, audio): self.calls+=1; return audio.values*5
        class FakeTTS:
            def __init__(self): self.configs=Config(); self.precision='torch.float16'; self.sv_model=Model()
            def set_ref_audio(self, path): self.ref=path
            def run(self, inputs): yield self.sv_model.compute_embedding3(Tensor([9]))
        install_for_tts(FakeTTS)
        tts=FakeTTS(); payload={'ref_audio_path':'ref.wav','aux_ref_audio_paths':[]}
        first=list(tts.run(payload)); second=list(tts.run(payload))
        self.assertEqual(tts.sv_model.calls,1); np.testing.assert_array_equal(first[0],second[0])

    def test_repeat_is_one_compute_and_equal_output(self):
        cache=SpeakerEmbeddingCache(); calls=[]; f=lambda x: calls.append(1) or x.values*3
        audio=Tensor([1,2]); first=cache.get_or_compute(ctx(),audio,f); second=cache.get_or_compute(ctx(),audio,f)
        self.assertEqual(len(calls),1); np.testing.assert_array_equal(first,second)
    def test_invalidation_axes(self):
        cache=SpeakerEmbeddingCache(); calls=[]; f=lambda x: calls.append(1) or x.values
        audio=Tensor([1]); cache.get_or_compute(ctx(),audio,f)
        for change in ({'ref_audio_path':'new.wav'},{'aux_ref_audio_paths':('a.wav',)},{'device':'cpu'},{'precision':'torch.float32'},{'model_identity':2}): cache.get_or_compute(ctx(**change),audio,f)
        cache.clear(); cache.get_or_compute(ctx(),audio,f); cache.get_or_compute(ctx(),Tensor([2]),f)
        self.assertEqual(len(calls),8)
    def test_concurrent_same_input_computes_once(self):
        cache=SpeakerEmbeddingCache(); calls=[]; gate=threading.Barrier(8)
        audio=Tensor([7])
        def worker(): gate.wait(); cache.get_or_compute(ctx(),audio,lambda x: calls.append(1) or x.values)
        threads=[threading.Thread(target=worker) for _ in range(8)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(len(calls),1)

if __name__=='__main__': unittest.main()
