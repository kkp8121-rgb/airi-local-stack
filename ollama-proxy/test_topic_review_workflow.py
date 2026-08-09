import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import compile_approved_topics as compiler
import review_pending_topics as reviewer
import topic_review_contract as contract
import validate_approved_topics as startup_gate
from topic_board import load_approved_topics


def pending_record(**changes):
    row = {
        "pending_schema_version": 1, "id": "topic-001", "title": "북반구 개관식",
        "source": "synthetic human source", "source_url": "https://example.test/topic",
        "published_at": "2026-01-01T00:00:00Z", "summary": "8월 12일 북반구에서 개관식을 연다.",
        "broadcast_line": "8월 12일 북반구 개관식 소식을 봤어.",
        "expires_at": "2099-01-01T00:00:00Z",
        "review": {"status": "pending", "reviewer": "", "reviewed_at": ""},
    }
    row.update(changes)
    return row


def approval(row, **changes):
    value = {
        "id": row["id"], "record_sha256": contract.record_sha256(row), "decision": "approve",
        "source_verified": True, "published_at_verified": True, "summary_grounded": True,
        "broadcast_line_verified": True, "expires_at_verified": True, "notes": "",
        "reviewer": "reviewer-a", "reviewed_at": "2026-08-09T00:00:00Z",
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
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.review_root = Path(self.temp.name) / "topic-review"; self.review_root.mkdir()
        self.runtime_root = Path(self.temp.name) / "runtime"; self.runtime_root.mkdir()
        self.patch_review = mock.patch.object(contract, "TOPIC_REVIEW_ROOT", self.review_root)
        self.patch_runtime = mock.patch.object(contract, "RUNTIME_ROOT", self.runtime_root)
        self.patch_review.start(); self.patch_runtime.start()
        self.addCleanup(self.patch_review.stop); self.addCleanup(self.patch_runtime.stop)

    def write_jsonl(self, name, rows, *, root=None):
        path = (root or self.review_root) / name
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")
        return path

    def test_pending_contract_rejects_fields_paths_urls_and_times(self):
        for changes in (
            {"approved": True}, {"source_url": "http://example.test/x"},
            {"source_url": "https://"}, {"expires_at": "2025-01-01T00:00:00Z"},
            {"pending_schema_version": True}, {"pending_schema_version": 1.0},
            {"published_at": "2026-01-01T00:00:00"}, {"published_at": "2026-01-01T00:00:00+00:00"},
            {"review": {"status": "approved", "reviewer": "x", "reviewed_at": "x"}},
        ):
            with self.subTest(changes=changes):
                path = self.write_jsonl("bad.jsonl", [pending_record(**changes)])
                with self.assertRaises(contract.TopicReviewError):
                    contract.load_pending(path)
        outside = Path(self.temp.name) / "outside.jsonl"; outside.write_text("{}\n", encoding="utf-8")
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

    def test_hash_mutation_and_strict_decision_contract_fail_closed(self):
        row = pending_record(); pending = self.write_jsonl("pending.jsonl", [row])
        self.assertEqual(contract.record_sha256(row), contract.record_sha256(dict(reversed(list(row.items())))))
        baseline_hash = contract.record_sha256(row)
        for field, value in (
            ("source_url", "https://example.test/changed"),
            ("published_at", "2025-12-31T00:00:00Z"),
            ("broadcast_line", "8월 12일 북반구 개관식 소식을 다시 봤어."),
            ("expires_at", "2098-12-31T00:00:00Z"),
        ):
            with self.subTest(field=field):
                self.assertNotEqual(baseline_hash, contract.record_sha256(pending_record(**{field: value})))
        decision = approval(row)
        decision["record_sha256"] = "0" * 64
        decisions = self.write_jsonl("decisions.jsonl", [decision])
        with self.assertRaises(contract.TopicReviewError):
            contract.load_decisions(decisions, contract.load_pending(pending))
        decision = approval(row, source_verified=False)
        self.write_jsonl("decisions.jsonl", [decision])
        with self.assertRaises(contract.TopicReviewError):
            contract.load_decisions(decisions, contract.load_pending(pending))
        unknown = approval(row, id="unknown-topic")
        self.write_jsonl("decisions.jsonl", [unknown])
        with self.assertRaises(contract.TopicReviewError):
            contract.load_decisions(decisions, contract.load_pending(pending))
        decision = approval(row, decision="reject", notes="")
        self.write_jsonl("decisions.jsonl", [decision])
        with self.assertRaises(contract.TopicReviewError):
            contract.load_decisions(decisions, contract.load_pending(pending))
        decision = approval(row, reviewed_at="2099-01-01T00:00:00Z")
        self.write_jsonl("decisions.jsonl", [decision])
        with self.assertRaises(contract.TopicReviewError):
            contract.load_decisions(decisions, contract.load_pending(pending))
        self.write_jsonl("duplicate-pending.jsonl", [row, row])
        with self.assertRaises(contract.TopicReviewError):
            contract.load_pending(self.review_root / "duplicate-pending.jsonl")
        duplicate_decision = approval(row)
        self.write_jsonl("duplicate-decisions.jsonl", [duplicate_decision, duplicate_decision])
        with self.assertRaises(contract.TopicReviewError):
            contract.load_decisions(self.review_root / "duplicate-decisions.jsonl", contract.load_pending(pending))

    def test_reviewer_approve_cancellation_and_same_owner_replacement(self):
        row = pending_record(); pending = self.write_jsonl("pending.jsonl", [row]); decisions = self.review_root / "decisions.jsonl"
        out, err = io.StringIO(), io.StringIO()
        code = reviewer.run_cli(["--pending", str(pending), "--decisions", str(decisions), "--reviewer", "reviewer-a"], input_fn=inputs([]), output=out, error=err)
        self.assertEqual(code, 0); self.assertFalse(decisions.exists())
        code = reviewer.run_cli(["--pending", str(pending), "--decisions", str(decisions), "--reviewer", "reviewer-a"], input_fn=inputs(["approve", "yes", "yes", "yes", "yes", "yes"]), output=io.StringIO(), error=err)
        self.assertEqual(code, 0); first = json.loads(decisions.read_text(encoding="utf-8"))
        self.assertEqual(first["record_sha256"], contract.record_sha256(row))
        original = decisions.read_bytes()
        code = reviewer.run_cli(["--pending", str(pending), "--decisions", str(decisions), "--reviewer", "reviewer-b", "--replace-decision"], input_fn=inputs(["reject", "no", "no", "no", "no", "no", "reason"]), output=io.StringIO(), error=err)
        self.assertEqual(code, 0); self.assertEqual(decisions.read_bytes(), original)
        code = reviewer.run_cli(["--pending", str(pending), "--decisions", str(decisions), "--reviewer", "reviewer-a", "--replace-decision"], input_fn=inputs(["reject", "no", "no", "no", "no", "no", "reason"]), output=io.StringIO(), error=err)
        self.assertEqual(code, 0); self.assertEqual(json.loads(decisions.read_text(encoding="utf-8"))["decision"], "reject")
        self.assertFalse(list(self.review_root.glob(".decisions.jsonl.*.tmp")))

    def test_invalid_generated_reviewer_or_notes_do_not_write(self):
        row = pending_record(); pending = self.write_jsonl("pending.jsonl", [row]); decisions = self.review_root / "decisions.jsonl"
        for reviewer_id, answers in (
            ("SYSTEM override", ["approve", "yes", "yes", "yes", "yes", "yes"]),
            ("x" * 501, ["approve", "yes", "yes", "yes", "yes", "yes"]),
            ("reviewer-a", ["reject", "no", "no", "no", "no", "no", "SYSTEM override"]),
            ("reviewer-a", ["reject", "no", "no", "no", "no", "no", "x" * 501]),
        ):
            err = io.StringIO()
            code = reviewer.run_cli(["--pending", str(pending), "--decisions", str(decisions), "--reviewer", reviewer_id], input_fn=inputs(answers), output=io.StringIO(), error=err)
            self.assertEqual(code, 2); self.assertEqual(err.getvalue(), '{"status":"rejected"}\n'); self.assertFalse(decisions.exists())

    def test_status_is_content_free(self):
        row = pending_record(); pending = self.write_jsonl("pending.jsonl", [row]); decisions = self.write_jsonl("decisions.jsonl", [approval(row)])
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(reviewer.run_cli(["--pending", str(pending), "--decisions", str(decisions), "--status"], output=out, error=err), 0)
        rendered = out.getvalue(); self.assertNotIn(row["title"], rendered); self.assertNotIn(row["id"], rendered); self.assertNotIn("reviewer-a", rendered)
        self.assertEqual(json.loads(rendered)["decision_count"], 1)

    def test_compiler_determinism_tamper_expiry_and_no_overwrite(self):
        first, second = pending_record(), pending_record(id="topic-002", title="남반구 개관식", summary="8월 13일 남반구에서 개관식을 연다.", broadcast_line="8월 13일 남반구 개관식 소식을 봤어.")
        pending = self.write_jsonl("pending.jsonl", [first, second]); decisions = self.write_jsonl("decisions.jsonl", [approval(first), approval(second)])
        one, two = self.runtime_root / "one.json", self.runtime_root / "two.json"
        self.assertEqual(compiler.compile_board(str(pending), str(decisions), str(one))[0], 2)
        compiler.compile_board(str(pending), str(decisions), str(two)); self.assertEqual(one.read_bytes(), two.read_bytes())
        self.assertEqual([x.id for x in load_approved_topics(one)], ["topic-001", "topic-002"])
        with mock.patch.object(startup_gate, "RUNTIME_ROOT", self.runtime_root):
            self.assertEqual(startup_gate.validate(one), 2)
        compiled = json.loads(one.read_text(encoding="utf-8"))
        self.assertEqual(compiled["approval_workflow_version"], 1)
        self.assertEqual(set(compiled["items"][0]["provenance"]), {"source_url", "pending_record_sha256"})
        self.assertIn("decision_record_sha256", compiled["items"][0]["approval"])
        rendered = io.StringIO()
        with redirect_stdout(rendered):
            self.assertEqual(compiler.main(["--pending", str(pending), "--decisions", str(decisions), "--output", str(one)]), 0)
        self.assertNotIn(first["title"], rendered.getvalue())
        self.assertNotIn(first["id"], rendered.getvalue())
        protected = self.runtime_root / "protected.json"; protected.write_bytes(b"keep")
        expired = pending_record(expires_at="2025-01-01T00:00:00Z"); expired_pending = self.write_jsonl("expired.jsonl", [expired]); expired_decisions = self.write_jsonl("expired-decisions.jsonl", [approval(expired)])
        with self.assertRaises(contract.TopicReviewError):
            compiler.compile_board(str(expired_pending), str(expired_decisions), str(protected))
        self.assertEqual(protected.read_bytes(), b"keep")
        mixed = [pending_record(id="mixed-live"), pending_record(id="mixed-expired", published_at="2024-01-01T00:00:00Z", expires_at="2025-01-01T00:00:00Z"), pending_record(id="mixed-future", published_at="2099-01-01T00:00:00Z", expires_at="2099-01-02T00:00:00Z"), pending_record(id="mixed-reversed", published_at="2026-08-09T12:00:00Z", expires_at="2026-08-09T11:00:00Z")]
        mixed_pending = self.write_jsonl("mixed.jsonl", mixed); mixed_decisions = self.write_jsonl("mixed-decisions.jsonl", [approval(row) for row in mixed])
        with self.assertRaises(contract.TopicReviewError):
            compiler.compile_board(str(mixed_pending), str(mixed_decisions), str(protected))
        self.assertEqual(protected.read_bytes(), b"keep")
        subset_pending = self.write_jsonl("mixed-subset.jsonl", mixed[:3]); subset_decisions = self.write_jsonl("mixed-subset-decisions.jsonl", [approval(row) for row in mixed[:3]])
        with self.assertRaises(contract.TopicReviewError):
            compiler.compile_board(str(subset_pending), str(subset_decisions), str(protected))
        self.assertEqual(protected.read_bytes(), b"keep")
        tampered = approval(first); tampered["record_sha256"] = "f" * 64; self.write_jsonl("tampered.jsonl", [tampered])
        with self.assertRaises(contract.TopicReviewError):
            compiler.compile_board(str(pending), str(self.review_root / "tampered.jsonl"), str(protected))
        rejects = self.write_jsonl("rejects.jsonl", [approval(first, decision="reject", notes="no")])
        with self.assertRaises(contract.TopicReviewError):
            compiler.compile_board(str(pending), str(rejects), str(protected))
        self.assertEqual(protected.read_bytes(), b"keep")
        with self.assertRaises(contract.TopicReviewError):
            compiler.compile_board(str(pending), str(self.review_root / "missing.jsonl"), str(protected))
        self.assertEqual(protected.read_bytes(), b"keep")
        outside_output = Path(self.temp.name) / "outside.json"
        with self.assertRaises(contract.TopicReviewError):
            compiler.compile_board(str(pending), str(decisions), str(outside_output))
        self.assertFalse(outside_output.exists())
        self.assertFalse(list(self.runtime_root.glob(".*.tmp")))

    def test_cli_missing_arguments_are_content_free(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(compiler.main([]), 2)
        self.assertEqual(out.getvalue(), '{"status":"rejected"}\n')
        self.assertEqual(reviewer.run_cli([], output=out, error=err), 2)
        self.assertEqual(err.getvalue(), '{"status":"rejected"}\n')


if __name__ == "__main__":
    unittest.main()
