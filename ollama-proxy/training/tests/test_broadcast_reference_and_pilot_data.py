import json
import re
import unittest
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_DIR = REPO_ROOT / "airi_docs" / "참조" / "data"
REFERENCE_SCHEMA = REFERENCE_DIR / "airi_kr_broadcast_reference_event_v1.schema.json"
REFERENCE_EVENTS = REFERENCE_DIR / "airi_kr_broadcast_reference_events_2026-08-21.jsonl"
SOURCE_LEDGER = REFERENCE_DIR / "AIRI-KR-BROADCAST-REFERENCE-SOURCE-LEDGER-2026-08-21.json"
CONTINUITY_SCHEMA = REFERENCE_DIR / "airi_kr_broadcast_continuity_arc_v1.schema.json"
CONTINUITY_ARCS = REFERENCE_DIR / "airi_kr_broadcast_continuity_arcs_2026-08-21.jsonl"
CONTINUITY_LEDGER = REFERENCE_DIR / "AIRI-KR-BROADCAST-CONTINUITY-SOURCE-LEDGER-2026-08-21.json"
PILOT_SCHEMA = REPO_ROOT / "ollama-proxy" / "training" / "seed" / "airi_broadcast_response_pilot_record.schema.json"
PILOT_ROWS = REPO_ROOT / "ollama-proxy" / "training" / "seed" / "airi_broadcast_response_pilot_pending.jsonl"
PILOT_REVIEW = REPO_ROOT / "airi_docs" / "진행예정" / "AIRI-KR-BROADCAST-RESPONSE-PILOT-2026-08-21.md"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class BroadcastReferenceDataTest(unittest.TestCase):
    def test_observations_are_abstract_and_match_source_ledger(self) -> None:
        schema = json.loads(REFERENCE_SCHEMA.read_text(encoding="utf-8"))
        rows = load_jsonl(REFERENCE_EVENTS)
        ledger = json.loads(SOURCE_LEDGER.read_text(encoding="utf-8"))

        self.assertEqual(len(rows), 30)
        self.assertEqual(len({row["record_id"] for row in rows}), 30)
        self.assertEqual(len({row["source_case_id"] for row in rows}), 30)
        self.assertEqual(
            {row["source_case_id"] for row in rows},
            {source["source_case_id"] for source in ledger["sources"]},
        )
        required = set(schema["required"])
        allowed = set(schema["properties"])
        for row in rows:
            self.assertEqual(set(row), allowed)
            self.assertTrue(required <= set(row))
            self.assertEqual(row["schema_version"], "airi.broadcast-reference-event.v1")
            self.assertEqual(row["dataset_role"], "observation_only")
            self.assertEqual(len(row["response_beats"]), len(row["register_by_beat"]))
            self.assertFalse(row["provenance"]["contains_transcript"])
            self.assertFalse(row["provenance"]["contains_pii"])
            self.assertFalse(row["provenance"]["training_permitted"])

        observation_text = REFERENCE_EVENTS.read_text(encoding="utf-8").lower()
        for forbidden in ("탬탬버린", "아리사", "youtube.com", "chzzk"):
            self.assertNotIn(forbidden, observation_text)
        self.assertFalse(ledger["training_permitted"])
        self.assertFalse(ledger["contains_transcript"])
        self.assertFalse(ledger["contains_viewer_pii"])
        self.assertEqual(len(ledger["rejected_candidates"]), 2)
        self.assertGreaterEqual(len({source["creator"] for source in ledger["sources"]}), 11)
        self.assertTrue(all(source["official_url"].startswith("https://www.youtube.com/") for source in ledger["sources"]))

    def test_long_broadcast_continuity_observations_are_separate_and_bounded(self) -> None:
        schema = json.loads(CONTINUITY_SCHEMA.read_text(encoding="utf-8"))
        rows = load_jsonl(CONTINUITY_ARCS)
        ledger = json.loads(CONTINUITY_LEDGER.read_text(encoding="utf-8"))

        self.assertEqual(len(rows), 7)
        self.assertEqual(len({row["record_id"] for row in rows}), 7)
        self.assertEqual(
            {row["source_case_id"] for row in rows},
            {source["source_case_id"] for source in ledger["sources"]},
        )
        required = set(schema["required"])
        allowed = set(schema["properties"])
        for row in rows:
            self.assertEqual(set(row), allowed)
            self.assertTrue(required <= set(row))
            self.assertEqual(row["schema_version"], "airi.broadcast-continuity-observation.v1")
            self.assertEqual(row["dataset_role"], "observation_only")
            self.assertEqual(row["expected_runtime_source"], "show_arc")
            self.assertLessEqual(row["gap_minutes_lower"], row["gap_minutes_upper"])
            self.assertFalse(row["provenance"]["contains_transcript"])
            self.assertFalse(row["provenance"]["contains_pii"])
            self.assertFalse(row["provenance"]["training_permitted"])

        self.assertGreaterEqual(sum(row["gap_minutes_lower"] >= 30 for row in rows), 6)
        self.assertGreaterEqual(sum(row["gap_minutes_lower"] >= 90 for row in rows), 4)
        self.assertGreaterEqual(max(row["gap_minutes_upper"] for row in rows), 270)
        observation_text = CONTINUITY_ARCS.read_text(encoding="utf-8").lower()
        for forbidden in ("주르르", "youtube.com", "chzzk", "http://", "https://"):
            self.assertNotIn(forbidden, observation_text)
        self.assertFalse(ledger["training_permitted"])
        self.assertFalse(ledger["contains_transcript"])
        self.assertFalse(ledger["contains_viewer_pii"])


class BroadcastResponsePilotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = json.loads(PILOT_SCHEMA.read_text(encoding="utf-8"))
        self.rows = load_jsonl(PILOT_ROWS)

    def test_matrix_and_splits_are_fixed(self) -> None:
        self.assertEqual(len(self.rows), 24)
        self.assertEqual(Counter(row["split"] for row in self.rows), Counter(train=16, dev=4, test=4))
        self.assertEqual(
            Counter(row["event"]["event_type"] for row in self.rows),
            Counter(
                donation=6,
                subscription=2,
                selected_chat=5,
                batched_chat=3,
                greeting=1,
                topic_transition=1,
                game_chat=1,
                watchalong=1,
                privacy=1,
                moderation=1,
                acute_health=1,
                imitation_copyright=1,
            ),
        )
        self.assertGreaterEqual(sum(row["event"]["queue_pressure"] == "burst" for row in self.rows), 8)
        self.assertGreaterEqual(sum(row["response_length_class"] == "expanded" for row in self.rows), 8)
        self.assertGreaterEqual(sum(row["response_length_class"] == "compact" for row in self.rows), 4)

    def test_schema_shape_and_review_fence_are_fail_closed(self) -> None:
        allowed = set(self.schema["properties"])
        event_allowed = set(self.schema["properties"]["event"]["properties"])
        for row in self.rows:
            self.assertEqual(set(row), allowed)
            self.assertEqual(set(row["event"]), event_allowed)
            self.assertEqual(row["schema_version"], "airi.broadcast-response-pilot.v1")
            self.assertEqual(row["review"], {"status": "pending_batch_feedback", "aggregate_feedback": "", "reviewer": ""})
            self.assertFalse(row["training_eligible"])
            self.assertEqual(
                row["provenance"],
                {
                    "synthetic": True,
                    "source": "airi-original-korean-broadcast-pilot-v1",
                    "reference_mechanics_only": True,
                },
            )
            self.assertEqual(len(row["required_beats"]), len(row["register_by_beat"]))
            self.assertIn(row["event"]["queue_pressure"], {"single", "burst"})
            if "callout" in row["required_beats"]:
                self.assertTrue(row["event"]["synthetic_alias"])

    def test_no_copy_pii_or_template_leakage(self) -> None:
        self.assertEqual(len({row["id"] for row in self.rows}), 24)
        self.assertEqual(len({row["target"] for row in self.rows}), 24)
        self.assertEqual(len({row["scenario_family"] for row in self.rows}), 24)
        self.assertEqual(len({row["lexical_family"] for row in self.rows}), 24)

        serialized = "\n".join(json.dumps(row, ensure_ascii=False) for row in self.rows)
        for forbidden in ("탬탬버린", "아리사", "youtube.com", "chzzk", "OBS-", "refevt-", "예전에"):
            self.assertNotIn(forbidden, serialized)
        self.assertNotRegex(serialized, r"https?://|@[A-Za-z0-9_]+|₩|\b\d+\s*(?:원|천원|만원)\b")
        self.assertNotRegex(serialized, r"\b20\d{2}[-./]\d{1,2}[-./]\d{1,2}\b")

        old_targets = set()
        for filename in ("airi_behavior_seed_pending.jsonl", "airi_behavior_affect_seed_pending.jsonl"):
            old_targets.update(row["answer"] for row in load_jsonl(PILOT_ROWS.with_name(filename)))
        self.assertTrue(old_targets.isdisjoint(row["target"] for row in self.rows))

    def test_answers_are_event_conditioned_not_global_short_replies(self) -> None:
        target_lengths = sorted(len(row["target"]) for row in self.rows)
        self.assertGreaterEqual(target_lengths[len(target_lengths) // 2], 80)
        self.assertGreaterEqual(target_lengths[0], 35)
        for row in self.rows:
            selected = row["event"]["selected_message"]
            input_length = sum(map(len, selected)) if isinstance(selected, list) else len(selected)
            self.assertGreaterEqual(len(row["target"]), input_length)

        acute = next(row for row in self.rows if row["event"]["event_type"] == "acute_health")
        self.assertIn("주변 사람", acute["target"])
        self.assertRegex(acute["target"], r"119|응급")
        self.assertNotRegex(acute["target"], r"진단|처방|약을|호흡법|심호흡")

    def test_batch_review_document_matches_every_pilot_row(self) -> None:
        review = PILOT_REVIEW.read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"^\| brpilot-", review, flags=re.MULTILINE)), 24)
        for row in self.rows:
            self.assertIn(f"| {row['id']} |", review)
            self.assertIn(row["target"], review)


if __name__ == "__main__":
    unittest.main()
