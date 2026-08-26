# AIRI Codex GPU 인수인계 — broadcast continuity v4

갱신: 2026-08-26 10:10 KST (파일명은 과거 GPU SSoT 식별자로 유지)

현재 상태: **M4 완료(`goal_status=complete`)**. 이 문서의 E1/E2/E2-C1/E2-C2 GPU 계약과
결과는 검증된 이력으로 보존하지만 다음 세션 진입점은 아니다. live 결정론 배선·blind v6
48-report 재측정은 `AIRI-CODEX-HANDOFF-2026-08-25-M4.md`에서 종료됐고, 다음 Claude 단일
진입점은 `AIRI-CLAUDE-HANDOFF-2026-08-26-POST-M4.md`다. M5는 사용자가 그 문서의 Goal
명령을 실제로 제출한 뒤에만 활성화된다. GPU 재학습·운영 채택은 자동 승인되지 않는다.

상태: **E2-C1 NO_WINNER 진단 완료, 핸들 GROUNDING 가드+채점기 신호 SHIPPED
(2026-08-24 16:33) — 아래 -7 참조. E2-C1 학습 계약 자체는 불변, GPU 재학습(E2-C2)은
아직 미실행.
이전 스냅샷: E2-C1 TRAINED/PACKAGED, BLIND MATRIX NO_WINNER (2026-08-24 15:14) — 아래 -6 참조.
이전 스냅샷: ACTIVE, E2-C1 ADAPTER-INIT OFFLINE PASS — PUBLISHED. K=3 controlled GPU와 authoritative E2
1,600/1,600, E1/E2 merge·BF16/Q4_K_M package는 완료·미채택이다. authoritative T3는
baseline/E1/E2 각 12, 총 36 reports와 두 comparator까지 실행했으나 두 comparison이 모두
`status=fail`, paired reports 0, reason `polite violation or invented handle`로 종료해 launcher
exit 1이고 `summary.json`은 없다. winner 0이므로 3×500 campaign은 금지한다. 실패 root를
보존하고 같은 matrix나 hard gate를 반복·약화하지 않는다. E2를 초기 weight로 쓰는 새
교정 후보 E2-C1의 데이터·비오염 평가 계약은 current bytes에서 full freeze validation을
PASS했다. 앞서 확인한 `으로/로` 오류 5건과 validator 공백은 최소 수리·회귀로 닫혔다.
milestone `2e61842`와 receipt `3dba3ca`는 origin/main에 push됐고 직후 local/remote exact·
  clean·PID 0이다. E2 weights-only init과 fresh optimizer/scheduler/RNG/cursor/progress,
  manifest/run-state/checkpoint provenance와 fault 회귀의 최소 구현은 pinned CPU/offline gate를
  PASS했고 implementation `6dd2412`와 receipt `3c4b1a9`는 origin/main에 push됐다. 현재
  blocker/다음 gate는 검토 PC의 fresh mandatory reconciliation 뒤 별도 intent를 쓰는 bounded
  GPU smoke다. 이 인계 배치에서는 `gpu_authorized=false`이며 smoke를 시작하지 않는다.
  E2-C1 GPU는 0/0이고 승자·채택 모델도 아니다.**

운영 채택: **금지** (`adoption_authorized=false`, `t3_status=pending`)

기계 판독 계약: `goal_status=complete`;
`execution_order=P0_A>P0_B>E2_LAUNCH>E2_PROVENANCE>PACKAGE>T3_36>CAMPAIGN_3X500>USER_DECISION`

현재 권한: **2026-08-24 09:47 KST 사용자 `/goal`(클로드 PC, Fable 감독)로 GPU 제한 없음**이
명시됐다. E2-C1 bounded smoke → durable 본 학습 step 0 → merge/package → 36 reports → gate
판정, winner 시 3×500 campaign 즉시, no_winner 시 새 blind 봉인·E2-C2 루프 연속 진행, T3
invented-handle read-only 진단, T-05 126번 A/B 합성, 문서 commit/push가 허가됐다. 세션
경계·compact 뒤에도 intent/receipt만 쓰고 GPU 작업을 계속한다(`gpu_authorized=false` 자체
gate는 이 goal로 해제). 금지는 blind 확인 뒤 target/fixture/threshold/seed 변경·blind 재사용·
hard gate 완화, 운영 서비스 모델/태그 변경·외부 provider/extraction/greybox ON·126번 음성
운영 승격이며, 운영 채택은 campaign 결과 묶음을 본 사용자의 별도 승인이다.
(이전 08-23 `/goal`: 저장소 구현·검증, GPU 학습, 병합·패키징, 로컬 서비스, T3·캠페인,
milestone commit/push 승인 — 이 문단으로 대체.)

## -8. 2026-08-25 02:40 KST E2-C2 no_winner 종결 — 다음 방향은 사용자 결정

사용자 `/goal`(2026-08-24 17:00, GPU 무제한) 전 구간을 완주했다: 레시피 설계(1536/96,
LR 2e-5, frozen dataset 유지 — `AIRI-E2-C2-FROZEN-CONTRACT-2026-08-24.md`) → blind v3
신규 저작·봉인(`airi-e2-c2-blind-freeze-20260824-v3`, seal 도구 신설) → e2c2 하네스
(comparator/commitment/policy/launcher profile, guard=on 강제+attest) → bounded smoke
PASS → durable 본 학습 exit 0(**dev loss 2.0723→1.8219→1.6105 단조 하강**) → safe
merge(l2 0.1124) → Q4_K_M 패키징(평가 태그 `...e2c2-broadcast-v4-20260824-5eda8184...`)
→ 36/36 matrix(가드 신호 ON) → verdict **winner=null**.

