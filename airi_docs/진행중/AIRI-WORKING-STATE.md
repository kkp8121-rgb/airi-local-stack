---
schema_version: 1
updated_at_kst: "2026-08-23 03:07:09 +09:00"
checkpoint_id: "20260823-030709-p0-receipt-docs-push-finalization-intent"
goal_status: "active"
authorization: "repository-gpu-training-packaging-local-services-evaluation-commit-push-authorized; operational-adoption-forbidden"
active_phase: "p0-batch-final-receipt"
git_head: "a898ff82939ab59dc3fd84d2fb6214ecf381113e"
worktree_state: "5-final-receipt-docs-modified-head-origin-main-equal"
active_trainer_count: 0
---

# AIRI live working state

> **세션 시작·goal resume·재부팅·컨텍스트 compact 직후 가장 먼저 읽는다.**
> 채팅 요약이나 기억만으로 작업을 재개하지 않는다. 이 문서는 현재 행동을 짧게
> 보존하는 가변 SSoT이고, `AIRI-CODEX-HANDOFF-2026-08-21.md`는 검증된 장기
> 인계 SSoT다.
> frontmatter의 `git_head`와 `worktree_state`는 이 checkpoint를 쓰기 직전에 관측한
> 기준 상태다. checkpoint를 포함한 commit 자체의 SHA를 자가 참조하지 않는다.

## 1. 권한과 현재 사실

- 2026-08-23 01:12 KST 최신 사용자 `/goal` 명령으로 goal을 명시적으로 재개했다.
  Goal 도구의 실제 status는 `active`이며 complete/cancel이 아니다. 저장소 구현·검증,
  통제 GPU, authoritative E2, 병합·패키징, T3·campaign, 검증된 milestone commit/push가
  승인됐다. 운영 모델 채택과 기본 서비스 모델 변경은 계속 별도 사용자 승인 대상이다.
- 운영 모델 채택과 기본 모델 변경 금지는 pause와 무관하게 계속 유지한다.
- 2026-08-22 18:40 KST compact 복구 재확인: Python trainer/durable runner
  프로세스 0. GPU process 목록에는 OS/app 프로세스가 있지만 식별 가능한 AIRI
  trainer/runner workload는 0이다.
- v4 파인튜닝은 E1 adapter/report까지만 완료·검증됐고 아직 미채택이다.
- E2 adapter/report, merge/package, v4 T3, live campaign 산출물은 0이다.
- HEAD와 origin/main은 safe-pause final receipt
  `32830a43556ba7704a39bd9094f128a5a98dd7d7`로 일치한다. source/chat/base와
  E1 adapter/config/report의 크기·SHA는 고정값과 exact 일치한다. E2 adapter/report/
  durable run, T3와 campaign은 없고 기존 E2 stdout/stderr는 각 0 bytes다. 사용량
  초기화 후 지정 SSoT를 다시 읽고 19:27 KST actual worktree clean, AIRI
  trainer/runner 0, 기존 planned P0-B root와 E2 adapter/report 부재를 대조했다.

## 2. 현재 작업 트랜잭션

| 항목 | 값 |
|---|---|
| 의도 | 동결된 현재 로컬 P0 코드 배치를 범위 확장 없이 검증·마감해 origin/main에 push한다. |
| 허용 범위 | 동결 P0/P1 기준의 최소 수정, 지정 gate·독립 감사·offline/security 검증, SSoT 갱신과 commit/push. 운영 채택은 금지 |
| 시작 전 증거 | Goal active, HEAD=local/remote origin/main `32830a4`, modified 16+untracked 1+staged 0 exact, AIRI trainer/runner 0, planned GPU root/E2 adapter/report absent. source/chat/base/E1 크기·SHA exact, E2 logs 각 0 bytes. |
| exact 변경 | checkpoint event-before-index 원자 권한·index-rooted hash chain, 누적 monotonic elapsed, payload/event/report/progress 결속, producer evidence root, Windows no-follow 입력 잠금, trainer/helper 실행 snapshot, authenticated run-state lineage를 구현한다. launcher는 Start-Process ancestry와 trainer parentage에 결속하고 marker 직전 deadline/state/PID를 재검증한다. |
| 출력 경로 | 저장소 owned code/test와 SSoT 문서만 변경. 모델·adapter·GGUF·runtime DB·로그 본문·D: P0-B root 출력 0 |
| 완료 조건 | manifest mismatch/path fault, prearm fresh-only/first-boundary, exact runner-exit/timeout 회귀와 focused/full offline PASS, 독립 최신 P0/P1 0, diff/security PASS, milestone commit/push |
| 중단·복구 | 회귀 실패·새 P0/P1·프로세스 누수 시 GPU/E2 금지를 유지하고 receipt를 기록한다. 기존 실행/산출물을 삭제하거나 재사용하지 않는다. |
| 현재 행동 | implementation push receipt 5-doc commit `a898ff82939ab59dc3fd84d2fb6214ecf381113e`까지 origin/main에 push됐고 worktree clean/PID 0을 확인했다. 이 final receipt를 5-doc에 반영해 `docs: finalize P0 batch receipt`로 commit/push한 뒤 HEAD=origin/main·clean을 확인하고 controlled GPU preflight로 이동한다. |

## 3. 마지막 내구성 체크포인트

- `20260823-030709-p0-receipt-docs-push-finalization-intent`: exact 5-doc stage는
  staged 5+unstaged/untracked 0, boundary/cached diff/security PASS였다. exact
  `git commit -m "docs: record durable training push"`는 exit 0, commit
  `a898ff82939ab59dc3fd84d2fb6214ecf381113e`, 5 files, 90 insertions/38 deletions이다.
  이어 exact push exit 0, `911d082..a898ff8 main -> main`; 이후 HEAD/local origin/main/
  remote main은 모두 `a898ff8`, worktree clean, 관련 PID 0, E2 adapter/report absent다.
  P0 implementation과 5-doc receipt는 origin/main에 durable하다. 이 actual docs-push
  receipt를 최종 5-doc에 반영해 focused/diff/security, exact stage/cached 검증,
  `docs: finalize P0 batch receipt` commit/push를 수행한다. 성공 뒤 read-only
  HEAD=origin/main·clean/PID 0을 확인해야만 controlled GPU intent를 쓴다.
- `20260823-030605-p0-push-receipt-docs-stage-intent`: implementation push receipt를
  반영한 WORKING-STATE, 현행 handoff, roadmap status/log, NEXT exact 5경로만 dirty이며
  boundary diff 0, staged/untracked 0이다. focused continuity exit 0/PASS, repo diff-check
  exit 0/whitespace error 0, security hit 0이다. 5-doc 총 506,017 bytes path+size+SHA
  manifest는 `66f49a42b3f4291e6599df6b4d125702f09f31bb623a347a0dffa79e3915305b`다.
  이 receipt 문서 반영 뒤 exact 5경로를 stage해 staged 5/unstaged 0/untracked 0과
  cached diff/security를 확인하고 `git commit -m "docs: record durable training push"`,
  `git push origin main` 순서로 실행한다. 실패하면 controlled GPU/E2로 이동하지 않는다.
- `20260823-030416-p0-implementation-push-receipt-docs-intent`: commit receipt 두 문서는
  exact boundary 2, staged/untracked 0, focused continuity와 repo diff-check PASS였다.
  exact `git push origin main`은 exit 0,
  `32830a4..911d082 main -> main`. 이후 HEAD/local origin/main/remote main은 모두
  `911d082dcf1768a5145bd34d56a19f82deb9d248`, 관련 PID와 AIRI GPU workload 0,
  E2 adapter/report absent다. P0 로컬 배치 구현·검증 commit은 origin/main에 durable하지만
  actual push receipt용 문서는 아직 로컬이다. WORKING-STATE, 현행 handoff, roadmap
  status/log, NEXT 5종에 이 receipt와 controlled-GPU-next 경계를 반영한다. focused
  continuity/diff/security 뒤 exact 5-doc commit/push를 완료하기 전에는 controlled GPU/E2를
  시작하지 않는다.
- `20260823-030311-p0-implementation-commit-push-intent`: receipt 문서 재stage 뒤 final
  index는 staged 17+unstaged/untracked 0, boundary diff 0, cached diff/security PASS,
  총 blob 1,170,009 bytes, manifest
  `69cbf2c653d896d1863aa28b69544c63deca3cba83d58427e6ba658302c9b23d`였다.
  exact `git commit -m "fix: harden durable training evidence"`는 exit 0, commit
  `911d082dcf1768a5145bd34d56a19f82deb9d248`, 17 files, 8,275 insertions/
  544 deletions, input-manifest builder 신규다. parent는 `32830a4`; commit 직후
  worktree clean, local main은 local/remote origin/main `32830a4`보다 1 ahead, 관련 PID
  0이다. 이 receipt용 WORKING-STATE와 roadmap log 두 파일만 dirty로 만들고 boundary/
  diff-check 뒤 exact `git push origin main`을 실행한다. 실패하면 local commit과 receipt
  문서를 보존하고 GPU/E2로 이동하지 않는다.
- `20260823-030150-p0-staged-batch-commit-intent`: exact 17-path `git add --` exit 0.
  cached diff-check는 exit 0/출력 0이고 staged 17, boundary diff 0, unstaged 0,
  untracked 0이다. staged blob 총 1,168,787 bytes, index path/mode/blob/size manifest SHA는
  `19a63ba87469e8b0b7f55f466e3b9394c22079abbb14b44cb095a7a09b8182b8`다.
  cached 금지 경로·5 MiB 초과 blob·알려진 credential·민감 literal·개인 경로 hit 0,
  관련 PID 0이고 문서 인덱스는 stage하지 않았다. 이 receipt로 바뀐 WORKING-STATE와
  roadmap log 두 파일만 재stage해 동일 17/0/0 경계와 cached diff/security를 재확인한 뒤
  exact `git commit -m "fix: harden durable training evidence"`를 실행한다. 실패하면
  push/GPU/E2로 이동하지 않고 staged 배치를 보존한다.
- `20260823-030013-p0-prestage-pass-stage-intent`: milestone SSoT 정리 뒤 focused
  `test-airi-work-continuity.ps1` exit 0/PASS, repo 기본 diff-check exit 0/whitespace
  error 0이다. actual 변경 경로는 expected 17개와 boundary diff 0, staged 0,
  untracked는 input-manifest builder exact 1개, 관련 PID 0이다. 최신 17-file 총
  1,170,513 bytes의 금지 산출물/비밀정보 hit는 0이고 path+size+SHA canonical manifest는
  `e4a183c77969284794237202bcbc05e93f2abc47ee1f6918de027cf92f8e065a`다. 이
  receipt 문서 갱신 뒤 focused continuity와 repo diff-check를 최종 확인하고 exact 17경로만
  `git add --`한다. 완료 조건은 staged 17+unstaged 0+untracked 0, cached diff-check와
  cached security hit 0이다. 실패하면 commit/push/GPU/E2로 이동하지 않는다.
- `20260823-025711-p0-diff-security-pass-docs-intent`: repo 기본 exact
  `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'`은 exit 0, whitespace
  error 0이며 LF→CRLF 경고만 있었다. 현재 17개 변경 경로 1,167,298 bytes를 값 노출 없이
  검사해 금지 `.env`/weight/adapter/GGUF/audio/DB/log filename, binary, 5 MiB 초과,
  알려진 credential 형식, 민감 변수의 literal 값 할당, 개인 경로 hit가 모두 0이다.
  staged 0도 유지된다. 이 receipt로 동결된 P0 로컬 코드 배치의 지정 검증은 완료됐고,
  현재 blocker는 milestone SSoT 정리와 exact stage/commit/push뿐이다. WORKING-STATE,
  현행 handoff, roadmap status/log, NEXT를 실제 receipt에 맞춰 갱신하고 문서 인덱스는
  현행 handoff를 정확히 가리키므로 변경하지 않는다. 이후 focused continuity와 repo
  diff-check를 수행하며 실패 시 stage/commit/push/GPU/E2로 이동하지 않는다.
- `20260823-025556-p0-full-offline-pass-security-intent`: exact
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\test-current-checkpoint.ps1`은
  exit 0이다. 내부 `AIRI work-continuity contract: PASS`, `AIRI training durability
  contract: PASS`와 최종 `Current checkpoint contract: PASS (offline synthetic ASAR
  only; no installed archive/service/model access)`를 확인했다. post-run 관련 PID 0,
  worktree는 16 modified+1 untracked+0 staged의 동일 경계다. 이 receipt로 P0 로컬 배치의
  지정 Python/PowerShell/full-offline gate는 모두 완료됐다. 다음은 repo 기본 exact
  `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'`와 현재 17-path 금지
  산출물 filename·비밀 값 형태 content scan이다. 둘 다 exit 0/hit 0 전에는 milestone
  SSoT 정리, stage/commit/push, GPU/E2로 이동하지 않는다.
- `20260823-025314-post-compact-p0-final-receipt-reconcile`: compact 직후 지정 SSoT
  5종을 순서대로 전체 재독하고 Goal/Git/PID/SHA를 다시 대조했다. Goal status=`active`;
  HEAD/local origin/main/remote main은
  `32830a43556ba7704a39bd9094f128a5a98dd7d7`, actual worktree modified 16+
  untracked 1+staged 0, 관련 runner/trainer/test/verifier PID 0, 식별 가능한 AIRI GPU
  workload 0이다. source/chat/base/E1 크기·SHA는 고정값과 exact 일치하고 E2 adapter/
  report와 D: durable run-state/checkpoint는 absent, E2 stdout/stderr는 각 0 bytes/SHA
  `e3b0c442...b855`다. 세 preserved synthetic root는 그대로 존재하고 inventory SHA는
  `a6395584...c215`/`7fe8a23e...4439`/`3d3b38b...99db`, 로그 12개는 모두 0 bytes다.
  직전 intent 뒤 exact fresh PowerShell contract는 02:43 KST exit 0, literal
  `AIRI training durability contract: PASS`, post-run 관련 PID 0이다. final test/launcher/
  verifier SHA는 `738630d9...8756c6`/`856c4322...e9acda`/`621de009...230799`로
  intent와 exact 일치하고 12-file manifest `59087297...a4a5b` 경계도 유지된다. 따라서
  한 차례 독립 감사의 P0=0과 그 감사가 고정한 원래 P1 네 건은 exact 수정+targeted+
  Python/PowerShell 통합 receipt로 모두 닫혔다. 새 감사 라운드는 추가하지 않는다.
  다음 한 동작은 exact `powershell -NoProfile -ExecutionPolicy Bypass -File
  .\test-current-checkpoint.ps1` 1회다. exit 0/final checkpoint PASS/PID 0 전에는
  diff/security, stage/commit/push, GPU/E2로 이동하지 않는다.
- `20260823-024141-powershell-final-orphan-retry-intent`: orphan fixture는 state publication
  직후 기존 `Write-ContractRunStateAnchor`로 canonical current anchor를 게시한다. dynamic
  probe의 current SHA/revision/run-id exact와 previous null, AST, authenticated existing→
  trainerAlive static path, scoped diff-check가 PASS했다. test는 99,227 bytes SHA
  `738630d9...8756c6`, 새 12-file manifest는
  `5908729735313b72fedaa309c62d04a20472d049900de192817ea7fb975a4a5b`, 관련 PID 0이다.
  제품/Python bytes unchanged이므로 Python final `145 passed, 5 skipped`를 유지한다. exact
  fresh PowerShell contract 한 번을 영향/최종 gate로 실행하고 exit 0/literal PASS/PID 0을
  요구한다. 실패 시 새 root를 보존·원인 확정 전 반복하지 않으며 offline/GPU/E2는 금지다.
- `20260823-023824-powershell-orphan-anchor-fixture-fix-intent`: anchor raw-restore 뒤
  fresh PowerShell gate는 exit 1/final PASS 없음, preserved root
  `airi-durability-contract-24fedabe234741418465bc9711341d0f`, post-run 관련 PID 0이다.
  보존 terminal-injection run은 unrelated prime/forged/exact anchor-authorized restore
  marker를 모두 남기고 complete revision 3/trainer-complete, current/previous와 anchor
  exact, final evidence/artifacts verified로 수렴했다. 따라서 직전 fixture 수정과 product
  poll anchor 결속은 실제 경로에서 PASS했다. 다음 생성 시각의 `orphan-case`는 structurally
  valid interrupted run-state와 live trainer identity만 쓰고 `run-state.anchor.json`을 만들지
  않아 launcher가 side effect 전 exact `run-state anchor ... CreateFileW failed: 2`로
  거부했다. 이는 제품 결함이 아니라 새 authenticated-existing-state 계약에 이관되지 않은
  fixture다. 제품을 변경하지 않고 기존 `Write-ContractRunStateAnchor`로 orphan current의
  canonical anchor만 게시해 원래 `alive without its durable runner`/no logs duplicate 방지
  회귀를 유지한다. AST/static/diff와 새 manifest/PID 0 뒤 exact final gate 한 번을 다시
  실행하며 Python PASS, GPU/E2 금지는 유지한다.
- `20260823-023607-powershell-anchor-restore-retry-intent`: test-only embedded fake는
  anchor-authenticated state의 `state_raw`를 캡처하고, forgery 뒤 still-current anchor의
  SHA/revision과 재확인한 뒤 동일 bytes를 임시 파일에 써 atomic replace한다. 임의 +200
  revision과 JSON 재직렬화는 제거했고 parent는 prime marker와 새 exact-authority restore
  marker, non-complete live launcher receipt를 모두 요구한다. 제품 파일 unchanged다.
  worker의 PowerShell AST, embedded fake py_compile, raw capture/exact restore/anchor check/
  restore marker/no revision bump static 5/5, scoped diff-check가 PASS했다. test는 99,142 bytes
  SHA `2aa141d7...05d2b0`, 새 12-file manifest는
  `a50787accc09e9ed7dda7cb0dbf886ad3df4103978acd2ad27ccab3e29200976`, 관련 PID 0,
  worktree modified 16+untracked 1+staged 0이다. Python final `145 passed, 5 skipped`는
  test-only 변경으로 유지한다. exact fresh `powershell -NoProfile -ExecutionPolicy Bypass
  -File .\test-airi-training-durability.ps1 -KeepFailedArtifacts` 한 번을 영향/최종 gate로
  실행한다. exit 0/literal PASS/PID 0 실패 시 root를 보존·진단하고 반복하지 않는다.
- `20260823-023219-powershell-anchor-restore-fixture-fix-intent`: exact final PowerShell
  gate는 약 60초 뒤 exit 1, final PASS 없음; preserved root
  `airi-durability-contract-dd1dbf0a827e4f65aa7b3a1e3dc1a89f`, post-run 관련 PID 0이다.
  실패는 line 1310 terminal-injection launcher timeout이며 `launch_shim_exited=False`다.
  로그 본문 없이 68-file size/SHA와 state/anchor를 대조했다. terminal-injection run은
  이후 complete revision 3/trainer-complete exit 0, current SHA `bad88b13...e944f1`와
  anchor.current exact, previous revision 1/SHA `04aa80c0...71c639`, adapter/report/final
  evidence가 존재하고 PID 0이다. quarantine에는 actual runner/trainer identity를 가진
  `running` revision 202 state가 exact 남았다. fixture가 anchor-authenticated revision 2
  state를 캡처한 뒤 forgery 종료 시 revision을 `+200`해 재직렬화하므로 복원 state 자체가
  의도와 달리 unanchored가 됐고, 새 launcher가 이를 관측하지 않은 것이 정확한 원인이다.
  제품은 변경하지 않는다. embedded fake만 captured authority raw bytes를 보존해 forgery
  뒤 byte-exact 복원하고, anchor exact live 관찰/forged rejection/final complete를 targeted
  actual job으로 검증한다. AST/static/scoped diff와 새 manifest/PID 0 receipt 뒤에만 fresh
  PowerShell 영향/최종 gate 한 번을 승인한다. Python `145 passed, 5 skipped`는 test-only
  수정으로 유지하며 full offline/stage/GPU/E2는 금지한다.
- `20260823-022808-p1-python-pass-powershell-final-intent`: finalized 12-file manifest
  `64441cf4...2be00c`에서 핀된 5-module py_compile과 네 Python suite 전체는 exit 0,
  `145 passed, 5 skipped in 34.84s`; post-run 관련 PID 0이다. verifier/launcher/test SHA는
  intent 값과 unchanged이고 actual worktree modified 16+untracked 1+staged 0이다. 다음
  exact 단일 명령은 `powershell -NoProfile -ExecutionPolicy Bypass -File
  .\test-airi-training-durability.ps1 -KeepFailedArtifacts`다. console과 synthetic system-temp
  root만 출력하며 pass면 정리되고 failure면 보존한다. 완료 조건은 exit 0, literal
  `AIRI training durability contract: PASS`, post-run 관련 PID 0이다. 실패 시 같은 원인을
  반복하지 않고 보존 진단하며 full offline/stage/commit/push/GPU/E2를 금지한다.
- `20260823-022645-p1-final-python-integration-intent`: launcher 후속은 미정의 snapshot
  결함을 exact authority receipt bytes 보존으로 고쳤고, polling도 non-null previous를
  포함한 full anchor entry schema와 state SHA/revision/run-id를 매 iteration 결속한다.
  worker AST, 동적 candidate authority snapshot, anchor static guard, scoped diff-check가
  PASS했고 launcher/test SHA는 `856c4322...e9acda`/`f6a57ce1...254b4b`다. root는 verifier
  세 schema/timing 수정과 launcher existing/polling anchor 경로를 source에서 대조했다.
  최종 12-file path+size+SHA manifest는
  `64441cf4bbe0a559d850de0a6b8fa5166625c807c72bd22ed3837be0032be00c`, 관련 PID 0,
  worktree modified 16+untracked 1+staged 0이다. 핀된 Python 3.12로 checkpoint/trainer/
  runner/verifier/input-manifest builder py_compile 후 네 Python suite 전체를 한 순차 명령으로
  정확히 한 번 실행한다. exit 0, exact pytest count, post-run 관련 PID 0을 요구하며 실패 시
  같은 원인을 반복하지 않고 PowerShell/full offline/GPU/E2를 금지한다.
- `20260823-022415-p1-worker-review-failure-receipt`: verifier 담당은 세 감사 항목을
  exact 최소 수정했다. checkpoint payload progress는 producer/runner와 같은 3-field,
  terminal run-state는 completed progress의 exact 5-field projection, checkpoint state
  비교는 dedicated timing evidence에서 별도 검증되는 `training_elapsed_ns`만 제외한다.
  핀된 pycompile exit 0, verifier focused `61 passed, 1 skipped in 1.97s`; verifier/test
  SHA는 `621de009...230799`/`fc2cbf3c...0a436`다. root source 검토도 세 producer 계약과
  일치함을 확인했다. launcher 담당의 AST/static/diff receipt는 root가 승인하지 않았다.
  `Read-ValidRunStateCandidate`가 authority JSON의 `.value`만 저장한 뒤 존재하지 않는
  `$snapshot.Bytes`를 hash해 StrictMode catch로 모든 실제 candidate를 null 처리하는
  재현 가능한 수정 결함이 있다. full contract를 실행하지 않고 exact authority receipt의
  bytes를 유지하도록 같은 담당에게 최소 수리와 동적 candidate/anchor 검증을 요청했다.
  polling은 anchor current뿐 아니라 non-null previous entry까지 전체 schema가 유효해야
  state를 관측하도록 함께 확인한다. 이 receipt는 P1 closure PASS가 아니며 GPU/E2,
  full integration, stage/commit/push는 금지 상태다.
- `20260823-021837-p0-final-audit-p1-fix-intent`: compact 직후 지정 SSoT 5종을 순서대로
  전체 재독했다. Goal status=`active`; HEAD/local origin/main/remote main은
  `32830a43556ba7704a39bd9094f128a5a98dd7d7`, actual worktree modified 16+
  untracked 1+staged 0, 관련 runner/trainer/contract/verifier PID 0이다. source/chat/base와
  E1 adapter/config/report의 크기·SHA는 고정값과 exact 일치하며 E2 adapter/report와
  D: durable run-state/checkpoint는 absent, 기존 E2 stdout/stderr는 각 0 bytes다. 보존
  synthetic `ff7cec...` root는 존재하고 state/anchor SHA만 재대조했으며 로그 본문은 읽지
  않았다. 한 차례 독립 최신-byte 감사의 최종 판정은 `NOT READY`, P0=0/P1=4다:
  (1) producer checkpoint event의 3-field `checkpoint_payload_progress`와 verifier의
  4-field 요구 불일치, (2) runner terminal 5-field progress와 verifier의 completed
  `progress.json` 11-field whole-object 비교 불일치, (3) 무중단/재개 state 비교가
  비결정적 cumulative `training_elapsed_ns`를 exact 비교, (4) launcher existing/polling
  path가 anchor로 current를 인증하기 전에 already-running/baseline으로 사용할 수 있다.
  사용자 동결선에 따라 이 네 원래 safety/integrity/evaluator P1만 최소 수정하고 새 감사
  라운드는 추가하지 않는다. 각 targeted 회귀와 root diff 검토 뒤 영향을 받은 Python/
  PowerShell gate 및 최종 Python+actual-process 통합 gate를 재실행한다. P1 0과 권위
  receipt 전에는 full offline/stage/commit/push/GPU/E2로 이동하지 않는다.
- `20260823-020638-p0-latest-byte-independent-audit-intent`: exact fresh PowerShell
  contract는 exit 0, literal `AIRI training durability contract: PASS`; post-run 관련
  runner/trainer/contract/verifier PID 0이다. test SHA `b93d29bd...03b6b0`, HEAD와
  origin/main `32830a4`, actual worktree modified 16+untracked 1+staged 0으로 입력 경계가
  유지됐다. resume 이후 권위 Python receipt는 `139 passed, 5 skipped in 33.12s`, 이번
  actual-process PowerShell receipt는 PASS다. 사용자 고정 순서에 따라 현재 최종 bytes를
  한 차례만 독립 read-only 감사한다. 판정 범위는 동결 P0(10분 손실, corrupt/forged,
  exact SHA/seed/config, duplicate PID, unverified SAFE, equivalence/provenance false PASS,
  localhost/privacy/opt-in/adoption 금지)와 원래 safety/integrity/evaluator P1뿐이며 새
  schema/threat/refactor/observability는 backlog로 분리한다. P0/P1 0 전에는 full offline,
  stage/commit/push/GPU/E2로 이동하지 않는다.
- `20260823-020504-p0-powershell-contract-prearm-fix-intent`: prearm fixture는 launcher
  run-id/nonempty verified receipt, terminal paused-safe/exit 75/checkpoint verification을
  요구하고, 별도 post-hoc pause는 nonzero/no exact marker/exact already-paused error를
  요구하도록 바뀌었다. 제품 unchanged다. AST error 0, static 7/7, preserved prearm에 대한
  actual subprocess exit 1/no marker/expected error, scoped diff-check exit 0, test 97,192 bytes
  SHA `b93d29bdf0e8ee5e672b219fd85d8edbed9205bfa1d360282da1d0259103b6b0`,
  12-file manifest `c588ddc358444ae83668605a1a9b50d39d00137ef1782e31836bb2f1e2f8ce11`,
  관련 PID 0이다. exact fresh `-KeepFailedArtifacts` contract 한 번을 영향/최종 gate로
  실행하며 exit 0/final PASS/PID 0 실패 시 반복 없이 보존 진단한다. GPU/E2 금지다.
- `20260823-020406-prearm-posthoc-safe-fixture-fix-intent`: fresh integration은 앞선
  terminal/quarantine fault를 통과하고 prearm-first-boundary에서 pause product의 exact
  `Already-paused terminal cannot authorize power-off without runner and trainer identities observed live by this invocation`
  거부로 exit 1; preserved root `airi-durability-contract-408960062357437f98c9c096dc0aa515`,
  post-run PID 0이다. 보존 prearm state는 paused-safe revision 4/exit 75, terminal
  checkpoint-verification 6-field, request+ack, current anchor가 존재한다. launcher는 자신의
  invocation에서 live identities를 관측해 terminal receipt를 반환했지만 test가 그 뒤
  별도 post-hoc pause invocation에서 unobserved terminal로 SAFE marker를 기대한 stale
  fixture다. 제품을 변경하지 않고 launcher receipt의 paused-safe/run-id를 직접 요구하고,
  별도 post-hoc pause는 nonzero/no exact marker/위 exact error로 거부돼야 한다고 바꾼다.
  이는 unverified SAFE 금지선을 강화한다. AST/targeted/static/diff 뒤 영향/최종 integration
  gate를 실행하며 GPU/E2는 금지다.
