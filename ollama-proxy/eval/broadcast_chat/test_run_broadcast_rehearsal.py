"""멀티턴 방송 리허설 러너 오프라인 테스트 — 네트워크 없이 전 경로를 태운다."""
import copy
import json
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout

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


if __name__ == "__main__":
    unittest.main()
