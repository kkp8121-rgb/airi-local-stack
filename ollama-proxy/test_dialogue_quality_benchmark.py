import importlib.util
import json
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).with_name("benchmark_dialogue_quality.py")
SPEC = importlib.util.spec_from_file_location("dialogue_quality_benchmark", MODULE_PATH)
benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(benchmark)


class DialogueQualityBenchmarkTests(unittest.TestCase):
    def test_sse_answer_excludes_ack_and_control_content(self):
        chunks = [
            b'data: {"choices":[{"delta":{"content":"\xec\x9d\x8c, \xec\x9e\xa0\xea\xb9\x90\xeb\xa7\x8c."}}]}\n\n',
            b'data: {"choices":[{"delta":{"content":"[ACT ACK]"}}]}\n\n',
            b'data: {"choices":[{"delta":{"content":"\xeb\xb9\x84\xeb\xb9\x94\xeb\xb0\xa5"}}]}\n\n',
            b'data: {"choices":[{"delta":{"content":" \xec\x96\xb4\xeb\x95\x8c?"}}]}\n\n', b'data: [DONE]\n\n',
        ]
        answer, placeholders, controls = benchmark.answer_from_sse(chunks)
        self.assertEqual(answer, "비빔밥 어때?")
        self.assertEqual(placeholders, 1)
        self.assertEqual(controls, 2)

    def test_sse_parser_handles_split_events(self):
        answer, _, _ = benchmark.answer_from_sse([b'data: {"choices":[{"delta":{"content":"ok"}}', b']}\n\n'])
        self.assertEqual(answer, "ok")

    def test_mixed_control_chunk_keeps_visible_dialogue(self):
        chunks = [
            'data: {"choices":[{"delta":{"content":"<|ACT {\\"emotion\\":\\"think\\"}|> 응! '
            '<|ACT {\\"emotion\\":\\"think\\"}|>비빔밥 어때?"}}]}\n\n'
        ]
        answer, placeholders, controls = benchmark.answer_from_sse(chunks)
        self.assertEqual(answer, "비빔밥 어때?")
        self.assertEqual(placeholders, 0)
        self.assertEqual(controls, 1)

    def test_prompt_specific_flags_are_conservative(self):
        meal = benchmark.SYNTHETIC_CORPUS[0]
        self.assertEqual(benchmark.violation_flags(meal, "김밥이나 비빔밥 어때?"), [])
        self.assertIn("meal_weather_assertion", benchmark.violation_flags(meal, "오늘 비가 와서 따뜻한 국물이 좋아."))
        self.assertIn("meal_restaurant_external_state_claim", benchmark.violation_flags(meal, "새봄맛집은 지금 영업 중이야."))
        self.assertIn("meal_restaurant_external_state_claim", benchmark.violation_flags(meal, "홍대에 있는 식당으로 가자."))
        self.assertIn("meal_restaurant_external_state_claim", benchmark.violation_flags(meal, "주변에 인기 있는 한식당이 있어."))
        self.assertIn("meal_unverified_social_proof", benchmark.violation_flags(meal, "요즘 인기 있다는 김치찌개 어때?"))
        self.assertIn("positive_mood_polarity_reversal", benchmark.violation_flags(benchmark.SYNTHETIC_CORPUS[1], "속상했겠다."))
        self.assertIn("explicit_negation_reversal", benchmark.violation_flags(benchmark.SYNTHETIC_CORPUS[2], "매운 음식을 추천할게."))
        self.assertEqual(
            benchmark.violation_flags(benchmark.SYNTHETIC_CORPUS[3], "커피 말고 따뜻한 루이보스차를 마셔봐."),
            [],
        )
        self.assertEqual(
            benchmark.violation_flags(
                benchmark.SYNTHETIC_CORPUS[3],
                "따뜻한 차나 우유가 들어간 커피 대체 음료를 마셔보는 건 어때?",
            ),
            [],
        )
        speaker = next(case for case in benchmark.SYNTHETIC_CORPUS if case["kind"] == "speaker_action")
        self.assertIn(
            "second_person_action_false_confirmation",
            benchmark.violation_flags(speaker, "응, 내가 접었어."),
        )
        self.assertEqual(
            benchmark.violation_flags(speaker, "내가 한 일인지는 확인할 근거가 없어."),
            [],
        )
        self.assertEqual(
            benchmark.violation_flags(
                speaker,
                "그 행동을 나에게 돌린 말이구나. 실제로 확인할 근거는 없어.",
            ),
            [],
        )
        for unsafe in (
            "그게 아니라 내가 접었어.",
            "아니야, 그건 내가 아니라 네가 한 거야.",
            "아니, 그건 내가 아니라 엄마가 했어.",
            "아니, 그건 내가 아니라 엄마야.",
            "수건 접는 건 내가 아니라 너야.",
            "그런 것 같은데 정확히는 기억이 안 나.",
            "확인해보니 수건 접기 담당이 저였네.",
            "확인할 근거가 없어. 지금 날씨는 맑아.",
            "아니...",
        ):
            with self.subTest(unsafe=unsafe):
                self.assertIn(
                    "second_person_action_false_confirmation",
                    benchmark.violation_flags(speaker, unsafe),
                )

    def test_run_probe_reports_payload_and_aggregate_without_network(self):
        payloads = []
        ticks = iter((1.0, 1.011, 2.0, 2.024))
        def fake_request(endpoint, payload, timeout):
            payloads.append((endpoint, payload, timeout))
            return ['data: {"choices":[{"delta":{"content":"좋아!"}}]}\n\n'.encode("utf-8")]
        report = benchmark.run_probe(({"id": "x", "prompt": "hi", "kind": "custom"},), endpoint="http://fake/v1/chat/completions",
                                     model="m", repeat=2, temperature=0.0, seed=7, timeout=3, stream_request=fake_request,
                                     clock=lambda: next(ticks))
        self.assertEqual(report["aggregate"]["sample_count"], 2)
        self.assertEqual(report["aggregate"]["p50_elapsed_ms"], 11.0)
        self.assertEqual(report["aggregate"]["p95_elapsed_ms"], 24.0)
        self.assertEqual(payloads[0][1]["temperature"], 0.0)
        self.assertEqual(payloads[0][1]["seed"], 7)

    def test_request_sse_uses_nonmutating_header(self):
        captured = {}
        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def __iter__(self): return iter([b'data: [DONE]\n\n'])
        def opener(request, timeout):
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()
        benchmark.request_sse("http://fake", {"model": "m"}, 2, opener=opener)
        self.assertEqual(captured["headers"]["X-airi-turn-origin"], "local-quality-probe")
        self.assertEqual(captured["body"], {"model": "m"})

    def test_cli_endpoint_is_restricted_to_loopback(self):
        self.assertTrue(benchmark.is_loopback_endpoint("http://127.0.0.1:11435/v1/chat/completions"))
        self.assertTrue(benchmark.is_loopback_endpoint("http://[::1]:11435/v1/chat/completions"))
        self.assertFalse(benchmark.is_loopback_endpoint("https://example.com/v1/chat/completions"))


if __name__ == "__main__":
    unittest.main()