- `20260823-020141-p0-powershell-contract-revision-sync-intent`: current embedded fake를
  쓴 별도 actual job은 readiness, unrelated prime, forged marker, marker 시점 job live,
  launcher non-complete running receipt, final complete/exit 0/trainer-complete, related PID 0
  등 10/10 조건 PASS다. final current/anchor SHA는 `17b8c887...85a15`/
  `2bad5ab5...13faa`다. 현재 test SHA는 `3b5a9359...68b00`, 12-file manifest
  `d5214cee961f12b569d18c8774b340e806d51b3c0f2f269d4981ee01bf56aae3`, 관련 PID 0이다.
  exact fresh `-KeepFailedArtifacts` contract 한 번을 영향/최종 integration gate로
  실행한다. exit 0/literal final PASS/post-run PID 0이 아니면 보존 root를 진단하고
  반복하지 않는다. 제품/GPU/E2는 unchanged/금지다.
- `20260823-015941-terminal-prime-targeted-actual-intent`: revision/anchor sync 수정 뒤
  PowerShell AST error 0, embedded fake Python compile exit 0, authority/deadline static 7/7,
  scoped diff-check exit 0, test 96,651 bytes SHA
  `3b5a935931e56f9653bf7676880b79964de27764db99536a2ffaa0d1cef68b00`, 관련 PID 0이다.
  전체 contract 전 별도 system-temp에 현재 embedded fake source, fresh input fixture와
  exact live sleeper records를 만들고 JSON job 한 건으로 readiness→authenticated rev>=2→
  unrelated prime→forged marker→launcher non-complete/final state를 targeted 검증한다.
  관련 synthetic PID는 identity 확인 후 회수하며 실패 시 full contract를 반복하지 않는다.
  제품/GPU/E2는 변경하지 않는다.
- `20260823-015817-terminal-prime-revision-sync-fix-intent`: quarantine fixture 수정 뒤
  fresh integration은 terminal-injection line 1264
  `Actual-process forged complete terminal was not observed while launcher invocation remained live`
  로 exit 1; preserved root `airi-durability-contract-9f6737fc53ea4965b12d2f4b7ae04990`,
  post-run PID 0이다. RunDir와 readiness/prime marker는 존재하지만 forged marker는 없고,
  final state는 failed/supervisor-durablerunnererror exit 1, quarantined state는 unrelated
  sleeper identities를 가진 running revision 2다. runner source는 trainer identity
  publication 직후 loop 첫 publication을 즉시 한 번 더 수행한 뒤 heartbeat sleep에
  들어간다. fixture가 첫 running revision부터 prime해 이 두 publication과 경쟁한
  원인이다. embedded fake trainer만 actual state revision >=2를 관측한 뒤 actual snapshot과
  0.8초 prime/2초 injection deadline을 시작하도록 동기화한다. 제품은 변경하지 않고
  AST/targeted/static/diff 뒤 영향 gate와 final integration을 다시 실행한다. GPU/E2 금지다.
- `20260823-015458-p0-powershell-contract-quarantine-fix-intent`: fixture는 후반 fault
  전 original previous bytes와 existing quarantine name/size/SHA inventory를 보존하고,
  launcher rejection 직후 structurally-corrupt current exact bytes와 inventory 불변을
  확인한 뒤 current/previous를 모두 원복한다. resume 완료 후에도 inventory 불변만
  요구한다. 제품 코드는 unchanged다. AST error 0, required static 6/6, scoped diff-check
  exit 0, test 96,077 bytes SHA `8e3232307d688f72c7b76c69f2d62b36b97dc5b316b62754dde9bb033a90451b`,
  12-file manifest `002607b34aedbcedff92d3a2ba20a46aa34d49bfd057717130188764cad584b1`,
  관련 PID 0이다. exact fresh `-KeepFailedArtifacts` contract 한 번을 영향/최종 integration
  gate로 실행한다. exit 0/final PASS/PID 0이 아니면 보존 root를 진단하고 반복하지 않는다.
  Python PASS는 PowerShell test-only 변경으로 유지하며 GPU/E2는 금지다.
- `20260823-015349-corrupt-current-quarantine-fixture-fix-intent`: fresh integration은
  terminal-injection과 live pause/resume 후반까지 진행한 뒤 line 1820
  `Launcher rejection mutated the corrupt current run-state before explicit restoration`로
  exit 1; preserved root `airi-durability-contract-4e5aaf5957914b98a0dc38b205a76cba`,
  post-run 관련 PID 0, 로그 8개는 모두 0 bytes다. 보존 quarantine 단 한 개는
  `running` revision 7, malformed runner 1-field receipt로, 후반 launcher fault가 아니라
  앞선 active corrupt-current fault를 live runner가 의도대로 격리한 것이다. test는 이
  정상 기존 격리까지 count 0을 요구한 stale fixture였다. 제품을 변경하지 않고 기존
  quarantine name/size/SHA inventory와 original previous bytes를 저장한 뒤, 후반 launcher
  rejection 직후 corrupt current bytes와 inventory 불변, 명시 복원 뒤 정상 resume 후
  inventory 불변만 요구하도록 최소 수정한다. AST/targeted/static/diff receipt 뒤 영향
  gate와 final integration을 실행하며 GPU/E2는 금지 유지다.
- `20260823-015111-p0-powershell-contract-final-fix-intent`: JSON transport를 사용한
  actual terminal-injection targeted run은 RunDir와 unrelated-live/forged-complete
  marker를 모두 생성하고 final `complete/trainer-complete`, exit 0으로 수렴했다. 첫
  diagnostic wrapper는 완료 직후 잠시 열린 runner.lock 해시에서 exit 1이었으므로 PASS로
  쓰지 않지만, 종료 뒤 read-only 검증 15개 조건은 전부 true다: current/previous SHA와
  revision의 anchor exact 결속, forged gate 제거, 두 marker 존재, adapter/report 존재,
  runner/trainer/관련 PID 0. current/previous/anchor SHA는 각각 `0157dcfb...008fb`,
  `7b666a24...049a`, `ed785d3c...e2a10a`다. 현재 12-file input manifest는
  `6d3c31f65339491a1b95249fb59b72b37a7162f24b52325506b9361dd04c4441`,
  관련 PID 0이다. 정확히 한 번 fresh `powershell -NoProfile -ExecutionPolicy Bypass
  -File .\test-airi-training-durability.ps1 -KeepFailedArtifacts`를 영향/최종 PowerShell
  integration gate로 실행한다. exit 0, literal final PASS, post-run PID 0이 필요하며
  실패 시 새 root를 보존·진단하고 반복하지 않는다. GPU/E2는 계속 금지다.
- `20260823-014859-terminal-job-actual-gate-targeted-intent`: test-only JSON transport
  수정 뒤 AST error 0, job round-trip은 exact `System.String[]` count 36/first-last/exact
  JSON 모두 PASS, required static token 5/5 true, scoped diff-check exit 0이다. 첫 검증
  wrapper는 Git의 LF→CRLF warning을 terminating native stderr로 취급해 receipt 없이
  끝났고 원인을 고쳐 다시 수행한 위 receipt만 권위로 쓴다. test는 94,488 bytes,
  SHA `47e3f3027923a954f92d9f7ddf045fe4c063b2ff3afe26f4334c96bda9afdabd`다.
  다음은 별도 temp root와 exact live synthetic sleeper identities를 써 같은 JSON job의
  forged gate/marker/launcher receipt를 한 번 targeted 실행한다. 관련 PID를 exact
  회수하고 PASS 전 full contract는 실행하지 않는다. 제품/GPU/E2는 변경하지 않는다.
- `20260823-014734-terminal-job-argument-json-fix-intent`: exact binding probe는 parent
  trainer arguments 36개가 job의 `[object[]]` param에서 count 1,
  element type `System.Collections.ArrayList`로 도착하고 `[string]` 변환 시 모든 값을 한
  문자열로 합치는 것을 재현했다. 이것이 runner 필수 플래그 소실과 pre-RunDir exit의
  정확한 fixture 원인이다. 제품을 변경하지 않고 terminal-injection test 한 곳만
  argument array를 compressed JSON string으로 job에 전달하고, child에서 exact 36개
  string array로 복원한다. targeted binding/AST/static/scoped diff-check를 통과한 뒤에만
  영향 gate와 fresh full contract를 별도 intent로 실행한다. GPU/E2는 금지 유지다.
- `20260823-014656-terminal-job-argument-binding-diagnostic-intent`: launcher 자체
  deadline까지 회수한 targeted job은 outer diagnostic exit 0이나 child job
  state=`Failed`, exact reason/output
  `Durable runner terminal-injection-contract did not publish a verified run-state within 30 seconds; launch_shim_exited=True`다.
  01:46:00~01:46:31 timeline 내내 RunDir/state/gate 0, 별도 root에는 sentinel 8 bytes만,
  post-run 관련 PID 0이다. 따라서 test의 10초 readiness만 늘리는 것은 수리가 아니며
  `Start-Job -ArgumentList`를 건넌 trainer argument가 runner launch 전에 손상되는 fixture
  경계를 우선 의심한다. 같은 argument expression을 launcher 없이 job param으로만 받아
  실제 type/count/value를 한 번 출력한다. 제품/full contract/GPU/E2는 건드리지 않는다.
- `20260823-014512-terminal-job-launcher-timeout-diagnostic-intent`: 10초 sentinel
  진단은 job 본문 시작 sentinel을 즉시 썼지만 마지막까지 RunDir/state/gate 0,
  child error/output 0, 명시 Stop 뒤 관련 PID 0이었다. 별도 root에는 8-byte sentinel
  하나만 있다. 이는 test의 고정 10초 readiness gate가 fresh job 내부 launcher
  preflight보다 짧다는 가설을 지지하지만 원인 확정은 아니다. 같은 synthetic fixture를
  새 root에서 launcher 자체 30초 poll 종료까지 한 번 관측하고 job exit/output/error를
  회수한다. GPU/E2/제품 파일은 변경하지 않으며 이 receipt 전에는 fixture/full contract를
  수정·재실행하지 않는다.
- `20260823-014343-terminal-job-start-sentinel-diagnostic-intent`: 첫 targeted job
  진단은 30초 tool window에서 output/exit/session receipt 없이 끊겨 PASS나 원인 근거가
  아니다. 생성된 별도 root `airi-terminal-job-diagnostic-b30b...`는 file 0이며 이후
  관련 child PID 0이다. 동일 35초 명령을 반복하지 않고, job scriptblock 첫 줄에 별도
  synthetic sentinel을 쓰고 10초만 관측한 뒤 job을 명시 회수하는 더 짧은 진단으로
  `Start-Job` 자체 startup 대 launcher 진입을 분리한다. 제품·모델·GPU·서비스는 변경하지
  않으며 receipt 전 full contract를 재실행하지 않는다.
- `20260823-014129-terminal-injection-job-targeted-diagnostic-intent`: 보존 root의
  ordinary launcher fixture와 현재 launcher/test bytes를 사용하되 별도 system-temp
  RunDir를 만들어 terminal-injection `Start-Job` 호출만 한 번 재현한다. job이 Running인
  시각, RunDir/gate 생성, 종료 상태와 child output/error를 최대 35초 동안 회수하고 exact
  관련 PID가 남으면 identity 확인 후 해당 진단 tree만 종료한다. 출력은 console과
  synthetic temp뿐이며 제품·모델·GPU·서비스는 변경하지 않는다. 이 receipt 전에는
  fixture 수정이나 full contract 재실행을 하지 않는다.
- `20260823-014028-terminal-injection-job-failure-reconcile`: 세 번째 fresh exact
  PowerShell contract는 initial launcher와 competitor fault를 통과한 뒤 test line 1246
  `Launcher did not remain live through the forged-terminal readiness gate`로 exit 1했다.
  preserved root `airi-durability-contract-983f6da66a534db09f3415dfe19a0ce0`에는 ordinary
  `launcher-case/run with spaces`의 complete artifact/state/anchor가 있으나 기대한
  `terminal-injection-run`은 생성되지 않았고 `unrelated-live-prime.json`까지만 존재한다.
  따라서 현재 증거는 제품이 forged terminal을 승인했다는 재현이 아니라 background
  launcher job이 RunDir 생성 전 종료한 fixture/preflight 실패다. compact 뒤 지정 SSoT
  5종을 순서대로 전체 재독했고 Goal status=`active`, HEAD/local·remote origin/main
  `32830a4`, modified 16+untracked 1+staged 0, 관련 PID 0, source/chat/base/E1 SHA exact,
  E2 adapter/report absent를 다시 대조했다. 같은 full contract를 반복하지 않고 보존된
  fixture 입력으로 exact background job의 exit/output을 targeted 회수해 원인을 확정한다.
  GPU/E2는 계속 0/금지이며 운영 채택·기본 모델 변경 금지를 유지한다.

- `20260823-013354-p0-powershell-contract-third-intent`: competitor fault는 8초 live
  sleepers와 background pause job을 사용하고, job Running 관측 뒤 parent가 +1 revision/
  zero command hash current를 동기 게시하며 anchor는 그대로 둔다. child result를 회수한 뒤
  기존 exit/marker/error assertion을 적용한다. 제품 변경은 없다. root AST error 0,
  targeted job/static probe와 scoped diff-check PASS, test SHA
  `3f05d981c51fb636b3d2b09d39170e39c46564d0c498bdd6a90ac822575bd830`, 새 12-file
  manifest `63e225eb0c3badbbc04b405dccbd432eb24ef4dd3f21e251087cc61d182ca8d5`,
  관련 PID 0이다. exact `-KeepFailedArtifacts` contract 1회를 실행해 exit 0/literal PASS/
  PID 0을 요구하고 실패 시 새 root를 보존·진단한다.
- `20260823-013206-live-competitor-fixture-sync-intent`: preserved `2846...` root는
  변경하지 않고 별도 temp 복제본에서 same anchored paused-safe current/previous, exact
  live sleeper identities와 300ms 뒤 +1 revision/zero command hash 교체를 격리 재현했다.
  verified 재현 결과는 exit 1, exact SAFE marker false, exact error
  `An unanchored or terminal previous run-state cannot authorize power-off`; 결합 assertion의
  세 실패항은 모두 false다. 제품은 competitor를 정확히 거부한다. 첫 진단 copy 명령은
  literal wildcard로 empty copy를 만들어 anchor-schema exit 1이었고 진척으로 쓰지 않았다.
  두 진단의 exact sleeper는 identity 확인 뒤 종료했고 관련 PID 0이다. full suite의 실패는
  3초 pause와 별개 background mutator job의 Windows 시작 지연 경쟁이다. pause를 background
  job으로 시작하고 parent가 current를 동기 교체해 같은 rejection을 결정론적으로 관측하도록
  test-only sync를 최소 수정한다. 제품은 변경하지 않는다.
- `20260823-012935-live-competitor-fault-diagnostic-intent`: synthetic 관찰 창 수정 뒤
  fresh contract는 initial launcher를 통과했지만 15.6초에 test line 719
  `A live higher-revision competitor bypassed anchor authority`로 exit 1했다. preserved root
  `airi-durability-contract-2846...`, related PID 0이며 새 model/GPU/service 출력은 없다.
  이 결합 assertion은 child exit, exact marker, expected error 세 조건 중 어느 것이
  실패했는지 남기지 않았다. preserved root는 그대로 두고 별도 system-temp 복제본에서
  같은 anchored paused-safe current/previous와 live runner/trainer, 300ms 뒤 +1 revision/
  command-hash competitor 교체만 재현해 exit/marker/error를 회수한다. 실패 원인을 확정하기
  전에는 test/product를 수정하거나 full contract를 반복하지 않는다.
- `20260823-012751-p0-powershell-contract-second-retry-intent`: ordinary fake trainer의
  명시 관찰 창만 0.5초→2.0초로 늘려 launcher의 500ms poll/CIM provenance를 여러 번
  허용했다. 제품·다른 fixture 계약은 변경하지 않았다. AST error 0, targeted static true,
  scoped diff-check exit 0, test SHA `d8501b46d3f8d24d3a71f7b4d9dc1472db203c2c6f76b6bcadeddca89ac8f5ff`다.
  새 12-file manifest `d81d781a3ec852e9767094f9bfe532547520a761270f71e804a47eaffc0bba07`,
  관련 PID 0에서 exact `-KeepFailedArtifacts` contract 1회를 실행한다. exit 0/literal PASS/
  PID 0을 요구하고 실패 시 새 receipt를 보존·진단한다.
- `20260823-012708-p0-launch-observation-fixture-fix-intent`: anchor fixture 이관 뒤 fresh
  actual-process contract는 약 43초 후 exit 1, preserved root `airi-durability-contract-
  c0d477...`, failure receipt SHA `dd153701...b4703`다. 첫 `launcher-contract`가
  verified run-state를 30초 안에 수용하지 못했고 `launch_shim_exited=False`였다. post-run
  관련 PID 0이다. 보존 terminal은 complete/trainer-complete exit 0, current revision 3와
  previous revision 2가 anchor SHA/revision에 exact 일치하고 adapter/report/final evidence가
  존재한다. 같은 RunDir의 pause gateway 단독 검증은 exit 0/`SAFE_TO_POWER_OFF`다. 따라서
  terminal/anchor 제품 검증 실패가 아니라 launcher가 live observed runner+trainer를 얻기
  전 synthetic ordinary trainer가 terminal로 전환한 fixture 경쟁이다. 실제 trainer 생성부터
  terminal까지 1,452.17ms이고 fake trainer의 명시 sleep은 500ms뿐이다. ordinary fake의
  관찰 창만 최소 2초로 늘려 여러 500ms poll/CIM provenance 기회를 보장한다. 제품 검증은
  변경하지 않으며 AST/static/diff receipt 전에는 full contract를 재실행하지 않는다.
- `20260823-012315-p0-powershell-contract-retry-intent`: 제품 변경 없이
  `test-airi-training-durability.ps1`만 최신 canonical anchor current/previous fixture,
  rollback/live higher-revision competitor rejection과 비동기 forged-terminal gate 관찰로
  최소 이관했다. root가 canonical key/quote와 `TrainerArguments` 배열 결속을 재검토했고
  AST error 0, dynamic canonical/array/static probe와 scoped diff-check가 PASS했다. test SHA는
  `7493d7f040c952a95742e9a9fd54e86ba3c7366e0d0065e614ff647756900450`, 새 12-file manifest는
  `a2039e618dbd92d6e00eb788ea41a26a30958715c47222dc2b8aa9651e48b91a`, 관련 PID 0이다.
  작업자 probe temp root 1개/합성 JSON 3개는 cleanup 명령이 환경 정책에 의해 실행 전
  거부돼 Git 밖에 남았고 우회 삭제하지 않는다. exact full contract 1회를 실행해 exit 0,
  literal PASS, post-run PID 0을 요구하며 실패 시 새 root를 보존·진단한다.
- `20260823-011636-p0-powershell-source-contract-failure`: 허가된 exact PowerShell
  contract는 child/runtime root 생성 전에 test line 58의 source-contract preflight에서
  `Safe-pause contract token is missing: previous terminal run-state cannot authorize
  power-off`로 nonzero(exit 1) 종료했다. post-run related PID 0이며 새 synthetic root는
  없고 마지막 보존 root는 계속 `ff7cec...`다. 제품 pause는 최신 anchor 계약 문구
  `An unanchored or terminal previous run-state cannot authorize power-off`를 사용하지만
  fixture는 구 문구와 anchor 없는 `Write-ContractTerminalPredecessor`를 유지한다. 제품을
  약화하지 않고 test fixture만 exact anchor current/previous 계약과 frozen rollback/
  authorized/competitor fault에 최소 이관한다. AST/targeted 회귀 뒤 별도 intent 전에는
  full contract를 재실행하지 않으며 GPU/E2는 닫혀 있다.
- `20260823-011516-p0-powershell-contract-intent`: 핀된 Python pycompile 5개와 네 P0
  suite는 exit 0, `139 passed, 5 skipped in 33.12s`; post-run related PID 0이다.
  PowerShell까지 포함한 exact 12-file path+size+SHA manifest는
  `0fd3c06ca51db80a99e8c50796ac98b9445fd99babab22812e28e0c579be5570`다. 다음 단일
  명령은 `powershell -NoProfile -ExecutionPolicy Bypass -File
  .\test-airi-training-durability.ps1 -KeepFailedArtifacts`이며 출력은 console과 synthetic
  system-temp root뿐이다. exit 0, literal `AIRI training durability contract: PASS`,
  post-run related PID 0을 모두 요구한다. 실패 root는 보존·진단하고 동일 명령을 원인 없이
  반복하지 않으며 독립 감사/GPU/E2를 열지 않는다.
- `20260823-011354-p0-python-integration-intent`: resume 후 첫 continuity gate는 exit 0,
  `AIRI work-continuity contract: PASS`이며 관련 PID 0이다. 핀된 interpreter는
  `D:\AIRI-Models\venv-midm-broadcast-qlora-py312\Scripts\python.exe`, Python 3.12.13이다.
  pycompile 5개와 checkpoint/trainer/runner/verifier 네 suite의 exact 9-file
  path+size+SHA manifest는 `e9d180d9be9786b8702b73401995489e46b67c960a1c7aaeaea7fffed5ed3a84`다.
  한 순차 명령으로 py_compile 뒤 네 suite를 각 1회 실행한다. 출력은 console과 pytest
  임시 파일뿐이며 완료 조건은 전체 exit 0, 정확한 PASS count, post-run related PID 0이다.
  실패 시 PowerShell contract/GPU/E2를 실행하지 않고 같은 원인을 중복 재시도하지 않는다.
- `20260823-011214-goal-resume-reconciliation-receipt`: 최신 사용자 `/goal`로 Goal 도구
  status=`active`를 생성·확인했다. local HEAD, local origin/main, remote
  `refs/heads/main`은 모두 `32830a43556ba7704a39bd9094f128a5a98dd7d7`이며 actual
  worktree는 handoff exact 목록의 modified 16+untracked 1+staged 0이다. 관련
  durable runner/trainer/검증 PowerShell PID는 0이고 NVIDIA compute 목록에 식별 가능한
  AIRI workload는 0이다. 보존 실패 root `airi-durability-contract-ff7cec...`가 존재하며
  관련 run-state/anchor/log의 크기·SHA를 read-only로 회수했고 로그 본문은 읽지 않았다.
  source/chat/base/E1 3종은 고정 크기·SHA와 exact 일치한다. E2 adapter/report, T3,
  campaign은 absent이고 기존 E2 stdout/stderr는 각 0 bytes/SHA-256 `e3b0c442...b855`다.
  문서의 pause 상태만 최신 명령과 달랐으므로 이 checkpoint와 roadmap log를 관측 사실로
  먼저 정정한다. 다음 exact 동작은 resume 후 첫 continuity gate 1회이며, PASS 전에는
  Python/PowerShell P0 통합·GPU·E2·stage/commit/push를 시작하지 않는다.
- `20260823-010417-paused-user-session-handoff-receipt`: 허용된 focused continuity
  문서 검사는 exit 1, `Work-continuity contract missing: recognized goal status`였다.
  검사기가 새 `paused-user-session-handoff` 상태를 인식하지 못한 것이며 pause 문서를
  active로 되돌리거나 검사기를 수정·재실행하지 않는다. 같은 실행의 현재 tracked
  16파일 scoped `git diff --check`는 exit 0이다. 관련 PID는 계속 0이고 새 산출물·
  checkpoint·모델 변경은 없다. 따라서 이 배치는 P0 통합 PASS가 아니라 로컬
  미검증·미커밋 handoff이며, continuity 결과도 PASS가 아닌 명시적 failure receipt다.
