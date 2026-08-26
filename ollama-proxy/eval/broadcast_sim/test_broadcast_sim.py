from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path
from typing import Any


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


class _LiveResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")


class _LiveClient:
    def __init__(self, events: list[tuple[str, object]], health: dict[str, Any] | None = None) -> None:
        self.headers: dict[str, str] = {}
        self.events = events
        self.receipt_calls = 0
        self.health = {
            "broadcast_contract": True, "immediate_ack": "marker",
        } if health is None else health

    def get(self, url: str, *, timeout: float):
        self.events.append(("health", {"url": url}))
        return _LiveResponse(200, self.health)

    def post(self, url: str, *, json: dict[str, object], headers: dict[str, str]):
        action = str(json.get("action", "receipt"))
        self.events.append((action, {"url": url, "payload": json, "headers": headers}))
        if action == "issue_turn":
            return _LiveResponse(200, {"turn_token": "t" * 32, "delivery_token": "d" * 32})
        if action == "receipt":
            self.receipt_calls += 1
            return _LiveResponse(202 if self.receipt_calls == 1 else 200, {"status": "pending"})
        return _LiveResponse(200, {})


class _LiveTransport:
    def __init__(self, health: dict[str, Any] | None = None) -> None:
        self.events: list[tuple[str, object]] = []
        self.client = _LiveClient(self.events, health)
        self.messages: list[list[dict[str, str]]] = []

    def stream_chat(self, *, model, messages, max_tokens, timeout):
        self.messages.append(messages)
        self.events.append(("chat", dict(self.client.headers)))
        return '<|ACT {"emotion":"think"}|>live answer', 5.0, 10.0, {
            "status_code": 200, "streaming": True, "terminal": True,
            "immediate_ack": "marker",
        }

    def close(self) -> None:
        self.events.append(("transport_close", {}))


class LiveBroadcastContextRunnerTests(unittest.TestCase):
    def test_main_binds_live_turn_then_retries_durable_receipt_without_system_prompt(self) -> None:
        transport = _LiveTransport()
        environment = {
            runner.LIVE_CONTEXT_ENV_MASTER: "m" * 32,
            runner.LIVE_CONTEXT_ENV_OBSERVER: "o" * 32,
        }
        with mock.patch.object(
                runner.ab, "HttpTransport", return_value=transport,
        ) as transport_constructor, \
             mock.patch.dict(os.environ, environment, clear=False), \
             mock.patch.object(runner.time, "sleep", return_value=None):
            self.assertEqual(runner.main(["--max-turns", "1", "--live-broadcast-context", "on"]), 0)

        transport_constructor.assert_called_once_with(
            "http://127.0.0.1:11435/v1", None, stream_mode="on",
        )
        self.assertEqual([name for name, _data in transport.events[:6]],
                         ["health", "start", "issue_turn", "chat", "receipt", "receipt"])
        issue = transport.events[2][1]["payload"]
        context = issue["broadcast_context"]
        self.assertEqual(context["schema_version"], 1)
        self.assertEqual(context["topic_title"], sim.load_fixture()["topic"]["title"])
        self.assertFalse(context["donation_continuation"])
        self.assertTrue(all(message["role"] != "system" for message in transport.messages[0]))
        chat_headers = transport.events[3][1]
        receipt = transport.events[5][1]["payload"]
        user_content = transport.messages[0][-1]["content"]
        self.assertEqual(receipt["trace_id"], chat_headers["x-airi-request-id"])
        self.assertEqual(receipt["query_sha256"], runner.sha256_text(user_content))
        self.assertEqual(receipt["user_sha256"], runner.sha256_text(user_content))
        self.assertEqual(receipt["answer_sha256"], runner.sha256_text("live answer"))
        self.assertEqual(transport.events[6][0], "close")

    def test_report_records_max_tokens_and_served_model_digest(self) -> None:
        # R2 F6: the report must carry the confounders the comparator compares.
        digest = "f" * 64
        health = {"broadcast_contract": True, "immediate_ack": "marker",
                  "chat_model": {"digest": {"status": "pinned", "verified": True, "digest": digest}}}
        environment = {
            runner.LIVE_CONTEXT_ENV_MASTER: "m" * 32,
            runner.LIVE_CONTEXT_ENV_OBSERVER: "o" * 32,
        }
        with tempfile.TemporaryDirectory() as raw:
            report_path = Path(raw) / "report.json"
            for label, transport in (("pinned", _LiveTransport(health)), ("absent", _LiveTransport())):
                with self.subTest(health=label), \
                     mock.patch.object(runner.ab, "HttpTransport", return_value=transport), \
                     mock.patch.dict(os.environ, environment, clear=False), \
                     mock.patch.object(runner.time, "sleep", return_value=None):
                    report_path.unlink(missing_ok=True)
                    self.assertEqual(runner.main(["--max-turns", "1", "--live-broadcast-context", "on",
                                                  "--max-tokens", "96", "--report", str(report_path)]), 0)
                report = json.loads(report_path.read_text(encoding="utf-8"))
                self.assertEqual(report["max_tokens"], 96)
                self.assertEqual(report["model_digest"], digest if label == "pinned" else None)
                # The digest is read after the show closes and before the transport closes.
                names = [event[0] for event in transport.events]
                self.assertEqual(names[-3:], ["close", "health", "transport_close"])

    def test_live_contract_must_match_on_off_and_be_present(self) -> None:
        for contract, health in (("on", {"broadcast_contract": False, "immediate_ack": "marker"}),
                                 ("off", {"broadcast_contract": True, "immediate_ack": "marker"}),
                                 ("on", {})):
            transport = _LiveTransport(health)
            environment = {
                runner.LIVE_CONTEXT_ENV_MASTER: "m" * 32,
                runner.LIVE_CONTEXT_ENV_OBSERVER: "o" * 32,
            }
            with mock.patch.object(runner.ab, "HttpTransport", return_value=transport), \
                 mock.patch.dict(os.environ, environment, clear=False):
                with self.assertRaisesRegex(RuntimeError, "contract"):
                    runner.main(["--max-turns", "1", "--contract", contract,
                                 "--live-broadcast-context", "on"])
            self.assertEqual([event[0] for event in transport.events], ["health", "transport_close"])

    def test_live_preseeds_are_receipted_before_the_first_scored_capability(self) -> None:
        transport = _LiveTransport()
        environment = {
            runner.LIVE_CONTEXT_ENV_MASTER: "m" * 32,
            runner.LIVE_CONTEXT_ENV_OBSERVER: "o" * 32,
        }
        with mock.patch.object(runner.ab, "HttpTransport", return_value=transport), \
             mock.patch.dict(os.environ, environment, clear=False), \
             mock.patch.object(runner.time, "sleep", return_value=None):
            self.assertEqual(runner.main(["--memory-arm", "seeded", "--max-turns", "1",
                                          "--live-broadcast-context", "on"]), 0)
        events = [event[0] for event in transport.events]
        controls = [event for event in transport.events if event[0] in {"start", "close"}]
        self.assertEqual([event[0] for event in controls], ["start", "close", "start", "close"])
        preseed_show_id = controls[0][1]["payload"]["show_id"]
        scored_show_id = controls[2][1]["payload"]["show_id"]
        self.assertNotEqual(preseed_show_id, scored_show_id)
        self.assertEqual(controls[1][1]["payload"]["show_id"], preseed_show_id)
        self.assertEqual(controls[3][1]["payload"]["show_id"], scored_show_id)
        first_scored_issue = next(
            index for index, event in enumerate(transport.events)
            if event[0] == "issue_turn" and event[1]["payload"]["action_id"].startswith("turn-")
        )
        first_preseed_close = events.index("close")
        scored_start = events.index("start", events.index("start") + 1)
        self.assertIn("receipt", events[:first_preseed_close])
        self.assertLess(first_preseed_close, scored_start)
        self.assertLess(scored_start, first_scored_issue)
        self.assertTrue(all(message[0]["role"] == "user" for message in transport.messages))
        chat_headers = [event[1] for event in transport.events if event[0] == "chat"]
        self.assertEqual({headers[runner.SESSION_HEADER] for headers in chat_headers},
                         {"broadcast-sim-seeded-20260818"})

    def test_preseed_close_error_fails_the_run_before_scored_show_starts(self) -> None:
        transport = _LiveTransport()
        original_post = transport.client.post

        def reject_close(url, *, json, headers):
            if json.get("action") == "close":
                return _LiveResponse(500, {"error": "close failed"})
            return original_post(url, json=json, headers=headers)

        transport.client.post = reject_close
        environment = {
            runner.LIVE_CONTEXT_ENV_MASTER: "m" * 32,
            runner.LIVE_CONTEXT_ENV_OBSERVER: "o" * 32,
        }
        with mock.patch.object(runner.ab, "HttpTransport", return_value=transport), \
             mock.patch.dict(os.environ, environment, clear=False), \
             mock.patch.object(runner.time, "sleep", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "capability unavailable"):
                runner.main(["--memory-arm", "seeded", "--max-turns", "1",
                             "--live-broadcast-context", "on"])
        self.assertEqual([event[0] for event in transport.events].count("start"), 1)

    def test_live_receipt_rejection_of_raw_hash_fails_closed(self) -> None:
        transport = _LiveTransport()
        original_post = transport.client.post

        def reject_raw_hash(url, *, json, headers):
            if "delivery_token" in json:
                return _LiveResponse(400, {"error": "answer hash mismatch"})
            return original_post(url, json=json, headers=headers)

        transport.client.post = reject_raw_hash
        live = {"base_url": "http://example/v1", "master_token": "m" * 32,
                "observer_token": "o" * 32, "show_id": "show"}
        with self.assertRaisesRegex(RuntimeError, "capability unavailable"):
            runner.run_live_capability_turn(
                transport, live, model="test", messages=[{"role": "user", "content": "u"}],
                user_content="u", max_tokens=1, timeout=1.0, action_id="a", trace_id="t",
                turn_type="chat_question",
            )

    def test_live_input_screening_block_fails_before_receipt(self) -> None:
        transport = _LiveTransport()
        transport.stream_chat = mock.Mock(return_value=(
            "blocked answer", 5.0, 10.0,
            {
                "status_code": 200, "streaming": True, "terminal": True,
                "immediate_ack": "false", "input_screened": "blocked",
                "input_screen_category": "privacy",
            },
        ))
        live = {"base_url": "http://example/v1", "master_token": "m" * 32,
                "observer_token": "o" * 32, "show_id": "show"}
        with self.assertRaisesRegex(RuntimeError, "category=privacy"):
            runner.run_live_capability_turn(
                transport, live, model="test", messages=[{"role": "user", "content": "u"}],
                user_content="u", max_tokens=1, timeout=1.0, action_id="a", trace_id="t",
                turn_type="chat_question",
            )
        self.assertEqual(transport.client.receipt_calls, 0)

    def test_live_receipt_binds_substantive_body_after_marker_ack(self) -> None:
        transport = _LiveTransport()
        transport.stream_chat = mock.Mock(return_value=(
            '<|ACT {"emotion":"think"}|>live answer', 5.0, 10.0,
            {"status_code": 200, "streaming": True, "terminal": True,
             "immediate_ack": "marker"},
        ))
        live = {"base_url": "http://example/v1", "master_token": "m" * 32,
                "observer_token": "o" * 32, "show_id": "show"}
        with mock.patch.object(runner.time, "sleep", return_value=None):
            record, ok = runner.run_live_capability_turn(
                transport, live, model="test", messages=[{"role": "user", "content": "u"}],
                user_content="u", max_tokens=1, timeout=1.0, action_id="a", trace_id="t",
                turn_type="chat_question",
            )
        self.assertTrue(ok)
        receipt = next(
            event[1]["payload"] for event in transport.events
            if event[0] == "receipt"
        )
        self.assertEqual(receipt["answer_sha256"], runner.sha256_text("live answer"))
        self.assertEqual(record["receipt_binding"], {
            "schema": "airi.attested-stream-answer.v1",
            "leading_marker_stripped": True,
        })

    def test_live_receipt_binds_terminal_dialogue_when_response_has_no_ack(self) -> None:
        transport = _LiveTransport()
        transport.stream_chat = mock.Mock(return_value=(
            "  answer without marker  ", 5.0, 10.0,
            {"status_code": 200, "streaming": True, "terminal": True,
             "immediate_ack": "false"},
        ))
        live = {"base_url": "http://example/v1", "master_token": "m" * 32,
                "observer_token": "o" * 32, "show_id": "show"}
        with mock.patch.object(runner.time, "sleep", return_value=None):
            record, ok = runner.run_live_capability_turn(
                transport, live, model="test", messages=[{"role": "user", "content": "u"}],
                user_content="u", max_tokens=1, timeout=1.0, action_id="a", trace_id="t",
                turn_type="chat_question",
            )
        self.assertTrue(ok)
        receipt = next(event[1]["payload"] for event in transport.events
                       if event[0] == "receipt")
        self.assertEqual(receipt["answer_sha256"], runner.sha256_text("answer without marker"))
        self.assertEqual(record["receipt_binding"], {
            "schema": "airi.attested-stream-answer.v1",
            "leading_marker_stripped": False,
        })

    def test_live_receipt_keeps_nonprefix_act_like_text_byte_exact(self) -> None:
        transport = _LiveTransport()
        public = 'live answer <|ACT {"emotion":"curious"}|> literal'
        transport.stream_chat = mock.Mock(return_value=(
            '<|ACT {"emotion":"think"}|>' + public, 5.0, 10.0,
            {"status_code": 200, "streaming": True, "terminal": True,
             "immediate_ack": "marker"},
        ))
        live = {"base_url": "http://example/v1", "master_token": "m" * 32,
                "observer_token": "o" * 32, "show_id": "show"}
        with mock.patch.object(runner.time, "sleep", return_value=None):
            runner.run_live_capability_turn(
                transport, live, model="test", messages=[{"role": "user", "content": "u"}],
                user_content="u", max_tokens=1, timeout=1.0, action_id="a", trace_id="t",
                turn_type="chat_question",
            )
        receipt = next(event[1]["payload"] for event in transport.events
                       if event[0] == "receipt")
        self.assertEqual(receipt["answer_sha256"], runner.sha256_text(public))

    def test_live_turn_rejects_nonterminal_stream_before_receipt(self) -> None:
        transport = _LiveTransport()
        transport.stream_chat = mock.Mock(return_value=(
            "partial answer", 5.0, 10.0,
            {"status_code": 200, "streaming": True, "terminal": False,
             "immediate_ack": "marker"},
        ))
        live = {"base_url": "http://example/v1", "master_token": "m" * 32,
                "observer_token": "o" * 32, "show_id": "show"}
        with self.assertRaisesRegex(RuntimeError, "terminal answer"):
            runner.run_live_capability_turn(
                transport, live, model="test", messages=[{"role": "user", "content": "u"}],
                user_content="u", max_tokens=1, timeout=1.0, action_id="a", trace_id="t",
                turn_type="chat_question",
            )
        self.assertFalse(any(event[0] == "receipt" for event in transport.events))


