import argparse
import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import httpx

import run_airi_conversation_soak as runner


class FragmentedSseStream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    def __iter__(self):
        yield from self.chunks

    def close(self) -> None:
        pass


def _sse_response(
    content: str,
    *,
    immediate_ack: str | None,
    fragment: bool = False,
) -> httpx.Response:
    payload = (
        'data: ' + json.dumps({"choices": [{"delta": {"content": content}}]})
        + '\n\ndata: [DONE]\n\n'
    ).encode("utf-8")
    headers = {} if immediate_ack is None else {"X-AIRI-Immediate-Ack": immediate_ack}
    if fragment:
        chunks = [payload[index:index + 5] for index in range(0, len(payload), 5)]
        return httpx.Response(200, headers=headers, stream=FragmentedSseStream(chunks))
    return httpx.Response(200, headers=headers, content=payload)


class ConversationSoakTransportTests(unittest.TestCase):
    def test_proxy_literal_contract_matches_runner_constants(self) -> None:
        """Read source only: importing the live proxy has runtime side effects."""
        proxy_source = Path(__file__).resolve().parents[1] / "ollama_proxy.py"
        wanted = {
            "LOCAL_IMMEDIATE_ACK",
            "SEARCH_IMMEDIATE_ACK",
            "GROUNDING_SILENCE_FALLBACK_DIALOGUE",
        }
        values: dict[str, str] = {}
        # 침묵 폴백 풀(GROUNDING_SILENCE_FALLBACK_POOL, 6문구 결정론 순환)이 SSoT다.
        # 첫 원소는 GROUNDING_SILENCE_FALLBACK_DIALOGUE 를 그대로 참조하는 Name
        # 노드라서(중복 리터럴 방지) ast.literal_eval 이 통째로는 못 읽는다 —
        # 순수 리터럴 원소만 개별 literal_eval 하고 Name 원소는 위에서 이미 뽑은
        # 값으로 치환한다(ollama-proxy/eval/broadcast_sim/test_broadcast_sim.py 의
        # EchoFilterProxyContractTests._proxy_silence_fallback_pool 과 동일 패턴).
        pool_elts: list[ast.expr] | None = None
        for node in ast.parse(proxy_source.read_text(encoding="utf-8")).body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in wanted:
                    values[target.id] = ast.literal_eval(node.value)
                elif isinstance(target, ast.Name) and target.id == "GROUNDING_SILENCE_FALLBACK_POOL":
                    self.assertIsInstance(node.value, ast.Tuple)
                    pool_elts = list(node.value.elts)
        self.assertEqual(values.keys(), wanted)
        self.assertIsNotNone(pool_elts, "GROUNDING_SILENCE_FALLBACK_POOL 을 프록시 소스에서 못 찾았다")
        pool = frozenset(
            values[elt.id] if isinstance(elt, ast.Name) else ast.literal_eval(elt)
            for elt in pool_elts
        )
        self.assertEqual(runner.LOCAL_IMMEDIATE_ACK, values["LOCAL_IMMEDIATE_ACK"])
        self.assertEqual(runner.SEARCH_IMMEDIATE_ACK, values["SEARCH_IMMEDIATE_ACK"])
        self.assertEqual(runner.NON_SUBSTANTIVE_RESPONSES, pool)

    def _reply(self, content: str, header: str | None, *, fragment: bool = False) -> runner.StreamReply:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "POST")
            return _sse_response(content, immediate_ack=header, fragment=fragment)

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return runner._stream_reply(
                client, "http://airi.test:8080/v1/chat/completions", "test-model", [], "test-session",
            )

    def test_local_ack_is_header_gated_and_fragment_safe(self) -> None:
        reply = self._reply(runner.LOCAL_IMMEDIATE_ACK + "  Final answer.  ", "audible", fragment=True)
        self.assertEqual(reply.content, "Final answer.")
        self.assertEqual(reply.immediate_ack, "local")
        self.assertEqual(reply.immediate_ack_count, 1)
        self.assertTrue(runner._score({"language": "en"}, reply.content)["checks"]["no_control"])

    def test_search_ack_is_classified(self) -> None:
        reply = self._reply(runner.SEARCH_IMMEDIATE_ACK + "Search result.", "audible")
        self.assertEqual(reply.content, "Search result.")
        self.assertEqual(reply.immediate_ack, "search")
        self.assertEqual(reply.immediate_ack_count, 1)

    def test_non_audible_headers_never_strip_ack_text(self) -> None:
        combined = runner.LOCAL_IMMEDIATE_ACK + "  Final answer.  "
        for header in (None, "silent", "false"):
            with self.subTest(header=header):
                reply = self._reply(combined, header)
                self.assertEqual(reply.content, combined.strip())
                self.assertIsNone(reply.immediate_ack)
                self.assertEqual(reply.immediate_ack_count, 0)
                self.assertFalse(runner._score({"language": "en"}, reply.content)["checks"]["no_control"])

    def test_unexpected_or_malformed_control_is_not_removed(self) -> None:
        for content in (
            '<|ACT {"emotion":"other"}|> Final answer.',
            runner.LOCAL_IMMEDIATE_ACK + ' <|ACT malformed Final answer.',
        ):
            with self.subTest(content=content):
                reply = self._reply(content, "audible")
                self.assertFalse(runner._score({"language": "en"}, reply.content)["checks"]["no_control"])

    def test_waiting_fallback_is_not_a_substantive_response(self) -> None:
        fallback = runner._score({"korean": True}, "음, 잠깐만.")
        real_response = runner._score({"language": "en"}, "A real answer.")
        self.assertFalse(fallback["checks"]["substantive_response"])
        self.assertFalse(fallback["passed"])
        self.assertTrue(real_response["checks"]["substantive_response"])
        self.assertTrue(real_response["passed"])

    def test_main_reports_ack_metadata_and_keeps_only_final_dialogue_in_history(self) -> None:
        requests: list[dict[str, object]] = []
        final_contents = iter(("First answer.", "Second answer."))

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/health":
                return httpx.Response(200, json={})
            payload = json.loads(request.content)
            requests.append(payload)
            return _sse_response(
                runner.LOCAL_IMMEDIATE_ACK + next(final_contents), immediate_ack="audible",
            )

        cases = (
            {"id": "one", "group": "shared", "input": "first", "korean": False, "language": "en"},
            {"id": "two", "group": "shared", "input": "second", "korean": False, "language": "en"},
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            args = argparse.Namespace(
                endpoint="http://airi.test:8080/v1/chat/completions", model="test-model", output=output,
                temperature=0.2, request_timeout_seconds=20.0, style_card=None, case_id=[],
            )
            client = httpx.Client(transport=httpx.MockTransport(handler))
            with mock.patch.object(runner, "CASES", cases), \
                    mock.patch.object(runner.argparse.ArgumentParser, "parse_args", return_value=args), \
                    mock.patch.object(runner.httpx, "Client", return_value=client):
                self.assertEqual(runner.main(), 0)
            report = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual([row["output"] for row in report["cases"]], ["First answer.", "Second answer."])
        self.assertEqual([row["immediate_ack"] for row in report["cases"]], ["local", "local"])
        self.assertEqual([row["immediate_ack_count"] for row in report["cases"]], [1, 1])
        self.assertEqual(requests[1]["messages"], [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "First answer."},
            {"role": "user", "content": "second"},
        ])


if __name__ == "__main__":
    unittest.main()
