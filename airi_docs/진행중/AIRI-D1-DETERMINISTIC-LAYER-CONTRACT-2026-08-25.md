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

## 6. 결과와 진단 (2026-08-25, 결과-후 절)

48-report matrix는 12:38:14 KST에 exit 0으로 완주했다(48/48 reports·health·run-contract·
packets·runtime, environment attestation `airi.d1-environment-attestation.v1`,
comparator `airi.d1-blind-comparison.v1`). **결과는 `winner=null`(45개 게이트 실패)이며
goal의 `no_winner` 경로에 따라 3×500 campaign은 실행하지 않았다.**

| 지표 | baseline | e2 | e2-c1 | e2-c2 |
|---|---:|---:|---:|---:|
| weighted score | 0.105751 | 0.109299 | **0.116965** | 0.108908 |
| `invented_handle` 위반 | 5 | 4 | 8 | 6 |
| `unknown_identity_safe` | 0.0 | 0.0 | 0.0 | 0.0 |
| `stale_transition_clean` | 0.200 | 0.225 | 0.300 | 0.300 |
| donation composite | 0.292 | 0.250 | 0.375 | 0.458 |
| `decoy_fact_use`(목표 0) | 0.050 | 0.038 | 0.050 | 0.025 |
| `long_callback` / `complete_show_arc` / `memory_probe` | 0.0 | 0.0 | 0.0 | 0.0 |

**이 숫자는 계층 성능이 아니라 계측 결함을 먼저 반영한다.** 채점 후 blind 원문을
열람해 분류한 결과는 다음과 같다(전량 재현 가능, comparator rate 소수점 일치 검증됨).

1. **프록시 오류 응답이 전 arm 턴의 33.9~35.3%** 다(`LOCAL_ERROR_DIALOGUE`). 이는
   D1 고유가 아니라 E2-C1 30.3~31.6%, E2-C2 37.2~38.6%로 **세 blind 라운드 공통**이며
   `summary.fallback`이 세지 않아 지금까지 한 번도 보고된 적이 없다.
2. **P3 `answer_recall_question` 과발동(D1 신규 회귀)**: `continuity_callback` 320행
   중 176행(55%)을 근거 없음 → `_RECALL_FALLBACK`으로 대체했다. 프록시 오류 117행을
   더하면 실제 모델 발화는 27행(8.4%)뿐이고, 이것이 `long_callback`·
   `complete_show_arc`를 정확히 0.0으로 만든 직접 원인이다.
3. **`memory_probe` 160행 중 152행(95%)이 프록시 오류, 실제 발화 0행** — 이 축은 D1
   이전에도 측정되지 않고 있었다(E2-C2 36~38/40 동일).
4. `unknown_identity_safe`의 분모 12행은 **전 arm 12/12가 차단된 턴**이라 0.0은
   모델 판정이 아니라 측정 불능이다.
5. P4는 decoy 위반을 3라운드 최저(0.025~0.05)로 줄였으나 0에 못 미쳤고, P5는 측정
   가능한 donation 턴에서 live rate 0.688(e2-c2)로 가장 높다. `invented_handle`은
   85% 감소했으나 감소분 일부는 발화 부재의 산술 효과이므로 가드 공로로 승격하지
   않는다.

**미확정**: 프록시 오류의 근본 원인은 프록시 stdout이 보존되지 않아 특정하지 못했다.
코드상 유력 후보는 memory 경로(`prepare_memory_body` → `fetch_local_dialogue`)의
포괄 예외 처리다. 확정에는 프록시 stdout을 남기는 짧은 재현 실행이 필요하며 GPU
학습은 필요 없다.

**동결 유지**: §1~§5의 설계·게이트 정의·threshold·seed·fixture는 이 결과로 변경하지
않는다. hard gate 완화 0, 운영 채택 0(`adoption_authorized=false`). 다음 라운드
방향은 사용자 결정 사항이며 자동으로 시작하지 않는다.

## 7. 재측정 d1v5 결과와 진단 (2026-08-25 21:22, 결과-후 절)

