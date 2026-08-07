import json
import unittest

import ollama_proxy


class SearchRoutingTests(unittest.TestCase):
    def test_detects_korean_search_intents(self) -> None:
        for text in (
            "음유잉여 검색해줘",
            "음유잉여 웹서칭해봐",
            "음유잉여가 누군지 찾아봐",
        ):
            with self.subTest(text=text):
                self.assertTrue(ollama_proxy.is_search_request(text))

        self.assertFalse(ollama_proxy.is_search_request("음유잉여가 누구야?"))

    def test_prefers_quoted_proper_noun_as_query(self) -> None:
        query = ollama_proxy.extract_search_query("고유명사 '음유잉여'를 웹에서 검색해줘")

        self.assertEqual(query, "음유잉여")

    def test_extracts_unquoted_query_without_command_residue(self) -> None:
        query = ollama_proxy.extract_search_query("음유잉여를 웹에서 검색해줘")

        self.assertEqual(query, "음유잉여")

    def test_normalizes_cloud_markdown_for_speech(self) -> None:
        normalized = ollama_proxy.normalize_cloud_result(
            "[이터널 리턴 공식 사이트](https://example.com)에서 확인했어. **선수 닉네임**이야."
        )

        self.assertNotIn("https://", normalized)
        self.assertNotIn("**", normalized)
        self.assertIn("이터널 리턴 공식 사이트", normalized)

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
