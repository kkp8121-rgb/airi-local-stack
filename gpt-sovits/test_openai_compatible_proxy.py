import ast
import asyncio
import re
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi.testclient import TestClient

import openai_compatible_proxy as proxy

OLLAMA_PROXY = Path(__file__).resolve().parents[1] / "ollama-proxy" / "ollama_proxy.py"
SENTENCE_RE = re.compile(r"[^\s][^.!?]*[.!?]")


def assert_leaked_lock_released(test):
    """Fail on a leaked engine lock without deadlocking every later test."""
    leaked = proxy.TTS_LOCK.locked()
    if leaked:
        proxy.TTS_LOCK.release()
    test.assertFalse(leaked, "TTS_LOCK was left acquired")


class FakeBackendResponse:
    """Stand-in for a streaming requests.Response from GPT-SoVITS api_v2."""

    def __init__(self, status_code=200, chunks=(), text="", error=None):
        self.status_code = status_code
        self.text = text
        self.closed = False
        self._chunks = list(chunks)
        self._error = error
        self.chunks_read = 0

    def iter_content(self, chunk_size):
        for chunk in self._chunks:
            self.chunks_read += 1
            yield chunk
        if self._error is not None:
            raise self._error

    def close(self):
        self.closed = True


class ImmediateResponseCacheTests(unittest.TestCase):
    def setUp(self):
        self.cache = dict(proxy._WAV_CACHE)
        self.status = dict(proxy._WAV_CACHE_STATUS)

    def tearDown(self):
        with proxy._WAV_CACHE_LOCK:
            proxy._WAV_CACHE.clear(); proxy._WAV_CACHE.update(self.cache)
            proxy._WAV_CACHE_STATUS.clear(); proxy._WAV_CACHE_STATUS.update(self.status)

    def test_cache_only_matches_wav_default_speed_and_known_phrase(self):
        with proxy._WAV_CACHE_LOCK:
            proxy._WAV_CACHE["응!"] = b"RIFFcached"
        self.assertEqual(proxy.cached_wav_for_request("응!", "wav", 1.0), b"RIFFcached")
        self.assertIsNone(proxy.cached_wav_for_request("응!", "pcm", 1.0))
        self.assertIsNone(proxy.cached_wav_for_request("응!", "wav", 1.1))
        self.assertIsNone(proxy.cached_wav_for_request("다른 사용자 문장", "wav", 1.0))

    def test_warmup_keeps_success_and_marks_failure_for_safe_fallback(self):
        original = proxy._fetch_wav_from_backend
        calls = []
        def fake_fetch(payload):
            calls.append(payload["text"])
            if payload["text"] == "응!": return b"RIFFok"
            raise RuntimeError("backend unavailable")
        try:
            proxy._fetch_wav_from_backend = fake_fetch
            proxy.warm_immediate_response_cache()
        finally:
            proxy._fetch_wav_from_backend = original
        self.assertEqual(proxy.cached_wav_for_request("응!", "wav", 1.0), b"RIFFok")
        self.assertEqual(proxy.cache_health()["states"]["바로 찾아볼게."], "failed")
        self.assertEqual(calls, list(proxy.IMMEDIATE_RESPONSE_TEXTS))

    def test_payload_preserves_existing_generation_options(self):
        payload = proxy.build_backend_payload("응!", 1.25)
        self.assertEqual(payload["text_lang"], "ko")
        self.assertEqual(payload["speed_factor"], 1.25)
        self.assertFalse(payload["parallel_infer"])