M1·M2 계측 수리(프록시 오류 기록·`service_error` 지표·P3 probe/confirmation·num_ctx 4096·브리핑
마커) 뒤 새 blind v5(`airi-d1-blind-freeze-20260825-v5`)로 같은 4-arm 48-report matrix를 정확히
한 번 재실행했다. 48/48 완주, 두 런타임 플래그 48/48 attest, `context_exceeded 0`. comparator는
v4 하드코딩 verifier에 막혀 launcher 단계에서 실패했고, verifier를 v5 root까지 받도록 고친 뒤
동일 인자로 오프라인 재실행해 verdict를 발행했다(`summary.json` 미생성 기록).

| 지표 | baseline | e2 | e2-c1 | e2-c2 |
|---|---:|---:|---:|---:|
| weighted score | 0.340 | 0.345 | 0.364 | **0.373** |
| `invented_handle` | 7 | 17 | 11 | 9 |
| `unknown_identity_safe` | 0.917 | **1.0** | **1.0** | **1.0** |
| `stale_transition_clean` | 0.375 | 0.300 | 0.425 | 0.575 |
| donation composite | 0.250 | 0.375 | 0.208 | 0.333 |
| `decoy_fact_use`(목표 0) | 0.063 | 0.025 | 0.025 | 0.013 |
| memory_probe / topic_anchored | 0.90 / 0.52 | 0.90 / 0.51 | 0.88 / 0.52 | 0.90 / **0.65** |
| long_callback / complete_show_arc | 0.04 / 0.06 | 0.02 / 0.06 | 0.06 / 0.08 | 0.06 / 0.09 |

**verdict `winner=null`**(실패 게이트 38). 계측은 이번에 실제로 작동했다 — `service_error` 0,
memory_probe 36/40, `unknown_identity_safe`가 학습 arm에서 닫혔다.

**진단(P2~P5 귀책)**:
1. **결정론 계층은 운영 경로에서 근거를 받지 못한다(배선 결함).** live-broadcast 프로토콜에서
   브리핑과 후원 계약은 `broadcast_context` → `airi_broadcast_context` system note로 **주입된
   body**에만 존재하고, `build_layer_inputs`는 주입 전 `context.original_messages`를 받는다.
   따라서 P3는 continuity callback 80행 중 62~65행을 폴백으로 덮었고(`released 0/80`), P5의
   `donation_turn`은 한 번도 참이 아니었으며(donation composite miss 29~39/52 전부
   `shared_tokens=false`), P4의 결정 풀도 비어 있었다. 714e196의 시뮬레이터 마커는 live 모드에서
   전송되지 않는 `system_content`에 붙어 효과가 없었다. 이 결함은 D1(v4)에도 동일하게 있었다.
2. **P3 추출 정규식**: v5 arc 12개 중 5개("가득 말고 팔 할만", "한 번씩 말고 두 번씩" 등 1글자
   토큰·띄어쓴 구)는 `_REJECTED_BRANCH_RE`가 못 잡는다(오프라인 재현 7/12 추출).
3. **`invented_handle`은 대부분 채점 artefact**: 전부 `question` 행이고 v5 viewer handle이 주제
   명사 합성어(채밀칼날·훈연기연기·태엽감기…)라 주제 발화가 roster 부분일치에 걸렸다. blind
   저작 결함이며 가드 범위 밖이다.
4. **decoy**: "A가 아니라 B" 부정 교정문이 금지 패턴에 걸린 사례가 다수 — P4는 풀이 비어
   드롭하지 못했고 채점기는 부정 문맥을 구분하지 않는다.

**동결 유지**: §1~§5의 게이트 정의·threshold·seed는 불변. hard gate 완화 0, campaign 0,
adoption 0. **다음 라운드(주입 후 메시지/`context_note`를 계층 입력에 전달, runtime이 브리핑
마커를 붙임, P3 정규식 확장, live 경로 통합 테스트, 새 blind v6 — handle은 주제 어휘와 분리)는
사용자 결정 사항이며 자동으로 시작하지 않는다.**

