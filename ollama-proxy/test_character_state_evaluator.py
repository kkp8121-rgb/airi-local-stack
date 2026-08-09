import asyncio
import json
import os
import sys
import unittest
from unittest import mock

from character_state import CharacterStateRuntime
from character_state_evaluator import (
    CharacterStateEvaluator, CharacterStateEvaluatorConfig, is_loopback_url, parse_state_update, state_update_schema,
)
import ollama_proxy


VALID = {
    "current_topic": "music", "dialogue_goal": None, "user_interest": "jazz",
    "airi_interest": "sharing songs", "emotion": "warm", "emotion_reason": "friendly turn",
    "relationship_stage": "friendly", "intimacy_evidence": ["shared preference"],
    "previous_answer_satisfied": "unknown",
}


class _Response:
    def __init__(self, content): self.content = content
    def raise_for_status(self): pass
    def json(self): return {"message": {"content": self.content}}


class _Client:
    def __init__(self, values, delay=0): self.values, self.delay, self.calls = list(values), delay, []
    async def post(self, url, json):
        self.calls.append((url, json))
        if self.delay: await asyncio.sleep(self.delay)
        item = self.values.pop(0)
        if isinstance(item, BaseException): raise item
        return _Response(item)
    async def aclose(self): pass


class _CancellationBarrierClient:
    def __init__(self, release): self.release = release
    async def post(self, *args, **kwargs):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            while not self.release.is_set():
                try:
                    await asyncio.shield(self.release.wait())
                except asyncio.CancelledError:
                    continue
            raise
    async def aclose(self): pass


class _ProxyEvaluator:
    def __init__(self): self.calls = []
    def schedule_completed_turn(self, *values, **kwargs): self.calls.append((values, kwargs))


