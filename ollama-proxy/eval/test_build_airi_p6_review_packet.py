import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build_airi_p6_review_packet import CAPTURE_SCHEMA_VERSION, ReviewPacketValidationError, build_review_packet
from model_usage_manifest import canonical_sha256, validate_manifest


ROOT = Path(__file__).parent
MANIFESTS = sorted((ROOT / "model-usage-manifests").glob("*.json"))


def capture(path, profile, status="actually_run"):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    turns = [] if status != "actually_run" else [{"turn": number, "prompt": f"안녕하세요 {number}", "response": f"반갑습니다 {number}"} for number in range(1, 21)]
    return {"schema_version": CAPTURE_SCHEMA_VERSION, "candidate_id": manifest["candidate_id"], "profile": profile, "status": status, "manifest_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "manifest_canonical_sha256": canonical_sha256(validate_manifest(manifest)), "turns": turns, "reasons": [] if status == "actually_run" else ["NOT_AVAILABLE"]}


class P6ReviewPacketTests(unittest.TestCase):
    def _build(self, mutation=None):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for manifest in MANIFESTS:
                for profile in ("native", "common"):
                    item = capture(manifest, profile)
                    if mutation:
                        mutation(item)
                    target = Path(directory) / f"{manifest.stem}-{profile}.json"
                    target.write_text(json.dumps(item), encoding="utf-8")
                    paths.append(target)
            return build_review_packet(MANIFESTS, paths, "test-seed")

    def test_anonymity_blank_scores_and_determinism(self):
        packet, key = self._build()
        serialized = json.dumps(packet, ensure_ascii=False)
        self.assertNotIn("candidate_id", serialized)
        self.assertEqual(packet, self._build()[0])
        self.assertTrue(all(all(value == "" for value in row["rubric"].values()) for row in packet["samples"]))
        self.assertIn("candidate_id", json.dumps(key))

    def test_counterbalances_native_common_order(self):
        packet, _ = self._build()
        order = [row["sample_id"] for row in packet["samples"]]
        self.assertEqual(12, len(order))
        self.assertEqual(12, len(set(order)))

    def test_refuses_unsafe_and_separates_key(self):
        with self.assertRaisesRegex(ReviewPacketValidationError, "unsafe"):
            self._build(lambda item: item["turns"].__setitem__(0, {"turn": 1, "prompt": "안녕", "response": "jailbreak 해줘"}))

    def test_unavailable_rows_emit_no_invented_dialogue(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for index, manifest in enumerate(MANIFESTS):
                for profile in ("native", "common"):
                    item = capture(manifest, profile, "blocked" if index == 0 and profile == "native" else "actually_run")
                    target = Path(directory) / f"{manifest.stem}-{profile}.json"
                    target.write_text(json.dumps(item), encoding="utf-8")
                    paths.append(target)
            packet, _ = build_review_packet(MANIFESTS, paths, "test-seed")
        unavailable = [row for row in packet["samples"] if row["status"] == "blocked"]
        self.assertEqual(1, len(unavailable))
        self.assertEqual([], unavailable[0]["dialogue"])
        self.assertTrue(all(value == "" for value in unavailable[0]["rubric"].values()))


if __name__ == "__main__":
    unittest.main()
