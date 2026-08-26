# AIRI 실태 파악과 파인튜닝 검토 (2026-08-26)

> **상태: 사용자 결정 (C) — 2026-08-26 M5 step 4(blind v7 저작·재측정)를 즉시 중단하고,
> 공회전 실태를 파악해 모든 현행 문서를 갱신하며 파인튜닝을 재검토한다.**
> 이 문서는 새 단일 진입점이며, `AIRI-CLAUDE-HANDOFF-2026-08-26-POST-M4.md` §4의 M5 Goal
> 명령(v7 매트릭스·조건부 campaign)은 step 3까지만 유효하고 step 4 이후는 **대체(superseded)**됐다.
> 수치는 전부 이 세션에서 저장소·외부 root·report를 read-only로 읽어 계산한 값이다.

## 0. 결론 먼저

1. **2026-08-19 로드맵 v3 개편 이후 7일 동안의 주 루프(합성 fixture blind 매트릭스 → no_winner →
   하니스 수리 → 새 blind)는 공회전이었다.** 6라운드 216 report가 전부 `winner=null`이고, 각
   라운드의 실패 원인 대부분이 모델이 아니라 계측·저작 결함이었다. 라운드마다 하니스가 바뀌어
   점수(0.11 → 0.34 → 0.47~0.56)는 서로 비교할 수 없다.
2. **파인튜닝은 지금 중단하는 것이 맞다.** 학습 후보 4개(E1·E2·E2-C1·E2-C2)와 이전 v3는 하나도
   운영에 채택되지 않았고, 운영 모델은 여전히 stock Mi:dm 2.0 Mini Instruct Q4_K_M이다. 학습
   데이터는 100% 템플릿 합성이며, 평가도 100% 합성 시청자 + 정규식 게이트다. 일반 능력은
   병합을 거듭할수록 단조 하락했다(kobest −0.9%p, haerae −1.9%p).
3. **실제 방송 데이터가 0이다.** 실제 시청자 채팅을 받는 전송층(chat-ingress)은 설계만 있고
   transport가 없으며, 사람 검수 결과는 08-15 결정 브리프의 "PENDING" 그대로 하나도 없다.
   "방송 같은가"를 판정할 근거 자체가 저장소에 없다.
4. **헛돈 것만은 아니다.** 하니스가 실제 방송에도 그대로 나타날 배관 결함을 여러 개 찾아냈고,
   결정론 계층(P2~P5)·메모리·브리핑·live-broadcast 런타임은 제품 코드로 남았다. 이번 세션의
   step 2 수리(계층·proxy·grader pool)도 red/green으로 검증된 실제 버그 수정이다.
5. 다음 단계는 **더 정교한 합성 평가가 아니라 실제 대화 데이터와 사람 채점**이다(§5).

## 1. 무엇을 했나 — 2026-08-19 v3 개편 이후 실측

| 항목 | 값 | 근거 |
|---|---|---|
| 커밋 | 156개 (08-19 13 · 08-20 19 · 08-21 6 · 08-22 12 · 08-23 27 · 08-24 31 · 08-25 44 · 08-26 4) | `git log --since=2026-08-19` |
| live state 체크포인트 | WORKING-STATE §1 항목 152개 (08-24 61 · 08-25 74), 파일 6,762행 | `AIRI-WORKING-STATE.md` |
| GPU 학습 후보 | E1, E2(1,600/1,600 microsteps), E2-C1, E2-C2(1,536/96, 3 epochs, ≈48분) — 채택 0 | ROADMAP-LOG 08-22~08-24 |
| blind 라운드 | v1(영문 결함, 실행 불능) · v2 36 · v3 36 · v4 48 · v5 48 · v6 48 = **216 report, 전부 no_winner** | `D:\AIRI-Models\airi-*blind-matrix-*` comparisons |
| 이번 M5 goal 사용량 | 2,370,132 tokens · 약 6h19m (사용자 제출 시점 기준) | goal 명령 |
| 운영 모델 | `midm-airi:2.0-mini` = `hf.co/DevQuasar/K-intelligence.Midm-2.0-Mini-Instruct-GGUF:Q4_K_M` (stock, 2.3B) | `참조/AIRI-CLAUDE-REVIEW-2026-08-25.md` |
| 실제 시청자 데이터 | 0 (chat-ingress: transport/OAuth/polling 없음, default-off) | `chat-ingress/README.md` |
| 사람 검수 결과 | 0 ("사람 검수 결과가 하나도 없으므로 … 채택 금지 유지") | `완료/AIRI-LONG-CHAT-TEST-DECISION-BRIEF-2026-08-15.md` |
| 실제 방송에서 나온 입력 | 실제 방송 트랜스크립트에서 역추출한 시청자 채팅 38건(08-14 A/B)뿐 | `완료/AIRI-REMOTE-BROADCAST-CHAT-AB-2026-08-14.md` |

### 라운드별 실패의 실제 원인 (모델 vs 계측)

