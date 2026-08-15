from __future__ import annotations

from datetime import datetime, timedelta, timezone
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

import collect_youtube_live_export as collector
import prepare_youtube_live_capture as preparation
from normalize_authorized_export import ReplayAuthorizationError, _authorize_allowlist, provider_binding_hmac


NOW = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)


class PrepareYoutubeLiveCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(dir=preparation.INTAKE)
        self.directory = Path(self.temporary.name)
        self.provenance = self.directory / "provenance.txt"
        self.key = self.directory / "identity.key"
        self.provenance.write_bytes(b"written operator authorization\n")
        self.key.write_bytes(b"x" * 32)
        self.request_path = self.directory / "request.json"
        self.request = self.make_request()
        self.write_request()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def custody_relative(self, path: Path) -> str:
        return path.relative_to(preparation.HERE).as_posix()

    def make_request(self) -> dict[str, object]:
        return {
            "schema_version": preparation.REQUEST_SCHEMA,
            "operator_decision": {
                "authorization": "authorized",
                "authorization_basis": "operator_owned_broadcast",
                "authorized_at": (NOW - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                "expires_at": (NOW + timedelta(hours=3)).isoformat().replace("+00:00", "Z"),
                "delete_by": (NOW + timedelta(days=2)).isoformat().replace("+00:00", "Z"),
                "revoked": False,
                "purposes": ["local_replay_evaluation"],
            },
            "capture": {
                "provider": "youtube", "video_id": "video_123", "channel_id": "channel:1",
                "exporter_id": "operator.1", "source_slot": "channel_a", "phase": "opening",
                "duration_seconds": 1800, "max_events": 300,
                "excluded_creator_names": ["Creator"],
            },
            "custody": {
                "provenance_file": self.custody_relative(self.provenance),
                "identity_key_file": self.custody_relative(self.key),
            },
        }

    def write_request(self) -> None:
        self.request_path.write_text(json.dumps(self.request), encoding="utf-8")

    def test_generates_exact_compatible_documents_and_binding(self) -> None:
        output = self.directory / "bundle"
        _, authorization, allowlist = preparation.prepare_youtube_live_capture(self.request_path, output, now=NOW)
        self.assertEqual(set(authorization), collector._AUTH_KEYS)
        self.assertEqual(authorization["provenance_sha256"], hashlib.sha256(self.provenance.read_bytes()).hexdigest())
        expected = provider_binding_hmac(self.key.read_bytes(), provider="youtube", channel_id="channel:1", exporter_id="operator.1", source_schema=collector.SOURCE_SCHEMA, authorization_ref_sha256=authorization["provenance_sha256"], source_slot="channel_a")
        self.assertEqual(authorization["provider_binding_hmac"], expected)
        self.assertEqual(allowlist["entries"], [{"provider": "youtube", "channel_id": "channel:1", "exporter_id": "operator.1", "source_schema": collector.SOURCE_SCHEMA, "authorization_ref_sha256": authorization["provenance_sha256"], "source_slot": "channel_a", "provider_binding_hmac": expected, "not_after": self.request["operator_decision"]["expires_at"], "enabled": True}])
        loaded = collector._load_authorization(output / preparation.AUTHORIZATION_NAME, self.provenance, self.key.read_bytes(), NOW)
        self.assertEqual(loaded, authorization)
        header = {"provider": "youtube", "channel_id": "channel:1", "exporter_id": "operator.1", "source_schema": collector.SOURCE_SCHEMA}
        consent = {"provenance_sha256": authorization["provenance_sha256"], "capture_profile": {"source_slot": "channel_a", "provider_binding_hmac": expected}}
        self.assertEqual(_authorize_allowlist(output / preparation.ALLOWLIST_NAME, self.key, header, consent, NOW), self.key.read_bytes())

    def test_rejects_decisions_times_ids_and_custody_paths(self) -> None:
        cases = [
            ("operator_decision", {"revoked": True}),
            ("operator_decision", {"expires_at": (NOW + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")}),
            ("capture", {"video_id": "bad id"}),
            ("custody", {"provenance_file": "local-replay-intake/../secret"}),
        ]
        for section, changes in cases:
            with self.subTest(changes=changes):
                request = self.make_request()
                request[section].update(changes)
                self.request = request; self.write_request()
                with self.assertRaises(preparation.PreparationError):
                    preparation.prepare_youtube_live_capture(self.request_path, self.directory / ("bad" + str(len(changes))), now=NOW)

    def test_rejects_exact_keys_booleans_bounds_times_names_and_paths(self) -> None:
        for section, key in ((None, "extra"), ("operator_decision", "extra"), ("capture", "extra"), ("custody", "extra")):
            with self.subTest(section=section, kind="extra"):
                request = self.make_request()
                target = request if section is None else request[section]
                target[key] = True
                self.request = request; self.write_request()
                with self.assertRaises(preparation.PreparationError):
                    preparation.prepare_youtube_live_capture(self.request_path, self.directory / "keys", now=NOW)
            with self.subTest(section=section, kind="missing"):
                request = self.make_request()
                target = request if section is None else request[section]
                target.pop("schema_version" if section is None else next(iter(target)))
                self.request = request; self.write_request()
                with self.assertRaises(preparation.PreparationError):
                    preparation.prepare_youtube_live_capture(self.request_path, self.directory / "keys2", now=NOW)
        cases = [
            ("capture", {"duration_seconds": True}), ("capture", {"max_events": False}),
            ("capture", {"duration_seconds": 1799}), ("capture", {"duration_seconds": 7201}),
            ("capture", {"max_events": 299}), ("capture", {"max_events": 20001}),
            ("operator_decision", {"authorized_at": (NOW + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")}),
            ("operator_decision", {"expires_at": (NOW + timedelta(seconds=1800)).isoformat().replace("+00:00", "Z")}),
            ("operator_decision", {"expires_at": NOW.isoformat().replace("+00:00", "Z")}),
            ("operator_decision", {"delete_by": (NOW + timedelta(seconds=1800)).isoformat().replace("+00:00", "Z")}),
            ("operator_decision", {"delete_by": NOW.isoformat().replace("+00:00", "Z")}),
            ("operator_decision", {"delete_by": (NOW + timedelta(days=30, seconds=1)).isoformat().replace("+00:00", "Z")}),
            ("capture", {"excluded_creator_names": ["Creator", "Creator"]}),
            ("capture", {"excluded_creator_names": ["bad\nname"]}),
            ("capture", {"excluded_creator_names": [3]}),
        ]
        for section, changes in cases:
            with self.subTest(changes=changes):
                self.request = self.make_request(); self.request[section].update(changes); self.write_request()
                with self.assertRaises(preparation.PreparationError):
                    preparation.prepare_youtube_live_capture(self.request_path, self.directory / "bad-value", now=NOW)
        for value in ("/tmp/file", "C:/temp/file", "local-replay-intake\\file", "local-replay-intake/../file"):
            with self.subTest(path=value):
                self.request = self.make_request(); self.request["custody"]["provenance_file"] = value; self.write_request()
                with self.assertRaises(preparation.PreparationError):
                    preparation.prepare_youtube_live_capture(self.request_path, self.directory / "bad-path", now=NOW)

    def test_existing_output_reparse_and_publish_failure_leave_no_bundle(self) -> None:
        existing = self.directory / "existing"; existing.mkdir()
        with self.assertRaises(preparation.PreparationError):
            preparation.prepare_youtube_live_capture(self.request_path, existing, now=NOW)
        unsafe = self.directory / "unsafe"
        try:
            unsafe.symlink_to(self.directory, target_is_directory=True)
        except OSError:
            pass
        else:
            with self.assertRaises(preparation.PreparationError):
                preparation.prepare_youtube_live_capture(self.request_path, unsafe / "bundle", now=NOW)
        target = self.directory / "failed"
        with mock.patch.object(preparation.os, "rename", side_effect=OSError("failed")):
            with self.assertRaises(preparation.PreparationError):
                preparation.prepare_youtube_live_capture(self.request_path, target, now=NOW)
        self.assertFalse(target.exists())
        self.assertFalse(list(self.directory.glob(".capture-preparation-*")))
        self.assertFalse(list(self.directory.glob(".*.capture-preparation.lock")))

    def test_changed_provenance_or_key_invalidates_downstream(self) -> None:
        output = self.directory / "bundle"
        preparation.prepare_youtube_live_capture(self.request_path, output, now=NOW)
        self.provenance.write_bytes(b"changed")
        with self.assertRaises(collector.CaptureError):
            collector._load_authorization(output / preparation.AUTHORIZATION_NAME, self.provenance, self.key.read_bytes(), NOW)
        self.provenance.write_bytes(b"written operator authorization\n")
        self.key.write_bytes(b"y" * 32)
        header = {"provider": "youtube", "channel_id": "channel:1", "exporter_id": "operator.1", "source_schema": collector.SOURCE_SCHEMA}
        auth = json.loads((output / preparation.AUTHORIZATION_NAME).read_text())
        consent = {"provenance_sha256": auth["provenance_sha256"], "capture_profile": {"source_slot": "channel_a", "provider_binding_hmac": auth["provider_binding_hmac"]}}
        with self.assertRaises(ReplayAuthorizationError):
            _authorize_allowlist(output / preparation.ALLOWLIST_NAME, self.key, header, consent, NOW)

    def test_path_aliases_hardlinks_and_reparse_are_rejected(self) -> None:
        for field, path in (("provenance_file", self.key), ("identity_key_file", self.provenance), ("provenance_file", self.request_path), ("identity_key_file", self.request_path)):
            with self.subTest(field=field):
                self.request = self.make_request(); self.request["custody"][field] = self.custody_relative(path); self.write_request()
                with self.assertRaises(preparation.PreparationError):
                    preparation.prepare_youtube_live_capture(self.request_path, self.directory / "collision", now=NOW)
        alias = self.directory / "provenance-alias"
        try:
            os.link(self.provenance, alias)
        except OSError:
            self.skipTest("hard links unavailable")
        self.request = self.make_request(); self.request["custody"]["identity_key_file"] = self.custody_relative(alias); self.write_request()
        with self.assertRaises(preparation.PreparationError):
            preparation.prepare_youtube_live_capture(self.request_path, self.directory / "hard-link", now=NOW)
        for source, field in ((self.request_path, "provenance_file"), (self.request_path, "identity_key_file")):
            alias = self.directory / ("request-" + field)
            os.link(source, alias)
            self.request = self.make_request(); self.request["custody"][field] = self.custody_relative(alias); self.write_request()
            with self.assertRaises(preparation.PreparationError):
                preparation.prepare_youtube_live_capture(self.request_path, self.directory / "request-hard-link", now=NOW)
        for name, field in (("request-link", None), ("provenance-link", "provenance_file"), ("key-link", "identity_key_file")):
            link = self.directory / name
            source = self.request_path if field is None else (self.provenance if field == "provenance_file" else self.key)
            try:
                link.symlink_to(source)
            except OSError:
                continue
            self.request = self.make_request()
            if field is not None:
                self.request["custody"][field] = self.custody_relative(link); self.write_request()
                requested = self.request_path
            else:
                requested = link
            with self.assertRaises(preparation.PreparationError):
                preparation.prepare_youtube_live_capture(requested, self.directory / "link", now=NOW)

    def test_custody_limits_and_precommit_failures_clean_up(self) -> None:
        self.key.write_bytes(b"x" * 31)
        with self.assertRaises(preparation.PreparationError):
            preparation.prepare_youtube_live_capture(self.request_path, self.directory / "short-key", now=NOW)
        self.key.write_bytes(b"x" * 32)
        self.provenance.write_bytes(b"x" * (1024 * 1024 + 1))
        with self.assertRaises(preparation.PreparationError):
            preparation.prepare_youtube_live_capture(self.request_path, self.directory / "large-proof", now=NOW)
        self.provenance.write_bytes(b"written operator authorization\n")
        for side_effect in (OSError("first"), [None, OSError("second")]):
            target = self.directory / ("write-" + str(type(side_effect).__name__))
            with self.subTest(effect=side_effect), mock.patch.object(preparation, "_write_fsynced_json", side_effect=side_effect):
                with self.assertRaises(preparation.PreparationError):
                    preparation.prepare_youtube_live_capture(self.request_path, target, now=NOW)
            self.assertFalse(target.exists())
            self.assertFalse(list(self.directory.glob(".capture-preparation-*")))
            self.assertFalse(list(self.directory.glob(".*.capture-preparation.lock")))
        with mock.patch.object(preparation.os, "fsync", side_effect=[None, OSError("file-sync")]):
            with self.assertRaises(preparation.PreparationError):
                preparation.prepare_youtube_live_capture(self.request_path, self.directory / "file-sync", now=NOW)
        with mock.patch.object(preparation.os, "fsync", side_effect=OSError("lock-sync")):
            with self.assertRaises(preparation.PreparationError):
                preparation.prepare_youtube_live_capture(self.request_path, self.directory / "lock-sync", now=NOW)
        self.assertFalse(list(self.directory.glob(".*.capture-preparation.lock")))

    def test_target_race_and_post_commit_directory_sync(self) -> None:
        target = self.directory / "race"
        def create_target_then_refuse(stage: Path, destination: Path) -> None:
            destination.mkdir()
            (destination / "sentinel").write_text("keep", encoding="utf-8")
            raise FileExistsError("exists")
        with mock.patch.object(preparation.os, "rename", side_effect=create_target_then_refuse):
            with self.assertRaises(preparation.PreparationError):
                preparation.prepare_youtube_live_capture(self.request_path, target, now=NOW)
        self.assertEqual((target / "sentinel").read_text(encoding="utf-8"), "keep")
        target = self.directory / "post-commit"
        with mock.patch.object(preparation, "_fsync_directory", side_effect=[None, OSError("post")]):
            preparation.prepare_youtube_live_capture(self.request_path, target, now=NOW)
        self.assertTrue((target / preparation.AUTHORIZATION_NAME).is_file())
        self.assertTrue((target / preparation.ALLOWLIST_NAME).is_file())

    def test_cleanup_unlink_failure_is_sanitized_and_still_removes_lock(self) -> None:
        target = self.directory / "unlink-failure"
        original_unlink = Path.unlink

        def fail_only_staged_authorization(path: Path, *args, **kwargs) -> None:
            if path.name == preparation.AUTHORIZATION_NAME and path.parent.name.startswith(".capture-preparation-"):
                raise OSError("secret staged path")
            return original_unlink(path, *args, **kwargs)

        with mock.patch.object(preparation.os, "rename", side_effect=OSError("publish failed")), mock.patch.object(Path, "unlink", autospec=True, side_effect=fail_only_staged_authorization):
            with self.assertRaises(preparation.PreparationError) as caught:
                preparation.prepare_youtube_live_capture(self.request_path, target, now=NOW)
        self.assertNotIn("secret staged path", str(caught.exception))
        self.assertFalse(list(self.directory.glob(".*.capture-preparation.lock")))
        for stage in self.directory.glob(".capture-preparation-*"):
            original_unlink(stage / preparation.AUTHORIZATION_NAME, missing_ok=True)
            original_unlink(stage / preparation.ALLOWLIST_NAME, missing_ok=True)
            stage.rmdir()

    def test_cli_output_and_source_have_no_network_or_sensitive_echo(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(preparation, "prepare_youtube_live_capture", return_value=(self.directory / "bundle", {}, {})):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                preparation.main(["--request", str(self.request_path), "--output-dir", str(self.directory / "bundle")])
        captured = stdout.getvalue() + stderr.getvalue()
        for secret in ("video_123", "channel:1", str(self.key), hashlib.sha256(self.provenance.read_bytes()).hexdigest()):
            self.assertNotIn(secret, captured)
        tree = ast.parse(Path(preparation.__file__).read_text(encoding="utf-8"))
        imports = {node.names[0].name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)}
        imports.update(node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
        self.assertFalse({"urllib", "requests", "http", "socket"} & imports)

    def test_real_cli_failure_is_sanitized(self) -> None:
        self.request["capture"]["video_id"] = "secret video"
        self.request["custody"]["identity_key_file"] = self.custody_relative(self.key)
        self.write_request()
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr), self.assertRaises(SystemExit):
            preparation.main(["--request", str(self.request_path), "--output-dir", str(self.directory / "cli")])
        captured = stdout.getvalue() + stderr.getvalue()
        for secret in ("secret video", "channel:1", str(self.request_path), str(self.key), hashlib.sha256(self.provenance.read_bytes()).hexdigest()):
            self.assertNotIn(secret, captured)


if __name__ == "__main__":
    unittest.main()
