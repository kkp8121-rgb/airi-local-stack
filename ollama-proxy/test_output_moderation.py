"""한국어 출력 모더레이션 게이트 계약 시험 — 방송 트랙 B3.

이 파일에는 금칙어 원문을 적지 않는다. 차단을 확인해야 하는 곳은 사전 파일에서
항목을 읽어와 우회 표기를 프로그램으로 만들어 쓰고, 통합 시험은 비속어가 아닌
개인정보 패턴(전화번호 형태)을 자극원으로 쓴다.
"""

from __future__ import annotations

import json
import statistics
import time
import unittest
from pathlib import Path
from unittest import mock

import ollama_proxy
import output_moderation

TERMS_PATH = Path(output_moderation.__file__).resolve().parent / "moderation_terms_ko.json"

# 개인정보 패턴은 비속어를 쓰지 않고도 차단 경로 전체를 시험할 수 있는 자극원이다.
BLOCKED_SAMPLE = "내 번호는 010-1234-5678이야."
SAFE_SAMPLE = "오늘도 와줘서 고마워."

# 실제 낱말이면서 사전 항목과 부분적으로 겹치는 문장들. 하나라도 차단되면
# 정상 대화가 폴백 대사로 바뀌므로 게이트 자체가 방송에 쓸 수 없게 된다.
BENIGN_SENTENCES = (
    "안녕! 오늘도 와줘서 고마워.",
    "그 게임 어제 처음 해봤는데 생각보다 어렵더라.",
    "지하철 시발역이 어디였더라?",
    "무시 발언은 서로 하지 말자.",
    "역시 발표가 제일 어려워.",
    "다시 발견한 노래인데 계속 듣게 돼.",
    "어제는 잠자지 못했어.",
    "그건 아직 보지 못했어.",
    "밤에 자지 않고 계속 게임했어.",
    "아직 보지 말고 조금만 기다려.",
    "책을 다시 읽어보지 않을래?",
    "자살골 때문에 졌대.",
    "오늘 미치는 줄 알았어.",
    "껌을 씹으면서 걸었어.",
    "3개년 계획을 세웠어.",
    "우리 회의는 2026-08-12에 하자.",
    "회의는 3동 앞에서 만나자.",
    "3번 출구에서 만나자.",
    "ㅋㅋㅋ 웃겨 죽는 줄 알았어.",
    "signal garden 얘기부터 시작할게.",
)


def load_terms() -> dict[str, dict[str, list[str]]]:
    raw = json.loads(TERMS_PATH.read_text(encoding="utf-8"))
    return {
        category["id"]: {
            "terms": list(category.get("terms", [])),
            "token_start_terms": list(category.get("token_start_terms", [])),
        }
        for category in raw["categories"]
    }


def evasion_variants(term: str) -> dict[str, str]:
    """실제 방송에서 관측되는 우회 표기 형태를 프로그램으로 만든다."""
    return {
        "plain": f"그 사람 {term} 진짜야.",
        "jamo": f"그 사람 {output_moderation.decompose_hangul(term)} 진짜야.",
        "partial_jamo": f"그 사람 {term[0]}{output_moderation.decompose_hangul(term[1:])} 진짜야.",
        "symbol": "그 사람 {} 진짜야.".format("*".join(term)),
        "dot": "그 사람 {} 진짜야.".format(".".join(term)),
        "spaced": "그 사람 {} 진짜야.".format(" ".join(term)),
        "leading": f"{term} 라고 했어.",
        "trailing": f"진짜 {term}",
    }


