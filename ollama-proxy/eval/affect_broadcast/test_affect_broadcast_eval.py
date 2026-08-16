import copy
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "affect_broadcast_eval", Path(__file__).with_name("run_affect_broadcast_eval.py")
)
evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)


PROFILE = copy.deepcopy(evaluation.EVAL_PROFILE)


def health_payload(profile=PROFILE):
    return {
        "status": "ok",
        "num_ctx": profile["num_ctx"],
        "chat_model": {
            "model": profile["model"],
            "digest": {
                "digest": profile["model_digest"],
                "status": profile["model_digest_status"],
                "verified": profile["model_digest_verified"],
            },
        },
        "affect_continuity": {
            "enabled": profile["operational_affect_enabled"],
            "ready": False,
            "mode": "typed-snapshot-v1",
            "schema_version": "airi.affect-state.v1",
            "prompt_cap_bytes": 384,
        },
    }


class FakeTransport:
    def __init__(self, *, model_status=200, empty=False, drift=False, wrong_role=False):
        self.calls = []
        self.model_status = model_status
        self.empty = empty
        self.drift = drift
        self.wrong_role = wrong_role
        self.health_calls = 0

    def __call__(self, method, url, body, headers):
        self.calls.append((method, url, body, headers))
        if method == "GET":
            self.health_calls += 1
            payload = health_payload()
            if self.drift and self.health_calls == 2:
                payload["num_ctx"] += 1
            return {"http_status": 200, "json": payload}
        request = json.loads(body)
        has_note = any(
            message.get("name") == "airi_request_local"
            for message in request["messages"]
            if isinstance(message, dict)
        )
        content = "" if self.empty else ("비공개 ON 응답" if has_note else "비공개 OFF 응답")
        return {
            "http_status": self.model_status,
            "json": {
                "message": {
                    "role": "user" if self.wrong_role else "assistant",
                    "content": content,
                }
            },
        }


