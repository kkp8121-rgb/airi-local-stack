from __future__ import annotations

from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import urllib.error
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_youtube_live_export as collector
from normalize_authorized_export import (
    normalize_authorized_export,
    provider_binding_hmac,
)
from chat_replay import ReplayAuthorizationError


NOW = datetime(2026, 8, 15, 3, 0, tzinfo=timezone.utc)


def iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


class FakeClock:
    def __init__(self) -> None:
        self.seconds = 0.0
        self.wall_ms = int(NOW.timestamp() * 1_000)

    def monotonic(self) -> float:
        return self.seconds

    def wall(self) -> int:
        return self.wall_ms

    def sleep(self, seconds: float) -> None:
        self.seconds += seconds
        self.wall_ms += round(seconds * 1_000)


class CollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.key = b"collector-test-identity-key-32b!"
        self.proof = b"operator-owned broadcast permission"
        self.key_path = self.directory / "identity.key"
        self.api_path = self.directory / "youtube-api.key"
        self.proof_path = self.directory / "permission.txt"
        self.auth_path = self.directory / "authorization.json"
        self.key_path.write_bytes(self.key)
        self.api_path.write_text("testApiKey_123", encoding="utf-8")
        self.proof_path.write_bytes(self.proof)
        self.authorization = self.write_authorization()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_authorization(self, **changes) -> dict[str, object]:
        provenance_hash = hashlib.sha256(self.proof).hexdigest()
        value: dict[str, object] = {
            "schema_version": collector.AUTH_SCHEMA,
            "authorization": "authorized",
            "authorization_basis": "operator_owned_broadcast",
            "authorized_at": iso(NOW - timedelta(minutes=1)),
            "expires_at": iso(NOW + timedelta(hours=2)),
            "delete_by": iso(NOW + timedelta(days=1)),
            "revoked": False,
            "purposes": ["local_replay_evaluation"],
            "provenance_sha256": provenance_hash,
            "provider": "youtube",
            "video_id": "video_1",
            "channel_id": "channel_1",
            "exporter_id": "airi-local-exporter",
            "source_slot": "channel_a",
            "phase": "opening",
            "duration_seconds": 1_800,
            "max_events": 1_000,
            "excluded_creator_names": ["CreatorName"],
        }
        value.update(changes)
        if "provider_binding_hmac" not in changes:
            value["provider_binding_hmac"] = provider_binding_hmac(
                self.key,
                provider="youtube",
                channel_id=str(value["channel_id"]),
                exporter_id=str(value["exporter_id"]),
                source_schema=collector.SOURCE_SCHEMA,
                authorization_ref_sha256=str(value["provenance_sha256"]),
                source_slot=str(value["source_slot"]),
            )
        self.auth_path.write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )
        self.authorization = value
        return value

    def message(
        self,
        number: int,
        *,
        message_type: str = "textMessageEvent",
        text: str = "안녕",
        timestamp: datetime = NOW,
    ) -> dict[str, object]:
        snippet: dict[str, object] = {
            "type": message_type,
            "publishedAt": iso(timestamp),
        }
        if message_type == "textMessageEvent":
            snippet["textMessageDetails"] = {"messageText": text}
        return {"id": f"message-{number}", "snippet": snippet}

    def complete_messages(self) -> list[dict[str, object]]:
        return [
            self.message(-1, timestamp=NOW - timedelta(milliseconds=1)),
            self.message(0, message_type="superChatEvent"),
            self.message(1, message_type="membershipGiftingEvent"),
            self.message(2, message_type="modeChangedEvent"),
            *[self.message(number) for number in range(3, 300)],
            self.message(299),
        ]

    def transport(
        self,
        messages: list[dict[str, object]] | None = None,
        *,
        video_id: str = "video_1",
        channel_id: str = "channel_1",
        offline: bool = False,
        interval_ms: int = 60_000,
    ):
        calls: list[tuple[str, float]] = []
        selected = self.complete_messages() if messages is None else messages

        def fetch(url: str, timeout: float) -> dict[str, object]:
            calls.append((url, timeout))
            parsed = urllib.parse.urlsplit(url)
            query = urllib.parse.parse_qs(parsed.query)
            if parsed.path.endswith("/videos"):
                return {"items": [{
                    "id": video_id,
                    "snippet": {"channelId": channel_id},
                    "liveStreamingDetails": {"activeLiveChatId": "live-chat"},
                }]}
            page_token = query.get("pageToken", [None])[0]
            first_page = page_token is None and len(selected) > collector.MAX_PAGE_ITEMS
            second_page = page_token == "next-page"
            response: dict[str, object] = {
                "items": (
                    selected[:collector.MAX_PAGE_ITEMS]
                    if first_page else selected[collector.MAX_PAGE_ITEMS:]
                    if second_page else selected
                    if page_token is None else []
                ),
                "pollingIntervalMillis": 0 if first_page else interval_ms,
            }
            if first_page:
                response["nextPageToken"] = "next-page"
            else:
                response["nextPageToken"] = "tail-page"
            if offline:
                response["offlineAt"] = iso(NOW)
            return response

        return fetch, calls

    def collect(
        self,
        fetch,
        *,
        clock: FakeClock | None = None,
        abort_checker=None,
    ):
        active_clock = clock or FakeClock()
        with mock.patch.object(collector, "MAX_WAIT_SLICE_SECONDS", 7_200.0):
            result = collector.collect_youtube_live_export(
                self.auth_path,
                self.proof_path,
                self.key_path,
                self.api_path,
                fetch_json=fetch,
                monotonic=active_clock.monotonic,
                wall_time_ms=active_clock.wall,
                sleep=active_clock.sleep,
                abort_checker=abort_checker,
            )
        return (*result, active_clock)

    @staticmethod
    def export_bytes(rows: list[dict[str, object]]) -> bytes:
        return b"".join(collector._json_line(row) for row in rows)

    def test_complete_capture_is_minimized_bound_and_normalizer_compatible(self):
        fetch, calls = self.transport()
        rows, consent, receipt, clock = self.collect(fetch)
        raw = self.export_bytes(rows)

        self.assertEqual(len(rows) - 1, 300)
        self.assertEqual(receipt["actual_duration_ms"], 1_800_000)
        self.assertEqual(receipt["source_type_counts"], {
            "text": 297,
            "donation": 2,
            "system": 1,
        })
        self.assertEqual(receipt["duplicates"], 1)
        self.assertEqual(receipt["prestart"], 1)
        self.assertEqual(rows[1]["source_type"], "donation")
        self.assertIsNone(rows[1]["text"])
        self.assertEqual(rows[3]["source_type"], "system")
        self.assertIsNone(rows[3]["text"])
        collector.verify_capture_receipt(raw, consent, receipt, self.key)

        queries = [urllib.parse.parse_qs(urllib.parse.urlsplit(url).query) for url, _ in calls]
        self.assertEqual(queries[0]["part"], ["snippet,liveStreamingDetails"])
        self.assertEqual(queries[1]["part"], ["snippet"])
        requested_fields = ",".join(query["fields"][0] for query in queries)
        for forbidden in (
            "authorDetails", "authorChannelId", "displayMessage",
            "amountMicros", "currency", "profileImageUrl",
        ):
            self.assertNotIn(forbidden, requested_fields)
        serialized = raw + json.dumps(receipt, sort_keys=True).encode("utf-8")
        for forbidden in (b"testApiKey_123", b"live-chat", b"video_1"):
            self.assertNotIn(forbidden, serialized)

        export_path = self.directory / "capture.safe.jsonl"
        consent_path = self.directory / "capture.consent.json"
        allowlist_path = self.directory / "allowlist.json"
        export_path.write_bytes(raw)
        consent_path.write_text(json.dumps(consent), encoding="utf-8")
        allowlist_path.write_text(json.dumps({
            "schema_version": "airi.provider-channel-allowlist.v1",
            "entries": [{
                "provider": "youtube",
                "channel_id": self.authorization["channel_id"],
                "exporter_id": self.authorization["exporter_id"],
                "source_schema": collector.SOURCE_SCHEMA,
                "authorization_ref_sha256": self.authorization["provenance_sha256"],
                "source_slot": self.authorization["source_slot"],
                "provider_binding_hmac": self.authorization["provider_binding_hmac"],
                "not_after": self.authorization["expires_at"],
                "enabled": True,
            }],
        }), encoding="utf-8")
        capture_receipt_path = self.directory / "capture.receipt.json"
        capture_receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        normalized, derived, normalization_receipt = normalize_authorized_export(
            export_path,
            consent_path,
            self.proof_path,
            allowlist_path,
            self.key_path,
            capture_receipt_path=capture_receipt_path, now=NOW + timedelta(minutes=31),
        )
        self.assertEqual(len(normalized), 300)
        self.assertEqual(derived["source_sha256"], hashlib.sha256(
            b"".join(
                json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
                for row in normalized
            ),
        ).hexdigest())
        self.assertEqual(normalization_receipt["input_event_count"], 300)
        self.assertEqual(clock.seconds, 1_800)

        with self.assertRaises(ReplayAuthorizationError):
            normalize_authorized_export(
                export_path, consent_path, self.proof_path, allowlist_path,
                self.key_path, now=NOW + timedelta(minutes=31),
            )
        changed_consent = json.loads(json.dumps(consent))
        changed_consent["excluded_creator_names"] = ["DifferentCreator"]
        consent_path.write_text(json.dumps(changed_consent), encoding="utf-8")
        with self.assertRaises(ReplayAuthorizationError):
            normalize_authorized_export(
                export_path, consent_path, self.proof_path, allowlist_path,
                self.key_path, capture_receipt_path=capture_receipt_path,
                now=NOW + timedelta(minutes=31),
            )
        consent_path.write_text(json.dumps(consent), encoding="utf-8")
        changed_receipt = json.loads(json.dumps(receipt))
        changed_receipt["batches"] += 1
        capture_receipt_path.write_text(json.dumps(changed_receipt), encoding="utf-8")
        with self.assertRaises(ReplayAuthorizationError):
            normalize_authorized_export(
                export_path, consent_path, self.proof_path, allowlist_path,
                self.key_path, capture_receipt_path=capture_receipt_path,
                now=NOW + timedelta(minutes=31),
            )
        capture_receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        export_path.write_bytes(raw.replace(b'"source_type":"text"', b'"source_type":"textX"', 1))
        changed_consent = json.loads(json.dumps(consent))
        changed_consent["source_sha256"] = hashlib.sha256(export_path.read_bytes()).hexdigest()
        consent_path.write_text(json.dumps(changed_consent), encoding="utf-8")
        with self.assertRaises(ReplayAuthorizationError):
            normalize_authorized_export(
                export_path, consent_path, self.proof_path, allowlist_path,
                self.key_path, capture_receipt_path=capture_receipt_path,
                now=NOW + timedelta(minutes=31),
            )

    def test_final_scheduler_overrun_is_bounded_and_validated(self):
        def collect_with_final_oversleep(extra_seconds):
            clock = FakeClock()
            def sleep(seconds):
                extra = extra_seconds if clock.seconds + seconds >= 1_800 else 0
                clock.seconds += seconds + extra
                clock.wall_ms += round((seconds + extra) * 1_000)
            return self.collect(self.transport()[0], clock=clock) if extra_seconds == 0 else collector.collect_youtube_live_export(
                self.auth_path, self.proof_path, self.key_path, self.api_path,
                fetch_json=self.transport()[0], monotonic=clock.monotonic,
                wall_time_ms=clock.wall, sleep=sleep,
            )

        rows, consent, receipt = collect_with_final_oversleep(0.001)
        self.assertEqual(receipt["actual_duration_ms"], 1_800_001)
        collector.verify_capture_receipt(self.export_bytes(rows), consent, receipt, self.key)
        with self.assertRaises(collector.CaptureError):
            collect_with_final_oversleep((collector.MAX_ACTUAL_OVERRUN_MS + 1) / 1_000)

    def test_setup_time_and_event_admission_share_the_authorized_window(self):
        clock = FakeClock()
        original_read = collector._read_bounded

        def delayed_read(*args, **kwargs):
            clock.sleep(5)
            return original_read(*args, **kwargs)

        with mock.patch.object(collector, "_read_bounded", side_effect=delayed_read):
            rows, _, receipt, _ = self.collect(self.transport()[0], clock=clock)
        self.assertEqual(
            clock.wall_ms - rows[0]["exported_at_ms"],
            receipt["actual_duration_ms"],
        )
        self.assertEqual(receipt["actual_duration_ms"], 1_800_000)

        messages = [self.message(number) for number in range(300)]
        messages.append(self.message(
            300,
            timestamp=NOW + timedelta(seconds=1_800, milliseconds=1),
        ))
        clock = FakeClock()
        base_fetch, _ = self.transport(messages)

        def fetch_at_window_end(url: str, timeout: float):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            if query.get("pageToken") == ["next-page"] and clock.seconds == 0:
                clock.sleep(1_799.999)
            return base_fetch(url, timeout)

        rows, _, receipt, _ = self.collect(fetch_at_window_end, clock=clock)
        self.assertEqual(len(rows) - 1, 300)
        self.assertEqual(receipt["event_count"], 300)

    def test_authorization_provenance_and_full_interval_fail_closed(self):
        cases = (
            {"revoked": True},
            {"provider_binding_hmac": "0" * 64},
            {"provenance_sha256": "0" * 64},
            {"expires_at": iso(NOW + timedelta(minutes=30))},
            {"delete_by": iso(NOW + timedelta(days=31))},
            {"excluded_creator_names": []},
            {"duration_seconds": True},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                self.write_authorization(**changes)
                fetch = mock.Mock(side_effect=AssertionError("network must not run"))
                with self.assertRaises(collector.CaptureError):
                    self.collect(fetch)
                fetch.assert_not_called()
        self.write_authorization()

    def test_provider_mismatch_unsafe_order_early_end_and_minimum_fail(self):
        bad_video, _ = self.transport(video_id="other-video")
        with self.assertRaisesRegex(collector.CaptureError, "authorized live broadcast"):
            self.collect(bad_video)

        unsafe = [self.message(number) for number in range(300)]
        unsafe[10] = self.message(10, text="unsafe\u202etext")
        with self.assertRaisesRegex(collector.ReplayFormatError, "unsafe"):
            self.collect(self.transport(unsafe)[0])

        regressed = [self.message(number, timestamp=NOW + timedelta(seconds=1)) for number in range(300)]
        regressed[1] = self.message(1, timestamp=NOW)
        with self.assertRaisesRegex(collector.ReplayFormatError, "regressed"):
            self.collect(self.transport(regressed)[0])

        with self.assertRaisesRegex(collector.CaptureError, "ended"):
            self.collect(self.transport(offline=True)[0])
        missing_token, _ = self.transport()

        def without_page_token(url: str, timeout: float):
            response = missing_token(url, timeout)
            if urllib.parse.urlsplit(url).path.endswith("/liveChat/messages"):
                response.pop("nextPageToken", None)
            return response

        with self.assertRaisesRegex(collector.CaptureError, "unsupported or ended"):
            self.collect(without_page_token)
        blank_token, _ = self.transport()

        def with_blank_page_token(url: str, timeout: float):
            response = blank_token(url, timeout)
            if urllib.parse.urlsplit(url).path.endswith("/liveChat/messages"):
                response["nextPageToken"] = ""
            return response

        with self.assertRaisesRegex(collector.CaptureError, "unsupported or ended"):
            self.collect(with_blank_page_token)
        with self.assertRaisesRegex(collector.CaptureError, "fewer than 300"):
            self.collect(self.transport([self.message(number) for number in range(299)])[0])

    def test_transient_retry_permanent_failure_abort_and_limits_are_bounded(self):
        base_fetch, _ = self.transport()
        attempts = 0

        def transient_once(url: str, timeout: float):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise collector.TransientTransportError("sanitized")
            return base_fetch(url, timeout)

        _, _, receipt, _ = self.collect(transient_once)
        self.assertEqual(receipt["retries"], 1)

        permanent = mock.Mock(side_effect=collector.CaptureError("rejected"))
        with self.assertRaisesRegex(collector.CaptureError, "rejected"):
            self.collect(permanent)
        permanent.assert_called_once()

        checks = 0

        def abort() -> bool:
            nonlocal checks
            checks += 1
            return checks >= 3

        with self.assertRaisesRegex(collector.CaptureError, "aborted"):
            self.collect(base_fetch, abort_checker=abort)

        self.write_authorization(max_events=300)
        with self.assertRaisesRegex(collector.CaptureError, "event limit"):
            self.collect(self.transport([self.message(number) for number in range(301)])[0])
        self.write_authorization()
        with mock.patch.object(collector, "MAX_BATCHES", 0):
            with self.assertRaisesRegex(collector.CaptureError, "batch limit"):
                self.collect(base_fetch)

    def test_receipt_metadata_export_and_types_are_authenticated(self):
        rows, consent, receipt, _ = self.collect(self.transport()[0])
        raw = self.export_bytes(rows)
        mutations = []
        for field, value in (
            ("event_count", 999),
            ("batches", -1),
            ("prestart", receipt["prestart"] + 1),
            ("actual_duration_ms", 1),
            ("invalid", False),
        ):
            changed = json.loads(json.dumps(receipt))
            changed[field] = value
            mutations.append(changed)
        changed_counts = json.loads(json.dumps(receipt))
        changed_counts["source_type_counts"]["text"] = True
        mutations.append(changed_counts)
        for changed in mutations:
            with self.subTest(changed=changed):
                with self.assertRaises(collector.CaptureError):
                    collector.verify_capture_receipt(raw, consent, changed, self.key)
        with self.assertRaises(collector.CaptureError):
            collector.verify_capture_receipt(raw + b"{}\n", consent, receipt, self.key)
        with self.assertRaises(collector.CaptureError):
            collector.verify_capture_receipt(b"not-jsonl", consent, receipt, self.key)

    def test_official_transport_is_direct_sanitized_and_rejects_permanent_http(self):
        with mock.patch(
            "urllib.request.getproxies",
            return_value={"https": "http://external-proxy.invalid:8080"},
        ):
            opener = collector._build_direct_opener()
        self.assertFalse(any(
            isinstance(handler, urllib.request.ProxyHandler)
            for handler in opener.handlers
        ))

        secret_url = "https://www.googleapis.com/youtube/v3/videos?key=SECRET_KEY"

        class RejectingOpener:
            def __init__(self, status: int):
                self.status = status

            def open(self, *_args, **_kwargs):
                raise urllib.error.HTTPError(
                    secret_url,
                    self.status,
                    "provider secret",
                    {},
                    None,
                )

        with mock.patch.object(collector, "_OPENER", RejectingOpener(403)):
            with self.assertRaises(collector.CaptureError) as caught:
                collector.official_fetch_json(secret_url, 1)
        self.assertNotIn("SECRET_KEY", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

        with mock.patch.object(collector, "_OPENER", RejectingOpener(503)):
            with self.assertRaises(collector.TransientTransportError) as caught:
                collector.official_fetch_json(secret_url, 1)
        self.assertNotIn("SECRET_KEY", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

        with self.assertRaises(collector.CaptureError):
            collector.official_fetch_json("http://www.googleapis.com/youtube/v3/videos", 1)

    def test_bundle_replace_rolls_back_and_cli_rejects_outside_custody(self):
        intake = collector.HERE / "local-replay-intake"
        intake.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=intake) as temporary:
            parent = Path(temporary)
            targets = [parent / f"item-{number}.json" for number in range(3)]
            for number, target in enumerate(targets):
                target.write_bytes(f"old-{number}".encode())
            original_replace = collector.os.replace
            calls = 0

            def fail_fourth(source, target):
                nonlocal calls
                calls += 1
                if calls == 4:
                    raise OSError("synthetic replace failure")
                return original_replace(source, target)

            with mock.patch.object(collector.os, "replace", side_effect=fail_fourth):
                with self.assertRaises(OSError):
                    collector._commit_bundle([
                        (target, f"new-{number}".encode(), parent)
                        for number, target in enumerate(targets)
                    ])
            self.assertEqual(
                [target.read_bytes() for target in targets],
                [b"old-0", b"old-1", b"old-2"],
            )

        outside = self.directory / "outside.json"
        arguments = []
        for name in (
            "authorization", "provenance", "identity-key", "api-key",
            "output", "consent-output", "receipt",
        ):
            arguments.extend((f"--{name}", str(outside)))
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                collector.main(arguments)


if __name__ == "__main__":
    unittest.main()
