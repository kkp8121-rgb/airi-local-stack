import unittest
from monitor_server import Correlator, validate

def event(source, phase, request_id, stamp): return {"source": source, "phase": phase, "request_id": request_id, "timestamp_ms": stamp}

class CorrelationTests(unittest.TestCase):
    def test_half_duplex_different_request_ids_join_one_turn(self):
        c = Correlator()
        for e in [event("stt", "start", "s1", 100), event("stt", "end", "s1", 200), event("llm", "start", "l1", 220), event("llm", "first", "l1", 300), event("tts", "start", "t1", 310), event("tts", "first", "t1", 390), event("tts", "end", "t1", 480)]: self.assertTrue(c.add(e))
        t = c.snapshot()[0]
        self.assertEqual((t["stt"]["end"], t["llm"]["first"], t["tts"]["first"]), (200, 300, 390))
        self.assertEqual(t["tts"]["segments"], 1)

    def test_tts_segments_and_new_stt_turn(self):
        c = Correlator()
        for e in [event("stt","start","s1",1),event("llm","start","l1",2),event("tts","start","t1",3),event("tts","start","t2",4),event("stt","start","s2",10)]: c.add(e)
        turns=c.snapshot()
        self.assertEqual(len(turns),2); self.assertEqual(turns[1]["tts"]["segments"],2); self.assertEqual(turns[0]["turn_id"],"s2")

    def test_tts_keeps_earliest_first_audio_and_merges_numeric_meta(self):
        c = Correlator()
        events = [
            {**event("stt", "start", "s1", 1), "meta": {"audio_bytes": 10}},
            {**event("stt", "end", "s1", 2), "meta": {"inference_ms": 7}},
            event("llm", "start", "l1", 3),
            event("tts", "start", "t1", 4),
            {**event("tts", "first", "t1", 5), "meta": {"lock_wait_ms": 0}},
            event("tts", "start", "t2", 6),
            event("tts", "first", "t2", 9),
            event("tts", "end", "t2", 12),
        ]
        for item in events:
            self.assertTrue(c.add(item))
        turn = c.snapshot()[0]
        self.assertEqual(turn["tts"]["first"], 5)
        self.assertEqual(turn["tts"]["segments"], 2)
        self.assertEqual(turn["stt"]["meta"], {"audio_bytes": 10, "inference_ms": 7})

    def test_rejects_raw_content_but_keeps_safe_meta(self):
        self.assertIsNone(validate({"source":"stt","phase":"start","request_id":"x","text":"secret"}))
        c=Correlator(); c.add(validate({"source":"stt","phase":"start","request_id":"x","meta":{"frames":3,"voice":True,"text":"secret"}}))
        self.assertEqual(c.snapshot()[0]["stt"]["meta"], {"frames":3,"voice":True})

if __name__ == "__main__": unittest.main()
