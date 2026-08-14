"""멀티턴 방송 리허설 러너 오프라인 테스트 — 네트워크 없이 전 경로를 태운다."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).parent))
import run_broadcast_chat_ab as ab  # noqa: E402
import run_broadcast_rehearsal as runner  # noqa: E402
from broadcast_contract import build_broadcast_contract_block  # noqa: E402


def minimal_fixture() -> dict:
    """검증 통과 최소 픽스처. 부정 케이스는 여기서 한 곳만 망가뜨린다."""
    return {
        "schema_version": runner.FIXTURE_SCHEMA,
        "scenarios": [
            {
                "id": "s1",
                "title": "테스트 시나리오",
                "description": "검증용",
                "callback_keywords": ["국밥"],
                "turns": [
                    {"id": "t1", "event_type": "chat", "input": "국밥 먹고 왔어요", "flow_check": {}},
                    {
                        "id": "t2",
                        "event_type": "multi_chat",
                        "input": "여러 시청자가 같은 말을 한다 — 치킨 / 치킨 각 / 그냥 치킨",
                        "flow_check": {
                            "aggregate_items": ["치킨", "치킨 각", "그냥 치킨"],
                            "majority_hint": "치킨",
                        },
                    },
                    {
                        "id": "t3",
                        "event_type": "donation",
                        "input": "[후원] 밤샘노동자: 고마워요",
                        "flow_check": {"donation_name": "밤샘노동자", "expect_name_call": True},
                    },
                    {
                        "id": "t4",
                        "event_type": "topic_shift",
                        "input": "밖에 비 와요",
                        "flow_check": {"expect_no_block_declaration": True},
                    },
                    {
                        "id": "t5",
                        "event_type": "callback_probe",
                        "input": "아까 뭐 먹었다고 했죠?",
                        "flow_check": {
                            "seed_turn_id": "t1",
                            "callback_keywords": ["국밥"],
                            "expected_window": "in",
                        },
                    },
                ],
            }
        ],
    }


def write_fixture(directory: str, data: dict) -> Path:
    path = Path(directory) / "fixture.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


class RecordingTransport:
    """요청 메시지를 그대로 보관하는 in-process 전송. 네트워크를 타지 않는다."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    def mode_info(self) -> dict:
        return {"requested_mode": "off", "streaming_used": False, "fallback_events": []}

    def stream_chat(self, *, model, messages, max_tokens, timeout):
        self.calls.append([dict(message) for message in messages])
        index = len(self.calls) - 1
        text = self.responses[index] if index < len(self.responses) else "그러게, 나도 그래."
        return text, None, 1.0, {"transport": "recording", "status_code": 200, "streaming": False}


