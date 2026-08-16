from __future__ import annotations

import ast
import copy
import importlib.util
import json
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "must_act_realization.py"
SPEC = importlib.util.spec_from_file_location("must_act_realization_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
realization = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(realization)


def candidate(act: str) -> dict[str, str]:
    return {
        "schema_version": "airi.broadcast-reply-act.v1",
        "act": act,
        "evidence_scope": "prior_airi_and_latest_viewer",
    }


class MustActRealizationTests(unittest.TestCase):
    def test_templates_are_exact_and_canonical(self) -> None:
        expected = {
            "thank": "고마워. 함께해줘서 힘이 돼.",
            "close": "오늘은 여기까지 할게. 고마워.",
            "correct": "정정할게. 확인된 내용만 말할게.",
            "repair": "미안해. 내가 잘못 말했어. 확인하고 바로잡을게.",
            "deescalate": "지금은 안전이 먼저야. 혼자 있지 말고 119나 주변 사람에게 도움을 요청해.",
        }
        for act, text in expected.items():
            context = {"emergency_context": True} if act == "deescalate" else None
            rendered = realization.render_must_act(candidate(act), oracle_context=context)
            self.assertEqual(rendered["text"], text)
            self.assertEqual(realization.serialize_rendered_artifact(rendered), realization.canonical_bytes(rendered))
            self.assertEqual(realization.validate_rendered_artifact(rendered), rendered)

    def test_rejects_noncanonical_schema_and_unsupported_acts(self) -> None:
        invalids = [
            None, "{}", {"act": "thank"},
            {**candidate("thank"), "extra": "x"},
            {**candidate("callback")},
        ]
        for value in invalids:
            with self.assertRaises(realization.MustActRealizationError):
                realization.render_must_act(value)

    def test_parser_and_output_schema_fail_closed(self) -> None:
        canonical = json.dumps(candidate("thank"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(realization.parse_must_act_candidate(canonical), candidate("thank"))
        with self.assertRaises(realization.MustActRealizationError):
            realization.parse_must_act_candidate(canonical + " ")
        rendered = realization.render_must_act(candidate("thank"))
        for key, value in (("act", "callback"), ("direction", "caller_data"), ("postcondition", "grounded"), ("text", 1)):
            malformed = copy.deepcopy(rendered)
            malformed[key] = value
            with self.assertRaises(realization.MustActRealizationError):
                realization.validate_rendered_artifact(malformed)

    def test_deescalation_requires_closed_trusted_marker(self) -> None:
        for context in (None, {}, {"emergency_context": False}, {"emergency_context": True, "text": "x"}, "urgent"):
            with self.assertRaises(realization.MustActRealizationError):
                realization.render_must_act(candidate("deescalate"), oracle_context=context)

    def test_postcondition_is_deterministic_and_closed(self) -> None:
        rendered = realization.render_must_act(candidate("repair"))
        malformed = copy.deepcopy(rendered)
        malformed["text"] = "caller text"
        self.assertEqual(realization.validate_rendered_artifact(rendered, expected_act="repair"), rendered)
        with self.assertRaises(realization.MustActRealizationError):
            realization.validate_rendered_artifact(malformed)
        with self.assertRaises(realization.MustActRealizationError):
            realization.validate_rendered_artifact(rendered, expected_act="thank")

    def test_renderer_has_no_caller_text_path(self) -> None:
        rendered = realization.render_must_act(candidate("thank"))
        fixture = json.loads((HERE / "synthetic_affect_broadcast_v1.json").read_text(encoding="utf-8"))
        raw = json.dumps(fixture, ensure_ascii=False)
        self.assertNotIn(rendered["text"], raw)
        self.assertNotIn("first-23", rendered["text"])
        self.assertNotIn("1000", rendered["text"])

    def test_oracle_is_content_free_ordered_and_pinned(self) -> None:
        oracle = realization.load_oracle()
        self.assertEqual(realization.validate_oracle(
            oracle,
            json.loads((HERE / "synthetic_affect_broadcast_v1.json").read_text(encoding="utf-8")),
            json.loads((HERE / "synthetic_reply_act_v1.json").read_text(encoding="utf-8")),
        ), oracle)
        forbidden = {"text", "viewer", "source", "name", "amount", "event_id", "runtime_state"}
        for entry in oracle["entries"]:
            self.assertFalse(forbidden & set(entry))
            self.assertNotEqual(entry["expected_act"], "callback")
        human_routes = [entry for entry in oracle["entries"] if entry.get("emergency_context") is False]
        self.assertEqual([entry["turn_id"] for entry in human_routes], ["fatigue-03"])
        self.assertEqual(human_routes[0]["direction"], "human_review_only")
        self.assertEqual(human_routes[0]["postcondition"], "emergency_context_required")
        with self.assertRaises(realization.MustActRealizationError):
            realization.render_must_act(candidate("deescalate"), oracle_context={"emergency_context": False})

        tampered = copy.deepcopy(oracle)
        tampered["entries"][0]["expected_act"] = "thank"
        with self.assertRaises(realization.MustActRealizationError):
            realization.validate_oracle(
                tampered,
                json.loads((HERE / "synthetic_affect_broadcast_v1.json").read_text(encoding="utf-8")),
                json.loads((HERE / "synthetic_reply_act_v1.json").read_text(encoding="utf-8")),
            )

    def test_module_stays_pure(self) -> None:
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        banned = {"socket", "requests", "urllib", "subprocess", "random", "time", "datetime"}
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(banned & imported)

        import_from = ast.parse("from requests import get")
        roots = {
            node.module.split(".")[0]
            for node in ast.walk(import_from)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertEqual(roots, {"requests"})


if __name__ == "__main__":
    unittest.main()
