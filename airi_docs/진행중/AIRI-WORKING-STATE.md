---
schema_version: 1
updated_at_kst: "2026-08-26 17:54:00 +09:00"
checkpoint_id: "20260826-175500-m7-3-human-rating-receipt"
matrix_note: "M7-3 closed: human rating of 06b-r3 (99 turns, all commented) = 3-axis 1.90 vs baseline 1.76 (+0.14 < +0.2), filler 55.6% (+10.1pp), critical 1 (turn 23 rumor question answered with a leading yes). S1 alone rejected (decision 19), production flag stays off. New M7-10 safety guard candidate for sensitive rumor questions. Next: user decides S6 input alignment (M7-9), M7-10, push. No services running"
active_trainer_note: "GPU 학습 없음. replay run 05 종료, 스택 stop, owned listener 0"
goal_status: "active"
authorization: "user-goal-2026-08-25-1720-m3: approve-all-three-recommendations (blind-v5-seal-then-4-arm-48-report-rematrix-with-marker-and-num_ctx-4096, enforce-lm-eval-general-capability-gate-le-2pp-vs-stock, fix-native-baseline-fixture-pin); no-gpu-training; matrix-exact-once; operational-adoption-forbidden-until-separate-user-approval. superseded: user-goal-2026-08-25-1630-m2: proceed-with-proposed-direction (review-docs-into-참조+INDEX, num_ctx-4096-prompt-budget, R2-F7-campaign-code-gate) and adopt-tools-judged-beneficial (lm-eval, llama.cpp perplexity; unsloth/DPO deferred); no-gpu-training; operational-adoption-still-separate-approval. superseded: user-goal-2026-08-25-0454-d1: no-gpu-training-inference-only; scope: (1) deterministic-runtime-layer-for-4-gates (invented_handle-full-coverage-incl-87%-common-noun, donation-composite, stale_transition_clean, decoy_fact_use; gate-definitions-and-thresholds-immutable, default-off-flags, off-path-byte-identical-regression-required), (2) offline-regression-then-commit-push, (3) new-retained-blind-v4-x3-author-validate-seal (seal-tooling-reuse; v1/v2/v3-reuse-forbidden), (4) 48-report-4-arm-matrix-baseline-e2-e2c1-e2c2-with-deterministic-layer-on (comparator-policy-extended-to-4-arms-no-threshold-relaxation), (5) gates-closed-then-3x500-campaign-with-top-score-arm / not-closed-then-preserve-diagnose-report-await-user; forbidden: gpu-retraining-or-new-candidate-training, blind-v1-v2-v3-reuse, hard-gate-relaxation, operational-model-tag-change, external-provider-extraction-greybox-default-on, t05-126-promotion; operational-adoption-forbidden-until-separate-user-approval; per-step intent/receipt + per-batch LOG + commit/push-after-verification. superseded: user-goal-2026-08-24-1700-e2c2: gpu-unlimited; scope: (1) e2-c2-recipe-redesign-microsteps-lr-correction-replay-ratio-per-frozen-contract-s11-undertraining, (2) new-retained-blind-x3-author-offline-validate-seal (stream-only, hangul-ratio, correction-proper-noun-collision-0; v1/v2 reuse forbidden), (3) bounded-smoke-then-durable-train-then-safe-merge-then-package, (4) 36-report-matrix-baseline-e2-e2c2-with-AIRI_HANDLE_GROUNDING_GUARD-on, (5) winner-then-3x500-campaign / no-winner-then-preserve-diagnose-report-await-user (no auto E2-C3); forbidden: blind-v1-v2-reuse, hard-gate-relaxation, same-data-epoch-only-E3, operational-model-tag-change, external-provider-extraction-greybox-default-on, t05-speaker-126-operational-promotion; operational-adoption-forbidden-regardless-of-campaign-until-separate-user-approval; per-step intent/receipt + per-batch ROADMAP-LOG + commit/push-after-verification required"
m4_authorization: "user-goal-2026-08-25-m4: fix live deterministic-layer wiring, add pre-fix-failing/live-path tests, expand P3 rejected-branch extraction, author/seal fresh blind-v6 with handle-topic collision gate, exact-once 48-report d1v6 matrix, winner-only 3x500 campaign, otherwise diagnose-and-wait; no GPU/new candidate training; no blind-v1-v5 reuse; no gate/threshold/metric/seed/fixture-definition changes; operational adoption forbidden without separate approval"
m4_dashboard_authorization: "user-additional-goal-2026-08-26: keep running M4 matrix untouched; add evidence-backed user roadmap live dashboard, normalize stale whole-roadmap checklist after terminal, create shared-contract Codex+Claude project skill airi-roadmap-dashboard with skill-creator after terminal, update WORKING+ROADMAP together every <=14m; no skill/test/contract files during matrix; push requires fresh separate user approval"
m4_handoff_authorization: "user-2026-08-26: approve final push, synchronize all current milestone documents, create a Claude handoff, then give the Claude goal command; next round is not active until that command is submitted; operational adoption remains separately forbidden"
m5_authorization: "user-goal-2026-08-26-m5 (submitted handoff goal command): step1 classify d1v6 residual gates (P2 invented_handle 5 rows, P3 identity/stale required miss, common polite opinion 43 rows) into non-overlapping causes using scored reports as diagnosis input only; step2 minimal deterministic red/green repair without GPU, preserve P4/P5 closed behavior and flag-OFF outbound bytes exact; step3 affected offline regression separated from known env/behavior-v2 failures; step4 author/seal fresh Korean blind v7 x3 distinct from v1-v6 with existing seal contract and synthetic 48-report comparator check; step5 -PreflightOnly 48/48 -> WORKING intent commit/push -> exact-once detached d1v7 48-report matrix with <=14m heartbeat; step6 winner-only campaign seeds 101,202,303 x 500 x NumCtx 4096 else diagnose-and-wait; step7 dashboard contract, per-batch ROADMAP-LOG, exact Conventional Commits, separate user approval before every push. Forbidden: GPU/new candidate training, blind v1-v6 reuse/rerun/reseal, gate/threshold/metric/seed/fixture definition change, P4/P5 relaxation, operational model/tag change, external provider/extraction/greybox default ON, T-05 126 promotion, adoption assumption, user-change reset/checkout/revert, auto follow-up round after no_winner, import-target edits during matrix, unverified delegated results"
m5_pivot_authorization: "user-goal-2026-08-26-pivot-c: stop step 4 (blind v7 authoring/seal/matrix/campaign) immediately as idling; assess the real state, update every current document, review fine-tuning; superseded M5 steps 4-8 of the POST-M4 handoff; operational adoption, GPU training, commit and push remain separately gated"
m6_authorization: "user-2026-08-26: approve (1) real-dialogue capture + human-rated evaluation as the only adoption gate, (2) production fix of needs_grounding_retry silencing declarative viewer statements in live broadcast, (3) commit of the verified step-2 repairs (done a9583c3; push still needs separate approval), (4) doc diet (WORKING archive, heartbeat 60/15->120/30 min, matrix 14->30 min) and a full roadmap/checklist overhaul (v4). Fine-tuning paused per reality-check section 4.2; GPU training, operational adoption and push remain separately gated; 2026-08-26 14:2x user chose the recommended first candidate: A (donation ritual gating + non-verbatim safe P5 echo) + B (drop thanks/ritual feedback from history) as one batch, C deferred; deterministic code only, no fine-tuning"
active_phase: "m7-await-s6-input-alignment-decision"
git_head: "723372b1ce5aaba811449c2567d14c1d5761baae"
worktree_state: "post-push: HEAD = local main = origin/main = remote main 7a998bb (39c29bf..7a998bb, 3 commits); worktree clean except this heartbeat; single worktree; AIRI PID 0"
active_trainer_count: 0
reconciliation_receipt: "2026-08-24 15:14 KST E2-C1 blind v2 36-report matrix final receipt (Claude PC, Fable supervisor). Matrix completed cleanly (detached launcher exit 0, monitoring loop kills by user did not affect it): 36/36 reports, comparator status=pass, winner=null. Scores baseline=0.217883/e2=0.224945/e2-c1=0.244070; improved_additive_axes_vs_e2=4/5; invented_handle violations 28/40/53 (worsens with training) drove 13 failed hard/legacy/perfect-rate gates. adoption_authorized=false, campaign blocked. User accepted next plan: (1) read e2-c1 invented-handle transcripts from this now-scored blind for root-cause classification, (2) design a deterministic runtime guard rejecting un-rostered Korean handles, (3) if gaps remain, E2-C2 with revisited training dose/LR and a fresh blind. This checkpoint records docs (frozen contract SS11, handoff -6, ROADMAP-STATUS banner/checklist, ROADMAP-LOG) and asks the user for a fresh /goal covering the diagnosis+guard phase. All AIRI/GPU processes idle, no listeners beyond Ollama 11434."
---