## 8. M4 blind v6 재측정 결과와 진단 (2026-08-26 03:22, 결과-후 절)

M4 배선 수정과 정규식 확장 뒤 새 blind v6로 같은 4-arm 48-report matrix를 정확히 한 번
실행했다. wrapper exit-code receipt는 `0`, report·health·run-contract·packet 고유 교집합은
48/48이고 duplicate·incomplete는 0이다. 두 결정론 flag는 48/48 before·after `true`,
`context_exceeded`와 `service_error`는 모두 0이며 wrapper·owned PID/listener도 0으로 정리됐다.
summary와 comparator는 `status=pass`, `adoption_authorized=false`다.

| 지표 | baseline | e2 | e2-c1 | e2-c2 |
|---|---:|---:|---:|---:|
| weighted score | 0.465862 | 0.543016 | 0.510247 | **0.557373** |
| failed gate 수 | 6 | 4 | 9 | 10 |
| `invented_handle` 위반 | 2 | **0** | **0** | 3 |
| `unknown_identity_safe` | 0.75 | **1.0** | 0.75 | 0.75 |
| `stale_transition_clean` | 0.475 | 0.50 | 0.475 | 0.50 |
| donation composite | **1.0** | **1.0** | **1.0** | **1.0** |
| `decoy_fact_use`(목표 0) | **0.0** | **0.0** | **0.0** | **0.0** |
| complete_show_arc | 0.2625 | 0.3625 | 0.3125 | 0.3625 |
| viewer_fact_usage | 0.230159 | 0.205306 | 0.267442 | 0.220320 |
| long_callback / memory_probe | 0.650 / 0.700 | 0.766667 / 0.875 | 0.683333 / 0.775 | 0.766667 / 0.850 |

**verdict는 `winner=null`(`no_winner`, 실패 gate 29개)**다. 최고 점수 arm인 e2-c2도 자기
게이트 10개를 통과하지 못했으므로 winner나 retained model로 승격하지 않는다. M4 계약에 따라
3×500 campaign과 자동 후속 라운드는 실행하지 않는다.

**P2~P5 row 귀책**:

1. **P2/P1 호명 보장에는 잔여 구멍이 있다.** `invented_handle`은 baseline 2행과 e2-c2
   3행에서 남았고 전부 `question` 행이다. v6의 handle-topic collision 검사는 0으로 봉인됐으므로
   v5의 주제 부분일치 저작 artefact로 돌릴 수 없다. 다만 identity probe의 실패행에는 invented
   handle이 0이어서 `unknown_identity_safe` 0.75의 직접 원인은 P2가 아니라 P3 probe miss다.
2. **P3 회수/필수 답변이 주된 미폐쇄 축이다.** identity fixture에서 baseline·e2-c1·e2-c2는
   각각 12 probe 중 3개를 놓쳤고 e2만 12/12였다. stale-transition fixture의 40행 중 required
   패턴 miss도 baseline 21, e2 20, e2-c1 21, e2-c2 20이다. 그 결과
   `complete_show_arc` 0.2625~0.3625와 `viewer_fact_usage` 0.205306~0.267442가 절대 최소선에
   못 미쳤고, 후보 arm의 long-callback·memory delta와 legacy memory/fact gate도 닫히지 않았다.
3. **P4의 decoy 억제는 닫혔지만 transition 전체를 닫지는 못했다.** factual fixture의 checked
   80행/arm에서 decoy hit는 전 arm 0이다. transition forbidden hit도 baseline·e2·e2-c1은 0,
   e2-c2만 3이어서 거부 옵션 억제는 대부분 작동했다. `stale_transition_clean`의 큰 공백은
   forbidden 재발보다 P3 required miss가 지배한다.
4. **P5 후원 이어말하기는 닫혔다.** identity fixture donation 24/24 per arm이 호명·수신자·감사·
   메시지 공유 composite를 모두 통과했고, 전체 52 donation/arm도 callout·shared token을 모두
   충족했다. v5의 `donation_turn=false` 배선 결함은 재현되지 않았다.
