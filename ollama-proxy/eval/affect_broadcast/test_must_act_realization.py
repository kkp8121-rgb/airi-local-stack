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
            "deescalate": "지금은 안전이 먼저야. 바로 119에 연락하고 주변 사람에게도 도움을 요청해.",
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
        self.assertEqual(
            [entry["turn_id"] for entry in human_routes],
            ["fatigue-03", "fatigue-10", "fatigue-11", "fatigue-13", "fatigue-14", "fatigue-15", "fatigue-17", "fatigue-19", "fatigue-21"],
        )
        fixed_emergency = [
            entry for entry in oracle["entries"]
            if entry.get("emergency_context") is True
        ]
        self.assertEqual([entry["turn_id"] for entry in fixed_emergency], ["fatigue-09"])
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

    def test_callout_is_inert_until_a_verified_name_arrives(self) -> None:
        default = realization.render_must_act(candidate("thank"))
        self.assertEqual(default["text"], "고마워. 함께해줘서 힘이 돼.")
        self.assertEqual(default["direction"], "fixed_korean_template")
        self.assertEqual(default["postcondition"], "exact_template_only")
        self.assertEqual(
            realization.canonical_bytes(default),
            realization.canonical_bytes({
                "schema_version": "airi.must-act-realization.v1",
                "act": "thank",
                "direction": "fixed_korean_template",
                "postcondition": "exact_template_only",
                "text": "고마워. 함께해줘서 힘이 돼.",
            }),
        )

    def test_callout_fills_only_the_two_approved_slots(self) -> None:
        self.assertEqual(realization.THANK_CALLOUT_TEMPLATE, "{nickname}, 고마워! {closer}")
        self.assertEqual(
            realization.THANK_CALLOUT_CLOSERS,
            ("덕분에 오늘도 달린다!", "이 힘으로 조금 더 해볼게!", "사장님한테 자랑해야지!"),
        )
        for index, closer in enumerate(realization.THANK_CALLOUT_CLOSERS):
            rendered = realization.render_must_act(
                candidate("thank"), callout_context={"nickname": "별빛수집가", "closer_index": index}
            )
            self.assertEqual(rendered["text"], f"별빛수집가, 고마워! {closer}")
            self.assertEqual(rendered["direction"], "fixed_korean_template_with_verified_callout")
            self.assertEqual(rendered["postcondition"], "exact_template_with_single_callout_only")
            self.assertEqual(realization.validate_rendered_artifact(rendered, expected_act="thank"), rendered)
            self.assertEqual(realization.decompose_thank_callout(rendered["text"]), ("별빛수집가", index))
            self.assertEqual(rendered["text"].count("별빛수집가"), 1)
        longest = "가" * realization.MAX_CALLOUT_NICKNAME_CHARS
        worst = realization.render_must_act(candidate("thank"), callout_context={"nickname": longest, "closer_index": 1})
        self.assertLessEqual(len(realization.canonical_bytes(worst)), realization.MAX_RENDERED_BYTES)

    def test_callout_context_fails_closed(self) -> None:
        invalid_contexts = [
            {"nickname": "별빛"}, {"closer_index": 0},
            {"nickname": "별빛", "closer_index": 0, "amount": 1000},
            {"nickname": "별빛", "closer_index": True},
            {"nickname": "별빛", "closer_index": 3}, {"nickname": "별빛", "closer_index": -1},
            {"nickname": "별빛", "closer_index": "0"},
            {"nickname": "", "closer_index": 0},
            {"nickname": "가" * (realization.MAX_CALLOUT_NICKNAME_CHARS + 1), "closer_index": 0},
            {"nickname": "별, 빛", "closer_index": 0}, {"nickname": "별빛!", "closer_index": 0},
            {"nickname": "별\n빛", "closer_index": 0}, {"nickname": "별" + chr(0x202E) + "빛", "closer_index": 0},
            {"nickname": "별" + chr(0x00A0) + "빛", "closer_index": 0}, {"nickname": "별  빛", "closer_index": 0},
            {"nickname": " 별빛", "closer_index": 0}, {"nickname": "별빛 ", "closer_index": 0},
            {"nickname": chr(0x1100) + chr(0x1161), "closer_index": 0},
            {"nickname": 1000, "closer_index": 0}, {"nickname": None, "closer_index": 0},
            "별빛", ["별빛", 0], {},
        ]
        for context in invalid_contexts:
            with self.assertRaises(realization.MustActRealizationError):
                realization.render_must_act(candidate("thank"), callout_context=context)
        for act in ("close", "correct", "repair"):
            with self.assertRaises(realization.MustActRealizationError):
                realization.render_must_act(candidate(act), callout_context={"nickname": "별빛", "closer_index": 0})
        with self.assertRaises(realization.MustActRealizationError):
            realization.render_must_act(
                candidate("deescalate"),
                oracle_context={"emergency_context": True},
                callout_context={"nickname": "별빛", "closer_index": 0},
            )

    def test_callout_artifacts_reject_tampering(self) -> None:
        rendered = realization.render_must_act(
            candidate("thank"), callout_context={"nickname": "별빛", "closer_index": 0}
        )
        tampered = [
            {**rendered, "direction": "fixed_korean_template", "postcondition": "exact_template_only"},
            {**rendered, "postcondition": "exact_template_only"},
            {**rendered, "direction": "fixed_korean_template"},
            {**rendered, "text": "별빛, 고마워! 아무 말이나 붙인다!"},
            {**rendered, "text": "별빛, 고마워! 덕분에 오늘도 달린다!, 고마워! 덕분에 오늘도 달린다!"},
            {**rendered, "text": "고마워! 덕분에 오늘도 달린다!"},
            {**rendered, "text": "별, 빛, 고마워! 덕분에 오늘도 달린다!"},
            {**rendered, "act": "close"},
        ]
        for value in tampered:
            with self.assertRaises(realization.MustActRealizationError):
                realization.validate_rendered_artifact(value)
        for text in ("고마워. 함께해줘서 힘이 돼.", "별빛, 고마워! ", "", "별빛, 고마워! 덕분에 오늘도 달린다"):
            with self.assertRaises(realization.MustActRealizationError):
                realization.decompose_thank_callout(text)

    def test_callout_sidecar_oracle_is_content_free_and_pinned(self) -> None:
        sidecar = realization.load_thank_callout_oracle()
        oracle = realization.load_oracle()
        self.assertEqual(realization.validate_thank_callout_oracle(sidecar, oracle), sidecar)
        self.assertEqual(sidecar["template"], realization.THANK_CALLOUT_TEMPLATE)
        self.assertEqual(sidecar["closers"], list(realization.THANK_CALLOUT_CLOSERS))
        self.assertEqual(
            [entry["turn_id"] for entry in sidecar["entries"]],
            [entry["turn_id"] for entry in oracle["entries"] if entry["expected_act"] == "thank"],
        )
        forbidden = {"text", "viewer", "source", "name", "nickname", "amount", "event_id", "runtime_state"}
        for entry in sidecar["entries"]:
            self.assertFalse(forbidden & set(entry))
            # 합성 코퍼스의 후원 턴에는 검증된 표시 이름이 없다 — 기대 경로는 v1 고정 템플릿이다.
            self.assertIs(entry["callout_available"], False)
            self.assertEqual((entry["direction"], entry["postcondition"]), ("fixed_korean_template", "exact_template_only"))
        for mutate in (
            lambda value: {**value, "closers": ["아무 말이나!"]},
            lambda value: {**value, "template": "{nickname} 고마워"},
            lambda value: {**value, "realization_oracle_sha256": "0" * 64},
            lambda value: {**value, "entries": value["entries"][:1]},
            lambda value: {**value, "entries": [{**value["entries"][0], "callout_available": True}] + value["entries"][1:]},
        ):
            with self.assertRaises(realization.MustActRealizationError):
                realization.validate_thank_callout_oracle(mutate(copy.deepcopy(sidecar)), oracle)

    def test_callout_never_invents_a_name(self) -> None:
        fixture = json.loads((HERE / "synthetic_affect_broadcast_v1.json").read_text(encoding="utf-8"))
        sidecar = json.loads((HERE / "synthetic_reply_act_v1.json").read_text(encoding="utf-8"))
        raw = json.dumps(fixture, ensure_ascii=False) + json.dumps(sidecar, ensure_ascii=False)
        for closer in realization.THANK_CALLOUT_CLOSERS:
            self.assertNotIn(closer, raw)
        rendered = realization.render_must_act(
            candidate("thank"), callout_context={"nickname": "별빛", "closer_index": 0}
        )
        self.assertTrue(rendered["text"].startswith("별빛, "))
        default = realization.render_must_act(candidate("thank"))
        self.assertNotIn(", 고마워! ", default["text"])

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
