import importlib.util
import json
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("build_extraction_review_form_test",
                                              HERE / "build_extraction_review_form.py")
assert SPEC is not None and SPEC.loader is not None
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class ExtractionReviewFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.markup = builder.build_form(builder.DEFAULT_PENDING, "test-label")
        cls.records = [json.loads(line) for line in
                       builder.DEFAULT_PENDING.read_text(encoding="utf-8").splitlines() if line]

    def _payload(self) -> list[dict]:
        raw = self.markup.split("const RECORDS = ", 1)[1].split(";\n", 1)[0]
        return json.loads(raw)

    def test_every_pending_record_is_embedded(self) -> None:
        for record in self.records:
            self.assertIn(record["id"], self.markup)
        self.assertIn(f"({len(self.records)}건)", self.markup)

    def test_embedded_payload_round_trips_and_stays_content_faithful(self) -> None:
        embedded = self._payload()
        self.assertEqual(len(embedded), len(self.records))
        by_id = {record["id"]: record for record in self.records}
        for entry in embedded:
            source = by_id[entry["id"]]
            self.assertEqual(entry["scene"], source["scene"])
            self.assertEqual(entry["character"], source["character"])
            self.assertEqual(entry["turns"], source["turns"])
            self.assertEqual(entry["target"], source["target"])

    def test_every_target_carries_readable_items_with_evidence(self) -> None:
        # 검수자가 판단하려면 추출 항목과 그 근거 인용이 보여야 한다.
        embedded = self._payload()
        evidenced = 0
        for entry in embedded:
            items = json.loads(entry["target"])["extracted"]
            for item in items:
                self.assertIn("evidence", item)
                self.assertIn(item["evidence"], entry["turns"])
                evidenced += 1
        self.assertGreater(evidenced, 0)
        self.assertIn("evidence", self.markup.split("const RECORDS")[1])

    def test_every_scene_has_a_label(self) -> None:
        scenes = {record["scene"] for record in self.records}
        labels = self.markup.split("const SCENE_LABELS = ", 1)[1].split(";\n", 1)[0]
        for scene in scenes:
            self.assertIn(f'"{scene}"', labels)

    def test_reply_header_matches_the_applier_contract(self) -> None:
        self.assertIn("[AIRI 추출 SFT 검수 회신 test-label]", self.markup)
        self.assertNotIn("__DATE__", self.markup)

    def test_form_never_claims_training_eligibility(self) -> None:
        # 폼은 검수 입력 수집용이지 승인·학습 권한이 아니다.
        self.assertNotIn("training_eligible", self.markup.split("const RECORDS")[0])
        self.assertIn("검수 회신", self.markup)

    def test_committed_form_matches_the_builder_output(self) -> None:
        committed = builder.DEFAULT_OUTPUT
        if committed.exists():
            self.assertEqual(committed.read_text(encoding="utf-8"),
                             builder.build_form(builder.DEFAULT_PENDING, builder.DEFAULT_DATE_LABEL))

    def test_empty_queue_fails_closed(self) -> None:
        empty = HERE / "tests" / "_empty_extraction_pending.jsonl"
        empty.write_text("", encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                builder.build_form(empty, "x")
        finally:
            empty.unlink()


if __name__ == "__main__":
    unittest.main()
