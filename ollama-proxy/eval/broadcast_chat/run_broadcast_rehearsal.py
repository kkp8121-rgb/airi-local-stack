"""AIRI 멀티턴 방송 리허설 러너 — 단발 Q→A가 못 재는 '흐름' 축을 잰다.

`run_broadcast_chat_ab.py` 는 채팅 1건 → 응답 1건을 독립적으로 잰다. 실제 방송은
그렇게 흐르지 않는다. 낭독→응답이 연쇄되고, 앞 화제가 뒤에서 다시 불려 나오고,
같은 취지 채팅이 몰리면 집계해서 처리하고, 후원은 문장 사이에 인라인으로 끼며,
화제는 선언 없이 미끄러진다(관찰 연구 §2 P1·P5·P6·P7, §5 차이표).

이 러너는 시나리오 하나를 턴 순서대로 돌리며 어시스턴트 응답을 히스토리에 되먹여
그 흐름을 텍스트로 근사한다. 상수·전송 계층·출력 규격 채점기는 A/B 러너에서
그대로 import 해 쓴다(사본을 만들지 않는다 = drift 원천 차단).

한계: 채팅 낭독(TTS 음성)이 없는 텍스트 시뮬레이션이다. '낭독→응답 원자화'는
텍스트 근사로만 관측되며 실제 음성 타이밍·침묵 예산을 대체하지 않는다.

사용 예:
  python run_broadcast_rehearsal.py \
      --base-url https://<host>/v1 --models midm-airi:2.0-mini \
      --output results/broadcast-rehearsal.json      # 토큰은 env AIRI_REMOTE_TOKEN

오프라인 검증:
  python run_broadcast_rehearsal.py --dry-run --output /tmp/dry-rehearsal.json
  python run_broadcast_rehearsal.py --dry-run --contract on --output /tmp/dry-contract.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Sequence

BASE_DIR = Path(__file__).resolve().parent
PROXY_DIR = BASE_DIR.parents[1]
for _path in (str(BASE_DIR), str(PROXY_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    import run_broadcast_chat_ab as ab  # noqa: E402  (경로 주입 뒤에 온다)
except ImportError as exc:  # pragma: no cover - 배치 오류 가드
    raise SystemExit(f"run_broadcast_chat_ab 모듈을 찾지 못했다 ({BASE_DIR}): {exc}") from exc

try:
    from broadcast_contract import apply_broadcast_contract  # noqa: E402
except ImportError as exc:  # pragma: no cover - 배치 오류 가드
    raise SystemExit(f"broadcast_contract 모듈을 찾지 못했다 ({PROXY_DIR}): {exc}") from exc

DEFAULT_FIXTURES = BASE_DIR / "rehearsal-fixtures.json"
SCHEMA = "airi.broadcast-rehearsal.v1"
FIXTURE_SCHEMA = "airi.broadcast-rehearsal-fixtures.v1"
CHECKPOINT_EVIDENCE_SCHEMA = "airi.broadcast-rehearsal-checkpoint-evidence.v1"

# 운영 proxy 기본값 (ollama_proxy.py 의 요청 조립부와 동일). 이 위로 올리면 방송
# 리듬과 다른 길이를 재게 되므로 경고한다.
PRODUCTION_MAX_TOKENS = 128
DEFAULT_HISTORY_TURNS = 8
WARMUP_TEXT = "안녕, 방송 시작했어?"

EVENT_TYPES = ("chat", "multi_chat", "donation", "callback_probe", "topic_shift")

MEASUREMENT_SCOPE = (
    "이 측정은 TTS 제외 — 프롬프트 전송 → 텍스트 완료까지의 순수 LLM 구간이다. "
    "비스트리밍이라 TTFT(첫 토큰 시점)는 관측하지 않는다."
)
SIMULATION_LIMIT = (
    "채팅 낭독(TTS 음성)이 없는 텍스트 시뮬레이션이다. '낭독→응답 원자화'의 텍스트 "
    "근사만 측정하며 실제 음성 타이밍·침묵 예산·오디오 베드 효과는 재지 않는다."
)
SCORING_NOTE = "자동 마커는 전부 휴리스틱이다. 인간 검수를 대체하지 않는다."

# ---------------------------------------------------------------------------
# 흐름 마커 (휴리스틱 — 인간 검수 대체 아님)
# ---------------------------------------------------------------------------
# 여론 집계: "한 문장으로 묶어 정리한 뒤 네 입장" (관찰 연구 §4 탬 사례).
# 집계 한 문장 + 입장 한 문장이 들어갈 여유로 기본 자수 상한의 2배까지 허용한다.
AGGREGATE_MAX_SENTENCES = ab.MAX_SENTENCES_OK
AGGREGATE_MAX_CHARS = ab.LENGTH_MAX * 2
# 개별 채팅을 이만큼 그대로 옮기면 집계가 아니라 나열로 본다.
AGGREGATE_ENUMERATION_MIN = 3

# 존댓말 drift: 전반/후반 각 N턴을 비교한다.
POLITENESS_WINDOW = 10

# 화제 전환 선언 — 실측 규범은 '선언 없음'이다(관찰 연구 P7·§5 차이표).
BLOCK_DECLARATION = re.compile(
    r"다음\s*(주제|화제|코너)"
    r"|(주제|화제)\s*(를|는)?\s*(바꿔|바꾸|바꿀|돌려|돌리|전환)"
    r"|이제부터\s*[^.!?]{0,14}(얘기|이야기|코너|시간)"
    r"|새로운?\s*(주제|화제|코너)"
    r"|(오늘|지금)\s*의?\s*(두|세)\s*번째\s*(주제|코너)"
)

FLOW_MARKER_ORDER = [
    "callback_hit",
    "aggregate_response",
    "donation_name_call",
    "no_name_leak",
    "topic_shift_natural",
]


def callback_hit(response: str, keywords: Sequence[str]) -> tuple[bool, list[str]]:
    """콜백 probe 응답이 seed 화제 키워드를 스스로 다시 꺼냈는가."""
    text = (response or "").strip()
    hits = [k for k in keywords if k and k in text]
    return bool(hits), hits


def aggregate_response(response: str, items: Sequence[str]) -> tuple[bool, dict[str, Any]]:
    """여론 집계형 응답인가 — 1~2문장 유지 + 개별 채팅 나열 없음."""
    text = (response or "").strip()
    sentences = ab.split_sentences(text)
    verbatim = [item for item in items if item and item in text]
    listed = bool(ab.NUMBERED_LIST.search(text))
    ok = (
        bool(text)
        and 1 <= len(sentences) <= AGGREGATE_MAX_SENTENCES
        and len(text) <= AGGREGATE_MAX_CHARS
        and not listed
        and len(verbatim) < AGGREGATE_ENUMERATION_MIN
    )
    return ok, {
        "sentence_count": len(sentences),
        "char_count": len(text),
        "verbatim_items": verbatim,
        "list_markers": listed,
    }


def name_called(response: str, name: str) -> bool:
    """후원 턴에서 후원자 닉네임을 실제로 불렀는가."""
    return bool(name) and name in (response or "")


def leaked_names(response: str, names: Sequence[str]) -> list[str]:
    """호명 정책 위반 — 그 턴의 후원자가 아닌 이름을 불렀다(관찰 연구 P6)."""
    text = response or ""
    return [name for name in names if name and name in text]


def topic_shift_natural(response: str) -> bool:
    """화제 전환을 선언 없이 받았는가."""
    text = (response or "").strip()
    return bool(text) and not BLOCK_DECLARATION.search(text)


def _violation_rate(flags: Sequence[bool]) -> float | None:
    """flags 는 banmal 마커(True=반말 유지). 위반율 = False 비율."""
    if not flags:
        return None
    return round(sum(1 for flag in flags if not flag) / len(flags), 3)


def politeness_drift(flags: Sequence[bool], window: int = POLITENESS_WINDOW) -> dict[str, Any]:
    """턴 진행에 따른 존댓말 위반율 변화 — 전반 N턴 vs 후반 N턴."""
    size = min(window, len(flags) // 2)
    if size <= 0:
        return {
            "window": 0,
            "first_violation_rate": None,
            "second_violation_rate": None,
            "drift": None,
            "note": "턴 수가 적어 전·후반 비교를 만들 수 없다",
        }
    first = _violation_rate(flags[:size])
    second = _violation_rate(flags[-size:])
    drift = None if (first is None or second is None) else round(second - first, 3)
    return {
        "window": size,
        "first_violation_rate": first,
        "second_violation_rate": second,
        "drift": drift,
        "note": "양수면 후반으로 갈수록 존댓말이 늘었다는 뜻이다",
    }


def length_variance(chars: Sequence[int]) -> dict[str, Any]:
    """가변 길이 실현 여부 — 턴별 자수 분포."""
    values = list(chars)
    low = ab.pct(values, 0.0)
    high = ab.pct(values, 1.0)
    return {
        "p50": ab.pct(values, 0.5),
        "p95": ab.pct(values, 0.95),
        "min": low,
        "max": high,
        "spread": None if (low is None or high is None) else round(high - low, 1),
        "distinct": len(set(values)),
        "n": len(values),
    }


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------
def load_rehearsal_fixtures(path: Path) -> dict[str, Any]:
    """리허설 픽스처 로드 + 스키마 검증. 위반은 즉시 SystemExit."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise SystemExit(f"fixture 에 scenarios 배열이 없다: {path}")

    seen_scenarios: set[str] = set()
    for scenario in scenarios:
        for key in ("id", "title", "description"):
            if not isinstance(scenario.get(key), str) or not scenario[key].strip():
                raise SystemExit(f"시나리오에 {key} 가 없다: {scenario.get('id')}")
        if scenario["id"] in seen_scenarios:
            raise SystemExit(f"시나리오 id 중복: {scenario['id']}")
        seen_scenarios.add(scenario["id"])

        keywords = scenario.get("callback_keywords")
        if not isinstance(keywords, list) or not keywords:
            raise SystemExit(f"시나리오에 callback_keywords 가 없다: {scenario['id']}")

        turns = scenario.get("turns")
        if not isinstance(turns, list) or not turns:
            raise SystemExit(f"시나리오에 turns 가 없다: {scenario['id']}")

        turn_ids: set[str] = set()
        for turn in turns:
            label = f"{scenario['id']}/{turn.get('id')}"
            for key in ("id", "input"):
                if not isinstance(turn.get(key), str) or not turn[key].strip():
                    raise SystemExit(f"턴에 {key} 가 없다: {label}")
            if turn["id"] in turn_ids:
                raise SystemExit(f"턴 id 중복: {label}")
            turn_ids.add(turn["id"])
            if turn.get("event_type") not in EVENT_TYPES:
                raise SystemExit(f"알 수 없는 event_type: {label} — {turn.get('event_type')}")
            check = turn.get("flow_check")
            if not isinstance(check, dict):
                raise SystemExit(f"턴에 flow_check 딕셔너리가 없다: {label}")
            _validate_flow_check(turn, check, scenario, turn_ids, label)
    return data


