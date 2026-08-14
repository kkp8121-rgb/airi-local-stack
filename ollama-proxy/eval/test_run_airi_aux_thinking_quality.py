import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import run_airi_aux_thinking_quality as runner


class Tests(unittest.TestCase):
    def setUp(self):
        self.digest = "a" * 64
        self.fixture = Path(__file__).with_name("airi_baseline_cases.json")
        self.manifest = Path(__file__).with_name("model-usage-manifests") / "qwen3-4b.json"

    def transport(self, method, url, body):
        if url.endswith("/api/tags"):
            return {"models": [{"name": "qwen3:4b", "digest": self.digest}]}
        if url.endswith("/api/show"):
            return {"digest": self.digest, "template": "pinned", "parameters": ""}
        if url.endswith("/api/generate"):
            return {"done": True}
        self.assertTrue(body["think"])
        self.assertEqual("qwen3:4b", body["model"])
        self.assertNotEqual(body["messages"][-1]["content"], body["messages"][-1].get("id"))
        return iter(
            [
                {"model": "qwen3:4b", "message": {"content": "안녕"}, "done": False},
                {
                    "model": "qwen3:4b",
                    "message": {"content": ""},
                    "done": True,
                    "eval_count": 2,
                    "eval_duration": 1000000000,
                },
            ]
        )

    def test_exact_runtime_fixture_and_content_free_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            result = runner.run_thinking_quality(
                manifest_path=self.manifest,
                runtime_model="qwen3:4b",
                expected_digest=self.digest,
                report_path=output,
                fixture_path=self.fixture,
                transport=self.transport,
            )
        self.assertEqual("complete", result["status"])
        self.assertEqual(16, len(result["rows"]))
        self.assertEqual(0.6, result["sampling"]["temperature"])
        self.assertEqual(1024, result["requested_options"]["num_predict"])
        raw = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("안녕", raw)
        self.assertIn("not_history_P5_or_latency", result["scope"])

    def test_granite_marks_unknown_sampling_unsupported(self):
        summary = runner._summary_options("granite-3.3-2b-instruct")
        self.assertIn("unsupported_options", summary)

    def test_digest_and_loopback_fail_closed(self):
        with self.assertRaises((runner.ThinkingQualityError, runner.RunnerError)):
            runner.run_thinking_quality(
                manifest_path=self.manifest,
                runtime_model="qwen3:4b",
                expected_digest=self.digest[:-1],
                report_path="unused.json",
                endpoint="https://example.com",
                fixture_path=self.fixture,
                transport=self.transport,
            )


if __name__ == "__main__":
    unittest.main()