class BriefingEvidenceSignalTests(unittest.TestCase):
    """디렉터→프록시 근거 신호: 브리핑이 회상 재료를 실은 턴에만 붙는다."""

    def setUp(self) -> None:
        self.fixture = sim.load_fixture()
        self.stream = sim.generate_stream(self.fixture, seed=20260818)
        self.picks = sim.plan_pickups(self.stream, self.fixture)

    def test_assembly_reports_whether_it_carried_recall_material(self) -> None:
        # 좁힌 정의(Task 1 리뷰 Minor 1, 2026-08-20): 근거는 "관련 있는" 줄이 실린
        # 턴에만 선다 — recency 로 채워진 무관 줄만 있는 턴은 이제 evidence=False.
        first_time = next(pick for pick in self.picks
                          if not sim.select_viewer_lines(self.fixture, self.stream, pick))
        filler_only = next(
            pick for pick in self.picks
            if sim.select_viewer_lines(self.fixture, self.stream, pick)
            and not any(relevant for _item, relevant
                        in sim.select_viewer_lines_tagged(self.fixture, self.stream, pick)))
        relevant_pick = next(
            pick for pick in self.picks
            if any(relevant for _item, relevant
                   in sim.select_viewer_lines_tagged(self.fixture, self.stream, pick)))
        for pick, expected in ((first_time, False), (filler_only, False), (relevant_pick, True)):
            text, evidence = sim.build_turn_briefing_with_evidence(
                self.fixture, self.stream, pick, [])
            self.assertIs(evidence, expected, pick["turn_index"])
            # 근거 여부는 조립 시점의 사실이고, 본문은 기존과 바이트 동일하다.
            self.assertEqual(text, sim.build_turn_briefing(self.fixture, self.stream, pick, []))

    def _run(self, briefing: str, briefing_evidence: str) -> tuple[_FakeTransport, list[bool]]:
        transport = _FakeTransport()
        # 좁힌 정의로는 관련 태그가 이 seed 의 turn_index 14 부터 처음 등장한다
        # (12턴 슬라이스로는 실측 성립 불가) — 20턴까지 넓혀 최소 하나는 담는다.
        picks = self.picks[:20]
        runner.run_arm(
            transport, self.fixture, self.stream, picks,
            model="test-model", contract="on", protocol="operational",
            author_format="runtime", history_turns=8, max_tokens=32, timeout=1.0,
            pre_session_seeds=False, briefing=briefing, acts="off",
            briefing_evidence=briefing_evidence,
        )
        # 좁힌 정의: recency 로 채워진 무관 줄이 아니라 관련 있는 줄이 있어야 근거다.
        expected = [any(relevant for _item, relevant
                        in sim.select_viewer_lines_tagged(self.fixture, self.stream, pick))
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


class _FakeHealthResponse:
    """httpx.Response 의 최소 부분집합 — /health JSON 만 흉내 낸다."""

    def __init__(self, absence_bypasses: int) -> None:
        self._absence_bypasses = absence_bypasses

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"briefing_evidence": {"absence_bypasses": self._absence_bypasses}}


