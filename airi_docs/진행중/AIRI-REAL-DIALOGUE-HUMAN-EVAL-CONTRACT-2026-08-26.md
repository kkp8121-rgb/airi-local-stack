# AIRI 실제 대화 사람 채점 평가 계약 (2026-08-26)

> **상태: 사용자 승인(2026-08-26) — 앞으로 유일한 채택 게이트.** 합성 fixture blind 매트릭스는
> 회귀 도구로만 남고, 모델·프롬프트·결정론 계층·파인튜닝의 채택 여부는 이 계약의 사람 채점
> 결과로만 결정한다. 배경과 근거는 `AIRI-REALITY-CHECK-AND-FINETUNE-REVIEW-2026-08-26.md`.

## 1. 입력 — 실제 대화만

- 대상: (a) 비공개 테스트 방송 1회 이상, (b) 사용자가 AIRI 로컬 스택과 직접 나눈 채팅 세션, 또는
  (c) 2026-08-26 사용자 지시로 추가 — 공개 저스트 채팅 방송(치지직/유튜브 원본 라이브 아카이브)의 채팅
  리플레이를 가명화해 로컬 스택에 재생한 세션. (c)는 시청자 발화는 실제이지만 원 방송 맥락에 묶인 메시지가
  섞이므로 채점 시 "원 방송 맥락 의존" 코멘트로 구분한다. 합성 fixture·템플릿 시청자 출력은 입력이 아니다.
- 최소 규모: **50턴**, 목표 100턴(user/assistant 쌍 기준). 여러 세션을 합쳐도 된다.
- 출처: 프록시 memory DB의 `conversation_message` journal(세션·턴·역할·본문). 스택은
  `start-airi-local-stack.ps1 -MemoryDbPath <경로>`로 DB 위치를 지정하며, 비워 두면 기본 경로
  `ollama-proxy/runtime/airi-memory.sqlite3`(프록시 env `AIRI_MEMORY_DB`)를 쓴다. 상세는
  `ollama-proxy/eval/human_review/README.md`.
