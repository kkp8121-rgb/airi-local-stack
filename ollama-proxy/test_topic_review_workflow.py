import hashlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import compile_approved_topics as compiler
import review_pending_topics as reviewer
import topic_discovery_contract as discovery
import topic_review_contract as contract
import validate_approved_topics as startup_gate
from topic_board import load_approved_topics


def pending_record(**changes):
    row = {
        "pending_schema_version": 1,
        "id": "topic-001",
        "title": "북반구 개기월식",
        "source": "synthetic human source",
        "source_url": "https://example.test/topic/1",
        "published_at": "2026-01-01T00:00:00Z",
        "summary": "8월 12일 북반구에서 개기월식이 열린다.",
        "broadcast_line": "8월 12일 개기월식 소식을 같이 살펴보자.",
        "expires_at": "2099-01-01T00:00:00Z",
        "review": {"status": "pending", "reviewer": "", "reviewed_at": ""},
    }
    row.update(changes)
    return row


def approval(row, **changes):
    value = {
        "id": row["id"],
        "record_sha256": contract.record_sha256(row),
        "decision": "approve",
        "source_verified": True,
        "published_at_verified": True,
        "summary_grounded": True,
        "broadcast_line_verified": True,
        "expires_at_verified": True,
        "notes": "",
        "reviewer": "reviewer-a",
        "reviewed_at": "2026-08-09T00:00:00Z",
    }
    value.update(changes)
    return value


def inputs(values):
    iterator = iter(values)

    def read(_):
        try:
            return next(iterator)
        except StopIteration as exc:
            raise EOFError from exc

    return read


class TopicReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.review_root = Path(self.temp.name) / "topic-review"
        self.review_root.mkdir()
        self.runtime_root = Path(self.temp.name) / "runtime"
        self.runtime_root.mkdir()
        self.patch_review = mock.patch.object(
            contract,
            "TOPIC_REVIEW_ROOT",
            self.review_root,
        )
        self.patch_runtime = mock.patch.object(
            contract,
            "RUNTIME_ROOT",
            self.runtime_root,
        )
        self.patch_review.start()
        self.patch_runtime.start()
        self.addCleanup(self.patch_review.stop)
        self.addCleanup(self.patch_runtime.stop)

    def write_jsonl(self, name, rows, *, root=None):
        path = (root or self.review_root) / name
        path.write_bytes(contract.canonical_jsonl_bytes(rows))
        return path

    def discovery_fixture(self, name: str, rows: list[dict]):
        policy = {
            "policy_id": f"policy-{name}",
            "source_kind": "feed",
            "source": "synthetic human source",
            "feed_url": "https://feed.test/list",
            "article_host": "example.test",
            "article_path_prefix": "/topic/",
            "license": {
                "spdx": "CC-BY-4.0",
                "license_url": "https://license.test/cc",
                "attribution": "synthetic attribution",
                "attribution_url": "https://example.test/about",
            },
            "approved": True,
            "reviewer": "policy-reviewer",
            "reviewed_at": "2026-01-01T00:00:00Z",
        }
        policies = self.review_root / f"source-policies-{name}.json"
        policies.write_text(
            json.dumps({"schema_version": 1, "policies": [policy]}),
            encoding="utf-8",
        )
        raw_rows = []
        curations = []
        for row in rows:
            published = datetime.fromisoformat(
                row["published_at"][:-1] + "+00:00"
            )
            discovered = (published + timedelta(hours=1)).astimezone(timezone.utc)
            raw = {
                "discovery_schema_version": 1,
                "discovery_id": discovery.discovery_id(
                    policy["policy_id"],
                    row["source_url"],
                    row["published_at"],
                ),
                "source_policy_id": policy["policy_id"],
                "source_kind": policy["source_kind"],
                "source": policy["source"],
                "feed_url": policy["feed_url"],
                "source_url": row["source_url"],
                "published_at": row["published_at"],
                "discovered_at": discovered.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source_title": f"합성 원문 {row['id']}",
                "source_snippet": "합성 검수용 원문 요약",
                "license": policy["license"],
                "source_body_sha256": hashlib.sha256(
                    contract.canonical_json(row)
                ).hexdigest(),
                "source_policy_sha256": discovery.policy_sha256(policy),
            }
            raw_rows.append(raw)
            curations.append(
                {
                    "curation_schema_version": 1,
                    "discovery_id": raw["discovery_id"],
                    "raw_record_sha256": contract.record_sha256(raw),
                    "source_metadata_sha256": contract.record_sha256(
                        discovery.source_metadata(raw)
                    ),
                    "disposition": "curate",
                    "notes": "",
                    "pending_record": row,
                    "pending_record_sha256": contract.record_sha256(row),
                    "curator": "curator-a",
                    "curated_at": "2026-08-09T00:00:00Z",
                }
            )
        raw_path = self.write_jsonl(f"{name}-raw.jsonl", raw_rows)
        curations_path = self.write_jsonl(f"{name}-curations.jsonl", curations)
        pending_path = self.write_jsonl(f"{name}-pending.jsonl", rows)
        return policies, raw_path, curations_path, pending_path

    @staticmethod
    def discovery_cli_args(paths):
        policies, raw, curations, pending = paths
        return [
            "--pending",
            str(pending),
            "--source-policies",
            str(policies),
            "--raw-discoveries",
            str(raw),
            "--curations",
            str(curations),
        ]

    def test_pending_contract_rejects_fields_paths_urls_and_times(self):
        for changes in (
            {"approved": True},
            {"source_url": "http://example.test/x"},
            {"source_url": "https://"},
            {"expires_at": "2025-01-01T00:00:00Z"},
            {"pending_schema_version": True},
            {"pending_schema_version": 1.0},
            {"published_at": "2026-01-01T00:00:00"},
            {"published_at": "2026-01-01T00:00:00+00:00"},
            {"review": {"status": "approved", "reviewer": "x", "reviewed_at": "x"}},
        ):
            with self.subTest(changes=changes):
                path = self.write_jsonl("bad.jsonl", [pending_record(**changes)])
                with self.assertRaises(contract.TopicReviewError):
                    contract.load_pending(path)
        outside = Path(self.temp.name) / "outside.jsonl"
        outside.write_text("{}\n", encoding="utf-8")
        with self.assertRaises(contract.TopicReviewError):
            contract.load_pending(outside)
        with self.assertRaises(contract.TopicReviewError):
            contract.load_pending("relative.jsonl")
        link = self.review_root / "linked.jsonl"
        try:
            os.symlink(path, link)
        except OSError:
            with mock.patch.object(Path, "is_symlink", return_value=True):
                with self.assertRaises(contract.TopicReviewError):
                    contract.load_pending(path)
        else:
            with self.assertRaises(contract.TopicReviewError):
                contract.load_pending(link)

    def test_hash_mutation_and_decision_contract_fail_closed(self):
        row = pending_record()
        pending = self.write_jsonl("pending.jsonl", [row])
        decision = approval(row, record_sha256="0" * 64)
        decisions = self.write_jsonl("decisions.jsonl", [decision])
        with self.assertRaises(contract.TopicReviewError):
            contract.load_decisions(decisions, contract.load_pending(pending))
        self.write_jsonl(
            "decisions.jsonl",
            [approval(row, source_verified=False)],
        )
        with self.assertRaises(contract.TopicReviewError):
            contract.load_decisions(decisions, contract.load_pending(pending))
        self.write_jsonl("duplicate-pending.jsonl", [row, row])
        with self.assertRaises(contract.TopicReviewError):
            contract.load_pending(self.review_root / "duplicate-pending.jsonl")

    def test_reviewer_requires_bound_discovery_and_same_owner_replace(self):
        paths = self.discovery_fixture("review", [pending_record()])
        decisions = self.review_root / "decisions.jsonl"
        base = self.discovery_cli_args(paths) + ["--decisions", str(decisions)]
        self.assertEqual(
            reviewer.run_cli(
                base + ["--reviewer", "reviewer-a"],
                input_fn=inputs([]),
                output=io.StringIO(),
                error=io.StringIO(),
            ),
            0,
        )
        self.assertFalse(decisions.exists())
        self.assertEqual(
            reviewer.run_cli(
                base + ["--reviewer", "reviewer-a"],
                input_fn=inputs(["approve", "yes", "yes", "yes", "yes", "yes"]),
                output=io.StringIO(),
                error=io.StringIO(),
            ),
            0,
        )
        original = decisions.read_bytes()
        self.assertEqual(
            reviewer.run_cli(
                base
                + ["--reviewer", "reviewer-b", "--replace-decision"],
                input_fn=inputs(["reject", "no", "no", "no", "no", "no", "reason"]),
                output=io.StringIO(),
                error=io.StringIO(),
            ),
            0,
        )
        self.assertEqual(decisions.read_bytes(), original)
        err = io.StringIO()
        self.assertEqual(
            reviewer.run_cli(
                [
                    "--pending",
                    str(paths[3]),
                    "--decisions",
                    str(decisions),
                    "--status",
                ],
                output=io.StringIO(),
                error=err,
            ),
            2,
        )
        self.assertEqual(err.getvalue(), '{"status":"rejected"}\n')

    def test_reviewer_status_is_content_free(self):
        row = pending_record()
        paths = self.discovery_fixture("status", [row])
        decisions = self.write_jsonl("status-decisions.jsonl", [approval(row)])
        out = io.StringIO()
        args = self.discovery_cli_args(paths) + [
            "--decisions",
            str(decisions),
            "--status",
        ]
        self.assertEqual(
            reviewer.run_cli(args, output=out, error=io.StringIO()),
            0,
        )
        rendered = out.getvalue()
        self.assertNotIn(row["title"], rendered)
        self.assertNotIn(row["id"], rendered)
        self.assertNotIn("reviewer-a", rendered)
        self.assertEqual(json.loads(rendered)["decision_count"], 1)

    def test_compiler_is_deterministic_and_preserves_failed_output(self):
        first = pending_record()
        second = pending_record(
            id="topic-002",
            title="남반구 개기월식",
            source_url="https://example.test/topic/2",
            published_at="2026-01-02T00:00:00Z",
            summary="8월 13일 남반구에서 개기월식이 열린다.",
            broadcast_line="8월 13일 개기월식 소식을 같이 살펴보자.",
        )
        paths = self.discovery_fixture("compile", [first, second])
        decisions = self.write_jsonl(
            "compile-decisions.jsonl",
            [approval(first), approval(second)],
        )
        one = self.runtime_root / "one.json"
        two = self.runtime_root / "two.json"
        kwargs = {
            "source_policies": str(paths[0]),
            "raw_discoveries": str(paths[1]),
            "curations": str(paths[2]),
        }
        self.assertEqual(
            compiler.compile_board(str(paths[3]), str(decisions), str(one), **kwargs)[0],
            2,
        )
        compiler.compile_board(str(paths[3]), str(decisions), str(two), **kwargs)
        self.assertEqual(one.read_bytes(), two.read_bytes())
        self.assertEqual(
            [item.id for item in load_approved_topics(one)],
            ["topic-001", "topic-002"],
        )
        with mock.patch.object(startup_gate, "RUNTIME_ROOT", self.runtime_root):
            self.assertEqual(startup_gate.validate(one), 2)
        compiled = json.loads(one.read_text(encoding="utf-8"))
        self.assertEqual(compiled["approval_workflow_version"], 1)
        self.assertIn("decision_record_sha256", compiled["items"][0]["approval"])

        protected = self.runtime_root / "protected.json"
        protected.write_bytes(b"keep")
        expired = pending_record(
            id="expired-topic",
            source_url="https://example.test/topic/expired",
            published_at="2024-01-01T00:00:00Z",
            expires_at="2025-01-01T00:00:00Z",
        )
        expired_paths = self.discovery_fixture("expired", [expired])
        expired_decisions = self.write_jsonl(
            "expired-decisions.jsonl",
            [approval(expired)],
        )
        with self.assertRaises(contract.TopicReviewError):
            compiler.compile_board(
                str(expired_paths[3]),
                str(expired_decisions),
                str(protected),
                source_policies=str(expired_paths[0]),
                raw_discoveries=str(expired_paths[1]),
                curations=str(expired_paths[2]),
            )
        self.assertEqual(protected.read_bytes(), b"keep")

    def test_cli_missing_discovery_arguments_are_content_free(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(compiler.main([]), 2)
        self.assertEqual(out.getvalue(), '{"status":"rejected"}\n')
        err = io.StringIO()
        self.assertEqual(reviewer.run_cli([], output=io.StringIO(), error=err), 2)
        self.assertEqual(err.getvalue(), '{"status":"rejected"}\n')


if __name__ == "__main__":
    unittest.main()
