from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chat_replay import (
    ReplayAuthorizationError,
    ReplayEvent,
    ReplayFormatError,
    ReplayResponse,
    _canonical,
    import_private_replay,
    run_replay,
)
import run_chat_replay
import replay_local_io
from score_private_review import score_private_review


NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


def consent_for(export: Path, provenance: Path, **changes):
    value = {
        "schema_version": "airi.chat-replay-consent.v1", "authorization": "authorized",
        "authorization_basis": "creator_or_platform_written_permission",
        "authorized_at": (NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        "purposes": ["local_replay_evaluation"], "expires_at": (NOW + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        "delete_by": (NOW + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        "revoked": False, "source_sha256": hashlib.sha256(export.read_bytes()).hexdigest(),
        "provenance_sha256": hashlib.sha256(provenance.read_bytes()).hexdigest(),
        "excluded_creator_names": ["NamedCreator", "Alice"],
    }
    value.update(changes)
    return value


class ChatReplayTests(unittest.TestCase):
    def write_export(self, directory: Path) -> Path:
        export = directory / "capture.jsonl"
        events = [
            {"timestamp_ms": 100, "kind": "chat", "viewer_id": "private-viewer-7", "provider_id": "provider-private-3", "display_name": "Alice", "profile_url": "https://profile.example/u/1", "text": "Alice private-viewer-7 provider-private-3 @viewer https://profile.example/u/1 연락 010-1234-5678"},
            {"timestamp_ms": 400, "kind": "chat", "viewer_id": "private-viewer-7", "provider_id": "provider-private-3", "display_name": "Alice", "profile_url": "https://profile.example/u/1", "text": "Alice private-viewer-7 provider-private-3 @viewer https://profile.example/u/1 연락 010-1234-5678"},
            {"timestamp_ms": 900, "kind": "noise", "text": "ㅋㅋ"},
            {"timestamp_ms": 2100, "kind": "donation", "text": "NamedCreator 10,000원 응원해요"},
        ]
        export.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in events) + "\n", encoding="utf-8")
        return export

    def test_redaction_preserves_structure_without_identity_or_text_report(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            export = self.write_export(directory)
            provenance = directory / "permission.txt"
            provenance.write_text("local written authorization record", encoding="utf-8")
            sidecar = directory / "consent.json"
            sidecar.write_text(json.dumps(consent_for(export, provenance)), encoding="utf-8")
            events = import_private_replay(export, sidecar, provenance, now=NOW)
        self.assertEqual([item.seq for item in events], [1, 2, 3, 4])
        self.assertEqual([item.offset_ms for item in events], [0, 300, 800, 2000])
        self.assertEqual(events[1].duplicate_of_seq, 1)
        self.assertEqual(events[2].event_kind, "system_noise")
        self.assertFalse(events[1].selection_eligible); self.assertFalse(events[2].selection_eligible)
        joined = " ".join(item.model_text for item in events)
        for forbidden in ("Alice", "NamedCreator", "private-viewer-7", "provider-private-3", "@viewer", "https://", "010-1234-5678", "10,000원"):
            self.assertNotIn(forbidden, joined)
        report = run_replay(
            events, lambda text, event: "response: " + text,
            report_hmac_key=b"k" * 32,
        )
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertEqual(report["delivered_count"], 1)
        self.assertEqual(report["response_count"], 1)
        self.assertEqual(len(report["response_rows"]), 1)
        self.assertEqual(report["timing_buckets"], {"1s_to_5s": 1, "under_1s": 3})
        self.assertEqual(report["surface_signal_counts"], {
            "donation": 1,
            "laughter_run": 1,
            "noise": 1,
            "source_text_repeat": 1,
        })
        self.assertEqual(report["adjacent_event_count"], 3)
        self.assertEqual(report["adjacent_signal_pair_counts"], {
            "laughter_run->donation": 1,
            "noise->donation": 1,
            "none->source_text_repeat": 1,
            "source_text_repeat->laughter_run": 1,
            "source_text_repeat->noise": 1,
        })
        self.assertEqual(report["response_outcome_counts"], {"normal": 1})
        self.assertEqual(report["outcome_by_surface_signal"], {
            "donation": {"normal": 1},
        })
        self.assertEqual(report["max_events_in_rolling_5s"], 4)
        self.assertEqual(report["flow"], {
            "duration_ms": 2000,
            "gap_p50_ms": 500,
            "gap_p95_ms": 1200,
            "gap_max_ms": 1200,
            "interarrival_rate_per_minute": 90.0,
            "active_fixed_5s_bins": 1,
            "rolling_5s_burst_threshold": 5,
            "rolling_5s_burst_start_count": 0,
            "duplicate_rate": 0.25,
            "noise_rate": 0.25,
            "eligible_rate": 0.5,
            "repeat_cluster_count": 1,
            "max_repeat_cluster_size": 2,
        })
        self.assertNotIn("response:", serialized)
        self.assertNotIn("응원해요", serialized)
        offline = run_replay(events)
        self.assertEqual(offline["response_count"], 0)
        self.assertEqual(offline["delivered_count"], 0)
        self.assertGreater(offline["response_sampling"]["selected_event_count"], 0)

    def test_source_repeat_is_measured_before_redaction_collision(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            export = directory / "capture.jsonl"
            rows = [
                {"timestamp_ms": 0, "kind": "chat", "text": "Alice 1000원 응원"},
                {"timestamp_ms": 1, "kind": "chat", "text": "NamedCreator 2000원 응원"},
            ]
            export.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
            provenance = directory / "permission.txt"; provenance.write_text("permission", encoding="utf-8")
            consent = directory / "consent.json"; consent.write_text(json.dumps(consent_for(export, provenance)), encoding="utf-8")
            events = import_private_replay(export, consent, provenance, now=NOW)
        self.assertEqual(events[0].model_text, events[1].model_text)
        self.assertIsNone(events[0].duplicate_of_seq)
        self.assertIsNone(events[1].duplicate_of_seq)
        self.assertTrue(events[0].selection_eligible)
        self.assertTrue(events[1].selection_eligible)
        self.assertNotIn("source_text_repeat", events[1].surface_signals)

    def test_rolling_flow_boundaries_and_single_event_are_exact(self):
        def event(seq, offset):
            return ReplayEvent(seq, offset, "under_1s", "chat", f"채팅 {seq}", None, True, ())

        boundary = run_replay([
            event(1, 0), event(2, 4999), event(3, 5000),
            event(4, 5000), event(5, 5000), event(6, 9998),
        ])
        self.assertEqual(boundary["max_events_in_rolling_5s"], 5)
        self.assertEqual(boundary["flow"]["rolling_5s_burst_start_count"], 1)
        self.assertEqual(boundary["flow"]["active_fixed_5s_bins"], 2)

        one = run_replay([event(1, 0)])
        self.assertIsNone(one["flow"]["gap_p50_ms"])
        self.assertIsNone(one["flow"]["interarrival_rate_per_minute"])
        self.assertEqual(one["max_events_in_rolling_5s"], 1)
        minute = run_replay([event(1, 0), event(2, 60_000)])
        self.assertEqual(minute["flow"]["interarrival_rate_per_minute"], 1.0)

    def test_fixed_5s_sampler_selects_one_tie_lowest_seq_and_skips_neutral(self):
        events = [
            ReplayEvent(1, 4999, "under_1s", "chat", "first?", None, True, ("question_mark",)),
            ReplayEvent(2, 5000, "under_1s", "chat", "tie two?", None, True, ("question_mark",)),
            ReplayEvent(3, 5001, "under_1s", "chat", "tie three?", None, True, ("question_mark",)),
            ReplayEvent(4, 10000, "under_1s", "chat", "neutral", None, True, ()),
        ]
        calls: list[int] = []
        report = run_replay(events, lambda _, event: calls.append(event.seq) or "ok", report_hmac_key=b"k" * 32)
        self.assertEqual(calls, [1, 2])
        self.assertEqual(report["response_sampling"]["fixed_5s_batch_count"], 3)
        self.assertEqual(report["response_sampling"]["no_reply_batch_count"], 1)
        self.assertEqual(report["response_sampling"]["selected_event_count"], 2)
        self.assertNotIn("first?", json.dumps(report))

    def test_invalid_prepared_eligibility_or_duplicate_is_rejected(self):
        with self.assertRaises(ReplayFormatError):
            run_replay([ReplayEvent(1, 0, "under_1s", "chat", "x", None, False, ())])
        with self.assertRaises(ReplayFormatError):
            run_replay([ReplayEvent(1, 0, "under_1s", "chat", "x", 1, False, ("source_text_repeat",))])

    def test_surface_signals_are_lexical_and_pair_counts_are_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            export = directory / "capture.jsonl"
            rows = [
                {"timestamp_ms": 0, "kind": "chat", "text": "진짜??"},
                {"timestamp_ms": 1, "kind": "chat", "text": "아니, 진짜!"},
                {"timestamp_ms": 2, "kind": "chat", "text": "아니면 갈까"},
                {"timestamp_ms": 3, "kind": "chat", "text": "ㅋ"},
            ]
            export.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
            provenance = directory / "permission.txt"; provenance.write_text("permission", encoding="utf-8")
            consent = directory / "consent.json"; consent.write_text(json.dumps(consent_for(export, provenance)), encoding="utf-8")
            events = import_private_replay(export, consent, provenance, now=NOW)
        self.assertEqual(events[0].surface_signals, ("question_mark", "emphasis"))
        self.assertEqual(events[1].surface_signals, ("correction_marker", "emphasis"))
        self.assertEqual(events[2].surface_signals, ())
        self.assertEqual(events[3].surface_signals, ())
        report = run_replay(events)
        expected_pairs = {
            "question_mark->correction_marker",
            "question_mark->emphasis",
            "emphasis->correction_marker",
            "emphasis->emphasis",
        }
        self.assertEqual(
            set(report["adjacent_signal_pair_counts"]) & expected_pairs,
            expected_pairs,
        )
        self.assertEqual(report["adjacent_event_count"], 3)

    def test_capture_profile_is_bounded_and_part_of_structural_hash(self):
        event = ReplayEvent(1, 0, "under_1s", "chat", "채팅", None, True, ())
        opening = run_replay([event], capture_profile={"source_slot": "channel_a", "phase": "opening"})
        middle = run_replay([event], capture_profile={"source_slot": "channel_a", "phase": "middle"})
        self.assertNotEqual(opening["structural_sha256"], middle["structural_sha256"])
        self.assertEqual(opening["capture_profile"], {"source_slot": "channel_a", "phase": "opening"})
        with self.assertRaises(ReplayFormatError):
            run_replay([event], capture_profile={"source_slot": "named-channel", "phase": "opening"})

    def test_missing_expired_revoked_or_changed_authorization_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            export = self.write_export(directory)
            provenance = directory / "permission.txt"
            provenance.write_text("local written authorization record", encoding="utf-8")
            sidecar = directory / "consent.json"
            for changes in ({}, {"revoked": True}, {"expires_at": (NOW - timedelta(seconds=1)).isoformat()}, {"delete_by": (NOW - timedelta(seconds=1)).isoformat()}, {"authorization_basis": "public_watch_page"}, {"source_sha256": "0" * 64}):
                with self.subTest(changes=changes):
                    if changes:
                        sidecar.write_text(json.dumps(consent_for(export, provenance, **changes)), encoding="utf-8")
                    elif sidecar.exists():
                        sidecar.unlink()
                    with self.assertRaises(ReplayAuthorizationError):
                        import_private_replay(export, sidecar, provenance, now=NOW)
            sidecar.write_text(json.dumps(consent_for(export, provenance)), encoding="utf-8")
            provenance.write_text("changed permission record", encoding="utf-8")
            with self.assertRaises(ReplayAuthorizationError):
                import_private_replay(export, sidecar, provenance, now=NOW)

    def test_unsafe_unicode_and_non_integer_timestamp_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            provenance = directory / "permission.txt"
            provenance.write_text("local written authorization record", encoding="utf-8")
            for timestamp, text in ((True, "채팅"), (100, "안전하지 않은\u202e채팅")):
                with self.subTest(timestamp=timestamp, text=text):
                    export = directory / "capture.jsonl"
                    export.write_text(json.dumps({
                        "timestamp_ms": timestamp, "kind": "chat", "text": text,
                    }, ensure_ascii=False) + "\n", encoding="utf-8")
                    sidecar = directory / "consent.json"
                    sidecar.write_text(json.dumps(consent_for(export, provenance)), encoding="utf-8")
                    with self.assertRaises(ReplayFormatError):
                        import_private_replay(export, sidecar, provenance, now=NOW)
            export.write_text(json.dumps({
                "timestamp_ms": 100,
                "kind": "chat",
                "text": "채팅",
                "unknown_identity_field": "must not be silently accepted",
            }, ensure_ascii=False) + "\n", encoding="utf-8")
            sidecar.write_text(
                json.dumps(consent_for(export, provenance)), encoding="utf-8",
            )
            with self.assertRaises(ReplayFormatError):
                import_private_replay(export, sidecar, provenance, now=NOW)

    def test_fixture_is_explicitly_synthetic_and_has_no_identity_fields(self):
        base = Path(__file__).parent
        schema = json.loads((base / "fixture.schema.json").read_text(encoding="utf-8"))
        manifest = json.loads((base / "replay-suite-manifest.v1.json").read_text(encoding="utf-8"))
        self.assertTrue(schema["synthetic_only"])
        self.assertTrue(manifest["synthetic_only"])
        self.assertFalse(manifest["privacy"]["real_chat_committed"])
        self.assertEqual(manifest["model_profile"], {
            "model": run_chat_replay.EVAL_MODEL,
            "model_digest": run_chat_replay.EVAL_MODEL_DIGEST,
            "temperature": run_chat_replay.EVAL_TEMPERATURE,
            "seed": run_chat_replay.EVAL_SEED,
            "num_ctx": run_chat_replay.EVAL_NUM_CTX,
            "max_tokens": run_chat_replay.EVAL_MAX_TOKENS,
            "history_turns": 8,
        })
        for line in (base / "fixtures" / "synthetic-korean-v1.jsonl").read_text(encoding="utf-8").splitlines():
            self.assertFalse(set(json.loads(line)) & set(schema["prohibited_fields"]))
        for fixture in manifest["fixtures"]:
            self.assertEqual(
                hashlib.sha256((base / fixture["path"]).read_bytes()).hexdigest(),
                fixture["sha256"],
            )

    def test_loopback_responder_uses_openai_shape_and_bounded_history(self):
        requests = []

        class Response:
            status = 200
            headers = {}
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
            def read(self):
                return json.dumps({"choices": [{"message": {"content": f"응답 {len(requests)}"}}]}).encode("utf-8")

        def fake_urlopen(request, timeout):
            self.assertEqual(timeout, 15)
            requests.append(request)
            return Response()

        with mock.patch.object(run_chat_replay, "urlopen", side_effect=fake_urlopen):
            attestations = []
            profile = {"model": "midm-airi:2.0-mini"}
            respond = run_chat_replay.loopback_responder(
                "http://127.0.0.1:11435/v1/chat/completions", "midm-airi:2.0-mini",
                history_turns=1,
                attest=lambda: attestations.append(True) or profile,
            )
            first_result = respond("첫 채팅", None)
            second_result = respond("둘째 채팅", None)
            self.assertEqual(first_result, ReplayResponse("응답 1", "normal"))
            self.assertEqual(second_result, ReplayResponse("응답 2", "normal"))

        first = json.loads(requests[0].data.decode("utf-8"))
        second = json.loads(requests[1].data.decode("utf-8"))
        self.assertEqual(first["messages"], [{"role": "user", "content": "첫 채팅"}])
        self.assertEqual([item["role"] for item in second["messages"]], ["user", "assistant", "user"])
        self.assertEqual(requests[0].get_header("X-airi-turn-origin"), "local-evaluation")
        self.assertFalse(first["stream"])
        self.assertEqual(len(attestations), 4)
        self.assertEqual(first["temperature"], 0)
        self.assertEqual(first["seed"], 42)
        self.assertEqual(first["max_tokens"], 128)
        with self.assertRaises(ValueError):
            run_chat_replay.loopback_responder("https://example.com/chat", "model")
        with self.assertRaises(ValueError):
            run_chat_replay.loopback_responder(
                "http://127.0.0.1:11434/v1/chat/completions", "model",
            )
        profiles = iter(({"digest": "before"}, {"digest": "after"}))
        with mock.patch.object(run_chat_replay, "urlopen", side_effect=fake_urlopen):
            unstable = run_chat_replay.loopback_responder(
                "http://127.0.0.1:11435/v1/chat/completions",
                "midm-airi:2.0-mini",
                attest=lambda: next(profiles),
            )
            with self.assertRaises(RuntimeError):
                unstable("프로필 변경 검사", None)

    def test_response_headers_become_only_bounded_outcomes(self):
        class Response:
            def __init__(self, headers):
                self.headers = headers

        self.assertEqual(run_chat_replay._response_outcome(Response({
            "X-AIRI-Epistemic-Confidence": "reference",
        })), "epistemic_reference")
        self.assertEqual(run_chat_replay._response_outcome(Response({
            "X-AIRI-Input-Screened": "blocked",
        })), "input_screened")
        self.assertEqual(run_chat_replay._response_outcome(Response({
            "X-AIRI-Serious-Safety": "handled",
            "X-AIRI-Epistemic-Confidence": "live_state",
        })), "serious_safety")
        event = ReplayEvent(1, 0, "under_1s", "chat", "질문?", None, True, ("question_mark",))
        report = run_replay(
            [event], lambda *_: ReplayResponse("실제 응답 원문", "epistemic_reference"),
            report_hmac_key=b"k" * 32,
        )
        self.assertEqual(report["response_outcome_counts"], {"epistemic_reference": 1})
        self.assertNotIn("실제 응답 원문", json.dumps(report, ensure_ascii=False))
        self.assertIn("response_hmac_sha256", report["response_rows"][0])
        with self.assertRaises(ReplayFormatError):
            run_replay([event], lambda *_: "응답")

    def test_private_review_packet_includes_skipped_rows_for_human_labels(self):
        events = [
            ReplayEvent(1, 0, "under_1s", "chat", "입력 1?", None, True, ("question_mark",)),
            ReplayEvent(2, 1, "under_1s", "system_noise", "ㅋㅋ", None, False, ("laughter_run", "noise")),
        ]
        profile = {"source_slot": "channel_a", "phase": "opening"}
        key = b"k" * 32
        source_report = run_replay(
            events, lambda *_: "응답 1", capture_profile=profile,
            report_hmac_key=key,
        )
        evidence = {
            "provider": "test-provider", "source_identity_hmac": "a" * 64,
            "exact_capture_hmac": "b" * 64,
        }
        runtime = {"history_turns": 8}
        binding = hashlib.sha256(_canonical({
            "source_structural_sha256": source_report["structural_sha256"],
            "source_evidence": evidence, "runtime_profile": runtime,
            "response_rows": source_report["response_rows"],
            "response_sampling": source_report["response_sampling"],
        })).hexdigest()
        replay = {
            **source_report,
            "source_evidence": evidence,
            "runtime_profile": runtime,
            "run_binding_sha256": binding,
        }
        replay["report_hmac_sha256"] = run_chat_replay.replay_report_hmac(
            key, replay,
        )
        packet = run_chat_replay.build_private_review_packet(
            events, {1: "응답 1"}, profile, source_report["structural_sha256"],
            evidence, runtime, binding, replay["report_hmac_sha256"],
            source_report["response_rows"],
            source_report["response_sampling"],
        )
        self.assertEqual(len(packet["rows"]), 2)
        self.assertEqual(
            packet["report_hmac_sha256"], replay["report_hmac_sha256"],
        )
        self.assertTrue(packet["rows"][0]["delivered"])
        self.assertFalse(packet["rows"][1]["delivered"])
        self.assertIsNone(packet["rows"][1]["response"])
        self.assertTrue(all(
            value is None for value in packet["rows"][0]["review"].values()
        ))
        packet["rows"][0]["review"] = {
            "expected_action": "respond", "grounded": True,
            "context_preserved": True, "tone_ok": True,
            "privacy_ok": True, "current_fact_ok": True,
            "reference_grounding_ok": True, "agreement_calibration_ok": True,
        }
        packet["rows"][1]["review"]["expected_action"] = "ignore"
        packet["source_review"] = {
            "atmosphere": "calm", "pace": "steady",
            "context_pressure": "low", "dominant_patterns": ["question_wave"],
        }
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "review.json"
            replay_path = Path(temp) / "replay.json"
            key_path = Path(temp) / "key.bin"
            path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
            replay_path.write_text(json.dumps(replay), encoding="utf-8")
            key_path.write_bytes(key)
            score = score_private_review(path, replay_path, key_path)
        self.assertEqual(score["row_count"], 2)
        self.assertEqual(score["replay_selector"]["tp"], 1)
        self.assertEqual(score["replay_selector"]["tn"], 1)
        self.assertRegex(score["score_hmac_sha256"], r"^[0-9a-f]{64}$")

    def test_loopback_health_attests_profile_and_gate_without_mutating_them(self):
        digest = run_chat_replay.EVAL_MODEL_DIGEST
        health = {
            "status": "ok",
            "num_ctx": 2048,
            "chat_model": {
                "model": "midm-airi:2.0-mini",
                "digest": {"digest": digest, "status": "pinned", "verified": True},
            },
            "epistemic_confidence": {"enabled": True},
        }

        class Response:
            status = 200
            def __init__(self, value):
                self.value = value
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
            def read(self):
                return json.dumps(self.value).encode("utf-8")

        requests = []
        with mock.patch.object(
            run_chat_replay, "urlopen",
            side_effect=lambda request, timeout: requests.append((request, timeout)) or Response(health),
        ):
            profile = run_chat_replay.verify_loopback_health(
                "http://127.0.0.1:11435/v1/chat/completions",
                "midm-airi:2.0-mini",
            )
        self.assertEqual(requests[0][0].full_url, "http://127.0.0.1:11435/health")
        self.assertEqual(requests[0][1], 5)
        self.assertEqual(profile["model_digest"], digest)
        self.assertTrue(profile["epistemic_confidence_enabled"])

        for changed, message in (
            ({"num_ctx": 4096}, "num_ctx"),
            ({"epistemic_confidence": {"enabled": False}}, "gate"),
            ({"chat_model": {"model": "other", "digest": {"digest": digest, "status": "pinned", "verified": True}}}, "model"),
            ({"chat_model": {"model": "midm-airi:2.0-mini", "digest": {"digest": digest, "status": "observed", "verified": False}}}, "unpinned"),
        ):
            with self.subTest(message=message):
                broken = dict(health)
                broken.update(changed)
                with mock.patch.object(
                    run_chat_replay, "urlopen", return_value=Response(broken),
                ):
                    with self.assertRaises(RuntimeError):
                        run_chat_replay.verify_loopback_health(
                            "http://127.0.0.1:11435/v1/chat/completions",
                            "midm-airi:2.0-mini",
                        )

    def test_secure_inside_rejects_a_reparse_base_and_parent_escape(self):
        here = Path(run_chat_replay.HERE)
        with tempfile.TemporaryDirectory(dir=here) as temp:
            parent = Path(temp)
            candidate = parent / "report.json"
            real_is_reparse = replay_local_io._is_reparse
            with mock.patch.object(
                replay_local_io,
                "_is_reparse",
                side_effect=lambda path: Path(path) == parent or real_is_reparse(path),
            ):
                self.assertFalse(run_chat_replay._secure_inside(candidate, parent))
        self.assertFalse(
            run_chat_replay._secure_inside(here / "outside.json", here / "reports"),
        )


if __name__ == "__main__":
    unittest.main()
