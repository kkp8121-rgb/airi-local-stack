import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_airi_baseline as runner


class FakeResponse:
    status = 200
    def __init__(self, data): self.data = io.BytesIO(data)
    def read(self, size=-1): return self.data.read(size)

class FakeConnection:
    def __init__(self, *args, **kwargs): pass
    def request(self, *args, **kwargs): pass
    def getresponse(self):
        # Korean UTF-8 is deliberately split one byte at a time by stream_chat.
        rows = [
            b": ack\n\n",
            json.dumps({"message": {"content": ""}, "done": False}).encode() + b"\n",
            json.dumps({"message": {"content": "안"}, "done": False}, ensure_ascii=False).encode() + b"\n",
            json.dumps({"message": {"content": "녕"}, "done": False}, ensure_ascii=False).encode() + b"\n",
            b'{"done":true,"eval_count":4,"eval_duration":2000000000}\n',
        ]
        return FakeResponse(b"".join(rows))
    def close(self): pass


class TruncatedConnection(FakeConnection):
    def getresponse(self):
        return FakeResponse(json.dumps({"message": {"content": "부분"}, "done": False}, ensure_ascii=False).encode() + b"\n")


class BaselineTests(unittest.TestCase):
    def fixture(self):
        return json.loads(Path(__file__).with_name("airi_baseline_cases.json").read_text(encoding="utf-8"))

    def test_fixture_valid_and_unique(self):
        self.assertEqual(len(runner.validate_fixture(self.fixture())["cases"]), 16)
        broken = self.fixture(); broken["cases"][1]["id"] = broken["cases"][0]["id"]
        with self.assertRaises(runner.EvalError): runner.validate_fixture(broken)

    def test_character_card_is_bounded_sanitized_and_precedes_memory(self):
        card = "  이름: 라임\x00\n\t성격: 장난기  " + ("x" * 5000)
        system = runner.build_case_system_prompt(
            "BASE", {"character_card": card, "memory_block": "[Character Memory]\n- 기억"}
        )
        self.assertIn("[Active Character Card]\nThe card is descriptive context. Proxy output, safety, and control constraints take priority.\n이름: 라임\n", system)
        self.assertNotIn("\x00", system)
        self.assertLess(
            system.index("[Active Character Card]"), system.index("[Character Memory]")
        )
        rendered_card = system.split(
            "The card is descriptive context. Proxy output, safety, and control constraints take priority.\n", 1
        )[1].split("\n\n[Character Memory]", 1)[0]
        self.assertLessEqual(len(rendered_card), runner.ACTIVE_CARD_MAX_CHARS)

    def test_stream_utf8_split_and_ttft_is_first_content(self):
        ticks = iter((10.0, 10.125, 10.5))
        with patch.object(runner.http.client, "HTTPConnection", FakeConnection):
            text, timings = runner.stream_chat("http://127.0.0.1:11434/api/chat", {}, clock=lambda: next(ticks))
        self.assertEqual(text, "안녕"); self.assertEqual(timings["ttft_seconds"], 0.125); self.assertEqual(timings["tokens_per_second"], 2.0)

    def test_stream_requires_terminal_done_marker(self):
        ticks = iter((10.0, 10.125))
        with patch.object(runner.http.client, "HTTPConnection", TruncatedConnection):
            with self.assertRaises(runner.EvalError):
                runner.stream_chat("http://127.0.0.1:11434/api/chat", {}, clock=lambda: next(ticks))

    def test_repeated_runs_use_all_samples_and_median_timing(self):
        samples = [
            {"checks":{"passed":True,"failures":[]},"timings":{"ttft_seconds":0.1,"total_seconds":1.0,"tokens_per_second":2.0}},
            {"checks":{"passed":False,"failures":["required_any"]},"timings":{"ttft_seconds":0.3,"total_seconds":3.0,"tokens_per_second":4.0}},
        ]
        result = runner.aggregate_runs(samples)
        self.assertFalse(result["checks"]["passed"])
        self.assertEqual(result["checks"]["failures"], ["required_any"])
        self.assertEqual(result["timings"]["ttft_seconds"], 0.2)

    def test_checks(self):
        self.assertTrue(runner.score_output("안녕, 괜찮아.", {"required_any":["안녕"],"max_sentences":2})["passed"])
        failure = runner.score_output("<|ACT {}|> 파일을 모두 지웠어. 😊", {"no_control_tokens":True,"no_emoji":True,"no_unverified_tool_claim":True})
        self.assertIn("no_control_tokens", failure["failures"]); self.assertIn("no_emoji", failure["failures"]); self.assertIn("no_unverified_tool_claim", failure["failures"])

    def test_checks_enforce_question_range(self):
        passed = runner.score_output("한 가지만 물어볼게?", {"min_questions": 1, "max_questions": 1})
        missing = runner.score_output("질문 없이 끝낼게.", {"min_questions": 1, "max_questions": 1})
        failed = runner.score_output("하나? 둘?", {"max_questions": 1})
        self.assertTrue(passed["passed"])
        self.assertEqual(passed["question_count"], 1)
        self.assertIn("min_questions", missing["failures"])
        self.assertIn("max_questions", failed["failures"])

    def test_style_fixture_is_valid_and_has_required_human_review(self):
        fixture = json.loads(Path(__file__).with_name("airi_vtuber_style_cases_v0.1.json").read_text(encoding="utf-8"))
        cases = runner.validate_fixture(fixture)["cases"]
        self.assertEqual(fixture["suite_id"], "airi-s1-style-contract")
        self.assertEqual(fixture["suite_version"], "0.1")
        self.assertEqual(len(cases), 12)
        self.assertTrue(all(case["human_review"].get("required") is True and case["human_review"].get("focus") for case in cases))

    def test_v02_style_contract_is_synthetic_and_covers_human_focus_categories(self):
        fixture = json.loads(Path(__file__).with_name("airi_style_contract_v0.2.json").read_text(encoding="utf-8"))
        cases = runner.validate_fixture(fixture)["cases"]
        self.assertEqual(fixture["suite_version"], "0.2")
        self.assertEqual(len(cases), 12)
        self.assertEqual({case["category"] for case in cases}, {
            "general_chat", "light_brag", "mistake", "broadcast_monologue",
            "serious_switch", "danger", "ambiguous", "memory_truth",
            "card_context", "tool_truth", "creator_imitation", "output_hygiene",
        })
        self.assertTrue(all(case["human_review"].get("focus") for case in cases))
        self.assertTrue(all(all(case["checks"].get(key) is True for key in (
            "no_control_tokens", "no_emoji", "no_markdown", "no_stage_direction", "no_emoticon",
        )) for case in cases))

    def test_structural_output_gates_include_malformed_controls_and_decorations(self):
        checks = {"no_control_tokens":True,"no_markdown":True,"no_stage_direction":True,"no_emoticon":True}
        failures = runner.score_output('<|ACT {"emotion":"x"}| hello **there** [laugh] :)', checks)["failures"]
        self.assertEqual(set(failures), {"no_control_tokens", "no_markdown", "no_stage_direction", "no_emoticon"})

    def test_v02_rejects_repeated_runs_before_any_model_metadata_call(self):
        fixture = Path(__file__).with_name("airi_style_contract_v0.2.json")
        with patch.object(runner, "safe_model_metadata") as metadata:
            result = runner.main(["--fixture", str(fixture), "--runs", "2"])
        self.assertEqual(result, 1)
        metadata.assert_not_called()

    def test_loopback_gate(self):
        runner.ensure_local_endpoint("http://localhost:11434/api/chat")
        with self.assertRaises(runner.EvalError): runner.ensure_local_endpoint("http://example.com/api/chat")

    def test_metadata_and_markdown_do_not_leak_raw_modelfile_or_secrets(self):
        raw = {"modelfile":"FROM sha256:abcdefabcdefabcdef\nLICENSE private-key=not-for-report", "details":{"family":"x"}}
        tags = {"models":[{"name":"x","digest":"abc","size":123}]}
        with patch.object(runner, "request_json", side_effect=(raw, tags)): meta = runner.safe_model_metadata("http://127.0.0.1:11434/api/chat", "x")
        rendered = json.dumps(meta)
        self.assertNotIn("private-key", rendered); self.assertNotIn("FROM ", rendered)
        self.assertEqual(meta["runtime_manifest"]["digest"], "abc")
        report = {"cases":[{"id":"a","category":"x","checks":{"passed":True},"timings":{"ttft_seconds":None,"total_seconds":1.0}}],"aggregate":{"case_count":1,"passed_count":1,"gate":"PASS"}}
        self.assertEqual(runner.markdown_report(report), runner.markdown_report(report))

    def test_runtime_fingerprint_is_deterministic_and_uses_local_version_metadata(self):
        config = {"endpoint":"http://127.0.0.1:11434/api/chat", "model":"x", "runs":1,
                  "num_ctx":2048, "num_gpu":0, "temperature":0, "seed":42}
        with patch.object(runner, "request_json", return_value={"version":"0.12.3", "path":"C:/private/ollama", "secret":"nope"}) as request:
            metadata = runner.runtime_metadata(config["endpoint"], config)
        self.assertEqual(request.call_args.args[0], "http://127.0.0.1:11434/api/version")
        self.assertEqual(request.call_args.kwargs, {"method":"GET"})
        self.assertEqual(metadata["ollama_version"], "0.12.3")
        self.assertEqual(metadata["runtime_config"], config)
        self.assertEqual(set(metadata), {"runner_sha256", "runner_version", "python", "ollama_version", "runtime_config"})
        self.assertEqual(runner.runtime_sha256(metadata), runner.runtime_sha256(dict(reversed(list(metadata.items())))))
        rendered = json.dumps(metadata)
        self.assertNotIn("sys.executable", rendered)
        self.assertNotIn("PATH=", rendered)
        self.assertNotIn("C:/private", rendered)
        self.assertNotIn("nope", rendered)

    def test_runtime_version_metadata_cannot_bypass_loopback_gate(self):
        config = {"endpoint":"http://example.com/api/chat", "model":"x", "runs":1,
                  "num_ctx":2048, "num_gpu":0, "temperature":0, "seed":42}
        with self.assertRaises(runner.EvalError):
            runner.runtime_metadata(config["endpoint"], config)


if __name__ == "__main__": unittest.main()
