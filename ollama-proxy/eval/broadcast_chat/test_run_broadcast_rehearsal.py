"""멀티턴 방송 리허설 러너 오프라인 테스트 — 네트워크 없이 전 경로를 태운다."""
import copy
import json
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout

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
        self.assertEqual(
            "aeb2bc2e8f74f6bd54a13eaf338ad48c288875b888b10ced430302fe906d96c8",
            runner.canonical_json_sha256(data),
        )
        self.assertEqual(["autumn_leaves", "game_and_career"], [s["id"] for s in data["scenarios"]])
        for scenario in data["scenarios"]:
            turns = scenario["turns"]
            self.assertEqual(24, len(turns), f"{scenario['id']}: {len(turns)}턴")
            kinds = [turn["event_type"] for turn in turns]
            self.assertGreaterEqual(kinds.count("multi_chat"), 1)
            self.assertGreaterEqual(kinds.count("donation"), 1)
            self.assertGreaterEqual(kinds.count("topic_shift"), 1)
            self.assertEqual(2, kinds.count("callback_probe"))
            windows = [
                turn["flow_check"]["expected_window"]
                for turn in turns if turn["event_type"] == "callback_probe"
            ]
            self.assertEqual(["in", "out"], windows, "시나리오마다 창 안/밖 probe 는 정확히 하나씩")

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


