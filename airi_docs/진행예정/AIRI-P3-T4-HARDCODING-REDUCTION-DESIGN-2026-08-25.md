# P3-T4 하드코딩 축소 설계안 (2026-08-25)

> **상태: 설계안(코드 변경 0).** 로드맵 v3 §3 `P3-T4 하드코딩 축소 — T3 통과 행동부터
> 결정론 계층 걷어냄(집계 오프너·폴백 후보). thank 렌더러는 유지`
> (`로드맵/AIRI-ROADMAP-STATUS.md` P3-T4 항목)를 착수 가능한 형태로 풀어 쓴 문서다.
> 병렬 오프라인 세션(branch `feature/parallel-offline-20260825`)에서 작성했고, 코드·
> threshold·policy·플래그 기본값은 하나도 바꾸지 않았다. 인벤토리는 read-only
> subagent 조사 결과를 받아 함수 라인·정책 파일·D1 계약 문서 §6 인용을 직접 대조했다.

## 0. 결론 먼저

1. **P3-T4의 전제("T3 통과 행동")는 아직 성립하지 않는다.** 2026-08-23 production
   36/36(invented_handle/polite hard gate FAIL, winner 0), E2-C1/E2-C2 blind(winner=null),
   D1 48-report(winner=null, 45 게이트 실패) 전부 미통과다. 따라서 이 문서는 "지금
   무엇을 걷어낼지"가 아니라 **"게이트가 닫힌 뒤 어떤 순서로, 어떤 증거를 조건으로
   걷어낼지"**를 고정한다. d1v5 재측정 verdict가 나오기 전에는 어떤 항목도 착수하지
   않는다.
2. 축소 후보는 로드맵이 이미 지목한 두 축 — **집계 오프너(P2-2)**와 **폴백** — 로
   좁히되, 폴백 중에서는 P3 회수 폴백(`_RECALL_FALLBACK`)이 실측상 자기 게이트의
   분모를 잠식하는 유일한 항목이라 **1순위**다. thank 렌더러(P2-1)·P5·P4·핸들 가드는
   hard gate에 직접 결속돼 있어 **유지**한다.
3. 어떤 항목도 "off 경로 byte-identical 회귀 + 새 blind A/B(계층 on/off 두 arm) +
   기존 comparator 게이트 무완화"의 세 조건을 모두 갖추기 전에는 제거하지 않는다.
   측정 결함(프록시 오류 34%, `memory_probe` 분모 95% 오류)이 남아 있는 한 어떤
   제거 판단도 근거가 없다.

## 1. 결정론 계층·가드·렌더러·폴백 인벤토리

플래그 기본값은 전부 **off**(sim 전용 항목은 launcher/러너 인자 `acts on`으로만 켜짐).
"대응 gate"는 `eval/broadcast_sim/fixtures/commitments/airi_d1_metric_policy.json`
(frozen_pre_result)과 `진행중/AIRI-D1-DETERMINISTIC-LAYER-CONTRACT-2026-08-25.md` §3
매핑표 기준이며, 코드·문서에 명시가 없으면 "명시 없음"으로 적었다.

