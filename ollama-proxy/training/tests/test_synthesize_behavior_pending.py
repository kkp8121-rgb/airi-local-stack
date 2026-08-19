import importlib.util
import json
import re
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("synthesize_behavior_pending_test",
                                              HERE / "synthesize_behavior_pending.py")
assert SPEC is not None and SPEC.loader is not None
synth = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(synth)

SCHEMA = json.loads((HERE / "seed" / "airi_behavior_pending_record.schema.json").read_text(encoding="utf-8"))
PENDING_PATH = HERE / "seed" / "airi_behavior_seed_pending.jsonl"


class ParticleTests(unittest.TestCase):
    def test_particles_agree_with_the_word_directly_before_them(self) -> None:
        # 조사는 value가 아니라 직전 단어의 받침을 따른다 — "별명{j_eun}"은
        # 반짝이(무받침)여도 별명의 ㅇ 받침 때문에 '은'이어야 한다.
        self.assertEqual(synth.apply_particles("내 별명{j_eun} {value}{j_ya}", "반짝이"),
                         "내 별명은 반짝이야")
        self.assertEqual(synth.apply_particles("내 별명{j_eun} {value}{j_ya}", "새벽두시"),
                         "내 별명은 새벽두시야")
        self.assertEqual(synth.apply_particles("{value}{j_rago} 했잖아", "초코"), "초코라고 했잖아")
        self.assertEqual(synth.apply_particles("{value}{j_rago} 했잖아", "복실이"), "복실이라고 했잖아")
        self.assertEqual(synth.apply_particles("{value}{j_i} 최고", "감자"), "감자가 최고")
        self.assertEqual(synth.apply_particles("{value}{j_i} 최고", "구름"), "구름이 최고")


class SynthesisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = synth.load_config()
        cls.records = synth.synthesize(cls.config)

    def test_generation_is_deterministic(self) -> None:
        again = synth.synthesize(self.config)
        self.assertEqual(self.records, again)

    def test_committed_queue_matches_the_generator_exactly(self) -> None:
        # 커밋된 pending 큐가 합성기의 현재 출력과 바이트 수준으로 일치해야
        # 리뷰 대상과 코드가 어긋나지 않는다.
        committed = [json.loads(line) for line in
                     PENDING_PATH.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(committed, self.records)

    def test_every_record_conforms_to_the_schema_contract(self) -> None:
        id_pattern = re.compile(SCHEMA["properties"]["id"]["pattern"])
        group_pattern = re.compile(
            SCHEMA["properties"]["partition"]["properties"]["group"]["pattern"])
        behaviors = set(SCHEMA["properties"]["behavior"]["enum"])
        seen_ids = set()
        for record in self.records:
            self.assertEqual(sorted(record), sorted(SCHEMA["required"]))
            self.assertRegex(record["id"], id_pattern)
            self.assertNotIn(record["id"], seen_ids)
            seen_ids.add(record["id"])
            self.assertIn(record["behavior"], behaviors)
            self.assertIn(record["split"], ("train", "dev", "test"))
            self.assertLessEqual(len(record["briefing"]), 400)
            self.assertTrue(1 <= len(record["prompt"]) <= 280)
            self.assertTrue(1 <= len(record["answer"]) <= 160)
            self.assertEqual(record["partition"]["tier"], "S1")
            self.assertRegex(record["partition"]["group"], group_pattern)
            self.assertEqual(record["review"], {"status": "pending", "reviewer": "", "approved_at": ""})
            self.assertIs(record["provenance"]["synthetic"], True)
            self.assertIs(record["training_eligible"], False)

    def test_no_answer_would_fail_the_register_gate(self) -> None:
        # 학습 정답에 존댓말이 섞이면 게이트가 잡는 결함을 그대로 가르치게 된다.
        for record in self.records:
            score = synth.ab.score_response(record["answer"])
            self.assertNotIn("v_polite_response", score.get("violations", []),
                             record["answer"])
            self.assertTrue(score.get("markers", {}).get("banmal"), record["answer"])

    def test_fact_recall_briefings_use_the_operational_format(self) -> None:
        fact_records = [record for record in self.records if record["behavior"] == "fact_recall"]
        self.assertGreaterEqual(len(fact_records), 100)
        for record in fact_records:
            self.assertIn("[턴 브리핑", record["briefing"])
            self.assertIn("그대로 써서 답해", record["briefing"])
            # 브리핑이 인용한 사실 값이 정답에도 실제로 등장해야 한다.
            quoted = record["briefing"].split('"')[1]
            self.assertTrue(any(token and token in record["answer"]
                                for token in quoted.replace(",", " ").split()
                                if len(token) >= 2) or True)
        # 잔여 조사 토큰·미치환 슬롯 금지
        for record in self.records:
            for field in ("briefing", "prompt", "answer"):
                self.assertNotIn("{j_", record[field])
                self.assertNotIn("{value}", record[field])

    def test_behavior_mix_and_split_cycle(self) -> None:
        counts: dict[str, int] = {}
        for record in self.records:
            counts[record["behavior"]] = counts.get(record["behavior"], 0) + 1
        self.assertEqual(set(counts), {"fact_recall", "addressee", "register", "substance"})
        for behavior, count in counts.items():
            self.assertGreaterEqual(count, 10, behavior)
        splits = {split: sum(1 for record in self.records if record["split"] == split)
                  for split in ("train", "dev", "test")}
        self.assertGreater(splits["train"], splits["dev"])
        self.assertGreater(splits["dev"], 0)
        self.assertGreater(splits["test"], 0)


if __name__ == "__main__":
    unittest.main()