핵심 수치: scores baseline 0.167511 / e2 0.201901 / **e2-c2 0.187536(E2보다 낮음 —
첫 역전)**, improved additive 2/5, invented_handle 14/27/33, 13 게이트 전부 실패.
verdict SHA `68f4107d...2e8ce5`, root `D:\AIRI-Models\airi-e2c2-blind-matrix-20260824\`.

진단(contract §7): ① dev 개선과 blind 후퇴의 절연 — 교정 480행의 좁은 도메인에 6×
선량이 표면 과적합을 만들었다(형식화된 donation composite만 0.458→0.583 개선, fact/
memory 하락). ② invented_handle 학습-단조 악화는 가드 신호 ON에서도 지속 — 행동 학습
자체의 부작용이며 채점기 보정은 절대 수만 낮췄다(v2 28/40/53 → v3 14/27/33). ③ 전
arm이 절대 최소선 2-4× 미달 — E2-C1(1 epoch/1e-5)과 E2-C2(3 epochs/2e-5) 두 점으로
"선량·LR 축 재조정으로는 게이트가 닫히지 않는다"가 실증됐다.

goal 지시 이행: campaign 미실행, 자동 E2-C3 없음, adoption_authorized=false, blind
v1/v2/v3 전부 소비(재사용 금지), 실패 root 보존. 다음 후보 방향(교정 데이터 도메인
다변화 / 결정론 계층 확대(로드맵 v3 원칙) / 게이트 체계 자체의 재검토 논의)은 사용자
결정 후 새 `/goal`로 시작한다.

## -7. 2026-08-24 16:33 KST 핸들 grounding 가드 + 채점기 신호 구현 — SHIPPED

-6의 다음 순서 ①②를 사용자 승인 goal("1과 2함께")로 완료했다.

**① invented_handle 53건 원문 진단**: 순수 날조 0건, 재호명(실제 memory 회수) 47건
(89%), 렌더러 되먹임 0건 — 모델이 이름을 지어낸 게 아니라 라이브 memory 검색이
정확히 회수한 과거 시청자를 언급했는데 채점기 `fact_tokens_used`가 director의 손수
브리핑만 알고 memory retrieval 존재를 몰라 발명으로 오채점했다. 구현 착수 전 이
47건을 문법적으로 다시 훑어 -7 설계를 정밀화했다: vocative 접미사(-님) 직후에
handle이 오는 경우는 7/53(13%)뿐이고, 나머지 46/53(87%)은 "배접천부터 꺼내야 해"처럼
일반 명사로 쓰였다 — 이 비중이 가드와 채점기 수정 각각의 실제 담당 범위를 정했다.

**② 결정론 가드 설계 반영**: 프로덕션은 roster(등록된 시청자 handle 목록)가 없다 —
표시 이름을 프롬프트 재료에서 의도적으로 뺀 설계(chat-ingress 프라이버시 경계)라,
문법 신호 없이는 어떤 한국어 단어가 "handle"인지 식별할 방법이 없다. 그래서 -6이
적었던 "roster 밖 한국어 인명을 걸러내는 가드"는 문자 그대로는 프로덕션에서 불가능
했고, 실제로는 두 갈래로 나눠 구현했다:

1. **런타임 가드** (`ollama-proxy/handle_grounding_guard.py`, 기본
   `AIRI_HANDLE_GROUNDING_GUARD=off`): 이번 턴 실제 근거 풀(유저 발화+브리핑+memory
   회수+journal)을 한 번 계산해 -님 vocative 호칭만 좁게 검사 — 근거에 없으면 안전한
   호칭으로 치환한다. 13%만 커버하는 좁은 범위이지만, 프로덕션에서 안전하게 만들 수
   있는 최대치다.
2. **채점기 신호** (`run_broadcast_chat_ab.py`/`run_broadcast_sim.py`): 같은 근거 풀
   계산의 memory/journal 부분(브리핑 계층에는 없던, 채점기가 원래 못 보던 부분만)을
   기존 in-band `airi_moderation` SSE 신호로 항상 노출한다. 시뮬레이터가 roster
   handle의 부분일치를 찾아 `fact_tokens`에 합친다 — 실제 no_winner의 87% 원인을
   여기서 처리한다. `invented_handle` 게이트의 정의(무엇이 위반인가)는 바꾸지
   않았고, 그 판정이 보는 근거 범위만 정확하게 넓혔다.

프록시 flag가 off면 완전 no-op이고(시뮬레이터 쪽 union도 자동 무동작), 두 신호
모두 하나의 grounding 계산에서 나온다(사용자 "1과 2함께" 지시).

**구현 중 발견·수리한 실제 결함 2건**: (a) `build_grounding_pools`가 flag-off
경로에서도 호출부가 `_memory_result.block` 속성을 먼저 꺼내 넘기다가 RetrievalResult가
아닌 테스트 자리표시자에서 AttributeError로 `stream_local_with_ack` 전체가 깨짐
(수리 전 `test_ollama_proxy.py` 370개 중 62 FAIL/6 ERROR로 재현) — memory_result
원본을 그대로 넘기고 flag 확인 뒤에만 getattr로 읽도록 고쳤다. (b) `from ... import
HANDLE_GROUNDING_GUARD_ENABLED`가 `ollama_proxy`와 `handle_grounding_guard`에 독립
사본을 만들어 monkeypatch 불일치 위험이 있었다 — `import handle_grounding_guard`
qualified 접근으로 단일 소스화했다. 둘 다 회귀 테스트로 고정.

**검증**: 신규 모듈 단위 16 tests, `test_ollama_proxy.py` 373(ON/OFF/grounded 통합 3건
포함, 이전 370 전부 유지) 전부 pass, `run_broadcast_sim`/`compare_e2c1_blind`/
`compare_broadcast_t3` 88 pass+1 skip, `run_broadcast_rehearsal` 85 pass(SSE 신호 캡처
회귀 2건 포함), `test_e2_c1_blind_commitment` 6 pass, `test-current-checkpoint.ps1`
PASS, work-continuity PASS, `git diff --check` 0. commit `a0020dd`(fix) + docs
3개로 `59d1836`까지 origin/main push, HEAD/local/remote exact 확인.

**E2-C1 학습 계약은 이 배치로 바뀌지 않았다** — `AIRI-E2-C1-FROZEN-CONTRACT-2026-08-24.md`
§1-10(correction 480/replay 200/mixture 680, 512/32 microsteps, LR 1e-5 등)은 그대로
frozen이다. 다음 gate는 이 진단 근거로 학습량/LR/correction:replay 비율을 재검토한
**E2-C2** 설계이고, 반드시 **새** retained blind가 필요하다(v1/v2 둘 다 이미
소비돼 재사용 금지). GPU/서비스는 idle, 관련 PID 0.

## -6. 2026-08-24 E2-C1 36-report blind matrix 결과 — no_winner, 다음 순서 확정

사용자 GPU 무제한 `/goal`(09:47 KST) 하에 smoke → 본 학습(512/32, K=3) → merge → BF16/
Q4_K_M 패키징 → 한국어 blind v2 재봉인(v1 영어 문구 결함 수리) → baseline/e2/e2-c1 ×
3 fixture × 4 seed 36 reports를 완주했다. verdict: `status=pass`(채점 정상 실행을 뜻함),
**`winner=null`**. score는 e2-c1 0.244 > e2 0.225 > baseline 0.218로 최고점이지만, hard/
legacy/perfect-rate 게이트 13개가 전부 실패했다 — 특히 `invented_handle` 위반이 baseline
28 → e2 40 → **e2-c1 53**으로 학습할수록 악화해 다른 4/5 additive 축의 개선 방향과 무관하게
winner 자격을 잃었다. `adoption_authorized=false`, 3×500 campaign 금지 유지.

사용자가 수락한 원인·다음 순서(상세는
`AIRI-E2-C1-FROZEN-CONTRACT-2026-08-24.md` §11): 512/32 microsteps는 mixture 680행
(accum 16) 기준 1 epoch 미만이었고 LR도 E1/E2의 1/5(1e-5)라 교정 신호가 과소학습됐을
가능성과, `invented_handle`이 0회를 요구하는 hard gate라 확률적 생성만으로는 구조적으로
닫기 어려울 가능성 두 가지를 함께 본다. 순서: ① 이번 matrix의 e2-c1 위반 53건 원문 진단
(blind는 이미 채점 완료라 열람 가능) ② roster에 없는 한국어 인명을 걸러내는 결정론
런타임 가드 설계·구현 ③ 가드 적용 후 남는 축은 학습량/LR 재검토한 **E2-C2**로 새 blind
봉인해 재도전. GPU/서비스는 현재 idle이고 관련 PID 0이다.

## -5a. 2026-08-24 bounded smoke 실측 — adapter-init seam 공백 3건 수리

첫 bounded GPU smoke(fresh root `airi-e2-c1-smoke-20260824-100200`, 80 microsteps/5 opt steps,
K=1, 두 arm)가 offline 검증이 놓친 실행 공백 3건을 드러냈고 전부 최소 수리·회귀로 닫았다.

1. builder `main()` self-check가 v3 manifest publish 뒤 `missing trainer argument: --model-sha256`
   exit 2 — 검증 인자에 base pin 추가(1줄) + subprocess 회귀
   (`test_builder_main_publishes_and_self_validates_adapter_init_manifest`). refused root는
   `...-095500-builder-refused`로 보존.
2. `pause-airi-safely.ps1`·launcher already-running 검사의 v2 7-key exact `inputs` 목록이 v3
   12-key run-state를 거부 — v2|v3 exact set 허용 + init pin/hex 검증, durability contract에
   AST 추출 기반 4-case 회귀. 수리 뒤 실측 gateway가 `SAFE_TO_POWER_OFF`를 1회 방출했다.
3. durable resume가 init flag 4종을 제거해 trainer expected pins가 `init_mode=fresh-lora`가 되고
   checkpoint pins(`adapter-weights-only`+initialization)와 exact 불일치 — adapter-init run 전면
   재개 불능(P0). 현행 계약: resume는 init flag를 유지, trainer는 resume+init 조합에서 disk
   재검증으로 identity/pins만 구성하고 weight는 checkpoint 복원이 덮어씀, fresh-state receipt는
   fresh run 전용. 상호배제 문구 2종은 코드에서 제거됐다. cpu-smoke end-to-end 회귀
   (`test_cpu_adapter_init_run_resumes_from_its_own_checkpoint`)와 pre-fix fail-first 재현으로 고정.

smoke 실측 receipt: baseline arm terminal exit 0(80/5, fresh-state receipt에 상속
optimizer/scheduler/rng/cursor 전부 false, dev 2.5150, peak CUDA 5.85 GB), safe arm paused-safe
16/1 + `SAFE_TO_POWER_OFF`, resume은 공백 3으로 failed — failure root 보존. 수리 후 pinned
combined `158 passed, 5 skipped`, durability contract process exit 0 literal PASS. **수리로
trainer/runner source SHA가 바뀌어 smoke 두 arm은 fresh root에서 재실행해야 하며**, 그 PASS가
본 학습 gate다. frozen 학습 값·dataset·blind는 불변.

## -5. 2026-08-24 E2-C1 adapter-init offline PASS / published

- trainer는 E2 adapter model/config/artifact-manifest를 lowercase SHA와 source base SHA,
  LoRA config/target modules로 검증하고 `PeftModel.from_pretrained(..., is_trainable=True)`로
  weight만 초기화한다. PEFT load 직전 held descriptor를 다시 stat/hash하며 checkpoint resume와
  init을 상호배제한다(→ **2026-08-24 smoke 개정으로 대체**, 아래 -5a). optimizer/scheduler/RNG/
  cursor/progress는 새 run에서 0부터 시작한다.
- input-manifest builder·durable runner·equivalence verifier는 schema v3 `init_mode`와 E2 run/
  model/config/artifact/inventory provenance를 결속한다. v2는 기존 key set만 허용한다. adapter
  inventory는 extra file·empty/undeclared directory·link/reparse·special entry를 fail-closed한다.
  durable resume에서는 E2 init flag를 재주입하지 않고 같은 process tree의 checkpoint full-state
  resume만 수행해 초기화와 resume 의미를 섞지 않는다.
- pinned Python 3.12 pycompile은 exit 0, trainer/runner/verifier focused suite는 각각
  27 passed/2 skipped, 50/2, 67/1이고 combined는 144 passed/5 skipped다. work-continuity,
  full `test-current-checkpoint.ps1`, repository diff-check도 PASS했다.
- actual E2 read-only helper probe는 run id `v4-e2-seed42-1600-20260823-074326`, base
  `394b6624...f506`, adapter/config/artifact `2a72292c...5c5b`/`e01129ea...2b0`/
  `70998cff...7195`와 3-file artifact inventory를 builder/trainer 양쪽에서 exact 확인했다.
- final code SHA는 builder/runner/trainer/verifier `415934b4...d218`/`df522273...24ec`/
  `6b19ad5c...43f8`/`5bbe1071...335f`; tests는 `9e2e4a4f...4038`/
  `391d45cb...ee4`/`04a54b4f...8ee3`다.
- implementation `6dd24129d3d374fb9add1080aca2838ada1267b0`과 receipt
  `3c4b1a9fed9be7f7e4adf6c9434b1e284bd8fc0d`는 `3d7d0e3..3c4b1a9 main -> main`으로
  origin/main에 push됐고 HEAD/local·remote exact, clean, related PID 0, GPU AIRI workload 0,
  E2-C1 0/0을 확인했다. 검토 PC는 mandatory reconciliation과 별도 bounded-smoke intent 뒤에만
  fresh external smoke root를 만들 수 있다. 이 문서 finalization에서는 GPU를 시작하지 않는다.

## -4. 2026-08-24 E2-C1 frozen-contract first milestone

- latest Goal은 E2 adapter weight를 검증된 초기값으로 쓰되 fresh optimizer/scheduler/RNG/
  cursor로 새 교정 후보 `E2-C1`을 만드는 것이다. 같은 v4의 E3 반복이 아니다.
- 첫 milestone은 GPU가 아니라 correction 480 + v4 replay 200 + mixture 680, retained blind
  3종, split/seed/max-step/LR/scheduler/checkpoint/metric 계약의 동결·검증·origin/main
  push다. 현재 E2-C1 progress는 0 microstep/0 optimizer step이고 durable runner/trainer 0,
  GPU 학습 0이다.
- 2026-08-24 02:18 KST milestone `2e61842ba72875bff4d473653b635541e6e0b82a`와 receipt
  `3dba3ca43a161d69f677eec2a8d10c3ddd061fca`를 `1de57a2..3dba3ca main -> main`으로
  push했다. 직후 HEAD/local main/local origin/main/remote main exact, worktree/stage clean,
  related AIRI PID 0, E2-C1 0/0이다. E2 terminal state/checkpoint/adapter/report와 T3
  36/36/89/72/2 failure root, external blind exact 5-file sealed receipt는 기존 크기·SHA와
  exact하고 로그·T3 report·blind fixture body는 읽지 않았다.
- final sample/조사 감사에서 확인했던 exact five malformed targets는 다음이었다:
  `e2c1-long_callback-001-v3`, `e2c1-complete_show_arc-002-v2`, `-003-v1`, `-010-v2`,
  `-011-v1`. generator/helper와 independent verifier에 `(으로,로)` 및 받침 ㄹ의 `로`
  예외를 추가하고 direct template와 mutation regression을 최소 수정했다. write-free 감사
  mismatch 0 뒤 overwrite 1회와 current generated 전수 감사 mismatch 0을 확인했다.
- current bytes는 pinned pycompile, full unit 12, blind pytest 5, generator byte check,
  repository/external verifier, independent counts/splits/family/group/semantic/grammar/replay/
  collision 감사, continuity/diff/security를 모두 PASS했다. correction/replay/mixture는
  480/200/680, train correction:replay는 352:160이고 blind는 `response_viewed=false`다.
- 세부 frozen 계약과 exact dataset SHA는
  `AIRI-E2-C1-FROZEN-CONTRACT-2026-08-24.md`를 따른다. 현재 `freeze_status=pass`이고
  publication gate도 PASS했다. 다음 adapter-init seam read-only 감사와 필요한 경우 최소
  구현·fault 회귀가 검증·push되기 전에는 `gpu_authorized=false`다.
- 검토 PC의 첫 동작은 mandatory 5문서→Goal/Git/PID/E2/T3/blind read-only 대조다.
  PID 0이면 pause를 호출하지 않는다. 다음 동작은 trainer adapter-init/provenance/fresh-state/
  run-state/checkpoint/safe-pause seam의 read-only 감사다. counts/splits/replay, v4/base/E2,
  seed 42·batch 1·accumulation 16·seq 2048·512 microsteps·LR 1e-5·constant/K=3,
  blind fixture/seed/threshold는 바꾸지 않는다. clean publication 뒤에도 GPU를 자동 시작하지
  않고 trainer adapter-initialization seam을 별도 intent에서 먼저 감사한다.

## -3. 2026-08-23 E1/E2 사용자 검토와 교정 학습 경계

- baseline/E1/E2는 서로 다른 기반 모델이 아니라 같은 Mi:dm 계열이다. baseline은 기존
  broadcast v3, E1은 continuity v4 1 epoch, E2는 같은 v4 2 epoch 후보다.
- 사용자가 직접 판단할 원본은 external T3 root의 `reports/e1`·`reports/e2` 각 12개,
  총 24 schema `airi.broadcast-sim-report.v1` JSON이다. 각 파일의 `summary`는 run 집계,
  `rows`는 턴별 metric/action/trace/receipt, `transcript`는 response-bearing 입력·응답이다.
  원본 response, packet, runtime DB와 로그는 Git 금지이며 외부 root에만 보존한다.
- 1,248 turns씩의 E1→E2 aggregate는 topic `572→586`, fact `180→193`, memory
  `8→11`, invented-handle turns `46→37`, fallback `7→4`, callback `6→8`, complete arc
  `1→5`로 E2가 상대 우세다. E1 donation은 `56/56`, E2는 `55/56`이다. transport와 polite
  violation은 양쪽 0이다.
- E2 dev loss history는 epoch 1 `2.893371758116589`, epoch 2
  `2.735453106217887`이고 selected epoch은 2다. 이는 학습 신호가 남았다는 근거지만
  same-data 3 epoch가 방송 hard gate를 통과한다는 근거는 아니다.
- final blind만 보면 invented handle이 E1 26에서 E2 34로 악화했고 long memory probe는
  양쪽 모두 0/12다. E2는 T3 winner나 운영 채택 모델이 아니며, 사용자 승인 없는 기본
  서비스 모델 변경과 공식 campaign은 계속 금지한다.
- 후속 학습을 원하면 단순 same-data epoch 연장이 아니라 identity/unknown-name,
  장기 callback, donation/addressee, stale-context 전환을 보강한 교정 데이터와 새 비오염
  blind, 후보 명칭·범위를 별도 intent로 고정한다. 이 설계 승인 전 GPU 학습은 시작하지 않는다.

## -2. 2026-08-23 authoritative T3 terminal FAIL receipt

- external root `airi-t3-authoritative-20260823-175152`에서 baseline/E1/E2 각 12,
  총 36 reports와 36 packets가 게시됐다. 모든 arm의 aggregate transport failure는 0이고
  run별 local service/durable receipt 무결성은 보존됐다.
- 마지막 `e2-3-20260822.json`은 419,613 bytes SHA
  `2c8d74bd17a52905abc7732c8e74b58c1a9dc1a21b59c3d6d7298805663c140c`다.
  실제 집계는 topic 99/216, fact 31/111, donation 4/4이나 memory 0/3,
  continuity callback 4/12, complete arc 3/12, invented handle 11이다.
- arm별 aggregate invented handle은 baseline/E1/E2 `30/46/37`, memory는
  `5/36`·`8/36`·`11/36`, fact는 `173/752`·`180/752`·`193/752`, donation은
  `56/56`·`56/56`·`55/56`이다. baseline에는 polite violation 1건도 있다.
- `baseline-vs-e1.json`과 `baseline-vs-e2.json`은 각각 196 bytes, 같은 SHA
  `5f2b42135a2d2a6cdae23d4e512b3754807bbbdcdc3938b9d0d1940867d83afa`, schema
  `airi.broadcast-sim-t3-comparison.v1`, `status=fail`, adoption false, paired reports 0,
  reason `polite violation or invented handle`이다. launcher는 이를 PASS로 승격하지 않고
  exit 1했으며 `summary.json`을 게시하지 않았다.
- report/packet/evidence/runtime/comparison inventory는 36/36/89/72/2 files이고 manifest
  SHA는 `e5241341...16b4`/`00b90c95...859a`/`7cb97aea...3dee`/
  `0417f814...4e8a`/`5a4793b9...d75`다. launcher/관련 process/owned listener는 종료 뒤 0이다.
- T3 winner와 campaign output은 0이다. hard gate 우회나 같은 공개 blind matrix 반복은
  증거가 아니므로 금지한다. 후속 학습 iteration에는 오염되지 않은 새 평가 설계와 별도
  intent가 필요하다. 운영 채택과 기본 서비스 모델 변경 금지는 유지한다.
- terminal failure 다섯 SSoT commit `d3724b1ea3d0df7cff8e14fd511f4b8244b8838c`은
  `90a436e..d3724b1 main -> main`으로 origin/main push됐다. push 뒤 HEAD/local·remote
  origin/main exact, launcher/관련 process/owned listener 0, summary absent를 확인했다.

## -1. 2026-08-23 T3 journal false-success 수정 receipt

- E2 `v4-e2-seed42-1600-20260823-074326`은 1,600/1,600 microsteps·100/100 optimizer
  steps, selected epoch 2 dev loss `2.735453106217887`로 완료됐다. E1 dev
  `2.8938066467`보다 낮고 adapter/config/report/provenance SHA가 검증됐다.
- E1/E2 safe merge와 BF16·Q4_K_M GGUF, exact tag/digest model manifest는 외부 모델
  root에 완료됐다. 어느 후보도 운영 채택하거나 기본 서비스 모델로 바꾸지 않았다.
- T3의 400 `journal_pending`은 같은 trace의 늦은 append가 아니었다. OpenAI SSE broad
  exception과 directed-repeat local failure가 public fallback과 `[DONE]`을 보낸 뒤에도
  journal을 예약하지 않는 false-success였다. aggregate `/health.last_outcome=appended`는
  이전 trace 값이었다. 전달된 exact fallback을 terminal 전에 durable journal로 예약하도록
  두 경로만 최소 수정했다.
- py_compile, targeted 2/2, 영향 suite 113/113, proxy 전체 370/370, broadcast simulator
  63/63, work-continuity와 `test-current-checkpoint.ps1`이 PASS했다.
- 외부 smoke root `airi-t3-journal-smoke-20260823-174232`의 report는 4,510 bytes,
  SHA `6193fb80c0c9072af92ea8fb222a54da172b6ab05e3e364149f4326772126886`이고 packet은
  783 bytes, SHA `e89f9e0043d77e041f3517668f7a084b2ab4c6159f1a6f0a0686f018e5777fcc`다.
  response-bearing report/packet과 runtime DB는 Git 금지 외부 산출물로 유지한다.
- smoke 종료 뒤 관련 service/listener는 0이다. GPU 학습은 없고 Ollama baseline 추론
  모델만 로드돼 있다. authoritative T3 36과 승자 campaign은 아직 PASS가 아니다.
- fix/test와 필수 SSoT 5종은 Conventional commit
  `80160a14179a0685a0b15b6bdbc724cd68c2e5b1`로 묶여
  `9724833..80160a1 main -> main` push됐다. push 직후 HEAD/local/remote exact, worktree
  clean이었다. 이 push receipt 문서 commit 뒤 다시 clean을 확인하고 T3 36으로 간다.

## 0. 2026-08-23 P0 로컬 배치 최종 검증 receipt

- 07:18 KST fresh K=3 controlled GPU root
  `airi-controlled-gpu-20260823-051231`의 무중단 baseline과 실제 optimizer-boundary
  `SAFE_TO_POWER_OFF` pause/checkpoint/resume arm이 모두 terminal 480 microsteps/30 optimizer
  steps로 완료됐다. safe arm은 checkpoint event 12개, request/ack/resume-accepted history
  exact 3개/live control 0이고 관련 PID 0이다. 두 arm의 정상 checkpoint 구간은 각 최소 4개,
  실제 event 기준 baseline max training/durable `549.6979634`/`552.845175`초,
  safe arm `230.3527189`/`234.870925`초로 모두 600초 아래다.
- paired verifier 첫 실행은 actual adapter row 집합과 SHA가 exact인데 Windows producer의
  case-insensitive `Path` 순서와 verifier의 case-sensitive 문자열 순서가 `README.md` 위치를
  달리해 exit 2/receipt absent로 거짓 거부했다. verifier 정렬 한 줄을 producer와 같은
  platform `Path` 순서로 바꾸고 targeted 회귀를 추가했다. pinned pycompile+targeted
  `1 passed, 62 deselected`, verifier suite `62 passed, 1 skipped`, actual preserved GPU
  verifier 재실행 exit 0, final `test-current-checkpoint.ps1` PASS다.
- 권위 GPU equivalence receipt는 48,323 bytes SHA
  `d913992e93ab81035e586fcd5587b7f565ad58fd685759f61adb035d688e84b9`, schema v1,
  `pass=true`, `adoption_authorized=false`다. manifest/config SHA, seed 42, batch 1,
  accumulation 16, K=3, safe pause 16/1이 exact하고, recursive checkpoint comparator는
  672 tensors·rtol/atol 0·max abs/rel diff 0이다. governed normal interval count 10,
  minimum gate 4, max `551.5176357`초다. baseline/safe final-root·producer/progress/report/
  adapter manifest와 pause history를 모두 결속했다. controlled GPU P0-B는 완료다.
- verifier/test+five SSoT commit `87dfabdfa482a22694cdc343d8ec938d979b9665`와 commit
  receipt `29080bed9227887ff3336d7c2c42997440d39df9`는
  `0454ca8..29080be main -> main`으로 origin/main push됐다. push 직후 HEAD/local·remote
  origin/main exact, worktree clean, 관련 PID 0이다. E2 adapter/report는 absent, 기존 로그
  각 0 bytes, E2 microstep 0이다. actual push receipt five-doc final commit/push와 다시
  HEAD=origin/main·clean·PID 0을 확인하기 전에는 E2를 시작하지 않는다.
- 04:30 KST 첫 controlled GPU K=5 baseline은 480/480 microsteps·30/30 optimizer
  steps까지 계산했으나 PASS가 아니다. authority state는 `failed` revision 392, exit 0/
  `supervisor-durablerunnererror`, latest checkpoint 7 SHA `c65f7bac...d04f1`, 관련 PID 0,
  final evidence root absent다. checkpoint event의 normal training interval은
  569.416106/548.424438/502.980348/705.902827초로 실제 600초 상한을 넘었다. root
  `airi-controlled-gpu-20260823-031152`는 실패 증거로 보존하며 같은 K=5를 반복하지 않는다.
- final-root 첫 실패는 producer internal `artifact-manifest.json` SHA를 runner와 pause가
  adapter directory inventory SHA와 비교한 의미 혼동이었다. runner/pause를 exact internal
  manifest receipt row SHA에 결속하고 PowerShell fake fixture를 actual artifact schema로
  이관했다. targeted runner 1 PASS, pinned 5-module+네 Python suite
  `146 passed, 5 skipped`, actual-process PowerShell durability literal PASS, final offline
  checkpoint PASS, 관련 PID 0이다. repo diff/security도 exact 6-path/hit 0이다.
- 이 검증 배치는 `18d0bc6bc6df22e6667a4647945bfcff5701d420`
  (`fix: bind final adapter evidence`)로 commit됐고 `5f2f50e..18d0bc6 main -> main` push됐다.
  HEAD/local·remote origin/main exact, 관련 PID 0이다. WORKING/handoff/roadmap status/log/NEXT의
  actual push receipt를 별도 docs commit/push하고 clean을 확인해야만 K=3 fresh controlled
  GPU로 이동한다. E2는 계속 microstep 0이며 운영 채택·기본 모델 변경 금지는 유지한다.
- 03:04 KST Goal 도구 status=`active`; exact implementation commit
  `911d082dcf1768a5145bd34d56a19f82deb9d248`을 origin/main에 push했다
  (`32830a4..911d082 main -> main`). HEAD/local origin/main/remote main은 모두
  `911d082dcf1768a5145bd34d56a19f82deb9d248`다. actual push receipt용 5개 SSoT만
  로컬 갱신 중이며 관련 runner/trainer/test/verifier PID와 식별 가능한 AIRI GPU workload는
  0, E2 microstep은 0이다. source/chat/base/E1 크기·SHA는 exact, E2 adapter/report·
  D: durable state·T3·campaign은 absent, E2 로그는 각 0 bytes다.
- 03:07 KST actual implementation-push receipt 5-doc commit
  `a898ff82939ab59dc3fd84d2fb6214ecf381113e`도 origin/main에 push됐다
  (`911d082..a898ff8 main -> main`). 확인 시점 HEAD/local·remote origin/main은 exact,
  worktree clean, 관련 PID 0, E2 adapter/report absent다. final live receipt commit/push 뒤
  같은 clean 경계를 재확인하면 다음 단계는 fresh controlled GPU preflight다.
- 최종 P0 코드 receipt: 핀된 5-module pycompile+네 Python suite exit 0,
  `145 passed, 5 skipped in 34.84s`; actual-process PowerShell durability exit 0/literal
  `AIRI training durability contract: PASS`; 전체 `test-current-checkpoint.ps1` exit 0/
  최종 offline checkpoint PASS; 각 post-run 관련 PID 0이다.
- 한 차례 독립 최신-byte 감사는 P0=0/P1=4였다. 고정된 네 원래 P1만 최소 수정했고
  verifier targeted `61 passed, 1 skipped`, launcher dynamic/static/AST, 최종 Python과
  actual-process PowerShell로 exact closure를 검증했다. 사용자 동결선대로 새 감사
  라운드는 추가하지 않았으며 현재 잔여 로컬 P0/P1은 0이다.
- final test/launcher/verifier SHA는 `738630d9...8756c6`/`856c4322...e9acda`/
  `621de009...230799`, 12-file path+size+SHA manifest는
  `5908729735313b72fedaa309c62d04a20472d049900de192817ea7fb975a4a5b`다.
  repo 기본 diff-check exit 0/whitespace error 0, 17-path 1,167,298 bytes의 금지
  산출물·credential·민감 literal·개인 경로 hit는 0이다.

- 이전 01:00 pause 인계 당시 Goal 도구 status는 `paused`, 세부 상태명은
  `goal_status=paused-user-session-handoff`였으며 complete/cancel은 아니었다. 최신
  `/goal` resume가 이를 대체해 현재 실제 status는 `active`다.
- Git: HEAD=`32830a43556ba7704a39bd9094f128a5a98dd7d7`,
  origin/main=`32830a43556ba7704a39bd9094f128a5a98dd7d7`.
- staged 0, modified 16, untracked 1이다. modified exact 목록:
  `NEXT-SESSION.md`,
  `airi_docs/로드맵/AIRI-ROADMAP-LOG.md`,
  `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md`,
  `airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-08-21.md`,
  `airi_docs/진행중/AIRI-WORKING-STATE.md`,
  `ollama-proxy/training/behavior_training_checkpoint.py`,
  `ollama-proxy/training/durable_training_runner.py`,
  `ollama-proxy/training/tests/test_behavior_training_checkpoint.py`,
  `ollama-proxy/training/tests/test_durable_training_runner.py`,
  `ollama-proxy/training/tests/test_train_airi_behavior_lora.py`,
  `ollama-proxy/training/tests/test_verify_airi_behavior_gpu_equivalence.py`,
  `ollama-proxy/training/train_airi_behavior_lora.py`,
  `ollama-proxy/training/verify_airi_behavior_gpu_equivalence.py`,
  `pause-airi-safely.ps1`, `run-airi-behavior-training-durable.ps1`,
  `test-airi-training-durability.ps1`. untracked exact 목록:
  `ollama-proxy/training/build_airi_behavior_input_manifest.py`.
- AIRI 관련 Python/PowerShell PID와 실제 durable GPU trainer는 0이다. 따라서
  `pause-airi-safely.ps1`은 실행하지 않았다. D:의 실제 durable `run-state.json`/
  checkpoint도 0이다. 보존된 synthetic 실패 root의 state/anchor 파일은 삭제하지 않았다.
- v4 source `7,056,597` bytes SHA `43f9c1ed...eba2ed`, chat `6,886,621` bytes
  SHA `96cc223c...6eb44`, base `4,611,084,960` bytes SHA `394b6624...8f506`,
  E1 adapter `56,318,520` bytes SHA `379b2a5a...305041`, config `863` bytes SHA
  `930eddf6...3de2c`, report `1,287` bytes SHA `0f71b042...b41f41`로 고정값과
  exact 일치한다.
- E2 adapter/report, T3 matrix, live campaign은 없다. 기존 E2 stdout/stderr는 각각
  0 bytes이며 본문은 읽지 않았다.
- 이전 pause 당시 마지막 actual-process 실패 root `airi-durability-contract-ff7cec...`와
  이후 fixture 원인 진단 root `dd1dbf...`/`24fed...`는 삭제하지 않고 보존한다. 최종
  PowerShell PASS가 이 실패 receipt를 대체했으며 세 root의 로그 12개는 모두 0 bytes다.
- 현재까지 검증·구현된 P0: origin/main의 P0-A full-state/RNG/provenance checkpoint,
  same-volume atomic 승격·latest/previous·격리, exact-pin resume, durable runner와
  run-state, optimizer-boundary safe-pause/자동 탐지의 이전 offline fault 계층이다.
  로컬 배치의 no-follow input snapshot/manifest, authenticated run-state lineage와
  recovery, producer evidence/index/event 결속, trainer-bound launcher, anchor-bound pause는
  위 최종 통합·offline gate로 검증됐다.
- 남은 P0-B 실증은 clean timestamped 외부 root의 controlled GPU 무중단 대 safe
  pause/checkpoint/resume 동등성과 실제 checkpoint 간격 ≤600초·최소 4구간뿐이다.
  이미 닫힌 P0-A나 현 로컬 배치를 새 기준으로 재감사하지 않는다.
- final-evidence P0 code/test/milestone commit `18d0bc6`은 **origin/main push 완료**다.
  actual push receipt 5-doc의 별도 commit/push 뒤 HEAD=origin/main·clean worktree를 다시
  확인해야만 controlled GPU로 이동한다. 운영 채택과 기본 모델 변경 금지는 유지한다.
- 새 세션/compact는 다섯 SSoT 전체 읽기와 read-only 대조를 먼저 한다. 현재 다음 상태
  변경은 exact 5-doc stage/cached 검증과 docs receipt commit/push이며, 성공 뒤 clean K=3
  GPU preflight를 별도 intent로 기록한다.
- pause 인계 중 위 focused 검사 1회는 exit 1,
  `Work-continuity contract missing: recognized goal status`였다. 검사기가 새 pause
  상태를 아직 인식하지 못한 것이며 문서를 active로 되돌리거나 test를 수정·재실행하지
  않았다. 같은 시점 tracked 16파일 scoped `git diff --check`는 exit 0이다. 따라서
  continuity PASS는 없고 이 결과 자체가 명시적 failure receipt다. 새 세션에서 명시적
  resume로 상태 문서를 갱신한 뒤 위 gate를 실행한다.

세션 시작·goal resume·재부팅·compact 직후에는 이 문서보다 먼저
`AIRI-WORKING-STATE.md`를 전체 읽고 실제 goal status, HEAD/worktree,
PID·command line, 산출물·SHA와 대조한다. live state는 현재 행동과 receipt를,
이 인계서는 검증된 장기 기준과 exact 명령을 담당한다.

이 문서가 다음 Codex/Claude PC 세션의 GPU 작업 단일 진입점이다. 이전
`AIRI-CODEX-HANDOFF-2026-08-20.md`의 방송 학습 진행 상태를 대체하되,
그 문서의 greybox·추출 게이트 이력은 과거 근거로 보존한다.

## 1. 반드시 지킬 상태

- P0 checkpoint/resume/durable runner/safe-pause와 전원 종료 복구 실증 전에는
  E2를 시작하지 않는다. 이후 단계도 §8 순서를 fail-closed로 따른다.
- 현재 서비스 모델이나 기본 태그를 v4로 바꾸지 않는다.
- 외부 chat/search, 기억 추출, greybox는 계속 OFF다.
- E1/E2는 실제 11435 live-context T3와 사용자 승인 전까지 후보일 뿐이다.
- 모델 weight, adapter, GGUF, report, 로그는 `D:\AIRI-Models`에만 두고 Git에
  넣지 않는다.
- T3 baseline/candidate는 동일 fixture, seed, memory arm, contract, history,
  max tokens, proxy flags, isolated memory/knowledge DB로 실행한다.
- 단일 seed, raw Ollama 직결, caller system prompt, summary-only 결과는 근거로
  인정하지 않는다.

## 2. 확정된 v4 corpus

파일:

- `ollama-proxy/training/seed/airi_broadcast_continuity_v4.jsonl`
- `ollama-proxy/training/seed/airi_broadcast_continuity_v4_chat.jsonl`
- `ollama-proxy/training/synthesize_broadcast_continuity_v4.py`
- `ollama-proxy/training/tests/test_synthesize_broadcast_continuity_v4.py`
- 40개 author card partition (`..._cards_m01..m16`, `c1/c2/c3a/c3b`,
  `d01..d10`, `g1/g2a/g2b/g3`, `n1/n2/n3a/n3b`)

고정값:

- source SHA-256:
  `43f9c1ed1abf1d32c94329de81d8ba9ddef93f560ef914814d34e0520eeba2ed`
- chat SHA-256:
  `96cc223ca5915355394480b60b459d9d039ffad4b47304974c5d939d4686eb44`
- 1,000행, train/dev/test `800/100/100`
- family: memory known 256, memory unknown 64, donation 180,
  briefing/topic 250, grounding/capability 130, natural broadcast 120
- 교차 split fact/update/decoy token 충돌 0
- `v4-v4-` ID 0, replacement character 0, source/chat target 불일치 0
- exact trainer token 수: all max 2,010, train max 2,010;
  `>2016` 0. 따라서 `max_seq_len=2048`을 낮추지 않는다.

재생성·검증:

```powershell
python ollama-proxy/training/synthesize_broadcast_continuity_v4.py --overwrite
python -m unittest ollama-proxy/training/tests/test_synthesize_broadcast_continuity_v4.py -v
```

직전 결과: generator 8/8 PASS. 독립 한국어 전수 감사에서 거짓 행동 주장,
근거 없는 기억 소유권, template/ID/split 누출 blocker 0. 실제 파일 bytes와
in-memory render가 두 SHA에 exact 일치했다.

## 3. QLoRA 실행 결과

공통 입력:

```text
Python: D:\AIRI-Models\venv-midm-broadcast-qlora-py312\Scripts\python.exe
Base: D:\AIRI-Models\airi-broadcast-v3-20260821\merged-hf
Base model.safetensors SHA-256:
394b6624de810fd0630ba451c31b3530cc26444ba0e1fa7d98842b6af6e8f506
GPU: RTX 3060 Ti 8GB
r=8, alpha=16, dropout=0.05, lr=2e-5, seq=2048,
batch=1, gradient_accumulation=16, seed=42
```

### 3.1 1-step probe — 완료

- dev loss `3.4270614578`
- peak PyTorch CUDA `5,400,689,664` bytes
- output:
  `D:\AIRI-Models\airi-broadcast-v4-20260821\probe-r8-seq2048-step1-lr2e5`

### 3.2 E1 — 완료, 아직 미채택

- 800 microsteps / 50 optimizer updates
- train first3 mean `3.3845` → last3 mean `2.9151`
- dev loss `2.8938066467`
- peak PyTorch CUDA `6,134,145,536` bytes
- adapter:
  `D:\AIRI-Models\airi-broadcast-v4-20260821\adapter-r8-seq2048-e1-lr2e5`
- report:
  `D:\AIRI-Models\airi-broadcast-v4-20260821\adapter-r8-seq2048-e1-lr2e5-report.json`
- adapter model SHA-256:
  `379b2a5aba1ea5750e0c0d42dbb3b6830f53085b2e61a063f4e3222138305041`
- adapter config SHA-256:
  `930eddf68b9b61936a6b905249f047ba539dc77c04f14f99fa5015333963de2c`
- report SHA-256:
  `0f71b042a74379623197129b609251254c174df3ef026d076523beffb5b41f41`

독립 감사 결과: dataset/base pin exact, LoRA/CAUSAL_LM rank 8, base weight 복사
없음, `training_authorization=true`, `adoption_authorized=false`,
`t3_status=pending`.

### 3.3 E2 — 중단, 재실행 필요

사용량 한계가 가까워졌다는 사용자 요청에 따라 첫 실행은 약 14분, 인계 재검증 중
시작한 두 번째 실행은 약 3분 시점에 각각 Ctrl+C로 안전 중단했다. 컴퓨터 재부팅 후
세 번째로 독립 프로세스를 시작했지만 pause 요청 직후 checkpoint 전에 안전 종료했다.
2026-08-22 read-only 재감사에서 trainer 0, 다음 두 경로 0을 확인했고, 세 번째 시작
흔적인 `e2-train.stdout.log`와 `e2-train.stderr.log`도 각각 0 bytes다. 계산 이력은
있지만 재개 가능한 상태는 없으므로 동일 seed의 step 0부터 다시 실행한다.

```text
D:\AIRI-Models\airi-broadcast-v4-20260821\adapter-r8-seq2048-e2-lr2e5
D:\AIRI-Models\airi-broadcast-v4-20260821\adapter-r8-seq2048-e2-lr2e5-report.json
```

### 3.3.1 PRE-P0 PARAMETER REFERENCE — DO NOT RUN

아래 direct trainer block은 검증된 E2 파라미터를 보존하는 **참고용**이며 실행
명령이 아니다. 아직 checkpoint/durable runner 인터페이스가 없으므로 직접 실행하면
§8의 P0 gate를 우회한다. P0 구현 receipt에서 이 파라미터를 감싼 authoritative
durable runner 명령으로 교체하기 전에는 E2 실행 근거로 사용할 수 없다.

```powershell
$Py = 'D:\AIRI-Models\venv-midm-broadcast-qlora-py312\Scripts\python.exe'
& $Py .\ollama-proxy\training\train_airi_behavior_lora.py `
  --mode cuda-qlora `
  --dataset .\ollama-proxy\training\seed\airi_broadcast_continuity_v4_chat.jsonl `
  --dataset-sha256 96cc223ca5915355394480b60b459d9d039ffad4b47304974c5d939d4686eb44 `
  --model-dir D:\AIRI-Models\airi-broadcast-v3-20260821\merged-hf `
  --model-sha256 394b6624de810fd0630ba451c31b3530cc26444ba0e1fa7d98842b6af6e8f506 `
  --seed 42 --lora-r 8 --lora-alpha 16 --lora-dropout 0.05 `
  --learning-rate 2e-5 --max-seq-len 2048 --batch-size 1 `
  --gradient-accumulation 16 --max-steps 1600 `
  --output D:\AIRI-Models\airi-broadcast-v4-20260821\adapter-r8-seq2048-e2-lr2e5 `
  --report D:\AIRI-Models\airi-broadcast-v4-20260821\adapter-r8-seq2048-e2-lr2e5-report.json