def canonical_json_sha256(data: Any) -> str:
    """Hash JSON semantics, rather than its whitespace or platform line endings."""
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_flow_check(
    turn: dict[str, Any],
    check: dict[str, Any],
    scenario: dict[str, Any],
    seen_turn_ids: set[str],
    label: str,
) -> None:
    event = turn["event_type"]
    if event == "multi_chat":
        items = check.get("aggregate_items")
        if not isinstance(items, list) or len(items) < 3:
            raise SystemExit(f"multi_chat 턴에는 aggregate_items 3건 이상이 필요하다: {label}")
        if not all(isinstance(item, str) and item.strip() for item in items):
            raise SystemExit(f"aggregate_items 에 빈 항목이 있다: {label}")
    elif event == "donation":
        name = check.get("donation_name")
        if not isinstance(name, str) or not name.strip():
            raise SystemExit(f"donation 턴에는 donation_name 이 필요하다: {label}")
        if name not in turn["input"]:
            raise SystemExit(f"donation_name 이 입력에 없다: {label}")
    elif event == "callback_probe":
        seed = check.get("seed_turn_id")
        if not isinstance(seed, str) or seed not in seen_turn_ids:
            raise SystemExit(f"callback_probe 의 seed_turn_id 가 앞 턴에 없다: {label}")
        keywords = check.get("callback_keywords")
        if not isinstance(keywords, list) or not keywords:
            raise SystemExit(f"callback_probe 에 callback_keywords 가 없다: {label}")
        missing = [k for k in keywords if k not in scenario["callback_keywords"]]
        if missing:
            raise SystemExit(f"시나리오 callback_keywords 에 없는 키워드: {label} — {missing}")
        if check.get("expected_window") not in ("in", "out"):
            raise SystemExit(f"callback_probe 의 expected_window 는 in|out 이다: {label}")
    elif event == "topic_shift":
        if check.get("expect_no_block_declaration") is not True:
            raise SystemExit(f"topic_shift 턴에는 expect_no_block_declaration 이 필요하다: {label}")


# ---------------------------------------------------------------------------
# 프롬프트 조립
# ---------------------------------------------------------------------------
def build_system_content(contract: str = "off") -> str:
    """시스템 메시지 전문. off 면 A/B 러너 조합과 바이트 동일하다."""
    base = ab.AIRI_SYSTEM_PROMPT + "\n\n" + ab.BROADCAST_FRAME
    return apply_broadcast_contract(base, contract == "on")


def contract_block_of(system_content: str) -> str:
    """조립된 시스템 메시지에서 계약 블록만 떼어낸다. off 면 빈 문자열이다."""
    base = build_system_content("off")
    return system_content[len(base) :].strip() if system_content.startswith(base) else ""