class _FakeTransportWithHealth(_FakeTransport):
    """_FakeTransport 확장 — /health 폴링을 스크립트로 재현한다.

    ollama_proxy.py 는 이 신호 부착이 실제로 absence 가드를 해제했는지 요청별로
    알려주지 않는다(content-free 텔레메트리, 무수정). 러너는 그 대신 누계
    absence_bypasses 를 턴 전후로 대조해 해제 여부를 추정한다 — 이 페이크는
    그 누계가 호출될 때마다 스크립트의 다음 값을 내놓도록 흉내 낸다.
    """

    def __init__(self, bypass_sequence: list[int]) -> None:
        super().__init__()
        self._bypass_sequence = list(bypass_sequence)
        self.health_calls = 0
        self.client.get = self._get  # SimpleNamespace 에 메서드 속성만 얹는다

    def _get(self, url, timeout=None):  # noqa: ANN001 — httpx.Client.get 시그니처 흉내
        self.health_calls += 1
        return _FakeHealthResponse(self._bypass_sequence.pop(0))


class BriefingEvidenceReleaseObservabilityTests(unittest.TestCase):
    """Task 1 리뷰 Minor 2: 해제(release) 여부의 행 단위 관측성.

    프록시의 absence_bypasses 는 누계뿐이라 어느 턴이 실제로 가드를 해제시켰는지
    행만 봐서는 알 수 없었다. /health 를 턴 전후로 대조해 그 사실을 행에 싣는다.
    """

    def setUp(self) -> None:
        self.fixture = sim.load_fixture()
        self.stream = sim.generate_stream(self.fixture, seed=20260818)
        self.picks = sim.plan_pickups(self.stream, self.fixture)[:20]
        # 이 seed 에서 근거가 붙는(관련 태그 있는) 첫 세 턴: 14, 16, 19.
        self.signalled_turns = [pick["turn_index"] for pick in self.picks
                                if any(relevant for _item, relevant in
                                       sim.select_viewer_lines_tagged(self.fixture, self.stream, pick))]
        self.assertEqual(self.signalled_turns, [14, 16, 19], "고정 seed 실측 전제가 깨졌다")

    def test_release_is_true_only_when_the_cumulative_counter_actually_moves(self) -> None:
        # 기준값(0) + 3개 신호턴: 14→해제(1), 16→미해제(그대로 1), 19→해제(2).
        transport = _FakeTransportWithHealth([0, 1, 1, 2])
        result = runner.run_arm(
            transport, self.fixture, self.stream, self.picks,
            model="test-model", contract="on", protocol="operational",
            author_format="runtime", history_turns=8, max_tokens=32, timeout=1.0,
            pre_session_seeds=False, briefing="on", acts="off",
            briefing_evidence="on", health_url="http://proxy.invalid/health",
        )
        by_turn = {row["turn_index"]: row["briefing_evidence_released"] for row in result["rows"]}
        self.assertEqual(by_turn[14], True)
        self.assertEqual(by_turn[16], False)
        self.assertEqual(by_turn[19], True)
        # 신호가 붙지 않은 턴은 애초에 해제될 수 없다 — 미관측(None), False 아님.
        unsignalled = [row["briefing_evidence_released"] for row in result["rows"]
                       if row["turn_index"] not in self.signalled_turns]
        self.assertTrue(all(value is None for value in unsignalled))
        self.assertEqual(result["summary"]["briefing_evidence_release"], {"hits": 2, "of": 3})
        # 기준값 1회 + 신호턴 3회 = 4번만 폴링한다(매 턴 폴링하지 않는다).
        self.assertEqual(transport.health_calls, 4)

    def test_release_stays_unobserved_without_a_health_url(self) -> None:
        transport = _FakeTransportWithHealth([0, 1, 1, 2])
        result = runner.run_arm(
            transport, self.fixture, self.stream, self.picks,
            model="test-model", contract="on", protocol="operational",
            author_format="runtime", history_turns=8, max_tokens=32, timeout=1.0,
            pre_session_seeds=False, briefing="on", acts="off",
            briefing_evidence="on",  # health_url 기본값(None) — 폴링 자체가 없어야 한다.
        )
        self.assertTrue(all(row["briefing_evidence_released"] is None for row in result["rows"]))
        self.assertEqual(transport.health_calls, 0)
        self.assertEqual(result["summary"]["briefing_evidence_release"], {"hits": 0, "of": 0})

    def test_release_stays_unobserved_when_evidence_signal_is_off(self) -> None:
        # health_url 은 있어도 briefing_evidence="off" 면 헤더 자체가 안 붙으니
        # 해제도 있을 수 없다 — 폴링 낭비를 하지 않는다.
        transport = _FakeTransportWithHealth([0, 1, 1, 2])
        result = runner.run_arm(
            transport, self.fixture, self.stream, self.picks,
            model="test-model", contract="on", protocol="operational",
            author_format="runtime", history_turns=8, max_tokens=32, timeout=1.0,
            pre_session_seeds=False, briefing="on", acts="off",
            briefing_evidence="off", health_url="http://proxy.invalid/health",
        )
        self.assertTrue(all(row["briefing_evidence_released"] is None for row in result["rows"]))
        self.assertEqual(transport.health_calls, 0)

    def test_health_url_derives_the_root_path_not_the_versioned_chat_path(self) -> None:
        self.assertEqual(runner.proxy_health_url("http://127.0.0.1:11435/v1"),
                         "http://127.0.0.1:11435/health")
        self.assertEqual(runner.proxy_health_url("http://127.0.0.1:11435"),
                         "http://127.0.0.1:11435/health")

    def test_read_absence_bypasses_fails_soft_on_a_broken_transport(self) -> None:
        broken = types.SimpleNamespace(client=types.SimpleNamespace())  # .get 없음
        self.assertIsNone(runner.read_absence_bypasses(broken, "http://proxy.invalid/health"))


