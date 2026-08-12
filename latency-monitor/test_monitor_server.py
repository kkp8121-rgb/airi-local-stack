import unittest
from pathlib import Path
from monitor_server import Correlator, LocalBroadcastProofs, validate, validate_local_broadcast_proof

def event(source, phase, request_id, stamp): return {"source": source, "phase": phase, "request_id": request_id, "timestamp_ms": stamp}

class CorrelationTests(unittest.TestCase):
    def test_text_only_llm_start_creates_an_explicit_content_free_turn(self):
        c = Correlator()
        self.assertTrue(c.add(event("llm", "start", "text-turn", 100)))
        self.assertTrue(c.add(event("llm", "raw_content", "text-turn", 180)))
        self.assertTrue(c.add(event("llm", "content", "text-turn", 220)))
        turn = c.snapshot()[0]
        self.assertEqual(turn["stt"], {})
        self.assertEqual(turn["llm"]["raw_content"], 180)
        self.assertEqual(turn["llm"]["content"], 220)
        self.assertEqual(turn["correlation"]["llm"], "explicit")

    def test_consecutive_text_only_llm_starts_create_distinct_turns(self):
        c = Correlator()
        for item in [
            event("llm", "start", "text-1", 100),
            event("llm", "content", "text-1", 150),
            event("llm", "end", "text-1", 160),
            event("llm", "start", "text-2", 200),
            event("llm", "raw_content", "text-2", 240),
        ]:
            self.assertTrue(c.add(item))
        turns = c.snapshot()
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["llm"]["start"], 200)
        self.assertEqual(turns[0]["llm"]["raw_content"], 240)
        self.assertEqual(turns[0]["correlation"]["llm"], "explicit")

    def test_local_broadcast_proof_is_content_free_strict_and_bounded(self):
        payload = {
            "schema_version": 1,
            "source": "local-proactive-broadcast",
            "phase": "playback-completed",
            "completion_count": 2,
        }
        proof = validate_local_broadcast_proof(payload)
        self.assertEqual(proof, payload)
        self.assertIsNone(validate_local_broadcast_proof({**payload, "text": "secret"}))
        self.assertIsNone(validate_local_broadcast_proof({**payload, "request_id": "secret"}))
        self.assertIsNone(validate_local_broadcast_proof({**payload, "completion_count": True}))

        store = LocalBroadcastProofs(limit=2)
        store.add({**payload, "completion_count": 1})
        store.add(payload)
        store.add({**payload, "completion_count": 3})
        snapshot = store.snapshot()
        self.assertEqual(snapshot["accepted_events"], 2)
        self.assertEqual(snapshot["latest_completion_count"], 3)
        self.assertEqual([event["completion_count"] for event in snapshot["events"]], [3, 2])
        self.assertEqual(set(snapshot["events"][0]), {"received_ms", "completion_count"})
        self.assertEqual(snapshot["incomplete_events"], 0)
        self.assertIsNone(snapshot["latest_incomplete"])

        incomplete = {
            "schema_version": 1,
            "source": "local-proactive-broadcast",
            "phase": "playback-incomplete",
            "attempt_count": 4,
            "failure_code": "pipeline-incomplete",
            "tts_requests": 2,
            "successful_tts_results": 2,
            "natural_playback_ends": 1,
        }
        self.assertEqual(validate_local_broadcast_proof(incomplete), incomplete)
        self.assertIsNone(validate_local_broadcast_proof({**incomplete, "text": "secret"}))
        self.assertIsNone(validate_local_broadcast_proof({**incomplete, "failure_code": "secret"}))
        store.add(incomplete)
        diagnostic = store.snapshot()
        self.assertEqual(diagnostic["incomplete_events"], 1)
        self.assertEqual(
            set(diagnostic["latest_incomplete"]),
            {"received_ms", "attempt_count", "failure_code", "tts_requests", "successful_tts_results", "natural_playback_ends"},
        )

    def test_dashboard_renders_memory_timing_only(self):
        dashboard = (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("--memory", dashboard)
        self.assertIn("Memory retrieve", dashboard)
        self.assertIn("Memory extract", dashboard)
        self.assertNotIn("memory.content", dashboard)
        self.assertNotIn("memory.raw", dashboard)

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

    def test_playback_keeps_first_actual_start(self):
        c = Correlator()
        for item in [
            event("stt", "start", "s1", 100),
            event("tts", "start", "t1", 300),
            event("playback", "start", "p1", 420),
            event("playback", "start", "p1", 900),
        ]:
            self.assertTrue(c.add(item))

        self.assertEqual(c.snapshot()[0]["playback"]["start"], 420)

    def test_ack_and_substantive_audio_kpis_are_separate(self):
        c = Correlator()
        for item in [
            event("stt", "start", "turn-1", 100),
            event("llm", "start", "turn-1", 110),
            event("llm", "first", "turn-1", 120),
            event("tts", "first", "turn-1", 130),
            event("playback", "start", "turn-1", 140),
            event("llm", "content", "turn-1", 200),
            event("tts", "first", "turn-1", 230),
            event("playback", "start", "turn-1", 240),
        ]:
            self.assertTrue(c.add(item))
        kpi = c.snapshot()[0]["kpi"]
        self.assertEqual(kpi["ack_tts_first"], 130)
        self.assertEqual(kpi["ack_playback_start"], 140)
        self.assertEqual(kpi["substantive_tts_first"], 230)
        self.assertEqual(kpi["substantive_playback_start"], 240)

    def test_llm_content_keeps_first_boundary_delta_and_latest_diagnostic(self):
        c = Correlator()
        for item in [
            event("stt", "start", "turn-1", 100),
            event("llm", "raw_content", "turn-1", 180),
            event("llm", "content", "turn-1", 200),
            event("llm", "content", "turn-1", 260),
        ]:
            self.assertTrue(c.add(item))
        llm = c.snapshot()[0]["llm"]
        self.assertEqual(llm["raw_content"], 180)
        self.assertEqual(llm["content"], 200)
        self.assertEqual(llm["content_last"], 260)

    def test_substantive_kpis_fail_closed_for_heuristic_or_unmatched_ids(self):
        c = Correlator()
        self.assertTrue(c.add(event("stt", "start", "turn-1", 100)))
        # This LLM ID is only associated by the legacy recency heuristic.
        self.assertTrue(c.add(event("llm", "content", "llm-1", 200)))
        self.assertTrue(c.add(event("tts", "first", "tts-1", 230)))
        self.assertTrue(c.add(event("playback", "start", "play-1", 240)))
        turn = c.snapshot()[0]
        self.assertEqual(turn["kpi"], {})
        self.assertEqual(turn["correlation"], {
            "stt": "explicit", "llm": "heuristic", "tts": "heuristic",
            "playback": "heuristic",
        })
        self.assertEqual(
            turn["tts"]["timeline"],
            [{"phase": "first", "timestamp_ms": 230, "correlation": "heuristic"}],
        )
        self.assertEqual(
            turn["playback"]["timeline"],
            [{"phase": "start", "timestamp_ms": 240, "correlation": "heuristic"}],
        )

        other = Correlator()
        self.assertFalse(other.add(event("tts", "first", "orphan", 1)))

    def test_heuristic_request_id_never_becomes_explicit_on_reuse(self):
        c = Correlator()
        self.assertTrue(c.add(event("stt", "start", "turn-1", 100)))
        self.assertTrue(c.add(event("llm", "content", "llm-1", 200)))
        # Reusing the same heuristically attached ID must not upgrade its
        # provenance or make a substantive KPI eligible.
        self.assertTrue(c.add(event("tts", "first", "llm-1", 230)))
        turn = c.snapshot()[0]
        self.assertEqual(turn["correlation"]["tts"], "heuristic")
        self.assertNotIn("substantive_tts_first", turn["kpi"])

    def test_audio_timeline_is_numeric_only_and_bounded(self):
        c = Correlator()
        self.assertTrue(c.add(event("stt", "start", "turn-1", 1)))
        for stamp in range(2, 72):
            self.assertTrue(c.add(event("tts", "first", f"tts-{stamp}", stamp)))
        timeline = c.snapshot()[0]["tts"]["timeline"]
        self.assertEqual(len(timeline), 64)
        self.assertEqual(timeline[0]["timestamp_ms"], 8)
        self.assertEqual(set(timeline[0]), {"phase", "timestamp_ms", "correlation"})

    def test_memory_retrieval_and_extraction_share_the_turn_without_raw_content(self):
        c = Correlator()
        events = [
            event("stt", "start", "turn-1", 100),
            event("llm", "start", "turn-1", 200),
            {**event("memory", "retrieve_start", "turn-1", 210), "meta": {"cache_hit": False}},
            {
                **event("memory", "retrieve_end", "turn-1", 240),
                "duration_ms": 30,
                "meta": {"entity_hits": 1, "memory_text": "must not persist"},
            },
            event("memory", "extract_start", "turn-1", 400),
            {
                **event("memory", "extract_end", "turn-1", 450),
                "meta": {"extract_items": 2, "watermark_advanced": True},
            },
        ]
        for item in events:
            self.assertTrue(c.add(item))

        memory = c.snapshot()[0]["memory"]
        self.assertEqual(memory["retrieve_start"], 210)
        self.assertEqual(memory["retrieve_end"], 240)
        self.assertEqual(memory["extract_start"], 400)
        self.assertEqual(memory["extract_end"], 450)
        self.assertEqual(
            memory["meta"],
            {"cache_hit": False, "entity_hits": 1, "extract_items": 2,
             "watermark_advanced": True},
        )

    def test_memory_phase_validation_keeps_source_contract_strict(self):
        accepted = validate(event("memory", "retrieve_start", "turn-1", 100))

        self.assertIsNotNone(accepted)
        self.assertIsNone(validate(event("memory", "unknown", "turn-1", 100)))
        self.assertIsNone(validate(event("unknown", "retrieve_start", "turn-1", 100)))
        self.assertIsNotNone(validate(event("llm", "content", "turn-1", 100)))
        self.assertIsNotNone(validate(event("llm", "raw_content", "turn-1", 100)))
        self.assertIsNone(validate(event("tts", "content", "turn-1", 100)))

    def test_rejects_raw_content_but_keeps_safe_meta(self):
        self.assertIsNone(validate({"source":"stt","phase":"start","request_id":"x","text":"secret"}))
        c=Correlator(); c.add(validate({"source":"stt","phase":"start","request_id":"x","meta":{"frames":3,"voice":True,"text":"secret"}}))
        self.assertEqual(c.snapshot()[0]["stt"]["meta"], {"frames":3,"voice":True})

    def test_ollama_terminal_metrics_survive_the_generic_meta_budget(self):
        c = Correlator()
        meta = {f"diagnostic_{index}": index for index in range(24)}
        meta.update({
            "ollama_prompt_eval_count": 17,
            "ollama_prompt_eval_ms": 2.0,
            "ollama_eval_count": 9,
            "ollama_eval_ms": 3.5,
        })
        c.add(event("llm", "start", "turn-1", 90))
        c.add({**event("llm", "end", "turn-1", 100), "meta": meta})
        saved = c.snapshot()[0]["llm"]["meta"]
        self.assertEqual(saved["ollama_prompt_eval_count"], 17)
        self.assertEqual(saved["ollama_prompt_eval_ms"], 2.0)
        self.assertEqual(saved["ollama_eval_count"], 9)
        self.assertEqual(saved["ollama_eval_ms"], 3.5)

if __name__ == "__main__": unittest.main()
