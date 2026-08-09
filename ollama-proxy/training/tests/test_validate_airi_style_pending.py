"""Focused offline tests for the pending-review quality gate."""
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validate_airi_style_pending import GateError, record_sha256, validate_decisions, validate_pending_dataset
from verify_airi_style_dataset import CATEGORY_TAXONOMY


def pending_row(index: int, split: str, category: str) -> dict:
    return {
        "id": f"seed-{index:03d}",
        "split": split,
        "category": category,
        "prompt": f"質問 {index}",
        "answer": f"返事{index}",
        "partition": {"tier": "S1", "group": f"pending-{index:03d}"},
        "review": {"status": "pending", "reviewer": "", "approved_at": ""},
        "provenance": {"synthetic": True, "source": "pending-seed"},
        "training_eligible": False,
    }


def clean_rows() -> list[dict]:
    rows = []
    for index in range(200):
        split = "train" if index < 160 else "dev" if index < 180 else "test"
        rows.append(pending_row(index + 1, split, CATEGORY_TAXONOMY[index % len(CATEGORY_TAXONOMY)]))
    return rows


class PendingQualityGateTests(unittest.TestCase):
    def validate(self, rows: list[dict]) -> dict:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pending.jsonl"
            path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
            return validate_pending_dataset(path)

    def test_clean_pending_dataset_passes_existing_contracts(self) -> None:
        summary = self.validate(clean_rows())
        self.assertEqual(summary["status"], "pending-review")
        self.assertEqual(summary["record_count"], 200)
        with self.assertRaisesRegex(GateError, "exactly 200"):
            self.validate(clean_rows()[:-1])
        with self.assertRaisesRegex(GateError, "exactly 200"):
            self.validate(clean_rows() + [pending_row(201, "train", CATEGORY_TAXONOMY[0])])

    def test_normalized_id_group_and_prompt_duplicates_reject(self) -> None:
        for field, value in (("id", "seed--001"), ("group", "pending_001"), ("prompt", "質問-1")):
            rows = clean_rows()
            if field == "group":
                rows[1]["partition"]["group"] = value
            else:
                rows[1][field] = value
            with self.assertRaisesRegex(GateError, "duplicate normalized"):
                self.validate(rows)

    def test_answer_cross_split_and_sentence_repetition_reject(self) -> None:
        rows = clean_rows()
        rows[180]["answer"] = rows[0]["answer"]
        with self.assertRaisesRegex(GateError, "overlaps dataset splits"):
            self.validate(rows)
        rows = clean_rows()
        for index in range(5):
            rows[index]["answer"] = f"同文.別文{index}"
        with self.assertRaisesRegex(GateError, "sentence repeats too often"):
            self.validate(rows)

    def test_question_ended_answers_are_bounded_but_allow_clarification(self) -> None:
        rows = clean_rows()
        for index in range(10):
            rows[index]["answer"] = f"확인 질문 {index}?"
        self.assertEqual(self.validate(rows)["record_count"], 200)

        rows[10]["answer"] = "확인 질문 10?"
        with self.assertRaisesRegex(GateError, "question-ended answers exceed 10"):
            self.validate(rows)

    def test_answer_quality_and_pending_contracts_reject(self) -> None:
        rows = clean_rows()
        rows[0]["answer"] = "English"
        with self.assertRaisesRegex(GateError, "English alphabet"):
            self.validate(rows)
        rows = clean_rows()
        rows[0]["prompt"] = "영어로 짧게 인사해 줘"
        rows[0]["answer"] = "Good morning."
        self.assertEqual(self.validate(rows)["record_count"], 200)
        rows = clean_rows()
        rows[0]["prompt"] = "회의에서 할 한마디를 골라 줘"
        rows[0]["answer"] = "이 안으로 결정해도 될까요?"
        self.assertEqual(self.validate(rows)["record_count"], 200)
        rows = clean_rows()
        rows[0]["review"]["status"] = "approved"
        with self.assertRaisesRegex(GateError, "unapproved pending"):
            self.validate(rows)
        rows = clean_rows()
        rows[0]["training_eligible"] = True
        with self.assertRaisesRegex(GateError, "training_eligible"):
            self.validate(rows)

    def test_decisions_bind_to_the_exact_canonical_pending_record(self) -> None:
        with TemporaryDirectory() as directory:
            rows = clean_rows()
            sidecar = Path(directory) / "decisions.jsonl"
            decision = {"id": rows[0]["id"], "record_sha256": record_sha256(rows[0]), "decision": "approve", "vtuber_voice": True, "counselor_tone": False, "safety_truth": True, "notes": "", "reviewer": "reviewer-a", "reviewed_at": "2026-08-09T00:00:00Z"}
            sidecar.write_text(json.dumps(decision, ensure_ascii=False) + "\n", encoding="utf-8")
            validate_decisions(sidecar, {row["id"]: row for row in rows})
            rows[0]["answer"] += "!"
            with self.assertRaisesRegex(GateError, "record hash does not match"):
                validate_decisions(sidecar, {row["id"]: row for row in rows})


if __name__ == "__main__":
    unittest.main()
