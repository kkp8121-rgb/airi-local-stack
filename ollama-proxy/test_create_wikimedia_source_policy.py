"""Synthetic tests for the explicit Wikimedia source-policy creator."""
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import create_wikimedia_source_policy as creator
import topic_discovery_contract as discovery
from topic_discovery_contract import load_source_policies
import topic_review_contract as review
from topic_review_contract import OwnershipLock, canonical_json


NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


class CreatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # The production contract permits only its own fixed review root; patch
        # it at this module boundary so tests remain synthetic and isolated.
        self.old_root = creator.review_output_path
        self.old_review_root = review.TOPIC_REVIEW_ROOT
        creator.review_output_path = lambda value: Path(value)
        review.TOPIC_REVIEW_ROOT = self.root
        self.path = self.root / "source-policies.json"

    def tearDown(self):
        creator.review_output_path = self.old_root
        review.TOPIC_REVIEW_ROOT = self.old_review_root
        self.tmp.cleanup()

    def call(self, args, values=()):
        stream = io.StringIO(); iterator = iter(values)
        code = creator.run_cli(args, input_fn=lambda _: next(iterator), output=stream, now=lambda: NOW)
        return code, json.loads(stream.getvalue())

    def args(self):
        return ["--create-wikimedia-policy", "--output", str(self.path), "--policy-id", "ko-wiki", "--reviewer", "reviewer"]

    def test_off_does_nothing(self):
        def unexpected(*_args, **_kwargs):
            raise AssertionError("default-OFF path touched an enabled dependency")

        with mock.patch.object(creator, "review_output_path", side_effect=unexpected):
            code = creator.run_cli(
                ["--output", "bad", "--unknown"],
                input_fn=unexpected,
                output=(stream := io.StringIO()),
                now=unexpected,
            )
        result = json.loads(stream.getvalue())
        self.assertEqual((code, result), (0, {"status": "disabled", "policy_count": 0}))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_each_confirmation_cancels_without_write(self):
        for values in (("no",), ("approve-source", "no"), ("approve-source", "approve-license", "other")):
            with self.subTest(values=values):
                code, result = self.call(self.args(), values)
                self.assertEqual(code, 0); self.assertEqual(result["status"], "cancelled")
                self.assertFalse(self.path.exists())

    def test_create_load_and_idempotence(self):
        values = ("approve-source", "approve-license", "ko-wiki")
        code, result = self.call(self.args(), values)
        self.assertEqual((code, result), (0, {"status": "created", "policy_count": 1}))
        loaded = load_source_policies(self.path)
        self.assertEqual(loaded["ko-wiki"]["feed_url"], creator.wikimedia.API_URL)
        self.assertEqual(self.path.read_bytes(), canonical_json({"schema_version": 1, "policies": list(loaded.values())}))
        before = self.path.read_bytes()
        code, result = self.call(self.args(), values)
        self.assertEqual((code, result), (0, {"status": "already-present", "policy_count": 1}))
        self.assertEqual(self.path.read_bytes(), before)

    def test_collision_noncanonical_and_lock_reject(self):
        values = ("approve-source", "approve-license", "ko-wiki")
        self.assertEqual(self.call(self.args(), values)[0], 0)
        changed = self.args(); changed[-1] = "other"
        self.assertEqual(self.call(changed, values)[0], 2)
        self.path.write_bytes(self.path.read_bytes() + b"\n")
        self.assertEqual(self.call(self.args(), values)[0], 2)
        self.path.write_bytes(canonical_json({"schema_version": 1, "policies": []}))
        with OwnershipLock(self.path, wait_seconds=0):
            self.assertEqual(self.call(self.args(), values)[0], 2)

    def test_duplicate_flags_and_naive_clock_reject_without_write(self):
        values = ("approve-source", "approve-license", "ko-wiki")
        duplicated = self.args() + ["--reviewer", "other"]
        self.assertEqual(self.call(duplicated, values)[0], 2)
        stream = io.StringIO()
        confirmation_values = iter(values)
        code = creator.run_cli(
            self.args(), input_fn=lambda _: next(confirmation_values), output=stream,
            now=lambda: datetime(2026, 1, 2, 3, 4, 5),
        )
        self.assertEqual(code, 2)
        self.assertFalse(self.path.exists())

    def test_partial_lock_interrupt_cleans_sidecar_and_preserves_target(self):
        values = iter(("approve-source", "approve-license", "ko-wiki"))
        original_write = review.os.write

        def interrupt_write(fd, data):
            if Path(review.OwnershipLock(self.path).path).exists():
                raise KeyboardInterrupt
            return original_write(fd, data)

        with mock.patch.object(review.os, "write", side_effect=interrupt_write):
            with self.assertRaises(KeyboardInterrupt):
                creator.run_cli(
                    self.args(), input_fn=lambda _: next(values), output=io.StringIO(),
                    now=lambda: NOW,
                )
        self.assertFalse(self.path.exists())
        self.assertFalse(review.OwnershipLock(self.path).path.exists())

    def test_release_failure_emits_one_rejected_status(self):
        values = iter(("approve-source", "approve-license", "ko-wiki"))

        class ReleaseFailureLock:
            fd = 1

            def __init__(self, *_args, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.fd = None
                raise review.TopicReviewError("lock ownership")

        stream = io.StringIO()
        with mock.patch.object(creator, "OwnershipLock", ReleaseFailureLock):
            code = creator.run_cli(
                self.args(), input_fn=lambda _: next(values), output=stream,
                now=lambda: NOW,
            )
        lines = stream.getvalue().splitlines()
        self.assertEqual(code, 2)
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), {"status": "rejected", "policy_count": 0})
        self.assertTrue(self.path.exists())


if __name__ == "__main__":
    unittest.main()
