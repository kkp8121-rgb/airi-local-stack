# AIRI 로드맵 v3 — 방송 품질 중심 (2026-08-19 전면 개편)

> **이 문서가 프로젝트 최상위 SSoT다.** 부속 문서(GROWTH-STRATEGY·
> MODEL-CUSTOMIZATION-PLAN·NEUROSAMA-LOW-LATENCY-PLAN)와 충돌하면
> 이 문서가 우선한다. 갱신 로그는 `AIRI-ROADMAP-LOG.md`로 분리했다 —
> **매 배치(커밋)마다 로그 파일에 기록**하고, 이 문서는 상태가 실제로
> 변할 때만 고친다. v2 원문(트랙 상세 이력 포함)은
> `아카이브/AIRI-ROADMAP-STATUS-v2-SNAPSHOT-2026-08-19.md`에 동결 보존.

> **2026-08-24 E2-C1 frozen contract milestone published / adapter-init audit next:** 사용자는 E2 adapter
> weight를 검증된 초기값으로 사용하고 optimizer/scheduler/RNG/cursor는 새로 시작하는
> 교정 후보 `E2-C1`을 승인했다. correction 480 + 검증된 v4 replay 200 + mixture 680과
> 새 retained blind 3종·4 seeds·baseline/E2/E2-C1 36-report 평가 계약을 GPU보다 먼저
> 동결했다. final 한국어 감사에서 확인한 `으로/로` target 오류 exact 5건과 validator
> 공백은 최소 helper/template/verifier/mutation 수리로 닫았고, current bytes의 full unit,
> blind commitment, generator byte check, repository/external verifier, independent semantic/
> grammar/split/replay/collision 감사와 diff/security가 PASS했다. milestone `2e61842`와 receipt
> `3dba3ca`는 origin/main에 push됐고 직후 HEAD/local·remote exact, clean, PID 0이다. 따라서
> `freeze_status=pass`, E2-C1 0/0, 관련 AIRI PID 0이다. 다음 gate는 trainer adapter-init seam의
> read-only 감사이며 그 감사와 필요한 최소 구현·fault 회귀의 검증·push 전에는
> `gpu_authorized=false`다. 계약은 `진행중/AIRI-E2-C1-FROZEN-CONTRACT-2026-08-24.md`를
> 따른다. 운영 채택과 기본 모델·태그 변경 금지는 유지한다.

> **2026-08-23 E1/E2 사용자 검토:** baseline/E1/E2는 모두 같은 Mi:dm 계열의 기존
> broadcast v3/continuity-v4 1 epoch/2 epoch 후보다. 1,248턴씩에서 E2는 E1 대비 topic
> 572→586, fact 180→193, memory 8→11, invented handle 46→37, callback 6→8,
> complete arc 1→5로 상대 우세하고 dev loss도 epoch 1 `2.893371758116589`에서 epoch 2
> `2.735453106217887`로 낮아졌다. 그러나 final blind invented handle은 E1 26→E2 34로
> 악화했고 long memory는 양쪽 0/12, E2 donation은 55/56이다. 따라서 E2는 교정 학습의
> 검토상 우세한 출발점일 뿐 T3 승자·운영 채택 모델이 아니다. same-data 3 epoch 반복은
> 승인·권고하지 않으며 새 교정 데이터·비오염 blind·후보 범위를 별도 사용자 intent로
> 고정하기 전에는 학습/T3/campaign을 실행하지 않는다. response-bearing 24 reports는
> external T3 root에만 보존한다.

> **2026-08-23 authoritative T3 terminal FAIL:** controlled GPU와 E2 1,600/1,600,
> E1/E2 merge·BF16/Q4_K_M package는 완료·미채택이다. external root에서 baseline/E1/E2
> 각 12, 총 36 reports와 두 comparator를 실행했으나 양쪽 comparison이 모두 schema v1,
> `status=fail`, adoption false, paired reports 0, reason `polite violation or invented handle`로
> 종료했고 launcher exit 1, `summary.json` absent다. 전 arm transport failure는 0이나 invented
> handle baseline/E1/E2 30/46/37, memory 5/36·8/36·11/36, fact
> 173/752·180/752·193/752, donation 56/56·56/56·55/56이다. comparison 두 파일은 각
> 196 bytes SHA `5f2b4213...3afa`; report/packet/evidence/runtime/comparison inventory SHA는
> `e5241341...16b4`/`00b90c95...859a`/`7cb97aea...3dee`/
> `0417f814...4e8a`/`5a4793b9...d75`다. 관련 PID/listener 0, winner 0이므로 campaign과
> adoption을 금지한다. blind가 공개된 같은 matrix를 반복하거나 hard gate를 낮추지 않는다.
> terminal failure 다섯 SSoT commit `d3724b1`은 `90a436e..d3724b1 main -> main`으로
> origin/main push됐고 HEAD/local·remote exact, 관련 PID/listener 0을 확인했다.

> **2026-08-23 T3 journal blocker 최소 수정·실서비스 smoke PASS:** E2는
> 1,600/1,600 microsteps·100/100 optimizer steps, selected epoch 2 dev loss
> `2.735453106217887`로 완료됐고 E1/E2 merge·BF16/Q4_K_M package와 exact model
> manifest도 완료·미채택이다. T3 `journal_pending`의 원인은 OpenAI SSE 오류 경로가
> public fallback과 terminal을 정상 전달하면서 같은 trace journal을 예약하지 않은
> false-success였다. exact public fallback을 terminal 전에 durable 예약하도록 최소 수정했고
> targeted 2, 영향 113, proxy 370, simulator 63, continuity/current-checkpoint gate가 모두
> PASS했다. baseline/첫 승인 fixture/seed 11 실제 1-turn smoke는
> `transport_failures=0`, `live_receipt_bound=true`; report SHA는
> `6193fb80...26886`이다. authoritative T3 36 `summary.json`과 campaign은 아직 0이며,
> 수정 commit/push·clean 뒤 새 외부 root에서 T3 36을 실행한다. GPU 학습은 없고 baseline
> Ollama 추론 모델만 로드돼 있다. `adoption_authorized=false`를 유지한다.
> fix/test+필수 SSoT commit `80160a1`은 `9724833..80160a1 main -> main`으로 push됐고
> 직후 HEAD/local/remote exact·worktree clean이었다. push receipt 문서 commit 뒤
> authoritative T3 36으로 이동한다.

