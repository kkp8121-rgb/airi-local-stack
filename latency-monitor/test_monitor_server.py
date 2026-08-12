import http.client
import json
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
import monitor_server
from monitor_server import Correlator, Handler, LocalBroadcastProofs, validate, validate_local_broadcast_proof

def event(source, phase, request_id, stamp): return {"source": source, "phase": phase, "request_id": request_id, "timestamp_ms": stamp}


class Clock:
    def __init__(self): self.value = 0
    def __call__(self): return self.value
    def advance(self, seconds): self.value += seconds

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

    def test_dashboard_acceptance_uses_the_substantive_metrics_module(self):
        dashboard = (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("import { summarizeAcceptance } from '/dashboard-metrics.mjs'", dashboard)
        acceptance = dashboard.split("const acceptance = summarizeAcceptance", 1)[1].split("if (!turns.length)", 1)[0]
        self.assertNotIn("requestToPlayback", acceptance)

    def test_dashboard_metrics_module_is_served_from_fixed_route(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        try:
            connection.request("GET", "/dashboard-metrics.mjs")
            response = connection.getresponse()
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Content-Type"), "application/javascript; charset=utf-8")
            self.assertIn("export function summarizeAcceptance", body)
            connection.request("GET", "/dashboard-metrics.mjs/extra")
            self.assertEqual(connection.getresponse().status, 404)
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_half_duplex_different_request_ids_join_one_turn(self):
        clock = Clock(); c = Correlator(reorder_ttl_ms=10, clock=clock)
        for e in [event("stt", "start", "s1", 100), event("stt", "end", "s1", 200), event("llm", "start", "l1", 220), event("llm", "first", "l1", 300), event("tts", "start", "t1", 310), event("tts", "first", "t1", 390), event("tts", "end", "t1", 480)]: self.assertTrue(c.add(e))
        clock.advance(.02); self.assertTrue(c.add(event("llm", "end", "l1", 500)))
        t = c.snapshot()[0]
        self.assertEqual((t["stt"]["end"], t["llm"]["first"], t["tts"]["first"]), (200, 300, 390))
        self.assertEqual(t["tts"]["segments"], 1)
        self.assertEqual(t["correlation"]["tts"], "heuristic")

    def test_tts_segments_and_new_stt_turn(self):
        c = Correlator()
        for e in [event("stt","start","s1",1),event("llm","start","l1",2),event("tts","start","s1",3),event("tts","start","s1",4),event("stt","start","s2",10)]: c.add(e)
        turns=c.snapshot()
        self.assertEqual(len(turns),2); self.assertEqual(turns[1]["tts"]["segments"],2); self.assertEqual(turns[0]["turn_id"],"s2")

    def test_tts_keeps_earliest_first_audio_and_merges_numeric_meta(self):
        c = Correlator()
        events = [
            {**event("stt", "start", "s1", 1), "meta": {"audio_bytes": 10}},
            {**event("stt", "end", "s1", 2), "meta": {"inference_ms": 7}},
            event("llm", "start", "l1", 3),
            event("tts", "start", "s1", 4),
            {**event("tts", "first", "s1", 5), "meta": {"lock_wait_ms": 0}},
            event("tts", "start", "s1", 6),
            event("tts", "first", "s1", 9),
            event("tts", "end", "s1", 12),
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
            event("tts", "start", "s1", 300),
            event("playback", "start", "s1", 420),
            event("playback", "start", "s1", 900),
        ]:
            self.assertTrue(c.add(item))

        self.assertEqual(c.snapshot()[0]["playback"]["start"], 420)

    def test_ack_and_substantive_audio_kpis_are_separate(self):
        clock = Clock(); c = Correlator(reorder_ttl_ms=10, clock=clock)
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

    def test_pre_anchor_audio_replays_into_a_distinct_explicit_text_turn(self):
        clock = Clock()
        c = Correlator(reorder_ttl_ms=100, clock=clock)
        for item in [
            event("stt", "start", "a", 10),
            event("llm", "start", "a", 20),
            event("llm", "content", "a", 30),
            event("tts", "first", "a", 40),
            event("playback", "start", "a", 45),
            event("tts", "first", "b", 100),
            event("playback", "start", "b", 105),
            event("llm", "start", "b", 110),
            event("llm", "content", "b", 120),
            event("tts", "first", "b", 130),
            event("playback", "start", "b", 135),
        ]:
            self.assertTrue(c.add(item))
        turns = c.snapshot()
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[1]["turn_id"], "a")
        self.assertEqual(turns[0]["turn_id"], "b")
        self.assertEqual(turns[0]["stt"], {})
        self.assertEqual(turns[0]["correlation"], {
            "llm": "explicit", "tts": "explicit", "playback": "explicit",
        })
        self.assertEqual(turns[0]["kpi"], {
            "ack_tts_first": 100,
            "ack_playback_start": 105,
            "substantive_tts_first": 130,
            "substantive_playback_start": 135,
        })
        self.assertEqual(
            turns[0]["tts"]["timeline"],
            [
                {"phase": "first", "timestamp_ms": 100, "correlation": "explicit"},
                {"phase": "first", "timestamp_ms": 130, "correlation": "explicit"},
            ],
        )
        self.assertEqual(
            turns[0]["playback"]["timeline"],
            [
                {"phase": "start", "timestamp_ms": 105, "correlation": "explicit"},
                {"phase": "start", "timestamp_ms": 135, "correlation": "explicit"},
            ],
        )

    def test_pre_anchor_audio_joins_a_same_id_stt_turn_arriving_before_llm(self):
        c = Correlator()
        for item in [
            event("tts", "first", "same", 300),
            event("playback", "start", "same", 310),
            event("stt", "start", "same", 100),
            event("stt", "end", "same", 180),
            event("llm", "start", "same", 200),
            event("llm", "content", "same", 250),
        ]:
            self.assertTrue(c.add(item))
        turns = c.snapshot()
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["stt"], {"start": 100, "end": 180})
        self.assertEqual(turns[0]["llm"]["start"], 200)
        self.assertEqual(turns[0]["tts"]["first"], 300)
        self.assertEqual(turns[0]["playback"]["start"], 310)
        self.assertEqual(turns[0]["kpi"], {
            "substantive_tts_first": 300,
            "substantive_playback_start": 310,
        })

    def test_pending_audio_is_bounded_content_free_and_drops_oldest_bucket(self):
        clock = Clock()
        c = Correlator(pending_request_limit=2, pending_event_limit=2,
                       pending_per_request_limit=1, clock=clock)
        self.assertTrue(c.add({**event("tts", "first", "one", 1), "meta": {"private words from user": 1}}))
        self.assertEqual(
            c.pending_audio["one"]["events"][0]["event"],
            event("tts", "first", "one", 1),
        )
        self.assertTrue(c.add(event("playback", "start", "two", 2)))
        self.assertTrue(c.add(event("tts", "first", "three", 3)))
        self.assertEqual(set(c.pending_audio), {"two", "three"})
        self.assertEqual(c.pending_event_count, 2)
        self.assertEqual(
            c.pending_audio["two"]["events"][0]["event"],
            event("playback", "start", "two", 2),
        )

        current = Correlator(pending_request_limit=3, pending_event_limit=2,
                             pending_per_request_limit=2, clock=clock)
        self.assertTrue(current.add(event("tts", "first", "old", 4)))
        self.assertTrue(current.add(event("tts", "start", "current", 5)))
        self.assertTrue(current.add(event("tts", "first", "current", 6)))
        self.assertEqual(set(current.pending_audio), {"current"})
        self.assertEqual(current.pending_event_count, 2)
        self.assertTrue(current.add(event("tts", "end", "current", 7)))
        self.assertEqual(len(current.pending_audio["current"]["events"]), 2)
        self.assertEqual(current.pending_event_count, 2)

    def test_correlator_rejects_invalid_reorder_bounds(self):
        for kwargs in [
            {"limit": 0}, {"limit": True}, {"reorder_ttl_ms": 0},
            {"reorder_ttl_ms": False}, {"reorder_ttl_ms": float("nan")},
            {"reorder_ttl_ms": float("inf")}, {"pending_request_limit": 1.5},
            {"pending_event_limit": 0}, {"pending_per_request_limit": -1},
            {"limit": 10 ** 1000}, {"reorder_ttl_ms": 10 ** 1000},
            {"clock": "not-a-clock"},
        ]:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    Correlator(**kwargs)

        for values in [[float("nan")], [float("inf")], [1, 0]]:
            c = Correlator(clock=lambda values=iter(values): next(values))
            if len(values) == 2:
                self.assertTrue(c.add(event("llm", "start", "turn", 1)))
            with self.assertRaises(ValueError):
                c.snapshot()

    def test_pending_audio_expires_as_heuristic_without_explicit_upgrade(self):
        clock = Clock(); c = Correlator(reorder_ttl_ms=10, clock=clock)
        self.assertTrue(c.add(event("stt", "start", "a", 1)))
        self.assertTrue(c.add(event("tts", "first", "different", 2)))
        clock.advance(.02)
        self.assertTrue(c.add(event("llm", "content", "llm-a", 3)))
        turn = c.snapshot()[0]
        self.assertEqual(turn["tts"]["first"], 2)
        self.assertEqual(turn["correlation"]["tts"], "heuristic")
        self.assertNotIn("substantive_tts_first", turn["kpi"])
        self.assertTrue(c.add(event("llm", "start", "different", 4)))
        self.assertEqual(c.snapshot()[0]["correlation"]["llm"], "heuristic")

    def test_snapshot_expires_pending_audio_without_a_later_event(self):
        clock = Clock(); c = Correlator(reorder_ttl_ms=10, clock=clock)
        self.assertTrue(c.add(event("stt", "start", "a", 1)))
        self.assertTrue(c.add({**event("tts", "first", "different", 2), "meta": {"private words from user": 1}}))
        clock.advance(.02)
        public = c.snapshot()
        self.assertEqual(c.pending_audio, {})
        self.assertEqual(public[0]["tts"]["first"], 2)
        self.assertNotIn("private words from user", str(public))

    def test_delayed_content_reclassifies_buffered_audio_from_ack_to_substantive(self):
        c = Correlator()
        for item in [
            event("tts", "first", "text", 130),
            event("playback", "start", "text", 135),
            event("llm", "start", "text", 110),
            event("llm", "content", "text", 120),
        ]:
            self.assertTrue(c.add(item))
        self.assertEqual(c.snapshot()[0]["kpi"], {
            "substantive_tts_first": 130,
            "substantive_playback_start": 135,
        })

    def test_expiry_replays_cross_request_audio_in_global_arrival_order(self):
        clock = Clock(); c = Correlator(reorder_ttl_ms=10, clock=clock)
        self.assertTrue(c.add(event("llm", "start", "base", 1)))
        self.assertTrue(c.add(event("playback", "start", "x", 10)))
        self.assertTrue(c.add(event("tts", "first", "y", 11)))
        self.assertTrue(c.add(event("tts", "first", "x", 12)))
        clock.advance(.02)
        turn = c.snapshot()[0]
        self.assertEqual(turn["tts"]["first"], 11)
        self.assertEqual(
            [item["timestamp_ms"] for item in turn["tts"]["timeline"]],
            [11, 12],
        )

    def test_heuristic_stage_scalar_never_becomes_an_explicit_kpi(self):
        clock = Clock(); c = Correlator(reorder_ttl_ms=10, clock=clock)
        self.assertTrue(c.add(event("llm", "start", "a", 10)))
        self.assertTrue(c.add(event("tts", "first", "x", 100)))
        self.assertTrue(c.add(event("playback", "start", "y", 110)))
        clock.advance(.02)
        c.snapshot()
        self.assertTrue(c.add(event("tts", "first", "a", 200)))
        self.assertTrue(c.add(event("playback", "start", "a", 210)))
        self.assertTrue(c.add(event("llm", "content", "a", 150)))
        turn = c.snapshot()[0]
        self.assertEqual(turn["tts"]["first"], 100)
        self.assertEqual(turn["playback"]["start"], 110)
        self.assertEqual(turn["correlation"]["tts"], "mixed")
        self.assertEqual(turn["correlation"]["playback"], "mixed")
        self.assertEqual(turn["kpi"], {
            "substantive_tts_first": 200,
            "substantive_playback_start": 210,
        })

    def test_completed_explicit_request_id_reuse_preserves_prior_turn(self):
        c = Correlator()
        for item in [
            event("llm", "start", "same", 100),
            event("llm", "content", "same", 120),
            event("llm", "end", "same", 140),
            event("tts", "start", "same", 190),
            event("tts", "first", "same", 200),
            event("tts", "end", "same", 205),
            event("playback", "start", "same", 207),
            event("llm", "start", "same", 210),
        ]:
            self.assertTrue(c.add(item))
        turns = c.snapshot()
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[1]["llm"], {"start": 100, "content": 120, "content_last": 120, "end": 140})
        self.assertEqual(turns[1]["tts"]["first"], 200)
        self.assertEqual(turns[1]["tts"]["end"], 205)
        self.assertEqual(turns[1]["playback"]["start"], 207)
        self.assertEqual(turns[0]["llm"], {"start": 210})
        self.assertEqual(turns[0]["tts"], {"segments": 0})

        clock = Clock(); expired = Correlator(reorder_ttl_ms=10, clock=clock)
        for item in [
            event("llm", "start", "same", 100),
            event("llm", "end", "same", 140),
            event("tts", "first", "same", 200),
        ]:
            self.assertTrue(expired.add(item))
        clock.advance(.02)
        old = expired.snapshot()[0]
        self.assertEqual(old["llm"], {"start": 100, "end": 140})
        self.assertEqual(old["tts"]["first"], 200)

    def test_delayed_content_kpis_survive_diagnostic_timeline_rollover(self):
        c = Correlator()
        self.assertTrue(c.add(event("llm", "start", "a", 1)))
        self.assertTrue(c.add(event("tts", "first", "a", 100)))
        self.assertTrue(c.add(event("tts", "first", "a", 200)))
        for stamp in range(300, 366):
            self.assertTrue(c.add(event("tts", "end", "a", stamp)))
        self.assertTrue(c.add(event("llm", "content", "a", 150)))
        turn = c.snapshot()[0]
        self.assertEqual(turn["kpi"], {
            "ack_tts_first": 100,
            "substantive_tts_first": 200,
        })
        self.assertNotIn("_kpi_events", turn)
        self.assertNotIn("_kpi_overflow", turn)

    def test_http_api_accepts_then_promotes_pre_anchor_audio(self):
        original = monitor_server.CORRELATOR
        monitor_server.CORRELATOR = Correlator(reorder_ttl_ms=60_000)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)

        def request(method, path, payload=None):
            body = None if payload is None else json.dumps(payload).encode("utf-8")
            headers = {} if body is None else {
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            }
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read().decode("utf-8"))

        try:
            status, accepted = request("POST", "/api/event", event("tts", "first", "text-b", 100))
            self.assertEqual((status, accepted), (202, {"accepted": True}))
            status, before = request("GET", "/api/snapshot")
            self.assertEqual(status, 200)
            self.assertEqual(before["turns"], [])
            status, accepted = request("POST", "/api/event", event("llm", "start", "text-b", 110))
            self.assertEqual((status, accepted), (202, {"accepted": True}))
            status, after = request("GET", "/api/snapshot")
            self.assertEqual(status, 200)
            self.assertEqual(after["turns"][0]["turn_id"], "text-b")
            self.assertEqual(
                after["turns"][0]["correlation"],
                {"llm": "explicit", "tts": "explicit"},
            )
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            monitor_server.CORRELATOR = original

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
        clock = Clock(); c = Correlator(reorder_ttl_ms=10, clock=clock)
        self.assertTrue(c.add(event("stt", "start", "turn-1", 100)))
        # This LLM ID is only associated by the legacy recency heuristic.
        self.assertTrue(c.add(event("llm", "content", "llm-1", 200)))
        self.assertTrue(c.add(event("tts", "first", "tts-1", 230)))
        self.assertTrue(c.add(event("playback", "start", "play-1", 240)))
        clock.advance(.02); self.assertTrue(c.add(event("llm", "end", "llm-1", 250)))
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
        self.assertTrue(other.add(event("tts", "first", "orphan", 1)))
        self.assertEqual(other.snapshot(), [])

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
            self.assertTrue(c.add(event("tts", "first", "turn-1", stamp)))
        timeline = c.snapshot()[0]["tts"]["timeline"]
        self.assertEqual(len(timeline), 64)
        self.assertEqual(timeline[0]["timestamp_ms"], 8)
        self.assertEqual(set(timeline[0]), {"phase", "timestamp_ms", "correlation"})
        self.assertNotIn("ack_tts_first", c.snapshot()[0]["kpi"])

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

    def test_rejects_nonfinite_event_numbers(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                self.assertIsNone(validate({**event("tts", "first", "x", 1), "timestamp_ms": value}))
                self.assertIsNone(validate({**event("tts", "first", "x", 1), "duration_ms": value}))
                self.assertIsNone(validate({**event("tts", "first", "x", 1), "meta": {"metric": value}}))

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
