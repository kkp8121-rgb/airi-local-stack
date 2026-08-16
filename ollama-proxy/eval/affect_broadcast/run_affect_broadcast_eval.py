"""Offline structural evaluation for synthetic AIRI affect broadcasts.

This is deliberately an evaluator, not an adoption gate.  It proves the
closed reducer oracle and the OFF/ON request pairing; people evaluate replies.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
import secrets
import socket
import stat
import time
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlparse, urlunparse


HERE = Path(__file__).resolve().parent
FIXTURE_PATH = HERE / "synthetic_affect_broadcast_v1.json"
FIXTURE_SCHEMA_VERSION = "airi.affect-broadcast-fixture.v1"
REPORT_SCHEMA_VERSION = "airi.affect-broadcast-report.v2"
RUNNER_VERSION = "1.2.0"
FIXTURE_SHA256 = "acbcc991e32820aeed2bb2eeaf58487f72a4629393c57d11142b77d84ead1bf8"
TURN_KEYS = frozenset(("id", "synthetic_only", "prior_airi", "context", "chat_batch", "selected_message", "selection_reason", "events", "expected_state", "allowed_traits", "forbidden_traits"))
SCENARIO_KEYS = frozenset(("id", "synthetic_only", "title", "turns"))
FIXTURE_KEYS = frozenset(("schema_version", "synthetic_only", "scenarios"))
TRAITS = frozenset(("warm", "curious", "playful", "direct", "apologetic", "calm", "brief", "competitive", "careful", "restful"))
PRIMARY_RESPONSE_TRAITS = {
    "neutral": (("brief", "calm"), ("competitive", "apologetic")),
    "curious": (("curious", "direct"), ("restful", "apologetic")),
    "amused": (("playful", "warm"), ("restful", "apologetic")),
    "pleased": (("warm", "direct"), ("restful", "competitive")),
    "proud": (("competitive", "direct"), ("apologetic", "restful")),
    "embarrassed": (("brief", "direct"), ("competitive", "warm")),
    "skeptical": (("careful", "direct"), ("warm", "playful")),
    "playful_annoyed": (("playful", "direct"), ("apologetic", "restful")),
    "concerned": (("calm", "careful"), ("playful", "competitive")),
    "disappointed": (("brief", "direct"), ("warm", "playful")),
    "competitive": (("competitive", "direct"), ("restful", "apologetic")),
    "relieved": (("apologetic", "brief"), ("competitive", "playful")),
    "tired": (("restful", "brief"), ("competitive", "playful")),
}
SELECTION_REASONS = frozenset(("screen_reaction", "reply_to_prior", "callback_relevance", "donation_acknowledgement", "safety_priority", "no_reply_observed", "ambient_noise"))
SCENARIO_IDS = ("first", "teasing", "game", "correction", "callback", "fatigue")
SCENARIO_TITLES = {
    "first": "처음 방송 적응",
    "teasing": "그림 퀴즈 장난과 수습",
    "game": "얼음 동굴 보스 재도전",
    "correction": "지도 표식 정정과 인정",
    "callback": "주말 간식 잡담과 콜백",
    "fatigue": "늦은 밤 피로와 안전",
}
SCENARIO_TOPICS = {
    "first": ("오디오와 화면 설정", "신호 정원 첫 기록", "다음 방송 아이디어", "첫 방송 마무리"),
    "teasing": ("그림 퀴즈 첫 오답", "놀림을 받아치는 법", "힌트와 두 번째 정정", "마지막 문제와 수습"),
    "game": ("보스 패턴 확인", "회피 순서 재설계", "두 번째 페이즈 돌파", "클리어 복기"),
    "correction": ("지도 표식 읽기", "추측과 화면 확인 분리", "정정 내용 고정", "확실한 경로만 남기기"),
    "callback": ("주말 간식 이야기", "후원 알림과 채팅 공백", "앞선 이야기 콜백", "다음 잡담 약속"),
    "fatigue": ("늦은 밤 피로 신호", "시청자 안전 우선", "안전 확인과 진행 중단", "회복 확인 후 종료"),
}
SCENARIO_EVENT_ARCS = {
    "first": ("broadcast_start", "topic_open", "chat_question", "chat_question", "silence", "chat_question", "topic_open", "chat_question", "chat_question", "silence", "chat_question", "chat_question", "topic_open", "chat_question", "chat_question", "silence", "chat_question", "chat_question", "topic_open", "chat_question", "chat_question", "callback_hit", "chat_question", "silence"),
    "teasing": ("broadcast_start", "chat_teasing", "chat_teasing", "chat_teasing", "chat_correction", "response_repair", "chat_teasing", "chat_question", "response_repair", "chat_question", "chat_teasing", "chat_correction", "response_repair", "chat_question", "chat_teasing", "chat_question", "chat_correction", "response_repair", "chat_concern", "response_repair", "chat_question", "chat_correction", "response_repair", "silence"),
    "game": ("broadcast_start", "game_failure", "silence", "game_failure", "chat_question", "game_failure", "chat_question", "game_failure", "topic_open", "chat_question", "game_failure", "silence", "chat_question", "topic_open", "game_success", "chat_question", "game_failure", "game_success", "game_success", "response_repair", "callback_hit", "topic_change", "silence", "silence"),
    "correction": ("broadcast_start", "chat_correction", "chat_correction", "chat_correction", "response_repair", "chat_question", "chat_correction", "chat_question", "chat_correction", "topic_open", "response_repair", "chat_question", "chat_correction", "chat_question", "chat_correction", "response_repair", "chat_concern", "response_repair", "topic_open", "chat_question", "response_repair", "chat_question", "topic_change", "silence"),
    "callback": ("broadcast_start", "callback_hit", "chat_question", "donation_received", "chat_question", "chat_question", "silence", "silence", "callback_hit", "chat_question", "donation_received", "chat_question", "silence", "chat_question", "callback_hit", "silence", "chat_question", "chat_question", "silence", "donation_received", "chat_question", "callback_hit", "chat_question", "silence"),
    "fatigue": ("broadcast_start", "silence", "chat_concern", "silence", "chat_concern", "chat_concern", "silence", "chat_concern", "safety_override", "safety_override", "safety_override", "silence", "safety_override", "chat_concern", "safety_override", "response_repair", "safety_override", "silence", "response_repair", "chat_concern", "safety_override", "silence", "response_repair", "broadcast_end"),
}
NO_RESPONSE_TURNS = {
    "first": (5, 10, 16, 24),
    "teasing": (24,),
    "game": (3, 12, 23, 24),
    "correction": (24,),
    "callback": (7, 8, 13, 16, 19, 24),
    "fatigue": (2, 4, 7, 12, 18, 22),
}
AMBIENT_NOISE_TURNS = {"callback": (7,)}
PROFILE_KEYS = frozenset(("model", "model_digest", "model_digest_status", "model_digest_verified", "num_ctx", "temperature", "seed", "max_tokens", "history_turns", "operational_affect_enabled"))
EXECUTION_KEYS = frozenset(("status", "selected_turn_count", "model_call_count", "response_count_by_arm", "response_char_count_by_arm", "health_profile_sha256", "private_responses"))
EVAL_PROFILE = {
    "model": "midm-airi:2.0-mini",
    "model_digest": "92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f",
    "model_digest_status": "pinned",
    "model_digest_verified": True,
    "num_ctx": 2048,
    "temperature": 0,
    "seed": 42,
    "max_tokens": 128,
    "history_turns": 8,
    "operational_affect_enabled": False,
}
MAX_TEXT = 240
MAX_RESPONSE_CHARS = 4000
MAX_REQUEST_BYTES = 64 * 1024
MAX_HTTP_BODY_BYTES = 64 * 1024
MAX_ARTIFACT_BYTES = {
    "public-report.json": 256 * 1024,
    "private-review-packet.json": 8 * 1024 * 1024,
    "private-arm-key.json": 8 * 1024,
    "local-run-receipt.json": 16 * 1024,
}
LOCAL_RESULTS_DIR = HERE / "local-results"
LOCAL_OPERATOR_KEYS_DIR = HERE / "local-operator-keys"
SAFE_RUN_BASENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
WINDOWS_RESERVED_BASENAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)
_REQUEST_INJECTOR: Callable[[bytes, str], bytes] | None = None


class EvalError(ValueError):
    pass


def _has_hangul(value: str) -> bool:
    return any("\uac00" <= char <= "\ud7a3" for char in value)


def _valid_korean_text(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value == value.strip()
        and value == unicodedata.normalize("NFC", value)
        and _has_hangul(value)
        and "??" not in value
        and "\ufffd" not in value
        and not re.search(r"\d+번 장면|\d+번째 흐름|같이 봐요", value)
        and not any(
            unicodedata.category(char) in {"Cc", "Cf"}
            or 0xD800 <= ord(char) <= 0xDFFF
            for char in value
        )
    )


def _affect():
    spec = importlib.util.spec_from_file_location("airi_eval_affect_state", HERE.parents[1] / "affect_state.py")
    if spec is None or spec.loader is None:
        raise EvalError("affect reducer is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inject_request_local_system_note(body: bytes, note: str) -> bytes:
    """Execute only the production copier function, without importing the app."""
    global _REQUEST_INJECTOR
    if _REQUEST_INJECTOR is not None:
        return _REQUEST_INJECTOR(body, note)
    try:
        source = (HERE.parents[1] / "ollama_proxy.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "inject_request_local_system_note"
        )
        constant = next(
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "REQUEST_LOCAL_SYSTEM_MESSAGE_NAME"
                for target in node.targets
            )
        )
        namespace: dict[str, Any] = {"json": json}
        exec(compile(ast.Module(body=[constant, function], type_ignores=[]), str(HERE.parents[1] / "ollama_proxy.py"), "exec"), namespace)
        candidate = namespace["inject_request_local_system_note"]
        if not callable(candidate):
            raise TypeError
        _REQUEST_INJECTOR = candidate
    except (OSError, StopIteration, SyntaxError, TypeError, KeyError) as error:
        raise EvalError("request-local injector is unavailable") from error
    return _REQUEST_INJECTOR(body, note)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def load_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvalError("fixture is not readable JSON") from error
    validate_fixture(value)
    if path.resolve() == FIXTURE_PATH.resolve() and hashlib.sha256(canonical_bytes(value)).hexdigest() != FIXTURE_SHA256:
        raise EvalError("canonical fixture digest does not match the pinned suite")
    return value


def expected_selection_reason(kind: str, selected: str | None, *, ambient_noise: bool = False) -> str:
    if selected is None:
        return "ambient_noise" if ambient_noise else "no_reply_observed"
    if kind == "callback_hit":
        return "callback_relevance"
    if kind == "donation_received":
        return "donation_acknowledgement"
    if kind in {"safety_override", "chat_concern"}:
        return "safety_priority"
    if kind in {"game_failure", "game_success", "topic_open"}:
        return "screen_reaction"
    return "reply_to_prior"


def validate_fixture(fixture: Any) -> None:
    if not isinstance(fixture, dict) or set(fixture) != FIXTURE_KEYS or fixture.get("schema_version") != FIXTURE_SCHEMA_VERSION or fixture.get("synthetic_only") is not True:
        raise EvalError("fixture has an invalid closed schema")
    scenarios = fixture["scenarios"]
    if not isinstance(scenarios, list) or len(scenarios) != 6:
        raise EvalError("fixture must contain exactly six scenarios")
    if tuple(item.get("id") if isinstance(item, dict) else None for item in scenarios) != SCENARIO_IDS:
        raise EvalError("fixture scenario manifest is not canonical")
    reducer, seen = _affect(), set()
    fixture_text_parts: list[str] = []
    all_prior: set[str] = set()
    all_screens: set[str] = set()
    all_selected: set[str] = set()
    for scenario in scenarios:
        if (
            not isinstance(scenario, dict)
            or set(scenario) != SCENARIO_KEYS
            or scenario.get("synthetic_only") is not True
            or scenario.get("id") not in SCENARIO_IDS
            or scenario.get("title") != SCENARIO_TITLES.get(scenario.get("id"))
            or not _valid_korean_text(scenario.get("title"))
            or len(scenario["title"]) > 80
        ):
            raise EvalError("scenario has an invalid closed schema")
        turns = scenario.get("turns")
        if not isinstance(turns, list) or len(turns) != 24:
            raise EvalError("each scenario must contain exactly 24 turns")
        state = reducer.initial_state()
        for index, turn in enumerate(turns):
            if not isinstance(turn, dict) or set(turn) != TURN_KEYS or turn.get("synthetic_only") is not True:
                raise EvalError("turn has an invalid closed schema")
            if turn.get("id") != f"{scenario['id']}-{index + 1:02d}" or turn["id"] in seen:
                raise EvalError("turn IDs must be ordered and unique")
            seen.add(turn["id"])
            if not _valid_korean_text(turn["prior_airi"]) or not isinstance(turn["selection_reason"], str) or len(turn["prior_airi"]) > MAX_TEXT:
                raise EvalError("turn text metadata must be bounded")
            if turn["prior_airi"] in all_prior:
                raise EvalError("AIRI history lines must be independently authored")
            all_prior.add(turn["prior_airi"])
            fixture_text_parts.append(turn["prior_airi"])
            if not isinstance(turn["context"], dict) or set(turn["context"]) != {"screen", "topic"} or not all(isinstance(turn["context"][key], str) and len(turn["context"][key]) <= 120 for key in ("screen", "topic")):
                raise EvalError("context must be bounded")
            if not all(_valid_korean_text(turn["context"][key]) for key in ("screen", "topic")):
                raise EvalError("context must contain Korean text without placeholders")
            if turn["context"]["topic"] != SCENARIO_TOPICS[scenario["id"]][index // 6]:
                raise EvalError("scenario topic progression is not canonical")
            if turn["context"]["screen"] == turn["prior_airi"] or turn["context"]["screen"] in all_screens:
                raise EvalError("screen context must be independent from spoken history")
            all_screens.add(turn["context"]["screen"])
            fixture_text_parts.extend(turn["context"].values())
            if not isinstance(turn["chat_batch"], list) or len(turn["chat_batch"]) > 3 or not all(isinstance(item, str) and len(item) <= 160 for item in turn["chat_batch"]):
                raise EvalError("chat batch is invalid")
            if not all(_valid_korean_text(item) for item in turn["chat_batch"]):
                raise EvalError("chat batch must contain Korean text without placeholders")
            fixture_text_parts.extend(turn["chat_batch"])
            if turn["selected_message"] is not None and (not isinstance(turn["selected_message"], str) or turn["selected_message"] not in turn["chat_batch"]):
                raise EvalError("selected message must be from the batch")
            if turn["selected_message"] is not None and not _valid_korean_text(turn["selected_message"]):
                raise EvalError("selected message must contain Korean text without placeholders")
            if turn["selected_message"] is not None:
                if turn["selected_message"] in {turn["prior_airi"], turn["context"]["screen"]}:
                    raise EvalError("viewer chat must be independent from AIRI and screen text")
                if turn["selected_message"] in all_selected:
                    raise EvalError("selected chat must be independently authored")
                all_selected.add(turn["selected_message"])
            if turn["selected_message"] is None and turn["chat_batch"]:
                raise EvalError("no selected message requires an empty batch")
            if not isinstance(turn["events"], list) or len(turn["events"]) != 1:
                raise EvalError("turn must carry exactly one affect event")
            if not isinstance(turn["events"][0], dict) or not isinstance(turn["events"][0].get("kind"), str):
                raise EvalError("turn event must be a typed object")
            if (
                turn["selection_reason"] not in SELECTION_REASONS
                or turn["selection_reason"]
                != expected_selection_reason(
                    turn["events"][0]["kind"], turn["selected_message"],
                    ambient_noise=index + 1 in AMBIENT_NOISE_TURNS.get(scenario["id"], ()),
                )
            ):
                raise EvalError("selection reason does not match selected message")
            if turn["events"][0].get("kind") != SCENARIO_EVENT_ARCS[scenario["id"]][index]:
                raise EvalError("scenario event arc is not canonical")
            try:
                for event in turn["events"]:
                    reducer.validate_event(event)
                    if event["turn_index"] != index:
                        raise EvalError("event turn index is not canonical")
                    state = reducer.reduce_affect(state, event)
                if reducer.validate_state(turn["expected_state"]) != state:
                    raise EvalError("fixture expected state differs from reducer")
            except reducer.AffectValidationError as error:
                raise EvalError("fixture affect event or state is invalid") from error
            traits = turn["allowed_traits"], turn["forbidden_traits"]
            if not all(isinstance(part, list) and part and len(part) == len(set(part)) and set(part) <= TRAITS for part in traits) or set(traits[0]) & set(traits[1]):
                raise EvalError("response traits are invalid")
            expected_traits = PRIMARY_RESPONSE_TRAITS[state["primary"]]
            if tuple(traits[0]) != expected_traits[0] or tuple(traits[1]) != expected_traits[1]:
                raise EvalError("response traits do not match the reducer state")
        selected_count = sum(turn["selected_message"] is not None for turn in turns)
        if selected_count < 18:
            raise EvalError("scenario requires at least eighteen distinct viewer selections")
        if tuple(index + 1 for index, turn in enumerate(turns) if turn["selected_message"] is None) != NO_RESPONSE_TURNS[scenario["id"]]:
            raise EvalError("scenario no-response milestones are not canonical")
    if len(seen) != 144:
        raise EvalError("fixture must contain exactly 144 turns")
    if sum(sum("\uac00" <= char <= "\ud7a3" for char in part) for part in fixture_text_parts) < 1000:
        raise EvalError("fixture does not contain meaningful Korean text")


def run_reducer_oracle(fixture: dict[str, Any]) -> dict[str, Any]:
    validate_fixture(fixture)
    distributions: dict[str, int] = {}
    no_response = 0
    ambient_noise = 0
    for scenario in fixture["scenarios"]:
        for turn in scenario["turns"]:
            if not turn["chat_batch"]:
                no_response += 1
            if turn["selection_reason"] == "ambient_noise":
                ambient_noise += 1
            for event in turn["events"]:
                distributions[event["kind"]] = distributions.get(event["kind"], 0) + 1
    return {"exact_pass": True, "distribution": distributions, "no_response_count": no_response, "ambient_noise_count": ambient_noise}


def ensure_loopback(endpoint: str) -> str:
    try:
        parsed = urlparse(endpoint)
        port = parsed.port
    except (TypeError, ValueError) as error:
        raise EvalError("execute endpoint must be literal http://127.0.0.1:11435/api/chat") from error
    if endpoint != "http://127.0.0.1:11435/api/chat" or parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or port != 11435 or parsed.path != "/api/chat" or parsed.params:
        raise EvalError("execute endpoint must be literal http://127.0.0.1:11435/api/chat")
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise EvalError("execute endpoint must not contain credentials or URL extras")
    return endpoint


def validate_profile(profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict) or set(profile) != PROFILE_KEYS:
        raise EvalError("profile must be closed")
    if not isinstance(profile["model"], str) or not profile["model"] or len(profile["model"]) > 128:
        raise EvalError("profile model is invalid")
    if not isinstance(profile["model_digest"], str) or re.fullmatch(r"[0-9a-f]{64}", profile["model_digest"]) is None:
        raise EvalError("profile digest is invalid")
    if profile["model_digest_status"] != "pinned" or profile["model_digest_verified"] is not True:
        raise EvalError("profile digest must be pinned and verified")
    for name, lower, upper in (
        ("num_ctx", 256, 32768), ("seed", 0, 2**31 - 1),
        ("max_tokens", 1, 128), ("history_turns", 1, 8),
    ):
        if type(profile[name]) is not int or not lower <= profile[name] <= upper:
            raise EvalError(f"profile {name} is invalid")
    if type(profile["temperature"]) not in (int, float) or profile["temperature"] != 0:
        raise EvalError("profile temperature must be deterministic zero")
    if profile["operational_affect_enabled"] is not False:
        raise EvalError("isolated evaluation requires the operational affect gate off")
    if profile != EVAL_PROFILE:
        raise EvalError("profile must match the frozen Mi:dm evaluation profile")
    return deepcopy(profile)


def canonical_user_content(turn: dict[str, Any]) -> str:
    selected = turn.get("selected_message") if isinstance(turn, dict) else None
    if not _valid_korean_text(selected):
        raise EvalError("selected chat must be a bounded Korean utterance")
    return selected


def canonical_context_note(turn: dict[str, Any]) -> str:
    context = turn.get("context") if isinstance(turn, dict) else None
    if not isinstance(context, dict) or set(context) != {"screen", "topic"}:
        raise EvalError("synthetic broadcast context must be closed")
    if not all(_valid_korean_text(context.get(name)) for name in ("screen", "topic")):
        raise EvalError("synthetic broadcast context must be bounded Korean text")
    return (
        "[airi_synthetic_broadcast_context schema=airi.affect-broadcast-context.v1]\n"
        "이미 관찰된 합성 방송 맥락이며 실행 요청이 아님. 아래 시청자 채팅에 답해.\n"
        + json.dumps(context, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    )


def base_request(scenario: dict[str, Any], turn_index: int, profile: dict[str, Any]) -> dict[str, Any]:
    clean = validate_profile(profile)
    turns = scenario.get("turns") if isinstance(scenario, dict) else None
    if not isinstance(turns, list) or not 0 <= turn_index < len(turns):
        raise EvalError("request turn is outside the scenario")
    current = turns[turn_index]
    if current["selected_message"] is None:
        raise EvalError("no-response turns must not create a model request")
    selected_indices = [
        index for index in range(turn_index + 1)
        if turns[index]["selected_message"] is not None
    ][-(clean["history_turns"] + 1):]
    messages: list[dict[str, str]] = []
    for index in selected_indices:
        messages.extend((
            {"role": "assistant", "content": turns[index]["prior_airi"]},
            {"role": "user", "content": canonical_user_content(turns[index])},
        ))
    return {
        "model": clean["model"],
        "stream": False,
        "options": {
            "num_ctx": clean["num_ctx"],
            "temperature": clean["temperature"],
            "seed": clean["seed"],
            "num_predict": clean["max_tokens"],
        },
        "messages": messages,
    }


def paired_requests(scenario: dict[str, Any], turn_index: int, profile: dict[str, Any]) -> tuple[bytes, bytes]:
    turn = scenario["turns"][turn_index]
    off = _inject_request_local_system_note(
        canonical_bytes(base_request(scenario, turn_index, profile)),
        canonical_context_note(turn),
    )
    on = _inject_request_local_system_note(
        off, _affect().render_continuity_snapshot(turn["expected_state"])
    )
    return off, on


def _assert_pair_only_note(off: bytes, on: bytes) -> None:
    try:
        off_value, on_value = json.loads(off), json.loads(on)
        off_notes = [
            (index, message) for index, message in enumerate(off_value["messages"])
            if isinstance(message, dict)
            and message.get("role") == "system"
            and message.get("name") == "airi_request_local"
        ]
        on_notes = [
            (index, message) for index, message in enumerate(on_value["messages"])
            if isinstance(message, dict)
            and message.get("role") == "system"
            and message.get("name") == "airi_request_local"
        ]
        if len(off_notes) != 1 or len(on_notes) != 1:
            raise EvalError("paired requests must contain one coalesced local note")
        off_index, off_note = off_notes[0]
        on_index, on_note = on_notes[0]
        off_content = off_note.get("content")
        on_content = on_note.get("content")
        if (
            off_index != on_index
            or not isinstance(off_content, str)
            or not isinstance(on_content, str)
            or not on_content.startswith(off_content + "\n\n[airi_affect_continuity ")
        ):
            raise EvalError("ON request must append only the affect note")
        on_note["content"] = off_content
        if canonical_bytes(off_value) != canonical_bytes(on_value):
            raise EvalError("paired requests differ outside the affect note")
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise EvalError("paired request is malformed") from error


def _health_url(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    return urlunparse((parsed.scheme, parsed.netloc, "/health", "", "", ""))


def _transport_result(value: Any, purpose: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"http_status", "json"}:
        raise EvalError(f"{purpose} transport result is malformed")
    if type(value["http_status"]) is not int or value["http_status"] != 200 or not isinstance(value["json"], dict):
        raise EvalError(f"{purpose} transport did not return a successful JSON response")
    return value["json"]


def _health_profile(payload: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    chat_model = payload.get("chat_model")
    digest = chat_model.get("digest") if isinstance(chat_model, dict) else None
    affect = payload.get("affect_continuity")
    if (
        payload.get("status") != "ok"
        or type(payload.get("num_ctx")) is not int
        or payload["num_ctx"] != profile["num_ctx"]
        or not isinstance(chat_model, dict)
        or chat_model.get("model") != profile["model"]
        or not isinstance(digest, dict)
        or digest.get("digest") != profile["model_digest"]
        or digest.get("status") != profile["model_digest_status"]
        or digest.get("verified") is not profile["model_digest_verified"]
        or not isinstance(affect, dict)
        or affect.get("enabled") is not profile["operational_affect_enabled"]
        or affect.get("ready") is not False
        or affect.get("mode") != "typed-snapshot-v1"
        or affect.get("schema_version") != "airi.affect-state.v1"
        or affect.get("prompt_cap_bytes") != 384
    ):
        raise EvalError("loopback health does not match the frozen isolated profile")
    return _expected_health_profile(profile)


def _expected_health_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": profile["model"],
        "model_digest": profile["model_digest"],
        "model_digest_status": profile["model_digest_status"],
        "model_digest_verified": profile["model_digest_verified"],
        "num_ctx": profile["num_ctx"],
        "operational_affect_enabled": profile["operational_affect_enabled"],
        "operational_affect_ready": False,
        "affect_mode": "typed-snapshot-v1",
        "affect_schema_version": "airi.affect-state.v1",
        "affect_prompt_cap_bytes": 384,
    }


def _response_content(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if (
        not isinstance(message, dict)
        or message.get("role") != "assistant"
        or not isinstance(content, str)
        or not 1 <= len(content) <= MAX_RESPONSE_CHARS
        or content != content.strip()
        or any(unicodedata.category(char) == "Cc" and char != "\n" for char in content)
    ):
        raise EvalError("model response must be a bounded nonempty assistant string")
    return content


def execute(
    fixture: dict[str, Any], endpoint: str, profile: dict[str, Any],
    transport: Callable[[str, str, bytes | None, dict[str, str]], Any],
) -> dict[str, Any]:
    validate_fixture(fixture)
    ensure_loopback(endpoint)
    clean_profile = validate_profile(profile)
    health_url = _health_url(endpoint)
    before = _health_profile(
        _transport_result(transport("GET", health_url, None, {}), "health"),
        clean_profile,
    )
    private_responses: list[dict[str, str]] = []
    response_chars = {"off": 0, "on": 0}
    for scenario in fixture["scenarios"]:
        for turn_index, turn in enumerate(scenario["turns"]):
            if turn["selected_message"] is None:
                continue
            off_body, on_body = paired_requests(scenario, turn_index, clean_profile)
            _assert_pair_only_note(off_body, on_body)
            responses: dict[str, str] = {}
            for arm, body in (("off", off_body), ("on", on_body)):
                payload = _transport_result(
                    transport(
                        "POST", endpoint, body,
                        {"x-airi-turn-origin": "local-evaluation"},
                    ),
                    f"{arm} model",
                )
                responses[arm] = _response_content(payload)
                response_chars[arm] += len(responses[arm])
            private_responses.append({
                "scenario_id": scenario["id"],
                "turn_id": turn["id"],
                "off": responses["off"],
                "on": responses["on"],
            })
    after = _health_profile(
        _transport_result(transport("GET", health_url, None, {}), "health"),
        clean_profile,
    )
    if before != after:
        raise EvalError("loopback profile changed during paired execution")
    selected_count = len(private_responses)
    return {
        "status": "paired_transport_complete",
        "selected_turn_count": selected_count,
        "model_call_count": selected_count * 2,
        "response_count_by_arm": {"off": selected_count, "on": selected_count},
        "response_char_count_by_arm": response_chars,
        "health_profile_sha256": hashlib.sha256(canonical_bytes(before)).hexdigest(),
        "private_responses": private_responses,
    }


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise EvalError("loopback redirects are forbidden")


def make_local_transport(endpoint: str, *, request_timeout: float, overall_timeout: float) -> Callable[[str, str, bytes | None, dict[str, str]], dict[str, Any]]:
    """Return the deliberately narrow, proxy-free transport used by the opt-in CLI."""
    ensure_loopback(endpoint)
    if not 0 < request_timeout <= 60 or not request_timeout <= overall_timeout <= 7200:
        raise EvalError("execution timeouts are out of range")
    deadline = time.monotonic() + overall_timeout
    opener = urlrequest.build_opener(urlrequest.ProxyHandler({}), _NoRedirect())

    def transport(method: str, url: str, body: bytes | None, headers: dict[str, str]) -> dict[str, Any]:
        health_url = _health_url(endpoint)
        if (method, url) not in {("GET", health_url), ("POST", endpoint)}:
            raise EvalError("local transport URL is not permitted")
        if method == "GET" and (body is not None or headers != {}):
            raise EvalError("health transport contract is not permitted")
        if method == "POST" and (
            not isinstance(body, bytes)
            or not body
            or headers != {"x-airi-turn-origin": "local-evaluation"}
        ):
            raise EvalError("model transport contract is not permitted")
        if time.monotonic() >= deadline:
            raise EvalError("execution deadline exceeded")
        if body is not None and (not isinstance(body, bytes) or len(body) > MAX_REQUEST_BYTES):
            raise EvalError("request body exceeds the local execution limit")
        request_headers = dict(headers)
        if method == "POST":
            request_headers["Content-Type"] = "application/json"
        request = urlrequest.Request(url, data=body, headers=request_headers, method=method)
        timeout = min(request_timeout, max(0.001, deadline - time.monotonic()))
        try:
            with opener.open(request, timeout=timeout) as response:
                content_type = response.headers.get_content_type()
                if content_type != "application/json":
                    raise EvalError("local endpoint did not return JSON")
                chunks: list[bytes] = []
                total = 0
                while True:
                    if time.monotonic() >= deadline:
                        raise EvalError("execution deadline exceeded")
                    chunk = response.read(min(8192, MAX_HTTP_BODY_BYTES + 1 - total))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_HTTP_BODY_BYTES:
                        raise EvalError("local endpoint response exceeds the execution limit")
                    chunks.append(chunk)
                    if time.monotonic() >= deadline:
                        raise EvalError("execution deadline exceeded")
                data = b"".join(chunks)
                status = response.getcode()
        except EvalError:
            raise
        except (urlerror.URLError, urlerror.HTTPError, socket.timeout, TimeoutError, OSError) as error:
            raise EvalError("local endpoint request failed") from error
        if time.monotonic() > deadline:
            raise EvalError("execution deadline exceeded")
        try:
            parsed = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EvalError("local endpoint returned malformed JSON") from error
        if not isinstance(parsed, dict):
            raise EvalError("local endpoint returned a non-object JSON response")
        return {"http_status": status, "json": parsed}

    return transport


def _validate_execution(fixture: dict[str, Any], execution: Any, profile: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(execution, dict) or set(execution) != EXECUTION_KEYS or execution.get("status") != "paired_transport_complete":
        raise EvalError("execution evidence is malformed")
    selected_ids = [
        (scenario["id"], turn["id"])
        for scenario in fixture["scenarios"]
        for turn in scenario["turns"]
        if turn["selected_message"] is not None
    ]
    selected_count = len(selected_ids)
    if type(execution["selected_turn_count"]) is not int or execution["selected_turn_count"] != selected_count:
        raise EvalError("execution selected-turn count is inconsistent")
    if type(execution["model_call_count"]) is not int or execution["model_call_count"] != selected_count * 2:
        raise EvalError("execution model-call count is inconsistent")
    for name in ("response_count_by_arm", "response_char_count_by_arm"):
        value = execution[name]
        if not isinstance(value, dict) or set(value) != {"off", "on"} or any(type(item) is not int or item < 0 for item in value.values()):
            raise EvalError(f"execution {name} is malformed")
    if execution["response_count_by_arm"] != {"off": selected_count, "on": selected_count}:
        raise EvalError("execution response counts are inconsistent")
    expected_health_sha256 = hashlib.sha256(canonical_bytes(_expected_health_profile(profile))).hexdigest()
    if execution["health_profile_sha256"] != expected_health_sha256:
        raise EvalError("execution health binding is malformed")
    rows = execution["private_responses"]
    if not isinstance(rows, list) or len(rows) != selected_count:
        raise EvalError("execution private response rows are incomplete")
    seen: list[tuple[str, str]] = []
    chars = {"off": 0, "on": 0}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"scenario_id", "turn_id", "off", "on"}:
            raise EvalError("execution private response row is malformed")
        seen.append((row["scenario_id"], row["turn_id"]))
        for arm in ("off", "on"):
            chars[arm] += len(_response_content({"message": {"role": "assistant", "content": row[arm]}}))
    if seen != selected_ids or chars != execution["response_char_count_by_arm"]:
        raise EvalError("execution response ordering or lengths are inconsistent")
    return deepcopy(execution)


def _pairing_summary(fixture: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    bases: list[str] = []
    selected_ids: list[str] = []
    for scenario in fixture["scenarios"]:
        for turn_index, turn in enumerate(scenario["turns"]):
            if turn["selected_message"] is None:
                continue
            off, on = paired_requests(scenario, turn_index, profile)
            _assert_pair_only_note(off, on)
            bases.append(hashlib.sha256(off).hexdigest())
            selected_ids.append(turn["id"])
    return {
        "exact_non_affect_identity": True,
        "paired_turn_count": len(bases),
        "canonical_base_requests_sha256": hashlib.sha256(canonical_bytes(bases)).hexdigest(),
        "selected_turn_sequence_sha256": hashlib.sha256(canonical_bytes(selected_ids)).hexdigest(),
    }


def public_report(fixture: dict[str, Any], profile: dict[str, Any], execution: dict[str, Any] | None = None) -> dict[str, Any]:
    validate_fixture(fixture)
    clean_profile = validate_profile(profile)
    oracle = run_reducer_oracle(fixture)
    pairing = _pairing_summary(fixture, clean_profile)
    coverage = {
        "scenario_count": len(fixture["scenarios"]),
        "turns_per_scenario": 24,
        "has_no_response": oracle["no_response_count"] > 0,
        "safety_arc_present": oracle["distribution"].get("safety_override", 0) > 0,
        "repair_arc_present": oracle["distribution"].get("response_repair", 0) > 0,
        "ambient_noise_present": oracle["ambient_noise_count"] > 0,
    }
    if execution is None:
        execution_public = {
            "status": "offline_no_network",
            "selected_turn_count": pairing["paired_turn_count"],
            "model_call_count": 0,
            "paired_response_count": 0,
            "response_char_count_total": 0,
            "health_profile_sha256": None,
        }
    else:
        valid_execution = _validate_execution(fixture, execution, clean_profile)
        execution_public = {
            "status": valid_execution["status"],
            "selected_turn_count": valid_execution["selected_turn_count"],
            "model_call_count": valid_execution["model_call_count"],
            "paired_response_count": valid_execution["selected_turn_count"],
            "response_char_count_total": sum(valid_execution["response_char_count_by_arm"].values()),
            "health_profile_sha256": valid_execution["health_profile_sha256"],
        }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "fixture_sha256": hashlib.sha256(canonical_bytes(fixture)).hexdigest(),
        "scenario_count": 6,
        "turn_count": 144,
        "scenario_coverage": coverage,
        "reducer_oracle_exact_pass": oracle["exact_pass"],
        "event_distribution": oracle["distribution"],
        "no_response_count": oracle["no_response_count"],
        "ambient_noise_count": oracle["ambient_noise_count"],
        "pairing": pairing,
        "pairing_profile_sha256": hashlib.sha256(canonical_bytes(clean_profile)).hexdigest(),
        "execution": execution_public,
        "character_specificity": "unscored_constitution_unapproved",
        "operational_adoption": False,
        "model_quality_labels": "human_only",
    }


def validate_arm_mapping(mapping: Any) -> dict[str, str]:
    if not isinstance(mapping, dict) or set(mapping) != {"a", "b"} or set(mapping.values()) != {"off", "on"}:
        raise EvalError("arm mapping must be an exact blinded permutation")
    return dict(mapping)


def build_private_review_packet(fixture: dict[str, Any], execution: dict[str, Any], arm_mapping: dict[str, str]) -> dict[str, Any]:
    """Build a pure, caller-custodied packet with deliberately blind arm labels."""
    validate_fixture(fixture)
    clean = _validate_execution(fixture, execution, EVAL_PROFILE)
    mapping = validate_arm_mapping(arm_mapping)
    responses = {
        (row["scenario_id"], row["turn_id"]): row
        for row in clean["private_responses"]
    }
    rows: list[dict[str, Any]] = []
    for scenario in fixture["scenarios"]:
        for turn in scenario["turns"]:
            if turn["selected_message"] is None:
                continue
            response = responses[(scenario["id"], turn["id"])]
            rows.append({
                "scenario_id": scenario["id"],
                "turn_id": turn["id"],
                "prior_airi": turn["prior_airi"],
                "context": deepcopy(turn["context"]),
                "selected_message": turn["selected_message"],
                "expected_state": deepcopy(turn["expected_state"]),
                "response_a": response[mapping["a"]],
                "response_b": response[mapping["b"]],
                "review": {
                    "causal_expression": None,
                    "continuity": None,
                    "positivity_collapse": None,
                    "repair": None,
                    "safety_privacy": None,
                    "notes": None,
                },
            })
    return {
        "schema_version": "airi.affect-broadcast-private-review.v1",
        "local_only": True,
        "synthetic_only": True,
        "human_review_required": True,
        "arm_labels_blinded": True,
        "rows": rows,
    }


def build_private_arm_key(arm_mapping: dict[str, str]) -> dict[str, Any]:
    return {
        "schema_version": "airi.affect-broadcast-private-arm-key.v1",
        "local_only": True,
        "arm_mapping": validate_arm_mapping(arm_mapping),
    }


def reserve_local_run(output_dir: Path) -> dict[str, Path]:
    base = LOCAL_RESULTS_DIR.resolve()
    candidate = output_dir.resolve()
    if (
        candidate.parent != base
        or not SAFE_RUN_BASENAME.fullmatch(candidate.name)
        or candidate.name.upper() in WINDOWS_RESERVED_BASENAMES
    ):
        raise EvalError("output directory must be a direct child of local-results")
    LOCAL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_OPERATOR_KEYS_DIR.mkdir(parents=True, exist_ok=True)
    key_target = LOCAL_OPERATOR_KEYS_DIR.resolve() / (candidate.name + ".json")
    for path in (LOCAL_RESULTS_DIR, LOCAL_OPERATOR_KEYS_DIR, candidate, key_target):
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise EvalError("output path must not contain a reparse point")
    if candidate.exists() or key_target.exists():
        raise EvalError("output directory must be fresh")
    # The deterministic sibling is both the staging directory and the
    # exclusive run-name lock. A second honest runner cannot spend 244 model
    # calls for the same target while this reservation exists.
    reservation = base / (".reservation-" + candidate.name)
    if reservation.exists():
        raise EvalError("unable to reserve fresh output staging directory")
    reservation.mkdir()
    return {"target": candidate, "key_target": key_target, "stage": reservation}


def abort_local_run(reservation: dict[str, Path]) -> None:
    stage = reservation["stage"]
    for name in (*MAX_ARTIFACT_BYTES, "private-arm-key.json"):
        try:
            (stage / name).unlink()
        except OSError:
            pass
    try:
        stage.rmdir()
    except OSError:
        pass


def publish_local_run(reservation: dict[str, Path], report: dict[str, Any], packet: dict[str, Any], arm_key: dict[str, Any]) -> Path:
    """Atomically publish complete local artifacts; the receipt is integrity, not authenticity."""
    target, stage, key_target = reservation["target"], reservation["stage"], reservation["key_target"]
    encoded = {
        "public-report.json": canonical_bytes(report),
        "private-review-packet.json": canonical_bytes(packet),
    }
    key_bytes = canonical_bytes(arm_key)
    receipt = {
        "schema_version": "airi.affect-broadcast-local-run-receipt.v1",
        "local_only": True,
        "integrity_scope": "canonical_sha256_of_report_and_blinded_review_packet",
        "authenticity_claim": "none_hostile_local_environment_not_addressed",
        # The two possible arm-key encodings are trivially enumerable.  Do not
        # publish its digest, or the receipt itself would unblind the packet.
        "artifact_sha256": {
            name: hashlib.sha256(value).hexdigest()
            for name, value in encoded.items()
            if name != "private-arm-key.json"
        },
        "private_arm_key_custody": "separate_operator_only_not_receipt_bound",
    }
    encoded["local-run-receipt.json"] = canonical_bytes(receipt)
    if len(key_bytes) > 8 * 1024 or any(len(value) > MAX_ARTIFACT_BYTES[name] for name, value in encoded.items()):
        abort_local_run(reservation)
        raise EvalError("local artifact exceeds its custody size limit")
    try:
        if not stage.is_dir() or target.exists() or key_target.exists():
            raise EvalError("local run reservation is no longer fresh")
        for name, value in encoded.items():
            path = stage / name
            with path.open("xb") as handle:
                handle.write(value)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
        # Stage the operator-only key inside the reserved directory. Moving it
        # out before the review directory is published keeps the two custody
        # roots separate without leaving a second untracked staging pathname.
        key_stage = stage / "private-arm-key.json"
        with key_stage.open("xb") as handle:
            handle.write(key_bytes)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        os.rename(key_stage, key_target)
        try:
            os.rename(stage, target)
        except FileExistsError as error:
            try:
                key_target.unlink()
            except OSError:
                pass
            raise EvalError("output directory must be fresh") from error
    except Exception:
        try:
            key_target.unlink()
        except OSError:
            pass
        abort_local_run(reservation)
        raise
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11435/api/chat")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--request-timeout", type=float, default=15.0)
    parser.add_argument("--overall-timeout", type=float, default=7200.0)
    args = parser.parse_args()
    fixture = load_fixture(args.fixture)
    if args.execute:
        ensure_loopback(args.endpoint)
        if args.output_dir is None:
            raise EvalError("--execute requires an explicit --output-dir")
        reservation = reserve_local_run(args.output_dir)
        try:
            transport = make_local_transport(args.endpoint, request_timeout=args.request_timeout, overall_timeout=args.overall_timeout)
            execution = execute(fixture, args.endpoint, EVAL_PROFILE, transport)
            mapping = {"a": "off", "b": "on"} if secrets.randbelow(2) == 0 else {"a": "on", "b": "off"}
            report = public_report(fixture, EVAL_PROFILE, execution)
            packet = build_private_review_packet(fixture, execution, mapping)
            arm_key = build_private_arm_key(mapping)
            publish_local_run(reservation, report, packet, arm_key)
        except Exception:
            abort_local_run(reservation)
            raise
        print(json.dumps({"status": "published", "model_call_count": execution["model_call_count"], "selected_turn_count": execution["selected_turn_count"]}, sort_keys=True))
        return 0
    print(json.dumps(public_report(fixture, EVAL_PROFILE), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