5. **별도 공통 차단축은 말투 gate다.** `polite` 위반은 baseline 45, 나머지 arm 43이며 공통
   43행은 모두 opinion 행이다. 이는 P2~P5의 직접 보장 대상이 아니지만 모든 arm의 hard-zero
   gate를 독립적으로 막는다.

**동결 유지**: hard gate·threshold·metric·seed·fixture 정의를 변경하지 않는다. GPU/새 후보 학습,
campaign, 운영 채택, 자동 후속 라운드는 0이다. 후속 측정이나 운영 채택은 별도 사용자 결정 사항이다.

## 9. M4 종료와 Claude 이관 (2026-08-26 10:10, 결과-후 절)

사용자가 M4 final push와 현행 문서 전체 동기화, 다음 작업의 Claude 이관을 명시적으로 승인했다.
M4는 §8의 `no_winner` 분기까지 계약대로 종료한다(`goal_status=complete`). winner 조건이
성립하지 않아 campaign은 실행 대상이 아니며, 최고 점수 e2-c2를 retained/adopted model로
승격하지 않는다.

다음 단일 진입점은 `AIRI-CLAUDE-HANDOFF-2026-08-26-POST-M4.md`다. 이 문서는 P4/P5가
닫혔고 P2 잔여 호명·P3 required recall·공통 polite opinion gate가 남았다는 §8 진단을 그대로
전달한다. 문서 안의 M5 Goal 명령은 사용자가 Claude에 실제 제출할 때만 새 실행 권한이 된다.
그전에는 새 blind, matrix, campaign, GPU 학습, 운영 채택을 시작하지 않는다.

## 10. M5 step 1~2 — d1v6 잔여 게이트 분리 진단과 최소 결정론 수리 (2026-08-26 11:20, 결과-후 절)

M5 Goal(사용자 제출)에 따라 채점된 d1v6 report 48개를 read-only 진단 입력으로만 사용해 §8의
잔여 축을 겹치지 않는 원인으로 분류했고, 위임 결과는 report 집계와 코드로 재대조한 것만 채택했다.

**step 1 원인 분류(arm 합산)**

| 축 | 원인 | 수 | 귀책 위치 |
|---|---|---:|---|
| polite 43행/arm 공통 | sealed v6 `aggregation_openers` 9개가 전부 존댓말(v4·v5·공개 fixture는 반말); harness가 모델 호출 뒤 붙임 | 172 | fixture 저작 artefact, `run_broadcast_sim.py:529-592` |
| polite baseline 추가 | 모델 발화 "…살핍니다" | 2 | 모델 |
| invented_handle | roster `모아`가 동사 "모아볼게/모아둘게"의 substring(`broadcast_sim.py:622` `handle in text`) | 2 | 채점 artefact·저작 |
| invented_handle | 직전 8턴 발언자가 briefing `방금 흐름:`/`직전 후원:` author 라벨로 프롬프트에 있었으나 grader pool·proxy memory_pool 신호 어디에도 없음 | 3 | `run_broadcast_sim.py:597-611` |
| transition required miss | proxy grounding 침묵 폴백이 seed 발화를 대체(continuity_seed 139/320, memory_seed 66/160) | 72 | `needs_grounding_retry`(`ollama_proxy.py:4665`)가 초안을 사용자 문장 어휘 겹침만으로 판정 |
| transition required miss | 모델 자유 발화(거부 어휘를 쓰지 않아 P4 미개입) | 15 | 모델 |
| transition required miss | `어느`가 `_INTERROGATIVE_RE`에 없어 probe로 인식되지 않음 | 2 | 계층 |
| probe miss | 근거가 pool에 있는데 P3가 한 번도 안 뜸: proxy 회피 문구 "확인된 정보 없이…" 15 + 모델 추측 14 | 29 | `_RECALL_QUESTION_RES`/`_POSSESSIVE_FACT_RE`가 "X은 어디에 놓았나요?"/"X은 Y에 놓았습니다" 문형을 못 잡음 |
| probe miss | 침묵 폴백 2, 근거 부재 1 | 3 | — |
| 계층 자체 결함 | P2가 `_RECALL_FALLBACK`의 "한 번만"→"한 그거" 훼손 37행; P4 ack가 1글자 주어 `검`을 잡아 "좋아, 검은 남색 잉크로 갈게!" 16행; 닫힌 결정 동사 목록으로 "열자고로" 비문 56행 | — | `deterministic_utterance_layer.py` |

