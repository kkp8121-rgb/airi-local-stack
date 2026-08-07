import asyncio
import json
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import ollama_proxy


class _StubClient:
    """Minimal httpx.AsyncClient stand-in that always fails on send."""

    def __init__(self, error: BaseException) -> None:
        self._error = error

    def build_request(self, *args: object, **kwargs: object) -> object:
        return object()

    async def send(self, *args: object, **kwargs: object) -> object:
        raise self._error


def post_stream(text: str) -> object:
    return TestClient(ollama_proxy.app).post(
        "/v1/chat/completions",
        json={
            "model": "exaone-airi:2.4b",
            "stream": True,
            "messages": [{"role": "user", "content": text}],
        },
    )


class SearchRoutingTests(unittest.TestCase):
    def test_detects_korean_search_intents(self) -> None:
        for text in (
            "음유잉여 검색해줘",
            "음유잉여 웹서칭해봐",
            "음유잉여가 누군지 찾아봐",
            "이거 알아봐 줘",
            "음유잉여 검색 좀 해줘",
        ):
            with self.subTest(text=text):
                self.assertTrue(ollama_proxy.is_search_request(text))

        self.assertFalse(ollama_proxy.is_search_request("음유잉여가 누구야?"))

    def test_ignores_search_lookalike_words(self) -> None:
        # Substring matching used to route these to the cloud, leaking 500
        # characters of the raw utterance to an external process.
        for text in (
            "리서치 자료 정리해줘",
            "research 논문 요약해줘",
            "서치라이트가 뭐야?",
            "검색엔진 이야기해줘",
        ):
            with self.subTest(text=text):
                self.assertFalse(ollama_proxy.is_search_request(text))

    def test_prefers_quoted_proper_noun_as_query(self) -> None:
        query = ollama_proxy.extract_search_query("고유명사 '음유잉여'를 웹에서 검색해줘")

        self.assertEqual(query, "음유잉여")

    def test_extracts_unquoted_query_without_command_residue(self) -> None:
        query = ollama_proxy.extract_search_query("음유잉여를 웹에서 검색해줘")

        self.assertEqual(query, "음유잉여")

    def test_keeps_words_that_merely_contain_filler_syllables(self) -> None:
        # Bare 해/좀 in the filler alternation used to shave the first syllable
        # off the actual query.
        cases = {
            "해리포터 검색해줘": "해리포터",
            "좀비 아포칼립스 검색해줘": "좀비 아포칼립스",
            "해외 뉴스 검색해줘": "해외 뉴스",
            "이해충돌 검색해줘": "이해충돌",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(ollama_proxy.extract_search_query(text), expected)

    def test_still_drops_whole_filler_eojeol(self) -> None:
        self.assertEqual(ollama_proxy.extract_search_query("음유잉여 좀 검색해줘"), "음유잉여")
        self.assertEqual(ollama_proxy.extract_search_query("음유잉여가 뭔지 찾아봐"), "음유잉여")

    def test_bare_search_command_yields_no_query(self) -> None:
        for text in ("검색해줘", "웹에서 검색해 줘"):
            with self.subTest(text=text):
                self.assertEqual(ollama_proxy.extract_search_query(text), "")

    def test_timestamp_prefix_is_not_treated_as_a_search_query(self) -> None:
        text = "[2026-08-07 09:10] 웹에서 검색해줘"

        self.assertEqual(ollama_proxy.extract_search_query(text), "")

    def test_recovers_clipped_subject_from_previous_search_turn(self) -> None:
        query, recovered = ollama_proxy.resolve_search_query(
            "[2026-08-07 09:11] 웹에서 검색해줘",
            ["[2026-08-07 09:10] 음유잉여를 웹에서 검색해줘"],
        )

        self.assertEqual(query, "음유잉여")
        self.assertTrue(recovered)

    def test_first_bare_search_has_no_recoverable_subject(self) -> None:
        query, recovered = ollama_proxy.resolve_search_query(
            "[2026-08-07 09:10] 웹에서 검색해줘", []
        )

        self.assertEqual(query, "")
        self.assertFalse(recovered)

    def test_bare_search_command_stays_on_the_local_branch(self) -> None:
        attempted: list[str] = []

        async def unexpected_search(user_text: str, query: str) -> tuple[str, float]:
            attempted.append(query)
            return "", 0.0

        with mock.patch.object(ollama_proxy, "run_codex_search", unexpected_search), mock.patch.object(
            ollama_proxy, "client", _StubClient(RuntimeError("upstream down"))
        ):
            response = post_stream("검색해줘")

        self.assertEqual(attempted, [])
        self.assertIn(ollama_proxy.LOCAL_ERROR_DIALOGUE, response.text)


class DialogueNormalizationTests(unittest.TestCase):
    def test_normalizes_cloud_markdown_for_speech(self) -> None:
        normalized = ollama_proxy.normalize_cloud_result(
            "[이터널 리턴 공식 사이트](https://example.com)에서 확인했어. **선수 닉네임**이야."
        )

        self.assertNotIn("https://", normalized)
        self.assertNotIn("**", normalized)
        self.assertIn("이터널 리턴 공식 사이트", normalized)

    def test_cloud_result_speaks_in_the_local_persona(self) -> None:
        normalized = ollama_proxy.normalize_cloud_result("검색 결과를 정리했어요. 감사합니다.")

        self.assertNotIn("어요", normalized)
        self.assertNotIn("감사합니다", normalized)
        self.assertIn("고마워", normalized)

    def test_cloud_result_keeps_a_three_sentence_budget(self) -> None:
        normalized = ollama_proxy.normalize_cloud_result(
            "하나야. 둘이야. 셋이야. 넷이야. 다섯이야."
        )

        self.assertNotIn("넷이야", normalized)
        self.assertIn("셋이야", normalized)

    def test_leading_reaction_keeps_words_that_start_like_one(self) -> None:
        # The reaction word must be closed by a separator, otherwise these lose
        # their first syllable.
        for text in (
            "그래도 괜찮아.",
            "응원할게!",
            "그래프가 이상해.",
            "알겠어요, 지금 할게.",
        ):
            with self.subTest(text=text):
                self.assertEqual(ollama_proxy.strip_leading_reaction(text), text)

    def test_leading_reaction_is_still_stripped(self) -> None:
        cases = {
            "응! 알겠어.": "알겠어.",
            "그래, 좋아": "좋아",
            "아하 그런 거였구나": "그런 거였구나",
            "응응! 알았어.": "알았어.",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(ollama_proxy.strip_leading_reaction(text), expected)

    def test_null_message_content_never_becomes_the_word_none(self) -> None:
        self.assertEqual(ollama_proxy.message_content({"content": None}), "")
        self.assertEqual(ollama_proxy.message_content({"content": ["a"]}), "")
        self.assertEqual(ollama_proxy.message_content(None), "")
        self.assertEqual(ollama_proxy.message_content({"content": "안녕"}), "안녕")


class AccessControlTests(unittest.TestCase):
    def test_allows_only_the_endpoints_airi_uses(self) -> None:
        for path in ("/v1/chat/completions", "/api/chat", "/api/tags", "/health"):
            with self.subTest(path=path):
                self.assertTrue(ollama_proxy.is_allowed_path(path))

        for path in ("/api/delete", "/api/pull", "/api/push", "/api/create", "/v1/../api/delete"):
            with self.subTest(path=path):
                self.assertFalse(ollama_proxy.is_allowed_path(path))

    def test_blocked_path_returns_403(self) -> None:
        response = TestClient(ollama_proxy.app).post("/api/delete", json={"model": "exaone-airi:2.4b"})

        self.assertEqual(response.status_code, 403)

    def test_foreign_browser_origin_returns_403(self) -> None:
        response = TestClient(ollama_proxy.app).get(
            "/health", headers={"Origin": "http://evil.example"}
        )

        self.assertEqual(response.status_code, 403)

    def test_allowlisted_origin_and_originless_clients_pass(self) -> None:
        http = TestClient(ollama_proxy.app)

        self.assertEqual(http.get("/health", headers={"Origin": "http://127.0.0.1:5173"}).status_code, 200)
        self.assertEqual(http.get("/health").status_code, 200)
        self.assertTrue(ollama_proxy.is_allowed_origin("app://."))
        self.assertFalse(ollama_proxy.is_allowed_origin("https://example.com"))


class UpstreamResilienceTests(unittest.TestCase):
    def test_upstream_timeout_is_bounded(self) -> None:
        self.assertIsNotNone(ollama_proxy.UPSTREAM_TIMEOUT.connect)
        self.assertIsNotNone(ollama_proxy.UPSTREAM_TIMEOUT.read)
        self.assertLessEqual(ollama_proxy.CODEX_SEARCH_TIMEOUT_SECONDS, 30.0)

    def test_upstream_timeout_ends_the_stream(self) -> None:
        import httpx

        with mock.patch.object(
            ollama_proxy, "client", _StubClient(httpx.ReadTimeout("too slow"))
        ):
            response = post_stream("안녕")

        self.assertEqual(response.status_code, 200)
        self.assertIn(ollama_proxy.UPSTREAM_TIMEOUT_DIALOGUE, response.text)
        self.assertIn("[DONE]", response.text)


class CloudSearchFallbackTests(unittest.TestCase):
    def test_failed_search_falls_back_to_the_local_model(self) -> None:
        async def failing_search(user_text: str, query: str) -> tuple[str, float]:
            raise RuntimeError("codex unavailable")

        async def local_answer(
            method: str, path: str, params: object, headers: dict, body: bytes
        ) -> str:
            return "이터널 리턴 선수야."

        with mock.patch.object(ollama_proxy, "run_codex_search", failing_search), mock.patch.object(
            ollama_proxy, "fetch_local_dialogue", local_answer
        ), mock.patch.object(ollama_proxy, "client", _StubClient(RuntimeError("unused"))):
            response = post_stream("음유잉여 검색해줘")

        self.assertEqual(response.status_code, 200)
        self.assertIn(ollama_proxy.SEARCH_FALLBACK_PREFIX, response.text)
        self.assertIn("이터널 리턴 선수야.", response.text)
        self.assertIn("[DONE]", response.text)

    def test_search_timeout_without_a_local_model_still_closes_the_stream(self) -> None:
        async def timing_out_search(user_text: str, query: str) -> tuple[str, float]:
            raise asyncio.TimeoutError

        async def broken_local(
            method: str, path: str, params: object, headers: dict, body: bytes
        ) -> str:
            raise RuntimeError("ollama down")

        with mock.patch.object(ollama_proxy, "run_codex_search", timing_out_search), mock.patch.object(
            ollama_proxy, "fetch_local_dialogue", broken_local
        ), mock.patch.object(ollama_proxy, "client", _StubClient(RuntimeError("unused"))):
            response = post_stream("음유잉여 검색해줘")

        self.assertIn(ollama_proxy.SEARCH_UNAVAILABLE_DIALOGUE, response.text)
        self.assertIn("[DONE]", response.text)

    def test_slow_search_emits_sse_heartbeats(self) -> None:
        async def slow_search(user_text: str, query: str) -> tuple[str, float]:
            await asyncio.sleep(0.15)
            return "결과를 찾았어.", 150.0

        with mock.patch.object(ollama_proxy, "HEARTBEAT_INTERVAL_SECONDS", 0.02), mock.patch.object(
            ollama_proxy, "run_codex_search", slow_search
        ), mock.patch.object(ollama_proxy, "client", _StubClient(RuntimeError("unused"))):
            response = post_stream("음유잉여 검색해줘")

        self.assertIn(": ping", response.text)
        self.assertIn("결과를 찾았어.", response.text)
        self.assertIn("[DONE]", response.text)


class SseContractTests(unittest.TestCase):
    def test_known_proper_noun_adds_untrusted_search_context(self) -> None:
        prompt = ollama_proxy.build_codex_search_prompt("음유잉여 검색해줘", "음유잉여")

        self.assertIn("이터널 리턴", prompt)
        self.assertIn("웹 결과로 검증", prompt)

    def test_sse_delta_is_valid_openai_chunk(self) -> None:
        event = ollama_proxy.openai_sse_delta(
            "chatcmpl-test",
            "test-model",
            "응! ",
            include_role=True,
        ).decode("utf-8")
        payload = json.loads(event.removeprefix("data: ").strip())

        self.assertEqual(payload["choices"][0]["delta"]["role"], "assistant")
        self.assertEqual(payload["choices"][0]["delta"]["content"], "응! ")

    def test_immediate_ack_literal_is_closed_by_a_trailing_marker(self) -> None:
        # AIRI's marker parser deliberately retains the last five literal
        # characters. A trailing marker forces the acknowledgement literal
        # to flush to the sentence/TTS pipeline before the next SSE delta.
        for ack in (
            ollama_proxy.LOCAL_IMMEDIATE_ACK,
            ollama_proxy.SEARCH_IMMEDIATE_ACK,
        ):
            with self.subTest(ack=ack):
                self.assertGreater(ack.count("<|ACT "), 1)
                self.assertTrue(ack.endswith("|>"))
                self.assertRegex(ack, r"\|>\s+\S.+\s+<\|ACT ")


if __name__ == "__main__":
    unittest.main()
