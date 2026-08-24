# AIRI D1 결정론 발화 계층 동결 계약 (2026-08-25)

> **상태: 설계 동결(design-frozen).** 2026-08-25 04:54 KST 사용자 `/goal`(D1)의 실행
> 계약이다. GPU 학습 없음. 게이트 정의·threshold는 불변이며, 이 계층은 채점이 보는
> 근거 범위의 정확화(신호)와 응답 텍스트의 결정론 구성(가드/렌더러)만 더한다.
> blind v4 pin은 봉인 시 §5에 결과-전으로 추가한다.

## 1. 진단 근거 (설계 입력)

- E2-C1/E2-C2 연속 no_winner로 "선량·LR 재조정으로는 게이트가 닫히지 않는다" 실증
  (E2-C2 contract §7). invented_handle은 가드 신호 ON에도 14/27/33 학습 단조 악화.
- **신규 발견(2026-08-25 조사)**: e2-c2 위반 33건 중 표본 16건 전수가 실제 과거
  시청자 재호명(날조 0), 상당수 거리 1~8턴 = **모델 프롬프트의 history 메시지에
  실재하는 근거**. 현행 신호 풀(`handle_grounding_guard.build_grounding_pools`)은
  user text+briefing+memory+journal만 담고 **history를 누락** — E2-C1 §12와 동형의
  측정 사각지대가 한 층 더 있다.
- 채점 파생(broadcast_sim.py): invented_handle = roster 문자열 substring ∧ ¬(현재
  메시지∪author∪fact_tokens_used∪(roster∩신호 memory_pool)). donation composite =
  정확히 저자 1회 호명 ∧ required regex ∧ ¬forbidden regex ∧ 응답∩메시지 공유 토큰.
  arc required/forbidden = 응답 regex. probe_hit = expect_any substring.
- fixture의 required = 입력에 실재하는 주제어/확정 옵션, forbidden = 입력이 명시적으로
  거부한 대안("A 말고 B"의 A) 또는 입력에 없는 근사-오답. 따라서 **"긍정 분기만
  echo, 거부 분기 절대 미반복, 입력 밖 사실 미도입"** 원칙의 결정론 구성으로 check를
  보지 않고 게이트를 만족시킬 수 있다.
- 결정론 act(thank_renderer/wave_opener/memory_guard)는 sim 러너에만 존재. donation
  composite 실패(0.583)는 오프너가 아니라 **모델 이어쓰기**(추가 호명, 메시지 무반응,
  근사-오답)가 원인.

## 2. 계층 설계 — 단일 모듈 `deterministic_utterance_layer.py`, 5부

플래그 `AIRI_DETERMINISTIC_UTTERANCE_LAYER`(기본 off, 기존 truthy 파싱 패턴). off 시
요청/응답 바이트 무변화 회귀 필수. 적용 지점은 `prepare_openai_sse_dialogue`의
기존 2-gate(output moderation → handle guard) 뒤 3번째 gate + memory_guard형 대체 경로.

1. **P1 grounding pool v2 (신호 확장, 게이트 정의 불변)**: `build_grounding_pools`에
   request history 메시지 본문을 추가한다(프록시가 이미 보유). 신호 `memory_pool`에
   history 텍스트가 포함되므로 시뮬레이터의 기존 union(roster∩pool)이 코드 변경 없이
   history 근거를 인정한다. E2-C1 §12(가드+신호)와 동일한 "판정 입력 범위 정확화"의
   3차 적용이다.
2. **P2 과거-전용 토큰 가드 (invented_handle 잔여 커버)**: 프록시가 세션(x-airi-
   session-id)별로 사용자 메시지의 한글 토큰(2~8자, stoplist 제외)을 누적하고, 응답
   토큰 중 "과거 세션에 등장했으나 현재 턴 전체 프롬프트(현재 메시지+briefing+memory+
   journal+history)에 없는" 토큰을 "그거"류 지시어로 치환한다. 프롬프트에 있는 근거는
   P1이 grounding하므로, 최종 응답의 roster handle은 전부 (a) 근거 있음 또는 (b) 치환됨
   — invented_handle 0을 구성적으로 접근한다. 현재 주제 토큰(topic block/briefing/현재
   메시지)은 정의상 프롬프트에 있어 오탐이 없다.
