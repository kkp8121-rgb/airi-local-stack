"""리포트→평가지 JSONL 변환기의 오프라인 계약 테스트. 네트워크·GPU 없이 돈다."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_rating_sheet as sheet  # noqa: E402
import report_to_review_jsonl as converter  # noqa: E402


def sample_report() -> dict:
    return {
        "schema_version": "airi.broadcast-sim-report.v1",
        "topic_title": "AIRI 저스트 채팅 — 시청자와 수다",
        "transcript": [
            {"stage": "pre_session", "user": "[YouTube] 시드", "airi": "시드 응답"},
            {"stage": "scripted_opening", "airi": "왔네!"},
            {
                "stage": "turn", "turn_index": 1, "minute": 0, "beat": "opening",
                "kind": "question", "author": "시청자가명001", "chat": "오늘 뭐 하고 지냈어?",
                "user_sent": "[YouTube] 오늘 뭐 하고 지냈어?", "airi": "어제 늦게 자서 좀 졸려.",
                "raw": "어제 늦게 자서 좀 졸려.",
            },
            {
                "stage": "turn", "turn_index": 2, "minute": 1, "beat": "opening",
                "kind": "donation", "author": "시청자가명002", "chat": "응원해!",
                "user_sent": "[YouTube] 응원해!", "airi": "고마워, 진짜 힘난다.",
                "raw": "고마워, 진짜 힘난다.",
            },
            {"stage": "scripted_closing", "airi": "오늘 여기까지야."},
        ],
    }


class BuildRowsTests(unittest.TestCase):
    def test_only_turn_stages_become_rows(self) -> None:
        rows = converter.build_rows(sample_report(), "report-2026")
        self.assertEqual([row["turn_no"] for row in rows], [1, 2])
        self.assertEqual([row["session_id"] for row in rows], ["report-2026"] * 2)
        self.assertEqual(rows[0]["user"], "오늘 뭐 하고 지냈어?")
        self.assertEqual(rows[0]["assistant"], "어제 늦게 자서 좀 졸려.")

    def test_hashes_are_truncated_sha256_of_the_content(self) -> None:
        rows = converter.build_rows(sample_report(), "report-2026")
        expected = hashlib.sha256("응원해!".encode("utf-8")).hexdigest()[:16]
        self.assertEqual(rows[1]["user_hash"], expected)
        self.assertEqual(len(rows[1]["assistant_hash"]), 16)

    def test_empty_answer_still_produces_a_ratable_row(self) -> None:
        report = sample_report()
        report["transcript"][2]["airi"] = ""
        rows = converter.build_rows(report, "report-2026")
        self.assertEqual(rows[0]["assistant"], "")

    def test_malformed_transcript_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            converter.build_rows({"transcript": "nope"}, "s")
        with self.assertRaises(ValueError):
            converter.build_rows(
                {"transcript": [{"stage": "turn", "turn_index": 1, "chat": "x"}]}, "s")


class ConverterCliTests(unittest.TestCase):
    def test_output_is_consumable_by_the_rating_sheet_builder(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            report_path = root / "replay-report.json"
            report_path.write_text(json.dumps(sample_report(), ensure_ascii=False), encoding="utf-8")
            output_path = root / "review.jsonl"
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = converter.main(["--report", str(report_path), "--output", str(output_path)])
            self.assertEqual(code, 0)
            self.assertIn("turns=2", stdout.getvalue())

            turns = sheet.load_turns(output_path)
            self.assertEqual([turn["session_id"] for turn in turns], ["replay-report"] * 2)
            self.assertEqual([turn["turn_no"] for turn in turns], [1, 2])
            html = sheet.build_html(turns, "재생 평가", "rater")
            self.assertIn("오늘 뭐 하고 지냈어?", html)

    def test_repo_path_output_is_refused_without_the_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            report_path = Path(raw) / "report.json"
            report_path.write_text(json.dumps(sample_report(), ensure_ascii=False), encoding="utf-8")
            inside = Path(converter.HERE) / "should-not-exist.jsonl"
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = converter.main(["--report", str(report_path), "--output", str(inside)])
            self.assertEqual(code, 1)
            self.assertIn("refusing to write real dialogue", stderr.getvalue())
            self.assertFalse(inside.exists())

    def test_missing_report_and_empty_transcript_return_one(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(converter.main(
                    ["--report", str(root / "nope.json"), "--output", str(root / "o.jsonl")]), 1)
            empty = root / "empty.json"
            empty.write_text(json.dumps({"transcript": []}), encoding="utf-8")
            with redirect_stderr(stderr):
                self.assertEqual(converter.main(
                    ["--report", str(empty), "--output", str(root / "o.jsonl")]), 1)
            self.assertIn("no scored turns", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