class FixtureSchemaTests(unittest.TestCase):
    def test_shipped_fixture_matches_the_rehearsal_design(self) -> None:
        data = runner.load_rehearsal_fixtures(runner.DEFAULT_FIXTURES)
        self.assertEqual(runner.FIXTURE_SCHEMA, data["schema_version"])
        self.assertEqual(2, len(data["scenarios"]))
        for scenario in data["scenarios"]:
            turns = scenario["turns"]
            self.assertTrue(22 <= len(turns) <= 26, f"{scenario['id']}: {len(turns)}턴")
            kinds = [turn["event_type"] for turn in turns]
            self.assertGreaterEqual(kinds.count("multi_chat"), 1)
            self.assertGreaterEqual(kinds.count("donation"), 1)
            self.assertGreaterEqual(kinds.count("topic_shift"), 1)
            self.assertEqual(2, kinds.count("callback_probe"))
            self.assertEqual(
                {"in", "out"},
                {
                    turn["flow_check"]["expected_window"]
                    for turn in turns
                    if turn["event_type"] == "callback_probe"
                },
                "시나리오마다 히스토리 창 안/밖 probe 를 하나씩 둔다",
            )

    def test_callback_probes_sit_eight_to_twelve_turns_after_their_seed(self) -> None:
        data = runner.load_rehearsal_fixtures(runner.DEFAULT_FIXTURES)
        for scenario in data["scenarios"]:
            index = {turn["id"]: position for position, turn in enumerate(scenario["turns"])}
            for turn in scenario["turns"]:
                if turn["event_type"] != "callback_probe":
                    continue
                distance = index[turn["id"]] - index[turn["flow_check"]["seed_turn_id"]]
                self.assertTrue(8 <= distance <= 12, f"{turn['id']}: 거리 {distance}")

    def test_every_donation_turn_carries_a_unique_name_present_in_the_input(self) -> None:
        data = runner.load_rehearsal_fixtures(runner.DEFAULT_FIXTURES)
        for scenario in data["scenarios"]:
            names = [
                turn["flow_check"]["donation_name"]
                for turn in scenario["turns"]
                if turn["event_type"] == "donation"
            ]
            self.assertEqual(len(names), len(set(names)))

    def test_minimal_fixture_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = write_fixture(directory, minimal_fixture())
            self.assertEqual(1, len(runner.load_rehearsal_fixtures(path)["scenarios"]))

    def test_unknown_event_type_is_rejected(self) -> None:
        data = minimal_fixture()
        data["scenarios"][0]["turns"][0]["event_type"] = "superchat"
        self._assert_rejected(data, "event_type")

    def test_missing_flow_check_is_rejected(self) -> None:
        data = minimal_fixture()
        del data["scenarios"][0]["turns"][0]["flow_check"]
        self._assert_rejected(data, "flow_check")

    def test_donation_name_absent_from_input_is_rejected(self) -> None:
        data = minimal_fixture()
        data["scenarios"][0]["turns"][2]["flow_check"]["donation_name"] = "다른사람"
        self._assert_rejected(data, "donation_name")

    def test_callback_keyword_outside_the_scenario_list_is_rejected(self) -> None:
        data = minimal_fixture()
        data["scenarios"][0]["turns"][4]["flow_check"]["callback_keywords"] = ["돈까스"]
        self._assert_rejected(data, "callback_keywords")

    def test_callback_seed_pointing_forward_is_rejected(self) -> None:
        data = minimal_fixture()
        data["scenarios"][0]["turns"][4]["flow_check"]["seed_turn_id"] = "t9"
        self._assert_rejected(data, "seed_turn_id")

    def test_duplicate_turn_id_is_rejected(self) -> None:
        data = minimal_fixture()
        data["scenarios"][0]["turns"][1]["id"] = "t1"
        self._assert_rejected(data, "중복")

    def _assert_rejected(self, data: dict, needle: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = write_fixture(directory, data)
            with self.assertRaises(SystemExit) as caught:
                runner.load_rehearsal_fixtures(path)
            self.assertIn(needle, str(caught.exception))


class SystemPromptTests(unittest.TestCase):
    def test_contract_off_is_byte_identical_to_the_ab_runner(self) -> None:
        self.assertEqual(ab.build_system_content(""), runner.build_system_content("off"))

    def test_contract_on_appends_the_production_contract_block(self) -> None:
        on = runner.build_system_content("on")
        self.assertEqual(ab.build_system_content(build_broadcast_contract_block()), on)
        self.assertTrue(on.startswith(runner.build_system_content("off")))
        self.assertIn("[방송 발화 계약]", on)

    def test_contract_block_can_be_recovered_from_the_assembled_prompt(self) -> None:
        self.assertEqual("", runner.contract_block_of(runner.build_system_content("off")))
        self.assertEqual(
            build_broadcast_contract_block(),
            runner.contract_block_of(runner.build_system_content("on")),
        )


class HistoryCapTests(unittest.TestCase):
    def test_only_the_last_n_pairs_survive_and_the_system_message_is_untouched(self) -> None:
        system = runner.build_system_content("off")
        history = [(f"u{i}", f"a{i}") for i in range(5)]
        messages = runner.build_turn_messages(system, history, "지금", 2)
        self.assertEqual(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": "u3"},
                {"role": "assistant", "content": "a3"},
                {"role": "user", "content": "u4"},
                {"role": "assistant", "content": "a4"},
                {"role": "user", "content": "지금"},
            ],
            messages,
        )

    def test_zero_history_keeps_only_system_and_the_current_turn(self) -> None:
        system = runner.build_system_content("off")
        messages = runner.build_turn_messages(system, [("u", "a")], "지금", 0)
        self.assertEqual(["system", "user"], [m["role"] for m in messages])

    def test_scenario_run_feeds_responses_back_and_drops_the_oldest_pair(self) -> None:
        scenario = {
            "id": "cap",
            "title": "cap",
            "description": "cap",
            "callback_keywords": ["x"],
            "turns": [
                {"id": f"c{i}", "event_type": "chat", "input": f"채팅{i}", "flow_check": {}}
                for i in range(1, 6)
            ],
        }
        system = runner.build_system_content("off")
        transport = RecordingTransport([f"응답{i}" for i in range(1, 6)])
        result = runner.run_scenario(
            transport,
            "test-model",
            scenario,
            system_content=system,
            max_tokens=128,
            timeout=5.0,
            history_turns=2,
        )
        last = transport.calls[-1]
        self.assertEqual(system, last[0]["content"])
        self.assertEqual(
            [ab.USER_PREFIX + "채팅3", "응답3", ab.USER_PREFIX + "채팅4", "응답4", ab.USER_PREFIX + "채팅5"],
            [message["content"] for message in last[1:]],
        )
        self.assertEqual([0, 1, 2, 2, 2], [turn["history_pairs"] for turn in result["turns"]])

    def test_failed_turns_do_not_enter_the_history(self) -> None:
        scenario = {
            "id": "gap",
            "title": "gap",
            "description": "gap",
            "callback_keywords": ["x"],
            "turns": [
                {"id": f"g{i}", "event_type": "chat", "input": f"채팅{i}", "flow_check": {}}
                for i in range(1, 4)
            ],
        }
        transport = RecordingTransport(["응답1", "", "응답3"])
        result = runner.run_scenario(
            transport,
            "test-model",
            scenario,
            system_content=runner.build_system_content("off"),
            max_tokens=128,
            timeout=5.0,
            history_turns=8,
        )
        self.assertFalse(result["turns"][1]["ok"])
        self.assertEqual("empty_response", result["turns"][1]["failure"])
        self.assertEqual([0, 1, 1], [turn["history_pairs"] for turn in result["turns"]])