- `20260823-010007-paused-user-session-handoff-intent`: 최신 사용자 명령이 active AIRI
  goal을 `paused-user-session-handoff`로 전환했다. Goal 도구 실제 status=`paused`;
  complete/cancel이 아니다. HEAD=origin/main
  `32830a43556ba7704a39bd9094f128a5a98dd7d7`, 인계 문서 반영 후 예상 worktree는
  tracked modified 16, untracked 1, staged 0이다. AIRI 관련 Python/PowerShell PID와
  durable GPU trainer는 0이므로 `pause-airi-safely.ps1`은 실행하지 않는다. source/chat/
  base/E1 SHA·크기는 고정값과 exact 일치하고 E2 adapter/report, T3, campaign은 없다.
  마지막 권위 PASS는 최신 Python bytes의 `139 passed, 5 skipped in 51.53s`; 마지막
  actual-process PowerShell contract는 exit 1(line 1160)이며 보존 root
  `airi-durability-contract-ff7cec...`가 남아 있다. 그 뒤 pause anchor static receipt만
  있고 full integration은 없으며, 중단된 최신 Python 독립 감사와 launcher/test 후속은
  `no-authoritative-receipt`다. 이 로컬 배치를 stage/commit/push하지 않는다. 인계 검증
  intent는 exact command
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\test-airi-work-continuity.ps1`
  1회와 현재 16 modified+1 untracked 파일에 대한 scoped `git diff --check`다. 새 산출물은
  없고, exit 0/PASS와 post-check PID 0을 receipt로 요구하며 실패해도 재실행하지 않는다.
- `20260823-005241-powershell-anchor-binding-p0-p1-intent`: independent latest-byte
  anchor-boundary audit is `NOT READY`, P0=1/P1=1. P0: pause reads internally valid current/
  previous terminal receipts without authenticating their exact bytes/revisions to
  `run-state.anchor.json`, so a concurrent valid rollback pair can authorize old artifacts and
  exited identities and emit `SAFE_TO_POWER_OFF` while the real run remains active. P1: launcher
  existing/polling paths likewise accept an unanchored competitor current; it can return false
  already-running or poison `baselineRevision` and force timeout before Python quarantine.
  Bind both tools to an exact no-follow anchor snapshot: current must match `anchor.current`,
  terminal predecessor must match `anchor.previous`; an uncommitted current may fall back only to
  a nonterminal previous matching `anchor.current`. Malformed/missing anchors with receipts fail
  closed. Add rollback pair, authorized complete pair and live +1000 competitor faults. Root also
  found the current forged-gate check remains timing-sensitive because runner may publish trainer
  identity before the child executes its first instruction; make the launcher invocation
  asynchronous and prove it stays running after the forged marker/gate is actually observed.
  No full contract retry/GPU/E2 until implementation/static receipt and a new intent.
- `20260823-005007-launcher-trainer-bound-static-receipt`: launcher nonterminal return
  now uses a distinct `$trustedTrainerState` that is true only after the present trainer is
  exact-live, retains stable identity and passes child-of-observed-runner provenance. Runner-only
  `starting` remains preliminary and cannot return; terminal verification/bindings/deadline are
  unchanged. The contract source tokens and failure message explicitly bind this gate. Root AST
  parse error count 0, targeted static probe true, scoped diff-check exit 0, related PID 0;
  launcher/test SHA `3a5b2738...9fb5a5`/`016ced39...8f991`. Await the independent anchor-boundary
  review before authorizing one fresh full contract, avoiding a run on a known trust-boundary gap.
  GPU/E2 remain forbidden.
- `20260823-004723-launcher-trainer-bound-receipt-p0-intent`: preserved evidence shows
  the injected run later reached verified complete exit 0 and the new anchor quarantined both
  forged current generations; current/anchor are consistent and related PID 0. The contract
  failed earlier because launcher polling accepts `$trustedLiveState` when only the exact runner
  is proven and `state.trainer` is still null. It returned the initial `starting` receipt before
  fake trainer created the gate; the gate then appeared before the caller's assertion. This is a
  real launch-receipt readiness gap plus a timing-sensitive fault, not model/repository damage.
  Require nonterminal success to include an observed exact trainer whose live parent is the
  observed runner, while retaining terminal receipt rules; make the fault assertion prove this
  trainer-bound contract. Owned inputs launcher/test SHA `5ac72b46...ea05a4a`/
  `ff0d4e51...fafad7`. Run AST/static/scoped diff only first; root alone authorizes a fresh full
  contract after a receipt. GPU/E2 remain forbidden.
- `20260823-004552-terminal-injection-window-contract-failure`: the authorized root
  PowerShell contract exited 1 in 22.92s at test line 1160 and did not emit the final PASS.
  Preserved root is `airi-durability-contract-ff7cec1da47a4ea5a3624971031aab9b`;
  post-run related runner/trainer/pytest/contract PID count is 0. The exact failure is
  `Launcher returned during the unrelated-process prime or forged terminal window`, after the
  fixture observed `forged-complete-live.gate`. Do not classify this as repository/model damage
  or P0 progress, and do not retry the full contract. Inspect only the preserved terminal-
  injection run's state/anchor/gates/output sizes plus launcher/runner cutpoints to determine
  product early-return versus fixture ordering. GPU/E2 remain forbidden.
- `20260823-004446-root-powershell-contract-intent`: root pinned pycompile plus all four
  P0 Python suites exited 0 with `139 passed, 5 skipped in 51.53s`; post-run related PID 0
  and scoped diff-check exit 0. The exact current twelve-file Python/PowerShell input manifest
  is `20e45732cef06b7a84217184288eb52c89f2077d6124d48d5aec0109a63d43fe`.
  Root now runs exactly one fresh `powershell -NoProfile -ExecutionPolicy Bypass -File
  .\test-airi-training-durability.ps1 -KeepFailedArtifacts`. Outputs are console plus a
  synthetic system-temp root, cleaned on success and retained on failure. Completion requires
  exit 0, literal final `AIRI training durability contract: PASS` and post-run related PID 0;
  any failure is preserved and diagnosed before another retry. GPU/E2 remain forbidden.
- `20260823-004306-root-python-integration-intent`: related durability Python/PowerShell
  PID 0 after compact reconciliation. Root now runs pinned Python py_compile for checkpoint/
  trainer/runner/verifier/input-manifest builder, then the four checkpoint/trainer/runner/
  verifier suites in one sequential process. Exact nine-file path+SHA manifest is
  `7be9afb6f950b7721b82b7432cb0771dcbc1232e634817a03abb3a2697d14433`; console and
  pytest temporary files are the only outputs. Completion requires exit 0, exact pytest PASS
  counts and post-run related PID 0. Failure is recorded without PowerShell retry/GPU/E2 and
  diagnosed on the same bytes.
- `20260823-004148-post-compact-runstate-recovery-worker-receipt`: compact 직후 지정
  SSoT 5종을 순서대로 전체 재독하고 goal `active`, HEAD=origin/main `32830a4`, actual
  worktree 13 modified+1 untracked/staged 0, AIRI trainer/runner/pytest/contract PID 0을
  대조했다. v4 source/chat, 4.61 GB base, E1 adapter/config/report는 크기·SHA가 모두
  고정값과 exact 일치하고 E2 adapter/report와 T3 output은 absent, 기존 E2 stdout/stderr는
  각 0 bytes다. 따라서 저장소·모델 손상 증거는 없다. delegated runner 수정은 anchor를
  먼저 strict snapshot해 anchor.current와 exact 일치하는 current만 회전하고, corrupt/
  unanchored/valid-looking competitor current와 unbound previous를 삭제하지 않고 no-follow
  quarantine하도록 구현했다. current-before-anchor 전원차단도 authenticated previous로만
  복구한다. 담당 receipt는 pinned pycompile PASS, runner focused `48 passed, 2 skipped in
  26.03s`, scoped diff-check PASS; runner/test SHA `3091bfe4...5315596`/
  `254670ad...6c5ce`다. 이는 worker receipt이며 root diff 검토와 fresh 통합 Python/
  PowerShell receipt 전에는 P0 완료·GPU/E2 진척으로 승격하지 않는다.
- `20260823-003710-live-corrupt-current-rotation-p0-intent`: root contract exceeded the
  initial 30s window, was retained as exec session `52396`, then exited 1 near live auto-pause;
  preserved root `airi-durability-contract-d5db34d385a941f8be053a77b92d40e9` and related PID
  0 after the synthetic tree's natural exit. Seven-field helper schema and second-run safe pause
  passed. The first live run becomes `failed/supervisor-durablerunnererror` immediately after the
  fixture replaces current state and copies it over previous. Code trace identifies the P0:
  `_write_state` rotates the now-corrupt current into `.prev`, publishes a valid new current,
  then fails while parsing the corrupt predecessor to build the anchor and stops the trainer.
  Implement anchor-authorized live publication recovery: verify current/previous against the
  existing anchor before rotation; quarantine untrusted receipts without deleting them; preserve
  only authenticated predecessor, publish current+anchor consistently, and reject valid-looking
  competitor lineage. Add current-corrupt/previous-corrupt/competitor/power-cut faults in runner
  tests. No PowerShell/full retry/GPU/E2 until focused PASS and a new intent.
- `20260823-003052-helper-schema-fix-root-contract-intent`: launcher now resolves the
  trainer's sibling checkpoint helper, hashes input manifest/trainer/helper/runner through its
  native no-follow snapshot, and requires/binds helper SHA in existing/live state. Pause exact
  inputs require the same 64-hex field; manual paused fixture includes it while intentionally
  malformed spoof/orphan states remain invalid. Product/test AST, scoped diff-check and static
  helper probe PASS; launcher/pause/test SHAs `5ac72b46...ea05a4a`/
  `83b778f0...a9b042d`/`ff0d4e51...fafad7`, related PID 0. Root authorizes one fresh exact
  actual-process contract; exit 0/final PASS/PID 0 is mandatory. Full offline/stage/commit/GPU/E2
  remain gated.
- `20260823-002613-helper-input-schema-p0-fix-intent`: root contract ran about 42s and
  exited 1 after reaching live-pause integration; preserved root
  `airi-durability-contract-15e815d8b2284bc2a557e61a93801fe2`. The synthetic runner/trainer
  tree was briefly visible at receipt collection and then exited naturally; fresh related PID
  recount is 0. Exact current run-state inputs are the prior six fields plus
  `checkpoint_helper_source_sha256`; pause `Assert-VerifiedCheckpoint` and launcher's
  already-running schema still require only the old six, causing `run-state inputs property set
  is invalid`. This is a real v2 cross-product schema P0. Add the helper pin to both exact schemas,
  compute it from the sibling helper through the existing native no-follow launcher snapshot,
  compare it in live/existing launch bindings, validate it as 64-hex in pause, and migrate the
  manual paused fixture. Static tests precede a new contract intent; GPU/E2 remain gated.
- `20260823-002314-disappeared-report-fix-root-contract-intent`: disappeared-report fault
  now independently requires nonzero child exit, no exact safety marker, and the stable
  `completed file artifact` rejection class; product native no-follow verification is unchanged.
  AST/scoped diff-check PASS, test SHA `9b93b81e...b20d0618`, related PID 0. Root authorizes
  one fresh exact actual-process contract; exit 0/final PASS/PID 0 is mandatory and any failure
  is preserved/diagnosed before retry. Full offline/stage/commit/GPU/E2 remain gated.
- `20260823-002206-disappeared-report-fixture-message-failure`: root contract exited 1 in
  23.48s at test line 1104; preserved root
  `airi-durability-contract-030b61547dc244bf91edd69c8328bef6`, related PID 0. The completed
  report is absent as injected. One isolated child check proves product exit 1/no marker with
  `completed file artifact cannot be read through a no-follow authority handle` and native
  `CreateFileW` missing-file code 2. Product therefore correctly rejects the disappeared report;
  the fixture falsely required the missing-receipt message even though the receipt exists and its
  target disappeared. Change the fault gate to require nonzero, no exact marker and a completed
  file-artifact validation error, with independent diagnostics. No product weakening or full
  retry is authorized before AST/diff-check and a new intent.
- `20260823-002114-directory-artifact-fix-root-contract-intent`: pause artifact verifier
  now validates either exact file/directory receipt schema, derives `$path` once from the receipt
  before both branches, and preserves native file snapshots, reparse and closed inventory checks.
  Contract adds a caller-scope decoy while child PowerShell verifies a completed directory
  adapter; deadline-fault diagnostics now report exit/marker/deadline booleans independently.
  Product/test AST and scoped diff-check PASS; pause SHA `9c64edaa...e44c0ab`, test SHA
  `cd29fc8e...b527cfa`, related PID 0. Root authorizes one fresh exact actual-process contract;
  exit 0/literal final PASS/PID 0 is required, otherwise preserve/diagnose before retry. Full
  offline/stage/commit/GPU/E2 remain gated.
- `20260823-001930-directory-artifact-path-p0-fix-intent`: one isolated preserved-run
  diagnostic returned exit 1 with no marker; exact first line is
  `Assert-VerifiedArtifactReceipt: variable '$path' ... not set` at pause line 1124. The full
  contract's combined assertion message had conflated this missing expected deadline text with
  marker emission. Product inspection confirms `Assert-VerifiedArtifactReceipt` assigns `$path`
  only inside the file-artifact branch, then uses it uninitialized for directory adapters under
  StrictMode. This is a real completed-adapter verification P0 availability defect. Move the
  canonical receipt path assignment before the kind split, keep native snapshot/reparse/inventory
  checks unchanged, and add a no-ambient-path directory-artifact fault assertion. AST/static
  checks precede a new contract intent; no retry/GPU/E2 is currently authorized.
- `20260823-001839-exact-marker-still-fails-diagnostic-intent`: fresh root contract again
  exited 1 in 19.70s at the final-completion deadline fault, preserved root
  `airi-durability-contract-924fb64abbea495fa886de34538b5d7f`, related PID 0. Unlike the
  earlier v1 failure, the launcher run/output/report now exist, so v2 launch is integrated.
  Exact-line parsing still observed a marker; do not assume another fixture false positive.
  No full retry is authorized. Run only the preserved completed synthetic RunDir through the
  1-second/1.5-second test hook once, capture child exit and output as line-delimited diagnostic
  evidence, and determine whether product emits a status object plus literal marker before its
  deadline error. No model/GPU/service/E2 output is involved.
- `20260823-001745-exact-safe-marker-root-contract-intent`: test subprocess gates now
  recognize only an exact standalone `SAFE_TO_POWER_OFF` LF/CRLF line. Deterministic assertions
  prove the deadline error token is not a marker and a multiline exact marker is accepted;
  all prior negative substring checks were migrated while direct output-array success checks
  remain exact. AST/scoped diff-check PASS, test SHA
  `8aa629f67372a85b85fd9ffda3ed212e3c2f5fc352db9961a456c98aaaf99500`, related PID 0.
  Root authorizes one fresh exact `-KeepFailedArtifacts` actual-process contract. Exit 0,
  literal final PASS and post-run PID 0 are required; failure remains a receipt and blocks
  retries until diagnosed. Full offline/stage/commit/GPU/E2 remain gated.
- `20260823-001617-safe-marker-substring-fixture-failure`: root fresh PowerShell contract
  exited 1 in 19.75s at test line 1065; preserved root
  `airi-durability-contract-c968bc25e3244d6a96b9c66e21f33890`, related PID 0. The v2
  initial launcher succeeded and reached the intended final-deadline fault. Static source proves
  product pause checks deadline after the injected 1.5-second delay and throws
  `deadline expired before SAFE_TO_POWER_OFF emission`. The test used substring regex
  `-match 'SAFE_TO_POWER_OFF'`, so it mistook that expected error text for a literal standalone
  safety marker. This is a fixture false positive, not an emitted marker/P0 product failure.
  Replace all subprocess negative checks with exact-line marker recognition and add a direct
  error-text-vs-marker assertion; AST/diff-check precede a separately recorded fresh retry.
  Full offline/stage/commit/GPU/E2 remain gated.
- `20260823-001459-powershell-v2-fixture-root-contract-intent`: PowerShell synthetic
  input builder and both initial/live-pause sites now emit canonical manifest v2 with actual
  dataset/model.safetensors/trainer/sibling-helper SHA and deterministic full model inventory;
  every launcher argument uses the same actual fixture hashes. No v1 input-manifest literal
  remains. AST/static source probe and scoped diff-check PASS, test SHA
  `2a14abfafcbcd29a163fdbf9000e24346d8a079c71ff1c620c14632739692162`, related PID 0.
  Root now runs exactly one fresh
  `powershell -NoProfile -ExecutionPolicy Bypass -File
  .\test-airi-training-durability.ps1 -KeepFailedArtifacts`, retaining the exec session if it
  exceeds the initial tool window. Completion requires exit 0, literal contract PASS and
  post-run related PID 0. Failure preserves the new root/atomic redacted receipt and prohibits
  retry until diagnosed. Full offline/stage/commit/GPU/E2 remain gated.
- `20260823-000936-powershell-v1-fixture-cause-fix-intent`: the single diagnostic retry
  failed with a valid redacted receipt: stage `initial-launch`, `RuntimeException`, launcher
  line 768 timeout, `launch_shim_exited=True`; preserved root
  `airi-durability-contract-95f481b542a94517adf3d33ec8487d24`, post-run related PID 0.
  No RunDir/log/state was created. Static source comparison found the exact integration cause:
  PowerShell `New-ContractInputManifest` still emits deprecated
  `airi.behavior-input-manifest.v1`, while the final Python runner now accepts mandatory v2 only.
  The same helper is used by both initial-launch and live-pause fixtures. Next repository-only
  fix migrates both to canonical v2 with actual dataset/model bytes SHA, checkpoint-helper SHA
  and the exact closed model inventory; product trust rules remain unchanged. AST/focused static
  checks precede any new contract intent. Full offline/stage/commit/GPU/E2 remain gated.
- `20260823-000550-initial-launch-failure-receipt-retry-intent`: preserved-root/source
  diagnosis placed the first unobserved action at the initial launcher invocation; the prior
  tool window retained no exception receipt, so code-vs-fixture cause was unrecoverable.
  Test-only `Write-InitialLaunchFailureReceipt` now atomically publishes a redacted
  `contract-failure-receipt.json` with stage/time/exception type/message before rethrow; product
  files were unchanged by this observability edit. AST parse/scoped diff-check PASS, test SHA
  `484794d3f52c2786fc729f035ffe80312157a2dd23a2b2d6a8cf774048f79f6a`, related PID 0.
  One diagnostic retry of the same exact `-KeepFailedArtifacts` contract is authorized. Exit 0/
  literal PASS/PID 0 is success; any failure must preserve/read the new receipt and prohibits
  another retry until the exact cause is fixed. Full offline/stage/commit/GPU/E2 remain gated.
- `20260823-000316-powershell-contract-no-receipt-failure`: authorized single
  `powershell -NoProfile -ExecutionPolicy Bypass -File
  .\test-airi-training-durability.ps1 -KeepFailedArtifacts` did not return an exit/PASS
  receipt through the 30-second tool window and is therefore a failure, not progress. Related
  test/runner/trainer PID recount is 0. Preserved system-temp root is
  `airi-durability-contract-b0f79a3978864d6e9006dfd15f8c5a1b`; top-level synthetic run,
  spoof and launcher fixture entries exist, while the expected first launcher run subdirectory
  was not observed. No retry is authorized until source/retained-artifact read-only diagnosis
  identifies the exact failing line and code-vs-fixture cause. Full offline/stage/commit/GPU/E2
  remain gated.
- `20260823-000118-runner-input-lifecycle-pass-powershell-intent`: runner는 input manifest
  v2-only로 이관됐고 final validation 직후부터 child exit까지 dataset과 closed model
  inventory의 native Windows share-read-only/no-follow handles를 유지한다. held descriptor와
  path identity/hash를 spawn 전·exit 후 재대조하고 partial-open cleanup, POSIX swap,
  Windows write/delete/replace 거부, junction, final mutation terminal failure/no output
  promotion 회귀를 추가했다. 핀된 pycompile PASS, runner focused
  `43 passed, 2 skipped in 24.58s`, scoped diff-check PASS이며 관련 PID 0이다. 다음 exact
  장기 명령은 `powershell -NoProfile -ExecutionPolicy Bypass -File
  .\test-airi-training-durability.ps1 -KeepFailedArtifacts`; current repository bytes와
  synthetic system-temp root/console receipt만 사용한다. 완료 조건은 exit 0, literal
  `AIRI training durability contract: PASS`, 모든 관련 PID 0이다. 실패 시 보존 root를
  진단하고 중복 재시도하지 않으며 full offline/stage/commit/GPU/E2 gate를 닫아 둔다.
- `20260822-235402-post-compact-integrity-reconcile`: compact 직후 지정 SSoT 5종을
  순서대로 전체 재독하고 goal `active`, HEAD=origin/main `32830a4`, actual worktree
  13 modified+1 untracked/staged 0, AIRI trainer/runner/pytest PID 0을 대조했다. 문서의
  12 modified보다 1개 늘어난 것은 진행 중 checkpoint helper의 native Windows snapshot
  수정이며 저장소 손상이나 이력 유실로 보이는 증거는 없다. v4 source/chat, 4.61 GB base,
  E1 adapter/config/report는 크기·SHA가 모두 고정값과 exact 일치한다. E2 adapter/report와
  T3 output은 absent이고 기존 E2 stdout/stderr는 각 0 bytes다. Checkpoint helper는
  `CreateFileW` share-read-only/no-follow snapshot focused `12 passed`이나 runner의
  parent-held dataset/full model inventory lifetime은 아직 P0 잔여다. PowerShell v2/final-cut
  담당도 실행 중이다. 두 잔여의 통합 PASS와 독립 P0/P1 0 전에는 full offline/stage/
  commit/GPU/E2로 이동하지 않는다.
- `20260822-234506-p0-v2-schema-powershell-followups`: producer는 Windows
  `CreateFileW` read-only sharing, all-regular closed model inventory/no-follow walk,
  replacement/delete와 partial-open handle leak 회귀까지 focused `74 passed, 3 skipped`를
  통과했다. 이어 mandatory non-circular event v2에 helper-measured publish timing,
  active cumulative monotonic elapsed와 predecessor event/index commitments를 추가했다.
  checkpoint 단독은 11/11 PASS지만 optional event 제거로 durable runner fixture 17건이
  명시 event 없이 실패해 전체 receipt는 아직 없다; fixture 이관을 계속한다. Verifier는
  non-circular v2, expected progress/output/final roots와 monotonic interval 결속으로 focused
  `51 passed, 1 skipped`였으나 predecessor index exact parse 보강을 추가 진행 중이다.
  최신 PowerShell 독립 감사 판정은 `NOT READY`, P0=4/P1=3: delay 뒤 final evidence cut
  재검증 부재, self-reported forged paused terminal, v2 index/event 무시, path-based TOCTOU,
  final-root terminal/recovered-complete/v1 fixture 호환성이다. 담당 follow-up이 fault 회귀와
  함께 수리 중이며 GPU/E2/full offline/stage/commit은 계속 금지한다.
- `20260822-233036-goal-resume-producer-followup-receipt`: goal status `active`,
  HEAD=origin/main `32830a4`, actual worktree 12 modified+1 untracked/staged 0,
  AIRI trainer/runner/pytest PID 0을 재대조했다. v4 source/chat, base weight와 E1
  adapter/config/report SHA는 고정값과 exact 일치하고 E2 adapter/report 및 T3 output은
  absent, 기존 E2 logs는 각 0 bytes다. producer follow-up은 pinned focused pytest
  `72 passed, 1 skipped in 27.07s`, scoped diff-check clean으로 종료했다. Held loader input
  snapshot, cumulative monotonic progress와 runner final evidence-root binding은 추가됐지만,
  Windows에서 명시적인 native share-read-only lock이 아니며 runner resume index parser도
  legacy v1-only다. 두 결함과 verifier 최신 audit 잔여를 fault 회귀로 닫기 전에는
  full offline/stage/commit/GPU/E2를 금지한다.
- `20260822-232333-p0b-producer-v2-manifest-anchor-partial`: pinned producer focused pytest
  exited `72 passed, 1 skipped in 26.37s`, related PID 0, scoped diff-check clean. Input
  manifest v2 now pins helper SHA and closed model inventory; runner validates it, snapshots
  trainer/helper, and run-state anchor v1 authorizes only SHA/revision/run-id-bound nonterminal
  predecessor recovery. Trainer uses only transactional event v2 publication. Still partial:
  no-follow model handles are not yet held across actual transformers loaders and runner terminal
  state does not yet verify/bind producer evidence root + completed progress. A second follow-up
  owns exactly those remaining gaps and faults; verifier/GPU/E2 remain gated.
- `20260822-232035-p0b-producer-followup-test-running`: the producer follow-up focused suite
  is active (pytest PIDs 12172/14320 under PowerShell 10948, synthetic runner PIDs 21676/26976
  at observation). These are CPU/test fixtures, not GPU/E2. It is exercising manifest/source/
  model-lock/lineage follow-up changes; do not start another durability or Python suite until
  an exit receipt and related-PID recount are recorded.
- `20260822-231748-p0b-producer-v2-partial-receipt`: producer focused pinned pytest exited
  with `72 passed, 1 skipped in 26.90s`, post-run related PID 0, assigned-file diff-check
  clean. Implemented checkpoint index/event v2 event-before-index chain, cumulative
  `training_elapsed_ns`, initial producer evidence root, and run-local trainer/helper snapshots.
  This is partial and not a gate PASS: canonical input manifest still lacks helper/closed model
  inventory, dataset/model handles are not held across loader reopen, run-state predecessor has
  no authenticated anchor recovery, final evidence root is not yet bound into terminal
  run-state/completed progress, and some authoritative checkpoint/trainer reads still reopen
  paths. Producer follow-up owns these gaps and replacement/power-cut faults. Verifier waits for
  the final schema; GPU/E2/full offline/commit remain gated.
- `20260822-231307-p0b-producer-focused-test-running`: pause/launcher now implements
  launch-PID ancestry + trainer-parent provenance, requested binding before observation,
  post-verification/immediate-pre-marker deadline checks, and unrelated-process priming,
  report disappearance, concurrent terminal revision/identity, plus complete/paused-safe
  deadline-overrun faults. The delay hook defaults off and is accepted only with
  `AIRI_DURABILITY_TEST_HOOKS=1`; parse/diff-check pass, but no full contract is claimed while
  producer code is changing. Producer focused pytest is currently active (pytest PIDs
  13000/2892 under PowerShell 3636 at observation); these are test processes, not GPU/E2.
  Do not start another durability test until its receipt and PID recount.
- `20260822-231143-p0b-producer-redesign-intent`: repository-only producer redesign is
  delegated over checkpoint/trainer/runner/input-manifest code and focused tests; no GPU,
  services, models, logs or D: outputs are authorized. Exact intended schema is event-before-
  index authority with index-rooted event hash chain, cumulative monotonic elapsed, exact
  payload/event/progress/output evidence commitment, Windows no-follow locked inputs,
  byte-exact run-local trainer/helper snapshots, and authenticated current/previous run-state
  lineage. Completion requires deterministic power-cut/competitor/reparse/replacement/progress/
  lineage faults and pinned focused Python PASS. Verifier work waits for these real producer
  fields; pause/launcher final test hook remains separate. GPU/E2 and commit/push remain gated.
- `20260822-230718-p0b-python-reaudit-not-ready`: independent latest-byte Python audit is
  `NOT READY`, P0=7/P1=3; no tests/processes were run. P0: injectable verifier loaders can
  forge PASS; rotated event JSON is self-authenticating without retained chain; <=600-second
  intervals use adjustable inter-event wall time; expected progress is not bound to payload,
  event and report counters; actual current index bytes are not exactly bound to final event;
  hashed trainer/model/dataset paths can be replaced before execution/reopen and helper source
  is unpinned; directly invoked checkpoint/trainer code lacks Windows final-component no-follow
  and fresh event publication can overwrite a competitor. P1: current predecessor has no
  authenticated recovery path; index-before-event power cut creates an evidence gap; per-path
  cache is not an atomic cross-tree evidence generation. These require architectural fixes and
  new faults before integration/audit. Prior PASS receipts remain test history only; GPU/E2,
  full offline, stage/commit/push remain gated. Pause/launcher P1 fixes/tests are still in flight.
- `20260822-230154-p0b-pause-launcher-reaudit-not-ready`: independent latest-byte
  pause/launcher audit is `NOT READY`, P0=0/P1=3. Remaining P1s are: observed nonterminal
  identities can be primed from unrelated live processes before requested/launch provenance
  binding; final expensive artifact/checkpoint verification can overrun the absolute deadline
  before marker emission; and required final report/revision/PID-reuse/deadline cutpoints lack
  direct fault regressions. Fixes must bind runner to the just-started PID/ancestry and trainer
  to that runner, check the deadline immediately before every marker, and add the missing
  deterministic faults. Root integration PASS remains a valid prior receipt but does not open
  GPU/E2; Python and pre-commit audits are still running.
- `20260822-225720-p0b-root-integration-pass-receipt`: root fresh PowerShell command
  `powershell -NoProfile -ExecutionPolicy Bypass -File
  .\test-airi-training-durability.ps1 -KeepFailedArtifacts` exited 0 after about 32 seconds
  with literal `AIRI training durability contract: PASS`; post-run related PID count is 0 and
  diff-check has no error (line-ending warnings only). Because the run passed, its synthetic
  root was cleaned despite the failure-retention switch. Together with root pinned Python
  `82 passed, 1 skipped in 22.46s`, integration is green; independent latest-byte P0/P1=0
  audits are now required before full offline/stage/GPU.
- `20260822-225625-p0b-powershell-contract-retry-intent`: the fixture now waits until both
  runner and trainer identity objects exist before substituting forged PIDs; parse and
  diff-check pass, related PID preflight is 0. Retry exact command:
  `powershell -NoProfile -ExecutionPolicy Bypass -File
  .\test-airi-training-durability.ps1 -KeepFailedArtifacts`. The switch changes only failure
  retention; a pass still cleans the synthetic root. Completion and interruption conditions
  remain exit 0 + literal PASS + PID 0, otherwise preserve the new synthetic root and diagnose
  without GPU/E2.
- `20260822-225413-p0b-forged-complete-injection-failure`: the one fresh exact PowerShell
  contract exited 1 after about 30 seconds at `test-airi-training-durability.ps1:829` with
  `Actual-process forged complete terminal was not injected`; no PASS/SAFE completion is
  claimed. Post-failure related PID count is 0. The default-cleaned new synthetic root was not
  retained; older preserved synthetic diagnostics remain untouched. Diagnose the fixture
  injection condition, add observability or a deterministic synchronization receipt, then run
  one fresh contract only; GPU/E2 and independent audit remain gated.
- `20260822-225306-p0b-root-powershell-contract-intent`: root pinned focused Python exited
  0 with `82 passed, 1 skipped in 22.46s`; post-run related PID count is 0 and diff-check has
  no error (line-ending warnings only). The second sequential command is now authorized:
  `powershell -NoProfile -ExecutionPolicy Bypass -File
  .\test-airi-training-durability.ps1`. It may spawn only synthetic temp runner/trainer cases;
  completion requires exit 0, literal `AIRI training durability contract: PASS`, and related
  PID 0. Any failure/timeout keeps GPU/E2 gated and is recorded before retry.
- `20260822-225209-p0b-root-fresh-integration-intent`: related PID preflight is 0.
  Run sequentially from repo root: (1) pinned Python
  `D:\AIRI-Models\venv-midm-broadcast-qlora-py312\Scripts\python.exe -m pytest -q
  ollama-proxy/training/tests/test_durable_training_runner.py
  ollama-proxy/training/tests/test_verify_airi_behavior_gpu_equivalence.py`; then only after its
  process tree exits, (2) `powershell -NoProfile -ExecutionPolicy Bypass -File
  .\test-airi-training-durability.ps1`. Inputs are the current 9 modified + one untracked P0-B
  implementation/test set; outputs are console receipts and synthetic temporary roots only.
  Completion requires exit 0/PASS plus related PID 0 after each command; failure or interruption
  keeps GPU/E2 gated and preserves any failed synthetic root for diagnosis.
- `20260822-224908-p0b-reparse-regressions-receipt`: explicit adapter/report receipt
  substitution, Windows reparse-attribute inventory, and asymmetric two-arm interval receipt
  regressions now pass in pinned focused pytest: `81 passed, 1 skipped in 22.42s`; related
  test/runner/trainer PID recount is 0. Root identified that Windows `O_NOFOLLOW` can be zero,
  so final-component replacement must still be closed with a native no-follow handle read
  before the root contract and independent audit. GPU/E2 remains gated.
- `20260822-224630-p0b-final-hardening-focused-receipt`: pause/launcher integrated
  observed live runner/trainer identity binding, required report receipts, and a final
  unchanged-state/process cut immediately before `SAFE_TO_POWER_OFF`. Python runner/verifier
  now refuses every missing-current predecessor rollback, binds terminal adapter/report
  receipts to one immutable evidence cut, closes symlink/reparse artifact inventory, and
  reports conservative interval evidence across both controlled arms. Pinned focused pytest
  receipt: `79 passed, 1 skipped in 22.64s`; the observed test-only pytest/runner tree exited
  after the receipt and was not GPU/E2. The worker's PowerShell invocation remains
  inconclusive, so root must run one fresh exact actual-process contract before audit.
- `20260822-223722-p0b-independent-reaudit-not-ready`: root Python `75 passed,
  1 skipped`와 actual-process PowerShell PASS 뒤 최신 bytes 두 독립 감사 판정은
  `NOT READY`. runner/verifier는 P0 3/P1 1: missing current가 stale terminal previous를
  resume 권한으로 만드는 rollback, completed run-state checkpoint와 latest index/event
  미결속, adapter/report/safetensors가 evidence cut 밖에서 재개방되는 mixed-generation PASS,
  resumed arm timing 미게이트다. pause/launcher는 P0 1/P1 2: schema-valid full forged complete가
  substituted absent PID로 `SAFE_TO_POWER_OFF` 가능한 경로, launcher terminal과 실제 시작
  process 미결속, marker 직전 runner/trainer/state 재확인 공백이며 complete report optional도
  P0에 포함된다. 각 absent-PID/path replacement/concurrent-resume fault를 수리·회귀하고 fresh
  통합·독립 P0/P1 0 전에는 full offline/stage/GPU/E2를 금지한다.
- `20260822-223238-p0b-latest-integration-pass-reaudit-intent`: corrupt-current side-effect
  assertion을 새 계약에 맞춘 뒤 root single fresh
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\test-airi-training-durability.ps1`
  exit 0, `AIRI training durability contract: PASS`; 종료 뒤 관련 test/runner/trainer PID 0이다.
  앞선 root pinned Python은 `75 passed, 1 skipped`. latest 통합은 corrupt current가 stale
  terminal previous resume 권한이 되는 경로, input/checkpoint single-handle snapshot,
  verifier cached evidence cut/state.pt, schema-valid forged complete와 null report, terminal
  process/artifact semantics, paused-safe authoritative gateway, auto-discovery와 실제 pause→resume를
  포함한다. 최신 전체 bytes를 runner/verifier와 pause/launcher 두 범위로 독립 재감사해
  P0/P1 0 전에는 full offline/stage/GPU/E2로 이동하지 않는다.
