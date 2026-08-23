# AIRI 다음 세션 안내

> **2026-08-24 02:07 KST 검토 PC 최우선 진입점 — E2-C1 FROZEN VALIDATED / MILESTONE PUSH PENDING:**
> latest Goal은 E2 adapter weight를 초기값으로 쓰고 optimizer/scheduler/RNG/cursor는
> 새로 시작하는 `E2-C1` 교정 후보다. correction 480, v4 replay 200, mixture 680과
> 새 retained blind 3종/4 seeds/3 arms의 계약은 동결됐다. final 감사에서 확인한 exact
> five `으로/로` target 오류는 helper/template/independent verifier와 mutation regression의
> 최소 수리로 닫혔다. current bytes는 full unit 12, blind pytest 5, generator byte check,
> repository/external verifier, independent semantic/grammar/split/replay/collision 감사와
> diff/security를 PASS했다. 현재 `freeze_status=pass`, `gpu_authorized=false`, E2-C1
> 0 microstep/0 optimizer step, related AIRI durable runner/trainer/service PID 0이다.
> blocker는 frozen milestone commit/push와 HEAD=origin/main clean뿐이다.
>
> 새 PC에서는 다른 실행보다 먼저 `AGENTS.md` → `AIRI-WORKING-STATE.md` → 현행 handoff →
> `AIRI-ROADMAP-STATUS.md` → 이 파일을 전체 읽고 Goal/Git/PID/E2/T3/blind를 read-only로
> 대조한다. PID 0이면 `pause-airi-safely.ps1`을 실행하지 않는다. 현재 checkpoint의
> exact 설계·SHA·blind gate는
> `airi_docs/진행중/AIRI-E2-C1-FROZEN-CONTRACT-2026-08-24.md`에 있다. 다음 무-GPU 동작은
> frozen SSoT continuity/boundary/diff/security 검증과 exact milestone commit/push다.
> counts/splits/replay,
> v4/base/E2, seed 42·batch 1·accumulation 16·seq 2048·512 microsteps·LR 1e-5·constant/K=3,
> blind fixture/seed/threshold는 변경하지 않는다. commit/push 뒤 HEAD=origin/main clean/
> PID 0 전에는 GPU로 이동하지 않는다. publication clean 뒤에도 GPU를 자동 시작하지 않고
> trainer의 E2 adapter-initialization 지원 여부를 별도 intent에서 read-only 감사한다.

> **2026-08-23 22:38 KST E1/E2 사용자 검토 경계:** baseline/E1/E2는 모두 같은
> Mi:dm 계열의 기존 broadcast v3/continuity-v4 1 epoch/2 epoch 후보다. E2는 E1 대비
> topic 572→586, fact 180→193, memory 8→11, invented handle 46→37, callback 6→8,
> complete arc 1→5로 상대 우세하고 dev loss도 epoch 1 `2.893371758116589`에서 epoch 2
> `2.735453106217887`로 낮아졌다. 그러나 final blind invented handle은 E1 26→E2 34,
> long memory는 양쪽 0/12이고 E2 donation은 55/56이다. E2는 후속 교정 학습의 검토상
> 우세한 출발점일 뿐 T3 winner/adopted가 아니다. 사용자는 external T3 root의 E1/E2
> 각 12개 원본 report와 대표 실제 응답을 검토 중이다. response-bearing report/packet/
> runtime은 Git에 넣지 않는다. same-data 3 epoch 반복은 승인·권고하지 않으며, 다음 실행
> gate는 이 five-doc 배치 commit/push·clean 뒤 새 교정 데이터/비오염 blind/후보 범위를
> 사용자가 별도 승인하는 것이다. 그전에는 GPU 학습, 같은 T3, campaign, 운영 채택을 금지한다.

> **2026-08-23 20:56 KST 현재 gate: T3 FAILED CLOSED.** controlled GPU와
> authoritative E2 1,600/1,600, E1/E2 merge·BF16/Q4_K_M package는 완료·미채택이다.
> authoritative T3는 baseline/E1/E2 각 12, 총 36 reports와 두 comparator까지 실행했으나
> 두 comparison 모두 `status=fail`, adoption false, paired reports 0, reason
> `polite violation or invented handle`로 종료했고 launcher exit 1, `summary.json` absent다.
> 전 arm transport failure는 0이나 invented handle baseline/E1/E2 30/46/37,
> memory 5/36·8/36·11/36, fact 173/752·180/752·193/752, donation
> 56/56·56/56·55/56이다. comparison 두 파일은 각 196 bytes SHA `5f2b4213...3afa`;
> report/packet/evidence/runtime/comparison inventory SHA는 `e5241341...16b4`/
> `00b90c95...859a`/`7cb97aea...3dee`/`0417f814...4e8a`/`5a4793b9...d75`다.
> launcher/관련 PID/owned listener는 0이다. winner 0이므로 3×500 campaign과 운영 채택을
> 금지하며, 실패 root를 보존하고 같은 공개 blind matrix나 hard gate를 반복·약화하지 않는다.
> terminal failure 다섯 SSoT commit `d3724b1ea3d0df7cff8e14fd511f4b8244b8838c`은
> `90a436e..d3724b1 main -> main`으로 origin/main push됐고 HEAD/local·remote exact,
> 관련 PID/listener 0을 확인했다. 다음 실행 gate는 campaign이 아니라, 공개된 blind를
> 재사용하지 않는 새 모델링/evaluation iteration에 대한 사용자 방향이다.

