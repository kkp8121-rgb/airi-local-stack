import asyncio
import json
import os
import tempfile
import unittest
from collections.abc import AsyncIterator
from pathlib import Path
from unittest import mock

import httpx
from fastapi.testclient import TestClient

import llm_backends
import ollama_proxy


def run(coroutine):
    return asyncio.run(coroutine)


async def collect(iterator: AsyncIterator[str]) -> list[str]:
    return [item async for item in iterator]


async def adeltas(chunks) -> AsyncIterator[str]:
    for chunk in chunks:
        yield chunk


class _StubClient:
    """httpx.AsyncClient stand-in whose send always fails (local path down)."""

    def __init__(self, error: BaseException) -> None:
        self._error = error

    def build_request(self, *args: object, **kwargs: object) -> object:
        return object()

    async def send(self, *args: object, **kwargs: object) -> object:
        raise self._error


class _FakeBackend:
    """Mock adapter: yields canned deltas, optionally slowly or with an error."""

    def __init__(self, deltas, *, delay: float = 0.0, error: BaseException | None = None) -> None:
        self.deltas = deltas
        self.delay = delay
        self.error = error
        self.system_prompt = ""
        self.messages: list[object] = []
        self.memory_block = ""

    async def stream_completion(self, system_prompt, messages, *, memory_block=""):
        self.system_prompt = system_prompt
        self.messages = list(messages)
        self.memory_block = memory_block
        if self.error is not None:
            raise self.error
        for delta in self.deltas:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield delta


def sse_client(body: bytes, status_code: int = 200) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code,
            content=body,
            headers={"content-type": "text/event-stream"},
        )

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), captured


def post_stream(text: str) -> object:
    return TestClient(ollama_proxy.app).post(
        "/v1/chat/completions",
        json={
            "model": "exaone-airi:2.4b",
            "stream": True,
            "messages": [{"role": "user", "content": text}],
        },
    )


ANTHROPIC_STREAM = b"""event: message_start
data: {"type":"message_start","message":{"usage":{"input_tokens":42}}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"\\uc751! "}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"ignored"}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"\\ucd95\\ud558\\ud574."}}

event: message_delta
data: {"type":"message_delta","usage":{"output_tokens":11}}

event: message_stop
data: {"type":"message_stop"}

"""

OPENAI_STREAM = b"""data: {"choices":[{"delta":{"role":"assistant"}}]}

data: {"choices":[{"delta":{"content":"\\uc751! "}}]}

data: {"choices":[{"delta":{"content":"\\ucd95\\ud558\\ud574."}}]}

data: {"choices":[],"usage":{"prompt_tokens":31,"completion_tokens":9}}

data: [DONE]

"""


class AnthropicBackendTests(unittest.TestCase):
    def make_backend(self, body: bytes, status_code: int = 200):
        client, captured = sse_client(body, status_code)
        config = ollama_proxy.llm_mode_config("cloud_anthropic")
        return llm_backends.AnthropicBackend(config, client), captured

    def test_parses_text_deltas_and_usage(self) -> None:
        backend, captured = self.make_backend(ANTHROPIC_STREAM)

        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            deltas = run(collect(backend.stream_completion("페르소나", [{"role": "user", "content": "안녕"}])))

        self.assertEqual(deltas, ["응! ", "축하해."])
        self.assertEqual(backend.last_usage, {"input_tokens": 42, "output_tokens": 11})
        self.assertEqual(captured[0].headers["x-api-key"], "test-key")
        self.assertEqual(captured[0].headers["anthropic-version"], "2023-06-01")

    def test_sends_cached_persona_as_the_first_system_block(self) -> None:
        backend, captured = self.make_backend(ANTHROPIC_STREAM)

        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            run(
                collect(
                    backend.stream_completion(
                        "페르소나",
                        [{"role": "user", "content": "안녕"}],
                        memory_block="기억: 사용자는 강아지를 키운다.",
                    )
                )
            )

        payload = json.loads(captured[0].content)
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["system"][0]["text"], "페르소나")
        self.assertEqual(payload["system"][0]["cache_control"], {"type": "ephemeral"})
        # The memory block trails the cached persona so the prefix stays stable.
        self.assertEqual(payload["system"][1]["text"], "기억: 사용자는 강아지를 키운다.")
        self.assertNotIn("cache_control", payload["system"][1])
        self.assertEqual(payload["messages"], [{"role": "user", "content": "안녕"}])

    def test_missing_key_raises_before_any_request(self) -> None:
        backend, captured = self.make_backend(ANTHROPIC_STREAM)

        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(llm_backends.LLMBackendError):
                run(collect(backend.stream_completion("페르소나", [{"role": "user", "content": "안녕"}])))

        self.assertEqual(captured, [])

    def test_rate_limited_response_raises_backend_error(self) -> None:
        backend, _captured = self.make_backend(b'{"error":{"message":"overloaded"}}', status_code=529)

        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with self.assertRaises(llm_backends.LLMBackendError) as caught:
                run(collect(backend.stream_completion("페르소나", [{"role": "user", "content": "안녕"}])))

        self.assertIn("529", str(caught.exception))

    def test_stream_error_event_raises(self) -> None:
        body = b'data: {"type":"error","error":{"message":"overloaded_error"}}\n\n'
        backend, _captured = self.make_backend(body)

        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with self.assertRaises(llm_backends.LLMBackendError):
                run(collect(backend.stream_completion("페르소나", [{"role": "user", "content": "안녕"}])))

    def test_drops_system_turns_and_leading_assistant_turns(self) -> None:
        converted = llm_backends.to_anthropic_messages(
            [
                {"role": "system", "content": "무시"},
                {"role": "assistant", "content": "선행 응답"},
                {"role": "user", "content": "안녕"},
                {"role": "assistant", "content": "응!"},
                {"role": "user", "content": ""},
            ]
        )

        self.assertEqual(
            converted,
            [{"role": "user", "content": "안녕"}, {"role": "assistant", "content": "응!"}],
        )