> **2026-08-23 controlled GPU P0-B PASS receipt:** Goal status는 `active`다. 첫 K=5
> baseline은 480/30 계산 뒤 actual checkpoint interval max `705.902827`초와 final-evidence
> 결속 실패로 FAIL해 보존했고 같은 K=5를 반복하지 않았다. final-evidence SHA 의미 혼동을
> exact internal manifest receipt row에 결속해 pinned Python `146 passed, 5 skipped`,
> actual-process PowerShell durability와 final offline gate로 최소 수리했다. fresh K=3 root의
> 무중단 baseline과 실제 `SAFE_TO_POWER_OFF` pause/checkpoint/resume arm은 모두 terminal
> 480/30이다. 권위 equivalence receipt SHA `d913992e...e84b9`는 `pass=true`, adoption false,
> 672 tensors exact/max abs·rel 0, normal interval 10개/max `551.5176357`초다. Windows
> producer/verifier의 `README.md` 순서 false reject는 platform `Path` 순서 한 줄과 targeted
> 회귀로 최소 수정했고 suite 62 passed/1 skipped, actual GPU verifier와 final offline gate도
> PASS했다. verifier/test+five SSoT commit `87dfabd`와 commit receipt `29080be`는
> `0454ca8..29080be main -> main`으로 origin/main push됐다. actual push receipt five-doc의
> final commit/push 및 clean 확인 뒤에만 authoritative E2를 step 0부터 시작한다.
> `goal_status=active`; E2 microstep 0, 운영 채택과 기본 모델 변경 금지는 유지한다.
>
> **이전 권한 이력 — 2026-08-22 goal resume:** 사용자 `/goal` 명령으로 당시 AIRI 본 goal은 `active`였다.
> 저장소 구현·GPU 학습·모델 병합/패키징·로컬 서비스·T3·장시간 캠페인과
> 검증된 milestone commit/push가 승인됐다. 운영 채택과 기본 모델 변경은 별도
> 사용자 승인 전까지 금지한다. E1 adapter/report만 존재하고 E2·후속 산출물은 0이며,
> P0-A offline 구현·fault 실증과 독립 P0/P1 0 감사는 완료되어 `6f0c1358`로
> origin/main push됐다. P0-B checkpoint timing/exact-equivalence evidence gate와
> external expected-run 결속도 offline 회귀·독립 P0/P1 0 감사를 거쳐
> `e970cf7`·`8cd69b5`로 origin/main push됐으며, E2보다 먼저
> safe-pause의 exactly-one verified active-run 자동 탐지도 0/1/multiple/spoof/
> corrupt-current actual-process 회귀와 독립 P0/P1 0을 통과했다. 이어서
> P0-B controlled GPU 동등성·실제 속도 10분 checkpoint 상한을 실증한다.
> 현재 `goal_status=active`; pause 인계 이력은 `goal_status=paused-user-session-handoff`;
> `adoption_authorized=false`;
> `execution_order=P0_A>P0_B>E2_LAUNCH>E2_PROVENANCE>PACKAGE>T3_36>CAMPAIGN_3X500>USER_DECISION`

> **장기 작업 지속성:** 세션 시작·goal resume·재부팅·compact 직후에는
> `진행중/AIRI-WORKING-STATE.md`를 먼저 전체 읽고 실제 goal status·HEAD·PID·
> 산출물과 대조한다. active goal은 최대 60분 heartbeat 및 단계 전후
> intent/receipt checkpoint를 남긴다.

- 표기: `[x]` 완료(일자) / `[~]` 진행중·부분 / `[ ]` 미착수 /
  `(보류: 재개 조건)`. 완료 표시는 근거 문서·커밋 필수.

## 0. 왜 갈아엎었나 (개편 배경 — 사용자 진단 2026-08-19)

v2 체제의 사이클은 "평가 → 결함 발견 → 가드 추가 → 위반률↓"였고,
**빼기 지표가 전부 0에 도달**(존댓말 위반 0/144턴·이탈 0·오변환 0)한
뒤에도 같은 루프를 돌아 공회전했다. 100인 방송 시뮬레이션
(`완료/AIRI-BROADCAST-SIM-3ARM-2026-08-18.md`)이 그 결과를 보여줬다:
틀리지는 않지만 응답 중앙값 8~16자, "응!" 연발, 집계·호명·기억 활용 부재.

**진단**: 병목은 하드웨어도 Mi:dm도 아니라 **모델을 굶기는 구조**다.
같은 모델·같은 하드웨어에서 컨텍스트에 재료만 넣어준 arm(seeded)이
전 지표 개선(단답 10→3건·주제 적중 27→50%)을 실측으로 증명했다.
프롬프트 지시의 상한도 2회 실증됐다(dn04·gr01 — 명시 금지 예시조차
위반). 따라서 v3의 원칙:

1. **모든 배치는 §1 더하기 지표 중 하나를 올려야 한다.** 빼기 지표는
   회귀 가드로만 유지한다(§2).
2. **프롬프트 지시보다 결정론 계층 우선.** 모델에게 시키지 말고,
   재료를 주거나(P1) 코드가 만든다(P2).
3. **모델 교체·하드웨어 논의는 P1·P2 소진 후**(P3 게이트 조건 참조).

## 1. 주 지표 — 발화 실질 (더하기)

기준선 = 2026-08-18 100인 시뮬레이션(48턴, CPU, 계약+게이트 ON).
목표치는 **제안값**이며 사용자 확정 전까지 잠정이다.