> **2026-08-23 controlled GPU P0-B PASS receipt:** 최신 Goal status는 `active`,
> `goal_status=active`다. 첫 K=5 baseline은 480/30 계산 뒤 actual interval max
> `705.902827`초와 final-evidence 결속 실패로 FAIL해 보존했고 같은 K=5를 반복하지 않았다.
> exact internal manifest receipt row 결속으로 최소 수정한 뒤 fresh K=3 baseline과 실제
> `SAFE_TO_POWER_OFF` pause/checkpoint/resume arm을 모두 terminal 480/30으로 완주했다.
> final equivalence receipt는 48,323 bytes SHA `d913992e...e84b9`, `pass=true`, adoption
> false, 672 tensors exact/max abs·rel 0, normal interval 10개/max `551.5176357`초다.
> Windows producer/verifier의 `README.md` receipt-order false reject는 platform `Path` 순서
> 한 줄과 targeted 회귀로 최소 수정했고 targeted 1 PASS, suite 62 passed/1 skipped,
> actual GPU verifier와 final offline checkpoint도 PASS했다. 운영 채택과 기본 모델 변경
> 금지는 유지한다.
>
> 07:38 KST verifier/test+five SSoT commit `87dfabd`와 commit receipt `29080be`는
> `0454ca8..29080be main -> main`으로 origin/main push됐다. push 직후 HEAD/local·remote
> origin/main exact, worktree clean, 관련 durable runner/trainer/verifier/test PID와 AIRI GPU
> workload 0이다. source/chat/base와 E1 adapter/config/report SHA는 exact, E2 adapter/report
> absent, 기존 로그 두 개 각 0 bytes, E2 microstep 0이다. 현재 gate는 actual push receipt
> five-doc final 검증·commit/push와 clean 재확인뿐이다. 그 뒤 fresh timestamped E2 root/
> manifest를 만들고 authoritative
> durable runner로 seed 42·1,600 microsteps를 step 0부터 시작한다. direct trainer는 금지한다.
> 새 감사 라운드는 추가하지 않으며 문서 인덱스는 현행 handoff를 정확히 가리켜 변경하지 않는다.
>
> **이전 권한 이력 — 2026-08-22 goal resume:** 사용자 `/goal` 명령으로 당시 AIRI 본 goal은 `active`였다.
> 운영 모델 채택과 기본 서비스 모델 변경만 별도 사용자 승인 전까지 금지한다.
> 전원 종료 복구용 P0-A checkpoint/full-state/atomic fault 계층은 offline 구현·독립
> P0/P1 0 감사까지 완료되어 `6f0c1358`로 origin/main push됐다. P0-B timing/
> exact-equivalence evidence gate와 external expected-run 결속도 offline 회귀·독립
> P0/P1 0을 거쳐 `e970cf7`·`8cd69b5`로 origin/main push됐다. `pause-airi-safely.ps1`은
> RunDir 생략 시 exactly-one verified active durable run만 자동 선택하도록 actual-process
> 0/1/multiple/spoof/fallback 회귀와 독립 P0/P1 0을 통과했다. controlled GPU 동등성과 실제 E2 속도 10분 checkpoint 상한은
> 아직 미실측이며, 둘을 실증한 뒤에만 E2를 시작한다.
> 현재 계약은 `goal_status=active`; 이전 pause 인계 이력은
> `goal_status=paused-user-session-handoff`; `adoption_authorized=false`
> `execution_order=P0_A>P0_B>E2_LAUNCH>E2_PROVENANCE>PACKAGE>T3_36>CAMPAIGN_3X500>USER_DECISION`

**진입점은 네 개다** (2026-08-22 live-state 지속성 규칙 추가):

1. `airi_docs/진행중/AIRI-WORKING-STATE.md` — **가장 먼저 읽는 live SSoT.**
   세션 시작·goal resume·재부팅·compact 직후 실제 goal status, HEAD/worktree,
   PID, 산출물과 대조하고 불일치하면 이 문서를 먼저 정정한다. active goal에서는
   최대 60분 heartbeat와 단계 전후 intent/receipt checkpoint를 유지한다.
2. `airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-08-21.md` — **현행 GPU 인계 단일
   SSoT.** runtime-shaped v4 1,000행의 exact SHA, E1 완료 결과, P0-A offline 완료와
   `e970cf7` P0-B timing/exact-equivalence gate 및 `8cd69b5` expected-run 결속,
   E2 전 controlled GPU 내구성 실증,
   중단한 E2의 step 0 재실행 명령, merge/GGUF 핀, calibration 2종+blind 180분 T3의
   36-report 행렬, 이후 3×500 live campaign 순서를 고정한다. 현재 E1은
   `adoption_authorized=false`, `t3_status=pending`이며 서비스 모델은 바꾸지 않았다.
   코덱스든 클로드든 먼저 이 문서부터 읽는다. 08-20판의 greybox·추출 이력은
   근거로 보존하지만 방송 GPU 작업 상태는 새 문서가 대체한다.
