import sys
import unittest
from pathlib import Path
from unittest import mock

import broadcast_contract
from broadcast_contract import (
    BROADCAST_CONTRACT_ENV,
    BROADCAST_CONTRACT_PARAMS,
    apply_broadcast_contract,
    broadcast_contract_enabled,
    build_broadcast_contract_block,
)

sys.path.insert(0, str(Path(__file__).resolve().parent / "eval" / "broadcast_chat"))
import run_broadcast_chat_ab as ab_runner


class ApplyContractTests(unittest.TestCase):
    def test_disabled_returns_the_exact_same_string(self) -> None:
        for prompt in ("", "너는 AIRI야.", "여러\n줄\n\n프롬프트"):
            with self.subTest(prompt=prompt):
                applied = apply_broadcast_contract(prompt, False)
                self.assertEqual(applied, prompt)
                self.assertEqual(applied.encode("utf-8"), prompt.encode("utf-8"))

    def test_enabled_appends_the_block_after_one_blank_line(self) -> None:
        block = build_broadcast_contract_block()
        applied = apply_broadcast_contract("기존 프롬프트", True)
        self.assertEqual(applied, "기존 프롬프트\n\n" + block)
        self.assertTrue(applied.startswith("기존 프롬프트"))
        self.assertTrue(applied.endswith(block))
        self.assertEqual(applied.count(block), 1)

    def test_block_is_stable_across_calls(self) -> None:
        self.assertEqual(build_broadcast_contract_block(), build_broadcast_contract_block())


class EnvGateTests(unittest.TestCase):
    def test_missing_variable_is_off(self) -> None:
        self.assertFalse(broadcast_contract_enabled({}))

    def test_off_values(self) -> None:
        for value in ("", "0", "false", "FALSE", "off", "OFF", "no", " 0 ", "maybe"):
            with self.subTest(value=value):
                self.assertFalse(broadcast_contract_enabled({BROADCAST_CONTRACT_ENV: value}))

    def test_on_values(self) -> None:
        for value in ("1", "true", "TRUE", "on", "ON", "yes", " on "):
            with self.subTest(value=value):
                self.assertTrue(broadcast_contract_enabled({BROADCAST_CONTRACT_ENV: value}))

    def test_default_reads_process_environment(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=False):
            broadcast_contract.os.environ.pop(BROADCAST_CONTRACT_ENV, None)
            self.assertFalse(broadcast_contract_enabled())
            broadcast_contract.os.environ[BROADCAST_CONTRACT_ENV] = "1"
            self.assertTrue(broadcast_contract_enabled())


class BlockShapeTests(unittest.TestCase):
    def test_block_stays_inside_the_num_ctx_budget(self) -> None:
        limits = BROADCAST_CONTRACT_PARAMS["contract_block"]
        block = build_broadcast_contract_block()
        self.assertLessEqual(len(block), limits["hard_max_chars"])
        self.assertLessEqual(len(block), limits["target_max_chars"])

    def test_block_obeys_the_existing_output_rules(self) -> None:
        block = build_broadcast_contract_block()
        lines = block.splitlines()
        self.assertTrue(all(line == line.rstrip() for line in lines))
        self.assertTrue(all(line.strip() for line in lines))
        self.assertFalse(block.startswith("\n"))
        self.assertFalse(block.endswith("\n"))
        for banned in ("**", "```", "<|", "# ", "- "):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, block)
        self.assertTrue(all(ord(char) < 0x1F300 for char in block))

    def test_block_carries_the_observed_broadcast_patterns(self) -> None:
        block = build_broadcast_contract_block()
        for rule in (
            "되짚은 뒤",
            "한 호흡",
            "명분이 있을 때만",
            "서술체",
            "반말 구어체",
            "존댓말을 써도 따라 하지 마",
            "되묻기",
            "가볍게 받아쳐",
            "한 문장으로 묶어",
            "후원이나 특별한 순간에만",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, block)

    def test_length_numbers_come_from_the_parameter_table(self) -> None:
        fragment = BROADCAST_CONTRACT_PARAMS["reaction_fragment"]
        block = build_broadcast_contract_block()
        self.assertIn(f"{fragment['min_chars']}~{fragment['max_chars']}자", block)
        self.assertIn(
            f"{fragment['min_sentences']}~{fragment['max_sentences']}문장", block
        )