def build_turn_messages(
    system_content: str,
    history: Sequence[tuple[str, str]],
    user_content: str,
    history_turns: int,
) -> list[dict[str, str]]:
    """시스템 1개 + 최근 N쌍 + 이번 턴. 시스템 메시지는 어떤 경우에도 바뀌지 않는다."""
    kept = list(history[-history_turns:]) if history_turns > 0 else []
    messages = [{"role": "system", "content": system_content}]
    for past_user, past_assistant in kept:
        messages.append({"role": "user", "content": past_user})
        messages.append({"role": "assistant", "content": past_assistant})
    messages.append({"role": "user", "content": user_content})
    return messages


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------
def score_turn_flow(
    turn: dict[str, Any],
    response: str,
    *,
    seed_in_context: bool | None,
    prior_names: Sequence[str],
) -> dict[str, Any]:
    """턴 하나의 흐름 마커. 해당 없는 마커는 None 으로 남긴다."""
    event = turn["event_type"]
    check = turn.get("flow_check") or {}
    markers: dict[str, bool | None] = {name: None for name in FLOW_MARKER_ORDER}
    details: dict[str, Any] = {}

    if event == "callback_probe":
        hit, hits = callback_hit(response, check.get("callback_keywords") or [])
        markers["callback_hit"] = hit
        details["callback"] = {
            "seed_turn_id": check.get("seed_turn_id"),
            "keywords": check.get("callback_keywords") or [],
            "matched": hits,
            "expected_window": check.get("expected_window"),
            "seed_in_context": seed_in_context,
        }
    elif event == "multi_chat":
        ok, info = aggregate_response(response, check.get("aggregate_items") or [])
        markers["aggregate_response"] = ok
        details["aggregate"] = info
    elif event == "donation":
        markers["donation_name_call"] = name_called(response, check.get("donation_name") or "")
        details["donation"] = {"name": check.get("donation_name")}
    elif event == "topic_shift":
        markers["topic_shift_natural"] = topic_shift_natural(response)

    leaks = leaked_names(response, prior_names)
    markers["no_name_leak"] = not leaks
    if leaks:
        details["name_leak"] = leaks
    return {"markers": markers, "details": details}


