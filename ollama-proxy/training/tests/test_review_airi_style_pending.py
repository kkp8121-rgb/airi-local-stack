import io
import json
import tempfile
import unittest
from pathlib import Path

from review_airi_style_pending import run_cli


def record():
    return {"id": "seed-001", "prompt": "민감한 원문", "answer": "검수 원문", "category": "warmth", "split": "train"}


def inputs(values):
    iterator = iter(values)
    return lambda _: next(iterator)


class PendingReviewTests(unittest.TestCase):
    def review(self, directory, values, *extra):
        pending, sidecar = Path(directory) / "pending.jsonl", Path(directory) / "decisions.jsonl"
        pending.write_text(json.dumps(record(), ensure_ascii=False) + "\n", encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        code = run_cli(["--pending", str(pending), "--decisions", str(sidecar), "--reviewer", "reviewer-a", *extra], input_fn=inputs(values), output=out, error=err)
        return code, pending, sidecar, out.getvalue(), err.getvalue()

    def test_approve_guard_and_atomic_output_source_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            code, pending, sidecar, out, _ = self.review(directory, ["approve", "yes", "yes", "yes"])
            self.assertEqual(code, 0); self.assertFalse(sidecar.exists()); self.assertIn("not recorded", out)
            source = pending.read_bytes()
            code, pending, sidecar, _, _ = self.review(directory, ["approve", "yes", "no", "yes"])
            self.assertEqual(code, 0); self.assertEqual(pending.read_bytes(), source)
            decision = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(decision["decision"], "approve"); self.assertTrue(decision["reviewed_at"].endswith("Z"))
            self.assertFalse(list(Path(directory).glob(".decisions.jsonl.*.tmp")))

    def test_notes_skip_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, sidecar, out, _ = self.review(directory, ["rewrite", "yes", "no", "yes", " "])
            self.assertFalse(sidecar.exists()); self.assertIn("notes are required", out)
            _, _, sidecar, _, _ = self.review(directory, ["skip"]); self.assertFalse(sidecar.exists())
            _, _, sidecar, _, _ = self.review(directory, ["reject", "no", "no", "no", "reason"]); original = sidecar.read_bytes()
            _, _, sidecar, out, _ = self.review(directory, [])
            self.assertEqual(sidecar.read_bytes(), original); self.assertNotIn("민감한 원문", out)

    def test_replace_mismatch_and_content_free_status(self):
        with tempfile.TemporaryDirectory() as directory:
            _, pending, sidecar, _, _ = self.review(directory, ["reject", "no", "no", "no", "reason"]); original = sidecar.read_bytes()
            out, err = io.StringIO(), io.StringIO()
            code = run_cli(["--pending", str(pending), "--decisions", str(sidecar), "--reviewer", "reviewer-b", "--replace-decision"], input_fn=inputs([]), output=out, error=err)
            self.assertEqual(code, 0); self.assertEqual(sidecar.read_bytes(), original); self.assertIn("different reviewer", out.getvalue())
            out, err = io.StringIO(), io.StringIO()
            code = run_cli(["--pending", str(pending), "--decisions", str(sidecar), "--status"], output=out, error=err)
            out = out.getvalue()
            self.assertEqual(code, 0); self.assertNotIn("민감한 원문", out); self.assertNotIn("검수 원문", out)
            self.assertEqual(json.loads(out)["decision_count"], 1)


if __name__ == "__main__": unittest.main()