if ($LASTEXITCODE -ne 0) { throw 'v4 E2 training failed' }
```

예상: 1 epoch 실측 약 64분이므로 E2 전체는 약 2시간. E2 report의 epoch 1/2
dev loss와 `selected_dev_epoch`을 E1 `2.8938066467`과 비교한다.

## 4. 병합·GGUF 패키징 — E2 완료 뒤

도구:

- `ollama-proxy/training/merge_airi_behavior_lora.py`
- `ollama-proxy/training/package_airi_gguf.py`
- converter b10375 script SHA:
  `21b70f59d9cfa5f3963bfe9b1c648c16b1fdeca9cff67778bf776d1137b267b5`
- quantizer bundle SHA:
  `354c70ff428a9805f64749d4b80736567488119b656e7819e8ff9a09221aadbe`
- Ollama exe SHA:
  `a64341018083a575267896f8117e66cca0a04262a963bfb3053e46ce2fc4acda`

E1 merge pins:

```text
base artifact manifest: bac2b8153cbe3e960a4a95163f6806eeee72a482c1cffbbd35fe8e0efc108209
E1 adapter artifact manifest: 9254f81d0d62e782caa0e7c04e3214e55ba246a979ce8515a2aedf302e38b05b
```

E2 adapter SHA와 manifest SHA는 E2 완료 후 계산한다. 두 후보 모두
HF safe-merge → BF16 GGUF → Q4_K_M 순서로 패키징한다. 패키저가 128-bit
build suffix를 붙이므로 최종 태그는 각 `package-evidence.json`에서 읽는다.
패키징은 모델 태그를 만드는 상태 변경이지만 운영 채택은 아니다.

## 5. T3 — 36 reports 완료, comparator FAIL

2026-08-23 authoritative 실행은 exact model manifest SHA `42e94892...3bde`와 승인 fixture
manifest를 사용해 36/36 reports를 게시했다. 두 comparator가 위 §-2의 품질 hard gate에서
실패해 PASS summary와 승자는 없다. 아래 계약과 명령은 실행 당시 고정 입력의 기록이며 같은
matrix 재실행 명령이 아니다.

baseline v3:

```text
tag: midm-airi:2.0-mini-broadcast-v3-q4-20260821-04d64a38eeb4638babb90b12647d3704
digest: e683802b7e9bc72dc0c0ad094bedf4c49142c6248c1b148d3100001c04ff5291
```

fixtures/seeds:

- first calibration canonical SHA
  `0d558c0ce3e019569673ed96f4f171e3464e1e044028e7de6b7ede9d5b8085d6`:
  `11,22,33,20260818`
- second heldout calibration canonical SHA
  `c2ae8a2db00f8f0ed8bd4ee4d909bde965bcbf18dd359b8dbaf340f4c65a57b1`:
  `11,22,33,20260818`
- third final blind 180-minute canonical SHA
  `ddb43f03f88dacff70ebd8a6221274e51348e01e9fe542153139c0330bd52b61`:
  `44,55,66,20260822`

각 baseline/E1/E2 모델에 12 reports, 총 36 reports가 필요하다. 공통 설정은
`--memory-arm seeded --contract on --protocol operational --author-format runtime
--history-turns 8 --max-tokens 220 --briefing on --briefing-evidence on --acts on
--live-broadcast-context on`이다.

전용 launcher `run-airi-broadcast-t3-matrix.ps1`과 오프라인 계약 테스트
`test_broadcast_t3_matrix_launcher_contract.py`를 추가했다. 이전 반려 초안의 배열 비교,
health schema, memory-arm confound, 반복 디렉터리 문제를 모두 제거했으며 다음을
fail-closed로 고정한다.

- model manifest는 exact `baseline/e1/e2` 세 태그와 서로 다른 64-hex digest만 허용
- 승인 fixture manifest와 세 fixture raw/canonical SHA를 실행 전 retained copy에서 재검증
- 세 모델 모두 공통 `seeded`, `max_tokens=220`, `timeout=180`, `num_ctx=2048`,
  live context/briefing/evidence/acts ON
- 매 run fresh empty memory/knowledge DB와 fresh master/observer capability
- local provider, pinned+verified digest, memory/knowledge ready, knowledge 0문서/0청크,
  screening/moderation/epistemic/affect/show-arc ready를 실행 전후 health로 증명
- GPT-SoVITS cache wrapper 소유권, streaming mode 2, min chunk 16, WAV/nonparallel을
  고정하고 하위 script가 바꾼 process 환경까지 최종 복원
- fixture+seed별 immutable stream plan과 report의 exact turn 집합, unique action/trace,
  모든 row의 live context + durable receipt를 검증
- 36 reports가 모두 생긴 뒤 baseline↔E1과 baseline↔E2 두 12-pair comparator를 모두 실행
- report/packet/health/run-contract/plan/comparison와 run별 SQLite/sidecar 전체를 해시 inventory;
  성공 summary도 `adoption_authorized=false`
- PID는 현재 launcher의 직접 자식이면서 exact command identity인 프로세스만 회수하고,
  partial start도 listener 유무와 관계없이 종료를 기다린다

모델 세 태그가 준비되면 다음 형식의 외부 manifest를 만든다. 이 파일과 실행 산출물은
모델 디렉터리 아래에 두고 Git에 넣지 않는다.

```json
{"schema_version":"airi.broadcast-sim-t3-model-manifest.v2","arms":[
  {"name":"baseline","tag":"<baseline tag>","digest":"<64-hex>"},
  {"name":"e1","tag":"<E1 tag>","digest":"<64-hex>"},
  {"name":"e2","tag":"<E2 tag>","digest":"<64-hex>"}
]}
```

```powershell
.\run-airi-broadcast-t3-matrix.ps1 `
  -OutputDir D:\AIRI-Models\airi-broadcast-v4-20260821\t3-matrix `
  -ModelManifest D:\AIRI-Models\airi-broadcast-v4-20260821\t3-model-manifest.json
