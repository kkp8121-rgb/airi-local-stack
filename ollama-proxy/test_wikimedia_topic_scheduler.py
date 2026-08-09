"""Synthetic-only tests for the opt-in Wikimedia scheduler."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import topic_review_contract as contract
import wikimedia_topic_scheduler as scheduler


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "topic-review"
        self.root.mkdir()
        patch = mock.patch.object(contract, "TOPIC_REVIEW_ROOT", self.root)
        patch.start(); self.addCleanup(patch.stop)
        self.args = ["--enable-wikimedia-schedule", "--source-policies", str(self.root / "source-policies.json"),
                     "--raw-discoveries", str(self.root / "raw.jsonl"), "--cache", str(self.root / ".wikimedia-topic-cache.json"),
                     "--policy-id", "ko-wiki", "--user-agent", "agent/1 (https://contact.example/)"]

    def statuses(self, output):
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertTrue(all(set(row) == {"status"} and row["status"] in {"disabled", "complete", "rejected", "stopped"} for row in rows))
        return [row["status"] for row in rows]

    def test_off_is_inert(self):
        for arguments in ([], ["--interval", "not-a-number"], ["--unknown", "value"]):
            with self.subTest(arguments=arguments):
                output = io.StringIO()
                with mock.patch.object(scheduler, "collect_wikimedia") as collect, mock.patch.object(scheduler.time, "monotonic") as clock, mock.patch.object(scheduler.time, "sleep") as sleep:
                    self.assertEqual(scheduler.run_cli(arguments, output=output), 0)
                self.assertEqual(self.statuses(output), ["disabled"])
                collect.assert_not_called(); clock.assert_not_called(); sleep.assert_not_called()
                self.assertEqual(list(self.root.iterdir()), [])

    def test_enabled_passes_exact_adapter_arguments(self):
        output = io.StringIO()
        with mock.patch.object(scheduler, "collect_wikimedia", side_effect=KeyboardInterrupt) as collect:
            self.assertEqual(scheduler.run_cli(self.args, output=output), 0)
        self.assertEqual(self.statuses(output), ["stopped"])
        self.assertEqual(collect.call_args.kwargs, {"policies_path": self.args[2], "raw_path": self.args[4], "cache_path": self.args[6], "policy_id": "ko-wiki", "user_agent": self.args[10]})
        self.assertEqual(list(self.root.iterdir()), [])

    def test_interrupt_immediately_after_lock_acquisition_removes_sidecar(self):
        output = io.StringIO()
        original_enter = contract.OwnershipLock.__enter__

        def interrupt_after_acquire(lock):
            original_enter(lock)
            raise KeyboardInterrupt

        with mock.patch.object(
            contract.OwnershipLock,
            "__enter__",
            interrupt_after_acquire,
        ):
            self.assertEqual(scheduler.run_cli(self.args, output=output), 0)
        self.assertEqual(self.statuses(output), ["stopped"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_serial_success_failure_retry(self):
        output, calls, sleeps = io.StringIO(), [], []
        active = [False]
        def collect():
            self.assertFalse(active[0]); active[0] = True; calls.append(1); active[0] = False
            if len(calls) == 2: raise ValueError("synthetic")
            return {"raw_count": len(calls), "added_count": 1}
        self.assertEqual(scheduler.run_scheduler(collect=collect, interval=900, retry_interval=60, monotonic=lambda: 1.0, sleep=sleeps.append, output=output, max_cycles=3), 3)
        self.assertEqual(self.statuses(output), ["complete", "rejected", "complete"])
        self.assertEqual(sleeps, [900.0, 60.0])

    def test_invalid_collector_result_is_rejected_and_retried(self):
        output, sleeps = io.StringIO(), []
        self.assertEqual(
            scheduler.run_scheduler(
                collect=lambda: {"raw_count": True, "added_count": 0},
                interval=900,
                retry_interval=60,
                monotonic=lambda: 1.0,
                sleep=sleeps.append,
                output=output,
                max_cycles=2,
            ),
            2,
        )
        self.assertEqual(self.statuses(output), ["rejected", "rejected"])
        self.assertEqual(sleeps, [60.0])

    def test_unexpected_collector_bug_stops_instead_of_retrying(self):
        output = io.StringIO()
        with mock.patch.object(
            scheduler,
            "collect_wikimedia",
            side_effect=TypeError("synthetic implementation bug"),
        ):
            self.assertEqual(scheduler.run_cli(self.args, output=output), 2)
        self.assertEqual(self.statuses(output), ["rejected"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_duplicate_owner_fails_closed_and_removes_only_lock(self):
        target = scheduler.scheduler_lock_target(self.args[6])
        output = io.StringIO()
        with contract.OwnershipLock(target, wait_seconds=0):
            self.assertEqual(scheduler.run_cli(self.args, output=output), 2)
        self.assertEqual(self.statuses(output), ["rejected"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_bad_interval_rejected_without_collector_or_state(self):
        output = io.StringIO()
        with mock.patch.object(scheduler, "collect_wikimedia") as collect:
            self.assertEqual(scheduler.run_cli(self.args + ["--interval", "899"], output=output), 2)
        self.assertEqual(self.statuses(output), ["rejected"]); collect.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