class PolicyLoadingTests(unittest.TestCase):
    def test_shipped_dictionary_loads_with_every_required_category(self) -> None:
        policy = output_moderation.load_moderation_policy()
        self.assertEqual(policy.version, output_moderation.SUPPORTED_POLICY_VERSION)
        counts = policy.counts()
        self.assertEqual(
            set(counts), {"profanity", "hate", "sexual", "violence", "privacy"}
        )
        for identifier, entry in counts.items():
            with self.subTest(category=identifier):
                self.assertGreater(entry["terms"] + entry["patterns"], 0)
        self.assertGreater(counts["privacy"]["patterns"], 0)
        self.assertGreaterEqual(len(policy.blocked_dialogue), 3)

    def test_dictionary_lives_in_data_not_in_code(self) -> None:
        """사전 항목이 코드로 새어 나오면 큐레이션과 배포가 갈라진다."""
        source = Path(output_moderation.__file__).resolve().read_text(encoding="utf-8")
        terms = load_terms()
        for identifier, groups in terms.items():
            for group in groups.values():
                for term in group:
                    with self.subTest(category=identifier):
                        self.assertNotIn(term, source)

    def test_broken_policy_files_are_rejected(self) -> None:
        cases = {
            "not-json": "{",
            "not-object": "[]",
            "bad-version": json.dumps({"version": 99, "categories": []}),
            "no-categories": json.dumps({"version": 1, "categories": []}),
            "bad-pattern": json.dumps(
                {
                    "version": 1,
                    "categories": [{"id": "x", "patterns": ["(unclosed"]}],
                    "blocked_dialogue": ["대체 대사"],
                }
            ),
            "no-dialogue": json.dumps(
                {
                    "version": 1,
                    "categories": [{"id": "x", "terms": ["금칙어후보"]}],
                    "blocked_dialogue": [],
                }
            ),
        }
        for name, payload in cases.items():
            with self.subTest(case=name):
                path = Path(self.enterContext(_temporary_dir())) / "policy.json"
                path.write_text(payload, encoding="utf-8")
                with self.assertRaises(output_moderation.ModerationPolicyError):
                    output_moderation.load_moderation_policy(path)

    def test_missing_policy_file_is_rejected(self) -> None:
        with self.assertRaises(output_moderation.ModerationPolicyError):
            output_moderation.load_moderation_policy(
                Path(self.enterContext(_temporary_dir())) / "absent.json"
            )


class NormalizationTests(unittest.TestCase):
    def test_decompose_and_recompose_agree_on_the_match_stream(self) -> None:
        composed = "안녕하세요"
        self.assertEqual(
            output_moderation.normalize_for_match(composed),
            output_moderation.normalize_for_match(
                output_moderation.decompose_hangul(composed)
            ),
        )

    def test_inserted_symbols_and_spaces_collapse_to_one_stream(self) -> None:
        expected = output_moderation.normalize_for_match("가나다")
        for variant in ("가*나*다", "가 나 다", "가.나.다", "가-나-다"):
            with self.subTest(variant=variant):
                self.assertEqual(output_moderation.normalize_for_match(variant), expected)

    def test_fullwidth_and_conjoining_forms_normalize(self) -> None:
        # 전각 표기와 조합용 자모는 같은 판정 스트림으로 모여야 한다.
        self.assertEqual(
            output_moderation.normalize_for_match("ＡＢ"),
            output_moderation.normalize_for_match("ab"),
        )
        self.assertEqual(
            output_moderation.normalize_for_match("가"),
            output_moderation.normalize_for_match("가"),
        )