```

실행에 사용한 exact tag/digest는 external model manifest에 baseline
`e683802b...5291`, E1 `721812de...79c8`, E2 `4afe7f4e...243`으로 결속됐다. T3에는 RAG
corpus를 섞지 않았고 각 fresh knowledge DB가 빈 상태임을 attest했다. terminal failure root는
삭제하지 않으며 동일 command를 다시 실행하지 않는다.

통과 기준은 기존 calibration 계약과 새 blind fixture를 모두 만족해야 하며,
특히 v3의 memory 12/24→8/24, donation callout 40/40→38/40 회귀를 되돌려야 한다.
blind fixture는 폐쇄된 후 처음 사용하므로 결과를 보고 target을 고치면 오염이다.

## 6. T3 뒤 실제 스택 장시간 캠페인

T3 우승 후보만 `run-airi-live-broadcast-campaign.ps1`로 3 seed × 500 turns를
실행한다. 캠페인은 현재 다음을 fail-closed로 증명한다.

- semantic callback과 실제 미노출 decoy
- trace-bound RAG document/chunk receipt와 retained fixture/DB hash
- durable journal append/duplicate
- answer → canonical spoken text → TTS input SHA
- LLM start/content/end → TTS start/first/end 인과 순서
- 정상·실패 show close 증적
- endpoint/model/voice/streaming mode pin

캠페인 통과 전에는 live adoption도, Claude PC 전달용 완료 주장도 하지 않는다.

## 7. 직전 검증과 2026-08-22 상태 감사

2026-08-23 동결 P0 배치 최종 receipt는 핀된 Python `145 passed, 5 skipped`,
actual-process PowerShell durability literal PASS, 전체 offline checkpoint PASS,
repo diff-check와 17-path security hit 0, 관련 PID 0이다. commit `911d082`과 receipt
docs `a898ff8`은 origin/main push됐고 GPU·서비스·E2 실행은 이 배치에서 0이다. 아래
2026-08-21 수치는 역사적 증거다.

- v4 generator: 8 passed
- LoRA trainer: 16 passed, 1 skipped(CUDA box라 gpu-less refusal skip)
- proxy runtime seam: 369 passed (v4 작성 전 완료; data-only 수정 뒤 코드 변화 없음)
- 인계 직전 묶음 회귀(live runtime, broadcast runner, campaign, v4,
  merge/package, stack/campaign launcher): **131 passed**
- `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'`: whitespace error 0
- E1 artifact 독립 provenance audit: blocker 0
- E2: 세 번 모두 checkpoint 전 중단, adapter/report 0, 마지막 시작 로그 2개 각 0 bytes
- T3 matrix launcher: 계약 unittest 8 passed, 시뮬/비교기 unittest 75 passed
  (1 skipped), PowerShell AST·py_compile·diff-check PASS