| 지표 | 기준선 (off / on / seeded) | 제안 목표 | 측정 수단 |
|---|---|---|---|
| 단답률 (5자 이하) | 10 / 14 / **3** /48 | ≤3/48 상시 | broadcast_sim |
| 주제 앵커 적중 | 27% / 38% / **50%** | ≥60% | broadcast_sim |
| 응답 다양성 (고유율) | 60% / 67% / **75%** | ≥80% | broadcast_sim |
| 기억 콜백 사용 | 0 / **1** / **1** /3 | 3/3 | broadcast_sim 프로브 |
| 시청자 사실 활용 | **7% (2/29)** — 2026-08-19 신설 | ≥40% (제안) | broadcast_sim fact_usage |
| 여론 집계 발화 | 0/6 전 arm | ≥4/6 | broadcast_sim 웨이브 |
| 후원 호명 정확 | 0/5 전 arm (named 변형도 0/5) | 5/5 | P2 렌더러 + sim |
| 후원 수신자 정합 | 1~2/5 | 5/5 | sim addressee 검사 |

## 2. 회귀 가드 — 유지만 한다 (빼기, 완결된 축)

새 작업 금지. 배치마다 깨지지 않았는지만 확인한다.

- 존댓말: 게이트+치환표+주체높임 가드+폴백 정규화 — 위반 0/144턴 유지
- 이탈(drift) 0 · 오변환 0 · addressee 검사(사이드카 28케이스)
- 방송 발화 계약 v3(`ec7a4209…`) + 스타일 게이트 이중 배선
- 안전(B3 모더레이션·입력 스크리닝) · 모델 SSoT 게이트(digest pin 등)
- 지연 예산: §12 원문 목표 유지(결정 5) — 코덱스 GPU 실측 축

## 3. 돌파 3축 (P1 → P2 → P3 순서, P1·P2는 병행 가능)

### P1. 쇼 러너 브리핑 — 모델에게 재료를 공급한다

디렉터가 매 턴 **브리핑을 자동 조립**해 컨텍스트에 넣는다(LLM 추가
호출 0, 방송 중 사람 개입 0): 이 시청자에 대해 아는 것(viewer_memory
I2a 기존 기반) · 방송 구간/경과 · 최근 화제 · 여론 현황 · 후원 이벤트.
근거: seeded arm 실측 + 뉴로사마 구조(작은 모델 + 두꺼운 자동화 계층).

- [~] P1-1 턴 브리핑 조립기 — 2026-08-19 시뮬레이션 배선·실측 완료
  (`완료/AIRI-P1P2-BRIEFING-DETERMINISTIC-ACTS-2026-08-19.md`).
  **2026-08-20 추가**: 브리핑 근거를 프록시에 알리는 신호 계약
  `X-AIRI-Briefing-Evidence: memory`(정확 일치·루프백 전용) 구현·라이브
  확정 — 헤더 없이 218 ms 결정론 폴백 vs 헤더 있으면 11,299 ms 모델 응답,
  6런에서 선점 4건 해제(`absence_bypasses=4`)·결정론 축 만점 유지,
  단 **기억 프로브 2/9 불변**(선점 해소 ≠ 모델 활용)
  (`완료/AIRI-BRIEFING-EVIDENCE-SIGNAL-2026-08-20.md`, `f6a4167`+`df5b264`).
  이어서 근거 정의를 "관련도 매칭된 줄 존재"로 좁혀 부착률 68.1%→23.6%·
  해제 4→2(결정론적 감소)로 확정하고 행 단위 해제 관측성
  (`briefing_evidence_released`)을 신설
  (`완료/AIRI-BRIEFING-EVIDENCE-NARROW-2026-08-20.md`, `a5abc2c`+`6889d1e`).
  운영 디렉터(B4a) 이식 잔여 — 이식 시 ①근거 판정은 좁힌 정의를 쓰고
  ②프록시 계약·루프백 제약은 그대로 두며 ③원격 디렉터가 되면 루프백
  제약 전체가 재검토 대상이고 ④해제 관측은 `/health` 누계 대조 대신
  프록시가 요청-응답 상관을 직접 남기는 텔레메트리로 승격을 검토한다
  (`/health` 대조는 전용 프로세스·순차 실행 전제에서만 안전)
- [x] P1-2 브리핑 지렛대 소진 — 2026-08-19 관련도 매칭·에코 필터
  (`363c6a7`)+지시형 문구·고정 문구 차단(`40298e2`). 에코 차단은 유효
  (앵커 17→35%·다양성 52→71%), 지시형은 무효(사실 활용 7% 동결) —
  P3 게이트 판정 근거. I2a 실데이터 주입은 B1b 이후
- [x] P3-T1b 추출 판단 학습쌍 — 2026-08-19, 102건(주체 선택·{{user}}·
  과추출 억제 장면), 전 타깃 스팬 파서 무손실 통과 강제, 게이트 어휘
  분리 테스트. 2차 학습 후보(1차=행동 SFT)
- [x] P1-3 "시청자 사실 활용" 지표 신설·재실측 — 2026-08-19. **기준선
  7%(2/29)** — 재료를 줘도 안 쓰는 비율이 수치화됨(P3 게이트 1차 증거,
  단 P1 지렛대 소진 전이라 게이트는 계속 잠김)
- [x] P1-4 **C안: ACK marker 모드** — 2026-08-19 구현 완료(`3ead135`).
  env `AIRI_IMMEDIATE_ACK`(audible 기본=바이트 동일) + 런처 기본 marker.
  실측: control 런에서 marker 자체는 모델 입력 불변 확인
- (연계) 히스토리 8쌍 + num_ctx 예산 재배분 — 브리핑이 차지할 토큰과
  트레이드오프 실측 필요

### P2. 결정론 발화 계층 — 코드가 만드는 발화

모델이 프롬프트로는 못 하는 것(2회 실증)을 결정론으로 생산한다.

- [~] P2-1 thank 렌더러 배선 — 시뮬레이션 5/5 실증 2026-08-19(생일
  반사 소멸). 운영 B4b 어댑터 이식 잔여. 원계획: B4b 어댑터 →
  `callout_context`. 렌더러 자체는 완료(2026-08-18, default-inert,
  테스트 14). 배선·비공개 리허설·운영 ON은 사용자 승인 경유.
  근거: 생일 후원 반사 4/4 arm + 호명 0/5(닉네임 줘도 0).
  **2026-08-20 추가 실측**: 운영 후원은 액션 3종
  (`donation_name_callout_request`/`donation_read_request`/
  `donation_reaction_request` — `broadcast-director/core.mjs:106,121`)인데
  현행 렌더러는 **1번만 덮는다**. 시뮬 5/5는 후원 턴 전체를 렌더러가
  대체한 값이라 reaction 슬롯은 미검증 — dn04류 반사가 운영에서 재발할
  지점이다(P2-4 조사에서 P2-1 귀속 판정)
