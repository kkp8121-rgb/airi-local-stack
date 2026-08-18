from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "run_embedding_ab.py"
SPEC = importlib.util.spec_from_file_location("run_embedding_ab_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def oracle_encoder(fixture: dict) -> "runner.Encoder":
    """A stub that places every query exactly on its own relevant document."""
    slots = {item["id"]: index for index, item in enumerate(fixture["corpus"])}
    size = len(slots)
    vectors = {item["text"]: [1.0 if slots[item["id"]] == index else 0.0 for index in range(size)]
               for item in fixture["corpus"]}
    for query in fixture["queries"]:
        vectors[query["text"]] = [1.0 if slots[query["relevant"][0]] == index else 0.0 for index in range(size)]

    def encode(texts):
        return [vectors[text] for text in texts]

    return encode


def adversarial_encoder(fixture: dict) -> "runner.Encoder":
    """A stub that always ranks the first document first, whatever the query."""
    size = len(fixture["corpus"])
    first = fixture["corpus"][0]["text"]

    def encode(texts):
        return [[1.0] + [0.0] * (size - 1) if text == first else [0.0, 1.0] + [0.0] * (size - 2)
                for text in texts]

    return encode


class FixtureTests(unittest.TestCase):
    def test_fixture_is_pinned_synthetic_and_self_consistent(self) -> None:
        fixture = runner.load_fixture()
        self.assertIs(fixture["synthetic_only"], True)
        self.assertEqual(len(fixture["corpus"]), 48)
        self.assertEqual(len(fixture["queries"]), 24)
        ids = [item["id"] for item in fixture["corpus"]]
        self.assertEqual(len(set(ids)), len(ids))
        counts = {category: 0 for category in runner.CATEGORIES}
        for query in fixture["queries"]:
            counts[query["category"]] += 1
            self.assertTrue(set(query["relevant"]) <= set(ids))
        # 카테고리를 고르게 채워야 평균이 한 축에 쏠리지 않는다.
        self.assertEqual(set(counts.values()), {6})

    def test_fixture_validation_fails_closed(self) -> None:
        fixture = runner.load_fixture()
        broken = [
            {**fixture, "schema_version": "other"},
            {**fixture, "synthetic_only": False},
            {**fixture, "corpus": []},
            {**fixture, "corpus": fixture["corpus"] + [fixture["corpus"][0]]},
            {**fixture, "queries": [{**fixture["queries"][0], "category": "vibes"}]},
            {**fixture, "queries": [{**fixture["queries"][0], "relevant": ["c99"]}]},
            {**fixture, "queries": [{**fixture["queries"][0], "relevant": []}]},
        ]
        for value in broken:
            with self.assertRaises(runner.EmbeddingAbError):
                runner.validate_fixture(value)

    def test_pinned_digest_rejects_edited_fixture(self) -> None:
        tampered = copy.deepcopy(runner.load_fixture())
        tampered["corpus"][0]["text"] = "바뀐 문장"
        path = HERE / "_tampered_fixture.json"
        path.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")
        try:
            with self.assertRaises(runner.EmbeddingAbError):
                runner.load_fixture(path)
            self.assertEqual(runner.load_fixture(path, verify_digest=False)["corpus"][0]["text"], "바뀐 문장")
        finally:
            path.unlink()


class ScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = runner.load_fixture()

    def test_perfect_encoder_scores_one(self) -> None:
        result = runner.evaluate(oracle_encoder(self.fixture), self.fixture, name="oracle")
        self.assertEqual(result["overall"]["mrr"], 1.0)
        self.assertEqual(result["overall"]["recall_at_1"], 1.0)
        self.assertEqual(result["overall"]["queries"], 24)
        self.assertEqual(result["misses"], [])
        for category in runner.CATEGORIES:
            self.assertEqual(result["by_category"][category]["recall_at_1"], 1.0)
            self.assertEqual(result["by_category"][category]["queries"], 6)

    def test_adversarial_encoder_is_not_credited(self) -> None:
        result = runner.evaluate(adversarial_encoder(self.fixture), self.fixture, name="adversarial")
        self.assertLess(result["overall"]["mrr"], 0.2)
        self.assertLessEqual(result["overall"]["recall_at_1"], round(1 / 24, 4))
        self.assertGreaterEqual(len(result["misses"]), 23)
        for miss in result["misses"]:
            self.assertIn(miss["category"], runner.CATEGORIES)

    def test_rank_helper_handles_ties_and_absence(self) -> None:
        scores = [("a", 0.9), ("b", 0.9), ("c", 0.1)]
        self.assertEqual(runner.rank_of_first_relevant(scores, ["b"]), 2)
        self.assertEqual(runner.rank_of_first_relevant(scores, ["c"]), 3)
        self.assertEqual(runner.rank_of_first_relevant(scores, ["a", "c"]), 1)
        self.assertIsNone(runner.rank_of_first_relevant(scores, ["missing"]))

    def test_unranked_queries_lower_the_mean_rather_than_vanish(self) -> None:
        summary = runner._summarize([1, None, 4])
        self.assertEqual(summary["queries"], 3)
        self.assertEqual(summary["mrr"], round((1 + 0.25) / 3, 4))
        self.assertEqual(summary["recall_at_1"], round(1 / 3, 4))
        self.assertEqual(summary["recall_at_5"], round(2 / 3, 4))

    def test_cosine_ignores_vector_scale(self) -> None:
        self.assertAlmostEqual(runner.cosine([1.0, 0.0], [4.0, 0.0]), 1.0)
        self.assertAlmostEqual(runner.cosine([1.0, 0.0], [0.0, 2.0]), 0.0)
        self.assertEqual(runner.cosine([0.0, 0.0], [1.0, 1.0]), 0.0)

    def test_encoder_length_mismatch_fails_closed(self) -> None:
        with self.assertRaises(runner.EmbeddingAbError):
            runner.evaluate(lambda texts: [[1.0]], self.fixture)


class CliTests(unittest.TestCase):
    def test_model_specs_require_name_and_path(self) -> None:
        self.assertEqual(runner.parse_model_specs(["kure=nlpai-lab/KURE-v1"]), [("kure", "nlpai-lab/KURE-v1")])
        for value in (["kure"], ["=path"], ["name="], []):
            with self.assertRaises(runner.EmbeddingAbError):
                runner.parse_model_specs(value)

    def test_missing_model_is_reported_without_network(self) -> None:
        report = HERE / "_cli_report.json"
        try:
            # 기본은 다운로드 금지 — 캐시에 없는 경로는 오류로 기록되고 다른 arm을 가리지 않는다.
            code = runner.main(["--model", "absent=./definitely-not-a-model", "--report", str(report)])
            payload = json.loads(report.read_text(encoding="utf-8"))
        finally:
            if report.exists():
                report.unlink()
        self.assertEqual(code, 1)
        self.assertIs(payload["network_allowed"], False)
        self.assertEqual(payload["models"][0]["status"], "error")
        self.assertEqual(payload["fixture_sha256"], runner.FIXTURE_SHA256)


if __name__ == "__main__":
    unittest.main()
