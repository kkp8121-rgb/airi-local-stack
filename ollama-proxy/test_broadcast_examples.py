import json
import os
import unittest
from unittest import mock

import broadcast_examples
import deterministic_utterance_layer
from deterministic_utterance_layer import system_briefing_evidence


class BroadcastExamplesTests(unittest.TestCase):
    def setUp(self):
        self.body = json.dumps({
            "messages": [
                {"role": "system", "name": "airi_broadcast_context", "content": "server context"},
                {"role": "user", "content": "안녕"},
            ],
        }, ensure_ascii=False).encode("utf-8")

    def test_env_gate_accepts_only_documented_true_values(self):
        for value in ("1", "true", "on", "yes", " TRUE "):
            self.assertTrue(broadcast_examples.broadcast_examples_enabled(value))
        for value in (None, "", "0", "false", "off", "enabled", "yesplease"):
            self.assertFalse(broadcast_examples.broadcast_examples_enabled(value))

    def test_disabled_path_and_non_live_path_leave_bytes_unchanged(self):
        with mock.patch.dict(os.environ, {broadcast_examples.BROADCAST_EXAMPLES_ENV: "off"}):
            rendered, injected = broadcast_examples.inject_broadcast_examples(
                self.body, authenticated_live_broadcast=True,
            )
        self.assertEqual((rendered, injected), (self.body, False))
        with mock.patch.dict(os.environ, {broadcast_examples.BROADCAST_EXAMPLES_ENV: "on"}):
            rendered, injected = broadcast_examples.inject_broadcast_examples(
                self.body, authenticated_live_broadcast=False,
            )
        self.assertEqual((rendered, injected), (self.body, False))

    def test_live_enabled_injects_one_style_only_note_without_evidence(self):
        with mock.patch.dict(os.environ, {broadcast_examples.BROADCAST_EXAMPLES_ENV: "yes"}):
            rendered, injected = broadcast_examples.inject_broadcast_examples(
                self.body, authenticated_live_broadcast=True,
            )
        self.assertTrue(injected)
        messages = json.loads(rendered)["messages"]
        examples = [message for message in messages if message.get("name") == broadcast_examples.BROADCAST_EXAMPLES_MESSAGE_NAME]
        self.assertEqual(len(examples), 1)
        self.assertEqual(examples[0]["content"], broadcast_examples.BROADCAST_EXAMPLES_PROMPT)
        self.assertIn(broadcast_examples.BROADCAST_EXAMPLES_STYLE_ONLY_MARKER, examples[0]["content"])
        self.assertEqual(system_briefing_evidence(examples[0]["content"]), "")
        with mock.patch.object(
                deterministic_utterance_layer,
                "DETERMINISTIC_UTTERANCE_LAYER_ENABLED", True):
            inputs = deterministic_utterance_layer.build_layer_inputs(
                user_text="안녕",
                briefing_evidence="",
                original_messages=examples,
            )
        self.assertNotIn("오늘은 채팅 보면서", inputs["pool_text"])
        self.assertIn("오늘은 채팅 보면서", inputs["prompt_text"])
        self.assertLess(messages.index(examples[0]), len(messages) - 1)

    def test_repeat_injection_does_not_duplicate_examples(self):
        with mock.patch.dict(os.environ, {broadcast_examples.BROADCAST_EXAMPLES_ENV: "1"}):
            first, first_injected = broadcast_examples.inject_broadcast_examples(
                self.body, authenticated_live_broadcast=True,
            )
            second, second_injected = broadcast_examples.inject_broadcast_examples(
                first, authenticated_live_broadcast=True,
            )
        self.assertTrue(first_injected)
        self.assertTrue(second_injected)
        self.assertEqual(second, first)
        self.assertEqual(
            sum(message.get("name") == broadcast_examples.BROADCAST_EXAMPLES_MESSAGE_NAME
                for message in json.loads(second)["messages"]),
            1,
        )


if __name__ == "__main__":
    unittest.main()