class ProxyEndpointTestCase(unittest.TestCase):
    """Shared harness: a mocked backend plus captured latency telemetry."""

    def setUp(self):
        self.client = TestClient(proxy.app)
        self.events = []
        patcher = mock.patch.object(
            proxy,
            "emit_latency_event",
            lambda source, phase, trace, **kwargs: self.events.append((source, phase, kwargs)),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        # Every request path must hand the engine lock back, or the next
        # sentence would block forever. Release a leaked lock before failing so
        # one broken test reports a failure instead of hanging the whole suite.
        assert_leaked_lock_released(self)

    def post_speech(self, **overrides):
        body = {"model": "tts-1-ko", "input": "안녕하세요.", "voice": "airi-vtuber", "response_format": "wav"}
        body.update(overrides)
        return self.client.post("/v1/audio/speech", json=body)

    def phases(self):
        return [phase for _, phase, _ in self.events]

    def meta_for(self, phase):
        return [kwargs.get("meta", {}) for _, event_phase, kwargs in self.events if event_phase == phase]


class BackendErrorPropagationTests(ProxyEndpointTestCase):
    def test_backend_error_status_becomes_502_instead_of_empty_200(self):
        backend = FakeBackendResponse(status_code=400, text="ref_audio_path is required")
        with mock.patch.object(proxy.HTTP, "post", return_value=backend):
            response = self.post_speech()
        self.assertEqual(response.status_code, 502)
        self.assertIn("400", response.json()["error"]["message"])
        self.assertTrue(backend.closed)
        self.assertIn("error", self.phases())

    def test_unreachable_backend_becomes_502(self):
        import requests
        with mock.patch.object(proxy.HTTP, "post", side_effect=requests.ConnectionError("refused")):
            response = self.post_speech()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["type"], "gpt_sovits_backend_error")

    def test_successful_backend_streams_body(self):
        audio = b"RIFF" + b"\x00" * 40 + b"\x11\x22" * 4096
        backend = FakeBackendResponse(chunks=[audio[:2048], audio[2048:]])
        with mock.patch.object(proxy.HTTP, "post", return_value=backend):
            response = self.post_speech()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, audio)
        self.assertTrue(backend.closed)
        self.assertEqual(self.phases(), ["start", "first", "end"])

    def test_streaming_path_uses_the_lock_releasing_response(self):
        # The lock-releasing response class is only useful if the handler
        # actually returns it, so pin the wiring here.
        backend = FakeBackendResponse(chunks=[b"RIFF" + b"\x00" * 40, b"\x01\x02" * 4096])
        http_request = SimpleNamespace(headers={})
        with mock.patch.object(proxy.HTTP, "post", return_value=backend):
            response = proxy.speech(proxy.SpeechRequest(input="안녕하세요."), http_request)
            self.assertIsInstance(response, proxy._EngineStreamingResponse)
            self.assertTrue(proxy.TTS_LOCK.locked(), "handler must hold the lock across the stream")
            loop = asyncio.new_event_loop()
            try:
                # Starlette wrapped the sync generator into an async one.
                async def drain():
                    return b"".join([chunk async for chunk in response.body_iterator])
                self.assertEqual(len(loop.run_until_complete(drain())), 44 + 8192)
            finally:
                loop.close()
        self.assertTrue(backend.closed)

    def test_header_only_success_is_recorded_as_an_error(self):
        backend = FakeBackendResponse(chunks=[b"RIFF" + b"\x00" * 40])
        with mock.patch.object(proxy.HTTP, "post", return_value=backend):
            response = self.post_speech()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("end", self.phases())
        self.assertEqual(self.meta_for("error")[-1]["empty_body"], 1)

    def test_backend_cut_midstream_reports_an_error(self):
        import requests
        backend = FakeBackendResponse(
            chunks=[b"RIFF" + b"\x00" * 40, b"\x01\x02" * 4096],
            error=requests.ConnectionError("backend closed the socket"),
        )
        with mock.patch.object(proxy.HTTP, "post", return_value=backend):
            with self.assertRaises(Exception):
                self.post_speech()
        self.assertTrue(backend.closed)
        self.assertEqual(self.meta_for("error")[-1]["backend_truncated"], 1)