- T3 matrix launcher 독립 최종 감사: P0/P1 0, READY. 실제 서비스/GPU 실행은 E2 부재로 0
- `test-current-checkpoint.ps1`: PASS. 이 과정에서 기존 추적 방송 테스트 15개가 CI
  matrix에서 빠진 불일치, 의도적으로 허용한 `AI` 토큰 뒤 B3-d policy hash pin 누락,
  dry-run stream terminal 증적 누락을 발견해 각각 CI 등록·pin 재결속·synthetic terminal
  회귀 수정했다. B3-d 16/16, B4c rehearsal 83/83 PASS

2026-08-22 pause 시점 실파일 감사: HEAD `0c0ffbe` clean, trainer 0, v4 corpus 두
SHA와 E1 adapter/config/report SHA exact. E2, E1/E2 merge/package, v4 T3
manifest/output, live campaign output은 모두 0이었다. 15:09 KST goal resume 감사에서는
같은 HEAD 위 기존 문서 배치 9 modified + 2 untracked, trainer/Python 0, 동일 SHA exact와
동일 후속 산출물 0을 재확인했다.

2026-08-22 continuity milestone receipt: active goal/P0-before-E2 문서·회귀 배치를
`e822f9f120e27e561d2e90353da4ba8315e4e3dd`로 commit했고 origin/main push를
확인했다. focused/full offline/reference 회귀와 diff/security 검증, 독립 재감사는
P0/P1 0이었다. GPU·서비스·E2 실행은 이 milestone에서 0이다.

