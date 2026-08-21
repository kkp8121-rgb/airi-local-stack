import ast
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import affect_state
import broadcast_affect_event_mapper as mapper


def candidate(evidence: str = "director_delivery", outcome: str = "callback_hit", **changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": mapper.BROADCAST_AFFECT_OUTCOME_CANDIDATE_SCHEMA_VERSION,
        "evidence": evidence,
        "outcome": outcome,
        "delivery_status": "delivered",
        "turn_index": 9,
    }
    value.update(changes)
    return value


class BroadcastAffectEventMapperTests(unittest.TestCase):
    def test_exact_fixed_outputs_and_a1_acceptance(self) -> None:
        expected = {
            ("director_delivery", "donation_acknowledged"): ("broadcast_director", "donation_received", 1, {"goal_congruence": 1, "agency": "none", "control": 1, "novelty": 1, "social_tone": "neutral"}),
            ("director_delivery", "callback_hit"): ("broadcast_director", "callback_hit", 1, {"goal_congruence": 1, "agency": "none", "control": 1, "novelty": 1, "social_tone": "neutral"}),
            ("director_delivery", "callback_miss"): ("broadcast_director", "callback_miss", 1, {"goal_congruence": -1, "agency": "none", "control": 1, "novelty": 1, "social_tone": "neutral"}),
            ("game_telemetry", "game_success"): ("broadcast_director", "game_success", 2, {"goal_congruence": 1, "agency": "self", "control": 2, "novelty": 1, "social_tone": "neutral"}),
            ("game_telemetry", "game_failure"): ("broadcast_director", "game_failure", 2, {"goal_congruence": -1, "agency": "none", "control": 1, "novelty": 1, "social_tone": "neutral"}),
            ("silence_observer", "silence"): ("broadcast_director", "silence", 1, {"goal_congruence": -1, "agency": "none", "control": 1, "novelty": 1, "social_tone": "neutral"}),
            ("proxy_terminal_output", "response_repair"): ("proxy_outcome", "response_repair", 2, {"goal_congruence": 1, "agency": "none", "control": 1, "novelty": 1, "social_tone": "neutral"}),
        }
        for (evidence, outcome), (source, kind, weight, appraisal) in expected.items():
            with self.subTest(evidence=evidence, outcome=outcome):
                event = mapper.map_broadcast_outcome_candidate(candidate(evidence, outcome, turn_index=17))
                self.assertEqual(event, {"schema_version": affect_state.EVENT_SCHEMA_VERSION, "source": source, "kind": kind, "appraisal": appraisal, "weight": weight, "turn_index": 17})
                self.assertEqual(affect_state.validate_event(event), event)

    def test_strict_malformed_matrix_and_sanitized_errors(self) -> None:
        bad_values = [None, [], {}, candidate(schema_version="wrong"), candidate(evidence=1), candidate(outcome=True), candidate(delivery_status="queued"), candidate(turn_index="9")]
        for key in ("raw_action", "private", "text", "id", "name", "amount", "token"):
            bad_values.append(candidate(**{key: "SECRET-CALLER-DATA"}))
        for value in bad_values:
            with self.subTest(value=value):
                with self.assertRaises(mapper.BroadcastAffectMappingError) as raised:
                    mapper.map_broadcast_outcome_candidate(value)
                self.assertEqual(str(raised.exception), "invalid broadcast affect outcome")
                self.assertNotIn("SECRET-CALLER-DATA", str(raised.exception))

    def test_unknown_pairs_statuses_and_integer_boundaries(self) -> None:
        for evidence, outcome in (("director_delivery", "game_success"), ("unknown", "callback_hit"), ("game_telemetry", "callback_hit")):
            with self.subTest(pair=(evidence, outcome)):
                with self.assertRaises(mapper.BroadcastAffectMappingError):
                    mapper.map_broadcast_outcome_candidate(candidate(evidence, outcome))
        for status in ("accepted", "queued", "selected", "scheduled", "ack", "partial", "error", "control", "failed", "Delivered", "delivered "):
            with self.subTest(status=status):
                with self.assertRaises(mapper.BroadcastAffectMappingError):
                    mapper.map_broadcast_outcome_candidate(candidate(delivery_status=status))
        for index in (False, True, -1, mapper.MAX_SAFE_INTEGER + 1, 1.0):
            with self.subTest(index=index):
                with self.assertRaises(mapper.BroadcastAffectMappingError):
                    mapper.map_broadcast_outcome_candidate(candidate(turn_index=index))
        for key in ("evidence", "outcome"):
            with self.subTest(oversized=key):
                with self.assertRaises(mapper.BroadcastAffectMappingError):
                    mapper.map_broadcast_outcome_candidate(candidate(**{key: "x" * 65}))
        self.assertEqual(mapper.map_broadcast_outcome_candidate(candidate(turn_index=0))["turn_index"], 0)
        self.assertEqual(mapper.map_broadcast_outcome_candidate(candidate(turn_index=mapper.MAX_SAFE_INTEGER))["turn_index"], mapper.MAX_SAFE_INTEGER)

    def test_closed_broadcast_and_screened_chat_extensions(self) -> None:
        expected = {
            ("director_delivery", "broadcast_start"): "broadcast_start",
            ("director_delivery", "topic_open"): "topic_open",
            ("screened_chat", "chat_question"): "chat_question",
            ("screened_chat", "chat_teasing"): "chat_teasing",
            ("screened_chat", "chat_correction"): "chat_correction",
            ("screened_chat", "chat_concern"): "chat_concern",
            ("proxy_terminal_output", "moderation_block"): "moderation_block",
            ("proxy_terminal_output", "safety_override"): "safety_override",
            ("director_delivery", "broadcast_end"): "broadcast_end",
        }
        for (evidence, outcome), kind in expected.items():
            with self.subTest(outcome=outcome):
                self.assertEqual(mapper.map_broadcast_outcome_candidate(candidate(evidence, outcome))["kind"], kind)

    def test_input_immutability_output_isolation_and_canonical_json(self) -> None:
        source = candidate()
        original = json.loads(json.dumps(source))
        first = mapper.map_broadcast_outcome_candidate(source)
        second = mapper.map_broadcast_outcome_candidate(source)
        self.assertEqual(source, original)
        self.assertIsNot(first, second)
        self.assertIsNot(first["appraisal"], second["appraisal"])
        first["appraisal"]["goal_congruence"] = -2
        self.assertEqual(second["appraisal"]["goal_congruence"], 1)
        wire_one = json.dumps(second, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        wire_two = json.dumps(mapper.map_broadcast_outcome_candidate(source), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.assertEqual(wire_one, wire_two)


class PurityAndInertnessTests(unittest.TestCase):
    def test_module_has_no_forbidden_imports(self) -> None:
        tree = ast.parse(Path(mapper.__file__).read_text(encoding="utf-8"))
        imports = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imports.update(node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
        self.assertFalse(imports & {"os", "pathlib", "time", "datetime", "requests", "sqlite3", "socket", "http", "urllib", "subprocess", "asyncio"})
        self.assertNotIn("AffectStateRuntime", Path(mapper.__file__).read_text(encoding="utf-8"))

    def test_module_runtime_ownership_fence(self) -> None:
        root = Path(__file__).resolve().parents[1]
        proxy = root / "ollama-proxy"
        targets = [path for path in proxy.glob("*.py") if path.name != Path(mapper.__file__).name and not path.name.startswith("test_")]
        targets.extend(root.glob("*.ps1"))
        targets.extend(proxy.glob("*.ps1"))
        director = root / "broadcast-director"
        if director.exists():
            targets.extend(director.rglob("*.mjs"))
            targets.extend(director.rglob("*.js"))
        allowed = {"live_broadcast_runtime.py", "ollama_proxy.py"}
        for target in targets:
            with self.subTest(target=target):
                if target.name in allowed:
                    continue
                self.assertNotIn("broadcast_affect_event_mapper", target.read_text(encoding="utf-8"))
