import io
import json
import tempfile
import unittest
from pathlib import Path

from review_airi_style_pending import run_cli
from validate_airi_style_pending import record_sha256


SEED_PENDING = Path(__file__).resolve().parents[1] / "seed" / "airi_style_seed_pending.jsonl"


def inputs(values):
    iterator = iter(values)
    def read(_):
        try:
            return next(iterator)
        except StopIteration as exc:
            raise EOFError from exc
    return read


class PendingReviewTests(unittest.TestCase):
    def review(self, directory, values, *extra):
        pending, sidecar = Path(directory) / "pending.jsonl", Path(directory) / "decisions.jsonl"
        pending.write_bytes(SEED_PENDING.read_bytes())
        out, err = io.StringIO(), io.StringIO()
        code = run_cli(["--pending", str(pending), "--decisions", str(sidecar), "--reviewer", "reviewer-a", "--limit", "1", *extra], input_fn=inputs(values), output=out, error=err)
        return code, pending, sidecar, out.getvalue(), err.getvalue()

    def test_approve_guard_atomic_output_and_exact_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            code, pending, sidecar, out, _ = self.review(directory, ["approve", "yes", "yes", "yes"])
            self.assertEqual(code, 0); self.assertFalse(sidecar.exists()); self.assertIn("not recorded", out)
            source = pending.read_bytes()
            code, pending, sidecar, _, _ = self.review(directory, ["approve", "yes", "no", "yes"])
            self.assertEqual(code, 0); self.assertEqual(pending.read_bytes(), source)
            decision = json.loads(sidecar.read_text(encoding="utf-8"))
            pending_record = json.loads(pending.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(decision["decision"], "approve")
            self.assertTrue(decision["reviewed_at"].endswith("Z"))
            self.assertEqual(decision["record_sha256"], record_sha256(pending_record))
            self.assertFalse(list(Path(directory).glob(".decisions.jsonl.*.tmp")))

    def test_notes_skip_and_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            _, _, sidecar, out, _ = self.review(directory, ["rewrite", "yes", "no", "yes", " "])
            self.assertFalse(sidecar.exists()); self.assertIn("notes are required", out)
            _, _, sidecar, _, _ = self.review(directory, ["skip"]); self.assertFalse(sidecar.exists())
            _, _, sidecar, _, _ = self.review(directory, ["reject", "no", "no", "no", "reason"]); original = sidecar.read_bytes()
            _, _, sidecar, out, _ = self.review(directory, [], "--limit", "0")
            self.assertEqual(sidecar.read_bytes(), original); self.assertNotIn("--- pending record ---", out)

    def test_replace_mismatch_and_content_free_status(self):
        with tempfile.TemporaryDirectory() as directory:
            _, pending, sidecar, _, _ = self.review(directory, ["reject", "no", "no", "no", "reason"]); original = sidecar.read_bytes()
            out, err = io.StringIO(), io.StringIO()
            code = run_cli(["--pending", str(pending), "--decisions", str(sidecar), "--reviewer", "reviewer-b", "--replace-decision"], input_fn=inputs([]), output=out, error=err)
            self.assertEqual(code, 0); self.assertEqual(sidecar.read_bytes(), original); self.assertIn("different reviewer", out.getvalue())
            out, err = io.StringIO(), io.StringIO()
            code = run_cli(["--pending", str(pending), "--decisions", str(sidecar), "--status"], output=out, error=err)
            rendered = out.getvalue(); first = json.loads(pending.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(code, 0); self.assertNotIn(first["prompt"], rendered); self.assertNotIn(first["answer"], rendered)
            self.assertEqual(json.loads(rendered)["decision_count"], 1)

    def test_strict_pending_gate_runs_before_status_or_write(self):
        with tempfile.TemporaryDirectory() as directory:
            pending, sidecar = Path(directory) / "pending.jsonl", Path(directory) / "decisions.jsonl"
            pending.write_text(json.dumps({"id": "seed-001"}) + "\n", encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            code = run_cli(["--pending", str(pending), "--decisions", str(sidecar), "--status"], output=out, error=err)
            self.assertEqual(code, 2); self.assertFalse(sidecar.exists())
            self.assertIn("strict validation", err.getvalue())

    def test_content_mutation_rejects_existing_sidecar_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            _, pending, sidecar, _, _ = self.review(directory, ["reject", "no", "no", "no", "reason"])
            original = sidecar.read_bytes()
            rows = [json.loads(line) for line in pending.read_text(encoding="utf-8").splitlines()]
            rows[0]["prompt"] += "!"
            pending.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            code = run_cli(["--pending", str(pending), "--decisions", str(sidecar), "--status"], output=out, error=err)
            self.assertEqual(code, 2); self.assertEqual(sidecar.read_bytes(), original)
            self.assertIn("record hash does not match", err.getvalue())


if __name__ == "__main__":
    unittest.main()
