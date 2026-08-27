"""보정 채점 도구의 오프라인 계약 테스트. 네트워크·GPU·설치본 없이 돈다."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import calibrate_ratings as calibrator  # noqa: E402
import summarize_ratings as summarizer  # noqa: E402

SESSION = "sess-calib"


def rating(rater: str, scores_by_turn: dict[int, list[int]],
           flags_by_turn: dict[int, dict] | None = None) -> dict:
    flags_by_turn = flags_by_turn or {}
    return {
        "schema_version": calibrator.SCHEMA_VERSION, "rater": rater,
        "turns": [
            {"session_id": SESSION, "turn_no": turn_no,
             "scores": dict(zip(calibrator.AXIS_KEYS, values)),
             "flags": {flag: bool(flags_by_turn.get(turn_no, {}).get(flag, False))
                       for flag in calibrator.FLAG_KEYS}}
            for turn_no, values in sorted(scores_by_turn.items())
        ],
    }


def write(directory: Path, name: str, payload: dict) -> Path:
    path = directory / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class EnsembleTests(unittest.TestCase):
    def test_scores_are_averaged_and_critical_is_a_union(self):
        a = rating("a", {1: [1, 1, 1, 1, 1]}, {1: {"critical_failure": True}})
        b = rating("b", {1: [3, 3, 3, 3, 3]}, {1: {"silence_or_filler": True}})
        merged = calibrator.ensemble([
            {t["turn_no"]: t for t in a["turns"]}, {t["turn_no"]: t for t in b["turns"]}])
        self.assertEqual(merged[1]["scores"]["broadcast_likeness"], 2.0)
        # critical 은 한 명만 잡아도 살린다 — 놓치면 끝이므로.
        self.assertTrue(merged[1]["flags"]["critical_failure"])
        # 나머지 플래그는 과반이라야 산다. 2인 중 1인은 과반이 아니다.
        self.assertFalse(merged[1]["flags"]["silence_or_filler"])

    def test_only_shared_turns_survive(self):
        a = rating("a", {1: [3] * 5, 2: [3] * 5})
        b = rating("b", {2: [3] * 5, 3: [3] * 5})
        merged = calibrator.ensemble([
            {t["turn_no"]: t for t in a["turns"]}, {t["turn_no"]: t for t in b["turns"]}])
        self.assertEqual(sorted(merged), [2])

    def test_duplicate_turn_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = rating("a", {1: [3] * 5})
            payload["turns"].append(dict(payload["turns"][0]))
            path = write(Path(tmp), "dupe.json", payload)
            with self.assertRaises(calibrator.CalibrationError):
                calibrator.load_rating(path)


class SelectTests(unittest.TestCase):
    def setUp(self):
        # 3축 합성이 1..5 로 고르게 퍼진 20턴.
        self.ai = calibrator.ensemble([{t["turn_no"]: t for t in rating(
            "a", {n: [1 + (n - 1) % 5] * 5 for n in range(1, 21)})["turns"]}])

    def test_selection_spans_the_score_range(self):
        picked = calibrator.select_turns(self.ai, 5)
        self.assertEqual(len(picked), 5)
        values = {calibrator.composite(self.ai[t]["scores"]) for t in picked}
        # 층마다 하나씩 골랐으므로 점수 구간 전체가 덮여야 한다.
        self.assertEqual(values, {1.0, 2.0, 3.0, 4.0, 5.0})

    def test_selection_is_deterministic(self):
        self.assertEqual(calibrator.select_turns(self.ai, 7), calibrator.select_turns(self.ai, 7))

    def test_selection_rejects_impossible_sizes(self):
        with self.assertRaises(calibrator.CalibrationError):
            calibrator.select_turns(self.ai, 1)
        with self.assertRaises(calibrator.CalibrationError):
            calibrator.select_turns(self.ai, len(self.ai) + 1)


class CalibrateTests(unittest.TestCase):
    def test_offset_recovers_a_constant_bias(self):
        # AI 가 전 축에서 정확히 1점 낮게 준 상황. 사람이 4턴만 채점해도 전부 복원돼야 한다.
        ai_raw = rating("ai", {n: [2] * 5 for n in range(1, 11)})
        human = rating("human", {n: [3] * 5 for n in range(1, 5)})
        ai = calibrator.ensemble([{t["turn_no"]: t for t in ai_raw["turns"]}])
        result = calibrator.calibrate(ai, {t["turn_no"]: t for t in human["turns"]})
        self.assertAlmostEqual(result["calibration"]["composite_estimate"], 3.0)
        for axis, offset in result["calibration"]["axis_offsets"].items():
            self.assertAlmostEqual(offset, 1.0, msg=axis)
        self.assertEqual(result["calibration"]["turns_human"], 4)
        self.assertEqual(result["calibration"]["turns_calibrated"], 6)

    def test_human_turns_are_kept_verbatim(self):
        ai_raw = rating("ai", {n: [2] * 5 for n in range(1, 11)})
        human = rating("human", {1: [5, 4, 3, 2, 1]})
        human["turns"].append({"session_id": SESSION, "turn_no": 2,
                               "scores": dict(zip(calibrator.AXIS_KEYS, [1] * 5)),
                               "flags": {f: False for f in calibrator.FLAG_KEYS}})
        ai = calibrator.ensemble([{t["turn_no"]: t for t in ai_raw["turns"]}])
        result = calibrator.calibrate(ai, {t["turn_no"]: t for t in human["turns"]})
        by_turn = {t["turn_no"]: t for t in result["turns"]}
        self.assertEqual(by_turn[1]["scores"], dict(zip(calibrator.AXIS_KEYS, [5, 4, 3, 2, 1])))
        self.assertEqual(by_turn[1]["source"], "human")
        self.assertEqual(by_turn[3]["source"], "calibrated")

    def test_calibrated_scores_stay_inside_the_scale(self):
        ai_raw = rating("ai", {n: [5] * 5 for n in range(1, 11)})
        human = rating("human", {n: [5] * 5 for n in range(1, 5)})
        # 사람이 표본에서 만점을 줬는데 AI 도 만점이면 오프셋 0 이지만, 경계를 넘겨도
        # 1..5 밖으로 나가면 안 된다는 계약을 확인한다.
        human["turns"][0]["scores"] = dict(zip(calibrator.AXIS_KEYS, [5] * 5))
        ai = calibrator.ensemble([{t["turn_no"]: t for t in ai_raw["turns"]}])
        result = calibrator.calibrate(ai, {t["turn_no"]: t for t in human["turns"]})
        for turn in result["turns"]:
            for axis, value in turn["scores"].items():
                self.assertGreaterEqual(value, calibrator.SCORE_MIN, msg=axis)
                self.assertLessEqual(value, calibrator.SCORE_MAX, msg=axis)

    def test_output_passes_the_official_summarizer_schema(self):
        ai_raw = rating("ai", {n: [2] * 5 for n in range(1, 11)})
        human = rating("human", {n: [4] * 5 for n in range(1, 5)})
        ai = calibrator.ensemble([{t["turn_no"]: t for t in ai_raw["turns"]}])
        result = calibrator.calibrate(ai, {t["turn_no"]: t for t in human["turns"]})
        with tempfile.TemporaryDirectory() as tmp:
            path = write(Path(tmp), "calibrated.json", result)
            # 게이트 계산은 summarize_ratings.py 가 그대로 받아야 한다.
            payload = summarizer.load_ratings(path)
        self.assertEqual(payload["schema_version"], summarizer.SCHEMA_VERSION)
        self.assertEqual(len(payload["turns"]), 10)

    def test_human_turn_outside_the_ai_set_is_rejected(self):
        ai_raw = rating("ai", {n: [2] * 5 for n in range(1, 5)})
        human = rating("human", {1: [3] * 5, 99: [3] * 5})
        ai = calibrator.ensemble([{t["turn_no"]: t for t in ai_raw["turns"]}])
        with self.assertRaises(calibrator.CalibrationError):
            calibrator.calibrate(ai, {t["turn_no"]: t for t in human["turns"]})

    def test_standard_error_grows_when_the_residual_is_noisy(self):
        ai_raw = rating("ai", {n: [2] * 5 for n in range(1, 21)})
        quiet = rating("human", {n: [3] * 5 for n in range(1, 9)})
        noisy = rating("human", {n: [1 if n % 2 else 5] * 5 for n in range(1, 9)})
        ai = calibrator.ensemble([{t["turn_no"]: t for t in ai_raw["turns"]}])
        quiet_se = calibrator.calibrate(
            ai, {t["turn_no"]: t for t in quiet["turns"]})["calibration"]["composite_standard_error"]
        noisy_se = calibrator.calibrate(
            ai, {t["turn_no"]: t for t in noisy["turns"]})["calibration"]["composite_standard_error"]
        self.assertEqual(quiet_se, 0.0)
        self.assertGreater(noisy_se, 0.5)


class ReportTests(unittest.TestCase):
    def _result(self, estimate: float, error: float) -> dict:
        return {"calibration": {
            "turns_total": 99, "turns_human": 30, "turns_calibrated": 69, "human_effort": 0.303,
            "axis_offsets": {axis: 0.0 for axis in calibrator.AXIS_KEYS},
            "composite_estimate": estimate, "composite_standard_error": error,
            "composite_interval_95": [estimate - 1.96 * error, estimate + 1.96 * error],
            "residual_sd": 0.5, "filler_rate": 0.1, "critical_count": 0, "human_turns": []}}

    def test_interval_crossing_the_gate_is_reported_as_undecided(self):
        text = "\n".join(calibrator.report_lines(self._result(3.05, 0.09), 3.0, 0.25))
        self.assertIn("판정 보류", text)

    def test_interval_clear_of_the_gate_is_reported_as_decidable(self):
        for estimate in (3.6, 2.0):
            text = "\n".join(calibrator.report_lines(self._result(estimate, 0.09), 3.0, 0.25))
            self.assertIn("확정 가능", text)
            self.assertNotIn("판정 보류", text)


if __name__ == "__main__":
    unittest.main()