class StreamCancellationTests(unittest.TestCase):
    """A client that hangs up must stop the backend generation (F11)."""

    def setUp(self):
        self.events = []
        patcher = mock.patch.object(
            proxy,
            "emit_latency_event",
            lambda source, phase, trace, **kwargs: self.events.append((source, phase, kwargs)),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        assert_leaked_lock_released(self)

    def test_client_disconnect_closes_backend_and_frees_the_lock(self):
        backend = FakeBackendResponse(chunks=[b"RIFF" + b"\x00" * 40, b"\x01\x02" * 4096, b"\x03\x04" * 4096])
        proxy.TTS_LOCK.acquire()
        stream = proxy._BackendStream(backend, 12.0)
        generator = proxy._stream_backend(stream, "trace-cancel", 0.0)
        self.assertTrue(next(generator))
        self.assertTrue(proxy.TTS_LOCK.locked())
        generator.close()  # what uvicorn does when AIRI drops the connection
        self.assertTrue(backend.closed, "backend response was left open after cancellation")
        self.assertFalse(proxy.TTS_LOCK.locked(), "engine lock was held after cancellation")
        self.assertLess(backend.chunks_read, 3, "backend kept generating after cancellation")
        cancelled = [kwargs["meta"] for _, phase, kwargs in self.events if kwargs.get("meta", {}).get("client_cancelled")]
        self.assertEqual(len(cancelled), 1)
        self.assertEqual(cancelled[0]["bytes"], 44)

    def test_client_disconnect_releases_the_lock_starlette_abandons_the_iterator(self):
        # Starlette never closes an abandoned body iterator, so the response
        # object itself has to free the engine lock. Without this the next
        # sentence waits for a garbage collection that may never come.
        backend = FakeBackendResponse(chunks=[b"RIFF" + b"\x00" * 40, b"\x01\x02" * 4096, b"\x03\x04" * 4096])
        proxy.TTS_LOCK.acquire()
        stream = proxy._BackendStream(backend, 0.0)
        response = proxy._EngineStreamingResponse(
            stream,
            proxy._stream_backend(stream, "trace-disconnect", 0.0),
            media_type="audio/wav",
        )

        async def receive():
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body":
                raise OSError("client went away")  # uvicorn's disconnect signal

        async def drive():
            with self.assertRaises(Exception):
                await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)

        # Deliberately not asyncio.run(): it calls shutdown_asyncgens() on exit,
        # which finalizes the abandoned iterator and hides the very leak this
        # test guards. uvicorn's loop outlives the request, so keep it open.
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(drive())
            self.assertFalse(proxy.TTS_LOCK.locked(), "engine lock survived a client disconnect")
            self.assertTrue(backend.closed, "backend generation was left running after a disconnect")
        finally:
            if proxy.TTS_LOCK.locked():
                proxy.TTS_LOCK.release()
            loop.close()

    def test_release_is_idempotent_and_never_double_releases_the_lock(self):
        backend = FakeBackendResponse()
        proxy.TTS_LOCK.acquire()
        stream = proxy._BackendStream(backend, 0.0)
        stream.release()
        stream.release()
        self.assertFalse(proxy.TTS_LOCK.locked())

    def test_open_backend_stream_serializes_generations(self):
        backend = FakeBackendResponse(chunks=[b"RIFF"])
        with mock.patch.object(proxy.HTTP, "post", return_value=backend):
            stream = proxy.open_backend_stream(proxy.build_backend_payload("응!"))
            self.assertTrue(proxy.TTS_LOCK.locked())
            blocked = threading.Event()
            def second_request():
                second = proxy.open_backend_stream(proxy.build_backend_payload("응!"))
                blocked.set()
                second.release()
            worker = threading.Thread(target=second_request, daemon=True)
            worker.start()
            self.assertFalse(blocked.wait(0.2), "a second generation started while one was in flight")
            stream.release()
            self.assertTrue(blocked.wait(2))
            worker.join(2)
        self.assertFalse(proxy.TTS_LOCK.locked())


