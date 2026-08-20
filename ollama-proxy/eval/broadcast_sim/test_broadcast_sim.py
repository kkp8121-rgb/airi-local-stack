from __future__ import annotations

import ast
import copy
import importlib.util
import sys
import types
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROXY_SOURCE = HERE.parent.parent / "ollama_proxy.py"  # ollama-proxy/ollama_proxy.py — read-only(부작용 무거운 import 금지)
SPEC = importlib.util.spec_from_file_location("broadcast_sim_test", HERE / "broadcast_sim.py")
assert SPEC is not None and SPEC.loader is not None
sim = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sim)

sys.path.insert(0, str(HERE))
RUNNER_SPEC = importlib.util.spec_from_file_location(
    "broadcast_sim_runner_test", HERE / "run_broadcast_sim.py")
assert RUNNER_SPEC is not None and RUNNER_SPEC.loader is not None
runner = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(runner)


def message(**overrides):
    base = {"id": "m0000", "t_ms": 0, "minute": 0, "author": "별빛수집가", "archetype": "supporter",
            "kind": "reaction", "text": "잘한다!"}
    base.update(overrides)
    return base


class FixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = sim.load_fixture()

    def test_roster_is_a_hundred_distinct_viewers(self) -> None:
        handles = [viewer["handle"] for viewer in self.fixture["viewers"]]
        self.assertEqual(len(handles), 100)
        self.assertEqual(len(set(handles)), 100)
        self.assertIs(self.fixture["synthetic_only"], True)

    def test_beats_cover_the_whole_broadcast(self) -> None:
        beats = self.fixture["topic"]["beats"]
        self.assertEqual(beats[0]["start_minute"], 0)
        self.assertEqual(beats[-1]["end_minute"], self.fixture["rates"]["broadcast_minutes"])
        self.assertEqual(sim.beat_at(self.fixture, 0)["id"], "opening")
        self.assertEqual(sim.beat_at(self.fixture, 999)["id"], beats[-1]["id"])

    def test_validation_fails_closed(self) -> None:
        broken = [
            {**self.fixture, "schema_version": "other"},
            {**self.fixture, "synthetic_only": False},
            {**self.fixture, "viewers": [self.fixture["viewers"][0], self.fixture["viewers"][0]]},
            {**self.fixture, "viewers": [{**self.fixture["viewers"][0], "archetype": "ghost"},
                                         self.fixture["viewers"][1]]},
            {**self.fixture, "pickup_priority": ["donation", "telepathy"]},
        ]
        for value in broken:
            with self.assertRaises(sim.BroadcastSimError):
                sim.validate_fixture(value)

        gapped = copy.deepcopy(self.fixture)
        gapped["topic"]["beats"][0]["end_minute"] += 1
        with self.assertRaises(sim.BroadcastSimError):
            sim.validate_fixture(gapped)

        inverted = copy.deepcopy(self.fixture)
        inverted["rates"]["messages_per_minute_min"] = 99
        with self.assertRaises(sim.BroadcastSimError):
            sim.validate_fixture(inverted)