**step 2 최소 수리(flag ON 경로만; OFF 경로는 `build_layer_inputs`가 None을 돌려 byte 동일)**

1. `_REJECTED_BRANCH_RE` 주어 `{2,12}`·`(?:은|는|을|를)`: 목적격 제안("활자함을 … 열자고 했습니다")에서 주어를 얻고 1글자 오검출을 없앤다.
2. recall 결과 보호: P4는 `signal["recall"] is None`일 때만 실행하고, P4가 모든 문장을 떨어뜨려 `_RECALL_FALLBACK`을 돌려주면 `recall="fallback"`으로 표시해 P2가 건드리지 않는다.
3. `find_rejected_branches`: affirmed 두 번째 어절이 "…자고"(인용 결정 동사)면 제거한다(기존 닫힌 목록은 유지).
4. `_INTERROGATIVE_RE`에 `어느`.
5. `apply_deterministic_utterance_layer(..., content_free=False)`: proxy 침묵 폴백 상수처럼 내용 없는 후보에 살아 있는 "A 말고 B" 제안 ack가 붙을 때는 앞에 붙이지 않고 **대체**한다. `ollama_proxy.py` `stream_local_with_ack`의 침묵 폴백 emission 한 곳에서만 `grounding_silence_fallback_used`일 때 `content_free=True`를 넘긴다(같은 호출이 회피 문구·timeout 라인도 처리하므로 그 둘은 제외).
6. P3 2단계 `echo_grounded_fact(user_text, pool_text, draft)`: 의문사 질문이고 살아 있는 제안이 아니며, pool의 평서 문장(briefing 인용부만, author 라벨 제외)과 내용 어간 ≥2개가 겹치고, 초안이 그 문장의 고유 어간을 하나도 쓰지 않았을 때만 그 문장을 반말 종결로 되읽는다(`recall="echoed"`, 이후 P2/P4 생략). `answer_recall_question` 뒤·`is_recall_probe` 폴백 앞에 놓인다.
7. harness grader pool: `run_broadcast_sim.py`가 이번 턴 `briefing_text` 안 roster handle을 `token_pool`에 합산한다(2026-08-24 memory_pool·2026-08-25 history 확장과 같은 "판정 입력 범위" 정정, gate 정의 불변).

**손대지 않은 것**: `needs_grounding_retry` 게이트(flag 무관 production 동작, 사용자 승인 문구) —
seed 침묵 72행 중 "A 말고 B" 제안이 있는 턴만 5번 ack로 대체되고 제안 없는 seed 침묵은 남는다.
gate·threshold·metric·seed·fixture 정의, P4 억제·P5 echo 강도, blind v1~v6는 불변이다. 계층은 여전히
fixture 검사 패턴을 모른다(v6 seed required `"기로"`에 맞춘 문구는 넣지 않았다).

**red/green 증거**: pre-fix `d7c6283` detached worktree에 새 테스트만 복사해 계층 18 failed/36
passed, proxy 새 테스트 `TypeError(content_free)`, harness 새 테스트 `['별빛수집가'] != []` 실패;
수정 tree에서 pinned pytest(`venv-midm-broadcast-qlora-py312`, 3.12.13/pytest 9.1.1) 계층·guard·
runtime 90 passed+12 subtests, broadcast_sim+launcher 계약 251 passed/1 skipped, affect/training
494 passed/8 skipped(알려진 behavior-v2 2건만 실패, continuity_v4는 WindowsApps 3.14 unittest 8 OK),
WindowsApps 3.14 unittest proxy/runtime 405 OK(+2), patch-manifest·current-checkpoint·work-continuity·
dashboard 계약 PASS, `git diff --check` clean.

