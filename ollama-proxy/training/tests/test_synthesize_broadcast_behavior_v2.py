from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


builder = load("synthesize_broadcast_behavior_v2")
trainer = load("train_airi_behavior_lora")
SOURCE = HERE / "seed" / "airi_broadcast_behavior_v2.jsonl"
SCHEMA = HERE / "seed" / "airi_broadcast_behavior_v2.schema.json"
EXPECTED_SHA256 = "eb4891006206ee6ad0c978f1ac1e152844fec06175a299aeaaeb151453d48ed1"


class BroadcastBehaviorV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = SOURCE.read_bytes()
        cls.rows = [json.loads(line) for line in cls.payload.decode("utf-8").splitlines()]

    def test_committed_source_is_exact_deterministic_output(self):
        self.assertEqual(hashlib.sha256(self.payload).hexdigest(), EXPECTED_SHA256)
        self.assertEqual(self.payload.decode("utf-8"), builder.render_jsonl(builder.build_records()))

    def test_stratified_distribution_and_safety_holdouts(self):
        self.assertEqual(len(self.rows), 240)
        self.assertEqual(Counter(row["category"] for row in self.rows), builder.QUOTAS)
        self.assertEqual(Counter(row["split"] for row in self.rows), builder.EXPECTED_SPLITS)
        builder.validate_records(self.rows)
        for category in builder.CATEGORIES[:-1]:
            rows = [row for row in self.rows if row["category"] == category]
            self.assertEqual(Counter(row["split"] for row in rows), {"train": 16, "dev": 2, "test": 2})
        for safety_class in builder.SAFETY_CLASSES:
            rows = [row for row in self.rows if row["event"]["safety_class"] == safety_class]
            self.assertEqual(Counter(row["split"] for row in rows), {"train": 3, "dev": 1, "test": 1})

    def test_schema_and_provenance_are_strict(self):
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(builder.CATEGORIES), set(schema["properties"]["category"]["enum"]))
        for row in self.rows:
            self.assertTrue(row["provenance"]["synthetic"])
            self.assertFalse(row["provenance"]["official_transcript_used"])
            self.assertTrue(row["provenance"]["reference_mechanics_only"])
            self.assertFalse(row["review"]["human_review_per_row"])
            self.assertTrue(row["review"]["user_aggregate_authorized"])
            self.assertTrue(row["review"]["root_quality_audit"])

    def test_mutations_fail_closed(self):
        meta = copy.deepcopy(self.rows)
        meta[0]["prompt"] = "안전한 답변을 해줘"
        with self.assertRaisesRegex(ValueError, "meta prompt"):
            builder.validate_records(meta)

        broken = copy.deepcopy(self.rows)
        broken[0]["prompt"] = "?? ??? ????"
        with self.assertRaisesRegex(ValueError, "broken text encoding"):
            builder.validate_records(broken)

        duplicate = copy.deepcopy(self.rows)
        duplicate[-1]["answer"] = duplicate[-2]["answer"]
        duplicate[-1]["target"] = duplicate[-2]["answer"]
        with self.assertRaisesRegex(ValueError, "duplicate|skeleton"):
            builder.validate_records(duplicate)

        formal = copy.deepcopy(self.rows)
        selected = next(row for row in formal if row["category"] == "selected_proposal")
        selected["answer"] = selected["target"] = "제안을 확인했습니다. 지금부터 그 방향으로 차분하게 진행하겠습니다. 화면의 근거를 먼저 확인하고 다음 장면으로 이동하겠습니다."
        with self.assertRaisesRegex(ValueError, "casual banmal"):
            builder.validate_records(formal)

    def test_export_uses_exact_production_v4_prompt_and_trainer_shape(self):
        chat = builder.export_chat(self.rows)
        self.assertEqual(len(chat), 240)
        self.assertIn("70~220자 2~4문장", chat[0]["messages"][0]["content"])
        self.assertIn("[방송 발화 계약]", chat[0]["messages"][0]["content"])
        self.assertEqual(chat[0]["messages"][0]["content"], builder.production_system_content())
        self.assertEqual(chat[0]["messages"][1]["name"], "airi_request_local")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chat.jsonl"
            payload = builder.render_jsonl(chat).encode("utf-8")
            path.write_bytes(payload)
            loaded = trainer.load_pinned_dataset(path, hashlib.sha256(payload).hexdigest())
        self.assertEqual(len(loaded), 240)
        self.assertEqual(Counter(row["split"] for row in loaded), builder.EXPECTED_SPLITS)

    def test_no_reference_identity_urls_pii_or_prior_target_overlap(self):
        whole = "\n".join(json.dumps(row, ensure_ascii=False) for row in self.rows)
        self.assertNotRegex(whole, r"https?://|www\.|@[A-Za-z0-9_]{3,}|\b[\w.+-]+@[\w.-]+\.")
        self.assertNotRegex(whole, r"\b(?:01[0-9]-?\d{3,4}-?\d{4}|\d{6}-[1-4]\d{6})\b")
        old_targets = set()
        for path in (HERE / "seed").glob("*.jsonl"):
            if path == SOURCE:
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row.get("target"), str):
                    old_targets.add(row["target"])
                if isinstance(row.get("answer"), str):
                    old_targets.add(row["answer"])
        self.assertFalse({row["answer"] for row in self.rows} & old_targets)


if __name__ == "__main__":
    unittest.main()
