"""Default-off tag-bound live show context (AIRI_LIVE_TAG_CONTEXT).

A real show's YouTube chat reaches the proxy only as ``[YouTube] {text}`` turns from AIRI desktop,
with no broadcast turn token. The operator sets the current show context once per segment; a tagged
viewer turn then gets the same context note an issued turn would, and nothing else.
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ollama_proxy
from live_broadcast_runtime import BROADCAST_BRIEFING_HEADER, LiveBroadcastRuntime, render_broadcast_context
from memory_runtime import NullMemoryRuntime
from persona_temperament import TEMPERAMENT_CARD
from show_carryover import CARRYOVER_FILE_NAME, ShowCarryoverStore
from word_chain_referee import WordChainReferee


MASTER, OBSERVER = "m" * 32, "o" * 32
CONTEXT = {
    "schema_version": 1, "topic_title": "두 번째 방송", "segment_label": "오프닝 잡담",
    "situation": "인사가 끝났다.", "briefing": BROADCAST_BRIEFING_HEADER + "\n- 채팅 집계: 참여 5",
    "donation_continuation": False,
}
WORD_CHAIN = {**CONTEXT, "segment_label": "끝말잇기 1라운드", "situation": "끝말잇기 대결 중이다."}
TAGGED = "[YouTube] 오늘 뭐 해?"
STAMPED = "[2026-09-29 21:03] [YouTube] 오늘 뭐 해?"
ENDPOINTS = (("/api/chat", True), ("/api/chat", False), ("/v1/chat/completions", True),
             ("/v1/chat/completions", False))
CARRY_ITEMS = [("약속", "원하면 다음 방송에 세 줄 쪽 재대결"), ("결과", "양쪽 모두 성공, 무승부")]
CARRY_LINE = "- 지난 방송 기억: 약속은 원하면 이번 방송에 세 줄 쪽 재대결. 결과는 양쪽 모두 성공, 무승부."
REJECTED = {"error": "invalid broadcast request"}


def _event(content: str) -> bytes:
    return (json.dumps({"message": {"role": "assistant", "content": content}, "done": True},
                       ensure_ascii=False) + "\n").encode("utf-8")


class _Response:
    def __init__(self, chunks: list[bytes]) -> None:
        self.status_code = 200
        self.headers = {"content-type": "application/x-ndjson"}
        self._chunks = chunks

    async def aiter_raw(self):
        for chunk in self._chunks:
            yield chunk

    async def aread(self) -> bytes:
        return b"".join(self._chunks)

    async def aclose(self) -> None:
        return None


class _RawClient:
    """One native answer per attempt; keeps the exact upstream bytes of every attempt."""

    def __init__(self, drafts: list[str]) -> None:
        self.responses = [_Response([_event(draft)]) for draft in drafts]
        self.raw: list[bytes] = []

    def build_request(self, *args: object, **kwargs: object) -> bytes:
        content = kwargs.get("content", b"")
        return content if isinstance(content, bytes) else b""

    async def send(self, request: bytes, *args: object, **kwargs: object) -> _Response:
        self.raw.append(request)
        return self.responses.pop(0)


def _contexts(raw: bytes) -> list[str]:
    """The show context messages in one upstream request."""
    return [str(message.get("content")) for message in json.loads(raw)["messages"]
            if "[오늘 방송]" in str(message.get("content", ""))]


def _word_list(test: unittest.TestCase, words: list[str]) -> Path:
    folder = tempfile.TemporaryDirectory()
    test.addCleanup(folder.cleanup)
    path = Path(folder.name) / "words.tsv"
    rows = "".join(f"{word}\t{index + 1}\tA\n" for index, word in enumerate(words))
    path.write_text("word\trank\tlevel\n" + rows, encoding="utf-8")
    return path


class TagContextTests(unittest.TestCase):
    class _Verdict:
        allowed = True
        category = "allowed"
        rule = "allow"

    class _ReadyScreen:
        enabled = True

        @staticmethod
        def health():
            return {"ready": True}

        @staticmethod
        def inspect(_text):
            return TagContextTests._Verdict()

        @staticmethod
        def classify(_text):
            return TagContextTests._Verdict()

    def setUp(self):
        screen = mock.patch.object(ollama_proxy, "input_screening_runtime", self._ReadyScreen())
        screen.start()
        self.addCleanup(screen.stop)
        self._use_runtime()

    def _use_runtime(self, *, enabled: bool = True, tag_context: bool = True,
                     carryover: ShowCarryoverStore | None = None) -> LiveBroadcastRuntime:
        self.runtime = LiveBroadcastRuntime(enabled, MASTER, OBSERVER, carryover=carryover, tag_context=tag_context)
        patch = mock.patch.object(ollama_proxy, "live_broadcast_runtime", self.runtime)
        patch.start()
        self.addCleanup(patch.stop)
        return self.runtime

    def _use_carryover(self, items: list[tuple[str, str]]) -> ShowCarryoverStore:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        store = ShowCarryoverStore(Path(folder.name) / CARRYOVER_FILE_NAME)
        self.assertTrue(store.finalize(items))
        self._use_runtime(carryover=store)
        return store

    def control(self, payload: dict[str, object], token: str | None = MASTER, header: str = "x-airi-broadcast-master-token"):
        headers = {"content-type": "application/json"}
        if token is not None:
            headers[header] = token
        return TestClient(ollama_proxy.app, client=("127.0.0.1", 9)).post(
            "/v1/airi/broadcast/control", content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
        )

    def start(self, *show_ids: str) -> None:
        for show_id in show_ids:
            self.assertEqual(self.runtime.master_control({"action": "start", "show_id": show_id}), {})

    def set_context(self, show_id: str, context: dict[str, object] | None = None) -> None:
        response = self.control({"action": "set_tag_context", "show_id": show_id,
                                 "broadcast_context": dict(CONTEXT if context is None else context)})
        self.assertEqual((response.status_code, response.json()), (200, {}))

    def chat(self, user: str | list[dict[str, str]], *, path: str = "/api/chat", stream: bool = True,
             env: dict[str, str] | None = None, referee: WordChainReferee | None = None,
             headers: dict[str, str] | None = None, host: str = "127.0.0.1",
             drafts: tuple[str, ...] = ("좋아, 받았어.",)):
        """One chat turn; returns the upstream client (raw bytes per attempt) and the response."""
        messages = [{"role": "user", "content": user}] if isinstance(user, str) else user
        client = _RawClient(list(drafts))
        values = {"AIRI_LIVE_BRIEFING_CANDIDATES": "", "AIRI_LIVE_PERSONA_TEMPERAMENT": "", **(env or {})}
        with mock.patch.dict("os.environ", values), \
                mock.patch.object(ollama_proxy.deterministic_utterance_layer,
                                  "DETERMINISTIC_UTTERANCE_LAYER_ENABLED", False), \
                mock.patch.object(ollama_proxy, "client", client), \
                mock.patch.object(ollama_proxy, "needs_grounding_retry", lambda *a, **k: False), \
                mock.patch.object(ollama_proxy, "memory_runtime", NullMemoryRuntime()), \
                mock.patch.object(ollama_proxy, "character_state_runtime",
                                  ollama_proxy.CharacterStateRuntime(clock=lambda: 1_790_000_000.0)), \
                mock.patch.object(ollama_proxy, "word_chain_referee", referee or WordChainReferee()):
            response = TestClient(ollama_proxy.app, client=(host, 9)).post(
                path, content=json.dumps({"model": "exaone-airi:2.4b", "stream": stream, "messages": messages},
                                         ensure_ascii=False).encode("utf-8"),
                headers={"content-type": "application/json", "x-airi-request-id": "tag-trace", **(headers or {})},
            )
        return client, response

    def tag_raw(self, user: str = TAGGED, **kwargs) -> bytes:
        client, response = self.chat(user, **kwargs)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(client.raw), 1)
        return client.raw[0]

    def issued_raw(self, show_id: str, action_id: str, user: str, context: dict[str, object], **kwargs) -> bytes:
        capability = self.runtime.master_control({
            "action": "issue_turn", "show_id": show_id, "action_id": action_id,
            "turn_type": "chat_question", "required_delivery": "renderer", "broadcast_context": dict(context),
        })
        try:
            return self.tag_raw(user, headers={"x-airi-broadcast-turn-token": capability["turn_token"]}, **kwargs)
        finally:
            self.runtime.cancel_turn(capability["turn_token"])

    def test_feature_off_leaves_a_tagged_turn_byte_identical(self):
        for path, stream in ENDPOINTS:
            with self.subTest(path=path, stream=stream):
                self._use_runtime(enabled=False)
                baseline = self.tag_raw(path=path, stream=stream)
                off = self._use_runtime(tag_context=False)
                self.start("show-off")
                rejected = off.health()["rejected_controls"]
                unknown = self.control({"action": "no_such_action", "show_id": "show-off"})
                for payload in ({"action": "set_tag_context", "show_id": "show-off", "broadcast_context": CONTEXT},
                                {"action": "clear_tag_context", "show_id": "show-off"}):
                    response = self.control(payload)
                    self.assertEqual((response.status_code, response.json()), (unknown.status_code, unknown.json()))
                    self.assertEqual((response.status_code, response.json()), (400, REJECTED))
                self.assertEqual(off.health()["rejected_controls"], rejected + 3)
                self.assertEqual(self.tag_raw(path=path, stream=stream), baseline)
                self.assertEqual(off.tag_context_health(), {"enabled": False, "active": False, "turns": 0})
                self._use_runtime()
                self.start("show-on")
                self.assertEqual(self.tag_raw(path=path, stream=stream), baseline)
                self.set_context("show-on")
                on = self.tag_raw(path=path, stream=stream)
                self.assertNotEqual(on, baseline)
                self.assertEqual(_contexts(on), [render_broadcast_context(CONTEXT)])
                self.assertEqual(self.control({"action": "clear_tag_context", "show_id": "show-on"}).json(), {})
                self.assertEqual(self.tag_raw(path=path, stream=stream), baseline)

    def test_a_tag_turn_drops_caller_system_messages_like_an_issued_turn(self):
        # The persona model is trained on issued-turn prompts, where the runtime is the only source of
        # system context; AIRI desktop's own system messages would make real-show prompts differ.
        desktop = {"role": "system", "content": "DESKTOP CARD: 너는 데스크톱 캐릭터야."}
        self.start("show-sys")
        self.set_context("show-sys")
        tagged = self.tag_raw([desktop, {"role": "user", "content": TAGGED}]).decode("utf-8")
        self.assertNotIn("DESKTOP CARD", tagged)
        self.assertEqual(_contexts(tagged.encode("utf-8")), [render_broadcast_context(CONTEXT)])
        untagged = self.tag_raw([desktop, {"role": "user", "content": "오늘 뭐 해?"}]).decode("utf-8")
        self.assertIn("DESKTOP CARD", untagged)
        self._use_runtime(tag_context=False)
        self.assertIn("DESKTOP CARD", self.tag_raw([desktop, {"role": "user", "content": TAGGED}]).decode("utf-8"))

    def test_a_tagged_viewer_turn_gets_the_operator_context_on_both_endpoints(self):
        self.start("show-a")
        self.set_context("show-a")
        turns = 0
        for path, stream in ENDPOINTS:
            for user in (TAGGED, STAMPED):
                with self.subTest(path=path, stream=stream, user=user):
                    raw = self.tag_raw(user, path=path, stream=stream)
                    turns += 1
                    self.assertEqual(_contexts(raw), [render_broadcast_context(CONTEXT)])
                    # Downstream it is a live broadcast turn, but no arc or affect record rides along.
                    self.assertIn(ollama_proxy.BROADCAST_RESPONSE_STYLE_CONTRACT, raw.decode("utf-8"))
                    self.assertNotIn("airi_affect_expression", raw.decode("utf-8"))
                    self.assertEqual(self.runtime.tag_context_health()["turns"], turns)
        # A later set replaces the context; only the latest one is shown.
        replaced = {**CONTEXT, "segment_label": "게임 구간", "situation": "게임을 시작했다."}
        self.set_context("show-a", replaced)
        self.assertEqual(_contexts(self.tag_raw()), [render_broadcast_context(replaced)])
        self.start("show-b")
        self.set_context("show-b")
        self.assertEqual(_contexts(self.tag_raw()), [render_broadcast_context(CONTEXT)])

    def test_temperament_card_and_referee_lines_follow_the_tag_context(self):
        self.start("show-card", "show-wc")
        self.set_context("show-card")
        for path, stream in ENDPOINTS:
            with self.subTest(path=path, stream=stream):
                raw = self.tag_raw(path=path, stream=stream, env={"AIRI_LIVE_PERSONA_TEMPERAMENT": "on"})
                self.assertEqual(_contexts(raw), [TEMPERAMENT_CARD + "\n\n" + render_broadcast_context(CONTEXT)])
        # A referee without a 끝말잇기 segment is never consulted.
        referee = WordChainReferee.from_path(_word_list(self, ["기차", "차표"]))
        self.assertTrue(referee.enabled)
        self.assertEqual(_contexts(self.tag_raw("[YouTube] 기차", referee=referee)), [render_broadcast_context(CONTEXT)])
        self.assertEqual(referee.health()["turns"], 0)
        self.set_context("show-wc", WORD_CHAIN)
        note = render_broadcast_context(WORD_CHAIN)
        raw = self.tag_raw("[YouTube] 내가 먼저 한다 기차", referee=referee)
        self.assertEqual(_contexts(raw), [note + "\n- 심판 판정: 기차 유효, AIRI 차례\n- AIRI 낼 단어: 차표"])
        # The round is the show's: a fresh round would accept 기차, this one must follow 차표.
        raw = self.tag_raw("[YouTube] 기차", path="/v1/chat/completions", referee=referee)
        self.assertEqual(_contexts(raw), [note + "\n- 심판 판정: 기차 무효(끝 글자와 안 이어짐), 다시"])

    def test_a_tag_turn_note_matches_an_issued_turn_note(self):
        store = self._use_carryover(CARRY_ITEMS)
        self.assertEqual(store.items, CARRY_ITEMS)
        self.start("show-issued", "show-tagged")
        self.set_context("show-tagged", WORD_CHAIN)
        env = {"AIRI_LIVE_PERSONA_TEMPERAMENT": "on"}
        user = "[YouTube] 내가 먼저 한다 기차"
        for path in ("/api/chat", "/v1/chat/completions"):
            with self.subTest(path=path):
                words = _word_list(self, ["기차", "차표"])
                issued = self.issued_raw("show-issued", f"issued-{path.count('/')}", user, WORD_CHAIN, path=path,
                                         env=env, referee=WordChainReferee.from_path(words))
                tagged = self.tag_raw(user, path=path, env=env, referee=WordChainReferee.from_path(words))
                self.assertEqual(len(_contexts(issued)), 1)
                self.assertEqual(_contexts(tagged), _contexts(issued))
                self.assertIn(CARRY_LINE, _contexts(tagged)[0])
                self.assertTrue(_contexts(tagged)[0].startswith(TEMPERAMENT_CARD))
                self.assertTrue(_contexts(tagged)[0].endswith("\n- AIRI 낼 단어: 차표"))
                self.assertIn("airi_affect_expression", issued.decode("utf-8"))
                self.assertNotIn("airi_affect_expression", tagged.decode("utf-8"))

    def test_briefing_candidates_select_on_a_tag_turn(self):
        self.start("show-brief")
        self.set_context("show-brief", {
            **CONTEXT, "briefing": BROADCAST_BRIEFING_HEADER + "\n- 이번 턴에 말할 것: 오늘은 통증이 왼쪽 귀까지 번져 있었어."
                                   "\n- 아직 말하지 말 것: 병원, 진료 결과",
        })
        for budget, requests in (("", 1), ("2", 2)):
            for stream in (True, False):
                with self.subTest(budget=budget, stream=stream):
                    client, response = self.chat(
                        "[YouTube] 그래서 오늘은 좀 나아짐?", stream=stream, env={"AIRI_LIVE_BRIEFING_CANDIDATES": budget},
                        drafts=("응, 훨씬 나아졌어!", "아니, 오늘은 통증이 왼쪽 귀까지 번져 있었어."),
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(len(client.raw), requests)
                    rows = [json.loads(line) for line in response.text.splitlines() if line.strip()]
                    spoken = rows[-1]["message"]["content"]
                    prompt = client.raw[0].decode("utf-8")
                    self.assertIn("이번 턴에 말할 것", prompt)
                    if budget:
                        self.assertEqual(spoken, "아니, 오늘은 통증이 왼쪽 귀까지 번져 있었어.")
                        self.assertNotIn("아직 말하지 말 것", prompt)
                    else:
                        self.assertEqual(spoken, "응, 훨씬 나아졌어!")
                        self.assertIn("아직 말하지 말 것", prompt)

    def test_untagged_and_ineligible_turns_are_untouched(self):
        cases = (
            ("untagged", "오늘 뭐 해?"),
            ("tag only earlier", [{"role": "user", "content": TAGGED}, {"role": "assistant", "content": "노래 불러."},
                                  {"role": "user", "content": "오늘 뭐 해?"}]),
            ("tag mid-text", "아니 [YouTube] 오늘 뭐 해?"),
        )
        self._use_runtime(enabled=False)
        baselines = {name: self.tag_raw(user) for name, user in cases}
        self._use_runtime()
        self.start("show-a")
        self.set_context("show-a")
        for name, user in cases:
            with self.subTest(case=name):
                self.assertEqual(self.tag_raw(user), baselines[name])
        for name, headers, host in (
            ("proactive", {"x-airi-turn-origin": "local-proactive"}, "127.0.0.1"),
            ("evaluation", {"x-airi-turn-origin": "local-evaluation"}, "127.0.0.1"),
            ("quality probe", {"x-airi-turn-origin": "local-quality-probe"}, "127.0.0.1"),
            ("unknown turn token", {"x-airi-broadcast-turn-token": "t" * 43}, "127.0.0.1"),
            ("empty turn token", {"x-airi-broadcast-turn-token": ""}, "127.0.0.1"),
            ("remote peer", {}, "192.0.2.10"),
        ):
            with self.subTest(case=name):
                client, _ = self.chat(TAGGED, headers=headers, host=host, drafts=("좋아.", "좋아."))
                for raw in client.raw:
                    self.assertEqual(_contexts(raw), [])
        self.assertEqual(self.runtime.tag_context_health()["turns"], 0)

    def test_set_and_clear_need_the_master_token_and_a_started_show(self):
        self.start("show-a")
        set_a = {"action": "set_tag_context", "show_id": "show-a", "broadcast_context": CONTEXT}
        for token, header in ((None, "x-airi-broadcast-master-token"), ("x" * 32, "x-airi-broadcast-master-token"),
                              (OBSERVER, "x-airi-broadcast-master-token"), (OBSERVER, "x-airi-broadcast-observer-token"),
                              (MASTER, "x-airi-broadcast-observer-token")):
            for payload in (set_a, {"action": "clear_tag_context", "show_id": "show-a"}):
                with self.subTest(header=header, action=payload["action"]):
                    self.assertEqual(self.control(payload, token=token, header=header).status_code, 401)
        self.assertFalse(self.runtime.tag_context_health()["active"])
        for payload in (
            {**set_a, "show_id": "show-never-started"},
            {"action": "clear_tag_context", "show_id": "show-never-started"},
            {**set_a, "action_id": "extra"},
            {"action": "set_tag_context", "show_id": "show-a"},
            {"action": "clear_tag_context", "show_id": "show-a", "broadcast_context": CONTEXT},
        ):
            with self.subTest(payload=payload):
                response = self.control(payload)
                self.assertEqual((response.status_code, response.json()), (400, REJECTED))
        self.assertFalse(self.runtime.tag_context_health()["active"])
        self.set_context("show-a")
        # The context is validated exactly as issue_turn validates it; a rejected set keeps the active one.
        invalid = (
            {**CONTEXT, "extra": "x"}, {key: value for key, value in CONTEXT.items() if key != "situation"},
            {**CONTEXT, "schema_version": 2}, {**CONTEXT, "topic_title": ""}, {**CONTEXT, "situation": "가" * 301},
            {**CONTEXT, "briefing": "- 이번 턴에 말할 것: 헤더 없음"}, {**CONTEXT, "briefing": BROADCAST_BRIEFING_HEADER + "가" * 2048},
            {**CONTEXT, "donation_continuation": "no"}, {**CONTEXT, "segment_label": "a\0b"}, "not a context",
        )
        for index, context in enumerate(invalid):
            with self.subTest(context=index):
                response = self.control({**set_a, "broadcast_context": context})
                self.assertEqual((response.status_code, response.json()), (400, REJECTED))
                with self.assertRaises(ValueError):
                    self.runtime.master_control({
                        "action": "issue_turn", "show_id": "show-a", "action_id": f"bad-{index}",
                        "turn_type": "chat_question", "required_delivery": "renderer", "broadcast_context": context,
                    })
        self.assertEqual(_contexts(self.tag_raw()), [render_broadcast_context(CONTEXT)])
        # Clearing another show's context leaves this one; clearing this show's removes it.
        self.start("show-b")
        self.assertEqual(self.control({"action": "clear_tag_context", "show_id": "show-b"}).json(), {})
        self.assertTrue(self.runtime.tag_context_health()["active"])
        self.assertEqual(self.control({"action": "clear_tag_context", "show_id": "show-a"}).json(), {})
        self.assertFalse(self.runtime.tag_context_health()["active"])
        self.assertEqual(self.control({"action": "clear_tag_context", "show_id": "show-a"}).json(), {})
        self.assertEqual(_contexts(self.tag_raw()), [])

    def test_closing_the_show_clears_its_tag_context(self):
        self.start("show-a", "show-b")
        self.set_context("show-b")
        self.assertEqual(self.control({"action": "close", "show_id": "show-a"}).json(), {})
        self.assertTrue(self.runtime.tag_context_health()["active"])
        self.assertEqual(self.control({"action": "close", "show_id": "show-b"}).json(), {})
        self.assertFalse(self.runtime.tag_context_health()["active"])
        self.assertEqual(_contexts(self.tag_raw()), [])
        self.start("show-b")
        self.assertEqual(_contexts(self.tag_raw()), [])
        self.assertEqual(self.runtime.tag_context_health()["turns"], 0)

    def test_health_reports_the_tag_context_without_content(self):
        keys = {"enabled", "active", "turns"}
        self._use_runtime(tag_context=False)
        self.assertEqual(asyncio.run(ollama_proxy.health())["tag_context"], {"enabled": False, "active": False, "turns": 0})
        self._use_runtime()
        self.assertEqual(asyncio.run(ollama_proxy.health())["tag_context"], {"enabled": True, "active": False, "turns": 0})
        self.start("secret-show-7")
        self.set_context("secret-show-7", {**CONTEXT, "topic_title": "비밀주제오메가"})
        self.tag_raw()
        reported = asyncio.run(ollama_proxy.health())["tag_context"]
        self.assertEqual(set(reported), keys)
        self.assertEqual(reported, {"enabled": True, "active": True, "turns": 1})
        serialized = json.dumps(reported, ensure_ascii=False)
        for text in ("secret-show-7", "비밀주제오메가", "오늘 뭐 해"):
            self.assertNotIn(text, serialized)

    def test_carryover_finalizes_memo_items_of_a_tag_context_show(self):
        store = self._use_carryover(CARRY_ITEMS)
        briefing = (BROADCAST_BRIEFING_HEADER + "\n- 채팅 집계: 재대결 찬성 12"
                    "\n- 약속: 다음 방송에 네 줄 쪽 재대결\n- 결과: 감자님 우승")
        self.start("show-carry", "show-unaired")
        self.set_context("show-unaired", {**CONTEXT, "briefing": briefing})
        # A context never shown to a viewer turn is never delivered, so closing writes nothing.
        finalized = store.finalized
        self.assertEqual(self.control({"action": "close", "show_id": "show-unaired"}).json(), {})
        self.assertEqual((store.finalized, store.items), (finalized, CARRY_ITEMS))
        self.set_context("show-carry", {**CONTEXT, "briefing": briefing})
        self.assertEqual(self.runtime.carryover_health()["rejected"], 2)
        context = _contexts(self.tag_raw())[0]
        self.assertIn(BROADCAST_BRIEFING_HEADER + "\n" + CARRY_LINE + "\n- 채팅 집계", context)
        self.assertEqual(context, render_broadcast_context({**CONTEXT, "briefing": briefing}, carryover_line=CARRY_LINE))
        self.assertEqual(self.runtime.carryover_health()["captured"], 1)
        self.assertEqual(self.control({"action": "close", "show_id": "show-carry"}).json(), {})
        self.assertEqual(store.finalized, finalized + 1)
        self.assertEqual(store.items, [("약속", "다음 방송에 네 줄 쪽 재대결")])
        self.assertEqual(ShowCarryoverStore(store.path).items, [("약속", "다음 방송에 네 줄 쪽 재대결")])

    def test_from_env_turns_the_tag_context_on_only_for_on(self):
        for value, enabled in (("on", True), ("1", False), ("true", False), ("", False), (None, False)):
            with self.subTest(value=value):
                env = {"AIRI_LIVE_BROADCAST_ENABLED": "on", "AIRI_LIVE_BROADCAST_MASTER_TOKEN": MASTER,
                       "AIRI_LIVE_BROADCAST_OBSERVER_TOKEN": OBSERVER, "AIRI_LIVE_SHOW_CARRYOVER": ""}
                with mock.patch.dict("os.environ", env):
                    if value is None:
                        os.environ.pop("AIRI_LIVE_TAG_CONTEXT", None)
                    else:
                        os.environ["AIRI_LIVE_TAG_CONTEXT"] = value
                    runtime = LiveBroadcastRuntime.from_env()
                self.assertEqual(runtime.tag_context_health()["enabled"], enabled)
        # A disabled live runtime never enables it.
        self.assertFalse(LiveBroadcastRuntime(False, MASTER, OBSERVER, tag_context=True).tag_context_health()["enabled"])


if __name__ == "__main__":
    unittest.main()