def run_scenario(
    transport: Any,
    model: str,
    scenario: dict[str, Any],
    *,
    system_content: str,
    max_tokens: int,
    timeout: float,
    history_turns: int,
) -> dict[str, Any]:
    """시나리오 하나를 턴 순서대로 돌린다. 응답은 히스토리에 되먹인다."""
    turns = scenario["turns"]
    user_by_id = {turn["id"]: ab.USER_PREFIX + turn["input"] for turn in turns}
    index_by_id = {turn["id"]: position for position, turn in enumerate(turns, start=1)}

    history: list[tuple[str, str]] = []
    donation_names: list[str] = []
    rows: list[dict[str, Any]] = []

    for position, turn in enumerate(turns, start=1):
        user_content = user_by_id[turn["id"]]
        messages = build_turn_messages(system_content, history, user_content, history_turns)
        record = ab.call_once(
            transport, model=model, messages=messages, max_tokens=max_tokens, timeout=timeout
        )
        response = record.get("response", "") or ""

        seed_in_context: bool | None = None
        seed_distance: int | None = None
        if turn["event_type"] == "callback_probe":
            seed_id = (turn.get("flow_check") or {}).get("seed_turn_id")
            seed_content = user_by_id.get(seed_id)
            seed_in_context = any(
                message["role"] == "user" and message["content"] == seed_content
                for message in messages[:-1]
            )
            if seed_id in index_by_id:
                seed_distance = position - index_by_id[seed_id]

        current_name = (turn.get("flow_check") or {}).get("donation_name")
        prior_names = [name for name in donation_names if name != current_name]

        record.update(
            {
                "turn_id": turn["id"],
                "turn_index": position,
                "event_type": turn["event_type"],
                "input_text": turn["input"],
                "source_fixture_id": turn.get("source_fixture_id"),
                "synthetic": bool(turn.get("synthetic")),
                "history_pairs": max(0, (len(messages) - 2) // 2),
                "seed_distance": seed_distance,
                "score": ab.score_response(response),
                "addressee": ab.score_addressee(turn["id"], response),
                "flow": score_turn_flow(
                    turn,
                    response,
                    seed_in_context=seed_in_context,
                    prior_names=prior_names,
                ),
            }
        )
        rows.append(record)

        if current_name:
            donation_names.append(current_name)
        if record.get("ok") and response.strip():
            history.append((user_content, response))

        status = "ok" if record.get("ok") else record.get("failure", "fail")
        print(
            f"[{model}/{scenario['id']}] {position}/{len(turns)} {turn['id']}"
            f"({turn['event_type']}) {status} hist={record['history_pairs']} "
            f"total={record.get('complete_ms')}",
            file=sys.stderr,
        )

    return {
        "scenario_id": scenario["id"],
        "title": scenario["title"],
        "description": scenario["description"],
        "turns": rows,
    }


def _marker_bucket(rows: Sequence[dict[str, Any]], marker: str) -> dict[str, Any]:
    applicable = [r for r in rows if r["flow"]["markers"].get(marker) is not None]
    hits = sum(1 for r in applicable if r["flow"]["markers"][marker])
    return {
        "turns": len(applicable),
        "hits": hits,
        "rate": round(hits / len(applicable), 3) if applicable else None,
    }


def summarize_scenario(scenario_result: dict[str, Any]) -> dict[str, Any]:
    rows = scenario_result["turns"]
    ok = [r for r in rows if r.get("ok")]
    completes = [r["complete_ms"] for r in ok if r.get("complete_ms") is not None]
    chars = [r["score"]["char_count"] for r in ok]

    marker_rates = {}
    for marker in ab.MARKER_ORDER:
        hits = sum(1 for r in ok if r["score"]["markers"][marker])
        marker_rates[marker] = {
            "hits": hits,
            "n": len(ok),
            "rate": round(hits / len(ok), 3) if ok else None,
        }
    violations = {
        name: sum(1 for r in ok if name in r["score"]["violations"]) for name in ab.VIOLATION_ORDER
    }
    passes = sum(1 for r in ok if r["score"]["broadcast_pass"])

    # 흐름 마커는 응답이 온 턴에서만 의미가 있다(실패 턴의 빈 응답이 준수로 집계되면 안 된다).
    probes = [r for r in ok if r["event_type"] == "callback_probe"]
    in_window = [
        r for r in probes if r["flow"]["details"].get("callback", {}).get("seed_in_context")
    ]
    out_window = [
        r for r in probes if not r["flow"]["details"].get("callback", {}).get("seed_in_context")
    ]

    def probe_bucket(items: Sequence[dict[str, Any]]) -> dict[str, Any]:
        hits = sum(1 for r in items if r["flow"]["markers"].get("callback_hit"))
        return {
            "probes": len(items),
            "hits": hits,
            "rate": round(hits / len(items), 3) if items else None,
        }

    leaks = [
        {"turn_id": r["turn_id"], "names": r["flow"]["details"]["name_leak"]}
        for r in rows
        if r["flow"]["details"].get("name_leak")
    ]

    failures: dict[str, int] = {}
    for row in rows:
        if not row.get("ok"):
            key = row.get("failure", "unknown")
            failures[key] = failures.get(key, 0) + 1

    return {
        "scenario_id": scenario_result["scenario_id"],
        "title": scenario_result["title"],
        "n_turns": len(rows),
        "n_ok": len(ok),
        "n_failed": len(rows) - len(ok),
        "failures": failures,
        "complete_ms": {
            "p50": ab.pct(completes, 0.5),
            "p95": ab.pct(completes, 0.95),
            "min": ab.pct(completes, 0.0),
            "max": ab.pct(completes, 1.0),
        },
        "markers": marker_rates,
        "violations": violations,
        "broadcast_pass": {
            "hits": passes,
            "n": len(ok),
            "rate": round(passes / len(ok), 3) if ok else None,
        },
        # 흐름 마커와 같은 이유로 응답이 온 턴에서만 채점한다.
        "addressee": ab.summarize_addressee(ok),
        "flow": {
            "callback": {
                **probe_bucket(probes),
                "in_context": probe_bucket(in_window),
                "out_of_context": probe_bucket(out_window),
                "note": (
                    "out_of_context = 요청 시점 히스토리 창에 seed 가 없었다. "
                    "미스가 모델 능력 부족이 아니라 --history-turns 캡의 결과일 수 있다."
                ),
            },
            "aggregate_response": _marker_bucket(ok, "aggregate_response"),
            "donation_name_call": _marker_bucket(ok, "donation_name_call"),
            "no_name_leak": _marker_bucket(ok, "no_name_leak"),
            "topic_shift_natural": _marker_bucket(ok, "topic_shift_natural"),
            "name_leaks": leaks,
            "politeness_drift": politeness_drift([r["score"]["markers"]["banmal"] for r in ok]),
            "length_variance": length_variance(chars),
        },
    }


def summarize_model(model_result: dict[str, Any]) -> dict[str, Any]:
    scenarios = [summarize_scenario(s) for s in model_result["scenarios"]]
    rows = [row for s in model_result["scenarios"] for row in s["turns"]]
    ok = [r for r in rows if r.get("ok")]
    completes = [r["complete_ms"] for r in ok if r.get("complete_ms") is not None]
    chars = [r["score"]["char_count"] for r in ok]
    probes = [r for r in ok if r["event_type"] == "callback_probe"]
    probe_hits = sum(1 for r in probes if r["flow"]["markers"].get("callback_hit"))
    passes = sum(1 for r in ok if r["score"]["broadcast_pass"])

    return {
        "model": model_result["model"],
        "scenarios": scenarios,
        "overall": {
            "n_turns": len(rows),
            "n_ok": len(ok),
            "n_failed": len(rows) - len(ok),
            "complete_ms": {
                "p50": ab.pct(completes, 0.5),
                "p95": ab.pct(completes, 0.95),
                "min": ab.pct(completes, 0.0),
                "max": ab.pct(completes, 1.0),
            },
            "length_variance": length_variance(chars),
            "broadcast_pass": {
                "hits": passes,
                "n": len(ok),
                "rate": round(passes / len(ok), 3) if ok else None,
            },
            "addressee": ab.summarize_addressee(ok),
            "callback": {
                "probes": len(probes),
                "hits": probe_hits,
                "rate": round(probe_hits / len(probes), 3) if probes else None,
            },
            "aggregate_response": _marker_bucket(ok, "aggregate_response"),
            "donation_name_call": _marker_bucket(ok, "donation_name_call"),
            "no_name_leak": _marker_bucket(ok, "no_name_leak"),
            "topic_shift_natural": _marker_bucket(ok, "topic_shift_natural"),
        },
        "transport_mode": model_result.get("transport_mode") or {},
        "warmup_excluded": {
            "ok": (model_result.get("warmup") or {}).get("ok"),
            "complete_ms": (model_result.get("warmup") or {}).get("complete_ms"),
            "note": "모델 첫 로드 흡수용. 집계에서 제외.",
        },
    }


def _checkpoint_flow(flow: dict[str, Any]) -> dict[str, Any]:
    """Keep only numeric flow evidence; names, prose, and turn content never escape."""
    return {
        "callback": {
            key: {name: bucket[name] for name in ("probes", "hits", "rate")}
            for key, bucket in (
                ("all", flow["callback"]),
                ("in_context", flow["callback"]["in_context"]),
                ("out_of_context", flow["callback"]["out_of_context"]),
            )
        },
        **{
            name: {key: flow[name][key] for key in ("turns", "hits", "rate")}
            for name in (
                "aggregate_response",
                "donation_name_call",
                "no_name_leak",
                "topic_shift_natural",
            )
        },
        "politeness_drift": {
            key: flow["politeness_drift"][key]
            for key in ("window", "first_violation_rate", "second_violation_rate", "drift")
        },
        "length_variance": {
            key: flow["length_variance"][key]
            for key in ("p50", "p95", "min", "max", "spread", "distinct", "n")
        },
    }


def _checkpoint_scenario(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenario_id": summary["scenario_id"],
        **{key: summary[key] for key in ("n_turns", "n_ok", "n_failed")},
        "markers": summary["markers"],
        "violations": summary["violations"],
        "broadcast_pass": summary["broadcast_pass"],
        "flow": _checkpoint_flow(summary["flow"]),
    }


def project_checkpoint_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    """Create the closed, content-free artifact used by the offline checkpoint.

    This is deliberately a projection instead of a redaction pass: unknown report
    fields cannot accidentally become evidence fields.
    """
    config = payload["config"]
    prompt = payload["prompt"]
    fixtures = payload["fixtures"]
    default_fixture = DEFAULT_FIXTURES.resolve()
    if Path(fixtures["path"]).resolve() != default_fixture:
        raise ValueError("checkpoint evidence requires the shipped rehearsal fixture")
    expected_ids = [scenario["id"] for scenario in load_rehearsal_fixtures(default_fixture)["scenarios"]]
    contract = prompt.get("contract")
    contract_block = contract_block_of(build_system_content(contract)) if contract in ("off", "on") else None
    expected_hashes = {
        "system_prompt_sha256": ab.sha256(ab.AIRI_SYSTEM_PROMPT),
        "broadcast_frame_sha256": ab.sha256(ab.BROADCAST_FRAME),
        "combined_system_sha256": ab.sha256(build_system_content(contract)) if contract in ("off", "on") else None,
        "contract_block_sha256": ab.sha256(contract_block) if contract_block else None,
    }
    if (
        config.get("dry_run") is not True
        or config.get("token_supplied") is not False
        or config.get("base_url") != "dry-run"
        or config.get("models") != ["dry-midm"]
        or config.get("max_tokens") != PRODUCTION_MAX_TOKENS
        or config.get("history_turns") != DEFAULT_HISTORY_TURNS
        or config.get("streaming") is not False
        or contract not in ("off", "on")
        or any(prompt.get(key) != value for key, value in expected_hashes.items())
        or fixtures.get("selected_scenarios") != expected_ids
        or fixtures.get("total_scenarios") != len(expected_ids)
        or fixtures.get("selected_turns") != sum(len(s["turns"]) for s in load_rehearsal_fixtures(default_fixture)["scenarios"])
    ):
        raise ValueError("checkpoint evidence is limited to the full synthetic dry fixture")
    evidence = {
        "schema_version": CHECKPOINT_EVIDENCE_SCHEMA,
        "config": {
            key: config[key]
            for key in ("models", "max_tokens", "history_turns", "dry_run", "streaming")
        } | {"contract": contract},
        "scope": {
            "synthetic_only": True,
            "network_used": False,
            "model_called": False,
            "proxy_path_tested": False,
            "b1b_tested": False,
            "tts_tested": False,
        },
        "hashes": {
            key: prompt[key]
            for key in (
                "system_prompt_sha256",
                "broadcast_frame_sha256",
                "combined_system_sha256",
                "contract_block_sha256",
            )
        },
        "fixtures": {
            "schema_version": fixtures["schema_version"],
            "semantic_json_sha256": canonical_json_sha256(load_rehearsal_fixtures(DEFAULT_FIXTURES)),
            **{key: fixtures[key] for key in ("selected_scenarios", "total_scenarios", "selected_turns")},
        },
        "summaries": [
            {
                "model": model["model"],
                "scenarios": [_checkpoint_scenario(scenario) for scenario in model["scenarios"]],
                "overall": {
                    key: model["overall"][key]
                    for key in (
                        "n_turns", "n_ok", "n_failed", "length_variance", "broadcast_pass",
                        "callback", "aggregate_response", "donation_name_call", "no_name_leak",
                        "topic_shift_natural",
                    )
                },
            }
            for model in payload["summaries"]
        ],
    }
    validate_checkpoint_evidence(evidence)
    return evidence


def validate_checkpoint_evidence(evidence: Any) -> None:
    """Fail closed unless evidence exactly has the content-free v1 shape."""
    if not isinstance(evidence, dict) or set(evidence) != {
        "schema_version", "config", "scope", "hashes", "fixtures", "summaries"
    }:
        raise ValueError("checkpoint evidence root schema is not exact")
    if evidence["schema_version"] != CHECKPOINT_EVIDENCE_SCHEMA:
        raise ValueError("unsupported checkpoint evidence schema")
    expected = {
        "config": {"models", "max_tokens", "history_turns", "dry_run", "streaming", "contract"},
        "scope": {"synthetic_only", "network_used", "model_called", "proxy_path_tested", "b1b_tested", "tts_tested"},
        "hashes": {"system_prompt_sha256", "broadcast_frame_sha256", "combined_system_sha256", "contract_block_sha256"},
        "fixtures": {"schema_version", "semantic_json_sha256", "selected_scenarios", "total_scenarios", "selected_turns"},
    }
    for key, keys in expected.items():
        if not isinstance(evidence[key], dict) or set(evidence[key]) != keys:
            raise ValueError(f"checkpoint evidence {key} schema is not exact")
    if evidence["scope"] != {
        "synthetic_only": True, "network_used": False, "model_called": False,
        "proxy_path_tested": False, "b1b_tested": False, "tts_tested": False,
    }:
        raise ValueError("checkpoint evidence scope is not the closed synthetic scope")
    config = evidence["config"]
    if (
        config["models"] != ["dry-midm"]
        or config["max_tokens"] != PRODUCTION_MAX_TOKENS
        or config["history_turns"] != DEFAULT_HISTORY_TURNS
        or config["dry_run"] is not True
        or config["streaming"] is not False
        or config["contract"] not in ("off", "on")
    ):
        raise ValueError("checkpoint evidence config values are malformed")
    contract_block = contract_block_of(build_system_content(config["contract"]))
    expected_hashes = {
        "system_prompt_sha256": ab.sha256(ab.AIRI_SYSTEM_PROMPT),
        "broadcast_frame_sha256": ab.sha256(ab.BROADCAST_FRAME),
        "combined_system_sha256": ab.sha256(build_system_content(config["contract"])),
        "contract_block_sha256": ab.sha256(contract_block) if contract_block else None,
    }
    if evidence["hashes"] != expected_hashes:
        raise ValueError("checkpoint evidence hashes are malformed")
    shipped = load_rehearsal_fixtures(DEFAULT_FIXTURES)
    expected_ids = [scenario["id"] for scenario in shipped["scenarios"]]
    fixture = evidence["fixtures"]
    if (
        fixture["schema_version"] != FIXTURE_SCHEMA
        or fixture["semantic_json_sha256"] != canonical_json_sha256(shipped)
        or fixture["selected_scenarios"] != expected_ids
        or fixture["total_scenarios"] != len(expected_ids)
        or fixture["selected_turns"] != sum(len(s["turns"]) for s in shipped["scenarios"])
    ):
        raise ValueError("checkpoint evidence fixture pin is malformed")
    if not isinstance(evidence["summaries"], list) or len(evidence["summaries"]) != 1:
        raise ValueError("checkpoint evidence requires exactly one dry summary")
    flow_keys = {
        "callback", "aggregate_response", "donation_name_call", "no_name_leak",
        "topic_shift_natural", "politeness_drift", "length_variance",
    }
    scenario_keys = {
        "scenario_id", "n_turns", "n_ok", "n_failed", "markers", "violations",
        "broadcast_pass", "flow",
    }
    overall_keys = {
        "n_turns", "n_ok", "n_failed", "length_variance", "broadcast_pass", "callback",
        "aggregate_response", "donation_name_call", "no_name_leak", "topic_shift_natural",
    }
    def exact_int(value: Any) -> bool:
        return type(value) is int

    def finite_number(value: Any) -> bool:
        return type(value) in (int, float) and math.isfinite(float(value))

    def validate_bucket(bucket: Any, denominator_key: str, expected_total: int) -> bool:
        keys = {denominator_key, "hits", "rate"}
        if not isinstance(bucket, dict) or set(bucket) != keys:
            return False
        total = bucket[denominator_key]
        hits = bucket["hits"]
        if not exact_int(total) or not exact_int(hits) or total != expected_total or not 0 <= hits <= total:
            return False
        expected_rate = round(hits / total, 3) if total else None
        rate = bucket["rate"]
        return rate is None if expected_rate is None else finite_number(rate) and rate == expected_rate

    def validate_variance(value: Any, expected_n: int) -> bool:
        if not isinstance(value, dict) or set(value) != {"p50", "p95", "min", "max", "spread", "distinct", "n"}:
            return False
        if not exact_int(value["n"]) or value["n"] != expected_n:
            return False
        if not exact_int(value["distinct"]) or not 1 <= value["distinct"] <= expected_n:
            return False
        metrics = [value[key] for key in ("min", "p50", "p95", "max", "spread")]
        if not all(finite_number(item) and item >= 0 for item in metrics):
            return False
        if not value["min"] <= value["p50"] <= value["p95"] <= value["max"]:
            return False
        return value["spread"] == round(value["max"] - value["min"], 1)

    def validate_drift(value: Any) -> bool:
        if not isinstance(value, dict) or set(value) != {
            "window", "first_violation_rate", "second_violation_rate", "drift"
        }:
            return False
        if value["window"] != POLITENESS_WINDOW:
            return False
        first = value["first_violation_rate"]
        second = value["second_violation_rate"]
        drift = value["drift"]
        return (
            finite_number(first) and 0 <= first <= 1
            and finite_number(second) and 0 <= second <= 1
            and finite_number(drift) and -1 <= drift <= 1
            and drift == round(second - first, 3)
        )

    model = evidence["summaries"][0]
    if not isinstance(model, dict) or set(model) != {"model", "scenarios", "overall"}:
        raise ValueError("checkpoint evidence model schema is not exact")
    if model["model"] != "dry-midm" or not isinstance(model["scenarios"], list):
        raise ValueError("checkpoint evidence model identity is malformed")
    if [scenario.get("scenario_id") for scenario in model["scenarios"] if isinstance(scenario, dict)] != expected_ids:
        raise ValueError("checkpoint evidence scenarios are not the frozen ordered pair")
    if len(model["scenarios"]) != len(expected_ids):
        raise ValueError("checkpoint evidence scenario count is malformed")

    expected_flow_totals: dict[str, dict[str, int]] = {}
    for source in shipped["scenarios"]:
        kinds = [turn["event_type"] for turn in source["turns"]]
        expected_flow_totals[source["id"]] = {
            "aggregate_response": kinds.count("multi_chat"),
            "donation_name_call": kinds.count("donation"),
            "no_name_leak": len(kinds),
            "topic_shift_natural": kinds.count("topic_shift"),
        }

    for scenario, source in zip(model["scenarios"], shipped["scenarios"]):
        if not isinstance(scenario, dict) or set(scenario) != scenario_keys:
            raise ValueError("checkpoint evidence scenario schema is not exact")
        if (scenario["n_turns"], scenario["n_ok"], scenario["n_failed"]) != (24, 24, 0):
            raise ValueError("checkpoint evidence scenario must be a complete 24-turn dry run")
        if not isinstance(scenario["markers"], dict) or not isinstance(scenario["violations"], dict):
            raise ValueError("checkpoint evidence score objects are malformed")
        if set(scenario["markers"]) != set(ab.MARKER_ORDER) or set(scenario["violations"]) != set(ab.VIOLATION_ORDER):
            raise ValueError("checkpoint evidence score schema is not exact")
        if any(not validate_bucket(bucket, "n", 24) for bucket in scenario["markers"].values()):
            raise ValueError("checkpoint evidence marker buckets are malformed")
        if any(not exact_int(value) or not 0 <= value <= 24 for value in scenario["violations"].values()):
            raise ValueError("checkpoint evidence violation counts are malformed")
        if not validate_bucket(scenario["broadcast_pass"], "n", 24):
            raise ValueError("checkpoint evidence broadcast bucket is malformed")
        flow = scenario["flow"]
        if not isinstance(flow, dict) or set(flow) != flow_keys:
            raise ValueError("checkpoint evidence flow schema is not exact")
        callback = flow["callback"]
        if not isinstance(callback, dict) or set(callback) != {"all", "in_context", "out_of_context"}:
            raise ValueError("checkpoint evidence callback schema is not exact")
        if (
            not validate_bucket(callback["all"], "probes", 2)
            or not validate_bucket(callback["in_context"], "probes", 1)
            or not validate_bucket(callback["out_of_context"], "probes", 1)
            or callback["all"]["hits"] != callback["in_context"]["hits"] + callback["out_of_context"]["hits"]
        ):
            raise ValueError("checkpoint evidence callback values are malformed")
        for key, expected_total in expected_flow_totals[source["id"]].items():
            if not validate_bucket(flow[key], "turns", expected_total):
                raise ValueError("checkpoint evidence flow bucket is malformed")
        if not validate_drift(flow["politeness_drift"]):
            raise ValueError("checkpoint evidence politeness drift is malformed")
        if not validate_variance(flow["length_variance"], 24):
            raise ValueError("checkpoint evidence flow variance is malformed")

    overall = model["overall"]
    if not isinstance(overall, dict) or set(overall) != overall_keys:
        raise ValueError("checkpoint evidence overall schema is malformed")
    if (overall["n_turns"], overall["n_ok"], overall["n_failed"]) != (48, 48, 0):
        raise ValueError("checkpoint evidence overall counts are malformed")
    scenarios = model["scenarios"]
    if not validate_variance(overall["length_variance"], 48):
        raise ValueError("checkpoint evidence overall variance is malformed")
    if not validate_bucket(overall["broadcast_pass"], "n", 48) or overall["broadcast_pass"]["hits"] != sum(
        scenario["broadcast_pass"]["hits"] for scenario in scenarios
    ):
        raise ValueError("checkpoint evidence overall broadcast bucket is malformed")
    if not validate_bucket(overall["callback"], "probes", 4) or overall["callback"]["hits"] != sum(
        scenario["flow"]["callback"]["all"]["hits"] for scenario in scenarios
    ):
        raise ValueError("checkpoint evidence overall callback bucket is malformed")
    for key in ("aggregate_response", "donation_name_call", "no_name_leak", "topic_shift_natural"):
        expected_total = sum(expected_flow_totals[scenario_id][key] for scenario_id in expected_ids)
        if not validate_bucket(overall[key], "turns", expected_total) or overall[key]["hits"] != sum(
            scenario["flow"][key]["hits"] for scenario in scenarios
        ):
            raise ValueError("checkpoint evidence overall flow bucket is malformed")
    scenario_variances = [scenario["flow"]["length_variance"] for scenario in scenarios]
    if (
        overall["length_variance"]["min"] != min(value["min"] for value in scenario_variances)
        or overall["length_variance"]["max"] != max(value["max"] for value in scenario_variances)
    ):
        raise ValueError("checkpoint evidence overall variance does not match its scenarios")
    forbidden = {"prompt", "input", "input_text", "response", "error", "path", "token", "title", "description", "name_leak", "name_leaks", "note"}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if forbidden & set(value):
                raise ValueError("checkpoint evidence contains content-bearing data")
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)
        elif isinstance(value, str) and len(value) > 128:
            raise ValueError("checkpoint evidence contains an unexpected long string")

    walk(evidence)