2026-08-22 P0-A offline implementation receipt: trainer full-state/RNG/order/loss/pins,
same-volume staged flush/verify/write-through generation+index, latest/previous와 corrupt
quarantine, final adapter/report recovery, exact resume handshake, durable run-state/PID,
safe-pause/`SAFE_TO_POWER_OFF`, reboot duplicate refusal를 구현했다. CPU uninterrupted 대
pause/resume는 LoRA/AdamW/LambdaLR/RNG/cursor/loss가 exact이며, generation/index/final
artifact/control archive/N+2 retention, reparse/mapped/corrupt state fault를 포함한 focused
Python `39 passed, 1 skipped`, actual-process PowerShell PASS, 전체 offline checkpoint PASS.
최신 독립 감사 P0/P1 0, controlled GPU READY다. 모델/GPU/서비스/E2 실행은 0이며,
구현 commit `6f0c1358d2acd18b828ebc0ae8482a348712c461`은 origin/main push됐다.
P0-B의 controlled GPU 동등성과 실제 E2 속도 checkpoint ≤10분 실측 전에는 E2 금지다.

2026-08-22 P0-B evidence gate implementation receipt: checkpoint generation마다
manifest/payload/index/pins SHA와 publish wall/monotonic timing을 연속 atomic event로
보존하고, deterministic CUDA/cuDNN/TF32/CUBLAS/quantization identity를 exact pins에
결속했다. verifier는 무중단 대 safe-pause/resume의 adapter·report·recursive full
checkpoint state를 허용오차 0으로 비교하며, 고정 상한 600초와 최소 4개 정상 구간,
closed control-history inventory, latest event 결속을 fail-closed로 강제한다. fresh
Python `68 passed, 1 skipped`, actual-process PowerShell durability PASS,
`test-current-checkpoint.ps1` PASS, 독립 최신 감사 P0/P1 0을 거쳐 implementation
`e970cf7e4c3a4685fd8bce23c659a1c9aa93c21e`이 origin/main에 push됐다. 이 receipt는
GPU 실험을 증거로 만들 수 있는 코드 gate의 완료이지 P0-B 실증 완료가 아니다.
controlled GPU paired run과 실제 E2 속도 ≤600초 실측은 아직 0이며 E2는 계속 금지다.

