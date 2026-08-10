"""Regression tests only; training is never invoked."""

import json
import sys
import tempfile
import unittest
from pathlib import Path


TRAINING_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRAINING_DIR))

from train_airi_style_qlora import TrainingRefused, _assert_train_rows
from validate_airi_style_pending import (
    record_sha256,
    validate_decisions,
    validate_pending_dataset,
)
from verify_airi_style_dataset import (
    CATEGORY_TAXONOMY,
    GateError,
    canonical_sha256,
    load_jsonl,
    load_jsonl_bytes,
    prompt_sha256,
    sha256_file,
    validate_fixture,
    validate_fixture_rows,
    verify_reviewed_dataset,
)


def make_row(index, split, category):
    return {
        "id": f"style-{index:03d}",
        "split": split,
        "category": category,
        "prompt": f"오늘 기분은 어때 {index}",
        "answer": "좋아, 차분히 이야기할게.",
        "partition": {"tier": "S1", "group": f"reviewed-{index:03d}"},
        "review": {
            "status": "approved",
            "reviewer": "reviewer-alex",
            "approved_at": "2026-08-08T00:00:00Z",
        },
        "provenance": {"synthetic": True, "source": "curated-synthetic"},
        "training_eligible": True,
    }


def make_fixture(tier):
    prompt = f"{tier} 점검 문장"
    answer = "점검 결과는 안정적이야."
    return {
        "schema_version": 1,
        "suite_id": "airi-c0-s1-evaluation",
        "suite_version": "1.0",
        "tier": tier,
        "case_id": f"{tier.lower()}-case-001",
        "group": f"{tier.lower()}-holdout-001",
        "prompt": prompt,
        "answer": answer,
        "prompt_sha256": prompt_sha256(prompt),
        "example_sha256": canonical_sha256({"prompt": prompt, "answer": answer}),
    }


def write_jsonl(path, rows):
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def make_bundle(directory):
    rows = [
        make_row(
            index,
            "train" if index < 160 else "dev" if index < 180 else "test",
            CATEGORY_TAXONOMY[index % len(CATEGORY_TAXONOMY)],
        )
        for index in range(200)
    ]
    dataset = directory / "reviewed.jsonl"
    write_jsonl(dataset, rows)
    manifest = directory / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 3,
        "policy_version": "airi-style-qlora/v3",
        "dataset_sha256": sha256_file(dataset),
        "human_approved": True,
        "approved_by": "reviewer-alex",
        "approved_at": "2026-08-08T00:00:00Z",
        "reviewed_record_count": 200,
        "categories": list(CATEGORY_TAXONOMY),
        "reviewer_provenance": {
            "review_program": "independent-review",
            "dataset_author": "author-kim",
            "fixture_owner": "fixture-lee",
            "independent_review": True,
            "reviewers": [{
                "id": "reviewer-alex",
                "role": "senior-reviewer",
                "affiliation": "quality-team",
            }],
        },
    }, ensure_ascii=False), encoding="utf-8")
    c0_fixture = directory / "c0.jsonl"
    s1_fixture = directory / "s1.jsonl"
    write_jsonl(c0_fixture, [make_fixture("C0")])
    write_jsonl(s1_fixture, [make_fixture("S1")])
    return rows, dataset, manifest, c0_fixture, s1_fixture