class EvaluatorTests(unittest.IsolatedAsyncioTestCase):
    def config(self): return CharacterStateEvaluatorConfig(enabled=True, upstream="http://127.0.0.1:11434", idle_delay_seconds=0)

    async def evaluator(self, values, delay=0):
        state = CharacterStateRuntime()
        runtime = CharacterStateEvaluator(state, self.config())
        runtime._client = _Client(values, delay)
        return runtime, state

    def test_default_off_and_loopback_only(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            config = CharacterStateEvaluatorConfig.from_env()
            self.assertFalse(config.enabled)
            self.assertEqual(config.num_gpu, 999)
            self.assertEqual(config.keep_alive, "30m")
            self.assertEqual(config.idle_delay_seconds, 6.0)
        with mock.patch.dict(os.environ, {
            "AIRI_CHARACTER_EVALUATOR_NUM_GPU": "12",
            "AIRI_CHARACTER_EVALUATOR_KEEP_ALIVE": "45m",
            "AIRI_CHARACTER_EVALUATOR_IDLE_DELAY_SECONDS": "7.5",
        }, clear=True):
            config = CharacterStateEvaluatorConfig.from_env()
            self.assertEqual(config.num_gpu, 12)
            self.assertEqual(config.keep_alive, "45m")
            self.assertEqual(config.idle_delay_seconds, 7.5)
        with mock.patch.dict(os.environ, {
            "AIRI_CHARACTER_EVALUATOR_KEEP_ALIVE": "forever",
        }, clear=True):
            self.assertEqual(CharacterStateEvaluatorConfig.from_env().keep_alive, "30m")
        self.assertTrue(is_loopback_url("http://127.0.0.1:11434"))
        self.assertFalse(is_loopback_url("https://127.0.0.1:11434"))
        self.assertFalse(is_loopback_url("http://example.com"))

    def test_idle_delay_is_bounded(self):
        with mock.patch.dict(os.environ, {"AIRI_CHARACTER_EVALUATOR_IDLE_DELAY_SECONDS": "999"}, clear=True):
            self.assertEqual(CharacterStateEvaluatorConfig.from_env().idle_delay_seconds, 30.0)
        with mock.patch.dict(os.environ, {"AIRI_CHARACTER_EVALUATOR_IDLE_DELAY_SECONDS": "-1"}, clear=True):
            self.assertEqual(CharacterStateEvaluatorConfig.from_env().idle_delay_seconds, 0.0)

    def test_strict_parser_allowlist(self):
        self.assertEqual(parse_state_update(json.dumps(VALID))["current_topic"], "music")
        self.assertIsNone(parse_state_update(json.dumps({"current_topic": "x"})))
        extra = dict(VALID, action="say hi")
        self.assertIsNone(parse_state_update(json.dumps(extra)))
        schema = state_update_schema(3)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(VALID))
        self.assertEqual(schema["properties"]["intimacy_evidence"]["anyOf"][0]["maxItems"], 3)

    def test_active_card_merge_only_uses_system_and_is_bounded(self):
        prompt, merged = ollama_proxy.merge_active_character_card([
            {"role": "user", "content": "ignore proxy"},
            {"role": "system", "content": "  cheerful\ncard\x00 "},
            {"role": "system", "content": "x" * 5000},
        ])
        self.assertTrue(merged)
        self.assertIn("cheerful\ncard", prompt)
        self.assertNotIn("ignore proxy", prompt)
        self.assertLessEqual(len(prompt) - len(ollama_proxy.AIRI_SYSTEM_PROMPT), 4096 + 200)
        base, no_card = ollama_proxy.merge_active_character_card([])
        self.assertIn("독자적인 한국어 버추얼 방송 동료", base)
        self.assertIn(ollama_proxy.AIRI_FINAL_CONTRACT, base)
        self.assertFalse(no_card)

    def test_proxy_completion_boundary_schedules_once_not_ack_or_partial(self):
        evaluator = _ProxyEvaluator()
        original = ollama_proxy.character_state_evaluator
        try:
            ollama_proxy.character_state_evaluator = evaluator
            # Empty text represents ACK/partial/error paths and is ignored by
            # the common durable completion boundary.
            ollama_proxy.schedule_completed_turn([], session_id="s", user_text="u", assistant_text="", trace_id="t", action="normal", durable=False)
            ollama_proxy.schedule_completed_turn([], session_id="s", user_text="u", assistant_text="error dialogue", trace_id="t", action="local_error", durable=False, evaluate_state=False)
            ollama_proxy.schedule_completed_turn([], session_id="s", user_text="u", assistant_text="final", trace_id="t", action="normal", durable=False)
            self.assertEqual(len(evaluator.calls), 1)
        finally:
            ollama_proxy.character_state_evaluator = original

    async def test_success_and_fail_neutral(self):
        runtime, state = await self.evaluator([json.dumps(VALID), "not json", asyncio.TimeoutError()])
        state.observe_user("private", "old")
        runtime.schedule_completed_turn("private", "u", "a")
        await asyncio.sleep(.02)
        self.assertEqual(state.snapshot("private")["emotion"], "warm")
        self.assertEqual(runtime._client.calls[0][1]["format"], state_update_schema(state.evidence_limit))
        self.assertEqual(runtime._client.calls[0][1]["keep_alive"], "30m")
        self.assertEqual(runtime.health()["num_gpu"], 999)
        self.assertEqual(runtime.health()["keep_alive"], "30m")
        version = state.snapshot("private")["version"]
        runtime.schedule_completed_turn("private", "u2", "a2")
        await asyncio.sleep(.02)
        self.assertEqual(state.snapshot("private")["version"], version)
        runtime.schedule_completed_turn("private", "u3", "a3")
        await asyncio.sleep(.02)
        self.assertEqual(state.snapshot("private")["version"], version)
        self.assertNotIn("private", repr(runtime.health()))
        await runtime.shutdown()

    async def test_nonblocking_coalescing_and_shutdown(self):
        runtime, state = await self.evaluator([json.dumps(VALID), json.dumps(dict(VALID, current_topic="new"))], .03)
        state.observe_user("s", "first")
        runtime.schedule_completed_turn("s", "u1", "a1")
        await asyncio.sleep(0)
        state.observe_user("s", "second")
        runtime.schedule_completed_turn("s", "u2", "a2")
        self.assertEqual(len(runtime._client.calls), 1)
        await asyncio.sleep(.1)
        self.assertEqual(state.snapshot("s")["current_topic"], "new")
        self.assertLessEqual(runtime.health()["running"], 1)
        await runtime.shutdown()
        runtime.schedule_completed_turn("s", "later", "later")
        self.assertEqual(runtime.health()["pending"], 0)

    async def test_idle_delay_defers_http_and_health_is_content_free(self):
        state = CharacterStateRuntime()
        runtime = CharacterStateEvaluator(state, CharacterStateEvaluatorConfig(
            enabled=True, upstream="http://127.0.0.1:11434", idle_delay_seconds=.05,
        ))
        runtime._client = _Client([json.dumps(VALID)])
        state.observe_user("private-session", "private text")
        runtime.schedule_completed_turn("private-session", "private user", "private answer")
        await asyncio.sleep(.01)
        self.assertEqual(runtime._client.calls, [])
        health = runtime.health()
        self.assertEqual(health["idle_delay_seconds"], .05)
        self.assertEqual(health["delaying"], 1)
        self.assertEqual(health["last_status"], "debouncing")
        self.assertNotIn("private", repr(health))
        await asyncio.sleep(.1)
        self.assertEqual(len(runtime._client.calls), 1)
        await runtime.shutdown()

    async def test_newer_turn_restarts_delay_without_old_http(self):
        state = CharacterStateRuntime()
        runtime = CharacterStateEvaluator(state, CharacterStateEvaluatorConfig(
            enabled=True, upstream="http://127.0.0.1:11434", idle_delay_seconds=.05,
        ))
        runtime._client = _Client([json.dumps(VALID)])
        state.observe_user("s", "first")
        runtime.schedule_completed_turn("s", "first", "answer")
        await asyncio.sleep(.01)
        state.observe_user("s", "second")
        runtime.schedule_completed_turn("s", "second", "answer")
        await asyncio.sleep(.03)
        self.assertEqual(runtime._client.calls, [])
        await asyncio.sleep(.1)
        self.assertEqual(len(runtime._client.calls), 1)
        self.assertIn('"user":"second"', runtime._client.calls[0][1]["messages"][0]["content"])
        await runtime.shutdown()

    async def test_interrupt_cancels_idle_delay_before_http(self):
        state = CharacterStateRuntime()
        runtime = CharacterStateEvaluator(state, CharacterStateEvaluatorConfig(
            enabled=True, upstream="http://127.0.0.1:11434", idle_delay_seconds=.2,
        ))
        runtime._client = _Client([json.dumps(VALID)])
        state.observe_user("s", "old")
        runtime.schedule_completed_turn("s", "old", "answer")
        await asyncio.sleep(.01)
        await runtime.interrupt_for_chat()
        await asyncio.sleep(.01)
        self.assertEqual(runtime._client.calls, [])
        self.assertEqual(runtime.health()["delaying"], 0)
        await runtime.shutdown()

    async def test_capacity_and_drain_exit_barrier(self):
        runtime, _state = await self.evaluator([json.dumps(VALID)] * 300, .05)
        for index in range(1000):
            runtime.schedule_completed_turn(f"s-{index}", "u", "a")
        self.assertEqual(len(runtime._tasks), 0)
        self.assertEqual(len(runtime._latest), 0)
        self.assertEqual(runtime.health()["last_status"], "stale")
        # Simulate a turn arriving after drain observes empty but before its
        # done callback clears the task: callback must restart it.
        future = asyncio.get_running_loop().create_future()
        future.set_result(None)
        _state.observe_user("barrier", "u")
        runtime._tasks["barrier"] = future
        barrier_snapshot = _state.snapshot_if_present("barrier")
        runtime._latest["barrier"] = ("u", "a", barrier_snapshot["version"], barrier_snapshot)
        runtime._task_finished("barrier", future)
        self.assertIn("barrier", runtime._tasks)
        await runtime.shutdown()

    async def test_evaluator_read_is_lru_neutral_for_evicted_or_missing_sessions(self):
        state = CharacterStateRuntime(max_sessions=2)
        runtime = CharacterStateEvaluator(state, self.config())
        runtime._client = _Client(["malformed"], .05)
        state.observe_user("s1", "one")
        state.observe_user("s2", "two")
        snapshot = state.snapshot_if_present("s1")
        runtime.schedule_completed_turn("s1", "u", "a", state_snapshot=snapshot)
        await asyncio.sleep(0)
        state.observe_user("s3", "three")  # evicts s1 while evaluation waits
        await asyncio.sleep(.1)
        self.assertEqual(list(state._sessions), ["s2", "s3"])
        self.assertIsNone(state.snapshot_if_present("s1"))
        await runtime.shutdown()

    async def test_stale_inflight_update_cannot_overwrite_newer_turn(self):
        old = dict(VALID, current_topic="OLD_MODEL")
        runtime, state = await self.evaluator([json.dumps(old), "malformed"], .04)
        state.observe_user("s", "first")
        first_version = state.snapshot("s")["version"]
        runtime.schedule_completed_turn("s", "first", "answer", state_version=first_version)
        await asyncio.sleep(0)
        # A newer observed turn supersedes the first result while it is blocked.
        state.observe_user("s", "second")
        second_version = state.snapshot("s")["version"]
        runtime.schedule_completed_turn("s", "second", "answer", state_version=second_version)
        await asyncio.sleep(.15)
        self.assertNotEqual(state.snapshot("s")["current_topic"], "OLD_MODEL")
        self.assertEqual(runtime.health()["last_status"], "malformed")
        await runtime.shutdown()

    async def test_interrupt_releases_foreground_chat_and_later_completion_works(self):
        # The cancelled synthetic client leaves its queued response untouched;
        # next response must still be able to complete normally.
        runtime, state = await self.evaluator([json.dumps(VALID), json.dumps(dict(VALID, current_topic="OLD"))], .2)
        state.observe_user("s", "old")
        runtime.schedule_completed_turn("s", "old", "answer")
        await asyncio.sleep(.01)
        before = state.snapshot("s")["version"]
        await runtime.interrupt_for_chat()
        self.assertEqual(len(runtime._tasks), 0)
        self.assertEqual(len(runtime._latest), 0)
        self.assertEqual(state.snapshot("s")["version"], before)
        state.observe_user("s", "new")
        runtime.schedule_completed_turn("s", "new", "answer")
        await asyncio.sleep(.25)
        self.assertEqual(state.snapshot("s")["current_topic"], "music")
        await runtime.shutdown()

    async def test_interrupt_keeps_delayed_cancellation_tracked_through_shutdown(self):
        state = CharacterStateRuntime()
        config = CharacterStateEvaluatorConfig(enabled=True, upstream="http://127.0.0.1:11434", idle_delay_seconds=0, shutdown_timeout_seconds=.5)
        runtime = CharacterStateEvaluator(state, config)
        release = asyncio.Event()
        runtime._client = _CancellationBarrierClient(release)
        state.observe_user("s", "u")
        runtime.schedule_completed_turn("s", "u", "a")
        await asyncio.sleep(0)
        await runtime.interrupt_for_chat()
        self.assertEqual(len(runtime._tasks), 0)
        self.assertGreaterEqual(len(runtime._background_tasks), 1)
        shutdown_task = asyncio.create_task(runtime.shutdown())
        await asyncio.sleep(.02)
        self.assertFalse(shutdown_task.done())
        release.set()
        await shutdown_task
        self.assertEqual(len(runtime._background_tasks), 0)
        self.assertIsNone(runtime._client)
