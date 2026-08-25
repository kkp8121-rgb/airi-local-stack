import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import verify_general_capability_gate as gate  # noqa: E402


def _candidate(groups: dict[str, float], subtasks: dict[str, float], **config) -> dict:
    results = {name: {"acc,none": value, "acc_stderr,none": 0.01} for name, value in {**groups, **subtasks}.items()}
    return {"results": results,
            "config": {"num_fewshot": 0, "batch_size": 16, "limit": None,
                       "model_args": {"pretrained": "D:\\candidate", "dtype": "bfloat16"}, **config}}


class GeneralCapabilityGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = gate.load_baseline(gate.DEFAULT_BASELINE)
        self.groups = dict(self.baseline["groups"])
        self.subtasks = dict(self.baseline["subtasks"])

    def test_committed_baseline_is_well_formed_and_pinned_to_the_evidence(self) -> None:
        self.assertEqual(self.baseline["schema_version"], gate.BASELINE_SCHEMA_VERSION)
        self.assertEqual(set(self.groups), {"kobest", "haerae"})
        self.assertEqual(len(self.subtasks), 10)
        self.assertEqual(self.baseline["gate"]["max_group_drop_pct_points"], 2.0)
        self.assertRegex(self.baseline["stock_model"]["results_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(self.baseline["harness"]["limit"], None)

    def test_candidate_within_budget_passes(self) -> None:
        # The measured E2-C2 merge: kobest -0.90%p, haerae -1.92%p.
        groups = {"kobest": 0.6749, "haerae": 0.7003}
        verdict = gate.judge(self.baseline, _candidate(groups, self.subtasks), "0" * 64)
        self.assertEqual(verdict["status"], "pass")
        self.assertEqual(verdict["failed_groups"], [])
        self.assertAlmostEqual(verdict["groups"]["haerae"]["drop_pct_points"], 1.92, places=2)
        self.assertFalse(verdict["adoption_authorized"])

    def test_drop_over_budget_fails_closed_on_that_group_only(self) -> None:
        groups = {"kobest": 0.6838, "haerae": 0.6990}  # -2.05%p
        verdict = gate.judge(self.baseline, _candidate(groups, self.subtasks), "0" * 64)
        self.assertEqual(verdict["status"], "fail")
        self.assertEqual(verdict["failed_groups"], ["haerae"])
        self.assertTrue(verdict["groups"]["kobest"]["passed"])

    def test_exactly_at_budget_passes(self) -> None:
        groups = {"kobest": round(0.6838 - 0.02, 4), "haerae": 0.7195}
        verdict = gate.judge(self.baseline, _candidate(groups, self.subtasks), "0" * 64)
        self.assertEqual(verdict["status"], "pass")

    def test_missing_group_or_subtask_is_a_gate_error(self) -> None:
        with self.assertRaisesRegex(gate.GateError, "lacks group haerae"):
            gate.judge(self.baseline, _candidate({"kobest": 0.68}, self.subtasks), "0" * 64)
        subtasks = dict(self.subtasks); subtasks.pop("kobest_wic")
        with self.assertRaisesRegex(gate.GateError, "lacks subtask kobest_wic"):
            gate.judge(self.baseline, _candidate(self.groups, subtasks), "0" * 64)

    def test_different_harness_settings_are_refused(self) -> None:
        for override in ({"num_fewshot": 5}, {"batch_size": 4}, {"limit": 100}):
            with self.subTest(override=override):
                with self.assertRaisesRegex(gate.GateError, "harness settings differ"):
                    gate.judge(self.baseline, _candidate(self.groups, self.subtasks, **override), "0" * 64)

    def test_budget_cannot_be_relaxed_from_the_command_line(self) -> None:
        # The threshold lives only in the committed baseline; no CLI override exists.
        with tempfile.TemporaryDirectory() as raw:
            candidate = Path(raw) / "results.json"
            candidate.write_text(json.dumps(_candidate({"kobest": 0.60, "haerae": 0.60}, self.subtasks)), encoding="utf-8")
            self.assertEqual(gate.main(["--candidate", str(candidate)]), 1)
            with self.assertRaises(SystemExit):
                gate.main(["--candidate", str(candidate), "--max-group-drop-pct-points", "50"])

    def test_string_typed_harness_values_from_lm_eval_are_accepted(self) -> None:
        # Real results files carry batch_size as the CLI string "16".
        verdict = gate.judge(self.baseline, _candidate(self.groups, self.subtasks, batch_size="16", num_fewshot=0), "0" * 64)
        self.assertEqual(verdict["status"], "pass")

    def test_main_writes_a_no_overwrite_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            candidate = Path(raw) / "results.json"
            candidate.write_text(json.dumps(_candidate(self.groups, self.subtasks)), encoding="utf-8")
            out = Path(raw) / "verdict.json"
            self.assertEqual(gate.main(["--candidate", str(candidate), "--output", str(out)]), 0)
            verdict = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(verdict["schema_version"], gate.VERDICT_SCHEMA_VERSION)
            self.assertEqual(verdict["status"], "pass")
            self.assertEqual(gate.main(["--candidate", str(candidate), "--output", str(out)]), 1)

    def test_tampered_baseline_is_refused(self) -> None:
        tampered = copy.deepcopy(self.baseline)
        tampered["gate"]["max_group_drop_pct_points"] = 0
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "baseline.json"
            path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(gate.GateError, "budget"):
                gate.load_baseline(path)


if __name__ == "__main__":
    unittest.main()
