from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "correction_target.py"
SPEC = importlib.util.spec_from_file_location("correction_target_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
target = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(target)


MAPPINGS = [
    ("teasing-02", "rabbit_ears", "replace_prior_visual_interpretation"),
    ("teasing-12", "candle_wick", "replace_prior_visual_interpretation"),
    ("correction-02", "exit_marker_right_door", "replace_prior_visual_interpretation"),
    ("correction-03", "bottom_glyph_compass", "replace_prior_visual_interpretation"),
    ("correction-04", "needle_gray", "replace_prior_visual_interpretation"),
    ("correction-07", "door_number_twenty_one", "replace_prior_visual_interpretation"),
    ("correction-08", "original_map_number_twenty_one", "confirm_corrected_reading"),
    ("correction-12", "glyph_feather_like", "shift_to_hedged_resemblance"),
]


def candidate(target_id: str, direction: str) -> dict[str, str]:
    return {
        "schema_version": "airi.correction-target.v1",
        "act": "correct",
        "target_id": target_id,
        "direction": direction,
        "evidence_basis": "pinned_synthetic_fixture_assertion",
    }


class CorrectionTargetTests(unittest.TestCase):
    def test_oracle_exact_order_hash_and_mappings(self) -> None:
        oracle = target.load_oracle()
        self.assertEqual(target.ORACLE_SHA256, hashlib.sha256(target.canonical_bytes(oracle)).hexdigest())
        self.assertEqual(len(oracle["entries"]), 8)
        self.assertEqual(
            [(entry["turn_id"], entry["target_id"], entry["direction"]) for entry in oracle["entries"]], MAPPINGS
        )
        self.assertEqual(oracle["entries"][6]["direction"], "confirm_corrected_reading")
        self.assertEqual(oracle["entries"][7]["direction"], "shift_to_hedged_resemblance")

    def test_all_pairs_canonical_round_trip(self) -> None:
        for _, target_id, direction in MAPPINGS:
            value = candidate(target_id, direction)
            serialized = target.serialize_candidate(value)
            self.assertEqual(target.parse_candidate(serialized.decode("utf-8")), value)
            self.assertEqual(target.validate_candidate(dict(reversed(list(value.items())))), value)
        with self.assertRaises(target.CorrectionTargetError):
            target.parse_candidate(target.serialize_candidate(candidate(*MAPPINGS[0][1:])).decode("utf-8") + " ")
        with self.assertRaises(target.CorrectionTargetError):
            target.parse_candidate('{"x":"' + ("x" * target.MAX_CANDIDATE_BYTES) + '"}')
        documented_order = json.dumps(candidate(*MAPPINGS[0][1:]), ensure_ascii=False, separators=(",", ":"))
        with self.assertRaises(target.CorrectionTargetError):
            target.parse_candidate(documented_order)

    def test_candidate_fails_closed(self) -> None:
        valid = candidate(*MAPPINGS[0][1:])
        invalids = [
            None, {"act": "correct"}, {**valid, "text": "free text"},
            {key: value for key, value in valid.items() if key != "direction"},
            {**valid, "act": "repair"}, {**valid, "target_id": "free text"},
            {**valid, "direction": "wrong"}, {**valid, "target_id": 1},
            {**valid, "evidence_basis": "fixture\u0301"},
            {**valid, "target_id": "bad\u0000value"},
        ]
        for value in invalids:
            with self.assertRaises(target.CorrectionTargetError):
                target.validate_candidate(value)

    def test_exact_eligibility_and_cross_turn_rejection(self) -> None:
        for turn_id, target_id, direction in MAPPINGS:
            result = target.validate_target_for_turn(turn_id, candidate(target_id, direction))
            self.assertEqual(list(result), ["schema_version", "decision", "act", "target_id", "direction", "evidence_basis"])
            self.assertEqual(result["decision"], "eligible_for_offline_human_review")
            self.assertEqual((result["target_id"], result["direction"]), (target_id, direction))
        turn_id, target_id, direction = MAPPINGS[0]
        with self.assertRaises(target.CorrectionTargetError):
            target.validate_target_for_turn(MAPPINGS[1][0], candidate(target_id, direction))
        with self.assertRaises(target.CorrectionTargetError):
            target.validate_target_for_turn(turn_id, candidate(target_id, "confirm_corrected_reading"))

    def test_oracle_fixture_and_sidecar_tampering_fails(self) -> None:
        oracle = target.load_oracle()
        fixture = json.loads((HERE / "synthetic_affect_broadcast_v1.json").read_text(encoding="utf-8"))
        sidecar = json.loads((HERE / "synthetic_reply_act_v1.json").read_text(encoding="utf-8"))
        for value, kind in ((copy.deepcopy(oracle), "oracle"), (copy.deepcopy(fixture), "fixture"), (copy.deepcopy(sidecar), "sidecar")):
            if kind == "oracle":
                value["entries"][0]["target_id"] = "changed"
            elif kind == "fixture":
                value["scenarios"][0]["turns"][0]["id"] = "changed"
            else:
                value["entries"][0]["turn_id"] = "changed"
            with self.assertRaises(target.CorrectionTargetError):
                target.validate_oracle(
                    value if kind == "oracle" else oracle,
                    value if kind == "fixture" else fixture,
                    value if kind == "sidecar" else sidecar,
                )

    def test_output_is_closed_deterministic_and_deep_copied(self) -> None:
        turn_id, target_id, direction = MAPPINGS[0]
        first = target.validate_target_for_turn(turn_id, candidate(target_id, direction))
        second = target.validate_target_for_turn(turn_id, candidate(target_id, direction))
        self.assertEqual(first, second)
        first["target_id"] = "changed"
        self.assertEqual(second["target_id"], target_id)
        forbidden = {"text", "identity", "name", "amount", "value", "event_id", "model_output", "reason", "prior_airi", "selected_message", "screen", "fixture"}
        self.assertFalse(forbidden & set(second))
        rendered = json.dumps(second, ensure_ascii=False)
        fixture = json.loads((HERE / "synthetic_affect_broadcast_v1.json").read_text(encoding="utf-8"))
        for scenario in fixture["scenarios"]:
            for turn in scenario["turns"]:
                for key in ("prior_airi", "selected_message"):
                    if turn[key]:
                        self.assertNotIn(turn[key], rendered)
                for screen_value in turn["context"].values():
                    if type(screen_value) is str:
                        self.assertNotIn(screen_value, rendered)

    def test_byte_cap_and_module_purity(self) -> None:
        oversized = candidate("x" * target.MAX_CANDIDATE_BYTES, MAPPINGS[0][2])
        with self.assertRaises(target.CorrectionTargetError):
            target.validate_candidate(oversized)
        valid = candidate(*MAPPINGS[0][1:])
        original_cap = target.MAX_CANDIDATE_BYTES
        try:
            target.MAX_CANDIDATE_BYTES = len(target.canonical_bytes(valid)) - 1
            with self.assertRaises(target.CorrectionTargetError):
                target.validate_candidate(valid)
        finally:
            target.MAX_CANDIDATE_BYTES = original_cap
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        self.assertTrue(imports)
        roots = set()
        for node in imports:
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif node.module:
                roots.add(node.module.split(".")[0])
        self.assertTrue(roots <= {"__future__", "hashlib", "json", "unicodedata", "copy", "pathlib", "typing"})

    def test_runtime_does_not_import_evaluator_or_wire_operational_launchers(self) -> None:
        proxy_tree = ast.parse((HERE.parents[1] / "ollama_proxy.py").read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(proxy_tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        imported_modules.update(
            alias.name
            for node in ast.walk(proxy_tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        self.assertNotIn("correction_target", imported_modules)
        self.assertFalse(any(name.endswith(".correction_target") for name in imported_modules))
        self.assertIn("broadcast_correction_target", imported_modules)

        operational_files = [
            HERE.parents[2] / "broadcast-director" / "core.mjs",
            HERE.parents[2] / "broadcast-director" / "priority-policy.mjs",
        ]
        operational_files.extend(HERE.parents[2].glob("*airi*.ps1"))
        for path in operational_files:
            self.assertNotIn("broadcast_correction_target", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()
