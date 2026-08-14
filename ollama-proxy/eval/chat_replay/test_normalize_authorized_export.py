from datetime import datetime, timedelta, timezone
import ast
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chat_replay import (
    ReplayAuthorizationError,
    ReplayFormatError,
    import_private_replay,
    run_replay,
)
from normalize_authorized_export import (
    HERE,
    main,
    normalize_authorized_export,
    provider_binding_hmac,
    source_identity_hmac,
    verify_normalization_receipt,
)
import run_chat_replay


NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class AuthorizedExportNormalizerTests(unittest.TestCase):
    def make_files(self, directory, provider="chzzk", events=None, phase="opening", source_slot="channel_a"):
        export = directory / "provider-safe.jsonl"
        header = {"record_type": "header", "schema_version": "airi.authorized-provider-export.v1", "provider": provider, "channel_id": "opaque-channel", "exporter_id": "opaque-exporter", "source_schema": "provider-approved-envelope.v1", "exported_at_ms": 100}
        events = events or [
            {"record_type": "event", "provider": provider, "channel_id": "opaque-channel", "occurred_at_ms": 100, "source_type": "text", "text": "NamedCreator @viewer 10,000원 안녕"},
            {"record_type": "event", "provider": provider, "channel_id": "opaque-channel", "occurred_at_ms": 100, "source_type": "text", "text": "NamedCreator @viewer 10,000원 안녕"},
            {"record_type": "event", "provider": provider, "channel_id": "opaque-channel", "occurred_at_ms": 200, "source_type": "system", "text": None},
            {"record_type": "event", "provider": provider, "channel_id": "opaque-channel", "occurred_at_ms": 300, "source_type": "donation", "text": None},
        ]
        export.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in [header, *events]) + "\n", encoding="utf-8")
        provenance = directory / "provenance.txt"; provenance.write_text("locally recorded authorization", encoding="utf-8")
        identity_key = directory / "provider-identity.key"; identity_key.write_bytes(b"fixed-test-provider-identity-key-32")
        provenance_hash = hashlib.sha256(provenance.read_bytes()).hexdigest()
        binding = provider_binding_hmac(
            identity_key.read_bytes(), provider=provider,
            channel_id="opaque-channel", exporter_id="opaque-exporter",
            source_schema="provider-approved-envelope.v1",
            authorization_ref_sha256=provenance_hash, source_slot=source_slot,
        )
        consent = directory / "consent.json"
        write_json(consent, {"schema_version": "airi.chat-replay-consent.v2", "authorization": "authorized", "authorization_basis": "creator_or_platform_written_permission", "authorized_at": (NOW - timedelta(days=1)).isoformat().replace("+00:00", "Z"), "purposes": ["local_replay_evaluation"], "expires_at": (NOW + timedelta(days=1)).isoformat().replace("+00:00", "Z"), "delete_by": (NOW + timedelta(days=1)).isoformat().replace("+00:00", "Z"), "revoked": False, "source_sha256": hashlib.sha256(export.read_bytes()).hexdigest(), "provenance_sha256": provenance_hash, "excluded_creator_names": ["NamedCreator"], "capture_profile": {"source_slot": source_slot, "phase": phase, "provider_binding_hmac": binding}})
        allowlist = directory / "allowlist.json"
        write_json(allowlist, {"schema_version": "airi.provider-channel-allowlist.v1", "entries": [{"provider": provider, "channel_id": "opaque-channel", "exporter_id": "opaque-exporter", "source_schema": "provider-approved-envelope.v1", "authorization_ref_sha256": provenance_hash, "source_slot": source_slot, "provider_binding_hmac": binding, "not_after": (NOW + timedelta(days=1)).isoformat().replace("+00:00", "Z"), "enabled": True}]})
        return export, consent, provenance, allowlist, identity_key

    def test_all_providers_normalize_and_derived_consent_imports(self):
        for provider in ("chzzk", "soop", "youtube"):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp); export, consent, provenance, allowlist, identity_key = self.make_files(directory, provider)
                rows, derived, receipt = normalize_authorized_export(export, consent, provenance, allowlist, identity_key, now=NOW)
                self.assertEqual([row["kind"] for row in rows], ["chat", "chat", "noise", "donation"])
                self.assertEqual([row["timestamp_ms"] for row in rows], [100, 100, 200, 300])
                self.assertEqual(rows[0], rows[1])
                self.assertNotIn("NamedCreator", rows[0]["text"]); self.assertNotIn("@viewer", rows[0]["text"]); self.assertNotIn("10,000", rows[0]["text"])
                self.assertEqual(rows[2]["text"], "[시스템 메시지]")
                self.assertEqual(rows[3]["text"], "[후원 이벤트]")
                self.assertNotIn("opaque-channel", json.dumps(receipt)); self.assertNotIn("opaque-exporter", json.dumps(receipt))
                self.assertEqual(receipt["schema_version"], "airi.authorized-provider-normalization-receipt.v2")
                self.assertEqual(len(receipt["source_identity_hmac"]), 64)
                self.assertFalse({"channel_sha256", "exporter_sha256", "input_sha256", "output_sha256"} & set(receipt))
                self.assertEqual(len(receipt["normalization_hmac_sha256"]), 64)
                normalized = directory / "normalized.jsonl"
                normalized.write_bytes(b"".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n" for row in rows))
                derived_path = directory / "derived.json"; write_json(derived_path, derived)
                replay = import_private_replay(normalized, derived_path, provenance, now=NOW)
                self.assertEqual(len(replay), 4); self.assertEqual(replay[1].duplicate_of_seq, 1)

    def test_strict_envelope_rejections(self):
        cases = [
            ("unknown", lambda h, e: h.update(extra=True)),
            ("identity", lambda h, e: e[0].update(viewer_id="x")),
            ("cross-channel", lambda h, e: e[0].update(channel_id="other")),
            ("decreasing", lambda h, e: e[1].update(occurred_at_ms=99)),
            ("null-text", lambda h, e: e[0].update(text=None)),
            ("unsafe", lambda h, e: e[0].update(text="bad\u202e")),
        ]
        for name, change in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp); export, consent, provenance, allowlist, identity_key = self.make_files(directory)
                records = [json.loads(x) for x in export.read_text(encoding="utf-8").splitlines()]; change(records[0], records[1:])
                export.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in records), encoding="utf-8")
                # Rebind only to make this a format test, not a stale-consent test.
                data = json.loads(consent.read_text(encoding="utf-8")); data["source_sha256"] = hashlib.sha256(export.read_bytes()).hexdigest(); write_json(consent, data)
                with self.assertRaises(ReplayFormatError): normalize_authorized_export(export, consent, provenance, allowlist, identity_key, now=NOW)

    def test_source_identity_is_stable_and_domain_separated(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            first_dir = directory / "first"; first_dir.mkdir()
            second_dir = directory / "second"; second_dir.mkdir()
            first = self.make_files(first_dir)
            different_events = [{
                "record_type": "event", "provider": "chzzk",
                "channel_id": "opaque-channel", "occurred_at_ms": 400,
                "source_type": "text", "text": "a different capture",
            }]
            second = self.make_files(second_dir, events=different_events, phase="middle")
            first_receipt = normalize_authorized_export(*first, now=NOW)[2]
            second_receipt = normalize_authorized_export(*second, now=NOW)[2]
            self.assertEqual(
                first_receipt["source_identity_hmac"],
                second_receipt["source_identity_hmac"],
            )
            self.assertNotEqual(
                first_receipt["normalization_hmac_sha256"],
                second_receipt["normalization_hmac_sha256"],
            )

            key = first[-1].read_bytes()
            baseline = source_identity_hmac(
                key, provider="chzzk", channel_id="opaque-channel",
            )
            self.assertNotEqual(baseline, source_identity_hmac(
                key, provider="chzzk", channel_id="other-channel",
            ))
            self.assertNotEqual(baseline, source_identity_hmac(
                key, provider="soop", channel_id="opaque-channel",
            ))

            third_dir = directory / "third"; third_dir.mkdir()
            third = self.make_files(third_dir, source_slot="channel_b")
            third_receipt = normalize_authorized_export(*third, now=NOW)[2]
            self.assertEqual(
                baseline,
                third_receipt["source_identity_hmac"],
                "campaign slots must not make one raw channel look distinct",
            )

    def test_authorization_and_allowlist_fail_closed(self):
        for mode in ("revoked", "missing", "duplicate", "expired", "disabled", "reference", "binding", "consent-binding", "wrong-key"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp); export, consent, provenance, allowlist, identity_key = self.make_files(directory)
                if mode == "revoked":
                    data = json.loads(consent.read_text()); data["revoked"] = True; write_json(consent, data)
                elif mode == "missing":
                    write_json(allowlist, {"schema_version": "airi.provider-channel-allowlist.v1", "entries": []})
                else:
                    data = json.loads(allowlist.read_text()); entry = data["entries"][0]
                    if mode == "duplicate": data["entries"].append(dict(entry))
                    elif mode == "expired": entry["not_after"] = (NOW - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
                    elif mode == "disabled": entry["enabled"] = False
                    elif mode == "reference": entry["authorization_ref_sha256"] = "0" * 64
                    elif mode == "binding": entry["provider_binding_hmac"] = "0" * 64
                    elif mode == "consent-binding":
                        consent_data = json.loads(consent.read_text()); consent_data["capture_profile"]["provider_binding_hmac"] = "0" * 64; write_json(consent, consent_data)
                    else:
                        identity_key.write_bytes(b"different-provider-identity-key-32!!")
                    write_json(allowlist, data)
                with self.assertRaises(ReplayAuthorizationError): normalize_authorized_export(export, consent, provenance, allowlist, identity_key, now=NOW)

    def test_header_identifiers_and_all_donation_wording_never_reach_rows_or_receipt(self):
        variants = ("$1,000 감사합니다", "USD 1,000", "후원 5000", "10000 points")
        for wording in variants:
            with self.subTest(wording=wording), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                events = [
                    {"record_type": "event", "provider": "chzzk", "channel_id": "opaque-channel", "occurred_at_ms": 100, "source_type": "text", "text": "opaque-channel opaque-exporter 안녕"},
                    {"record_type": "event", "provider": "chzzk", "channel_id": "opaque-channel", "occurred_at_ms": 200, "source_type": "donation", "text": wording},
                ]
                export, consent, provenance, allowlist, identity_key = self.make_files(directory, events=events)
                rows, _, receipt = normalize_authorized_export(export, consent, provenance, allowlist, identity_key, now=NOW)
                serialized = json.dumps({"rows": rows, "receipt": receipt}, ensure_ascii=False)
                self.assertNotIn("opaque-channel", serialized)
                self.assertNotIn("opaque-exporter", serialized)
                self.assertNotIn(wording, serialized)
                self.assertEqual(rows[1]["text"], "[후원 이벤트]")

    def test_raw_provider_shapes_and_format_characters_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            export, consent, provenance, allowlist, identity_key = self.make_files(directory)
            raw_provider_shape = {"kind": "youtube#liveChatMessage", "snippet": {"publishedAt": "2026-08-15T00:00:00Z"}}
            export.write_text(json.dumps(raw_provider_shape), encoding="utf-8")
            data = json.loads(consent.read_text()); data["source_sha256"] = hashlib.sha256(export.read_bytes()).hexdigest(); write_json(consent, data)
            with self.assertRaises(ReplayFormatError):
                normalize_authorized_export(export, consent, provenance, allowlist, identity_key, now=NOW)

            export, consent, provenance, allowlist, identity_key = self.make_files(directory)
            records = [json.loads(line) for line in export.read_text(encoding="utf-8").splitlines()]
            records[1]["text"] = "zero\u200bwidth"
            export.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in records), encoding="utf-8")
            data = json.loads(consent.read_text()); data["source_sha256"] = hashlib.sha256(export.read_bytes()).hexdigest(); write_json(consent, data)
            with self.assertRaises(ReplayFormatError):
                normalize_authorized_export(export, consent, provenance, allowlist, identity_key, now=NOW)

    def test_module_has_no_network_imports(self):
        tree = ast.parse((Path(__file__).parent / "normalize_authorized_export.py").read_text(encoding="utf-8"))
        forbidden = {"requests", "urllib", "http", "socket", "aiohttp", "webbrowser"}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name.split(".")[0] for alias in node.names] if isinstance(node, ast.Import) else [(node.module or "").split(".")[0]]
                self.assertFalse(set(names) & forbidden)

    def test_cli_writes_only_ignored_atomic_bundle_compatible_with_importer(self):
        intake = HERE / "local-replay-intake"
        reports = HERE / "reports"
        intake.mkdir(exist_ok=True)
        reports.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=intake) as intake_temp, tempfile.TemporaryDirectory(dir=reports) as report_temp:
            directory = Path(intake_temp)
            export, consent, provenance, allowlist, identity_key = self.make_files(directory)
            normalized = directory / "normalized.jsonl"
            derived = directory / "normalized.consent.json"
            receipt = Path(report_temp) / "normalization-receipt.json"
            result = main([
                "--input", str(export), "--consent", str(consent),
                "--provenance", str(provenance), "--allowlist", str(allowlist),
                "--identity-key", str(identity_key), "--output", str(normalized),
                "--derived-consent-output", str(derived), "--receipt", str(receipt),
            ], now=NOW)
            self.assertEqual(result, 0)
            events = import_private_replay(normalized, derived, provenance, now=NOW)
            self.assertEqual(len(events), 4)
            verified_profile = verify_normalization_receipt(
                normalized, derived, provenance, receipt, identity_key,
                expected_event_count=4, now=NOW,
            )
            serialized_receipt = receipt.read_text(encoding="utf-8")
            receipt_value = json.loads(serialized_receipt)
            self.assertEqual(verified_profile, {
                "capture_profile": {"source_slot": "channel_a", "phase": "opening"},
                "provider": "chzzk",
                "source_identity_hmac": receipt_value["source_identity_hmac"],
                "exact_capture_hmac": receipt_value["normalization_hmac_sha256"],
            })
            self.assertNotIn("NamedCreator", serialized_receipt)
            self.assertNotIn("opaque-channel", serialized_receipt)
            self.assertNotIn("opaque-exporter", serialized_receipt)
            self.assertNotIn("@viewer", serialized_receipt)
            self.assertNotIn("10,000", serialized_receipt)

            changed = json.loads(serialized_receipt)
            changed["phase"] = "middle"
            write_json(receipt, changed)
            with self.assertRaises(ReplayAuthorizationError):
                verify_normalization_receipt(
                    normalized, derived, provenance, receipt, identity_key,
                    expected_event_count=4, now=NOW,
                )

            changed = json.loads(serialized_receipt)
            changed["source_identity_hmac"] = "0" * 64
            write_json(receipt, changed)
            with self.assertRaises(ReplayAuthorizationError):
                verify_normalization_receipt(
                    normalized, derived, provenance, receipt, identity_key,
                    expected_event_count=4, now=NOW,
                )

            # Restore the receipt and prove the offline runner requires and
            # consumes the same HMAC-bound normalization evidence.
            write_json(receipt, json.loads(serialized_receipt))
            replay_report = Path(report_temp) / "replay-report.json"
            self.assertEqual(run_chat_replay.main([
                "--input", str(normalized), "--consent", str(derived),
                "--provenance", str(provenance),
                "--normalization-receipt", str(receipt),
                "--identity-key", str(identity_key),
                "--report", str(replay_report),
            ], now=NOW), 0)
            report_value = json.loads(replay_report.read_text(encoding="utf-8"))
            self.assertEqual(report_value["capture_profile"], {
                "source_slot": "channel_a", "phase": "opening",
            })
            self.assertEqual(report_value["event_count"], 4)

    def test_20000_event_authorized_export_replays_with_bounded_public_report(self):
        """Exercise the advertised long offline path without retaining an artifact."""
        event_count = 20_000
        duration_ms = 7_200_000
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            events = [
                {
                    "record_type": "event",
                    "provider": "chzzk",
                    "channel_id": "opaque-channel",
                    "occurred_at_ms": (index - 1) * duration_ms // (event_count - 1),
                    "source_type": "donation" if index % 1_000 == 0 else "text",
                    "text": None if index % 1_000 == 0 else f"e{index:05d}",
                }
                for index in range(1, event_count + 1)
            ]
            export, consent, provenance, allowlist, identity_key = self.make_files(
                directory, events=events,
            )
            rows, derived, receipt = normalize_authorized_export(
                export, consent, provenance, allowlist, identity_key, now=NOW,
            )
            self.assertEqual(len(rows), event_count)
            self.assertEqual(receipt["input_event_count"], event_count)
            self.assertEqual(receipt["output_event_count"], event_count)

            normalized = directory / "normalized.jsonl"
            normalized.write_bytes(b"".join(
                json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
                for row in rows
            ))
            derived_path = directory / "normalized.consent.json"
            write_json(derived_path, derived)
            imported = import_private_replay(normalized, derived_path, provenance, now=NOW)
            self.assertEqual(len(imported), event_count)
            self.assertEqual(imported[0].offset_ms, 0)
            self.assertEqual(imported[-1].offset_ms, duration_ms)

            callback_seqs = []
            report = run_replay(
                imported,
                lambda _text, event: callback_seqs.append(event.seq) or "ok",
                report_hmac_key=b"load-test-report-hmac-key-32-bytes",
            )
            self.assertEqual(report["event_count"], event_count)
            self.assertEqual(report["flow"]["duration_ms"], duration_ms)
            self.assertEqual(report["response_sampling"]["fixed_5s_batch_count"], 1_441)
            self.assertEqual(report["response_sampling"]["selected_event_count"], 20)
            self.assertEqual(report["response_count"], 20)
            self.assertEqual(report["delivered_count"], 20)
            self.assertEqual(len(callback_seqs), 20)
            self.assertLessEqual(len(callback_seqs), duration_ms // 5_000 + 1)
            self.assertLess(
                len(json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")),
                64 * 1024,
            )
