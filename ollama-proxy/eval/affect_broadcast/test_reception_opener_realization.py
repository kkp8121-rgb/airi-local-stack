from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import unittest
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "reception_opener_realization.py"
SPEC = importlib.util.spec_from_file_location("reception_opener_realization_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
opener = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(opener)

DIRECTOR_PRIORITIES = ("question", "topic_expansion", "sincere_reaction", "cheer", "positive")
POLITE_ENDINGS = re.compile(r"(요|니다|세요|십시오)[.!?]?$")


class ReceptionOpenerTemplateTests(unittest.TestCase):
    def test_templates_are_pinned_korean_banmal_without_slots(self) -> None:
        self.assertEqual(tuple(opener.OPENER_TEMPLATES), opener.SUPPORTED_PRIORITIES)
        self.assertEqual(opener.SUPPORTED_PRIORITIES, ("cheer", "sincere_reaction"))
        self.assertTrue(set(opener.SUPPORTED_PRIORITIES) < set(DIRECTOR_PRIORITIES))
        for priority, templates in opener.OPENER_TEMPLATES.items():
            self.assertEqual(len(templates), 3, priority)
            self.assertEqual(len(set(templates)), 3, priority)
            for text in templates:
                for sentence in re.split(r"(?<=[.!?])\s+", text):
                    self.assertIsNone(POLITE_ENDINGS.search(sentence), text)
                self.assertNotRegex(text, r"[{}\d]")
                self.assertNotRegex(text, r"[A-Za-z]")
                self.assertEqual(text.encode("utf-8").decode("utf-8"), text)

    def test_render_returns_exact_template_for_every_priority_and_variant(self) -> None:
        for priority, templates in opener.OPENER_TEMPLATES.items():
            for index, text in enumerate(templates):
                with self.subTest(priority=priority, index=index):
                    self.assertEqual(opener.render_reception_opener_text(priority, index), text)
                    rendered = opener.render_reception_opener(priority, index)
                    self.assertEqual(rendered, {
                        "schema_version": "airi.reception-opener.v1", "priority": priority,
                        "direction": "fixed_korean_template", "postcondition": "exact_template_only",
                        "text": text,
                    })
                    self.assertEqual(opener.validate_rendered_reception_opener(rendered, expected_priority=priority), rendered)
                    self.assertLessEqual(len(opener.canonical_bytes(rendered)), opener.MAX_RENDERED_BYTES)

    def test_invalid_inputs_are_rejected_without_echo(self) -> None:
        cases = [("cheer", 3), ("cheer", -1), ("cheer", True), ("cheer", "0"), ("question", 0),
                 ("positive", 0), (None, 0), (b"cheer", 0), ("cheeŕ", 0)]
        for priority, index in cases:
            with self.subTest(priority=priority, index=index):
                with self.assertRaises(opener.ReceptionOpenerError) as caught:
                    opener.render_reception_opener_text(priority, index)
                self.assertEqual(str(caught.exception), "reception opener rejected")

    def test_rendered_artifact_postcondition_is_strict(self) -> None:
        good = opener.render_reception_opener("sincere_reaction", 1)
        mutations = [
            {**good, "text": good["text"] + " "},
            {**good, "text": opener.OPENER_TEMPLATES["cheer"][0]},
            {**good, "priority": "cheer"},
            {**good, "direction": "model"},
            {**good, "schema_version": "airi.reception-opener.v2"},
            {key: good[key] for key in reversed(list(good))},
            dict(good, extra="x"),
        ]
        for value in mutations:
            with self.subTest(value=value):
                with self.assertRaises(opener.ReceptionOpenerError):
                    opener.validate_rendered_reception_opener(value)
        with self.assertRaises(opener.ReceptionOpenerError):
            opener.validate_rendered_reception_opener(good, expected_priority="cheer")


class ReceptionOpenerFlagTests(unittest.TestCase):
    def test_flag_is_off_by_default_and_only_explicit_values_enable_it(self) -> None:
        self.assertEqual(opener.FLAG_ENV, "AIRI_RECEPTION_OPENER")
        self.assertFalse(opener.reception_opener_enabled({}))
        for value in ("", "0", "false", "off", "no", "maybe"):
            with self.subTest(value=value):
                self.assertFalse(opener.reception_opener_enabled({opener.FLAG_ENV: value}))
                self.assertIsNone(opener.select_reception_opener("cheer", 0, {opener.FLAG_ENV: value}))
        for value in ("1", "true", "ON", " yes "):
            with self.subTest(value=value):
                self.assertTrue(opener.reception_opener_enabled({opener.FLAG_ENV: value}))

    def test_select_returns_none_for_priorities_it_does_not_own(self) -> None:
        on = {opener.FLAG_ENV: "on"}
        for priority in ("question", "topic_expansion", "positive"):
            with self.subTest(priority=priority):
                self.assertIsNone(opener.select_reception_opener(priority, 0, on))
        self.assertEqual(opener.select_reception_opener("cheer", 2, on)["text"], opener.OPENER_TEMPLATES["cheer"][2])
        self.assertEqual(opener.select_reception_opener("sincere_reaction", 0, on)["text"],
                         opener.OPENER_TEMPLATES["sincere_reaction"][0])
        with self.assertRaises(opener.ReceptionOpenerError):
            opener.select_reception_opener(None, 0, on)
        with self.assertRaises(opener.ReceptionOpenerError):
            opener.select_reception_opener("cheer", 3, on)

    def test_process_environment_default_is_off(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(opener.FLAG_ENV, None)
            self.assertFalse(opener.reception_opener_enabled())
            self.assertIsNone(opener.select_reception_opener("cheer", 0))


class ReceptionOpenerModuleTests(unittest.TestCase):
    def test_module_is_pure_and_not_imported_by_any_runner(self) -> None:
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported, {"__future__", "json", "os", "unicodedata", "copy", "typing"})
        # Default-off means default-unwired: no runner references the module yet.
        runners = [HERE.parent / "broadcast_sim" / "run_broadcast_sim.py", HERE / "run_affect_broadcast_eval.py",
                   HERE.parents[1] / "ollama_proxy.py", HERE.parents[1] / "deterministic_utterance_layer.py"]
        for runner in runners:
            self.assertNotIn("reception_opener", runner.read_text(encoding="utf-8"), runner.name)

    def test_canonical_bytes_round_trip(self) -> None:
        rendered = opener.render_reception_opener("cheer", 1)
        self.assertEqual(json.loads(opener.canonical_bytes(rendered).decode("utf-8")), rendered)


if __name__ == "__main__":
    unittest.main()
