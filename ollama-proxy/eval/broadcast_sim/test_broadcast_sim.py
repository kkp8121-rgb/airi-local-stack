from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("broadcast_sim_test", HERE / "broadcast_sim.py")
assert SPEC is not None and SPEC.loader is not None
sim = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sim)


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

    def test_every_donation_and_probe_is_answered(self) -> None:
        stream = sim.generate_stream(self.fixture, seed=20260818)
        picks = sim.plan_pickups(stream, self.fixture)
        picked = {pick["message"]["id"] for pick in picks}
        for item in stream["messages"]:
            if item["kind"] in ("donation", "memory_probe"):
                self.assertIn(item["id"], picked, f"{item['kind']} {item['id']} 를 놓쳤다")

    def test_max_turns_truncates_without_reordering(self) -> None:
        stream = sim.generate_stream(self.fixture, seed=20260818)
        full = sim.plan_pickups(stream, self.fixture)
        short = sim.plan_pickups(stream, self.fixture, max_turns=5)
        self.assertEqual(len(short), 5)
        self.assertEqual([pick["message"]["id"] for pick in short],
                         [pick["message"]["id"] for pick in full[:5]])


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
