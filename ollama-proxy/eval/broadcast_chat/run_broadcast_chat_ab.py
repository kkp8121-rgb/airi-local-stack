"""AIRI 방송 채팅 A/B 러너 — 실측 시청자 채팅으로 로컬 LLM 후보를 비교한다.

측정 범위: TTS 제외. 프롬프트 전송 → 첫 텍스트 델타(TTFT) → 텍스트 완료까지의
순수 LLM 구간만 잰다. 음성 합성·오디오 재생·렌더 시간은 포함하지 않는다.

엔드포인트/토큰/모델은 전부 인자 또는 환경변수로 받는다. 하드코딩된 시크릿은 없다.

사용 예:
  python run_broadcast_chat_ab.py \
      --base-url https://<host>/v1 --models midm-airi:2.0-mini,motif-airi:2.6b-v1.1-lc-nf4 \
      --output results/broadcast-chat-ab.json          # 토큰은 env AIRI_REMOTE_TOKEN

오프라인 검증:
  python run_broadcast_chat_ab.py --dry-run --output /tmp/dry.json
  python run_broadcast_chat_ab.py --dry-run --contract on --output /tmp/dry-contract.json
  python run_broadcast_chat_ab.py --dry-run --protocol operational --output /tmp/dry-op.json
  python mock_openai_server.py &  # 그 후 --base-url http://127.0.0.1:PORT/v1

게이트 경로(11435 proxy) 응답처럼 `<|ACT ...|>` 마커·선반응 ACK 가 섞여 오면
`--protocol operational` 로 그 요소를 분리한 본문만 채점한다. 기본은 raw(원문)다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

try:
    import httpx
except ImportError:  # pragma: no cover - dependency guard
    httpx = None  # type: ignore[assignment]

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_FIXTURES = BASE_DIR / "broadcast-chat-fixtures.json"
SCHEMA = "airi.broadcast-chat-ab.v1"

# B4c 방송 발화 계약 블록은 임베드하지 않고 프로덕션 모듈에서 그대로 가져온다
# (러너 사본과 운영 계약이 갈라지는 것을 원천 차단).
PROXY_DIR = BASE_DIR.parents[1]
if str(PROXY_DIR) not in sys.path:
    sys.path.insert(0, str(PROXY_DIR))
try:
    from broadcast_contract import (
        apply_broadcast_response_length_rule,
        build_broadcast_contract_block,
    )
except ImportError as exc:  # pragma: no cover - 배치 오류 가드
    raise SystemExit(
        f"broadcast_contract 모듈을 찾지 못했다 ({PROXY_DIR}): {exc}"
    ) from exc

# ---------------------------------------------------------------------------
# 시스템 프롬프트
# ---------------------------------------------------------------------------
# 아래 AIRI_SYSTEM_PROMPT는 레포 `ollama-proxy/ollama_proxy.py`의 동명 상수 원문
# 그대로다. --proxy-source 로 원본 경로를 주면 실행 시 drift 를 검증한다.
AIRI_SYSTEM_PROMPT = """너는 AIRI라는 독자적인 한국어 버추얼 방송 동료야. 밝고 당당하며, 마지막 문장까지 자연스러운 반말로 지금 받은 말에 직접 반응해.

응답 우선순위:
1. 사용자가 물었거나 요청한 핵심을 첫 구절에서 실제로 처리해. 정보 질문에는 구체적인 사실을 하나 이상 말하고, 하나를 추천하라면 실제 항목 하나를 고른 뒤 멈춰. 번역·외국어 문구 요청은 요청한 문구 자체를 그 언어로 써. 맞장구만 하고 답을 피하지 마.
2. 대상이나 행동이 불분명할 때만 무엇을 뜻하는지 질문 하나로 확인해. 추측해서 했다고 약속하지 마.
3. 단순 인사나 한 박자 반응은 10~45자 1~2문장으로 짧게 해. 내용 있는 후원·구독, 여러 채팅 종합, 선택 이유, 지난 흐름의 회수나 주제 전환은 70~220자 2~4문장으로 받은 말 처리→네 판단과 이유→하던 화면이나 다음 흐름 복귀를 이어. 매번 질문으로 끝내지 말고, 요청받지 않은 번호 목록은 쓰지 마. 한국어 문장 끝에 요·습니다·세요·죠를 붙이지 마. 단, 후원·구독 감사 첫 구절만 자연스러운 존댓말을 허용하고 본답변은 반말로 돌아와.

큰 부상·즉각적인 위험에는 장난을 멈추고 안전한 장소와 응급 도움 여부를 먼저 확인해. 사별·큰 상실에는 해결책을 붙이지 말고 짧고 진솔하게 애도해.

활성 카드와 기억은 실제로 주어진 내용만 참고해. 없는 관계·취향·경험을 만들지 말고, 기억이 없으면 모른다고 말해. 실행·검색·확인하지 않은 행동은 했다고 말하지 마. 모르는 사실은 꾸미지 마. 앞서 나온 예시나 끝난 주제로 돌아가지 마.