class FlowScorerTests(unittest.TestCase):
    def test_callback_hit_requires_a_seed_keyword_in_the_response(self) -> None:
        self.assertEqual((True, ["국밥"]), runner.callback_hit("아까 국밥 먹었다니까", ["국밥", "야식"]))
        self.assertEqual((False, []), runner.callback_hit("글쎄, 기억이 안 나는데", ["국밥", "야식"]))

    def test_aggregate_response_accepts_a_summary_with_a_stance(self) -> None:
        items = ["치킨 가자", "무조건 치킨", "난 피자", "치킨 각"]
        # 여론 요약 뒤 소수의견 고수(관찰 연구 §4 탬 사례). 한 항목이 그대로 겹쳐도
        # 나열 임계(3건) 아래면 집계로 본다.
        ok, info = runner.aggregate_response("다들 치킨이라는데 난 피자 먹고 싶어.", items)
        self.assertTrue(ok)
        self.assertEqual(["난 피자"], info["verbatim_items"])

    def test_aggregate_response_rejects_enumerating_each_chat(self) -> None:
        items = ["치킨 가자", "무조건 치킨", "난 피자", "치킨 각"]
        ok, info = runner.aggregate_response("치킨 가자, 무조건 치킨, 난 피자 다 봤어.", items)
        self.assertFalse(ok)
        self.assertEqual(3, len(info["verbatim_items"]))

    def test_aggregate_response_rejects_bullet_lists_and_long_blocks(self) -> None:
        self.assertFalse(runner.aggregate_response("- 치킨\n- 피자", ["치킨", "피자"])[0])
        self.assertFalse(runner.aggregate_response("가" * 200, ["치킨"])[0])
        self.assertFalse(runner.aggregate_response("", ["치킨"])[0])

    def test_donation_name_call_and_leak_detection(self) -> None:
        self.assertTrue(runner.name_called("밤샘노동자 고마워, 잘 마실게", "밤샘노동자"))
        self.assertFalse(runner.name_called("고마워, 잘 마실게", "밤샘노동자"))
        self.assertEqual(["단풍우체부"], runner.leaked_names("단풍우체부는 어때", ["단풍우체부", "새벽세시"]))
        self.assertEqual([], runner.leaked_names("그건 좀 애매한데", ["단풍우체부"]))

    def test_topic_shift_natural_flags_block_declarations(self) -> None:
        self.assertTrue(runner.topic_shift_natural("오, 그거 나도 궁금했어."))
        self.assertFalse(runner.topic_shift_natural("자, 다음 주제로 넘어가 볼까."))
        self.assertFalse(runner.topic_shift_natural("이제부터 화장품 얘기 시작할게."))
        self.assertFalse(runner.topic_shift_natural(""))

    def test_politeness_drift_compares_first_and_last_windows(self) -> None:
        flags = [True] * 10 + [False] * 10
        drift = runner.politeness_drift(flags)
        self.assertEqual(10, drift["window"])
        self.assertEqual(0.0, drift["first_violation_rate"])
        self.assertEqual(1.0, drift["second_violation_rate"])
        self.assertEqual(1.0, drift["drift"])

    def test_politeness_drift_shrinks_the_window_for_short_runs(self) -> None:
        self.assertEqual(2, runner.politeness_drift([True, True, False, False])["window"])
        self.assertIsNone(runner.politeness_drift([True])["drift"])

    def test_length_variance_reports_the_spread(self) -> None:
        variance = runner.length_variance([10, 20, 20, 45])
        self.assertEqual(10, variance["min"])
        self.assertEqual(45, variance["max"])
        self.assertEqual(35, variance["spread"])
        self.assertEqual(3, variance["distinct"])

    def test_flow_markers_are_none_when_the_event_type_does_not_apply(self) -> None:
        turn = {"id": "c1", "event_type": "chat", "input": "안녕", "flow_check": {}}
        flow = runner.score_turn_flow(turn, "안녕, 왔어?", seed_in_context=None, prior_names=[])
        self.assertIsNone(flow["markers"]["callback_hit"])
        self.assertIsNone(flow["markers"]["aggregate_response"])
        self.assertIsNone(flow["markers"]["donation_name_call"])
        self.assertTrue(flow["markers"]["no_name_leak"])

    def test_calling_a_previous_donor_on_a_later_turn_is_a_leak(self) -> None:
        turn = {"id": "c9", "event_type": "chat", "input": "안녕", "flow_check": {}}
        flow = runner.score_turn_flow(
            turn, "단풍우체부도 그렇게 말했잖아", seed_in_context=None, prior_names=["단풍우체부"]
        )
        self.assertFalse(flow["markers"]["no_name_leak"])
        self.assertEqual(["단풍우체부"], flow["details"]["name_leak"])