- `20260822-223113-p0b-corrupt-current-side-effect-assertion-failure`: launcher P0
  수리 뒤 contract는 정상 resume complete와 archived pause controls까지 통과한 뒤 구
  `corrupt current was quarantined` assertion에서 exit 1, SAFE marker 0, 관련 runner/trainer
  PID 0이다. launcher가 runner 시작 전 거부하므로 quarantine 0이 새 fail-closed 계약이며,
  assertion을 mutation 0으로 뒤집었다. parse 뒤 single fresh contract를 재실행하며 PASS 전
  full offline/stage/GPU/E2는 금지다.
- `20260822-222957-p0b-corrupt-current-launcher-retry-intent`: 보존 diagnostic root
  `airi-durability-contract-8fe7...`에서 live pause current는 격리됐고 valid terminal
  previous만 남아 있어 timeout이 resume 호출임을 확정했다. 구 fixture는 current runner
  identity를 구조적으로 깨뜨린 뒤 stale terminal previous가 resume 권한이 되길 기대해 새
  P0 계약과 충돌했다. launcher도 invalid current가 존재하면 previous fallback 전에 즉시
  `previous state cannot authorize resume`로 거부하고, test는 이 거부/무프로세스 실행을
  확인한 뒤 원본 current bytes를 복원해 별도 정상 resume를 수행하도록 수정했다. 두 PS
  parse exit 0이며 single fresh contract PASS/PID 0 전 full offline/stage/GPU/E2는 금지다.
- `20260822-222738-p0b-live-pause-timeout-diagnostic-intent`: RunId 관측성 추가 뒤
  single contract는 약 63초 후 `live-pause-contract` launcher timeout exit 1, SAFE marker 0,
  관련 PID 0이다. 이는 canonical 수리로 injected arm을 넘어 실제 live pause fresh 또는
  resume 호출에 도달했음을 뜻하지만 동일 RunId라 둘 중 어느 것인지 console만으로는
  모른다. exact `-KeepFailedArtifacts`를 한 번 실행해 pause-case current/previous state,
  control/checkpoint와 output/log size를 보존 대조한다. 실패 산출물은 진척이 아니며 full
  offline/stage/GPU/E2 gate는 닫혀 있다.
- `20260822-222534-p0b-unlocated-launcher-timeout`: source token 복원 뒤 single
  contract는 다시 약 65초 후 launcher timeout exit 1, SAFE marker 0, 관련 PID 0이다.
  console에 RunId가 없어 injected complete와 prearm paused-safe 중 어느 호출인지 여전히
  직접 식별되지 않는다. timeout 문구에 비민감 RunId를 추가해 동일 actual-process contract를
  한 번 재실행하고 해당 state만 보존·대조한다. 이 관측성 수리는 권한/검증을 완화하지 않으며
  PASS 전 full offline/stage/GPU/E2 gate는 닫혀 있다.
- `20260822-222345-p0b-launcher-source-token-failure`: paused-safe gateway 수리 뒤
  contract는 실행 전 source token `launcher polling never` 부재로 exit 1, SAFE marker 0,
  관련 PID 0이다. paused-safe를 무조건 거부하던 기존 주석을 재작성하면서 contract가
  요구하는 literal을 제거한 문서화 fixture 회귀다. authoritative gateway 실패 시
  `launcher polling never` authorizes terminal success 의미로 주석에 복원하고 parse 뒤
  동일 contract를 재실행한다. full offline/stage/GPU/E2 gate는 닫혀 있다.
- `20260822-222310-p0b-paused-terminal-launcher-timeout`: artifact canonical 순서 수리
  뒤 보존 receipt 직접 adapter/report/terminal 모두 true였다. single fresh contract는 다시
  약 64초 후 launcher timeout exit 1, SAFE marker 0, 관련 PID 0이다. injected complete는
  이제 검증 가능하므로 후속 초단명 prearm이 첫 poll 전에 valid paused-safe terminal을 쓰면
  launcher가 paused-safe를 무조건 false로 한 가용성 결함으로 분리했다. paused-safe만 기존
  `pause-airi-safely.ps1`의 explicit RunDir full checkpoint/ack 검증을 호출해 marker를 캡처하고
  성공할 때 terminal launch receipt를 허용한다. 새 검증이 실패하면 계속 timeout/fail-closed다.
  parse·single fresh PASS 전 full offline/stage/GPU/E2는 금지다.
- `20260822-222047-p0b-artifact-canonical-order-retry-intent`: 보존 진단 root
  `airi-durability-contract-51fc...`에서 ordinary와 injected run 모두 complete exit 0,
  adapter directory/report file 실제 존재·hash 일치, logs 0 bytes, 관련 PID 0이다. launcher
  helper 직접 대조는 runner/trainer exited·report true지만 adapter false였다. Python
  artifact manifest는 sorted key `path,sha256,size`인데 PowerShell이 `path,size,sha256`으로
  canonical JSON을 만들어 동일 row manifest SHA가 달라진 원인이다. ordered row를 Python
  key 순서로 정정하고 보존 receipt 직접 true·parse 뒤 single fresh contract를 재실행한다.
  PASS 전 full offline/stage/GPU/E2는 금지다.
- `20260822-221817-p0b-launcher-timeout-after-forged-fix`: full-receipt fixture 수리 뒤
  single contract는 약 65초 후 launcher 30초 timeout,
  `launch_shim_exited=True`, exit 1, SAFE marker 0, 관련 PID 0이다. default finally가 새
  temp root를 제거해 console만으로 injected complete가 실패했는지 후속 prearmed
  paused-safe terminal을 launcher가 의도적으로 거부해 timeout했는지 분리할 수 없다.
  exact 같은 contract를 `-KeepFailedArtifacts`로 한 번만 실행해 final state/output/log size를
  보존하고 원인을 분리한다. 실패 계산은 진척이 아니며 full offline/stage/GPU/E2는 금지다.
- `20260822-221637-p0b-forged-receipt-fixture-retry-intent`: 보존 final state는
  `failed/terminal-artifact-missing`과 path-only outputs였다. fixture는 forged complete에서
  output 경로가 존재한다는 이유만으로 verified completion을 true로 만들고 null/minimal
  receipt의 `.Properties`를 읽었다. injected fake가 venv launch-shim timing과 무관하게 fault
  window 전에 synthetic artifacts를 만들고, test는 adapter `manifest_sha256`+report `sha256`
  full receipts가 모두 있을 때만 legitimate complete로 인정하도록 수리했다. PowerShell
  parse exit 0이며 exact single fresh contract를 재실행한다. PASS/PID 0 전 full offline/
  stage/GPU/E2 금지를 유지한다.
- `20260822-221403-p0b-terminal-receipt-property-failure`: heartbeat 15 정정 뒤
  single contract는 실제 fault suite를 진행해 약 30초 후 exit 1,
  `The property 'Properties' cannot be found on this object`; SAFE marker 0, 관련
  test/runner/trainer PID 0이다. test finally는 잠긴 synthetic temp root
  `airi-durability-contract-6e80...`를 caller 종료 후 정리 대상으로 남겼다. forged arm의
  legitimate receipt가 dictionary/PSCustomObject 중 어느 형식인지 보지 않고
  `.PSObject.Properties`를 읽는 fixture 또는 제품 artifact verifier 형식 경계로 분리해
  보존 state/output 존재·schema만 대조하고 최소 수리한다. full offline/stage/GPU/E2는 금지다.
- `20260822-221251-p0b-heartbeat-fixture-range-failure`: 주석 위치 정정 뒤 single
  contract는 약 18초에 injected arm의 `HeartbeatSeconds 20`이 launcher 허용 상한 15를
  넘어 parameter binding exit 1, SAFE marker 0, 관련 PID 0이다. fault window 2초보다
  충분히 긴 허용 최대 15로 정정하고 parse 뒤 동일 contract를 재실행한다. 제품 코드에는
  도달하지 않았고 full offline/stage/GPU/E2 gate는 닫혀 있다.
- `20260822-221205-p0b-powershell-continuation-failure`: single contract 재시도는 약
  19초 뒤 제품 forged arm 실행 전에 `missing mandatory parameters: TrainerArguments`,
  exit 1, SAFE marker 0, 관련 PID 0이다. injected launcher의 backtick 연속 매개변수 사이에
  넣은 설명 주석이 호출을 끊은 fixture 편집 실수다. 주석을 호출 앞 독립 줄로 옮기고
  parse 뒤 동일 contract를 재실행하며 full offline/stage/GPU/E2 gate는 닫혀 있다.
- `20260822-221123-p0b-forged-fixture-retry-intent`: 제품 poll 분기는 terminal이면
  verified terminal receipt만, nonterminal이면 exact live runner만 허용해 의도대로였다.
  실패는 initial launcher가 정상 `running` receipt를 반환한 시점에 forged gate가 존재하면
  status를 보지 않고 forged complete 성공으로 오판한 fixture 결함이다. injected arm의
  heartbeat를 20초로 늘려 runner heartbeat가 2초 fault window를 덮지 않게 하고, gate 중
  `status=complete` 반환만 실패하도록 정정했으며 PowerShell parse exit 0이다. 같은 single
  fresh contract를 한 번 재실행해 old OR branch 거부와 실제 terminal artifacts를 함께
  검증하며 PASS/PID 0 전 full offline/stage/GPU/E2 금지를 유지한다.
- `20260822-220951-p0b-forged-terminal-contract-failure`: root single fresh
  `test-airi-training-durability.ps1`은 약 20초 뒤 exit 1,
  `Launcher returned a forged complete terminal receipt while its exact runner was live`;
  SAFE marker 0이고 종료 뒤 관련 test/runner/trainer PID 0이다. 제품 terminal/nonterminal
  분기 또는 re-entry fixture가 여전히 forged state를 성공 receipt로 노출한다. 이 실패는
  진척/PASS가 아니며 보존된 source와 exact test 구간을 대조해 최소 수리한 뒤 Python/
  PowerShell 통합을 다시 수행한다. full offline/stage/GPU/E2 gate는 닫혀 있다.
- `20260822-220907-p0b-latest-python-pass-powershell-intent`: root pinned Python
  pycompile+runner/verifier focused exit 0, `75 passed, 1 skipped in 19.83s`; 종료 뒤 관련
  pytest/runner/trainer PID 0이다. exact 다음 단일 명령은
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\test-airi-training-durability.ps1`;
  actual child process에서 forged terminal, stale current, single snapshots, pause/resume와
  SAFE marker를 통합 검증한다. exit 0/PASS와 종료 뒤 관련 PID 0 전에는 full offline/
  stage/GPU/E2를 금지한다.
- `20260822-220814-p0b-latest-fix-root-integration-intent`: runner/input의 단일
  regular-handle snapshot과 corrupt-current terminal previous 권한 차단, verifier의
  run-state/index/manifest/payload/event/history 동일 evidence cut 및 cached `state.pt`
  비교, launcher의 terminal-only verified receipt 분기와 complete exit/artifact semantics를
  fault 회귀와 함께 통합했다. 위임 focused는 최신 `75 passed, 1 skipped`, PowerShell parse/
  diff-check PASS지만 root 권위 receipt 전이다. 관련 test/runner/trainer PID 0을 대조했고,
  exact 다음 명령은 핀된 Python runner+verifier 두 suite와 단일 fresh
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\test-airi-training-durability.ps1`다.
  두 명령 exit 0, expected PASS와 종료 뒤 관련 PID 0이 완료 조건이며 실패 시 full offline/
  stage/GPU/E2를 금지하고 즉시 실패 receipt를 기록한다.
- `20260822-215745-p0b-latest-reaudit-not-ready`: compact 복구 뒤 지정 SSoT를 순서대로
  재독하고 goal `active`, HEAD=origin/main `32830a4`, 실제 worktree 9 modified+generator
  1 untracked, AIRI trainer/runner 0, planned P0-B root와 E2 adapter/report 부재, 기존 E2
  로그 각 0 bytes를 대조했다. 최신 두 독립 감사 판정은 `NOT READY`: runner가 corrupt
  current에서 stale terminal previous로 rollback해 resume 권한으로 쓰는 P0, manifest/source
  locality 검사와 read가 단일 handle snapshot이 아닌 P0, verifier PASS가 run-state/index/
  checkpoint/events를 여러 번 열어 서로 다른 evidence generation을 섞을 수 있는 P0,
  launcher가 requested binding만 맞는 schema-valid forged terminal을 runner exit·artifact
  검증 없이 성공 receipt로 수용하는 P1이다. 각 cutpoint/forgery fault 회귀를 포함해 수리하고
  fresh focused·actual-process·독립 P0/P1 0 전에는 full offline/stage/GPU/E2를 금지한다.
- `20260822-215328-p0b-four-p0-integration-pass-final-reaudit-intent`: single fresh
  `test-airi-training-durability.ps1` exit 0,
  `AIRI training durability contract: PASS`; 종료 후 관련 test/runner/trainer PID 0이다.
  checkpoint manifest/payload cutpoint, raw canonical pins SHA tamper, stale terminal previous,
  malformed launcher terminal injection, first-instruction prearm, float pins, auto-discovery 0/1/2,
  actual pause→resume base/actual command, exact trainer/runner exit와 SAFE marker를 포함한다.
  핀된 Python은 `68 passed, 1 skipped`. 최신 bytes를 pause/launcher와 runner/manifest/verifier
  두 범위로 독립 재감사해 P0/P1 0 전에는 full offline/stage/GPU/E2로 이동하지 않는다.
- `20260822-215216-p0b-injection-fixture-wait-retry-intent`: discovery schema 수리 뒤
  contract는 terminal-injection 사후 대기 assertion에서 exit 1, SAFE marker 0, 관련 PID
  0이다. launcher 즉시 반환은 forged complete+missing outputs를 거부했지만 test wait가 raw
  `status=complete`만 보고 forged terminal에서 break한 fixture 결함이다. wait/final은 terminal
  exit 0+`trainer-complete`+실제 adapter/report를 함께 요구하도록 수리했고 parse PASS다.
  single fresh contract PASS 전 full offline/stage/GPU/E2 금지를 유지한다.
- `20260822-215051-p0b-discovery-command-schema-retry-intent`: base command 수리 뒤
  contract는 multi-active auto-discovery fault에서 exit 1; 기대한 2개 대신 0개를 보고
  SAFE marker 0, 관련 PID 0이다. pause discovery가 state command를 구 3필드 exact schema로
  검사해 새 `base_canonical_sha256`을 가진 정상 4필드 state를 모두 제외한 동기화 결함이다.
  command schema를 4필드로 정정했고 parse PASS다. single fresh contract PASS 전 full
  offline/stage/GPU/E2 금지를 유지한다.
- `20260822-214842-p0b-resume-base-powershell-intent`: base/actual command 분리 뒤 핀된
  Python focused exit 0, `68 passed, 1 skipped in 17.13s`, 관련 PID 0이다. single fresh
  PowerShell actual-process contract를 재실행하며 PASS 전 full offline/stage/GPU/E2를 금지한다.
- `20260822-214752-p0b-resume-base-command-test-intent`: 보존 temp `f107...`에서 ordinary와
  injected launcher run은 모두 complete/artifacts verified였고 실제 pause→resume run도
  complete까지 진행했다. timeout은 resume actual command에만 붙는 checkpoint absolute
  path 때문에 launcher가 base request SHA와 final actual SHA를 직접 비교한 계약 결함이다.
  runner state command에 `base_canonical_sha256`을 추가해 checkpoint path 전 immutable
  command를 별도 결속하고 launcher already-running/poll은 base SHA를 비교한다. fresh는
  base=actual, resume는 base 보존/actual 차이를 Python 회귀로 고정했다. parse·핀된 pycompile·
  diff-check PASS 뒤 Python focused부터 재검증하며 실패 시 PowerShell/full offline/GPU/E2 금지다.
- `20260822-214501-p0b-terminal-injection-timeout`: command exact-match 수리 뒤 single
  contract는 약 51초 후 두 번째 30초 launcher timeout exit 1, SAFE marker 0, 관련 PID 0.
  elapsed상 ordinary launcher는 통과하고 새 malformed terminal injection case에서 실패한
  것으로 보이나 final state overwrite 대 requested binding을 아직 분리하지 않았다. 같은
  contract를 `-KeepFailedArtifacts`로 한 번만 재현해 injection run final state/output/log와
  command SHA를 대조한다. full offline/stage/GPU/E2 gate는 닫혀 있다.
- `20260822-214324-p0b-launcher-command-exact-match-retry-intent`: 직전 single contract도
  30초 launcher timeout exit 1, SAFE marker 0, 관련 PID 0. runner가 추가하는 세 번째 인자
  `--checkpoint-every-optimizer-steps`가 effective command SHA에서 빠졌고 PowerShell nested
  array flatten도 암묵적이었다. run-dir, run-id, checkpoint interval을 runner와 같은 순서로
  append하고 explicit flatten한 계산은 보존 actual state canonical SHA
  `ccd43513...329bf`와 exact 일치한다. parse PASS 뒤 single fresh contract를 재실행하며
  PASS 전 full offline/stage/GPU/E2 금지를 유지한다.
- `20260822-214046-p0b-launcher-effective-command-retry-intent`: started-PID 제거 뒤 single
  contract도 같은 30초 launcher timeout exit 1, SAFE marker 0, 관련 PID 0이었다. requested
  command SHA가 사용자 TrainerArguments만 해시하지만 runner는 실제 command에 `--run-dir`과
  `--run-id`를 append하므로 정상 state와 일치할 수 없는 결속 계산 결함으로 분리했다.
  launcher가 runner와 같은 중복/누락/충돌 규칙과 append 순서로 effective args를 만든 뒤
  canonical SHA를 계산하도록 수리했고 parse·diff-check PASS다. 다음 single fresh contract
  PASS 전에는 full offline/stage/GPU/E2를 계속 금지한다.
- `20260822-213854-p0b-launcher-binding-retry-intent`: 보존 temp `e861...`에서 ordinary
  launcher run은 runner PID 9212/trainer 14016, complete exit 0, adapter/report verified,
  logs 0 bytes였다. `Start-Process`가 반환한 Python launch shim PID와 실제 runner PID가 달라
  started-PID equality가 정상 receipt를 30초 동안 거부한 원인이다. started PID 조건을
  제거하고 strict state schema에 requested manifest canonical path/SHA, trainer/runner source
  SHA, canonical command SHA를 exact 결속했다. parse·diff-check PASS 후 single fresh
  PowerShell contract를 재실행한다. PASS 전 full offline/stage/GPU/E2 금지는 유지한다.
- `20260822-213636-p0b-launcher-strict-poll-failure`: single fresh PowerShell contract는
  약 37초 후 exit 1, `Durable runner did not publish a verified run-state within 30 seconds;
  launch_shim_exited=True`; SAFE marker 0, 종료 뒤 관련 PID 0이다. 새 launcher strict reader/
  started PID 결속 또는 injected terminal fixture가 정상 final receipt까지 거부한 것으로
  아직 분리되지 않았다. `-KeepFailedArtifacts`를 한 번만 재현해 각 run-state terminal과
  output/log size를 대조하고 최소 수리한다. 실패를 진척으로 승격하지 않고 full offline/
  stage/GPU/E2를 계속 금지한다.
- `20260822-213516-p0b-four-p0-powershell-intent`: 핀된 Python focused는 exit 0,
  `68 passed, 1 skipped in 17.01s`; manifest/payload snapshot cutpoint를 포함하며 관련 PID
  0이다. exact single fresh PowerShell durability contract로 canonical raw pins tamper,
  stale terminal previous, malformed terminal injection, prearm/auto-discovery/exact exit를
  actual child process에서 검증한다. 실패 시 full offline/stage/GPU/E2를 금지한다.
- `20260822-213427-p0b-four-p0-fix-test-intent`: checkpoint manifest와 payload를 각각
  regular handle 단일 bytes snapshot으로 읽어 이후 SHA/parse/canonical/schema/size 검사를
  같은 관측에 결속했다. checkpoint canonical은 실제 trainer 모듈의 ensure-ASCII 계약과
  분리했고 pause는 canonical manifest top-level layout에서 raw pins value bytes를 잘라
  receipt SHA와 비교하므로 float를 재직렬화하지 않는다. current가 invalid할 때 terminal
  previous fallback을 금지했고 launcher poll은 strict state reader와 exact started PID를
  요구한다. manifest/payload cutpoint, pins receipt tamper, stale terminal previous, injected
  malformed terminal launcher fault를 추가했다. parse·핀된 pycompile·diff-check PASS. 다음은
  핀된 Python 두 focused suite이며 실패하면 actual PowerShell/full offline/GPU/E2로 이동하지 않는다.
- `20260822-212955-p0b-final-reaudit-not-ready`: 최신 두 독립 read-only 재감사는
  manifest/runner P0 1/P1 0, pause/launcher P0 3으로 `NOT READY`. runner의 authoritative
  checkpoint validation이 manifest SHA→parse→canonical에서 세 번 열고 payload도 stat/hash
  분리 관측인 TOCTOU, pause가 `canonical_pins_sha256` 형식만 보고 실제 manifest pins bytes와
  비교하지 않는 공백, malformed current에서 stale terminal previous로 fallback해 old PID
  exit만으로 SAFE marker가 가능한 경로, launcher launch-poll이 strict state reader를 우회해
  임의 terminal JSON을 성공 receipt로 쓰는 경로다. checkpoint manifest/payload 단일 byte
  snapshot, checkpoint canonical raw pins slice hash, terminal previous fallback 금지, launcher
  strict reader+started PID 결속을 각각 fault 회귀와 함께 닫는다. 재통합·독립 P0/P1 0 전에는
  full offline/stage/GPU/E2를 금지한다.
- `20260822-212440-p0b-authoritative-receipt-integration-pass-reaudit-intent`: single
  fresh `test-airi-training-durability.ps1`은 exit 0,
  `AIRI training durability contract: PASS`; 종료 후 관련 test/runner/trainer PID 0이다.
  첫-instruction prearm, Python float checkpoint pins, authoritative terminal receipt,
  receipt tamper 거부, 자동 RunDir 탐지, exact trainer/runner exit와 SAFE marker를 actual child
  process로 통과했다. 앞선 핀된 Python은 `66 passed, 1 skipped`. 최신 전체 bytes를 pause/
  launcher와 manifest/runner/verifier 두 범위로 독립 read-only 재감사해 P0/P1 0을 받기
  전에는 full offline/stage/GPU/E2로 이동하지 않는다.
- `20260822-212346-p0b-powershell-contract-second-retry-intent`: 보존 state의 schema와
  fields는 모두 유효했고 pause reader가 존재하지 않는 `Test-ExactJsonProperties`를 호출해
  outer catch가 state를 fail-closed 무효화한 구현 실수로 분리했다. 기존
  `Assert-ExactJsonProperties`를 사용하도록 고친 뒤 같은 보존 state 직접 실행은 exit 0,
  `SAFE_TO_POWER_OFF`. parse PASS, 관련 PID 0이다. exact fresh PowerShell contract를 다시
  한 번 실행하며 이번 PASS 전에는 full offline/stage/GPU/E2로 이동하지 않는다.
- `20260822-212229-p0b-powershell-receipt-reader-failure`: 단일 fresh PowerShell
  contract는 exit 1, 첫 already-paused synthetic receipt에서 `No valid current or previous
  run-state receipt is available`; SAFE marker 0, 종료 후 관련 PID 0이다. fail-closed는
  유지됐지만 새 paused-safe terminal schema의 fixture 대 reader 조건이 불일치한다. 같은
  command에 `-KeepFailedArtifacts`를 한 번만 붙여 state bytes를 보존·대조하고 reader 또는
  fixture를 최소 수리한다. 실패를 PASS/진척으로 승격하지 않으며 중복 contract/full offline/
  GPU/E2를 계속 금지한다.
- `20260822-212155-p0b-powershell-contract-retry-intent`: 핀된 Python focused는 exit 0,
  `66 passed, 1 skipped in 17.41s`; 종료 후 관련 durability test/runner/trainer PID 0이다.
  exact command `powershell -NoProfile -ExecutionPolicy Bypass -File
  .\test-airi-training-durability.ps1`를 단 한 번 실행한다. 새 contract는 trainer 첫 instruction
  prearm, Python float pins, authoritative terminal receipt, receipt tamper 거부, 자동 RunDir
  탐지와 SAFE marker 전 exact trainer/runner exit를 실제 child process로 검증한다. 실패하면
  원인을 receipt로 기록하고 중복 실행/full offline/GPU/E2를 금지한다.
- `20260822-212103-p0b-authoritative-checkpoint-receipt-test-intent`: PowerShell이
  Python float canonical JSON을 재구현하지 않게 수리했다. exact runner가 Python으로
  canonical/schema/payload와 dataset/model/trainer pins를 검증한 뒤 manifest·payload·
  canonical pins SHA와 payload bytes/generation을 paused-safe terminal receipt에만
  기록한다. pause와 launcher는 exact receipt schema를 요구하고 pause는 manifest/payload
  단일 byte snapshot, ack/state/terminal receipt와 재대조한다. resume도 persisted receipt를
  fresh Python verification과 exact 비교한다. 실제 Python float pins와 receipt 변조 fault를
  회귀에 추가했고 parse·pycompile·diff-check는 PASS. 다음 exact command는 핀된 Python
  runner+verifier 두 focused suite이며, 실패 시 PowerShell contract/full offline/GPU/E2로
  이동하지 않는다. 보존 합성 temp root는 absolute Temp 하위·live PID 0을 확인했지만 두
  recursive cleanup 호출이 exec policy로 실행 전 거부돼 그대로 보존하고 우회 삭제하지 않았다.
- `20260822-211357-p0b-prearm-fixture-diagnostic-receipt`: 보존 진단 contract는 exit 1,
  temp root `airi-durability-contract-d85f...`, 관련 trainer/runner PID 0이었다. 보존
  run-state SHA `d4688c2e...57a5`, checkpoint manifest SHA `9a60de49...bf9`다.
  request·ack·checkpoint·progress가 모두 존재하고 optimizer step 1/pending 0이며 trainer
  stderr/stdout 0 bytes, terminal은 trainer exit 75 뒤 `supervisor-durablerunnererror`와
  trainer null이다. 같은 보존 checkpoint를 runner `_validate_safe_pause`에 다시 넣으면
  PASS하므로 trainer는 첫 instruction에서 prearm을 보고 정상 증거를 썼지만 너무 빨리
  종료되어 supervisor의 PID snapshot 전에 사라진 fixture 경쟁으로 분리했다. 첫 instruction
  확인 직후 1.5초 생존시켜 PID를 캡처하게 하되 확인 자체는 sleep보다 앞에 유지한다.
  진단 중 self command까지 수집한 PowerShell PID 24932가 재귀 JSON 직렬화로 남아 exact
  command를 대조한 뒤 종료했으며 그 외 관련 PID는 0이다. float canonical P0는 별도
  authoritative runner receipt 설계로 계속 닫는다.
