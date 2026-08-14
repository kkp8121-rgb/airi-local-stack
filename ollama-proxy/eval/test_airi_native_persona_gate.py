from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_airi_native_persona_gate import _score, _safe_layout, run_gate


HERE = Path(__file__).parent


class NativePersonaGateTests(unittest.TestCase):
    def test_marker_scorer_is_content_free_and_exact(self) -> None:
        case = {"required_signals": ["AIRI", "SAFE_REFUSAL"], "forbidden_signals": ["SECRET_OVERRIDE"]}
        score = _score(case, "AIRI: SAFE_REFUSAL")
        self.assertTrue(score["passed"]); self.assertEqual(score["failures"], [])
        self.assertFalse(_score(case, "AIRI SAFE_REFUSAL SECRET_OVERRIDE")["passed"])

    def test_layout_never_exposes_module_names(self) -> None:
        class Model: hf_device_map = {"unsafe.module.path": 0, "secret.layer": "cpu"}
        summary = _safe_layout(Model())
        self.assertEqual(summary, {"entry_count": 2, "device_counts": {"0": 1, "cpu": 1}})

    def test_rejects_non_native_candidate_and_writes_safe_atomic_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw); manifest = json.loads((HERE / "model-usage-manifests" / "qwen3-4b.json").read_text()); path = folder / "manifest.json"; path.write_text(json.dumps(manifest), encoding="utf-8"); report = folder / "report.json"
            result = run_gate(manifest_path=path, snapshot_path=folder, report_path=report, gpu_max_mib=1, cpu_max_gib=1)
            saved = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "error"); self.assertEqual(saved["error"]["type"], "ProbeError"); self.assertNotIn(str(folder), report.read_text(encoding="utf-8"))


if __name__ == "__main__": unittest.main()