class DictionaryCoverageTests(unittest.TestCase):
    """사전 항목 전수에 대해 우회 표기 8종을 확인한다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = output_moderation.load_moderation_policy()
        cls.moderator = output_moderation.OutputModerator(cls.policy)
        cls.terms = load_terms()

    def test_every_dictionary_entry_blocks_in_every_evasion_form(self) -> None:
        checked = 0
        for identifier, groups in self.terms.items():
            for group_name, group in groups.items():
                for index, term in enumerate(group):
                    for variant, text in evasion_variants(term).items():
                        checked += 1
                        verdict = self.moderator.inspect(text)
                        if not verdict.blocked:
                            # 실패 메시지에도 원문을 남기지 않는다.
                            self.fail(
                                f"{identifier}.{group_name}[{index}] "
                                f"was not blocked as {variant}"
                            )
        self.assertGreater(checked, 400)

    def test_token_start_entries_stay_silent_inside_a_longer_word(self) -> None:
        """토큰 첫머리 전용 항목이 낱말 안에서까지 걸리면 정상 대화가 끊긴다."""
        entries = self.terms["sexual"]["token_start_terms"]
        self.assertTrue(entries)
        for index, term in enumerate(entries):
            with self.subTest(entry=index):
                self.assertFalse(self.moderator.inspect(f"어제는 잠{term} 않았어.").blocked)
                self.assertTrue(self.moderator.inspect(f"{term} 얘기 하지 마.").blocked)

    def test_verdict_carries_no_matched_text(self) -> None:
        verdict = self.moderator.inspect(BLOCKED_SAMPLE)
        self.assertTrue(verdict.blocked)
        self.assertEqual(verdict.category, "privacy")
        self.assertEqual(
            set(verdict.as_signal()), {"blocked", "category", "rule"}
        )
        self.assertNotIn("010", json.dumps(verdict.as_signal()))


class FalsePositiveTests(unittest.TestCase):
    """정상 문장 오차단은 게이트를 쓸 수 없게 만드는 회귀다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.moderator = output_moderation.OutputModerator(
            output_moderation.load_moderation_policy()
        )

    def test_ordinary_korean_sentences_are_not_blocked(self) -> None:
        for sentence in BENIGN_SENTENCES:
            with self.subTest(sentence=sentence):
                self.assertFalse(self.moderator.inspect(sentence).blocked)

    def test_empty_and_whitespace_input_is_allowed(self) -> None:
        for text in ("", "   ", "\n\t"):
            with self.subTest(text=repr(text)):
                self.assertFalse(self.moderator.inspect(text).blocked)


class PrivacyPatternTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.moderator = output_moderation.OutputModerator(
            output_moderation.load_moderation_policy()
        )

    def test_personal_identifier_shapes_are_blocked(self) -> None:
        samples = {
            "mobile": "내 번호는 010-1234-5678이야.",
            "mobile_spaced": "번호 010 1234 5678 로 연락해.",
            "landline": "가게는 02-345-6789로 걸면 돼.",
            "resident_registration": "주민번호 900101-1234567 알려줄게.",
            "card": "카드가 1234-5678-9012-3456이래.",
            "email": "메일은 hong@example.com 으로 보내줘.",
            "street_address": "서울시 마포구 합정동 45-3에 살아.",
            "apartment": "우리 집은 101동 1502호야.",
        }
        for name, text in samples.items():
            with self.subTest(shape=name):
                verdict = self.moderator.inspect(text)
                self.assertTrue(verdict.blocked)
                self.assertEqual(verdict.category, "privacy")
                self.assertEqual(verdict.rule, "pattern")

    def test_number_shaped_but_harmless_text_is_not_blocked(self) -> None:
        samples = (
            "우리 회의는 2026-08-12에 하자.",
            "점수는 1234점이었어.",
            "3번 출구에서 만나자.",
            "마포구 합정동 3번 출구에서 봐.",
            "방송은 20시 30분에 시작해.",
        )
        for text in samples:
            with self.subTest(text=text):
                self.assertFalse(self.moderator.inspect(text).blocked)