- `20260822-211152-p0b-prearm-failure-diagnostic-intent`: strict pause 수리 뒤 단일
  fresh PowerShell contract는 exit 1, `Fresh prearm request was not visible to the
  trainer at process spawn`; 종료 후 관련 child PID 0이다. source 순서는 prearm publication,
  run-state publication, trainer `Popen`이지만 실패 문구만으로 제품 순서 결함과 fixture의
  terminal validation 결함을 구분할 수 없다. exact command
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\test-airi-training-durability.ps1
  -KeepFailedArtifacts`를 한 번만 실행해 격리 temp root와 run-state/log receipt를 보존한다.
  출력은 OS temp 아래 contract root뿐이며 GPU/model/service/E2는 0이다. 실패 산출물은
  진척으로 승격하지 않고 원인 분리 후 안전하게 정리한다.
- `20260822-210952-p0b-pause-canonical-float-failure`: pause strict 수리의 단일
  PowerShell contract가 실행된 뒤 별도 실제 형식 대조에서 새 P0 availability 결함을
  확인했다. 대표 E2 값 `learning_rate=0.00002`를 Python
  `json.dumps(sort_keys=True,separators=(',',':'))`는 `2e-05`로, Windows PowerShell
  `ConvertTo-Json -Compress`는 `0.00002`로 직렬화해 bytes가 불일치한다. 현재 pause의
  canonical bytes 재직렬화 검사는 정상 Python checkpoint를 거짓 거부할 수 있으므로
  직전 contract 결과만으로 승인하지 않는다. 실제 float fixture를 fault 회귀로 고정하고
  권위 검증 결속을 수정한 뒤 단일 fresh 통합·독립 재감사 전까지 full offline/stage/GPU/E2를
  계속 금지한다. 이 대조는 저장소·GPU·모델·서비스 산출물을 만들지 않았다.
- `20260822-205510-p0b-second-reaudit-final-not-ready`: 두 독립 최종 판정은 pause
  P0 2/P1 4, manifest P0 3/P1 2로 `NOT READY`. pause P0는 terminal trainer identity
  continuity와 권위 Python validator보다 약한 checkpoint canonical/schema/pins/reparse
  검증이다. pause P1은 marker 전 absolute deadline, recovered-complete terminal
  cross-contract, launcher already-running의 requested manifest/command 미결속,
  prearm-before-Popen 경쟁 회귀 공백이다. manifest P0는 hash/parse 다중-open TOCTOU,
  verifier receipt가 evidence tree 안에 게시돼 closed inventory를 사후 파괴하는 문제,
  prearm check-then-replacing publish 경쟁이다. manifest P1은 Windows builder target
  metadata write-through 부재와 heartbeat NaN 선행 gate다. 최신 focused PASS는 이 경로를
  덮지 못하므로 모두 fault 회귀와 함께 닫고 fresh 통합·독립 P0/P1 0 전에는 full offline,
  stage/commit, controlled GPU/E2를 금지한다.
- `20260822-205317-p0b-second-reaudit-not-ready`: 최신 pause 독립 재감사의 확정 중간
  판정은 P0 1, `NOT READY`. terminal revision에서 trainer record를 null/다른 identity로
  바꿔도 `Wait-RecordedRunnerExit`가 runner continuity만 검사하고 반환 state의 trainer만
  기다려 SAFE marker가 가능하며, synthetic success fixture도 trainer null을 허용했다.
  추가 P1 후보는 marker 직전 deadline 재검사 부재, runner가 생성 가능한
  `recovered-complete-artifacts` reason을 pause가 거부하는 계약 불일치, PowerShell
  checkpoint 검증의 canonical/exact schema/pins/reparse 공백이다. manifest 재감사도
  single immutable read가 아닌 hash/parse/canonical 다중 open TOCTOU, Windows
  non-replacing publish의 write-through 부재, heartbeat NaN gate를 점검 중이다. 최종
  판정을 받은 뒤 모두 fault 회귀와 함께 닫고 fresh 통합/재감사 전에는 full offline,
  stage/commit, GPU/E2를 금지한다.
- `20260822-204923-p0b-nonfinite-param-retry-pass`: learning-rate Infinity case의
  argv 표현을 정정한 targeted 회귀는 exit 0, `4 passed, 25 deselected`; runner+verifier
  전체 focused는 exit 0, `58 passed, 1 skipped in 15.86s`. builder가 dropout과
  learning-rate 각각의 NaN/Infinity를 publication 전에 거부하는 회귀가 모두 PASS했다.
  직전 단일 actual-process PowerShell PASS는 test mode 외 product/pause bytes가 변하지
  않아 유지하되, 최신 독립 감사 판정을 기다린다. P0/P1 0 전에는 full offline/GPU/E2를
  실행하지 않는다.
- `20260822-204839-p0b-nonfinite-param-fixture-failure`: 감사 대기 중 추가한 builder
  non-finite 4-case targeted 회귀는 exit 1, `1 failed, 3 passed`. 제품 validation이
  아니라 `--learning-rate -inf`를 argparse가 새 option으로 해석해 expected argument
  이전에 usage exit 2가 난 fixture 표현 결함이다. output publication은 없었다.
  해당 case를 양의 `inf` 또는 `--learning-rate=-inf` 형식으로 정정하고 targeted 뒤
  전체 focused를 다시 실행한다. 이 실패를 제품 진척/PASS로 승격하지 않으며 독립 감사와
  full offline/GPU/E2 gate는 계속 닫혀 있다.
- `20260822-204418-p0b-hardening-single-fresh-integration-pass`: 핀된 Python의
  builder/runner/verifier pycompile과 runner+verifier 두 suite는 exit 0,
  `55 passed, 1 skipped in 15.85s`. 이어 다른 contract가 없는 상태에서 단일 fresh
  `test-airi-training-durability.ps1`은 exit 0,
  `AIRI training durability contract: PASS`다. 종료 뒤 test/runner/trainer 관련 PID 0,
  실제 worktree는 9 modified+generator 1 untracked로 경계가 유지된다. SAFE marker의
  exact runner+trainer exit/replacement gate와 bounded deadline, actual manifest
  canonical schema/config/hash/pin 해석, non-finite 선행 거부, launcher fixed-drive gate가
  fault 회귀와 함께 통과했다. 다음은 이 최신 bytes의 독립 read-only P0/P1 재감사이며,
  0건 전에는 full offline/stage/commit/GPU/E2를 금지한다.
- `20260822-204255-p0b-hardening-single-fresh-integration-intent`: 두 중복 contract의
  outer/child/runner/trainer PID가 모두 자연 종료해 0임을 확인했고, 그 결과는 receipt
  부재로 폐기했다. manifest worker의 pycompile+owned pytest는 `55 passed, 1 skipped`지만
  root 통합 전 근거다. strict manifest mode와 PowerShell synthetic fixture의 `qlora`
  불일치를 `cpu-smoke`로 정정했다. 다음 exact 검증은 핀된 Python으로 builder/runner/
  verifier pycompile 및 runner+verifier 두 suite, 이어
  `powershell -NoProfile -ExecutionPolicy Bypass -File
  .\test-airi-training-durability.ps1` 단일 실행이다. 완료 조건은 두 명령 exit 0,
  Python expected PASS, PowerShell 최종 contract PASS와 관련 PID 0이다. 실패하면
  receipt를 기록하고 같은 원인을 수리할 때까지 full offline/GPU/E2를 금지한다.
- `20260822-204053-p0b-powershell-contract-duplicate-supervisor`: pause 수정 담당의 첫
  actual-process contract가 잠시 durable runner PID를 게시한 뒤 root의 runner/trainer
  필터에서는 0이 됐지만 상위 test PowerShell PID까지 필터하지 못했다. 이를 전체 테스트
  종료로 오판해 fresh 재실행을 허용했고, read-only 재대조에서 첫 outer/child
  `11704/25520`과 둘째 `22112/12480` 두 contract가 동시에 살아 있음을 확인했다.
  더 이상 테스트를 시작하거나 PID를 임의 종료하지 않고 두 실행의 자연 종료와 각 exit를
  회수한다. 동시 실행 결과는 성공해도 권위 receipt로 인정하지 않으며, 모든 관련 PID 0 뒤
  단일 fresh contract를 다시 실행한다. GPU/model/service/E2 출력은 0이다.
- `20260822-203520-p0b-hardening-independent-audit-not-ready`: compact 뒤 지정 SSoT
  5종을 순서대로 전체 재독하고 goal `active`, HEAD=origin/main `32830a4`, 실제
  worktree 9 modified+generator 1 untracked, AIRI trainer/runner 0, old planned P0-B
  root와 E2 adapter/report absent를 대조했다. 새 구현의 focused Python
  `47 passed, 1 skipped`와 actual-process PowerShell PASS는 유지되지만, 두 독립
  최신 바이트 감사 판정은 P0 2/P1 4, `NOT READY`다. P0는 (1) runner 종료 뒤
  trainer PID가 exact `exited`인지 `replaced`인지 재검증하지 않아 PID 재사용에서
  SAFE marker가 가능한 점, (2) GPU verifier가 actual manifest bytes를 rehash만 하고
  v1 schema·embedded config/hash를 해석하지 않는 점이다. P1은 trainer-replacement
  회귀 부재, PollSeconds가 absolute timeout을 넘을 수 있는 점, NaN learning-rate의
  nonstandard manifest가 non-replacing publish 뒤 남는 점, PowerShell launcher의
  fixed-drive gate 불일치다. 이 결함과 회귀를 수리하고 fresh focused/actual-process,
  독립 P0/P1 0을 확보하기 전에는 full offline/stage/commit/GPU/E2를 금지한다.
- `20260822-203048-p0b-hardening-integration-pass-audit-intent`: launcher/runner가
  canonical manifest의 actual path/bytes/schema와 dataset/model/trainer/config를 이중
  검증하고, fresh absent RunDir에 trainer spawn 전 첫 optimizer 경계 pause request를
  원자 게시한다. 별도 generator는 actual dataset/base weight/trainer를 해시하고 같은
  schema를 non-replacing publish한다. verifier는 두 arm의 현행 manifest path/bytes/config
  SHA를 다시 검증한다. pause 도구는 paused/complete 모든 marker 경로에서 exact runner
  identity 종료와 receipt/checkpoint/artifact 재검증 후에만 `SAFE_TO_POWER_OFF`를 낸다.
  새 Python py_compile+runner/verifier 묶음은 exit 0, `47 passed, 1 skipped`; 새
  actual-process PowerShell contract 최종 fresh run은 exit 0/PASS, 관련 AIRI process 0이다.
  중간 첫 통합 실패는 fake trainer의 argparse abbreviation이 `--mode qlora`를
  `--model-sha256`으로 오인해 checkpoint pin을 오염한 fixture 결함으로 exact 재현·수리했다.
  다음 fresh run의 synthetic second runner heartbeat 1회 실패는 새 temp 재실행에서 재현되지
  않았고 최종 PASS로 대체하되 독립 감사가 코드 원인을 발견하면 다시 연다. 구현 9 modified+
  generator 1 untracked와 두 SSoT modified 상태이며 GPU/service/D: P0 root/E2 출력은 0이다.
  두 독립 감사 P0/P1 0 전에는 full offline/stage/commit/GPU를 금지한다.
- `20260822-200738-p0b-preflight-pass-hardening-intent`: goal은 실제 `active`, HEAD와
  origin/main은 `32830a43556ba7704a39bd9094f128a5a98dd7d7`, staged/untracked 0이고
  WORKING-STATE만 live diff다. AIRI trainer/runner 0, planned P0-B root와 E2 adapter/
  report absent다. 분리 재시도한 preflight는 source/chat/base/E1/code SHA exact,
  Python 3.12.13·Torch 2.7.0+cu128·CUDA 12.8·RTX 3060 Ti 8 GiB, D: free
  64,238,112,768 bytes, canonical 480-microstep config SHA
  `fb21fb2e1eee8e749c270a94abc074d910ac2c1ae473c554b2803ef29b1a2ca8`를 확보했다.
  따라서 입력·환경 read-only gate는 PASS지만 GPU GO는 아니다. 독립 command/sequence
  감사가 (1) opaque input manifest, (2) 첫 optimizer 경계 pause의 launch-time 원자
  선점 부재, (3) `SAFE_TO_POWER_OFF` 전 exact runner 종료 대기 부재를 확인했다.
  이 세 항목을 code-authoritative하게 구현·fault test·독립 P0/P1 0·commit/push하기
  전에는 planned root를 만들거나 GPU/E2를 실행하지 않는다. baseline 중 generic
  interruption이나 safe arm의 pre-SAFE/추가 interruption은 fresh path로 폐기 재실행한다.
- `20260822-200042-p0b-preflight-receipt-yield-loss`: stdin Python 방식은 quoting
  오류 없이 프로세스가 종료됐고 이후 Python/AIRI runner/trainer 0, planned root absent지만,
  tool wrapper가 10초에 yield한 session ID를 출력하지 않아 JSON/exit receipt를 확보하지
  못했다. 따라서 preflight PASS나 진척이 아니다. 파일/GPU 학습 출력은 0이다. 동일
  read-only 명령을 30초 yield window로 재실행해 exit/JSON을 확보하며 또 receipt가 없으면
  개별 짧은 조회로 분해하고 GPU를 시작하지 않는다.
- `20260822-195918-p0b-preflight-python-quoting-failure`: fresh preflight는
  HEAD=origin/main `32830a4`, WORKING-STATE 단독 diff, planned root/E2 target absent,
  required paths 존재, AIRI runner/trainer 0까지 통과했다. 그러나 pinned Python 환경/
  canonical config 조회가 PowerShell→`python -c`에서 Python 문자열 quote가 소실되어
  `SyntaxError`, exit 1이었다. nvidia/SHA/disk receipt까지 도달하지 못했으므로 preflight
  PASS가 아니다. 파일/root/manifest/GPU 학습 출력은 0이다. Python code를 temp 파일 없이
  stdin으로 전달하는 read-only 조회로 한 번 재시도하고, 또 실패하면 blocker로 남긴다.
- `20260822-195750-p0b-controlled-gpu-fresh-preflight-intent`: final docs commit
  `32830a43556ba7704a39bd9094f128a5a98dd7d7` (`docs: record safe-pause push`)은
  `d8f3936..32830a4 main -> main`으로 push됐다. 이후 HEAD=origin/main `32830a4`,
  worktree clean, AIRI runner/trainer 0이다. safe-pause auto-discovery milestone은
  origin/main에 durable하다. 다음은 GPU 실행이 아니라 planned fresh D: root 부재와
  Git/PID/path/SHA/GPU/venv를 확인하는 read-only P0-B preflight다. `ollama ps`는 이전
  side effect 때문에 금지하며, 이 preflight receipt와 독립 command review 전에는
  manifest/root를 만들거나 GPU/E2를 시작하지 않는다.
- `20260822-195540-p0-safe-pause-auto-discovery-final-docs-intent`: actual push receipt
  exact 2-doc boundary, continuity PASS, repo diff-check PASS 뒤 stage exit 0. staged 2,
  unstaged 0, untracked 0, cached diff-check PASS다. 이 stage receipt를 restage·재검증한 뒤
  exact `git commit -m "docs: record safe-pause push"`, `git push origin main`을 순서대로
  실행한다. 실패하면 receipt 상태를 보존하고 GPU/E2를 실행하지 않는다.
- `20260822-195505-p0-safe-pause-auto-discovery-push-receipt`: exact
  `git push origin main` exit 0, `e3a8819..d8f3936 main -> main`. 이후 HEAD=origin/main
  `d8f393625a4898b41d605f4955064f246990f7fe`, AIRI runner/trainer 0이고 actual push
  receipt용 WORKING-STATE/roadmap log 두 파일만 dirty다. automatic safe-pause code,
  actual-process regression과 6개 SSoT는 origin/main에 durable하다. 두 receipt 문서를
  focused boundary/diff-check 뒤 final docs commit/push하고 clean 경계를 확인해야만
  controlled GPU intent로 이동하며 E2는 계속 금지한다.
- `20260822-195422-p0-safe-pause-auto-discovery-push-intent`: stage receipt 두 문서
  restage 뒤 staged 8·unstaged 0·untracked 0, cached diff-check PASS. exact commit exit 0,
  `d8f393625a4898b41d605f4955064f246990f7fe` (`fix: auto-detect durable training run`),
  8 files, 404 insertions/39 deletions이다. commit 직후 worktree clean, local main은
  origin/main `e3a8819`보다 1 ahead다. 다음 상태 변경은 exact `git push origin main`;
  실패하면 local commit과 두 receipt 문서를 보존하고 GPU/E2를 실행하지 않는다.
- `20260822-195339-p0-safe-pause-auto-discovery-commit-intent`: exact 8-path `git add`
  exit 0. staged 8, unstaged 0, untracked 0, cached diff-check PASS다. 이 stage receipt로
  dirty해진 WORKING-STATE/roadmap log만 restage하고 동일 8/0/0과 cached diff-check를
  확인한 뒤 exact `git commit -m "fix: auto-detect durable training run"`을 실행한다.
  commit 실패 시 push/GPU/E2를 실행하지 않고 staged 배치를 보존한다.
- `20260822-195306-p0-safe-pause-auto-discovery-stage-intent`: final docs 뒤 exact changed
  8(code/test+6 SSoT), boundary diff 0, staged 0, untracked 0, forbidden artifact path 0,
  AIRI runner/trainer 0, final full offline checkpoint와 diff-check PASS다. 독립 최종 감사도
  P0 0/P1 0 `READY`이며 batch 미commit/mispush 주장이 없음을 확인했다. 다음 상태 변경은
  exact 8-path `git add`; staged 8·unstaged 0·untracked 0과 cached diff-check가 모두
  PASS하지 않으면 commit/push/GPU/E2를 실행하지 않는다.
- `20260822-195017-p0-safe-pause-auto-discovery-review-receipt`: 첫 독립 리뷰는 P0 2/
  P1 1로 explicit empty가 auto mode로 승격되는 문제, zero-run test가 ambient workload를
  멈출 위험, `--` 뒤 decoy runner token 오인을 검출했다. `PSBoundParameters`로 omission과
  invalid manual 값을 분리하고, 테스트는 모든 process command line에 대한 보수적 ambient
  guard 뒤에만 zero-run을 호출하며, runner script 탐색 범위를 첫 standalone `--` 앞으로
  제한했다. 첫 수정 재리뷰의 잔여 P1(python.exe에만 한정된 ambient guard)도 all-process로
  정정했다. 이후 focused actual-process PASS, full offline checkpoint PASS, diff-check PASS,
  최종 독립 리뷰 P0/P1 0이다. 최종 pause 28,150 B
  `2616402b...22bbce`, test 37,269 B `0bea228c...ebaf0`, AIRI trainer/runner 0이다.
  6개 SSoT receipt를 포함한 exact 8-file batch stage/commit/push 전에는 GPU/E2를 실행하지 않는다.
- `20260822-194410-p0-safe-pause-auto-discovery-offline-receipt`: RunDir 생략 자동 탐지를
  구현했다. live Windows command line을 `CommandLineToArgvW` Unicode로 파싱해 standalone
  `--` 앞의 exact `--run-dir`/`--run-id`만 허용하고, strict current→previous state,
  runner source SHA, state runner PID/creation/executable/command identity와 active status를
  모두 결속한다. 정확히 1개만 선택하며 0개는 prompt 없이 nonzero, 복수는 run ID/RunDir
  후보를 표시하고 nonzero다. manual RunDir와 기존 checkpoint/ack/artifact/
  `SAFE_TO_POWER_OFF` gate는 유지했다. 첫 actual-process 회귀는 Unicode marshaling 누락으로
  정상 runner 2개를 0개로 오판해 FAIL했고 이를 receipt로 남겨 `CharSet.Unicode`로
  정정했다. 이후 process-identity spoof, 0/1/multiple, corrupt-current/valid-previous를
  포함한 `test-airi-training-durability.ps1` exit 0 PASS, `test-current-checkpoint.ps1`
  exit 0 PASS, repo diff-check exit 0이다. pause 27,927 B
  `db9a72a...34d81`, test 36,383 B `04a9fc8...bc33c`, AIRI trainer/runner 0이다.
  당시 독립 review와 6-doc receipt·commit/push 전에는 controlled GPU/E2를 실행하지 않았다.
- `20260822-192728-p0-safe-pause-auto-discovery-intent`: 사용량 초기화 후 user는
  `pause-airi-safely.ps1`을 매개변수 없이 쓸 수 있도록 개선한 뒤 goal을 계속하라고
  요청했다. SSoT 전량 재독과 fresh 감사에서 goal active, HEAD=origin/main `e3a8819`,
  worktree clean, AIRI trainer/runner 0, E2 adapter/report와 old planned P0-B root 부재다.
  자동 탐지는 live `durable_training_runner.py` command line에서 exact `--run-dir`/
  `--run-id`를 파싱하고 run-state current→previous strict schema, runner PID/creation/
  executable/command hashes, active status를 모두 결속한다. 0개면 prompt 없이 명확히
  중단, 2개 이상이면 안전한 후보만 표시하고 거부하며 mtime/newest/광범위 재귀 탐색은
  금지한다. manual `-RunDir`과 기존 checkpoint/ack/`SAFE_TO_POWER_OFF` 검증은 유지한다.
  owned pause/test 구현·회귀·독립 감사·commit/push 전에는 GPU/E2를 시작하지 않는다.
- `20260822-191844-p0b-final-receipt-commit-push-intent`: actual docs push receipt의
  exact 2-doc boundary, continuity PASS, repo diff-check exit 0 뒤 `git add` exit 0.
  staged 2, unstaged 0, untracked 0, cached diff-check exit 0이다. 이 stage receipt를
  다시 stage하고 동일 2/0/0과 cached diff-check를 확인한 뒤 exact
  `git commit -m "docs: record expected gate push"`, `git push origin main` 순서로
  실행한다. 실패하면 local 상태를 보존하고 GPU/E2를 실행하지 않는다.
- `20260822-191746-p0b-doc-receipt-push-receipt`: exact `git push origin main`
  exit 0, `8cd69b5..248e548 main -> main`. 이후 HEAD=origin/main
  `248e5481b50658ecd6da6d4bc9675f7ff3971d77`, AIRI trainer/runner와 Ollama 0이고
  이 actual push receipt용 WORKING-STATE/roadmap log 두 파일만 dirty다. expected-run
  gate 구현과 6개 장기 SSoT receipt는 origin/main에 durable하다. 두 문서 final
  receipt를 focused 검증·commit/push해 clean boundary를 만든 뒤에만 fresh controlled
  GPU intent로 이동하며 E2는 계속 금지한다.
- `20260822-191705-p0b-doc-receipt-push-intent`: final restage 뒤 staged 6,
  unstaged 0, untracked 0, boundary diff 0, cached diff-check exit 0. exact
  `git commit -m "docs: record expected GPU gate receipt"` exit 0, commit
  `248e5481b50658ecd6da6d4bc9675f7ff3971d77`, 6 files, 102 insertions/
  30 deletions이다. commit 직후 worktree clean, local main은 origin/main `8cd69b5`보다
  1 ahead, AIRI trainer/runner 0이다. 다음 exact 상태 변경은 `git push origin main`;
  실패하면 local commit과 receipt 문서를 보존하고 GPU/E2를 실행하지 않는다.
- `20260822-191630-p0b-doc-receipt-commit-intent`: exact 6-doc `git add` exit 0.
  staged 6, unstaged 0, untracked 0, cached diff-check exit 0이다. 이 stage receipt를
  담은 WORKING-STATE/roadmap log만 다시 stage하고 동일 6/0/0과 cached diff-check를
  확인한 뒤 exact `git commit -m "docs: record expected GPU gate receipt"`을
  실행한다. commit 실패 시 push/GPU/E2를 실행하지 않고 staged 배치를 보존한다.
- `20260822-191600-p0b-doc-receipt-ready-stage-intent`: P1 정정 뒤 fresh root
  검증은 changed 6, staged/untracked 0, boundary diff 0, continuity PASS, repo
  diff-check exit 0이다. 독립 재감사는 root `NEXT-SESSION.md` 존재, exact diff 6,
  HEAD=origin/main `8cd69b5`, current transaction과 active/adoption/P0-before-E2/
  GPU-E2-zero 경계를 확인해 P0 0/P1 0 `READY`다. 이는 문서 stage/commit/push만
  허용한다. 다음 상태 변경은 exact 6-doc `git add`; staged 6·unstaged 0·untracked 0과
  cached diff-check를 확인하며 실패하면 commit/push/GPU/E2를 실행하지 않는다.
- `20260822-191445-p0b-doc-audit-p1-correction`: 6-doc validation은 exact changed 6,
  staged/untracked 0, boundary diff 0, continuity PASS, repo diff-check exit 0,
  forbidden filename/secret-value hit 0이다. 첫 독립 문서 감사는 P0 0/P1 2,
  `NOT READY`. P1 중 actual diff 3/NEXT 부재 주장은 root fresh read-only
  `NEXT_EXISTS=True`, resolved root path, `git diff HEAD` exact 6으로 반증됐다. 그러나
  active transaction의 recovery가 stale `f2c9a46`/3-file을 가리킨 P1은 확정됐다.
  live scope를 HEAD=origin/main `8cd69b5`와 exact 6-doc receipt로 정정했으며, 같은
  담당의 fresh 재감사에서 P0/P1 0 전에는 stage/commit/GPU/E2로 이동하지 않는다.
- `20260822-191126-p0b-expected-gate-push-receipt-doc-intent`: exact
  `git push origin main` exit 0, `f2c9a46..8cd69b5 main -> main`. 이후
  HEAD=origin/main `8cd69b5f455bd41b48faa5ed6e9cac1af00f8908`, AIRI trainer/runner와
  Ollama process 0이며 post-push receipt용 WORKING-STATE/roadmap log 두 파일만
  dirty다. expected external input/config/seed/batch/accumulation/single-first-pause gate
  구현은 origin/main에 durable하지만 controlled GPU paired run과 실제 E2 속도
  ≤600초 실측은 0이다. 이 receipt를 6개 SSoT에 반영해 focused continuity/diff/security,
  exact docs commit/push를 완료하기 전에는 GPU/E2를 실행하지 않는다.
- `20260822-191052-p0b-expected-gate-push-intent`: final restage 뒤 staged 4,
  unstaged 0, untracked 0, boundary diff 0, cached diff-check exit 0. exact
  `git commit -m "fix: bind GPU equivalence to expected run"` exit 0, commit
  `8cd69b5f455bd41b48faa5ed6e9cac1af00f8908`, 4 files, 405 insertions/
  27 deletions이다. commit 직후 worktree clean, local main은 origin/main `f2c9a46`보다
  1 ahead이고 AIRI trainer/runner 0이다. 다음 exact 상태 변경은
  `git push origin main`; 실패하면 local commit과 receipt 문서를 보존하고 GPU/E2를
  실행하지 않는다.
- `20260822-191020-p0b-expected-gate-commit-intent`: full-offline receipt 두 문서의
  exact `git add` exit 0. staged 4, unstaged 0, untracked 0, cached diff-check exit 0이다.
  이 stage receipt를 담은 두 문서만 다시 stage하고 동일 4/0/0과 cached diff-check를
  확인한 뒤 exact `git commit -m "fix: bind GPU equivalence to expected run"`을
  실행한다. commit 실패 시 push/GPU/E2를 실행하지 않고 staged 배치를 보존한다.
- `20260822-190933-p0b-expected-gate-full-offline-pass`: compact 뒤 지정 SSoT 5종을
  순서대로 전체 재독하고 goal `active`를 확인했다. 실제 HEAD=origin/main `f2c9a46`,
  expected gate 네 파일만 staged, unstaged/untracked 0, source/chat/base와 E1 3종의
  크기·SHA exact, E2/T3/campaign 부재, E2 로그 각 0 bytes, AIRI trainer/runner 0을
  대조했다. 중복 실행하지 않고 기존 exec session `45999`를 회수한 결과
  `test-current-checkpoint.ps1` exit 0, 최종 `Current checkpoint contract: PASS
  (offline synthetic ASAR only; no installed archive/service/model access)`, 종료 뒤 관련
  PID 0이다. 이 receipt를 담은 WORKING-STATE/roadmap log를 재stage해 동일 4/0/0과
  cached diff-check를 확인한 뒤 `fix: bind GPU equivalence to expected run`으로
  commit/push한다. 실패하면 controlled GPU/E2를 실행하지 않는다.
- `20260822-190548-p0b-expected-gate-staged-full-offline-intent`: exact 4-file
  `git add` exit 0. staged 4, unstaged 0, untracked 0, cached diff-check exit 0이고
  최초 staged 통계는 368 insertions/24 deletions다. 이 receipt를 담은 WORKING-STATE와
  roadmap log만 재stage하고 동일 4/0/0과 cached diff-check를 확인한 뒤 exact
  `.\test-current-checkpoint.ps1`을 실행한다. 완료 조건은 exit 0과 최종 offline
  checkpoint PASS, 관련 PID 0이다. 실패하면 commit/push/GPU/E2를 실행하지 않는다.
- `20260822-190523-p0b-expected-gate-prestage-pass`: fresh pre-stage 감사는 exact
  4 changed, boundary diff 0, untracked 0, repo 기본 diff-check exit 0/whitespace error 0,
  금지 산출물 filename 0, 비밀 값 형태 content hit 0이다. verifier/test SHA는
  `6c64cd0c...7439` 41,449 B / `da797b70...ee0e` 23,774 B다. 다음 상태 변경은
  WORKING-STATE/roadmap log/verifier/test 네 경로만 exact `git add`하고 staged 4·
  unstaged 0·untracked 0 및 cached diff-check를 확인하는 것이다. 실패하면 full offline/
  commit/push/GPU/E2를 실행하지 않는다.
- `20260822-190443-p0b-expected-gate-ready-prestage`: 최신 bytes 독립 read-only
  재감사는 repaired baseline control, expected manifest/config/seed/batch/accumulation,
  단일 safe event/history, latest 결속, 고정 최소 4구간/≤600초, exact state/tensor와
  fresh non-replacing receipt를 확인해 P0 0/P1 0, `READY`다. static 감사로 테스트/GPU는
  실행하지 않았고 root fresh Python `73 passed, 2 skipped`, PowerShell PASS,
  diff-check PASS, 관련 PID 0이 실행 근거다. 다음은 WORKING-STATE/roadmap log/verifier/
  test exact 4개 배치의 boundary·security·SHA preflight, exact stage/cached diff-check,
  `test-current-checkpoint.ps1`이다. 실패하면 commit/push/GPU/E2를 실행하지 않는다.
- `20260822-190232-p0b-expected-gate-ready-reaudit`: exact identity가 유지된 Ollama
  app PID 26872를 먼저 종료하고 남은 serve PID 24004를 종료했다. 종료 대기 뒤
  `ollama.exe`/`ollama app.exe` process 0이다. AIRI trainer/runner PID도 0이며 GPU/E2
  실행은 0이다. 최신 verifier는 actual baseline의 empty regular control을 허용하되
  entry/link/Windows reparse를 거부하고, root 통합 `73 passed, 2 skipped`, actual-process
  PowerShell PASS다. 이전 독립 감사 P0 1의 exact 수정 bytes를 재감사해 P0/P1 0
  `READY` 전에는 full offline·stage/commit/GPU/E2로 이동하지 않는다.
- `20260822-190158-p0b-ollama-app-restart-correction`: baseline control 수정 뒤
  actual-process PowerShell durability exit 0/PASS, AIRI trainer/runner/planned-root/fake
  관련 PID 0이다. 그러나 `ollama.exe` PID 24004가 creation 18:52:58 KST로 존재했고,
  parent는 `ollama app.exe` PID 26872, creation 18:50:22 KST, hidden fast-startup이다.
  둘 다 첫 `ollama ps` 부작용 시각에 생성됐으며 앞서 child serve PID 16312만 종료한 뒤
  app이 새 child를 재생성한 것이다. localhost `/api/ps`는 `models: []`로 GPU 모델 적재
  0을 확인했다. 따라서 `185302`의 순간 Ollama process 0은 맞지만 이후 자동 재기동을
  놓쳤고 `185826`의 서비스 0 표현은 부정확했다. 관측 사실로 정정한다. exact parent/app
  PID 26872와 child/serve PID 24004 identity를 재검증해 parent부터 종료한 뒤 child를
  종료하고 Ollama process 0을 확인한다. GPU trainer/E2는 계속 0이다.
- `20260822-190053-p0b-baseline-control-fix-python-pass`: baseline control은 부재 또는
  fixed-local/non-reparse empty regular directory만 허용하고 어떤 entry도 거부하도록
  수정했다. pass fixture가 실제 empty control을 만들고 orphan entry/link fault를 추가했다.
  existing `_require_local_fixed_path`가 Windows junction/reparse attributes도 차단한다.
  핀된 Python pycompile exit 0, 4-suite exit 0,
  `73 passed, 2 skipped in 17.08s`. 기존 CUDA-box gpu-less skip과 Windows test symlink
  권한 조건 skip이며 제품 reparse 검사는 직접 결속됐다. 다음 exact 검증은 actual-process
  PowerShell durability이며 PASS/PID 0 뒤 최신 bytes 독립 재감사를 다시 요청한다.
- `20260822-185917-p0b-baseline-control-false-reject`: root가 trainer
  `run_dir.mkdir` 직후 `(run_dir / "control").mkdir(exist_ok=True)`를 모든 run에
  수행하는 실제 계약을 대조했다. 새 `_require_no_safe_pause_evidence`는
  `os.path.lexists(control)` 자체를 거부해 실제 uninterrupted baseline이 항상 실패한다.
  따라서 직전 Python/PowerShell PASS는 synthetic pass fixture가 빈 control을 만들지 않은
  회귀 공백 때문에 valid-run readiness 근거가 아니다. GPU/E2는 0이다. baseline은 control
  부재 또는 **빈 regular non-link directory**만 허용하고 어떤 entry/link/history도
  거부하며, pass fixture가 실제 빈 control을 만들도록 수정해 focused+전체 통합을 다시
  실행한다. 수정·독립 P0/P1 0 전에는 full offline/commit/GPU/E2 금지를 유지한다.
- `20260822-185826-p0b-expected-gate-integration-pass-audit`: exact identity와 child 0을
  재확인한 뒤 leaked preflight PowerShell PID 19300을 `Stop-Process -Force`로 종료했다.
  종료 대기 뒤 PID 부재, trainer/runner/planned root/fake trainer 관련 process 0이다.
  최신 통합 receipt는 Python `72 passed, 1 skipped`, actual-process PowerShell PASS다.
  GPU·서비스·E2는 0이다. verifier/test 최신 bytes를 독립 read-only 재감사해 expected
  input/config/seed/batch/accumulation/pause gate와 기존 exact/atomic 계약에 P0/P1 0을
  받기 전에는 full offline·stage/commit/GPU/E2로 이동하지 않는다.
- `20260822-185752-p0b-preflight-shell-leak`: actual-process PowerShell durability
  contract는 exit 0, `AIRI training durability contract: PASS`. 그러나 종료 후 related
  PID 감사에서 trainer/runner가 아니라 첫 18:50 통합 preflight 명령 자체인 PowerShell
  PID 19300이 도구 timeout 뒤에도 남은 것을 발견했다. exact executable은 Windows
  PowerShell, creation `2026-08-22T18:50:17.0324210+09:00`, command에는 pinned planned
  root와 `OLLAMA_PS_BEGIN` 이후 CUDA 조회가 결속돼 있고 direct child 0이다. 이는
  `ollama ps` auto-start 부작용과 같은 실패 명령의 supervisor shell 누수이므로 이 exact
  PID만 종료하고 fresh AIRI trainer/runner/preflight PID 0을 확인한다. 확인 전에는
  PowerShell PASS를 전체 통합 완료로 승격하거나 독립 감사/GPU/E2로 이동하지 않는다.
- `20260822-185705-p0b-expected-gate-python-pass`: 핀된 Python 3.12의 checkpoint/
  trainer/runner/verifier py_compile exit 0, 4-suite focused exit 0,
  `72 passed, 1 skipped in 17.21s`. skip은 CUDA 장비에서 gpu-less refusal 경로가
  비적용인 기존 조건이다. GPU·서비스·모델 output은 0이다. 다음 exact 명령은
  `powershell -NoProfile -ExecutionPolicy Bypass -File
  .\test-airi-training-durability.ps1`; exit 0/PASS와 관련 PID 0이 완료 조건이며
  실패하면 GPU/E2를 계속 금지한다.
- `20260822-185558-p0b-expected-gate-integration-intent`: 두 owned 파일 worker
  결과는 pycompile PASS, focused `17 passed, 1 skipped`, owned diff-check PASS다.
  root diff 검토에서 expected input manifest SHA, canonical full config SHA, seed/batch/
  accumulation, safe-pause microstep/optimizer step, exactly one event/history triple과 receipt
  결속을 확인했다. actual worktree는 WORKING-STATE+verifier+test 세 modified뿐이며 GPU/
  서비스/E2 실행은 0이다. root는 핀된 Python의 4-suite와 actual-process PowerShell을
  fresh 실행하고 최신 독립 P0/P1 0 전에는 commit/GPU/E2로 이동하지 않는다.
- `20260822-185441-p0b-preflight-partial-verifier-blocker`: quoting을 단순화한 핀된
  Python CUDA env 조회 exit 0. Python 3.12.13, Torch 2.7.0+cu128, CUDA runtime 12.8,
  transformers 4.48.2, peft 0.14.0, bitsandbytes 0.50.1, RTX 3060 Ti capability 8.6,
  total 8,589,410,304 bytes, PyTorch 조회 free 7,472,152,576 bytes다. trainer 적용 전
  deterministic/TF32 기본값은 고정값과 다르지만 `--deterministic-validation`이 이를
  fail-closed로 설정하고 pins에 기록한다. 별도 NVIDIA 조회는 driver 591.74, total
  8192 MiB, used/free 3942/4083 MiB, utilization 27%, 45°C였고 Ollama process 0으로
  복구됐다. 그러나 독립 설계 감사에서 현재 verifier가 두 run의 input/config 동일성만
  보고 계획된 input manifest SHA, 전체 training config SHA, seed/batch/gradient
  accumulation과 단일 첫 optimizer 경계 safe-pause를 외부 expected 값으로 강제하지
  않는 증거 결함을 확인했다. 따라서 preflight는 부분 PASS지만 GPU GO는 아니다.
  verifier/test 두 파일에 expected gate와 mismatch fault를 추가해 offline PASS·독립
  P0/P1 0·commit/push한 뒤 fresh target preflight를 반복한다. 실제 E2와 같은 batch 1,
  grad accumulation 16을 고정하고, timing 표본은 최소 4구간 턱걸이 320 대신
  max 480 microsteps/30 optimizer steps/checkpoint K=5의 정상 6구간으로 잡는다.
- `20260822-185338-p0b-python-env-quoting-failure`: 핀된 Python 환경 조회는
  약 2.3초 뒤 exit 1, `NameError: name 'python' is not defined`. 인라인 JSON key
  quoting이 PowerShell→Python 전달에서 벗겨진 조회 명령 결함이며 학습·output은 0이다.
  CUDA/package 값을 얻지 못했으므로 preflight PASS로 인정하지 않는다. Python dict key를
  single quote로 고정한 단순 명령으로 한 번 fresh 재실행하고, 또 실패하면 blocker로
  남기며 GPU를 시작하지 않는다.
- `20260822-185302-p0b-ollama-side-effect-restored`: 기록된 PID 16312가
  `ollama.exe`, creation `2026-08-22T18:50:23.7479920+09:00`, command suffix
  `ollama.exe serve`와 exact 일치함을 확인한 뒤 `Stop-Process -Id 16312 -Force`
  exit 0. 종료 대기 뒤 PID 부재, 전체 `ollama.exe` process 0이다. 이 프로세스는 직전
  preflight가 자동 기동한 side effect이며 그 exact 대상만 원상 복구했다. GPU trainer/
  runner/E2는 계속 0이다. 다음은 NVIDIA 조회와 핀된 Python 환경 확인을 별도 실행한다.
- `20260822-185230-p0b-preflight-ollama-side-effect`: 첫 controlled GPU read-only
  preflight는 HEAD=origin/main `f2c9a46`, WORKING-STATE 단독 diff, fresh planned D:
  root/targets, fixed/non-reparse C: dataset·D: model/Python, dataset/base/config와 6개
  code SHA, D: free 64,238,112,768 bytes, 관련 trainer/runner 0까지 확보했다. 그러나
  `ollama ps`가 단순 조회 대신 `ollama.exe serve` PID 16312를 18:50:23 KST에 자동
  기동했고 명령은 30초 창에서 후속 NVIDIA/Python env receipt 없이 중단됐다. 따라서
  이 명령 전체를 완결 PASS로 인정하지 않는다. GPU trainer/E2는 0이다. 생성 시각·exe·
  exact command가 일치하는 PID 16312만 `Stop-Process`로 종료하고 부재를 확인한 뒤,
  NVIDIA와 핀된 Python CUDA/package env를 `ollama ps` 없이 분리 검사한다. 종료 identity가
  달라졌으면 손대지 않고 blocker로 기록한다.
- `20260822-184706-p0b-controlled-gpu-readonly-design`: final receipt commit
  `f2c9a46dfb0b15b1e1a6340c84167b0a5f009119`을 origin/main에 push했다
  (`74d8999..f2c9a46 main -> main`). 이후 HEAD=origin/main, worktree clean,
  AIRI trainer/runner 0을 확인했다. P0-B gate code·SSoT receipt milestone은 durable하며
  다음 단계는 GPU 실행이 아닌 exact paired command의 read-only 교차 감사다. controlled
  GPU와 실제 E2 속도 구간은 여전히 0이므로 P0-B/E2를 승격하지 않는다.
- `20260822-184552-p0b-final-receipt-staged`: exact 2-doc `git add` exit 0.
  staged 2, unstaged 0, untracked 0, cached diff-check exit 0이다. 이 WORKING-STATE
  stage receipt만 재stage하고 동일 2/0/0과 cached diff-check를 확인한 뒤 exact
  `git commit -m "docs: record P0-B gate push"`를 실행한다. commit 실패 시
  push/GPU/E2를 실행하지 않고 staged 배치에서 복구한다.
- `20260822-184529-p0b-final-receipt-validation`: actual `74d8999` push receipt의
  변경 경로 exact 2, boundary diff 0, untracked 0, focused continuity exit 0/PASS,
  repo 기본 diff-check exit 0/whitespace error 0이다. 다음은 두 문서만 exact stage하고
  staged 2·unstaged 0·untracked 0 및 cached diff-check를 확인한 뒤 기록된 final receipt
  commit/push를 수행한다. 실패하면 controlled GPU/E2를 시작하지 않는다.
- `20260822-184446-p0b-receipt-doc-pushed`: exact `git push origin main` exit 0,
  `e970cf7..74d8999 main -> main`. 이후 HEAD=origin/main
  `74d8999bdfba7cc1bf45749b9e110379853b8bac`, AIRI trainer/runner 0이고
  post-commit receipt용 WORKING-STATE와 roadmap log 두 파일만 dirty다. P0-B evidence
  gate code와 장기 SSoT receipt는 origin/main에 durable하다. controlled GPU paired run과
  실제 E2 속도 ≤600초 실측은 여전히 0이므로 P0-B/E2 완료로 승격하지 않는다. 이 actual
  push receipt 두 문서를 focused 검증·final receipt commit/push해 clean GPU preflight
  경계를 만든다.
- `20260822-184352-p0b-receipt-doc-commit-push-intent`: 재stage 뒤 staged 6,
  unstaged 0, untracked 0, cached diff-check exit 0 상태에서 exact
  `git commit -m "docs: record GPU equivalence gate receipt"` exit 0. commit
  `74d8999bdfba7cc1bf45749b9e110379853b8bac`, 6 files, 107 insertions/
  32 deletions이다. commit 직후 worktree clean, local main은 origin/main
  `e970cf7`보다 1 ahead다. 다음 exact 상태 변경은 `git push origin main`; 실패 시
  이 commit과 post-commit receipt 문서를 보존하고 controlled GPU/E2를 실행하지 않는다.
  성공 뒤 HEAD=origin/main·AIRI PID 0을 대조한 뒤 controlled GPU intent를 별도로 쓴다.
- `20260822-184302-p0b-receipt-doc-staged`: exact 6-doc `git add` exit 0.
  staged 6, unstaged 0, untracked 0, cached diff-check exit 0이고 최초 staged 통계는
  99 insertions/32 deletions다. 이 receipt를 담은 WORKING-STATE와 roadmap log만
  재stage하고 staged 6·unstaged 0·untracked 0 및 cached diff-check를 다시 확인한다.
  통과하면 exact `git commit -m "docs: record GPU equivalence gate receipt"`를
  실행한다. commit 실패 시 push/GPU/E2를 실행하지 않고 staged 배치에서 복구한다.
- `20260822-184229-p0b-receipt-doc-validation`: P0-B implementation push receipt와
  controlled GPU 미실행 경계를 SSoT 6종에 반영했다. 변경 경로 exact 6,
  untracked 0, boundary diff 0, focused `test-airi-work-continuity.ps1` exit 0/PASS,
  repo 기본 diff-check exit 0/whitespace error 0, 금지 산출물 filename 0, 비밀 값 형태
  content hit 0이다. 다음 상태 변경은 이 6개만 exact stage하고 staged 6·unstaged 0·
  untracked 0 및 cached diff-check를 재확인하는 것이다. 통과하면
  `git commit -m "docs: record GPU equivalence gate receipt"`, `git push origin main`
  순서로 실행하며 하나라도 실패하면 controlled GPU/E2를 시작하지 않는다.
- `20260822-184022-post-compact-p0b-push-reconcile`: 지정 SSoT 5종을 순서대로
  전체 재독하고 goal `active`를 확인했다. 실제 HEAD=origin/main
  `e970cf7e4c3a4685fd8bce23c659a1c9aa93c21e`; push 출력은
  `59a2363..e970cf7 main -> main` exit 0이다. AIRI trainer/runner 0이며 GPU에는
  OS/app 프로세스가 있지만 식별 가능한 AIRI workload는 0이다. source/chat/base와
  E1 adapter/config/report 크기·SHA exact, E2 adapter/report/durable run과 T3/campaign
  부재, E2 stdout/stderr 각 0 bytes를 대조했다. 실제 worktree는 이전 receipt용
  WORKING-STATE와 roadmap log 두 파일만 dirty여서 문서의 local-ahead/10-file 구현
  상태를 관측 사실로 먼저 정정한다. implementation `e970cf7`은 durable하지만 controlled
  GPU 동등성 및 실제 E2 속도 checkpoint ≤600초 실측은 아직 0이므로 P0-B/E2를 완료로
  승격하지 않는다. 다음은 SSoT 6-doc receipt 검증·commit/push다.
- `20260822-183559-p0b-implementation-commit-push-intent`: exact staged 배치의
  `git commit -m "feat: add GPU training equivalence gate"` exit 0. commit
  `e970cf7e4c3a4685fd8bce23c659a1c9aa93c21e`, 10 files, 1,703 insertions/
  52 deletions, verifier/test 신규 2개다. commit 직후 worktree clean, local main은
  origin/main `59a2363`보다 1 ahead이고 AIRI trainer/runner PID 0이다. 다음 exact
  상태 변경은 `git push origin main`; 실패하면 이 local commit과 receipt 문서를
  보존하고 controlled GPU/E2를 실행하지 않는다. 성공 뒤 HEAD=origin/main/PID 0을
  대조하고 long-lived SSoT receipt 문서의 별도 commit/push를 완료한 뒤에만 controlled
  GPU intent로 이동한다.
- `20260822-183502-p0b-full-offline-pass-commit-intent`: exact staged 10/unstaged 0/
  untracked 0과 cached diff-check PASS 상태에서 `test-current-checkpoint.ps1` exit 0,
  최종 `Current checkpoint contract: PASS (offline synthetic ASAR only; no installed
  archive/service/model access)`. continuity, actual-process durability, manifest/source/
  entrypoint와 기존 Python/Node/PowerShell 핵심 회귀가 모두 PASS했다. 종료 뒤 관련
  Python PID 0, staged 10/0/0이며 최초 staged 통계는 1,687 insertions/52 deletions다.
  직전 frontmatter와 두 수동 checkpoint ID를 실제 clock보다 최대 약 2분 앞선
  `18:36`/`18:37`로 적은 문서 오차를 실제 `Get-Date 18:35:02`로 정정한다. 작업·receipt
  순서는 변하지 않으며 이 checkpoint가 권위 시각이다. 이 receipt 문서들을 재stage해
  staged 경계/diff-check를 다시 확인한 뒤 exact `git commit -m
  "feat: add GPU training equivalence gate"`를 실행한다. commit 실패 시 push/GPU/E2를
  실행하지 않고 staged 배치에서 복구한다.
- `20260822-1837-p0b-staged-full-offline-intent`: exact 10-file `git add` exit 0.
  최초 stage receipt는 staged 10, unstaged 0, untracked 0이고 cached diff-check exit 0/
  whitespace error 0이다. 이 receipt를 담은 WORKING-STATE만 다시 stage한 뒤 동일
  10/0/0 경계와 cached diff-check를 재검증한다. 다음 exact 명령은
  `.\test-current-checkpoint.ps1`; 새 verifier test와 P0-A checkpoint/runner tests가
  staged tracked inventory 및 CI training shard에 모두 보이는 상태여야 한다. 완료 조건은
  exit 0과 최종 `Current checkpoint contract: PASS`, 관련 PID 0이다. 실패하면 commit/
  push/GPU/E2를 실행하지 않고 stage를 보존해 수리한다.
- `20260822-1836-p0b-prestage-pass-stage-intent`: `core.quotePath=false`로 Unicode
  경로를 보존한 fresh pre-stage 감사 exit 0. exact 10개 경로, boundary diff 0,
  금지 산출물 filename 0, 비밀 값 형태 content hit 0, repo 기본 diff-check exit 0/
  whitespace error 0이다. 핵심 구현 SHA는 verifier `c5e2075c...fd99`, verifier test
  `15c5ef6f...b6ad`, runner `8cd24b45...1d803`, runner test `13ba0ba5...392b9`,
  trainer `d61c167c...6ad8e`, trainer test `5cc55944...ccf65`, PowerShell contract
  `826788f3...b017c`, CI workflow `e5116e7d...f044`다. 다음 상태 변경은 이 10경로만
  exact `git add --`하고 staged 10·unstaged 0·untracked 0 및 cached diff-check를
  확인하는 것이다. 실패하면 commit/push/full offline/GPU/E2를 실행하지 않는다.
- `20260822-1835-prestage-quotepath-audit-failure`: 첫 pre-stage 감사 스크립트는
  stage/Git mutation 없이 종료됐지만 Git 기본 `core.quotePath`가 두 한글 문서 경로를
  quoted octal 문자열로 반환해 `Compare-Object` boundary diff 4와 두 파일의
  `Illegal characters in path` ReadAllText/Get-FileHash 오류를 냈다. 따라서 출력된
  secret hit 0과 boundary 판정은 완결 receipt로 인정하지 않는다. 별도로 실행된 repo
  기본 diff-check는 exit 0/whitespace error 0이고 나머지 8개 SHA는 읽혔다. exact 같은
  10경로 배열을 유지하되 `git -c core.quotePath=false diff --name-only`와 동일 untracked
  조회로 Unicode 실제 경로를 받아 boundary/security/SHA를 fresh 재실행한다. 통과 전에는
  stage/commit/push/GPU/E2를 실행하지 않는다.
- `20260822-1833-p0b-ready-prestage-audit-intent`: 최신 독립 read-only 재감사는
  closed safe-pause inventory, non-replacing receipt, fixed-local/non-reparse 5-path와
  mutable publication same-volume 경계를 확인해 P0 0/P1 0, controlled GPU `READY`다.
  static audit로 테스트/Git/GPU는 실행하지 않았고 직전 fresh 통합
  `68 passed, 1 skipped`, PowerShell PASS, diff-check PASS, PID 0이 실행 근거다.
  다음은 현재 exact 10개 경로의 status/diff/security/SHA preflight다. 통과하면 exact
  10-file `git add`, staged 경계와 `git diff --cached --check`를 검증한 상태에서
  `test-current-checkpoint.ps1`을 실행한다. 새 untracked verifier test는 staged여야
  `git ls-files` CI manifest gate가 보므로 staging 전 full offline은 유효 근거가 아니다.
  실패 시 stage/commit/push/GPU/E2를 중단하고 현 배치에서 수리한다.
- `20260822-1831-p0b-second-integration-pass-reaudit`: closed control/history와
  non-replacing receipt fault 보강 뒤 pycompile exit 0, 4-suite focused exit 0,
  `68 passed, 1 skipped in 17.90s`; actual-process PowerShell durability exit 0/PASS.
  종료 뒤 관련 Python PID 0이고 repo 기본 diff-check exit 0/whitespace error 0
  (LF→CRLF 경고만)이다. 독립 감사 담당에게 최신 bytes와 명시된 immutable-input 대
  mutable-publication volume 경계를 다시 판정시킨다. P0/P1 0 `READY`와 staged full
  offline 전에는 GPU/E2를 시작하지 않는다.
- `20260822-1829-p0b-reaudit-fix-retest-intent`: 최신 독립 재감사는 이전 event,
  archive cutpoint, exact fixed gate, TF32/CUDA/quantization, timing, payload/comparator,
  safe load를 해소로 확인했지만 P0 2/P1 1, `NOT READY`로 판정했다. 확정 P0는
  verifier가 완전한 history triple과 동시에 남은 live controls 및 extra/orphan history를
  거부하지 않은 점이고, P1은 receipt freshness 확인 뒤 다른 writer의 파일을 덮거나
  실패 cleanup에서 지울 수 있는 race다. verifier가 control root를 history-only,
  history를 exact canonical triple inventory로 닫고 live 3종을 `lexists`로 거부하게
  했으며, receipt는 same-parent staged fsync 뒤 Windows non-replacing write-through move/
  POSIX exclusive link로 fresh publish해 타 파일을 덮거나 지우지 않는다. 나머지 P0는
  dataset/model까지 run과 같은 drive여야 한다는 조건부 해석이다. 이는 read-only pinned
  input은 서로 다른 fixed local volume을 허용하고 mutable run/output/report만 same-volume
  원자 승격한다는 설계이므로 양쪽 코드에 명시해 재판정을 요청한다. 최신 verifier/test
  SHA는 `36487/c5e2075c...fd99`, `16856/15c5ef6f...b6ad`; runner/trainer는 주석 포함
  `60565/8cd24b45...1d803`, `50680/d61c167c...6ad8e`. exact 다음 명령은 pycompile+
  4-suite focused와 PowerShell durability이며, PASS 뒤 독립 재감사를 반복한다.
- `20260822-1825-p0b-integration-pass-reaudit-intent`: 수정된 actual-process
  `test-airi-training-durability.ps1` exit 0, `AIRI training durability contract: PASS`.
  종료 뒤 trainer/runner/fake trainer 관련 Python PID 0이며 actual worktree는 기록된
  8 modified+2 untracked의 10개 경로와 일치한다. 최신 통합 증거는 Python
  `63 passed, 1 skipped`와 PowerShell PASS다. 직전 P0-B 감사 담당에게 최신 전체 diff를
  read-only로 재감사시켜 event 최신 결속/전원차단 cutpoint/fixed exact gate/TF32·path/
  timing·payload receipt/안전 load 각각의 해소 여부와 새 P0/P1을 판정받는다. P0/P1 0
  `READY` 전에는 full offline·stage/commit이나 GPU/E2로 이동하지 않는다.
- `20260822-1824-powershell-fixture-retry-intent`: 실패 뒤 관련 process 필터는
  검사 명령 자신의 PowerShell 외 AIRI trainer/runner 0이고, default contract가 실패
  temp를 정리해 stderr 본문은 남지 않았다. source 검사에서 launcher-case 3곳과
  live-pause 공통 `TrainerArguments`가 새 필수 `--dataset`/`--model-dir` 없이 SHA만
  전달한 동일 fixture 결함을 확인했다. 각 temp case에 regular dataset과 config model
  dir를 만들고 네 argument block에 exact path를 추가했다. 수정된 contract는
  `30311` bytes, SHA `826788f3...b017c`; 실제 worktree는 이 test와 runner test를 포함해
  8 modified+2 untracked, 10개다. exact 다음 명령은 같은 PowerShell durability
  contract이며 exit 0/PASS와 관련 PID 0이 완료 조건이다. 실패 시 이번에는 원인을
  다시 receipt로 기록하고 GPU/E2 금지를 유지한다.
- `20260822-1823-p0b-powershell-launch-failure`: actual-process PowerShell durability
  contract는 약 30초 뒤 exit 1. launcher가 `Durable runner did not publish a verified
  run-state within 30 seconds; launch_shim_exited=True`로 중단했다. 검증된 run-state나
  제품 경로 receipt가 없으므로 PASS/진척으로 승격하지 않는다. 먼저 관련 Python/
  launcher PID와 실패 temp 보존 여부, runner stderr와 exact trainer args를 read-only로
  대조한다. 새 dataset/model-dir 필수 path 계약 누락이면 PowerShell synthetic fixture를
  실제 계약에 맞게 고치고 같은 contract를 재실행하며, 다른 원인이면 해당 fault를 먼저
  수리한다. 성공 receipt·독립 P0/P1 0 전에는 GPU/E2를 계속 금지한다.
- `20260822-1822-p0b-focused-pass-powershell-intent`: fake fixture에 local regular
  dataset과 config model dir exact 인자를 추가한 뒤 동일 pycompile exit 0,
  4-suite focused exit 0, `63 passed, 1 skipped in 17.79s`. 종료 뒤 trainer/runner/
  fake-trainer Python PID 0이다. skip은 CUDA 장비에서 gpu-less refusal 경로가
  비적용인 기존 조건이다. 최신 핵심 SHA는 직전 intent와 같고 runner test만
  `34334/13ba0ba5...92b9`로 바뀌었다. 다음 exact 명령은
  `powershell -NoProfile -ExecutionPolicy Bypass -File
  .\test-airi-training-durability.ps1`; 출력은 system temp synthetic runtime과 console
  receipt이며 contract가 자체 정리한다. exit 0/PASS와 관련 PID 0이 완료 조건이고,
  실패하면 산출물을 진단용으로 보존해 수리하며 독립 P0/P1 0 전에는 GPU/E2를 금지한다.
- `20260822-1821-p0b-focused-fixture-failure`: py_compile exit 0 뒤 최신 4-suite
  focused는 exit 1, `2 failed, 61 passed, 1 skipped in 9.02s`. 두 실패는
  `test_resume_pin_mismatch_preserves_pause_request_and_ack`와
  `test_safe_pause_then_explicit_resume_reaches_atomic_terminal_receipt`가 공통으로
  `missing trainer argument: --dataset`에서 의도된 fake trainer 실행 전에 차단된 것이다.
  runner가 새로 강제한 dataset/model-dir end-to-end path 계약에 기존 `_arguments`
  fixture가 두 인자를 제공하지 않은 테스트 정합 결함이며 archive 제품 경로 판정에는
  도달하지 않았다. fixture가 local regular dataset과 config.json model dir를 만들고
  exact 인자를 전달하도록 고친 뒤 동일 pycompile+4-suite를 재실행한다. PASS receipt와
  독립 P0/P1 0 전에는 GPU/E2를 계속 금지한다.
- `20260822-1820-p0b-blocker-fix-test-intent`: event generation 1부터의 무결한
  연속성+latest/payload 결속, wall/monotonic publish 대조, 고정 600초·최소 4구간·exact
  comparator, full deterministic/TF32·CUDA/quantization pin, safe `weights_only=True`,
  payload/comparator receipt를 verifier에 반영했다. runner는 acceptance-first 포함 모든
  live/history 부분 archive와 동일 중복을 idempotent하게 수렴시키고 dataset/model/output/
  report fixed-path를 선행 검증한다. trainer는 all-history/no-live resume를 no-op으로
  수용하고 dataset/output/report/run fixed/reparse·same-volume을 독립 강제한다. 6개
  핵심 파일의 현재 bytes/SHA는 trainer `50470/4ca2409f...0d05d`, runner
  `60343/7a50bfbb...68e0e`, verifier `33610/105414b5...85764`, 세 test
  `31667/5cc55944...ccf65`, `33996/1480e5a6...d78bf`,
  `14114/b3939f57...4ddaa`다. exact 다음 명령은 위 표의 py_compile+4-suite focused다.
  출력은 console test receipt뿐이며 실패하면 현재 diff에서 수리하고 독립 P0/P1 0,
  offline commit/push 전에는 GPU/E2를 실행하지 않는다.
- `20260822-1811-post-compact-p0b-audit-reconcile`: compact 뒤 지정 SSoT 5종을
  순서대로 전체 재독하고 goal `active`, HEAD=origin/main `59a2363`, 실제 worktree
  6 modified+2 untracked의 8개 경로, AIRI trainer/runner 0을 대조했다. source/chat/base와
  E1 adapter/config/report의 크기·SHA는 exact 일치하고 E2 adapter/report/run-dir,
  T3/campaign은 없으며 기존 E2 stdout/stderr는 각 0 bytes다. GPU에는 비-AIRI OS/app
  process가 있으나 AIRI workload는 0이다. 첫 통합 SHA 명령은 30초 창에서 receipt 없이
  끝나 PASS로 인정하지 않았고, 남은 process 0 확인 뒤 분리 재실행해 위 exact 값을
  확보했다. 최신 독립 P0-B 감사 결과는 P0 5/P1 3, controlled GPU `NOT READY`다:
  최신 checkpoint와 event의 결속/연속성, safe-pause 부분 archive 전원차단 복구,
  comparator의 600초·4구간·exact 고정, TF32 포함 deterministic/환경 pin,
  dataset/model/output/report fixed-volume·reparse 검증이 P0이며 wall/monotonic 대조,
  receipt payload/comparator identity, `weights_only=True`가 P1이다. 직전 compact 직전에
  runner archive idempotency와 runner/trainer fixed-path 검증을 부분 수정했지만 아직
  테스트하지 않았다. 이 관측 정정을 먼저 기록하고 모든 blocker 수리·회귀·독립
  P0/P1 0·commit/push 전에는 controlled GPU/E2를 시작하지 않는다.
- `20260822-1804-full-offline-ci-matrix-failure`: `test-current-checkpoint.ps1`은
  continuity와 actual-process durability를 PASS한 뒤 exit 1. P0-A에서 새로 commit된
  `test_behavior_training_checkpoint.py`, `test_durable_training_runner.py`가 CI Python
  matrix에 없어 manifest gate가 차단했다. 이전 full offline 때는 두 파일이 untracked라
  `git ls-files` 기반 검사가 보지 못한 사후 통합 결함이다. 기존 두 테스트와 이번
  `test_verify_airi_behavior_gpu_equivalence.py`를 training shard에 등록하고, 새 파일을
  intent-to-add가 아닌 최종 exact stage한 상태에서 manifest/full offline을 재실행한다.
  GPU·서비스·E2는 0이며 이 실패를 P0-B 진척으로 승격하지 않는다.
- `20260822-1803-p0b-evidence-integration-pass`: fresh-parent 경로 수리 뒤 trainer+
  verifier focused exit 0, `25 passed, 1 skipped in 6.81s`; exact/tolerance tensor
  dtype 경계 보강 뒤 checkpoint+trainer+runner+verifier 전체 P0 Python exit 0,
  `47 passed, 1 skipped in 17.13s`. actual-process PowerShell durability contract도
  exit 0/PASS다. skip은 CUDA 장비에서 gpu-less refusal 경로가 비적용인 기존 조건이다.
  최신 바이트 독립 P0/P1 감사와 full offline checkpoint, diff/security 전에는 GPU/E2를
  시작하지 않는다.
- `20260822-1800-p0b-integrated-focused-path-failure`: root가 worker verifier를
  통합 검토하며 full pins, deterministic controls, durable-to-durable interval,
  retained safe-pause history, recursive optimizer/RNG/tensor 비교를 보강했다. py_compile
  뒤 첫 통합 focused는 exit 1, `1 failed, 24 passed, 1 skipped in 7.08s`. 유일한
  실패는 fresh receipt의 아직 없는 부모를 reparse 검사기가 즉시 `stat`해 거부한
  경로 검증 결함이다. 가장 가까운 existing ancestor까지 올라가 검사하도록 수정했고
  동일 exact 묶음을 재실행한다. GPU·서비스·E2 실행은 0이며 PASS로 승격하지 않는다.
- `20260822-1755-trainer-focused-no-receipt`: timing/determinism 보강 뒤 py_compile과
  trainer focused pytest를 한 명령으로 시작했으나 도구가 30초 창에서 exit/output/session
  receipt 없이 반환했다. actual pytest redirector/worker PID `4068`/`18228`을 확인해
  중복 실행하지 않고 종료를 기다렸으며 둘 다 종료됐다. exit/test output receipt가
  없으므로 PASS/진척으로 승격하지 않고 동일 focused test를 한 번 fresh 재실행한다.
  GPU·서비스·E2 실행은 0이다. 분리 verifier는 owned 2개 파일, py_compile exit 0,
  focused `3 passed in 0.11s`, diff-check PASS를 보고했으며 root 통합 검토 전이다.
- `20260822-1751-p0b-evidence-code-intent`: 두 독립 read-only 탐색에서 현재 P0-A는
  full-state 복구에 충분하지만 per-generation wall-clock durable receipt와 GPU 정식
  comparator/determinism 정책이 없어 지금 GPU를 돌리면 P0-B 완료 증거가 되지 않음을
  확인했다. 실제 `Get-Date 17:51`보다 앞선 직전 수동 `17:56` live timestamp도 관측값으로
  정정했다. root/worker 소유권, 입력 SHA, offline 명령과 실패 폐쇄 조건을 위 표에
  고정했으며 GPU·서비스·E2 실행은 0이다.
- `20260822-1751-p0a-milestone-pushed`: receipt docs commit
  `59a2363e3340c0e3a59eebf58f7b5f17de29bb1f`, 6 files, 53 insertions/
  15 deletions을 origin/main에 push했다(`6f0c135..59a2363`). 이후 HEAD=origin/main,
  worktree clean, AIRI trainer/runner 0이다. P0-A offline milestone은 durable하게
  완료됐고 다음은 별도 intent가 필요한 P0-B controlled GPU equivalence와 실제 E2
  속도의 ≤10분 checkpoint 간격 실측이다. P0-B receipt 전에는 E2를 시작하지 않는다.
- `20260822-1752-p0a-receipt-doc-validation`: actual implementation push receipt를
  SSoT 6종에 반영한 뒤 focused continuity exit 0/PASS, repo 기본 diff-check exit 0/
  whitespace error 0, 변경 경로 exact 6개, 금지 산출물 filename·비밀 값 형태 content
  hit 0이다. 다음은 exact 6-doc stage와 staged 경계/diff-check, `git commit -m
  "docs: record P0 durability milestone receipt"`, `git push origin main`이다.
  실패 시 P0-A receipt 배치에서 복구하고 controlled GPU/E2를 시작하지 않는다.
- `20260822-1750-p0a-implementation-push-receipt`: exact `git push origin main`
  exit 0, `e93d552..6f0c135`, main→main. 이후 HEAD=origin/main
  `6f0c1358d2acd18b828ebc0ae8482a348712c461`, AIRI trainer/runner 0을 대조했고
  기존 receipt용 WORKING-STATE/roadmap log 두 파일만 dirty였다. 이 actual receipt를
  WORKING-STATE, handoff, roadmap status/log, NEXT, 문서 인덱스 6종에 반영해 focused
  continuity/diff/security 후 `docs: record P0 durability milestone receipt`로
  commit/push한다. docs commit/push 실패 시 controlled GPU와 E2를 시작하지 않는다.
- `20260822-1747-p0a-implementation-commit-receipt`: exact 16-file commit 명령
  `git commit -m "feat: add durable AIRI training recovery"` exit 0. commit
  `6f0c1358d2acd18b828ebc0ae8482a348712c461`, 16 files, 5,134 insertions/
  48 deletions이며 commit 직후 worktree clean, local main은 origin/main보다 1 ahead다.
  다음 상태 변경은 exact `git push origin main`; 실패 시 이 commit과 receipt 문서를
  보존하고 GPU/E2를 실행하지 않는다. 성공 뒤 HEAD=origin/main/PID 0을 read-only 대조해
  SSoT receipt 문서의 별도 commit/push를 수행한다.
- `20260822-1745-p0a-staged-batch-receipt`: 기록된 exact 16개에 대한 `git add`
  exit 0. staged 16개, unstaged 0, untracked 0이며 staged diff-check exit 0/출력 0,
  최초 staged 통계는 5,124 insertions/48 deletions다. 이 receipt를 담은 live state와
  roadmap log 두 파일만 다시 stage하고 동일 경계를 재검증한 뒤
  `git commit -m "feat: add durable AIRI training recovery"`를 실행한다. commit 실패 시
  push/GPU를 실행하지 않고 staged 배치부터 복구하며 E2 금지를 유지한다.
- `20260822-1743-p0a-precommit-validation-receipt`: post-compact 정정 뒤 focused
  `test-airi-work-continuity.ps1` exit 0/PASS, repo 기본 `git diff --check -- .
  ':(exclude)airi_docs/patches/*.patch'` exit 0/whitespace error 0, exact 16개 파일의
  금지 산출물 filename hit 0·비밀 값 형태 content hit 0이다. 10개 코드/회귀 payload의
  path+bytes+SHA canonical manifest SHA는
  `dc8fca8e936b5baada64e91d2926c62c0ee3fd5dc59a0ae10118025a3636463e`다.
  다음 상태 변경은 문서 재검증 후 exact 16-file `git add`, staged/unstaged/untracked와
  staged diff-check 재검증, `git commit -m "feat: add durable AIRI training recovery"`,
  `git push origin main` 순서다. stage/commit/push 하나라도 실패하면 controlled GPU를
  시작하지 않고 현재 배치부터 복구하며 E2는 금지한다.
- `20260822-1741-post-compact-reconciliation`: compact 뒤 지정 SSoT 5종을 순서대로
  전체 재독하고 goal `active`, HEAD=origin/main `e93d552`, 실제 worktree 9 modified +
  7 untracked, AIRI trainer/runner 0을 대조했다. corpus source/chat, base, E1
  adapter/config/report 크기와 SHA는 exact 일치하고 E2 adapter/report/run-dir,
  T3/campaign은 없으며 기존 E2 stdout/stderr는 각 0 bytes다. GPU에는 OS/game 등
  비-AIRI process가 있으나 AIRI workload는 0이다. 직전 문서 갱신으로 worktree가
  12개에서 16개가 된 사실만 live state에 누락됐으므로 관측값으로 정정했다. 다음은
  16개 배치의 continuity/diff/security 검증과 exact stage/commit/push이며, 실패 시
  controlled GPU를 시작하지 않고 E2는 계속 금지한다.
- `20260822-1736-p0a-offline-milestone-doc-intent`: control snapshot 보강 뒤 최신
  독립 read-only 재감사는 P0 0/P1 0, controlled GPU `READY`. 전체 focused Python
  `39 passed, 1 skipped`, PowerShell actual-process PASS, 마지막
  `.\test-current-checkpoint.ps1` exit 0/PASS다. P0-A checkpoint/full-state/atomic
  rotation/offline fault 계층은 완료로, P0-B는 CPU exact resume+durable runner+safe pause
  offline 완료·controlled GPU equivalence와 실제 E2 속도 10분 상한 미실측으로 분리한다.
  handoff/roadmap/NEXT/index를 이 사실로 갱신하고 diff/security 후 exact 16-file
  milestone commit/push한다. commit/push 실패 시 GPU를 시작하지 않으며 E2는 P0-B까지 금지다.
- `20260822-1734-control-snapshot-integration-pass`: 최신 전체 focused Python
  exit 0, `39 passed, 1 skipped in 17.95s`; 병렬 PowerShell actual-process durability
  exit 0/PASS. 새 preflight snapshot/lexists fault와 기존 CPU exact resume,
  N+2 retention, final recovery, pause path/state 전 경로가 함께 통과했다. 독립 최신
  P0/P1 0 판정과 full offline/diff/security 전에는 controlled GPU/E2를 금지한다.
- `20260822-1733-control-snapshot-focused-pass`: py_compile exit 0,
  checkpoint+runner focused exit 0, `22 passed in 9.98s`. invalid live receipt에서
  index/generation/tmp side effect 0, snapshot 중 controls archive race의 일관된 commit,
  dangling link 선행 거부와 N+2 retention이 PASS했다. 전체 통합·독립 재감사 전에는
  controlled GPU/E2를 계속 금지한다.
- `20260822-1733-control-snapshot-fault-intent`: control keep-set을 checkpoint
  directory 생성보다 먼저 immutable bytes로 snapshot·strict 검증하고, commit 뒤에는
  snapshot만 사용한다. archive가 snapshot 중 파일을 move하면 읽은 bytes로 성공하며,
  move 전에 사라지면 최대 3회 재조회 후 정상 소거로 취급한다. dangling link는
  `lexists`+`is_symlink`로 side effect 전 거부한다. invalid hash에서 index/generation/tmp
  불변, snapshot 중 두 controls move에도 일관된 commit, dangling link 선행 무부작용
  회귀를 추가했다. 입력 SHA checkpoint `89785d37...f4f96` 22,642 B, test
  `a76917aa...c45c1` 12,506 B. exact 다음 명령은 py_compile과 checkpoint+runner
  focused pytest이며 실패 시 P0/P1/GPU/E2로 승격하지 않는다.
- `20260822-1731-control-snapshot-reaudit-not-ready`: N+2 수정 뒤 독립 재감사는
  P0 0/P1 2, controlled GPU `NOT READY`. P1-1은 generation/index durable commit 뒤
  live control을 읽어 malformed/mismatch나 runner의 정상 archive race에서 API만 실패하고
  index는 전진하는 ambiguous publication이다. P1-2는 dangling control symlink가
  `Path.exists()` false로 strict symlink 거부를 우회하는 점이다. control receipt를 모든
  checkpoint side effect 전 race-tolerant immutable bytes snapshot으로 검증하고
  `os.path.lexists`로 dangling link도 거부하며, commit 뒤 retention은 snapshot만 사용한다.
  failure 시 index/generation 불변 fault 전에는 GPU/E2를 계속 금지한다.
- `20260822-1728-live-control-retention-focused-pass`: py_compile exit 0,
  checkpoint+runner focused exit 0, `19 passed in 10.40s`. N+2 rotation에서도 accepted
  N이 live controls에 의해 보존되고 controls archive 뒤 latest N+2를 선택하는 fault가
  PASS했다. 전체 Python/PowerShell 통합과 최신 독립 P0/P1 재감사 전에는 controlled
  GPU/E2를 계속 금지한다.
- `20260822-1728-live-control-retention-intent`: checkpoint publisher가 strict regular
  live `pause.ack`/`resume.accepted`의 run/request/checkpoint/hash 정합을 검증하고,
  controls가 history로 archive될 때까지 참조 generation을 latest/previous 외 retention
  keep-set에 포함하도록 구현했다. N acceptance와 archive 첫 move 뒤 N+1·N+2를 실제
  publish해 N이 `checkpoints/`에 남고 controls archive 후 latest N+2 resume되는 fault로
  강화했다. 입력 SHA checkpoint `f42c93a5...4b36c` 21,536 B, runner test
  `86eaa516...6890e` 27,873 B. exact 다음 명령은 py_compile 및 checkpoint+runner focused
  pytest다. 실패 시 P0/GPU/E2 금지를 유지하고 즉시 receipt를 기록한다.
- `20260822-1726-acceptance-rotation-reaudit-not-ready`: 최신 독립 재감사는
  P0 1/P1 0, controlled GPU `NOT READY`. 직전 N/N+1, pause path/state,
  supervisor-final 항목은 해소됐지만 acceptance/ack가 N을 참조한 채 runner heartbeat 전
  N+1·N+2가 publish되면 `_retain_last_two`가 N을 archive로 옮기고 재부팅 acceptance
  검증은 `checkpoints/N`만 찾아 영구 차단한다. live ack/acceptance reference를 strict
  검증해 controls가 archive될 때까지 checkpoint retention keep-set에 포함하고 실제
  N+2 회전 fault를 통과하기 전에는 P0/GPU/E2로 승격하지 않는다.
- `20260822-1725-post-fix-full-offline-pass`: 최신 P0/P1 보강 뒤
  `.\test-current-checkpoint.ps1` 최종 exit 0, `Current checkpoint contract: PASS
  (offline synthetic ASAR only; no installed archive/service/model access)`. 강화 training
  durability와 continuity, 기존 Python/Node/PowerShell 핵심 회귀가 모두 통과했다.
  독립 최종 재감사와 diff/security receipt 전에는 controlled GPU/E2를 계속 금지한다.
- `20260822-1724-p0-p1-integration-pass`: root 통합 전체 focused Python exit 0,
  `36 passed, 1 skipped in 17.40s`; 병렬 PowerShell actual-process durability exit 0,
  PASS. 종료 후 trainer/durable/fake trainer exact Python PID 0. acceptance N과 latest
  N+1 분리, supervisor-failed verified final 회수, pause fixed-volume/reparse 선행 거부,
  corrupt/missing current→strict previous live safe-pause가 회귀에 포함됐다. 최신 바이트
  독립 재감사에서 P0/P1 0을 받기 전에는 controlled GPU/E2를 실행하지 않는다.
- `20260822-1723-p1-integration-intent`: N/N+1과 supervisor-final runner focused
  exit 0, `11 passed in 10.16s`. 병렬 P1은 pause 도구에 fixed-volume, reparse ancestor
  선행 거부와 strict current→previous read-only fallback을 구현하고 자체 PowerShell
  contract PASS를 보고했다. root가 diff를 검토해 current 부재+valid previous도 허용했다.
  통합 입력 SHA: runner/test `900db00e...37526`/`a1672f91...9f4e4`, pause/test
  `60d8fcf1...59cdd`/`c23846b5...17c39`. exact 다음 명령은 세 Python focused 전체와
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\test-airi-training-durability.ps1`.
  완료 조건은 둘 다 exit 0/PASS, 관련 PID 0이며 실패 시 GPU/E2 금지를 유지한다.