# AIRI live working state

> **세션 시작·goal resume·재부팅·컨텍스트 compact 직후 가장 먼저 읽는다.**
> 채팅 요약이나 기억만으로 작업을 재개하지 않는다. 이 문서는 현재 행동을 짧게
> 보존하는 가변 SSoT이고, `AIRI-CODEX-HANDOFF-2026-08-21.md`는 검증된 장기
> 인계 SSoT다.
> frontmatter의 `git_head`와 `worktree_state`는 이 checkpoint를 쓰기 직전에 관측한
> 기준 상태다. checkpoint를 포함한 commit 자체의 SHA를 자가 참조하지 않는다.

## 1. 권한과 현재 사실

- 2026-08-26 17:54 KST **M7-3 사람 채점 receipt**: 사용자 채점 `Downloads/airi-human-rating (1).json`(17:51, 99턴, 세션 06b-r3) → `20260826-replay-06b-r3/ratings-human.json`, `summary-human.{json,md}`(`--baseline` run 04): 3축 1.90(+0.14), 방송다움 2.46(+0.60)·맥락 1.49(−0.08)·반응 1.75(−0.08)·말투 4.29·사실성 3.25, filler 55.6%(+10.1%p), 치명 1.0%(23턴 루머 질문 "응" 시인). 판정: 채택(+0.2)·돌파(3.0) 미달, S1 단독 기각, 운영 flag off 유지. 참고 채점 대비 방송다움 절대차 0.84·filler 불일치 23%(`summary-human-vs-claude`). ROADMAP M7-3 `[x]`, M7-10 안전 가드 `[D]` 추가, 결정 큐 19 기각·21 추가. 실행 중 프로세스 0.

- 2026-08-26 17:32 KST **S1 정정 receipt**: 문형 무관 지표(최빈 응답 빈도/고유 응답) 추가 — off 5/93·4/89·78/18·72/24, on 3/94·19/44·3/94, journal 5/90·5/93·5/95, on+에코차단 4/87·28/36·33/43. 06b-r3 최빈 "응, 지금 채팅 보고 있어" 39턴 = fixture 오프닝 비트 큐 되풀이. Claude 참고 채점(사람 아님) 06b-r3 3축 1.59(기준선 1.76, −0.17, filler 77%), run 05 1.72(−0.04) — `summary-claude-preliminary.{json,md}` `--baseline`. 결론 정정: 되먹임은 증폭기, 원인은 맥락 빈곤 입력(원 방송 화면 전제 채팅) + 모델 기본 응답. 운영 flag on 요청 없음. 다음 변수 후보 S6 입력 정합(M7-9, 사용자 결정). receipt §2-1·2-2·3·4, ROADMAP M7-2 정정·M7-9 추가·결정 큐 19~20.

- 2026-08-26 17:25 KST **M7 S0·S1 receipt**: `06b-r1..r3`(on + 브리핑 자기 에코 차단, scratch fixture) exit 0(17:15~17:21): "음" 4/2/22, "?" 종결 7/17/16, 완전 에코 0, 붕괴 0/3 — off 3/4·on 1/3·journal 2/3. 운영 디렉터(B4)에는 자기 에코 없음(grep). 채점 시트 `20260826-replay-06b-r3/rating-sheet.html`(사전 등록 중앙값), `06a-r1`, run 05. checkpoint 계약 PASS, diff --check clean. 문서: `진행중/AIRI-M7-S0-S1-RECEIPT-2026-08-26.md`, ROADMAP M7-1·M7-2 `[x]`, M7-3 `[D]`, 결정 큐 18~19. 시각 정정: 17:03 항목은 기계 시각 17:00이었다. 실행 중 프로세스 0.

- 2026-08-26 17:16 KST **run 06 series receipt + 06b intent**: `06a-r1..r3`(hygiene on)·`06j-r1..r3`(journal) 6회 exit 0(17:00~17:12, health `feedback_hygiene` on/journal 확인). 시그니처(99턴): "?"종결 off 78/71/15/84 → on 33/14/55, journal 3/68/89; "음" 오프너 off 48/56/1/89 → on 5/18/67, journal 1/96/2; 고유 오프너 off 63/43/17/22 → on 85/41/82. 붕괴 run(음≥40 또는 ?≥60) off 3/4, on 1/3, journal 2/3 — on은 줄이지만 없애지 못함, journal 단독 무효. 집계 `D:/AIRI-Models/airi-human-eval/20260826-m7-signatures/signatures.{json,md}`. 사람 채점 시트(사전 등록: on 3회 중 "?"종결 중앙값 = on-r1) `20260826-replay-06a-r1/rating-sheet.html` 생성. 잔여 채널 확인: 브리핑 "방금 흐름 → 나: <직전 응답>"(`broadcast_sim.py:520-525`, fixture `min_echo_response_chars` 8)이 세 번째 자기 되먹임. 06b intent: 같은 구성 + hygiene on + scratch fixture 사본(`min_echo_response_chars`=10^9, sha f850dc38…; 원본 8ae3b94e…)으로 3회(`06b-r1..r3`), 드라이버 `run_s1b.ps1` 백그라운드. 코드 변경 없음.
- 2026-08-26 17:00 KST **S0 receipt + S1 구현 receipt + run 06 series intent**: S0 복제 `20260826-replay-05r1..r3` 3회 exit 0(각 ≈2분, 16:53~16:59), 픽업 결정론 확인(99 message_id 4 run 동일). 생성은 seed 20260818에도 재현되지 않음(run 05 대비 동일 응답 10/2/0). 시그니처 노이즈: "음" 오프너 48/56/1/89(SD 31), "?" 종결 78/71/15/84(SD 28), topic_anchored 45/28/10/4 — n=1 비교 무효, 붕괴는 run 단위 쌍봉. 집계 `D:\AIRI-Models\airi-human-eval\20260826-s0-replicates\signatures.{json,md}`(scratchpad `s0_signatures.py`). S1 구현 commit `098c887`(worktree에서 red/green: 새 test_foreground_context 10건, proxy unittest 394 OK, CI 샤드 등록, health `feedback_hygiene`), main ff 병합. run 06 intent: 같은 구성 + `AIRI_FEEDBACK_HYGIENE=on` 3회(`06a-r1..r3`) → `journal` 3회(`06j-r1..r3`), 드라이버 `run_s1.ps1` 백그라운드; 판정은 복제 분산·붕괴 빈도(자동, 표시용)와 사전 등록 규칙(on 3회 중 q_end 중앙값 run)으로 고른 1회의 사람 채점.
- 2026-08-26 16:52 KST **사용자 승인 4건 + S0 intent**: 사용자 "1 2 3 4 모두 진행" — S0 복제 측정·S1 proxy 되먹임 flag·run 05 사람 채점·push 승인. push 완료 `7a998bb..e6e745a`(5 commit). S0 intent: run 05와 같은 구성(`run_replay.ps1`, pseudo-korean 1,500건, max-turns 100, history 8, seed 20260818, stock 모델 digest pinned)으로 `20260826-replay-05r1..r3` 3회 순차 재생(드라이버 scratchpad `run_s0.ps1`, 백그라운드). S1은 worktree `s1-feedback-hygiene`에서 구현·테스트 후 main 병합(실행 중 proxy는 디스크 편집 영향 없음, reload 없음). 사람 채점 없음(측정 전용).
- 2026-08-26 16:55 KST **타계책 문서 반영 receipt (사용자 지시 "로드맵 등 문서에 반영부터")**: ROADMAP을 M7(타계책 실행)로 열었다 — 대시보드·M7-1~8 체크리스트(S0/S1/run 05 채점 `[D]`, S2~S5 `[ ]`, 파인튜닝 재진입 `[B]` 2026-09-09까지), M6는 이력 블록(M6-9·11은 M7로 이관 `[S]`), 용어집(되먹임 고리·3축 합성·복제), §0-1 원칙 5~7(되먹임 통제·1변수·복제·금지 목록), §1 사람 채점 주 지표 표(기준선→돌파 목표), P3-M1/M2를 S5와 연결, P2-6c·P3-T2d 재개 조건 강화, 결정 큐 17~18. 평가 계약 §4 돌파 정의·§5 복제 규칙·§6 시그니처 표시 전용, 실태 문서 §4.2 재개 조건 0항 추가. 계약 4종 PASS. 다음: 사용자 S0·S1 승인 + run 05 채점 + push 승인.