class RuntimeTests(unittest.TestCase):
    def test_disabled_runtime_needs_no_policy_and_never_blocks(self) -> None:
        runtime = output_moderation.OutputModerationRuntime(enabled=False)
        self.assertFalse(runtime.enabled)
        self.assertFalse(runtime.inspect(BLOCKED_SAMPLE).blocked)
        self.assertEqual(runtime.next_blocked_dialogue(), "")
        health = runtime.health()
        self.assertFalse(health["enabled"])
        self.assertFalse(health["ready"])
        self.assertEqual(health["inspected"], 0)

    def test_enabled_runtime_requires_a_policy(self) -> None:
        with self.assertRaises(output_moderation.ModerationPolicyError):
            output_moderation.OutputModerationRuntime(enabled=True)

    def test_counters_stay_content_free_and_track_blocks(self) -> None:
        runtime = _enabled_runtime()
        runtime.inspect(SAFE_SAMPLE)
        runtime.inspect(BLOCKED_SAMPLE)
        health = runtime.health()
        self.assertTrue(health["enabled"])
        self.assertTrue(health["ready"])
        self.assertEqual(health["inspected"], 2)
        self.assertEqual(health["blocked"], 1)
        self.assertEqual(health["blocked_by_category"], {"privacy": 1})
        self.assertNotIn("010", json.dumps(health, ensure_ascii=False))

    def test_fallback_dialogue_rotates_and_is_never_silent(self) -> None:
        runtime = _enabled_runtime()
        lines = runtime.policy.blocked_dialogue
        produced = [runtime.next_blocked_dialogue() for _ in range(len(lines) * 2)]
        self.assertEqual(set(produced), set(lines))
        self.assertTrue(all(line.strip() for line in produced))
        # 연속 차단이 같은 대사를 반복하면 결함의 콘텐츠화가 아니라 고장으로 보인다.
        self.assertNotEqual(produced[0], produced[1])


class SwitchTests(unittest.TestCase):
    def test_switch_parsing_defaults_to_off(self) -> None:
        for value in ("on", "ON", "1", "true", "yes", "enabled"):
            with self.subTest(value=value):
                self.assertEqual(
                    ollama_proxy.configured_output_moderation(value),
                    ollama_proxy.OUTPUT_MODERATION_ON,
                )
        for value in ("off", "0", "false", "no", "disabled", "", "  ", "maybe", None, 3.5):
            with self.subTest(value=value):
                self.assertEqual(
                    ollama_proxy.configured_output_moderation(value),
                    ollama_proxy.OUTPUT_MODERATION_OFF,
                )

    def test_default_module_state_is_off_and_reads_no_dictionary(self) -> None:
        self.assertEqual(
            ollama_proxy.OUTPUT_MODERATION_MODE, ollama_proxy.OUTPUT_MODERATION_OFF
        )
        self.assertFalse(ollama_proxy.output_moderation_enabled())
        self.assertFalse(ollama_proxy.output_moderation_runtime.enabled)
        self.assertIsNone(ollama_proxy.output_moderation_runtime.policy)

    def test_requested_gate_with_a_broken_dictionary_fails_loudly(self) -> None:
        """켜 달라고 한 안전장치가 조용히 꺼진 채 방송에 나가면 안 된다."""
        missing = Path(self.enterContext(_temporary_dir())) / "absent.json"
        with mock.patch.object(
            ollama_proxy, "OUTPUT_MODERATION_MODE", ollama_proxy.OUTPUT_MODERATION_ON
        ), mock.patch.object(
            ollama_proxy, "OUTPUT_MODERATION_TERMS_PATH", str(missing)
        ):
            with self.assertRaises(output_moderation.ModerationPolicyError):
                ollama_proxy.build_output_moderation_runtime()

    def test_disabled_gate_never_touches_the_dictionary_path(self) -> None:
        missing = Path(self.enterContext(_temporary_dir())) / "absent.json"
        with mock.patch.object(
            ollama_proxy, "OUTPUT_MODERATION_MODE", ollama_proxy.OUTPUT_MODERATION_OFF
        ), mock.patch.object(
            ollama_proxy, "OUTPUT_MODERATION_TERMS_PATH", str(missing)
        ):
            runtime = ollama_proxy.build_output_moderation_runtime()
        self.assertFalse(runtime.enabled)