- `20260822-1722-n-plus-one-recovery-intent`: acceptance가 가리키는 N을 현재
  latest N+1과 분리했다. runner는 acceptance의 N manifest/payload/run ID와
  dataset/model/trainer pins, ack를 독립 검증해 archive하고, resume 대상은 index의
  N+1을 별도로 선택한다. failed terminal 중 `supervisor-*`만 완전한 final
  manifest/report/completed progress 재검증 대상으로 제한했다. 실제 N→acceptance→N+1
  index→archive 첫 move power-cut fault와 supervisor-failed final 회귀를 추가했다.
  입력 SHA runner `900db00e...37526` 58,252 B, test `a1672f91...9f4e4` 27,602 B.
  py_compile exit 0. exact 다음 명령은 핀된 Python의 runner test 단독 pytest 후 세
  Python suite 전체다. 실패 시 GPU/E2 금지를 유지하고 receipt를 즉시 기록한다.
- `20260822-1719-independent-reaudit-not-ready`: 최신 바이트 독립 read-only 감사는
  P0 1/P1 2와 가용성 P1 1, controlled GPU `NOT READY`다. P0는 trainer가 full pins
  수락한 pause checkpoint N 뒤 archive 전 interval checkpoint N+1을 publish하고 전원이
  꺼지면, 재부팅 runner가 N acceptance/ack를 current latest N+1과 잘못 비교해 영구
  차단하는 창이다. P1은 pause PowerShell의 mapped-drive/reparse ancestor 선행 검증 부재,
  torn/corrupt current run-state에서 strict previous fallback 부재다. 추가 P1은 final
  artifact+completed progress 뒤 supervisor catch가 failed terminal을 쓰면 recovery가
  interrupted 상태만 허용해 검증된 final을 회수하지 못하는 가용성 창이다. accepted/ack의
  N을 독립 검증·archive한 뒤 N+1을 별도 resume하고, pause path/state fault와 제한된
  failed-final reconciliation 회귀를 구현하기 전에는 P0/GPU/E2로 승격하지 않는다.