| ID | 위치 | 플래그 | 무엇을 대체/제약하는가 | 대응 gate/metric | 현재 실측(D1 계약 §6) | P3-T4 처분 |
|---|---|---|---|---|---|---|
| P1 history 근거 풀 | `handle_grounding_guard.py:92-129 build_grounding_pools` | `AIRI_HANDLE_GROUNDING_GUARD` | 응답은 안 건드리고 판정 근거 풀에 request history 본문을 추가 | hard `invented_handle`, perfect `unknown_identity_safe` | invented_handle 5/4/8/6(v2 28/40/53 대비 85%↓, 일부는 발화 부재의 산술 효과) | **유지** |
| P2 세션 과거 토큰 가드 | `deterministic_utterance_layer.py:160-198 guard_session_past_tokens` | `AIRI_DETERMINISTIC_UTTERANCE_LAYER` | 과거 세션에만 있고 이번 턴 프롬프트에 없는 한글 토큰을 "그거"로 치환 | hard `invented_handle`, perfect `unknown_identity_safe` | 상동 | **유지** |
| P3 회수 답변 | `deterministic_utterance_layer.py:206-289 is_recall_probe / answer_recall_question` | 동일 | recall probe 응답을 증거 풀에서 추출한 결정으로 **통째 대체**, 실패 시 폴백 | perfect `unknown_identity_safe`; additive `memory_probe`/`long_callback`/`complete_show_arc` | **과발동(D1 신규 회귀)**: `continuity_callback` 320행 중 176행(55%) 폴백 대체 → `long_callback`·`complete_show_arc` 정확히 0.0 | **축소 1순위**(§3) |
| P3 폴백 문구 | `deterministic_utterance_layer.py:56 _RECALL_FALLBACK` | 동일 | 미발견 회수 질문을 "확실하게 기억나지 않아…"로 대체 | P3와 동일 | 상동 | P3와 함께 |
| P4 거부 분기 억제 | `deterministic_utterance_layer.py:292-330 suppress_rejected_branch` | 동일 | "A 말고 B"의 A 문장을 응답에서 제거, 전부 제거되면 P3 폴백 | perfect `stale_transition_clean`, `decoy_fact_use` | decoy 0.025~0.05(3라운드 최저, 0 미달), stale 0.200→0.300 | **유지** |
| P5 후원 engagement | `deterministic_utterance_layer.py:333-349 ensure_donation_engagement` | 동일 | 후원 계속 턴에서 공유 토큰 0이면 감사-echo 문장 append | perfect donation composite | 측정 가능한 후원 턴 live rate 0.688(e2-c2, 최고) | **유지** |
| 핸들 가드 | `handle_grounding_guard.py:146-195 guard_invented_vocative / apply_handle_grounding_guard` | `AIRI_HANDLE_GROUNDING_GUARD` | 근거 없는 `-님` vocative만 "여러분"으로 치환(narrow) | hard `invented_handle` | P1과 신호 공유 | **유지** |
| 기억 단정 가드 | `memory_claim_guard.py:38-46 guard_memory_claim`; sim `run_broadcast_sim.py:564-574`; live `ollama_proxy.py` 7905-7910 부근 | `AIRI_MEMORY_CLAIM_GUARD` | "응, 기억해!"류 무내용 단정을 approved fallback으로 전량 대체 | D1 policy 직접 항목 없음(레거시 `memory_probe` 간접, **명시 없음**) | 2026-08-19 100인 시뮬 기원 | 후보 검토(§3, 측정 후) |
| P2-1 thank 렌더러 | `eval/affect_broadcast/must_act_realization.py:117-184`; sim `run_broadcast_sim.py:502-508` | sim `acts on`(운영 미배선) | 후원 턴 호명·감사 첫 문장을 고정 템플릿으로 렌더링 | perfect donation composite(sim 한정) | 시뮬 5/5; 운영 후원 액션 3종 중 1종만 덮음(P2-4 조사) | **유지(로드맵 명시)** |
| P2-2 여론 오프너 | sim `run_broadcast_sim.py:509-515, 570-572`; 문구는 fixture `aggregation_openers` | sim `acts on`(운영 미배선) | 여론 집계 턴 응답 앞에 고정 오프너 prepend | D1 policy 게이트 없음(`opinion_*`는 retained axis 아님, **명시 없음**) | 시뮬 6/6(2026-08-19) | **축소 2순위**(§3) |
| deterministic_act 히스토리 격리 | sim `run_broadcast_sim.py:623-632` | acts와 함께 | 렌더러가 부른 이름이 히스토리/에코 사본으로 되먹여지지 않게 사본만 치환 | hard `invented_handle`(간접) | 같은 seed `invented_handle_turns` 2→0(`4046d75`) | **유지** |
| 침묵 폴백 풀 | `ollama_proxy.py` `GROUNDING_SILENCE_FALLBACK_POOL`(2398-2417) | `AIRI_SILENCE_FALLBACK_POOL` | grounding/quality 거부 시 6종 순환 문구 | D1 policy 항목 없음(**명시 없음**) | 게이트 런 172답 중 58(33.7%) 단일 문구 반복(코드 주석) | 후보 검토(§3, D1 스코프 밖) |
| 프록시 오류 대화 | `ollama_proxy.py` `LOCAL_ERROR_DIALOGUE`(2382) | 없음(예외 시 항상) | 프록시 예외를 한 줄 사과문으로 대체 | 게이트 아님 — **모든 게이트 분모 오염원** | 전 arm 턴의 33.9~35.3%, `summary.fallback` 미집계, 근본 원인 미확정(stdout 미보존) | 축소 대상 아님 — **선행 수리 과제** |
| 방송 계약 블록 | `broadcast_contract.py:180-183 apply_broadcast_contract` | `AIRI_BROADCAST_CONTRACT` | 텍스트 대체 아님, 시스템 프롬프트에 규범 블록 추가 | D1 policy 항목 없음(**명시 없음**) | 관찰연구 후보값 | 범위 밖 |
| P2-4b 수신 오프너(신규) | `eval/affect_broadcast/reception_opener_realization.py` | `AIRI_RECEPTION_OPENER`(off, 미배선) | cheer/sincere 분류 턴 앞에 고정 오프너 | 게이트 없음 | 2026-08-25 추가, 실측 0 | 배선 전이므로 축소 대상 아님 |