- 2026-08-26 16:35 KST **타계책 확정 receipt**: 워크플로(렌즈 4·반박 8, 에이전트 12, read-only, 서비스 0)의 제안은 문자 그대로는 전부 기각됐고 반박 조건만 채택했다. 감독 재대조: run 04→05 "음" 오프너 1→48, "?" 종결 20→78, 브리핑 재료 사용 35→0(같은 모델·입력·샘플링); `foreground_context.py:80-82` `_short_direct_answer`(≤5어절 + 직전 응답 "?" → 유지), `airi_memory.py:2208` journal 회수 assistant 포함; 픽업 결정론(같은 99 message_id) 확인; qwen3:8b 5.23GB는 TTS와 공존 불가(LLM 예산 ≈4~5GB), Kanana GGUF는 비선두 system 템플릿 거부. 산출: `진행중/AIRI-BREAKTHROUGH-PLAN-2026-08-26.md` — 돌파 정의(3축 합성 ≥3.0·critical 0·filler ≤25%·복제 ≥2), 순서 S0 복제 측정 → S1 proxy 되먹임 고리 차단(운영 flag, 승인) → S2 오프너 중복 재샘플 → S3 예시 4쌍 → S4 픽업 스킵·배치 → S5 모델 축 1회 진단(채택 아님), 파인튜닝 2주 금지·재진입 조건(실제 채팅+사람 검증 ≥300턴). ROADMAP M6-10 `[x]`, M6-11 `[D]`. 다음: 사용자 S0·S1 승인 + run 05 사람 채점.

- 2026-08-26 15:50 KST **타계책 탐색 intent (사용자 goal)**: 사용자가 "코드 제어와 파인튜닝 사이에서 갈팡질팡하며 단계를 돌파하지 못한다 — 타계책을 찾아라"를 goal로 제출하고 ultracode를 켰다. 실행: read-only 조사 워크플로(렌즈 4개 — 모델 축·추론 시점 설계·재료 공급·의사결정 규율 — 각 상위 제안 2개를 회의적 검증) + 감독의 독립 사실 수집(Ollama 모델 목록, sampling 기본값, 코퍼스 단문 비율, GPU 메모리). 서비스·commit·모델 변경 없음. 산출은 증거 기반 타계책 문서와 다음 실험 계획이며, 실행은 사용자 결정 뒤.

- 2026-08-26 15:35 KST **run 05 receipt + 참고 채점**: root `20260826-replay-05`, exit 0, health run 04와 동일, 99턴 응답 + 차단 1, service_error 0, fallback 2, polite 0, invented 0, 후원 픽업 0(치즈 102건 소액 처리), 의례·축자 인용·"고마워." 단답 전부 0. 그러나 T47 이후 "음... 뭐가 X인데?" 되묻기 37턴 + 완전 에코 19 + 뜻 되묻기 17 — health grounding 카운터 변화 0, raw는 ACT 마커+본문이라 모델 고유 출력의 자기 되먹임 붕괴. Claude 참고 채점 방송다움 1.70·맥락 1.65·반응 1.81·말투 4.22·사실성 3.94, critical 0%, filler 80.8%(run 04 참고 채점 대비 치명·말투·사실성 개선, 방송다움·filler 악화). 채점 시트 `rating-sheet.html` 생성. 문서 `진행중/AIRI-REAL-CHAT-REPLAY-RUN05-2026-08-26.md`, D1 contract §11. 다음: 사용자 run 05 채점(계약 §4 판정) + M6-10(D/E/F) 결정. push 미승인(로컬 `beb0559` 코드 + 문서 배치).

- 2026-08-26 15:05 KST **A+B 구현 receipt + run 05 intent**: commit `beb0559` — P5는 후원 본문을 절대 인용하지 않고 초안에 감사가 없을 때만 "후원 고마워!"를 붙이며, 성적·혐오·욕설 화면(`_UNSAFE_DONATION_RE`, 실제 후원 524건 중 23건 4.4% 적중·표본 전부 해당)에 걸린 본문을 따라 말한 초안 문장은 제거; 재생 모드 후원 티어(5,000 미만은 일반 채팅으로), 의례·감사 턴은 history에 되먹이지 않고 briefing echo는 모델 continuation만; importer `--nickname-style korean`. 검증: 계층·guard 61+·pytest 364 passed(broadcast_sim+human_review+계층), proxy unittest 414 OK(옛 인용 단정 2건을 중립 감사로 갱신), CRLF 0, diff-check clean. run 05 intent: run 04와 같은 스택 인자·같은 원본 1,500건(한국어식 가명 `pseudo-korean/chzzk-12901656.jsonl`), `--max-turns 100`, root `20260826-replay-05`. 기대 exit 0, screened_inputs 기록, 그 뒤 review→채점 시트→사용자 채점으로 기준선 대비 판정(계약 §4).

- 2026-08-26 14:30 KST **M6-8 결정 + A+B 구현 intent**: 사용자가 추천안(A+B 한 배치, C 보류)을 승인했다. A: 후원 의례를 금액 기준으로 축소(소액 치즈는 짧은 감사, 큰 후원만 의례 closer), P5 echo를 축자 인용 대신 내용 토큰 1개 언급형으로 바꾸고 성적·혐오 문구가 있으면 echo 생략(안전 회피); B: 후원 의례·echo가 붙은 응답을 history에 되먹이지 않아 "고마워." 붕괴 차단. 부수: 재생 가명을 한국어식 가짜 닉네임으로 표시(채점 시 "v…" 문자열 혼동 제거). 전부 결정론 코드(계층·harness·importer), 파인튜닝 아님. 검증: red/green + 기존 회귀, 그 뒤 같은 1,500건 입력으로 run 05 재생 → 채점 시트. subagent 2개 위임, 결과는 재검증 후 채택.

- 2026-08-26 14:15 KST **사람 채점 기준선 receipt**: 사용자가 run 04의 `rating-sheet.html`로 99/99턴을 채점해 내보낸 `airi-human-rating.json`(rater `사람`, 코멘트 99건)을 run root `20260826-replay-04/ratings-human.json`으로 복사(저장소 밖). `summarize_ratings.py` 결과: 방송다움 1.87·맥락 1.58·반응 1.83·말투 3.60·사실성 2.75, critical 7.1%(7턴), silence_or_filler 45.5%, 5축≥4 0%, 어떤 축이든 1점 56/99. Claude 참고 채점과의 축별 평균 절대차 0.48/0.37/0.51/1.10/1.24, 플래그 불일치 critical 4.0%·filler 43.4%. 코멘트 우선순위(본문 미인용): 후원 의례 오발동+축자 인용, "고마워." 폴백 연속, 성적·인종 채팅 재낭독/동조(회피 설계 부재), 에코 반문, 챗봇 말투 누출, 사실 지어냄. 계약 §4에 확정 기준선 기록, ROADMAP M6-7 `[x]`, M6-8 `[D]`(후보 A/B/C). 실행 중 프로세스 0, push 미승인(문서 배치만 dirty).

- 2026-08-26 12:45 KST **push receipt 2 (사용자 승인)**: `git push origin main` exit 0, `39c29bf..7a998bb`(3 commits). post-push HEAD/local/origin/`ls-remote` 모두 `7a998bb5521c94ed5c646e0b36b2970131661243`, clean(이 heartbeat만 dirty), AIRI PID 0. 남은 것: 사용자 최종 채점(M6-7)과 첫 개선 후보 결정(M6-8).