- [~] P2-2 여론 집계 발화 — 승인 3종(2026-08-19) 시뮬레이션 6/6 실증.
  운영 디렉터 이식 잔여
- [x] P2-3 "기억나?" 가드 — 2026-08-19 프록시 방출 경계 배선 완료
  (`363c6a7`, env 기본 OFF·런처 ON). 기존 absence 폴백(증거 0)의
  잔여 구멍(증거 있는데 무내용 단정) 전용 보완
- [~] P2-4 결정론 발화 격리 — **범위 재정의 2026-08-20**. 조사 결과
  "이관할 렌더러가 더 있다"는 전제는 실측과 어긋났다(**이관 후보 0건**).
  사이드카 28케이스의 최종 실패 4건(2026-08-18 게이트) 중 dn04·b18은
  후원 이벤트류=렌더러 소관(시뮬 5/5×12런, 단 addressee 분모가 후원
  5턴뿐이라 구조적 보장값), gr01·sp01은 답의 내용이 자기 상태·상대
  발언에 의존해 이관 불가(C2 자기 상태 주입·P1-2 소관 — v3 문서 §4-2
  판정 유지). 실질 잔여는 **이관한 발화의 격리**였다 — 후원 렌더러가
  부른 이름이 히스토리·브리핑 "방금 흐름"으로 되먹여져 이후 모델 턴이
  재호명(08-20 시뮬 15런 19턴, 그중 16건이 직전 후원 렌더러 이름 —
  B4a "이름 발명 금지" 계약 위반). **시뮬 격리 수리 완료(2026-08-20,
  `4046d75`)**: 러너 `run_arm()`에서 `deterministic_act` 턴의 히스토리·
  에코 사본만 이름 없는 A4.2 v1 문구로 치환(+4/−2줄, 채점·transcript는
  실제 발화 유지). 같은 시드 전/후 대조 `invented_handle_turns` 2→0,
  addressee·호명 5/5·존댓말 0/48·전송실패 0 무훼손, 테스트 52건 통과.
  잔여: 운영 디렉터(B4a/B4b) 이식 + 사이드카 28케이스 재측정
  (마지막 측정 2026-08-18 게이트 런 — 렌더러가 시뮬 러너에만 배선돼
  `run_broadcast_chat_ab.py`·`run_broadcast_rehearsal.py`에는 acts 경로가
  없어 A4.2·P2 배선 이후 미재측정. v3 문서 §4-5의 회귀 자산 의무 미이행)
- [ ] P2-4b (신설·저순위) cheer/sincere 수신 오프너 — 디렉터 분류는 이미
  존재(`priority-policy.mjs` CHEER_CUES/SINCERE_CUES)하나 근거 표본이
  sp01 1건(단발 한정)이고 다양성 지표를 누를 위험 → 착수 가치 낮음
- [~] P2-5 affect→표현 선택(평가 전용, 2026-08-21) — 기존 13상태를
  closed expression 계약으로 바꾸는 순수 선택기와 frozen fixture 3-arm
  GPU probe를 추가했다. 5상태×3시드 15쌍에서 표현 arm은 문자열을 12/15
  바꿨지만, 위트 0/3·pleased 반응 불변 3/3·competitive 문맥 이탈 3/3,
  safety 안내 약화 2/3이어서 **품질 승격 실패**. 이는 런타임 선택 구조보다
  모델의 표현 팔레트가 선행 병목임을 보여준다. 별도 affect 행동 pending 120건과
  queue-SHA 결속 검수 폼까지 준비했으나, **2026-08-21 사용자 내용 검수에서 반려**됐다.
  기존 행동 181건 중앙값 13자·affect 120건 중앙값 14자로 짧고, 후원/선택 채팅의
  이벤트 맥락·감사 의례·메시지별 반응·주제 확장·복귀 beat가 없는 챗봇형 Q→A다.
  두 큐와 폼은 실패 재현용으로만 보존하며 검수 회신·QLoRA에 쓰지 않는다. 이벤트
  ingress 배선·운영 ON은 별도 사용자 승인 전 금지하며 현재 기본/실행 모두 OFF
- [~] **P2-6 한국 인터넷 방송 반응 메타 재관찰·행동 데이터 재설계
  (2026-08-21)** — 탬탬버린 공식 다시보기/클립과 아리사 공식 영상의 확인 가능한
  입력→반응 장면을 비식별 코딩했다. 공통 단위는 `인지/감사 → 메시지별 반응 →
  의견·에피소드 확장 → 복귀·다음 훅`이며, 길이와 존댓말/반말은 전역 규칙이 아니라
  이벤트·beat별 계약이어야 한다. 실제 방송인의 고유 문체를 복제하지 않고 AIRI
  고유 합성 target을 새 큐로 저작한다. **2026-08-22 현행 데이터:** 공식 1차
  출처 30건·11명과 결속된 원문·PII 없는 observation-only event/beat 30행을 별도
  출처 원장으로 분리했고, 수 시간 연속성 arc 7건은 독립 데이터로 유지한다. 사용자
  지정 진행자 가설 선언 장면도 `OBS-S01` partial-evidence로 포함한다. 출처 식별자는
  비공개 원장에만 둔다.
  AIRI 원본 파일럿 24건도 train/dev/test 16/4/4,
  single/burst 15/9, compact/standard/expanded 4/10/10으로 작성했으며 target
  길이 중앙값 98자·입력보다 짧은 답 0건·전건 training-ineligible이다.
  24건 묶음 총평은 후속 v2→v3→v4 재설계에 반영됐다. 아리사 추가 공식 사례는
  자막 접근이 복구될 때만 확정 표본으로 승격한다.
  근거: `참조/AIRI-KR-BROADCAST-REGISTER-REFERENCE-2026-08-21.md`,
  `진행예정/AIRI-KR-BROADCAST-RESPONSE-PILOT-2026-08-21.md`

  **2026-08-21 총평 반영 후 학습 트랙 진입:** 사용자가 파일럿의 길이·후원
  의례·한국 방송식 주제 확장·RAG 연속성 방향을 묶음 단위로 승인했다.
  이 총평을 반영한 broadcast v2 240행 선행 학습은 T3에서 두 방송 사실 활용
  기준을 소폭 밑돌아 채택하지 않았다. 현행 v3는 120 card×10 연속성 변형+
  v2 240으로 **1,440행**이며, group split 1,148/146/146, 한국어 전수 감사
  blocker 0건·quality gate PASS였다. v3 QLoRA 실행은 현행 v4 트랙으로 대체됐고,
  현재 학습 프로세스는 0이다. T3+사용자 승인 전에는 어떤 어댑터·양자화 모델도
  운영 채택하지 않는다.