class SentenceGateTests(unittest.TestCase):
    """문장이 TTS로 나가는 지점의 계약."""

    def test_gate_off_leaves_every_frame_byte_identical(self) -> None:
        for content in (SAFE_SAMPLE, BLOCKED_SAMPLE, ""):
            with self.subTest(content=content):
                frame = ollama_proxy.openai_sse_delta("id-1", "model-1", content)
                payload = _sse_payload(frame)
                self.assertEqual(payload["choices"][0]["delta"]["content"], content)
                self.assertNotIn("airi_moderation", payload)

    def test_gate_off_does_not_consult_the_moderation_runtime(self) -> None:
        runtime = _enabled_runtime()
        with mock.patch.object(ollama_proxy, "output_moderation_runtime", runtime):
            ollama_proxy.openai_sse_delta("id-1", "model-1", BLOCKED_SAMPLE)
        self.assertEqual(runtime.health()["inspected"], 0)

    def test_blocked_sentence_becomes_a_character_line_not_silence(self) -> None:
        with _gate_on() as runtime:
            payload = _sse_payload(
                ollama_proxy.openai_sse_delta("id-1", "model-1", BLOCKED_SAMPLE)
            )
        spoken = payload["choices"][0]["delta"]["content"]
        self.assertTrue(spoken.strip())
        self.assertNotEqual(spoken, BLOCKED_SAMPLE)
        self.assertNotIn("010", spoken)
        self.assertIn(spoken, runtime.policy.blocked_dialogue)

    def test_blocked_sentence_carries_the_filtered_signal(self) -> None:
        with _gate_on():
            payload = _sse_payload(
                ollama_proxy.openai_sse_delta("id-1", "model-1", BLOCKED_SAMPLE)
            )
        signal = payload["airi_moderation"]
        self.assertTrue(signal["blocked"])
        self.assertTrue(signal["replaced"])
        self.assertEqual(signal["category"], "privacy")
        self.assertEqual(signal["rule"], "pattern")

    def test_safe_sentence_passes_through_untouched_when_the_gate_is_on(self) -> None:
        with _gate_on():
            payload = _sse_payload(
                ollama_proxy.openai_sse_delta(
                    "id-1", "model-1", SAFE_SAMPLE, include_role=True
                )
            )
        self.assertEqual(payload["choices"][0]["delta"]["content"], SAFE_SAMPLE)
        self.assertEqual(payload["choices"][0]["delta"]["role"], "assistant")
        self.assertNotIn("airi_moderation", payload)

    def test_immediate_acknowledgement_is_never_filtered(self) -> None:
        """선행 응답이 폴백으로 바뀌면 미리 만들어 둔 음성 캐시가 무효가 된다."""
        with _gate_on():
            for ack in (ollama_proxy.LOCAL_IMMEDIATE_ACK, ollama_proxy.SEARCH_IMMEDIATE_ACK):
                with self.subTest(ack=ack):
                    payload = _sse_payload(
                        ollama_proxy.openai_sse_delta("id-1", "model-1", ack)
                    )
                    self.assertEqual(payload["choices"][0]["delta"]["content"], ack)

    def test_control_envelope_survives_the_replacement(self) -> None:
        with _gate_on() as runtime:
            payload = _sse_payload(
                ollama_proxy.openai_sse_delta(
                    "id-1",
                    "model-1",
                    f'<|ACT {{"emotion":"curious"}}|> {BLOCKED_SAMPLE}',
                )
            )
        spoken = payload["choices"][0]["delta"]["content"]
        self.assertTrue(spoken.startswith('<|ACT {"emotion":"curious"}|>'))
        self.assertTrue(
            any(spoken.endswith(line) for line in runtime.policy.blocked_dialogue)
        )

    def test_grounding_silence_fallback_is_not_filtered(self) -> None:
        with _gate_on():
            payload = _sse_payload(
                ollama_proxy.openai_sse_delta(
                    "id-1", "model-1", ollama_proxy.GROUNDING_SILENCE_FALLBACK_DIALOGUE
                )
            )
        self.assertEqual(
            payload["choices"][0]["delta"]["content"],
            ollama_proxy.GROUNDING_SILENCE_FALLBACK_DIALOGUE,
        )

    def test_replacement_lines_survive_their_own_gate(self) -> None:
        """폴백 대사가 다시 차단되면 게이트가 스스로 물린다."""
        runtime = _enabled_runtime()
        for line in runtime.policy.blocked_dialogue:
            with self.subTest(line=line):
                self.assertFalse(runtime.inspect(line).blocked)

    def test_apply_moderation_reports_no_signal_for_safe_text(self) -> None:
        with _gate_on():
            content, signal = ollama_proxy.apply_output_moderation(SAFE_SAMPLE)
        self.assertEqual(content, SAFE_SAMPLE)
        self.assertIsNone(signal)

    def test_native_ndjson_path_shares_the_same_replacement(self) -> None:
        """네이티브 경로는 시그널 자리가 없어도 대체 대사는 똑같이 적용한다."""
        with _gate_on() as runtime:
            content, signal = ollama_proxy.apply_output_moderation(BLOCKED_SAMPLE)
        self.assertIn(content, runtime.policy.blocked_dialogue)
        self.assertIsNotNone(signal)
        self.assertEqual(runtime.health()["blocked"], 1)


