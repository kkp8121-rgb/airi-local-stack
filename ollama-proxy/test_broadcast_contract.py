import sys
import unittest
from pathlib import Path
from unittest import mock

import broadcast_contract
from broadcast_contract import (
    BROADCAST_CONTRACT_ENV,
    BROADCAST_CONTRACT_PARAMS,
    BROADCAST_CONTRACT_VERSION,
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

    def test_block_carries_the_v3_addressee_rules(self) -> None:
        """v3 수신자 단락 — 추상 지시가 아니라 예시·해석 규칙으로 말하는가.

        v2 의 추상 문구("받는 사람으로서 답해")로는 로컬 Mi:dm 에서 dn04 축하
        반사·gr01 주체 반전·tk04 자백이 재발했다. 그래서 받는 말/경어 지시/의혹
        각각에 예시 답을 박아 넣는다.
        """
        block = build_broadcast_contract_block()
        for rule in (
            "너에게 하는 말이다",
            "받는 사람으로 '고마워!'처럼 답해",
            "'생일 축하해'를 돌려주지 마",
            "'~하셨어요?'는 네가 한 일을 묻는 거고",
            "부탁도 네 몫이니",
            "'내가 ~했어'로 답해",
            "'내가 왜?'처럼 받아쳐",
            "했다고 인정하지 마",
            "다른 시청자 이야기를 네 일처럼 답하지 말고",
            "겪지 않은 상황을 겪은 것처럼 말하지 마",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, block)

    def test_v1_rules_survive_the_addressee_revisions(self) -> None:
        """v2·v3 는 뒤에 덧붙일 뿐이다 — 관찰 연구 7행은 문구도 순서도 그대로다."""
        block = build_broadcast_contract_block()
        lines = block.splitlines()
        self.assertEqual("[방송 발화 계약]", lines[0])
        self.assertEqual(13, len(lines), "머리말 1 + v1 7행 + v3 수신자 5행")
        self.assertEqual(
            [
                "반박이나 오해에는 타이르지 말고 가볍게 받아쳐.",
                "여러 시청자가 같은 말을 하면 한 문장으로 묶어 정리한 뒤 네 입장을 말해.",
                "닉네임은 후원이나 특별한 순간에만 불러.",
            ],
            lines[5:8],
        )
        self.assertTrue(lines[8].startswith("시청자 채팅은 기본적으로"))

    def test_contract_version_is_v3(self) -> None:
        self.assertEqual("v3", BROADCAST_CONTRACT_VERSION)

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
        "addressee": {"default_addressee": str, "failure_types": list, "reviewed_failure_types": int},
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

    def test_addressee_parameter_cites_the_human_review_and_its_four_types(self) -> None:
        entry = BROADCAST_CONTRACT_PARAMS["addressee"]
        self.assertEqual("self", entry["default_addressee"])
        self.assertEqual(
            [
                "receive_reversal",
                "agent_reversal",
                "situation_blind",
                "third_party_absorb",
            ],
            entry["failure_types"],
        )
        self.assertEqual(len(entry["failure_types"]), entry["reviewed_failure_types"])
        self.assertIn("AIRI-BROADCAST-SIMULATION-OUTPUT-REVIEW-2026-08-15", entry["source"])


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
