import asyncio
import os
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from memory_extraction_provider import MemoryExtractionProvider
from memory_runtime import MemoryConfig, MemoryRuntime


class Response:
    def __init__(self, body, status_code=200): self.body, self.status_code = body, status_code
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError("HTTP error")
    def json(self): return self.body


class FakeClient:
    def __init__(self, body, status_code=200): self.body, self.status_code, self.calls = body, status_code, []
    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response(self.body, self.status_code)


class TagClient:
    async def get(self, url, timeout=None):
        return Response({"models":[{"name":"extractor:latest"}]})


class CollectingLedger:
    def __init__(self): self.records = []
    def record(self, record): self.records.append(record)


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def config(self, provider, **changes):
        base = MemoryConfig(
            enabled=True, extraction_model="extractor", extraction_provider=provider,
            allow_external_extraction=True,
            extraction_base_url=("https://api.openai.com/v1" if provider == "openai" else "https://api.anthropic.com/v1"),
            extraction_api_key="not-a-real-key",
        )
        return replace(base, **changes)

    async def test_openai_exact_request_and_parse(self):
        client = FakeClient({"choices": [{"finish_reason":"stop","message": {"content": '{"extracted":[]}'}}]})
        provider = MemoryExtractionProvider(self.config("openai"), client)
        self.assertEqual(await provider.chat_json("system", "input", {"type": "object"}), '{"extracted":[]}')
        url, kwargs = client.calls[0]
        self.assertEqual(url, "https://api.openai.com/v1/chat/completions")
        self.assertEqual(kwargs["headers"], {"Authorization": "Bearer not-a-real-key", "Content-Type": "application/json"})
        body = kwargs["json"]
        self.assertEqual((body["store"], body["temperature"]), (False, 0))
        self.assertEqual(body["response_format"], {"type": "json_schema", "json_schema": {"name": "memory_extraction", "strict": True, "schema": {"type": "object"}}})

    async def test_truncated_external_json_is_rejected_even_when_parseable(self):
        client=FakeClient({"choices":[{"finish_reason":"length","message":{"content":"{\"extracted\":[]}"}}]})
        with self.assertRaises(ValueError):
            await MemoryExtractionProvider(self.config("openai"),client).chat_json("system","input",{"type":"object"})
        client=FakeClient({"stop_reason":"max_tokens","content":[{"type":"text","text":"{\"extracted\":[]}"}]})
        with self.assertRaises(ValueError):
            await MemoryExtractionProvider(self.config("anthropic"),client).chat_json("system","input",{"type":"object"})

    async def test_anthropic_exact_request_and_parse(self):
        client = FakeClient({"stop_reason": "end_turn", "content": [{"type": "text", "text": '{"operations":[]}' }]})
        provider = MemoryExtractionProvider(self.config("anthropic"), client)
        self.assertEqual(await provider.chat_json("system", "input", {"type": "object"}), '{"operations":[]}')
        url, kwargs = client.calls[0]
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(kwargs["headers"], {"x-api-key": "not-a-real-key", "anthropic-version": "2023-06-01", "content-type": "application/json"})
        body = kwargs["json"]
        self.assertEqual((body["temperature"], body["max_tokens"]), (0, 2048))
        self.assertEqual(body["output_config"], {"format": {"type": "json_schema", "schema": {"type": "object"}}})

    async def test_external_extraction_usage_is_recorded_without_content(self):
        cases = (
            ("openai", {
                "choices": [{"finish_reason": "stop", "message": {"content": '{"extracted":[]}'}}],
                "usage": {"prompt_tokens": 13, "completion_tokens": 5,
                          "prompt_tokens_details": {"cached_tokens": 3}},
            }, (13, 5, 3, None)),
            ("anthropic", {
                "stop_reason": "end_turn", "content": [{"type": "text", "text": '{"extracted":[]}'}],
                "usage": {"input_tokens": 11, "output_tokens": 4,
                          "cache_read_input_tokens": 2, "cache_creation_input_tokens": 1},
            }, (11, 4, 2, 1)),
        )
        for provider_name, response, expected in cases:
            with self.subTest(provider=provider_name):
                ledger = CollectingLedger()
                provider = MemoryExtractionProvider(
                    self.config(provider_name), FakeClient(response), ledger
                )
                await provider.chat_json("private system", "private input", {"type": "object"})
                record = ledger.records[0]
                self.assertEqual((record.input_tokens, record.output_tokens,
                                  record.cache_read_tokens, record.cache_write_tokens), expected)
                self.assertEqual(record.status, "completed")
                self.assertNotIn("private", repr(record))

        rejected = CollectingLedger()
        provider = MemoryExtractionProvider(
            self.config("openai"),
            FakeClient({
                "choices": [{"finish_reason": "length", "message": {"content": '{"extracted":[]}'}}],
                "usage": {"prompt_tokens": 17, "completion_tokens": 6},
            }),
            rejected,
        )
        with self.assertRaises(ValueError):
            await provider.chat_json("private system", "private input", {"type": "object"})
        self.assertEqual((rejected.records[0].status, rejected.records[0].input_tokens,
                          rejected.records[0].output_tokens), ("error", 17, 6))

    async def test_unapproved_or_missing_key_has_zero_calls_and_no_failure(self):
        for config in (self.config("openai", allow_external_extraction=False), self.config("anthropic", extraction_api_key="")):
            with self.subTest(provider=config.extraction_provider):
                with tempfile.TemporaryDirectory() as tmp:
                    client = FakeClient({})
                    runtime = MemoryRuntime(replace(config, db_path=os.path.join(tmp, "memory.db"), extraction_threshold=2), http_client=client)
                    await runtime.startup()
                    await runtime.schedule_completed_turn("s", "u", "a", 1)
                    await runtime._extract("s", "test", force=True)
                    self.assertEqual(client.calls, [])
                    self.assertEqual(runtime.store.job_state("s")["fail_count"], 0)
                    health = await runtime.health("s")
                    self.assertFalse(health["extraction_ready"])
                    self.assertNotIn("not-a-real-key", repr(health))
                    await runtime.shutdown()

    async def test_local_preflight_accepts_implicit_latest_tag(self):
        provider = MemoryExtractionProvider(
            MemoryConfig(enabled=True, extraction_model="extractor"), TagClient()
        )
        self.assertTrue(await provider.preflight(force=True))
        self.assertEqual(provider.availability, "ready")

    async def test_local_ollama_stage_a_and_b_payloads_disable_thinking(self):
        client = FakeClient({"message": {"content": '{"extracted":[]}'}})
        provider = MemoryExtractionProvider(
            MemoryConfig(enabled=True, extraction_model="extractor", extraction_seed=7,
                         extraction_max_tokens=333), client
        )
        await provider._ollama("stage a", "input", {"type": "object"})
        await provider._ollama("stage b", "input", {"type": "object"})
        for _url, kwargs in client.calls:
            body = kwargs["json"]
            self.assertIs(body["think"], False)
            options = body["options"]
            self.assertEqual((options["seed"], options["num_predict"]), (7, 333))

    async def test_permanent_external_4xx_counts_failure_without_retry_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient({}, status_code=401)
            runtime = MemoryRuntime(
                replace(
                    self.config("openai"),
                    db_path=os.path.join(tmp, "memory.db"),
                    extraction_threshold=3,
                ),
                http_client=client,
            )
            await runtime.startup()
            await runtime.schedule_completed_turn("s", "u", "a", 1)
            await runtime._extract("s", "test", force=True)
            state = runtime.store.job_state("s")
            self.assertEqual((state["pending_msgs"], state["fail_count"]), (2, 1))
            self.assertFalse(runtime._extraction_retry_sessions)
            health = await runtime.health("s")
            self.assertEqual(health["extraction_availability"], "rejected")
            self.assertFalse(health["extraction_ready"])
            await runtime.shutdown()

    def test_env_defaults_off_and_rejects_unapproved_external_host(self):
        with patch.dict(os.environ, {"AIRI_MEMORY_EXTRACTION_PROVIDER": "openai"}, clear=True):
            config = MemoryConfig.from_env()
        self.assertFalse(config.allow_external_extraction)
        self.assertEqual(config.extraction_base_url, "https://api.openai.com/v1")
        with patch.dict(os.environ, {"AIRI_MEMORY_EXTRACTION_PROVIDER": "anthropic", "AIRI_MEMORY_ANTHROPIC_BASE_URL": "https://elsewhere.example/v1"}, clear=True):
            with self.assertRaises(ValueError):
                MemoryConfig.from_env()


if __name__ == "__main__":
    unittest.main()