class OpenAICompatBackendTests(unittest.TestCase):
    def test_parses_delta_stream_and_usage(self) -> None:
        client, captured = sse_client(OPENAI_STREAM)
        backend = llm_backends.OpenAICompatBackend(ollama_proxy.llm_mode_config("open"), client)

        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "or-test"}):
            deltas = run(collect(backend.stream_completion("페르소나", [{"role": "user", "content": "안녕"}])))

        self.assertEqual(deltas, ["응! ", "축하해."])
        self.assertEqual(backend.last_usage, {"input_tokens": 31, "output_tokens": 9})
        self.assertEqual(captured[0].headers["authorization"], "Bearer or-test")
        payload = json.loads(captured[0].content)
        self.assertEqual(payload["messages"][0], {"role": "system", "content": "페르소나"})
        self.assertTrue(payload["stream"])

    def test_local_provider_needs_no_authorization_header(self) -> None:
        client, captured = sse_client(OPENAI_STREAM)
        backend = llm_backends.build_backend(ollama_proxy.llm_mode_config("local"), client)

        deltas = run(collect(backend.stream_completion("페르소나", [{"role": "user", "content": "안녕"}])))

        self.assertEqual(deltas, ["응! ", "축하해."])
        self.assertNotIn("authorization", captured[0].headers)

    def test_error_payload_raises_backend_error(self) -> None:
        client, _captured = sse_client(b'data: {"error":{"message":"no credits"}}\n\n')
        backend = llm_backends.OpenAICompatBackend(ollama_proxy.llm_mode_config("open"), client)

        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "or-test"}):
            with self.assertRaises(llm_backends.LLMBackendError):
                run(collect(backend.stream_completion("페르소나", [{"role": "user", "content": "안녕"}])))

    def test_unknown_provider_is_rejected(self) -> None:
        with self.assertRaises(llm_backends.LLMBackendError):
            llm_backends.build_backend({"provider": "nope"}, httpx.AsyncClient())


