import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("build_behavior_review_form_test", HERE / "build_behavior_review_form.py")
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)

class ReviewFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.markup = builder.build_form(builder.DEFAULT_PENDING, "test-label")
        cls.records = [json.loads(line) for line in builder.DEFAULT_PENDING.read_text(encoding="utf-8").splitlines() if line]
    def test_every_pending_record_is_embedded(self) -> None:
        for record in self.records: self.assertIn(record["id"], self.markup)
        self.assertIn(f"({len(self.records)}건)", self.markup)
    def test_embedded_payload_round_trips_and_stays_content_faithful(self) -> None:
        embedded = json.loads(self.markup.split("const RECORDS = ", 1)[1].split(";\n", 1)[0])
        by_id = {record["id"]: record for record in self.records}
        for entry in embedded:
            source = by_id[entry["id"]]
            for key in ("prompt", "answer", "briefing", "behavior"): self.assertEqual(entry[key], source[key])
    def test_form_never_claims_training_eligibility(self) -> None:
        self.assertNotIn("training_eligible", self.markup.split("const RECORDS")[0]); self.assertIn("검수 회신", self.markup)
    def test_committed_form_matches_the_builder_output(self) -> None:
        if builder.DEFAULT_OUTPUT.exists(): self.assertEqual(builder.DEFAULT_OUTPUT.read_text(encoding="utf-8"), builder.build_form(builder.DEFAULT_PENDING, "2026-08-19"))
    def test_empty_queue_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "empty.jsonl"; empty.write_text("", encoding="utf-8")
            with self.assertRaises(ValueError): builder.build_form(empty, "x")
    def test_queue_digest_is_eol_stable_and_content_sensitive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            lf, crlf, changed = (Path(directory) / name for name in ("lf", "crlf", "changed"))
            lf.write_bytes(b'{"x":1}\n'); crlf.write_bytes(b'{"x":1}\r\n'); changed.write_bytes(b'{"x":2}\n')
            self.assertRegex(builder.queue_digest(lf), r"^[0-9a-f]{12}$"); self.assertEqual(builder.queue_digest(lf), builder.queue_digest(crlf)); self.assertNotEqual(builder.queue_digest(lf), builder.queue_digest(changed))
    def test_storage_is_scoped_to_queue_without_stale_legacy_migration(self) -> None:
        self.assertIn("const KEY = 'airi-behavior-review-test-label-' + QUEUE_SHA", self.markup)
        self.assertNotIn("LEGACY_KEY", self.markup)
    def test_affect_queue_has_actual_labels_and_metadata(self) -> None:
        affect = HERE / "seed" / "airi_behavior_affect_seed_pending.jsonl"
        markup = builder.build_form(affect, "affect")
        self.assertIn("const QUEUE_SHA", markup); self.assertIn("queue=' + QUEUE_SHA", markup); self.assertIn("neutral", markup); self.assertIn("중립", markup); self.assertIn("affect_state", markup); self.assertIn("must_include_any", markup)
    def test_unknown_behavior_fails_closed(self) -> None:
        record = {"id":"bseed-unknown-0001", "behavior":"unknown", "briefing":"", "prompt":"q", "answer":"a"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue"; path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaises(ValueError): builder.build_form(path, "x")

if __name__ == "__main__": unittest.main()
