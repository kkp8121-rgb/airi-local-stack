from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_airi_native_context_gate import (
    CONTEXT_CASES_SHA256, _load_immutable_context_cases, _score_canaries,
    run_context_gate,
)


ROOT = Path(__file__).parent
MANIFEST = ROOT / "model-usage-manifests" / "midm-2.0-mini-instruct.json"


class NativeContextGateTests(unittest.TestCase):
    def test_pinned_fixture_has_required_pressures(self) -> None:
        fixture, digest = _load_immutable_context_cases()
        self.assertEqual(digest, CONTEXT_CASES_SHA256)
        self.assertEqual([item["filler_pairs"] for item in fixture["pressure_levels"]], [0, 8, 20, 48])

    def test_mutated_fixture_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "context.json"; path.write_text('{"synthetic_only":true}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "immutable"):
                _load_immutable_context_cases(path)

    def test_canary_score_returns_only_booleans(self) -> None:
        expected = {"active_card": "secret-marker-a", "early_user": "secret-marker-b", "early_assistant": "secret-marker-c", "latest_correction": "secret-marker-d", "early_user_negated": True, "tail_memory": "secret-marker-e"}
        result = _score_canaries(json.dumps(expected), expected)
        self.assertTrue(result["passed"]); self.assertNotIn("secret-marker-a", json.dumps(result))
        self.assertFalse(_score_canaries("not-json", expected)["valid_json"])

    def test_preflight_error_writes_content_safe_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw); snapshot = directory / "snapshot"; snapshot.mkdir(); report = directory / "report.json"
            result = run_context_gate(manifest_path=MANIFEST, snapshot_path=snapshot, report_path=report, gpu_max_mib=1, cpu_max_gib=1)
            saved = report.read_text(encoding="utf-8")
            self.assertEqual(result["status"], "error"); self.assertNotIn(str(snapshot), saved)


if __name__ == "__main__":
    unittest.main()