class _RecordingTransport(_FakeTransport):
    """`_FakeTransport` 확장 — 매 호출에 실제로 전송된 messages 를 그대로 기록한다."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[list[dict[str, str]]] = []

    def stream_chat(self, *, model, messages, max_tokens, timeout):
        self.calls.append(messages)
        return super().stream_chat(model=model, messages=messages, max_tokens=max_tokens, timeout=timeout)


class DeterministicActHistoryIsolationTests(unittest.TestCase):
    """Task 13: 결정론 렌더러(후원 thank 호명) 발화가 히스토리·브리핑으로 되먹여져
    이후 모델 턴이 그 이름을 재호명하는 결함(Task 9 실측 — 15런 19턴 중 16건이
    직전 후원 렌더러 이름, B4a "이름 발명 금지" 계약 위반)을 고정한다.

    누출 경로 둘 다 한 번에 잡는다 — ①`history.append` 가 렌더러 문구를
    assistant 턴으로 다음 모델 호출에 그대로 넣는 것, ②`answered_picks`
    에 실린 응답이 브리핑 "방금 흐름" 줄에 에코되는 것(`min_echo_response_chars`
    보다 길어 항상 통과). 격리는 되먹임 사본만 손대야 하므로, 렌더러가 실제로
    말한 트랜스크립트·채점 행은 이름이 그대로 남는지도 함께 확인한다.
    """

    def setUp(self) -> None:
        self.fixture = sim.load_fixture()
        self.stream = sim.generate_stream(self.fixture, seed=20260818)
        self.picks = sim.plan_pickups(self.stream, self.fixture)[:10]
        donation = next(pick for pick in self.picks if pick["effective_kind"] == "donation")
        self.donor = donation["message"]["author"]
        # 고정 seed 전제 — 깨지면 아래 인덱싱 가정이 전부 무의미해진다.
        self.assertEqual((donation["turn_index"], self.donor), (9, "파도소리"))

    def _run(self) -> tuple[_RecordingTransport, dict[str, Any]]:
        transport = _RecordingTransport()
        result = runner.run_arm(
            transport, self.fixture, self.stream, self.picks,
            model="test-model", contract="on", protocol="operational",
            author_format="runtime", history_turns=8, max_tokens=32, timeout=1.0,
            pre_session_seeds=False, briefing="on", acts="on",
        )
        return transport, result

    def test_renderer_callout_name_does_not_leak_into_the_next_model_call(self) -> None:
        transport, _result = self._run()
        # 후원 턴도 모델이 본답변을 잇는다. 렌더러는 호명·감사 opener만 소유한다.
        self.assertEqual(len(transport.calls), len(self.picks))
        donation_call_messages = transport.calls[8]
        self.assertIn(runner.DONATION_CONTINUATION_CONTRACT,
                      donation_call_messages[0]["content"])
        next_call_messages = transport.calls[-1]

        # 채널 1 — 히스토리: 렌더러 문구가 assistant 턴으로 되먹이면 안 된다.
        assistant_turns = [m["content"] for m in next_call_messages if m["role"] == "assistant"]
        self.assertTrue(assistant_turns, "히스토리에 assistant 턴이 없다 — 전제가 깨졌다")
        self.assertFalse(
            any(self.donor in content for content in assistant_turns),
            f"렌더러 호명이 히스토리로 되먹였다: {assistant_turns}",
        )

        # 채널 2 — 브리핑 "방금 흐름": 렌더러 호명 문형이 그대로 에코되면 안 된다.
        # ("- 직전 후원: {author} 는 실제 후원자 채팅을 그대로 인용하는 별개 줄이라
        #  이름 자체는 남아도 된다 — 렌더러가 만든 "{이름}, 고마워!" 패턴만 문제다.)
        system_content = next_call_messages[0]["content"]
        callout_prefix = f"{self.donor}, 고마워!"
        self.assertNotIn(callout_prefix, system_content, "브리핑 '방금 흐름'에 렌더러 호명이 에코됐다")

    def test_the_rendered_callout_itself_stays_intact_for_transcript_and_scoring(self) -> None:
        # 격리는 되먹임 사본만 손대야 한다 — 실제로 말한 트랜스크립트/채점은 그대로.
        _transport, result = self._run()
        donation_row = next(row for row in result["rows"] if row["kind"] == "donation")
        self.assertEqual(donation_row["deterministic_act"], "thank_renderer")
        self.assertIn(self.donor, donation_row["called_handles"])
        self.assertEqual(donation_row["invented_handles"], [])
        donation_entry = next(entry for entry in result["transcript"]
                              if entry.get("stage") == "turn" and entry["kind"] == "donation")
        self.assertIn(self.donor, donation_entry["airi"])
        self.assertGreater(len(donation_entry["airi"]), len(self.donor) + 5)


class BriefingTokenPoolIncludesBriefedHandlesTests(unittest.TestCase):
    """디렉터 브리핑이 그 턴에 실제로 준 시청자 handle 인데도 채점 근거 풀에는
    빠져, 모델이 브리핑이 방금 알려준 이름을 그대로 이어 부르면 invented_handles
    로 오판되던 결함(handle_grounding.memory_pool 만 챙기고 briefing_text 자체는
    안 챙겼다).
    """

    def setUp(self) -> None:
        self.fixture = sim.load_fixture()
        self.stream = sim.generate_stream(self.fixture, seed=20260818)
        picks = sim.plan_pickups(self.stream, self.fixture)
        # 이 seed 의 첫 턴(turn_index=1) 은 select_viewer_lines 가 비어 있다
        # (첫 발언이라 과거 발언이 없다) — 그래서 브리핑 자체가 준 handle 만
        # 근거 풀에 들어오는지를 다른 경로와 섞이지 않고 볼 수 있다.
        self.pick = next(pick for pick in picks if not sim.select_viewer_lines(
            self.fixture, self.stream, pick))
        self.assertEqual(self.pick["turn_index"], 1, "고정 seed 실측 전제가 깨졌다")

    def _run(self, body: str) -> dict[str, Any]:
        transport = _FakeTransport()
        transport.stream_chat = mock.Mock(return_value=(body, 5.0, 10.0, {"status_code": 200}))
        result = runner.run_arm(
            transport, self.fixture, self.stream, [self.pick],
            model="test-model", contract="on", protocol="operational",
            author_format="runtime", history_turns=8, max_tokens=32, timeout=1.0,
            pre_session_seeds=False, briefing="on", acts="off",
        )
        return result["rows"][0]

    def test_a_handle_the_briefing_just_named_is_not_flagged_as_invented(self) -> None:
        handle = "별빛수집가"
        briefing_text = f'- 방금 흐름: {handle} "비 얘기 시작했어"'
        with mock.patch.object(
                runner.sim, "build_turn_briefing_with_evidence",
                return_value=(briefing_text, True)):
            row = self._run(f"{handle}가 비 이야기를 이어 받았어.")
        self.assertEqual(row["invented_handles"], [])
        self.assertTrue(any(token.startswith(handle) for token in row["fact_tokens_used"]),
                        row["fact_tokens_used"])

    def test_a_handle_absent_from_viewer_lines_briefing_and_memory_pool_is_still_flagged(self) -> None:
        handle = "새벽두시"
        row = self._run(f"{handle}가 요즘 잘 지내는지 궁금하다.")
        self.assertEqual(row["invented_handles"], [handle])


class RescoreReportTests(unittest.TestCase):
    """rescore_report(): 모델 재호출 없이 채점만 다시 돈다.

    이 경로는 지금까지 테스트가 없었다 — 실행해 보니 정의 시점 자유변수 ``args``
    를 참조해 호출할 때마다 NameError 로 죽는 잠재 버그였다(CLI ``--rescore`` 는
    한 번도 성공한 적이 없다). 신규 행 필드(``briefing_evidence_released``) 를
    캐리 키에 추가하는 김에 같이 고쳤다 — fixture_path 인자로 받게 시그니처를
    바꿔 main() 의 지역변수 args 를 더는 참조하지 않는다.
    """

    def setUp(self) -> None:
        self.fixture = sim.load_fixture()
        self.stream = sim.generate_stream(self.fixture, seed=20260818)
        self.picks = {pick["turn_index"]: pick for pick in sim.plan_pickups(self.stream, self.fixture)}

    def _payload(self) -> dict[str, Any]:
        turns = [1, 2, 3]
        transcript = [{"stage": "turn", "turn_index": t, "airi": "응, 그렇구나!"} for t in turns]
        rows = [
            {"turn_index": 1, "beat": "opening", "backlog_size": 0, "briefing_evidence": True,
             "briefing_evidence_released": True, "polite_violation": False, "banmal": True,
             "ttft_ms": 5.0, "complete_ms": 10.0, "failure": None},
            {"turn_index": 2, "beat": "opening", "backlog_size": 0, "briefing_evidence": True,
             "briefing_evidence_released": False, "polite_violation": False, "banmal": True,
             "ttft_ms": 5.0, "complete_ms": 10.0, "failure": None},
            {"turn_index": 3, "beat": "opening", "backlog_size": 0, "briefing_evidence": False,
             "briefing_evidence_released": None, "polite_violation": False, "banmal": True,
             "ttft_ms": 5.0, "complete_ms": 10.0, "failure": None},
        ]
        return {
            "schema_version": sim.REPORT_SCHEMA_VERSION, "seed": 20260818,
            "fixture_sha256": self.stream["fixture_sha256"], "briefing": "on",
            "transcript": transcript, "rows": rows,
            "summary": {"transport_failures": 0},
        }

    def test_rescore_runs_without_a_module_level_args_global(self) -> None:
        # 회귀 고정: 예전엔 이 호출 자체가 NameError 로 죽었다.
        payload = runner.rescore_report(self._payload())
        self.assertTrue(payload["rescored"])

    def test_new_row_field_survives_rescore_via_the_carry_key_list(self) -> None:
        payload = runner.rescore_report(self._payload())
        by_turn = {row["turn_index"]: row["briefing_evidence_released"] for row in payload["rows"]}
        self.assertEqual(by_turn, {1: True, 2: False, 3: None})
        self.assertEqual(payload["summary"]["briefing_evidence_release"], {"hits": 1, "of": 2})


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

    def test_runner_briefing_marker_matches_the_layer_constant(self) -> None:
        # 러너가 브리핑 앞에 붙이는 마커는 계층이 인식하는 문자열과 바이트로
        # 같아야 한다. 어긋나면 브리핑이 다시 P3/P4 증거 풀 밖으로 떨어진다.
        layer = HERE.parent.parent / "deterministic_utterance_layer.py"
        tree = ast.parse(layer.read_text(encoding="utf-8"))
        marker = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "BRIEFING_EVIDENCE_MARKER":
                        marker = ast.literal_eval(node.value)
        self.assertIsNotNone(marker, "BRIEFING_EVIDENCE_MARKER 를 계층 소스에서 못 찾았다")
        self.assertEqual(marker, runner.BRIEFING_EVIDENCE_BLOCK_MARKER)

    def test_runner_donation_thanks_matches_the_layer_constant(self) -> None:
        # 계층(P5)이 후원 본문 끝에 붙이는 감사 문장과 바이트로 같아야 되먹임
        # 사본에서 그 문장을 떼어낼 수 있다. 어긋나면 의례가 다시 히스토리·브리핑
        # 으로 새어 들어간다(사람 평가 run 04 의 "고마워." 붕괴).
        layer = HERE.parent.parent / "deterministic_utterance_layer.py"
        tree = ast.parse(layer.read_text(encoding="utf-8"))
        thanks = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "DONATION_THANKS_LINE":
                        thanks = ast.literal_eval(node.value)
        self.assertIsNotNone(thanks, "DONATION_THANKS_LINE 을 계층 소스에서 못 찾았다")
        self.assertEqual(thanks, runner.DONATION_ECHO_THANKS)

    def _proxy_constant(self, name: str) -> str:
        for node in ast.walk(self._proxy_tree()):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        return ast.literal_eval(node.value)
        raise AssertionError(f"{name} 을 프록시 소스에서 못 찾았다")

    def test_runner_service_error_pool_matches_the_live_failure_dialogues(self) -> None:
        # 파이프라인 실패 안내 3종은 침묵 폴백과 달리 "모델 발화가 없었다"는 뜻이다.
        # 러너가 프록시와 바이트로 같은 문구를 세야 service_error 율이 의미를 갖는다.
        # 이 대조가 없으면 D1 라운드처럼 전 arm 턴의 1/3이 오류인데도 리포트는
        # fallback 0/108 만 보고한다.
        live = tuple(self._proxy_constant(name) for name in (
            "LOCAL_ERROR_DIALOGUE",
            "UPSTREAM_TIMEOUT_DIALOGUE",
            "UPSTREAM_RAW_PROGRESS_TIMEOUT_DIALOGUE",
        ))
        self.assertEqual(set(live), set(runner.SERVICE_ERROR_POOL))
        # 침묵 폴백과 겹치면 두 지표가 서로를 오염시킨다.
        self.assertFalse(set(runner.SERVICE_ERROR_POOL) & set(runner.FALLBACK_POOL))
        for line in runner.SERVICE_ERROR_POOL:
            with self.subTest(line=line):
                self.assertTrue(line.startswith(runner.DEGENERATE_ECHO_PREFIXES), line)


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

    def test_service_error_is_flagged_separately_from_the_silence_fallback(self) -> None:
        # 프록시 오류 응답은 침묵 폴백이 아니다. 두 플래그가 서로 독립이어야
        # "폴백률 0인데 실측 오류율 34%" 같은 사각이 다시 생기지 않는다.
        error_line = runner.SERVICE_ERROR_POOL[0]
        row = sim.score_turn(self.pick(message(text="이름 뜻이 뭐야?", kind="question")),
                             error_line, beat=self.beat, fallback_pool=("음, 잠깐만.",),
                             roster_handles=self.roster,
                             service_error_pool=runner.SERVICE_ERROR_POOL,
                             drift_terms=sorted(sim.offtopic_terms(self.fixture)))
        self.assertTrue(row["service_error"])
        self.assertFalse(row["is_fallback"])
        summary = sim.summarize_turns([row])
        self.assertEqual(summary["service_error"], {"hits": 1, "of": 1, "rate": 1.0})
        self.assertEqual(summary["fallback"], {"hits": 0, "of": 1, "rate": 0.0})

    def test_service_error_defaults_off_when_no_pool_is_supplied(self) -> None:
        # 풀을 안 넘긴 호출(기존 코드 경로)은 플래그가 항상 False여야 한다.
        row = self.score(message(text="이름 뜻이 뭐야?", kind="question"),
                         runner.SERVICE_ERROR_POOL[0])
        self.assertFalse(row["service_error"])

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

    def test_briefed_fact_that_matches_a_roster_handle_is_not_name_invention(self) -> None:
        probe = message(kind="memory_probe", author="밤산책", text="아까 말한 별명이 뭐였지?")
        row = sim.score_turn(
            self.pick(probe),
            "별명은 달빛우체국이라고 했지.",
            beat=self.beat,
            fallback_pool=("음, 잠깐만.",),
            roster_handles=("밤산책", "달빛우체국"),
            drift_terms=(),
            briefing_fact_tokens=("달빛우체국",),
        )
        self.assertTrue(any(token.startswith("달빛우체국") for token in row["fact_tokens_used"]))
        self.assertEqual(row["invented_handles"], [])


REAL_CHAT_FIXTURE = HERE.parent / "human_review" / "real_chat_fixture.json"
# 파일에 적힌 순서 그대로다 — 일부러 시간순이 아니고, 같은 offset 도 섞여 있다.
REPLAY_RAW_ROWS = (
    (5_000, "가명001", "chat", "안녕!", ""),
    (3_000, "가명002", "chat", "방송 오늘 몇 시까지 하나요", ""),
    (5_000, "가명003", "chat", "ㅋㅋㅋ", ""),
    (30_000, "가명001", "chat", "그거 진짜 웃겼어", ""),
    (61_000, "가명002", "donation", "화이팅!", "1000"),
    (95_000, "가명004", "chat", "밥은 먹었어?", ""),
    (130_000, "가명001", "chat", "게임 뭐 할 거야", ""),
    (200_000, "가명003", "chat", "이거 어때", ""),
    (400_000, "가명002", "chat", "졸리다", ""),
    (900_000, "가명004", "donation", "고생 많아", "5000"),
    (1_500_000, "가명001", "chat", "다음 방송 언제", ""),
    (2_400_000, "가명003", "chat", "잘 봤어", ""),
)


def replay_rows(raw: tuple = REPLAY_RAW_ROWS) -> list[dict[str, Any]]:
    rows = []
    for offset, author, kind, text, amount in raw:
        row: dict[str, Any] = {"source": "youtube-live", "video_ref": "vid-0001",
                               "offset_ms": offset, "author": author, "kind": kind, "text": text}
        if amount:
            row["amount_label"] = amount
        rows.append(row)
    return rows


def write_replay(directory: Path, rows: list[dict[str, Any]] | None = None) -> Path:
    path = Path(directory) / "capture.jsonl"
    body = "".join(json.dumps(row, ensure_ascii=False) + "\n"
                   for row in (replay_rows() if rows is None else rows))
    path.write_text(body, encoding="utf-8")
    return path


class _ReplayTransport(_FakeTransport):
    """_FakeTransport 확장 — main() 이 요구하는 close() 와 전송 본문을 갖춘다."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[list[dict[str, str]]] = []
        self.closed = False

    def stream_chat(self, *, model, messages, max_tokens, timeout):
        super().stream_chat(model=model, messages=messages, max_tokens=max_tokens, timeout=timeout)
        self.messages.append(messages)
        return f"응, {len(self.messages)}번째 대답이야.", 5.0, 10.0, {"status_code": 200}

    def close(self) -> None:
        self.closed = True


