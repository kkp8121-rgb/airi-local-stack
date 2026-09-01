"""Offline contract tests for the evaluation-only llama-server shim.

Every case is deterministic and runs without a network, without Ollama and
without llama-server: the shim's wire contract is pure translation, so it is
tested as pure translation.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from llama_server_shim import (
    create_app,
    ollama_final_line,
    ollama_request_to_openai,
    openai_delta_to_ollama_line,
    openai_finish_reason,
    openai_usage,
    parse_openai_sse_line,
)


# Captured from the live proxy -> Ollama hop on the pinned model.
MEASURED_OLLAMA_REQUEST = {
    "model": "midm-airi:2.0-mini",
    "messages": [
        {"role": "system", "content": "너는 아이리다. 반말로 한 문장만 말해."},
        {"role": "user", "content": "안녕? 오늘 방송 뭐 해?"},
    ],
    "stream": True,
    "keep_alive": "30m",
    "options": {
        "temperature": 0.45,
        "top_p": 0.9,
        "repeat_penalty": 1.05,
        "num_predict": 160,
        "seed": 7,
        "stop": ["<|endofturn|>"],
        "num_ctx": 4096,
        "num_gpu": 999,
    },
}

MEASURED_DELTA_KEYS = {"model", "created_at", "message", "done"}
MEASURED_FINAL_KEYS = {
    "model",
    "created_at",
    "message",
    "done",
    "done_reason",
    "total_duration",
    "load_duration",
    "prompt_eval_count",
    "prompt_eval_duration",
    "eval_count",
    "eval_duration",
}
MEASURED_DURATIONS = {
    "total_duration": 880148600,
    "load_duration": 185228700,
    "prompt_eval_duration": 71264000,
    "eval_duration": 611038000,
}


def test_ollama_request_to_openai_maps_generation_options() -> None:
    request = ollama_request_to_openai(MEASURED_OLLAMA_REQUEST)

    assert request["model"] == "midm-airi:2.0-mini"
    assert request["stream"] is True
    assert request["max_tokens"] == 160
    assert request["temperature"] == 0.45
    assert request["seed"] == 7
    assert request["stop"] == ["<|endofturn|>"]


def test_ollama_request_to_openai_drops_server_side_options() -> None:
    request = ollama_request_to_openai(MEASURED_OLLAMA_REQUEST)

    assert "num_ctx" not in request
    assert "num_gpu" not in request
    assert "options" not in request
    assert "num_predict" not in request
    assert "keep_alive" not in request


def test_ollama_request_to_openai_preserves_messages() -> None:
    request = ollama_request_to_openai(MEASURED_OLLAMA_REQUEST)

    assert request["messages"] == MEASURED_OLLAMA_REQUEST["messages"]


def test_ollama_request_to_openai_omits_max_tokens_without_num_predict() -> None:
    payload = {"model": "m", "messages": [], "options": {"temperature": 0.2}}

    assert "max_tokens" not in ollama_request_to_openai(payload)


def test_ollama_request_to_openai_omits_max_tokens_for_negative_num_predict() -> None:
    payload = {"model": "m", "messages": [], "options": {"num_predict": -1}}

    assert "max_tokens" not in ollama_request_to_openai(payload)


def test_ollama_request_to_openai_normalizes_string_stop() -> None:
    payload = {"model": "m", "messages": [], "options": {"stop": "<|endofturn|>"}}

    assert ollama_request_to_openai(payload)["stop"] == ["<|endofturn|>"]


def test_ollama_request_to_openai_defaults_stream_to_true() -> None:
    request = ollama_request_to_openai({"model": "m", "messages": []})

    assert request["stream"] is True
    assert ollama_request_to_openai({"model": "m", "messages": [], "stream": False})["stream"] is False


def test_parse_openai_sse_line_returns_delta_content() -> None:
    line = 'data: {"choices":[{"delta":{"content":"가"}}]}'

    assert parse_openai_sse_line(line) == "가"


def test_parse_openai_sse_line_ignores_terminator_and_blank_lines() -> None:
    assert parse_openai_sse_line("data: [DONE]") is None
    assert parse_openai_sse_line("") is None
    assert parse_openai_sse_line("   ") is None
    assert parse_openai_sse_line(": keep-alive") is None


def test_parse_openai_sse_line_ignores_delta_without_content() -> None:
    assert parse_openai_sse_line('data: {"choices":[{"delta":{"role":"assistant"}}]}') is None
    assert parse_openai_sse_line('data: {"choices":[{"delta":{"content":null}}]}') is None
    assert parse_openai_sse_line('data: {"choices":[]}') is None
    assert parse_openai_sse_line("data: not-json") is None


def test_openai_finish_reason_reads_the_whole_payload() -> None:
    # The buffered relay hands the completion body, not the bare choice, so the
    # reason must be read one level down from "choices".
    payload = {"choices": [{"message": {"content": "가"}, "finish_reason": "length"}]}

    assert openai_finish_reason(payload) == "length"
    assert openai_finish_reason({"choices": [{"finish_reason": None}]}) == ""
    assert openai_finish_reason({"finish_reason": "length"}) == ""


def test_openai_usage_reads_prompt_and_completion_tokens() -> None:
    payload = {"usage": {"prompt_tokens": 516, "completion_tokens": 10, "total_tokens": 526}}

    assert openai_usage(payload) == {"prompt_tokens": 516, "completion_tokens": 10}
    assert openai_usage({"choices": []}) == {}


def test_openai_delta_to_ollama_line_matches_measured_schema() -> None:
    line = openai_delta_to_ollama_line(
        "midm-airi:2.0-mini", "안녕하세요", "2026-09-01T01:12:36.491754Z"
    )

    assert set(line) == MEASURED_DELTA_KEYS
    assert line["model"] == "midm-airi:2.0-mini"
    assert line["created_at"] == "2026-09-01T01:12:36.491754Z"
    assert line["message"] == {"role": "assistant", "content": "안녕하세요"}
    assert line["done"] is False


def test_ollama_final_line_matches_measured_schema() -> None:
    line = ollama_final_line(
        "midm-airi:2.0-mini",
        "2026-09-01T01:12:36.491754Z",
        {"prompt_tokens": 516, "completion_tokens": 10},
        MEASURED_DURATIONS,
    )

    assert set(line) == MEASURED_FINAL_KEYS
    assert line["done"] is True
    assert line["done_reason"] == "stop"
    assert line["message"] == {"role": "assistant", "content": ""}
    assert line["prompt_eval_count"] == 516
    assert line["eval_count"] == 10
    for key, expected in MEASURED_DURATIONS.items():
        assert line[key] == expected
        assert type(line[key]) is int


def test_ollama_final_line_coerces_durations_and_counts_to_int() -> None:
    line = ollama_final_line(
        "m",
        "2026-09-01T01:12:36.491754Z",
        {"prompt_tokens": 7.9, "completion_tokens": None},
        {"total_duration": 1234.7},
        "length",
    )

    assert set(line) == MEASURED_FINAL_KEYS
    assert line["done_reason"] == "length"
    assert type(line["total_duration"]) is int
    assert line["total_duration"] == 1234
    assert type(line["prompt_eval_count"]) is int
    assert line["prompt_eval_count"] == 7
    assert line["eval_count"] == 0
    assert line["load_duration"] == 0


def test_round_trip_keeps_messages_byte_identical() -> None:
    original = json.dumps(
        MEASURED_OLLAMA_REQUEST["messages"], ensure_ascii=False, sort_keys=True
    ).encode("utf-8")

    converted = ollama_request_to_openai(json.loads(json.dumps(MEASURED_OLLAMA_REQUEST)))
    round_tripped = json.dumps(
        converted["messages"], ensure_ascii=False, sort_keys=True
    ).encode("utf-8")

    assert round_tripped == original


def test_api_tags_returns_the_configured_model_and_digest() -> None:
    digest = "106cfaacc185aec489ccbddd82894d6558aac745444b844a73cef4ea450e9f6c"
    app = create_app(
        llama_server="http://127.0.0.1:11500",
        model="midm-airi:2.0-mini",
        digest=digest,
        timeout=1.0,
    )

    response = TestClient(app).get("/api/tags")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["models"], list) and len(payload["models"]) == 1
    entry = payload["models"][0]
    assert entry["name"] == "midm-airi:2.0-mini"
    assert entry["model"] == "midm-airi:2.0-mini"
    assert entry["digest"] == digest
    assert type(entry["size"]) is int and entry["size"] > 0
    assert entry["modified_at"].endswith("Z")


def test_sampling_is_relayed_so_only_logit_bias_differs():
    # The proxy injects OLLAMA_SAMPLING_DEFAULTS (temperature, top_p,
    # repeat_penalty) into every request. Dropping any of them would make the
    # Stage 2 run differ from run-89 by more than the token suppression, so
    # each must reach llama-server.
    request = ollama_request_to_openai(MEASURED_OLLAMA_REQUEST)
    assert request["temperature"] == 0.45
    assert request["top_p"] == 0.9
    assert request["repeat_penalty"] == 1.05
    # Absent values must stay absent rather than inventing a default.
    bare = ollama_request_to_openai(
        {"model": "m", "messages": [], "options": {"temperature": 0.2}}
    )
    assert "top_p" not in bare
    assert "repeat_penalty" not in bare
