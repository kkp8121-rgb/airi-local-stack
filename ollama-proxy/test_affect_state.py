import ast
import copy
import json
from pathlib import Path
import threading
import unittest

from affect_state import (AffectStateRuntime, AffectValidationError, CONTINUITY_PROMPT_CAP_BYTES, EVENT_SCHEMA_VERSION,
                          CAUSE_VALUES, DRIVE_VALUES, FAMILIARITY_VALUES, KIND_VALUES,
                          MAX_SAFE_INTEGER, MAX_SESSIONS, PRIMARY_VALUES, _KIND_WEIGHT_MAX,
                          initial_state, reduce_affect, render_continuity_snapshot,
                          validate_event, validate_state)


def event(kind="chat_question", turn=1, weight=1, **changes):
    result = {"schema_version": EVENT_SCHEMA_VERSION, "source": "screened_chat",
              "kind": kind, "appraisal": {"goal_congruence": 0, "agency": "audience", "control": 1, "novelty": 1, "social_tone": "neutral"}, "weight": weight, "turn_index": turn}
    result.update(changes)
    if kind not in ("chat_question", "chat_teasing", "chat_correction", "chat_concern"):
        result["source"] = "broadcast_director" if kind in ("topic_open", "callback_hit", "callback_miss", "donation_received", "game_success", "game_failure") else "system"
    if kind in ("response_repair", "moderation_block"):
        result["source"] = "proxy_outcome"
    return result


