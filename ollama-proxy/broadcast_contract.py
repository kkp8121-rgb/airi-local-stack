"""B4c 방송 발화 계약 — 관찰 연구 실측 패턴을 프롬프트 규범으로 옮긴다 (기본 OFF).

`AIRI_BROADCAST_CONTRACT` 가 켜졌을 때만 시스템 프롬프트 뒤에 계약 블록을 덧붙인다.
꺼져 있으면 입력 문자열을 그대로 돌려주므로 운영 요청 프롬프트는 바이트 단위로
변하지 않는다(greybox — 이 코드를 그대로 pull 해도 기본 무영향).

실증 근거: `airi_docs/참조/AIRI-BROADCAST-OBSERVATION-STUDY-2026-08-14.md`
(4인 트랜스크립트 실측 — §2 공통 패턴 P1~P10, §5 기존 설계와의 차이표,
§6 AIRI 파라미터 후보). 아래 상수 테이블의 값은 전부 §6 후보값이며 확정값이
아니다(사용자 확인 경유 전).
"""
from __future__ import annotations

import os
from collections.abc import Mapping

BROADCAST_CONTRACT_ENV = "AIRI_BROADCAST_CONTRACT"

# 켜짐으로 읽을 값만 열거한다(default-deny). 미설정·0·false·off·그 외 = 꺼짐.
BROADCAST_CONTRACT_ON_VALUES = frozenset({"1", "true", "on", "yes"})

# ---------------------------------------------------------------------------
# 파라미터 테이블 — 관찰 연구 §6 후보값. 프롬프트 문장에 숫자를 직접 쓰지 않고
# 이 테이블을 참조한다(매직넘버 금지).
# ---------------------------------------------------------------------------
BROADCAST_CONTRACT_PARAMS: dict[str, dict[str, object]] = {
    # 4인 공통 지배 구간(≤2초 리액션 조각 32~75%). 현행 10~45자를 유지하되
    # 문장 수만 1~2로 열어 낭독(인용)과 응답을 한 발화에 담을 수 있게 한다.
    "reaction_fragment": {
        "min_chars": 10,
        "max_chars": 45,
        "min_sentences": 1,
        "max_sentences": 2,
        "source": "관찰 연구 §6 — 리액션 조각 길이 1~3초(10~45자 현행 유지), 4인 공통 지배 구간",
    },
    # 긴 블록은 명분이 있을 때만 나온다. 한국 3인 최장 33~59초,
    # 359초 1건은 감상이라는 명분이 붙은 우이 사례.
    "narration_block": {
        "min_seconds": 15,
        "max_seconds": 60,
        "requires_justification": True,
        "source": "관찰 연구 §6 — 나레이션 블록 15~60초, 명분(사연·감상·중계) 필수",
    },
    # 낭독→응답은 한 단위다. "낭독 → 침묵 → 답변"으로 분리되면 대화감이 붕괴한다(§1).
    "readout_to_response": {
        "max_ms": 1300,
        "source": "관찰 연구 §6 — 낭독→응답 개시 ≤1.3초 (리제 1.06s·아이네 1.2s 중앙값)",
    },
    "undeclared_silence": {
        "conservative_seconds": 10,
        "max_seconds": 20,
        "source": "관찰 연구 §6 — 무선언 무음 상한 10초(보수)~20초 (아이네 27s 최장·30s+ 0회)",
    },
    "declared_absence": {
        "max_seconds": 120,
        "requires_declaration": True,
        "source": "관찰 연구 §6 — 이탈 허용: 선언+복귀 대사 시 ~120초 (리제 102s·탬 99.7s)",
    },
    "name_call": {
        "scope": "donation_or_special",
        "max_per_hour": 10,
        "source": "관찰 연구 §6 — 호명 빈도: 후원·특별시만(시간당 ~10회 이하), 탬 13건 전부 후원",
    },
    "tag_question": {
        "min_ratio": 0.05,
        "max_ratio": 0.10,
        "source": "관찰 연구 §6 — 태그의문 비율 발화의 5~10%대 (탬 4.7%, 리제 시간당 ~50회)",
    },
    "opening": {
        "max_seconds": 30,
        "source": "관찰 연구 §6 — 오프닝 30초 내(인사+오늘 1줄+개시 신호), 아이네 17초 실증",
    },
    "closing": {
        "min_seconds": 60,
        "max_seconds": 900,
        "requires_next_promise": True,
        "source": "관찰 연구 §6 — 클로징: 다음 약속 포함 1~15분 가변 (아이네 40s ↔ 리제 15분)",
    },
    # 계약 블록이 컨텍스트를 잠식하면 안 된다. 운영 proxy 는 num_ctx 2048 로 돈다.
    "contract_block": {
        "target_max_chars": 600,
        "hard_max_chars": 800,
        "source": "운영 제약 — proxy num_ctx 2048 (ollama_proxy.NUM_CTX)",
    },
}


def _build_block() -> str:
    """계약 블록 원문을 조립한다. 숫자는 전부 파라미터 테이블에서 온다.

    문장 수를 1~2로 여는 것은 `AIRI_SYSTEM_PROMPT` 의 "한 문장" 기본값을
    방송 상황에서만 완화하려는 의도다(§5 차이표 — 상태별 가변 길이).
    """
    fragment = BROADCAST_CONTRACT_PARAMS["reaction_fragment"]
    return "\n".join(
        [
            "[방송 발화 계약]",
            "시청자 채팅을 짧게 되짚은 뒤 곧바로 네 반응을 붙여. 되짚기와 반응은 한 호흡이니"
            " 끊어서 두 번에 나눠 말하지 마.",
            f"기본은 {fragment['min_chars']}~{fragment['max_chars']}자"
            f" {fragment['min_sentences']}~{fragment['max_sentences']}문장짜리 짧은 반응이다."
            " 사연·감상·상황 중계처럼 길게 말할 명분이 있을 때만 늘려.",
            "인용하거나 설명할 때는 잠깐 서술체로 바꿔도 되지만 네 말은 반말 구어체로 돌아와."
            " 시청자가 존댓말을 써도 따라 하지 마.",
            "가끔 ~잖아·~지?·~거든? 처럼 동의를 구하는 말끝이나 되묻기로 말을 시청자에게 돌려."
            " 매번 하지 말고 어울릴 때만 써.",
            "반박이나 오해에는 타이르지 말고 가볍게 받아쳐.",
            "여러 시청자가 같은 말을 하면 한 문장으로 묶어 정리한 뒤 네 입장을 말해.",
            "닉네임은 후원이나 특별한 순간에만 불러.",
        ]
    )


_BROADCAST_CONTRACT_BLOCK = _build_block()


def build_broadcast_contract_block() -> str:
    """모델에게 주는 방송 발화 계약 프롬프트 블록."""
    return _BROADCAST_CONTRACT_BLOCK


def broadcast_contract_enabled(env: Mapping[str, str] = os.environ) -> bool:
    """계약 게이트 상태. 미설정이면 꺼짐이 기본이다."""
    return str(env.get(BROADCAST_CONTRACT_ENV, "")).strip().lower() in BROADCAST_CONTRACT_ON_VALUES


def apply_broadcast_contract(system_prompt: str, enabled: bool) -> str:
    """꺼져 있으면 입력을 그대로 돌려준다(바이트 동일). 켜져 있을 때만 뒤에 붙인다."""
    if not enabled:
        return system_prompt
    return system_prompt + "\n\n" + build_broadcast_contract_block()
