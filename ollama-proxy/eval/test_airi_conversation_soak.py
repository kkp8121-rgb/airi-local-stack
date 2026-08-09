import argparse
import json
from pathlib import Path
import tempfile
import unittest

from run_airi_conversation_soak import _score, _write_report


class ConversationSoakScoreTests(unittest.TestCase):
    def test_speaker_labels_fail_meta_gate(self) -> None:
        case = {"korean": True}
        for output in (
            "사용자: 오늘 날씨 어때?",
            "너: 오늘은 흥미로운 주제네!",
            '“AIRI: 반가워!”',
        ):
            with self.subTest(output=output):
                self.assertFalse(_score(case, output)["checks"]["no_meta"])

    def test_ordinary_second_person_is_not_a_speaker_label(self) -> None:
        scored = _score({"korean": True}, "너라면 이쪽이 더 재밌을 것 같아.")
        self.assertTrue(scored["checks"]["no_meta"])


    def test_middle_polite_register_and_incomplete_clause_fail_structurally(self) -> None:
        polite = _score({"korean": True}, "그건 어렵습니다, 그래도 해볼 수 있어.")
        incomplete = _score({"korean": True}, "먼저 쉬고 몸이 계속 아프다면.")
        self.assertFalse(polite["checks"]["banmal_register"])
        self.assertFalse(incomplete["checks"]["complete_sentence"])

    def test_explanation_requires_a_claim_not_only_a_reaction(self) -> None:
        case = {"korean": True, "requires_explanation": True}
        self.assertFalse(_score(case, "신기하지.")["checks"]["explanation_has_claim"])
        self.assertTrue(_score(case, "태양계는 태양 주위를 도는 천체들의 관계야.")["checks"]["explanation_has_claim"])

    def test_checkpoint_report_preserves_transport_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "partial.json"
            args = argparse.Namespace(
                endpoint="http://127.0.0.1:11435/v1/chat/completions",
                model="local-model",
                temperature=0.2,
                request_timeout_seconds=20.0,
            )
            _write_report(
                path,
                args=args,
                results=[{"passed": False, "error_type": "ReadTimeout"}],
                health_before={},
                health_after=None,
                complete=False,
            )
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(report["complete"])
            self.assertEqual(report["transport_errors"], 1)
            self.assertEqual(report["quality_gate"], "FAIL")


if __name__ == "__main__":
    unittest.main()