- `20260822-1717-full-offline-checkpoint-pass`: `.\test-current-checkpoint.ps1`
  최종 exit 0, `Current checkpoint contract: PASS (offline synthetic ASAR only; no
  installed archive/service/model access)`. 내부 continuity와 강화 training durability,
  patch/source/entrypoint, Node/Python/PowerShell 핵심 회귀가 모두 PASS했고 offline
  applicability skip만 계약대로 유지됐다. 다음은 diff/security와 최신 바이트 독립
  재감사다. 독립 P0/P1 0과 controlled GPU intent 전에는 E2를 계속 금지한다.
- `20260822-1716-handshake-offline-receipt`: 강화 PowerShell actual-process
  durability contract exit 0, `AIRI training durability contract: PASS`. hidden runner가
  actual pause/checkpoint/ack→`SAFE_TO_POWER_OFF`→PID 종료→explicit resume→full-pin
  acceptance receipt→pause controls archive→terminal adapter/report receipt를 통과했고,
  동적 request ID의 acceptance history 정확히 1개를 확인했다. 종료 뒤 exact Python
  process filter의 trainer/durable runner/fake trainer는 0이다. 다음 intent는 최신
  worktree 바이트의 독립 read-only P0/P1 감사와 `test-current-checkpoint.ps1`; 두 검증과
  diff/security가 PASS하기 전에는 controlled GPU/E2를 시작하지 않는다.
- `20260822-1715-handshake-python-pass`: assertion 문구 정정 뒤 동일 전체 focused
  Python exit 0, `36 passed, 1 skipped in 17.67s`. full-pin acceptance 전 request/ack
  live 보존, acceptance 뒤 archive, full-pin-only mismatch에서 live 증거 보존,
  request-before-ack 전원차단 보존, archive 첫 move 뒤 재개, CPU 무중단 대 resume
  exact 동등성, checkpoint/final-artifact power-cut 회귀가 함께 PASS했다. skip은 CUDA
  장비에서 gpu-less refusal 경로가 비적용인 기존 조건이다. PowerShell actual-process
  durability contract와 독립 재감사 전에는 controlled GPU/E2를 계속 금지한다.
- `20260822-1714-full-pin-assertion-text-failure`: py_compile exit 0. 첫 전체
  focused Python은 exit 1, `1 failed, 35 passed, 1 skipped in 18.30s`다. 유일한
  실패는 새 full-pin mismatch 회귀가 실제 fail-closed 오류
  `cannot resume checkpoint: checkpoint exact pins mismatch`를 발생시켰지만 assertion이
  더 좁은 `checkpoint pin mismatch`만 요구한 테스트 문구 결함이다. acceptance receipt
  생성 전 중단 경로 자체는 의도대로다. regex를 exact 실제 계약에 맞추고 동일 전체
  묶음을 재실행하며, PASS receipt 전에는 handshake/P0/GPU/E2를 승격하지 않는다.
- `20260822-1713-handshake-fault-suite-intent`: ack된 pause controls는 child가 exact
  full pins를 검증해 acceptance receipt를 쓰기 전까지 live 위치에 유지하고, runner는
  receipt를 검증한 뒤에만 write-through history 승격하도록 구현했다. pause request 기록
  뒤 ack 전 전원차단은 원문을 `unacknowledged` history로 보존해 재기동 시 같은 요청으로
  즉시 재pause하지 않게 했고, acceptance archive 중 첫 move 뒤 전원차단 재개 fault도
  추가했다. direct CPU full-pin-only mismatch는 request/ack live 보존과 acceptance 부재를
  요구한다. 입력 SHA: checkpoint `8c517abd...90f0c`, trainer `890dd7bf...b7960`,
  runner `3faf8c4a...b3123`, 세 test `31d99095...318f`/`32461355...8c04`/
  `9711c024...ab6e`, PowerShell contract `26f882ee...057b`. exact 검증은 핀된
  Python 3.12의 `-m py_compile` 3개 모듈, `-m pytest -q` 위 세 Python test,
  `powershell -NoProfile -ExecutionPolicy Bypass -File .\test-airi-training-durability.ps1`다.
  출력은 console receipt와 system temp synthetic runtime뿐이며 성공 시 정리하고 실패
  산출물은 보존한다. 하나라도 실패하면 P0/GPU/E2로 승격하지 않고 즉시 기록한다.
- `20260822-1709-post-compact-handshake-partial`: compact 직후 지정 SSoT 5종을
  순서대로 전체 재독하고 goal `active`, HEAD=origin/main `e93d552`, worktree
  5 modified + 7 untracked, AIRI trainer/runner 0을 대조했다. corpus source/chat,
  base, E1 adapter/config/report의 크기와 SHA는 exact 일치하고 E2 adapter/report/run,
  T3/campaign은 없으며 기존 E2 stdout/stderr만 각 0 bytes다. OS/game GPU process는
  존재하지만 AIRI workload는 0이다. 직전 receipt 이후 trainer가 full pins 수락 뒤
  `resume.accepted.json`을 쓰고 runner가 그 receipt 뒤 pause controls를 history로
  옮기는 handshake와 fake-trainer 회귀가 부분 편집됐으나 아직 테스트하지 않았다.
  direct-trainer full-pin-only mismatch와 request-only power-cut 복구를 보강하고 전체
  offline 검증·독립 재감사하기 전에는 P0 완료, controlled GPU, E2를 허용하지 않는다.
- `20260822-1703-power-cut-recovery-focused-pass`: durable index가 참조하지 않는
  same-name orphan generation만 quarantine 후 deterministic replay하고, interrupted
  final recovery는 adapter full manifest/checkpoint pins/canonical report/completed progress를
  모두 검증해 complete terminal로 승격하도록 구현했다. partial adapter/report/output.tmp는
  삭제하지 않고 same-volume runtime-artifacts quarantine 후 checkpoint resume한다.
  generation publish→index fault와 verified-final/partial/staging fault를 포함한 checkpoint+
  runner focused pytest exit 0, `17 passed in 10.34s`. full-pin acceptance 전 live pause
  controls 보존 P1과 전체 재검증/독립 재감사 전에는 controlled GPU/E2를 실행하지 않는다.
- `20260822-1659-power-cut-window-reaudit-not-ready`: 최신 독립 재감사는 P0 2/P1 1,
  controlled GPU `NOT READY`. P0-1은 generation directory write-through 승격 후 index 전
  전원차단 시 valid unindexed generation이 남아 같은 generation 재발행을 영구 차단하는
  창이다. P0-2는 trainer final adapter/report publication 후 runner complete terminal 전
  전원차단 시 재부팅이 active→interrupted로 바꾼 뒤 existing output/report를 무조건
  거부하고 output `.tmp`도 트레이너가 거부하는 창이다. P1은 runner subset pins/argv 뒤
  pause controls를 archive하지만 CUDA/BnB/config/tokenizer full pins는 child가 나중에
  검증하는 순서다. unindexed generation quarantine/retry, verified completed artifact
  terminal recovery와 partial/tmp quarantine, full-pin-only mismatch control 보존을 각 fault
  test와 구현하기 전에는 GPU/E2를 실행하지 않는다.
