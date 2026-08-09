import io
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import compile_approved_topics as compiler
import topic_discovery_contract as discovery
import topic_review_contract as contract
import topic_workflow_status as status


def pending_record(*, expires_at="2099-01-01T00:00:00Z"):
    return {
        "pending_schema_version": 1,
        "id": "synthetic-topic-1",
        "title": "가상 별빛 관측 소식",
        "source": "synthetic source",
        "source_url": "https://example.test/wiki/topic-1",
        "published_at": "2026-01-01T00:00:00Z",
        "summary": "가상 자료에서 별빛 관측 소식을 정리했다.",
        "broadcast_line": "가상 자료의 별빛 관측 소식을 같이 살펴보자.",
        "expires_at": expires_at,
        "review": {"status": "pending", "reviewer": "", "reviewed_at": ""},
    }


def approval(row, *, decision="approve"):
    approved = decision == "approve"
    return {
        "id": row["id"],
        "record_sha256": contract.record_sha256(row),
        "decision": decision,
        "source_verified": approved,
        "published_at_verified": approved,
        "summary_grounded": approved,
        "broadcast_line_verified": approved,
        "expires_at_verified": approved,
        "notes": "" if approved else "synthetic rejection",
        "reviewer": "synthetic-reviewer",
        "reviewed_at": "2026-01-02T00:00:00Z",
    }


class TopicWorkflowStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.review_root = root / "topic-review"
        self.runtime_root = root / "runtime"
        self.review_root.mkdir()
        self.runtime_root.mkdir()
        self.review_patch = mock.patch.object(contract, "TOPIC_REVIEW_ROOT", self.review_root)
        self.runtime_patch = mock.patch.object(contract, "RUNTIME_ROOT", self.runtime_root)
        self.review_patch.start()
        self.runtime_patch.start()
        self.addCleanup(self.review_patch.stop)
        self.addCleanup(self.runtime_patch.stop)
        self.policies = self.review_root / "source-policies-status.json"
        self.raw = self.review_root / "raw.jsonl"
        self.curations = self.review_root / "curations.jsonl"
        self.pending = self.review_root / "pending.jsonl"
        self.decisions = self.review_root / "decisions.jsonl"
        self.runtime = self.runtime_root / "approved-topics.json"

    def args(self, *, policy_id="synthetic-policy"):
        return [
            "--inspect-topic-workflow",
            "--source-policies", str(self.policies),
            "--raw-discoveries", str(self.raw),
            "--curations", str(self.curations),
            "--pending", str(self.pending),
            "--decisions", str(self.decisions),
            "--runtime-board", str(self.runtime),
            "--policy-id", policy_id,
        ]

    def policy(self):
        return {
            "policy_id": "synthetic-policy",
            "source_kind": "feed",
            "source": "synthetic source",
            "feed_url": "https://feed.test/list",
            "article_host": "example.test",
            "article_path_prefix": "/wiki/",
            "license": {
                "spdx": "CC-BY-4.0",
                "license_url": "https://license.test/cc",
                "attribution": "synthetic attribution",
                "attribution_url": "https://example.test/about",
            },
            "approved": True,
            "reviewer": "synthetic-policy-reviewer",
            "reviewed_at": "2026-01-01T00:00:00Z",
        }

    def raw_record(self, row):
        policy = self.policy()
        value = {
            "discovery_schema_version": 1,
            "discovery_id": discovery.discovery_id(
                policy["policy_id"], row["source_url"], row["published_at"],
            ),
            "source_policy_id": policy["policy_id"],
            "source_kind": policy["source_kind"],
            "source": policy["source"],
            "feed_url": policy["feed_url"],
            "source_url": row["source_url"],
            "published_at": row["published_at"],
            "discovered_at": "2026-01-01T01:00:00Z",
            "source_title": "가상 원문 제목",
            "source_snippet": "가상 원문 요약",
            "license": policy["license"],
            "source_body_sha256": hashlib.sha256(b"synthetic").hexdigest(),
            "source_policy_sha256": discovery.policy_sha256(policy),
        }
        return value

    def curation(self, raw, row, *, disposition="curate"):
        curated = disposition == "curate"
        return {
            "curation_schema_version": 1,
            "discovery_id": raw["discovery_id"],
            "raw_record_sha256": contract.record_sha256(raw),
            "source_metadata_sha256": contract.record_sha256(discovery.source_metadata(raw)),
            "disposition": disposition,
            "notes": "" if curated else "synthetic rejection",
            "pending_record": row if curated else None,
            "pending_record_sha256": contract.record_sha256(row) if curated else None,
            "curator": "synthetic-curator",
            "curated_at": "2026-01-02T00:00:00Z",
        }

    @staticmethod
    def write_jsonl(path, rows):
        path.write_bytes(contract.canonical_jsonl_bytes(rows))

    def write_policy(self):
        self.policies.write_bytes(contract.canonical_json({
            "schema_version": 1,
            "policies": [self.policy()],
        }))

    def write_curated(self, row=None, *, disposition="curate"):
        row = row or pending_record()
        raw = self.raw_record(row)
        self.write_jsonl(self.raw, [raw])
        self.write_jsonl(self.curations, [self.curation(raw, row, disposition=disposition)])
        self.write_jsonl(self.pending, [row] if disposition == "curate" else [])
        return row

    def rendered(self, argv):
        out = io.StringIO()
        code = status.run_cli(argv, output=out)
        rows = out.getvalue().splitlines()
        self.assertEqual(len(rows), 1)
        value = json.loads(rows[0])
        self.assertEqual(set(value), set(status._KEYS))
        return code, value

    def test_default_is_content_free_and_does_not_parse_or_touch_dependencies(self):
        out = io.StringIO()
        with mock.patch.object(status, "_arguments", side_effect=AssertionError("parsed")), \
             mock.patch.object(status, "review_output_path", side_effect=AssertionError("path")), \
             mock.patch.object(status, "runtime_output_path", side_effect=AssertionError("path")), \
             mock.patch.object(status, "runtime_items_are_live", side_effect=AssertionError("clock")):
            self.assertEqual(status.run_cli(["--anything"], output=out), 0)
        self.assertEqual(json.loads(out.getvalue()), {
            "status": "disabled", "stage": "disabled", "policy_count": 0,
            "raw_count": 0, "curation_count": 0, "pending_count": 0,
            "decision_count": 0, "approved_count": 0, "live_count": 0,
        })

    def test_enabled_requires_each_known_flag_exactly_once(self):
        for argv in (
            ["--inspect-topic-workflow"],
            ["--inspect-topic-workflow", "--policy-id", "x", "--policy-id", "x"],
            ["--inspect-topic-workflow", "--unknown", "x"],
        ):
            with self.subTest(argv=argv):
                code, value = self.rendered(argv)
                self.assertEqual(code, 2)
                self.assertEqual(value["status"], "rejected")
                self.assertEqual(value["stage"], "rejected")
                self.assertEqual(set(value), set(status._KEYS))

    def test_disabled_wins_even_for_malformed_unrelated_arguments(self):
        code, value = self.rendered(["--source-policies", "not-an-absolute-path"])
        self.assertEqual(code, 0)
        self.assertEqual(value["status"], "disabled")

    def test_all_workflow_stages_and_exact_current_board(self):
        args = self.args()
        code, value = self.rendered(args)
        self.assertEqual((code, value["stage"]), (0, "policy_required"))

        self.write_policy()
        self.assertEqual(self.rendered(args)[1]["stage"], "raw_required")

        self.write_jsonl(self.raw, [])
        self.assertEqual(self.rendered(args)[1]["stage"], "raw_required")

        row = pending_record()
        raw = self.raw_record(row)
        self.write_jsonl(self.raw, [raw])
        value = self.rendered(args)[1]
        self.assertEqual(value["stage"], "curation_required")
        self.assertEqual(value["raw_count"], 1)

        self.write_jsonl(self.curations, [])
        self.write_jsonl(self.pending, [])
        self.assertEqual(self.rendered(args)[1]["stage"], "curation_required")

        self.write_jsonl(self.curations, [self.curation(raw, row)])
        self.write_jsonl(self.pending, [row])
        value = self.rendered(args)[1]
        self.assertEqual(value["stage"], "review_required")
        self.assertEqual((value["curation_count"], value["pending_count"]), (1, 1))

        self.write_jsonl(self.decisions, [])
        self.assertEqual(self.rendered(args)[1]["stage"], "review_required")

        decision = approval(row)
        self.write_jsonl(self.decisions, [decision])
        value = self.rendered(args)[1]
        self.assertEqual(value["stage"], "compile_required")
        self.assertEqual((value["decision_count"], value["approved_count"]), (1, 1))

        _items, data = compiler.build_runtime_board([row], [decision])
        self.runtime.write_bytes(data)
        before = {path: path.read_bytes() for path in self.review_root.iterdir() if path.is_file()}
        runtime_before = self.runtime.read_bytes()
        code, value = self.rendered(args)
        self.assertEqual((code, value["stage"], value["live_count"]), (0, "ready", 1))
        self.assertEqual(runtime_before, self.runtime.read_bytes())
        self.assertEqual(before, {path: path.read_bytes() for path in self.review_root.iterdir() if path.is_file()})

    def test_all_rejected_curations_require_new_raw_without_decisions(self):
        self.write_policy()
        self.write_curated(disposition="reject")
        code, value = self.rendered(self.args())
        self.assertEqual((code, value["stage"]), (0, "raw_required"))
        self.assertEqual((value["raw_count"], value["curation_count"], value["pending_count"]), (1, 1, 0))
        self.write_jsonl(self.decisions, [])
        code, value = self.rendered(self.args())
        self.assertEqual((code, value["stage"], value["decision_count"]), (0, "raw_required", 0))

    def test_zero_approved_decisions_require_new_raw(self):
        self.write_policy()
        row = self.write_curated()
        self.write_jsonl(self.decisions, [approval(row, decision="reject")])
        code, value = self.rendered(self.args())
        self.assertEqual((code, value["stage"]), (0, "raw_required"))
        self.assertEqual((value["decision_count"], value["approved_count"]), (1, 0))

    def test_shared_liveness_predicate_matches_runtime_boundaries(self):
        now = datetime(2026, 8, 10, tzinfo=timezone.utc)
        live = {
            "published_at": "2026-08-10T00:00:00Z",
            "expires_at": "2026-08-11T00:00:00Z",
        }
        expired_at_boundary = {
            "published_at": "2026-08-09T00:00:00Z",
            "expires_at": "2026-08-10T00:00:00Z",
        }
        future = {
            "published_at": "2026-08-10T00:00:01Z",
            "expires_at": "2026-08-11T00:00:00Z",
        }
        self.assertTrue(compiler.runtime_items_are_live([live], now=now))
        self.assertFalse(compiler.runtime_items_are_live([expired_at_boundary], now=now))
        self.assertFalse(compiler.runtime_items_are_live([future], now=now))
        self.assertFalse(compiler.runtime_items_are_live([live, future], now=now))

    def test_orphan_wrong_policy_and_tampered_runtime_are_rejected(self):
        self.runtime.write_text("{}", encoding="utf-8")
        self.assertEqual(self.rendered(self.args())[0], 2)
        self.runtime.unlink()
        self.write_policy()
        self.assertEqual(self.rendered(self.args(policy_id="missing"))[0], 2)

        row = self.write_curated()
        decision = approval(row)
        self.write_jsonl(self.decisions, [decision])
        _items, data = compiler.build_runtime_board([row], [decision])
        self.runtime.write_bytes(data + b" ")
        code, value = self.rendered(self.args())
        self.assertEqual((code, value["stage"]), (2, "rejected"))

    def test_expired_runtime_and_partial_pairs_are_rejected_without_write(self):
        self.write_policy()
        row = pending_record(expires_at="2026-02-01T00:00:00Z")
        raw = self.raw_record(row)
        self.write_jsonl(self.raw, [raw])
        self.write_jsonl(self.curations, [self.curation(raw, row)])
        self.assertEqual(self.rendered(self.args())[0], 2)

        self.write_jsonl(self.pending, [row])
        decision = approval(row)
        self.write_jsonl(self.decisions, [decision])
        _items, data = compiler.build_runtime_board([row], [decision])
        code, value = self.rendered(self.args())
        self.assertEqual((code, value["stage"]), (2, "rejected"))
        self.runtime.write_bytes(data)
        before = self.runtime.read_bytes()
        code, value = self.rendered(self.args())
        self.assertEqual((code, value["stage"]), (2, "rejected"))
        self.assertEqual(self.runtime.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