2026-08-22 P0-B expected-run binding receipt: verifier가 두 run끼리만 우연히 같은
잘못된 설정을 쓰는 false pass를 막도록 계획된 input manifest/full canonical config
SHA, seed, batch, gradient accumulation, 단일 첫 optimizer 경계 pause를 외부 기대값에
결속했다. baseline의 실제 empty regular `control/`은 허용하되 entry/link/reparse를
거부한다. root Python `73 passed, 2 skipped`, actual-process PowerShell durability와
전체 offline checkpoint PASS, 최신 독립 감사 P0/P1 0을 거쳐
`8cd69b5f455bd41b48faa5ed6e9cac1af00f8908`이 origin/main에 push됐다. 이는
controlled GPU 실험의 명령·입력 결속을 강화한 offline gate receipt이며, paired GPU
실험이나 실제 E2 속도 증거는 아직 0이므로 P0-B 완료나 E2 허가로 승격하지 않는다.

2026-08-22 safe-pause auto-discovery receipt: `pause-airi-safely.ps1`은 `-RunDir`를
생략하면 live Windows command line의 runner 영역(`--` 앞)에서 exact run ID/RunDir를
읽고, strict current→previous receipt, runner source SHA와 PID/creation/executable/
command identity, active status가 모두 일치하는 durable run만 후보로 인정한다. 정확히
1개일 때만 선택하고 0개·복수·process spoof는 noninteractive fail-closed다. 명시한
빈/공백 RunDir는 자동 모드로 바꾸지 않고 거부한다. manual `-RunDir`와 checkpoint/ack/
artifact/`SAFE_TO_POWER_OFF` 검증은 유지된다. actual-process 0/1/multiple, source decoy,
identity spoof, corrupt-current/valid-previous 회귀와 전체 offline checkpoint가 PASS했고
최종 독립 리뷰 P0/P1 0이다. 이 편의 개선은 controlled GPU 실증을 대체하지 않는다.