class VerifyAiriStyleDatasetTests(unittest.TestCase):
    def test_fixture_byte_helpers_match_path_helpers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_path = Path(temp_dir) / "c0.jsonl"
            write_jsonl(fixture_path, [make_fixture("C0")])

            rows = load_jsonl(fixture_path, "C0 fixture")
            self.assertEqual(rows, load_jsonl_bytes(fixture_path.read_bytes(), "C0 fixture"))
            self.assertEqual(
                validate_fixture(fixture_path, "C0"),
                validate_fixture_rows(rows, "C0"),
            )

    def test_production_v3_shape_balance_split_and_s1_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            _, dataset, manifest, c0_fixture, s1_fixture = make_bundle(Path(temp_dir))
            result = verify_reviewed_dataset(dataset, manifest, c0_fixture, s1_fixture)

        self.assertEqual(result.report_payload["splits"], {
            "dev": 20,
            "test": 20,
            "train": 160,
        })

    def test_production_rejects_pending_and_c0(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            rows, dataset, manifest, c0_fixture, s1_fixture = make_bundle(Path(temp_dir))
            rows[0]["review"]["status"] = "pending"
            write_jsonl(dataset, rows)
            with self.assertRaises(GateError):
                verify_reviewed_dataset(dataset, manifest, c0_fixture, s1_fixture)

            rows[0]["review"]["status"] = "approved"
            rows[0]["partition"]["tier"] = "C0"
            write_jsonl(dataset, rows)
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            manifest_payload["dataset_sha256"] = sha256_file(dataset)
            manifest.write_text(json.dumps(manifest_payload), encoding="utf-8")
            with self.assertRaisesRegex(GateError, "S1"):
                verify_reviewed_dataset(dataset, manifest, c0_fixture, s1_fixture)

    def test_pending_seed_passes_pending_gate_while_production_and_trainer_reject(self):
        pending = TRAINING_DIR / "seed" / "airi_style_seed_pending.jsonl"
        self.assertEqual(validate_pending_dataset(pending)["record_count"], 200)
        with self.assertRaises(GateError):
            verify_reviewed_dataset(pending, pending, pending, pending)
        rows = [json.loads(line) for line in pending.read_text(encoding="utf-8").splitlines()]
        with self.assertRaises(TrainingRefused):
            _assert_train_rows((rows[0],))

    def test_pending_rejects_approved_eligible_duplicate_private_and_questions(self):
        pending = TRAINING_DIR / "seed" / "airi_style_seed_pending.jsonl"
        rows = [json.loads(line) for line in pending.read_text(encoding="utf-8").splitlines()]
        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "bad.jsonl"
            rows[0]["review"]["status"] = "approved"
            write_jsonl(bad, rows)
            with self.assertRaises(GateError):
                validate_pending_dataset(bad)

            rows[0]["review"] = {"status": "pending", "reviewer": "", "approved_at": ""}
            rows[1]["id"] = rows[0]["id"]
            write_jsonl(bad, rows)
            with self.assertRaisesRegex(GateError, "duplicate"):
                validate_pending_dataset(bad)

            rows[1]["id"] = "seed-002"
            rows[1]["prompt"] = "a@b.com"
            write_jsonl(bad, rows)
            with self.assertRaises(GateError):
                validate_pending_dataset(bad)

            rows[1]["prompt"] = "그냥 말해"
            for index, item in enumerate(rows[:11]):
                item["answer"] = f"구체적으로 어떤 장면이었어 {index}?"
            write_jsonl(bad, rows)
            with self.assertRaisesRegex(GateError, "exceed"):
                validate_pending_dataset(bad)

    def test_decision_approval_requires_voice_no_counselor_tone_and_safety(self):
        pending = TRAINING_DIR / "seed" / "airi_style_seed_pending.jsonl"
        rows = [json.loads(line) for line in pending.read_text(encoding="utf-8").splitlines()]
        decision = {
            "id": rows[0]["id"],
            "record_sha256": record_sha256(rows[0]),
            "decision": "approve",
            "vtuber_voice": True,
            "counselor_tone": False,
            "safety_truth": True,
            "notes": "independent review",
            "reviewer": "reviewer-alex",
            "reviewed_at": "2026-08-09T00:00:00Z",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            sidecar = Path(temp_dir) / "decisions.jsonl"
            write_jsonl(sidecar, [decision])
            validate_decisions(sidecar, {rows[0]["id"]: rows[0]})

            decision["counselor_tone"] = True
            write_jsonl(sidecar, [decision])
            with self.assertRaisesRegex(GateError, "approval requires"):
                validate_decisions(sidecar, {rows[0]["id"]: rows[0]})


if __name__ == "__main__":
    unittest.main()
