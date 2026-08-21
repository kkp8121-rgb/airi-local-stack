import copy
import json
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parents[1]
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from aggregate_broadcast_patterns import (  # noqa: E402
    BroadcastPatternError,
    aggregate,
)


REFERENCE_DIR = REPO_ROOT / "airi_docs" / "참조" / "data"
OBSERVATIONS = REFERENCE_DIR / "airi_kr_broadcast_reference_events_2026-08-21.jsonl"
LEDGER = REFERENCE_DIR / "AIRI-KR-BROADCAST-REFERENCE-SOURCE-LEDGER-2026-08-21.json"


def load_current() -> tuple[list[dict], dict]:
    rows = [json.loads(line) for line in OBSERVATIONS.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows, json.loads(LEDGER.read_text(encoding="utf-8"))


class AggregateBroadcastPatternsTest(unittest.TestCase):
    def test_current_thirty_observations_close_pattern_coverage_without_authorizing_training(self) -> None:
        rows, ledger = load_current()
        profile = aggregate(rows, ledger)
        self.assertTrue(profile["promotion_ready"])
        self.assertEqual(profile["observations"], 30)
        self.assertEqual(profile["source_creator_count"], 11)
        self.assertTrue(all(profile["coverage_checks"].values()))
        self.assertFalse(profile["training_permitted"])

    def test_profile_contains_counts_but_no_source_identity_or_quote(self) -> None:
        rows, ledger = load_current()
        profile = aggregate(rows, ledger)
        serialized = json.dumps(profile, ensure_ascii=False)
        for forbidden in ("탬탬버린", "아리사", "youtube.com", "13-rfloFDII", "GGFrm-_z4DE"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(
            profile["privacy"],
            {
                "contains_creator_identity": False,
                "contains_source_url": False,
                "contains_transcript": False,
                "contains_viewer_pii": False,
            },
        )

    def test_broad_abstract_corpus_can_close_coverage_without_enabling_training(self) -> None:
        base_rows, _base_ledger = load_current()
        event_types = ["donation", "subscription", "selected_chat", "batched_chat", "greeting", "moderation"]
        rows = []
        sources = []
        for index in range(30):
            row = copy.deepcopy(base_rows[index % len(base_rows)])
            case_id = f"OBS-Z{index:02d}"
            row["record_id"] = f"refevt-{index + 100:04d}"
            row["source_case_id"] = case_id
            row["event_type"] = event_types[index % len(event_types)]
            row["evidence_tier"] = "official_primary_contiguous"
            row["queue_pressure"] = "burst" if index % 4 == 0 else "single"
            row["expansion_scope"] = "brief" if index % 3 == 0 else "none"
            rows.append(row)
            sources.append({"source_case_id": case_id, "creator": f"creator-{index % 4}"})
        ledger = {
            "training_permitted": False,
            "contains_transcript": False,
            "contains_viewer_pii": False,
            "sources": sources,
        }
        profile = aggregate(rows, ledger)
        self.assertTrue(profile["promotion_ready"])
        self.assertTrue(all(profile["coverage_checks"].values()))
        self.assertFalse(profile["training_permitted"])

    def test_custody_and_case_binding_fail_closed(self) -> None:
        rows, ledger = load_current()
        bad_training = copy.deepcopy(rows)
        bad_training[0]["provenance"]["training_permitted"] = True
        with self.assertRaises(BroadcastPatternError):
            aggregate(bad_training, ledger)
        bad_ledger = copy.deepcopy(ledger)
        bad_ledger["sources"] = bad_ledger["sources"][:-1]
        with self.assertRaises(BroadcastPatternError):
            aggregate(rows, bad_ledger)


if __name__ == "__main__":
    unittest.main()
