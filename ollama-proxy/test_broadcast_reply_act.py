import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import broadcast_reply_act as reply_act


class ReplyActSchemaTests(unittest.TestCase):
    def test_serializer_and_parser_are_canonical(self) -> None:
        value = {
            "schema_version": reply_act.REPLY_ACT_SCHEMA_VERSION,
            "act": "respond_grounded",
            "evidence_scope": reply_act.REPLY_ACT_EVIDENCE_SCOPE,
        }
        wire = reply_act.serialize_reply_act_candidate(value)
        self.assertEqual(
            wire,
            '{"act":"respond_grounded","evidence_scope":"prior_airi_and_latest_viewer","schema_version":"airi.broadcast-reply-act.v1"}',
        )
        self.assertEqual(reply_act.parse_reply_act_candidate(wire), value)

    def test_schema_is_strict_and_errors_do_not_echo_input(self) -> None:
        bad_values = [
            {},
            {"schema_version": reply_act.REPLY_ACT_SCHEMA_VERSION, "act": True, "evidence_scope": reply_act.REPLY_ACT_EVIDENCE_SCOPE},
            {"schema_version": reply_act.REPLY_ACT_SCHEMA_VERSION, "act": "unknown", "evidence_scope": reply_act.REPLY_ACT_EVIDENCE_SCOPE},
            {"schema_version": reply_act.REPLY_ACT_SCHEMA_VERSION + "\u0301", "act": "thank", "evidence_scope": reply_act.REPLY_ACT_EVIDENCE_SCOPE},
        ]
        for value in bad_values:
            with self.subTest(value=value):
                with self.assertRaises(reply_act.ReplyActValidationError) as raised:
                    reply_act.validate_reply_act(value)
                self.assertNotIn("unknown", str(raised.exception))

    def test_parser_rejects_noncanonical_and_unsafe_spellings(self) -> None:
        canonical = reply_act.serialize_reply_act_candidate({
            "schema_version": reply_act.REPLY_ACT_SCHEMA_VERSION,
            "act": "celebrate",
            "evidence_scope": reply_act.REPLY_ACT_EVIDENCE_SCOPE,
        })
        bad = [
            canonical + " ", canonical.replace('"act"', '"evidence_scope"', 1),
            canonical.replace("celebrate", "\\u0063elebrate"), canonical + "\n",
            canonical.replace("celebrate", "celebrate\u200b"),
        ]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(reply_act.ReplyActValidationError):
                    reply_act.parse_reply_act_candidate(value)


class RenderTests(unittest.TestCase):
    def test_every_act_is_fixed_deterministic_and_bounded(self) -> None:
        for act in reply_act.REPLY_ACTS:
            candidate = {"schema_version": reply_act.REPLY_ACT_SCHEMA_VERSION, "act": act, "evidence_scope": reply_act.REPLY_ACT_EVIDENCE_SCOPE}
            with self.subTest(act=act):
                first = reply_act.render_reply_act_contract(candidate)
                self.assertEqual(first, reply_act.render_reply_act_contract(candidate))
                self.assertLessEqual(len(first.encode("utf-8")), reply_act.REPLY_ACT_RENDER_MAX_BYTES)
                self.assertIn("반말", first)

    def test_renderer_cannot_echo_caller_free_text(self) -> None:
        candidate = {
            "schema_version": reply_act.REPLY_ACT_SCHEMA_VERSION,
            "act": "thank",
            "evidence_scope": reply_act.REPLY_ACT_EVIDENCE_SCOPE,
        }
        rendered = reply_act.render_reply_act_contract(candidate)
        self.assertNotIn("Alice", rendered)
        self.assertNotIn("100000", rendered)
        self.assertIn("이름·금액", rendered)


class PurityTests(unittest.TestCase):
    def test_module_has_no_forbidden_imports(self) -> None:
        source = Path(reply_act.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {node.names[0].name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)}
        imports.update(node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
        self.assertFalse(imports & {"os", "time", "datetime", "requests", "sqlite3", "socket", "http", "urllib"})