## 2. 게이트 ↔ 계층 매핑과 측정 가능성

`airi_d1_metric_policy.json` 기준(값 인용, 변경 0).

| 게이트 | 종류 | 임계 | 닫는다고 주장하는 계층 | 오늘 측정 가능? |
|---|---|---|---|---|
| `transport`/`polite`/`invented_handle` | hard zero | 0 | P1·P2·핸들 가드·히스토리 격리 | 가능(단, invented_handle 감소분 일부는 발화 부재 효과) |
| `privacy`/`localhost_exposure`/`external_provider_without_opt_in` | hard zero | 0 | 코드 계층 없음(launcher attestation) | 가능 |
| `unknown_identity_safe` | perfect | 1.0 | P3·P1·P2 | **불가** — 분모 12/12 전 arm 차단 턴 |
| donation composite | perfect | 1.0 | P2-1(sim)·P5·P2·P4 | 가능하나 분모 런당 후원 5턴(구조적 보장값) |
| `stale_transition_clean` | perfect | 1.0 | P3·P4 | 가능(0.2~0.3) |
| `decoy_fact_use` | perfect | 0.0 | P4·P5 | 가능(0.025~0.05) |
| `topic_anchored` | additive | min 0.55 / Δ −0.02 | 직접 계층 없음 | 가능 |
| `viewer_fact_usage` | additive | min 0.4 / Δ 0.1 | 직접 계층 없음 | 가능 |
| `memory_probe` | additive + legacy | min 0.5 / Δ 0.15; legacy 0.9 | P3 부수 | **불가** — 160행 중 152행(95%) 프록시 오류 |
| `long_callback` | additive | min 0.5 / Δ 0.2 | P3 부수 | 수치는 있으나 **P3 과발동+오류로 실발화 27행(8.4%)** |
| `complete_show_arc` | additive | min 0.75 / Δ 0.2 | P3 부수 | 상동 |

요약: hard gate 4종 중 1종(`unknown_identity_safe`)과 additive 3종은 계층 성능이 아니라
계측 결함을 반영한다. 계측 결함 2건(프록시 오류 34%, `summary.fallback` 미집계)은 D1
계약 §6이 이미 "선행 수리"로 지목했다.

## 3. 축소 순서(설계)

각 단계는 **직전 단계의 receipt**(새 blind A/B 결과와 comparator verdict)가 있어야
다음으로 넘어간다. 어느 단계에서도 threshold/policy 완화·기본값 on 전환은 없다.

### 단계 0 — 선행 조건(축소 아님)

- 프록시 stdout 보존 재현으로 `LOCAL_ERROR_DIALOGUE` 근본 원인 확정·수리, sim
  `summary.fallback`에 프록시 오류 행을 집계(측정 결함 2건 폐쇄).
