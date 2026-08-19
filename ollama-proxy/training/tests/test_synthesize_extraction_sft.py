import importlib.util
import json
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("synthesize_extraction_sft_test",
                                              HERE / "synthesize_extraction_sft.py")
assert SPEC is not None and SPEC.loader is not None
synth = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(synth)

PENDING_PATH = HERE / "seed" / "airi_extraction_seed_pending.jsonl"
_GATE_FIXTURE_PATH = HERE.parent / "memory_benchmark_fixtures.json"
GATE_FIXTURES = (json.loads(_GATE_FIXTURE_PATH.read_text(encoding="utf-8"))
                 if _GATE_FIXTURE_PATH.exists() else None)


class ExtractionSynthesisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = synth.load_config()
        cls.records = synth.synthesize(cls.config)

    def test_generation_is_deterministic_and_committed_queue_matches(self) -> None:
        self.assertEqual(self.records, synth.synthesize(self.config))
        committed = [json.loads(line) for line in
                     PENDING_PATH.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(committed, self.records)

    def test_every_target_survives_its_own_span_verification(self) -> None:
        for record in self.records:
            target = json.loads(record["target"])
            survivors, dropped = synth.parse_stage_a_span(target, record["turns"])
            self.assertEqual(dropped, 0, record["id"])
            self.assertEqual(len(survivors["extracted"]), len(target["extracted"]), record["id"])

    def test_measured_failure_classes_are_represented(self) -> None:
        scenes = {record["scene"] for record in self.records}
        self.assertIn("state_change", scenes)      # 주체 선택 함정
        self.assertIn("placeholder_add", scenes)   # {{user}} 등록
        self.assertIn("skip_chatter", scenes)      # 과추출 억제 (정답 = 0건)
        for record in self.records:
            target = json.loads(record["target"])
            if record["scene"] == "skip_chatter":
                self.assertEqual(target["extracted"], [])
            if record["scene"] == "state_change":
                # 조직이 아니라 상태가 바뀐 인물을 뽑는다.
                item = target["extracted"][0]
                self.assertEqual(item["kind"], "entity")
                self.assertEqual(item["subtype"], "person")
                self.assertIn(item["name"], self.config["persons"])
            if record["scene"] == "placeholder_add":
                names = [item.get("name") for item in target["extracted"]]
                self.assertIn("{{user}}", names)

    def test_content_is_disjoint_from_gate_fixtures_and_behavior_pools(self) -> None:
        # 게이트가 held-out 평가로 남으려면 학습쌍에 게이트 어휘가 없어야 한다.
        corpus = "\n".join(record["turns"] + record["target"] for record in self.records)
        for forbidden in ("하린", "루나", "달빛 길드", "별빛 나침반", "북쪽 탑"):
            self.assertNotIn(forbidden, corpus, forbidden)
        behavior_config = (HERE / "behavior_synthesis_config_v1.json").read_text(encoding="utf-8")
        for person in self.config["persons"]:
            self.assertNotIn(person, behavior_config, person)
        if GATE_FIXTURES is not None:
            gate_text = json.dumps(GATE_FIXTURES, ensure_ascii=False)
            for person in self.config["persons"]:
                self.assertNotIn(person, gate_text, person)

    def test_records_follow_the_pending_governance_shape(self) -> None:
        seen = set()
        for record in self.records:
            self.assertRegex(record["id"], r"^xseed-[a-z_]+-[0-9]{4}$")
            self.assertNotIn(record["id"], seen)
            seen.add(record["id"])
            self.assertEqual(record["task"], "stage_a_span")
            self.assertEqual(record["review"], {"status": "pending", "reviewer": "", "approved_at": ""})
            self.assertIs(record["training_eligible"], False)
            self.assertEqual(record["partition"]["tier"], "S1")
            self.assertRegex(record["partition"]["group"], r"^xpending-[a-z0-9-]+$")
        splits = {split: sum(1 for record in self.records if record["split"] == split)
                  for split in ("train", "dev", "test")}
        self.assertGreater(splits["train"], splits["dev"])
        self.assertGreater(splits["dev"], 0)
        self.assertGreater(splits["test"], 0)


if __name__ == "__main__":
    unittest.main()