# ---------------------------------------------------------------------------
# 리포트
# ---------------------------------------------------------------------------
def _fmt(value: Any, width: int = 9) -> str:
    return ("-" if value is None else str(value)).rjust(width)


def _rate(value: Any, width: int = 9) -> str:
    return ("-" if value is None else f"{value:.0%}").rjust(width)


def _ratio(bucket: dict[str, Any], key: str = "turns", width: int = 11) -> str:
    total = bucket.get(key) or 0
    if not total:
        return "-".rjust(width)
    return f"{bucket['hits']}/{total}".rjust(width)


def print_report(summaries: list[dict[str, Any]], *, contract: str, history_turns: int) -> None:
    line = "=" * 100
    print(line)
    print("AIRI 멀티턴 방송 리허설 — 흐름 축 (낭독 연쇄·콜백·여론 집계·후원·화제 전환)")
    print(line)
    print(f"[측정 범위] {MEASUREMENT_SCOPE}")
    print(f"[한계] {SIMULATION_LIMIT}")
    print(f"[채점] {SCORING_NOTE}")
    print(
        f"[발화 계약] B4c 방송 발화 계약 {contract}"
        + (" — 시스템 메시지 끝에 계약 블록을 덧붙였다" if contract == "on" else " (기존 프롬프트 그대로)")
    )
    print(f"[히스토리] 최근 {history_turns}쌍(유저·어시스턴트)만 유지 — 운영 num_ctx 2048 제약 존중")
    print()

    print("── 흐름 마커 " + "─" * 86)
    header = (
        "model / scenario".ljust(38)
        + _fmt("턴", 5)
        + _fmt("성공", 6)
        + "콜백(창안)".rjust(12)
        + "콜백(창밖)".rjust(12)
        + "집계".rjust(11)
        + "후원호명".rjust(11)
        + "호명준수".rjust(11)
        + "전환자연".rjust(11)
    )
    print(header)
    for summary in summaries:
        print(summary["model"])
        for scenario in summary["scenarios"]:
            flow = scenario["flow"]
            print(
                ("  " + scenario["scenario_id"])[:38].ljust(38)
                + _fmt(scenario["n_turns"], 5)
                + _fmt(scenario["n_ok"], 6)
                + _ratio(flow["callback"]["in_context"], "probes", 12)
                + _ratio(flow["callback"]["out_of_context"], "probes", 12)
                + _ratio(flow["aggregate_response"])
                + _ratio(flow["donation_name_call"])
                + _ratio(flow["no_name_leak"])
                + _ratio(flow["topic_shift_natural"])
            )
    print("  · 콜백(창안)=요청 시점 히스토리에 seed 가 남아 있던 probe / (창밖)=캡으로 밀려난 probe")
    print("  · 집계=1~2문장 유지 + 개별 채팅 나열 없음 / 후원호명=후원 턴에서 닉네임 호명")
    print("  · 호명준수=그 턴의 후원자가 아닌 이름을 부르지 않음(관찰 연구 P6 호명 정책)")
    print("  · 전환자연=화제 전환을 블록·주제 선언 없이 받음")
    print()

    print("── 존댓말 drift / 길이 가변성 " + "─" * 70)
    print(
        "model / scenario".ljust(38)
        + "전반위반".rjust(11)
        + "후반위반".rjust(11)
        + "drift".rjust(9)
        + _fmt("자수p50")
        + _fmt("자수p95")
        + _fmt("자수min")
        + _fmt("자수max")
        + _fmt("분포수", 8)
    )
    for summary in summaries:
        print(summary["model"])
        for scenario in summary["scenarios"]:
            drift = scenario["flow"]["politeness_drift"]
            variance = scenario["flow"]["length_variance"]
            print(
                ("  " + scenario["scenario_id"])[:38].ljust(38)
                + _rate(drift["first_violation_rate"], 11)
                + _rate(drift["second_violation_rate"], 11)
                + _fmt(drift["drift"], 9)
                + _fmt(variance["p50"])
                + _fmt(variance["p95"])
                + _fmt(variance["min"])
                + _fmt(variance["max"])
                + _fmt(variance["distinct"], 8)
            )
    print(f"  · 전·후반 각 최대 {POLITENESS_WINDOW}턴 비교. drift 양수 = 후반으로 갈수록 존댓말이 늘었다")
    print("  · 분포수 = 서로 다른 자수 값의 개수. 낮으면 길이가 굳어 있다는 신호")
    print()

    print("── 출력 규격 마커 / 지연 " + "─" * 75)
    header = "model / scenario".ljust(38)
    for marker in ab.MARKER_ORDER:
        header += marker[:9].rjust(11)
    header += "방송통과".rjust(11) + _fmt("완료p50") + _fmt("완료p95")
    print(header)
    for summary in summaries:
        print(summary["model"])
        for scenario in summary["scenarios"]:
            row = ("  " + scenario["scenario_id"])[:38].ljust(38)
            for marker in ab.MARKER_ORDER:
                row += _rate(scenario["markers"][marker]["rate"], 11)
            row += _rate(scenario["broadcast_pass"]["rate"], 11)
            row += _fmt(scenario["complete_ms"]["p50"]) + _fmt(scenario["complete_ms"]["p95"])
            print(row)
    print("  · 마커 정의는 A/B 러너와 동일하다 (run_broadcast_chat_ab.score_response)")
    print()

    print("── 수신자 인지 (addressee — 사이드카 채점) " + "─" * 57)
    scored_any = any(
        scenario["addressee"]["scored"] for summary in summaries for scenario in summary["scenarios"]
    )
    if not scored_any:
        print("  · 사이드카(addressee-checks.json)가 없거나 대상 턴이 없어 채점하지 않았다")
    else:
        header = "model / scenario".ljust(38) + _fmt("채점", 7) + _fmt("통과", 7) + _fmt("통과율", 9)
        for name in ab.ADDRESSEE_TYPES:
            header += name.replace("_", "")[:11].rjust(13)
        print(header)
        for summary in summaries:
            print(summary["model"])
            for scenario in summary["scenarios"]:
                bucket = scenario["addressee"]
                row = ("  " + scenario["scenario_id"])[:38].ljust(38)
                row += _fmt(bucket["scored"], 7) + _fmt(bucket["hits"], 7)
                row += ("-" if bucket["rate"] is None else f"{bucket['rate']:.0%}").rjust(9)
                for name in ab.ADDRESSEE_TYPES:
                    counts = bucket["by_type"][name]
                    row += ("-" if not counts["n"] else f"{counts['hits']}/{counts['n']}").rjust(13)
                print(row)
        for summary in summaries:
            for scenario in summary["scenarios"]:
                failures = scenario["addressee"]["failures"]
                ids = ", ".join(f"{f['case_id']}({f['type']})" for f in failures)
                print(
                    f"  {summary['model']}/{scenario['scenario_id']}: "
                    f"수신자 실패 {len(failures)}건 — {ids or '없음'}"
                )
    print("  · receive_reversal=받은 축하·감사·응원 되돌려주기 / agent_reversal=요청·핀잔을 시청자에게 넘기기")
    print("  · situation_blind=자기 방송·자기 존재 상황 오인 / third_party_absorb=제3자 이야기 1인칭 흡수")
    print(f"  · {ab.ADDRESSEE_NOTE} 사이드카에 없는 턴은 채점 대상이 아니다")
    print()

    print("── 금지 위반 / 실패 " + "─" * 80)
    for summary in summaries:
        for scenario in summary["scenarios"]:
            hits = {k: v for k, v in scenario["violations"].items() if v}
            leaks = scenario["flow"]["name_leaks"]
            print(
                f"  {summary['model']}/{scenario['scenario_id']}: "
                f"위반 {hits or '없음'} / 호명누출 {leaks or '없음'} / "
                f"실패 {scenario['n_failed']}건 {scenario['failures'] or '없음'}"
            )
    print(line)


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base-url", help="OpenAI 호환 base URL (예: https://host:11439/v1)")
    parser.add_argument("--token", help="Bearer 토큰. 없으면 env AIRI_REMOTE_TOKEN 사용")
    parser.add_argument("--models", default="", help="콤마 구분 모델 id")
    parser.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
    parser.add_argument("--scenarios", help="콤마 구분 시나리오 id 필터")
    parser.add_argument(
        "--contract",
        choices=("off", "on"),
        default="off",
        help="B4c 방송 발화 계약 블록 부착 여부. off(기본)=기존 프롬프트 그대로",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=PRODUCTION_MAX_TOKENS,
        help=f"응답 토큰 상한 (기본 {PRODUCTION_MAX_TOKENS} = 운영 proxy 값)",
    )
    parser.add_argument("--timeout", type=float, default=90.0, help="요청당 타임아웃 초 (기본 90)")
    parser.add_argument(
        "--history-turns",
        type=int,
        default=DEFAULT_HISTORY_TURNS,
        help=f"유지할 최근 유저·어시스턴트 교환쌍 수 (기본 {DEFAULT_HISTORY_TURNS})",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--insecure", action="store_true", help="TLS 검증 끄기(자체서명 인증서)")
    parser.add_argument("--dry-run", action="store_true", help="네트워크 없이 경로 검증")
    parser.add_argument("--proxy-source", help="ollama_proxy.py 경로 — 시스템 프롬프트 drift 검증")
    args = parser.parse_args(argv)

    if args.history_turns < 0:
        raise SystemExit("--history-turns 는 0 이상이어야 한다")
    if args.max_tokens > PRODUCTION_MAX_TOKENS:
        print(
            f"[warn] --max-tokens {args.max_tokens} 가 운영 기본값 {PRODUCTION_MAX_TOKENS} 보다 크다 "
            "— 방송 리듬과 다른 길이를 재게 된다",
            file=sys.stderr,
        )

    fixtures = load_rehearsal_fixtures(Path(args.fixtures))
    scenarios = fixtures["scenarios"]
    if args.scenarios:
        wanted = {s.strip() for s in args.scenarios.split(",") if s.strip()}
        unknown = wanted - {s["id"] for s in scenarios}
        if unknown:
            raise SystemExit(f"알 수 없는 시나리오 id: {sorted(unknown)}")
        scenarios = [s for s in scenarios if s["id"] in wanted]
    if not scenarios:
        raise SystemExit("선택된 시나리오가 0건이다")

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not models:
        if not args.dry_run:
            raise SystemExit("--models 가 필요하다")
        models = ["dry-midm"]

    prompt_check: dict[str, Any] = {"checked": False}
    if args.proxy_source:
        prompt_check = ab.verify_repo_prompt(Path(args.proxy_source))
        if not prompt_check.get("matches"):
            print("[warn] 레포 AIRI_SYSTEM_PROMPT 와 임베드 사본이 다르다", file=sys.stderr)

    token = args.token or os.environ.get("AIRI_REMOTE_TOKEN")
    if not args.dry_run:
        if not args.base_url:
            raise SystemExit("--base-url 이 필요하다")
        if not token:
            print("[warn] 토큰 없음 — 401 이 예상된다면 그대로 기록된다", file=sys.stderr)

    system_content = build_system_content(args.contract)

    results: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for model in models:
        # 서버가 스트리밍을 400 으로 거부하는 것이 실측이다(A/B 러너 주석). 멀티턴은
        # 요청 수가 많아 매 요청 폴백 왕복을 낭비할 이유가 없으므로 비스트리밍 고정.
        transport: Any = (
            ab.DryRunTransport(stream_mode="off")
            if args.dry_run
            else ab.HttpTransport(
                args.base_url, token, verify=not args.insecure, stream_mode="off"
            )
        )
        try:
            print(f"[{model}] warmup...", file=sys.stderr)
            warmup = ab.call_once(
                transport,
                model=model,
                messages=build_turn_messages(system_content, [], ab.USER_PREFIX + WARMUP_TEXT, 0),
                max_tokens=args.max_tokens,
                timeout=args.timeout,
            )
            warmup["role"] = "warmup_excluded_from_aggregate"
            print(
                f"[{model}] warmup ok={warmup.get('ok')} complete_ms={warmup.get('complete_ms')}",
                file=sys.stderr,
            )
            scenario_results = [
                run_scenario(
                    transport,
                    model,
                    scenario,
                    system_content=system_content,
                    max_tokens=args.max_tokens,
                    timeout=args.timeout,
                    history_turns=args.history_turns,
                )
                for scenario in scenarios
            ]
        finally:
            if hasattr(transport, "close"):
                transport.close()

        mode = transport.mode_info() if hasattr(transport, "mode_info") else {}
        result = {
            "model": model,
            "warmup": warmup,
            "scenarios": scenario_results,
            "transport_mode": mode,
        }
        results.append(result)
        summaries.append(summarize_model(result))

    contract_block = contract_block_of(system_content)
    payload = {
        "schema_version": SCHEMA,
        "generated_at": ab.now_iso(),
        "measurement_scope": MEASUREMENT_SCOPE,
        "simulation_limit": SIMULATION_LIMIT,
        "scoring_note": SCORING_NOTE,
        "config": {
            "base_url": args.base_url if not args.dry_run else "dry-run",
            "models": models,
            "max_tokens": args.max_tokens,
            "timeout_s": args.timeout,
            "history_turns": args.history_turns,
            "token_supplied": bool(token),
            "dry_run": args.dry_run,
            "tls_verify": not args.insecure,
            "streaming": False,
            "streaming_note": "서버가 스트리밍을 400 으로 거부하는 것이 실측이라 비스트리밍 고정이다",
        },
        "prompt": {
            "system_prompt_sha256": ab.sha256(ab.AIRI_SYSTEM_PROMPT),
            "broadcast_frame_sha256": ab.sha256(ab.BROADCAST_FRAME),
            "combined_system_sha256": ab.sha256(system_content),
            "user_prefix": ab.USER_PREFIX,
            "repo_prompt_check": prompt_check,
            "system_prompt": ab.AIRI_SYSTEM_PROMPT,
            "broadcast_frame": ab.BROADCAST_FRAME,
            "contract": args.contract,
            "contract_block_sha256": ab.sha256(contract_block) if contract_block else None,
            "contract_block": contract_block or None,
        },
        "fixtures": {
            "path": str(Path(args.fixtures).resolve()),
            "schema_version": fixtures.get("schema_version"),
            "selected_scenarios": [s["id"] for s in scenarios],
            "total_scenarios": len(fixtures["scenarios"]),
            "selected_turns": sum(len(s["turns"]) for s in scenarios),
        },
        "addressee_checks": ab.addressee_metadata(),
        "summaries": summaries,
        "results": results,
    }
    output = Path(args.output)
    ab.atomic_write(output, payload)
    print_report(summaries, contract=args.contract, history_turns=args.history_turns)
    print(f"\n원 응답 전문 포함 결과: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