- `20260822-1657-process-identity-fault-pass`: resume argv canonical SHA와 current/previous
  run-state의 runner/trainer exact process-record schema를 Python+PowerShell 양쪽에 추가했다.
  PowerShell corrupt-current 회귀는 truncated JSON 대신 parse 가능한 불완전 PID identity로
  강화해 valid previous만 선택하고 Python quarantine→resume하도록 했다. 전체 focused
  Python exit 0, `30 passed, 1 skipped in 17.24s`; 강화 PowerShell contract exit 0/PASS.
  최신 독립 재감사 판정 전까지 controlled GPU/E2는 계속 금지한다.
- `20260822-1652-p0-offline-fault-suite-pass`: 위임 diff root 검토 뒤 invalid manifest
  JSON fallback, strict nested index, checkpoint reference disappearance, exact resume trainer
  command mismatch 거부 회귀를 추가했다. 전체 focused Python exit 0,
  `30 passed, 1 skipped in 18.65s`; 병렬 강화 PowerShell contract exit 0/PASS.
  torn/structural index previous 복구, publish/resume corrupt generation 격리, same-epoch cursor와
  generation/hash 단조성, changed config command에서 pause 증거 보존, final artifact/complete
  receipt, stale revision, actual orphan, reparse 무부작용, corrupt run-state recovery와 live
  pause/resume가 모두 offline PASS다. 독립 재감사와 controlled GPU/10분 실측 전에는
  P0-B/E2를 완료 처리하지 않는다.
- `20260822-1647-powershell-fault-contract-pass`: canonical LF, ordered dictionary schema,
  quarantine glob을 수리한 강화 PowerShell contract exit 0/PASS. strict malformed
  already-paused ack 거부, final checkpoint 뒤 ack 없이 durable complete된 adapter/report
  actual inventory/SHA receipt 재검증과 PID 0 후 `SAFE_TO_POWER_OFF`, actual trainer-only
  orphan의 launcher side effect 전 거부, junction RunDir 하위 생성 0, corrupt current
  run-state 격리→valid previous resume→terminal complete, 기존 live optimizer-boundary
  pause/checkpoint/ack→SAFE→explicit resume를 모두 통과했다. Python 위임 diff와 전체
  focused/독립 재감사 전까지 controlled GPU/E2는 계속 닫혀 있다.
- `20260822-1646-quarantine-glob-failure`: dictionary key 검증 수리 뒤 네 번째
  PowerShell contract는 late-complete SAFE, actual orphan, junction 무부작용,
  corrupt-current→previous resume와 terminal complete까지 통과한 뒤 test exit 1.
  실제 격리 파일 `run-state.corrupt.<UTC>.<nonce>.json` 13 bytes가 존재하지만 assertion이
  `run-state.*.corrupt` 순서로 glob해 놓친 테스트 오타다. actual naming 규약으로 glob을
  고치고 동일 full contract를 재실행한다. 제품 복구 경로 자체는 이 실행에서 성공했다.
- `20260822-1645-powershell-dictionary-schema-failure`: property 검사 호출을 named
  parameter로 고정한 세 번째 contract도 exit 1, 같은 pause-request property-set
  fail-closed. active 경로에서 새로 만든 request는 디스크 JSON을 deserialize한
  PSCustomObject가 아니라 `[ordered]` dictionary라 helper가 JSON key 대신 PSObject
  dictionary 메타속성을 읽는 정확한 원인을 확정했다. helper가 `IDictionary.Keys`와
  deserialized JSON properties를 동일하게 검사하도록 수정한다. GPU/E2/서비스는 0이다.
- `20260822-1644-powershell-array-binding-failure`: Python canonical receipt에 포함된
  trailing LF를 PowerShell hash에도 반영한 뒤 contract 재실행은 exit 1. 다음 실패는
  `Assert-ExactJsonProperties`에 property-name 배열과 label을 positional 전달해 PowerShell
  binder가 배열을 기대대로 결속하지 못한 `pause request property set is invalid`다.
  synthetic JSON 자체의 필드 변조가 아니라 helper 호출 계약 결함이므로 모든 호출을
  named parameter로 고정하고 재실행한다. 새 temp 실패 산출물도 system temp에 보존됐고
  GPU/E2/서비스는 0이다.
- `20260822-1643-complete-receipt-canonical-failure`: corrupt-state previous fallback,
  strict ack, durable-complete safe power-off, actual orphan, reparse 무부작용 회귀를 추가한
  첫 PowerShell contract는 exit 1. final-checkpoint 뒤 late pause를 모사한 complete receipt
  검증에서 개별 파일 inventory/SHA 이후 PowerShell row-list canonical hash가 Python receipt의
  `manifest_sha256`과 달라 fail-closed했다. synthetic temp 경로 하나를 `-KeepFailedArtifacts`로
  보존했으며 로그 본문은 읽지 않는다. Python canonical bytes와 PowerShell JSON array
  serialization의 exact 차이만 대조해 수리하고 같은 contract를 재실행한다. GPU/E2는 0이다.
- `20260822-1638-independent-reaudit-not-ready`: 최신 바이트 독립 read-only 재감사는
  P0 2/P1 6, controlled GPU `NOT READY` 판정이다. P0는 torn/corrupt checkpoint-index의
  previous fallback 부재와 PowerShell launcher가 corrupt current run-state를 직접 parse해
  Python previous fallback 진입을 막는 문제다. P1은 same-epoch cursor/checkpoint 단조성,
  publish-time corrupt generation 격리, already-paused ack strict schema, final checkpoint
  직후 pause-vs-complete, checkpoint 선택 전 pause control archive, PowerShell reparse/mapped
  path 선행 부작용이다. final artifact/complete receipt, stale revision, orphan 분류, CUDA/BnB
  pins, child cleanup·single terminal write는 양호로 확인됐다. Python/PowerShell 소유권을
  분리해 fault 회귀와 함께 보강하고 재감사 전에는 GPU/E2를 실행하지 않는다.
- `20260822-1635-final-artifact-focused-pass`: run identity가 다른 두 adapter의
  manifest SHA는 각 실제 bytes와 결속하고, manifest에서 identity만 제거한 pins+file
  inventory를 exact 비교하도록 회귀를 분리했다. 동일 focused pytest exit 0,
  `24 passed, 1 skipped in 15.44s`; 병렬 PowerShell live pause/resume contract도 exit 0,
  PASS. 최종 adapter는 파일별 flush/fsync→inventory/manifest 검증→write-through directory
  승격 후 재검증되며 CPU 무중단 대 pause/checkpoint/resume의 LoRA tensor, AdamW,
  LambdaLR, RNG, cursor/counter와 identity-neutral summary가 exact다. controlled GPU와
  실제 E2 속도 10분 상한 실측 전까지 P0-B/E2 gate는 계속 미완료다.
- `20260822-1633-artifact-identity-comparison-failure`: `_fsync_file`을 `rb+`로 열어
  flush/fsync하도록 수리한 뒤 동일 Python focused는 exit 1,
  `23 passed, 1 skipped, 1 failed in 15.87s`; 병렬 PowerShell live durability는
  exit 0/PASS였다. 기존 세 final-artifact 실패는 모두 해소됐고 남은 한 건은 서로 다른
  run ID로 만든 무중단/재개 summary에서 새 `adapter_artifact_manifest_sha256`까지 같다고
  비교하는 assertion이다. tensor/optimizer/scheduler/RNG/cursor 비교 전에 summary
  assertion에서 중단됐으므로 원인을 확인해 identity-bound manifest SHA와 학습 상태
  동등성 계약을 분리하기 전에는 exact equivalence 완료로 승격하지 않는다.
- `20260822-1632-post-compact-final-artifact-failure`: 지정 SSoT 5종을 순서대로
  전체 재독하고 goal `active`, HEAD=origin/main `e93d552`, 실제 worktree 5 modified +
  7 untracked, trainer/durable runner 0을 대조했다. corpus source/chat, base, E1
  adapter/config/report의 크기와 SHA는 인계서와 exact 일치하고 E2 adapter/report/run-dir,
  T3, campaign은 0이며 기존 E2 로그만 각 0 bytes다. 직전 final-artifact durability
  보강 후 focused pytest는 exit 1, `21 passed, 1 skipped, 3 failed in 14.92s`였고 세
  실패 모두 `behavior_training_checkpoint.py::_fsync_file`가 Windows에서 read-only
  descriptor에 `os.fsync`해 `OSError: [Errno 9] Bad file descriptor`를 낸 동일 원인이다.
  병렬 PowerShell durability contract는 exit 0/PASS였다. 실패를 P0 진척으로 승격하지
  않으며 write-capable descriptor로 flush/fsync한 뒤 두 exact 검증을 다시 수행한다.
- `20260822-1622-live-pause-resume-pass`: startup trainer identity bounded wait와
  launcher 중복 redirect 제거 뒤 강화 PowerShell durability contract exit 0/PASS.
  hidden runner 시작 직후 live safe-pause 호출, exact trainer PID/creation/exe/command,
  optimizer-boundary checkpoint+manifest/payload SHA, ack, trainer/runner 종료,
  `SAFE_TO_POWER_OFF`, explicit resume, pause control history 보존, terminal adapter/report
  receipt까지 통과했고 temp command-line 관련 process 0을 확인했다. 실패 재현 temp 5개도
  exact system-temp 경로 검증 후 모두 제거했다. P0 offline 증거는 강화됐지만 재감사 P0
  3건(final artifact durability/stale resume receipt/orphan 분류)과 GPU 실측이 남아 있다.
- `20260822-1621-safe-pause-startup-race`: live pause contract가 launcher의 verified
  `starting` state 직후 호출되어 trainer PID가 아직 게시되기 전에 safe-pause가 blind
  pause로 거부, exit 1. runner PID receipt와 trainer PID receipt 사이의 정상 startup
  race다. pause 도구가 starting/running에서 최대 30초 exact trainer identity 게시를
  기다리고 terminal 전환은 fail-closed하도록 수정한다. 실제 GPU/E2는 0, P0-B 미완료다.
- `20260822-1617-launcher-handle-leak-failure`: runner PID 종료 대기 뒤에도 동일 temp
  stderr lock으로 contract exit 1. `Start-Process -PassThru`의 venv redirector Process
  객체를 launcher가 명시 Dispose하지 않아 같은 PowerShell 세션에서 redirection handle이
  GC까지 남는 handle 누수로 분리했다. 모든 launch receipt/timeout 경로에서 Process
  객체를 Dispose한 뒤 재실행한다. 본 pause/resume receipt는 통과했지만 공식 contract
  PASS 전까지 P0-B/E2는 미완료다.
- `20260822-1616-live-pause-cleanup-race`: 강화한 active PowerShell 통합은 hidden
  runner+live trainer의 PID/command 대조, pause request, optimizer-boundary checkpoint,
  ack, trainer 종료, `SAFE_TO_POWER_OFF`, explicit resume, terminal artifact receipt까지
  통과했다. 단 terminal state 직후 runner가 stderr handle을 닫기 전에 temp cleanup이
  시작돼 locked `runner.stderr.log` Remove-Item으로 test exit 1. runner PID 종료를 기다린
  뒤 cleanup하도록 회귀를 수정하며 공식 PASS receipt는 재실행 뒤에만 승격한다.
- `20260822-1613-powershell-durability-pass`: venv redirector와 실제 runner PID를
  분리해 새 run-state의 exact process identity를 권위로 삼은 뒤
  `test-airi-training-durability.ps1` exit 0,
  `AIRI training durability contract: PASS`. 공백 경로+핀된 venv의 hidden background
  runner가 독립 실행되어 heartbeat, trainer PID/command identity, terminal exit 0,
  adapter/report SHA receipt를 남겼고 verified pause receipt의 `SAFE_TO_POWER_OFF`도
  통과했다. offline P0 launcher/pause 증거는 확보됐지만 controlled GPU/10분 실측 전까지
  P0-B와 E2 gate는 미완료다.
- `20260822-1613-launcher-venv-redirector-failure`: terminal 재확인 뒤에도 contract
  exit 1/unknown. Windows venv `python.exe`의 단명 redirector PID와 실제 interpreter
  runner PID가 다를 수 있는데 launcher가 동일 PID를 강제하고 redirector 종료를 전체
  실패로 처리한 원인을 확정했다. 시작 전 state 부재를 확인한 뒤에는 새 run-state의
  exact live process identity/terminal receipt를 권위로 삼고 redirector exit만으로
  중단하지 않도록 수정한다. P0/E2/GPU 상태는 변함없이 미완료/0이다.
- `20260822-1612-launcher-terminal-race-failure`: executable-path hash 수리 뒤에도
  PowerShell contract exit 1. 종료 직전 poll에서 state read 후 runner가 terminal
  state를 쓰고 종료하면 `HasExited`가 state를 재확인하지 않는 final race를 식별했다.
  종료 감지 직후 exact run_id/runner PID/terminal receipt를 한 번 더 읽도록 수정한다.
  실제 P0 Python 증거는 유지되지만 launcher gate와 E2는 계속 닫혀 있고 GPU 실행은 0이다.
- `20260822-1610-launcher-integration-retry-failure`: reparse-point Python을 핀된 venv로
  교체한 PowerShell contract 재실행도 run-state 전 runner 종료로 exit 1했다. 첫 보안
  거부 원인은 제거됐으므로 별도 원인이며 Windows PowerShell Start-Process exit code도
  여전히 빈 값이다. 실패 runtime을 보존해 stderr/command quoting을 재대조한다. Python
  focused의 직전 `23 passed, 1 skipped`는 유효하지만 launcher P0는 미검증이고 GPU/E2는 0이다.
- `20260822-1608-launcher-integration-failure`: epoch-complete checkpoint와 CPU exact
  resume 보강 뒤 focused pytest exit 0, `23 passed, 1 skipped in 13.47s`. PowerShell
  durability contract는 hidden background runner가 verified run-state 전 종료해 exit 1;
  launcher는 exit code도 비어 있는 실패를 반환했다. 계약 테스트 finally가 임시 로그를
  제거해 원인 본문은 receipt로 남지 않았으므로, 다음 재현에서는 runtime log를 Git 밖
  임시 진단 경로에 보존하고 quoting/Start-Process 인자를 대조한다. P0 launcher는 미검증,
  GPU·서비스·E2는 0이며 gate는 닫혀 있다.
- `20260822-1606-cpu-exact-resume-receipt`: 핀된 Python 3.12로 새 CPU 통합 회귀
  `CpuSmokeTests::test_cpu_uninterrupted_and_safe_pause_resume_are_exact`를 실행해 exit 0,
  `1 passed in 8.53s`. 무중단 8 microstep과 optimizer 경계 pause/checkpoint→resume
  8 microstep의 최종 LoRA tensor, AdamW, 실제 constant LambdaLR, Python/Torch/CUDA RNG,
  loss 배열, cursor/counter, summary가 exact 일치했다. 별도 skip로 보였던 항목은 CUDA가
  존재할 때 gpu-less refusal만 생략하는 환경 적합 skip임도 확인했다. 자동 CPU 동등성은
  증명됐지만 controlled GPU 동등성과 실제 E2 속도 10분 상한 실측 전까지 P0-B는 미완료다.
- `20260822-1603-p0-focused-pass-with-skip`: 동일 focused pytest 재실행 exit 0,
  `22 passed, 1 skipped in 11.52s`; 실제 subprocess runner의 safe-pause→verified
  checkpoint→explicit resume→complete terminal receipt 회귀가 PASS했다. 남은 skip은
  기존 Torch/PEFT/Transformers CPU smoke dependency probe이며 중단·재개 tensor
  동등성 증거는 아직 없다. 따라서 P0-A/P0-B를 완료 처리하지 않고 핀된 venv import
  실패를 진단해 실행 가능한 exact equivalence 회귀를 추가한다. GPU·서비스·E2는 0이다.
- `20260822-1602-p0-focused-retry-failure`: 수정 뒤 PowerShell durability contract는
  exit 0/PASS, Python focused는 exit 1, `21 passed, 1 skipped, 1 failed in 13.81s`다.
  남은 실패는 초단명 fake trainer가 Windows CIM PID identity의 20×50ms 캡처 전에
  종료한 테스트 경쟁이며 runner는 이를 fail-closed하고 child 회수·failed terminal
  receipt를 남겼다. fake process에 짧은 관측 창을 부여해 실제 pause/resume 경로를
  재검증한다. GPU·서비스·E2 실행은 0이고 P0 gate는 계속 닫혀 있다.
- `20260822-1601-p0-focused-test-failure`: 첫 P0 통합 focused pytest는 exit 1,
  `20 passed, 1 skipped, 2 failed in 8.02s`; Python py_compile은 exit 0이다.
  실패는 backward-progress 테스트 fixture의 heartbeat 필드 누락과 같은 Python
  runner 프로세스 안에서 즉시 resume해 terminal state의 종료 전 runner PID가 자기
  자신과 일치한 테스트/재진입 계약 문제다. PowerShell 계약은 호출 script 뒤
  `$LASTEXITCODE`가 미설정인 테스트 판정 결함으로 exit 1했다. 실제 학습·GPU·서비스와
  D: runtime 산출물은 0이며 P0-A/P0-B·E2 gate는 미완료로 유지한다. 다음 행동은 세
  실패를 회귀가 표현하려는 계약에 맞게 수정하고 동일 exact 명령을 재실행하는 것이다.
- `20260822-1547-post-compact-reconciliation`: compact 직후 지정된 SSoT 5종을 순서대로
  전체 재독하고 goal active, HEAD=origin/main `e93d552`, Python trainer/runner 0을
  read-only로 대조했다. E2 adapter/report, T3 manifest/output, durable run directory는
  없고 기존 E2 stdout/stderr만 각 0 bytes다. worktree에는 intent 이후 생성된 P0
  부분 구현 2 modified + 3 untracked만 있다. 오래 남아 있던 §1의 pre-milestone
  HEAD/worktree와 §4의 다음 행동을 관측 사실로 정정했다. 테스트·GPU·서비스 실행은 0이다.
- `20260822-1537-p0-implementation-intent`: 두 독립 read-only 감사로 trainer optimizer
  경계·cursor/RNG/pin/rotation seam과 runner state/PID/control/quarantine 계약을 확정했다.
  위 입력 SHA, 소유 파일, offline 명령, D: runtime 경로와 실패 폐쇄 조건을 고정했으며
  actual trainer/GPU 실행은 0이다.
- `20260822-1531-p0-design-intent`: receipt commit
  `e93d55283006045eaaa745cff1122340d61a6476`도 origin/main push됐고 worktree clean,
  trainer 0을 확인했다. 첫 milestone은 완료됐으며 E2를 차단한 채 P0 read-only
  구조 감사로 전환한다. 구현 전 별도 intent를 다시 기록한다.
- `20260822-1530-receipt-doc-validation`: push receipt를 SSoT 5종에 반영한 뒤
  focused continuity exit 0/PASS, repo 기본 diff-check exit 0/출력 0, untracked 0.
  exact 5-file stage와 receipt commit/push를 실행한다.
- `20260822-1529-milestone-push-receipt-intent`: `git push origin main` exit 0,
  `0c0ffbe..e822f9f`, HEAD와 origin/main이 모두
  `e822f9f120e27e561d2e90353da4ba8315e4e3dd`. 첫 milestone 본체 push는 완료됐다.
  이 사실을 SSoT 5종에 기록해 receipt commit/push한 뒤 P0 구현으로 이동한다.
- `20260822-1529-milestone-commit-receipt`: `git commit -m "docs: harden long-goal
  continuity"` exit 0. commit `e822f9f120e27e561d2e90353da4ba8315e4e3dd`, 11 files,
  645 insertions/54 deletions, 신규 live state와 continuity test 2개. commit 직후
  worktree clean, `main`은 origin/main보다 1 ahead였으며 다음 명령은 exact push다.
- `20260822-1528-staged-batch-receipt`: exact 11개 검토 파일만 `git add`; staged
  diff-check exit 0/출력 0, unstaged 0, untracked 0, 총 642 insertions/54 deletions.
  이 receipt를 재stage한 뒤 동일 commit 명령을 실행한다.
- `20260822-1528-precommit-validation-receipt`: final focused continuity exit 0/PASS,
  repo 기본 diff-check exit 0/출력 0. 독립 재감사 P0/P1 0 상태에서 exact 11-file
  stage와 `docs: harden long-goal continuity` commit/push로 이동한다.
- `20260822-1527-milestone-commit-intent`: 수정 후 독립 재감사는 P0 0/P1 0,
  READY. direct trainer 우회 금지와 구조화 P0→E2 회귀를 확인했다. exact 11-file
  stage/commit/push 명령을 고정했으며 실패 시 push/완료 처리하지 않는다.
- `20260822-1526-final-diff-security-receipt`: repo 기본 설정의 exact
  `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'` exit 0, 출력 0.
  현재 9 modified + 2 untracked, 46,410자 diff/content의 secret·금지 산출물 hit 0.
  다음 행동은 기존 P1 두 건의 독립 재감사다.
- `20260822-1525-diff-config-failure`: 경고 억제를 위해 임시로
  `git -c core.autocrlf=false diff --check`를 사용한 진단이 기존 CRLF 전체를 trailing
  whitespace로 해석해 exit 2. 파일 변경은 0이며 이는 repo 명시 exact command가
  아니다. 기본 Git 설정의 `git diff --check -- . ...`로 즉시 재검증한다.
- `20260822-1525-offline-revalidation-receipt`: P1 수정 뒤
  `.\test-current-checkpoint.ps1` exit 0, 19.06초, 최종 checkpoint contract PASS.
  설치본·서비스·모델/GPU 접근은 0이며 다음 행동은 final diff-check와 재감사다.
- `20260822-1524-review-p1-focused-receipt`: direct trainer block을 PRE-P0 DO NOT RUN
  참고로 격리하고, 공통 goal/adoption/order token, P0-A→P0-B→E2-LAUNCH item 결속,
  git_head ancestor와 strict frontmatter 검증을 추가했다. focused test exit 0, PASS.
- `20260822-1523-milestone-review-p1-intent`: 독립 diff 감사 판정은 P0 0, P1 2,
  NOT READY. P1은 pre-P0 direct trainer 명령의 durable runner 우회 가능성과 단순
  문자열 회귀의 오탐 가능성이다. direct 명령을 실행 금지 파라미터 참고로 격리하고
  공통 machine-state/order token과 section/item 검증을 추가한 뒤 전체 재검증한다.
- `20260822-1519-diff-security-receipt`: `git diff --check -- .
  ':(exclude)airi_docs/patches/*.patch'` exit 0(whitespace 오류 0, LF→CRLF 경고만).
  9 modified + 2 untracked의 42,599자 diff/content를 값 형태 secret, `.env`, model
  weight/GGUF, audio, DB, log 파일명으로 스캔해 hit 0. 독립 최종 감사 뒤 commit한다.
- `20260822-1518-reference-regression-receipt`: 핀된 Python 3.12 venv로 reference/
  pilot 회귀 exit 0, `7 passed in 0.06s`. 출력 산출물·GPU·서비스 접근은 0이며
  다음 행동은 diff/금지 데이터 최종 검토다.
- `20260822-1517-reference-regression-retry-intent`: 문서에 핀된 QLoRA Python
  `D:\AIRI-Models\venv-midm-broadcast-qlora-py312\Scripts\python.exe`가 Python 3.12.13,
  pytest 9.1.1임을 확인했다. 이 interpreter로 동일 테스트를 재실행하고 실패 시
  commit/push하지 않는다.
- `20260822-1517-reference-regression-launch-failure`: exact pytest command exit 1,
  `pythoncore-3.14-64`에 pytest module이 없어 테스트 수집 전에 종료됐다. 코드·환경·
  산출물 변경은 0이며 기존 Python 3.12/venv를 확인한 뒤 새 intent를 기록한다.
- `20260822-1516-reference-regression-intent`: source ledger 밖 영상 식별자 제거와
  문서 수치 정합을 확인하기 위해 `python -m pytest -q
  ollama-proxy/training/tests/test_broadcast_reference_and_pilot_data.py`를 실행한다.
  입력은 추적 schema/JSONL/pilot이며 출력 파일은 없고 실패 시 commit/push하지 않는다.
- `20260822-1516-offline-checkpoint-receipt`: `.\test-current-checkpoint.ps1` exit 0,
  18.13초, 최종 `Current checkpoint contract: PASS`. 설치본·서비스·모델 접근 없이
  offline synthetic ASAR 계약만 실행했다. 다음 행동은 reference 회귀와 diff 검토다.
- `20260822-1515-continuity-order-test-receipt`: NEXT/handoff/roadmap의 active 상태와
  P0-before-E2 순서를 일치시킨 뒤 `.\test-airi-work-continuity.ps1` exit 0, PASS.
  다음 행동은 전체 offline checkpoint이며 GPU·서비스 실행은 0이다.
- `20260822-1515-roadmap-order-test-failure`: focused 재실행 exit 1. NEXT와 handoff는
  통과했지만 roadmap 문구가 `E2` 뒤 `P0` 순서여서 실패했다. 의미·문자열 순서를
  함께 `P0`→`E2`로 정정하며 commit/push·GPU 실행은 계속 0이다.
- `20260822-1515-handoff-order-test-failure`: focused 재실행 exit 1. NEXT ordering은
  통과했지만 handoff §8의 구현 항목에 literal P0 label이 없어 순서 계약이 실패했다.
  commit/push·GPU 실행은 계속 0이며 label 정정 후 재실행한다.
- `20260822-1514-continuity-order-test-failure`: `.\test-airi-work-continuity.ps1`
  exit 1. NEXT 상단이 의미상 P0 선행을 말하지만 토큰은 `E2` 뒤 `P0` 순서라 계약
  회귀가 실패했다. commit/push·GPU 실행은 0이며 문구 정정 후 focused test를 재실행한다.
- `20260822-1509-goal-resume-doc-batch-intent`: goal active, HEAD/worktree, trainer 0,
  corpus/base/E1 exact, E2·후속 산출물 0을 독립 재감사했다. 첫 milestone의 exact
  검증·commit/push 명령과 실패 폐쇄 조건을 기록했으며 GPU 실행은 아직 0이다.
- `20260822-1445-durability-protocol-receipt`: live state 우선 재독, 실제 상태 대조,
  active goal 최대 60분 heartbeat, 명령 전후 intent/receipt, milestone 승격 규칙을
  저장소 지침에 반영했다. 문서 계약 focused test와 전체 offline checkpoint가 PASS했다.
- `20260822-1434-roadmap-pause-audit`: reference 30건과 continuity arc 7건을
  분리해 정정했고 E1 완료/E2 산출물 0/후속 산출물 0을 실제 파일과 대조했다.
- 방송 reference/pilot 회귀 7/7과 당시 offline checkpoint가 PASS했다.
- 현재 작업은 위 체크포인트 이후의 **문서 지속성 프로토콜 배치**다.

## 4. 다음 허용 행동

1. implementation push receipt를 WORKING-STATE, 현행 handoff, roadmap status/log,
   NEXT에 반영하고 focused continuity/diff/security를 검증한다. 문서 인덱스는 현행
   handoff를 이미 정확히 가리키므로 변경하지 않는다.
2. exact 5-doc receipt batch를 Conventional Commit으로 commit/push하고 actual push
   receipt를 최종 live 문서에 durable하게 남긴다.
3. HEAD=origin/main과 clean worktree를 확인한 뒤 fresh timestamped 외부 root의 controlled
   GPU 동등성·실제 checkpoint ≤600초/최소 4구간 실측 intent를 별도로 기록한다.
4. controlled GPU receipt 전에는 authoritative E2를 시작하지 않는다.

## 5. 갱신 트리거

active goal에서는 다음 중 하나라도 발생하면 이 파일을 먼저 갱신한다.

- 마지막 기록 후 최대 60분 경과(heartbeat 상한)
- 체크리스트 항목 또는 테스트 묶음 완료·실패
- 10분 이상 걸릴 수 있는 명령 실행 직전과 종료 직후
- 장기 프로세스 시작·PID 변경·중단·checkpoint 생성
- 새 산출물·해시·커밋·push·권한·blocker 발생
- 사용자의 pause/stop/resume, 세션 종료, 예상 가능한 재부팅
- compact가 예상되거나, 요약된 컨텍스트를 받았다고 판단한 직후

자동 compact 직전 알림은 보장되지 않는다. 따라서 “compact 직전 기록”에만
의존하지 않고 위 이벤트 기록과 60분 heartbeat를 함께 사용한다. heartbeat는
이 문서만 짧게 덮어쓰며, 로드맵 로그는 milestone에서만 갱신한다.
GPU 학습·merge/package·T3·장기 campaign 중 heartbeat 상한은 15분이다.

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