### P3. 생성 상한 재검토 — **게이트 열림 (2026-08-19 실측 판정)**

게이트 조건("P1+P2 반영 후 재실측에서도 §1 목표 미달") 충족 —
프롬프트 지렛대 소진(지시형 브리핑까지 사실 활용 7% 동결, 명시 지시
불응 3회째), 독립 증거 4계열
(`완료/AIRI-P1-LEVER-EXHAUSTION-P3-GATE-2026-08-19.md`).
**실행은 코덱스 GPU 몫** — 시뮬레이션 하네스를 그대로 GPU에서 돌려
지연-품질을 한 표로 비교한다. 원 게이트 조건:
근거: 8B 게이트 실측 — 크기는 recall을 못 올렸다(0.43~0.50 정체),
"크면 해결" 반증 (`완료/AIRI-QWEN3-8B-EXTRACTION-GATE-2026-08-18.md`).

**주 경로 = 학습 트랙 (사용자 방향 확정 2026-08-19: "모델을 학습시키는
방향으로")**. 근거: 실패의 정체가 지식이 아니라 행동 패턴(사실 활용
7%·지시 불응 3회)이고, 크기 확대는 반증됐으며(8B recall 정체),
LightMem 실증(작은 모델+좁은 LoRA > 큰 모델)과 정합. 기존
`training/` QLoRA 스캐폴드·governance(합성→pending→**인간 검수**→
승인→로컬 학습)를 그대로 따른다.

- [x] **P3-T1 행동 SFT 데이터 합성** — 2026-08-19 완료. 4행동 181건
  (fact 126·addressee 15·register 10·substance 30), 운영 브리핑 포맷
  그대로, 전 정답 방송 채점기 통과, pending·eligible:false
  (`완료/AIRI-P3T1-BEHAVIOR-SFT-SYNTHESIS-2026-08-19.md`)
- [~] **P3-T2 인간 검수 + QLoRA 학습** — 트레이너 준비 완료 2026-08-19
  (`train_airi_behavior_lora.py` — sha 핀·로컬 전용·assistant 마스킹,
  CPU 스모크로 루프 검증). **2026-08-20 추가**: 2차(추출) 학습의 검수·
  익스포트 경로를 행동 SFT와 대칭으로 신설(`a473eb1`+`df31dc6`) — 폼→
  적용기(스팬 스키마 게이트, 한 건 실패 시 회신 전체 거부)→익스포터
  (벤치마크 Stage A 조립 import 재사용, 바이트 동일 테스트 고정).
  이어 **추출 검수 폼 v2**(`eb9f46a`): rewrite 브라우저 사전 검증
  (evidence ⊂ turns·이름 ⊂ evidence) + target 파싱 실패 배지 분리 +
  **회신-큐 sha256 결속 필수화** — 큐가 바뀌면 **구 폼 회신은 거부되고
  최신 폼을 안내**한다. **검수 직전 보강 완료(2026-08-20 코덱스)**:
  추출 익스포터가 split 도메인·빈 id·중복 id를 fail-closed로 거부하고,
  queue SHA를 LF 정규화해 Windows CRLF 체크아웃에서도 폼/적용기 결속이
  `2988a82bd738`으로 일치한다. **2026-08-21 보강**: 행동 폼도 LF-normalized
  queue SHA 결속과 duplicate/overlap fail-closed를 갖췄고, affect 행동 120건을
  별도 큐·폼으로 추가했다. 현행 SHA는 기존 행동 181건 `eab7f6b76c06`, affect
  행동 120건 `96d0d2d3c69d`, 추출 102건 `2988a82bd738`. 행동 exporter는 검수된
  두 행동 큐를 한 번에 합치되 affect만 운영 request-local 4-message 형태로 조립하고,
  trainer는 기존 3-message/affect 4-message 두 정확한 계약만 허용한다. training
  스위트 **136 passed, 3 skipped**. **2026-08-21 순서 변경:** 기존 행동 181·affect
  행동 120은 사용자 총평으로 반려되어 회신 적용·CUDA 행동 1차를 금지한다. P2-6의
  새 AIRI 고유 방송 반응 24건 파일럿 총평 반영과 별도 전량 검수 계약 뒤에만 행동 학습
  큐를 다시 연다. 추출 102건은
  기술적으로 별도이나 현 배치에서는 행동 재설계와 혼동하지 않도록 검수·2차 학습 보류
  **2026-08-21 현행 대체 트랙:** 반려된 181/120 큐를 재사용하지 않고,
  사용자 묶음 총평을 반영한 broadcast v2 240행→T3 실패 분석→continuity v3
  1,440행→**runtime-shaped continuity v4 1,000행**으로 재설계했다. v4는
  train/dev/test 800/100/100, chat SHA `96cc223ca591`, source SHA
  `43f9c1ed1abf`로 고정됐다. seq2048 E1 QLoRA(800 microsteps/50 optimizer
  updates)는 train first3 3.3845→last3 2.9151, dev loss 2.8938로 완료했지만
  `adoption_authorized=false`, `t3_status=pending`이다. E2는 사용량 한계에 따른
  사용자 요청으로 중단해 산출물 없이 다음 세션 재실행으로 넘겼다. 정확한 명령과
  해시는 `진행중/AIRI-CODEX-HANDOFF-2026-08-21.md`에 고정했다. **2026-08-22
  재감사:** 재부팅 후 세 번째 시작도 pause 요청 직후 checkpoint 전에 종료했으며,
  trainer 0, E2 adapter/report 0, 시작 로그 2개는 각각 0 bytes다. 계산 이력은 있으나
  재개 가능한 상태가 아니므로 P0 내구성 실증 뒤 동일 seed의 step 0부터 다시 실행한다.
