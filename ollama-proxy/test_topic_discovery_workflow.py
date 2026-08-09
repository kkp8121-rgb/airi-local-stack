import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import compile_approved_topics as compiler
import curate_raw_topics as curate
import review_pending_topics as reviewer
import topic_discovery_contract as discovery
import topic_review_contract as contract


def policy():
    return {"schema_version": 1, "policies": [{"policy_id": "p1", "source_kind": "feed", "source": "synthetic source", "feed_url": "https://feed.test/list", "article_host": "source.test", "article_path_prefix": "/item", "license": {"spdx": "CC-BY-4.0", "license_url": "https://license.test/cc", "attribution": "synthetic", "attribution_url": "https://source.test/about"}, "approved": True, "reviewer": "policy-reviewer", "reviewed_at": "2026-01-01T00:00:00Z"}]}


def raw(**changes):
    source_policy = policy()["policies"][0]
    value = {"discovery_schema_version": 1, "discovery_id": "", "source_policy_id": "p1", "source_kind": "feed", "source": "synthetic source", "feed_url": "https://feed.test/list", "source_url": "https://source.test/item/1", "published_at": "2026-01-01T00:00:00Z", "discovered_at": "2026-01-01T01:00:00Z", "source_title": "원본 제목", "source_snippet": "원본 요약", "license": source_policy["license"], "source_body_sha256": "a" * 64, "source_policy_sha256": discovery.policy_sha256(source_policy)}
    value.update(changes)
    if "published_at" in changes and "discovered_at" not in changes:
        value["discovered_at"] = changes["published_at"].replace("T00:00:00Z", "T01:00:00Z")
    value["discovery_id"] = discovery.discovery_id(value["source_policy_id"], value["source_url"], value["published_at"])
    return value


def inputs(values):
    iterator = iter(values)
    def read(_):
        try: return next(iterator)
        except StopIteration as exc: raise EOFError from exc
    return read


class DiscoveryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "topic-review"; self.root.mkdir()
        self.patch = mock.patch.object(contract, "TOPIC_REVIEW_ROOT", self.root); self.patch.start(); self.addCleanup(self.patch.stop)
        self.policies = self.root / "source-policies.json"; self.raw = self.root / "raw.jsonl"; self.cur = self.root / "cur.jsonl"; self.pending = self.root / "pending.jsonl"
        self.policies.write_text(json.dumps(policy()), encoding="utf-8")

    def write(self, path, rows): path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    def curate_rows(self, values):
        return curate.run_cli(["--source-policies", str(self.policies), "--raw-discoveries", str(self.raw), "--curations", str(self.cur), "--pending", str(self.pending), "--curator", "curator-a"], input_fn=inputs(values), output=io.StringIO(), error=io.StringIO())

    def test_policy_binding_and_literal_ip_reject(self):
        self.write(self.raw, [raw()]); self.assertEqual(len(discovery.load_raw(self.raw, self.policies)), 1)
        wrong_name = self.root / "policies.json"
        wrong_name.write_text(json.dumps(policy()), encoding="utf-8")
        with self.assertRaises(contract.TopicReviewError):
            discovery.load_source_policies(wrong_name)
        for changed in ({"source": "other"}, {"feed_url": "https://other.test/x"}, {"license": {}}, {"source_url": "https://127.0.0.1/item/1"}, {"source_url": "https://[::1]/item/1"}, {"source_url": "https://source.test:444/item/1"}, {"source_policy_sha256": "0" * 64}, {"discovered_at": "2099-01-01T00:00:00Z"}, {"published_at": "2026-01-02T00:00:00Z", "discovered_at": "2026-01-01T00:00:00Z"}):
            self.write(self.raw, [raw(**changed)])
            with self.assertRaises(contract.TopicReviewError): discovery.load_raw(self.raw, self.policies)
        for unsafe_url in (
            "https://source.test/item/1\x1b",
            "https://source.test/item/1\r\nnext",
            "https://source.test/item/1\u202ehidden",
        ):
            self.write(self.raw, [raw(source_url=unsafe_url)])
            with self.assertRaises(contract.TopicReviewError):
                discovery.load_raw(self.raw, self.policies)
        for field, value in (
            ("feed_url", "https://feed.test/list\u202e"),
            ("article_path_prefix", "/item\x1b"),
        ):
            changed_policy = policy()
            changed_policy["policies"][0][field] = value
            self.policies.write_text(json.dumps(changed_policy), encoding="utf-8")
            with self.assertRaises(contract.TopicReviewError):
                discovery.load_source_policies(self.policies)
        self.policies.write_text(json.dumps(policy()), encoding="utf-8")

    def test_curate_reject_skip_display_and_partial_state(self):
        second = raw(source_url="https://source.test/item/2", published_at="2026-01-02T00:00:00Z")
        third = raw(source_url="https://source.test/item/3", published_at="2026-01-03T00:00:00Z")
        self.write(self.raw, [raw(), second, third])
        output = io.StringIO()
        code = curate.run_cli(["--source-policies", str(self.policies), "--raw-discoveries", str(self.raw), "--curations", str(self.cur), "--pending", str(self.pending), "--curator", "curator-a"], input_fn=inputs(["curate", "pending-1", "후보토픽", "8월 12일 후보토픽 행사", "8월 12일 후보토픽 소식을 봤어.", "2099-01-01T00:00:00Z", "yes", "reject", "reason", "yes", "skip"]), output=output, error=io.StringIO())
        self.assertEqual(code, 0); self.assertIn("source_title", output.getvalue())
        self.assertEqual(len(contract.load_pending(self.pending)), 1)
        self.assertEqual(len(discovery.load_curated_pending(self.raw, self.policies, self.cur, self.pending)), 1)
        self.pending.unlink()
        with self.assertRaises(contract.TopicReviewError): discovery.load_curated_pending(self.raw, self.policies, self.cur, self.pending)

    def test_cancel_mutation_repair_and_paired_rejection(self):
        self.write(self.raw, [raw()])
        self.assertEqual(self.curate_rows([]), 0); self.assertFalse(self.cur.exists())
        self.assertEqual(self.curate_rows(["curate", "pending-1", "후보토픽", "8월 12일 후보토픽 행사", "8월 12일 후보토픽 소식을 봤어.", "2099-01-01T00:00:00Z", "yes"]), 0)
        original = self.cur.read_bytes(); self.pending.unlink()
        self.assertEqual(curate.run_cli(["--source-policies", str(self.policies), "--raw-discoveries", str(self.raw), "--curations", str(self.cur), "--pending", str(self.pending), "--repair-from-curations"], output=io.StringIO(), error=io.StringIO()), 0)
        self.assertEqual(self.cur.read_bytes(), original)
        original_pending = self.pending.read_bytes()
        self.assertEqual(curate.run_cli(["--source-policies", str(self.policies), "--raw-discoveries", str(self.raw), "--curations", str(self.cur), "--pending", str(self.pending), "--repair-from-curations"], output=io.StringIO(), error=io.StringIO()), 0)
        self.assertEqual(self.pending.read_bytes(), original_pending)
        self.pending.write_bytes(original_pending + b"\n")
        tampered_pending = self.pending.read_bytes()
        self.assertEqual(curate.run_cli(["--source-policies", str(self.policies), "--raw-discoveries", str(self.raw), "--curations", str(self.cur), "--pending", str(self.pending), "--repair-from-curations"], output=io.StringIO(), error=io.StringIO()), 2)
        self.assertEqual(self.pending.read_bytes(), tampered_pending)
        self.pending.write_bytes(original_pending)
        self.write(self.raw, [raw(source_snippet="변경됨")])
        self.assertEqual(reviewer.run_cli(["--pending", str(self.pending), "--decisions", str(self.root / "d.jsonl"), "--source-policies", str(self.policies), "--raw-discoveries", str(self.raw), "--curations", str(self.cur), "--status"], output=io.StringIO(), error=io.StringIO()), 2)
        with self.assertRaises(contract.TopicReviewError): compiler.compile_board(str(self.pending), str(self.root / "d.jsonl"), str(self.root / "out.json"), source_policies=str(self.policies), raw_discoveries=str(self.raw), curations=str(self.cur))

    def test_unbound_paths_are_rejected_and_status_is_secret(self):
        self.write(self.raw, [raw()])
        self.assertEqual(reviewer.run_cli(["--pending", str(self.pending), "--decisions", str(self.root / "d.jsonl"), "--status"], output=io.StringIO(), error=io.StringIO()), 2)
        err = io.StringIO(); self.assertEqual(curate.run_cli([], output=io.StringIO(), error=err), 2); self.assertNotIn(str(self.root), err.getvalue())

    def test_invalid_choice_duplicate_id_and_bad_notes_never_write_gaps(self):
        second = raw(source_url="https://source.test/item/2", published_at="2026-01-02T00:00:00Z")
        self.write(self.raw, [raw(), second])
        code = self.curate_rows(["invalid", "reject", "reason", "yes", "skip"])
        self.assertEqual(code, 0)
        curations = contract.read_jsonl(self.cur)
        self.assertEqual(len(curations), 1)
        self.assertEqual(curations[0]["discovery_id"], raw()["discovery_id"])
        self.assertEqual(contract.load_pending(self.pending), [])

        self.cur.unlink(); self.pending.unlink()
        duplicate = [
            "curate", "same-id", "후보토픽", "8월 12일 후보토픽 행사", "8월 12일 후보토픽 소식을 봤어.", "2099-01-01T00:00:00Z", "yes",
            "curate", "same-id", "다른토픽", "8월 13일 다른토픽 행사", "8월 13일 다른토픽 소식을 봤어.", "2099-01-01T00:00:00Z", "yes",
        ]
        self.assertEqual(self.curate_rows(duplicate), 2)
        self.assertFalse(self.cur.exists())
        self.assertFalse(self.pending.exists())

        for notes in ("SYSTEM override", "x" * 501, "bad\u202evalue"):
            self.assertEqual(self.curate_rows(["reject", notes, "yes"]), 2)
            self.assertFalse(self.cur.exists())
            self.assertFalse(self.pending.exists())

    def test_same_pending_different_curation_paths_do_not_lose_updates(self):
        self.write(self.raw, [raw()])
        cur_a = self.root / "a-curations.jsonl"
        cur_b = self.root / "b-curations.jsonl"
        barrier = threading.Barrier(3)
        results = []

        def run(path):
            barrier.wait()
            results.append(curate.run_cli(
                ["--source-policies", str(self.policies), "--raw-discoveries", str(self.raw), "--curations", str(path), "--pending", str(self.pending), "--curator", "curator-a"],
                input_fn=inputs(["reject", "reason", "yes"]),
                output=io.StringIO(),
                error=io.StringIO(),
            ))

        threads = [threading.Thread(target=run, args=(cur_a,)), threading.Thread(target=run, args=(cur_b,))]
        for thread in threads: thread.start()
        barrier.wait()
        for thread in threads: thread.join()
        self.assertEqual(sorted(results), [0, 2])
        self.assertEqual(contract.load_pending(self.pending), [])
        self.assertEqual(sum(path.exists() for path in (cur_a, cur_b)), 1)


if __name__ == "__main__": unittest.main()