**v7 저작에 넘기는 결정(사용자 보고 완료)**: `aggregation_openers`·`memory_guard_fallback`은 반말로
저작하고 seal-time register lint를 추가한다; handle은 흔한 동사 어절(`모아`류) 충돌 lint를 추가한다;
`seed_checks`는 v6의 `"기로"` 리터럴이 아니라 공개 fixture 관례(결정 내용 토큰)를 따른다.

**2026-08-26 11:29 추가 — 사용자 결정 C:** 위 "v7 저작에 넘기는 결정"은 실행하지 않는다. 사용자가 뷰어로
5라운드 대화를 확인한 뒤 합성 fixture 매트릭스를 공회전으로 판정해 v7 저작·seal·matrix·campaign을 중단했다.
이 계약의 P2~P5·evidence-echo 코드와 step 2 회귀는 유효하며, 합성 blind 매트릭스는 이후 채택 게이트가
아닌 회귀 도구로만 쓴다. 실태와 파인튜닝 검토는 `AIRI-REALITY-CHECK-AND-FINETUNE-REVIEW-2026-08-26.md` 참조.

## 11. P5·되먹임 계약 변경 — 사람 채점 run 04 결과 반영 (2026-08-26 15:05, commit `beb0559`)

실제 채팅 재생 run 04의 사람 채점(기준선: 방송다움 1.87·맥락 1.58·반응 1.83·말투 3.60·사실성 2.75, 치명 7.1%,
무의미 대꾸 45.5%)에서 후원 경로가 최대 결함으로 확인돼 사용자 승인(A+B) 아래 다음을 바꿨다. 합성 blind
매트릭스는 회귀 도구이므로 §3의 donation composite(shared_tokens) 수치가 낮아지는 것은 허용하며, 판정은
`AIRI-REAL-DIALOGUE-HUMAN-EVAL-CONTRACT-2026-08-26.md` §4만 따른다.

1. **P5 `ensure_donation_engagement`**: 후원 본문을 어떤 형태로도 인용하지 않는다. 초안에 감사 토큰(고마워|고맙|감사)이
   없을 때만 고정 중립 문장 `DONATION_THANKS_LINE = "후원 고마워!"`를 한 번 붙인다.
2. **`strip_unsafe_donation_echo`**: 후원 본문이 보수적 화면 `_UNSAFE_DONATION_RE`(성적·인종/차별·욕설, 시청자 차단이
   아니라 AIRI가 따라 말하지 않기 위한 것)에 걸리면, 본문과 6자 이상 연속 일치하는 초안 문장을 제거한다(공백 무시).
   전부 제거되면 중립 감사 문장만 남는다. 신호 `donation_unsafe_stripped: <n>`. 실제 후원 524건 실측 적중 4.4%.
3. **재생 러너 되먹임 위생(B)**: `thank_renderer` 의례 턴과 P5 감사 문장이 붙은 턴은 history 창에 넣지 않고, briefing
   `방금 흐름` echo에는 모델 continuation만 싣는다(의례 텍스트가 history를 채우면 모델이 이후 질문에 "고마워."로 답한
   run 04 실측 23턴). 합성 fixture 경로에도 적용되므로 이전 합성 run과 턴 단위 비교는 불가.
4. **재생 전용 후원 티어**: `REPLAY_DONATION_RITUAL_MIN_AMOUNT = 5000` 미만 또는 금액 미상 치즈는 일반 채팅으로 답한다
   (`donation_small` 표시). 합성 fixture의 후원은 그대로 의례를 탄다.
5. 고정 의례 렌더러(`must_act_realization.py`, 2026-08-18 사용자 승인 템플릿·오라클)는 바꾸지 않았다.