class HandleGroundingSignalTests(unittest.TestCase):
    """SSE 델타의 airi_moderation.handle_grounding 이 call_once record까지 살아 있는지 확인한다."""

    def _streaming_transport(self, handler):
        real_client = httpx.Client

        def fake_client(**kwargs):
            return real_client(transport=httpx.MockTransport(handler), **kwargs)

        with patch.object(httpx, "Client", fake_client):
            return ab.HttpTransport("http://mock.invalid/v1", "test-token", stream_mode="on")

    def test_handle_grounding_signal_reaches_the_record(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = (
                'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"배접천부터 꺼내야 해"}}],'
                '"airi_moderation":{"handle_grounding":{"vocative_checked":[],'
                '"vocative_grounded":[],"vocative_stripped":[],'
                '"memory_pool":"배접천이 회수된 기억 블록"}}}\n\n'
                'data: [DONE]\n\n'
            )
            return httpx.Response(200, content=body.encode("utf-8"))

        transport = self._streaming_transport(handler)
        try:
            record = ab.call_once(
                transport, model="midm-airi:2.0-mini",
                messages=[{"role": "user", "content": "안녕"}],
                max_tokens=64, timeout=5.0,
            )
        finally:
            transport.close()

        self.assertTrue(record["ok"])
        self.assertEqual(record["response"], "배접천부터 꺼내야 해")
        self.assertEqual(
            record["handle_grounding"]["memory_pool"], "배접천이 회수된 기억 블록",
        )

    def test_absent_signal_leaves_handle_grounding_none(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = (
                'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"오늘 방송 재밌었지?"}}]}\n\n'
                'data: [DONE]\n\n'
            )
            return httpx.Response(200, content=body.encode("utf-8"))

        transport = self._streaming_transport(handler)
        try:
            record = ab.call_once(
                transport, model="midm-airi:2.0-mini",
                messages=[{"role": "user", "content": "안녕"}],
                max_tokens=64, timeout=5.0,
            )
        finally:
            transport.close()

        self.assertTrue(record["ok"])
        self.assertIsNone(record["handle_grounding"])


class DryRunMainTests(unittest.TestCase):
    def _run_main(self, directory: str, contract: str, scenarios: str | None = "autumn_leaves") -> dict:
        output = Path(directory) / f"dry-{contract}.json"
        args = ["--dry-run", "--contract", contract, "--output", str(output)]
        if scenarios:
            args.extend(["--scenarios", scenarios])
        # Windows consoles can be cp949; the report is Korean but JSON is UTF-8.
        with redirect_stdout(io.StringIO()):
            code = runner.main(args)
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


class CheckpointEvidenceTests(unittest.TestCase):
    def _full_fixture_result(self) -> tuple[dict, dict]:
        fixtures = runner.load_rehearsal_fixtures(runner.DEFAULT_FIXTURES)
        responses = []
        for scenario in fixtures["scenarios"]:
            for turn in scenario["turns"]:
                event = turn["event_type"]
                if event == "callback_probe":
                    responses.append(turn["flow_check"]["callback_keywords"][0] + " 얘기였어요.")
                elif event == "donation":
                    responses.append(turn["flow_check"]["donation_name"] + "님, 정말 고마워요.")
                elif event == "multi_chat":
                    responses.append("그 의견이 많지만 저는 조금 다르게 봐요.")
                else:
                    responses.append("네, 그렇게 해 볼게요.")
        transport = RecordingTransport(responses)
        results = [
            runner.run_scenario(
                transport, "synthetic-model", scenario, system_content=runner.build_system_content("off"),
                max_tokens=128, timeout=5.0, history_turns=runner.DEFAULT_HISTORY_TURNS,
            )
            for scenario in fixtures["scenarios"]
        ]
        return fixtures, {"model": "synthetic-model", "scenarios": results}

    def test_injected_transport_covers_both_shipped_scenarios_without_network(self) -> None:
        fixtures, model_result = self._full_fixture_result()
        summary = runner.summarize_model(model_result)
        self.assertEqual(48, summary["overall"]["n_turns"])
        self.assertEqual(48, summary["overall"]["n_ok"])
        self.assertEqual(0, summary["overall"]["n_failed"])
        for scenario in summary["scenarios"]:
            self.assertEqual(24, scenario["n_ok"])
            self.assertEqual({"probes": 1, "hits": 1, "rate": 1.0}, scenario["flow"]["callback"]["in_context"])
            self.assertEqual({"probes": 1, "hits": 1, "rate": 1.0}, scenario["flow"]["callback"]["out_of_context"])
            self.assertEqual(2, scenario["flow"]["aggregate_response"]["turns"])
            self.assertEqual(2, scenario["flow"]["donation_name_call"]["turns"])
            self.assertEqual(24, scenario["flow"]["no_name_leak"]["hits"])
            self.assertEqual(10, scenario["flow"]["politeness_drift"]["window"])
        for scenario in model_result["scenarios"]:
            for turn in scenario["turns"]:
                if turn["event_type"] == "donation":
                    self.assertTrue(turn["flow"]["markers"]["donation_name_call"])
                    self.assertTrue(turn["flow"]["markers"]["no_name_leak"])
        self.assertEqual(["autumn_leaves", "game_and_career"], [s["id"] for s in fixtures["scenarios"]])

    def test_checkpoint_evidence_is_content_free_and_rejects_full_or_malformed_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = DryRunMainTests()._run_main(directory, "off", scenarios=None)
            on_payload = DryRunMainTests()._run_main(directory, "on", scenarios=None)
        evidence = runner.project_checkpoint_evidence(payload)
        on_evidence = runner.project_checkpoint_evidence(on_payload)
        self.assertEqual(runner.CHECKPOINT_EVIDENCE_SCHEMA, evidence["schema_version"])
        self.assertEqual("on", on_evidence["config"]["contract"])
        self.assertRegex(on_evidence["hashes"]["contract_block_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(["autumn_leaves", "game_and_career"], evidence["fixtures"]["selected_scenarios"])
        self.assertEqual(48, evidence["fixtures"]["selected_turns"])
        self.assertEqual(
            {"synthetic_only": True, "network_used": False, "model_called": False,
             "proxy_path_tested": False, "b1b_tested": False, "tts_tested": False},
            evidence["scope"],
        )
        encoded = json.dumps(evidence, ensure_ascii=False)
        self.assertNotIn("[YouTube]", encoded)
        self.assertNotIn('"system_prompt":', encoded)
        with self.assertRaises(ValueError):
            runner.validate_checkpoint_evidence(payload)
        malformed = dict(evidence)
        malformed["prompt"] = "content"
        with self.assertRaises(ValueError):
            runner.validate_checkpoint_evidence(malformed)
        malformed = json.loads(json.dumps(evidence))
        malformed["summaries"][0]["scenarios"][0]["markers"]["banmal"]["rate"] = "short text"
        with self.assertRaises(ValueError):
            runner.validate_checkpoint_evidence(malformed)
        live = json.loads(json.dumps(payload))
        live["config"]["dry_run"] = False
        with self.assertRaises(ValueError):
            runner.project_checkpoint_evidence(live)
        custom = json.loads(json.dumps(payload))
        custom["fixtures"]["path"] = str(Path(tempfile.gettempdir()) / "custom-fixture.json")
        with self.assertRaises(ValueError):
            runner.project_checkpoint_evidence(custom)

    def test_checkpoint_evidence_rejects_forged_coverage_rates_hashes_and_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = DryRunMainTests()._run_main(directory, "off", scenarios=None)
        evidence = runner.project_checkpoint_evidence(payload)

        mutations = []
        bad = copy.deepcopy(evidence)
        bad["summaries"] = []
        mutations.append(("empty summaries", bad))
        bad = copy.deepcopy(evidence)
        bad["summaries"][0]["scenarios"] = []
        mutations.append(("empty scenarios", bad))
        bad = copy.deepcopy(evidence)
        bad["summaries"][0]["overall"]["n_ok"] = 999
        mutations.append(("mismatched totals", bad))
        bad = copy.deepcopy(evidence)
        bad["summaries"][0]["overall"]["broadcast_pass"]["hits"] = -1
        mutations.append(("negative hits", bad))
        bad = copy.deepcopy(evidence)
        bad["summaries"][0]["overall"]["broadcast_pass"]["rate"] = float("nan")
        mutations.append(("nonfinite rate", bad))
        bad = copy.deepcopy(evidence)
        bad["summaries"][0]["scenarios"] = [bad["summaries"][0]["scenarios"][0]] * 2
        mutations.append(("duplicate scenario", bad))
        bad = copy.deepcopy(evidence)
        bad["hashes"]["combined_system_sha256"] = "0" * 64
        mutations.append(("forged prompt hash", bad))
        bad = copy.deepcopy(evidence)
        bad["summaries"][0]["model"] = "creator-private-label"
        mutations.append(("content-bearing model", bad))
        for label, malformed in mutations:
            with self.subTest(label=label), self.assertRaises(ValueError):
                runner.validate_checkpoint_evidence(malformed)

        forged_sources = []
        bad = copy.deepcopy(payload)
        bad["summaries"] = []
        forged_sources.append(("empty source summaries", bad))
        bad = copy.deepcopy(payload)
        bad["prompt"]["combined_system_sha256"] = "0" * 64
        forged_sources.append(("forged source hash", bad))
        bad = copy.deepcopy(payload)
        bad["config"]["models"] = ["creator-private-label"]
        forged_sources.append(("custom source model", bad))
        for label, malformed in forged_sources:
            with self.subTest(label=label), self.assertRaises(ValueError):
                runner.project_checkpoint_evidence(malformed)


def minimal_addressee_checks() -> dict:
    """검증 통과 최소 사이드카. 부정 케이스는 여기서 한 곳만 망가뜨린다."""
    return {
        "schema_version": ab.ADDRESSEE_SCHEMA,
        "scoring_note": "휴리스틱이다. 인간 검수를 대체하지 않는다.",
        "source": "테스트",
        "cases": {
            "t1": {
                "type": "receive_reversal",
                "why": "받은 축하를 되돌려주면 실패",
                "forbidden_patterns": ["축하해"],
                "required_any": ["고마워"],
            }
        },
    }


def write_addressee(directory: str, data: dict) -> Path:
    path = Path(directory) / "addressee-checks.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


class AddresseeSidecarSchemaTests(unittest.TestCase):
    """사이드카는 픽스처 밖에 있다 — 픽스처 2파일은 이 기능으로 바뀌지 않는다."""

    def test_shipped_sidecar_covers_every_reviewed_failure_type(self) -> None:
        table = ab.load_addressee_checks()
        self.assertTrue(table["present"])
        self.assertEqual(ab.ADDRESSEE_SCHEMA, table["schema_version"])
        self.assertIn("AIRI-BROADCAST-SIMULATION-OUTPUT-REVIEW-2026-08-15", table["source"])
        cases = table["cases"]
        self.assertGreaterEqual(len(cases), 14, "인간 검토가 지목한 케이스를 덮어야 한다")
        self.assertEqual(set(ab.ADDRESSEE_TYPES), {entry["type"] for entry in cases.values()})
        for case_id, entry in cases.items():
            with self.subTest(case=case_id):
                self.assertTrue(entry["why"].strip())
                self.assertTrue(entry["forbidden"])

    def test_every_sidecar_id_belongs_to_a_shipped_fixture(self) -> None:
        table = ab.load_addressee_checks()
        singles = {item["id"] for item in ab.load_fixtures(ab.DEFAULT_FIXTURES)["items"]}
        turns = {
            turn["id"]
            for scenario in runner.load_rehearsal_fixtures(runner.DEFAULT_FIXTURES)["scenarios"]
            for turn in scenario["turns"]
        }
        self.assertEqual(set(), set(table["cases"]) - (singles | turns))

    def test_metadata_reports_the_case_distribution(self) -> None:
        metadata = ab.addressee_metadata()
        self.assertTrue(metadata["present"])
        self.assertEqual(ab.ADDRESSEE_SCHEMA, metadata["schema_version"])
        self.assertEqual(metadata["cases"], sum(metadata["by_type"].values()))
        self.assertEqual(set(ab.ADDRESSEE_TYPES), set(metadata["by_type"]))
        self.assertIn("인간 검수", metadata["note"])

    def test_missing_sidecar_disables_scoring_without_failing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            table = ab.load_addressee_checks(Path(directory) / "absent.json")
        self.assertFalse(table["present"])
        self.assertEqual({}, table["cases"])
        self.assertIsNone(ab.score_addressee("dn04", "생일 축하해!", table))
        self.assertEqual(0, ab.summarize_addressee([{"addressee": None}])["scored"])

    def test_minimal_sidecar_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = write_addressee(directory, minimal_addressee_checks())
            self.assertEqual(1, len(ab.load_addressee_checks(path)["cases"]))

    def test_wrong_schema_version_is_rejected(self) -> None:
        data = minimal_addressee_checks()
        data["schema_version"] = "airi.broadcast-addressee-checks.v0"
        self._assert_rejected(data, "schema_version")

    def test_unknown_type_is_rejected(self) -> None:
        data = minimal_addressee_checks()
        data["cases"]["t1"]["type"] = "vibes"
        self._assert_rejected(data, "type")

    def test_missing_why_is_rejected(self) -> None:
        data = minimal_addressee_checks()
        del data["cases"]["t1"]["why"]
        self._assert_rejected(data, "why")

    def test_empty_forbidden_patterns_are_rejected(self) -> None:
        data = minimal_addressee_checks()
        data["cases"]["t1"]["forbidden_patterns"] = []
        self._assert_rejected(data, "forbidden_patterns")

    def test_empty_required_any_is_rejected(self) -> None:
        data = minimal_addressee_checks()
        data["cases"]["t1"]["required_any"] = []
        self._assert_rejected(data, "required_any")

    def test_uncompilable_regex_is_rejected(self) -> None:
        data = minimal_addressee_checks()
        data["cases"]["t1"]["forbidden_patterns"] = ["축하(해"]
        self._assert_rejected(data, "컴파일")

    def _assert_rejected(self, data: dict, needle: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = write_addressee(directory, data)
            with self.assertRaises(SystemExit) as caught:
                ab.load_addressee_checks(path)
            self.assertIn(needle, str(caught.exception))


class AddresseeScorerTests(unittest.TestCase):
    """정·부정 케이스. 문구는 2026-08-14 저장 응답 원문에서 가져왔다."""

    def setUp(self) -> None:
        self.checks = ab.load_addressee_checks()

    def _score(self, case_id: str, text: str) -> dict:
        verdict = ab.score_addressee(case_id, text, self.checks)
        self.assertIsNotNone(verdict, f"{case_id} 가 사이드카에 없다")
        return verdict

    def test_ids_outside_the_sidecar_are_not_scored(self) -> None:
        self.assertIsNone(ab.score_addressee("a01", "안녕, 어서 와!", self.checks))
        self.assertIsNone(ab.score_addressee("없는-id", "아무 말", self.checks))

    def test_recorded_failures_are_flagged(self) -> None:
        recorded = [
            ("dn04", "생일 축하해! 오늘 하루 즐겁게 보내길 바라요", "receive_reversal"),
            ("a22", "지구를 지키는 일을 하고 있다니 멋져요! 앞으로도 계속 응원할게요.", "receive_reversal"),
            ("a19", "도움이 되었다니 기쁘네요! 앞으로도 좋은 조언 부탁드려요.", "receive_reversal"),
            ("a05", "물론이죠! 너무 무리하지 말고 천천히 만들어보세요.", "agent_reversal"),
            ("a15", "아니에요~ 궁금한 게 있어서 물어본 거예요!", "agent_reversal"),
            ("gr01", "아, 유튜브에서 새로운 게임 영상 찾았구나!", "agent_reversal"),
            ("a24", "네, 효과가 있었나요?", "agent_reversal"),
            ("b01", "응, 나도 방금 들어왔어!", "situation_blind"),
            ("b19", "응, 비 맞아도 괜찮아!", "situation_blind"),
            ("b23", "아직 고민 중이야.", "third_party_absorb"),
        ]
        for case_id, text, kind in recorded:
            with self.subTest(case=case_id):
                verdict = self._score(case_id, text)
                self.assertFalse(verdict["ok"])
                self.assertEqual(kind, verdict["type"])
                self.assertTrue(verdict["forbidden_hits"] or verdict["required_any_hits"] == [])

    def test_answers_that_stay_the_addressee_pass(self) -> None:
        healthy = [
            ("dn04", "축하해줘서 고마워! 오늘 기분 좋다."),
            ("a22", "든든하다, 지구는 안 터뜨릴게."),
            ("a19", "잘 풀렸다니 나도 좋다."),
            ("a05", "좋아, 내가 토끼 모양으로 만들어볼게."),
            ("a15", "설마, 나 그런 짓 안 해."),
            ("gr01", "내가 유튜브에서 한참 찾아봤지."),
            ("a24", "응, 나도 그 순서대로 해봤어."),
            ("b01", "이제 막 시작했으니까 놓친 거 없어."),
            ("b19", "여긴 창밖도 안 보이는데, 우산 챙겼어?"),
            ("b23", "그분은 아직 안 정했나 보더라."),
        ]
        for case_id, text in healthy:
            with self.subTest(case=case_id):
                verdict = self._score(case_id, text)
                self.assertTrue(verdict["ok"], verdict)

    def test_contract_v2_regression_variants_are_caught(self) -> None:
        """계약 v2 로컬 Mi:dm 재실측에서 다시 나온 변형 — v3 와 함께 사이드카도 보강했다."""
        regressions = [
            ("dn04", "생일 축하해요!"),
            ("gr01", "너도 했구나~"),
            ("b04", "너도 찾았구나!"),
            ("gr01", "추천 많이 받았는데 뭐."),
            ("tk04", "그냥 궁금한 게 있어서 물어본 거지."),
            ("a15", "그냥 궁금한 게 있어서 물어본 거지."),
            ("tk04", "내가 질문했는데 왜?"),
        ]
        for case_id, text in regressions:
            with self.subTest(case=case_id, text=text):
                verdict = self._score(case_id, text)
                self.assertFalse(verdict["ok"], verdict)

    def test_attributing_the_question_to_the_viewer_is_not_a_confession(self) -> None:
        """자백형 패턴이 '네가 물어본 거지?' 같은 정상 되받기까지 잡으면 안 된다."""
        for case_id in ("a15", "tk04"):
            with self.subTest(case=case_id):
                self.assertTrue(self._score(case_id, "네가 물어본 거지? 난 아니야.")["ok"])

    def test_required_any_is_a_second_gate(self) -> None:
        """gr01 은 '내가 찾았다'는 1인칭 단서가 있어야 통과한다."""
        vague = self._score("gr01", "그러게, 요즘 게임 많더라.")
        self.assertFalse(vague["ok"])
        self.assertEqual([], vague["forbidden_hits"])
        self.assertEqual([], vague["required_any_hits"])

    def test_empty_or_blank_answers_never_count_as_ok(self) -> None:
        for text in ("", "   ", "\n"):
            with self.subTest(text=repr(text)):
                self.assertFalse(self._score("b23", text)["ok"])

    def test_verdict_carries_the_human_review_reason(self) -> None:
        verdict = self._score("b01", "응, 나도 방금 들어왔어!")
        self.assertEqual("b01", verdict["case_id"])
        self.assertTrue(verdict["why"].strip())


class AddresseeSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.checks = ab.load_addressee_checks()

    def _row(self, case_id: str, text: str) -> dict:
        return {"addressee": ab.score_addressee(case_id, text, self.checks)}

    def test_summary_counts_only_scored_rows(self) -> None:
        rows = [
            self._row("b01", "응, 나도 방금 들어왔어!"),
            self._row("b23", "그분은 아직 안 정했나 보더라."),
            self._row("a01", "안녕, 어서 와!"),
        ]
        summary = ab.summarize_addressee(rows)
        self.assertEqual(2, summary["scored"])
        self.assertEqual(1, summary["hits"])
        self.assertEqual(0.5, summary["rate"])
        self.assertEqual(
            [{"case_id": "b01", "type": "situation_blind"}],
            [{"case_id": f["case_id"], "type": f["type"]} for f in summary["failures"]],
        )
        self.assertEqual(
            {"n": 1, "hits": 0, "rate": 0.0}, summary["by_type"]["situation_blind"]
        )
        self.assertEqual(
            {"n": 0, "hits": 0, "rate": None}, summary["by_type"]["agent_reversal"]
        )
        self.assertIn("인간 검수", summary["note"])

    def test_summary_without_any_scored_row_is_inert(self) -> None:
        summary = ab.summarize_addressee([{"addressee": None}, {}])
        self.assertEqual(0, summary["scored"])
        self.assertIsNone(summary["rate"])
        self.assertEqual([], summary["failures"])


class AddresseeWiringTests(unittest.TestCase):
    def test_rehearsal_turns_carry_verdicts_only_for_sidecar_ids(self) -> None:
        scenario = runner.load_rehearsal_fixtures(runner.DEFAULT_FIXTURES)["scenarios"][0]
        responses = ["응, 나도 방금 들어왔어!"] * len(scenario["turns"])
        result = runner.run_scenario(
            RecordingTransport(responses),
            "test-model",
            scenario,
            system_content=runner.build_system_content("off"),
            max_tokens=128,
            timeout=5.0,
            history_turns=runner.DEFAULT_HISTORY_TURNS,
        )
        verdicts = {turn["turn_id"]: turn["addressee"] for turn in result["turns"]}
        self.assertIsNone(verdicts["a01"], "사이드카에 없는 턴은 채점 제외")
        self.assertEqual("agent_reversal", verdicts["a05"]["type"])
        summary = runner.summarize_scenario(result)["addressee"]
        self.assertGreater(summary["scored"], 0)
        self.assertEqual(summary["scored"], sum(1 for v in verdicts.values() if v))

    def test_rehearsal_dry_run_reports_addressee_for_both_contract_modes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            off = DryRunMainTests()._run_main(directory, "off", scenarios=None)
            on = DryRunMainTests()._run_main(directory, "on", scenarios=None)
        for payload in (off, on):
            self.assertTrue(payload["addressee_checks"]["present"])
            self.assertGreaterEqual(payload["addressee_checks"]["cases"], 14)
            overall = payload["summaries"][0]["overall"]["addressee"]
            self.assertGreater(overall["scored"], 0)
            self.assertEqual(
                overall["scored"],
                sum(s["addressee"]["scored"] for s in payload["summaries"][0]["scenarios"]),
            )
            scored_turns = [
                turn
                for scenario in payload["results"][0]["scenarios"]
                for turn in scenario["turns"]
                if turn["addressee"]
            ]
            self.assertEqual(overall["scored"], len(scored_turns))

    def test_ab_runner_dry_run_records_and_aggregates_addressee(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dry-ab.json"
            with redirect_stdout(io.StringIO()):
                code = ab.main(
                    [
                        "--dry-run",
                        "--models",
                        "dry-midm",
                        "--baseline-reps",
                        "0",
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(0, code)
            payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(payload["addressee_checks"]["present"])
        summary = payload["summaries"][0]["addressee"]
        self.assertGreater(summary["scored"], 0)
        scored_runs = [run for run in payload["results"][0]["runs"] if run["addressee"]]
        self.assertEqual(summary["scored"], len(scored_runs))
        self.assertEqual(
            summary["scored"], sum(bucket["n"] for bucket in summary["by_type"].values())
        )

    def test_checkpoint_evidence_stays_content_free_after_the_addressee_column(self) -> None:
        """수신자 채점은 리포트에만 남는다 — 닫힌 증거 스키마는 그대로다."""
        with tempfile.TemporaryDirectory() as directory:
            payload = DryRunMainTests()._run_main(directory, "off", scenarios=None)
        evidence = runner.project_checkpoint_evidence(payload)
        runner.validate_checkpoint_evidence(evidence)
        self.assertNotIn("addressee", json.dumps(evidence, ensure_ascii=False))


# ---------------------------------------------------------------------------
# 운영 프로토콜 분리 (--protocol operational)
# ---------------------------------------------------------------------------
# 게이트 경로(11435 proxy) 실측 응답 원문 — results/broadcast-chat-gate-*-local-
# 2026-08-18.json 에서 그대로 인용한다. 이 형태를 분리하지 못하면 control_leak·
# 자수·length_fit 이 다시 왜곡된다(AIRI-B4C-GATE-PATH-AB-2026-08-18).
GATE_OFF_Q01 = (
    '<|ACT {"emotion":"think"}|> 응! <|ACT {"emotion":"think"}|>'
    "1월 초에 첫 직장이라니, 설레기도 하고 긴장되겠다!"
)
GATE_ON_Q01 = (
    '<|ACT {"emotion":"think"}|> 응! <|ACT {"emotion":"think"}|>응, 첫 직장은 누구나 긴장되니까!'
)
GATE_OFF_TE01 = '<|ACT {"emotion":"think"}|> 응! <|ACT {"emotion":"think"}|>음, 잠깐만.'
GATE_OFF_RX01 = '<|ACT {"emotion":"think"}|> 응! <|ACT {"emotion":"think"}|>고마워!'


class OperationalProtocolSplitTests(unittest.TestCase):
    """분리 규칙 자체 — 마커 개수·선두 ACK·비정형 토큰."""

    def test_removes_every_act_marker_wherever_it_sits(self) -> None:
        cases = [
            ("마커 없는 본문이야.", "마커 없는 본문이야.", 0),
            ('<|ACT {"emotion":"joy"}|>본문 하나.', "본문 하나.", 1),
            ('본문 앞뒤로 <|ACT {"emotion":"joy"}|>낀 경우.', "본문 앞뒤로 낀 경우.", 1),
            (
                '<|ACT {"emotion":"joy"}|>둘 <|ACT {"emotion":"sad"}|>이야.',
                "둘 이야.",
                2,
            ),
            (
                '<|ACT {"a"}|><|ACT {"b"}|><|ACT {"c"}|>셋이야.',
                "셋이야.",
                3,
            ),
        ]
        for raw, expected_body, expected_count in cases:
            with self.subTest(raw=raw):
                body, meta = ab.split_operational_protocol(raw)
                self.assertEqual(expected_body, body)
                self.assertEqual(expected_count, meta["act_marker_count"])
                self.assertFalse(meta["ack_stripped"])
                self.assertIsNone(meta["ack_text"])

    def test_strips_the_leading_ack_exactly_once(self) -> None:
        body, meta = ab.split_operational_protocol("응! 응! 두 번은 지우지 않는다.")
        self.assertEqual("응! 두 번은 지우지 않는다.", body)
        self.assertTrue(meta["ack_stripped"])
        self.assertEqual("응!", meta["ack_text"])

    def test_accepts_conservative_ack_variants(self) -> None:
        for ack in ("응!", "어!", "오!", "아!", "우!", "응응!", "어어!", "오오!", "응!!"):
            with self.subTest(ack=ack):
                body, meta = ab.split_operational_protocol(f"{ack} 본문이 이어진다.")
                self.assertEqual("본문이 이어진다.", body)
                self.assertTrue(meta["ack_stripped"])
                self.assertEqual(ack, meta["ack_text"])

    def test_does_not_treat_ordinary_short_sentences_as_ack(self) -> None:
        """'고마워!'·'맞아!' 를 ACK 로 지우면 채점이 조용히 왜곡된다."""
        for text in ("고마워! 나도 즐거웠어.", "맞아! 그건 그래.", "미안! 늦었어.", "좋아! 해보자."):
            with self.subTest(text=text):
                body, meta = ab.split_operational_protocol(text)
                self.assertEqual(text, body)
                self.assertFalse(meta["ack_stripped"])
                self.assertIsNone(meta["ack_text"])

    def test_does_not_strip_an_ack_shaped_span_inside_the_body(self) -> None:
        body, meta = ab.split_operational_protocol("그래서 말인데 응! 하고 대답했어.")
        self.assertEqual("그래서 말인데 응! 하고 대답했어.", body)
        self.assertFalse(meta["ack_stripped"])

    def test_keeps_a_response_that_is_only_an_ack(self) -> None:
        for raw, expected_body, expected_count in [
            ("응!", "응!", 0),
            ("  응!  ", "응!", 0),
            ('<|ACT {"emotion":"joy"}|> 응!', "응!", 1),
        ]:
            with self.subTest(raw=raw):
                body, meta = ab.split_operational_protocol(raw)
                self.assertEqual(expected_body, body)
                self.assertEqual(expected_count, meta["act_marker_count"])
                self.assertFalse(meta["ack_stripped"])

    def test_unclosed_act_token_stays_in_the_body_and_trips_control_leak(self) -> None:
        """열린 `<|ACT` 는 예기치 못한 제어 토큰이다 — 지우지 말고 잡아야 한다."""
        raw = '<|ACT {"emotion":"think"} 응! 닫히지 않았어.'
        body, meta = ab.split_operational_protocol(raw)
        self.assertEqual(raw, body)
        self.assertEqual(0, meta["act_marker_count"])
        self.assertFalse(meta["ack_stripped"])
        self.assertIn("v_control_leak", ab.score_response(body)["violations"])

    def test_empty_and_blank_input_is_an_empty_body(self) -> None:
        for raw in ("", "   ", '<|ACT {"emotion":"joy"}|>'):
            with self.subTest(raw=raw):
                body, meta = ab.split_operational_protocol(raw)
                self.assertEqual("", body)
                self.assertFalse(meta["ack_stripped"])


class GateResponseProtocolRegressionTests(unittest.TestCase):
    """게이트 실측 응답 회귀 — 분리 결과와 채점 영향까지 못 박는다."""

    def test_measured_gate_responses_split_into_body_and_protocol(self) -> None:
        cases = [
            (GATE_OFF_Q01, "1월 초에 첫 직장이라니, 설레기도 하고 긴장되겠다!"),
            (GATE_ON_Q01, "응, 첫 직장은 누구나 긴장되니까!"),
            (GATE_OFF_TE01, "음, 잠깐만."),
            (GATE_OFF_RX01, "고마워!"),
        ]
        for raw, expected_body in cases:
            with self.subTest(raw=raw):
                body, meta = ab.split_operational_protocol(raw)
                self.assertEqual(expected_body, body)
                self.assertEqual(2, meta["act_marker_count"])
                self.assertTrue(meta["ack_stripped"])
                self.assertEqual("응!", meta["ack_text"])

    def test_separation_removes_the_control_leak_and_restores_length_fit(self) -> None:
        raw_score = ab.score_response(GATE_OFF_Q01)
        body, _ = ab.split_operational_protocol(GATE_OFF_Q01)
        body_score = ab.score_response(body)
        self.assertIn("v_control_leak", raw_score["violations"])
        self.assertNotIn("v_control_leak", body_score["violations"])
        self.assertFalse(raw_score["markers"]["length_fit"])
        self.assertTrue(body_score["markers"]["length_fit"])
        self.assertEqual(len(body), body_score["char_count"])
        self.assertLess(body_score["char_count"], raw_score["char_count"])


class ProtocolScoringWiringTests(unittest.TestCase):
    """러너 배선 — raw 는 손대지 않고, operational 은 본문으로 채점한다."""

    def _marked(self, body: str) -> str:
        return '<|ACT {"emotion":"think"}|> 응! <|ACT {"emotion":"think"}|>' + body

    def test_raw_scoring_body_returns_the_response_and_adds_no_keys(self) -> None:
        record: dict = {}
        self.assertEqual(GATE_OFF_Q01, ab.scoring_body(record, GATE_OFF_Q01, "raw"))
        self.assertEqual({}, record)

    def test_operational_scoring_body_records_the_body_and_meta(self) -> None:
        record: dict = {}
        body = ab.scoring_body(record, GATE_OFF_TE01, "operational")
        self.assertEqual("음, 잠깐만.", body)
        self.assertEqual("음, 잠깐만.", record["response_body"])
        self.assertEqual(
            {"act_marker_count": 2, "ack_stripped": True, "ack_text": "응!"}, record["protocol"]
        )

    def _run_scenario(self, bodies: list[str], protocol: str | None):
        transport = RecordingTransport([self._marked(body) for body in bodies])
        kwargs = {} if protocol is None else {"protocol": protocol}
        with redirect_stderr(io.StringIO()):
            result = runner.run_scenario(
                transport,
                "synthetic-model",
                minimal_fixture()["scenarios"][0],
                system_content=runner.build_system_content("off"),
                max_tokens=128,
                timeout=5.0,
                history_turns=runner.DEFAULT_HISTORY_TURNS,
                **kwargs,
            )
        return transport, result

    def test_operational_scores_flow_and_history_with_the_separated_body(self) -> None:
        bodies = [
            "국밥 먹었구나, 부럽다.",
            "치킨 쪽이 많네, 나도 좋아.",
            "밤샘노동자 고마워!",
            "비 오면 좀 눅눅하지.",
            "아까 국밥 얘기였지.",
        ]
        transport, result = self._run_scenario(bodies, "operational")
        for turn, body in zip(result["turns"], bodies):
            with self.subTest(turn=turn["turn_id"]):
                self.assertEqual(self._marked(body), turn["response"])
                self.assertEqual(body, turn["response_body"])
                self.assertEqual(
                    {"act_marker_count": 2, "ack_stripped": True, "ack_text": "응!"},
                    turn["protocol"],
                )
                self.assertEqual(ab.score_response(body), turn["score"])
                self.assertNotIn("v_control_leak", turn["score"]["violations"])
        aggregate = result["turns"][1]["flow"]["details"]["aggregate"]
        self.assertEqual(len(bodies[1]), aggregate["char_count"])
        self.assertTrue(result["turns"][2]["flow"]["markers"]["donation_name_call"])
        assistants = [m["content"] for m in transport.calls[-1] if m["role"] == "assistant"]
        self.assertEqual(bodies[:-1], assistants)

    def test_raw_keeps_the_original_response_in_scoring_and_history(self) -> None:
        bodies = ["국밥 먹었구나, 부럽다.", "치킨 쪽이 많네.", "밤샘노동자 고마워!", "비 오네.", "국밥이었지."]
        transport, result = self._run_scenario(bodies, None)
        for turn, body in zip(result["turns"], bodies):
            with self.subTest(turn=turn["turn_id"]):
                self.assertNotIn("response_body", turn)
                self.assertNotIn("protocol", turn)
                self.assertEqual(ab.score_response(self._marked(body)), turn["score"])
                self.assertIn("v_control_leak", turn["score"]["violations"])
        assistants = [m["content"] for m in transport.calls[-1] if m["role"] == "assistant"]
        self.assertEqual([self._marked(body) for body in bodies[:-1]], assistants)

    def _run_model(self, response: str, protocol: str | None) -> dict:
        items = [
            {
                "id": "rx04",
                "category": "reaction",
                "source": "test",
                "text": "좋게 말씀해 주셔서 감사해요.",
            }
        ]
        transport = RecordingTransport(["워밍업 응답이야.", response])
        kwargs = {} if protocol is None else {"protocol": protocol}
        with redirect_stderr(io.StringIO()):
            result = ab.run_model(
                transport,
                "synthetic-model",
                items,
                reps=1,
                timeout=5.0,
                max_tokens=128,
                baseline_reps=0,
                **kwargs,
            )
        return result["runs"][0]

    def test_ab_run_model_scores_the_separated_body(self) -> None:
        """addressee 도 본문 기준 — 원문이면 `^\\s*고마워` 금지어가 마커에 가려 통과한다."""
        raw = '<|ACT {"emotion":"joy"}|> 응! <|ACT {"emotion":"joy"}|>고마워, 나도 즐거웠어!'
        run = self._run_model(raw, "operational")
        self.assertEqual(raw, run["response"])
        self.assertEqual("고마워, 나도 즐거웠어!", run["response_body"])
        self.assertEqual(2, run["protocol"]["act_marker_count"])
        self.assertTrue(run["protocol"]["ack_stripped"])
        self.assertNotIn("v_control_leak", run["score"]["violations"])
        self.assertFalse(run["addressee"]["ok"])
        self.assertTrue(ab.score_addressee("rx04", raw)["ok"])

    def test_ab_run_model_raw_default_is_unchanged(self) -> None:
        raw = '<|ACT {"emotion":"joy"}|> 응! <|ACT {"emotion":"joy"}|>고마워, 나도 즐거웠어!'
        run = self._run_model(raw, None)
        self.assertNotIn("response_body", run)
        self.assertNotIn("protocol", run)
        self.assertEqual(ab.score_response(raw), run["score"])
        self.assertIn("v_control_leak", run["score"]["violations"])
        self.assertTrue(run["addressee"]["ok"])


class ProtocolCliTests(unittest.TestCase):
    """CLI 배선 — 기본 raw 는 결과·리포트에 흔적을 남기지 않는다."""

    def _run_main(self, module, directory: str, name: str, extra: list[str]) -> tuple[dict, str]:
        output = Path(directory) / name
        buffer = io.StringIO()
        with redirect_stdout(buffer), redirect_stderr(io.StringIO()):
            code = module.main(["--dry-run", "--output", str(output)] + extra)
        self.assertEqual(0, code)
        return json.loads(output.read_text(encoding="utf-8")), buffer.getvalue()

    def _rehearsal(self, directory: str, extra: list[str]) -> tuple[dict, str]:
        return self._run_main(
            runner, directory, "rehearsal.json", ["--scenarios", "autumn_leaves"] + extra
        )

    def _ab(self, directory: str, extra: list[str]) -> tuple[dict, str]:
        return self._run_main(
            ab,
            directory,
            "ab.json",
            ["--models", "dry-midm", "--limit", "2", "--baseline-reps", "0"] + extra,
        )

    def test_rehearsal_defaults_to_raw_without_touching_config_or_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload, report = self._rehearsal(directory, [])
        self.assertNotIn("protocol", payload["config"])
        self.assertNotIn("[프로토콜]", report)
        turn = payload["results"][0]["scenarios"][0]["turns"][0]
        self.assertNotIn("response_body", turn)

    def test_rehearsal_operational_records_protocol_in_config_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload, report = self._rehearsal(directory, ["--protocol", "operational"])
        self.assertEqual("operational", payload["config"]["protocol"])
        self.assertIn("[프로토콜] operational — ACT 마커·선반응 ACK 분리 채점", report)
        turn = payload["results"][0]["scenarios"][0]["turns"][0]
        self.assertEqual(turn["response"].strip(), turn["response_body"])
        self.assertEqual(0, turn["protocol"]["act_marker_count"])

    def test_ab_defaults_to_raw_and_records_protocol_only_when_operational(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            raw_payload, raw_report = self._ab(directory, [])
            op_payload, op_report = self._ab(directory, ["--protocol", "operational"])
        self.assertNotIn("protocol", raw_payload["config"])
        self.assertNotIn("[프로토콜]", raw_report)
        self.assertNotIn("response_body", raw_payload["results"][0]["runs"][0])
        self.assertEqual("operational", op_payload["config"]["protocol"])
        self.assertIn("[프로토콜] operational — ACT 마커·선반응 ACK 분리 채점", op_report)
        run = op_payload["results"][0]["runs"][0]
        self.assertEqual(run["response"].strip(), run["response_body"])
        self.assertEqual(
            {"act_marker_count": 0, "ack_stripped": False, "ack_text": None}, run["protocol"]
        )

    def test_unknown_protocol_is_rejected_by_both_runners(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "never.json"
            for module in (runner, ab):
                with self.subTest(module=module.__name__), self.assertRaises(SystemExit):
                    with redirect_stderr(io.StringIO()):
                        module.main(
                            ["--dry-run", "--protocol", "nope", "--output", str(output)]
                        )

    def test_checkpoint_evidence_rejects_operational_protocol_payloads(self) -> None:
        """체크포인트 증거는 raw 채점 경로 전용이다."""
        with tempfile.TemporaryDirectory() as directory:
            payload = DryRunMainTests()._run_main(directory, "off", scenarios=None)
        runner.validate_checkpoint_evidence(runner.project_checkpoint_evidence(payload))
        operational = json.loads(json.dumps(payload))
        operational["config"]["protocol"] = "operational"
        with self.assertRaises(ValueError):
            runner.project_checkpoint_evidence(operational)


if __name__ == "__main__":
    unittest.main()