- [x] **P3-T2b E1/E2 병합·GGUF 패키징** — P0 실증과 E2 provenance 검증 뒤
  E1/E2 각각 HF safe-merge → BF16 GGUF → Q4_K_M 순서로 완료했다. 후보별
  artifact manifest, SHA, `package-evidence.json`의 최종 tag/digest가 완료 증거다.
  패키징은 후보 생성일 뿐 운영 채택이 아니다.
- [~] **P3-T3 전/후 게이트 — authoritative FAIL** — 시뮬 하네스 그대로. **캘리브레이션 완료
  (2026-08-19 4-시드)**: 사실 활용은 12% 노이즈 천장 상회 필수, 결정론
  축 만점·존댓말 0 유지, 앵커·다양성은 3시드 평균 비교
  (`완료/AIRI-SPAN-CONTRACT-AND-VARIANCE-2026-08-19.md`). **held-out 2차
  방송 기준선 확보(2026-08-19)** — 과적합 검출용, 1차+2차 양쪽 측정 의무
  (`완료/AIRI-HELDOUT-AND-EXTRACTION-SFT-2026-08-19.md`). 미통과 어댑터 폐기
  **2026-08-21 실측 계약 보강:** baseline/candidate 모두 인증된
  `--live-broadcast-context on`으로만 새로 측정한다. proxy가 신원/규칙을 한 번만
  만들고 server-owned `[오늘 방송]`·브리핑·affect·request-local 문체 순으로
  모델에 전달한다. 호출자 system은 capability claim 후 전량 제거하고,
  사전 기억 seed도 trace-bound durable journal receipt 완료 후 본 방송을 시작한다.
  show-arc callback_hit/miss와 TTS·RAG·저널·지연 전 체인은 T3 통과 후
  3-seed×500-turn 장시간 캠페인이 별도로 소유한다. **v4 게이트는** baseline/E1/E2
  각각 first+second 4-seed와 final-blind 180분 4-seed, 총 36 reports로 수행한다.
  **전용 isolated T3 launcher 구현·감사 완료(실측 대기):**
  `run-airi-broadcast-t3-matrix.ps1`이 exact 3-model manifest, 승인 fixture raw/canonical
  pin, 공통 `seeded` 설정, run별 fresh DB/capability, 실행 전후 pinned health,
  immutable stream-plan 전체 turn 집합, 모든 row의 durable live receipt, 두 12-pair
  comparator와 전체 증적 hash inventory를 fail-closed로 강제한다. GPT-SoVITS cache
  wrapper/stream mode 2/min chunk 16과 identity-only partial cleanup·환경 복원도 고정했다.
  오프라인 launcher 8 tests, 시뮬/비교기 75 tests(1 skip), 독립 최종 감사 P0/P1 0.
  2026-08-23 production 36/36 reports와 두 comparator를 terminal까지 실행했으나 invented
  handle/polite hard gate에서 양쪽 모두 FAIL, PASS summary와 winner는 0이다. T3 knowledge
  DB는 fresh empty 상태를 attest했고 campaign RAG fixture를 섞지 않았다. 실패 root를
  보존하며 같은 공개 blind matrix를 반복하지 않는다.
- [ ] **P3-T4 하드코딩 축소** — T3 통과 행동부터 결정론 계층 걷어냄
  (집계 오프너·폴백 후보). **thank 렌더러는 유지** — 후원 호명 오류
  비용이 커서 고정이 정석

보조 경로 (T3 게이트 실패 시 재평가):
- [ ] P3-M1 코덱스 GPU 재실측에 4B급 공존 옵션 포함 (Qwen3-4B 2.5GB)
- [ ] P3-M2 챗 모델 체급 A/B (지연-품질, 기존 하네스)
- [ ] P3-M3 클라우드 하이브리드 재평가 (결정 2 연동)
- [ ] P3-M4 GPU 증설 — 최후 수단

## 4. 기존 트랙 → v3 매핑 (미완 항목 전수 이관)

| v2 트랙 | v3 처지 | 잔여 항목 |
|---|---|---|
| G1 캐릭터 루프 | 유지보수 | evaluator 재활성(보류: G1a validator 합류) |
| G1a 감정·연속성 | **P2에 흡수** | A4.2 배선=P2-1, 잔여 A류는 P2-4 |
| G2 장기 기억 | **P1 공급원** | Stage A 스팬 계약 실측 완료(2026-08-19 — 날조 차단 실증, 판단 축은 미돌파: 추출 판단도 학습 후보 + 코덱스 8B+span 1회 실측 권고). **MEM-04 락 경합 실측 완료(2026-08-20) — 판정: `busy_timeout` 5000 ms 현행 유지가 적정.** 실제 PRAGMA·`append_turn`/`latest_turn` 경로를 임시 DB에 재현: 방송 운영 근사(writer 2·reader 6, 각 2000 ops)·8-writer 동일 세션 최악 케이스 양쪽 모두 busy/locked 실패 0건, 최악 max 대기 2,099 ms=예산의 42%(500 ms로 되돌리면 최악 p99 780.6 ms조차 초과). 근거 `.superpowers/sdd/task-12-report.md` + LOG 2026-08-20. 런타임 계약 수렴분(v2b→v3-span opt-in `00482ec`)·결정론 alias/고정 택소노미 greybox(`9034428`)는 §3 P3·인계문 참조. I2=P1-2 |
| G3 평가 플라이휠 | 지표 교체 | 측정 체계를 §1로 전환. 인간 검수 100건(코덱스)·16케이스 게이트·replay(외부 권한 대기) 유지 |
| G4 / C1~C5 파인튜닝 | 장기 보류 | (보류: 인간 검수 데이터 축적 — 변동 없음) |
| G5 방송 디렉터 | **P1·P2의 몸통** | B4a partial → 브리핑·집계로 확장 |
| G6 화면·게임 | 보류 | (G5=P1·P2 이후) |
| B4c 발화 계약 | §2 가드로 완결 | 파라미터 확정(결정 큐 4)·운영 ON만 잔여 |
| 지연 플랜 v2.1 | 코덱스 트랙 §5 | 본답변 지연·마이크 체인 실측 |
| M1~M5 방송 실행 | 유지 (교차 게이트) | 아래 별도 |
| 모델 SSoT 게이트 | §2 가드 | 완결 유지 |