| 라운드 | 결과 | 지배적 원인 |
|---|---|---|
| E2-C1 v2 (36) | no_winner, invented_handle 28/40/53 | grader가 memory 검색으로 회수한 실제 이름을 발명으로 오판 → 신호 확장으로 정정 |
| E2-C2 v3 (36) | no_winner | 같은 계열 + history 창 누락(측정 사각지대) |
| D1 v4 (48) | no_winner 45 gate | **proxy 오류 응답 34%**(세 라운드 공통, 미보고), P3 과발동으로 callback 55% 폴백, memory_probe 95% 오류 |
| d1v5 (48) | no_winner | live 경로에서 결정론 계층이 브리핑을 못 받는 배선 결함, P3 정규식 공백, handle-주제 충돌 |
| d1v6 (48) | no_winner 29 gate | **v6 opener 존댓말 저작 artefact**(polite 43행×4), roster handle–동사 substring 충돌, grader pool이 briefing author 라벨 누락, **proxy grounding 게이트가 평서문 seed 43%를 침묵으로 대체** |

여섯 번 중 모델 자체의 한계로 귀결된 축은 P3 probe에서 baseline·e2-c1·e2-c2가 근거를 보고도
회피/추측한 15건 정도이며, 그것도 e2는 12/12를 맞췄다.

## 2. 왜 공회전이 됐나

- **측정 대상이 모델이 아니었다.** 응답의 큰 몫을 하니스와 코드가 쓴다: wave_opener·thank_renderer
  템플릿, 결정론 계층의 ack·echo·폴백, proxy 침묵 폴백. 게이트는 substring/regex다. 결과적으로
  "하니스+계층+게이트 조합이 정규식을 통과하는가"를 재면서 파인튜닝 채택을 판정했다.
- **fixture가 방송이 아니다.** 시청자는 템플릿 문장을 seed로 뿌리는 봇이고, AIRI는 1~2문장
  단답이다. 실제 시청자의 말투·오타·맥락 이탈·농담·되묻기·침묵의 리듬이 없다. 뷰어
  (`D:\AIRI-Models\airi-blind-review-html\d1v6-review.html`)로 5라운드 20,616턴을 보면 즉시 드러난다.
- **로드맵 v3 §0가 이미 같은 진단을 했다.** "빼기 지표가 전부 0에 도달한 뒤에도 같은 루프를 돌아
  공회전했다", "병목은 모델이 아니라 모델을 굶기는 구조다", "모델 교체·학습 논의는 P1·P2 소진
  후". 그런데 개편 직후 곧바로 E1/E2/E2-C1/E2-C2 학습과 6회 blind 매트릭스로 되돌아갔다.
- **절차 비용이 실질을 압도했다.** 하루 60~70개 체크포인트, 6,700행 live state, 라운드마다
  seal·commitment·launcher·verifier·CI 계약 재작성. 신뢰성은 높았지만 그 신뢰성이 향한 대상이
  합성 지표였다.

## 3. 실제로 남은 가치 (버리지 말 것)

- **런타임 배관 결함 발견·수리**: proxy 오류 응답 34% 계측 복구(M1), num_ctx 2048→4096(KT
  프리앰블 514토큰), 결정론 계층 live 배선(M4), history 되먹임 이름 제거의 부작용 인지,
  grader pool 사각지대 3종, 이번 세션의 계층 결함 3종(폴백 훼손·1글자 주어·비문).
- **제품 코드**: `deterministic_utterance_layer.py`(P2~P5 + evidence-echo), `handle_grounding_guard.py`,
  memory/knowledge/broadcast 런타임, latency 계측, 안전 폴백. 전부 flag 뒤에 있고 OFF 경로는 byte 동일.
- **도구**: greybox(lm-eval·llama.cpp perplexity) 기준선, blind seal/commitment 계약, campaign
  launcher — 회귀·재현 도구로는 유효하다. 다만 **채택 게이트로는 더 쓰지 않는다**.
- **관측된 진짜 문제 1건(미수리, 승인 필요)**: `needs_grounding_retry`(`ollama_proxy.py:4665`)가
  초안을 사용자 문장 어휘 겹침만으로 판정해, 시청자가 "우리 X로 하기로 했어요" 같은 평서문을
  말하면 43%가 침묵 폴백("음… 뭐라고 하지?")이 된다. 실제 방송에서도 그대로 나타난다.

## 4. 파인튜닝 검토

### 4.1 증거

| 관점 | 관측 |
|---|---|
| 방송 지표 이득 | blind d1v6에서 학습 arm이 baseline보다 나은 축: memory_probe 0.70→0.78~0.88, long_callback 0.65→0.68~0.77. hard gate(호명·거부 옵션·후원·정체성)는 학습으로 한 번도 닫히지 않았고 결정론 계층이 닫았다 |
| 일반 능력 손실 | stock → v3 → e2c2 단조 하락: kobest −0.53 → −0.90%p, haerae −1.19 → −1.92%p (제안 게이트 ≤2%p 경계) |
| 데이터 | 전량 템플릿 합성: continuity v3 1,440행, v4 1,000행, e2-c1 mixture 680행(교정 480+replay 200), behavior v2 240행. 실제 시청자 발화 0 |
| 평가 | 전량 합성 fixture + regex/substring 게이트. 사람 채점 0 |
| 베이스 | Mi:dm 2.0 Mini 2.3B, Q4_K_M(양자화 손실 비율 1.018, 작음). 8GB VRAM |
| v3 로드맵의 자체 실증 | 같은 모델에 재료(seeded 컨텍스트)만 넣어도 단답 10→3, 주제 적중 27→50% — 학습 없이 얻은 이득이 학습 이득보다 컸다 |