3. `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md` — **최상위 SSoT.** 북극성·
   주 지표(발화 실질)·돌파 3축(P1 쇼 러너 브리핑 / P2 결정론 발화 /
   P3 조건부 생성 상한)·사용자 결정 큐·코덱스 대기열이 전부 여기 있다.
4. `airi_docs/AIRI-CURRENT-DOCS-INDEX-2026-08-10.md` — 문서 지도.

행동 재설계 근거: `airi_docs/참조/AIRI-KR-BROADCAST-REGISTER-REFERENCE-2026-08-21.md`.
기계 판독 관찰 데이터는 `airi_docs/참조/data/`, AIRI 원본 파일럿은
`ollama-proxy/training/seed/airi_broadcast_response_pilot_pending.jsonl`이다.

토큰 실측 기록: `airi_docs/진행중/AIRI-CODEX-SERENA-TOKEN-ORDER-2026-08-20.md`.
Serena MCP는 로컬 A/B 순손실로 등록 롤백됐으며 2026-08-23 사용자 결정으로
사용·재도입하지 않는다. 관련 token-order 문서는 실행 지시가 아닌 역사 기록이다.
Caveman trial은 미실행이다.

최근 배치 이력은 `airi_docs/로드맵/AIRI-ROADMAP-LOG.md`(최신이 위).
**매 배치 커밋마다 LOG에 기록**하고, STATUS는 상태 변화 시에만 고친다.
과거 인계 문서(2026-08-13 이전)는 전부 `airi_docs/아카이브/`로 이동했다 —
현재 상태 검증에 사용 금지.

학습 중 사용량 종료나 PC 종료 준비에는 저장소 루트에서 다음만 실행한다.

```powershell
.\pause-airi-safely.ps1
```

검증된 active durable run이 정확히 하나면 자동 선택한다. 0개면 실행 중 학습 없음으로,
2개 이상이면 후보를 표시하고 중단한다. 수동 지정은 계속
`.\pause-airi-safely.ps1 -RunDir '<run-state가 있는 폴더>'`로 가능하다. 두 경우 모두
`SAFE_TO_POWER_OFF`가 출력되기 전에는 전원을 끄지 않는다.

현행 순서는 GPU 인계 §8의 체크리스트 한 곳만 따른다:
`P0 전원 종료 내구성 구현·실증 → E2 preflight/step 0 → provenance →
E1/E2 merge/package → 36 T3 → 승자 3×500 →
실제 응답·증거 제출 → 사용자 채택 판단`.

## 운영 기본값 (변경 시 이 절 갱신)

- Chat model: Mi:dm (`midm-airi:2.0-mini`) digest pin 유지 (사용자 결정 6)
- `num_ctx=2048` (주의: 고정 주제 블록+카드 병합 시 2,246토큰 — 시뮬레이션
  실측은 4096 필요. 예산 재배분은 P1 과제)
- 방송 기본 프로파일: chat/text 입력, STT/마이크 OFF (마이크는 사용자
  "마이크 테스트 시작" 요청 시에만 `-Stt on`)
- 기억 추출 OFF (통과 extractor 없음 — 다음 수순은 Stage A 재설계이지
  모델 확대가 아님)
- 런처 기본 ON (2026-08-19 `3ead135`, 사용자 결정 5·6 완료): `AIRI_IMMEDIATE_ACK=marker`·
  침묵 폴백 풀·방송 계약 v3·기억 가드(`AIRI_MEMORY_CLAIM_GUARD`).
  output moderation은 기본 OFF 유지
- 기억 추출 greybox 3종 기본 OFF·런처 미노출 (`AIRI_MEMORY_EXTRACTION_STAGE_A_CONTRACT`·
  `_ALIAS_RESOLUTION`·`_TAXONOMY_GATE`) — 켜기 전 선행 조건은 인계문 §3
- `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS`는 **유효 범위 1~30초**, 벗어나면
  경고 없이 8초로 클램프된다 (2026-08-20 실측 함정)
- 음성: 현행 일본어 참조 유지, T-05 126번 예비. 팬덤명 유보("시청자들")

## 작업 원칙 (v3)

- 모든 배치는 STATUS §1 더하기 지표 중 하나를 올려야 한다. 빼기
  지표(존댓말·이탈 등)는 회귀 가드로만 확인한다.
- 프롬프트 지시보다 결정론 계층 우선 (상한 2회 실증 — dn04·gr01).
- 완료·통과 주장은 직전 fresh 실측 증거 동반. raw 경로 시뮬레이션은 검토
  근거 불인정(11435 게이트 경유 의무 — 사용자 결정 7).