class HeldOutFixtureTests(unittest.TestCase):
    """2차 방송은 T3 과적합 검출기다 — 유효하면서 1차·학습 데이터와 분리."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.first = sim.load_fixture()
        cls.second = sim.load_fixture(HERE / "second_broadcast_v1.json")

    def test_second_fixture_is_valid_and_full_scale(self) -> None:
        sim.validate_fixture(self.second)
        self.assertEqual(len(self.second["viewers"]), 100)
        stream = sim.generate_stream(self.second, seed=20260818)
        picks = sim.plan_pickups(stream, self.second)
        self.assertGreater(len(picks), 10)
        picked = {pick["message"]["id"] for pick in picks}
        for item in stream["messages"]:
            if item["kind"] in ("donation", "memory_probe", "memory_seed"):
                self.assertIn(item["id"], picked)

    def test_topic_and_probe_facts_are_disjoint_from_the_first_broadcast(self) -> None:
        self.assertNotEqual(self.first["topic"]["title"], self.second["topic"]["title"])
        first_expect = {token for probe in self.first["memory_probes"] for token in probe["expect_any"]}
        second_expect = {token for probe in self.second["memory_probes"] for token in probe["expect_any"]}
        self.assertFalse(first_expect & second_expect)
        first_tags = {wave["tag"] for wave in self.first["opinion_waves"]}
        second_tags = {wave["tag"] for wave in self.second["opinion_waves"]}
        self.assertFalse(first_tags & second_tags)

    def test_probe_facts_do_not_appear_in_the_training_config(self) -> None:
        # 학습 데이터(행동 SFT config)에 있는 사실값으로 프로브를 만들면
        # 암기를 일반화로 오판한다 — 값 풀과 겹치지 않아야 한다.
        config_path = HERE.parent.parent / "training" / "behavior_synthesis_config_v1.json"
        config_text = config_path.read_text(encoding="utf-8")
        for probe in self.second["memory_probes"]:
            for token in probe["expect_any"]:
                self.assertNotIn(token, config_text, token)

    def test_returning_viewers_are_few_and_the_rest_are_new(self) -> None:
        first_handles = {viewer["handle"] for viewer in self.first["viewers"]}
        second_handles = {viewer["handle"] for viewer in self.second["viewers"]}
        returning = first_handles & second_handles
        self.assertLessEqual(len(returning), 10)
        self.assertGreaterEqual(len(second_handles - first_handles), 90)


class StreamTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = sim.load_fixture()
        self.stream = sim.generate_stream(self.fixture, seed=20260818)

    def test_same_seed_reproduces_the_same_broadcast(self) -> None:
        again = sim.generate_stream(self.fixture, seed=20260818)
        self.assertEqual(sim.canonical_bytes(self.stream), sim.canonical_bytes(again))
        other = sim.generate_stream(self.fixture, seed=1)
        self.assertNotEqual(sim.canonical_bytes(self.stream), sim.canonical_bytes(other))

    def test_stream_is_ordered_and_uniquely_identified(self) -> None:
        times = [item["t_ms"] for item in self.stream["messages"]]
        self.assertEqual(times, sorted(times))
        ids = [item["id"] for item in self.stream["messages"]]
        self.assertEqual(len(set(ids)), len(ids))
        roster = {viewer["handle"] for viewer in self.fixture["viewers"]}
        self.assertTrue({item["author"] for item in self.stream["messages"]} <= roster)

    def test_scripted_events_appear_exactly_once_each(self) -> None:
        kinds = [item["kind"] for item in self.stream["messages"]]
        self.assertEqual(kinds.count("donation"), len(self.fixture["donations"]))
        self.assertEqual(kinds.count("memory_probe"), len(self.fixture["memory_probes"]))
        self.assertEqual(kinds.count("memory_seed"), len(self.fixture["memory_probes"]))

    def test_a_probe_never_precedes_the_fact_it_probes(self) -> None:
        seeds = {item["probe_index"]: item for item in self.stream["messages"] if item["kind"] == "memory_seed"}
        probes = {item["probe_index"]: item for item in self.stream["messages"] if item["kind"] == "memory_probe"}
        self.assertEqual(set(seeds), set(probes))
        for index, probe in probes.items():
            self.assertLess(seeds[index]["t_ms"], probe["t_ms"])
            # 같은 사람이 심고 같은 사람이 되물어야 수신자 판정이 성립한다.
            self.assertEqual(seeds[index]["author"], probe["author"])

    def test_active_speakers_stay_inside_the_configured_band(self) -> None:
        rates = self.fixture["rates"]
        by_minute: dict[int, set[str]] = {}
        for item in self.stream["messages"]:
            by_minute.setdefault(item["minute"], set()).add(item["author"])
        self.assertEqual(len(by_minute), rates["broadcast_minutes"])
        for authors in by_minute.values():
            self.assertLessEqual(len(authors), rates["active_viewers_max"])

    def test_bursts_carry_more_traffic_than_quiet_minutes(self) -> None:
        counts: dict[int, int] = {}
        for item in self.stream["messages"]:
            counts[item["minute"]] = counts.get(item["minute"], 0) + 1
        burst = [counts[minute] for minute in self.fixture["rates"]["burst_minutes"]]
        quiet = [count for minute, count in counts.items() if minute not in self.fixture["rates"]["burst_minutes"]]
        self.assertGreater(min(burst), max(quiet) / 2)
        self.assertGreater(sum(burst) / len(burst), sum(quiet) / len(quiet))


class PickupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = sim.load_fixture()
        self.priority = self.fixture["pickup_priority"]
        self.threshold = self.fixture["rates"]["opinion_aggregate_threshold"]

    def test_priority_beats_recency(self) -> None:
        pending = [message(id="a", t_ms=0, kind="reaction"),
                   message(id="b", t_ms=5, kind="offtopic"),
                   message(id="c", t_ms=9, kind="donation")]
        self.assertEqual(choose := sim.choose_pickup(pending, self.priority, self.threshold), pending[2])
        self.assertEqual(choose["id"], "c")

    def test_oldest_wins_inside_one_kind(self) -> None:
        pending = [message(id="new", t_ms=90, kind="question"), message(id="old", t_ms=10, kind="question")]
        self.assertEqual(sim.choose_pickup(pending, self.priority, self.threshold)["id"], "old")

    def test_a_lone_wave_message_is_only_a_question(self) -> None:
        lonely = [message(id="w", kind="opinion", tag="song_request"),
                  message(id="q", t_ms=1, kind="question")]
        self.assertEqual(sim.effective_kind(lonely[0], lonely, self.threshold), "question")
        # 같은 tag 가 임계값을 채우면 그때부터 여론이다.
        crowd = [message(id=f"w{index}", t_ms=index, kind="opinion", tag="song_request")
                 for index in range(self.threshold)]
        self.assertEqual(sim.effective_kind(crowd[0], crowd, self.threshold), "opinion")
        self.assertEqual(sim.choose_pickup(crowd + [message(id="q", t_ms=99, kind="question")],
                                           self.priority, self.threshold)["id"], "w0")

    def test_empty_backlog_picks_nothing(self) -> None:
        self.assertIsNone(sim.choose_pickup([], self.priority, self.threshold))

    def test_turns_respect_the_cooldown_and_leave_a_backlog(self) -> None:
        stream = sim.generate_stream(self.fixture, seed=20260818)
        picks = sim.plan_pickups(stream, self.fixture)
        rates = self.fixture["rates"]
        gap = (rates["turn_cooldown_seconds"] + rates["window_seconds"]) * 1000
        starts = [pick["window_start_ms"] for pick in picks]
        self.assertEqual(starts, sorted(starts))
        for earlier, later in zip(starts, starts[1:]):
            self.assertGreaterEqual(later - earlier, gap)
        self.assertGreater(len(picks), 10)
        self.assertGreater(max(pick["backlog_size"] for pick in picks), 0)
        # 픽업된 메시지는 다음 턴의 대기열에 남지 않는다.
        for pick in picks:
            self.assertNotIn(pick["message"]["id"], pick["backlog_ids"])

    def test_every_donation_seed_and_probe_is_answered(self) -> None:
        stream = sim.generate_stream(self.fixture, seed=20260818)
        picks = sim.plan_pickups(stream, self.fixture)
        picked = {pick["message"]["id"] for pick in picks}
        for item in stream["messages"]:
            # 시드를 읽지 않으면 프로브는 기억이 아니라 못 들은 말을 묻는 것이 된다.
            if item["kind"] in ("donation", "memory_probe", "memory_seed"):
                self.assertIn(item["id"], picked, f"{item['kind']} {item['id']} 를 놓쳤다")
        order = {pick["message"]["id"]: pick["turn_index"] for pick in picks}
        seeds = {item["probe_index"]: item for item in stream["messages"] if item["kind"] == "memory_seed"}
        for item in stream["messages"]:
            if item["kind"] == "memory_probe":
                self.assertLess(order[seeds[item["probe_index"]]["id"]], order[item["id"]])

    def test_max_turns_truncates_without_reordering(self) -> None:
        stream = sim.generate_stream(self.fixture, seed=20260818)
        full = sim.plan_pickups(stream, self.fixture)
        short = sim.plan_pickups(stream, self.fixture, max_turns=5)
        self.assertEqual(len(short), 5)
        self.assertEqual([pick["message"]["id"] for pick in short],
                         [pick["message"]["id"] for pick in full[:5]])


class BriefingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = sim.load_fixture()
        self.stream = sim.generate_stream(self.fixture, seed=20260818)
        self.picks = sim.plan_pickups(self.stream, self.fixture)

    def test_briefing_is_deterministic_and_carries_the_viewer_history(self) -> None:
        # 같은 시청자의 두 번째 이후 픽업을 찾아 그 사람의 과거 발언이 실리는지 본다.
        seen: dict[str, dict] = {}
        target = None
        for pick in self.picks:
            author = pick["message"]["author"]
            if author in seen:
                target = pick
                break
            seen[author] = pick
        assert target is not None
        prior = [{**pick, "response": "응답"} for pick in self.picks[: target["turn_index"] - 1]]
        briefing = sim.build_turn_briefing(self.fixture, self.stream, target, prior)
        again = sim.build_turn_briefing(self.fixture, self.stream, target, prior)
        self.assertEqual(briefing, again)
        self.assertIn(target["message"]["author"], briefing)
        self.assertIn("이 시청자가 아까 한 말", briefing)
        self.assertIn("방금 흐름", briefing)
        config = self.fixture["briefing"]
        self.assertLessEqual(briefing.count("이 시청자가 아까 한 말"), config["max_viewer_lines"])
        self.assertLessEqual(briefing.count("방금 흐름"), config["max_recent_picks"])

    def test_viewer_lines_prefer_relevance_over_recency(self) -> None:
        # T21 실측 재현: 시드가 최신 발언들에 밀려 사라지던 결함 — 지금 질문과
        # 토큰이 겹치는 과거 발언이 최근성보다 먼저 자리를 차지해야 한다.
        probe = next(pick for pick in self.picks if pick["message"]["kind"] == "memory_probe"
                     and pick["message"].get("probe_index") == 0)
        chosen = sim.select_viewer_lines(self.fixture, self.stream, probe)
        texts = [item["text"] for item in chosen]
        self.assertTrue(any("별명" in text or "새벽두시" in text for text in texts), texts)
        briefing = sim.build_turn_briefing(self.fixture, self.stream, probe, [])
        self.assertIn("새벽두시", briefing)

    def test_relevant_lines_become_directives_and_filler_lines_stay_memos(self) -> None:
        # 수동 메모의 활용률 7% 실측 이후: 관련 줄은 지시형으로 요구한다.
        probe = next(pick for pick in self.picks if pick["message"]["kind"] == "memory_probe"
                     and pick["message"].get("probe_index") == 0)
        briefing = sim.build_turn_briefing(self.fixture, self.stream, probe, [])
        self.assertIn("그대로 써서 답해", briefing)
        self.assertIn("새벽두시", briefing)
        tagged = sim.select_viewer_lines_tagged(self.fixture, self.stream, probe)
        self.assertTrue(any(relevant for _item, relevant in tagged))
        # 관련이 하나도 없는 픽업은 지시형이 나오지 않는다.
        plain = next(pick for pick in self.picks
                     if not any(relevant for _item, relevant
                                in sim.select_viewer_lines_tagged(self.fixture, self.stream, pick))
                     and sim.select_viewer_lines(self.fixture, self.stream, pick))
        memo_briefing = sim.build_turn_briefing(self.fixture, self.stream, plain, [])
        self.assertNotIn("그대로 써서 답해", memo_briefing)
        self.assertIn("이 시청자가 아까 한 말", memo_briefing)

    def test_degenerate_fixed_lines_are_blanked_before_echo(self) -> None:
        # 8자 필터를 통과하는 고정 폴백("아직 기록이 없어." 11자)의 전염 차단.
        prior = [
            {**self.picks[0], "response": "아직 기록이 없어. 어떻게 부르면 돼?"},
            {**self.picks[1], "response": "음… 그건 확실하게 기억 안 나. 다시 알려줄래?"},
            {**self.picks[2], "response": "오늘 첫 방송이라 진짜 신난다!"},
        ]
        sanitized = sim.blank_degenerate_echo(prior, ("아직 기록", "음… 그건 확실하게 기억 안 나"))
        self.assertEqual(sanitized[0]["response"], "")
        self.assertEqual(sanitized[1]["response"], "")
        self.assertEqual(sanitized[2]["response"], "오늘 첫 방송이라 진짜 신난다!")
        # 원본은 무변경(전사에는 원문이 남아야 한다).
        self.assertTrue(prior[0]["response"].startswith("아직 기록"))

    def test_low_content_replies_are_not_echoed_back(self) -> None:
        # T35 실측 재현: "아직 기록 없어" 같은 저품질 응답을 되먹이면 모델이
        # 그 문형을 따라 한다 — 짧은 응답의 에코는 빠져야 한다.
        pick = self.picks[6]
        prior_short = [{**self.picks[5], "response": "응!"}]
        prior_long = [{**self.picks[5], "response": "오늘 첫 방송이라 진짜 떨리는데 재밌다!"}]
        without_echo = sim.build_turn_briefing(self.fixture, self.stream, pick, prior_short)
        with_echo = sim.build_turn_briefing(self.fixture, self.stream, pick, prior_long)
        self.assertNotIn("→ 나:", without_echo)
        self.assertIn("→ 나:", with_echo)
        self.assertIn("방금 흐름", without_echo)  # 채팅 자체는 남는다

    def test_live_absence_and_silence_fallbacks_are_blanked_regardless_of_length(self) -> None:
        # 갭 등록(2026-08-19): 프록시 absence 폴백("아직 기록이 없어. 어떻게
        # 부르면 돼?" 17자)은 8자 길이 필터만으로는 걸러지지 않는다. 실제로
        # 전염을 막는 건 run_broadcast_sim.py 가 매 턴 앞서 돌리는
        # blank_degenerate_echo(FALLBACK_POOL + DEGENERATE_ECHO_PREFIXES) 다 —
        # 여기서 그 결합 필터를 실제로 통과시켜 규명한다(4-1).
        pick = self.picks[6]
        prior_slot = self.picks[5]
        combined = runner.FALLBACK_POOL + runner.DEGENERATE_ECHO_PREFIXES
        absence_lines = (
            "아직 기록이 없어. 어떻게 부르면 돼?",  # ollama_proxy.memory_absence_dialogue (별명/이름 질문)
            "아직 그건 기록이 없어. 다시 알려줄래?",  # ollama_proxy.memory_absence_dialogue (그 외)
        )
        for line in absence_lines:
            # 원 갭 등록의 핵심 조건 — 8자 길이 필터'만'으로는 못 걸렀을 문구.
            # 침묵 풀 6종 중 일부(예: "음, 잠깐만." 7자)는 원래도 길이 필터를
            # 통과하므로 이 assert 대상이 아니다 — 결합 필터 자체는 아래에서
            # 전체(absence + 침묵 풀)에 공통으로 검증한다.
            self.assertGreaterEqual(len(line), 8, line)
        live_fallback_lines = (*absence_lines, *runner.FALLBACK_POOL)
        for response in live_fallback_lines:
            with self.subTest(response=response):
                prior = [{**prior_slot, "response": response}]
                echo_safe = sim.blank_degenerate_echo(prior, combined)
                briefing = sim.build_turn_briefing(self.fixture, self.stream, pick, echo_safe)
                self.assertNotIn("→ 나:", briefing)
                if len(response) >= 8:
                    # 대조군: 8자 이상인데 blank_degenerate_echo 를 안 거치면
                    # (수리 전 상태 재현) 길이 필터만으로는 못 걸러 새어 나간다
                    # — 이 테스트가 회귀에 민감한지 증명한다. 8자 미만 문구는
                    # 애초에 길이 필터 하나로도 막히므로 이 대조군 대상이 아니다.
                    leaking = sim.build_turn_briefing(self.fixture, self.stream, pick, prior)
                    self.assertIn("→ 나:", leaking)

    def test_fact_usage_scores_only_briefed_novel_tokens(self) -> None:
        probe = next(pick for pick in self.picks if pick["message"]["kind"] == "memory_probe"
                     and pick["message"].get("probe_index") == 0)
        tokens = set()
        for item in sim.select_viewer_lines(self.fixture, self.stream, probe):
            tokens |= sim._tokens(item["text"])
        beat = sim.beat_at(self.fixture, probe["message"]["minute"])
        roster = [viewer["handle"] for viewer in self.fixture["viewers"]]
        used = sim.score_turn(probe, "새벽두시였지!", beat=beat, fallback_pool=(),
                              roster_handles=roster, briefing_fact_tokens=sorted(tokens))
        self.assertTrue(used["fact_usage"])
        self.assertTrue(any(token.startswith("새벽두시") for token in used["fact_tokens_used"]), used["fact_tokens_used"])
        unused = sim.score_turn(probe, "음, 뭐였더라?", beat=beat, fallback_pool=(),
                                roster_handles=roster, briefing_fact_tokens=sorted(tokens))
        self.assertFalse(unused["fact_usage"])
        # 브리핑이 없던 턴은 분모에서 빠진다.
        none_row = sim.score_turn(probe, "새벽두시였지!", beat=beat, fallback_pool=(),
                                  roster_handles=roster, briefing_fact_tokens=None)
        self.assertIsNone(none_row["fact_usage"])
        summary = sim.summarize_turns([used, unused, none_row])
        self.assertEqual(summary["viewer_fact_usage"], {"hits": 1, "of": 2, "rate": 0.5})

    def test_briefing_reports_wave_pressure_from_the_backlog(self) -> None:
        wave_pick = next(pick for pick in self.picks
                         if pick["effective_kind"] == "opinion" and pick["backlog_ids"])
        briefing = sim.build_turn_briefing(self.fixture, self.stream, wave_pick, [])
        self.assertIn("대기 채팅", briefing)
        labels = [wave.get("label") for wave in self.fixture["opinion_waves"]]
        self.assertTrue(any(f"{label} 요청" in briefing for label in labels), briefing)

    def test_briefing_surfaces_a_recent_donation(self) -> None:
        donation_pick = next(pick for pick in self.picks if pick["effective_kind"] == "donation")
        index = donation_pick["turn_index"]
        following = next(pick for pick in self.picks if pick["turn_index"] > index)
        prior = [{**pick, "response": "응답"} for pick in self.picks[: following["turn_index"] - 1]]
        briefing = sim.build_turn_briefing(self.fixture, self.stream, following, prior)
        self.assertIn("직전 후원", briefing)

    def test_briefing_clips_lines_to_the_configured_budget(self) -> None:
        config = self.fixture["briefing"]
        pick = self.picks[5]
        prior = [{**earlier, "response": "가" * 200} for earlier in self.picks[:5]]
        briefing = sim.build_turn_briefing(self.fixture, self.stream, pick, prior)
        for line in briefing.splitlines():
            if "→ 나:" in line:
                quoted = line.split("→ 나: ")[1].strip('"')
                self.assertLessEqual(len(quoted), config["max_line_chars"] + 1)


class _FakeTransport:
    """헤더만 관찰하는 전송 스텁 — 모델도 네트워크도 쓰지 않는다."""

    def __init__(self) -> None:
        self.client = types.SimpleNamespace(headers={})
        self.seen: list[dict[str, str]] = []

    def stream_chat(self, *, model, messages, max_tokens, timeout):
        self.seen.append(dict(self.client.headers))
        return "응, 그렇구나!", 5.0, 10.0, {"status_code": 200}


class BriefingEvidenceSignalTests(unittest.TestCase):
    """디렉터→프록시 근거 신호: 브리핑이 회상 재료를 실은 턴에만 붙는다."""

    def setUp(self) -> None:
        self.fixture = sim.load_fixture()
        self.stream = sim.generate_stream(self.fixture, seed=20260818)
        self.picks = sim.plan_pickups(self.stream, self.fixture)

    def test_assembly_reports_whether_it_carried_recall_material(self) -> None:
        first_time = next(pick for pick in self.picks
                          if not sim.select_viewer_lines(self.fixture, self.stream, pick))
        returning = next(pick for pick in self.picks
                         if sim.select_viewer_lines(self.fixture, self.stream, pick))
        for pick, expected in ((first_time, False), (returning, True)):
            text, evidence = sim.build_turn_briefing_with_evidence(
                self.fixture, self.stream, pick, [])
            self.assertIs(evidence, expected)
            # 근거 여부는 조립 시점의 사실이고, 본문은 기존과 바이트 동일하다.
            self.assertEqual(text, sim.build_turn_briefing(self.fixture, self.stream, pick, []))

    def _run(self, briefing: str, briefing_evidence: str) -> tuple[_FakeTransport, list[bool]]:
        transport = _FakeTransport()
        picks = self.picks[:12]
        runner.run_arm(
            transport, self.fixture, self.stream, picks,
            model="test-model", contract="on", protocol="operational",
            author_format="runtime", history_turns=8, max_tokens=32, timeout=1.0,
            pre_session_seeds=False, briefing=briefing, acts="off",
            briefing_evidence=briefing_evidence,
        )
        expected = [bool(sim.select_viewer_lines(self.fixture, self.stream, pick))
                    for pick in picks]
        return transport, expected

    def test_header_rides_only_the_turns_whose_briefing_holds_evidence(self) -> None:
        transport, expected = self._run("on", "on")
        attached = [runner.BRIEFING_EVIDENCE_HEADER in headers for headers in transport.seen]
        self.assertEqual(attached, expected)
        self.assertTrue(any(expected), "근거를 실은 턴이 하나도 없으면 검증이 성립하지 않는다")
        values = {headers.get(runner.BRIEFING_EVIDENCE_HEADER) for headers in transport.seen
                  if runner.BRIEFING_EVIDENCE_HEADER in headers}
        self.assertEqual(values, {runner.BRIEFING_EVIDENCE_MEMORY})

    def test_signal_stays_off_by_default_and_without_a_briefing(self) -> None:
        for briefing, evidence in (("on", "off"), ("off", "on"), ("off", "off")):
            with self.subTest(briefing=briefing, briefing_evidence=evidence):
                transport, _expected = self._run(briefing, evidence)
                self.assertFalse(any(runner.BRIEFING_EVIDENCE_HEADER in headers
                                     for headers in transport.seen))


class EchoFilterProxyContractTests(unittest.TestCase):
    """ollama_proxy.py 의 결정론 폴백 문구와 run_broadcast_sim.py 의 에코 차단
    상수가 어긋나지 않는지 확인한다. ollama_proxy 모듈은 import 부작용이
    무거워(레포 관례) 여기서도 직접 import하지 않고, 소스를 AST로만 읽는다
    (ollama-proxy/eval/test_run_airi_conversation_soak_transport.py 의
    literal contract 테스트와 같은 방식)."""

    def _proxy_tree(self) -> ast.Module:
        return ast.parse(PROXY_SOURCE.read_text(encoding="utf-8"))

    def _proxy_absence_fallback_lines(self) -> tuple[str, ...]:
        tree = self._proxy_tree()
        lines: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "memory_absence_dialogue":
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Constant):
                        lines.append(sub.value.value)
        return tuple(lines)

    def _proxy_silence_fallback_pool(self) -> tuple[str, ...]:
        tree = self._proxy_tree()
        simple_values: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "GROUNDING_SILENCE_FALLBACK_DIALOGUE":
                        simple_values[target.id] = ast.literal_eval(node.value)
        pool_elts: list[ast.expr] | None = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "GROUNDING_SILENCE_FALLBACK_POOL":
                        assert isinstance(node.value, ast.Tuple)
                        pool_elts = list(node.value.elts)
        assert pool_elts is not None, "GROUNDING_SILENCE_FALLBACK_POOL 을 프록시 소스에서 못 찾았다"
        return tuple(
            simple_values[elt.id] if isinstance(elt, ast.Name) else ast.literal_eval(elt)
            for elt in pool_elts
        )

    def test_absence_fallback_wording_is_covered_by_the_runner_prefixes(self) -> None:
        # ollama_proxy.memory_absence_dialogue() 의 두 문구 — 소스에서 직접 뽑아
        # 하드코딩 중복 없이 대조한다.
        absence_lines = self._proxy_absence_fallback_lines()
        self.assertEqual(len(absence_lines), 2, absence_lines)
        for line in absence_lines:
            with self.subTest(line=line):
                self.assertTrue(
                    line.startswith(runner.DEGENERATE_ECHO_PREFIXES),
                    f"{line!r} 가 run_broadcast_sim.DEGENERATE_ECHO_PREFIXES 에 안 걸린다 — 구멍",
                )

    def test_runner_fallback_pool_matches_the_live_silence_rotation(self) -> None:
        # ollama_proxy.GROUNDING_SILENCE_FALLBACK_POOL(6종)과 러너 FALLBACK_POOL
        # 이 같은 문구 집합이어야 침묵 폴백률 계산과 에코 차단이 의미를 갖는다.
        live_pool = self._proxy_silence_fallback_pool()
        self.assertEqual(len(live_pool), 6, live_pool)
        self.assertEqual(set(live_pool), set(runner.FALLBACK_POOL))


class ScoringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = sim.load_fixture()
        self.beat = sim.beat_at(self.fixture, 0)
        self.roster = [viewer["handle"] for viewer in self.fixture["viewers"]]

    def pick(self, msg, **extra):
        return {"turn_index": 1, "message": msg, "effective_kind": msg["kind"], "backlog_size": 0,
                "backlog_ids": [], "wave_size": 0, "aggregate_expected": False, **extra}

    def score(self, msg, body, **extra):
        return sim.score_turn(self.pick(msg, **extra), body, beat=self.beat,
                              fallback_pool=("음, 잠깐만.",), roster_handles=self.roster,
                              drift_terms=sorted(sim.offtopic_terms(self.fixture)))

    def test_silence_fallback_is_flagged_and_not_counted_as_topical(self) -> None:
        row = self.score(message(text="이름 뜻이 뭐야?", kind="question"), "음, 잠깐만.")
        self.assertTrue(row["is_fallback"])
        self.assertFalse(row["topic_anchored"])
        self.assertFalse(row["empty"])

    def test_topic_anchoring_accepts_either_an_anchor_or_a_shared_token(self) -> None:
        self.assertTrue(self.score(message(text="이름 뜻이 뭐야?"), "이름은 그냥 AIRI야")["topic_anchored"])
        self.assertTrue(self.score(message(text="아무 말"), "오늘 첫 방송이라 떨려")["topic_anchored"])
        # 정상적인 짧은 반응은 주제어를 공유하지 않는다 — 그래서 이건 이탈 판정이 아니다.
        row = self.score(message(text="응원할게"), "고마워!")
        self.assertFalse(row["topic_anchored"])
        self.assertEqual(row["drift"], [])

    def test_drift_only_fires_on_offtopic_words_the_viewer_did_not_say(self) -> None:
        self.assertEqual(self.score(message(text="이름 뜻이 뭐야?"), "고구마 좋아해?")["drift"], ["고구마"])
        # 시청자가 먼저 꺼낸 딴소리를 받아준 것은 이탈이 아니다.
        self.assertEqual(self.score(message(text="고구마 맛있더라", kind="offtopic"), "고구마 좋지!")["drift"], [])

    def test_callout_separates_recall_from_invention(self) -> None:
        donation = message(kind="donation", author="별빛수집가", text="첫 방송 축하해!")
        correct = self.score(donation, "별빛수집가, 고마워! 덕분에 힘난다")
        self.assertTrue(correct["callout_correct"])
        self.assertEqual(correct["invented_handles"], [])

        wrong = self.score(donation, "라면요정, 고마워!")
        self.assertFalse(wrong["callout_correct"])
        self.assertEqual(wrong["invented_handles"], ["라면요정"])

        twice = self.score(donation, "별빛수집가! 별빛수집가 고마워")
        self.assertFalse(twice["callout_correct"])
        self.assertEqual(twice["callout_count"], 2)

    def test_addressee_checks_are_fixture_driven(self) -> None:
        birthday = message(kind="donation", text="오늘 내 생일인데 같이 기념하려고 왔어",
                           checks={"forbidden": ["생일\\s*축하"], "required_any": ["고마워", "축하", "기념"]})
        self.assertFalse(self.score(birthday, "생일 축하해!")["addressee_ok"])
        self.assertTrue(self.score(birthday, "같이 기념해줘서 고마워!")["addressee_ok"])
        self.assertIsNone(self.score(message(text="안녕"), "안녕!")["addressee_ok"])

    def test_memory_probe_hit_requires_the_seeded_token(self) -> None:
        probe = message(kind="memory_probe", text="내 별명 기억나?", expect_any=["새벽두시"])
        self.assertTrue(self.score(probe, "새벽두시였지!")["probe_hit"])
        self.assertFalse(self.score(probe, "음, 뭐였더라?")["probe_hit"])

    def test_wave_scoring_separates_topic_from_plurality(self) -> None:
        wave = message(kind="opinion", text="노래 한 곡만!", tag="song_request", aggregate_markers=["노래"])
        row = self.score(wave, "다들 노래 노래 하는데 아직 준비가 안 됐어", aggregate_expected=True, wave_size=5)
        self.assertTrue(row["wave_topic_answered"])
        self.assertTrue(row["wave_plurality_marked"])
        alone = self.score(wave, "노래는 다음에!", aggregate_expected=True, wave_size=5)
        self.assertTrue(alone["wave_topic_answered"])
        self.assertFalse(alone["wave_plurality_marked"])

    def test_summary_reports_each_rate_with_its_own_denominator(self) -> None:
        rows = [
            self.score(message(kind="donation", author="별빛수집가", text="첫 방송 축하해!",
                               checks={"required_any": ["고마워"]}), "별빛수집가, 고마워!"),
            self.score(message(kind="memory_probe", text="기억나?", expect_any=["초코"]), "음, 잠깐만."),
            self.score(message(text="이름 뜻이 뭐야?"), "이름은 AIRI야"),
        ]
        summary = sim.summarize_turns(rows)
        self.assertEqual(summary["turns"], 3)
        self.assertEqual(summary["fallback"], {"hits": 1, "of": 3, "rate": round(1 / 3, 4)})
        self.assertEqual(summary["donation_callout_correct"], {"hits": 1, "of": 1, "rate": 1.0})
        self.assertEqual(summary["memory_probe"], {"hits": 0, "of": 1, "rate": 0.0})
        self.assertEqual(summary["addressee"]["of"], 1)
        self.assertIsNone(summary["opinion_topic_answered"]["rate"])


if __name__ == "__main__":
    unittest.main()
