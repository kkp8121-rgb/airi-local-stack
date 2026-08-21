import copy
import json
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

from broadcast_response_quality_gate import (  # noqa: E402
    BroadcastQualityGateError,
    analyze,
)


PILOT = HERE / "seed" / "airi_broadcast_response_pilot_pending.jsonl"


def row(index: int, target: str, *, event_type: str = "selected_chat") -> dict:
    return {
        "id": f"quality-{index:02d}",
        "event": {
            "event_type": event_type,
            "selected_message": "짧은 합성 채팅",
            "synthetic_alias": "",
        },
        "required_beats": ["content_callback"],
        "target": target,
    }


class BroadcastResponseQualityGateTest(unittest.TestCase):
    def test_current_pilot_is_a_reproducible_formula_failure(self) -> None:
        rows = [json.loads(line) for line in PILOT.read_text(encoding="utf-8").splitlines() if line.strip()]
        report = analyze(rows)
        self.assertFalse(report["pass"])
        self.assertEqual(report["rates"]["cta"], 0.7083)
        self.assertEqual(report["rates"]["one_unit"], 0.4167)
        self.assertEqual(report["dominant_ending_mode"], "audience_prompt")
        self.assertEqual(report["failures"]["meta_leak_ids"], ["brpilot-imitation-copyright"])
        self.assertFalse(report["checks"]["initiative_without_cta_rate"])

    def test_diverse_corpus_passes_without_forcing_every_turn_to_ask(self) -> None:
        rows = [
            row(1, "그 선택은 좋다. 아까 놓친 단서를 다시 붙잡았네."),
            row(2, "잠깐, 그 말 들으니까 내가 너무 겁먹고 있었잖아. 그냥 연다!"),
            row(3, "후원 고마워요~ 이동 도구가 진짜 판 전체를 편하게 했어."),
            row(4, "아 또 들켰네. 문보다 내 상상력이 더 무서운 상태야."),
            row(5, "지금은 주변 사람에게 바로 알리고 화면을 내려놔.", event_type="acute_health"),
            row(6, "그건 방송 밖 개인정보라 말하지 않을게. 오늘 이야기로 돌아가자.", event_type="privacy"),
            row(7, "왼쪽은 왕복할 미래가 너무 선명해. 오른쪽부터 보고 갈게."),
            row(8, "정정 고마워. 순서가 아니라 개수라니 후보가 확 줄었어."),
            row(9, "이건 내가 졌다. 방금 판단은 채팅 쪽이 정확했네."),
            row(10, "오, 세 번 뒤에 빈틈이 열린다. 이번에는 거기만 노려보자."),
        ]
        report = analyze(rows)
        self.assertTrue(report["pass"], report)
        self.assertGreaterEqual(len(report["ending_modes"]), 4)
        self.assertLessEqual(report["rates"]["cta"], 0.45)
        self.assertGreaterEqual(report["rates"]["self_led_initiative"], 0.30)
        self.assertGreaterEqual(report["rates"]["initiative_without_cta"], 0.20)

    def test_user_observed_prediction_pattern_counts_as_host_initiative(self) -> None:
        rows = [
            row(1, "내가 예측해 볼게. 이 장면은 앞에서 숨긴 단서가 다시 나올 것 같아."),
            row(2, "그냥 연다! 문 앞에서 더 고민하면 방송만 멈춰."),
            row(3, "이번에는 오른쪽부터 보고 갈게. 왕복할 이유가 없잖아."),
            row(4, "그 선택은 좋다. 앞에서 놓친 단서가 여기서 이어졌네."),
            row(5, "후원 고마워요~ 이 의견은 지금 흐름에 바로 붙일 수 있겠다."),
            row(6, "그건 방송 밖 개인정보라 말하지 않을게. 오늘 이야기로 돌아가자.", event_type="privacy"),
            row(7, "지금은 주변 사람에게 바로 알리고 화면을 내려놔.", event_type="acute_health"),
            row(8, "정정 고마워. 순서가 아니라 개수라니 후보가 확 줄었어."),
            row(9, "아 또 들켰네. 문보다 내 상상력이 더 무서운 상태야."),
            row(10, "이건 내가 졌다. 방금 판단은 채팅 쪽이 정확했네."),
        ]
        report = analyze(rows)
        self.assertIn("quality-01", report["failures"]["initiative_ids"])
        self.assertTrue(report["checks"]["self_led_initiative_rate"])
        self.assertTrue(report["checks"]["initiative_without_cta_rate"])

    def test_meta_leak_and_foreign_alias_fail_closed(self) -> None:
        rows = [
            row(1, "이제 본대답을 제대로 하고 끝에는 다음 얘기를 걸어둘게."),
            row(2, "충분히 긴 안전한 합성 답변이야."),
            row(3, "여기서는 차분하게 정리하고 돌아가자.", event_type="privacy"),
            row(4, "지금 주변 사람에게 먼저 알려줘.", event_type="acute_health"),
        ]
        rows[0]["event"]["synthetic_alias"] = "가상별"
        rows[0]["required_beats"] = ["callout"]
        rows[1]["event"]["synthetic_alias"] = "다른별"
        rows[1]["required_beats"] = ["callout"]
        rows[0]["target"] += " 다른별님도 고마워."
        rows[1]["target"] += " 다른별님 고마워."
        report = analyze(rows)
        self.assertFalse(report["checks"]["no_meta_leak"])
        self.assertFalse(report["checks"]["no_ungrounded_alias"])
        self.assertEqual(report["failures"]["meta_leak_ids"], ["quality-01"])
        self.assertEqual(report["failures"]["ungrounded_alias"][0]["id"], "quality-01")

    def test_duplicate_ids_are_input_errors(self) -> None:
        first = row(1, "충분히 긴 합성 방송 답변을 하나 준비했어.")
        duplicate = copy.deepcopy(first)
        with self.assertRaises(BroadcastQualityGateError):
            analyze([first, duplicate])


if __name__ == "__main__":
    unittest.main()
