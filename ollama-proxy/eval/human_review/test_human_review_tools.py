"""사람 평가 도구 3종의 오프라인 계약 테스트. 네트워크·GPU·설치본 없이 돈다."""
from __future__ import annotations

import io
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import build_rating_sheet as sheet  # noqa: E402
import export_session_dialogue as exporter  # noqa: E402
import summarize_ratings as summarizer  # noqa: E402

# airi_memory.py 의 DDL 을 그대로 복사한 것. 스키마가 바뀌면 이 테스트가 먼저 깨져야 한다.
CONVERSATION_MESSAGE_DDL = """
            CREATE TABLE IF NOT EXISTS conversation_message (
              id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, turn_no INTEGER NOT NULL,
              role TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
              content TEXT NOT NULL, content_hash TEXT NOT NULL, extracted INTEGER NOT NULL DEFAULT 0
                CHECK(extracted IN (0,1)),
              -- NULL means this pre-metadata row is deliberately not eligible
              -- for bounded recall until it is naturally replaced/re-appended.
              recall_chars INTEGER CHECK(recall_chars IS NULL OR recall_chars >= 0),
              UNIQUE(session_id,turn_no,role)
            );
"""
SESSION_ACTIVITY_DDL = """
            CREATE TABLE IF NOT EXISTS session_activity (
              session_id TEXT PRIMARY KEY, latest_message_id INTEGER NOT NULL, latest_turn INTEGER NOT NULL
            );
"""
# (session_id, turn_no, role, content)
FIXTURE_ROWS = (
    ("sess-a", 1, "user", "안녕"),
    ("sess-a", 1, "assistant", "어 왔어"),
    ("sess-a", 2, "user", "뭐해"),
    ("sess-a", 2, "assistant", "게임 준비하고 있어요"),
    ("sess-a", 3, "user", "거기 있어?"),
    ("sess-b", 1, "user", "국밥 먹었어?"),
    ("sess-b", 1, "assistant", "당연하지 </script> 봐봐"),
    ("sess-b", 2, "user", "b2u"),
    ("sess-b", 2, "assistant", "b2a"),
    ("sess-b", 3, "user", "b3u"),
    ("sess-b", 3, "assistant", "b3a"),
)


def make_db(path: Path) -> None:
    """픽스처 메모리 DB 를 만든다."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(CONVERSATION_MESSAGE_DDL + SESSION_ACTIVITY_DDL)
        for index, (session_id, turn_no, role, content) in enumerate(FIXTURE_ROWS, start=1):
            conn.execute(
                "INSERT INTO conversation_message"
                "(id,session_id,turn_no,role,content,content_hash,extracted,recall_chars)"
                " VALUES(?,?,?,?,?,?,0,?)",
                (index, session_id, turn_no, role, content, f"h-{index}", len(content)),
            )
        conn.execute(
            "INSERT INTO session_activity VALUES('sess-a',5,3),('sess-b',11,3)"
        )
        conn.commit()
    finally:
        conn.close()


def run_main(module, argv: list[str]) -> tuple[int, str, str]:
    """CLI 를 in-process 로 돌리고 (exit code, stdout, stderr) 를 돌려준다."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = module.main(argv)
    return code, out.getvalue(), err.getvalue()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def rating_payload(rater: str, turns: list[dict]) -> dict:
    return {
        "schema_version": "airi.human-rating.v1",
        "rater": rater,
        "created_at": "2026-08-26T00:00:00Z",
        "turns": turns,
    }


def scores(broadcast: int, context: int, response: int, style: int, factuality: int) -> dict:
    return {
        "broadcast_likeness": broadcast,
        "context_retention": context,
        "response_appropriateness": response,
        "style_rules": style,
        "factuality": factuality,
    }


class ExportSessionDialogueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "memory.sqlite3"
        make_db(self.db)
        self.addCleanup(self.tmp.cleanup)

    def test_single_session_skips_incomplete_turn(self) -> None:
        output = self.root / "sess-a.jsonl"
        code, stdout, _err = run_main(
            exporter, ["--db", str(self.db), "--session", "sess-a", "--output", str(output)]
        )
        self.assertEqual(code, 0)
        rows = read_jsonl(output)
        self.assertEqual([row["turn_no"] for row in rows], [1, 2])
        self.assertEqual(rows[0]["user"], "안녕")
        self.assertEqual(rows[0]["assistant"], "어 왔어")
        self.assertEqual(rows[0]["user_hash"], "h-1")
        self.assertEqual(rows[0]["assistant_hash"], "h-2")
        self.assertIn("skipped_incomplete=1", stdout)
        self.assertIn("turns=2", stdout)
        self.assertNotIn("안녕", stdout)

    def test_all_sessions_ordered_by_session_then_turn(self) -> None:
        output = self.root / "all.jsonl"
        code, _stdout, _err = run_main(
            exporter, ["--db", str(self.db), "--all-sessions", "--output", str(output)]
        )
        self.assertEqual(code, 0)
        rows = read_jsonl(output)
        self.assertEqual(
            [(row["session_id"], row["turn_no"]) for row in rows],
            [("sess-a", 1), ("sess-a", 2), ("sess-b", 1), ("sess-b", 2), ("sess-b", 3)],
        )

    def test_since_turn_and_limit_turns(self) -> None:
        output = self.root / "window.jsonl"
        code, _stdout, _err = run_main(
            exporter,
            [
                "--db", str(self.db), "--session", "sess-b", "--since-turn", "2",
                "--limit-turns", "1", "--output", str(output),
            ],
        )
        self.assertEqual(code, 0)
        rows = read_jsonl(output)
        self.assertEqual([row["turn_no"] for row in rows], [2])

    def test_list_prints_counts_only(self) -> None:
        code, stdout, _err = run_main(exporter, ["--db", str(self.db), "--list"])
        self.assertEqual(code, 0)
        self.assertIn("sess-a\tturns=3\tlatest_turn=3", stdout)
        self.assertIn("sess-b\tturns=3\tlatest_turn=3", stdout)
        self.assertIn("sessions=2", stdout)
        self.assertNotIn("안녕", stdout)

    def test_refuses_output_inside_repository(self) -> None:
        inside = exporter.REPO_ROOT / "human-review-should-not-exist.jsonl"
        code, _stdout, err = run_main(
            exporter, ["--db", str(self.db), "--session", "sess-a", "--output", str(inside)]
        )
        self.assertEqual(code, 1)
        self.assertIn("refusing", err)
        self.assertFalse(inside.exists())

    def test_allow_repo_path_overrides_refusal(self) -> None:
        output = self.root / "inside.jsonl"
        with patch.object(exporter, "REPO_ROOT", self.root):
            refused, _stdout, err = run_main(
                exporter, ["--db", str(self.db), "--session", "sess-a", "--output", str(output)]
            )
            self.assertEqual(refused, 1)
            self.assertIn("refusing", err)
            allowed, _stdout, _err = run_main(
                exporter,
                [
                    "--db", str(self.db), "--session", "sess-a", "--output", str(output),
                    "--allow-repo-path",
                ],
            )
        self.assertEqual(allowed, 0)
        self.assertEqual(len(read_jsonl(output)), 2)

    def test_missing_db_and_argument_misuse(self) -> None:
        missing, _stdout, err = run_main(
            exporter,
            ["--db", str(self.root / "nope.sqlite3"), "--session", "s", "--output", str(self.root / "x.jsonl")],
        )
        self.assertEqual(missing, 1)
        self.assertIn("not found", err)
        both, _stdout, err_both = run_main(
            exporter,
            ["--db", str(self.db), "--session", "sess-a", "--all-sessions", "--output", str(self.root / "y.jsonl")],
        )
        self.assertEqual(both, 1)
        self.assertIn("exactly one", err_both)


class BuildRatingSheetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "memory.sqlite3"
        make_db(self.db)
        self.jsonl = self.root / "all.jsonl"
        run_main(exporter, ["--db", str(self.db), "--all-sessions", "--output", str(self.jsonl)])
        self.html_path = self.root / "sheet.html"
        code, _stdout, _err = run_main(
            sheet,
            ["--input", str(self.jsonl), "--output", str(self.html_path), "--rater", "평가자1"],
        )
        self.assertEqual(code, 0)
        self.html = self.html_path.read_text(encoding="utf-8")
        self.addCleanup(self.tmp.cleanup)

    def test_embeds_turns_and_rubric(self) -> None:
        self.assertIn("안녕", self.html)
        self.assertIn("어 왔어", self.html)
        self.assertIn('"turn_no": 3', self.html)
        for _key, label, _hint in sheet.AXES:
            self.assertIn(label, self.html)
        self.assertIn("JSON 내보내기", self.html)
        self.assertIn("JSON 불러오기", self.html)
        self.assertIn("미평가만 보기", self.html)
        self.assertIn('value="평가자1"', self.html)

    def test_dialogue_cannot_close_the_script_block(self) -> None:
        self.assertIn("당연하지 \\u003c/script\\u003e 봐봐", self.html)
        self.assertNotIn("당연하지 </script>", self.html)
        head, _sep, tail = self.html.partition('<script id="turn-data" type="application/json">')
        self.assertTrue(_sep)
        payload, _sep2, _rest = tail.partition("</script>")
        self.assertNotIn("<", payload)
        self.assertNotIn(">", payload)
        json.loads(payload.replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&"))
        self.assertTrue(head)

    def test_polite_hint_prefilled_only_for_polite_turn(self) -> None:
        turns = sheet.load_turns(self.jsonl)
        hints = {(turn["session_id"], turn["turn_no"]): turn["polite_hint"] for turn in turns}
        self.assertTrue(hints[("sess-a", 2)])
        self.assertFalse(hints[("sess-a", 1)])
        self.assertFalse(hints[("sess-b", 1)])

    def test_rejects_empty_and_malformed_input(self) -> None:
        empty = self.root / "empty.jsonl"
        empty.write_text("", encoding="utf-8")
        code, _stdout, err = run_main(
            sheet, ["--input", str(empty), "--output", str(self.root / "e.html")]
        )
        self.assertEqual(code, 1)
        self.assertIn("no turns", err)
        broken = self.root / "broken.jsonl"
        broken.write_text('{"session_id":"s","turn_no":1}\n', encoding="utf-8")
        code_broken, _stdout, err_broken = run_main(
            sheet, ["--input", str(broken), "--output", str(self.root / "b.html")]
        )
        self.assertEqual(code_broken, 1)
        self.assertIn("invalid input", err_broken)


class SummarizeRatingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.rater_one = self.root / "r1.json"
        self.rater_two = self.root / "r2.json"
        self.rater_one.write_text(
            json.dumps(
                rating_payload(
                    "r1",
                    [
                        {
                            "session_id": "sess-a", "turn_no": 1,
                            "scores": scores(4, 4, 4, 4, 4), "flags": {}, "comment": "",
                        },
                        {
                            "session_id": "sess-a", "turn_no": 2,
                            "scores": scores(2, 3, 4, 5, 4),
                            "flags": {"critical_failure": True},
                            "comment": "말투가 이상함",
                        },
                    ],
                ),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.rater_two.write_text(
            json.dumps(
                rating_payload(
                    "r2",
                    [
                        {
                            "session_id": "sess-a", "turn_no": 1,
                            "scores": scores(5, 5, 5, 5, 5), "flags": {}, "comment": "",
                        },
                        {
                            "session_id": "sess-a", "turn_no": 2,
                            "scores": scores(4, 3, 2, 5, 4),
                            "flags": {"polite_violation": True},
                            "comment": "",
                        },
                    ],
                ),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.summary_path = self.root / "summary.json"

    def summarize(self, *extra: str) -> tuple[int, str, str]:
        return run_main(
            summarizer,
            [
                "--ratings", str(self.rater_one), "--ratings", str(self.rater_two),
                "--output", str(self.summary_path), *extra,
            ],
        )

    def test_axis_stats_flag_rates_and_agreement(self) -> None:
        code, stdout, _err = self.summarize()
        self.assertEqual(code, 0)
        self.assertIn("ratings=4", stdout)
        summary = json.loads(self.summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["raters"], ["r1", "r2"])
        self.assertEqual(summary["n_ratings"], 4)
        self.assertEqual(summary["n_unique_turns"], 2)
        self.assertEqual(summary["n_sessions"], 1)
        self.assertEqual(summary["per_axis"]["broadcast_likeness"]["mean"], 3.75)
        self.assertEqual(summary["per_axis"]["broadcast_likeness"]["median"], 4.0)
        self.assertEqual(summary["per_axis"]["broadcast_likeness"]["min"], 2)
        self.assertEqual(summary["per_axis"]["factuality"]["mean"], 4.25)
        self.assertEqual(summary["all_axes_at_least_4_share"], 0.5)
        self.assertEqual(summary["flag_rates"]["critical_failure"], 0.25)
        self.assertEqual(summary["flag_rates"]["polite_violation"], 0.25)
        self.assertEqual(summary["flag_rates"]["invented_name"], 0.0)
        agreement = summary["agreement"]
        self.assertEqual(agreement["shared_turns"], 2)
        self.assertEqual(agreement["axis_mean_abs_diff"]["broadcast_likeness"], 1.5)
        self.assertEqual(agreement["axis_mean_abs_diff"]["context_retention"], 0.5)
        self.assertEqual(agreement["axis_mean_abs_diff"]["response_appropriateness"], 1.5)
        self.assertEqual(agreement["flag_disagreement_rate"]["critical_failure"], 0.5)
        self.assertEqual(agreement["flag_disagreement_rate"]["invented_name"], 0.0)
        self.assertEqual(summary["commented_ratings"], 1)

    def test_summary_never_contains_dialogue_or_comments(self) -> None:
        markdown_path = self.root / "summary.md"
        code, _stdout, _err = self.summarize("--markdown", str(markdown_path))
        self.assertEqual(code, 0)
        for text in (
            self.summary_path.read_text(encoding="utf-8"),
            markdown_path.read_text(encoding="utf-8"),
        ):
            self.assertNotIn("말투가 이상함", text)
            self.assertNotIn("comment", text.replace("commented_ratings", ""))
            self.assertNotIn("안녕", text)

    def test_single_rater_reports_no_shared_turns(self) -> None:
        code, _stdout, _err = run_main(
            summarizer, ["--ratings", str(self.rater_one), "--output", str(self.summary_path)]
        )
        self.assertEqual(code, 0)
        summary = json.loads(self.summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["agreement"]["shared_turns"], 0)
        self.assertEqual(summary["agreement"]["axis_mean_abs_diff"], {})

    def test_schema_errors_exit_one(self) -> None:
        cases = {
            "bad-score": rating_payload(
                "r3",
                [{"session_id": "s", "turn_no": 1, "scores": scores(7, 4, 4, 4, 4), "flags": {}}],
            ),
            "missing-axis": rating_payload(
                "r3",
                [{"session_id": "s", "turn_no": 1, "scores": {"broadcast_likeness": 4}, "flags": {}}],
            ),
            "unknown-flag": rating_payload(
                "r3",
                [
                    {
                        "session_id": "s", "turn_no": 1, "scores": scores(4, 4, 4, 4, 4),
                        "flags": {"vibes": True},
                    }
                ],
            ),
            "bad-version": {
                "schema_version": "airi.human-rating.v0", "rater": "r3",
                "created_at": "2026-08-26T00:00:00Z", "turns": [],
            },
            "blank-rater": rating_payload("  ", []),
            "no-turns": rating_payload("r3", []),
        }
        for name, payload in cases.items():
            with self.subTest(case=name):
                path = self.root / f"{name}.json"
                path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                code, _stdout, err = run_main(
                    summarizer,
                    ["--ratings", str(path), "--output", str(self.root / f"{name}-summary.json")],
                )
                self.assertEqual(code, 1)
                self.assertTrue(err.startswith("error:"))
                self.assertFalse((self.root / f"{name}-summary.json").exists())

    def test_axis_and_flag_keys_match_the_rating_sheet(self) -> None:
        self.assertEqual(summarizer.AXIS_KEYS, tuple(axis[0] for axis in sheet.AXES))
        self.assertEqual(summarizer.FLAG_KEYS, tuple(flag[0] for flag in sheet.FLAGS))
        self.assertEqual(summarizer.SCHEMA_VERSION, sheet.SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
