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
    ReplayFormatError,
    import_private_replay,
    run_replay,
)
import run_chat_replay


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
        report = run_replay(events, lambda text, event: "response: " + text)
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertEqual(report["delivered_count"], 2)
        self.assertEqual(report["response_count"], 2)
        self.assertEqual(len(report["response_rows"]), 2)
        self.assertEqual(report["timing_buckets"], {"1s_to_5s": 1, "under_1s": 3})
        self.assertNotIn("response:", serialized)
        self.assertNotIn("응원해요", serialized)
        offline = run_replay(events)
        self.assertEqual(offline["response_count"], 0)
        self.assertEqual(offline["delivered_count"], 2)

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
            self.assertEqual(respond("첫 채팅", None), "응답 1")
            self.assertEqual(respond("둘째 채팅", None), "응답 2")

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
            real_is_reparse = run_chat_replay._is_reparse
            with mock.patch.object(
                run_chat_replay,
                "_is_reparse",
                side_effect=lambda path: Path(path) == parent or real_is_reparse(path),
            ):
                self.assertFalse(run_chat_replay._secure_inside(candidate, parent))
        self.assertFalse(
            run_chat_replay._secure_inside(here / "outside.json", here / "reports"),
        )


if __name__ == "__main__":
    unittest.main()