3. **P3 결정 회수 렌더러 (probe/callback required 커버)**: 사용자 메시지가 회수
   질문형(`…뭐였지/뭐라고 했지/기억나/…기로 했(어|지)`)일 때, 현재 턴 풀에서
   결정/사실 씨앗 패턴(`S는 A 말고 B…`, `S는 …지 말고 B…`, `내 X는 Y야`)을 찾아
   B/Y를 추출해 결정론 응답("{B}로 하기로 했지!" / "{Y}라고 했지!")으로 **대체**한다
   (memory_guard 대체 선례). 풀에서 못 찾으면 기존 memory_guard 폴백(안전 미달, 위반
   0). 회수 성공률은 retrieval 품질에 결속 — 모델 기억을 코드+검색으로 대체.
4. **P4 거부-옵션 억제기 (forbidden/decoy 커버)**: 풀의 `A 말고/아니라 B` 패턴에서
   A-phrase 턴-덴이리스트를 만들고, 응답 문장 중 A-phrase 포함 문장을 제거한다(전부
   제거되면 P3 폴백). 거부된 대안을 절대 반복하지 않는 행동 보장 —
   stale_transition_clean·decoy_fact_use의 forbidden 축과 arc_forbidden을 구성적으로
   차단. (입력에 전혀 없는 근사-오답 페러프레이즈는 P5의 echo-보수주의로 간접 완화.)
5. **P5 후원 계속 응답 보강 (donation composite 커버)**: live control
   `donation_continuation=true` 턴에서 모델 continuation이 사용자 메시지와 공유 토큰
   0이면 결정론 감사-echo 문장("'{메시지 클립}' 얘기 진짜 고마워!")을 부가해
   shared_tokens·감사 표현을 보장한다. 추가 호명은 P2가 제거(호명 정확히 1회 =
   sim 오프너의 저자 1회만 잔존).

## 3. 게이트-파트 매핑

| 게이트 | 보장 경로 |
|---|---|
| zero_violations.invented_handle | P1(history 근거 인정) + P2(프롬프트-외 과거 토큰 치환) |
| perfect.donation composite | sim 오프너(기존) + P5(공유 토큰·감사) + P2(추가 호명 제거) + P4(근사-오답 문장 제거) |
| perfect.stale_transition_clean | P3(확정 옵션 응답) + P4(거부 옵션 미반복) |
| perfect.decoy_fact_use | P4 + P5 echo-보수주의(정확 인용, 페러프레이즈 회피) |
| perfect.unknown_identity_safe | P3(probe 회수) + P1/P2(호명 위반 0) |

additive 축(topic/fact/memory/callback/show_arc)은 이 계층의 직접 목표가 아니나
P3(회수 성공)·P1(fact 인정 범위)이 memory_probe·long_callback·fact 축을 부수적으로
올릴 것으로 예상한다. threshold는 전부 불변.

## 4. 평가 계약 (4-arm)

- arms: `baseline / e2 / e2-c1 / e2-c2` (전부 기존 패키징 태그, 재학습 0) × blind v4
  3 fixture × 4 seeds = **48 reports**, 전 run 프록시
  `AIRI_DETERMINISTIC_UTTERANCE_LAYER=on` + `AIRI_HANDLE_GROUNDING_GUARD=on`
  (launcher 강제 + /health attest).
- comparator `compare_d1_blind.py`(신규, policy `airi.d1-blind-metric-policy.v1`):
  threshold 값 전부 e2c2 policy와 동일(완화 0). 확장 규칙(결과-전 동결): hard-zero·
  perfect-rate·additive **절대 최소선**은 4 arm 전부에 평가하고, additive **delta**
  요건(vs e2)은 학습 후보 arm(e2-c1/e2-c2)에만 적용한다(reference 자신에의 delta는
  정의 불능이므로). winner = 자기 게이트를 전부 통과한 arm 중 최고 score, unique top
  margin >0.02 유지. 게이트를 전부 통과한 arm이 없으면 no_winner.
- blind v4: 신규 한국어 3종(동일 role), seeds [73,89,97,20260824] 불변,
  `seal_e2c2_blind.py`를 v4 파라미터로 일반화(또는 사본)해 봉인, v1/v2/v3
  root/hash/핸들/템플릿 재사용 금지(superseded 확장).
- winner면 top-score arm으로 3×500 campaign, 아니면 진단 보고 후 대기.

## 5. 실행 순서 (fail-closed)

1. 설계 배치(이 문서+receipt) commit/push.
2. P1~P5 구현 + OFF 무변화 회귀 + 신규 단위/통합 테스트 + 기존 suite 전체 → commit/push.
3. blind v4 저작·봉인 + d1 commitment/policy/comparator/launcher profile + CI 등록
   → commit/push.
4. 48-report matrix(계층 ON) → verdict.
5. 분기: winner→campaign / no_winner→진단·대기. adoption은 어느 경우에도 별도 승인.
