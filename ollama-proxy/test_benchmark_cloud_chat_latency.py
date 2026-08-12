import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from benchmark_cloud_chat_latency import BenchmarkError, benchmark, main, measure_stream
from cloud_chat_provider import CloudChatConfig, CloudChatProvider


class Clock:
    def __init__(self, values): self.values = iter(values)
    def __call__(self): return next(self.values)


class Response:
    def __init__(self, chunks): self.chunks = chunks
    def raise_for_status(self): pass
    async def aiter_raw(self):
        for chunk in self.chunks:
            yield chunk


class Client:
    def __init__(self, responses): self.responses = iter(responses)
    def build_request(self, *_args, **_kwargs): return object()
    async def send(self, _request, stream=False):
        self.stream = stream
        return next(self.responses)


def openai_response(text="hi", complete=True):
    ending = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n' if complete else b''
    return Response([b'data: {"choices":[{"delta":{"content":"' + text.encode() + b'"},"finish_reason":null}]}\n\n' + ending])


class BenchmarkCloudChatLatencyTests(unittest.IsolatedAsyncioTestCase):
    def config(self):
        return CloudChatConfig("openai", True, "safe-test-model", "test-secret", "https://api.openai.com/v1", "")

    async def test_real_provider_stream_path_records_ttft_total_and_p50(self):
        client = Client([openai_response(), openai_response()])
        result = await benchmark(self.config(), 2, "private prompt", client,
                                 Clock([0, .1, .3, 1, 1.2, 1.6]))
        self.assertEqual(result["runs"], [{"ttft_ms": 100.0, "total_ms": 300.0},
                                           {"ttft_ms": 200.0, "total_ms": 600.0}])
        self.assertEqual(result["summary"], {"ttft": {"count": 2, "p50_ms": 150.0},
                                             "total": {"count": 2, "p50_ms": 450.0}})
        self.assertNotIn("private prompt", str(result))
        self.assertTrue(client.stream)

    async def test_truncated_or_empty_stream_is_a_clean_error(self):
        provider = CloudChatProvider(self.config(), Client([openai_response(complete=False)]))
        with self.assertRaisesRegex(RuntimeError, "normal completion"):
            await measure_stream(provider, {"messages": []}, Clock([0, .1]))
        provider = CloudChatProvider(self.config(), Client([openai_response(text="", complete=True)]))
        with self.assertRaisesRegex(BenchmarkError, "without a text delta"):
            await measure_stream(provider, {"messages": []}, Clock([0, .1]))

    async def test_missing_credential_has_no_network_attempt(self):
        config = CloudChatConfig("openai", True, "model", "", "https://api.openai.com/v1", "")
        client = Client([])
        with self.assertRaisesRegex(BenchmarkError, "missing credential"):
            await benchmark(config, 1, "private", client)

    def test_main_writes_a_redacted_json_report_only_when_requested(self):
        env = {"AIRI_CHAT_PROVIDER": "openai", "AIRI_ALLOW_EXTERNAL_CHAT": "1",
               "AIRI_CHAT_MODEL": "model", "OPENAI_API_KEY": "secret"}
        with patch.dict(os.environ, env, clear=True), tempfile.TemporaryDirectory() as temp:
            report = os.path.join(temp, "report.json")
            with patch("benchmark_cloud_chat_latency.async_main", new_callable=AsyncMock,
                       return_value=(0, {"status": "measured", "provider": "openai", "model": "model", "runs": [], "summary": {"ttft": {"count": 0, "p50_ms": 0}, "total": {"count": 0, "p50_ms": 0}}, "prompt_sha256": "hash"})):
                self.assertEqual(main(["--report", report, "--prompt", "private prompt"]), 0)
            with open(report, encoding="utf-8") as handle:
                text = handle.read()
        self.assertNotIn("private prompt", text)
        self.assertNotIn("secret", text)


if __name__ == "__main__":
    unittest.main()
