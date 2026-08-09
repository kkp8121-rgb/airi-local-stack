import concurrent.futures
import unittest

from character_state import CharacterStateRuntime


class FakeClock:
    def __init__(self, value=100.0): self.value = value
    def __call__(self): return self.value


class CharacterStateRuntimeTests(unittest.TestCase):
    def test_session_isolation(self):
        runtime = CharacterStateRuntime()
        runtime.observe_user("one", "music")
        runtime.observe_user("two", "games")
        self.assertEqual(runtime.snapshot("one")["current_topic"], "music")
        self.assertEqual(runtime.snapshot("two")["current_topic"], "games")

    def test_fields_evidence_and_lru_are_bounded(self):
        runtime = CharacterStateRuntime(max_sessions=2, evidence_limit=2, text_limit=16, tool_result_limit=20)
        runtime.observe_user("a", "x" * 80)
        runtime.apply_model_state_update("a", {"intimacy_evidence": ["a" * 30, "b" * 30, "c" * 30]})
        state = runtime.snapshot("a")
        self.assertEqual(len(state["current_topic"]), 16)
        self.assertEqual(state["intimacy_evidence"], ["b" * 16, "c" * 16])
        runtime.snapshot("b"); runtime.snapshot("c")
        self.assertIsNone(runtime.snapshot("a")["current_topic"])

    def test_silence_uses_clock_since_user_observation(self):
        clock = FakeClock()
        runtime = CharacterStateRuntime(clock=clock)
        runtime.observe_user("s", "hello")
        clock.value += 2.75
        self.assertEqual(runtime.snapshot("s")["silence_ms"], 2750)
        runtime.observe_user("s", "back")
        state = runtime.snapshot("s")
        self.assertEqual(state["silence_ms"], 0)
        self.assertEqual(state["silence_before_turn_ms"], 2750)

    def test_repeat_changes_unknown_satisfaction_without_action_rule(self):
        runtime = CharacterStateRuntime()
        runtime.observe_user("s", "again", repeat_intent="repeat", repeat_count=99)
        state = runtime.snapshot("s")
        self.assertEqual(state["repeat_intent"], "repeat")
        self.assertFalse(state["previous_answer_satisfied"])
        self.assertIsNone(state["last_action"])
        runtime.observe_user("s", "new subject")
        self.assertEqual(runtime.snapshot("s")["previous_answer_satisfied"], "unknown")

    def test_assistant_records_actual_action_and_tool_result(self):
        runtime = CharacterStateRuntime(tool_result_limit=20)
        runtime.observe_user("s", "What should I do?")
        runtime.observe_assistant("s", "What next?", action="opened_calendar", tool_result="OK: event created " * 4)
        state = runtime.snapshot("s")
        self.assertEqual(state["last_action"], "opened_calendar")
        self.assertEqual(state["last_tool_result"], ("OK: event created " * 4)[:20])
        self.assertEqual(state["last_question"], "What should I do?")

    def test_model_update_allowlist_and_invalid_values(self):
        runtime = CharacterStateRuntime()
        runtime.observe_assistant("s", "x", action="actual")
        runtime.apply_model_state_update("s", {"emotion": "warm", "last_action": "invented", "last_question": "invented", "version": 999, "user_interest": 42})
        state = runtime.snapshot("s")
        self.assertEqual(state["emotion"], "warm")
        self.assertEqual(state["last_action"], "actual")
        self.assertIsNone(state["last_question"])
        self.assertNotEqual(state["version"], 999)
        self.assertIsNone(state["user_interest"])

    def test_prompt_is_compact_and_never_has_unbounded_raw_content(self):
        runtime = CharacterStateRuntime(text_limit=16)
        raw = "secret-" * 100
        runtime.observe_user("s", raw)
        block = runtime.prompt_block("s")
        self.assertTrue(block.startswith("[Character State] "))
        self.assertNotIn(raw, block)
        self.assertIn("current_topic", block)

    def test_concurrent_calls_smoke(self):
        runtime = CharacterStateRuntime(max_sessions=8)
        def work(index):
            runtime.observe_user("shared", "message " + str(index), repeat_intent="retry" if index % 3 == 0 else None)
            runtime.observe_assistant("shared", "reply " + str(index), action="sent")
            return runtime.snapshot("shared")["version"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            results = list(executor.map(work, range(100)))
        self.assertTrue(all(isinstance(value, int) for value in results))
        self.assertGreater(runtime.snapshot("shared")["version"], 0)

    def test_health_never_exposes_session_or_content(self):
        runtime = CharacterStateRuntime(max_sessions=4)
        runtime.observe_user("private-session", "private content")
        health = runtime.health()
        self.assertEqual(health["sessions"], 1)
        self.assertNotIn("private-session", repr(health))
        self.assertNotIn("private content", repr(health))

    def test_snapshot_if_present_never_creates_or_moves_lru(self):
        runtime = CharacterStateRuntime(max_sessions=2)
        runtime.observe_user("s1", "one")
        runtime.observe_user("s2", "two")
        self.assertIsNone(runtime.snapshot_if_present("absent"))
        self.assertEqual(list(runtime._sessions), ["s1", "s2"])
        before = runtime.version_if_present("s1")
        self.assertEqual(runtime.snapshot_if_present("s1")["version"], before)
        self.assertEqual(list(runtime._sessions), ["s1", "s2"])


if __name__ == "__main__":
    unittest.main()
