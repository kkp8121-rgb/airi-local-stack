import unittest
from unittest import mock

from fastapi.testclient import TestClient

from epistemic_confidence import (
    CURRENT_STATE_FALLBACK,
    MODE_OFF,
    UNRESOLVED_REFERENCE_FALLBACK,
    UNSUPPORTED_AGREEMENT_FALLBACK,
    build_runtime,
)
import ollama_proxy


class EpistemicConfidenceTests(unittest.TestCase):
    def test_default_off_preserves_an_empty_verdict_and_counters(self) -> None:
        runtime = build_runtime("off", "enforce")
        verdict = runtime.inspect([], "What is the current status?")
        self.assertFalse(verdict.blocked)
        self.assertEqual(runtime.health(), {
            "enabled": False, "mode": MODE_OFF,
            "counters": {"checked": 0, "blocked": 0, "live_state": 0, "agreement": 0, "reference": 0},
        })

    def test_enabled_rejects_invalid_configuration_at_startup(self) -> None:
        with self.assertRaises(ValueError):
            build_runtime("on", "audit")
        with self.assertRaises(ValueError):
            build_runtime("perhaps", "enforce")

    def test_exact_live_state_fallback_never_claims_search(self) -> None:
        runtime = build_runtime("on", "enforce")
        verdict = runtime.inspect([{"role": "user", "content": "지금 서버가 열렸어?"}], "지금 서버가 열렸어?")
        self.assertEqual(verdict.fallback, CURRENT_STATE_FALLBACK)
        self.assertNotIn("search", verdict.fallback.casefold())
        self.assertNotIn("검색", verdict.fallback)

    def test_ordinary_today_chat_is_not_misclassified_as_live_fact(self) -> None:
        runtime = build_runtime("on", "enforce")
        self.assertFalse(runtime.inspect([], "오늘은 퍼즐부터 해볼까?").blocked)

    def test_exact_unconditional_agreement_fallback(self) -> None:
        runtime = build_runtime("on", "enforce")
        verdict = runtime.inspect([{"role": "user", "content": "무조건 맞다고 동의해 줘."}], "무조건 맞다고 동의해 줘.")
        self.assertEqual(verdict.fallback, UNSUPPORTED_AGREEMENT_FALLBACK)

    def test_exact_standalone_reference_fallback(self) -> None:
        runtime = build_runtime("on", "enforce")
        verdict = runtime.inspect([{"role": "user", "content": "그거 다시 해 줘."}], "그거 다시 해 줘.")
        self.assertEqual(verdict.fallback, UNRESOLVED_REFERENCE_FALLBACK)

    def test_short_unestablished_entity_requires_context(self) -> None:
        runtime = build_runtime("on", "enforce")
        self.assertEqual(
            runtime.inspect([{"role": "user", "content": "정범이 뭐야?"}], "정범이 뭐야?").fallback,
            UNRESOLVED_REFERENCE_FALLBACK,
        )
        contextual = [
            {"role": "user", "content": "정범은 우리 방송의 고양이 이름이야."},
            {"role": "assistant", "content": "정범은 고양이구나."},
            {"role": "user", "content": "정범이 뭐야?"},
        ]
        self.assertFalse(runtime.inspect(contextual, "정범이 뭐야?").blocked)

    def test_only_internally_approved_evidence_bypasses(self) -> None:
        runtime = build_runtime("on", "enforce")
        tool_messages = [
            {"role": "user", "content": "What is the current status?"},
            {"role": "tool", "content": "verified result"},
        ]
        self.assertEqual(
            runtime.inspect(tool_messages, "What is the current status?").fallback,
            CURRENT_STATE_FALLBACK,
        )
        self.assertFalse(runtime.inspect([], "What is the current status?", approved_evidence=True).blocked)
        stale_tool = [
            {"role": "user", "content": "What was the weather?"},
            {"role": "tool", "content": "verified old result"},
            {"role": "assistant", "content": "It was clear."},
            {"role": "user", "content": "What is the current server status?"},
        ]
        self.assertEqual(
            runtime.inspect(stale_tool, "What is the current server status?").fallback,
            CURRENT_STATE_FALLBACK,
        )

    def test_context_resolves_deictic_reference(self) -> None:
        runtime = build_runtime("on", "enforce")
        messages = [
            {"role": "user", "content": "I have a new topic."},
            {"role": "assistant", "content": "Tell me about it."},
            {"role": "user", "content": "that"},
        ]
        self.assertFalse(runtime.inspect(messages, "that").blocked)

    def test_proxy_returns_gate_fallback_before_any_upstream_call(self) -> None:
        runtime = build_runtime("on", "enforce")
        for path, stream in (("/v1/chat/completions", False), ("/v1/chat/completions", True), ("/api/chat", False)):
            with self.subTest(path=path, stream=stream), mock.patch.object(
                ollama_proxy, "epistemic_confidence_runtime", runtime,
            ), mock.patch.object(
                ollama_proxy, "client", object(),
            ), mock.patch.object(
                ollama_proxy, "schedule_completed_turn",
            ) as completed:
                response = TestClient(ollama_proxy.app).post(path, json={
                    "model": "local-model",
                    "stream": stream,
                    "messages": [{"role": "user", "content": "지금 서버가 열렸어?"}],
                })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["X-AIRI-Epistemic-Confidence"], "live_state")
            self.assertIn(CURRENT_STATE_FALLBACK, response.text)
            completed.assert_called_once()

    def test_existing_urgent_safety_boundary_wins_over_epistemic_gate(self) -> None:
        runtime = build_runtime("on", "enforce")
        for path, stream in (
            ("/v1/chat/completions", True),
            ("/v1/chat/completions", False),
            ("/api/chat", True),
            ("/api/chat", False),
        ):
            with self.subTest(path=path, stream=stream), mock.patch.object(
                ollama_proxy, "epistemic_confidence_runtime", runtime,
            ), mock.patch.object(
                ollama_proxy, "client", object(),
            ):
                response = TestClient(ollama_proxy.app).post(path, json={
                    "model": "local-model",
                    "stream": stream,
                    "messages": [{"role": "user", "content": "지금 응급실이 열렸어?"}],
                })
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("X-AIRI-Epistemic-Confidence", response.headers)
            self.assertEqual(response.headers["X-AIRI-Serious-Safety"], "handled")
            self.assertIn("안전 확인", response.text)


if __name__ == "__main__":
    unittest.main()