class RequestContractTests(ProxyEndpointTestCase):
    def test_pcm_is_rejected_instead_of_receiving_wav_bytes(self):
        response = self.post_speech(response_format="pcm")
        self.assertEqual(response.status_code, 400)
        self.assertIn("wav", response.json()["detail"])

    def test_input_longer_than_the_limit_is_rejected(self):
        response = self.post_speech(input="가" * (proxy.MAX_INPUT_CHARS + 1))
        self.assertEqual(response.status_code, 400)
        self.assertIn(str(proxy.MAX_INPUT_CHARS), response.json()["detail"])

    def test_input_at_the_limit_is_accepted(self):
        backend = FakeBackendResponse(chunks=[b"RIFF" + b"\x00" * 40, b"\x01\x02" * 4096])
        with mock.patch.object(proxy.HTTP, "post", return_value=backend):
            response = self.post_speech(input="가" * proxy.MAX_INPUT_CHARS)
        self.assertEqual(response.status_code, 200)

    def test_empty_input_is_rejected(self):
        response = self.post_speech(input="   ")
        self.assertEqual(response.status_code, 400)


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(proxy.app)

    def health(self, reference_path):
        backend = mock.Mock(status_code=200)
        with mock.patch.object(proxy, "REFERENCE_AUDIO", str(reference_path)):
            with mock.patch.object(proxy.HTTP, "get", return_value=backend):
                return self.client.get("/health").json()

    def test_missing_reference_audio_degrades_health(self):
        body = self.health(Path(__file__).parent / "no-such-reference.wav")
        self.assertFalse(body["reference_audio_found"])
        self.assertEqual(body["status"], "degraded")

    def test_present_reference_audio_reports_ok(self):
        body = self.health(Path(__file__))
        self.assertTrue(body["reference_audio_found"])
        self.assertEqual(body["status"], "ok")

    def test_default_reference_audio_lives_inside_the_repository(self):
        self.assertEqual(
            proxy.DEFAULT_REFERENCE_AUDIO,
            proxy.PROJECT_ROOT / "chatterbox" / "voices" / "airi-reference.wav",
        )


class AcknowledgementContractTests(unittest.TestCase):
    """The cached phrases only pay off if ollama_proxy still emits exactly them."""

    @staticmethod
    def module_literals(path):
        """Read constants as source text: ollama_proxy pulls in heavy imports."""
        module = ast.parse(path.read_text(encoding="utf-8"))
        literals = {}
        for node in module.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            value = node.value
            if isinstance(value, ast.Call):  # re.compile(pattern, flags)
                if not value.args:
                    continue
                value = value.args[0]
            try:
                literals[target.id] = ast.literal_eval(value)
            except ValueError:
                continue
        return literals

    def test_immediate_ack_sentences_match_the_cached_phrases(self):
        literals = self.module_literals(OLLAMA_PROXY)
        control_token = re.compile(literals["CONTROL_TOKEN_RE"], re.DOTALL)
        spoken = set()
        for name in ("LOCAL_IMMEDIATE_ACK", "SEARCH_IMMEDIATE_ACK"):
            self.assertIn(name, literals, f"{name} disappeared from ollama_proxy.py")
            sentence_source = control_token.sub("", literals[name]).strip()
            sentences = [match.strip() for match in SENTENCE_RE.findall(sentence_source)]
            self.assertTrue(sentences, f"{name} produced no spoken sentence")
            spoken.update(sentences)
        self.assertEqual(
            spoken,
            set(proxy.IMMEDIATE_RESPONSE_TEXTS),
            "ollama_proxy acknowledgements drifted from IMMEDIATE_RESPONSE_TEXTS, "
            "so every acknowledgement would miss the preloaded WAV cache",
        )


if __name__ == "__main__":
    unittest.main()