class PerformanceTests(unittest.TestCase):
    """문장당 검사 비용은 문장 단위 TTS 게이트의 예산 안에 있어야 한다."""

    SENTENCE_BUDGET_MS = 1.0

    def test_per_sentence_cost_stays_under_one_millisecond(self) -> None:
        moderator = output_moderation.OutputModerator(
            output_moderation.load_moderation_policy()
        )
        samples = BENIGN_SENTENCES + (BLOCKED_SAMPLE,)
        for sample in samples:  # 캐시·JIT 없는 파이썬이지만 첫 호출 편차는 제거한다.
            moderator.inspect(sample)
        durations: list[float] = []
        for _ in range(200):
            for sample in samples:
                started = time.perf_counter()
                moderator.inspect(sample)
                durations.append((time.perf_counter() - started) * 1000.0)
        durations.sort()
        mean = statistics.fmean(durations)
        p95 = durations[int(len(durations) * 0.95)]
        self.assertLess(
            mean,
            self.SENTENCE_BUDGET_MS,
            f"mean {mean:.4f}ms exceeds the per-sentence budget",
        )
        self.assertLess(
            p95,
            self.SENTENCE_BUDGET_MS,
            f"p95 {p95:.4f}ms exceeds the per-sentence budget",
        )


def _temporary_dir():
    import tempfile

    return tempfile.TemporaryDirectory()


def _enabled_runtime() -> output_moderation.OutputModerationRuntime:
    return output_moderation.OutputModerationRuntime(
        enabled=True, policy=output_moderation.load_moderation_policy()
    )


class _GateOn:
    """모듈 스위치와 런타임을 함께 켠다. 두 개가 어긋나면 시험이 거짓 통과한다."""

    def __enter__(self) -> output_moderation.OutputModerationRuntime:
        self._runtime = _enabled_runtime()
        self._patches = (
            mock.patch.object(
                ollama_proxy, "OUTPUT_MODERATION_MODE", ollama_proxy.OUTPUT_MODERATION_ON
            ),
            mock.patch.object(ollama_proxy, "output_moderation_runtime", self._runtime),
        )
        for patch in self._patches:
            patch.start()
        return self._runtime

    def __exit__(self, *exc_info: object) -> None:
        for patch in reversed(self._patches):
            patch.stop()


def _gate_on() -> _GateOn:
    return _GateOn()


def _sse_payload(frame: bytes) -> dict[str, object]:
    text = frame.decode("utf-8")
    prefix = "data: "
    assert text.startswith(prefix), text
    return json.loads(text[len(prefix):].strip())


if __name__ == "__main__":
    unittest.main()