**M1~M5 잔여** (방송 실행 게이트 — P축과 교차):
- [~] M1: B0-1 streamList 쿼터 실측 마감(외부 자격증명 대기)
- [~] M2: B1b 라이브 어댑터/OAuth/실주입 (보류: 외부 자격증명·운영 승인),
  I2 시청자 기억 → P1-2로 이동
- [~] M3: B3-e 카테고리별 실기, B3-f replay(권한 대기), B2 송출(결정 2 이후)
- [~] M4: B4 확장 = P1·P2 그 자체
- [ ] M5: 비공개 리허설 → 데뷔 (조건 기반, 날짜 고정 없음 — 결정 4)

## 5. 코덱스(GPU) 대기열

### v4 active fail-closed 체크리스트 (2026-08-23 resume)

- [x] live working-state와 60분/장기작업 15분 heartbeat·intent/receipt·재독/대조
  프로토콜 도입 — `e822f9f` origin/main push(2026-08-22), 독립 P0/P1 0
- [x] 공식 방송 event reference 30건·continuity arc 7건과 v4 1,000행 SHA 고정
- [x] E1 QLoRA 및 adapter/report provenance 검증
- [x] 사용자 `/goal`로 명시적 resume, Goal status `active`, Git/PID/SHA/산출물 재대조;
  운영 채택·기본 모델 변경 금지선 유지
- [x] **P0-A (2026-08-22 offline 완료):** checkpoint를 E2보다 먼저 구현: 전체 학습/RNG/순서/loss/provenance 상태, 같은 볼륨
  원자 승격·latest/previous 회전·깨진 checkpoint 격리 구현 및 회귀 —
  `6f0c1358d2acd18b828ebc0ae8482a348712c461` origin/main push
- [x] **P0-B (controlled GPU 완료, 2026-08-23):** exact-pin CPU 중단/재개 동등성, durable runner/run-state, safe pause,
  PID/command/checkpoint SHA 재부팅 복구의 offline 실증은 완료. checkpoint별 durable
  timing event, deterministic pin, 허용오차 0 full-state comparator, 600초/최소 4구간
  gate와 fault 회귀는 `e970cf7`, external input/config/seed/batch/accumulation/first-pause
  expected 결속은 `8cd69b5`로 origin/main push됐다. RunDir 생략 safe-pause는 exact
  command/state/source/process identity가 일치하는 active run 정확히 1개만 선택하고
  0개·복수·spoof·명시적 empty를 거부하도록 offline 검증됐다. controlled GPU 동등성과 실제
  E2 속도 손실 상한 10분 이하 실측이 남음. 2026-08-23 로컬 후속 배치는 no-follow
  input lock/manifest, authenticated run-state recovery, producer evidence/index/event,
  trainer-bound launcher와 anchor-bound pause를 구현했다. 한 차례 감사 P0=0/P1=4의
  네 원래 P1만 최소 수정하고 targeted+최종 Python `145 passed, 5 skipped`+actual-process
  PowerShell+전체 offline+diff/security gate로 잔여 로컬 P0/P1 0을 확인했다. 새 감사
  라운드는 추가하지 않는다. 검증 완료 commit `911d082`과 receipt docs `a898ff8`은
  origin/main에 durable하다. 첫 K=5 controlled baseline은 480/30 계산 뒤 interval max
  705.902827초와 final-root adapter SHA 의미 혼동으로 FAIL했다. runner/pause 두 P0를 exact
  internal manifest receipt row에 결속해 pinned Python 146/5, actual PowerShell, final offline,
  diff/security PASS로 수리했고 `18d0bc6`으로 origin/main push했다. fresh K=3 baseline과
  실제 `SAFE_TO_POWER_OFF` safe arm은 terminal 480/30, paired receipt SHA
  `d913992e...e84b9`, 672 tensors exact, normal interval max 551.5176357초로 PASS했다.
  Windows verifier receipt-order 한 줄과 회귀는 `87dfabd`/`29080be`로 origin/main push됐다.
  actual push receipt five-doc finalization과 clean 확인 뒤 E2로 이동한다.
  이미 완료된 P0-A를 다시 넓게 감사하며 공회전하지 않는다.
- [x] controlled GPU preflight: 입력 code/data clean, trainer 0, corpus/base/E1 SHA exact,
  fresh root와 E2 산출물 부재를 확인했다. E2 직전에는 현재 commit/push·clean과 같은 입력/
  PID/E2 부재를 fresh timestamped run root 기준으로 다시 확인한다.
- [x] **E2-LAUNCH:** authoritative durable runner seed 42·1,600 microsteps terminal,
  report/SHA/manifest 검증 완료
- [x] E1/E2 각각 safe-merge → BF16 GGUF → Q4_K_M 패키징 완료·미채택
- [x] exact baseline/E1/E2 tag+digest manifest 작성·SHA 결속 완료
- [~] isolated 36-report T3와 두 comparator는 terminal 실행 완료이나 양쪽 hard-gate FAIL,
  PASS summary/winner 0
- [x] E1/E2 각 12개 원본 report 위치와 1,248-turn aggregate, 실제 응답 대표 사례를
  사용자 검토용으로 제출했다. E2는 상대 우세하나 T3 PASS/winner로 승격하지 않았다.
- [~] **E2-C1 교정 iteration 설계·데이터·평가 계약:** 사용자 승인 완료. same-data E3가
  아니라 E2 weight-only init + fresh optimizer/scheduler/RNG/cursor다. correction/replay/
  mixture와 retained blind commitment/policy, exact dataset SHA, split/seed/step/LR/scheduler/
  checkpoint/metric 계약은 current bytes에서 full freeze validation PASS다. `으로/로` 5건과
  validator 공백도 mutation regression으로 닫혔다. frozen-contract milestone commit/push와
  HEAD=origin/main clean/PID 0이 남았으며, 그전에는 GPU 학습을 시작하지 않는다.
