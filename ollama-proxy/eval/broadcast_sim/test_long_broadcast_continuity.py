import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import broadcast_sim as sim  # noqa: E402


FIXTURE_PATH = HERE / "long_broadcast_continuity_v1.json"


class LongBroadcastContinuityFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = sim.load_fixture(FIXTURE_PATH)
        cls.stream = sim.generate_stream(cls.fixture, seed=20260821)
        cls.picks = sim.plan_pickups(cls.stream, cls.fixture)

    def test_fixture_covers_three_hours_and_long_arc_bands(self) -> None:
        self.assertEqual(self.fixture["rates"]["broadcast_minutes"], 180)
        arcs = self.fixture["continuity_arcs"]
        self.assertEqual(len(arcs), 12)
        gaps = [arc["callback_minute"] - arc["seed_minute"] for arc in arcs]
        self.assertGreaterEqual(sum(gap >= 30 for gap in gaps), 12)
        self.assertGreaterEqual(sum(gap >= 90 for gap in gaps), 4)
        self.assertGreaterEqual(len({arc["event_type"] for arc in arcs}), 8)
        self.assertEqual(
            {arc["expected_source"] for arc in arcs},
            {"history", "briefing", "durable_memory", "show_arc"},
        )

    def test_stream_and_pickups_are_deterministic_and_keep_every_arc(self) -> None:
        again = sim.generate_stream(self.fixture, seed=20260821)
        self.assertEqual(sim.canonical_bytes(self.stream), sim.canonical_bytes(again))
        phase_pairs = {
            (pick["message"].get("arc_id"), pick["message"].get("arc_phase"))
            for pick in self.picks if pick["message"].get("arc_id")
        }
        expected = {
            (arc["id"], phase)
            for arc in self.fixture["continuity_arcs"]
            for phase in ("seed", "callback")
        }
        self.assertEqual(phase_pairs, expected)

    def test_positive_rows_score_all_long_callbacks(self) -> None:
        roster = [viewer["handle"] for viewer in self.fixture["viewers"]]
        rows = []
        arcs = {arc["id"]: arc for arc in self.fixture["continuity_arcs"]}
        for pick in self.picks:
            message = pick["message"]
            if not message.get("arc_id"):
                continue
            checks = arcs[message["arc_id"]][f"{message['arc_phase']}_checks"]
            body = checks["required_any"][0].replace(".*", " ")
            rows.append(sim.score_turn(
                pick, body,
                beat=sim.beat_at(self.fixture, message["minute"]),
                fallback_pool=(), roster_handles=roster,
            ))
        summary = sim.summarize_turns(rows)["continuity"]
        self.assertEqual(summary["seed_response"], {"hits": 12, "of": 12, "rate": 1.0})
        self.assertEqual(summary["callback"], {"hits": 12, "of": 12, "rate": 1.0})
        self.assertEqual(summary["long_callback_30m"], {"hits": 12, "of": 12, "rate": 1.0})
        self.assertEqual(
            summary["ultra_callback_90m"]["of"],
            sum(
                arc["callback_minute"] - arc["seed_minute"] >= 90
                for arc in self.fixture["continuity_arcs"]
            ),
        )
        self.assertEqual(summary["complete_arc"], {"hits": 12, "of": 12, "rate": 1.0})
        self.assertEqual(summary["forbidden_hit_turns"], 0)

    def test_wrong_callback_is_not_hidden_by_a_required_token(self) -> None:
        pick = next(
            pick for pick in self.picks
            if pick["message"].get("arc_id") == "arc-route-right"
            and pick["message"].get("arc_phase") == "callback"
        )
        row = sim.score_turn(
            pick, "오른쪽이 아니라 왼쪽을 권했다고 기억해.",
            beat=sim.beat_at(self.fixture, pick["message"]["minute"]),
            fallback_pool=(),
            roster_handles=[viewer["handle"] for viewer in self.fixture["viewers"]],
        )
        self.assertTrue(row["arc_required_met"])
        self.assertTrue(row["arc_forbidden_hits"])
        self.assertFalse(row["arc_callback_hit"])

    def test_fixture_validation_fails_closed_on_arc_drift(self) -> None:
        raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        mutations = []
        duplicate = copy.deepcopy(raw)
        duplicate["continuity_arcs"].append(copy.deepcopy(duplicate["continuity_arcs"][0]))
        mutations.append(duplicate)
        unknown_author = copy.deepcopy(raw)
        unknown_author["continuity_arcs"][0]["author"] = "실존하지않음"
        mutations.append(unknown_author)
        backwards = copy.deepcopy(raw)
        backwards["continuity_arcs"][0]["callback_minute"] = 1
        mutations.append(backwards)
        unknown_event = copy.deepcopy(raw)
        unknown_event["continuity_arcs"][0]["event_type"] = "freeform"
        mutations.append(unknown_event)
        for mutation in mutations:
            with self.subTest(mutation=mutations.index(mutation)):
                with self.assertRaises(sim.BroadcastSimError):
                    sim.validate_fixture(mutation)

    def test_fixture_is_synthetic_and_contains_no_reference_identity(self) -> None:
        text = FIXTURE_PATH.read_text(encoding="utf-8").lower()
        self.assertTrue(self.fixture["synthetic_only"])
        for forbidden in ("탬탬버린", "아리사", "youtube.com", "chzzk", "obs-"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
