import gzip
import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import collect_topic_candidates as collector
import topic_review_contract as contract


POLICY = collector.SourcePolicy("source.test", "/feed.json")


def row(**changes):
    value = {"pending_schema_version": 1, "id": "candidate-001", "title": "후보토픽", "source": "synthetic source", "source_url": "https://source.test/feed.json", "published_at": "2026-01-01T00:00:00Z", "summary": "8월 12일 후보토픽 행사가 열린다.", "broadcast_line": "8월 12일 후보토픽 소식을 봤어.", "expires_at": "2099-01-01T00:00:00Z", "review": {"status": "pending", "reviewer": "", "reviewed_at": ""}}
    value.update(changes); return value


class CandidateCollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "topic-review"; self.root.mkdir()
        self.patch = mock.patch.object(contract, "TOPIC_REVIEW_ROOT", self.root); self.patch.start(); self.addCleanup(self.patch.stop)
        self.pending = self.root / "pending.jsonl"

    def fetcher(self, rows, *, redirect=None, body=None, headers=None, peer_ip="8.8.8.8", status=200):
        calls = []
        payload = body if body is not None else json.dumps(rows, ensure_ascii=False).encode()
        def fetch(url, connect, read, total):
            calls.append((url, connect, read, total))
            return collector.FetchResponse(url=url, status=status, headers=headers or {}, body=payload, peer_ip=peer_ip, redirect_to=redirect)
        return fetch, calls

    def test_disabled_cli_never_calls_or_writes(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(collector.main([]), 0)
        self.assertEqual(json.loads(output.getvalue()), {"status": "disabled", "added_count": 0, "pending_count": 0})
        self.assertFalse(self.pending.exists())

    def test_allowlist_redirect_caps_and_decompression(self):
        fetch, _ = self.fetcher([row()], redirect="https://source.test/feed.json")
        with self.assertRaises(collector.CollectionError):
            collector.collect_candidates(self.pending, (POLICY,), fetch)
        bad_fetch, _ = self.fetcher([row()], redirect="https://localhost/feed.json")
        with self.assertRaises(collector.CollectionError):
            collector.collect_candidates(self.pending, (POLICY,), bad_fetch)
        huge = gzip.compress(b"[" + b" " * (collector.MAX_DECOMPRESSED_BYTES + 2) + b"]")
        capped, _ = self.fetcher([], body=huge, headers={"content-encoding": "gzip"})
        with self.assertRaises(collector.CollectionError):
            collector.collect_candidates(self.pending, (POLICY,), capped)
        oversized, _ = self.fetcher([], body=b"x" * (collector.MAX_BODY_BYTES + 1))
        with self.assertRaises(collector.CollectionError):
            collector.collect_candidates(self.pending, (POLICY,), oversized)
        for literal, literal_policy in (
            ("https://127.0.0.1/feed.json", collector.SourcePolicy("127.0.0.1", "/feed.json")),
            ("https://[::1]/feed.json", collector.SourcePolicy("::1", "/feed.json")),
            ("https://8.8.8.8/feed.json", collector.SourcePolicy("8.8.8.8", "/feed.json")),
        ):
            with self.assertRaises(collector.CollectionError):
                collector._allowed_url(literal, literal_policy)
        private_peer, _ = self.fetcher([row()], peer_ip="127.0.0.1")
        with self.assertRaises(collector.CollectionError):
            collector.collect_candidates(self.pending, (POLICY,), private_peer)
        non_redirect, _ = self.fetcher([row()], redirect="https://source.test/feed.json", status=200)
        with self.assertRaises(collector.CollectionError):
            collector.collect_candidates(self.pending, (POLICY,), non_redirect)
        unknown_encoding, _ = self.fetcher([row()], headers={"content-encoding": "br"})
        with self.assertRaises(collector.CollectionError):
            collector.collect_candidates(self.pending, (POLICY,), unknown_encoding)
        for headers in (
            {"Content-Encoding": "br"},
            {"cOnTeNt-EnCoDiNg": "br"},
            {"Content-Encoding": "gzip", "content-encoding": "br"},
        ):
            encoded, _ = self.fetcher([row()], headers=headers)
            with self.assertRaises(collector.CollectionError):
                collector.collect_candidates(self.pending, (POLICY,), encoded)
        self.assertFalse(self.pending.exists())

    def test_dedupe_determinism_existing_preservation_and_id_collision(self):
        first, duplicate = row(), row()
        second = row(id="candidate-002", published_at="2026-01-02T00:00:00Z")
        fetch, calls = self.fetcher([first, duplicate, second])
        result = collector.collect_candidates(self.pending, (POLICY,), fetch)
        self.assertEqual(result, {"existing_count": 0, "added_count": 2, "pending_count": 2})
        original = self.pending.read_bytes()
        again, _ = self.fetcher([second, first])
        self.assertEqual(collector.collect_candidates(self.pending, (POLICY,), again)["added_count"], 0)
        self.assertEqual(self.pending.read_bytes(), original)
        self.assertEqual(calls[0][1:3], (3.0, 5.0)); self.assertGreater(calls[0][3], 0); self.assertLessEqual(calls[0][3], collector.SOURCE_TOTAL_TIMEOUT)
        collision, _ = self.fetcher([row(title="다른후보")])
        with self.assertRaises(collector.CollectionError):
            collector.collect_candidates(self.pending, (POLICY,), collision)
        self.assertEqual(self.pending.read_bytes(), original)

    def test_invalid_existing_and_pending_only_concurrent_merge(self):
        self.pending.write_text('{"bad":true}\n', encoding="utf-8")
        fetch, _ = self.fetcher([row()])
        with self.assertRaises(contract.TopicReviewError):
            collector.collect_candidates(self.pending, (POLICY,), fetch)
        self.pending.unlink()
        fetch, _ = self.fetcher([row()])
        results, failures, barrier = [], [], threading.Barrier(3)
        def merge(candidate):
            try:
                barrier.wait(); results.append(collector.collect_candidates(self.pending, (POLICY,), candidate))
            except Exception as exc:
                failures.append(exc)
        second_row = row(id="candidate-002", published_at="2026-01-02T00:00:00Z")
        second_fetch, _ = self.fetcher([second_row])
        threads = [threading.Thread(target=merge, args=(fetch,)), threading.Thread(target=merge, args=(second_fetch,))]
        [thread.start() for thread in threads]; barrier.wait(); [thread.join() for thread in threads]
        self.assertEqual(failures, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(len(contract.load_pending(self.pending)), 2)
        self.assertEqual({record["id"] for record in contract.load_pending(self.pending)}, {"candidate-001", "candidate-002"})
        self.assertFalse((self.root / ".pending.jsonl.collect.lock").exists())
        self.assertFalse((self.root / "approved-topics.json").exists())

    def test_content_free_errors_and_no_default_collection_policy(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(collector.main(["--enable-collection", "--pending", str(self.pending)]), 2)
        rendered = output.getvalue(); self.assertNotIn(str(self.pending), rendered); self.assertEqual(json.loads(rendered)["status"], "rejected")
        for candidate in ("http://source.test/feed.json", "https://127.0.0.1/feed.json", "https://source.test/other", "https://user@source.test/feed.json", "https://source.test/feed.json#x"):
            with self.assertRaises(collector.CollectionError):
                collector._allowed_url(candidate, POLICY)

    def test_deadline_and_lock_ownership_fail_closed_without_write(self):
        clock = [0.0]
        def now(): return clock[0]
        def slow(url, connect, read, remaining):
            clock[0] += 9.0
            return collector.FetchResponse(url=url, status=200, headers={}, body=json.dumps([row()]).encode(), peer_ip="8.8.8.8")
        with mock.patch.object(collector, "MONOTONIC", now):
            with self.assertRaises(collector.CollectionError):
                collector.collect_candidates(self.pending, (POLICY,), slow)
        self.assertFalse(self.pending.exists())
        lock = self.root / ".pending.jsonl.collect.lock"; lock.write_text("stale-owner", encoding="ascii")
        with mock.patch.object(collector, "LOCK_WAIT_SECONDS", 0.0):
            with self.assertRaises(collector.CollectionError):
                collector.collect_candidates(self.pending, (POLICY,), self.fetcher([row()])[0])
        self.assertTrue(lock.exists())
        lock.unlink()
        owner = collector._SidecarLock(self.pending); owner.__enter__()
        lock.write_text("other-owner", encoding="ascii")
        with self.assertRaises(collector.CollectionError):
            owner.__exit__()
        self.assertTrue(lock.exists())

        with mock.patch.object(collector.os, "write", return_value=0):
            failed_owner = collector._SidecarLock(self.pending)
            lock.unlink()
            with self.assertRaises(OSError):
                failed_owner.__enter__()
            self.assertFalse(lock.exists())


if __name__ == "__main__": unittest.main()