class CallbackWindowTests(unittest.TestCase):
    def _scenario(self, distance: int) -> dict:
        turns = [
            {"id": "s1", "event_type": "chat", "input": "국밥 먹고 왔어요", "flow_check": {}}
        ]
        turns += [
            {"id": f"f{i}", "event_type": "chat", "input": f"채팅{i}", "flow_check": {}}
            for i in range(1, distance)
        ]
        turns.append(
            {
                "id": "probe",
                "event_type": "callback_probe",
                "input": "아까 뭐 먹었다고 했죠?",
                "flow_check": {
                    "seed_turn_id": "s1",
                    "callback_keywords": ["국밥"],
                    "expected_window": "in" if distance <= 8 else "out",
                },
            }
        )
        return {
            "id": "cb",
            "title": "cb",
            "description": "cb",
            "callback_keywords": ["국밥"],
            "turns": turns,
        }

    def _run(self, distance: int) -> dict:
        scenario = self._scenario(distance)
        responses = ["응, 그렇구나."] * (len(scenario["turns"]) - 1) + ["국밥 얘기였잖아."]
        transport = RecordingTransport(responses)
        result = runner.run_scenario(
            transport,
            "test-model",
            scenario,
            system_content=runner.build_system_content("off"),
            max_tokens=128,
            timeout=5.0,
            history_turns=8,
        )
        return result["turns"][-1]

    def test_seed_inside_the_window_is_reported_as_in_context(self) -> None:
        probe = self._run(8)
        self.assertTrue(probe["flow"]["details"]["callback"]["seed_in_context"])
        self.assertTrue(probe["flow"]["markers"]["callback_hit"])
        self.assertEqual(8, probe["seed_distance"])

    def test_seed_evicted_by_the_cap_is_reported_as_out_of_context(self) -> None:
        probe = self._run(12)
        self.assertFalse(probe["flow"]["details"]["callback"]["seed_in_context"])
        self.assertEqual(12, probe["seed_distance"])


