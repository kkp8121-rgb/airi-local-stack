import importlib.util
import json
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("build_behavior_review_form_test",
                                              HERE / "build_behavior_review_form.py")
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class ReviewFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.markup = builder.build_form(builder.DEFAULT_PENDING, "test-label")
        cls.records = [json.loads(line) for line in
                       builder.DEFAULT_PENDING.read_text(encoding="utf-8").splitlines() if line]

    def test_every_pending_record_is_embedded(self) -> None:
        for record in self.records:
            self.assertIn(record["id"], self.markup)
        self.assertIn(f"({len(self.records)}건)", self.markup)

    def test_embedded_payload_round_trips_and_stays_content_faithful(self) -> None:
        payload = self.markup.split("const RECORDS = ", 1)[1].split(";\n", 1)[0]
        embedded = json.loads(payload)
        self.assertEqual(len(embedded), len(self.records))
        by_id = {record["id"]: record for record in self.records}
        for entry in embedded:
            source = by_id[entry["id"]]
            self.assertEqual(entry["prompt"], source["prompt"])
            self.assertEqual(entry["answer"], source["answer"])
            self.assertEqual(entry["briefing"], source["briefing"])
            self.assertEqual(entry["behavior"], source["behavior"])

    def test_form_never_claims_training_eligibility(self) -> None:
        # 폼은 검수 입력 수집용이지 승인·학습 권한이 아니다.
        self.assertNotIn("training_eligible", self.markup.split("const RECORDS")[0])
        self.assertIn("검수 회신", self.markup)

    def test_committed_form_matches_the_builder_output(self) -> None:
        committed = builder.DEFAULT_OUTPUT
        if committed.exists():
            self.assertEqual(committed.read_text(encoding="utf-8"),
                             builder.build_form(builder.DEFAULT_PENDING, "2026-08-19"))

    def test_empty_queue_fails_closed(self) -> None:
        empty = HERE / "tests" / "_empty_pending.jsonl"
        empty.write_text("", encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                builder.build_form(empty, "x")
        finally:
            empty.unlink()


if __name__ == "__main__":
    unittest.main()
