import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build_airi_p1_summary import (CLASSIFICATION_SCHEMA_VERSION, RESULT_SCHEMA_VERSION, SummaryValidationError, build_summary)
from model_usage_manifest import canonical_sha256, validate_manifest


ROOT = Path(__file__).parent
MANIFESTS = sorted((ROOT / "model-usage-manifests").glob("*.json"))


def classifications():
    entries = []
    for path in MANIFESTS:
        candidate = json.loads(path.read_text(encoding="utf-8"))["candidate_id"]
        for profile in ("native", "common"):
            entries.append({"candidate_id": candidate, "profile": profile, "status": "pending", "reasons": ["NOT_RUN"]})
    return {"schema_version": CLASSIFICATION_SCHEMA_VERSION, "profiles": entries}


class BuildP1SummaryTests(unittest.TestCase):
    def test_complete_six_candidate_matrix_is_deterministic(self):
        first = build_summary(MANIFESTS, [], classifications(), {"other_services": "idle"})
        second = build_summary(list(reversed(MANIFESTS)), [], classifications(), {"other_services": "idle"})
        self.assertEqual(first, second)
        self.assertEqual(6, len(first["candidates"]))
        self.assertTrue(all(len(row["profiles"]) == 2 for row in first["candidates"]))

    def test_requires_valid_missing_run_classification(self):
        bad = classifications()
        bad["profiles"].pop()
        with self.assertRaisesRegex(SummaryValidationError, "missing required classification"):
            build_summary(MANIFESTS, [], bad, {})

    def test_rejects_human_scores_and_raw_output_keys(self):
        manifest = json.loads(MANIFESTS[0].read_text(encoding="utf-8"))
        checked = validate_manifest(manifest)
        with tempfile.TemporaryDirectory() as directory:
            result_path = Path(directory) / "result.json"
            result_path.write_text(json.dumps({"schema_version": RESULT_SCHEMA_VERSION, "candidate_id": manifest["candidate_id"], "profile": "native", "manifest_file_sha256": __import__("hashlib").sha256(MANIFESTS[0].read_bytes()).hexdigest(), "manifest_canonical_sha256": canonical_sha256(checked), "measured": {"human_score": 4}, "reasons": []}), encoding="utf-8")
            data = classifications()
            data["profiles"] = [item for item in data["profiles"] if not (item["candidate_id"] == manifest["candidate_id"] and item["profile"] == "native")]
            with self.assertRaisesRegex(SummaryValidationError, "forbidden"):
                build_summary(MANIFESTS, [result_path], data, {})


if __name__ == "__main__":
    unittest.main()