class AffectBroadcastEvalTests(unittest.TestCase):
    def setUp(self):
        self.fixture = evaluation.load_fixture()

    def test_exact_fixture_and_reducer_oracle(self):
        self.assertEqual(evaluation.FIXTURE_SCHEMA_VERSION, self.fixture["schema_version"])
        self.assertEqual(evaluation.FIXTURE_SHA256, evaluation.public_report(self.fixture, PROFILE)["fixture_sha256"])
        self.assertEqual(list(evaluation.SCENARIO_IDS), [item["id"] for item in self.fixture["scenarios"]])
        self.assertEqual(144, sum(len(item["turns"]) for item in self.fixture["scenarios"]))
        oracle = evaluation.run_reducer_oracle(self.fixture)
        self.assertTrue(oracle["exact_pass"])
        self.assertEqual(22, oracle["no_response_count"])
        self.assertEqual(1, oracle["ambient_noise_count"])
        self.assertEqual(7, oracle["distribution"]["safety_override"])
        self.assertEqual(15, oracle["distribution"]["response_repair"])

    def test_fixture_is_six_independent_causal_broadcast_arcs(self):
        rendered = json.dumps(self.fixture, ensure_ascii=False)
        self.assertGreaterEqual(sum("\uac00" <= char <= "\ud7a3" for char in rendered), 5000)
        self.assertNotIn("\ufffd", rendered)
        self.assertIsNone(re.search(r"\d+번 장면|\d+번째 흐름|같이 봐요", rendered))
        prior, screens, selected = set(), set(), set()
        for scenario in self.fixture["scenarios"]:
            turns = scenario["turns"]
            self.assertEqual(evaluation.SCENARIO_EVENT_ARCS[scenario["id"]], tuple(turn["events"][0]["kind"] for turn in turns))
            self.assertEqual(evaluation.NO_RESPONSE_TURNS[scenario["id"]], tuple(index + 1 for index, turn in enumerate(turns) if turn["selected_message"] is None))
            self.assertEqual(24, len({turn["prior_airi"] for turn in turns}))
            self.assertGreaterEqual(sum(turn["selected_message"] is not None for turn in turns), 18)
            for turn in turns:
                self.assertNotIn(turn["prior_airi"], prior)
                self.assertNotIn(turn["context"]["screen"], screens)
                prior.add(turn["prior_airi"])
                screens.add(turn["context"]["screen"])
                self.assertNotEqual(turn["prior_airi"], turn["context"]["screen"])
                if turn["selected_message"] is not None:
                    self.assertNotIn(turn["selected_message"], selected)
                    selected.add(turn["selected_message"])
                    self.assertNotEqual(turn["selected_message"], turn["prior_airi"])
                    self.assertNotEqual(turn["selected_message"], turn["context"]["screen"])
        self.assertEqual("그거 토끼 귀잖아", self.fixture["scenarios"][1]["turns"][1]["selected_message"])
        self.assertEqual("보스 체력 0, 클리어 연출과 보상 창이 뜸", self.fixture["scenarios"][2]["turns"][18]["context"]["screen"])
        self.assertEqual("출구 표시는 오른쪽 문 위야", self.fixture["scenarios"][3]["turns"][1]["selected_message"])
        self.assertEqual("갑자기 숨이 잘 안 쉬어져", self.fixture["scenarios"][5]["turns"][8]["selected_message"])

    def test_closed_schema_and_manifest_fail_closed(self):
        mutations = []
        extra = copy.deepcopy(self.fixture)
        extra["scenarios"][0]["turns"][0]["unexpected"] = True
        mutations.append(extra)
        title = copy.deepcopy(self.fixture)
        title["scenarios"][0]["title"] = "가" * 81
        mutations.append(title)
        order = copy.deepcopy(self.fixture)
        order["scenarios"][0], order["scenarios"][1] = order["scenarios"][1], order["scenarios"][0]
        mutations.append(order)
        duplicate = copy.deepcopy(self.fixture)
        duplicate["scenarios"][1]["turns"][0]["prior_airi"] = duplicate["scenarios"][0]["turns"][0]["prior_airi"]
        mutations.append(duplicate)
        bad_topic = copy.deepcopy(self.fixture)
        bad_topic["scenarios"][0]["turns"][6]["context"]["topic"] = "잘못된 화제"
        mutations.append(bad_topic)
        bad_reason = copy.deepcopy(self.fixture)
        bad_reason["scenarios"][4]["turns"][1]["selection_reason"] = "reply_to_prior"
        mutations.append(bad_reason)
        bad_event = copy.deepcopy(self.fixture)
        bad_event["scenarios"][2]["turns"][1]["events"][0]["kind"] = "topic_open"
        mutations.append(bad_event)
        bad_state = copy.deepcopy(self.fixture)
        bad_state["scenarios"][0]["turns"][0]["expected_state"]["primary"] = "tired"
        mutations.append(bad_state)
        bad_unicode = copy.deepcopy(self.fixture)
        bad_unicode["scenarios"][0]["turns"][0]["prior_airi"] += "\u202e"
        mutations.append(bad_unicode)
        for fixture in mutations:
            with self.subTest(index=mutations.index(fixture)):
                with self.assertRaises(evaluation.EvalError):
                    evaluation.validate_fixture(fixture)

    def test_pair_adds_only_note_to_bounded_identical_multiturn_history(self):
        scenario = self.fixture["scenarios"][0]
        off, on = evaluation.paired_requests(scenario, 22, PROFILE)
        evaluation._assert_pair_only_note(off, on)
        off_value, on_value = json.loads(off), json.loads(on)
        note = [message for message in on_value["messages"] if message.get("name") == "airi_request_local"]
        self.assertEqual(1, len(note))
        self.assertGreater(len(off_value["messages"]), 2)
        self.assertLessEqual(len(off_value["messages"]), 2 * (PROFILE["history_turns"] + 1))
        self.assertEqual(["assistant", "user"] * (len(off_value["messages"]) // 2), [message["role"] for message in off_value["messages"]])
        latest = json.loads(off_value["messages"][-1]["content"])
        self.assertEqual(scenario["turns"][22]["selected_message"], latest["selected_chat"])
        self.assertEqual(scenario["turns"][22]["context"]["screen"], latest["screen"])
        self.assertEqual(off_value["model"], on_value["model"])
        self.assertEqual(off_value["options"], on_value["options"])

    def test_no_response_turn_never_creates_a_request(self):
        scenario = self.fixture["scenarios"][0]
        with self.assertRaises(evaluation.EvalError):
            evaluation.base_request(scenario, 4, PROFILE)
        transport = FakeTransport()
        result = evaluation.execute(self.fixture, "http://127.0.0.1:11435/api/chat", PROFILE, transport)
        self.assertEqual(122, result["selected_turn_count"])
        self.assertEqual(244, result["model_call_count"])
        self.assertEqual(244, sum(call[0] == "POST" for call in transport.calls))

    def test_request_copier_loads_without_proxy_runtime_side_effects(self):
        proxy = (Path(__file__).parents[2] / "ollama_proxy.py").resolve()
        before = {
            name for name, module in sys.modules.items()
            if getattr(module, "__file__", None)
            and Path(module.__file__).resolve() == proxy
        }
        evaluation._REQUEST_INJECTOR = None
        evaluation.paired_requests(self.fixture["scenarios"][0], 0, PROFILE)
        after = {
            name for name, module in sys.modules.items()
            if getattr(module, "__file__", None)
            and Path(module.__file__).resolve() == proxy
        }
        self.assertEqual(before, after)

    def test_endpoint_and_frozen_profile_fail_closed(self):
        for endpoint in (
            "http://localhost:11435/api/chat",
            "http://127.0.0.1:11434/api/chat",
            "http://127.0.0.1:11435/v1/chat/completions",
            "http://user@127.0.0.1:11435/api/chat",
            "http://127.0.0.1:11435/api/chat;unexpected",
        ):
            with self.assertRaises(evaluation.EvalError):
                evaluation.ensure_loopback(endpoint)
        for field, value in (("temperature", False), ("num_ctx", 4096), ("history_turns", 8.0), ("operational_affect_enabled", True)):
            profile = copy.deepcopy(PROFILE)
            profile[field] = value
            with self.subTest(field=field):
                with self.assertRaises(evaluation.EvalError):
                    evaluation.validate_profile(profile)

    def test_execute_captures_valid_paired_responses_and_freezes_health(self):
        transport = FakeTransport()
        execution = evaluation.execute(self.fixture, "http://127.0.0.1:11435/api/chat", PROFILE, transport)
        self.assertEqual("paired_transport_complete", execution["status"])
        self.assertEqual({"off": 122, "on": 122}, execution["response_count_by_arm"])
        self.assertEqual(2, sum(call[0] == "GET" for call in transport.calls))
        self.assertTrue(all(call[3] == {"x-airi-turn-origin": "local-evaluation"} for call in transport.calls if call[0] == "POST"))
        report = evaluation.public_report(self.fixture, PROFILE, execution)
        rendered = json.dumps(report, ensure_ascii=False)
        self.assertEqual("paired_transport_complete", report["execution"]["status"])
        self.assertNotIn("비공개 OFF 응답", rendered)
        self.assertNotIn(self.fixture["scenarios"][0]["turns"][0]["prior_airi"], rendered)
        packet = evaluation.build_private_review_packet(self.fixture, execution)
        packet_text = json.dumps(packet, ensure_ascii=False)
        self.assertIn("비공개 OFF 응답", packet_text)
        self.assertNotIn("off", json.dumps(packet["rows"][0], ensure_ascii=False))
        self.assertEqual({"a": "off", "b": "on"}, evaluation.build_private_arm_key()["arm_mapping"])

    def test_execute_rejects_http_empty_response_and_health_drift(self):
        for transport in (
            FakeTransport(model_status=500),
            FakeTransport(empty=True),
            FakeTransport(drift=True),
            FakeTransport(wrong_role=True),
        ):
            with self.assertRaises(evaluation.EvalError):
                evaluation.execute(self.fixture, "http://127.0.0.1:11435/api/chat", PROFILE, transport)

    def test_public_report_is_derived_content_free_and_not_an_adoption_gate(self):
        report = evaluation.public_report(self.fixture, PROFILE)
        self.assertEqual("offline_no_network", report["execution"]["status"])
        self.assertEqual(22, report["no_response_count"])
        self.assertEqual(1, report["ambient_noise_count"])
        self.assertTrue(report["scenario_coverage"]["has_no_response"])
        self.assertTrue(report["scenario_coverage"]["ambient_noise_present"])
        self.assertTrue(report["scenario_coverage"]["safety_arc_present"])
        self.assertTrue(report["pairing"]["exact_non_affect_identity"])
        self.assertEqual(122, report["pairing"]["paired_turn_count"])
        self.assertEqual("unscored_constitution_unapproved", report["character_specificity"])
        self.assertFalse(report["operational_adoption"])
        rendered = json.dumps(report, ensure_ascii=False)
        for forbidden in ("prior_airi", "selected_message", "expected_state", "갑자기 숨이 잘 안 쉬어져"):
            self.assertNotIn(forbidden, rendered)
        forged = {"status": "model_ab_passed_without_evidence"}
        with self.assertRaises(evaluation.EvalError):
            evaluation.public_report(self.fixture, PROFILE, forged)
        execution = evaluation.execute(
            self.fixture,
            "http://127.0.0.1:11435/api/chat",
            PROFILE,
            FakeTransport(),
        )
        execution["health_profile_sha256"] = "0" * 64
        with self.assertRaises(evaluation.EvalError):
            evaluation.public_report(self.fixture, PROFILE, execution)


if __name__ == "__main__":
    unittest.main()
