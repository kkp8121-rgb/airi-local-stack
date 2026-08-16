import copy
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock
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
            and "[airi_affect_continuity " in str(message.get("content") or "")
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


class FakeHttpResponse:
    def __init__(self, body=b'{}', *, content_type='application/json', status=200, on_read=None):
        self.body = body
        self.offset = 0
        self.status = status
        self.on_read = on_read
        self.headers = type('Headers', (), {'get_content_type': lambda _: content_type})()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def read(self, size):
        if self.on_read:
            self.on_read()
        value = self.body[self.offset:self.offset + size]
        self.offset += len(value)
        return value

    def getcode(self):
        return self.status


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        return self.response


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
        off_note = [message for message in off_value["messages"] if message.get("name") == "airi_request_local"]
        on_note = [message for message in on_value["messages"] if message.get("name") == "airi_request_local"]
        self.assertEqual(1, len(off_note))
        self.assertEqual(1, len(on_note))
        self.assertIn("[airi_synthetic_broadcast_context ", off_note[0]["content"])
        self.assertNotIn("[airi_affect_continuity ", off_note[0]["content"])
        self.assertTrue(on_note[0]["content"].startswith(off_note[0]["content"] + "\n\n[airi_affect_continuity "))
        self.assertGreater(len(off_value["messages"]), 2)
        self.assertLessEqual(len(off_value["messages"]), 2 * (PROFILE["history_turns"] + 1) + 1)
        dialogue = [message for message in off_value["messages"] if message["role"] != "system"]
        self.assertEqual(["assistant", "user"] * (len(dialogue) // 2), [message["role"] for message in dialogue])
        self.assertEqual(scenario["turns"][22]["selected_message"], dialogue[-1]["content"])
        self.assertIn(scenario["turns"][22]["context"]["screen"], off_note[0]["content"])
        self.assertEqual(off_value["model"], on_value["model"])
        self.assertEqual(off_value["options"], on_value["options"])

    def test_no_response_turn_never_creates_a_request(self):
        scenario = self.fixture["scenarios"][0]
        with self.assertRaises(evaluation.EvalError):
            evaluation.base_request(scenario, 4, PROFILE)
        transport = FakeTransport()
        result = evaluation.execute(self.fixture, "http://127.0.0.1:11435/api/chat", PROFILE, transport)
        self.assertEqual(122, result["selected_turn_count"])
        self.assertEqual(366, result["model_call_count"])
        self.assertEqual(366, sum(call[0] == "POST" for call in transport.calls))

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
        self.assertEqual("triplet_transport_complete", execution["status"])
        self.assertEqual({"off": 122, "affect_only": 122, "reply_act": 122}, execution["response_count_by_arm"])
        self.assertEqual(2, sum(call[0] == "GET" for call in transport.calls))
        self.assertTrue(all(call[3] == {"x-airi-turn-origin": "local-evaluation"} for call in transport.calls if call[0] == "POST"))
        report = evaluation.public_report(self.fixture, PROFILE, execution)
        rendered = json.dumps(report, ensure_ascii=False)
        self.assertEqual("triplet_transport_complete", report["execution"]["status"])
        self.assertEqual(
            {
                "status", "completed_triplet_count", "model_call_count",
                "response_char_count_total",
                "health_profile_sha256",
            },
            set(report["execution"]),
        )
        self.assertNotIn("response_char_count_by_arm", report["execution"])
        self.assertEqual(122, report["execution"]["completed_triplet_count"])
        self.assertNotIn("response_count_by_arm", report["execution"])
        self.assertNotIn("response_char_count_by_arm", report["execution"])
        self.assertNotIn("비공개 OFF 응답", rendered)
        self.assertNotIn(self.fixture["scenarios"][0]["turns"][0]["prior_airi"], rendered)
        mapping = {"a": "affect_only", "b": "off", "c": "reply_act"}
        packet = evaluation.build_private_review_packet(self.fixture, execution, mapping)
        packet_text = json.dumps(packet, ensure_ascii=False)
        self.assertIn("비공개 OFF 응답", packet_text)
        self.assertNotIn("off", json.dumps(packet["rows"][0], ensure_ascii=False))
        self.assertEqual(
            {"review_a", "review_b", "review_c"},
            {key for key in packet["rows"][0] if key.startswith("review_")},
        )
        self.assertIsNot(packet["rows"][0]["review_a"], packet["rows"][0]["review_b"])
        self.assertEqual(mapping, evaluation.build_private_arm_key(mapping)["arm_mapping"])

    def test_injected_reply_act_sidecar_is_revalidated(self):
        sidecar = evaluation.load_reply_act_fixture(fixture=self.fixture)
        for mutation in ("unknown-act", "duplicate-turn", "extra-key"):
            changed = copy.deepcopy(sidecar)
            if mutation == "unknown-act":
                changed["entries"][0]["expected_reply_act"]["act"] = "invent"
            elif mutation == "duplicate-turn":
                changed["entries"][1]["turn_id"] = changed["entries"][0]["turn_id"]
            else:
                changed["entries"][0]["expected_reply_act"]["instruction"] = "free text"
            with self.subTest(mutation=mutation), self.assertRaises(evaluation.EvalError):
                evaluation.execute(
                    self.fixture,
                    "http://127.0.0.1:11435/api/chat",
                    PROFILE,
                    FakeTransport(),
                    reply_act_fixture=changed,
                )

        changed_fixture = copy.deepcopy(self.fixture)
        changed_fixture["scenarios"][0]["turns"][0]["prior_airi"] += " 조금"
        evaluation.validate_fixture(changed_fixture)
        with self.assertRaises(evaluation.EvalError):
            evaluation.validate_reply_act_fixture(sidecar, changed_fixture)

    def test_reply_act_oracle_answers_latest_viewer_not_event_kind(self):
        entries = {
            entry["turn_id"]: entry["expected_reply_act"]["act"]
            for entry in evaluation.load_reply_act_fixture(fixture=self.fixture)["entries"]
        }
        expected_edges = {
            "game-18": "respond_grounded",
            "teasing-17": "repair",
            "teasing-19": "respond_grounded",
            "correction-13": "respond_grounded",
            "fatigue-16": "respond_grounded",
            "fatigue-19": "deescalate",
            "fatigue-23": "close",
            "callback-01": "callback",
            "callback-02": "respond_grounded",
            "callback-09": "respond_grounded",
            "callback-15": "respond_grounded",
            "callback-22": "respond_grounded",
        }
        self.assertEqual(expected_edges, {key: entries[key] for key in expected_edges})

    def test_arm_mapping_is_exact_and_controls_blinded_packet_order(self):
        execution = evaluation.execute(self.fixture, "http://127.0.0.1:11435/api/chat", PROFILE, FakeTransport())
        off_first = execution["private_responses"][0]["off"]
        on_first = execution["private_responses"][0]["affect_only"]
        normal = evaluation.build_private_review_packet(self.fixture, execution, {"a": "off", "b": "affect_only", "c": "reply_act"})
        swapped = evaluation.build_private_review_packet(self.fixture, execution, {"a": "affect_only", "b": "off", "c": "reply_act"})
        self.assertEqual(off_first, normal["rows"][0]["response_a"])
        self.assertEqual(on_first, swapped["rows"][0]["response_a"])
        for bad in ({"a": "off", "b": "off", "c": "reply_act"}, {"a": "off"}, {"a": "off", "b": "affect_only", "c": "x"}):
            with self.assertRaises(evaluation.EvalError):
                evaluation.build_private_arm_key(bad)

        for offset in evaluation.BALANCED_EXECUTION_OFFSETS:
            positions = {condition: [0, 0, 0] for condition in evaluation.CONDITIONS}
            for ordinal in range(122):
                order = evaluation.EXECUTION_PERMUTATIONS[(ordinal + offset) % 6]
                for position, condition in enumerate(order):
                    positions[condition][position] += 1
            self.assertTrue(all(sorted(counts) == [40, 41, 41] for counts in positions.values()))
            self.assertEqual(offset, evaluation.build_private_arm_key(
                {"a": "off", "b": "affect_only", "c": "reply_act"}, offset,
            )["execution_order_offset"])
        for offset in (0, 2, 4, 5, False, 1.0):
            with self.assertRaises(evaluation.EvalError):
                evaluation.build_private_arm_key(
                    {"a": "off", "b": "affect_only", "c": "reply_act"}, offset,
                )

    def test_output_confinement_and_publish_is_content_free_except_private_packet(self):
        execution = evaluation.execute(self.fixture, "http://127.0.0.1:11435/api/chat", PROFILE, FakeTransport())
        report = evaluation.public_report(self.fixture, PROFILE, execution)
        mapping = {"a": "off", "b": "affect_only", "c": "reply_act"}
        packet = evaluation.build_private_review_packet(self.fixture, execution, mapping)
        key = evaluation.build_private_arm_key(mapping)
        with tempfile.TemporaryDirectory() as temporary:
            outside = Path(temporary) / "elsewhere"
            with self.assertRaises(evaluation.EvalError):
                evaluation.publish_local_run(evaluation.reserve_local_run(outside), report, packet, key)
        original_results_dir = evaluation.LOCAL_RESULTS_DIR
        original_keys_dir = evaluation.LOCAL_OPERATOR_KEYS_DIR
        isolated_results = tempfile.TemporaryDirectory()
        try:
            evaluation.LOCAL_RESULTS_DIR = Path(isolated_results.name) / "local-results"
            evaluation.LOCAL_OPERATOR_KEYS_DIR = Path(isolated_results.name) / "local-operator-keys"
            target = evaluation.LOCAL_RESULTS_DIR / "test-run"
            result = evaluation.publish_local_run(evaluation.reserve_local_run(target), report, packet, key)
            self.assertEqual(target.resolve(), result)
            public_text = (target / "public-report.json").read_text(encoding="utf-8")
            self.assertNotIn("비공개 OFF 응답", public_text)
            self.assertFalse((target / "private-arm-key.json").exists())
            operator_key = evaluation.LOCAL_OPERATOR_KEYS_DIR / "test-run.json"
            self.assertEqual(key, json.loads(operator_key.read_text(encoding="utf-8")))
            receipt = json.loads((target / "local-run-receipt.json").read_text(encoding="utf-8"))
            self.assertNotIn("private-arm-key.json", receipt["artifact_sha256"])
            for name, digest in receipt["artifact_sha256"].items():
                self.assertEqual(digest, hashlib.sha256((target / name).read_bytes()).hexdigest())
            with self.assertRaises(evaluation.EvalError):
                evaluation.reserve_local_run(target)
        finally:
            evaluation.LOCAL_RESULTS_DIR = original_results_dir
            evaluation.LOCAL_OPERATOR_KEYS_DIR = original_keys_dir
            isolated_results.cleanup()

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
        self.assertTrue(report["pairing"]["exact_nested_identity"])
        self.assertEqual(122, report["pairing"]["completed_triplet_count"])
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

    def test_local_transport_is_proxy_free_and_fail_closed(self):
        endpoint = 'http://127.0.0.1:11435/api/chat'
        opener = FakeOpener(FakeHttpResponse(b'{"ok":true}'))
        with mock.patch.object(evaluation.urlrequest, 'build_opener', return_value=opener) as build:
            transport = evaluation.make_local_transport(endpoint, request_timeout=1, overall_timeout=2)
            self.assertEqual({'ok': True}, transport('GET', evaluation._health_url(endpoint), None, {})['json'])
            handlers = build.call_args.args
            self.assertEqual({}, handlers[0].proxies)
            with self.assertRaises(evaluation.EvalError):
                transport('DELETE', endpoint, None, {})
            with self.assertRaises(evaluation.EvalError):
                transport('GET', endpoint, None, {})
            with self.assertRaises(evaluation.EvalError):
                transport('POST', evaluation._health_url(endpoint), b'{}', {'x-airi-turn-origin': 'local-evaluation'})
            with self.assertRaises(evaluation.EvalError):
                transport('POST', 'http://127.0.0.1:11435/not-chat', b'{}', {})
            with self.assertRaises(evaluation.EvalError):
                transport('GET', evaluation._health_url(endpoint), b'x', {})
            with self.assertRaises(evaluation.EvalError):
                transport('GET', evaluation._health_url(endpoint), None, {'Authorization': 'x'})
            with self.assertRaises(evaluation.EvalError):
                transport('POST', endpoint, b'x' * (evaluation.MAX_REQUEST_BYTES + 1), {'x-airi-turn-origin': 'local-evaluation'})
            with self.assertRaises(evaluation.EvalError):
                transport('POST', endpoint, b'{}', {'Authorization': 'x'})
            opener.response = FakeHttpResponse(b'{"ok":true}')
            transport('POST', endpoint, b'{}', {'x-airi-turn-origin': 'local-evaluation'})
            self.assertEqual('application/json', opener.requests[-1][0].get_header('Content-type'))

        cases = (
            FakeHttpResponse(b'{}', content_type='text/plain'),
            FakeHttpResponse(b'{'),
            FakeHttpResponse(b'[]'),
            FakeHttpResponse(b'x' * (evaluation.MAX_HTTP_BODY_BYTES + 1)),
        )
        for response in cases:
            with self.subTest(response=response.body[:1]):
                with mock.patch.object(evaluation.urlrequest, 'build_opener', return_value=FakeOpener(response)):
                    transport = evaluation.make_local_transport(endpoint, request_timeout=1, overall_timeout=2)
                    with self.assertRaises(evaluation.EvalError):
                        transport('GET', evaluation._health_url(endpoint), None, {})
        import urllib.error
        http_error = urllib.error.HTTPError(endpoint, 500, 'x', None, None)
        with mock.patch.object(evaluation.urlrequest, 'build_opener', return_value=FakeOpener(error=http_error)):
            transport = evaluation.make_local_transport(endpoint, request_timeout=1, overall_timeout=2)
            with self.assertRaises(evaluation.EvalError):
                transport('GET', evaluation._health_url(endpoint), None, {})
        http_error.close()

    def test_local_transport_rejects_redirect_and_deadline_during_read(self):
        endpoint = 'http://127.0.0.1:11435/api/chat'
        handler = evaluation._NoRedirect()
        with self.assertRaises(evaluation.EvalError):
            handler.redirect_request(None, None, 302, 'found', None, endpoint)
        clock = [0.0]
        response = FakeHttpResponse(b'{"ok":true}', on_read=lambda: clock.__setitem__(0, 3.0))
        with mock.patch.object(evaluation.time, 'monotonic', side_effect=lambda: clock[0]), mock.patch.object(evaluation.urlrequest, 'build_opener', return_value=FakeOpener(response)):
            transport = evaluation.make_local_transport(endpoint, request_timeout=1, overall_timeout=2)
            with self.assertRaises(evaluation.EvalError):
                transport('GET', evaluation._health_url(endpoint), None, {})

    def test_main_default_is_offline_and_execute_is_explicit(self):
        with mock.patch.object(evaluation, 'make_local_transport', side_effect=AssertionError('network')), \
             mock.patch.object(sys, 'argv', ['runner']):
            self.assertEqual(0, evaluation.main())
        calls = []
        fake_execution = evaluation.execute(self.fixture, 'http://127.0.0.1:11435/api/chat', PROFILE, FakeTransport())
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'local-results' / 'fresh'
            def fake_execute(fixture, endpoint, profile, transport, **kwargs):
                calls.append(('execute', endpoint))
                return fake_execution
            with mock.patch.object(evaluation, 'make_local_transport', return_value=object()), \
                 mock.patch.object(evaluation, 'execute', side_effect=fake_execute), \
                 mock.patch.object(evaluation, 'reserve_local_run', return_value={'target': target, 'stage': target, 'key_target': target.with_suffix('.json')}), \
                 mock.patch.object(evaluation, 'publish_local_run', return_value=target) as publish, \
                 mock.patch.object(sys, 'argv', ['runner', '--execute', '--output-dir', str(target)]):
                self.assertEqual(0, evaluation.main())
            self.assertEqual([('execute', 'http://127.0.0.1:11435/api/chat')], calls)
            self.assertEqual(366, fake_execution['model_call_count'])
            self.assertEqual(target, publish.call_args.args[0]['target'])
            with mock.patch.object(sys, 'argv', ['runner', '--execute']):
                with self.assertRaises(evaluation.EvalError):
                    evaluation.main()

        original_results = evaluation.LOCAL_RESULTS_DIR
        original_keys = evaluation.LOCAL_OPERATOR_KEYS_DIR
        with tempfile.TemporaryDirectory() as temporary:
            try:
                evaluation.LOCAL_RESULTS_DIR = Path(temporary) / 'local-results'
                evaluation.LOCAL_OPERATOR_KEYS_DIR = Path(temporary) / 'local-operator-keys'
                existing = evaluation.LOCAL_RESULTS_DIR / 'existing'
                existing.mkdir(parents=True)
                with mock.patch.object(evaluation, 'make_local_transport', side_effect=AssertionError('network')), \
                     mock.patch.object(sys, 'argv', ['runner', '--execute', '--output-dir', str(existing)]):
                    with self.assertRaises(evaluation.EvalError):
                        evaluation.main()
            finally:
                evaluation.LOCAL_RESULTS_DIR = original_results
                evaluation.LOCAL_OPERATOR_KEYS_DIR = original_keys

    def test_publish_failure_does_not_create_target_and_rejects_reparse(self):
        report = {'x': 'x' * (evaluation.MAX_ARTIFACT_BYTES['public-report.json'] + 1)}
        original = evaluation.LOCAL_RESULTS_DIR
        original_keys = evaluation.LOCAL_OPERATOR_KEYS_DIR
        with tempfile.TemporaryDirectory() as temporary:
            evaluation.LOCAL_RESULTS_DIR = Path(temporary) / 'local-results'
            evaluation.LOCAL_OPERATOR_KEYS_DIR = Path(temporary) / 'local-operator-keys'
            target = evaluation.LOCAL_RESULTS_DIR / 'fresh'
            try:
                with self.assertRaises(evaluation.EvalError):
                    evaluation.publish_local_run(evaluation.reserve_local_run(target), report, {}, {})
                self.assertFalse(target.exists())
                self.assertFalse((evaluation.LOCAL_OPERATOR_KEYS_DIR / 'fresh.json').exists())
                reservation = evaluation.reserve_local_run(target)
                with self.assertRaises(evaluation.EvalError):
                    evaluation.reserve_local_run(target)
                evaluation.abort_local_run(reservation)
                for reserved_name in ('CON', 'con', 'PRN', 'AUX', 'NUL', 'COM1', 'LPT9'):
                    with self.subTest(reserved_name=reserved_name):
                        with self.assertRaises(evaluation.EvalError):
                            evaluation.reserve_local_run(evaluation.LOCAL_RESULTS_DIR / reserved_name)
                evaluation.LOCAL_RESULTS_DIR.mkdir(exist_ok=True)
                link = evaluation.LOCAL_RESULTS_DIR / 'linked'
                try:
                    os.symlink(Path(temporary), link, target_is_directory=True)
                except (OSError, NotImplementedError):
                    return
                with self.assertRaises(evaluation.EvalError):
                    evaluation.reserve_local_run(link)
            finally:
                evaluation.LOCAL_RESULTS_DIR = original
                evaluation.LOCAL_OPERATOR_KEYS_DIR = original_keys

    def test_astral_maximum_private_packet_fits_eight_mib_custody_cap(self):
        execution = evaluation.execute(self.fixture, 'http://127.0.0.1:11435/api/chat', PROFILE, FakeTransport())
        maximum = '😀' * evaluation.MAX_RESPONSE_CHARS
        for row in execution['private_responses']:
            row['off'] = maximum
            row['affect_only'] = maximum
            row['reply_act'] = maximum
        execution['response_char_count_by_arm'] = {name: 122 * evaluation.MAX_RESPONSE_CHARS for name in evaluation.CONDITIONS}
        packet = evaluation.build_private_review_packet(self.fixture, execution, {'a': 'off', 'b': 'affect_only', 'c': 'reply_act'})
        self.assertLessEqual(len(evaluation.canonical_bytes(packet)), evaluation.MAX_ARTIFACT_BYTES['private-review-packet.json'])


if __name__ == "__main__":
    unittest.main()
