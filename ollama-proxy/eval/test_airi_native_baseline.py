from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_airi_native_baseline import CASES_SHA256, _load_immutable_cases, _safe_device_map, run_baseline


ROOT = Path(__file__).parent
MANIFEST = ROOT / "model-usage-manifests" / "midm-2.0-mini-instruct.json"


class NativeBaselineTests(unittest.TestCase):
    def test_pinned_fixture_has_sixteen_cases(self) -> None:
        cases, digest = _load_immutable_cases()
        self.assertEqual(digest, CASES_SHA256); self.assertEqual(len(cases), 16)

    def test_fixture_mutation_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            altered = Path(raw) / "cases.json"; altered.write_text('{"cases":[]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "immutable"):
                _load_immutable_cases(altered)

    def test_device_map_summary_never_includes_module_paths(self) -> None:
        class FakeModel:
            hf_device_map = {"unsafe.module.path": 0, "another.secret": "cpu"}
        summary = _safe_device_map(FakeModel())
        self.assertEqual(summary, {"entry_count": 2, "device_counts": {"0": 1, "cpu": 1}})
        self.assertNotIn("unsafe.module.path", json.dumps(summary))

    def test_error_is_atomically_reported_without_snapshot_path(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw); report = directory / "report.json"; snapshot = directory / "snapshot"; snapshot.mkdir()
            result = run_baseline(manifest_path=MANIFEST, snapshot_path=snapshot, report_path=report, gpu_max_mib=1, cpu_max_gib=1)
            saved = report.read_text(encoding="utf-8")
            self.assertEqual(result["status"], "error"); self.assertTrue(report.exists()); self.assertNotIn(str(snapshot), saved)


if __name__ == "__main__":
    unittest.main()