### 4.2 판단

- **지금 상태에서 추가 파인튜닝은 기대값이 낮고, 판정 수단이 없다.** 합성 데이터로 합성 게이트를
  넘기게 만드는 학습은 Goodhart이며, 넘겨도 "방송 같다"의 증거가 되지 않는다. 손실(일반 능력
  하락)은 실측됐고 이득은 결정론 계층이 대체 가능한 영역에 몰려 있다.
- **기존 어댑터·병합·GGUF(v3, E1, E2, E2-C1, E2-C2)는 보관하되 채택 금지를 유지**한다. 삭제하지
  않는다(재현 증거).
- **재개 조건(전부 충족 시에만; 2026-08-26 타계책으로 강화 — 2026-09-09까지 금지, `AIRI-BREAKTHROUGH-PLAN-2026-08-26.md` §2)**:
  0. 타계책 S1~S5(되먹임 고리 차단·오프너 재샘플·예시·픽업 정책·모델 축 진단)를 마친 뒤에도 3축 합성 < 3.0이고,
     S5에서 큰 모델이 +0.6 이상(용량 병목 실측)일 것. 데이터는 실제 채팅 입력 + 사람 4점 이상 검증 답변 ≥ 300턴.
  1. 실제 시청자 채팅 로그(비공개 테스트 방송 포함) 또는 사람이 쓴 현실적 대화 코퍼스 수백 턴.
  2. 사람 채점 기반 평가 세트(최소 50~100턴, 채점 기준 문서화)와 채택 기준의 사전 동결.
  3. 결정론 계층·브리핑·메모리로 닫히지 않는 행동이 그 평가에서 실측으로 남을 것.
  4. 일반 능력 회귀 게이트(≤2%p, lm-eval kobest·haerae) 강제.
- **대안 우선순위**: (1) 재료 공급(P1 브리핑·메모리 회수 품질) (2) 결정론 계층 (3) 프롬프트
  (4) 모델 교체 검토(로드맵 v3 P3 게이트 조건대로, 실제 데이터 확보 뒤) (5) 파인튜닝.

## 5. 다음 제안 — 사용자 결정 큐 (2026-08-26 11:45 KST **4건 모두 승인** → 로드맵 v4 M6, 평가 계약 `AIRI-REAL-DIALOGUE-HUMAN-EVAL-CONTRACT-2026-08-26.md`)

1. **실제 대화 데이터 확보**: 비공개 테스트 방송 1회 또는 사용자가 직접 진행하는 채팅 세션에서
   채팅·응답 로그를 남긴다(개인정보 처리 계획 포함). 이 로그 50~100턴을 사람이 채점하는 세트가
   앞으로의 유일한 채택 게이트다.
2. **proxy grounding 게이트 평서문 침묵 수리**: production 동작 변경이라 별도 승인이 필요하다.
   방송 체감을 가장 크게 바꿀 단일 항목이다.
3. **이번 세션 step 2 수리 코드 commit 여부**: 검증 완료(§6). commit/push는 별도 승인.
4. **blind 하니스 격하**: 채택 게이트가 아닌 결정론 계층·배관 회귀 도구로 문서상 격하(이 문서로
   반영). v7 저작은 하지 않는다.
5. **문서 다이어트**: WORKING-STATE 6,700행·중복 handoff 정리, heartbeat 주기 완화. 절차 비용을
   실질 작업 아래로 내린다.

## 6. 이번 세션 산출물 상태 (2026-08-26, 로컬·미커밋)

- 코드(검증 완료): `ollama-proxy/deterministic_utterance_layer.py`, `ollama-proxy/ollama_proxy.py`,
  `ollama-proxy/eval/broadcast_sim/run_broadcast_sim.py` + 테스트 3파일. red: pre-fix `d7c6283`
  worktree에서 새 테스트 FAIL; green: pinned pytest 90/251/494 passed(알려진 behavior-v2 2건 분리),
  CI 동등 venv core suite 1,140 passed, proxy/runtime unittest 405 OK, 계약 4종 PASS, diff-check clean.
- 도구: `test-airi-roadmap-dashboard-contract.ps1` milestone 라벨 일반화.
- 문서: 이 문서, D1 contract §10, WORKING/ROADMAP/LOG/NEXT/handoff 동기화.
- 외부: `D:\AIRI-Models\airi-blind-review-html\d1v6-review.html`(5라운드 뷰어, 9.7MB).
- 중단·되돌림: step 4 seal 도구 `d1v7` 세대 편집(검증 전)은 `git checkout`으로 되돌렸고, v7 staging은
  생성되지 않았다. blind v7·matrix·campaign·GPU·adoption·push는 0.
