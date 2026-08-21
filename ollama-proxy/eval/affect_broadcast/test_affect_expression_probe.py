import importlib.util
import json
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "affect_expression_probe", HERE / "run_affect_expression_probe.py",
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class AffectExpressionProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = probe.load_fixture()

    def test_default_cases_cover_the_intended_expression_modes(self) -> None:
        observed = {
            probe._find_turn(self.fixture, turn_id)[2]["expected_state"]["primary"]
            for turn_id in probe.DEFAULT_CASE_IDS
        }
        self.assertEqual(observed, {
            "playful_annoyed", "skeptical", "competitive", "pleased", "concerned",
        })

    def test_triplet_has_only_nested_request_local_additions(self) -> None:
        bodies, metadata = probe.build_triplet(self.fixture, "teasing-11", 42)
        self.assertEqual(set(bodies), set(probe.ARMS))
        self.assertEqual(metadata["primary"], "playful_annoyed")
        off, _, off_note = probe._local_note(bodies["off"])
        snapshot, _, snapshot_note = probe._local_note(bodies["snapshot"])
        expression, _, expression_note = probe._local_note(bodies["expression"])
        self.assertEqual(
            snapshot_note.removeprefix(off_note + "\n\n").splitlines()[0].split()[0],
            "[airi_affect_continuity",
        )
        self.assertIn("[airi_affect_expression ", expression_note)
        self.assertEqual(
            off["messages"][-1], snapshot["messages"][-1],
        )
        self.assertEqual(
            snapshot["messages"][-1], expression["messages"][-1],
        )
        self.assertEqual(
            json.loads(bodies["off"])["options"],
            json.loads(bodies["expression"])["options"],
        )

    def test_seed_changes_only_the_declared_sampling_option(self) -> None:
        left, _ = probe.build_triplet(self.fixture, "game-17", 42)
        right, _ = probe.build_triplet(self.fixture, "game-17", 43)
        for arm in probe.ARMS:
            a, b = json.loads(left[arm]), json.loads(right[arm])
            self.assertEqual(a["options"].pop("seed"), 42)
            self.assertEqual(b["options"].pop("seed"), 43)
            self.assertEqual(a, b)

    def test_invalid_case_seed_and_profile_fail_closed(self) -> None:
        with self.assertRaises(probe.ProbeError):
            probe.build_triplet(self.fixture, "missing", 42)
        with self.assertRaises(probe.ProbeError):
            probe.build_triplet(self.fixture, "teasing-11", -1)
        with self.assertRaises(probe.ProbeError):
            probe.build_triplet(self.fixture, "teasing-11", 42, max_tokens=0)


if __name__ == "__main__":
    unittest.main()
