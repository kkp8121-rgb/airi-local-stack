import json
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from cloud_chat_provider import CloudChatConfig, CloudChatProvider


class Response:
    def __init__(self, chunks, error=None): self.chunks = chunks; self.closed = False; self.error = error
    def raise_for_status(self):
        if self.error: raise self.error
    async def aclose(self): self.closed = True
    async def aiter_raw(self):
        for chunk in self.chunks:
            yield chunk


class Client:
    def __init__(self, response): self.response = response; self.requests = []
    def build_request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs)); return object()
    async def send(self, request, stream=False):
        self.stream = stream; return self.response


class BrokenLedger:
    def record(self, _record): raise OSError("ledger unavailable")


class CollectingLedger:
    def __init__(self): self.records = []
    def record(self, record): self.records.append(record)


class CloudChatProviderTests(unittest.IsolatedAsyncioTestCase):
    def config(self, provider):
        return CloudChatConfig(provider=provider, allow_external=True, model="safe-test-model",
            api_key="not-a-real-key", base_url=f"https://api.{provider}.com/v1")

    async def test_openai_exact_request_and_unicode_sse(self):
        event = ('data: {"choices":[{"delta":{"content":"안녕"},"finish_reason":null}]}\n\n'
                 'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                 'data: [DONE]\n\n').encode()
        unicode_offset = event.index("안".encode("utf-8"))
        response = Response([event[:unicode_offset + 1], event[unicode_offset + 1:]])
        client = Client(response); provider = CloudChatProvider(self.config("openai"), client)
        response = await provider.open_stream({"model":"ignored", "stream":False, "options":{"num_gpu":12}, "messages":[{"role":"user","content":"hello"}]})
        self.assertEqual([text async for text in provider.deltas(response)], ["안녕"])
        method, url, kwargs = client.requests[0]
        self.assertEqual((method, url), ("POST", "https://api.openai.com/v1/chat/completions"))
        self.assertEqual(kwargs["headers"], {"Authorization":"Bearer not-a-real-key", "Content-Type":"application/json"})
        self.assertEqual(json.loads(kwargs["content"]), {"model":"safe-test-model", "stream":True, "store":False,
            "stream_options":{"include_usage":True}, "messages":[{"role":"user","content":"hello"}]})

    async def test_anthropic_exact_request_and_multiline_delta(self):
        event = (b'data: {"type":"content_block_delta",\ndata: "delta":{"text":"hello"}}\n\n'
                 b'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}\n\n'
                 b'data: {"type":"message_stop"}\n\n')
        client = Client(Response([event])); provider = CloudChatProvider(self.config("anthropic"), client)
        response = await provider.open_stream({"messages":[{"role":"system","content":"rules"},{"role":"user","content":"hello"}]})
        self.assertEqual([text async for text in provider.deltas(response)], ["hello"])
        _method, url, kwargs = client.requests[0]
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(kwargs["headers"], {"x-api-key":"not-a-real-key", "anthropic-version":"2023-06-01", "content-type":"application/json"})
        self.assertEqual(json.loads(kwargs["content"]), {"model":"safe-test-model", "stream":True, "max_tokens":1024, "system":[{"type":"text","text":"rules","cache_control":{"type":"ephemeral"}}], "messages":[{"role":"user","content":"hello"}]})

    async def test_http_error_closes_response_and_truncated_stream_fails(self):
        failed=Response([],RuntimeError("429")); provider=CloudChatProvider(self.config("openai"),Client(failed))
        with self.assertRaises(RuntimeError): await provider.open_stream({"messages":[]})
        self.assertTrue(failed.closed)
        truncated=Response([b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'])
        provider=CloudChatProvider(self.config("openai"),Client(truncated))
        response=await provider.open_stream({"messages":[]})
        with self.assertRaises(RuntimeError):
            _=[part async for part in provider.deltas(response)]
        length=Response([b'data: {"choices":[{"delta":{"content":"partial"},"finish_reason":null}]}\n\n'
                         b'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n'
                         b'data: [DONE]\n\n'])
        provider=CloudChatProvider(self.config("openai"),Client(length))
        response=await provider.open_stream({"messages":[]})
        with self.assertRaises(RuntimeError):
            _=[part async for part in provider.deltas(response)]

    async def test_usage_is_collected_and_ledger_failure_is_fail_soft(self):
        event = (b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                 b'data: {"choices":[],"usage":{"prompt_tokens":7,"completion_tokens":11,"prompt_tokens_details":{"cached_tokens":2}}}\n\n'
                 b'data: [DONE]\n\n')
        collector = CollectingLedger()
        provider = CloudChatProvider(self.config("openai"), Client(Response([event])), collector)
        response = await provider.open_stream({"messages":[]})
        self.assertEqual([part async for part in provider.deltas(response)], [])
        self.assertEqual((collector.records[0].input_tokens, collector.records[0].output_tokens,
                          collector.records[0].cache_read_tokens, collector.records[0].status), (7, 11, 2, "completed"))
        provider = CloudChatProvider(self.config("openai"), Client(Response([event])), BrokenLedger())
        response = await provider.open_stream({"messages":[]})
        self.assertEqual([part async for part in provider.deltas(response)], [])

    async def test_anthropic_usage_and_abnormal_completion_contract(self):
        completed = (
            b'data: {"type":"message_start","message":{"usage":{"input_tokens":5,'
            b'"cache_read_input_tokens":3,"cache_creation_input_tokens":2}}}\n\n'
            b'data: {"type":"message_delta","usage":{"output_tokens":7},'
            b'"delta":{"stop_reason":"end_turn"}}\n\n'
            b'data: {"type":"message_stop"}\n\n'
        )
        collector = CollectingLedger()
        provider = CloudChatProvider(self.config("anthropic"), Client(Response([completed])), collector)
        response = await provider.open_stream({"messages":[]})
        self.assertEqual([part async for part in provider.deltas(response)], [])
        usage = collector.records[0]
        self.assertEqual((usage.input_tokens, usage.output_tokens, usage.cache_read_tokens,
                          usage.cache_write_tokens, usage.status), (5, 7, 3, 2, "completed"))

        for event in (
            b'data: {"type":"message_delta","delta":{"stop_reason":"max_tokens"}}\n\n'
            b'data: {"type":"message_stop"}\n\n',
            b'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}\n\n',
        ):
            with self.subTest(event=event):
                rejected = CollectingLedger()
                provider = CloudChatProvider(self.config("anthropic"), Client(Response([event])), rejected)
                response = await provider.open_stream({"messages":[]})
                with self.assertRaises(RuntimeError):
                    _ = [part async for part in provider.deltas(response)]
                self.assertEqual(rejected.records[0].status, "error")

    def test_default_and_unapproved_or_missing_key_never_ready(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(CloudChatConfig.from_env().provider, "local")
        for config in (replace(self.config("openai"), allow_external=False), replace(self.config("anthropic"), api_key="")):
            client = Client(Response([])); provider = CloudChatProvider(config, client)
            self.assertFalse(provider.ready)
            self.assertEqual(client.requests, [])
        with patch.dict(os.environ, {"AIRI_CHAT_PROVIDER":"openai", "AIRI_CHAT_OPENAI_BASE_URL":"https://untrusted.example/v1"}, clear=True):
            with self.assertRaises(ValueError): CloudChatConfig.from_env()


if __name__ == "__main__": unittest.main()