- d1v5 4-arm verdict 수령. `winner` 유무와 무관하게 위 결함이 닫히지 않으면 P3-T4는
  대기한다.
- 착수 게이트: 어떤 arm이든 hard gate 4종 전부 통과한 blind 라운드 1회 이상.

### 단계 1 — P3 회수 답변 축소(1순위)

- 목표: 통째 대체를 **"증거를 찾았을 때만"**으로 좁히고, 미발견 시 `_RECALL_FALLBACK`
  대체 대신 모델 응답을 통과시키되 P2/P4/핸들 가드는 그대로 적용한다.
- 근거: 현재 P3는 자기 목표 게이트(`long_callback`, `complete_show_arc`)의 분모 55%를
  폴백으로 잠식한다. 폴백은 안전하지만 "정직한 무응답"이 additive 축을 0으로 만든다.
- 검증: (a) 플래그 off 경로 byte-identical 회귀, (b) 새 blind에서 `layer-on` vs
  `layer-on-minus-P3-fallback` 두 arm A/B, (c) `unknown_identity_safe`가 측정 가능해진
  뒤 1.0 유지, `stale_transition_clean` 비퇴행.
- 롤백: 서브플래그(예: `AIRI_DETERMINISTIC_UTTERANCE_LAYER_RECALL_FALLBACK`)로 즉시 복원.
  플래그 설계는 구현 단계에서 확정한다(이 문서는 이름을 고정하지 않는다).

### 단계 2 — P2-2 여론 오프너 축소(2순위)

- 목표: fixture 고정 문구 prepend를 제거하고 브리핑(`[턴 근거 메모]`)에 여론 집계
  사실만 싣는다 — 문구는 모델이 만들고, 집계 사실의 출처는 결정론으로 남긴다.
- 근거: D1 policy에 `opinion_*` 게이트가 없어 제거로 깨지는 hard gate가 없다. 로드맵이
  1순위 축소 후보로 지목한 항목이기도 하다.
- 검증: `opinion_topic_answered`/`opinion_plurality_marked`(sim 내부 지표) 비퇴행 +
  `topic_anchored` Δ ≥ −0.02. 운영 디렉터 이식이 안 된 항목이라 sim 한정 변경이다.

### 단계 3 — 검토 후보(측정 후 결정)

- 기억 단정 가드: D1 policy 결속이 없고 `memory_probe`가 측정 불가라 판단 보류. 단계 0
  이후 `memory_probe` 실발화가 생기면 on/off A/B로 판단한다.
- 침묵 폴백 풀: D1 스코프 밖. 단일 문구 반복 33.7%가 문제였으므로 축소가 아니라
  다양성 문제로 별도 트랙에서 다룬다.

### 유지(축소 금지)

P2-1 thank 렌더러(로드맵 명시), P5, P4, P1/P2, 핸들 가드, 히스토리 격리. 전부 hard
gate(`invented_handle`, donation composite, `stale_transition_clean`, `decoy_fact_use`)에
직접 결속돼 있고, 제거 시 재발 사례가 실측으로 남아 있다(E2-C1 53건 재호명, 2026-08-20
시뮬 19턴 중 16건 재호명).

## 4. 비목표

- 새 계층 추가, threshold/policy/seed/fixture 정의 변경, 플래그 기본값 on, 운영 태그·
  모델 변경, GPU 학습.
- 이 문서로 어떤 게이트의 "통과"를 주장하지 않는다. 수치는 전부 D1 계약 §6 인용이다.

## 5. 착수 체크리스트(구현 세션용)

1. 단계 0 receipt 2건(프록시 오류 근본 원인 수리 receipt, `summary.fallback` 집계
   테스트) 링크.
2. hard gate 4종 전부 통과한 blind verdict 파일 SHA.
3. 단계 1 서브플래그 이름·기본값(off) 확정, off 경로 byte-identical 테스트 추가.
4. 새 blind 봉인(기존 v1~v5 재사용 금지) → 2-arm A/B → comparator verdict.
5. ROADMAP-STATUS P3-T4 항목을 `[~]`로 바꾸고 이 문서를 `진행중/`으로 이동.
