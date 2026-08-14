import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import run_airi_p7_common_render_probe as runner


class Tests(unittest.TestCase):
    def test_fixed_order_hashes_and_percentiles(self):
        rows = [
            {
                "trial": index + 1,
                "prompt_sha256": str(index),
                "render_ms": index,
                "completion_ms": index * 2,
                "playback_started_ms": 1,
            }
            for index in range(10)
        ]
        manifest = {"candidate_id": "qwen3-4b", "exact_revision": "a" * 40}
        value = runner.build_report(
            manifest,
            "f" * 64,
            {"model": "qwen3:4b", "digest": "d" * 64, "num_ctx": 2048},
            "b" * 64,
            "c" * 40,
            rows,
            "game running",
            "complete",
            "b" * 64,
        )
        self.assertEqual(10, value["prompt_count"])
        self.assertEqual(4.5, value["metrics"]["render_ms"]["p50"])
        self.assertEqual(8.55, value["metrics"]["render_ms"]["p95"])
        self.assertTrue(value["asar"]["unchanged"])

    def test_measure_schema_loopback_and_source_root(self):
        with self.assertRaises(runner.P7Error):
            runner.loopback("https://example.com")
        called = []

        def command(args):
            called.append(args)
            return json.dumps(
                {
                    "ok": True,
                    "first_region_after_completion_ms": 123,
                    "completed_ms": 45,
                    "playback_started_ms": 12,
                }
            )

        value = runner.run_measure("meter.ps1", "안녕", "source", command)
        self.assertEqual(123, value["render_ms"])
        self.assertIn("source", called[0])
        with self.assertRaises(runner.P7Error):
            runner.run_measure("x", "x", "source", lambda _: '{"raw":"text"}')

    def test_atomic_content_free_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "x.json"
            runner.atomic(
                path,
                {
                    "rows": [
                        {
                            "trial": 1,
                            "prompt_sha256": "a" * 64,
                            "render_ms": 1,
                            "completion_ms": 2,
                        }
                    ]
                },
            )
            value = json.loads(path.read_text())
            self.assertNotIn("안녕", path.read_text())
            self.assertEqual(1, value["rows"][0]["render_ms"])


if __name__ == "__main__":
    unittest.main()