## 8. active goal fail-closed 실행 체크리스트

1. [x] 사용자 `/goal`의 재개 권한과 운영 채택 금지선을 확인했다(2026-08-22).
2. [x] **P0-A checkpoint (offline 구현·fault 실증 완료, 2026-08-22):** 트레이너가 LoRA·optimizer/scheduler·Python/Torch/CUDA RNG·epoch/microstep/
   optimizer step·데이터 순서/seed·loss/dev/best와 dataset/base/config SHA를 주기적으로
   같은 볼륨 임시 경로에 flush·검증하고 원자 승격하도록 구현한다. latest와 직전 정상본을
   유지하고 깨진 checkpoint는 삭제하지 않고 격리한다. 구현·회귀·문서는
   `6f0c1358d2acd18b828ebc0ae8482a348712c461`로 origin/main push됐다.
3. [x] **P0-B runner/recovery (controlled GPU 완료, 2026-08-23):** exact SHA·seed·config 일치 시에만 허용하는 `--resume-from-checkpoint`, 원자적
   `run-state.json` durable runner, optimizer 경계 safe-pause와 `SAFE_TO_POWER_OFF`,
   PID/command/checkpoint SHA 기반 재부팅 복구를 자동 회귀와 통제 GPU 실험으로 증명한다.
   CPU exact resume와 offline actual-process runner/safe-pause/reboot fault는 완료했다.
   checkpoint timing/exact full-state comparator·deterministic pin·600초/4구간 gate와
   offline fault 회귀는 `e970cf7e4c3a4685fd8bce23c659a1c9aa93c21e`, 계획된
   input/config/shape/first-pause 외부 기대값 결속은
   `8cd69b5f455bd41b48faa5ed6e9cac1af00f8908`로 origin/main push됐다.
   `pause-airi-safely.ps1`의 RunDir 생략 모드는 exactly-one verified active run만 자동
   선택하고 0개·복수·spoof·명시적 empty를 거부하도록 actual-process 회귀를 통과했다.
   2026-08-23 후속 동결 배치는 authenticated run-state lineage, no-follow input lock,
   producer evidence/index/event 결속, trainer-bound launcher와 anchor-bound pause를 추가했고
   final Python/PowerShell/offline gate와 한 차례 감사의 고정 P0/P1을 모두 닫아
   `911d082`·`18d0bc6`과 receipt docs를 origin/main에 push했다. 첫 K=5 controlled
   baseline은 480/30 계산 뒤 actual interval max 705.902827초와 final-root SHA 의미 혼동으로
   FAIL해 보존했다. 두 final-evidence P0를 pinned Python `146 passed, 5 skipped`,
   actual-process PowerShell와 final offline PASS로 최소 수리한 뒤 K=3 fresh baseline과
   실제 `SAFE_TO_POWER_OFF` pause/resume arm을 모두 terminal 480/30으로 완주했다. final
   receipt SHA `d913992e...e84b9`는 672 tensors exact, max normal interval
   `551.5176357`초, `pass=true`, adoption false다. Windows receipt-order verifier 최소 수정과
   milestone docs는 `87dfabd`/`29080be`로 origin/main push됐고 actual push receipt five-doc
   finalization만 남았다. GPU 실증 자체는 완료다.
4. [x] **controlled GPU preflight:** 입력 code/data clean, trainer 0, corpus source/chat,
   base model, E1 SHA exact, fresh root와 E2 adapter/report 부재를 확인하고 K3 실험을
   실행했다. E2-LAUNCH 직전에는 현재 verifier/docs commit push와 HEAD=origin/main·clean을
   확인한 뒤 같은 입력·PID·E2 부재 preflight를 fresh timestamped root 기준으로 반복한다.
5. [x] **E2-LAUNCH:** 기존 0-byte 로그를 삭제하지 않고 P0 receipt에서 검증·고정한
   authoritative durable runner 명령으로만 새 timestamped stdout/stderr 경로와
   run-state를 생성해 step 0부터 시작한다. direct trainer/임의 hidden process 실행은
   무효다. PID와 exact command identity, CUDA 메모리 사용을 기록한다.
6. [x] E2 1,600 microsteps를 완주했다. 완료 증거는 adapter model/config/report,
   dataset/base pin, optimizer step, epoch 1/2 dev loss, selected epoch, SHA와 artifact
   manifest다. 로그나 GPU 사용 시간만으로 완료 처리하지 않는다.
7. [x] E1/E2 provenance를 독립 재감사하고 E1 dev `2.8938066467`과 E2 epoch 1/2를
   비교한다. 두 후보 모두 계속 `adoption_authorized=false`다.
8. [x] E1/E2 각각 HF safe-merge → BF16 GGUF → Q4_K_M을 수행했다. 후보별
   manifest/SHA와 `package-evidence.json`의 최종 tag/digest를 보존한다.
9. [x] 서로 다른 exact baseline/E1/E2 tag+64-hex digest로 T3 model manifest를
   만들고 승인 fixture raw/canonical retained SHA를 재검증한다.
10. [~] isolated T3 36 reports와 baseline↔E1/E2 두 comparator는 terminal까지 실행했으나
   두 comparator가 hard-gate FAIL했고 PASS summary가 없어 **승자 없음**이다. report,
   health, contract, stream plan, SQLite/sidecar inventory는 실패 root에 보존한다.
11. [ ] T3 통과 승자 1개가 없어 3 seed × 500 turn live campaign은 **차단**한다. semantic/decoy,
   RAG receipt, durable journal, answer→spoken→TTS SHA, 인과 순서, close·latency·stability
   증거와 retained hashes를 모두 요구한다.
12. [ ] 실제 응답 비교 묶음, 실패 사례, 점수와 증거를 사용자에게 제출한다.
    현재는 T3 terminal 실패 aggregate/inventory를 제출하고, 새 모델링/evaluation iteration은
    공개된 blind를 재사용하지 않는 별도 사용자 방향이 필요하다. 사용자 승인 전에는 서비스
    모델·운영 태그를 바꾸지 않는다.
