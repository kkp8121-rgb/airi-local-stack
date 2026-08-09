import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import collect_topic_candidates as collector
import topic_discovery_contract as discovery
import topic_review_contract as contract


def policy() -> dict:
    return {
        "policy_id": "synthetic-policy",
        "source_kind": "feed",
        "source": "synthetic source",
        "feed_url": "https://feed.test/list",
        "article_host": "source.test",
        "article_path_prefix": "/item/",
        "license": {
            "spdx": "CC-BY-4.0",
            "license_url": "https://license.test/cc",
            "attribution": "synthetic attribution",
            "attribution_url": "https://source.test/about",
        },
        "approved": True,
        "reviewer": "policy-reviewer",
        "reviewed_at": "2026-01-01T00:00:00Z",
    }


def raw_record(number: int = 1, **changes) -> dict:
    source_policy = policy()
    published = f"2026-01-{number:02d}T00:00:00Z"
    value = {
        "discovery_schema_version": 1,
        "discovery_id": "",
        "source_policy_id": source_policy["policy_id"],
        "source_kind": source_policy["source_kind"],
        "source": source_policy["source"],
        "feed_url": source_policy["feed_url"],
        "source_url": f"https://source.test/item/{number}",
        "published_at": published,
        "discovered_at": f"2026-01-{number:02d}T01:00:00Z",
        "source_title": f"합성 원문 제목 {number}",
        "source_snippet": f"합성 원문 요약 {number}",
        "license": source_policy["license"],
        "source_body_sha256": f"{number:x}" * 64,
        "source_policy_sha256": discovery.policy_sha256(source_policy),
    }
    value.update(changes)
    value["discovery_id"] = discovery.discovery_id(
        value["source_policy_id"],
        value["source_url"],
        value["published_at"],
    )
    return value


class CandidateCollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "topic-review"
        self.root.mkdir()
        self.root_patch = mock.patch.object(contract, "TOPIC_REVIEW_ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.policies = self.root / "source-policies.json"
        self.raw = self.root / "raw.jsonl"
        self.policies.write_text(
            json.dumps({"schema_version": 1, "policies": [policy()]}),
            encoding="utf-8",
        )

    def test_disabled_and_standalone_enabled_cli_never_write(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(collector.main([]), 0)
        self.assertEqual(
            json.loads(output.getvalue()),
            {"status": "disabled", "added_count": 0, "raw_count": 0},
        )
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                collector.main(
                    [
                        "--enable-collection",
                        "--raw-discoveries",
                        str(self.raw),
                        "--source-policies",
                        str(self.policies),
                    ]
                ),
                2,
            )
        self.assertEqual(json.loads(output.getvalue())["status"], "rejected")
        self.assertFalse(self.raw.exists())

    def test_removed_pending_collector_always_fails_closed(self):
        pending = self.root / "pending.jsonl"
        with self.assertRaises(collector.CollectionError):
            collector.collect_candidates(pending, (), object())
        self.assertFalse(pending.exists())

    def test_raw_merge_deduplicates_and_preserves_on_collision(self):
        first = raw_record(1)
        second = raw_record(2)
        result = collector.collect_raw_discoveries(
            self.raw,
            self.policies,
            [first, first, second],
        )
        self.assertEqual(result, {"raw_count": 2, "added_count": 2})
        original = self.raw.read_bytes()
        self.assertEqual(
            collector.collect_raw_discoveries(
                self.raw,
                self.policies,
                [second, first],
            ),
            {"raw_count": 2, "added_count": 0},
        )
        self.assertEqual(self.raw.read_bytes(), original)
        changed = raw_record(1, source_title="변조된 제목")
        with self.assertRaises(collector.CollectionError):
            collector.collect_raw_discoveries(self.raw, self.policies, [changed])
        self.assertEqual(self.raw.read_bytes(), original)

    def test_policy_revision_and_invalid_existing_fail_without_overwrite(self):
        collector.collect_raw_discoveries(
            self.raw,
            self.policies,
            [raw_record(1)],
        )
        original = self.raw.read_bytes()
        changed_policy = policy()
        changed_policy["reviewed_at"] = "2026-01-02T00:00:00Z"
        self.policies.write_text(
            json.dumps({"schema_version": 1, "policies": [changed_policy]}),
            encoding="utf-8",
        )
        with self.assertRaises(contract.TopicReviewError):
            collector.collect_raw_discoveries(self.raw, self.policies, [])
        self.assertEqual(self.raw.read_bytes(), original)

    def test_concurrent_distinct_raw_merges_are_serialized(self):
        results: list[dict[str, int]] = []
        failures: list[Exception] = []
        barrier = threading.Barrier(3)

        def merge(record: dict) -> None:
            try:
                barrier.wait()
                results.append(
                    collector.collect_raw_discoveries(
                        self.raw,
                        self.policies,
                        [record],
                    )
                )
            except Exception as exc:  # pragma: no cover - asserted below
                failures.append(exc)

        threads = [
            threading.Thread(target=merge, args=(raw_record(1),)),
            threading.Thread(target=merge, args=(raw_record(2),)),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(failures, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(len(discovery.load_raw(self.raw, self.policies)), 2)
        self.assertFalse((self.root / ".raw.jsonl.lock").exists())

    def test_lock_stale_partial_and_replaced_owner_fail_closed(self):
        lock_path = self.root / ".raw.jsonl.lock"
        lock_path.write_text("stale-owner", encoding="ascii")
        with self.assertRaises(contract.TopicReviewError):
            with contract.OwnershipLock(self.raw, wait_seconds=0):
                pass
        self.assertEqual(lock_path.read_text(encoding="ascii"), "stale-owner")
        lock_path.unlink()

        with mock.patch.object(contract.os, "write", return_value=0):
            owner = contract.OwnershipLock(self.raw)
            with self.assertRaises(OSError):
                owner.__enter__()
        self.assertFalse(lock_path.exists())

        owner = contract.OwnershipLock(self.raw)
        owner.__enter__()
        lock_path.write_text("replacement-owner", encoding="ascii")
        with self.assertRaises(contract.TopicReviewError):
            owner.__exit__()
        self.assertEqual(
            lock_path.read_text(encoding="ascii"),
            "replacement-owner",
        )


if __name__ == "__main__":
    unittest.main()
