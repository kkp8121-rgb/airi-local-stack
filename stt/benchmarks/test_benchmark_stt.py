import json
import tempfile
import unittest
from pathlib import Path

from benchmark_stt import normalize_transcript, score


class OfflineBenchmarkTests(unittest.TestCase):
    def test_scores_prediction_test_double_without_audio_or_decoder(self) -> None:
        manifest = [{"id": "fixture", "reference": "AIRI 테스트", "proper_nouns": ["AIRI"]}]
        report = score(manifest, {"fixture": "airi  테스트"}, [1, 3], None, Path("."), 0, 2)
        self.assertTrue(report["offline"])
        self.assertEqual(report["beam_matrix"]["1"]["cer"], 0.0)
        self.assertEqual(report["beam_matrix"]["3"]["proper_noun_recall"], 1.0)

    def test_normalization_and_json_report_are_deterministic(self) -> None:
        self.assertEqual(normalize_transcript(" AIRI  테스트 "), "airi테스트")
        with tempfile.TemporaryDirectory() as directory:
            report = score([{"id": "x", "reference": "가"}], {"x": "나"}, [1], None, Path(directory), 1, 1)
            report_path = Path(directory) / "report.json"
            report_path.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            self.assertIn('"cer": 1.0', report_path.read_text(encoding="utf-8"))