- 2026-08-26 12:35 KST **replay run 04 receipt + Claude 1차 참고 채점**: run 04(root `D:/AIRI-Models/airi-human-eval/20260826-replay-04`) — 스택 health 정상(계층·guard·계약 true, num_ctx 4096, memory on, stock digest pinned), 99턴 응답 + 스크리닝 차단 1턴, service_error 0, fallback 1, polite 0, invented 0, topic_anchored 51.5%, donation 35·question 56·reaction 8. 러너는 packet 렌더러 KeyError(`screened` 항목)로 exit 1이었으나 report.json 완성; 렌더러 수정 뒤 packet 재생성, `f408eb7`(screened 처리+렌더러+테스트, broadcast_sim+human_review 269 passed). review.jsonl 99행 → rating-sheet.html 생성. Claude 1차 참고 채점(계약상 사람 채점 아님): 방송다움 1.89·맥락 1.85·반응 1.99·말투 4.03·사실성 3.99, silence_or_filler 44.4%, critical 3.0%(후원 본문 성희롱 문장 축자 인용), 5축≥4 2.0%. 핵심 패턴은 `진행중/AIRI-REAL-CHAT-REPLAY-RUN04-2026-08-26.md` §3: "고마워." 붕괴 23턴(모델 출력, 후원 감사 history 되먹임), P5 echo 축자 인용, 따라 말하기, 원 방송 맥락 의존. 스택 stop, owned listener 0. 다음: 사용자 최종 채점(M6-7)과 첫 개선 후보 결정(M6-8). push 미승인.

- 2026-08-26 12:25 KST **replay run 02·03 receipt(실패) + 러너 수정 + run 04 intent**: run 02(stt venv)는 스택·health 정상이었으나 PowerShell이 traceback 첫 줄만 남겨 원인 불명 → 런처를 Start-Process stdout/stderr 파일 리다이렉트로 바꿔 run 03 실행. run 03 stderr: 15번째 턴에서 `live broadcast fixture input was rejected before capability claim (category=profanity)` — 실제 채팅이 프록시 입력 스크리닝에 차단됐고 러너는 합성 fixture 전제로 이를 치명적 오류로 처리. 두 run 모두 finally에서 stop, listener 0. 수정(로컬, 미커밋): `run_broadcast_sim.py`에 `LiveInputScreened` 예외, `run_arm(tolerate_screened=)`(재생 모드에서만 True), 차단 턴을 transcript `stage=screened`(category 포함)로 기록하고 다음 픽업으로 진행, `summary.screened_inputs`; 합성 matrix 경로는 여전히 fatal. 새 테스트 `test_screened_input_is_recorded_and_skipped_only_in_replay`; broadcast_sim+human_review 269 passed. run 04: 같은 인자, root `20260826-replay-04`. 기대 exit 0, report 100턴 이하 + screened 항목.

- 2026-08-26 12:52 KST **replay run 01 receipt(실패) + run 02 intent**: run 01(root `20260826-replay-01`)은 스택 기동·health 정상(deterministic_utterance_layer true, handle_grounding_guard true, broadcast_contract true, num_ctx 4096, memory enabled, stock 모델 digest pinned·verified)이었으나 러너를 pinned venv Python으로 실행해 `httpx 가 필요하다`로 exit 1, report 없음; finally에서 stop-airi-local-stack 실행, owned listener 0 확인. 원인은 인터프리터 선택(M4 handoff: 시뮬레이터는 `stt/.venv` Python 3.11, httpx 0.28.1). run 02: 같은 스택 인자, 러너만 `stt/.venv` Python, root `20260826-replay-02`(no-overwrite), health JSON은 BOM 없이 기록. 기대 exit 0·report 100턴 이하.

- 2026-08-26 12:40 KST **replay run 01 intent**: commit `6dd8b22`(import_public_chat·--replay-chat·report_to_review_jsonl·CI 3행)까지 로컬 HEAD. 실행: scratchpad `run_replay.ps1` — `start-airi-local-stack.ps1 -Stt off -OllamaNumGpu 999 -NumCtx 4096 -EnableMemory -EnableKnowledge -MemoryDbPath D:/AIRI-Models/airi-human-eval/20260826-replay-01/runtime/memory.sqlite3 -EnableMemoryExtraction $false -ChatProvider local -ChatModel midm-airi:2.0-mini(digest 92a9ba2e…485f, stock) -OutputModeration on -InputScreening on -EpistemicConfidence on -AffectContinuity on -LiveBroadcast -LiveBroadcastEvalClock`(토큰 env, 값 미기록) + env AIRI_DETERMINISTIC_UTTERANCE_LAYER=on, AIRI_HANDLE_GROUNDING_GUARD=on, AIRI_IMMEDIATE_ACK=marker → `run_broadcast_sim.py --replay-chat D:/AIRI-Models/airi-real-chat/pseudo/chzzk-12901656.jsonl --replay-max-messages 1500 --max-turns 100 --memory-arm on --briefing on --briefing-evidence on --acts on --live-broadcast-context on --history-turns 8 --max-tokens 220` → report/packet/health-before/after/runner.exit-code.txt를 같은 run root에. 종료 후 stop-airi-local-stack. 기대: exit 0, report transcript 100턴 이하, owned listener 0. 실패 시 report 보존·원인 기록, 재시도는 새 run root. 입력은 가명화 공개 채팅(원본·표시명 미사용), 목적은 사람 채점 입력 생성이며 학습·adoption 아님.