- [ ] T3 승자 0이므로 3 seed × 500 turn full-stack live campaign 차단
- [~] T3 terminal 실패 aggregate·receipt·hash와 E1/E2 원본은 제출했다. 실제 승자 응답·
  지연·TTS/RAG campaign 묶음은 winner 0으로 생성 금지
- [ ] 사용자 승인 뒤에만 운영 채택 판단; 그전까지 `adoption_authorized=false`

각 단계의 fail-closed 완료 증거와 정확한 명령은
`진행중/AIRI-CODEX-HANDOFF-2026-08-21.md` §8을 따른다.

### 기존 GPU 대기열

- [~] GPU 재실측 — ctx/narrow/Qwen3-8B span은 2026-08-20 실행 완료.
  marker 실제 render TTFT A/B는 외부 GPT-SoVITS venv 불완전으로 보류,
  게이트 경로 폴백률 reps 확대·치환표 중기 조치 ①② 판단은 잔여
- [x] **ctx 예산 GPU 단일조건 재실측 (2026-08-20 완료)** —
  `--history-turns {4,8,12}` 효과가 CPU 스로틀 epoch와 완전히 교락돼
  앵커·다양성·fact_usage·프로브의 우열을 확정하지 못했다. 스로틀·워치독
  변경 없이 **단일 조건**으로 9런을 재실측해 history_turns 효과를 epoch
  효과와 분리할 것. 확정된 것은 결정론 축 무영향·`num_ctx 4096`이
  history_turns=12까지 수용한다는 두 가지뿐이다
  (`완료/AIRI-CTX-BUDGET-TRADEOFF-2026-08-20.md`). GPU 고정조건 9런은
  전송 실패 0, h4/h8/h12 앵커 41/48/46 of 144, 사실 5/7/5 of 90,
  프로브 4/4/3 of 9, 오프너 다양성 평균 78.5/81.3/84.0%였다.
  CPU의 h4 우위는 재현되지 않았고 시드 분산 때문에 단일 설정을 승격하지 않는다.
  주의: `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS`의 유효 범위는 **1~30초**이며
  벗어나면 경고 없이 8초로 클램프된다
- [x] **narrow evidence GPU 확인 (2026-08-20 완료)** — 좁힌 근거 정의
  (부착 23.6%·해제 2건)와 행 단위 해제 관측성이 GPU에서도 같은 값인지
  확인하고, 프로브·사실활용·앵커가 CPU 노이즈에 묻혀 판정 불가였던 축을
  다중 시드로 다시 쟀다. 부착 34/144·해제 2/34는 CPU와 정확히 같고,
  프로브 2/9·사실 4/90·앵커 49/144였다
  (`완료/AIRI-BRIEFING-EVIDENCE-NARROW-2026-08-20.md`)
- [x] **Qwen3-8B + `conversation-v3-span` GPU 1회** — 구조 schema 3종은
  1.0이나 connectivity/B coverage 0.857, recall 0.262, op-alias 0.143,
  failure code 1건으로 balanced gate FAIL. 운영 승인·span 활성화 근거 아님
- [~] TTS 재검증 (v2ProPlus 스트리밍 계약) — proxy 계약 23 passed.
  live 7문장 gate는 외부 GPT-SoVITS venv의 다수 선언 의존성 누락으로 보류
- [ ] B1b 라이브 어댑터 (외부 자격증명과 함께)
- [ ] 인간 검수 100건 수집
- [ ] 실제 마이크 음성 체인 P50/P95 (보류: 사용자 요청 시)

## 6. 사용자 결정 큐 (2026-08-19 정리)

| # | 항목 | 상태 |
|---|---|---|
| 0 | ACK 제거 C안 | **완료** — marker 채택·구현(2026-08-19) |
| 1 | thank 렌더러 운영 배선 (P2-1) | **승인** — 시뮬 실증 완료, 운영 이식 진행 |
| 2 | 여론 집계 발화 문구 (P2-2) | **승인** — 3종 원안, 시뮬 6/6 |
| 3 | "기억나?" 가드 (P2-3) | **승인** — 도입, 회피 문구 원안 |
| 4 | B4c 파라미터 9행 | **승인** — 원안 전체(2026-08-19) |
| 5 | 침묵 폴백 풀 운영 ON | **완료** — 런처 기본 ON(`3ead135`) |
| 6 | 계약 v3+게이트 운영 ON | **완료** — 런처 기본 ON(`3ead135`) |
| 7 | 팬덤명 | 유보 지속 |
| 8 | T-05 목소리 샘플 | 유보 지속 |
| 9 | DeepL 키 (talkain) | **종결** — 사용자 지시로 추적 종료(2026-08-19) |
| 10 | §1 목표치 확정 | **승인** — 제안값 확정, 실측 후 조정 가능 |

확정된 과거 결정(1~7, 2026-08-12·14·18)의 전문은 v2 스냅샷 §사용자 결정
참조 — 요지: 관계 축=AI 단독형+사장님 메타 서사, 로컬 LLM=Mi:dm,
지연 목표=§12 원문, 헌법 v2 7행+통과선 8지표+thank B안+장시간 채팅 A,
raw 경로 검토 근거 불인정(11435 게이트 경유 의무).

## 7. 문서 위계 (2026-08-19 정리 후)

- 최상위: 이 문서 → 로그: `AIRI-ROADMAP-LOG.md`
- 부속 계획(참조용, 이 문서가 우선): `AIRI-GROWTH-STRATEGY.md` ·
  `AIRI-MODEL-CUSTOMIZATION-PLAN.md` · `AIRI-NEUROSAMA-LOW-LATENCY-PLAN.md`
- 현행 스펙: `진행중/AIRI-LOCAL-TECH-SPECS.md`
- 문서 지도: `AIRI-CURRENT-DOCS-INDEX-2026-08-10.md` (파일명 불변 규칙)
- `아카이브/`의 문서는 **현재 상태 검증에 사용 금지** (역사 기록 전용)