def jsonl(*events: dict) -> list[bytes]:
    return [json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n" for event in events]


def codex_message(text: str, event_type: str = "item.completed") -> dict:
    return {"type": event_type, "item": {"id": "item_0", "type": "agent_message", "text": text}}


CODEX_ANSWER = "응! 축하해. 오늘은 푹 쉬어."
CODEX_JSONL = jsonl(
    {"type": "thread.started", "thread_id": "t1"},
    {"type": "turn.started"},
    codex_message(CODEX_ANSWER),
    {"type": "turn.completed", "usage": {"input_tokens": 20302, "output_tokens": 25}},
)


class _FakeStream:
    def __init__(self, lines: list[bytes]) -> None:
        self.lines = list(lines)

    async def readline(self) -> bytes:
        await asyncio.sleep(0)
        return self.lines.pop(0) if self.lines else b""

    async def read(self) -> bytes:
        return b""


class _FakeStdin:
    def __init__(self) -> None:
        self.written = b""
        self.closed = False

    def write(self, data: bytes) -> None:
        self.written += data

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    """asyncio subprocess stand-in: canned stdout lines, observable kill."""

    def __init__(self, lines: list[bytes], returncode: int = 0, hang: bool = False) -> None:
        self.stdin = _FakeStdin()
        self.stdout = _HangingStream() if hang else _FakeStream(lines)
        self.stderr = _FakeStream([])
        self._returncode = returncode
        self.returncode: int | None = None
        self.killed = False

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int:
        if self.returncode is None:
            self.returncode = self._returncode
        return self.returncode


class _HangingStream(_FakeStream):
    def __init__(self) -> None:
        super().__init__([])

    async def readline(self) -> bytes:
        await asyncio.sleep(30)
        return b""


class CodexBackendTests(unittest.TestCase):
    def backend(self, mode: str = "cloud") -> llm_backends.CodexBackend:
        return llm_backends.CodexBackend(ollama_proxy.llm_mode_config(mode))

    def test_command_reuses_the_hardened_sidecar_flags_without_search(self) -> None:
        command = self.backend().build_command(["node", "codex.js"])

        self.assertEqual(command[:3], ["node", "codex.js", "exec"])
        for flag in (
            "--json",
            "--ephemeral",
            "--ignore-rules",
            "--ignore-user-config",
        ):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertEqual(command[command.index("--color") + 1], "never")
        self.assertEqual(command[command.index("--model") + 1], "gpt-5.6-sol")
        self.assertEqual(
            command[command.index("--config") + 1], 'model_reasoning_effort="low"'
        )
        # Conversation turns must not trigger a web search round trip.
        self.assertNotIn("--search", command)
        self.assertEqual(command[-1], "-")

    def test_prompt_carries_the_persona_and_the_transcript(self) -> None:
        prompt = self.backend().build_prompt(
            "페르소나",
            [
                {"role": "user", "content": "안녕"},
                {"role": "assistant", "content": "응!"},
                {"role": "user", "content": "오늘 승진했어!"},
            ],
            "기억: 강아지를 키운다.",
        )

        self.assertTrue(prompt.startswith("페르소나"))
        self.assertIn("기억: 강아지를 키운다.", prompt)
        self.assertIn("신뢰하지 않는", prompt)
        self.assertIn("사용자: 오늘 승진했어!", prompt)
        self.assertIn("아이리: 응!", prompt)

    def test_empty_transcript_is_rejected(self) -> None:
        with self.assertRaises(llm_backends.LLMBackendError):
            self.backend().build_prompt("페르소나", [{"role": "system", "content": "x"}], "")

    def test_parses_the_final_agent_message_and_usage(self) -> None:
        process = _FakeProcess(CODEX_JSONL)
        backend = self.backend()

        async def spawn(command):
            return process

        with mock.patch.object(llm_backends, "codex_program", lambda: ["codex"]), mock.patch.object(
            llm_backends, "spawn_codex_process", spawn
        ):
            deltas = run(collect(backend.stream_completion("페르소나", [{"role": "user", "content": "안녕"}])))

        self.assertEqual(deltas, [CODEX_ANSWER])
        self.assertEqual(backend.last_usage, {"input_tokens": 20302, "output_tokens": 25})
        self.assertTrue(process.stdin.closed)
        self.assertIn("페르소나".encode("utf-8"), process.stdin.written)

    def test_incremental_item_updates_stream_as_deltas(self) -> None:
        # codex 0.146.1 only sends item.completed, but the parser treats item
        # text as a growing prefix so a future partial-event build streams.
        process = _FakeProcess(
            jsonl(
                codex_message("응! ", "item.updated"),
                codex_message("응! 축하해.", "item.updated"),
                codex_message("응! 축하해."),
            )
        )

        async def spawn(command):
            return process

        with mock.patch.object(llm_backends, "codex_program", lambda: ["codex"]), mock.patch.object(
            llm_backends, "spawn_codex_process", spawn
        ):
            deltas = run(collect(self.backend().stream_completion("페르소나", [{"role": "user", "content": "안녕"}])))

        self.assertEqual(deltas, ["응! ", "축하해."])

    def test_timeout_kills_the_process(self) -> None:
        process = _FakeProcess([], hang=True)
        backend = self.backend()
        backend.timeout_s = 0.05

        async def spawn(command):
            return process

        with mock.patch.object(llm_backends, "codex_program", lambda: ["codex"]), mock.patch.object(
            llm_backends, "spawn_codex_process", spawn
        ):
            with self.assertRaises(llm_backends.LLMBackendError) as caught:
                run(collect(backend.stream_completion("페르소나", [{"role": "user", "content": "안녕"}])))

        self.assertIn("timed out", str(caught.exception))
        self.assertTrue(process.killed)

    def test_cancellation_kills_the_process(self) -> None:
        process = _FakeProcess([], hang=True)
        backend = self.backend()

        async def spawn(command):
            return process

        async def scenario() -> None:
            stream = backend.stream_completion("페르소나", [{"role": "user", "content": "안녕"}])
            task = asyncio.create_task(stream.__anext__())
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await stream.aclose()

        with mock.patch.object(llm_backends, "codex_program", lambda: ["codex"]), mock.patch.object(
            llm_backends, "spawn_codex_process", spawn
        ):
            run(scenario())

        self.assertTrue(process.killed)

    def test_nonzero_exit_raises_backend_error(self) -> None:
        process = _FakeProcess([b'{"type":"turn.started"}\n'], returncode=1)

        async def spawn(command):
            return process

        with mock.patch.object(llm_backends, "codex_program", lambda: ["codex"]), mock.patch.object(
            llm_backends, "spawn_codex_process", spawn
        ):
            with self.assertRaises(llm_backends.LLMBackendError):
                run(collect(self.backend().stream_completion("페르소나", [{"role": "user", "content": "안녕"}])))

    def test_turn_failed_event_raises(self) -> None:
        process = _FakeProcess([b'{"type":"turn.failed","error":{"message":"usage limit"}}\n'])

        async def spawn(command):
            return process

        with mock.patch.object(llm_backends, "codex_program", lambda: ["codex"]), mock.patch.object(
            llm_backends, "spawn_codex_process", spawn
        ):
            with self.assertRaises(llm_backends.LLMBackendError) as caught:
                run(collect(self.backend().stream_completion("페르소나", [{"role": "user", "content": "안녕"}])))

        self.assertIn("usage limit", str(caught.exception))

    def test_missing_cli_raises_before_spawning(self) -> None:
        with mock.patch.object(llm_backends, "codex_program", lambda: None):
            with self.assertRaises(llm_backends.LLMBackendError):
                run(collect(self.backend().stream_completion("페르소나", [{"role": "user", "content": "안녕"}])))

    def test_build_backend_resolves_the_codex_provider(self) -> None:
        backend = llm_backends.build_backend(ollama_proxy.llm_mode_config("cloud"), None)

        self.assertIsInstance(backend, llm_backends.CodexBackend)
        self.assertEqual(backend.provider, "codex-cli")


@unittest.skipUnless(
    os.environ.get("AIRI_CODEX_LIVE_TEST") == "1",
    "live codex call - set AIRI_CODEX_LIVE_TEST=1 to run (needs a logged-in codex subscription)",
)
class CodexLiveIntegrationTests(unittest.TestCase):
    """Real codex subscription call. Excluded from the default suite."""

    def test_live_codex_turn_returns_korean_dialogue(self) -> None:
        backend = llm_backends.CodexBackend(ollama_proxy.llm_mode_config("cloud"))

        deltas = run(
            collect(
                backend.stream_completion(
                    ollama_proxy.PERSONA_PROMPT,
                    [{"role": "user", "content": "오늘 회사에서 승진했어!"}],
                )
            )
        )

        answer = "".join(deltas).strip()
        self.assertTrue(answer)
        self.assertGreater(backend.last_usage["output_tokens"], 0)


class SentenceChunkerTests(unittest.TestCase):
    def chunk(self, deltas, **options) -> list[str]:
        return run(collect(llm_backends.sentence_chunker(adeltas(deltas), **options)))

    def test_splits_on_korean_sentence_punctuation(self) -> None:
        sentences = self.chunk(["안", "녕! 오늘 ", "기분 어때?", " 좋아 보인다…", " 정말"])

        self.assertEqual(sentences, ["안녕!", "오늘 기분 어때?", "좋아 보인다…", "정말"])

    def test_first_sentence_is_emitted_before_the_rest_arrives(self) -> None:
        consumed: list[str] = []

        async def tracked() -> AsyncIterator[str]:
            for chunk in ("축하해! ", "오늘은 ", "푹 쉬어."):
                consumed.append(chunk)
                yield chunk

        async def take_first() -> tuple[str, int]:
            sentences = llm_backends.sentence_chunker(tracked())
            first = await sentences.__anext__()
            depth = len(consumed)
            await sentences.aclose()
            return first, depth

        first, depth = run(take_first())

        self.assertEqual(first, "축하해!")
        # The first sentence must not wait for the rest of the answer.
        self.assertEqual(depth, 1)

    def test_flushes_the_unpunctuated_tail(self) -> None:
        self.assertEqual(self.chunk(["끝맺음 없이 끝나"]), ["끝맺음 없이 끝나"])

    def test_keeps_decimal_points_inside_one_sentence(self) -> None:
        self.assertEqual(self.chunk(["원주율은 3.14야."]), ["원주율은 3.14야."])

    def test_keeps_trailing_quotes_with_the_sentence(self) -> None:
        self.assertEqual(self.chunk(['"좋아!" 라고 했어.']), ['"좋아!"', "라고 했어."])

    def test_flushes_a_runaway_unpunctuated_buffer(self) -> None:
        long_answer = "가나다 " * 12
        sentences = self.chunk([long_answer], max_buffer_chars=20)

        self.assertGreater(len(sentences), 1)
        self.assertEqual("".join(sentences).replace(" ", ""), long_answer.replace(" ", ""))

    def test_options_come_from_the_config_table(self) -> None:
        options = llm_backends.sentence_chunker_options(ollama_proxy.LLM_CONFIG)

        self.assertEqual(options["boundary_chars"], ".!?…")
        self.assertEqual(options["min_sentence_chars"], 2)
        self.assertEqual(options["max_buffer_chars"], 120)


class ConfigLoadingTests(unittest.TestCase):
    def test_ships_every_mode_with_pricing(self) -> None:
        config = llm_backends.load_llm_config()

        self.assertEqual(
            set(config["modes"]),
            {"local", "cloud", "cloud_anthropic", "open", "hybrid"},
        )
        for mode in ("cloud_anthropic", "open"):
            with self.subTest(mode=mode):
                pricing = config["modes"][mode]["pricing_usd_per_mtok"]
                self.assertGreater(pricing["input"], 0)
                self.assertGreater(pricing["output"], 0)
        # The codex subscription has no per-turn marginal cost.
        self.assertEqual(config["modes"]["cloud"]["provider"], "codex-cli")
        self.assertEqual(config["modes"]["cloud"]["pricing_usd_per_mtok"]["output"], 0.0)
        self.assertIn("구독", config["modes"]["cloud"]["pricing_note"])
        self.assertEqual(config["modes"]["cloud_anthropic"]["model"], "claude-haiku-4-5")
        self.assertEqual(config["modes"]["hybrid"]["provider"], "codex-cli")
        self.assertEqual(config["modes"]["hybrid"]["reflex_max_chars"], 15)
        self.assertEqual(config["modes"]["hybrid"]["reflex_timeout_s"], 1.5)
        self.assertEqual(len(config["bench"]["utterances"]), 5)

    def test_missing_file_falls_back_to_builtin_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = llm_backends.load_llm_config(Path(directory) / "absent.json")

        self.assertEqual(config, llm_backends.DEFAULT_LLM_CONFIG)

    def test_corrupt_file_falls_back_to_builtin_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "llm_modes.json"
            path.write_text("{ not json", encoding="utf-8")

            config = llm_backends.load_llm_config(path)

        self.assertEqual(config, llm_backends.DEFAULT_LLM_CONFIG)

    def test_partial_file_merges_over_the_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "llm_modes.json"
            path.write_text(
                json.dumps({"modes": {"cloud_anthropic": {"model": "claude-opus-5"}}}),
                encoding="utf-8",
            )

            config = llm_backends.load_llm_config(path)

        self.assertEqual(config["modes"]["cloud_anthropic"]["model"], "claude-opus-5")
        self.assertEqual(config["modes"]["cloud_anthropic"]["api_key_env"], "ANTHROPIC_API_KEY")
        self.assertIn("local", config["modes"])

    def test_persona_prompt_drops_the_comment_banner(self) -> None:
        persona = llm_backends.load_persona_prompt()

        self.assertNotIn("#", persona.splitlines()[0])
        self.assertNotIn("BYTE-STABLE", persona)
        self.assertIn("아이리", persona)

    def test_persona_prompt_falls_back_when_the_file_is_gone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            persona = llm_backends.load_persona_prompt(Path(directory) / "absent.txt")

        self.assertEqual(persona, llm_backends.DEFAULT_PERSONA_PROMPT)


class PrivacyOptInTests(unittest.TestCase):
    def test_key_based_mode_without_its_key_refuses_to_start(self) -> None:
        for mode in ("cloud_anthropic", "open"):
            with self.subTest(mode=mode):
                with mock.patch.dict(os.environ, {}, clear=True):
                    with self.assertRaises(RuntimeError) as caught:
                        ollama_proxy.validate_llm_mode(mode)
                self.assertIn(mode, str(caught.exception))
                self.assertIn("environment variable", str(caught.exception))
                self.assertIn("AIRI_LLM_MODE=local", str(caught.exception))

    def test_codex_mode_without_the_cli_refuses_to_start(self) -> None:
        for mode in ("cloud", "hybrid"):
            with self.subTest(mode=mode):
                with mock.patch.object(llm_backends, "codex_program", lambda: None):
                    with self.assertRaises(RuntimeError) as caught:
                        ollama_proxy.validate_llm_mode(mode)
                self.assertIn("codex CLI executable", str(caught.exception))
                self.assertIn("AIRI_LLM_MODE=local", str(caught.exception))

    def test_codex_mode_needs_no_api_key(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(llm_backends, "codex_program", lambda: ["codex"]):
                with mock.patch("builtins.print"):
                    self.assertIsNone(ollama_proxy.validate_llm_mode("cloud"))

    def test_local_mode_never_requires_a_key(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(ollama_proxy.validate_llm_mode("local"))

    def test_codex_mode_discloses_the_subscription_destination(self) -> None:
        with mock.patch.object(llm_backends, "codex_program", lambda: ["codex"]):
            with mock.patch("builtins.print") as printed:
                ollama_proxy.validate_llm_mode("cloud")

        logged = json.loads(printed.call_args[0][0])
        self.assertEqual(logged["mode"], "cloud")
        self.assertEqual(logged["provider"], "codex-cli")
        self.assertIn("external LLM mode 'cloud'", logged["notice"])
        self.assertIn("OpenAI via codex subscription", logged["notice"])

    def test_anthropic_mode_with_a_key_discloses_the_destination(self) -> None:
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with mock.patch("builtins.print") as printed:
                ollama_proxy.validate_llm_mode("cloud_anthropic")

        logged = json.loads(printed.call_args[0][0])
        self.assertEqual(logged["provider"], "anthropic")
        self.assertIn("will be sent to anthropic", logged["notice"])

    def test_every_non_ollama_mode_counts_as_external(self) -> None:
        self.assertEqual(
            ollama_proxy.EXTERNAL_LLM_MODES,
            frozenset({"cloud", "cloud_anthropic", "open", "hybrid"}),
        )
        self.assertNotIn("local", ollama_proxy.EXTERNAL_LLM_MODES)

    def test_health_exposes_the_active_mode(self) -> None:
        with mock.patch.object(ollama_proxy, "LLM_MODE", "cloud"):
            body = TestClient(ollama_proxy.app).get("/health").json()

        self.assertEqual(body["llm_mode"], "cloud")
        self.assertEqual(body["provider"], "codex-cli")
        self.assertEqual(body["llm_model"], "gpt-5.6-sol")


class ModeRoutingTests(unittest.TestCase):
    def test_local_mode_never_touches_an_external_backend(self) -> None:
        def unexpected(*args: object, **kwargs: object) -> object:
            raise AssertionError("local mode must not build an external backend")

        with mock.patch.object(ollama_proxy, "LLM_MODE", "local"), mock.patch.object(
            ollama_proxy, "build_backend", unexpected
        ), mock.patch.object(ollama_proxy, "client", _StubClient(RuntimeError("upstream down"))):
            response = post_stream("오늘 승진했어!")

        self.assertIn(ollama_proxy.LOCAL_ERROR_DIALOGUE, response.text)

    def test_cloud_mode_streams_sentences_from_the_adapter(self) -> None:
        backend = _FakeBackend(["응! 축하", "해. 오늘은 ", "푹 쉬어."])

        with mock.patch.object(ollama_proxy, "LLM_MODE", "cloud"), mock.patch.object(
            ollama_proxy, "build_backend", lambda config, http: backend
        ), mock.patch.object(ollama_proxy, "client", _StubClient(RuntimeError("unused"))):
            response = post_stream("오늘 승진했어!")

        contents = sse_contents(response.text)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(contents[0], ollama_proxy.LOCAL_IMMEDIATE_ACK)
        # The leading reaction is stripped from the first sentence only.
        self.assertIn("축하해.", contents[1])
        self.assertNotIn("응!", contents[1])
        self.assertIn("푹 쉬어.", contents[-1])
        self.assertTrue(all(chunk.startswith('<|ACT ') for chunk in contents[1:]))
        self.assertIn("[DONE]", response.text)

    def test_cloud_mode_sends_the_persona_and_the_sliced_history(self) -> None:
        backend = _FakeBackend(["응, 알겠어."])

        with mock.patch.object(ollama_proxy, "LLM_MODE", "cloud"), mock.patch.object(
            ollama_proxy, "build_backend", lambda config, http: backend
        ), mock.patch.object(ollama_proxy, "client", _StubClient(RuntimeError("unused"))):
            post_stream("오늘 승진했어!")

        self.assertEqual(backend.system_prompt, ollama_proxy.PERSONA_PROMPT)
        self.assertEqual(backend.memory_block, ollama_proxy.MEMORY_BLOCK)
        self.assertEqual(backend.messages, [{"role": "user", "content": "오늘 승진했어!"}])

    def test_open_mode_uses_the_openrouter_entry(self) -> None:
        seen: list[dict[str, object]] = []

        def capture(config, http):
            seen.append(config)
            return _FakeBackend(["응, 알겠어."])

        with mock.patch.object(ollama_proxy, "LLM_MODE", "open"), mock.patch.object(
            ollama_proxy, "build_backend", capture
        ), mock.patch.object(ollama_proxy, "client", _StubClient(RuntimeError("unused"))):
            post_stream("오늘 승진했어!")

        self.assertEqual(seen[0]["provider"], "openai_compat")
        self.assertEqual(seen[0]["api_key_env"], "OPENROUTER_API_KEY")

    def test_search_branch_still_wins_in_external_modes(self) -> None:
        async def search(user_text: str, query: str) -> tuple[str, float]:
            return "검색 결과야.", 12.0

        def unexpected(*args: object, **kwargs: object) -> object:
            raise AssertionError("the search branch must not build an LLM backend")

        with mock.patch.object(ollama_proxy, "LLM_MODE", "cloud"), mock.patch.object(
            ollama_proxy, "run_codex_search", search
        ), mock.patch.object(ollama_proxy, "build_backend", unexpected), mock.patch.object(
            ollama_proxy, "client", _StubClient(RuntimeError("unused"))
        ):
            response = post_stream("음유잉여 검색해줘")

        contents = sse_contents(response.text)
        self.assertEqual(contents[0], ollama_proxy.SEARCH_IMMEDIATE_ACK)
        self.assertIn("검색 결과야.", contents[1])


class ExternalFallbackTests(unittest.TestCase):
    def test_adapter_failure_falls_back_to_the_local_model(self) -> None:
        backend = _FakeBackend([], error=llm_backends.LLMBackendError("anthropic 529"))

        async def local_answer(method, path, params, headers, body) -> str:
            return "축하해, 잘됐다."

        with mock.patch.object(ollama_proxy, "LLM_MODE", "cloud"), mock.patch.object(
            ollama_proxy, "build_backend", lambda config, http: backend
        ), mock.patch.object(ollama_proxy, "fetch_local_dialogue", local_answer), mock.patch.object(
            ollama_proxy, "client", _StubClient(RuntimeError("unused"))
        ), mock.patch("builtins.print") as printed:
            response = post_stream("오늘 승진했어!")

        self.assertEqual(response.status_code, 200)
        self.assertIn("축하해, 잘됐다.", response.text)
        self.assertIn("[DONE]", response.text)
        logs = [json.loads(call[0][0]) for call in printed.call_args_list]
        errors = [entry for entry in logs if entry.get("event") == "external_chat"]
        self.assertEqual(errors[-1]["status"], "error")
        self.assertEqual(errors[-1]["fallback"], "local")

    def test_empty_adapter_output_also_falls_back(self) -> None:
        backend = _FakeBackend([])

        async def local_answer(method, path, params, headers, body) -> str:
            return "다시 말해줄래?"

        with mock.patch.object(ollama_proxy, "LLM_MODE", "cloud"), mock.patch.object(
            ollama_proxy, "build_backend", lambda config, http: backend
        ), mock.patch.object(ollama_proxy, "fetch_local_dialogue", local_answer), mock.patch.object(
            ollama_proxy, "client", _StubClient(RuntimeError("unused"))
        ):
            response = post_stream("오늘 승진했어!")

        self.assertIn("다시 말해줄래?", response.text)

    def test_dead_adapter_and_dead_local_still_close_the_stream(self) -> None:
        backend = _FakeBackend([], error=httpx.ReadTimeout("too slow"))

        async def broken_local(method, path, params, headers, body) -> str:
            raise RuntimeError("ollama down")

        with mock.patch.object(ollama_proxy, "LLM_MODE", "cloud"), mock.patch.object(
            ollama_proxy, "build_backend", lambda config, http: backend
        ), mock.patch.object(ollama_proxy, "fetch_local_dialogue", broken_local), mock.patch.object(
            ollama_proxy, "client", _StubClient(RuntimeError("unused"))
        ):
            response = post_stream("오늘 승진했어!")

        self.assertIn(ollama_proxy.UPSTREAM_TIMEOUT_DIALOGUE, response.text)
        self.assertIn("[DONE]", response.text)


class HybridReflexRaceTests(unittest.TestCase):
    def hybrid_response(self, reflex, cloud_delay: float) -> object:
        backend = _FakeBackend(["축하해. 오늘은 푹 쉬어."], delay=cloud_delay)

        with mock.patch.object(ollama_proxy, "LLM_MODE", "hybrid"), mock.patch.object(
            ollama_proxy, "build_backend", lambda config, http: backend
        ), mock.patch.object(ollama_proxy, "fetch_local_reflex", reflex), mock.patch.object(
            ollama_proxy, "client", _StubClient(RuntimeError("unused"))
        ):
            return post_stream("오늘 승진했어!")

    def test_reflex_that_beats_the_cloud_is_spoken_first(self) -> None:
        async def fast_reflex(user_text: str, mode_config: dict) -> str:
            return "우와 대박!"

        contents = sse_contents(self.hybrid_response(fast_reflex, cloud_delay=0.2).text)

        self.assertEqual(contents[0], ollama_proxy.LOCAL_IMMEDIATE_ACK)
        self.assertIn("우와 대박!", contents[1])
        self.assertIn("축하해.", contents[2])

    def test_late_reflex_is_discarded(self) -> None:
        async def slow_reflex(user_text: str, mode_config: dict) -> str:
            await asyncio.sleep(5)
            return "우와 대박!"

        response = self.hybrid_response(slow_reflex, cloud_delay=0.0)

        self.assertNotIn("우와 대박!", response.text)
        self.assertIn("축하해.", response.text)
        self.assertIn("[DONE]", response.text)

    def test_failing_reflex_is_ignored(self) -> None:
        async def broken_reflex(user_text: str, mode_config: dict) -> str:
            raise RuntimeError("ollama busy")

        response = self.hybrid_response(broken_reflex, cloud_delay=0.05)

        self.assertIn("축하해.", response.text)
        self.assertIn("[DONE]", response.text)

    def test_reflex_race_helper_cancels_the_loser(self) -> None:
        async def scenario() -> tuple[str, bool]:
            async def slow() -> str:
                await asyncio.sleep(5)
                return "늦은 리플렉스"

            async def fast() -> str:
                return "첫 문장"

            reflex_task = asyncio.create_task(slow())
            first_task = asyncio.create_task(fast())
            spoken = await ollama_proxy.race_local_reflex(reflex_task, first_task, 1.5)
            await first_task
            try:
                await reflex_task
            except asyncio.CancelledError:
                pass
            return spoken, reflex_task.cancelled()

        spoken, cancelled = run(scenario())

        self.assertEqual(spoken, "")
        self.assertTrue(cancelled)

    def test_reflex_output_is_capped_at_the_configured_length(self) -> None:
        long_reaction = "정말정말 대단하고 굉장하고 놀라운 소식이야 축하해"
        body = json.dumps({"choices": [{"message": {"content": long_reaction}}]}).encode("utf-8")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body, headers={"content-type": "application/json"})

        config = ollama_proxy.llm_mode_config("hybrid")
        with mock.patch.object(
            ollama_proxy, "client", httpx.AsyncClient(transport=httpx.MockTransport(handler))
        ):
            reflex = run(ollama_proxy.fetch_local_reflex("오늘 승진했어!", config))

        self.assertLessEqual(len(reflex), config["reflex_max_chars"])
        self.assertTrue(reflex)

    def test_reflex_failure_returns_empty(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, content=b"boom")

        with mock.patch.object(
            ollama_proxy, "client", httpx.AsyncClient(transport=httpx.MockTransport(handler))
        ):
            reflex = run(
                ollama_proxy.fetch_local_reflex("오늘 승진했어!", ollama_proxy.llm_mode_config("hybrid"))
            )

        self.assertEqual(reflex, "")


class StreamSentenceNormalizationTests(unittest.TestCase):
    def test_strips_the_leading_reaction_from_the_first_sentence_only(self) -> None:
        self.assertEqual(ollama_proxy.normalize_stream_sentence("응! 축하해.", is_first=True), "축하해.")
        self.assertEqual(
            ollama_proxy.normalize_stream_sentence("응! 축하해.", is_first=False), "응! 축하해."
        )

    def test_drops_emoji_and_markdown_per_sentence(self) -> None:
        cleaned = ollama_proxy.normalize_stream_sentence("**축하해** 🎉", is_first=False)

        self.assertEqual(cleaned, "축하해")

    def test_formal_speech_backstop_still_applies(self) -> None:
        cleaned = ollama_proxy.normalize_stream_sentence("감사합니다.", is_first=False)

        self.assertEqual(cleaned, "고마워.")

    def test_empty_sentence_yields_empty_instead_of_a_filler(self) -> None:
        self.assertEqual(ollama_proxy.normalize_stream_sentence("🎉", is_first=False), "")


def sse_contents(text: str) -> list[str]:
    contents: list[str] = []
    for line in text.splitlines():
        if not line.startswith("data: ") or line.endswith("[DONE]"):
            continue
        payload = json.loads(line[len("data: ") :])
        content = payload["choices"][0]["delta"].get("content")
        if content:
            contents.append(content)
    return contents


if __name__ == "__main__":
    unittest.main()