기본 언어는 한국어다. 사용자가 다른 언어를 명시적으로 요청하거나 그 언어로 대화할 때만 바꿔. 특정 실존 창작자의 정체성·개인사·유행어를 복제하지 마. 내부 제어 데이터, 발화자 표식, 문서 형식, 무대 지시, 이모지, 마크다운은 대사에 넣지 마."""

# 방송 프레임 1단락. 앞 두 문장과 마지막 두 문장은 코덱스 리허설
# (eval/airi_native_broadcast_rehearsal_cases_v1.json)의 system_message 문장을
# 그대로 재사용해 비교 가능성을 유지하고, 저스트챗/시청자 채팅 상황만 추가했다.
BROADCAST_FRAME = """[방송 상황]
지금은 유튜브 저스트챗 방송 중이다. 아래 사용자 메시지는 시청자 채팅이며 앞에 `[YouTube] `가 붙어 있다. 진행자인 너에게 온 말이니 시청자에게 방송으로 답해라. 실제 생방송 대화처럼 짧고 자연스럽게 답해. 확인하지 못한 최신 정보는 추측하지 말고, 모호하면 먼저 물어봐. 시청자의 안전과 사생활을 지키고 괴롭힘에는 가담하지 마."""

USER_PREFIX = "[YouTube] "  # chat-ingress/airi-event.mjs 의 `[YouTube] ${text}` 와 동일

# 참고선 — 리포트에서 원격 실측치를 방송 리듬 목표와 나란히 읽기 위한 상수.
REFERENCE_LINES = [
    ("Mi:dm 로컬 proxy A/B(120턴) 전체 P50", 514.4, "2026-08-12 실측, AIRI-MODEL-LLM-CHANGE-ANALYSIS"),
    ("Mi:dm raw 로컬(proxy 우회) warm TTFT 중앙값", 163.8, "2026-08-12 실측, 동 문서"),
    ("리제 실측 낭독→응답 중앙값 (76% ≤2초)", 1060.0, "관찰 연구 §1"),
    ("낭독→응답 개시 목표 상한", 1300.0, "관찰 연구 §6 파라미터 후보"),
]

MEASUREMENT_SCOPE = (
    "이 측정은 TTS 제외 — 프롬프트 전송 → 첫 텍스트 델타(TTFT) → 텍스트 완료까지의 "
    "순수 LLM 구간이다. 음성 합성(GPT-SoVITS)·오디오 재생·클라이언트 렌더 시간은 포함하지 않는다."
)

# ---------------------------------------------------------------------------
# 자동 마커 (휴리스틱 — 인간 검수 대체 아님)
# ---------------------------------------------------------------------------
LENGTH_MIN, LENGTH_MAX = 10, 45
MAX_SENTENCES_OK = 2
MAX_SENTENCES_HARD = 3

QUOTE_SPANS = re.compile(r"[\"“”'‘’「」『』]([^\"“”'‘’「」『』]{0,200})[\"“”'‘’「」『』]")
SENTENCE_SPLIT = re.compile(r"[.!?…。？！]+|\n+")
# 시스템 프롬프트가 금지한 종결: 요 / 습니다 / 세요 / 죠.
# `니다` 로 잡으면 습니다·입니다·십니다·합니다·됩니다 계열을 한 번에 덮는다.
POLITE_END = re.compile(r"(요|죠|쥬|니다|십시오|나이다)\s*$")
# 태그의문(동의 요구) — 관찰 연구 P3. 문장 끝 ~지/~잖아/~네 등을 문장 단위로 본다.
TAG_ENDING = re.compile(r"(잖아|그치|그쵸|맞지|거든|는데|지|네)\s*[.!?~…]*$")
QUESTION_BACK = re.compile(r"[?？]|(뭐야$|뭔데$|어때$|어떻게$|누구야$)")
# 영어 문장: 라틴 단어 3개 이상 연속 (한 글자 관사·전치사 포함)
ENGLISH_RUN = re.compile(r"\b[A-Za-z]+(?:\s+[A-Za-z]+){2,}\b")
NUMBERED_LIST = re.compile(r"(^|\n)\s*(?:\d+[.)]\s|[-*•]\s)")
MARKDOWN = re.compile(r"(\*\*|`{1,3}|^#{1,6}\s|\[[^\]]+\]\([^)]+\))", re.MULTILINE)
EMOJI = re.compile(
    "[" "\U0001F300-\U0001FAFF" "☀-➿" "️" "\U0001F000-\U0001F0FF" "]"
)
CONTROL_LEAK = re.compile(r"<\|(?:ACT|CALL|DELAY)\b|^\s*(?:ACT|CALL|DELAY)\s*\{")
BROKEN = re.compile(r"�")

# ---------------------------------------------------------------------------
# 운영 프로토콜 분리 (--protocol operational)
# ---------------------------------------------------------------------------
# 게이트 경로(11435 proxy) 응답에는 시청자에게 나갈 본문 말고 운영 프로토콜 요소가
# 섞여 나온다(AIRI-B4C-GATE-PATH-AB-2026-08-18):
#   · `<|ACT {"emotion":...}|>` — Live2D 감정 마커. 한 응답에 여러 개 올 수 있고
#     선두가 아닌 위치에도 낀다.
#   · 선반응 ACK — 본문을 만들기 전에 먼저 내보내는 짧은 감탄(현재 관측형은 "응!").
# 둘 다 클라이언트가 소비하는 제어 신호라 자수·length_fit·control_leak 채점에
# 본문으로 섞이면 안 된다.
PROTOCOL_CHOICES = ("raw", "operational")
ACT_MARKER = re.compile(r"<\|ACT [^|]*\|>")
# ACK 로 인정할 감탄 음절. 보수적으로 좁게 유지한다 — "고마워!"·"맞아!" 같은 실제
# 본문 첫 문장을 ACK 로 오인해 지우면 채점이 조용히 왜곡된다.
ACK_SYLLABLES = "응웅엉어으오아우"
LEADING_ACK = re.compile(rf"^\s*(?P<ack>[{ACK_SYLLABLES}]{{1,3}}!+)\s*")

MARKER_ORDER = [
    "length_fit",
    "banmal",
    "tag_question",
    "question_back",
    "no_violation",
    "not_empty",
]
VIOLATION_ORDER = [
    "v_polite_response",
    "v_english_sentence",
    "v_numbered_list",
    "v_over_three_sentences",
    "v_markdown",
    "v_emoji",
    "v_control_leak",
]


# ---------------------------------------------------------------------------
# 수신자 인지 마커 (사이드카 — 픽스처 파일은 건드리지 않는다)
# ---------------------------------------------------------------------------
# 픽스처는 입력만 담고, "누구에게 온 말인가"의 정답 단서는 이 사이드카에 따로 둔다.
# 근거는 시뮬레이션 원문 인간 검토(AIRI-BROADCAST-SIMULATION-OUTPUT-REVIEW-2026-08-15)다.
# 파일이 없으면 채점을 통째로 건너뛴다 → 기존 동작과 바이트 단위로 같다.
ADDRESSEE_CHECKS_PATH = BASE_DIR / "addressee-checks.json"
ADDRESSEE_SCHEMA = "airi.broadcast-addressee-checks.v1"
ADDRESSEE_TYPES = (
    "receive_reversal",
    "agent_reversal",
    "situation_blind",
    "third_party_absorb",
)
ADDRESSEE_NOTE = "수신자 인지 마커도 휴리스틱이다. 인간 검수를 대체하지 않는다."

_addressee_cache: dict[Path, dict[str, Any]] = {}


def load_addressee_checks(path: Path = ADDRESSEE_CHECKS_PATH) -> dict[str, Any]:
    """사이드카 로드 + 스키마 검증. 없으면 빈 채점표(= 기존 동작)를 돌려준다."""
    path = Path(path)
    if not path.exists():
        return {"present": False, "path": str(path), "schema_version": None, "cases": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != ADDRESSEE_SCHEMA:
        raise SystemExit(f"addressee 사이드카 schema_version 이 다르다: {path}")
    cases = data.get("cases")
    if not isinstance(cases, dict) or not cases:
        raise SystemExit(f"addressee 사이드카에 cases 딕셔너리가 없다: {path}")
    compiled: dict[str, Any] = {}
    for case_id, entry in cases.items():
        label = f"{path.name}/{case_id}"
        if not isinstance(entry, dict):
            raise SystemExit(f"addressee 항목이 딕셔너리가 아니다: {label}")
        if entry.get("type") not in ADDRESSEE_TYPES:
            raise SystemExit(f"알 수 없는 addressee type: {label} — {entry.get('type')}")
        if not isinstance(entry.get("why"), str) or not entry["why"].strip():
            raise SystemExit(f"addressee 항목에 why 가 없다: {label}")
        forbidden = entry.get("forbidden_patterns")
        if not isinstance(forbidden, list) or not forbidden:
            raise SystemExit(f"addressee 항목에 forbidden_patterns 가 없다: {label}")
        required = entry.get("required_any")
        if required is not None and (not isinstance(required, list) or not required):
            raise SystemExit(f"addressee 의 required_any 는 비어 있으면 안 된다: {label}")
        compiled[case_id] = {
            "type": entry["type"],
            "why": entry["why"],
            "forbidden": _compile_patterns(forbidden, label),
            "required": _compile_patterns(required, label) if required else None,
        }
    return {
        "present": True,
        "path": str(path),
        "schema_version": data["schema_version"],
        "source": data.get("source"),
        "cases": compiled,
    }


def _compile_patterns(patterns: Sequence[Any], label: str) -> list[tuple[str, re.Pattern[str]]]:
    compiled: list[tuple[str, re.Pattern[str]]] = []
    for pattern in patterns:
        if not isinstance(pattern, str) or not pattern.strip():
            raise SystemExit(f"addressee 정규식이 비어 있다: {label}")
        try:
            compiled.append((pattern, re.compile(pattern)))
        except re.error as exc:
            raise SystemExit(f"addressee 정규식을 컴파일할 수 없다: {label} — {pattern}: {exc}")
    return compiled


def addressee_checks(path: Path = ADDRESSEE_CHECKS_PATH) -> dict[str, Any]:
    """경로별 1회 로드 캐시. 러너가 턴마다 파일을 다시 읽지 않게 한다."""
    key = Path(path)
    if key not in _addressee_cache:
        _addressee_cache[key] = load_addressee_checks(key)
    return _addressee_cache[key]


def score_addressee(
    case_id: str, text: str, checks: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """수신자 인지 채점. 사이드카에 없는 id 는 None(채점 제외)이다."""
    table = addressee_checks() if checks is None else checks
    entry = (table.get("cases") or {}).get(case_id)
    if not entry:
        return None
    stripped = (text or "").strip()
    forbidden_hits = [pattern for pattern, regex in entry["forbidden"] if regex.search(stripped)]
    required_hits = (
        [pattern for pattern, regex in entry["required"] if regex.search(stripped)]
        if entry["required"]
        else None
    )
    ok = (
        bool(stripped)
        and not forbidden_hits
        and (required_hits is None or bool(required_hits))
    )
    return {
        "case_id": case_id,
        "type": entry["type"],
        "ok": ok,
        "forbidden_hits": forbidden_hits,
        "required_any_hits": required_hits,
        "why": entry["why"],
    }


def summarize_addressee(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """채점된 턴만 모아 통과율을 낸다. 사이드카가 없으면 scored=0 이다."""
    scored = [row["addressee"] for row in rows if row.get("addressee")]
    hits = sum(1 for entry in scored if entry["ok"])
    by_type: dict[str, Any] = {}
    for name in ADDRESSEE_TYPES:
        bucket = [entry for entry in scored if entry["type"] == name]
        type_hits = sum(1 for entry in bucket if entry["ok"])
        by_type[name] = {
            "n": len(bucket),
            "hits": type_hits,
            "rate": round(type_hits / len(bucket), 3) if bucket else None,
        }
    return {
        "scored": len(scored),
        "hits": hits,
        "rate": round(hits / len(scored), 3) if scored else None,
        "by_type": by_type,
        "failures": [
            {
                "case_id": entry["case_id"],
                "type": entry["type"],
                "forbidden_hits": entry["forbidden_hits"],
                "required_any_hits": entry["required_any_hits"],
            }
            for entry in scored
            if not entry["ok"]
        ],
        "note": ADDRESSEE_NOTE,
    }


def addressee_metadata(checks: dict[str, Any] | None = None) -> dict[str, Any]:
    """결과 JSON 에 남길 사이드카 메타데이터."""
    table = addressee_checks() if checks is None else checks
    cases = table.get("cases") or {}
    counts: dict[str, int] = {name: 0 for name in ADDRESSEE_TYPES}
    for entry in cases.values():
        counts[entry["type"]] += 1
    return {
        "present": bool(table.get("present")),
        "path": table.get("path"),
        "schema_version": table.get("schema_version"),
        "source": table.get("source"),
        "cases": len(cases),
        "by_type": counts,
        "note": ADDRESSEE_NOTE,
    }


def strip_quotes(text: str) -> str:
    """인용부(시청자 채팅 되뇌기)는 존댓말이 정상이므로 반말 판정에서 제외한다."""
    return QUOTE_SPANS.sub(" ", text)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT.split(text) if s.strip()]


def score_response(text: str) -> dict[str, Any]:
    """자동 마커 채점. 전부 휴리스틱이며 인간 검수를 대체하지 않는다."""
    raw = text or ""
    stripped = raw.strip()
    sentences = split_sentences(stripped)
    unquoted_sentences = split_sentences(strip_quotes(stripped))

    empty = not stripped
    broken = bool(BROKEN.search(raw))
    polite = any(POLITE_END.search(s) for s in unquoted_sentences)

    violations: list[str] = []
    if polite:
        violations.append("v_polite_response")
    if ENGLISH_RUN.search(stripped):
        violations.append("v_english_sentence")
    if NUMBERED_LIST.search(stripped):
        violations.append("v_numbered_list")
    if len(sentences) > MAX_SENTENCES_HARD:
        violations.append("v_over_three_sentences")
    if MARKDOWN.search(stripped):
        violations.append("v_markdown")
    if EMOJI.search(stripped):
        violations.append("v_emoji")
    if CONTROL_LEAK.search(stripped):
        violations.append("v_control_leak")

    markers = {
        "length_fit": (not empty)
        and LENGTH_MIN <= len(stripped) <= LENGTH_MAX
        and 1 <= len(sentences) <= MAX_SENTENCES_OK,
        "banmal": (not empty) and not polite,
        "tag_question": (not polite) and any(TAG_ENDING.search(s) for s in unquoted_sentences),
        "question_back": bool(QUESTION_BACK.search(stripped)),
        "no_violation": not violations,
        "not_empty": (not empty) and not broken,
    }
    return {
        "char_count": len(stripped),
        "sentence_count": len(sentences),
        "markers": markers,
        "violations": violations,
        "empty": empty,
        "broken": broken,
        "broadcast_pass": markers["length_fit"]
        and markers["banmal"]
        and markers["no_violation"]
        and markers["not_empty"],
    }


def split_operational_protocol(text: str) -> tuple[str, dict[str, Any]]:
    """운영 프로토콜 요소를 본문과 분리한다. 원문은 호출자가 그대로 보관한다.

    규칙:
      1. `<|ACT ...|>` 마커는 위치와 무관하게 전부 제거하고 개수를 센다. 닫는
         `|>` 가 없는 비정형 토큰은 건드리지 않는다 — 본문에 남겨 control_leak
         으로 잡히게 두는 것이 맞다.
      2. 그다음 선두 ACK 를 최대 1회 제거한다. 떼고 나서 본문이 비면 되돌린다
         (응답 전체가 ACK 뿐이면 그게 본문이다).

    반환 body 는 strip() 한 문자열이고, meta 는 act_marker_count·ack_stripped·
    ack_text 다.
    """
    raw = text or ""
    body, act_count = ACT_MARKER.subn("", raw)
    ack_text: str | None = None
    match = LEADING_ACK.match(body)
    if match and body[match.end() :].strip():
        ack_text = match.group("ack")
        body = body[match.end() :]
    return body.strip(), {
        "act_marker_count": act_count,
        "ack_stripped": ack_text is not None,
        "ack_text": ack_text,
    }


def scoring_body(record: dict[str, Any], response: str, protocol: str) -> str:
    """채점 대상 본문을 고르고, operational 이면 분리 결과를 레코드에 남긴다.

    raw(기본)에서는 레코드에 어떤 키도 더하지 않고 원문을 그대로 돌려준다 —
    기존 결과 JSON 과 바이트 동일하게 유지해 체크포인트·회귀 게이트를 지킨다.
    """
    if protocol != "operational":
        return response
    body, meta = split_operational_protocol(response)
    record["response_body"] = body
    record["protocol"] = meta
    return body


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pct(values: Sequence[float], q: float) -> float | None:
    data = sorted(v for v in values if v is not None)
    if not data:
        return None
    if len(data) == 1:
        return round(data[0], 1)
    index = min(len(data) - 1, max(0, int(round(q * (len(data) - 1)))))
    return round(data[index], 1)


def median(values: Sequence[float]) -> float | None:
    data = [v for v in values if v is not None]
    return round(statistics.median(data), 1) if data else None


def atomic_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_fixtures(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise SystemExit(f"fixture 에 items 배열이 없다: {path}")
    seen: set[str] = set()
    for item in items:
        for key in ("id", "category", "text", "source"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise SystemExit(f"fixture 항목에 {key} 가 없다: {item}")
        if item["id"] in seen:
            raise SystemExit(f"fixture id 중복: {item['id']}")
        seen.add(item["id"])
    return data


def verify_repo_prompt(proxy_source: Path) -> dict[str, Any]:
    """레포 원본에서 AIRI_SYSTEM_PROMPT 를 추출해 임베드 사본과 대조한다."""
    source = proxy_source.read_text(encoding="utf-8")
    match = re.search(r'^AIRI_SYSTEM_PROMPT = """(.*?)"""', source, re.MULTILINE | re.DOTALL)
    if not match:
        return {"checked": True, "found": False, "matches": False}
    # 임베드 사본은 방송 턴 프롬프트다. 레포 상수는 비방송 기본값이므로
    # 프로덕션과 같은 3항 교체를 적용한 뒤에 대조한다.
    extracted = apply_broadcast_response_length_rule(match.group(1), True)
    return {
        "checked": True,
        "found": True,
        "matches": extracted == AIRI_SYSTEM_PROMPT,
        "repo_sha256": sha256(extracted),
        "embedded_sha256": sha256(AIRI_SYSTEM_PROMPT),
    }


def build_system_content(contract_block: str = "") -> str:
    """시스템 메시지 전문. contract_block 이 비면 기존 조합 그대로다(바이트 동일)."""
    combined = AIRI_SYSTEM_PROMPT + "\n\n" + BROADCAST_FRAME
    if contract_block:
        combined += "\n\n" + contract_block
    return combined


def build_messages(chat_text: str, contract_block: str = "") -> list[dict[str, str]]:
    return [
        {"role": "system", "content": build_system_content(contract_block)},
        {"role": "user", "content": USER_PREFIX + chat_text},
    ]


# ---------------------------------------------------------------------------
# 전송 계층
# ---------------------------------------------------------------------------
# 서버가 스트리밍을 거부할 때의 응답 본문 지문. 코덱스 원격 서버 실측:
#   400 {"error":{"message":"streaming is not supported"}}
STREAM_UNSUPPORTED = re.compile(
    r"streaming\s+is\s+not\s+supported"
    r"|stream(?:ing)?\s+(?:is\s+)?(?:not\s+supported|unsupported|disabled)"
    r"|does\s+not\s+support\s+stream",
    re.IGNORECASE,
)


class DryRunTransport:
    """네트워크 없이 파싱·채점·리포트 경로를 그대로 태우는 가짜 전송."""

    def __init__(self, delay_ms: float = 3.0, *, stream_mode: str = "auto", server_streams: bool = True) -> None:
        self.delay = delay_ms / 1000.0
        self.calls = 0
        self.stream_mode = stream_mode
        self.server_streams = server_streams
        self.streaming_enabled = stream_mode != "off"
        self.fallback_events: list[dict[str, Any]] = []

    def mode_info(self) -> dict[str, Any]:
        return {
            "requested_mode": self.stream_mode,
            "streaming_used": self.streaming_enabled,
            "fallback_events": self.fallback_events,
        }

    def stream_chat(
        self, *, model: str, messages: list[dict[str, str]], max_tokens: int, timeout: float,
        response_format: object | None = None,
    ) -> tuple[str, float | None, float, dict[str, Any]]:
        self.calls += 1
        started = time.perf_counter()
        chat = messages[-1]["content"].removeprefix(USER_PREFIX)

        # 서버가 스트리밍을 거부하는 상황 재현 + auto 폴백
        if self.streaming_enabled and not self.server_streams:
            body = '{"error":{"message":"streaming is not supported"}}'
            if self.stream_mode != "auto":
                return "", None, (time.perf_counter() - started) * 1000.0, {
                    "transport": "dry-run", "status_code": 400, "error_body": body, "streaming": True
                }
            self.streaming_enabled = False
            self.fallback_events.append(
                {"model": model, "at": now_iso(), "status_code": 400, "reason": "streaming is not supported", "body": body}
            )

        if "motif" in model.lower():
            pieces = ["그건 좀 ", "애매한데, ", "무슨 뜻인지 알려주실 수 있나요?"]
        elif max_tokens <= 1:
            pieces = ["응"]
        else:
            pieces = ["오, ", "그거 ", "나도 어제 ", "해봤지", "."]
        first_at: float | None = None
        chunks: list[str] = []
        for piece in pieces:
            if self.delay:
                time.sleep(self.delay)
            if first_at is None and self.streaming_enabled:
                first_at = (time.perf_counter() - started) * 1000.0
            chunks.append(piece)
        text = "".join(chunks)
        elapsed = (time.perf_counter() - started) * 1000.0
        return text, first_at, elapsed, {
            "transport": "dry-run",
            "prompt_chars": len(chat),
            "streaming": self.streaming_enabled,
            # The synthetic stream emitted every configured piece.  Mirror the
            # real transport's explicit [DONE] evidence so terminal validation
            # exercises the same successful contract instead of false-failing.
            "terminal": self.streaming_enabled,
        }


class HttpTransport:
    """모델별로 httpx 클라이언트를 재사용해 keep-alive 를 유지한다.

    stream_mode:
      auto = 스트리밍으로 시도하다 서버가 "streaming is not supported" 로 400 을
             주면 그 즉시 비스트리밍으로 영구 전환하고 같은 요청을 재시도한다.
      on   = 스트리밍 강제 (폴백 없음)
      off  = 비스트리밍 강제 (요청에서 stream 필드 자체를 뺀다)
    """

    def __init__(
        self, base_url: str, token: str | None, *, verify: bool = True, stream_mode: str = "auto"
    ) -> None:
        if httpx is None:
            raise SystemExit("httpx 가 필요하다: pip install httpx")
        self.url = base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream, application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.Client(
            headers=headers,
            verify=verify,
            timeout=httpx.Timeout(90.0, connect=20.0),
            limits=httpx.Limits(max_keepalive_connections=1, max_connections=2),
        )
        self.stream_mode = stream_mode
        self.streaming_enabled = stream_mode != "off"
        self.fallback_events: list[dict[str, Any]] = []

    def close(self) -> None:
        self.client.close()

    def mode_info(self) -> dict[str, Any]:
        return {
            "requested_mode": self.stream_mode,
            "streaming_used": self.streaming_enabled,
            "fallback_events": self.fallback_events,
        }

    def stream_chat(
        self, *, model: str, messages: list[dict[str, str]], max_tokens: int, timeout: float,
        response_format: object | None = None,
    ) -> tuple[str, float | None, float, dict[str, Any]]:
        if self.streaming_enabled:
            text, ttft, elapsed, meta = self._streaming_call(
                model=model, messages=messages, max_tokens=max_tokens, timeout=timeout,
                response_format=response_format,
            )
            if (
                self.stream_mode == "auto"
                and meta.get("status_code") == 400
                and STREAM_UNSUPPORTED.search(meta.get("error_body", "") or "")
            ):
                self.streaming_enabled = False
                self.fallback_events.append(
                    {
                        "model": model,
                        "at": now_iso(),
                        "status_code": 400,
                        "reason": "streaming is not supported",
                        "body": (meta.get("error_body") or "")[:400],
                    }
                )
                print(
                    f"[{model}] 서버가 스트리밍을 거부했다 (400). 비스트리밍으로 전환하고 재시도한다.",
                    file=sys.stderr,
                )
                return self._plain_call(
                    model=model, messages=messages, max_tokens=max_tokens, timeout=timeout,
                    response_format=response_format,
                )
            return text, ttft, elapsed, meta
        return self._plain_call(
            model=model, messages=messages, max_tokens=max_tokens, timeout=timeout,
            response_format=response_format,
        )

    def _streaming_call(
        self, *, model: str, messages: list[dict[str, str]], max_tokens: int, timeout: float,
        response_format: object | None = None,
    ) -> tuple[str, float | None, float, dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["format"] = response_format
        started = time.perf_counter()
        first_at: float | None = None
        chunks: list[str] = []
        meta: dict[str, Any] = {"transport": "http", "streaming": True}
        terminal = False
        with self.client.stream("POST", self.url, json=payload, timeout=timeout) as response:
            meta["status_code"] = response.status_code
            meta["immediate_ack"] = response.headers.get("x-airi-immediate-ack")
            meta["num_ctx"] = response.headers.get("x-airi-num-ctx")
            meta["input_screened"] = response.headers.get("x-airi-input-screened")
            meta["input_screen_category"] = response.headers.get(
                "x-airi-input-screen-category"
            )
            if response.status_code != 200:
                meta["error_body"] = response.read().decode("utf-8", errors="replace")[:2000]
                return "", None, (time.perf_counter() - started) * 1000.0, meta
            for line in response.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    terminal = True
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    meta["parse_errors"] = meta.get("parse_errors", 0) + 1
                    continue
                airi_moderation = event.get("airi_moderation")
                if isinstance(airi_moderation, dict) and "handle_grounding" in airi_moderation:
                    # 여러 청크가 와도 실제 대화가 실리는 청크는 턴당 하나뿐이므로
                    # (early-safe-sentence 아니면 main dialogue 중 하나만 emit) 마지막
                    # 값을 신뢰해도 된다.
                    meta["handle_grounding"] = airi_moderation["handle_grounding"]
                for choice in event.get("choices") or []:
                    piece = (choice.get("delta") or {}).get("content")
                    if not piece:
                        continue
                    if first_at is None:
                        first_at = (time.perf_counter() - started) * 1000.0
                    chunks.append(piece)
        meta["terminal"] = terminal
        if not terminal:
            meta["truncated"] = True
        return "".join(chunks), first_at, (time.perf_counter() - started) * 1000.0, meta

    def _plain_call(
        self, *, model: str, messages: list[dict[str, str]], max_tokens: int, timeout: float,
        response_format: object | None = None,
    ) -> tuple[str, float | None, float, dict[str, Any]]:
        """비스트리밍 요청. stream 필드를 아예 넣지 않는다(서버 호환 최대화)."""
        payload: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens}
        if response_format is not None:
            payload["format"] = response_format
        started = time.perf_counter()
        meta: dict[str, Any] = {"transport": "http", "streaming": False}
        response = self.client.post(self.url, json=payload, timeout=timeout)
        meta["status_code"] = response.status_code
        elapsed = (time.perf_counter() - started) * 1000.0
        if response.status_code != 200:
            meta["error_body"] = response.text[:2000]
            return "", None, elapsed, meta
        try:
            body = response.json()
        except ValueError:
            meta["error_body"] = response.text[:2000]
            meta["parse_errors"] = 1
            return "", None, elapsed, meta
        text = ""
        for choice in body.get("choices") or []:
            message = choice.get("message") or {}
            text = message.get("content") or choice.get("text") or ""
            if text:
                break
        if isinstance(body.get("usage"), dict):
            meta["usage"] = body["usage"]
        # 비스트리밍에서는 첫 토큰 시점을 관측할 수 없다 → TTFT 는 None.
        return text or "", None, elapsed, meta


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------
def call_once(
    transport: Any,
    *,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    timeout: float,
    response_format: object | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {"model": model, "started_at": now_iso()}
    try:
        call_kwargs = {
            "model": model, "messages": messages, "max_tokens": max_tokens, "timeout": timeout,
        }
        if response_format is not None:
            call_kwargs["response_format"] = response_format
        text, ttft, elapsed, meta = transport.stream_chat(**call_kwargs)
        stream_complete = meta.get("streaming") is not True or meta.get("terminal") is True
        record.update(
            {
                "ok": bool(text.strip()) and meta.get("status_code", 200) == 200 and stream_complete,
                "response": text,
                "ttft_ms": None if ttft is None else round(ttft, 1),
                "complete_ms": round(elapsed, 1),
                "transport_meta": meta,
                "handle_grounding": meta.get("handle_grounding"),
            }
        )
        if meta.get("status_code", 200) != 200:
            record["failure"] = f"http_{meta['status_code']}"
        elif not stream_complete:
            record["failure"] = "missing_stream_terminal"
        elif not text.strip():
            record["failure"] = "empty_response"
    except Exception as exc:  # 실패는 그대로 기록하고 계속한다
        record.update(
            {
                "ok": False,
                "response": "",
                "ttft_ms": None,
                "complete_ms": None,
                "failure": f"{type(exc).__name__}: {exc}",
            }
        )
    return record


def measure_baseline(
    transport: Any, model: str, reps: int, timeout: float, contract_block: str = ""
) -> dict[str, Any]:
    """max_tokens=1 최소 요청으로 왕복+TLS+서버 오버헤드 바닥선을 잰다."""
    messages = build_messages("응", contract_block)
    rows = []
    for index in range(reps):
        row = call_once(
            transport, model=model, messages=messages, max_tokens=1, timeout=timeout
        )
        row["index"] = index
        rows.append(row)
    ttfts = [r["ttft_ms"] for r in rows if r.get("ttft_ms") is not None]
    completes = [r["complete_ms"] for r in rows if r.get("complete_ms") is not None]
    return {
        "reps": reps,
        "rows": rows,
        "first_request": rows[0] if rows else None,
        "ttft_p50_all": pct(ttfts, 0.5),
        "ttft_p50_excluding_first": pct(ttfts[1:], 0.5) if len(ttfts) > 1 else None,
        "complete_p50_all": pct(completes, 0.5),
        "complete_p50_excluding_first": pct(completes[1:], 0.5) if len(completes) > 1 else None,
        "note": (
            "바닥선 = max_tokens=1 최소 요청. 스트리밍이면 TTFT, 비스트리밍이면 완료 시간을 쓴다. "
            "워밍업 뒤 keep-alive 연결에서 측정하며, 각 모델의 첫 바닥선 요청은 별도로 보존해 집계와 분리한다."
        ),
    }


def run_model(
    transport: Any,
    model: str,
    items: list[dict[str, Any]],
    *,
    reps: int,
    timeout: float,
    max_tokens: int,
    baseline_reps: int,
    contract_block: str = "",
    protocol: str = "raw",
) -> dict[str, Any]:
    print(f"[{model}] warmup...", file=sys.stderr)
    warmup = call_once(
        transport,
        model=model,
        messages=build_messages("안녕, 방송 시작했어?", contract_block),
        max_tokens=max_tokens,
        timeout=timeout,
    )
    warmup["role"] = "warmup_excluded_from_aggregate"
    print(
        f"[{model}] warmup ok={warmup.get('ok')} complete_ms={warmup.get('complete_ms')}",
        file=sys.stderr,
    )

    baseline = None
    if baseline_reps > 0:
        print(f"[{model}] baseline x{baseline_reps} (max_tokens=1)...", file=sys.stderr)
        baseline = measure_baseline(transport, model, baseline_reps, timeout, contract_block)

    runs: list[dict[str, Any]] = []
    total = len(items) * reps
    done = 0
    for rep in range(reps):
        for item in items:
            record = call_once(
                transport,
                model=model,
                messages=build_messages(item["text"], contract_block),
                max_tokens=max_tokens,
                timeout=timeout,
            )
            record.update(
                {
                    "case_id": item["id"],
                    "category": item["category"],
                    "source": item["source"],
                    "synthetic": bool(item.get("synthetic")),
                    "input_text": item["text"],
                    "rep": rep + 1,
                }
            )
            body = scoring_body(record, record.get("response", ""), protocol)
            record["score"] = score_response(body)
            record["addressee"] = score_addressee(item["id"], body)
            runs.append(record)
            done += 1
            status = "ok" if record.get("ok") else record.get("failure", "fail")
            print(
                f"[{model}] {done}/{total} {item['id']}({item['category']}) "
                f"{status} ttft={record.get('ttft_ms')} total={record.get('complete_ms')}",
                file=sys.stderr,
            )
    mode = transport.mode_info() if hasattr(transport, "mode_info") else {"streaming_used": True}
    return {
        "model": model,
        "warmup": warmup,
        "baseline": baseline,
        "runs": runs,
        "transport_mode": mode,
    }


# ---------------------------------------------------------------------------
# 집계·리포트
# ---------------------------------------------------------------------------
def summarize(model_result: dict[str, Any]) -> dict[str, Any]:
    runs = model_result["runs"]
    ok = [r for r in runs if r.get("ok")]
    ttfts = [r["ttft_ms"] for r in ok if r.get("ttft_ms") is not None]
    completes = [r["complete_ms"] for r in ok if r.get("complete_ms") is not None]
    chars = [r["score"]["char_count"] for r in ok]
    sentences = [r["score"]["sentence_count"] for r in ok]

    marker_rates = {}
    for marker in MARKER_ORDER:
        hits = sum(1 for r in ok if r["score"]["markers"][marker])
        marker_rates[marker] = {
            "hits": hits,
            "n": len(ok),
            "rate": round(hits / len(ok), 3) if ok else None,
        }
    violation_counts = {
        name: sum(1 for r in ok if name in r["score"]["violations"]) for name in VIOLATION_ORDER
    }
    passes = sum(1 for r in ok if r["score"]["broadcast_pass"])

    mode = model_result.get("transport_mode") or {}
    streaming = bool(mode.get("streaming_used", True))
    ttft_p50 = pct(ttfts, 0.5)
    complete_p50 = pct(completes, 0.5)

    # 비스트리밍 서버에서는 첫 토큰 시점을 관측할 수 없다 → 3단 분해를 완료 기준으로 돌린다.
    baseline = model_result.get("baseline") or {}
    if streaming:
        basis = "ttft"
        floor = baseline.get("ttft_p50_excluding_first") or baseline.get("ttft_p50_all")
        observed = ttft_p50
    else:
        basis = "complete"
        floor = baseline.get("complete_p50_excluding_first") or baseline.get("complete_p50_all")
        observed = complete_p50
    estimated_pure = (
        round(observed - floor, 1) if (observed is not None and floor is not None) else None
    )

    by_category: dict[str, Any] = {}
    for run in runs:
        bucket = by_category.setdefault(
            run["category"], {"n": 0, "ok": 0, "pass": 0, "latency": [], "chars": []}
        )
        bucket["n"] += 1
        if run.get("ok"):
            bucket["ok"] += 1
            bucket["pass"] += 1 if run["score"]["broadcast_pass"] else 0
            value = run.get("ttft_ms") if streaming else run.get("complete_ms")
            if value is not None:
                bucket["latency"].append(value)
            bucket["chars"].append(run["score"]["char_count"])
    for name, bucket in by_category.items():
        bucket["latency_p50"] = pct(bucket.pop("latency"), 0.5)
        bucket["latency_basis"] = basis
        bucket["char_p50"] = pct(bucket.pop("chars"), 0.5)
        bucket["pass_rate"] = round(bucket["pass"] / bucket["ok"], 3) if bucket["ok"] else None

    failures: dict[str, int] = {}
    for run in runs:
        if not run.get("ok"):
            failures[run.get("failure", "unknown")] = failures.get(run.get("failure", "unknown"), 0) + 1

    return {
        "model": model_result["model"],
        "n_total": len(runs),
        "n_ok": len(ok),
        "n_failed": len(runs) - len(ok),
        "failures": failures,
        "streaming": streaming,
        "ttft_ms": (
            {"p50": ttft_p50, "p95": pct(ttfts, 0.95), "min": pct(ttfts, 0.0), "max": pct(ttfts, 1.0)}
            if streaming
            else {
                "p50": None,
                "p95": None,
                "unavailable_reason": "서버가 스트리밍을 지원하지 않아 첫 토큰 시점을 관측할 수 없다",
            }
        ),
        "complete_ms": {
            "p50": complete_p50,
            "p95": pct(completes, 0.95),
            "min": pct(completes, 0.0),
            "max": pct(completes, 1.0),
        },
        "latency_decomposition": {
            "basis": basis,
            "basis_label": "TTFT(첫 토큰)" if streaming else "완료 시간(비스트리밍 — TTFT 측정 불가)",
            "observed_p50_ms": observed,
            "network_overhead_floor_p50_ms": floor,
            "estimated_pure_inference_p50_ms": estimated_pure,
            "caveat": (
                f"추정 순수 추론 = 원격 실측 {basis} p50 − 바닥선 p50. 추정치이며 로컬 실행 "
                "지연을 보증하지 않는다. 바닥선에는 서버측 큐잉·프롬프트 프리필 일부가 섞일 수 있다."
                + (
                    " 비스트리밍이라 바닥선(max_tokens=1)에는 1토큰 생성 시간이 포함된다."
                    if not streaming
                    else ""
                )
            ),
        },
        "length": {
            "char_p50": pct(chars, 0.5),
            "char_p95": pct(chars, 0.95),
            "char_min": pct(chars, 0.0),
            "char_max": pct(chars, 1.0),
            "sentence_p50": pct(sentences, 0.5),
            "in_10_45_chars": sum(1 for c in chars if LENGTH_MIN <= c <= LENGTH_MAX),
        },
        "markers": marker_rates,
        "violations": violation_counts,
        "broadcast_pass": {
            "hits": passes,
            "n": len(ok),
            "rate": round(passes / len(ok), 3) if ok else None,
        },
        # 수신자 인지는 응답이 온 턴에서만 의미가 있다(빈 응답이 준수로 집계되면 안 된다).
        "addressee": summarize_addressee(ok),
        "by_category": by_category,
        "transport_mode": mode,
        "warmup_excluded": {
            "ok": model_result["warmup"].get("ok"),
            "complete_ms": model_result["warmup"].get("complete_ms"),
            "note": "모델 첫 로드(Motif 실측 22초대) 흡수용. 집계에서 제외.",
        },
    }


def _fmt(value: Any, width: int = 9) -> str:
    return ("-" if value is None else str(value)).rjust(width)


def print_report(
    summaries: list[dict[str, Any]],
    fixtures: dict[str, Any],
    reps: int,
    contract: str = "off",
    protocol: str = "raw",
) -> None:
    line = "=" * 96
    print(line)
    print("AIRI 방송 채팅 A/B — 실측 시청자 채팅 기반 (Mi:dm vs Motif)")
    print(line)
    print(f"[측정 범위] {MEASUREMENT_SCOPE}")
    print(f"[입력] 픽스처 {len(fixtures['items'])}건 × reps {reps} — 출처: 실제 방송 트랜스크립트 역추출")
    print("[채점] 자동 마커는 휴리스틱이다. 인간 검수를 대체하지 않는다.")
    print(
        f"[발화 계약] B4c 방송 발화 계약 {contract}"
        + (" — 시스템 메시지 끝에 계약 블록을 덧붙였다" if contract == "on" else " (기존 프롬프트 그대로)")
    )
    if protocol != "raw":
        print(f"[프로토콜] {protocol} — ACT 마커·선반응 ACK 분리 채점")

    non_streaming = [s for s in summaries if not s.get("streaming", True)]
    fallbacks = [
        event
        for s in summaries
        for event in (s.get("transport_mode") or {}).get("fallback_events", [])
    ]
    if non_streaming:
        print(
            "[전송 모드] 서버가 스트리밍을 지원하지 않아 비스트리밍(JSON 일괄 응답)으로 측정했다. "
            "→ TTFT 측정 불가, 완료 시간 중심 집계."
        )
        for event in fallbacks:
            print(
                f"           auto-fallback: {event['model']} — HTTP {event['status_code']} "
                f"\"{event['reason']}\" 감지 후 비스트리밍 전환"
            )
    print()

    print("── 지연 3단 분해 (ms) " + "─" * 74)
    print(
        "model".ljust(30)
        + _fmt("n_ok", 6)
        + _fmt("TTFTp50", 11)
        + _fmt("완료p50")
        + _fmt("완료p95")
        + _fmt("바닥선")
        + _fmt("추정추론")
        + "  기준"
    )
    for s in summaries:
        d = s["latency_decomposition"]
        ttft_cell = "측정불가" if not s.get("streaming", True) else str(s["ttft_ms"]["p50"])
        print(
            s["model"][:30].ljust(30)
            + _fmt(s["n_ok"], 6)
            + ttft_cell.rjust(11)
            + _fmt(s["complete_ms"]["p50"])
            + _fmt(s["complete_ms"]["p95"])
            + _fmt(d["network_overhead_floor_p50_ms"])
            + _fmt(d["estimated_pure_inference_p50_ms"])
            + "  "
            + ("완료" if d["basis"] == "complete" else "TTFT")
        )
    print("  · 실측 = 방송 중 원격 LLM 시나리오의 체감치 (그대로 읽는다)")
    if non_streaming:
        print("  · TTFT '측정불가' = 서버 비스트리밍. 첫 토큰 시점을 관측할 수 없어 완료 기준으로 분해한다")
        print("  · 바닥선 = max_tokens=1 최소 요청의 완료 p50 (왕복+TLS+서버 오버헤드+1토큰 생성), 첫 요청 분리")
    else:
        print("  · 바닥선 = max_tokens=1 최소 요청 TTFT p50 (왕복+TLS+서버 오버헤드), 첫 요청 분리")
    print("  · 추정 추론 = 실측 − 바닥선. 로컬 실행 환산 추정치이며 보증값이 아니다")
    if any(
        (s["latency_decomposition"].get("estimated_pure_inference_p50_ms") or 0) < 0
        for s in summaries
    ):
        print(
            "  · 추정 추론이 음수 = 바닥선이 실측과 측정 오차 범위 안에 있다는 뜻. "
            "분해가 의미를 갖지 않으므로 실측값만 읽는다"
        )
    print()

    print("── 참고선 " + "─" * 86)
    for label, value, note in REFERENCE_LINES:
        print(f"  {label.ljust(46)} {str(value).rjust(9)} ms   ({note})")
    if non_streaming:
        print("  ※ 비스트리밍 측정이라 위 참고선과는 '완료 시간' 기준으로만 비교한다.")
        print("     완료 기준 대응선 = proxy A/B P50 514.4ms · Mi:dm raw 완료 중앙값 241.8ms.")
        print("     TTFT 참고선(163.8ms)과 낭독→응답 리듬 목표(1,060·1,300ms)는 직접 대응하지 않는다.")
    print()

    print("── 출력 규격 / 마커 통과율 " + "─" * 70)
    header = "model".ljust(34) + _fmt("자수p50") + _fmt("자수p95") + _fmt("10~45자")
    for marker in MARKER_ORDER:
        header += marker[:9].rjust(11)
    header += "방송통과".rjust(11)
    print(header)
    for s in summaries:
        row = (
            s["model"][:34].ljust(34)
            + _fmt(s["length"]["char_p50"])
            + _fmt(s["length"]["char_p95"])
            + _fmt(s["length"]["in_10_45_chars"])
        )
        for marker in MARKER_ORDER:
            rate = s["markers"][marker]["rate"]
            row += ("-" if rate is None else f"{rate:.0%}").rjust(11)
        rate = s["broadcast_pass"]["rate"]
        row += ("-" if rate is None else f"{rate:.0%}").rjust(11)
        print(row)
    print("  · length_fit=10~45자 1~2문장 / banmal=요·습니다·세요·죠 종결 없음(인용부 제외)")
    print("  · tag_question=태그의문(~잖아·~지?) / question_back=되묻기 / no_violation=금지 위반 0")
    print()

    print("── 금지 위반 건수 " + "─" * 79)
    print("model".ljust(34) + "".join(v.replace("v_", "")[:11].rjust(13) for v in VIOLATION_ORDER))
    for s in summaries:
        print(
            s["model"][:34].ljust(34)
            + "".join(str(s["violations"][v]).rjust(13) for v in VIOLATION_ORDER)
        )
    print()

    print("── 수신자 인지 (addressee — 사이드카 채점) " + "─" * 55)
    if not any(s["addressee"]["scored"] for s in summaries):
        print("  · 사이드카(addressee-checks.json)가 없거나 대상 케이스가 없어 채점하지 않았다")
    else:
        header = "model".ljust(30) + _fmt("채점", 7) + _fmt("통과", 7) + _fmt("통과율", 9)
        for name in ADDRESSEE_TYPES:
            header += name.replace("_", "")[:11].rjust(13)
        print(header)
        for s in summaries:
            bucket = s["addressee"]
            row = s["model"][:30].ljust(30) + _fmt(bucket["scored"], 7) + _fmt(bucket["hits"], 7)
            row += ("-" if bucket["rate"] is None else f"{bucket['rate']:.0%}").rjust(9)
            for name in ADDRESSEE_TYPES:
                counts = bucket["by_type"][name]
                row += ("-" if not counts["n"] else f"{counts['hits']}/{counts['n']}").rjust(13)
            print(row)
        for s in summaries:
            failures = s["addressee"]["failures"]
            ids = ", ".join(f"{f['case_id']}({f['type']})" for f in failures)
            print(f"  {s['model']}: 실패 {len(failures)}건 — {ids or '없음'}")
    print("  · receive_reversal=받은 축하·감사·응원 되돌려주기 / agent_reversal=요청·핀잔을 시청자에게 넘기기")
    print("  · situation_blind=자기 방송·자기 존재 상황 오인 / third_party_absorb=제3자 이야기 1인칭 흡수")
    print(f"  · {ADDRESSEE_NOTE} 사이드카에 없는 케이스는 채점 대상이 아니다")
    print()

    categories = sorted({c for s in summaries for c in s["by_category"]})
    basis_label = "완료 p50" if any(not s.get("streaming", True) for s in summaries) else "TTFT p50"
    print(f"── 카테고리별 (통과율 / {basis_label} / 자수 p50) " + "─" * 52)
    print("category".ljust(16) + "".join(s["model"][:26].rjust(28) for s in summaries))
    for category in categories:
        row = category.ljust(16)
        for s in summaries:
            bucket = s["by_category"].get(category)
            if not bucket:
                row += "-".rjust(28)
                continue
            rate = bucket["pass_rate"]
            row += (
                f"{'-' if rate is None else format(rate, '.0%')} / "
                f"{bucket['latency_p50']} / {bucket['char_p50']}"
            ).rjust(28)
        print(row)
    print()

    print("── 실패 " + "─" * 88)
    for s in summaries:
        if s["n_failed"]:
            print(f"  {s['model']}: {s['n_failed']}건 — {s['failures']}")
        else:
            print(f"  {s['model']}: 실패 0건")
    print(line)


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", help="OpenAI 호환 base URL (예: https://host:11439/v1)")
    parser.add_argument("--token", help="Bearer 토큰. 없으면 env AIRI_REMOTE_TOKEN 사용")
    parser.add_argument("--models", default="", help="콤마 구분 모델 id")
    parser.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=90.0, help="요청당 타임아웃 초 (기본 90)")
    parser.add_argument("--max-tokens", type=int, default=160)
    parser.add_argument("--baseline-reps", type=int, default=5, help="바닥선 측정 횟수 (0=끔)")
    parser.add_argument("--categories", help="콤마 구분 카테고리 필터")
    parser.add_argument("--limit", type=int, help="카테고리 무관 앞에서 N건만")
    parser.add_argument("--insecure", action="store_true", help="TLS 검증 끄기(자체서명 인증서)")
    parser.add_argument(
        "--stream",
        choices=("auto", "on", "off"),
        default="auto",
        help="auto(기본)=스트리밍 시도 후 서버가 거부하면 비스트리밍 자동 전환 / on=강제 / off=비스트리밍",
    )
    parser.add_argument("--dry-run", action="store_true", help="네트워크 없이 경로 검증")
    parser.add_argument(
        "--dry-run-no-stream",
        action="store_true",
        help="dry-run 에서 '스트리밍 미지원 서버'를 흉내내 auto-fallback 경로를 검증",
    )
    parser.add_argument("--proxy-source", help="ollama_proxy.py 경로 — 시스템 프롬프트 drift 검증")
    parser.add_argument(
        "--contract",
        choices=("off", "on"),
        default="off",
        help="B4c 방송 발화 계약 블록 부착 여부. off(기본)=기존 프롬프트 그대로",
    )
    parser.add_argument(
        "--protocol",
        choices=PROTOCOL_CHOICES,
        default="raw",
        help=(
            "채점 대상. raw(기본)=응답 원문 그대로 / operational=게이트 경로 운영 프로토콜"
            "(<|ACT ...|> 마커·선반응 ACK)을 분리한 본문으로 채점"
        ),
    )
    args = parser.parse_args(argv)

    contract_block = build_broadcast_contract_block() if args.contract == "on" else ""

    fixtures = load_fixtures(Path(args.fixtures))
    items = fixtures["items"]
    if args.categories:
        wanted = {c.strip() for c in args.categories.split(",") if c.strip()}
        items = [i for i in items if i["category"] in wanted]
    if args.limit:
        items = items[: args.limit]
    if not items:
        raise SystemExit("선택된 픽스처 항목이 0건이다")

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not models:
        if not args.dry_run:
            raise SystemExit("--models 가 필요하다")
        models = ["dry-midm", "dry-motif"]

    prompt_check = {"checked": False}
    if args.proxy_source:
        prompt_check = verify_repo_prompt(Path(args.proxy_source))
        if not prompt_check.get("matches"):
            print("[warn] 레포 AIRI_SYSTEM_PROMPT 와 임베드 사본이 다르다", file=sys.stderr)

    token = args.token or os.environ.get("AIRI_REMOTE_TOKEN")
    if not args.dry_run:
        if not args.base_url:
            raise SystemExit("--base-url 이 필요하다")
        if not token:
            print("[warn] 토큰 없음 — 401 이 예상된다면 그대로 기록된다", file=sys.stderr)

    results: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for model in models:
        transport: Any
        if args.dry_run:
            transport = DryRunTransport(
                stream_mode=args.stream, server_streams=not args.dry_run_no_stream
            )
        else:
            transport = HttpTransport(
                args.base_url, token, verify=not args.insecure, stream_mode=args.stream
            )
        try:
            result = run_model(
                transport,
                model,
                items,
                reps=args.reps,
                timeout=args.timeout,
                max_tokens=args.max_tokens,
                baseline_reps=max(0, args.baseline_reps),
                contract_block=contract_block,
                protocol=args.protocol,
            )
        finally:
            if hasattr(transport, "close"):
                transport.close()
        results.append(result)
        summaries.append(summarize(result))

    payload = {
        "schema_version": SCHEMA,
        "generated_at": now_iso(),
        "measurement_scope": MEASUREMENT_SCOPE,
        "scoring_note": "자동 마커는 휴리스틱이다. 인간 검수를 대체하지 않는다.",
        "config": {
            "base_url": args.base_url if not args.dry_run else "dry-run",
            "models": models,
            "reps": args.reps,
            "max_tokens": args.max_tokens,
            "timeout_s": args.timeout,
            "baseline_reps": args.baseline_reps,
            "token_supplied": bool(token),
            "dry_run": args.dry_run,
            "tls_verify": not args.insecure,
            "keepalive": "모델별 httpx 클라이언트 1개 재사용 (연결 재사용 유지)",
            "stream_mode_requested": args.stream,
            "stream_mode_used": {
                r["model"]: (r.get("transport_mode") or {}).get("streaming_used") for r in results
            },
            "stream_fallback_events": [
                event
                for r in results
                for event in (r.get("transport_mode") or {}).get("fallback_events", [])
            ],
        },
        "prompt": {
            "system_prompt_sha256": sha256(AIRI_SYSTEM_PROMPT),
            "broadcast_frame_sha256": sha256(BROADCAST_FRAME),
            "combined_system_sha256": sha256(build_system_content(contract_block)),
            "user_prefix": USER_PREFIX,
            "repo_prompt_check": prompt_check,
            "system_prompt": AIRI_SYSTEM_PROMPT,
            "broadcast_frame": BROADCAST_FRAME,
            "contract": args.contract,
            "contract_block_sha256": sha256(contract_block) if contract_block else None,
            "contract_block": contract_block or None,
        },
        "fixtures": {
            "path": str(Path(args.fixtures).resolve()),
            "schema_version": fixtures.get("schema_version"),
            "selected": len(items),
            "total": len(fixtures["items"]),
        },
        "addressee_checks": addressee_metadata(),
        "reference_lines_ms": [
            {"label": label, "value_ms": value, "source": note} for label, value, note in REFERENCE_LINES
        ],
        "summaries": summaries,
        "results": results,
    }
    if args.protocol != "raw":
        # raw 는 키를 남기지 않는다 — 기존 결과 JSON 을 바이트 그대로 유지한다.
        # 키 부재 = raw 로 읽는다.
        payload["config"]["protocol"] = args.protocol
    output = Path(args.output)
    atomic_write(output, payload)
    print_report(summaries, {"items": items}, args.reps, args.contract, args.protocol)
    print(f"\n원 응답 전문 포함 결과: {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