- 2026-08-26 12:20 KST **M6-6 공개 채팅 수집·재생 intent (사용자 지시)**: 사용자가 실제 세션 캡처를 직접 하는 대신 공개 방송 채팅 로그를 검색·수집해 진행하라고 지시했다(유튜브 저스트 채팅 캡처 허용). 조사 결과 유튜브 "다시보기" 재업로드에는 채팅 리플레이가 없고 원본 라이브(`was_live`)만 `live_chat` 자막 트랙을 가지며 소규모(168·16건)다. 치지직 VOD 채팅 API(`api.chzzk.naver.com/service/v1/videos/{no}/chats`, 공개 JSON, 200건/페이지, cursor)가 한국 저챗 데이터로 훨씬 풍부하다(니니아·둥그레·탐랑 저챗 VOD, readCount 228~2,111). 실행: 원본 채팅 JSON은 `D:\AIRI-Models\airi-real-chat\raw\`(저장소 밖)에만 저장, 표시명·userIdHash·채널 ID는 저장소·문서에 넣지 않고 HMAC 가명으로만 재생한다. 진행 중: (a) 치지직 VOD 4편 채팅 수집(백그라운드, 40페이지 상한), (b) subagent `import_public_chat.py`(chzzk/youtube → 가명화 JSONL, 테스트), (c) subagent 시뮬레이터 `--replay-chat` 재생 모드 + `real_chat_fixture.json` + report→review JSONL 변환기. 그 뒤 intent checkpoint를 쓰고 로컬 스택(memory·결정론 계층·handle guard·live broadcast ON, stock 모델)을 띄워 50~100턴을 재생하고 export→채점 시트를 만든다. 목적은 평가 입력 확보이며 학습 데이터로 쓰지 않는다. matrix·campaign·GPU·adoption 0.

- 2026-08-26 11:58 KST **push receipt (사용자 승인)**: `git push origin main` exit 0, `d7c6283..39c29bf`(4 commits). post-push HEAD/local main/origin main/`ls-remote` main 모두 `39c29bfd1ea1754a7631ae4eeb3bf30f5eaa19ca`, worktree clean(이 heartbeat만 dirty), worktree 1, AIRI PID 0. 남은 것은 사용자 실제 세션 캡처(M6-6)뿐이다.

- 2026-08-26 11:53 KST **M6 code batches receipt**: subagent 결과를 재검증해 채택했다. (1) grounding 게이트 live-broadcast 완화 `cdbb6eb` — `grounding_balanced_candidate_is_acceptable(live_broadcast=)`가 방송 요청(`body_has_live_broadcast_context`, 스타일 계약 주입과 같은 조건)에서 1~4문장·공유 앵커 1개를 받고 인용 어미(`열자고`→`열자`)를 허용하며 날조 가드는 전부 유지; `LocalStreamRequestContext.live_broadcast_turn`; 일반 채팅 경로 불변. red: HEAD worktree에서 새 클래스 9 tests failures 1·errors 6; green: proxy/runtime unittest 414 OK(405+9). 알려진 결합: 4문장 출력 경계는 `AIRI_BROADCAST_CONTRACT`(런처 기본 on)에 의존. (2) `ollama-proxy/eval/human_review/` export·채점 HTML·요약 CLI + README, pinned pytest 16 passed, 합성 2턴으로 채점 HTML headless 렌더링 확인, CI `ollama-proxy-evaluations` shard 등록 → `776b462`. 기본 memory DB 경로 `ollama-proxy/runtime/airi-memory.sqlite3`를 평가 계약에 반영. ROADMAP M6-2·M6-3 `[x]`, 5/8. 남은 것: 사용자 실제 세션 캡처(M6-6) → 채점(M6-7) → 첫 개선 후보 결정(M6-8). 문서 배치 commit 뒤 push는 사용자 승인 대기. matrix·campaign·GPU·adoption 0.

- 2026-08-26 11:45 KST **M6 activation receipt (사용자 4건 승인) + 진행 중 intent**: 사용자가 실태 문서 §5의 결정 큐 4건을 모두 승인하고 로드맵·체크리스트 전면 개편을 요청했다. 완료: (1) 검증된 step 2 수리 코드 9경로를 `a9583c3`로 commit(로컬, origin/main `d7c6283`보다 1 ahead, push 미승인), (2) 문서 다이어트 — WORKING §1 139항목·과거 트랜잭션 표·체크포인트 462개를 `아카이브/AIRI-WORKING-STATE-HISTORY-2026-08-22-TO-2026-08-25.md`로 이동(6,785→235행), heartbeat 상한 AGENTS/CLAUDE 60/15→120/30분·대시보드 계약 matrix 14→30분과 두 계약 테스트 동기화, (3) 로드맵 v4 재개편 — 사람 채점 유일 게이트, M6 체크리스트 8행, M5 이력화, 파인튜닝 트랙 P2-6c·P3-T2d `[B]`(재개 조건 명시), 인간 검수 100건 `[S]`, P3-M1~M4는 기준선 뒤 검토, 결정 큐 11~16 추가, (4) 평가 계약 `AIRI-REAL-DIALOGUE-HUMAN-EVAL-CONTRACT-2026-08-26.md` 작성. 진행 중(subagent, 결과는 재검증 후 채택): grounding 게이트 live-broadcast 완화(한 문장 제한·겹침 요건 완화, 날조 가드 유지, red/green)와 `ollama-proxy/eval/human_review/` export·채점 HTML·요약 도구+테스트. 사용자 몫: 실제 세션 50~100턴 캡처(M6-6). matrix·campaign·GPU·adoption·push 0.

> 2026-08-26 11:45 KST 문서 다이어트: 2026-08-25 이전 §1 항목 139개, 과거 트랜잭션 표, 체크포인트 462개를 `아카이브/AIRI-WORKING-STATE-HISTORY-2026-08-22-TO-2026-08-25.md`로 옮겼다(이력 전용, 현재 상태 검증 금지).

- 2026-08-26 11:29 KST **M5 pivot (사용자 결정 C) receipt + 문서 전면 갱신 intent**: 사용자가 HTML 뷰어로 5라운드 대화를 확인한 뒤 "방송 같지 않다, 공회전"이라 판단했고 제안 (C)를 선택했다: step 4를 즉시 중단, 실태 파악, 모든 문서 갱신, 파인튜닝 재검토. 실행: step 4 subagent 2개(seal `d1v7` generation / v7 저작) TaskStop, 검증 전이던 `seal_e2c2_blind.py`·`test_seal_e2c2_blind.py` 편집은 `git checkout`으로 되돌림(+104/+191 폐기), v7 staging 디렉터리는 생성된 적 없음, pre-fix worktree 제거(worktree 1). 실태 파악 근거를 read-only로 수집해 `AIRI-REALITY-CHECK-AND-FINETUNE-REVIEW-2026-08-26.md`를 작성했다: 08-19 이후 commit 156, WORKING §1 항목 152, GPU 후보 4(채택 0), blind 6라운드 216 report 전부 no_winner, 운영 모델은 stock Mi:dm 2.0 Mini Q4_K_M, 실제 시청자 데이터 0, 사람 검수 0, 학습 데이터 100% 합성, greybox 일반 능력 단조 하락. 파인튜닝은 중단 권고(재개 조건 4개 명시), 기존 어댑터는 보관·채택 금지. step 2 수리 코드는 검증 완료 상태로 로컬에 유지한다(commit은 별도 승인). 이 배치의 write는 문서 동기화(WORKING/ROADMAP/LOG/NEXT/두 handoff/INDEX/D1 §10)뿐이며 matrix·서비스·GPU·adoption·commit·push는 0이다.

- 2026-08-26 11:20 KST **M5 step-2/step-3 receipt + step-4 intent**: step 2 수리를 red/green으로 닫았다. 변경 파일은 `ollama-proxy/deterministic_utterance_layer.py`(+190/-?, `_REJECTED_BRANCH_RE` 주어 `{2,12}`·목적격, `find_rejected_branches` `자고` 처리, `_INTERROGATIVE_RE` `어느`, `echo_grounded_fact` P3 2단계, `suppress_rejected_branch(content_free)`, `apply_…(content_free)`, recall 결과 뒤 P2/P4 차단), `ollama-proxy/ollama_proxy.py`(침묵 폴백 emission 한 곳에서 `grounding_silence_fallback_used`일 때만 `content_free=True`), `ollama-proxy/test_deterministic_utterance_layer.py`(+127), `ollama-proxy/test_ollama_proxy.py`(+32), `ollama-proxy/eval/broadcast_sim/run_broadcast_sim.py`(+7, briefing_text 안 roster handle을 grader pool에 합산), 같은 디렉터리 `test_broadcast_sim.py`(+46)다. red: pre-fix `d7c6283` detached worktree(scratchpad, 새 테스트만 복사) 계층 18 failed/36 passed, proxy 새 테스트 `TypeError(content_free)`, harness `['별빛수집가'] != []`. green(수정 tree): pinned `venv-midm-broadcast-qlora-py312` pytest 계층/guard/runtime 90 passed+12 subtests, broadcast_sim+launcher 계약 251 passed/1 skipped, affect/training 494 passed/8 skipped(알려진 `test_synthesize_broadcast_behavior_v2.py` 2건만 실패, continuity_v4는 WindowsApps 3.14 unittest 8 OK), WindowsApps 3.14 unittest proxy/runtime 405 OK(+2), CI 동등 scratch venv(3.12.13, pytest+httpx) core suite `ollama-proxy`(eval/training 제외)+latency+stt 1140 passed/1471 subtests, patch-manifest·current-checkpoint·work-continuity·dashboard 계약 PASS, `git diff --check` clean. 정정 2건: 구현 subagent가 `ollama_proxy.py`·`test_ollama_proxy.py`·`run_broadcast_sim.py`·`test_broadcast_sim.py`를 통째로 CRLF로 바꿔 놓은 것을 HEAD와 같은 LF로 복원했고, 저장소 추적 `.claude/agent-memory/implementer/`에 남긴 "pytest 미설치" memory를 pinned venv 경로로 정정했다. 문서 동기화: D1 contract §10, ROADMAP-LOG, `AIRI-CODEX-HANDOFF-2026-08-21.md` 기계 판독 계약 `goal_status=active`, NEXT-SESSION 최상단 M5 note. 사용자 별도 요청으로 5라운드 blind HTML 뷰어를 `D:\AIRI-Models\airi-blind-review-html\d1v6-review.html`(9,727,553 bytes, 저장소 외, 생성 스크립트는 scratchpad)로 만들었다. step 4 intent: `seal_e2c2_blind.py`에 `d1v7` generation(v6 superseded hash/root 추가, opener·memory_guard_fallback register lint, handle-동사 어절 충돌 lint) + 테스트 → 외부 staging `D:\AIRI-Models\airi-d1-blind-staging-v7`에 v1~v6와 다른 한국어 fixture 3종 저작(반말 opener, seed_checks는 공개 fixture 관례) → `--check --generation d1v7` → no-overwrite seal `airi-d1-blind-freeze-20260826-v7` → commitment JSON·test·launcher `d1v7` profile·verifier root 매핑·CI matrix → synthetic 48-report comparator 오프라인 확인. gate/threshold/metric/seed/fixture 정의 불변, blind v1~v6 재사용 0, matrix/서비스/GPU/adoption/commit/push 0.

- 2026-08-26 10:45 KST **M5 step-1 diagnosis receipt + step-2 intent**: 두 read-only 진단 subagent 결과를 report 집계·proxy 코드로 재대조해 채택했다. (1) 공통 polite 43행/arm: sealed v6 `aggregation_openers` 9개가 전부 존댓말(v4·v5·공개 fixture는 반말) → v6 fixture 저작 artefact, harness `run_broadcast_sim.py:529-592`가 모델 호출 뒤 붙이며 production code에는 없음. baseline 추가 2행은 모델 자체("살핍니다"). (2) invented_handle 5행: baseline 2행은 roster `모아`가 동사 "모아볼게/모아둘게"의 substring(`broadcast_sim.py:622` `handle in text`, v6 handle-topic collision 검사 범위 밖); e2-c2 3행(`하엘`·`이안`·`오린`)은 직전 8턴 안 발언자이며 briefing `방금 흐름:`/`직전 후원:` author 라벨로 프롬프트에 있었으나 grader pool(`run_broadcast_sim.py:597-611`, viewer line 본문 + memory_pool)과 proxy `memory_pool` 신호(history 사본은 Task 13으로 이름 제거) 어느 쪽에도 없던 pool 불일치. (3) transition required miss 89 = proxy grounding 침묵 폴백 72 + 모델 자유 발화 15 + `어느` 미인식 2; continuity_seed 139/320·memory_seed 66/160이 침묵 폴백이고 뿌리는 `needs_grounding_retry`(`ollama_proxy.py:4665`)가 초안을 사용자 문장 어휘 겹침으로만 판정해 briefing 근거를 보지 않는 production 동작. (4) probe miss 32 = 근거가 pool에 있는데 P3가 한 번도 안 뜬 29(그중 15는 proxy 회피 문구 `확인된 정보 없이…`, 15는 모델 추측) + 침묵 폴백 2 + 근거 부재 1; `_RECALL_QUESTION_RES`가 "X은 어디에 놓았나요?" 문형을, `_POSSESSIVE_FACT_RE`가 "X은 Y에 놓았습니다" 근거를 못 잡음. (5) 계층 자체 결함: P2가 `_RECALL_FALLBACK`의 "한 번만"을 "한 그거"로 훼손 37행, P4 ack가 1글자 주어 `검`을 잡아 "좋아, 검은 남색 잉크로 갈게!" 16행, 닫힌 결정 동사 목록으로 "열자고로" 비문 56행. step 2 intent: flag ON 경로에서만 (a) `_REJECTED_BRANCH_RE` 주어 2~12자·목적격 허용, (b) recall fallback/answer 뒤 P2·P4 재가공 차단, (c) 결정 동사 일반화, (d) `_INTERROGATIVE_RE`에 `어느`, (e) 살아 있는 제안 ack가 proxy 침묵 폴백 상수를 대체, (f) 의문사 질문의 주제 토큰과 겹치는 pool 근거 문장을 반말로 되읽는 P3 evidence-echo(초안이 그 근거 토큰을 이미 쓰면 유지), (g) harness grader pool에 이번 턴 briefing_text 안 roster handle 합산. grounding 게이트 자체·gate/threshold/metric/seed/fixture 정의·P4/P5 억제 강도·flag OFF bytes는 불변. v7 저작 시 반말 opener + seal-time register lint, handle-동사 어절 충돌 lint, seed_checks는 공개 fixture 관례(결정 내용 토큰)를 따른다는 결정을 사용자에게 명시 보고한다.

- 2026-08-26 10:40 KST **M5 activation + startup reconciliation receipt + step-1 diagnosis intent**: 사용자가 `AIRI-CLAUDE-HANDOFF-2026-08-26-POST-M4.md` §4의 M5 Goal 명령을 Claude 세션에 실제로 제출해 M5가 활성화됐다. 시작 프로토콜(AGENTS → WORKING 전체 → handoff → D1 contract §8·§9 → ROADMAP → NEXT)을 읽고 read-only 대조한 결과 HEAD/local main/origin main/`git ls-remote` main 모두 `d7c6283bb5f5d4bd9db614407f0db6297309c6db`, worktree/stage/untracked 0, worktree 1개, handoff 파일 origin/main 도달 가능이다. d1v6 external root는 wrapper exit-code receipt 0, reports/packets/health/run-contract 각 48, `summary.json` `airi.t3-matrix-launcher.v2` `status=pass` `run_count=48`, `comparisons/d1-blind.json` `airi.d1-blind-comparison.v1` `status=pass` `report_count=48` `winner=null` `adoption_authorized=false`, 실패 gate 29개다. owned 포트 6개 listener 0, AIRI 관련 python/pwsh/node PID 0(무관한 Unity MCP·Codex CLI 프로세스만 존재). 불일치 0이므로 M5 step 1을 시작한다: 채점된 d1v6 report를 read-only 진단 입력으로만 사용해 scratchpad에 축별 실패 row를 추출했다(polite 174행 중 4 arm 공통 43행은 전부 `kind=opinion`·`deterministic_act=wave_opener`, invented_handle 5행, probe miss 32행, transition required miss 89행). 원인 분류는 read-only 진단 subagent 2개(P3 / P2+polite)에 위임했고 결과는 코드·report 재대조 후에만 채택한다. blind v6 재사용·gate/metric 변경·matrix·서비스·GPU 학습·adoption은 0이다. 이 배치에서 허용한 write는 WORKING/ROADMAP-STATUS live 행, ROADMAP-LOG, 대시보드 계약 테스트의 milestone 라벨 일반화뿐이며 commit/push는 아직 없다.

- 2026-08-26 10:10 KST **M4 completion + Claude handoff final publication intent**:
  사용자가 fresh push를 명시적으로 승인하고, 모든 현행 milestone 문서를 갱신한 뒤 다음 작업을
  Claude에 이관할 handoff와 Goal 명령을 요청했다. 시작 프로토콜을 다시 적용한 실제 관측은
  HEAD/local main `09de314c84c2a075ddaab99e0bab4968a04b78f0`, origin/remote main
  `30fe3524996756fbb0a969b94b10d98f208f8508`, ahead 3, worktree/stage/untracked 0이다.
  d1v6는 report·health·run-contract·packet 각 48, unique union/intersection 48/48,
  duplicate·missing 0, exit 0, summary/comparison pass, winner null, adoption false를 유지하고
  관련 process/listener 0이다. 정확한 현재 문서와 신규
  `AIRI-CLAUDE-HANDOFF-2026-08-26-POST-M4.md`만 검증·stage·Conventional Commit한 뒤 승인된
  **한 번의 push**로 로컬 commit 묶음을 게시한다. post-push HEAD/local/origin/remote exact,
  clean, owned PID/listener 0까지 확인한 경우에만 M4를 완료 처리한다. Claude의 M5는 handoff의
  Goal 명령을 사용자가 실제로 제출한 뒤에만 활성화되며 운영 채택은 계속 금지다.

- 2026-08-26 04:00 KST **M4 final machine-state reconciliation + push-gate intent**:
  WORKING 전체와 M4 handoff·D1 contract §6·§7·ROADMAP·NEXT를 다시 읽고 실제 상태를
  대조했다. HEAD/local main은 receipt commit
  `8463e8017450c5cacb962f4eedb5ed9373aae1f2`, origin/main과 remote main은
  `30fe3524996756fbb0a969b94b10d98f208f8508`, local ahead 2, worktree/stage/untracked 0이었다.
  d1v6는 report·health·run-contract·packet 각 48개, 고유 union/intersection 48/48,
  duplicate·missing 0, launcher exit 0, summary/comparison pass를 유지하며 wrapper·관련 process·
  owned listener 0이다. 이 관측값을 다섯 milestone 문서에 동기화하고 계약 검증 뒤 exact
  Conventional Commit으로 닫는다. 그 뒤에도 push는 수행하지 않고 정확한 새 HEAD를 제시해
  fresh 사용자 승인을 요청한다. 운영 채택·campaign·자동 후속 라운드는 계속 금지다.

- 2026-08-26 03:54 KST **M4 dashboard primary commit receipt + push decision gate**:
  `git commit -m "docs: add evidence-backed roadmap dashboard"` exit 0, commit
  `c7500a3e1ef3e48786378c906057958406030386`, 13 files, 879 insertions/74 deletions이다.
  commit 직후 HEAD/local main exact `c7500a3`, origin/main은 `30fe352`, local ahead 1,
  worktree/stage/untracked 0, wrapper PID 10264 absent, owned listener 0이다. M4-10은 push만
  남았지만 추가 사용자 Goal과 global AGENTS 계약에 따라 지금부터 `[D]`로 바꾸고 push하지
  않는다. 이 receipt 문서 묶음을 별도 Conventional Commit으로 닫은 뒤 정확한 local HEAD와
  clean 상태를 사용자에게 제시해 fresh push 승인을 요청한다. 운영 채택·후속 라운드는 이
  승인과도 별개이며 계속 금지다.

- 2026-08-26 03:53 KST **M4 exact stage receipt + commit intent**: dashboard/skill/
  contract/test/docs exact 13경로를 stage했다. Unicode quote를 비활성화한 경로 대조에서
  staged 13/13, missing/extra/unstaged/untracked 0이다. staged 상태의 patch-manifest,
  current-checkpoint, standalone work-continuity, dashboard contract가 모두 PASS했고
  `skill-creator` validator와 staged diff-check도 exit 0이다. HEAD/local/origin은 여전히
  `30fe3524996756fbb0a969b94b10d98f208f8508`다. 이 receipt와 ROADMAP live 행을 재stage해
  동일 manifest·계약을 확인한 뒤 `git commit -m "docs: add evidence-backed roadmap dashboard"`
  를 실행한다. commit 실패 시 push/완료로 승격하지 않으며 push는 성공 뒤 별도 승인을 요청한다.

- 2026-08-26 03:49 KST **M4-10 final validation receipt + exact stage intent**: handoff §5
  exact pinned command는 앞 receipt의 `httpx` collection 함정으로 exit 1, 그 파일을 계약된
  WindowsApps Python으로 실행해 8/8 OK했다. pinned 나머지는 문서에 고정된 기존
  `test_synthesize_broadcast_behavior_v2.py` 2건만 실패하면서 743 passed/9 skipped/297 subtests,
  두 환경·기존 실패 파일을 제외한 M4 affected clean run은 739 passed/9 skipped/297 subtests로
  exit 0이다. proxy/runtime 403 OK, deterministic/guard 52 passed+10 subtests,
  patch-manifest·current-checkpoint·work-continuity·dashboard contract PASS, `skill-creator`
  validator PASS, diff-check exit 0이다. HEAD는 `30fe352`, stage 0, owned listener 0이며 GPU·
  service·campaign·외부 Claude 호출은 0이다. 다음 상태 변경은 관측된 M4 dashboard/skill/
  contract/test/docs 13개 exact path만 stage하고 staged manifest·diff·contract를 재검증한 뒤
  Conventional Commit하는 것이다. push는 수행하지 않고 직전 별도 사용자 승인을 요청한다.

- 2026-08-26 03:40 KST **handoff §5 pinned pytest environment receipt**: §5 첫 exact
  pinned Python command는 65.94초 뒤 collection exit 1이었다. 실패는 코드 assertion이 아니라
  `training/tests/test_synthesize_broadcast_continuity_v4.py` import가 `ollama_proxy.py`의
  `httpx`를 요구하지만 pinned venv에 module이 없는 기존 §4 interpreter split 함정 하나다.
  다른 test는 collection 중단으로 실행되지 않았다. stage/commit은 계속 차단한다. 다음은 이
  unittest 파일을 WindowsApps Python 3.14로 실행하고, pinned suite는 해당 파일을 명시적으로
  제외해 나머지를 실행한다. 문서에 고정된 기존 `test_synthesize_broadcast_behavior_v2.py`
  2 failure 이외의 실패가 없음을 확인한 뒤 known-failure 파일도 제외한 clean affected pass를
  별도로 남긴다.

- 2026-08-26 03:38 KST **M4-10 final validation intent**: HEAD/local/origin은
  `30fe3524996756fbb0a969b94b10d98f208f8508`, stage 0, owned listener 0이고 관측된 dirty는
  M4 terminal·dashboard/skill/contract/test/docs 배치뿐이다. 10분을 넘을 수 있는 handoff §5
  전체 명령을 순서대로 실행한다: pinned Python broadcast_sim·affect·training·launcher pytest,
  WindowsApps Python proxy/runtime unittest, pinned deterministic/guard pytest, patch-manifest·
  current-checkpoint·work-continuity·dashboard contract, `skill-creator` validator, repo diff-check.
  각 exit와 test count를 읽고 하나라도 실패하면 stage/commit으로 승격하지 않는다. GPU 학습,
  서비스, blind 재실행, campaign, 외부 Claude 호출은 0을 유지한다.

- 2026-08-26 03:35 KST **M4-9 shared dashboard skill receipt**: 공통 계약 하나를 참조하는
  byte-identical Codex `.agents/skills/airi-roadmap-dashboard/SKILL.md`와 Claude
  `.claude/skills/airi-roadmap-dashboard/SKILL.md`, Codex UI metadata를 만들었다. 새 root
  contract test는 허용 상태, 현재 Goal `[~]` 최대 1개, `[B]` 원인·재개 조건, `[?]` 0,
  heartbeat 시각/장기 수치, `[S]`·`[N/A]` 분모 제외, M4·전체 비율 재계산, 동일 공통 계약
  참조와 링크·metadata를 실제 파싱해 PASS했다. `skill-creator` quick validator는 Windows
  기본 cp949 첫 실행이 UTF-8 SKILL을 읽지 못해 exit 1이었고 `PYTHONUTF8=1`로 같은 validator를
  재실행해 `Skill is valid!`/exit 0을 받았다. Claude Code `2.1.245` 설치 binary의 project
  `.claude/skills/` 자동 발견 문구도 read-only로 확인해 project `CLAUDE.md` routing 추가는
  불필요하다. 외부 Claude 호출은 0이다. 다음 한 동작은 M4 handoff·LOG·NEXT를 동기화하고
  handoff §5 전체 검증을 실행하는 것이다.

- 2026-08-26 03:30 KST **compact 복구 재대조 receipt + M4-9 계속**: WORKING-STATE
  6,666행을 UTF-8로 EOF까지 다시 읽고 HEAD/local main/origin main exact
  `30fe3524996756fbb0a969b94b10d98f208f8508`, stage 0, 현재 tracked dirty 3개와
  untracked Codex·Claude skill 진입점/공통 계약을 확인했다. d1v6는 exit-code receipt 0,
  report·health·run-contract·packet 고유 교집합/합집합 48/48, duplicate·missing 0,
  summary/comparison pass, no_winner이며 wrapper/owned PID/listener 0과 소유 포트 6개 free다.
  채팅 요약과 달랐던 frontmatter의 `stage/untracked 0`을 관측값으로 정정했다. 다음 한 동작은
  전체 로드맵 계산값을 확정하고 공용 skill 운영 불변식 contract test를 추가·실행하는 것이다.

- 2026-08-26 00:29 KST **사용자용 로드맵 대시보드 추가 Goal 병합 + matrix heartbeat
  16/48**: 추가 사용자 지시로 M4를 중단하지 않고 evidence-backed live dashboard, 전체
  체크리스트 노후화 감사, Codex/Claude 공통 계약 기반 `airi-roadmap-dashboard` 프로젝트
  스킬을 기존 Goal에 합쳤다. matrix 중 허용 write는 WORKING과 ROADMAP-STATUS heartbeat뿐이며
  스킬/테스트/공통 계약 파일은 terminal receipt 뒤에만 만든다. push는 기존 허가를 재사용하지
  않고 직전 별도 승인을 요청한다. 실제 대조는 wrapper PID 10264 exact command live,
  report/health/run-contract/packet 고유 교집합 16/48, union 16, duplicate/incomplete 0,
  stdout 81,518 B, stderr 0 B, exit absent, listener 11435/8880/9880/8892 exact command,
  금지 11436/8890 free다. `skill-creator` 본문은 전체 읽었고 제작은 terminal까지 차단한다.

## 2. 현재 작업 트랜잭션

### M7 current transaction — 2026-08-26 11:45 KST

| 항목 | 값 |
|---|---|
| 의도 | 타계책(`AIRI-BREAKTHROUGH-PLAN-2026-08-26.md`) 실행: 런타임 되먹임 고리를 proxy에서 통제한 뒤 한 변수씩(S2 디코딩·S3 예시·S4 픽업·S5 모델 진단) 같은 99턴을 복제 재생해 사람 채점으로 판정한다. 돌파 = 3축 합성 ≥ 3.0·critical 0·filler ≤ 25%. |
| 입력 pins | local main `a9583c3`(origin/main `d7c6283`+1, push 미승인), 실태 문서 `AIRI-REALITY-CHECK-AND-FINETUNE-REVIEW-2026-08-26.md`, 평가 계약 `AIRI-REAL-DIALOGUE-HUMAN-EVAL-CONTRACT-2026-08-26.md`, 로드맵 v4. |
| 금지 | 파인튜닝·GPU 학습·새 후보, 합성 blind 매트릭스의 채택 게이트 사용, 운영 모델/태그 변경, 승인 없는 push, 실제 대화 본문·시청자 식별 정보의 Git/문서 기록. |
| 현재 행동 | M7-3 사람 채점 확정·기록 완료. S6 입력 정합 방식(M7-9)·M7-10 안전 가드·push 승인을 기다린다. 실행 중 프로세스 0. |
| 다음 성공 조건 | S6 방식이 정해지면 그 입력으로 off/on 복제 3회 + 사전 등록 1회 사람 채점; 성공 = 3축 합성 기준선 대비 +0.2 이상이고 filler 증가 없음. |

## 3. 마지막 내구성 체크포인트

- `20260826-123500-m6-replay-run-04-receipt-preliminary-rating`: run 04 99+1턴, Claude 참고 채점 요약 기록, `f408eb7` commit. HEAD f408eb7 (origin +2, push 미승인). 다음 한 동작은 문서 receipt commit 후 사용자 채점·후보 결정 대기.

- `20260826-115300-m6-code-batches-receipt-await-user-capture`: commit `cdbb6eb`(grounding)·`776b462`(human_review+CI) 재검증 채택, HEAD 3 ahead, push 미승인. 다음 한 동작은 문서 배치 commit과 사용자 세션 캡처 대기.

- `20260826-114500-m6-activation-approvals-receipt`: 사용자 4건 승인 receipt. commit `a9583c3`, 문서 다이어트·로드맵 v4·평가 계약 완료, grounding 수리·채점 도구 subagent 진행 중. 다음 한 동작은 subagent 결과 재검증(unittest/pytest 재실행, diff 검토, CRLF 확인) 뒤 CI matrix 등록과 commit.

- `20260826-112900-m5-pivot-c-reality-check-docs`: 사용자 결정 C. step 4 중단·되돌림 완료, 실태 파악 문서 작성, 현행 문서 전면 갱신 중. HEAD `d7c6283`, dirty는 step 2 코드/테스트 6 + 대시보드 테스트 1 + 문서 8 + agent-memory 2, commit/push 0. 다음 한 동작은 계약 4종 재검증 후 사용자에게 결정 큐(실제 대화 데이터, grounding 게이트 수리, commit 여부) 보고.

- `20260826-112000-m5-step2-step3-receipt-step4-v7-intent`: step 2 red/green과 step 3 분리 검증 완료(§1 11:20 항목에 exact 수치). HEAD `d7c6283` 유지, dirty는 코드/테스트 6 + 문서 6 + agent-memory 2 + 대시보드 테스트 1이며 commit/push 0. 다음 한 동작은 step 4 seal `d1v7` generation·lint 구현과 red/green이다.

- `20260826-104500-m5-step1-diagnosis-receipt-step2-intent`: step 1 완료. 축별 원인 분류(polite=v6 opener 저작 artefact, invented=substring 충돌 2+briefing author pool 불일치 3, transition=grounding 침묵 폴백 72/모델 15/어느 2, probe=P3 미발동 29/폴백 2/근거 부재 1, 계층 결함 3종)를 report 집계·코드로 재대조했다. 다음 한 동작은 step 2 red/green: 계층 `deterministic_utterance_layer.py`+테스트, harness `run_broadcast_sim.py` grader pool+테스트. 새 matrix/서비스/GPU/adoption 0, HEAD `d7c6283` 유지, dirty는 WORKING/ROADMAP/LOG/대시보드 테스트뿐.

- `20260826-104000-m5-activation-reconciliation-step1-diagnosis-intent`: M5 Goal 제출로 활성화. 대조값 HEAD/local/origin/remote `d7c6283`, clean, worktree 1, d1v6 exit 0·48/48·summary/comparison pass·winner null·failed gates 29·adoption false, owned listener 0, AIRI PID 0. step 1 진단 추출 완료(polite 공통 43행 = opinion/wave_opener, invented 5, probe miss 32, transition required miss 89) 및 subagent 위임 중. 다음 한 동작은 위임 결과 재대조 후 step 2 exact 파일 경계·red/green 명령 확정과 사용자 보고다. matrix/서비스/GPU/adoption 0.

## 4. 다음 허용 행동

1. grounding 게이트·human_review 도구 결과를 재검증해 채택하고 CI matrix에 새 테스트를 등록한 뒤
   exact 파일만 Conventional Commit한다(로컬). push는 사용자 승인 뒤에만.
2. 사용자가 실제 세션(테스트 방송 또는 직접 채팅) 50~100턴을 캡처하면 export→채점 시트→요약으로
   기준선을 만든다(M6-6/7). 본문·식별 정보는 저장소 밖에만 둔다.
3. 기준선 뒤 첫 개선 후보(재료 공급/결정론 계층/프롬프트/모델 교체)는 사용자 결정(M6-8).
   파인튜닝·합성 blind 매트릭스·운영 채택은 별도 승인 없이는 시작하지 않는다.

## 5. 갱신 트리거

active goal에서는 다음 중 하나라도 발생하면 이 파일을 먼저 갱신한다.

- 마지막 기록 후 최대 120분 경과(heartbeat 상한)
- 체크리스트 항목 또는 테스트 묶음 완료·실패
- 10분 이상 걸릴 수 있는 명령 실행 직전과 종료 직후
- 장기 프로세스 시작·PID 변경·중단·checkpoint 생성
- 새 산출물·해시·커밋·push·권한·blocker 발생
- 사용자의 pause/stop/resume, 세션 종료, 예상 가능한 재부팅
- compact가 예상되거나, 요약된 컨텍스트를 받았다고 판단한 직후

자동 compact 직전 알림은 보장되지 않는다. 따라서 “compact 직전 기록”에만
의존하지 않고 위 이벤트 기록과 60분 heartbeat를 함께 사용한다. heartbeat는
이 문서만 짧게 덮어쓰며, 로드맵 로그는 milestone에서만 갱신한다.
GPU 학습·merge/package·T3·장기 campaign 중 heartbeat 상한은 30분이다.

## 6. 시작·resume·compact 후 복구 절차

1. **행동 전에 이 파일 전체를 읽는다.**
2. 실제 goal status와 최신 사용자 명령을 확인해 권한 경계를 복원한다.
3. `git status --short --branch`, HEAD, 관련 PID·command line, 산출물·로그 크기와
   SHA를 read-only로 확인한다.
4. 현행 GPU 인계서와 로드맵 체크리스트의 해당 단계만 다시 읽는다.
5. 관측 상태와 이 문서가 다르면 실행하지 말고 이 문서를 실제 상태로 정정하며
   차이를 로드맵 로그에 남긴다.
6. 이미 실행 중인 PID가 있으면 exact command/output/log를 확인하기 전에는
   중복 프로세스를 시작하지 않는다.
7. 복구 시각·관측 근거·다음 한 동작을 새 checkpoint ID로 기록한 뒤 작업한다.

충돌 시 우선순위는 `최신 사용자 명령·goal status → 실제 프로세스/파일/SHA →
이 live state → 현행 handoff → roadmap status/log → compact된 채팅 요약`이다.

## 7. 단계 전후 기록 형식

장기·상태 변경 작업은 한 번의 서술로 끝내지 않고 두 단계로 기록한다.

- **intent checkpoint:** 실행 전 권한, exact command, 입력 SHA, 출력 경로,
  기대 완료 조건, 중단/복구 방식을 기록한다.
- **receipt checkpoint:** 종료 후 exit code, PID 종료 여부, 산출물 크기/SHA,
  테스트 결과, 실패·부분 완료 여부와 다음 한 동작을 기록한다.

의도만 있고 receipt가 없으면 완료가 아니다. 계산 시간이 있었더라도 checkpoint나
검증 산출물이 없으면 진척으로 승격하지 않는다.

## 8. 장기 문서로 승격하는 시점

- checklist 항목 완료·실패, 권한 변경, 모델/데이터/산출물 SHA 변경:
  현행 handoff와 roadmap status를 갱신한다.
- 매 작업 배치·commit: `AIRI-ROADMAP-LOG.md`에 기록한다.
- pause·handoff·PC 전환: 이 파일을 최종 receipt 상태로 갱신하고, 허가된 경우에만
  commit/push한다. push하지 못했으면 로컬 전용 상태임을 사용자에게 명시한다.
- heartbeat만 발생: 이 파일만 갱신하며 장기 문서를 불필요하게 다시 쓰지 않는다.

비밀, credential/token, `.env` 값, 원문 방송 데이터, 개인정보·개인 경로, 개인
오디오, 모델 weight, 런타임 DB와 로그 본문은 이 문서에 기록하지 않는다. exact
command는 민감한 인자를 redaction하고 경로·크기·비민감 SHA와 판정만 기록한다.
입력 clean preflight에서는 heartbeat로 생긴 이 파일 단독 diff만 명시적으로 제외해
별도 검토할 수 있다. 다른 tracked/untracked 변경은 허용하지 않는다.