class ReplayFixtureTests(unittest.TestCase):
    def test_real_chat_fixture_validates_and_carries_no_dialogue(self) -> None:
        fixture = sim.load_fixture(REAL_CHAT_FIXTURE)
        self.assertIs(fixture["synthetic_only"], True)
        self.assertEqual(fixture["rates"]["broadcast_minutes"], 60)
        self.assertEqual(fixture["topic"]["beats"][-1]["end_minute"], 60)
        self.assertEqual(len(fixture["topic"]["beats"]), 4)
        self.assertEqual(fixture["donations"], [])
        self.assertEqual(fixture["memory_probes"], [])
        self.assertNotIn("continuity_arcs", fixture)
        self.assertIn("offtopic_chatter", fixture["archetypes"])
        # 로스터는 자리표시자뿐이다 — 실제 가명은 replay 시점에만 들어온다.
        self.assertEqual([viewer["archetype"] for viewer in fixture["viewers"]],
                         ["replay", "replay"])


class ReplayStreamTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = sim.load_fixture(REAL_CHAT_FIXTURE)

    def build(self, raw: tuple = REPLAY_RAW_ROWS, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            path = write_replay(Path(directory), replay_rows(raw))
            rows = runner.load_replay_rows(path, **kwargs)
            fixture = runner.build_replay_fixture(self.fixture, rows)
            stream = runner.build_replay_stream(fixture, rows, path=path, seed=7)
        return fixture, stream

    def test_messages_are_ordered_and_rebased_to_the_first_offset(self) -> None:
        _fixture, stream = self.build()
        self.assertEqual([item["id"] for item in stream["messages"]],
                         [f"m{index:04d}" for index in range(12)])
        self.assertEqual([item["t_ms"] for item in stream["messages"]],
                         [0, 2_000, 2_000, 27_000, 58_000, 92_000, 127_000, 197_000,
                          397_000, 897_000, 1_497_000, 2_397_000])
        self.assertEqual([item["minute"] for item in stream["messages"]],
                         [0, 0, 0, 0, 0, 1, 2, 3, 6, 14, 24, 39])
        # 같은 offset 은 파일에 적힌 순서를 유지한다.
        self.assertEqual([item["text"] for item in stream["messages"][:3]],
                         ["방송 오늘 몇 시까지 하나요", "안녕!", "ㅋㅋㅋ"])
        self.assertEqual(stream["broadcast_minutes"], 40)
        self.assertEqual(stream["schema_version"], sim.STREAM_SCHEMA_VERSION)

    def test_kinds_come_from_the_row_then_the_question_heuristic(self) -> None:
        _fixture, stream = self.build()
        # m0004 는 1,000원짜리 소액 치즈다 — 의례 대신 평범한 채팅으로 받는다.
        self.assertEqual([item["kind"] for item in stream["messages"]],
                         ["question", "reaction", "reaction", "reaction", "reaction",
                          "question", "reaction", "question", "reaction", "donation",
                          "question", "reaction"])
        self.assertTrue(all(item["archetype"] == "replay" for item in stream["messages"]))

    def test_question_heuristic_reads_endings_as_well_as_the_mark(self) -> None:
        for text in ("밥은 먹었어?", "이거 어때", "다음 방송 언제", "몇 시까지 하나요",
                     "이거 될까", "지금 뭐임", "누구"):
            self.assertTrue(runner.looks_like_question(text), text)
        for text in ("안녕!", "ㅋㅋㅋ", "왜냐하면 그랬어", "잘 봤어", "그러니까", ""):
            self.assertFalse(runner.looks_like_question(text), text)

    def test_donation_rows_keep_the_ritual_scorable(self) -> None:
        _fixture, stream = self.build()
        donations = [item for item in stream["messages"] if item["kind"] == "donation"]
        self.assertEqual([item["amount_label"] for item in donations], ["5000"])
        self.assertEqual([item["donation_index"] for item in donations], [0])
        self.assertNotIn("donation_small", donations[0])
        self.assertEqual(donations[0]["checks"],
                         {"required_any": ["고마워", "감사"], "forbidden": []})
        row = sim.score_turn(
            {"turn_index": 1, "message": donations[0], "effective_kind": "donation"},
            "가명004, 고마워!", beat=self.fixture["topic"]["beats"][0],
            fallback_pool=(), roster_handles=("가명004",))
        self.assertTrue(row["addressee_ok"])

    def test_small_cheese_is_answered_as_ordinary_chat(self) -> None:
        raw = (
            (0, "가명001", "donation", "밥은 먹었어?", "1000"),
            (1_000, "가명002", "donation", "화이팅!", "4999"),
            (2_000, "가명003", "donation", "고생 많아", "5000"),
            (3_000, "가명004", "donation", "이거 어때", "20000"),
        )
        _fixture, stream = self.build(raw)
        messages = stream["messages"]
        self.assertEqual(runner.REPLAY_DONATION_RITUAL_MIN_AMOUNT, 5000)
        # 소액은 기존 휴리스틱대로 question/reaction 이 되고, 의례 검사는 붙지 않는다.
        self.assertEqual([item["kind"] for item in messages],
                         ["question", "reaction", "donation", "donation"])
        self.assertTrue(all(item["donation_small"] for item in messages[:2]))
        self.assertTrue(all("checks" not in item for item in messages[:2]))
        self.assertTrue(all("donation_index" not in item for item in messages[:2]))
        # 팁을 실었다는 사실 자체는 남는다 — 트랜스크립트가 금액을 잃지 않는다.
        self.assertEqual([item["amount_label"] for item in messages],
                         ["1000", "4999", "5000", "20000"])
        self.assertTrue(all("donation_small" not in item for item in messages[2:]))
        self.assertEqual([item["donation_index"] for item in messages[2:]], [0, 1])
        self.assertEqual(stream["replay"]["donation_ritual"], 2)
        self.assertEqual(stream["replay"]["donation_small"], 2)

    def test_unparseable_amount_labels_are_treated_as_small(self) -> None:
        raw = (
            (0, "가명001", "donation", "화이팅!", "5,000원"),
            (1_000, "가명002", "donation", "고생 많아", ""),
            (2_000, "가명003", "donation", "잘 봤어", "₩20,000"),
        )
        _fixture, stream = self.build(raw)
        self.assertEqual([item["kind"] for item in stream["messages"]], ["reaction"] * 3)
        self.assertTrue(all(item["donation_small"] for item in stream["messages"]))
        self.assertEqual(stream["replay"]["donation_ritual"], 0)
        self.assertEqual(stream["replay"]["donation_small"], 3)

    def test_amount_label_is_read_only_as_a_plain_ascii_integer(self) -> None:
        self.assertEqual(runner.replay_donation_amount("5000"), 5000)
        self.assertEqual(runner.replay_donation_amount(" 5000 "), 5000)
        self.assertEqual(runner.replay_donation_amount("0"), 0)
        for label in ("5,000원", "₩5,000", "", "  ", "5000원", "-5000", "5000.0", "٥٠٠٠"):
            with self.subTest(label=label):
                self.assertIsNone(runner.replay_donation_amount(label))

    def test_replay_block_records_provenance_without_any_dialogue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = write_replay(Path(directory))
            rows = runner.load_replay_rows(path)
            fixture = runner.build_replay_fixture(self.fixture, rows)
            stream = runner.build_replay_stream(fixture, rows, path=path, seed=7)
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(stream["replay"],
                         {"path_sha256": expected, "message_count": 12, "source": "youtube-live",
                          "donation_ritual": 1, "donation_small": 1})
        self.assertEqual(stream["fixture_sha256"], sim.sha256_of(fixture))

    def test_roster_merges_every_pseudonym_and_keeps_the_placeholders(self) -> None:
        fixture, _stream = self.build()
        handles = [viewer["handle"] for viewer in fixture["viewers"]]
        self.assertEqual(handles[:2], [viewer["handle"] for viewer in self.fixture["viewers"]])
        # 파일 순서가 아니라 재생 순서(첫 등장)를 따른다 — 가명002 가 가장 이르다.
        self.assertEqual(handles[2:], ["가명002", "가명001", "가명003", "가명004"])
        self.assertTrue(all(viewer["archetype"] == "replay" for viewer in fixture["viewers"]))
        # 원본 픽스처는 손대지 않는다.
        self.assertEqual(len(self.fixture["viewers"]), 2)

    def test_span_beyond_the_fixture_stretches_the_last_beat(self) -> None:
        raw = REPLAY_RAW_ROWS[:-1] + ((4_233_000, "가명003", "chat", "잘 봤어", ""),)
        fixture, stream = self.build(raw)
        self.assertEqual(stream["broadcast_minutes"], 71)
        self.assertEqual(fixture["rates"]["broadcast_minutes"], 71)
        self.assertEqual(fixture["topic"]["beats"][-1]["end_minute"], 71)
        self.assertEqual(fixture["topic"]["beats"][-1]["start_minute"], 45)
        self.assertEqual(self.fixture["rates"]["broadcast_minutes"], 60)

    def test_a_capture_ending_on_a_minute_boundary_still_gets_picked_up(self) -> None:
        raw = ((0, "가명001", "chat", "안녕!", ""), (60_000, "가명002", "chat", "잘 봤어", ""))
        fixture, stream = self.build(raw)
        # ceil 만 쓰면 60분 경계 메시지가 마지막 창(t_ms < window_end) 밖으로 떨어진다.
        self.assertEqual(stream["broadcast_minutes"], 2)
        picks = sim.plan_pickups(stream, fixture)
        self.assertIn("m0001", [pick["message"]["id"] for pick in picks])

    def test_window_and_cap_options_cut_the_capture(self) -> None:
        _fixture, stream = self.build(start_ms=61_000, end_ms=400_000)
        self.assertEqual([item["t_ms"] for item in stream["messages"]],
                         [0, 34_000, 69_000, 139_000, 339_000])
        self.assertEqual(stream["messages"][0]["kind"], "reaction")
        self.assertTrue(stream["messages"][0]["donation_small"])
        _fixture, capped = self.build(max_messages=3)
        self.assertEqual(len(capped["messages"]), 3)
        self.assertEqual(capped["replay"]["message_count"], 3)

    def test_malformed_rows_fail_closed(self) -> None:
        broken = [
            [{**replay_rows()[0], "kind": "superchat"}],
            [{key: value for key, value in replay_rows()[0].items() if key != "video_ref"}],
            [{**replay_rows()[0], "offset_ms": -1}],
            [{**replay_rows()[0], "offset_ms": "3000"}],
            [{**replay_rows()[0], "text": "   "}],
            [{**replay_rows()[0], "author": ""}],
            [],
        ]
        with tempfile.TemporaryDirectory() as directory:
            for index, rows in enumerate(broken):
                with self.subTest(case=index):
                    path = Path(directory) / f"broken{index}.jsonl"
                    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n"
                                            for row in rows), encoding="utf-8")
                    with self.assertRaises(SystemExit):
                        runner.load_replay_rows(path)
            path = Path(directory) / "notjson.jsonl"
            path.write_text("{oops\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                runner.load_replay_rows(path)


class ReplayPickupAndRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = write_replay(Path(self.directory.name))
        rows = runner.load_replay_rows(self.path)
        self.fixture = runner.build_replay_fixture(sim.load_fixture(REAL_CHAT_FIXTURE), rows)
        self.stream = runner.build_replay_stream(self.fixture, rows, path=self.path, seed=7)
        self.picks = sim.plan_pickups(self.stream, self.fixture)

    def test_pickups_run_on_the_replayed_stream(self) -> None:
        self.assertTrue(self.picks)
        self.assertTrue(all(pick["effective_kind"] in sim.KINDS for pick in self.picks))
        self.assertEqual([pick["turn_index"] for pick in self.picks],
                         list(range(1, len(self.picks) + 1)))
        self.assertIn("donation", {pick["effective_kind"] for pick in self.picks})
        texts = {item["text"] for item in self.stream["messages"]}
        self.assertTrue(all(pick["message"]["text"] in texts for pick in self.picks))

    def test_run_arm_answers_the_real_chat_with_the_real_pseudonyms(self) -> None:
        transport = _ReplayTransport()
        result = runner.run_arm(
            transport, self.fixture, self.stream, self.picks[:6],
            model="test-model", contract="on", protocol="operational",
            author_format="runtime", history_turns=8, max_tokens=32, timeout=1.0,
            pre_session_seeds=False, briefing="on", acts="on", briefing_evidence="off",
        )
        turns = [entry for entry in result["transcript"] if entry["stage"] == "turn"]
        self.assertEqual(len(turns), 6)
        pseudonyms = {row["author"] for row in replay_rows()}
        self.assertTrue({entry["author"] for entry in turns} <= pseudonyms)
        self.assertEqual([entry["chat"] for entry in turns],
                         [pick["message"]["text"] for pick in self.picks[:6]])
        self.assertTrue(all(entry["user_sent"].endswith(entry["chat"]) for entry in turns))
        self.assertEqual(result["summary"]["turns"], 6)
        self.assertEqual(result["summary"]["transport_failures"], 0)

    def test_main_writes_a_report_bound_to_the_capture(self) -> None:
        transport = _ReplayTransport()
        report_path = Path(self.directory.name) / "report.json"
        packet_path = Path(self.directory.name) / "packet.md"
        with mock.patch.object(runner.ab, "HttpTransport", return_value=transport):
            code = runner.main([
                "--fixture", str(REAL_CHAT_FIXTURE), "--replay-chat", str(self.path),
                "--max-turns", "3", "--report", str(report_path), "--packet", str(packet_path),
            ])
        self.assertEqual(code, 0)
        self.assertTrue(transport.closed)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["stream_messages"], 12)
        self.assertEqual(report["replay"]["message_count"], 12)
        self.assertEqual(report["replay"]["source"], "youtube-live")
        self.assertEqual(report["topic_title"], "AIRI 저스트 채팅 — 시청자와 수다")
        turns = [entry for entry in report["transcript"] if entry["stage"] == "turn"]
        self.assertEqual(len(turns), 3)
        self.assertIn(turns[0]["chat"], {row["text"] for row in replay_rows()})
        self.assertIn(turns[0]["chat"], packet_path.read_text(encoding="utf-8"))

    def test_screened_input_is_recorded_and_skipped_only_in_replay(self) -> None:
        transport = _LiveTransport()
        original = transport.stream_chat
        calls = {"n": 0}

        def stream_chat(**kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                return ("blocked answer", 5.0, 10.0, {
                    "status_code": 200, "streaming": True, "terminal": True,
                    "immediate_ack": "false", "input_screened": "blocked",
                    "input_screen_category": "profanity",
                })
            return original(**kwargs)

        transport.stream_chat = stream_chat
        live = {"base_url": "http://example/v1", "master_token": "m" * 32,
                "observer_token": "o" * 32, "show_id": "show"}
        kwargs = dict(
            model="test-model", contract="on", protocol="operational",
            author_format="runtime", history_turns=8, max_tokens=32, timeout=1.0,
            pre_session_seeds=False, briefing="on", acts="on", briefing_evidence="off",
            live_broadcast=live,
        )
        with mock.patch.object(runner.time, "sleep", return_value=None):
            result = runner.run_arm(transport, self.fixture, self.stream, self.picks[:3],
                                    tolerate_screened=True, **kwargs)
        stages = [entry["stage"] for entry in result["transcript"]
                  if entry["stage"] in ("turn", "screened")]
        self.assertEqual(stages, ["turn", "screened", "turn"])
        screened = next(entry for entry in result["transcript"] if entry["stage"] == "screened")
        self.assertEqual(screened["category"], "profanity")
        self.assertEqual(screened["chat"], self.picks[1]["message"]["text"])
        self.assertEqual(result["summary"]["screened_inputs"], 1)
        self.assertEqual(result["summary"]["turns"], 2)
        packet = runner.render_packet({**result, "seed": 1, "model": "test-model", "topic_title": "t",
                                       "memory_arm": "on", "contract": "on", "author_format": "runtime",
                                       "protocol": "operational", "briefing": "on", "acts": "on",
                                       "briefing_evidence": "off", "live_broadcast_context": "off",
                                       "history_turns": 8, "max_tokens": 32, "session_id": "s",
                                       "stream_messages": 3, "fixture_sha256": "0" * 64})
        self.assertIn("입력 스크리닝 차단(profanity)", packet)
        self.assertIn(screened["chat"], packet)
        # A synthetic fixture matrix keeps the block fatal.
        calls["n"] = 0
        with mock.patch.object(runner.time, "sleep", return_value=None), \
             self.assertRaisesRegex(RuntimeError, "category=profanity"):
            runner.run_arm(transport, self.fixture, self.stream, self.picks[:3], **kwargs)

    def test_donation_amount_tiering_survives_the_whole_replay_run(self) -> None:
        transport = _ReplayTransport()
        result = runner.run_arm(
            transport, self.fixture, self.stream, self.picks,
            model="test-model", contract="on", protocol="operational",
            author_format="runtime", history_turns=8, max_tokens=32, timeout=1.0,
            pre_session_seeds=False, briefing="on", acts="on", briefing_evidence="off",
        )
        acts = [row["deterministic_act"] for row in result["rows"]]
        # 1,000원 치즈에는 의례가 없고, 5,000원에만 렌더러가 붙는다.
        self.assertEqual(acts.count("thank_renderer"), 1)
        self.assertEqual(self.stream["replay"]["donation_ritual"], 1)
        self.assertEqual(self.stream["replay"]["donation_small"], 1)

    def test_replay_requires_a_fixture_and_a_scored_run(self) -> None:
        cases = [
            ["--replay-chat", str(self.path)],
            ["--fixture", str(REAL_CHAT_FIXTURE), "--replay-chat", str(self.path), "--stream-only"],
            ["--fixture", str(REAL_CHAT_FIXTURE), "--replay-chat", str(self.path),
             "--rescore", str(self.path)],
        ]
        for argv in cases:
            with self.subTest(argv=argv), self.assertRaises(SystemExit):
                runner.main(argv)


class _ThanksEchoTransport(_ReplayTransport):
    """지정한 호출에서만 프록시 P5 감사 문장으로 끝나는 본문을 돌려준다."""

    def __init__(self, thanks_on_call: int) -> None:
        super().__init__()
        self.thanks_on_call = thanks_on_call

    def stream_chat(self, *, model, messages, max_tokens, timeout):
        text, ttft, complete, meta = super().stream_chat(
            model=model, messages=messages, max_tokens=max_tokens, timeout=timeout)
        if len(self.messages) == self.thanks_on_call:
            return f"그 얘기 재밌겠다. {runner.DONATION_ECHO_THANKS}", ttft, complete, meta
        return text, ttft, complete, meta


class DonationRitualIsNotConversationTests(unittest.TestCase):
    """사람 평가 run 04: 의례(호명 opener + 프록시 감사 문장)를 히스토리와 브리핑에
    되먹이자 모델이 이후 질문 23건에 "고마워."로 답했다. 의례 턴은 히스토리에 아예
    넣지 않고, "방금 흐름"에는 모델이 이어 말한 본문만 남는지 고정한다.
    """

    RAW = (
        (0, "가명001", "chat", "안녕!", ""),
        (30_000, "가명002", "donation", "오늘 방송 재밌다", "20000"),
        (90_000, "가명003", "chat", "게임 뭐 할 거야", ""),
        (150_000, "가명001", "chat", "다음 방송 언제", ""),
    )
    # 5초 창·20초 쿨다운 계산상 후원은 두 번째 픽업이다(그 다음 턴을 봐야 되먹임이 보인다).
    RITUAL_TURN = 2

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = write_replay(Path(directory.name), replay_rows(self.RAW))
        rows = runner.load_replay_rows(self.path)
        self.fixture = runner.build_replay_fixture(sim.load_fixture(REAL_CHAT_FIXTURE), rows)
        self.stream = runner.build_replay_stream(self.fixture, rows, path=self.path, seed=7)
        self.picks = sim.plan_pickups(self.stream, self.fixture)
        self.assertEqual([pick["effective_kind"] for pick in self.picks],
                         ["reaction", "donation", "reaction", "question"])

    def _run(self, transport, acts: str = "on") -> dict[str, Any]:
        return runner.run_arm(
            transport, self.fixture, self.stream, self.picks,
            model="test-model", contract="on", protocol="operational",
            author_format="runtime", history_turns=8, max_tokens=32, timeout=1.0,
            pre_session_seeds=False, briefing="on", acts=acts, briefing_evidence="off",
        )

    def test_the_ritual_turn_never_enters_the_history_window(self) -> None:
        transport = _ReplayTransport()
        result = self._run(transport)
        opener = runner.thank_renderer.render_thank_callout_text("가명002", 0)
        spoken = next(entry for entry in result["transcript"]
                      if entry.get("stage") == "turn" and entry["kind"] == "donation")
        # 실제 발화와 채점은 그대로다.
        self.assertTrue(spoken["airi"].startswith(opener))
        self.assertEqual(spoken["deterministic_act"], "thank_renderer")
        self.assertTrue(result["rows"][self.RITUAL_TURN - 1]["addressee_ok"])
        # 다음 턴 요청에는 의례가 assistant 턴으로도 브리핑으로도 실리지 않는다.
        next_messages = transport.messages[self.RITUAL_TURN]
        assistant = [m["content"] for m in next_messages if m["role"] == "assistant"]
        self.assertEqual(assistant, ["응, 1번째 대답이야."])
        self.assertFalse(any(opener in m["content"] for m in next_messages))
        # 브리핑 "방금 흐름" 에는 모델이 이어 말한 본문만 남는다.
        system_content = next_messages[0]["content"]
        self.assertIn("응, 2번째 대답이야.", system_content)
        self.assertNotIn(opener, system_content)

    def test_the_proxy_thanks_line_is_stripped_from_the_briefing_echo(self) -> None:
        transport = _ThanksEchoTransport(self.RITUAL_TURN)
        self._run(transport)
        system_content = transport.messages[self.RITUAL_TURN][0]["content"]
        self.assertIn("그 얘기 재밌겠다.", system_content)
        self.assertNotIn(runner.DONATION_ECHO_THANKS, system_content)

    def test_a_donation_echo_without_the_renderer_is_still_kept_out_of_history(self) -> None:
        transport = _ThanksEchoTransport(self.RITUAL_TURN)
        self._run(transport, acts="off")
        next_messages = transport.messages[self.RITUAL_TURN]
        assistant = [m["content"] for m in next_messages if m["role"] == "assistant"]
        self.assertEqual(assistant, ["응, 1번째 대답이야."])
        self.assertNotIn(runner.DONATION_ECHO_THANKS, next_messages[0]["content"])

    def test_ordinary_turns_still_feed_the_history(self) -> None:
        transport = _ReplayTransport()
        self._run(transport)
        last_messages = transport.messages[-1]
        assistant = [m["content"] for m in last_messages if m["role"] == "assistant"]
        self.assertEqual(assistant, ["응, 1번째 대답이야.", "응, 3번째 대답이야."])


class ReplayTranscriptTests(unittest.TestCase):
    SEGMENTS = [
        {"start_ms": 1_000, "end_ms": 4_000, "text": "오늘은 트래커 달고 춤 연습할 거야"},
        {"start_ms": 5_000, "end_ms": 9_000, "text": "장갑은 손가락 트래킹 때문에 껴"},
        {"start_ms": 60_000, "end_ms": 63_000, "text": "이제 링피트 켤게"},
    ]

    def test_window_keeps_only_speech_that_ended_just_before_the_chat(self) -> None:
        self.assertEqual(
            runner.transcript_window_text(self.SEGMENTS, 10_000, 45_000),
            "오늘은 트래커 달고 춤 연습할 거야 장갑은 손가락 트래킹 때문에 껴")
        self.assertEqual(runner.transcript_window_text(self.SEGMENTS, 62_000, 45_000), "")
        self.assertEqual(runner.transcript_window_text(self.SEGMENTS, 70_000, 45_000), "이제 링피트 켤게")

    def test_window_is_capped_to_the_newest_chars(self) -> None:
        long = [{"start_ms": 0, "end_ms": 1_000, "text": "가" * 500}, {"start_ms": 1_000, "end_ms": 2_000, "text": "끝"}]
        text = runner.transcript_window_text(long, 3_000, 45_000)
        self.assertTrue(text.startswith("…") and text.endswith("끝"))
        self.assertLessEqual(len(text), runner.TRANSCRIPT_MAX_CHARS + 1)

    def test_loader_validates_rows_and_sorts_by_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.jsonl"
            path.write_text(
                json.dumps({"start_ms": 5000, "end_ms": 9000, "text": "둘"}) + "\n"
                + json.dumps({"start_ms": 1000, "end_ms": 4000, "text": "하나"}) + "\n"
                + json.dumps({"start_ms": 9000, "end_ms": 9500, "text": "  "}) + "\n",
                encoding="utf-8")
            segments = runner.load_transcript_segments(path)
            self.assertEqual([seg["text"] for seg in segments], ["하나", "둘"])
            path.write_text(json.dumps({"start_ms": 5, "end_ms": 1, "text": "x"}) + "\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                runner.load_transcript_segments(path)

    def test_replay_messages_keep_the_absolute_offset(self) -> None:
        rows = [
            {"source": "chzzk", "video_ref": "v", "offset_ms": 15_000, "author": "a", "kind": "chat", "text": "안녕"},
            {"source": "chzzk", "video_ref": "v", "offset_ms": 75_000, "author": "b", "kind": "chat", "text": "둥하"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chat.jsonl"
            path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
            base = sim.load_fixture(HERE.parent / "human_review" / "real_chat_fixture.json")
            fixture = runner.build_replay_fixture(base, rows)
            stream = runner.build_replay_stream(fixture, rows, path=path, seed=1)
        self.assertEqual([m["offset_ms"] for m in stream["messages"]], [15_000, 75_000])
        self.assertEqual([m["t_ms"] for m in stream["messages"]], [0, 60_000])


if __name__ == "__main__":
    unittest.main()