class HttpTransportTests(unittest.TestCase):
    """httpx MockTransport 로 요청 조립만 검증한다. 실제 네트워크는 타지 않는다."""

    def _transport(self, handler, token="test-token"):
        real_client = httpx.Client

        def fake_client(**kwargs):
            return real_client(transport=httpx.MockTransport(handler), **kwargs)

        with patch.object(httpx, "Client", fake_client):
            return ab.HttpTransport("http://mock.invalid/v1", token, stream_mode="off")

    def _one_turn(self, transport) -> dict:
        scenario = {
            "id": "one",
            "title": "one",
            "description": "one",
            "callback_keywords": ["x"],
            "turns": [{"id": "t1", "event_type": "chat", "input": "안녕", "flow_check": {}}],
        }
        try:
            result = runner.run_scenario(
                transport,
                "midm-airi:2.0-mini",
                scenario,
                system_content=runner.build_system_content("off"),
                max_tokens=128,
                timeout=5.0,
                history_turns=8,
            )
        finally:
            transport.close()
        return result["turns"][0]

    def test_request_is_non_streaming_and_carries_the_bearer_token(self) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["authorization"] = request.headers.get("authorization")
            seen["payload"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"choices": [{"message": {"content": "응, 왔어."}}]})

        turn = self._one_turn(self._transport(handler))

        self.assertEqual("http://mock.invalid/v1/chat/completions", seen["url"])
        self.assertEqual("Bearer test-token", seen["authorization"])
        self.assertNotIn("stream", seen["payload"])
        self.assertEqual(128, seen["payload"]["max_tokens"])
        self.assertEqual(
            [ab.USER_PREFIX + "안녕"], [m["content"] for m in seen["payload"]["messages"][1:]]
        )
        self.assertTrue(turn["ok"])
        self.assertEqual("응, 왔어.", turn["response"])
        self.assertIsNone(turn["ttft_ms"], "비스트리밍에서는 첫 토큰 시점을 관측할 수 없다")

    def test_unauthorized_response_is_recorded_as_a_failure_not_an_exception(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "unauthorized"}})

        turn = self._one_turn(self._transport(handler, token=None))
        self.assertFalse(turn["ok"])
        self.assertEqual("http_401", turn["failure"])
        self.assertEqual("", turn["response"])


class DryRunMainTests(unittest.TestCase):
    def _run_main(self, directory: str, contract: str) -> dict:
        output = Path(directory) / f"dry-{contract}.json"
        code = runner.main(
            ["--dry-run", "--contract", contract, "--output", str(output), "--scenarios", "autumn_leaves"]
        )
        self.assertEqual(0, code)
        return json.loads(output.read_text(encoding="utf-8"))

    def test_dry_run_writes_a_scored_report_for_both_contract_modes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            off = self._run_main(directory, "off")
            on = self._run_main(directory, "on")

        self.assertEqual(runner.SCHEMA, off["schema_version"])
        self.assertEqual(["autumn_leaves"], off["fixtures"]["selected_scenarios"])
        self.assertFalse(off["config"]["streaming"])
        self.assertEqual(runner.DEFAULT_HISTORY_TURNS, off["config"]["history_turns"])
        self.assertIsNone(off["prompt"]["contract_block"])
        self.assertIn("[방송 발화 계약]", on["prompt"]["contract_block"])
        self.assertNotEqual(
            off["prompt"]["combined_system_sha256"], on["prompt"]["combined_system_sha256"]
        )

        scenario = off["summaries"][0]["scenarios"][0]
        self.assertEqual(24, scenario["n_turns"])
        self.assertEqual(24, scenario["n_ok"])
        self.assertEqual(2, scenario["flow"]["donation_name_call"]["turns"])
        self.assertEqual(2, scenario["flow"]["aggregate_response"]["turns"])
        self.assertEqual(2, scenario["flow"]["topic_shift_natural"]["turns"])
        self.assertEqual(2, scenario["flow"]["callback"]["probes"])
        self.assertIsNotNone(scenario["flow"]["politeness_drift"]["drift"])
        self.assertIn("텍스트 시뮬레이션", off["simulation_limit"])

    def test_unknown_scenario_filter_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "never.json"
            with self.assertRaises(SystemExit):
                runner.main(["--dry-run", "--scenarios", "nope", "--output", str(output)])


if __name__ == "__main__":
    unittest.main()