class AffectStateTests(unittest.TestCase):
    def test_affect_snapshot_is_closed_bounded_and_actionable(self):
        longest = initial_state()
        longest.update({
            "primary": "playful_annoyed", "valence": -2, "arousal": 2,
            "dominance": -1, "intensity": 2, "cause": "donation_received",
            "remaining_turns": 4, "drive": "challenge_playfully",
            "audience_familiarity": "familiar", "version": MAX_SAFE_INTEGER,
        })
        rendered = render_continuity_snapshot(longest)
        self.assertLessEqual(len(rendered.encode("utf-8")), CONTINUITY_PROMPT_CAP_BYTES)
        self.assertIn("schema=airi.affect-state.v1", rendered)
        self.assertIn("감정명은 말하지 말고", rendered)
        for forbidden in ("free text", "session-id", "displayName", "provider_id"):
            self.assertNotIn(forbidden, rendered)

    def test_state_enums_ranges_and_exact_keys(self):
        for primary in PRIMARY_VALUES:
            state = initial_state(); state["primary"] = primary
            self.assertEqual(validate_state(state)["primary"], primary)
        for key, values in (("drive", DRIVE_VALUES), ("cause", CAUSE_VALUES),
                            ("audience_familiarity", FAMILIARITY_VALUES)):
            for value in values:
                state = initial_state(); state[key] = value
                self.assertEqual(validate_state(state)[key], value)
        for key, value in (("valence", 3), ("arousal", -1), ("dominance", 2), ("intensity", 3), ("remaining_turns", 5)):
            state = initial_state(); state[key] = value
            with self.assertRaises(AffectValidationError): validate_state(state)
        for bad in (True, 1.0, "1"):
            state = initial_state(); state["version"] = bad
            with self.assertRaises(AffectValidationError): validate_state(state)
        state = initial_state(); state["extra"] = "no"
        with self.assertRaises(AffectValidationError): validate_state(state)
        del state["extra"]; del state["drive"]
        with self.assertRaises(AffectValidationError): validate_state(state)

    def test_event_enums_bounds_unknown_missing_and_booleans(self):
        for kind in KIND_VALUES:
            if kind in ("broadcast_start", "silence", "topic_change", "safety_override", "broadcast_end"):
                source = "system"
            elif kind in ("response_repair", "moderation_block"):
                source = "proxy_outcome"
            elif kind.startswith("chat_"):
                source = "screened_chat"
            else: source = "broadcast_director"
            candidate = event(kind, source=source); candidate["source"] = source
            self.assertEqual(validate_event(candidate)["kind"], kind)
        candidate = event(); candidate["unknown"] = "x"
        with self.assertRaises(AffectValidationError): validate_event(candidate)
        candidate = event(); del candidate["weight"]
        with self.assertRaises(AffectValidationError): validate_event(candidate)
        for key, value in (("weight", True), ("turn_index", True)):
            candidate = event(); candidate[key] = value
            with self.assertRaises(AffectValidationError): validate_event(candidate)
        candidate = event(); candidate["appraisal"]["control"] = True
        with self.assertRaises(AffectValidationError): validate_event(candidate)
        candidate = event(); candidate["source"] = "system"
        with self.assertRaises(AffectValidationError): validate_event(candidate)

    def test_appraisal_enums_bounds_and_types(self):
        for agency in ("self", "audience", "external", "none"):
            candidate = event(); candidate["appraisal"]["agency"] = agency
            self.assertEqual(validate_event(candidate)["appraisal"]["agency"], agency)
        for tone in ("neutral", "supportive", "teasing", "hostile"):
            candidate = event(); candidate["appraisal"]["social_tone"] = tone
            self.assertEqual(validate_event(candidate)["appraisal"]["social_tone"], tone)
        for key, bad in (("goal_congruence", -3), ("control", 3), ("novelty", -1)):
            candidate = event(); candidate["appraisal"][key] = bad
            with self.assertRaises(AffectValidationError): validate_event(candidate)
        candidate = event(); candidate["appraisal"]["extra"] = 1
        with self.assertRaises(AffectValidationError): validate_event(candidate)

    def test_each_appraisal_field_is_strict_at_every_boundary(self):
        bounds = {"goal_congruence": (-2, 2), "control": (0, 2), "novelty": (0, 2)}
        for key, (lower, upper) in bounds.items():
            for value in (lower, upper):
                candidate = event(); candidate["appraisal"][key] = value
                self.assertEqual(validate_event(candidate)["appraisal"][key], value)
            for value in (lower - 1, upper + 1, True, 1.0, "1"):
                candidate = event(); candidate["appraisal"][key] = value
                with self.assertRaises(AffectValidationError): validate_event(candidate)
        for key in ("agency", "social_tone"):
            for value in ("invalid", True, 1, 1.0, None):
                candidate = event(); candidate["appraisal"][key] = value
                with self.assertRaises(AffectValidationError): validate_event(candidate)

    def test_every_numeric_boundary_and_safe_integer(self):
        state_bounds = {"valence": (-2, 2), "arousal": (0, 2), "dominance": (-1, 1),
                        "intensity": (0, 2), "remaining_turns": (0, 4),
                        "version": (0, MAX_SAFE_INTEGER)}
        for key, (lower, upper) in state_bounds.items():
            for value in (lower, upper):
                state = initial_state(); state[key] = value; self.assertEqual(validate_state(state)[key], value)
            for value in (lower - 1, upper + 1, True, 1.0, "1"):
                state = initial_state(); state[key] = value
                with self.assertRaises(AffectValidationError): validate_state(state)
        event_bounds = {"weight": (0, 2), "turn_index": (0, MAX_SAFE_INTEGER)}
        for key, (lower, upper) in event_bounds.items():
            for value in (lower, upper):
                candidate = event("game_failure") if key == "weight" else event()
                candidate[key] = value; self.assertEqual(validate_event(candidate)[key], value)
            for value in (lower - 1, upper + 1, True, 1.0, "1"):
                candidate = event(); candidate[key] = value
                with self.assertRaises(AffectValidationError): validate_event(candidate)
        with self.assertRaises(AffectValidationError): AffectStateRuntime(max_sessions=MAX_SESSIONS + 1)

    def test_one_step_limit_for_all_kinds_and_weights(self):
        state = initial_state(); state.update({"valence": 1, "arousal": 1, "dominance": 0,
                                               "intensity": 2, "remaining_turns": 4,
                                               "primary": "pleased", "drive": "celebrate"})
        for kind in KIND_VALUES:
            for weight in range(_KIND_WEIGHT_MAX[kind] + 1):
                result = reduce_affect(state, event(kind, 1, weight))
                for axis in ("valence", "arousal", "dominance", "intensity"):
                    self.assertLessEqual(abs(result[axis] - state[axis]), 1, (kind, weight, axis))

    def test_exact_turn_and_silence_decay_and_zero_weight_behavior(self):
        state = initial_state(); state.update({"primary": "playful_annoyed", "valence": -1,
                                               "arousal": 1, "intensity": 2, "remaining_turns": 3,
                                               "drive": "challenge_playfully", "cause": "chat_teasing"})
        zero = reduce_affect(state, event("chat_question", 1, 0))
        self.assertEqual((zero["primary"], zero["intensity"], zero["remaining_turns"]),
                         ("playful_annoyed", 1, 2))
        silent = reduce_affect(state, event("silence", 1, 2))
        self.assertEqual((silent["intensity"], silent["remaining_turns"]), (1, 2))
        runtime = AffectStateRuntime(); runtime.apply_event("turns", event("chat_teasing", 1, 1))
        after_gap = runtime.apply_event("turns", event("chat_question", 4, 0))
        self.assertEqual((after_gap["intensity"], after_gap["remaining_turns"]), (0, 0))

    def test_sanitized_ids_errors_lru_neutrality_and_input_copy(self):
        runtime = AffectStateRuntime(max_sessions=2)
        for bad in (" ", " a", "a ", "a\x00", "a\u0085", "a\u202e", "a\ud800", "e\u0301"):
            with self.assertRaises(AffectValidationError) as raised: runtime.snapshot_if_present(bad)
            self.assertEqual(str(raised.exception), "session_id must be a bounded non-empty string")
        malicious = event(); malicious["raw secret key"] = "raw secret value"
        with self.assertRaises(AffectValidationError) as raised: validate_event(malicious)
        self.assertNotIn("secret", str(raised.exception))
        runtime.apply_event("a", event("chat_question", 1)); runtime.apply_event("b", event("chat_question", 1))
        runtime.snapshot_if_present("a"); runtime.version_if_present("a")
        with self.assertRaises(AffectValidationError): runtime.apply_event("a", event("chat_question", 1))
        runtime.apply_event("c", event("chat_question", 1))
        self.assertIsNone(runtime.snapshot_if_present("a"))
        self.assertIsNotNone(runtime.snapshot_if_present("b"))
        candidate = event("chat_question", 2); runtime.apply_event("b", candidate)
        candidate["appraisal"]["agency"] = "external"
        self.assertNotEqual(runtime._sessions["b"]["events"][-1]["appraisal"]["agency"], "external")

    def test_session_id_size_nfc_and_state_schema_are_strict(self):
        runtime = AffectStateRuntime(session_id_limit=4)
        self.assertIsNone(runtime.snapshot_if_present("abcd"))
        for value in ("abcde", "e\u0301"):
            with self.assertRaises(AffectValidationError) as raised: runtime.snapshot_if_present(value)
            self.assertEqual(str(raised.exception), "session_id must be a bounded non-empty string")
        self.assertIsNone(AffectStateRuntime().snapshot_if_present("é"))
        state = initial_state(); state["schema_version"] = "wrong"
        with self.assertRaises(AffectValidationError): validate_state(state)

    def test_exact_ring_health_concurrency_and_no_forbidden_imports(self):
        runtime = AffectStateRuntime(max_sessions=2, ring_limit=2)
        runtime.apply_event("one", event("chat_question", 1)); runtime.apply_event("one", event("chat_question", 2)); runtime.apply_event("one", event("chat_question", 3))
        self.assertEqual(len(runtime._sessions["one"]["events"]), 2)
        self.assertEqual(set(runtime.health()), {"enabled", "sessions", "max_sessions", "events", "state_version", "primary_enum_count", "drive_enum_count"})
        self.assertTrue(all(isinstance(value, (bool, int)) for value in runtime.health().values()))
        runtime = AffectStateRuntime(); gates = [threading.Event() for _ in range(9)]; errors = []
        def ordered(index):
            gates[index].wait()
            try: runtime.apply_event("ordered", event("chat_question", index + 1))
            except Exception as exc: errors.append(exc)
            finally: gates[index + 1].set()
        threads = [threading.Thread(target=ordered, args=(index,)) for index in range(8)]
        for thread in threads: thread.start()
        gates[0].set()
        for thread in threads: thread.join()
        self.assertEqual(errors, []); self.assertEqual(runtime.version_if_present("ordered"), 8)
        tree = ast.parse(Path(__file__).with_name("affect_state.py").read_text(encoding="utf-8"))
        banned = {"socket", "requests", "urllib", "http", "sqlite3", "sqlalchemy", "ollama", "torch", "transformers", "time", "datetime"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): self.assertFalse({alias.name.split(".")[0] for alias in node.names} & banned)
            if isinstance(node, ast.ImportFrom): self.assertNotIn((node.module or "").split(".")[0], banned)

    def test_kind_weight_caps_and_strict_schema_matrix(self):
        for kind, maximum in _KIND_WEIGHT_MAX.items():
            self.assertEqual(validate_event(event(kind, weight=maximum))["weight"], maximum)
            candidate = event(kind, weight=maximum + 1)
            with self.assertRaises(AffectValidationError): validate_event(candidate)
        for key in ("schema_version", "source", "kind", "appraisal", "weight", "turn_index"):
            candidate = event(); del candidate[key]
            with self.assertRaises(AffectValidationError): validate_event(candidate)
        for key in ("goal_congruence", "agency", "control", "novelty", "social_tone"):
            candidate = event(); del candidate["appraisal"][key]
            with self.assertRaises(AffectValidationError): validate_event(candidate)
        for key in ("schema_version", "primary", "valence", "arousal", "dominance", "intensity", "cause", "remaining_turns", "drive", "audience_familiarity", "version"):
            state = initial_state(); del state[key]
            with self.assertRaises(AffectValidationError): validate_state(state)
        for bad_event in ({**event(), "schema_version": "wrong"}, {**event(), "source": "bad"}, {**event(), "kind": "bad"}):
            with self.assertRaises(AffectValidationError): validate_event(bad_event)
        for key, value in (("primary", "bad"), ("cause", "bad"), ("drive", "bad"), ("audience_familiarity", "bad")):
            state = initial_state(); state[key] = value
            with self.assertRaises(AffectValidationError): validate_state(state)

    def test_decay_repair_safety_end_and_max_version_invariants(self):
        state = initial_state(); state.update({"primary": "competitive", "valence": -2, "arousal": 2,
                                               "dominance": 1, "intensity": 2, "remaining_turns": 4,
                                               "drive": "challenge_playfully", "cause": "game_failure"})
        for turn in range(1, 6): state = reduce_affect(state, event("chat_question", turn, 0))
        self.assertEqual((state["primary"], state["valence"], state["arousal"], state["dominance"], state["intensity"], state["remaining_turns"], state["cause"]),
                         ("neutral", 0, 0, 0, 0, 0, "none"))
        repaired = reduce_affect(initial_state(), event("response_repair", 1, 2))
        self.assertEqual(repaired["intensity"], 1)
        locked = reduce_affect(initial_state(), event("safety_override", 1, 2))
        held = reduce_affect(locked, event("donation_received", 2, 1))
        self.assertEqual((held["cause"], held["drive"]), ("safety_override", "deescalate"))
        state = initial_state(); state["version"] = MAX_SAFE_INTEGER
        self.assertEqual(reduce_affect(state, event())["version"], MAX_SAFE_INTEGER)
        runtime = AffectStateRuntime(); final = runtime.apply_event("ended", event("broadcast_end", 1, 1))
        self.assertEqual(final["cause"], "broadcast_end"); self.assertIsNone(runtime.snapshot_if_present("ended"))
        fresh = runtime.apply_event("ended", event("chat_question", 1, 1))
        self.assertEqual(fresh["version"], 1)

    def test_canonical_determinism_and_128_ring_limit(self):
        state, candidate = initial_state(), event("game_failure", 1, 2)
        left = json.dumps(reduce_affect(state, candidate), sort_keys=True, separators=(",", ":"))
        right = json.dumps(reduce_affect(state, candidate), sort_keys=True, separators=(",", ":"))
        self.assertEqual(left, right)
        with self.assertRaises(AffectValidationError): AffectStateRuntime(ring_limit=129)
        runtime = AffectStateRuntime(ring_limit=128)
        for turn in range(1, 130): runtime.apply_event("ring", event("chat_question", turn, 1))
        self.assertEqual(len(runtime._sessions["ring"]["events"]), 128)

    def test_active_targets_and_safety_lock_refresh_exactly(self):
        first = reduce_affect(initial_state(), event("game_failure", 1, 2))
        second = reduce_affect(first, event("game_failure", 2, 2))
        self.assertEqual((first["intensity"], first["remaining_turns"]), (1, 1))
        self.assertEqual((second["intensity"], second["remaining_turns"]), (2, 2))
        self.assertLessEqual(second["intensity"] - first["intensity"], 1)
        weak_one = reduce_affect(initial_state(), event("chat_question", 1, 1))
        weak_two = reduce_affect(weak_one, event("chat_question", 2, 1))
        self.assertEqual((weak_one["intensity"], weak_two["intensity"]), (1, 1))
        safety_one = reduce_affect(initial_state(), event("safety_override", 1, 2))
        safety_two = reduce_affect(safety_one, event("safety_override", 2, 2))
        self.assertEqual((safety_two["cause"], safety_two["drive"], safety_two["remaining_turns"]),
                         ("safety_override", "deescalate", 2))
        locked = reduce_affect(safety_two, event("response_repair", 3, 2))
        self.assertEqual((locked["cause"], locked["drive"], locked["remaining_turns"]),
                         ("safety_override", "deescalate", 1))

    def test_zero_weight_safety_and_repair_duration_semantics(self):
        safe = reduce_affect(initial_state(), event("safety_override", 1, 0))
        self.assertEqual((safe["primary"], safe["drive"], safe["valence"], safe["arousal"], safe["intensity"], safe["remaining_turns"]),
                         ("concerned", "deescalate", -1, 1, 1, 1))
        held = reduce_affect(safe, event("silence", 2, 0))
        self.assertEqual((held["cause"], held["drive"]), ("safety_override", "deescalate"))
        state = initial_state(); state.update({"primary": "disappointed", "drive": "repair", "cause": "callback_miss",
                                               "valence": -2, "intensity": 2, "remaining_turns": 2})
        inactive = reduce_affect(state, event("response_repair", 1, 0))
        self.assertEqual(inactive["cause"], "callback_miss")
        repair_one = reduce_affect(initial_state(), event("response_repair", 1, 1))
        repair_two = reduce_affect(initial_state(), event("response_repair", 1, 2))
        self.assertEqual((repair_one["intensity"], repair_one["remaining_turns"]), (1, 1))
        self.assertEqual((repair_two["intensity"], repair_two["remaining_turns"]), (1, 1))
        repair_two_again = reduce_affect(repair_two, event("response_repair", 2, 2))
        self.assertEqual((repair_two_again["intensity"], repair_two_again["remaining_turns"]), (1, 2))

    def test_extrema_success_recovery_and_all_primaries_reachable(self):
        failure_one = reduce_affect(initial_state(), event("game_failure", 1, 2))
        failure_two = reduce_affect(failure_one, event("game_failure", 2, 2))
        self.assertEqual((failure_two["valence"], failure_two["arousal"]), (-2, 2))
        success_one = reduce_affect(initial_state(), event("game_success", 1, 2))
        success_two = reduce_affect(success_one, event("game_success", 2, 2))
        self.assertEqual((success_two["valence"], success_two["arousal"]), (2, 2))
        weak_one = reduce_affect(initial_state(), event("game_success", 1, 1))
        weak_two = reduce_affect(weak_one, event("game_success", 2, 1))
        self.assertEqual((weak_two["valence"], weak_two["arousal"], weak_two["intensity"]), (1, 1, 1))
        disappointed = reduce_affect(initial_state(), event("callback_miss", 1, 1))
        recovered = reduce_affect(disappointed, event("game_success", 2, 1))
        proud = reduce_affect(recovered, event("game_success", 3, 1))
        self.assertEqual((disappointed["primary"], recovered["primary"], proud["primary"]),
                         ("disappointed", "relieved", "proud"))
        embarrassed = reduce_affect(initial_state(), event("chat_teasing", 1, 1))
        self.assertEqual(embarrassed["primary"], "embarrassed")
        self.assertEqual(reduce_affect(embarrassed, event("game_success", 2, 1))["primary"], "relieved")
        sequences = {
            "neutral": [event("silence", 1, 0)], "curious": [event("topic_open", 1, 1)],
            "amused": [event("callback_hit", 1, 1)], "pleased": [event("donation_received", 1, 1)],
            "proud": [event("game_success", 1, 1)], "embarrassed": [event("chat_teasing", 1, 1)],
            "skeptical": [event("chat_correction", 1, 1)], "playful_annoyed": [event("chat_teasing", 1, 1), event("chat_teasing", 2, 1)],
            "concerned": [event("chat_concern", 1, 1)], "disappointed": [event("callback_miss", 1, 1)],
            "competitive": [event("game_failure", 1, 1)], "relieved": [event("response_repair", 1, 1)],
            "tired": [event("broadcast_end", 1, 1)],
        }
        for primary, events in sequences.items():
            state = initial_state()
            for candidate in events: state = reduce_affect(state, candidate)
            self.assertEqual(state["primary"], primary)

    def test_pure_deterministic_copy_safe_saturation_and_inertia(self):
        state, candidate = initial_state(), event("chat_teasing", weight=1)
        original_state, original_event = copy.deepcopy(state), copy.deepcopy(candidate)
        first, second = reduce_affect(state, candidate), reduce_affect(state, candidate)
        self.assertEqual(first, second); self.assertEqual(state, original_state); self.assertEqual(candidate, original_event)
        for turn in range(2, 8): first = reduce_affect(first, event("chat_teasing", turn, 1))
        self.assertEqual(first["valence"], -1); self.assertEqual(first["intensity"], 1)
        first["intensity"] = 2
        weak = event("donation_received", 9, 1); weak["source"] = "broadcast_director"
        self.assertEqual(reduce_affect(first, weak)["primary"], "playful_annoyed")

    def test_decay_repair_and_safety(self):
        state = initial_state()
        state = reduce_affect(state, event("game_failure", 1, 2))
        repaired = reduce_affect(state, event("response_repair", 2))
        self.assertEqual(repaired["primary"], "relieved")
        silent = reduce_affect(repaired, event("silence", 3))
        self.assertLessEqual(silent["intensity"], repaired["intensity"])
        safe = reduce_affect(repaired, event("safety_override", 4, 0))
        self.assertEqual((safe["primary"], safe["drive"]), ("concerned", "deescalate"))

    def test_runtime_isolation_lru_ring_reset_and_monotonicity(self):
        runtime = AffectStateRuntime(max_sessions=2, ring_limit=2)
        runtime.apply_event("a", event("chat_question", 1))
        runtime.apply_event("a", event("chat_question", 2))
        with self.assertRaises(AffectValidationError): runtime.apply_event("a", event("chat_question", 2))
        runtime.apply_event("b", event("chat_question", 1)); runtime.apply_event("c", event("chat_question", 1))
        self.assertIsNone(runtime.snapshot_if_present("a")); self.assertIsNotNone(runtime.snapshot_if_present("b"))
        runtime.apply_event("b", event("chat_question", 2)); runtime.apply_event("b", event("chat_question", 3))
        self.assertLessEqual(runtime.health()["events"], 4)
        snapshot = runtime.snapshot_if_present("b"); snapshot["primary"] = "tired"
        self.assertNotEqual(runtime.snapshot_if_present("b")["primary"], "tired")
        self.assertTrue(runtime.reset_session("b")); self.assertIsNone(runtime.snapshot_if_present("b"))

    def test_concurrency_and_content_free_health(self):
        runtime = AffectStateRuntime()
        errors = []
        def apply(index):
            try: runtime.apply_event("shared", event("chat_question", index + 1))
            except AffectValidationError: pass
            except Exception as exc: errors.append(exc)
        threads = [threading.Thread(target=apply, args=(index,)) for index in range(32)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertFalse(errors); self.assertIsNotNone(runtime.snapshot_if_present("shared"))
        health = runtime.health()
        rendered = repr(health).lower()
        for forbidden in ("raw", "text", "name", "provider", "amount", "shared"):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