class ParameterTableTests(unittest.TestCase):
    EXPECTED = {
        "reaction_fragment": {"min_chars": int, "max_chars": int, "min_sentences": int, "max_sentences": int},
        "narration_block": {"min_seconds": int, "max_seconds": int, "requires_justification": bool},
        "readout_to_response": {"max_ms": int},
        "undeclared_silence": {"conservative_seconds": int, "max_seconds": int},
        "declared_absence": {"max_seconds": int, "requires_declaration": bool},
        "name_call": {"scope": str, "max_per_hour": int},
        "tag_question": {"min_ratio": float, "max_ratio": float},
        "opening": {"max_seconds": int},
        "closing": {"min_seconds": int, "max_seconds": int, "requires_next_promise": bool},
        "contract_block": {"target_max_chars": int, "hard_max_chars": int},
    }

    def test_every_parameter_has_typed_values_and_a_study_citation(self) -> None:
        self.assertEqual(set(BROADCAST_CONTRACT_PARAMS), set(self.EXPECTED))
        for name, fields in self.EXPECTED.items():
            entry = BROADCAST_CONTRACT_PARAMS[name]
            with self.subTest(param=name):
                self.assertIsInstance(entry["source"], str)
                self.assertTrue(entry["source"].strip())
                for field, kind in fields.items():
                    self.assertIsInstance(entry[field], kind)

    def test_observed_candidate_values_are_pinned(self) -> None:
        self.assertEqual(BROADCAST_CONTRACT_PARAMS["reaction_fragment"]["min_chars"], 10)
        self.assertEqual(BROADCAST_CONTRACT_PARAMS["reaction_fragment"]["max_chars"], 45)
        self.assertEqual(BROADCAST_CONTRACT_PARAMS["readout_to_response"]["max_ms"], 1300)
        self.assertEqual(BROADCAST_CONTRACT_PARAMS["undeclared_silence"]["conservative_seconds"], 10)
        self.assertEqual(BROADCAST_CONTRACT_PARAMS["undeclared_silence"]["max_seconds"], 20)
        self.assertEqual(BROADCAST_CONTRACT_PARAMS["tag_question"]["min_ratio"], 0.05)
        self.assertEqual(BROADCAST_CONTRACT_PARAMS["tag_question"]["max_ratio"], 0.10)
        self.assertEqual(BROADCAST_CONTRACT_PARAMS["name_call"]["scope"], "donation_or_special")


class ProxyWiringTests(unittest.TestCase):
    """프록시 배선 — 기본 OFF 에서 최종 시스템 프롬프트가 바뀌지 않아야 한다."""

    def setUp(self) -> None:
        import ollama_proxy

        self.proxy = ollama_proxy

    def _system_content(self, messages: list[dict[str, object]]) -> str:
        import json

        body = json.dumps({"model": "local", "messages": messages}).encode("utf-8")
        transformed = self.proxy.transform_body("/api/chat", body)[0]
        projected = json.loads(transformed)["messages"]
        return projected[0]["content"]

    def test_default_off_keeps_the_request_prompt_byte_identical(self) -> None:
        messages = [{"role": "user", "content": "오늘 방송 뭐 해?"}]
        expected = self.proxy.AIRI_SYSTEM_PROMPT + "\n\n" + self.proxy.AIRI_FINAL_CONTRACT
        with mock.patch.dict("os.environ", {}, clear=False):
            self.proxy.os.environ.pop(BROADCAST_CONTRACT_ENV, None)
            content = self._system_content(messages)
        self.assertEqual(content, expected)
        self.assertEqual(content.encode("utf-8"), expected.encode("utf-8"))

    def test_explicit_off_values_keep_the_request_prompt_unchanged(self) -> None:
        messages = [{"role": "user", "content": "오늘 방송 뭐 해?"}]
        expected = self.proxy.AIRI_SYSTEM_PROMPT + "\n\n" + self.proxy.AIRI_FINAL_CONTRACT
        for value in ("0", "false", "off"):
            with self.subTest(value=value):
                with mock.patch.dict("os.environ", {BROADCAST_CONTRACT_ENV: value}):
                    self.assertEqual(self._system_content(messages), expected)

    def test_gate_on_appends_the_contract_block_once(self) -> None:
        messages = [{"role": "user", "content": "오늘 방송 뭐 해?"}]
        base = self.proxy.AIRI_SYSTEM_PROMPT + "\n\n" + self.proxy.AIRI_FINAL_CONTRACT
        block = build_broadcast_contract_block()
        with mock.patch.dict("os.environ", {BROADCAST_CONTRACT_ENV: "1"}):
            content = self._system_content(messages)
        self.assertEqual(content, base + "\n\n" + block)
        self.assertEqual(content.count(block), 1)

    def test_proxy_uses_the_shared_module_not_a_local_copy(self) -> None:
        self.assertIs(self.proxy.apply_broadcast_contract, apply_broadcast_contract)
        self.assertIs(self.proxy.broadcast_contract_enabled, broadcast_contract_enabled)


class AbRunnerContractTests(unittest.TestCase):
    """A/B 러너 — 계약 블록을 임베드하지 않고 프로덕션 모듈에서 가져온다."""

    def test_runner_imports_the_production_block(self) -> None:
        self.assertIs(ab_runner.build_broadcast_contract_block, build_broadcast_contract_block)

    def test_contract_off_keeps_the_previous_combined_system_content(self) -> None:
        expected = ab_runner.AIRI_SYSTEM_PROMPT + "\n\n" + ab_runner.BROADCAST_FRAME
        self.assertEqual(ab_runner.build_system_content(), expected)
        self.assertEqual(ab_runner.build_system_content(""), expected)
        self.assertEqual(ab_runner.build_messages("안녕")[0]["content"], expected)

    def test_contract_on_appends_the_block_to_the_system_message(self) -> None:
        block = build_broadcast_contract_block()
        expected = (
            ab_runner.AIRI_SYSTEM_PROMPT + "\n\n" + ab_runner.BROADCAST_FRAME + "\n\n" + block
        )
        self.assertEqual(ab_runner.build_system_content(block), expected)
        messages = ab_runner.build_messages("안녕", block)
        self.assertEqual(messages[0]["content"], expected)
        self.assertEqual(messages[1]["content"], ab_runner.USER_PREFIX + "안녕")

    def test_embedded_prompt_still_matches_the_repo_constant(self) -> None:
        check = ab_runner.verify_repo_prompt(Path(__file__).with_name("ollama_proxy.py"))
        self.assertTrue(check["found"])
        self.assertTrue(check["matches"])


if __name__ == "__main__":
    unittest.main()