- 개인정보: 실제 시청자 표시명·채널 ID·userIdHash·계정 정보는 저장소·문서·프롬프트에 넣지 않는다. 공개 채팅은
  `import_public_chat.py`가 HMAC 가명(`v`+8자)으로 바꾼 뒤에만 재생하며 원본 JSON은 저장소 밖에 둔다. export JSONL과 채점
  결과 JSON은 `D:\AIRI-Models\airi-human-eval\<날짜>\` 같은 저장소 밖 경로에만 둔다. 요약
  (`summarize_ratings.py`) 출력만 content-free이므로 문서에 인용할 수 있다.

## 2. 도구 (`ollama-proxy/eval/human_review/`)

| 단계 | 명령 | 산출물 |
|---|---|---|
| 1 export | `python export_session_dialogue.py --db <memory.sqlite3> --list` → `--session <id> --output <외부경로>.jsonl` | 턴별 user/assistant JSONL (저장소 밖) |
| 2 sheet | `python build_rating_sheet.py --input <jsonl> --output <외부경로>.html --rater <이름>` | 단일 파일 채점 HTML(의존성 0) |
| 3 rate | 브라우저에서 HTML 열고 채점 → "JSON 내보내기" | `airi.human-rating.v1` JSON |
| 4 summary | `python summarize_ratings.py --ratings <json>... --output <summary.json> --markdown <path>` | content-free 요약 |

## 3. 채점 기준 (턴당, 1~5 정수)

| 축 | 1 | 3 | 5 |
|---|---|---|---|
| 방송다움 | 챗봇/설명문 같다 | 방송 말투지만 흐름이 끊긴다 | 실제 스트리머가 채팅에 답하는 것 같다 |
| 맥락 유지 | 직전 대화·브리핑을 무시 | 일부만 반영 | 이번 턴과 앞선 맥락을 정확히 이어 받는다 |
| 반응 적절성 | 시청자가 말한 것과 무관 | 대체로 답하지만 빠진 부분 있음 | 시청자가 실제로 말한 것에 정확히 반응 |
| 말투 규칙 | 존댓말/리스트/이모지/영어 등 위반 | 경미한 어색함 | 반말·길이·형식 전부 자연스럽다 |
| 사실성 | 없는 사실·이름·감정을 만든다 | 모호한 단정 | 근거 있는 말만 한다 |

플래그: `critical_failure`(안전·치명적 오류), `silence_or_filler`(침묵 폴백·무의미 대꾸),
`invented_name`, `polite_violation`(자동 힌트, 수정 가능), 자유 코멘트.

## 4. 판정 규칙 (제안값 — 첫 기준선 측정 뒤 사용자가 확정)

- 기준선: 현재 운영 구성(stock Mi:dm 2.0 Mini Q4 + 결정론 계층 ON + 브리핑)으로 먼저 50~100턴을
  채점해 기준선을 만든다. 기준선 없이는 어떤 후보도 비교하지 않는다.
  **확정 기준선(2026-08-26 14:15 KST, run 04, 사람 99턴)**: 방송다움 1.87 · 맥락 1.58 · 반응 1.83 · 말투 3.60 ·
  사실성 2.75, critical 7.1%, silence_or_filler 45.5%, 5축≥4 0% — `진행중/AIRI-REAL-CHAT-REPLAY-RUN04-2026-08-26.md` §2-1.
- 후보(프롬프트·계층·모델 교체·파인튜닝) 채택 조건: 같은 입력 세트에서
  1. `critical_failure` 0, `silence_or_filler` 비율 기준선 이하,
  2. 5축 평균이 기준선 대비 +0.3 이상이고 어떤 축도 −0.2 이하로 떨어지지 않음,
  3. "5축 모두 ≥4"인 턴의 비율이 기준선 이상,
  4. 채점자 2명 이상이면 축별 평균 절대 차이 ≤1.0(그 이상이면 기준을 다시 쓴다).
- **돌파 정의(2026-08-26 타계책, `AIRI-BREAKTHROUGH-PLAN-2026-08-26.md` §1)**: 3축 합성(방송다움·맥락 유지·반응 적절성 평균) ≥ 3.0,
  critical 0, silence_or_filler ≤ 25%, 말투 ≥ 3.5, 사실성 ≥ 기준선. 5축 평균으로 판정하지 않는다. 후보당 복제 ≥ 2회
  중 사람이 1회 채점하며, 자동 시그니처("음" 오프너·"?" 종결·완전 에코·첫 2어절 고유율)는 채점자에게 표시만 한다.
- 파인튜닝 재개는 위 조건 외에 실태 문서 §4.2의 4개 조건(실제 코퍼스, 채점 세트 동결,
  결정론으로 못 닫는 행동 실측, 일반 능력 게이트 ≤2%p)을 모두 충족할 때만 검토한다.

## 5. 절차

1. 사용자가 세션을 진행한다(테스트 방송 또는 직접 채팅). 스택은 memory ON으로 띄운다.
2. 세션 종료 후 export → sheet 생성 → 채점(가능하면 2명) → summary. 후보 비교 run은 같은 입력으로 복제 ≥ 2회
   재생하고(자동 시그니처 평균·SD 기록) 그중 1회를 사람이 채점한다. 한 run에는 한 변수만 바꾼다.
3. summary 수치와 세션 메타(날짜·턴 수·구성 SHA/태그)를 `AIRI-ROADMAP-LOG.md`와 대시보드에
   기록한다. 본문·코멘트는 기록하지 않는다.
4. 결정: 기준선 확정 → 다음 개선 후보 한 가지를 정해 같은 절차로 비교한다.

## 6. 하지 않는 것

- 합성 fixture로 이 채점을 대체하지 않는다. 정규식 게이트·자동 시그니처로 사람 채점을 대체하거나 kill 판정에
  쓰지 않는다(표시 전용).
- 채점 결과를 보고 rubric·판정 규칙을 사후에 바꾸지 않는다(변경은 다음 라운드부터).
- 실제 대화 본문·시청자 식별 정보를 Git·문서·채팅에 넣지 않는다.
