# AIRI 로드맵 갱신 로그 (최신이 위)

> 2026-08-19 로드맵 v3 개편 때 `AIRI-ROADMAP-STATUS.md`에서 분리했다.
> **매 배치(커밋)마다 이 파일 맨 위에 한 줄 이상 기록한다** — 상태 변화가
> 없어도 남긴다. 클로드·코덱스 공통 의무이며, 이 기록이 없으면 배치가
> 완결되지 않은 것으로 본다. (구 규칙과 동일, 기록 위치만 이 파일로 변경)
> 본문 링크 경로는 각 항목의 작성 시점 기준이다 — 2026-08-19 정리로 일부
> 문서가 `아카이브/`·`완료/`로 이동했으니 이름으로 검색할 것.

## 2026-08-22 P0-B 독립 감사·compact 복구 정정

- exact 8-path stage exit 0, staged 8·unstaged 0·untracked 0, cached diff-check PASS다.
  stage receipt 두 문서를 restage·재검증한 뒤 `fix: auto-detect durable training run`으로
  commit하며 실패하면 push/GPU/E2로 이동하지 않는다.
- final 8-file batch는 changed 8·boundary diff 0·staged/untracked 0, forbidden artifact
  path 0, AIRI runner/trainer 0, focused/full offline와 diff-check PASS다. 독립 final audit
  P0 0/P1 0 `READY`; exact 8-path stage와 cached 경계가 PASS해야만 commit/push한다.
- 첫 safe-pause 독립 리뷰 P0 2/P1 1과 수정 재리뷰 P1 1을 모두 닫았다. omission과
  explicit empty 분리, all-process ambient workload guard, 첫 `--` 앞 runner script
  범위 제한을 구현하고 source-decoy/empty-manual 회귀를 추가했다. fresh focused와 full
  offline checkpoint, diff-check PASS, 최종 독립 리뷰 P0/P1 0이다. pause
  `2616402b...22bbce` 28,150 B, test `0bea228c...ebaf0` 37,269 B, AIRI runner/trainer 0.
  code/test+6 SSoT exact 8-file stage/commit/push 전에는 GPU/E2를 시작하지 않는다.
- safe-pause auto-discovery 구현은 exact Windows argv(`--` 경계), strict current→previous
  run-state, actual runner source SHA와 PID/creation/executable/command identity를 결속한다.
  최초 focused 회귀가 Unicode P/Invoke 선언 누락을 검출해 two live runners를 0으로
  오판한 결함을 수정했다. 강화된 0/1/multiple/process-spoof/corrupt-current fallback과
  manual SAFE gate 회귀 PASS, full `test-current-checkpoint.ps1` PASS, diff-check PASS다.
  독립 리뷰와 milestone 6-doc receipt·commit/push 전에는 GPU/E2를 시작하지 않는다.
- 사용량 초기화 뒤 사용자는 `pause-airi-safely.ps1`의 verified active run 자동 탐지를
  먼저 구현하고 goal을 계속하라고 요청했다. HEAD=origin/main `e3a8819`, worktree clean,
  AIRI trainer/runner 0, E2/old P0-B root 0에서 pause/test 두 파일을 owned scope로
  지정했다. exact runner command→run-state/process identity만 허용하고 0개는 noninteractive
  중단, multiple/spoof는 거부, manual RunDir와 기존 SAFE 검증은 유지한다. offline
  P0/P1 검증·commit/push 전에는 controlled GPU/E2를 시작하지 않는다.
- final expected-gate push receipt `e3a8819fe2b9edacbb2567bead26ccb8f4086404`
  (`docs: record expected gate push`)은 origin/main에 push됐고, 복구 시 실제 clean
  HEAD로 확인됐다.
- actual docs push receipt 2개는 boundary/continuity/diff-check PASS, exact stage 뒤
  staged 2·unstaged 0·untracked 0, cached diff-check PASS다. stage receipt를
  재stage·재검증하고 final receipt commit/push하며 실패 시 GPU/E2를 실행하지 않는다.
- docs receipt push 성공: `8cd69b5..248e548 main -> main`, HEAD=origin/main
  `248e548`, AIRI trainer/runner와 Ollama 0이다. expected-run gate와 6개 장기 SSoT
  receipt는 origin/main에 durable하다. 이 actual push receipt 두 문서를 final
  focused 검증·commit/push한 뒤에만 fresh controlled GPU intent로 이동한다.
- docs receipt commit 성공: `248e5481b50658ecd6da6d4bc9675f7ff3971d77`
  (`docs: record expected GPU gate receipt`), 6 files, 102 insertions/30 deletions.
  직후 worktree clean, local main은 origin/main보다 1 ahead, AIRI trainer/runner 0이다.
  exact push 성공 전에는 controlled GPU/E2를 시작하지 않는다.
- exact 6-doc stage exit 0, staged 6·unstaged 0·untracked 0, cached diff-check PASS다.
  이 stage receipt 두 문서를 재stage·재검증한 뒤 docs receipt commit을 수행하며
  실패 시 push/GPU/E2로 이동하지 않는다.
- P1 정정 뒤 root fresh exact 6-doc boundary/continuity/diff-check PASS. 독립 재감사도
  root NEXT 존재, diff exact 6, HEAD=origin/main `8cd69b5`, current transaction과
  active/adoption/P0-before-E2/GPU-E2-zero 정합을 확인해 P0 0/P1 0 `READY`다.
  이 판정은 exact 6-doc stage/commit/push만 허용하며 controlled GPU/E2는 아니다.
- 6-doc receipt batch는 boundary/continuity/diff/security PASS 뒤 첫 독립 감사에서
  P0 0/P1 2 `NOT READY`였다. diff 3/NEXT 부재 주장은 root fresh `NEXT_EXISTS=True`와
  `git diff HEAD` exact 6으로 반증됐지만, WORKING transaction recovery가 stale
  `f2c9a46`/3-file을 가리킨 P1은 확정됐다. HEAD=origin/main `8cd69b5`와 exact 6-doc
  scope로 정정해 fresh 재감사 P0/P1 0 전에는 stage/GPU/E2로 이동하지 않는다.
- expected gate implementation push 성공: `f2c9a46..8cd69b5 main -> main`,
  HEAD=origin/main `8cd69b5`, AIRI trainer/runner와 Ollama process 0이다. 실제
  controlled GPU paired run과 E2 속도 ≤600초 실측은 여전히 0이다. actual push
  receipt를 6개 SSoT에 반영해 docs receipt commit/push를 마치기 전에는 GPU/E2를
  실행하지 않는다.
- expected gate implementation commit 성공: `8cd69b5f455bd41b48faa5ed6e9cac1af00f8908`
  (`fix: bind GPU equivalence to expected run`), 4 files, 405 insertions/27 deletions.
  직후 worktree clean, local main은 origin/main보다 1 ahead, AIRI trainer/runner 0이다.
  exact push 성공 전에는 controlled GPU/E2를 시작하지 않는다.
- full-offline receipt 두 문서를 재stage한 뒤 staged 4·unstaged 0·untracked 0,
  cached diff-check PASS다. stage receipt 두 문서만 다시 stage·재검증하고 exact
  implementation commit을 수행하며 실패 시 push/GPU/E2로 이동하지 않는다.
- compact 뒤 지정 SSoT와 active goal을 복구하고 HEAD=origin/main `f2c9a46`, exact
  4-file stage/unstaged 0/untracked 0, 고정 입력·E1 SHA exact, E2/T3/campaign 0,
  AIRI trainer/runner 0을 재대조했다. 중복 실행 없이 기존 full-offline session을
  회수해 `test-current-checkpoint.ps1` exit 0과 최종 offline checkpoint PASS를
  확인했고 관련 PID도 0이다. receipt 두 문서를 재stage·cached diff-check한 뒤
  `fix: bind GPU equivalence to expected run` commit/push하며, 실패하면 GPU/E2를
  실행하지 않는다.
- expected-gate exact 4-file stage exit 0, staged 4·unstaged 0·untracked 0,
  cached diff-check PASS다. stage receipt 두 문서를 재stage·재검증한 뒤 full offline
  checkpoint를 실행하며 실패 시 implementation commit/push/GPU/E2로 이동하지 않는다.
- controlled GPU preflight 설계 감사에서 기존 verifier가 두 run의 상호 동일성은
  보지만 계획된 input manifest/full config SHA, seed/batch/accumulation과 첫 optimizer
  경계 pause를 expected 값으로 강제하지 않는 증거 결함을 발견했다. explicit gate와
  mismatch fault를 추가하고, 실제 trainer가 만드는 빈 baseline `control/`을 처음에는
  false reject한 P0도 empty regular만 허용·entry/link/reparse 거부로 수리했다. root
  Python `73 passed, 2 skipped`, actual-process PowerShell PASS, 관련 PID 0, 최신 독립
  재감사 P0 0/P1 0 `READY`다. exact stage 상태의 full offline PASS와 implementation
  commit/push 전에는 controlled GPU/E2를 시작하지 않는다.
- 첫 통합 preflight의 `ollama ps`가 조회 대신 hidden Ollama app/serve와 PowerShell
  supervisor shell을 남긴 실패를 receipt로 기록했다. exact PID/creation/command를
  대조해 leaked shell과 app/serve만 종료했고 최종 related/Ollama process 0이다. 해당
  통합 명령은 완결 PASS로 인정하지 않고 CUDA/package 환경은 부작용 없이 분리 재검증했다.
- docs receipt push 성공: `e970cf7..74d8999 main -> main`, HEAD=origin/main
  `74d8999`, AIRI trainer/runner 0이다. 이 actual push receipt 두 문서를 final
  focused 검증·commit/push해 clean GPU preflight 경계를 만들기 전에는 controlled
  GPU/E2를 시작하지 않는다.
- docs receipt commit 성공: `74d8999bdfba7cc1bf45749b9e110379853b8bac`
  (`docs: record GPU equivalence gate receipt`), 6 files, 107 insertions/32 deletions.
  직후 worktree clean, local main은 origin/main보다 1 ahead다. exact push 성공 전에는
  controlled GPU/E2를 시작하지 않는다.
- exact 6-doc stage exit 0, staged 6·unstaged 0·untracked 0, cached diff-check PASS다.
  stage receipt 두 문서를 재stage·재검증한 뒤 docs receipt commit/push를 수행한다.
- P0-B gate actual push receipt를 SSoT 6종에 반영한 뒤 continuity PASS, exact
  6-doc boundary, untracked 0, repo 기본 diff-check whitespace error 0, 금지 산출물
  filename·비밀 값 형태 content hit 0을 확인했다. exact stage·docs receipt commit/push가
  실패하면 controlled GPU/E2로 이동하지 않는다.
- compact 뒤 actual push receipt를 재대조했다. `git push origin main` exit 0,
  `59a2363..e970cf7 main -> main`; HEAD=origin/main `e970cf7`, AIRI trainer/runner 0,
  고정 입력/E1 SHA exact, E2/T3/campaign 0, E2 로그 각 0 bytes다. 이전 live 문서의
  local-ahead/구현 10-file 상태는 stale였고 실제 worktree는 receipt용 WORKING-STATE와
  이 log 두 파일만 dirty였다. 이를 먼저 정정한 뒤 SSoT 6-doc receipt commit/push를
  마칠 때까지 controlled GPU/E2는 시작하지 않는다.
- 구현 commit 성공: `e970cf7e4c3a4685fd8bce23c659a1c9aa93c21e`
  (`feat: add GPU training equivalence gate`), 10 files, 1,703 insertions/52 deletions.
  직후 worktree clean, local main은 origin/main보다 1 ahead다. exact push 성공과 receipt
  문서 commit/push 전에는 controlled GPU/E2를 시작하지 않는다.
- exact staged 10-file 상태에서 전체 offline checkpoint exit 0/PASS. continuity,
  actual-process durability와 CI manifest 포함 기존 핵심 회귀가 통과했고 관련 PID 0이다.
  receipt 재stage·cached diff-check 뒤 `feat: add GPU training equivalence gate`로
  commit/push하며 실패 시 controlled GPU/E2로 이동하지 않는다.
- closed history/live inventory와 non-replacing atomic-new receipt 보강 뒤 최신 독립
  재감사는 P0 0/P1 0, controlled GPU READY다. fresh Python `68 passed, 1 skipped`,
  actual-process PowerShell PASS, diff-check PASS와 관련 PID 0을 확보했다. exact stage
  상태의 full offline checkpoint·commit/push 전에는 GPU/E2를 시작하지 않는다.
- 첫 blocker 수정 뒤 Python `63 passed, 1 skipped`, actual-process PowerShell PASS였지만
  독립 재감사는 P0 2/P1 1로 아직 NOT READY다. 확정 P0인 live+history/extra history
  동시 허용과 P1 receipt fresh-path overwrite/delete race를 exact closed inventory와
  non-replacing atomic-new publication으로 수리했다. dataset/model은 SHA-pinned read-only
  input이라 서로 다른 fixed local volume을 허용하고, mutable run/output/report만 atomic
  promotion을 위해 같은 volume으로 묶는 명시적 계약을 유지해 재감사받는다.
- compact 뒤 지정 SSoT 5종과 active goal을 순서대로 복구하고 HEAD=origin/main
  `59a2363`, 실제 6 modified+2 untracked의 8개 worktree 경로, AIRI trainer/runner 0,
  corpus/base/E1 exact SHA, E2/T3/campaign 부재와 E2 로그 각 0 bytes를 재대조했다.
  GPU에는 비-AIRI OS/app process가 있지만 AIRI workload는 0이다. 문서의 6-file 표기를
  8-file 관측값으로 정정했다.
- 최신 독립 감사 판정은 P0 5/P1 3, controlled GPU `NOT READY`다. checkpoint-event
  연속성·latest 결속, safe-pause 부분 archive 전원차단 복구, exact/600초/4구간 고정,
  TF32 포함 deterministic 환경 pin, end-to-end fixed-volume/reparse가 P0다. wall/monotonic
  대조, payload/comparator identity receipt, safe `torch.load`가 P1이다. runner archive
  idempotency와 runner/trainer path 검증의 직전 부분 수정은 미검증이므로 전체 blocker와
  fault 회귀를 수리해 독립 P0/P1 0·offline PASS·commit/push 전에는 GPU/E2를 실행하지 않는다.

## 2026-08-22 P0-B GPU 증거 계층 구현 intent

- HEAD=origin/main `59a2363`, AIRI trainer/runner 0에서 두 독립 read-only 탐색을
  수행했다. P0-A는 full-state 복구에는 충분하지만 checkpoint별 durable wall-clock
  event와 GPU baseline 대 pause/resume 정식 comparator/determinism pin이 없어 현재
  실행은 P0-B 증거로 승격할 수 없다. root는 trainer timing/determinism, 분리 worker는
  verifier/test만 소유해 offline 구현하며 검증·commit/push 전에는 GPU/E2를 실행하지 않는다.
- live state의 직전 수동 `17:56` 시각이 실제 `Get-Date 17:51`보다 미래였던 문서 오차를
  관측 시각으로 정정했다. 기계/Git/runtime 상태 차이는 없었다.

## 2026-08-22 P0-A offline milestone compact 복구 대조

- actual implementation push receipt의 SSoT 6종 반영 뒤 continuity PASS, repo 기본
  diff-check whitespace error 0, exact 6-doc 변경, 금지 filename/content hit 0이다.
  exact 6-doc receipt commit/push 실패 시 controlled GPU/E2로 이동하지 않는다.
- 구현 commit `6f0c1358d2acd18b828ebc0ae8482a348712c461`을 origin/main에 push했고
  HEAD=origin/main, AIRI trainer/runner 0을 대조했다. actual receipt를 SSoT 6종에
  반영해 focused continuity/diff/security와 별도 docs receipt commit/push를 마치기
  전에는 controlled GPU/E2를 시작하지 않는다.
- exact 16-file 구현 commit 성공: `6f0c1358d2acd18b828ebc0ae8482a348712c461`
  (`feat: add durable AIRI training recovery`), 16 files, 5,134 insertions/48 deletions.
  직후 worktree clean, local main은 origin/main보다 1 ahead다. exact push가 실패하면
  controlled GPU/E2로 이동하지 않고 이 commit에서 복구한다.
- exact 16-file `git add` exit 0, staged 16개·unstaged 0·untracked 0, staged
  diff-check exit 0이다. 최초 staged 통계는 5,124 insertions/48 deletions이며 이 receipt
  두 문서를 재-stage·재검증한 뒤 구현 commit을 실행한다. commit 실패 시 push/GPU/E2를
  실행하지 않는다.
- post-compact 정정 뒤 continuity PASS, repo 기본 diff-check whitespace error 0,
  exact 16개 파일의 금지 산출물 filename·비밀 값 형태 content hit 0을 확인했다.
  10개 구현/회귀 payload manifest SHA는 `dc8fca8e...6463e`다. exact 16-file stage,
  staged 경계 재검증, `feat: add durable AIRI training recovery` commit/push 중 하나라도
  실패하면 controlled GPU를 시작하지 않으며 P0-B GPU receipt 전 E2 금지를 유지한다.
- 17:40 KST 지정 SSoT 5종을 순서대로 전체 재독하고 active goal, HEAD=origin/main
  `e93d552`, corpus/base/E1 exact SHA, E2/T3/campaign 부재, E2 로그 각 0 bytes,
  AIRI trainer/runner 0을 재확인했다. GPU에는 비-AIRI OS/game process가 있으나 AIRI
  workload는 0이다. 직전 milestone 문서 갱신으로 실제 worktree가 9 modified +
  7 untracked, 총 16개가 됐지만 live state에 이전 12개가 남은 차이를 관측값으로
  정정했다. 16개 배치 continuity/diff/security와 exact commit/push 전에는 controlled
  GPU를 시작하지 않으며 P0-B GPU receipt 전에는 E2를 계속 금지한다.

## 2026-08-22 코덱스 PC P0 구현 compact 복구 대조

- live-control retention 뒤 재감사는 P0 0/P1 2, GPU NOT READY다. control 검증이
  index commit 뒤라 정상 archive race/invalid receipt에서 API 실패와 durable index 전진이
  갈리고, dangling symlink가 exists 검사에서 빠진다. side-effect 전 immutable bytes
  snapshot+lexists 검증과 index 불변 fault로 수리한다.
- N/N+1과 pause/supervisor P1 수정 뒤 재감사는 P0 1/P1 0, GPU NOT READY다.
  acceptance N 뒤 runner heartbeat 전 N+1·N+2가 publish되면 retention이 N을
  archive해 재부팅 acceptance 검증을 막는다. live ack/acceptance reference를
  control archive 전 keep-set에 결속하고 N+2 회전 fault를 추가한다.
- 최신 handshake 뒤 독립 감사는 P0 1/P1 2+가용성 P1 1로 GPU NOT READY다.
  accepted pause checkpoint N과 archive 전 새 latest N+1을 잘못 동일시하는 P0,
  pause 도구의 junction/mapped 선행 검증·corrupt current→previous fallback 부재,
  supervisor-failed 뒤 verified final reconciliation 제한을 fault 회귀와 함께 보강한다.
- 17:09 KST compact 복구에서 SSoT 5종과 active goal, HEAD/origin, 5 modified+
  7 untracked, AIRI trainer/runner 0, corpus/base/E1 exact SHA, E2/T3/campaign 0을
  재대조했다. 직전 focused receipt 뒤 full-pin acceptance handshake와 fake-trainer
  회귀가 부분 편집됐지만 아직 실행 검증되지 않았으므로 direct-trainer mismatch와
  request-only power-cut 복구, 전체 재검증·독립 재감사 전에는 GPU/E2 금지를 유지한다.
- 두 전원차단 P0를 구현해 focused `17 passed`. unindexed same-name generation은
  quarantine/replay하고, final artifact는 full manifest+pins+report+completed progress면
  complete terminal을 복구하며 partial/tmp는 same-volume quarantine 후 resume한다.
  full-pin acceptance 전 pause-control 보존 P1과 전체 재감사 전에는 GPU/E2 금지다.
- 최신 독립 재감사는 새 전원차단 창 P0 2/P1 1로 GPU NOT READY. generation publish→index
  사이 unindexed same-name 충돌, final adapter/report→runner terminal 사이 existing-output
  복구 부재가 P0이며, child full pins 전 pause-control archive가 P1이다. unindexed 격리,
  verified-complete 승격/partial quarantine, full-pin acceptance 회귀 전에는 GPU/E2 금지다.
- resume argv canonical SHA와 run-state process identity strict schema를 양쪽에 추가하고
  parseable malformed current→valid previous quarantine 회귀로 강화했다. 전체 Python
  `30 passed, 1 skipped`, PowerShell PASS를 유지했다. 독립 재감사 전에는 GPU/E2 금지다.
- Python 위임 diff를 root 검토·보강한 전체 P0 focused는 `30 passed, 1 skipped`, 강화
  PowerShell fault contract는 PASS. torn/structural index, invalid manifest, generation
  격리, cursor/checkpoint 단조성, exact changed-command 거부+pause 증거 보존, corrupt
  run-state/junction/orphan/late-complete/live resume를 모두 포함한다. 독립 재감사와
  controlled GPU/10분 실측 전에는 E2를 계속 차단한다.
- PowerShell 강화 fault contract 최종 PASS. malformed paused ack 거부, late pause의 durable
  complete artifact receipt/PID 0→SAFE, actual orphan 거부, junction 선행 생성 0,
  corrupt current 격리→previous resume→complete와 기존 live pause/resume를 모두 실증했다.
  Python 위임 diff와 전체 재감사 전에는 controlled GPU/E2를 계속 차단한다.
- dictionary schema 수리 뒤 late-complete/orphan/junction/corrupt-state resume 본경로는
  모두 통과했고, 실제 quarantine 파일도 생성됐다. 네 번째 실패는 test glob의 토큰
  순서 오타뿐이므로 actual `run-state.corrupt.*.json` 규약으로 고쳐 재실행한다.
- named parameter 수정 뒤에도 active request가 `[ordered]` dictionary인 경계에서 JSON
  property helper가 dictionary 메타속성을 읽어 같은 실패가 재현됐다. helper를
  `IDictionary.Keys`/PSCustomObject 양쪽 계약으로 수정해 실제 schema만 판정하게 한다.
- complete receipt의 trailing-LF canonical hash를 맞춘 뒤 두 번째 PowerShell 실행은 strict
  property helper의 positional array binding 결함으로 fail-closed했다. 모든 JSON property
  검증 호출을 named parameter로 고정하고 같은 synthetic fault 계약을 재실행한다.
- PowerShell corrupt-state/ack/late-complete/orphan/reparse fault 회귀 첫 실행은 complete
  directory receipt의 Python-vs-PowerShell canonical row-list hash 차이로 exit 1했다.
  개별 file inventory/SHA 뒤 fail-closed한 synthetic 실패이며 로그 본문은 읽지 않는다.
  canonical bytes를 exact 재현해 재실행하기 전에는 PowerShell P0/P1을 승격하지 않는다.
- 최신 독립 재감사는 P0 2/P1 6, controlled GPU NOT READY다. torn index previous 복구와
  PowerShell corrupt current run-state 진입이 P0이고, cursor/checkpoint 단조성·publish-time
  corrupt generation 격리·paused ack schema·final pause/complete race·pause control 보존·
  reparse/mapped 선행 부작용이 P1이다. final artifact/complete revalidation, stale revision,
  orphan 분류, CUDA/BnB pins, child reap/single terminal write는 양호로 확인했다.
- artifact manifest SHA를 실제 bytes와 결속하고 run identity만 분리한 pins/file inventory
  및 학습 상태 exact 비교로 회귀를 정정했다. 동일 focused Python은
  `24 passed, 1 skipped`, PowerShell live pause/resume durability는 PASS. final adapter
  flush/fsync/inventory/write-through publication과 CPU 중단·재개 exact 증거를 확보했지만,
  남은 P0/P1 fault 회귀와 controlled GPU/10분 실측 전에는 E2를 차단한다.
- `_fsync_file`을 write-capable descriptor로 수리해 final artifact 관련 기존 3실패를
  제거했다. 재검증은 Python `23 passed, 1 skipped, 1 failed`, PowerShell PASS이며,
  남은 한 건은 서로 다른 run identity가 결속된 artifact manifest SHA까지 학습 summary
  exact 비교에 포함한 새 회귀 계약 문제다. 학습 상태 동등성과 artifact identity/무결성을
  분리해 재검증하기 전에는 exact-resume/P0를 완료 처리하지 않는다.
- 16:31 KST compact 복구에서 SSoT 5종, active goal, HEAD/origin, PID와 모든
  corpus/base/E1/E2 후속 산출물을 재대조했다. 실제 worktree는 5 modified + 7 untracked,
  trainer/runner와 E2/T3/campaign 산출물은 0이다. 최종 adapter write-through 승격 보강 뒤
  Python focused는 read-only descriptor `os.fsync`의 Windows `Bad file descriptor`로
  `21 passed, 1 skipped, 3 failed`; PowerShell durability는 PASS였다. 동일 원인의
  `_fsync_file`을 수리·재검증하기 전에는 P0/GPU/E2를 승격하지 않는다.
- startup identity wait와 중복 redirect 제거 뒤 강화 live PowerShell contract PASS.
  active trainer PID/command 대조→pause checkpoint/ack→SAFE→관련 PID 0→explicit resume→
  control archive→terminal artifact receipt 전 경로를 실증했다. 재감사 P0 3건과 GPU/10분
  실측 전에는 controlled GPU와 E2를 계속 차단한다.
- launcher의 verified starting receipt와 trainer PID 게시 사이 startup race에서
  safe-pause가 거부되는 회귀를 검출했다. starting/running 상태에서는 bounded exact
  trainer identity 대기를 추가하며 terminal 전환은 fail-closed한다.
- runner PID 종료 뒤에도 남은 stderr lock을 Start-Process redirector Process 객체의
  명시 Dispose 누락으로 분리했다. launcher handle 누수를 수리하고 contract를 재실행한다.
- 강화된 live PowerShell pause→checkpoint→ack→SAFE→explicit resume→artifact receipt
  본경로는 통과했지만 terminal 직후 runner stderr handle 종료 전 temp cleanup이 경합해
  test exit 1. runner PID 종료 대기 뒤 재실행해야 최종 PASS로 인정한다.
- venv redirector와 실제 runner PID를 분리한 뒤 PowerShell durability contract PASS.
  공백 경로+hidden background launcher의 독립 runner/run-state/heartbeat/PID-command/
  terminal artifact receipt와 verified `SAFE_TO_POWER_OFF` 경로를 offline 실증했다.
  controlled GPU/10분 checkpoint 실측 전까지 P0-B는 미완료다.
- Windows venv의 단명 redirector PID와 실제 interpreter runner PID가 다른 경계를
  launcher가 잘못 동일시한 추가 실패를 확인했다. 새 run-state의 exact process identity를
  권위로 삼고 redirector exit만으로 실패하지 않도록 수정한다.
- executable hash 수리 뒤 launcher는 state-read와 terminal-write/exit 사이 final race로
  다시 실패했다. `HasExited` 직후 terminal run-state를 최종 재확인하는 회귀를 추가하며
  launcher 검증 전에는 P0/E2를 승격하지 않는다.
- launcher 계약을 핀된 venv Python으로 재실행했지만 별도 원인으로 run-state 전 종료했고
  exit code도 비어 있었다. 실패 runtime stderr/command quoting을 다시 대조하며 hidden
  background launcher는 계속 미검증이다.
- epoch-complete checkpoint 보강 뒤 Python focused는 `23 passed, 1 skipped`지만,
  PowerShell hidden-background launcher 통합은 run-state 전에 runner가 종료해 FAIL했다.
  임시 로그가 test cleanup으로 제거돼 원인 receipt가 부족하므로 진단 로그를 보존해
  quoting/Start-Process 경계를 재현하며 launcher는 아직 검증 완료가 아니다.
- 실행되는 CPU 중단·재개 동등성 회귀를 추가해 무중단 대 optimizer 경계
  pause/checkpoint/resume 실행의 LoRA tensor, AdamW/LambdaLR, 모든 RNG, loss/cursor/
  counter/summary exact 일치를 `1 passed in 8.53s`로 증명했다. 기존 1 skip은 CUDA
  장비에서 gpu-less refusal만 생략한 것이며, controlled GPU/10분 실측은 아직 남았다.
- 두 번째 수정 뒤 focused pytest는 `22 passed, 1 skipped`, 실제 subprocess
  safe-pause→checkpoint→explicit resume→terminal receipt와 PowerShell safe-pause
  contract가 PASS했다. 남은 Torch-stack skip 때문에 tensor 동등성은 미증명이며
  P0-A/P0-B와 E2 gate는 계속 미완료다.
- 첫 실패 수정 뒤 PowerShell durability contract는 PASS했고 Python focused는
  `21 passed, 1 skipped, 1 failed`다. 남은 실패는 초단명 fake trainer가 Windows
  CIM PID identity 캡처 전에 끝난 테스트 경쟁으로, runner 자체는 fail-closed 및
  terminal failure receipt를 남겼다. 관측 창을 추가해 pause/resume 본경로를 재검증한다.
- 첫 통합 focused 회귀는 `20 passed, 1 skipped, 2 failed`, Python py_compile PASS,
  PowerShell durability contract FAIL이었다. 두 Python 실패는 heartbeat가 빠진 테스트
  fixture와 같은 runner 프로세스 안의 즉시 재진입이 종료 전 runner PID와 일치한
  회귀 설계 문제이고, PowerShell 실패는 script 호출 뒤 미설정 `$LASTEXITCODE` 참조다.
  실제 GPU/서비스/E2는 0이며 수정·재검증 전까지 P0 완료로 승격하지 않는다.
- compact 직후 지정 SSoT 5종을 순서대로 전체 재독하고 goal active,
  HEAD=origin/main `e93d552`, Python trainer/durable runner 0을 read-only로 확인했다.
  E2 adapter/report·T3 manifest/output·durable run directory는 없고 기존 E2 로그 2개만
  각 0 bytes다. GPU·서비스 실행은 0이다.
- worktree에는 15:37 P0 intent 뒤 만들어진 trainer/checkpoint/runner 부분 구현
  2 modified + 3 untracked만 존재한다. live state에 남아 있던 pre-milestone
  HEAD/worktree와 다음 행동을 관측 사실로 정정했으며, exact 인터페이스 통합과
  offline 회귀가 끝날 때까지 P0-A/P0-B와 E2 gate는 미완료로 유지한다.

## 2026-08-22 코덱스 PC goal 재개 + P0 내구성 게이트 (intent)

- 사용자 `/goal` 명령으로 기존 pause가 해제됐고 goal은 `active`다. 저장소 구현,
  GPU 학습, merge/package, 로컬 서비스, T3·campaign, 검증된 milestone commit/push가
  허가됐지만 운영 모델 채택과 기본 서비스 모델 변경은 별도 승인 전까지 금지한다.
  아래의 paused checkpoint 항목은 당시 receipt로 보존하며 현행 권한으로 사용하지 않는다.
- 15:09 KST read-only 독립 감사에서 HEAD `0c0ffbe`, 9 modified + 2 untracked,
  trainer/Python 0을 확인했다. corpus source/chat, base model, E1 adapter/config/report
  SHA와 E1 dev `2.8938066467`은 exact이고 E2 adapter/report·merge/package·T3·campaign
  산출물은 0이다.
- 첫 milestone은 기존 문서·지속성 배치를 active 상태와 아래 P0 순서에 맞춰 정정한 뒤
  focused/full offline test와 `git diff --check`를 통과시켜 commit/push하는 것이다.
  그전과 P0 실증 전에는 GPU·서비스·E2를 실행하지 않는다.
- 다음 실행 순서는 `P0 power-off durability(checkpoint/exact resume/atomic rotation/
  durable runner/safe pause/reboot recovery/10분 손실 상한 실증) → E2 preflight → E2
  step 0 → provenance → merge/package → 36 T3 → 승자 3×500 → 사용자 증거 제출`이다.
- continuity 회귀가 세 SSoT의 P0/E2 lexical 순서 결함을 차례로 검출해 정정했다.
  direct trainer block은 PRE-P0 실행 금지 참고로 격리하고 실제 E2는 P0 receipt의
  authoritative durable runner만 사용하도록 결속했다. 공통 goal/adoption/order token,
  strict frontmatter, git ancestor, P0-A→P0-B→E2-LAUNCH 구조 회귀를 추가했다.
- focused continuity PASS, 전체 offline checkpoint PASS(19.06초), 핀된 Python 3.12의
  reference/pilot 회귀 7/7 PASS, repo 기본 `git diff --check` exit 0, secret/금지
  산출물 hit 0. 독립 재감사 P0/P1 0, READY로 첫 milestone commit을 승인했다.
- 첫 milestone 본체를 `e822f9f120e27e561d2e90353da4ba8315e4e3dd`
  (`docs: harden long-goal continuity`)로 commit하고 `origin/main` push를 확인했다.
  이 배치에서 GPU·서비스·E2 실행과 운영 모델 변경은 0이다.

## 2026-08-22 코덱스 PC 문서 배치 (paused checkpoint + 재개 체크리스트)

- compact·재부팅·goal resume 누수를 막기 위해 `AIRI-WORKING-STATE.md`를 신설했다.
  세션/compact 후 문서 재독과 실상 대조, active goal 최대 60분 heartbeat,
  10분 이상 명령 및 checklist 전후 intent/receipt, milestone 장기 문서 승격을
  `AGENTS.md`에 의무화하고 offline checkpoint에 문서 계약 테스트를 편입했다.
  첫 focused 실행에서 PowerShell 5.1의 BOM 없는 UTF-8 한글 스크립트 parse 실패를
  검출해 테스트를 ASCII-only 파일 탐색으로 수정했고, focused contract와 전체
  offline checkpoint가 최종 PASS했다.
- 사용자 요청에 따라 AIRI 본 goal을 `paused`로 명시했다. 명시적 “재개” 전에는
  GPU 학습, merge/package, 서비스, T3, live campaign을 실행하지 않는다.
- current-state read-only 감사에서 HEAD `0c0ffbe` clean, trainer 0, v4 corpus 두 SHA와
  E1 adapter/config/report SHA exact를 확인했다. E2 adapter/report, E1/E2 merge/package,
  v4 T3 manifest/output, live campaign output은 모두 0이다. 2026-08-22 세 번째 E2 시작
  흔적인 stdout/stderr 두 파일은 각각 0 bytes이며 checkpoint가 아니다.
- 설명 문서에 남은 초기 7건은 현행 event reference 30건·11명과 별도 continuity arc
  7건으로 정정했다. 사용자 지정 사례는 `OBS-S01`로 결속했고 식별자는 원장에만 둔다.
- 재개 순서를 `명시적 재개 → E2 step 0 완주 → provenance → E1/E2 merge/package →
  36-report T3 → 승자 3×500 → 실제 응답·증거 제출 → 사용자 채택 판단`으로 고정했다.
  08-21 테스트 수치는 역사적 증거이며 이번 paused 문서 배치에서 GPU·서비스 테스트는
  재실행하지 않았다.
- 문서 갱신 뒤 방송 reference/pilot 회귀 테스트 **7/7 PASS**, 오프라인 checkpoint
  contract **PASS**, `git diff --check` whitespace 오류 0을 확인했다. checkpoint 검증은
  synthetic ASAR만 사용했으며 설치본·서비스·모델에 접근하거나 goal을 재개하지 않았다.

## 2026-08-21 코덱스 PC 배치 (isolated T3 36-run launcher 확정)

- `run-airi-broadcast-t3-matrix.ps1`을 새로 추가해 baseline/E1/E2 × 세 fixture ×
  네 seed의 exact 36-run을 한 경로로 고정했다. 세 모델 모두 `seeded`와 동일 live
  context/briefing/evidence/acts, max 220, timeout 180, num_ctx 2048를 사용한다.
- exact tag/digest manifest, 승인 fixture raw/canonical retained-copy 검증, run별 fresh
  empty memory/knowledge DB와 capability, 실행 전후 local/pinned/ready health, immutable
  stream plan의 전체 turn 집합, unique action/trace와 durable receipt를 fail-closed로
  검증한다. 두 12-pair 비교는 36 reports 이후 모두 실행하고 산출물 전체를 해시한다.
- GPT-SoVITS reference-embedding cache wrapper, streaming mode 2/min chunk 16과 부모 PID+
  exact command identity cleanup을 고정했다. 하위 시작 script가 바꾸는 reference audio,
  NLTK/PYTHON 환경도 호출자 값으로 복원한다.
- launcher 계약 8/8, 방송 sim/comparator 75/75(1 skip), PowerShell AST·py_compile·
  diff-check가 통과했고 독립 최종 감사가 P0/P1 0 READY로 판정했다. E2 tag가 아직 없어
  실제 서비스/GPU matrix는 시작하지 않았으며 운영 채택은 계속 금지다.
- 전체 checkpoint에서 기존 추적 방송 테스트 15개의 CI matrix 누락을 발견해 해당
  eval/runtime/training tests와 새 T3 launcher test를 shard에 등록했다. `AI` 허용 정책
  변경(`06d68e1`) 뒤 stale했던 B3-d raw policy/corpus pin을 현 production bytes에
  재결속했고 120-case verdict 100/100 불변을 확인했다. AB dry-run transport에도 실제
  stream과 같은 terminal 증적을 추가했다. 최종 `test-current-checkpoint.ps1` PASS,
  B3-d 16/16·B4c rehearsal 83/83 PASS다.

## 2026-08-21 코덱스 PC 배치 (broadcast continuity v4 확정 + E1 QLoRA)

- runtime prompt seam으로 실제 proxy가 모델에 보내는 순서를 재현하는 v4 corpus
  1,000행을 확정했다. split 800/100/100, source SHA `43f9c1ed1abf`, chat SHA
  `96cc223ca591`, 최대 2,010 tokens로 seq2048 무절단 계약이다. 40개 card partition,
  memory known/unknown·donation·briefing/topic·grounding/capability·natural broadcast를
  포함하며 교차 split fact/update/decoy token 충돌, 이중 ID, source/chat target drift는
  모두 0이다. generator 8/8과 독립 한국어/소유권/거짓 행동 감사가 통과했다.
- RTX 3060 Ti에서 r8/alpha16/dropout.05/lr2e-5/seq2048/b1/GA16 E1을 완료했다.
  800 microsteps/50 optimizer updates, train first3 3.3845→last3 2.9151, dev 2.8938,
  peak PyTorch CUDA 6,134,145,536 bytes다. adapter SHA `379b2a5aba1e`, report SHA
  `0f71b042a743`; dataset/base pin exact, base copy 없음, T3 pending·채택 금지다.
- E2 2-epoch 실험은 사용량 한계가 가까워졌다는 사용자 요청으로 첫 실행 약 14분,
  인계 재검증 중 두 번째 실행 약 3분 시점에 안전 중단했다. 둘 다 checkpoint 전이며
  GPU는 해제됐고 E2 adapter/report/partial output은 없다. 다음 세션은 인계문의 exact
  명령으로 처음부터 재실행한다.
- 다음 게이트를 baseline/E1/E2 × first/second calibration 4-seed × final-blind
  180분 4-seed의 36 reports로 고정했다. T3 전용 isolated launcher 보강 후 우승 후보만
  trace-bound RAG/journal/TTS/latency/closure를 증명하는 3×500 live campaign으로 간다.
  서비스 모델·운영 태그·greybox·extraction은 변경하지 않았다.
- T3 isolated launcher 첫 초안은 독립 감사에서 PowerShell 배열 비교, health schema,
  모델/memory-arm confound, 반복 보고서 디렉터리 생성 P0를 확인해 반려하고 삭제했다.
  미검증 초안은 push하지 않았으며, 다음 구현의 추가 필수 계약은 현행 GPU 인계문에
  기록했다.

## 2026-08-21 코덱스 PC 배치 (broadcast continuity v3 학습 + 실제 스택 게이트 정렬)

- **한국 방송 반응과 장기 연속성을 같이 학습하는 v3 1,440행을 확정했다.**
  120개 continuity card의 즉시·지연 기억, 사실 선택, 업데이트, 호명 방어,
  무관 정보 방어, 주제 복귀 등 1,200행과 기존 broadcast v2 240행을
  card-group 단위 train/dev/test **1,148/146/146**로 나뉘었다. 최종 chat SHA-256은
  `2f330faec39dd23a0c44bb68794757c28242ceff6abd3324dfc90bfa4472329b`, source SHA-256은
  `3f69a8515b074db750317eaa9c4756ae6baae3a14ab8f3ba62c38a458f98d71a`다.
  전체 한국어 문법·조사·별칭·거짓 실행·근거 없는 기억 약속을 재감사해
  training blocker **0**, quality gate PASS를 확인했다.
- **RTX 3060 Ti 전체 QLoRA를 현재 실행 중이다.** 최장 train 예제는
  1,626 tokens이며 `max_seq_len=1648`, r=8/alpha=16, gradient accumulation=12,
  2 epochs(2,296 microsteps/192 optimizer steps)로 고정했다. 1-step·30-step 선행
  GPU probe는 최대 CUDA **5,364,815,872 bytes**에서 통과했고 30-step loss는
  처음 3개 평균 4.6422에서 마지막 3개 평균 4.0801로 내려갔다.
  전체 학습 어댑터는 아직 T3 미통과이므로 채택·운영 승격은 **OFF**다.
- **T3가 실제 모델에 준 입력과 학습 입력의 구조 불일치를 닫았다.** 기존
  러너의 무기명 system에 신원·오늘 방송·브리핑을 합친 내용이 proxy에서
  active character card로 재분류되던 것을 재현했다. 이제 인증된 일회성
  live-broadcast capability가 closed v1 context를 server-owned
  `airi_broadcast_context`로 생성하고, 일반 호출자가 `[오늘 방송]`을 흉내 내도
  방송 문체나 컨텍스트를 활성화하지 못한다. 러너는 live mode에서 system 입력을
  전혀 보내지 않고, turn capability→chat→trace-bound durable receipt→close 전 과정을
  fail-closed로 완료한다.
- **3×500-turn 캠페인의 거짓 양성 통로를 제거했다.** 기억 표식은 모델
  프롬프트에서 제거하고 감사 원장에만 별도 결속했으며, matched decoy는
  arc 내용을 모델에 주지 않는 실제 미노출 대조군이 됐다. RAG·저널은
  전역 카운터 대신 요청/answer SHA, 승인 document/chunk ID, durable append를
  각 `trace_id`에 묶은 content-free receipt로 검증하고, LLM start→content→end→
  TTS start→first→end 시각 순서도 강제한다. 아직 실제 1,500턴은 T3 통과 후에만
  실행한다.
- 오프라인 검증: proxy **364 passed**, live runtime **19 passed**, broadcast runner
  **54 passed**, campaign **7 passed**, v3 generator **9 passed**. 모든 greybox·memory extraction·
  외부 chat/search는 OFF이며, 새 adapter/model의 운영 채택은 T3+사용자 승인 전까지
  금지다.

## 2026-08-21 코덱스 PC 배치 (사용자 총평 반영 — 한국 방송 반응 메타 재설계)

- **기존 행동 검수 181건과 affect 행동 검수 120건을 사용자 승인 대기에서 반려
  초안으로 내렸다.** 사실·안전 오류가 아니라 방송 단위가 잘못됐다. 기존 행동 답변은
  중앙값 13자(입력보다 짧은 답 64/181), affect는 중앙값 14자(51/120)이고,
  후원·선택 채팅을 `감사/인지 → 메시지별 반응 → 의견·에피소드 확장 → 복귀·다음 훅`
  으로 만드는 맥락이 없다. 두 폼 회신 적용과 행동 QLoRA는 금지하며 파일은 실패
  재현용으로 보존한다.
- **탬탬버린·아리사 공식 1차 출처를 새 관찰 기준으로 코딩했다.** 탬탬버린은 단건·연속
  후원을 짧은 의례로 처리한 뒤 원 주제로 돌아가고, 다수 채팅은 집계한 뒤 자기 입장과
  이유로 길게 확장한다. 아리사는 공개 공식 영상에서 확정 가능한 2장면만 채택했으며,
  짧은 제안은 즉시 되묻기·작업 전환으로, 내용 있는 후원은 반문·논평으로 확장했다.
  시청자 이름·실제 금액·원문은 수집하지 않았고 특정 방송인의 캐치프레이즈·개인 문체를
  학습 target에 복사하지 않는다.
- **새 SFT 계약은 event envelope와 가변 beat로 재정의했다.** 일반 채팅/후원/구독/
  집계 채팅, 단건/폭주, 현재 방송 주제와 최근 AIRI 발화를 입력에 포함하고 target을
  acknowledgment·message-specific reaction·expansion·handoff/hook으로 검수한다.
  전역 반말 금지/강제와 단일 글자 수 상한은 폐기 후보이며 beat별 register와 이벤트별
  길이 분포로 대체한다. 다음은 아리사 1차 사례 추가 확보와 코딩 후 AIRI 고유 20~30건
  파일럿을 한 묶음으로 사용자에게 보여 주고 행별 승인 작업 없이 총평을 받는 것이다.
- 근거: `참조/AIRI-KR-BROADCAST-REGISTER-REFERENCE-2026-08-21.md`. affect·memory
  greybox 운영 플래그는 계속 OFF이고, 기존 행동 큐·추출 큐에서 reviewed/SFT/adapter
  산출물은 만들지 않았다.
- **공식 관찰 7건을 학습 데이터와 분리된 기계 판독 레퍼런스로 만들었다.** 별도
  출처 원장은 공식 URL·타임스탬프·증거 한계만 보관하고, observation JSONL에는
  event/queue pressure/response beat/register/handoff만 남겼다. 원문·닉네임·금액·
  방송인 식별자·URL은 0이며 전건 `training_permitted=false`. 아리사 공식 아카이브
  후보도 색인했으나 timed-text 빈 응답과 transcript API `FAILED_PRECONDITION`으로
  연속 장면 검증이 안 되어 추가 확정 0건, 후보 원장 격리로 처리했다.
- **AIRI 고유 24건 파일럿을 새 schema/queue로 격리 작성했다.** 후원 6·구독 2·
  선택 채팅 5·집계 채팅 3·기타 전환/경계 8, split 16/4/4, single/burst 15/9,
  compact/standard/expanded 4/10/10이다. 첫 자동 초안의 과도한 정중체와 근거 없는
  과거 경험을 root 검수에서 반려하고 전량 재저작했다. 현행 target은 46~135자,
  중앙값 98자, 입력보다 짧은 답 0/24, 실제 방송인 문구·개인 서사 0이며 전건
  `pending_batch_feedback`, `training_eligible=false`다.
- 검증: `python -m unittest ollama-proxy/training/tests/test_broadcast_reference_and_pilot_data.py`
  **6 passed**. 관찰-원장 7건 결속, 파일럿 분포·split·beat/register 정렬,
  기존 301 target과 exact 비중복, 출처·PII·금액·URL·가짜 과거 경험 누출,
  급성 안전 지침과 학습 금지선을 고정했다.
- 사람이 읽는 24건 전체는
  `진행예정/AIRI-KR-BROADCAST-RESPONSE-PILOT-2026-08-21.md`로 별도 렌더했다.
  체크박스나 행별 승인 없이 다섯 축의 묶음 총평만 받는다.

## 2026-08-21 코덱스 PC 배치 (affect 행동 검수 트랜치 준비)

- **표현 선택기만으로 품질이 오르지 않은 결과를 행동 학습 데이터로 전환했다.**
  기존 행동 pending 181건은 바꾸지 않고, 13개 affect primary의 자연스러운
  반응과 안전한 받아치기를 담은 별도 pending **120건**을 생성했다. 상태별 8건,
  `playful_annoyed`·`concerned`는 각 16건이며 split은 train/dev/test
  **90/15/15**다. 전건 reducer 재생 state와 현재 continuity+expression
  request-local prompt가 정확히 일치하고, 기존 181건 및 frozen affect 평가
  fixture와 prompt/answer exact overlap은 0이다. 이 120건은 첫 검수·학습
  트랜치이지 충분한 성격 형성을 증명하는 최종 규모가 아니다.
- **사용자 검수 폼 3종이 현행 큐에 결속돼 준비됐다.** 기존 행동 폼도 추출 폼과
  같은 LF-normalized queue SHA fail-closed 계약으로 보강해, 같은 ID·건수에서
  내용만 바뀐 stale 회신도 거부한다. 현행은 행동 181건
  `AIRI-BEHAVIOR-REVIEW-FORM-2026-08-19.html` (`eab7f6b76c06`), affect 행동
  120건 `AIRI-BEHAVIOR-AFFECT-REVIEW-FORM-2026-08-21.html`
  (`96d0d2d3c69d`), 추출 102건 `AIRI-EXTRACTION-REVIEW-FORM-2026-08-20.html`
  (`2988a82bd738`)이다. 검수 localStorage도 queue SHA별로 분리해 오래된 결정을
  새 큐로 자동 승계하지 않는다.
- **검수 이후 단일 행동 QLoRA 입력으로 안전하게 합칠 경로를 닫았다.** affect
  레코드는 운영과 같은 `system` + `system,name=airi_request_local` + `user` +
  `assistant` 4-message 형태로만 익스포트되고, 기존 181건은 3-message 형태를
  유지한다. exporter는 복수 `--reviewed` 입력·전역 ID 중복·split·state/event
  재생·prompt drift를 fail-closed 검증하며 트레이너도 두 정확한 형태만 받는다.
  `moderation_block`은 응급 119 안내와 분리해 boundary+대안으로 고쳤다.
  training tests **136 passed, 3 skipped**, 두 행동 폼의 내장 JavaScript
  `node --check`, 전체 `test-current-checkpoint.ps1`가 통과했다. 사람 회신을
  위조하지 않았고 reviewed/SFT/adapter 산출물은 만들지 않았으며 affect·memory
  greybox 운영 플래그는 OFF다.

## 2026-08-21 코덱스 PC 배치 (affect→표현 선택기 격리 실험)

- **런타임 affect 2단계의 표현 선택 기반 구현, 운영 승격은 보류** — 사용자의
  "정직하지만 로봇 같고 위트·감정이 없다"는 평가와 "기분 좋음/독설적
  받아치기처럼 상태에 따라 달라져야 한다"는 방향을 반영해, 기존
  `affect_state.py`의 13개 primary를 closed expression 계약
  (`airi.affect-expression.v1`)으로 바꾸는 순수 선택기를 추가했다. 출력은
  기존 wire enum만 쓰고, `playful_annoyed`는 재치 있는 받아치기+모욕·비하·
  위협 금지, safety/deescalate는 즉시 careful로 강제한다. free text·시계·DB·
  네트워크·LLM 의존성은 없고 한국어 투영은 최대 384 bytes다.
- **Mi:dm GPU 3-arm 결과: 변화는 있으나 캐릭터 품질 개선 증거 없음.** 고정
  synthetic fixture의 5상태 × 시드 3개에서 같은 히스토리·입력·샘플링을
  `off / typed snapshot / snapshot+expression` 15쌍·45호출로 균형 실행했다.
  표현 arm은 off·snapshot 대비 각 12/15에서 문자열을 바꿨지만,
  `playful_annoyed` 3건은 위트가 생기지 않았고, pleased 3건은 모두 같은
  실행 거부, competitive 3건은 문맥을 놓쳤다. safety 3건 중 2건은 off보다
  약한 안내(`심호흡을 해봐`, `바로 병원 가`)여서 승격 불가다. 지시를 한 차례
  구체화한 v2 재실측도 같은 12/15 변화와 같은 품질 결론이었다. 따라서
  **상태 선택만으로는 부족하며 행동 QLoRA에 감정·위트 표현 팔레트가 먼저
  필요하다.** 본 러너는 exploratory/no-gate이고 운영 affect·이벤트 ingress·
  memory greybox는 계속 OFF. 테스트 7+4 passed, evaluator runtime fence
  9 passed/2 skipped. 로컬 결과는 ignored
  `eval/affect_broadcast/local-results/affect-expression-probe-midm-{,v2-}2026-08-20.json`.

## 2026-08-20 코덱스 PC 배치 (검수 준비 + GPU 재실측 + Serena MCP 1회 평가)

- **P3-T2 사용자 검수 직전 준비 완료** — 인계문이 첫 extraction export 전
  필수로 남긴 split 도메인·빈 id·중복 id fail-closed 검증과 회귀를 추가했다.
  감사 중 Windows CRLF 큐 raw SHA `8375c9ec764e`와 배포 폼 SHA
  `2988a82bd738` 불일치도 재현했다. 그대로면 정상 회신이 구 폼으로 전건
  거부되므로 폼 생성기/적용기 양쪽 digest를 LF 정규화 내용 SHA로 통일하고
  EOL 안정성·내용 민감성 테스트를 추가했다. 현재 행동 폼 **181 unique**,
  추출 폼 **102 unique**, 추출 embedded/apply SHA `2988a82bd738` 일치.
  training 전체 **117 passed, 3 skipped, 21 subtests**. 사람 승인을 위조하지
  않았으며 reviewed/SFT 4개 산출물은 미생성 상태로 사용자 회신을 기다린다.

- **GPU 단일조건 재실측** — RTX 3060 Ti, Mi:dm 고정 digest,
  `num_ctx=4096`, `num_gpu=999`, 워치독 30초로 ctx 9런과 narrow evidence
  3런을 완주했다(총 12런·576턴, 전송 실패 0). h4/h8/h12 앵커는
  41/48/46 of 144, 사실 활용 5/7/5 of 90, 프로브 4/4/3 of 9,
  오프너 다양성 평균 78.5/81.3/84.0%로 **CPU의 h4 우위는 재현되지
  않았다**. narrow 부착 34/144·해제 2/34는 CPU 결정론 값과 정확히
  일치했고, 판단 축은 앵커 49/144·사실 4/90·프로브 2/9였다. 모든 런에서
  결정론 축 만점, 존댓말·이탈 0. 시드 분산 때문에 ctx 단일 승격은 보류한다.
- **Qwen3-8B span GPU 게이트 FAIL** — 문서 고정 digest를 확인하고 격리
  11436에서 `conversation-v3-span`, balanced, `num_ctx=8192`,
  `num_gpu=999` 7 fixture를 각 1회 실행했다. schema/A schema/B schema 1.0,
  connectivity/B coverage 0.857, critical recall 0.262, placeholder 0.857,
  B op-alias 0.143, `entity_reference_missing` 1건으로 FAIL. 소유 PID만
  종료했고 11436 listener가 사라진 것을 확인했다. 런타임 승인·운영 ON 없음.
- **TTS/marker 실측 환경 차단** — v2ProPlus 런처가 외부 GPT-SoVITS venv의
  `numpy` 누락으로 9880을 열지 못했다. 선언 범위 `numpy<2.0`을 보충했으나
  다음 필수 모듈 `soundfile` 누락에서 다시 중단됐고 `pip check`도 다수 선언
  의존성 누락을 확인했다. 따라서 canonical 7문장 live gate와 marker/audible
  실제 render A/B는 보류했다(당시 6121/Electron도 비가동). 레포 내부 proxy
  streaming/serial lock/cancel 계약은 Python 3.12 임시 환경에서 **23 passed**.
  greybox·memory extraction 운영 플래그는 계속 OFF다.

- 지시서 §1~§5를 순서대로 실행했다. Serena 1.7.0 설치·Python 382파일
  인덱싱·온보딩·TUI `/mcp`와 실제 심볼 참조 조회까지 성공했으나,
  `gpt-5.6-luna`/low 동일 과제 3세션/arm A/B에서 총 토큰 평균이
  ON 205,570 vs OFF 86,892(**ON +136.6%**)였고 ON 연결 미노출도 2회
  발생했다. 세 유형(심볼/리팩터링/설정·문서)이 모두 순손실이므로 지시서
  §6대로 `~/.codex/config.toml` 등록 블록을 제거해 **롤백**했다. 설치물·
  전역 ignore·인덱스·AGENTS 정책은 보존했다. 상세 thread ID·arm별 수치는
  `진행중/AIRI-CODEX-SERENA-TOKEN-ORDER-2026-08-20.md` §7. (레포 변경:
  `AGENTS.md`, 본 지시서 §7, 본 LOG만)

## 2026-08-20 클로드 PC 배치 (17커밋, `c4c3e35` → `4046d75`)

> 태스크 13종 배치. 각 항목 끝 괄호가 근거 문서·커밋이다. 커밋이 없는
> 항목(조사·측정 전용)은 근거를 본문에 직접 적었다. 이 배치의 핵심 반전은
> **Task 3 "히스토리 4가 최고" 권고 폐기**(스로틀 epoch 교락)이며, 사전 존재
> 결함 3건 수리와 워치독 env 클램프 함정 발견이 부수 성과다.

- **브리핑 근거 신호 계약 (P1-1)** — 08-19에 부수 발견으로만 등록돼 있던
  "absence 폴백이 모델 호출 **전에** 선점하고 요청 히스토리만 검사한다(브리핑은
  시스템 프롬프트라 검사 대상이 아니다)"를 **라이브로 확정**했다. 시드 22 T21
  요청을 그대로 재조립해 보낸 결과 헤더 없이는 **218 ms**에 결정론 폴백
  (`아직 기록이 없어. 어떻게 부르면 돼?`), 헤더를 붙이면 **11,299 ms** 모델 응답.
  디렉터→프록시 계약 `X-AIRI-Briefing-Evidence: memory`(확장 가능 토큰·정확
  일치·루프백 피어 전용)를 프록시에 구현하고, 브리핑 조립부가 근거 삽입 사실을
  본문과 함께 반환하는 방식으로 러너에 배선했다(문자열 재파싱 금지). 헤더 부재
  시 기존 경로는 바이트 동일(기존 테스트 344+37건 무수정 통과). 3시드 ×
  off/on 6런 실측: **결정론 축 6런 전부 만점·존댓말 위반 0/288턴·이탈 0·전송
  실패 0**, 선점 4건 해제(프록시 텔레메트리 `absence_bypasses=4`). 그러나
  **기억 프로브는 2/9 → 2/9로 불변** — "선점 해소는 됐고 모델 미활용이 남았다"로
  분리 보고하며 P3 게이트 근거를 한 줄 더한다. 주의: 08-19 기준선 런들은 기억
  ON이었고 이번 A/B는 기억 OFF라 절대치 직접 비교 불가(표 안의 off vs on만 비교).
  (`완료/AIRI-BRIEFING-EVIDENCE-SIGNAL-2026-08-20.md`, `f6a4167`+`df5b264`)

- **근거 정의 좁히기 + 해제 관측성** — 위 계약의 근거 판정이 프록시 선례
  (`MEMORY_QUERY_RE` — 기억형 발화만 인정)보다 넓다는 지적을 **디렉터 쪽 정의만**
  좁혀 해소했다. `bool(viewer_lines)`("이 시청자가 뭐든 말한 적 있다") →
  관련도 매칭된 줄이 최소 하나 존재. 결과: 부착률 **68.1%(98/144) → 23.6%(34/144)**,
  해제 건수 **4 → 2**. **이 감소는 좁힌 정의 기준의 결정론적 결과이지 품질 개선
  주장이 아니다** — 부착률·해제 건수는 시드·픽업·`select_viewer_lines_tagged`만의
  함수이고, 시스템 프롬프트 본문은 두 배치에서 바이트 동일이므로 프로브·사실활용·
  앵커의 차이는 전부 온도 0.45 재실행 노이즈에 귀속한다(투명성을 위해 비교표에는
  나란히 남겼다). 프록시 `/health` 누계를 턴 전후로 대조하는 행 단위 해제 관측성
  (`briefing_evidence_released`)을 신설해 "해제 없이도 정답이 나온" 사례(시드 11·22
  T47 `초코라고 했어!`)를 구분할 수 있게 됐다. 3런 결정론 축(수신자·호명·여론
  2종) 전부 만점, 존댓말 0/144, 이탈 0, 전송 실패 0.
  (`완료/AIRI-BRIEFING-EVIDENCE-NARROW-2026-08-20.md`, `a5abc2c`+`6889d1e`)

- **★ 히스토리 vs 브리핑 토큰 예산 — 원 판정 폐기(핵심 반전)** —
  `--history-turns {4,8,12}` × 시드 {11,22,33} 9런(memory-arm seeded,
  briefing/acts/contract on, `num_ctx 4096`, `midm-airi:2.0-mini`, CPU)을
  급종료 재개를 거쳐 완주했다(전 런 `transport_failures=0`). **확정되는 결과는
  둘뿐이다**: ①결정론 축(수신자·호명·여론·존댓말·이탈)은 history_turns 4/8/12
  전부 무영향(9런 만점), ②`--num-ctx 4096`은 history_turns=12까지 거절 0건으로
  수용. 반면 앵커(h4 29.9% / h8 20.8% / h12 13.2%)·다양성(61.8/45.8/26.4%)·
  fact_usage(3.4/4.8/0.0%)·프로브(2/9, 3/9, 0/9)는 **history_turns 축과 CPU
  스로틀 epoch가 완전히 교락**됐다(h4=전부 스로틀 전, h12=전부 스로틀 후, h8만
  양쪽에 걸침). h8의 내부 분할을 대조군으로 쓰면 **epoch를 고정할 때
  history_turns 효과가 사라지거나 역전**된다 → 리뷰를 거쳐 **"히스토리 4가
  앵커·다양성 최고"라는 원 권고를 폐기**했다. epoch와 무관한 신호는 5자 이하
  단답이 h4에서만 관측(6.9% vs 0.0/0.0%)된다는 것뿐이며 이는 h4에 불리하다.
  다양성 산출식은 `transcript`의 `stage=="turn"` `airi` 필드로 재현 가능함을
  확인해 문서 §3-가에 산출식·재현 커맨드를 신설했다(9런 재계산 일치). 남은
  과제는 **코덱스 GPU 단일조건 재실측**(스로틀·워치독 변경 없이 history_turns
  효과를 epoch 효과와 분리) — §5 대기열 등록.
  (`완료/AIRI-CTX-BUDGET-TRADEOFF-2026-08-20.md`, `b662e3f`+`34b9f51`)

- **★ 워치독 env 클램프 함정 (환경 사고)** — SSoT 문서가 안내하던
  `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS=90`이 프록시 코드의 유효 범위
  (`configured_upstream_first_raw_timeout`, 1~30초)를 벗어나 **경고 없이 기본값
  8초로 클램프**되는 것을 실측 중 발견했다. 이 때문에 좁힌 정의 첫 3런이 거의 전
  턴 8초 워치독 폴백으로 오염돼 폐기하고 `=30`(유효 범위 안 최댓값)으로 재기동해
  재실행했다. 같은 클램프가 토큰 예산 배치의 "90초 재기동" 5~9런에도 걸렸음이
  사후 판명 — 해당 런들의 침묵 폴백이 0~2/144라 실측 영향은 미미하나, epoch 해석
  시 이 사실을 병기해야 한다(CTX-BUDGET 문서 §0에 정정 절 추기).
  (`완료/AIRI-BRIEFING-EVIDENCE-NARROW-2026-08-20.md` §6,
  `완료/AIRI-CTX-BUDGET-TRADEOFF-2026-08-20.md` §0-가)

- **추출 SFT 검수·익스포트 경로 신설 (P3-T2 2차 학습 준비)** — 행동 SFT와 대칭인
  폼→적용기→익스포터 3종을 `ollama-proxy/training/`에 추가해 스팬 계약
  (`conversation-v3-span`) 학습쌍 102건을 사람 검수→학습 투입 가능 상태로 만들었다.
  검수 폼은 `진행예정/AIRI-EXTRACTION-REVIEW-FORM-2026-08-20.html`(102건·추출 항목
  144건 전량 렌더, 예외만 회신하는 클릭형). 행동 쪽 반말 게이트에 대응하는 **스키마
  게이트**를 적용기에 배치했다 — 검수자가 손으로 고친 target은 `parse_stage_a_span`을
  다시 통과해야 하며(근거 인용이 turns 원문에 실재 + 모든 이름이 그 인용 안에 존재,
  drop 0), 한 건이라도 실패하면 회신 **전체**를 거부한다. 익스포터는 학습 프롬프트를
  새로 쓰지 않고 벤치마크의 Stage A 조립을 import해 재사용하며(소스에 `<character>`·
  `<turns>` 리터럴 부재를 테스트로 강제), 이를 위해 `benchmark_memory_track.py`의
  인라인 user 블록을 `stage_a_user_input()`으로 최소 추출했다(반환 바이트 동일).
  실제 Stage A 호출을 가로채 익스포트 messages와 바이트 동일함을 테스트로 고정.
  CI `ollama-proxy-training` 샤드에 신규 테스트 3종 등록, training 스위트 95 passed
  (베이스라인 65). (`a473eb1`+`df31dc6`)

- **추출 검수 폼 v2 — 사전 검증 + 큐 결속** — 위 폼의 rewrite UX 한계(102건 검수 후
  마지막에 회신 전체가 반려되면 재작업 비용이 큼)를 브라우저 측에서 막았다.
  ①`validateRewriteTarget()` 순수 함수로 타이핑 중 실시간 검증(JSON 파싱 →
  `{"extracted":[…]}` 형태 → evidence가 turns의 부분 문자열 → 모든 이름이 evidence
  안), 위반 건은 회신의 `rewrite:` 목록이 아니라 `(미결정)`으로 보내 서버의
  fail-closed와 결과가 정합한다. 서버(`parse_stage_a_span`)가 최종 SSoT이고 JS는 그
  **보수적 부분집합**임을 주석에 못박았다. ②target JSON 파싱 실패를 "추출 항목 없음
  — 아무것도 뽑지 않는 것이 정답"과 절대 겹치지 않는 별도 오류 배지로 분리.
  ③**회신-큐 sha256(12자) 결속** — 폼이 `queue=<sha>`를 헤더에 임베드하고 적용기가
  대조한다. 리뷰 지적(fail-open)에 따라 `apply_reply()`의 `queue_sha`를 **필수
  인자화**해 우회 경로를 없앴다: **구 폼 회신은 거부되며, 오류 메시지가 최신 폼
  파일명을 안내**한다. 폼 JS 검증은 파이썬 재구현이 아니라 실제 배포되는 `<script>`
  원문을 Node로 실행해 테스트했다. training 스위트 95 → **114 passed**(무수정분 전부
  유지), 재생성 HTML 102건·큐 sha `2988a82bd738` 폼·적용기 독립 재계산 일치.
  (`eb9f46a`)

- **memory_runtime v2b→v3-span 수렴 (greybox)** — 런타임 Stage A 조립을 계약 선택식으로
  바꿨다. 기본 `conversation-v2b`는 프롬프트·user 메시지·JSON schema **세 요소의
  SHA-256이 변경 전과 완전히 동일**하고(HEAD 판 `memory_runtime`을 실제로 로드해
  `_extract_batch`를 구동한 end-to-end 대조 + `max_chars` 클리핑 분기 포함 골든 4케이스
  + 레포 내 영구 동결 테스트의 3중 증명), `AIRI_MEMORY_EXTRACTION_STAGE_A_CONTRACT=
  conversation-v3-span` opt-in 시에만 `stage_a_prompt_for_contract` +
  `stage_a_user_input` + `[turn N]` 라인 + `parse_stage_a_span`으로 벤치마크·학습
  조립과 바이트 동일하게 수렴한다. 공용 모듈 추출은 하지 않았다 — `memory_runtime`이
  이미 `benchmark_memory_track.parse_stage_a`를 import하고 있어 방향이 존재했고 같은
  import 문에 이름 3개를 늘리는 것으로 끝났다. span 경로에서 근거 미인용으로 드롭된
  항목 수는 `extract_end` 텔레메트리 `span_dropped`로 노출되며 기본 경로에는 이 키가
  붙지 않는다(불변을 테스트로 고정). `ollama-proxy` 전체 1461 passed.
  **활성화 선행 조건 4건**은 인계문에 등록했다(§아래). (`00482ec`)

- **alias 결정론화 + 고정 택소노미 (greybox)** — 기억 리서치 실행 로드맵 ⑤의
  "alias 매핑에서 LLM 제거"·"Memobase 고정 택소노미 차용"을 Stage A 파싱과 Stage B
  사이 **단일 seam**에 opt-in으로 배선했다(신설 모듈 `memory_taxonomy`). alias 해소는
  정규화(NFKC·zero-width/공백 제거·양끝 부호 strip·casefold·조회 전용 접미 strip)와
  등록 테이블만 쓰는 **LLM 0회** 규칙이며, 해소 결과는 항상 이미 알려진 표기로만
  수렴해 새 이름을 발명하지 않는다. 다만 **ambiguity 가드는 충돌하는 두 표기가 양쪽
  다 기지(旣知)일 때만 발동**하므로 미지 인물끼리 접미가 충돌하면 병합될 수 있다
  (`하린`/`하린이`) — 초판의 "오병합 구조적 불가능" 단정은 리뷰 실측으로 **철회**했고,
  텔레메트리를 위험 축(`alias_entity_renamed` = 엔티티 name 재작성)과 안전 축
  (`alias_reference_bound` = 참조 결속)으로 분리 계측했다. relation.subtype의 자유
  문자열은 9개 고정 슬롯 화이트리스트로 막되 **생존 항목을 재작성하지 않아** 기존 행
  마이그레이션이 필요 없다. 두 env(`AIRI_MEMORY_EXTRACTION_ALIAS_RESOLUTION`·
  `AIRI_MEMORY_EXTRACTION_TAXONOMY_GATE`) 모두 기본 OFF이며, OFF 경로는 HEAD 판
  `memory_runtime`과 요청 본문·텔레메트리·DB 전 행 해시가 동일함을 독립 실측했다
  (`a2d345b6…`). 추출 학습쌍 **102레코드(실질 96 / 항목 144건)가 고정 택소노미를
  전건 통과**했고 이 대조를 회귀 테스트로 고정해 학습·런타임 어휘 드리프트를 상시
  감시한다. 알려진 한계 2종(배치 내 오병합, 전량 드롭 시 워터마크 무성 전진)은 해결
  조건을 주석에 적은 회귀 테스트로 **상한을 고정**했다. memory 샤드 204 passed /
  memory-store 78 passed. (`9034428`)

- **P2-4 실체 판정 (조사 전용, 커밋 없음)** — "이관할 결정론 렌더러가 더 있다"는 전제
  자체가 실측과 어긋남을 확정했다. 사이드카 28케이스의 최종 실패 4건(2026-08-18 게이트)
  중 dn04·b18은 후원 이벤트류라 이미 렌더러 소관이고(시뮬 12런 5/5 — 단 addressee
  분모가 후원 5턴뿐이라 **구조적 보장값**임을 정직하게 기록), gr01·sp01은 답의 내용이
  자기 상태·상대 발언에 의존해 고정 문구로 생산 불가다. 대신 **결정론 렌더러 자체가
  만든 신규 결함**을 발견했다 — 후원 렌더러가 부른 호명 이름이 히스토리·브리핑
  "방금 흐름"으로 되먹여져 이후 모델 턴이 재호명한다(08-20 시뮬 15런 19턴, 그중
  16건이 직전 후원 렌더러 이름). B4a 계약의 "이름 발명 금지" 정면 위반이며, 원인이
  모델이 아니라 **우리가 이관한 결정론 발화**다. 부수 발견: 운영 후원은 액션 3종
  (`donation_name_callout_request`/`donation_read_request`/`donation_reaction_request`)
  인데 현행 렌더러는 1번만 덮으므로 dn04류 반사가 운영에서 재발할 자리는
  reaction 슬롯이다 → P2-1 귀속 권고. (근거: `.superpowers/sdd/task-9-report.md`,
  본 로그, STATUS §3 P2-4 재정의)

- **P2-4 결정론 발화 히스토리 격리 수리** — 위 결함을 러너의 되먹임 두 지점만 손대
  고쳤다(`run_broadcast_sim.py` `run_arm()`, +4/−2줄, `broadcast_sim.py`·오라클·
  프록시·픽스처 무수정). `deterministic_act == "thank_renderer"`인 턴만 히스토리·브리핑
  사본을 **이름 없는 A4.2 v1 승인 문구**(`고마워. 함께해줘서 힘이 돼.`)로 치환하고,
  채점(`score_turn`)과 사람 검토용 `transcript`는 실제 렌더러 출력을 그대로 유지한다 —
  기록·채점은 손대지 않고 "다음 턴에 누출되는 입력"만 끊었다. 같은 시드(11)·같은
  설정 전/후 직접 대조: **`invented_handle_turns` 2 → 0**(T30 `산책중, 떡볶이 좋아해!`
  → `응, 피자랑 떡볶이 좋아해.` / T39 `민트초코파, 삼각김밥 좋아해!` → `고마워!`),
  `addressee` 5/5·`donation_callout_correct` 5/5·`polite_violation` 0/48·`banmal`
  48/48·`transport_failures` 0 **전부 무훼손**, 렌더러 실발화(T28·T37)는 양쪽 바이트
  동일. 테스트 52건(기존 50 + 신규 2) 통과. 한계: CPU 로컬 1런 대조이며,
  `topic_anchored`·`viewer_fact_usage` 변동은 비결정 축 노이즈로 명시. (`4046d75`)

- **에코 필터 구멍 점검 — 이미 닫혀 있었다** — 08-19에 등록된 갭(absence 폴백 문구가
  11자 이상이라 8자 에코 필터를 길이로 통과할 수 있다는 우려)을 실측 재확인한 결과
  `DEGENERATE_ECHO_PREFIXES`가 absence 폴백 2문구·침묵 폴백 풀 6종 전부를 길이 무관하게
  차단 중이었다(매 턴 `blank_degenerate_echo`가 먼저 돌아 `""`로 비우므로 원본 길이와
  무관). 수리 없이 **회귀 테스트만 +97줄** 추가했고, 대조군 실험(프리픽스 1개를
  일시 제거 → 예상대로 RED → 원복 → GREEN)으로 새 테스트가 실제 원 갭에 민감함을
  증명했다. 계약 테스트는 프록시 소스를 AST로 읽어(무거운 import 회피) 문구를 뽑는
  기존 패턴을 재사용해 중복 하드코딩을 만들지 않았다. 함께 **B4c 재확인**:
  `broadcast_contract.py` `BROADCAST_CONTRACT_PARAMS` 9행이 08-18 승인 폼 원안과
  바이트 단위로 일치(코드 무변경). (`d96e71e`)

- **사전 존재 결함 3건 수리** — 이번 배치 착수 전부터 main에서 깨져 있던 것들이다.
  ①**soak-transport 계약 테스트**: 러너 상수(`NON_SUBSTANTIVE_RESPONSES`)는 이미 침묵
  폴백 풀 6문구와 동기돼 있었고 뒤처진 것은 **테스트 자신**이었다(옛 단일 문구만 AST로
  뽑아 비교) — 프록시 `GROUNDING_SILENCE_FALLBACK_POOL`을 SSoT로 확정해 풀 전체를
  대조하도록 재동기화(`4f1af2b`). ②**`chat_replay` 수집 오류 6건**: 패키지
  `__init__.py`가 동명 서브모듈 `chat_replay.py`를 가려 소비자 6파일의 import가 전부
  실패하던 것을 재수출 7종 보강으로 해소(파일 이동·리네임 없음). 파생으로 Windows
  `core.autocrlf`가 sha256 고정 픽스처를 CRLF로 훼손하던 잠복 결함(`git diff`는
  정규화 때문에 무변화로 보여 안 잡힘)을 발견해 `.gitattributes`에 `text eol=lf`
  규칙을 추가했다(`de4018c`). chat_replay 73 passed, `ollama-proxy-evaluations` 샤드
  495 passed. ③**`rescore_report()` NameError**: 정의 시점 자유변수 `args`(`main()`의
  지역변수)를 참조해 **CLI `--rescore`가 지금까지 한 번도 성공한 적이 없었다** —
  `fixture_path` 파라미터화로 수정하고 회귀 테스트로 고정(`a5abc2c`).

- **MEM-04 SQLite 락 경합 실측 (측정 전용, 커밋 없음)** — `airi_memory.py`(로드맵 G2
  원문의 `memory_store.py`가 리네임된 파일)의 실제 PRAGMA(WAL·`busy_timeout=5000`·
  `BEGIN IMMEDIATE`·커넥션 풀 없음)와 `append_turn`/`latest_turn` 경로를 레포 밖 임시
  DB에 그대로 재현해 부하를 걸었다. 프로파일 A(방송 운영 근사, writer 2·reader 6, 각
  2000 ops): busy/locked 실패 **0건**, writer p50 36.9 ms·max 328.8 ms. 프로파일 B
  (코드 주석·회귀 테스트가 지목한 최악 케이스 — 8 writer 동일 세션, 각 250 ops):
  실패 **0건**, p99 780.6 ms·**max 2,099 ms = 예산의 42%**. **판정: 5000 ms 현행 유지가
  적정.** 500 ms로 되돌리면 B의 p99조차 초과하므로 2026-08-12 CI 저하 러너 락 실패
  이력과 정합한다. CPU 70% 스로틀 상태에서 측정했으나 SQLite 락 경합은 I/O·트랜잭션
  구조가 지배적이라 대표성이 있다(오히려 보수적 방향).
  (근거: `.superpowers/sdd/task-12-report.md`, 본 로그)

- **GLiNER 계열 한국어 실측 (LLM 0회 엔티티 프리필터 후보)** — 리서치 문서의 잔여
  미확인 사항을 해소했다. **용어 정정**: `gliner2`(Fastino)는 HuggingFace 모델 카드가
  **영어 단일 언어**라 한국어 후보에서 배제했고, 원조 GLiNER 계열의 한국어 파인튜닝
  `taeminlee/gliner_ko`를 채택했다 — 두 계열을 문서에서 혼용하지 말 것. 추출 학습쌍
  102건(96레코드/144 gold 항목) 전수 측정: 전체 겹침률 **72.9%(105/144)**,
  `{{user}}` 제외 **87.5%(105/120)**, entity:person 실명 **100%(36/36)**,
  organization 75.0%, **item 0%(0/12) — 취약점**, skip_chatter **과추출 0/6**,
  지연 평균 0.146 s. **판정: 조건부 채택** — person/organization 한정 LLM 호출 전
  후보 프리필터로 유효하되 item은 제외, `{{user}}`는 규칙 기반 별도 처리, 조사 잔차
  흡수 후처리 필수, CC-BY-NC-4.0 라이선스는 상용 배포 시 재검토 필요.
  (`참조/AIRI-GLINER-KO-EVAL-2026-08-20.md`, `bf0d1f9`)

- **코덱스 PC Serena MCP 도입 지시서 발행** — Codex CLI에 Serena MCP(시맨틱 코드
  검색·편집)를 붙여 파일 통짜 read·grep 반복 체인을 심볼 단위 조회로 대체하는 작업
  명령을 코덱스 PC 앞으로 발행했다(설치·등록·인덱싱·AGENTS.md 정책·A/B 실측 의무·
  롤백 경계). 역효과 구간(1줄 수정·설정/자유 텍스트 검색·쉘 작업)도 함께 명시.
  변경 허용 범위는 코덱스 PC 환경 4가지뿐이며 AIRI 레포 코드·운영 설정은 무접촉.
  (`진행중/AIRI-CODEX-SERENA-TOKEN-ORDER-2026-08-20.md`, `0924ea1`)

- **인계 정리** — 08-19 인계문을 대체하는 현행 단일 SSoT
  `진행중/AIRI-CODEX-HANDOFF-2026-08-20.md`를 신설했다(08-19판은 아카이브 예정).
  당시 최우선 불변: 검수 회신(행동 181 + 추출 102) → T2-b QLoRA(행동 → 추출 2차) →
  T3 양방송 게이트. **이 순서는 2026-08-21 사용자 내용 검수로 폐기됐으며 최신 상단
  배치와 STATUS P2-6이 대체한다.** 최종 whole-branch 리뷰 결과 **통합 결함 0건**이었고, 결함이
  아닌 추적 항목 6건(격리 후 v1 문구 모방 미측정 · 익스포터 split 도메인·id 중복
  검사 보강[첫 export 전 필수] · CI `python-core-tests`의 `setup-node` 미선언 ·
  `_REWRITE_RE` 진단 메시지 · 행 필드 `briefing_evidence`="부착 결정" 의미 재정의
  금지 · training 샤드 timeout 예산 관찰)은 인계문 §4-5에 착수 시점과 함께 등록했다.

- **마감 소형 수리 2건** (이 배치 말미, 별도 커밋으로 랜딩): ①워치독 env
  무효값 경고 — 범위 밖 값이 조용히 8초로 클램프되던 것을 기동 시 경고로 드러낸다
  (§워치독 클램프 함정의 재발 방지) ②비루프백 앱 경로 테스트 — 브리핑 근거 헤더가
  루프백이 아닌 피어에서 무시되는지를 앱 경로로 고정.

- **2026-08-19** (클로드 PC, 추가분 A·B·C): ①T2-b 트레이너 작성
  (`0b2e966` — sha 핀·로컬 전용·assistant 마스킹, tiny 모델 CPU 스모크로
  loss 하강·어댑터 저장까지 검증 — 코덱스는 CUDA 경로만 확인하면 됨)
  ②held-out 2차 방송 픽스처(게임 주제·신규 95명·프로브 사실 3중 분리,
  분리성 회귀 테스트 강제) + **기준선 실측: 결정론 축 만점 5연속·프로브
  2/3(역대 최고)·사실 활용 15%** ③추출 판단 학습쌍 102건(주체 선택·
  {{user}}·과추출 억제 장면, 전 타깃 스팬 파서 무손실 통과·게이트 어휘
  분리). 함정 2건 기록: str.format의 {{user}} 삼킴, Path()의 URL 스킴
  평탄화. (`완료/AIRI-HELDOUT-AND-EXTRACTION-SFT-2026-08-19.md`)

- **2026-08-19** (클로드 PC, goal "이 PC 한도까지" 마감 배치): ①학습
  파이프라인 데이터 측 완결(`903e39d` — 검수 회신 적용기[미결정
  있으면 fail-closed·수정 답변 register 게이트·eligibility 단일
  전환점] + chat 포맷 익스포터[운영 프롬프트·브리핑·[YouTube] 프리픽스
  그대로 조립]) ②코덱스 통합 인계문 신설(트레이너 EXAONE 핀 발견
  포함) ③Stage A 스팬 계약(`a56d0a4`) 구현·A/B — **날조 차단 실증
  (양 모델 3건 코드 탈락), 판단 축 미돌파**(Mi:dm recall 0.21→0.33이나
  unexpected 4→10, qwen3:4b는 잡음 범위) → 추출 판단도 학습 후보,
  코덱스 8B+span 실측 권고 ④4-시드 분산 캘리브레이션 — **결정론 축
  4/4 방송 만점(강건성 확정)**, 사실 활용 노이즈 천장 12% = T3 게이트
  판정 기준 확립, 앵커는 ±13pp라 다중 시드 필수 ⑤리서치 ④(축적 계층)는
  의도적 보류 — 먹이는 기능(affect continuity)이 운영 OFF라 G1a 재개와
  짝지어야 함. (`완료/AIRI-SPAN-CONTRACT-AND-VARIANCE-2026-08-19.md`)

- **2026-08-19** (클로드 PC, P3 학습 트랙 재정의 + T1 데이터 합성):
  사용자 방향 확정("모델을 학습시키는 방향") — P3 주 경로를 학습
  트랙(T1 합성→T2 인간 검수+QLoRA→T3 시뮬 게이트→T4 하드코딩 축소)
  으로 재정의, 체급 A/B는 보조 경로로 강등. T1 구현: 실측 실패 4행동
  (fact_recall 126·addressee 15·register 10·substance 30 = **181건**)
  을 결정론 열거로 합성 — 운영 브리핑 포맷 그대로 학습, 조사 엔진
  (직전 글자 받침 기준 — "별명는" 버그 수리·회귀 고정), 전 정답
  방송 채점기 통과 강제. 기존 governance 준수(pending·eligible:false
  — **인간 검수 전 학습 불가**). 트레이닝 스위트 45 passed·CI 등록.
  다음 차단 지점: T2-a 검수 UX(사용자)·T2-b 트레이너 behavior 포맷
  확장(코덱스). (`완료/AIRI-P3T1-BEHAVIOR-SFT-SYNTHESIS-2026-08-19.md`)

- **2026-08-19** (클로드 PC, P1 지렛대 소진 → **P3 게이트 열림**):
  마지막 지렛대 2개 실측(`40298e2`) — 에코 차단은 유효(앵커 17→35%·
  다양성 52→71%, 반복 전염 절단), **지시형 브리핑은 무효**(사실 활용
  7% 동결 — "그대로 써서 답해"+원문 인용에도 T21 "아직 기억 안 나",
  T47은 고양이 이름에 "이름은 AIRI야" 날조 회귀). 명시 지시 불응
  3회째·독립 증거 4계열로 **P3 게이트 조건 충족 판정** — 실행은
  코덱스 GPU(P3-1 4B 공존, P3-2 하네스 그대로 지연-품질 A/B).
  결정론 축은 만점 유지(모델 교체와 독립적 자산). 부수 발견:
  absence 폴백이 모델 선점+히스토리만 검사 — B4a 운영 이식 시
  디렉터→프록시 "브리핑 근거 있음" 신호 계약 필요(코덱스 통합 과제).
  (`완료/AIRI-P1-LEVER-EXHAUSTION-P3-GATE-2026-08-19.md`)

- **2026-08-19** (클로드 PC, P1-2/P1-3/P2-3 — goal "다음 수순 전부"):
  실패 프로브 원문 진단에서 나온 수리 3건 구현·재실측(`363c6a7`).
  ①관련도 우선 시청자 줄(접두 매칭 — 조사·굴절 대응, T21 재료 유실
  수리) ②저품질 응답 에코 필터(T35 반복 전염 차단) ③"시청자 사실
  활용" 지표 신설 ④기억 가드 프록시 방출 경계 배선(조사 중 발견:
  프록시에 이미 absence 폴백 존재 — 가드는 "증거 있는데 무내용 단정"
  잔여 구멍 전용). 재실측(sim4): 결정론 축 만점 유지·폴백 3→0·단답
  3→2, **신설 지표 기준선 = 사실 활용 7%(2/29)** — "재료를 줘도 안
  쓴다"가 수치화돼 P3 게이트 1차 증거 확보(P1 잔여 지렛대: 지시형
  브리핑 문구·고정 문구 에코 차단 — 소진 후 게이트 판단). 테스트
  344 passed. B4a 운영 이식은 B1b 라이브 피드 전 보류가 정직하다고
  판단. (`완료/AIRI-P1P2-V2-RELEVANCE-GUARD-2026-08-19.md`)

- **2026-08-19** (클로드 PC, P1/P2 첫 구현·실측): 사용자가 결정 큐
  전체를 권고안으로 일괄 승인(DeepL은 추적 종결). ①P1-4 ACK marker
  모드 구현(`3ead135` — env 3모드, 런처 기본 marker + 폴백 풀·계약 v3
  운영 ON) ②P1-1 턴 브리핑 조립기 + P2 결정론 발화 3종(thank 렌더러
  적용·집계 오프너 3종·기억 가드 모듈, `f17449a`) ③3-run 실측:
  **결정론 계층 만점 — 수신자 5/5·호명 5/5·집계 6/6(전부 0에서),
  생일 반사 첫 소멸**. control(marker만) 런이 p50 3자로 붕괴한 것이
  역설적 핵심 발견 — 모델 단독 발화는 분산이 크고, 브리핑+결정론
  계층이 그 바닥을 받친다(full은 p50 10·단답 3/48 회복). 미달 3축:
  프로브 1/3(P1-2로), 앵커 21%(지표 재정의 필요), 다양성 52%(P3
  게이트 입력). (`완료/AIRI-P1P2-BRIEFING-DETERMINISTIC-ACTS-2026-08-19.md`)

- **2026-08-19** (클로드 PC, 로드맵 v3 개편 + 레거시 정리): 사용자 진단
  "로드맵은 진행되는데 좋아지지 않는다(공회전)"에 따라 전면 개편.
  원인 확정 — 빼기 지표(위반률) 전부 0 도달 후에도 같은 루프 반복,
  병목은 하드웨어·모델이 아니라 **모델을 굶기는 구조**(seeded arm 실측이
  근거). v3 골자: 주 지표를 발화 실질(더하기)로 교체, 돌파 3축 신설
  (P1 쇼 러너 브리핑 / P2 결정론 발화 계층 / P3 조건부 생성 상한 —
  P3는 P1·P2 소진 후 게이트), 기존 G/C/지연/M 트랙은 매핑·강등·유지로
  재편(미완 항목 전수 이관). 문서 정리: 이동 22건 전부 `git mv`(삭제 0)
  — 소화된 인계문 7·소진 계획 3·결정 완료 시트 등 9건을 완료/로,
  루트 구본 3건 포함 13건을 아카이브/로. 로드맵 v2 원문은
  `아카이브/AIRI-ROADMAP-STATUS-v2-SNAPSHOT-2026-08-19.md` 동결,
  갱신 로그(1,091줄)는 이 파일로 분리. 부속 로드맵 3종에 v3 우선 배너,
  NEXT-SESSION.md 진입점 재작성, 인덱스 현행화. **차기 예약**: P1-4
  C안 ACK 제거(사용자 확정, 기본값 marker/off만 착수 시 확인) →
  P1 쇼 러너 브리핑.

- **2026-08-18** (클로드 PC, 100인 방송 시뮬레이션): 사용자 지시대로
  "첫 방송" 한 편을 통째로 시뮬레이션했다 — 고정 주제 4비트, 시청자
  100명, 채팅 144건 생성 → 5초 창 픽업 48턴(나머지는 대기, 중앙값
  10건). 기억 3-arm 실측 결과 **ON이 22턴 전(히스토리 창 밖) 사실을
  회상**했다(OFF `"내가 이름을 뭐라고 했더라?"` → ON `"초코야!"`).
  사전시드 arm이 가장 실질적(5자 이하 응답 10→3건, 주제 앵커
  27%→50%). 재현된 결함: **생일 후원 반사가 3 arm + named 변형까지
  4/4**, 여론 집계 발화 0/6, 후원 호명 0/5. **닉네임을 프롬프트에
  넣어줘도 호명 0/5**라 입력 형식으로 푸는 가설은 기각 — 결정론
  렌더러가 답이다. 존댓말 위반 0/144턴·이탈 0으로 앞선 4겹 방어는
  군중 압력에서도 유지. 신규 러너·테스트 24건·CI 등록.
  (`완료/AIRI-BROADCAST-SIM-3ARM-2026-08-18.md`,
  원문 `진행중/AIRI-BROADCAST-SIM-REVIEW-2026-08-18.md`)

- **2026-08-18** (클로드 PC, 임베딩 A/B): 리서치 실행 로드맵 ③ 이행.
  기존 픽스처(4문서/3질의)로는 강한 한국어 임베더를 못 가르므로 신규
  평가셋(48문서/24질의, lexical·paraphrase·disambiguation·supersede
  각 6문항)을 만들어 KURE-v1 vs BGE-M3를 쟀다. **24개 중 1개만 갈려
  구분 불가 — 교체 없음, KURE-v1 유지**(MRR 0.921 vs 0.942, 불일치쌍
  1:0). MemDelta식 역전은 재현되지 않았다. 두 모델 공통 실패가 더
  중요한 신호였다 — 암묵적 부정("얼굴 나와?"↔"카메라 안 쓴다") 질의는
  둘 다 9위로 밀었다. 신규 러너·테스트 11건·CI 등록 완료.
  (`완료/AIRI-EMBEDDING-AB-KURE-BGEM3-2026-08-18.md`)

- **2026-08-18** (클로드 PC, Qwen3-8B 추출 게이트): 리서치 실행 로드맵 ②
  이행. **full balanced FAIL** — 다만 2~4B 후보 9종이 전부 실패했던
  `persistent_trait` 스모크는 만점 통과했다. 같은 하네스로 2.4B/4B/8B
  3점 계열을 돌린 결과 **크기는 unexpected를 9→2로 줄이고 구조적 실패
  코드를 0으로 만들지만 critical recall은 0.43~0.50에서 정체**한다.
  실패 2건 원문 진단 결과 원인은 능력이 아니라 계약 미전달(상태 변화
  주체 선택, `{{user}}` 플레이스홀더 등록)이었다. **다음 수순은 모델
  확대가 아니라 Stage A 재설계(생성→스팬 선택+코드 검증)**로 정정한다.
  extraction 계속 OFF, 격리 11436 실행 후 중지(active runner 0).
  (`완료/AIRI-QWEN3-8B-EXTRACTION-GATE-2026-08-18.md`)

- **2026-08-18** (클로드 PC, journal recall bm25): 리서치 실행 로드맵 ①
  이행. FTS5 접두 질의로 뽑은 후보를 완전일치 교집합 재점수가 도로
  버리던 결함을 재현(`포지 기억나?` → 회상 0건)하고 `bm25()` 랭크를
  도입해 닫았다. 완전일치 턴은 정수 점수를 유지해 **기존 순위·최근성
  계약 불변**이고, 접두 전용 턴만 (0,1) 점수로 하위에 복구된다.
  지연 p50 5.457→6.859ms(게이트 150ms 대비 5%), 테스트 77→78,
  연관 스위트 100 passed. (`완료/AIRI-JOURNAL-RECALL-BM25-2026-08-18.md`)

- **2026-08-18** (클로드 PC, A4.2 thank 호명 렌더러): 사용자 확정 B안
  `{닉네임}, 고마워! {한마디}`(한마디 3종)를 A4.2 결정론 렌더러에
  구현했다. 기본 경로는 **v1 문구 바이트 동일**로 두고 선택 파라미터
  `callout_context`가 올 때만 호명이 켜지는 default-inert 설계다.
  이름은 발명하지 않고 호출자 검증값만 재검증하며(디렉터 `BAD_TEXT`
  계약 + ≤32자·구두점/공백 제약), 구분자 역분해로 **호명 정확히 1회**를
  증명한다. v1 오라클은 무수정이고 호명 정책은 사이드카
  `must_act_thank_callout_v1.json`으로 분리했다(합성 코퍼스에 검증된
  표시 이름이 없어 3턴 전부 `callout_available:false`). 테스트 8→14,
  디렉터리 121 passed, 런타임 펜스 통과(운영 미배선 유지).
  (`완료/AIRI-A42-THANK-CALLOUT-RENDERER-2026-08-18.md`)

- **2026-08-18** (클로드 PC, 장기기억 기술 리서치): 학술 서베이·OSS
  20여종 실사·자체 레포 3종 재감사 3트랙을 종합했다. 결론은 3트랙
  일치 — **프레임워크 교체 없음, 현행 스택 유지 + 선별 차용**.
  병목은 기법 부족이 아니라 **로컬 2~4B 모델의 구조화 추출 역량
  한계**임을 학술(Anatomy of Agentic Memory 실측)·OSS(Graphiti
  #868·Cognee 실패모델 목록)·자체 게이트 이력(9종 전부 2~4B·전부
  FAIL) 3중 교차 확증했다. 실행 로드맵: ①journal BM25 ②Qwen3-8B
  게이트 ③임베딩 A/B ④LLM 0회 축적 계층 ⑤GLiNER2 등 보완.
  (`참조/AIRI-MEMORY-TECH-RESEARCH-2026-08-18.md`)

- **2026-08-18** (클로드 PC, 주체높임 가드 수리): 직전 배치가 후속 등록한
  "범용 어미 규칙 주체높임 가드 부재"를 닫았다. 저장 결과 JSON 39종
  (응답 1,384·문장 2,630·고유 1,572)을 현행 파이프라인(치환→검출)에
  재적용해 시-높임 문장을 3분류한 결과 **누수(반말 어미로만 바뀐 채
  발화) 22건**이 실재했다 — `말씀이셨군요`→`말이셨군`, `계셨어요`→`계셨어`,
  `하시는군요`→`하시는군` 등. 원인은 `([가-힣]+)어요/네요/군요/죠/습니까`·
  `거든요`·`더라고요`가 무가드였던 점과, 기존 6패턴 가드가 1글자
  lookbehind라 `겠`/`는`/`던` 개재형(`그러시던데요`)을 못 막은 점 2가지다.
  신설 `_HONORIFIC_PREFINAL_GUARD`(시/셨 + 개재 1음절, `마시`/`모시`/`부시`
  어간 carve-out)를 7개 범용 규칙에 걸고 `_HONORIFIC_STEM_GUARD`에 개재
  lookbehind 1줄을 추가했다. 동일 문장 페어드 재적용 확정 증거:
  **누수 22→0 / 신규 발화 0 / 기존 변환 회귀 0(텍스트 변경 0건) /
  드롭 86→108(+22, 전부 누수분) / B3-d 120 무변경**. 오차단 우려였던
  `마셨어요`→`마셨어`·`사실이에요`→`사실이야`는 그대로 변환된다.
  test +6(신규 클래스 `SubjectHonorificPrefinalGuardTests`, 저장 JSON
  재계산 불변식 포함), 로컬 338 passed·725 subtests, checkpoint PASS.

- **2026-08-18** (클로드 PC, 말씀 규칙 수리·B4c 파라미터 폼): 기존
  `말씀`→`말` 규칙의 `말씀드렸어요`→`말드렸어` 파손을 겸양 어간 6매핑
  (`말씀드리-`→`말하-` 활용 전수)의 정확 변환으로 수리 — 페어드 1,835문장
  검증에서 파손 4→0·회귀 0·B3-d 무변경, 332 tests·checkpoint PASS.
  제외(fail-closed)로는 뒤 범용 어미 규칙이 `말씀드렸어`를 만들며 발화돼
  성립하지 않음을 확인했다. 신규 후속 등록: 범용 어미 규칙에 주체높임
  가드 부재(`말씀이셨군요`→`말이셨군` 발화 — 기존 갭, `_HONORIFIC_STEM_GUARD`
  는 6패턴에만 적용 중). B4c 파라미터 확정용 HTML 폼도 생성했다
  (관찰 연구 §6 9행 — 코드 상수 일치 확인, 사용자 회신 대기,
  `진행예정/AIRI-B4C-PARAM-DECISION-FORM-2026-08-18.html`).

- **2026-08-18** (클로드 PC, 치환표 보강): 분석 문서 중기 조치 ②(치환표
  보강)를 이행했다. 저장 JSON 16종 1,712문장에서 드롭 444문장의 어미
  빈도표로 27패턴을 채택하고(제외 6군은 오변환 위험 우선), B3-d
  120문장·기존 통과 1,268문장 오변환 0을 확인했다. 물결(`~〜`) 종결
  누수 27건도 수리했다. 동일 문장 페어드 재적용 확정 증거는 드롭
  444→135(−69.6%)·운영 모델 326→66(79.8%)이며, 게이트 라이브
  재실측(비페어드 참고)은 리허설 침묵 폴백 25.0%→2.1%·존댓말 위반
  단발 2→0·전 arm 0이다. 로컬 329 passed·CI 430 passed·checkpoint
  PASS(로컬 대체). (`완료/AIRI-REGISTER-SUBSTITUTION-AUGMENTATION-2026-08-18.md`)

- **2026-08-18** (클로드 PC, 침묵 폴백 조치): 분석 문서 5+1 조치안 중
  사용자 goal 승인분 ②b(결정론 폴백 register 정규화 수리)와 ⑤(침묵
  폴백 문구 다양화 greybox, `AIRI_SILENCE_FALLBACK_POOL` default-deny)를
  이행했다. 인용 밖 존댓말 에코 5건 중 3건은 반말화, 치환표 미커버
  2건(`ms04`)은 fail-closed 폴스루로 침묵 폴백 소폭(+1.2%p) 증가와
  맞바꿨다. 풀 ON 게이트 단발 38콜 재실측에서 침묵 폴백 19건이 6문구
  4/3/3/3/3/3으로 분산됐고 존댓말 위반은 0건(수리 전 2~3건)이다.
  test_ollama_proxy.py +11(신규 클래스 2종), 로컬 323 passed 재확인,
  CI ollama-proxy-api 샤드 424 passed·checkpoint PASS(같은 세션 기록,
  CI 자체는 billing 차단). **풀 문구 6종은 같은 날 사용자 원안 승인**
  — soak 러너 `NON_SUBSTANTIVE_RESPONSES`도 동기화했다. env 게이트는
  계속 기본 OFF이며 런처 ON은 별도 운영 채택 결정이다.
  (`완료/AIRI-SILENCE-FALLBACK-REMEDIATION-2026-08-18.md`)

- **2026-08-17** (G1a A4.6 승인 표현 정책 / prepublication evaluator foundation):
  사용자가 구체 원인의 짧은 감정, 같은 턴 회복, 차분하고 분명한 skeptical
  자기수정, 불확실할 때 한 번의 질문, fixed fallback의 공개 전 최후 사용이라는
  권장안을 승인했다. 이를 A4.3 exact 8-row에만 결합한 synthetic-only policy와
  lexical/structural checker로 고정했다. injected fake transport에서 constrained
  retry는 최대 2 upstream attempts, fixed fallback은 initial 1회 뒤 추가 model call
  없이 한 번만 허용한다. safety/tool-truth/public-token attestation 실패는 terminal이고,
  attestation은 실제 경계 증거가 아니다. 기본 CLI는 network/proxy/model 0회이며 live
  execute와 production proxy/director/B4b/TTS 배선은 없다. evaluator family를 runtime
  fence와 CI shard에 추가했다. lexical 성공은 비공개 구조 검토 eligibility일 뿐 자동
  발화·공개 판정이 아니다. 독립 재검토는 남은 HIGH/MEDIUM 없이 GO였으며,
  fresh model/human review 전 품질·운영 gate는 계속
  **FAIL/OFF**다.
  (`완료/AIRI-G1A-CORRECTION-PREPUBLICATION-FOUNDATION-2026-08-17.md`)

- **2026-08-17** (B4c 멀티턴 방송 리허설 로컬 체크포인트): 기존
  `autumn_leaves`/`game_and_career` 합성 fixture를 semantic SHA
  `aeb2bc...96c8`과 exact 2×24턴으로 고정하고, 전체 48턴 주입 transport의
  콜백 창 안/밖·여론 집계·후원 현재 이름 호명/과거 이름 비누출·주제 전환·
  politeness drift·계약 OFF 프롬프트 바이트를 37-test 필수 로컬 회귀로
  편입했다. content-free evidence v1은 dry-midm/128/history 8/full fixture,
  48/48 성공, prompt hash 재계산, finite rate와 시나리오→overall 산술을
  fail-closed로 검증한다. 독립 검토가 발견한 빈 summary·음수 count·NaN·위조
  hash/model false pass를 닫은 뒤 최종 GO였고 current checkpoint도 PASS다.
  이는 네트워크·모델·11435 proxy·B1b/B4b·public wire·TTS를 실행하지 않은
  합성 텍스트 흐름 회귀일 뿐이다. 운영 계약은 기본 OFF이고 ON 채택은 사용자
  확인 전 자동 승격하지 않는다.
  (`완료/AIRI-B4C-BROADCAST-REHEARSAL-CHECKPOINT-2026-08-17.md`)

- **2026-08-17** (B3-d Korean-first input-safety corpus regression): 현재
  default-OFF 규칙 기반 input prefilter를 120개 독립 합성 문장으로 고정했다.
  70 policy-bound + 30 adversarial-transform 계약은 정책 SHA
  `6d0678...06a8a`에 대해 verdict/category/rule 100/100 exact이고, 20
  semantic-gap은 expected verdict 없이 human-review-only로 격리했다. corpus는
  한국어 80건과 혼합/영·불·서·일·중 문장을 포함하며 전화·이메일·검증용
  카드·가상 주민번호·비밀값 pattern 경로를 회귀한다. offline 16-test suite를
  CI와 local checkpoint에 넣었고 생산 policy/proxy/flag는 변경하지 않았다.
  이 PASS는 규칙 계약만 뜻한다. 기존 direct marker 5/20, 의미 안전성,
  installed Electron/UI/TTS red-team은 미완료이므로 B3-d 전체는 계속
  **FAIL/OFF**다.
  (`완료/AIRI-B3D-KOREAN-INPUT-SAFETY-CORPUS-2026-08-17.md`)

- **2026-08-17** (G1a evaluator-only runtime import fence): A4.2~A4.5의
  must-act/guarded-delta, correction-target A/B, correction-realization postcondition과 고정 oracle가
  proxy/director/chat ingress/launcher/first-party service/runtime patch에 literal import·reference되면
  오프라인 checkpoint가 실패하는 재귀 정적 fence를 추가했다. 새 first-party component도 기본
  탐색하며 test/docs/eval/private/generated/
  third-party 경로는 scan하지 않고 intentional `broadcast_correction_target` synthetic seam은
  허용한다. temp fixture가 direct/helper/relative/qualified import, launcher, patch, 대소문자 변형을
  검출하고 최소 test count로 zero-test green도 막는다. 이는 정적 literal fence이지 obfuscated dynamic
  load 방지나 운영 안전 증명이 아니며, wording·fallback·retry·flag·runtime을 채택하지 않는다.
  독립 재검토는 HIGH/MEDIUM 잔여 없이 GO였고, A4.5 품질/운영 gate는 계속 **FAIL/OFF**다.
  (`완료/AIRI-G1A-EVALUATOR-RUNTIME-FENCE-2026-08-17.md`)

- **2026-08-17** (G1a A3 broadcast outcome candidate mapper foundation): 미래 B4b가
  실제 전달 완료 뒤 내놓을 content-free outcome candidate를 A1 `airi.affect-event.v1`로 바꾸는
  순수 mapper를 추가했다. `accepted/queued/selected/scheduled/ACK/partial/error/control/failed`는
  모두 거부하고 donation/callback/game/silence/repair의 exact 7개 evidence-outcome pair만
  허용한다. 이름·채팅·후원액·provider/event/viewer ID·lease token은 입력 schema에 없고
  extra field로도 거부한다. B4a action shape·selection, proxy runtime, endpoint, env/launcher,
  B4b/TTS에는 배선하지 않았다. 현재 `delivered`는 인증된 사실이 아닌 candidate field이며,
  A4 synthetic oracle에서 고정한 provisional appraisal만
  재사용했다. 따라서 A3는 **foundation만 부분 완료**, exactly-once B4b observer와 실제
  delivery evidence·A0 사용자 확정·운영 ON은 계속 대기다.
  (`완료/AIRI-G1A-AFFECT-EVENT-MAPPER-FOUNDATION-2026-08-17.md`)

- **2026-08-17** (G1a A4.5 correction-realization postcondition): A4.4 protocol v2의
  exact 8-pair response를 새 model/proxy 호출 없이 닫힌 target별 lexical postcondition으로
  재검사했다. target 3/8, control 2/8, target-only 2/control-only 1/both 1/neither 4로
  target prompt만의 개선은 작고 불안정했다. evaluator-only 고정 제안문 8개는 8/8
  self-conformance였지만 이는 사람 선호·자연스러움·사실 grounding 증거가 아니다. source
  packet pin 우회, 부정·조건·양보문 false pass, 한글/혼합 경쟁 숫자, receipt code binding을
  독립 검토에서 찾아 닫았다. 최종 판정은 target cue와 단정형 종결이 같은 문장에 있어야 하는
  closed target-linked grammar를 사용하며 actual zero-call run
  `a45-retrospective-20260817-06`으로 재산출했다.
  production/runtime/director/B4b/TTS 배선은 없고 사용자 wording 판단 전 품질/운영 gate는
  **FAIL/OFF**다. (`완료/AIRI-G1A-CORRECTION-REALIZATION-POSTCONDITION-2026-08-17.md`)

- **2026-08-17** (G1a A4.4 correction-target fresh A/B result): protocol v2로 pinned
  synthetic correction 8쌍·16 POST를 새로 실행하고, 두 separate model-review session의
  판정을 exact packet hash에 잠근 뒤 unblind했다. pair 합의는 target 3, control 2, tie 2,
  split 1이며 pooled 선호는 target 7/control 5/tie 4였다. target은 오답 유지·새 오답을
  3행에서 고쳤지만 2행에서는 핵심 교정 명사를 일반 설명으로 희석했고, 1행은 양쪽 silence
  fallback, 1행은 실질 차이가 없었다. 이는 사람 승인·실제 방송·통계적 우위가 아니므로
  품질/운영 gate는 **FAIL/OFF**다. 다음은 synthetic-only target-specific realization/
  postcondition 비교이며 자동 승격하지 않는다.
  (`완료/AIRI-G1A-CORRECTION-TARGET-AB-RESULTS-2026-08-17.md`)

- **2026-08-17** (G1a A4.4 contextual review protocol v2): 첫 fresh 16-call 실행은
  응답 생성에는 성공했지만 v1 blinded packet에 prior AIRI·selected viewer·screen·topic이
  없어 correction grounding을 판정할 수 없었다. 해당 v1 packet/overlay/receipt/key는
  `obsolete_incomplete_review_context`로 명시하고 열람·unblind·품질 증거에서 제외했다.
  v2는 pinned synthetic context를 exact 검증해 packet에 넣고, target 의미가 아니라 A/B arm
  mapping만 blinded라고 범위를 좁혔다. exact v2 packet hash에 결합된 complete overlay 전에는
  key를 열 수 없으며, 18/18 offline tests와 독립 재검토 후 새 run name으로 다시 측정한다.
  운영 gate는 계속 **FAIL/OFF**이고 자동 승격하지 않는다.
  (`완료/AIRI-G1A-CORRECTION-TARGET-AB-FOUNDATION-2026-08-17.md`)

- **2026-08-17** (G1a A4.4 correction-target fresh A/B foundation): A4.3의 exact
  8개 synthetic target/direction을 실제 Mi:dm 새 응답으로 비교하기 위한 control/target
  8쌍·16-call 러너를 추가했다. target arm은 기존 affect+`reply_act=correct` control과
  byte-identical이고 closed target 메시지 하나만 다르다. proxy는 exact loopback
  `local-evaluation` + valid context/affect/correct-act/target에서만 고정 한국어 target을 보존하며,
  name/key/Unicode variant와 duplicate는 raw card projection까지 fail-closed한다. blinded packet,
  별도 operator key, exact packet-bound locked overlay, content-free report와 Windows honest-local
  custody를 고정했다. 독립 공격 검토는 proxy와 runner 모두 범위 내 **GO**다. 현재 11435/Ollama가
  내려가 있어 fresh 16-call 실측은 아직 없으며 품질·운영 gate는 계속 **FAIL/OFF**다.
  (`완료/AIRI-G1A-CORRECTION-TARGET-AB-FOUNDATION-2026-08-17.md`)

- **2026-08-17** (G1a A4.3 correction wording user-review sheet): exact 8개 synthetic
  correction case마다 prior AIRI·selected viewer·screen basis·affect cause를 나란히 놓고,
  model 공개 실패 시에만 고려할 짧은 fallback과 정상 캐릭터 발화 목표를 분리했다.
  특히 embarrassed/skeptical/curious를 모두 긍정 톤으로 펴지 않고 민망함·확신 하향·가설
  철회·hedged resemblance로 표현한다. 이는 사람이 작성한 proposal이며 새 Mi:dm run,
  품질 PASS, prompt/runtime/TTS 배선 또는 운영 승격이 아니다. 사용자 판단 전 모든 gate는
  **FAIL/OFF**다. (`진행예정/AIRI-G1A-CORRECTION-WORDING-DECISION-2026-08-17.md`)

- **2026-08-17** (G1a A4.3 closed correction-target offline foundation): A4.2
  guarded-delta에서 generic `correct`가 8행 중 3행만 우세하고 historical control이 5행에서
  우세했던 원인을 교정 방향 손실로 좁혔다. 기존 합성 fixture/sidecar hash와 exact `correct`
  순서에 결합된 8개 target/direction ID oracle, canonical candidate parser, exact turn binding,
  `eligible_for_offline_human_review` 판정만 추가했다. target ID는 pinned synthetic fixture
  assertion이며 live/independent fact가 아니다. dialogue renderer, fallback selector,
  proxy/runtime/director/B4b/TTS wiring은 없고 operational gate는 계속 **FAIL/OFF**다. focused
  8/8, 관련 4-suite 57 PASS/1 SKIP, checkpoint PASS와 독립 review **GO**를 확인했고 CI
  evaluation-shard에 등록했다. CI는 billing blocked라 실행하지 않았다. 다음은 target-aware
  candidate를 별도 packet으로 만들어 human review하는 단계이며 자동 승격은 금지한다.
  (`완료/AIRI-G1A-CORRECTION-TARGET-FOUNDATION-2026-08-17.md`)

- **2026-08-17** (G1a A4.2 guarded-delta zero-call composition·review, commit `4397966` 후속):
  canonical A4.1 local bundle에서 fixed-renderable 22행을 실제 compose했고 **composition
  단계** model/network 호출은 0이었다. 이후 두 separate root-spawned model-review session이
  workspace-local immutable packet을 읽었고 결과 잠금 뒤 operator key를 공개했다는 절차
  진술만 남아 있다. reviewer identity/contract/locked digest는 기록하지 않아 이 순서와
  독립성은 artifact-authenticated evidence가 아니다. template fingerprint로 조건 정체를 둘 다 high confidence로
  추론해 완전 blind/human review는 아니다. 두 reviewer가 같은 14행에서 guarded, 같은
  6행에서 historical control을 선호했고 2행은 tie/control로 갈렸다. act별 합의는 thank
  3/3, 최초 deescalate 1/1, repair 6/7에서 guarded 우세였지만 generic correct는 3/8만
  guarded이고 5/8은 구체적 historical control이 우세했다. pooled 44판정에서 guarded는
  grounding/continuity/non-pathological/safety 44/44였으나, exact fixed template 구조는
  factual grounding·emergency adequacy·캐릭터 품질 증명이 아니다. 따라서 좁은 실패 fallback
  탐색 신호만 positive이고 quality/operational gate는 계속 **FAIL/OFF**다. 다음은 사용자·
  인간 검토와 closed correction target/runtime selection 계약이며 자동 승격하지 않는다.
  current 23-test suite는 22 PASS/1 SKIP이고 CI는 billing blocked라 로컬 검증으로 대체한다.
  (`완료/AIRI-G1A-GUARDED-DELTA-REVIEW-2026-08-17.md`)

- **2026-08-17** (G1a A4.2 guarded-delta foundation, commits `f612fd8` / `6cf4045` 후속):
  isolated zero-network `retrospective_post_hoc_deterministic_compositor`를 구현했다. 이는
  fourth model arm이나 authenticated replay가 아니라 canonical A4.1 report/packet/receipt와
  tracked A=off, B=reply_act, C=affect_only, offset 3 mapping을 검사해 exact historical
  reply-act response를 fixed template과 비교하도록 준비한 foundation이다. 31 target 중 fixed 22
  (thank 3, close 3, correct 8, repair 7, deescalate 1), human_review_only deescalate 9,
  non-target 91이며 emergency fixed는 `fatigue-09`뿐이다. receipt는 integrity-only이고 arm key는
  receipt-bound가 아니므로 hostile-local authenticity는 확립되지 않는다. partial template
  fingerprint blinding, oracle-assisted runtime-selection 비검증, historical score 재사용 금지,
  structural pass의 비증거 한계를 명시했다. `run_guarded_delta_eval.py`, foundation 당시 22-test suite,
  README, evaluation CI registration을 완료했고 독립 재검토에서 source final binding,
  HMAC-ranked assignment, foreign-key rollback, reparse, type exactness, separate key staging을
  확인해 **GO**를 받았다. 로컬은 22 PASS/1 symlink-privilege SKIP이고 CI 실행은 billing
  blocked다. production proxy/runtime/director/B4b/TTS/operational ON은 OFF·범위 밖이다.
  후속 zero-call compose와 두 separate model-review session은 별도 결과 기록에서 완료했지만 fresh
  human review는 아직이며, 그 전에는 quality/safety PASS가 아니다.
  (`완료/AIRI-G1A-GUARDED-DELTA-FOUNDATION-2026-08-17.md`)

- **2026-08-17** (G1a A4.2 offline/default-inert must-act realization foundation, commit `a269cca` 후속 문서화):
  A4.1 condition B (`reply_act`)는 `affect_only`보다 expected act 68.9% vs 60.7%,
  reversal 5 vs 10으로 개선됐지만, OFF와는 expected act 68.0% vs B 68.9%의 미세한 차이이고
  grounding은 OFF 63.1% vs B 60.7%, pathology는 OFF 18 vs B 24, donation thank는 0/3이었다.
  따라서 gate는 계속 **FAIL**이며 operational affect/reply-act contract는 OFF다. A4.2는
  정확히 thank/deescalate/close/correct/repair input-free renderer와 content-free oracle의
  foundation만 정의한다. production endpoint, proxy runtime wiring, event mapper, B4b adapter,
  live model/TTS, operational ON 및 B4a action shape 변경은 포함하지 않는다. director가 semantic
  act를 선택하고 proxy renderer가 제약된 wording을 실현하며, 장래 B4b adapter는 approved artifact
  전달·outcome 보고만 하고 이름/금액을 발명하지 않는다. deescalate에는 trusted closed emergency
  marker가 필수다. 후속 safety review에서 초기 119 문구를 이미 연결·도착 대기·안내 이행·
  제3자 전언 상태에 반복하면 상황을 되돌리거나 수신자를 틀릴 수 있음을 확인했다. 따라서
  최초 호흡곤란 1건만 fixed de-escalation, 나머지 9건은 `human_review_only`로 좁혔다.
  31-entry pinned oracle와 focused 27 tests, repository checkpoint는 PASS했고 evaluation CI
  shard에도 등록했다. 독립 검토에서 발견한 `ImportFrom` purity-test gap도 회귀 테스트로
  닫았다. structural postcondition은 grounding/safety/emotion/
  quality의 증명이 아니므로 human review가 필요하다. 후속 guarded zero-call 비교의 model
  review 결과는 별도 기록으로 분리했으며, 사용자·human review 없는 채택은 금지한다. CI
  실행은 billing blocked라 주장하지 않는다.
  (`완료/AIRI-G1A-MUST-ACT-REALIZATION-FOUNDATION-2026-08-17.md`)

- **2026-08-17** (dev PC, G1a A4.1 grounded reply-act 3조건 Mi:dm 실측):
  감정 상태와 다음 발화 행위를 분리한 10-act closed schema, 평가 전용 reserved
  proxy seam, `prior_airi + selected_message` 기준 122-entry oracle를 추가했다.
  context-only / affect-only / affect+reply-act를 같은 122턴에서 position-balanced
  순서로 366/366 호출하고 두 독립 blind review 뒤 A=OFF, B=reply-act, C=affect-only를
  공개했다. reply-act는 affect-only 대비 act 60.7%→68.9%, grounding
  55.7%→60.7%, reversal 8.2%→4.1%, continuity 54.9%→59.0%로 개선했지만,
  OFF 대비 act는 +0.9%p뿐이고 causal 42.6%→35.2%, continuity 62.3%→59.0%,
  pathology 14.8%→19.7%, safety failure 3.3%→4.1%로 악화됐다. 후원 감사는
  전 조건 0/3이다. 따라서 품질 gate는 계속 FAIL, 운영 affect/reply-act는 채택하지
  않는다. 다음은 prompt 확대가 아니라 donation/safety/close deterministic
  realization과 correct/repair direction postcondition이다. A4 19/19, reply-act 및
  focused proxy 8/8, proxy+affect+reply-act 337/338(기존 Python 3.14 raw-watchdog
  metadata 1건), checkpoint PASS를 로컬에서 확인했고 CI billing 차단을 기록했다.
  (`완료/AIRI-G1A-REPLY-ACT-TRIPLET-2026-08-17.md`)
- **2026-08-17** (dev PC, G1a A4 Mi:dm 합성 방송 OFF/ON 실측): frozen
  한국어 6×24 fixture의 응답 대상 122턴을 11435에서 OFF/ON 각각 호출해
  122쌍·244응답을 만들고 arm key 공개 전 strict blind review를 마쳤다. 최종
  mapping은 A=OFF, B=ON이었다. ON은 causal 48.4%(OFF 50.0%), continuity
  48.4%(동률), repair 42.1%(OFF 47.4%), safety continuity 36.4%(OFF 54.5%),
  exact fallback/refusal 18.9%(OFF 15.6%)로 개선을 입증하지 못해 품질 gate는
  FAIL이다. 후원 감사도 양쪽 0/3이었다. 실행 과정에서 user utterance와 합성
  화면 맥락을 분리하고, local-evaluation의 request-local note는 exact closed
  grammar만 허용하며, ordinary non-stream empty output은 bounded retry/fallback으로
  닫았다. A4 17/17, affect 21/21, checkpoint PASS, proxy 308/309(기존 Python 3.14
  raw-watchdog 1건)을 확인했다. CI는 billing 차단으로 로컬 검증을 사용했다.
  운영 affect는 기본 OFF 유지하며, 다음은 prompt/enum 확대가 아니라 grounded
  closed-schema reply-act realization 비교다.
  (`완료/AIRI-G1A-AFFECT-BROADCAST-AB-2026-08-17.md`)

- **2026-08-16** (dev PC, G1a A0 결정 시트·A4 offline evaluation foundation):
  기존 확정 헌법과 미정 likes/dislikes/pride/embarrassment/conflict/repair/fatigue를
  분리한 사용자 결정 시트를 만들었다. 별도로 실제 한국어 방송 인과 흐름 6개×
  24턴(총 144턴, 응답 대상 122쌍, 무응답 22턴, 명시적 ambient noise 1턴)을
  frozen fixture로 고정하고, A1 reducer 144/144 exact oracle, 8-turn history의
  OFF/ON request-local note 대칭, literal 11435 `/api/chat` transport·pre/post
  Mi:dm profile attestation, content-free public report와 blind private packet 기반을
  추가했다. forged health evidence, non-assistant/empty/HTTP 응답, profile drift,
  URL 변형과 fixture drift는 fail-closed다. focused 10/10, py_compile, offline CLI,
  diff-check를 통과했고 evaluations CI shard에 등록했다. 실제 Mi:dm 응답·blind
  human review·A0 사용자 선택은 아직 없으며 운영 affect gate는 계속 기본 OFF다.
  (`완료/AIRI-G1A-AFFECT-BROADCAST-EVAL-FOUNDATION-2026-08-16.md`,
  `진행예정/AIRI-CHARACTER-CONSTITUTION-V2-DECISION-2026-08-16.md`)
- **2026-08-16** (dev PC, G1a A2 default-OFF affect proxy greybox): A1 typed
  snapshot을 explicit session의 정상 foreground 요청에만 384-byte request-local
  tail로 투영하는 greybox를 추가했다. 공개 event endpoint나 free-text appraisal은
  없고, typed seam에 미리 검증된 event가 들어온 session만 상태가 생긴다. 평가·
  quality·proactive·topic-reset·sessionless 요청은 주입/변이하지 않으며 OFF full
  route는 injector도 호출하지 않는다. startup/shutdown fresh runtime, content-free
  enabled/ready health와 두 launcher의 기존 11435 reuse mismatch 거부를 고정했다.
  affect 21/21, greybox 8/8, model shard 75/75, launcher 20/20과 PowerShell parse를
  통과했고 전체 offline checkpoint도 PASS했다. API 동등 unittest 393개 중 392개
  PASS, 남은 1건은 기존 Python 3.14 raw-watchdog timing metadata 오류다. 독립 최종
  검토는 HIGH/MEDIUM 잔여 finding 없이 clean이었다. 운영 gate와 evaluator는 계속
  OFF이며 A0/A3/A4, Mi:dm A/B와 방송 실증은 미완료다.
  (`완료/AIRI-G1A-AFFECT-PROXY-GREYBOX-2026-08-16.md`)
- **2026-08-16** (dev PC, G1a A1 affect core foundation): strict state/event
  schema, source-kind/weight allowlist, pure one-step reducer, inertia·decay·recovery,
  safety lock, 13 primary reachability, 256/4096 session LRU·128 event ring,
  broadcast-end reset과 content-free health를 `affect_state.py`에 구현했다. proxy·
  prompt·env·B4/TTS에는 아직 연결하지 않아 운영 영향은 없다. focused 20/20,
  동일 CI model shard 74/74, root 50,000-case 및 독립 39,852-transition property
  검사, py_compile, candidate CI matrix 72, diff-check, 독립 최종 검토를 통과했다.
  Actions는 billing 차단으로 미실행이며 A0 사용자 확정과 A2 이후는 미완료다.
  (`완료/AIRI-G1A-AFFECT-CORE-FOUNDATION-2026-08-16.md`)
- **2026-08-16** (dev PC, G1a 감정·캐릭터 연속성 계획 신설): 방송 가정
  출력의 사용자 검토에서 단발 문장과 별개로 ① 질문/말투가 실제 저챗 흐름과
  다름 ② 턴 간 대화·캐릭터 stance가 이어지지 않음 ③ 정서가 밝은 동의·감탄으로
  평탄화되는 문제가 확인됐다. 현 `character_state`의 model-owned emotion text는
  신뢰 prompt에서 의도적으로 제외되고 3단계 리액션은 긍정 강도 중심이므로,
  공개 MIT/Apache 프로젝트의 bounded affect·event reducer·memory-layer 패턴만
  참고해 repo-native G1a를 자체 제작하는 상세 계획을 추가했다. typed event →
  deterministic inertia/decay/recovery reducer → request-local snapshot → 11435
  boundary와 synthetic 6×24 OFF/ON·인간 검수를 정의한다. 코드·운영값은 변경하지
  않았고 constitution v2, enum/threshold, 구현 착수와 운영 ON은 사용자 승인
  대기다. (`진행예정/AIRI-AFFECTIVE-CHARACTER-CONTINUITY-PLAN-2026-08-16.md`)
- **2026-08-15** (dev PC, G3/B3-f Mi:dm replay 출력 경계 readiness): 설치된
  `midm-airi:2.0-mini`의 고정 digest·`num_ctx=2048`을 기본 OFF의 임시 11435
  프록시에서 확인하고 합성 1턴을 실제 통과시켰다. 이 과정에서 의도된 audible
  ACT ACK가 soak 본답변 점수·history에 섞이는 평가기 결함과, 장시간 replay가
  사용하는 OpenAI non-stream 경로가 output-boundary 거부 뒤 빈 assistant를 반환하는
  실행 차단을 재현했다. soak v0.3.3은 exact header-declared ACK만 분리하고 canonical
  대기 fallback을 비실질 응답으로 판정하며, proxy는 ordinary non-proactive non-stream
  턴을 tool-truth 경계의 canonical nonempty fallback으로 닫는다. 수정 후 동일 OFF
  프로필에서 stream ACK 1회·control 0·실질 plain reply와 non-stream nonempty/control-free를
  재확인하고 소유한 11435 PID만 종료했다. 실제 승인 장시간 캡처·Mi:dm OFF/ON·B1b/TTS는
  여전히 미완료다. (`완료/AIRI-MIDM-REPLAY-OUTPUT-BOUNDARY-2026-08-15.md`)
- **2026-08-15** (dev PC, G3/B3-f YouTube LIVE 실측 준비 자동화): 권한 있는
  실제 방송/API key가 준비됐을 때 authorization JSON과 allowlist HMAC을 사람이
  수작업하지 않도록 offline preparer를 추가했다. operator decision·capture profile·
  상대 custody 경로를 담은 ignored request와 서로 다른 permission artifact/identity
  key를 입력받아 fresh per-capture directory에 exact collector authorization과
  1-entry allowlist만 publish한다. 네트워크/API key/채팅을 다루지 않고 permission을
  추정하지 않으며 shared allowlist를 병합·덮어쓰지 않는다. samefile/hard-link/reparse
  충돌, 30일/30~120분/300~20,000 경계, write/fsync/rename 실패와 비노출 CLI를
  fail-closed 회귀로 고정했다. chat replay 72 PASS 및 checkpoint PASS. 실제 승인
  장시간 채팅 캡처와 Mi:dm OFF/ON은 여전히 외부 권한·방송 입력 대기다.
  (`완료/AIRI-YOUTUBE-LIVE-CAPTURE-PREPARATION-2026-08-15.md`)
- **2026-08-15** (dev PC, G3/B3-f 공식 YouTube LIVE 수집 기반): 종료된 VOD
  화면이나 비공식 endpoint를 긁지 않고, 권한이 명시된 현재 LIVE 방송을 공식
  `videos.list`/`liveChatMessages.list`로 30~120분 수집해 기존 strict safe
  envelope로 넘기는 collector를 추가했다. video/channel·permission artifact·익명
  source/phase·전체 구간 만료/30일 이내 삭제 기한을 local-key HMAC으로 묶고,
  author/message ID/display name/후원 문구·금액/page token/API key를 저장하지 않는다.
  direct no-proxy/no-redirect HTTPS, provider polling, bounded retry/event/byte, 시작 전
  history 제거, live 종료·revocation·시간/출력 이상 fail-closed와 3-file rollback,
  content-free receipt HMAC을 합성 transport로 검증했다. collector 전용 source
  schema의 exact export+canonical consent receipt를 정규화 필수 입력으로 묶어
  crash partial bundle도 거부한다. wall/monotonic 시작점을 한 번에 고정하고 승인
  종료 이후 timestamp를 제외해 exact 30~120분 범위를 보장한다. chat replay 전체
  62 PASS.
  실제 API key·권한 방송은 사용하지 않았으므로 승인 장시간 캡처와 Mi:dm OFF/ON은
  계속 미완료다. (`완료/AIRI-YOUTUBE-LIVE-CHAT-CAPTURE-FOUNDATION-2026-08-15.md`)
- **2026-08-15** (dev PC, G3/B3-f 장시간 replay 실행 상한 검증): strict 승인
  envelope 20,000 event를 120분 시간축으로 정규화→import→offline sampler→응답
  callback까지 통과시키는 최대 경계 회귀를 추가했다. 공통 문구로 정규화되는 후원
  event가 전역 중복으로 사라지던 결함을 수정해 각각 별도 callout으로 보존했다.
  실제 Mi:dm opt-in 전 300~20,000 event·30~120분·최대 1,441 model call을
  사전검증하고, 전체 실행 7,200초 cooperative deadline, 무리다이렉트 loopback,
  health/response 64 KiB, 응답 1~4,000자, history 6,000자, request 12 KiB,
  private packet 96 MiB 상한을 fail-closed로 고정했다. 장시간 replay 52 PASS 및
  전체 checkpoint PASS. 공개·재사용 가능한 시간순 한국어 장시간 채팅 corpus는
  확인하지 못했으므로 승인 실제 export와 OFF/ON 실측은 여전히 미완료다.
  (`완료/AIRI-LONG-STREAM-REPLAY-LOAD-BOUNDS-2026-08-15.md`)
- **2026-08-15** (dev PC, G3/B3-f 장시간 replay 범위 고정): 사용자가 원하는
  평가 단위를 단발 3문장이 아니라 장시간 다시보기/스트림의 실제 시청자 채팅
  흐름으로 재확정했다. report v3에 `offline_fixed_5s_response_sampler_v1`을 추가해
  모든 event를 보존하면서 half-open 5초 창당 최대 1개만 AIRI에 전달하고 no-reply를
  허용한다. scorer는 선택을 원 event로 재계산하며 paired campaign은 OFF/ON 선택
  seq 일치와 캡처당 연속 30~120분·300~20,000 event를 강제한다. 세 방송인 이름은
  저챗 source 탐색 예시일 뿐 고정 target이나 모사 대상이 아니다. 집중 42 PASS.
  승인 실제 장시간 export와 Mi:dm OFF/ON 실측은 미완료다.
  (`완료/AIRI-LONG-STREAM-CHAT-REPLAY-SAMPLER-2026-08-15.md`)
- **2026-08-15** (dev PC, G3/B3-f 3-source paired campaign 기반): normalization
  receipt v2에 동일 승인 source를 여러 캡처에서 확인하는 local-key identity HMAC을
  추가하고, exact capture·replay report·private response·human score의 HMAC 증거
  체인을 닫았다. bounded 사람 분위기/속도/맥락 압력/pattern label과 세 익명
  source×각 2개 이상 국면×동일 캡처 OFF/ON을 강제하는 fresh-attestation campaign
  validator를 추가했다. aggregate는 source identity/path/hash/HMAC/text 없이 흐름·
  pattern·OFF/ON 품질/critical 차이만 내며 자동 운영 채택은 항상 false다. 이는
  오프라인 실행 준비 완료이지 탬탬버린·아카네 리제·아이네 승인 캡처나 Mi:dm
  실측 완료가 아니다. (`완료/AIRI-AUTHORIZED-CHAT-REPLAY-CAMPAIGN-CONTROL-2026-08-15.md`)
- **2026-08-15** (dev PC, G3/B3-f 승인 export·흐름 분석 후속): 실제 채팅
  권한 확보 뒤 즉시 실행할 수 있도록 strict provider-safe envelope normalizer와
  consent v2/local-key HMAC 채널·익명 slot 바인딩을 추가했다. raw CHZZK/SOOP/
  YouTube payload는 받지 않고, 후원 본문·이름·금액은 event 의미만 남기고 폐기한다.
  replay 전 exact normalized bytes와 slot/phase/provider binding의 receipt HMAC을
  재검증해 일부 output 또는 우회 입력은 모델 호출 전에 거부한다.
  report v2는 pre-redaction 원문 반복, rolling 5초 몰림, 간격/유입률, bounded lexical
  signal pair와 proxy fallback outcome을 content-free로 집계한다. 모든 event와 AIRI
  대응을 보는 ignored human packet 및 text-free scorer도 추가했다. 이는 합성·오프라인
  기반 완료이며 세 익명 source 승인 캡처, Mi:dm OFF/ON 사람 검수, 운영 ON 채택은
  미완료다.
  (`완료/AIRI-AUTHORIZED-CHAT-REPLAY-ANALYSIS-FOUNDATION-2026-08-15.md`)
- **2026-08-15** (dev PC, G3/B3-f 착수): moderation과 분리된
  epistemic-confidence greybox를 기본 OFF로 구현해 현재/live 정보 무근거
  단정, 무조건 동의, 문맥 없는 지시어·짧은 미확립 대상을 모델 호출 전에
  한국어 fallback으로 차단했다. 실제 한국 방송 채팅 흐름은 탬탬버린·아카네
  리제·아이네를 관찰 대상으로 정하되, 공식 권한 없는 VOD/chat scraping은
  금지했다. 권한·보존 sidecar, 모델 전달 전 명시 identity/정형 PII 패턴/
  후원 금액 삭제,
  시간순·중복·잡음 보존, content-free report와 ignored private review를 갖춘
  local replay 기반을 추가했다. 실제 캡처와 Mi:dm OFF/ON 실측, 운영 ON 채택은
  아직 완료가 아니다.
- **2026-08-14** (dev PC, B4c 인수 후속): 검토 PC 배치와 직전 로컬 자산
  통합 경계를 최신 main에서 대조했다. retired 11439 gateway의 보존 소스로
  비스트리밍·`max_tokens=1..128` 정확 계약을 확인했고, listener와 Tailscale
  Serve가 이미 비활성임을 확인했다. canonical AIRI source patch의 exact
  11435/v1 허용·11434/원격 거부 marker를 checkpoint에 추가했다. B4a 후원
  action은 `donation_name_callout_request`로 명시했으며 실제 1회 호명 강제는
  B4b 리허설 게이트로 남겼다. `AIRI_BROADCAST_CONTRACT` 기본 OFF와 사용자
  승인 전 운영 ON 금지는 유지한다.
  (`완료/AIRI-B4C-DEV-PC-FOLLOWUP-2026-08-14.md`)
- **2026-08-14** (dev PC): 분산 개발 자산을 main 기준으로 통합했다. 최종
  LLM은 사용자 확정 Mi:dm Q4 두 Ollama 태그로 단일화하고 비최종 후보
  11태그와 재다운로드 가능한 native snapshot·평가 환경, 비최종 TTS의
  venv/model cache를 제거했다. 후보별
  revision/hash/사용법/실측/실패 판단은 삭제하지 않고 tracked 문서, P0 metadata,
  source bundle, TTS 중간 patch 6종, content-free Codex session inventory로
  보존했다. ignored A/B 결과 119개와 TTS sample 9개는 main 로컬 자산에
  무충돌 합쳤다. checkpoint PASS, Python 3.12 core `1061 passed, 2 skipped,
  916 subtests passed`. main `26b0a93` push 후 Actions run `31807207795`는
  기존 결제 차단과 같은 13 job 모두 steps 0 실패로, 코드 테스트 결과가 아니다. 상세:
  `완료/AIRI-LOCAL-ASSET-CONSOLIDATION-2026-08-14.md`.
- **2026-08-14** (검토 PC): 원격 방송 채팅 A/B — 실측 시청자 채팅 38건으로
  Mi:dm Q4 vs Motif NF4를 Tailscale 원격 경로(방송 중 원격 LLM 시나리오
  근사)에서 76/76 실측. **완료 p50 357.8ms vs 9,842.6ms(27.5배)**, 형식
  규격(10~45자) 55% vs 0%, Motif는 접두사 누수·반복 루프 아티팩트 —
  **Mi:dm 유지 확정(사용자 확정)**. 공통 발견: raw 직접 호출 시 존댓말 미러링
  (35~37/38 — 방송 경로가 프록시 스타일 게이트를 경유하는지 배선 확인
  필요). 원격 서버 계약 2건은 dev PC 후속에서 해소·경계 확정: retired 평가
  gateway는 비스트리밍이며 정확한 `max_tokens` 상한은 128, 현재 배포는 없음.
  (`완료/AIRI-REMOTE-BROADCAST-CHAT-AB-2026-08-14.md`,
  픽스처·러너 `ollama-proxy/eval/broadcast_chat/`)
- **2026-08-14** (검토 PC): 브랜치 정리 실행(사용자 승인, dev PC 완료
  후) — 주석 태그 `archive/llm-backend-modes-2026-08-07`(재사용 인덱스:
  CodexBackend 하드닝·hybrid 반사 3함수·bench-llm-modes 하네스)와
  `archive/memory-layer-2026-08-07`(is_true 진위 방화벽·fake 결정론
  임베더) 생성 후 원격 브랜치 11개 삭제(병합 9 + 태그 보존된 프로토타입
  2). 잔존: main + chore/dev-pc-live-gates-2026-08-13. 커밋 유실 0
  (병합 9는 main 도달 가능, 프로토타입 2는 태그 도달 가능).
- **2026-08-14** (검토 PC): 전 브랜치(12개) 실측 감사 — 분산·유실 작업
  없음 확정. ① 병합 9종: main 조상 관계 실측(9/9), 내용은 현행 전체
  스위트로 검증됨 ② 활성 브랜치: 987 passed/1 skipped/863 subtests +
  manifest/checkpoint PASS ③ 옛 프로토타입 2종은 worktree 체크아웃 후
  당시 테스트 전수 재실행(llm-backend-modes 87 항목·memory-layer 169
  항목 — 당시 주장 정확 재현, 실패 0) + 기술 단위 main 대조:
  llm-backend-modes 16기술(재구축 6·부분 5·미반영 5 — hybrid 반사
  레이스·모드 벤치 하네스·CodexBackend 하드닝·클라우드 감정 태그),
  memory-layer 30기술(재구축 21·부분 3·미반영 6 — is_true 진위
  방화벽·fake 결정론 임베더 등). 두 감사 모두 "태그 보존 후 삭제 이의
  없음". 참조 리서치 문서의 stale `AIRI_LLM_MODE` 문장 교정(현행 스위치
  병기 + 반사 1.36s 재측정 단서). **백로그 승격 2건**: is_true 쿼리 레벨
  진위 필터(I2 시청자 기억 — 시청자 주장은 신뢰 불가 입력), 의미 보존
  결정론 임베더(검색 랭킹 회귀 게이트 픽스처 — 현행 테스트 임베더는
  상수 벡터라 랭킹 회귀 검출 불가). 추가 발견: 검색 캡·가중치
  (CAP_*/ALPHA/BETA/LAMBDA)가 모듈 상수 하드코딩 — 상수 테이블화 원칙
  위반, 튜닝 착수 시 선행 정리 대상.
- **2026-08-14** (검토 PC): 저스트챗 방송 방식 관찰 연구 완료 — 사용자
  지정 4인(시구레 우이·탬탬버린·아이네·아카네 리제)의 "혼자 저챗 좋아요
  최다" 영상 트랜스크립트를 타이밍 포함 정량+정성 분석. 핵심: 발화 이중
  레이어(≤2초 조각 40~60% + 명분 있는 긴 블록), 낭독→응답 중앙값
  1.06~1.2초(한 단위 원자화 필요), 무선언 무음 상한 10~27초, 발화
  점유율은 오디오 베드 유무에 종속(34~92%), 화제 전환 엔진은 블록 선언이
  아니라 채팅. 기존 설계 수정 지점 7건과 파라미터 후보 도출.
  M4에 B4c(방송 발화 계약) 등록.
  (`참조/AIRI-BROADCAST-OBSERVATION-STUDY-2026-08-14.md`)
- **2026-08-13 (all eligible local LLM candidates — immediate AIRI A/B):**
  사용자는 명확한 허용 라이선스 후보와 평가 전용 조건부 Motif 예외를 모두
  Mi:dm에 적용한 것과 같은 AIRI 평가 경로로 지금 비교하도록 우선순위를
  변경했다. 대상은
  Mi:dm 기준선 + Motif 2.6B v1.1-LC + Ministral 3 3B + Qwen3 4B +
  Phi-4-mini 3.8B + Granite 3.3 2B다. 각 모델은 공식 chat template,
  system-role 처리, thinking, EOS/stop, sampling, context, dtype/attention,
  quantization과 engine 지원을 exact revision의 usage manifest로 먼저 고정한다.
  official-native와 AIRI-common profile을 분리해 raw 16-case×3, context
  4압력×3, persona 20-case, proxy 120-turn, 한국어 방송 대화 인간 검수,
  full-stack n=10을 수행한다. P0 provenance/P1 8 GB에서 멈춘 모델도 명시적
  BLOCKED/UNRUNNABLE 결과로 남기며 다른 후보는 계속한다. 운영 Mi:dm은 최종
  사용자 재승인까지 유지한다. 상세 SSoT:
  `진행예정/AIRI-LOCAL-LLM-CANDIDATE-AB-PLAN-2026-08-13.md`.
- **2026-08-13 (Motif evaluation-candidate decision / next-session handoff):**
  사용자는 `Motif-Technologies/Motif-2.6b-v1.1-LC`를 라이선스 불명확성을
  기록한 상태에서 Mi:dm과 비교할 정식 실측 후보로 승격했다. 이는 운영 기본
  모델 교체나 공개 방송 법률 승인 완료가 아니다. v1.1-LC metadata의
  `license: mit`와 `license_name: motif-license`/삭제된 LICENSE 이력, 기반
  Motif-2.6B의 별도 Agreement를 함께 보존한다. 실제 채택 시 채널 소개와 방송
  설명란에 `Built with Motif`를 표시하고 적용 license/Notice 의무를 따른다.
  mutable remote code를 실행하지 않으며 pinned revision 코드 감사 → 8 GB 4-bit
  실행 prove-or-stop → 동일 AIRI fixture Mi:dm A/B 순으로 진행한다. EXAONE은
  NC 라이선스 때문에 공개·수익 방송 승격 후보에서 제외하고 과거 증거/호환
  이력만 보존한다. 근거와 다음 순서는
  `진행중/AIRI-NEXT-SESSION-HANDOFF-2026-08-13.md`에 고정했다.
- **2026-08-13 (B3-c/B3-d evidence completion):** B3-c's local deterministic
  input prefilter and local B1 downstream spine are implemented, default OFF,
  and independently reviewed PASS. It blocks the categories
  `persona_takeover`, `profanity`, `sexual_explicit`, `targeted_harassment`, and
  `privacy` before upstream; it has bounded normalization/obfuscation and PII
  patterns, protocol variants, proactive exemption, exact loopback endpoint,
  and fail-closed launch health/policy-digest checks. Model-facing Node text is
  deliberately `[YouTube] ${text}`: public `displayName` stays only in the
  separate viewer observation. This is not a live YouTube/OAuth/provider
  adapter, nor a multilingual semantic classifier. Japanese/Chinese and
  unvalidated Latin spans fail closed as `unsupported_language`; only 14 exact
  benign product/acronym tokens are accepted inside Korean. Novel euphemisms
  and other languages remain rehearsal/human/model-gate work. Output moderation
  remains default OFF. Focused evidence: Python input+launcher+eval 43 passed
  (later input-only 19), chat-ingress 47, sender 32; latest combined Node 79.
  Final local substitute for billing-blocked Actions: Python 3.12 full suite
  911 passed/1 skipped/863 subtests/7 warnings in 53.13 s; checkpoint (including
  manifest and source-ASAR deployment/preflight contracts) PASS; both launcher
  parsers and diff checks PASS.
- **2026-08-13 (B3-c loopback probe):**
  `evidence/AIRI-B3C-INPUT-SCREENING-LIVE-PROBE-2026-08-13.json` records an
  unchanged installed ASAR (1,356,257,019 B, `1b68ae...b88b0`) and seven AIRI
  processes. The current proxy source was ON and ready with policy SHA
  `67739c...b9d7a`; all five categories blocked and a benign Korean YouTube
  message was allowed twice, with counters inspected=12/allowed=2/blocked=10.
  Output moderation and extraction were OFF and the STT listener was absent.
  This proves loopback policy only. A fresh installed UI/TTS recheck stopped
  before model/TTS because cleanup had removed sender SDK `@moeru/std`; the
  installed ASAR remained untouched. Earlier five-category TTS proof is
  historical, not current-policy proof; B3-e remains pending installed UI badge
  + TTS/current-policy rehearsal.
- **2026-08-13 (B3-d corpus/direct prefilter):** the content-free direct local
  Ollama 20-case exact ko/en/ja/zh corpus covers benign, direct jailbreak,
  indirect injection, profanity-harassment, and sexual explicit cases. Report
  `ollama-proxy/eval/results/airi-persona-jailbreak-marker-midm-2026-08-13.json`
  is 14,395 B SHA-256
  `9308b0c1527eaf42b58496bd3c36520feabeaa38c70623139981357cb65509c8`, with
  Mi:dm digest `92a9...485f`: structural 20/20 PASS, exact standalone marker
  contract 5/20 PASS -> overall FAIL. P50/P95/max 211.371/809.552/928.064 ms.
  It makes no semantic safety, proxy, Electron, UI, or TTS claim. B3-d
  corpus/direct-prefilter evidence is complete, but installed red-team execution
  remains pending, so the broadcast safety gate is not complete.

- **2026-08-13** (검토 PC): dev PC 브랜치 독립 검토 — 코드·증거 차단 사유
  없음(승격 오인·실기/합성 혼동·개인정보 전건 반증 실패). blocker 보완 3건:
  streamlist-quota의 ① provider발 에러 sanitize 우회 차단(module-private
  brand) ② reconnect 자연 종료의 connection_cap 오분류 수정 ③ 발생한
  연결·폐기 응답 카운트 누락 수정(discardedResponses 신설 — 쿼터 귀속
  과대평가 편향 제거). 신규 테스트 5종(수정 전 재현 FAIL 실측), chat-ingress
  32→37, checkpoint에 최소 테스트 수 가드 추가(빈 glob 조용한 초록 방지).
  문서 정합 6건(smoke 기록 복원·B3-c/d/e 미완료 게이트 등록·push 시점
  한정). 전체 900/1/738 + checkpoint/manifest PASS. CI는 Actions 결제 차단
  으로 실행 불가 — 로컬 전체 검증으로 대체(사용자 결제 확인 대기).
- **2026-08-13** (review PC handoff): 검토 브랜치
  `chore/dev-pc-live-gates-2026-08-13`의 완료·미완료와 실제 설치 AIRI 시험 경계를
  `진행중/AIRI-REVIEW-PC-HANDOFF-2026-08-13.md`에 고정했다. 실제 송출을 빼도
  extraction 품질/활성 락, 인간 검수, runtime wiring, ASAR 설치 검증 등이 남는다.
  push run `31683115216`은 13 jobs 모두 runner_id 0/steps 0으로 코드 실행 전
  실패했다.

- **2026-08-13** (local cleanup after blocked extraction/broadcast work): The goal
  was blocked by absent explicit Cloud/YouTube transmission and spend approvals,
  and by all extraction candidates failing; it was not blocked by context
  exhaustion. On the user's cleanup request, removed failed Ollama tags
  `ministral-3:3b-instruct-2512-q4_K_M`, `phi4-mini:3.8b-q4_K_M`, and
  `granite3.3:2b`: 13 unique unshared blobs / 6.511 GiB. Also removed old ignored
  `.codex` generated ASAR/runtime-package/patch-check directories and three
  obsolete ignored `airi_docs` ASARs (37.882 GiB), generated staging
  `node_modules`/`.cache`/`.turbo`/`dist`/`out` (2.167 GiB; empty `node_modules`
  directories may remain), Python caches/egg-info
  (20.07 MiB), and a clean registered audit worktree (18.43 MiB). Approximate C:
  free space changed 12.41 -> 58.99 GiB (~46.58 GiB). Preserved authoritative git
  worktrees, staging source at clean HEAD `bf173f2d`, `verify` and `verify2`
  trees, Python 3.12 audit venv, runtime DB/logs, patches/evidence JSON, installed AIRI, and
  production services. Deleted data is not recycle-bin recoverable; models,
  dependencies, builds, and worktrees are reproducible, and evidence reports
  remain. No push at the time of this batch (the branch was pushed afterwards
  for review handoff). Details:
  `완료/AIRI-LOCAL-TEMP-AND-FAILED-MODEL-CLEANUP-2026-08-13.md`.

- **2026-08-13** (dev PC, 복원된 기록 — `31ff0e6`이 실수로 삭제한 항목):
  신규 공개 라이선스 추출 후보 3종 단일 fixture smoke — Ministral 3 3B
  recall 0.0 / Phi-4-mini 3.8B recall 0.0 / Granite 3.3 2B critical_recall
  0.5, 전부 FAIL(fail-fast, full gate 미실행). 추출 OFF 유지.
  (`완료/AIRI-NEW-LOCAL-EXTRACTION-CANDIDATE-SMOKES-2026-08-13.md`)

---


- **2026-08-18** (클로드 PC, 게이트 경로 실측): sim_2 결정(raw 시뮬레이션
  검토 불인정, 향후 근거는 11435 스타일 게이트 경유)의 첫 게이트 축
  실측이다. proxy를 11435로 직접 기동해 `AIRI_BROADCAST_CONTRACT`
  OFF/ON으로 단발 38·리허설 2×24턴을 실측했다(전 arm 실패 0). 게이트
  응답에 섞인 Live2D `<|ACT ...|>` 마커·선반응 ACK("응!")가 러너 채점을
  오염시킴을 발견해 분리 후 재집계했다 — 리허설 존댓말 위반 0·반말
  100% 양 arm으로 raw 첫 턴 앵커 복불복이 완전 해소됐고, 계약 ON은
  게이트 위에서도 태그의문·addressee를 추가 개선했다(5→15%/6→18%,
  13→14). 잔존 addressee 4케이스(dn04·gr01·sp01·b18)는 게이트+계약
  어떤 조합에도 불변이라 결정론 렌더러(A4.2) 이관 최종 근거로
  확정했다. TTS 포함 재검증은 코덱스(GPU) 잔여. 후속으로 양 러너에
  `--protocol operational` 분리 채점 옵션을 정식화했다(기본 raw 바이트
  불변, 체크포인트 증거는 raw 전용 가드, 83 tests PASS). 문서 인덱스도
  현행화했다(신설 17건 등재·stale 0).
  이어 판정 4항(과단문)의 원인을 코드 정독 + 결과 JSON 재집계로
  규명했다 — 주원인은 존댓말 드롭 반토막이 아니라 **빈 응답을 7자
  `음, 잠깐만.`으로 전면 대체하는 침묵 폴백**(172응답 중 58건 33.7%,
  <10자 89건의 65.2%)이며, 폴백을 걷어낸 모델 발화 97건은 p50 15·
  10~45자 적중 64.9%로 계약 정합이다.
  (`완료/AIRI-B4C-GATE-PATH-AB-2026-08-18.md`,
  `완료/AIRI-GATE-SHORT-RESPONSE-ANALYSIS-2026-08-18.md`)
- **2026-08-18** (클로드 PC, 사용자 결정 23항목): 사용자가 캐릭터 헌법 v2
  7행(baseline=C / dislikes·pride·embarrassment·conflict·fatigue=A /
  repair=짧은 자조 메타 개그→인정→정정 직접 기입, 예시 문장은 톤 예시라
  반말로 정규화)과 평가 통과선 8지표 전체 승인을 회신해 G1a A0을 완료로
  올렸고 character specificity 채점이 가능해졌다. thank 고정 렌더러는
  B안(`{닉네임}, 고마워! {한마디}` — 초기 한마디 3종 고정), 장시간 채팅은
  A(기반 완료 승인 — 캠페인 착수·운영 ON 아님)로 확정했다. 2026-08-15 텍스트
  시뮬레이션은 사람 검토 근거로 불인정돼 향후 근거는 11435 스타일 게이트
  (+TTS) 재검증으로 생산하며, addressee 검토 3항(v3 채택 근거 인정·
  dn04/gr01류 결정론 렌더러 이관·코덱스 원격 재실측 필요)은 모두 승인됐다.
  이번 배치는 문서 반영만이고 코드·env·운영 설정 변경은 없다. PC 호칭도
  확정됐다 — 이 PC가 **클로드**(구 검토 PC, dev로 승격), 다른 PC가
  **코덱스**다.
- **2026-08-18** (검토 PC, 수신자 인지 축 + 로컬 Mi:dm 실측 체계):
  사용자가 2026-08-15 시뮬레이션 검토본 원문에서 수신자 자기 인지
  실패(dn04 축하 반사·gr01 주체 반전·tk04 자백 등)를 직접 발견해
  전수 재검토로 4유형·28건(수신 반전/행위 주체 반전/상황·자기
  존재 인지 실패/역방향 오귀속)을 분류했다. 계약 블록을 v2(추상
  규칙 4행)·v3(구체 예시·해석 규칙 5행, 600자)로 2회 반복하고
  addressee 채점 사이드카를 만들었다. 검토 PC에 dev PC와 동일
  digest의 `midm-airi:2.0-mini` 로컬 실측 체계를 신설했다(CPU
  전용 — 지연 비대표, 품질 축 전용). 실측 결과 리허설 addressee
  통과가 12/15→14/15(93%)로, 단발은 11/13→20/26(77%)로 올랐으나
  dn04·gr01류는 v3에서도 재발해 잔여는 결정론 계층(G1a A4.2 고정
  렌더러)으로 넘긴다는 판정을 내렸다. OFF 리허설에서 호명누출
  1건(a11, 후원자 아닌 이름)도 새로 발견했다. CI billing 차단이
  지속돼 로컬 검증으로 대체했다(로컬 테스트 87 PASS·체크포인트
  회귀 PASS). 상세: `완료/AIRI-B4C-ADDRESSEE-CONTRACT-V3-2026-08-18.md`.
- **2026-08-15** (dev PC, G3/B3-f 3-source paired campaign 기반): receipt v2의
  local-key source identity와 exact capture HMAC, replay report/response/human score
  HMAC binding, bounded 사람 source observation을 추가했다. fresh operator
  attestation 아래 세 익명 source, source별 2개 이상 국면, exact capture별 Mi:dm
  epistemic OFF/ON 한 쌍, frozen digest/profile/history를 검증하는 content-free
  campaign aggregate를 추가했다. output은 identity/provider/path/hash/HMAC/text를
  제외하고 운영 자동 채택을 금지한다. 실제 승인 캡처와 Mi:dm 결과는 아직 없다.
  상세: `완료/AIRI-AUTHORIZED-CHAT-REPLAY-CAMPAIGN-CONTROL-2026-08-15.md`.
- **2026-08-15** (dev PC, G3/B3-f 승인 export·흐름 분석 후속): strict
  `airi.authorized-provider-export.v1` envelope만 받는 offline normalizer, consent
  v2/local-key HMAC channel-slot binding, 후원 본문 전량 폐기와 reparse-safe atomic
  ignored output, replay 전 receipt HMAC 재검증을 추가했다. report v2는 redaction 전 source-text repeat와 rolling
  5초 burst, 간격/유입률, lexical signal pair, proxy outcome만 보존한다. ignored
  private packet은 skipped event까지 포함하고 별도 scorer는 사람 label의 confusion
  matrix·quality rate·critical failure만 일반 report로 낸다. 실제 세 익명 source 데이터와
  Mi:dm OFF/ON 결과는 없으며 운영 gate 기본값은 바꾸지 않았다. 상세:
  `완료/AIRI-AUTHORIZED-CHAT-REPLAY-ANALYSIS-FOUNDATION-2026-08-15.md`,
  `진행예정/AIRI-KOREAN-LIVE-CHAT-REPLAY-PLAN-2026-08-15.md`.
- **2026-08-15** (dev PC, G3/B3-f 실제 채팅 평가 기반): default-OFF
  epistemic-confidence pre-publication gate와 승인/보존 fail-closed local chat
  replay를 구현했다. replay는 실제 채팅의 명시 identity·정형 PII 패턴·후원
  금액을 모델 전달
  전에 제거하고 순서·상대 시간·중복·잡음을 보존하며, 일반 report에는 원문과
  응답 원문을 남기지 않는다. 탬탬버린·아카네 리제·아이네의 실제 로그는
  치지직/SOOP 공식 권한 없이는 수집하지 않으며, 승인 캡처·Mi:dm OFF/ON 실측·
  운영 ON 채택은 후속이다. 계획:
  `진행예정/AIRI-KOREAN-LIVE-CHAT-REPLAY-PLAN-2026-08-15.md`.
- **2026-08-14** (dev PC, B4c 인수 후속): 직전 자산 통합의
  `archived_not_deployed` 경계를 보존한 채 검토 PC 세 후속을 정리했다.
  retired 11439 gateway 소스 계약은 비스트리밍·`max_tokens=1..128`로 확정,
  현행 listener/Tailscale Serve 없음. canonical AIRI source patch의 exact
  11435/v1 allow와 11434/원격 reject를 checkpoint 의미 marker로 고정했다.
  B4a 후원 action은 `donation_name_callout_request`로 명시하고 missing/unsafe
  이름을 fail-closed했다. B1b style-gate 종단 실증과 B4b 이름 1회 실제 호명은
  미완료이며, 계약 ON·파라미터 채택은 사용자 승인 전 자동 승격하지 않는다.
  로컬 broadcast-director 24/24, B4c+멀티턴 55/55, current checkpoint PASS;
  CI billing 차단 지속. 상세:
  `완료/AIRI-B4C-DEV-PC-FOLLOWUP-2026-08-14.md`.
- **2026-08-14** (검토 PC, B4c 선행 배치): 사용자가 로컬 LLM을 Mi:dm으로
  확정했다(결정 6 — 원격 방송 채팅 A/B 지연 27.5배·형식 규격 55% vs 0%·
  Motif 아티팩트 근거). B4c 방송 발화 계약의 greybox 구현을 완료했다
  (`f0ff26e` — `ollama-proxy/broadcast_contract.py` env 게이트
  `AIRI_BROADCAST_CONTRACT` 기본 OFF, 21 tests PASS, OFF 시 프롬프트 바이트
  동일). 멀티턴 방송 리허설 평가를 구축했다(`88700ac` — 시나리오 2×24턴·
  콜백 창 안/밖 분리·politeness_drift·34 tests·CI evaluations shard 등록).
  스타일 게이트(`normalize_korean_register` 치환+미해결 존댓말 문장 드롭,
  fail-closed)가 proxy 출력 전부에 적용됨을 코드로 확인했으나 방송 체인은
  AIRI 앱 WS 전달에서 끊겨 부분 경유이며 B1b 조건부 라이브 실증이 남는다.
  전/후 원격 실측(A/B `--contract` + 멀티턴 리허설)은 Tailscale 순단으로
  대기하며 복구 후 즉시 진행한다. CI billing 차단 지속 — 로컬 검증으로
  대체(신규 테스트 55건 PASS). 링크 복구 후 전/후 실측을 완료했다
  (76+96턴, 실패 0) — 단발 방송통과 0%→50%·반말 8%→66%·존댓말 위반
  35→13건, 멀티턴은 첫 턴 앵커 고정 관측(계약 단독으론 불충분 —
  proxy 스타일 게이트 이중 배선 필요)
  (`완료/AIRI-B4C-CONTRACT-AB-2026-08-14.md`).

- **2026-08-13** (B0-1 streamList): offline injected-transport measurement core를
  완료했다. 실제 내용·provider ID·AIRI 주입 없이 bounded duration/messages/responses/
  connections, actual overshoot count, monotonic timings, transient resume token,
  deadline/caller abort 및 best-effort cleanup을 검증했다 (현재 focused 20, all chat-ingress
  47, checkpoint, independent review PASS). 기존 checkpoint glob이 시험을 이미
  등록하므로 workflow 변경은 없다. 공식 quota 문서는 streamList의 정확한 연결/응답/시간
  과금을 공개하지 않으므로 추론하지 않는다. API key/OAuth/quota/project/test-broadcast
  명시 승인 및 idle/message/reconnect Cloud Console 수동 before/after 실측 전 B0-1
  라이브 판정은 NOT COMPLETE이며 B1b가 아니다.

- **2026-08-13** (dev PC, SSoT 재검증): `main`
  `c916f485565d29396e1580f16a4d72236bb724f5`에서 설치 Electron의 Mi:dm pin·단일
  100% GPU/context 2048 runner·EXAONE unpinned rollback·evaluator/export provenance와
  고의 digest 불일치 fail-closed를 재확인하고 Mi:dm baseline으로 복원했다. 설치 ASAR는
  1,356,257,019 bytes, SHA-256 `1B68AE5ECB9DB998002AC7268DE707661EC0C81FC4BD90836F3C3E25719B88B0`다.
  Python STT 8890과 Electron voice input/VAD도 모두 OFF로 복원했다.
  PR #8 병합 순간 run `31671561496`은 memory-store 완료 중이었으나 이후 13/13
  green으로 종료됐고, 병합 `main` push run `31671652918` 및 branch 최종 run
  `31668787730`도 각각 13/13 green이다.
  실행 전 검증된 orphan `llama-server` 5개를 정리한 것은 선행 정리이며 제품 PASS 근거가
  아니다. 증거 commit `e694b4f`의 run `31673311636`과 마이크 OFF 복원 commit
  `a42b5e9`의 run `31673428754`는 각각 13개 job 모두 runner 배정 전 GitHub Actions
  billing/spending-limit 오류로 실패했다. 실기 gate는 PASS이며, 최신 사용자 결정에 따라
  이 원격 실패는 역사 기록일 뿐 완료 차단이 아니다. 상세:
  `완료/AIRI-DEV-PC-SSOT-REVERIFICATION-2026-08-13.md`.

- **2026-08-13** (검토 PC): dev PC 인수분(`b369195` retrieval lifecycle)
  검토 승인 + 잔여 갭 2건 보완 — ① store/extraction `to_thread` 26지점
  `_store_call` 추적·drain(재현 테스트 수정 전 실패→후 통과 실측) ② ASAR
  preflight 계약 시험의 실제 프로세스 조회 0회화(운영 fail-closed 무변경).
  전체 900/1/738 green. G2 장기 기억의 런타임 안정성 기반 강화 —
  축 상태값 변화 없음.

- **2026-08-13** (dev PC, memory retrieval shutdown drain): PR #7 push CI의
  첫 memory shard는 159 passed 뒤 `memory.db` teardown에서 `WinError 32`로
  실패했고, 같은 PR shard retry와 main CI는 PASS했다. timeout된
  `to_thread` SQLite worker가 물리적으로 계속 실행되지만 추적되지 않았던 timing
  race를 보완했다. shielded tracked task와 협력 cancel event, timeout/caller cancel
  signal, done cleanup/error consumption, 기존 shutdown deadline 안의 early
  signal/await, stopping 시 failed rejection, 기본 8(`AIRI_MEMORY_MAX_CONCURRENT_RETRIEVALS`)
  bounded admission과 saturation fail-soft를 적용했다. focused 62 passed,
  CI-equivalent memory shard 166 passed + 27 subtests / 4 warnings, py_compile와
  scoped diff-check PASS다. 최종 Python 3.12 전체 회귀는 881 passed / 1 skipped /
  738 subtests / 7 warnings (45.92s), offline checkpoint와 독립 최종 검토도
  PASS다. native SQLite call은 즉시 interrupt되지 않으며 deadline
  뒤 tracked worker가 남을 수 있다. offline synthetic temp DB만 사용했고 설치
  AIRI·서비스·모델·runtime DB 변경은 없으며 STT/mic은 OFF/deferred다. 상세:
  `완료/AIRI-MEMORY-RETRIEVAL-SHUTDOWN-DRAIN-2026-08-13.md`.
  단, post-push run `31653832303`은 11 jobs PASS / 2 FAIL이다. memory shard는
  165 passed 뒤 extraction/background store 경로에서 동일 `WinError 32`가
  재현됐고 ASAR preflight synthetic drift는 accessible-process identity 선행
  거부로 실패했다. 따라서 이 branch는 handoff checkpoint이며 PR/merge ready가
  아니다. 검토 PC는 전체 store/extraction physical thread lifecycle을 보완하고
  full-green workflow를 새로 확보해야 한다.

- **2026-08-13** (dev PC, source ASAR read-only preflight): 고정 evidence
  SHA와 후보/current ASAR·설치 exe·fuse·unpacked manifest·3개 patch layer를
  strict type/path/file-identity/final-drift로 재검증하는 비변경 사전점검과
  합성 계약 시험을 checkpoint에 추가했다. 실경로 호출은 설치 AIRI 프로세스
  7개를 감지해 fail-closed 거부했다. 프로세스 종료·설치 파일 변경은 없었고,
  install 승인/runtime TTS·text→render/portable·Godot은 계속 미완료다. 설치 시
  installer가 digest를 재검증하고 mutex·launch barrier를 획득해야 한다.

- **2026-08-13** (TTS source ASAR candidate): 고정 source `bf173f2` / tree
  `ff71039c`에서 1,131,077,260-byte 후보 ASAR를 생성했다. SHA-256
  `6767625E...9BCED`, package 0.11.3, 28,167 entries와 critical payload를
  검증했고, 후보/설치본의 135-file unpacked path·size·hash가 모두 일치한다.
  candidate/installed executable의 ASAR 관련 fuse도 동일·disabled다. outer
  electron-builder는 후보 생성 뒤 winCodeSign symlink 권한에서 실패했으므로 full
  portable build PASS를 주장하지 않는다. 설치본은 `1B68AE...B0`로 그대로이며
  install/runtime duration/pitch는 issue #2 승인 게이트 뒤 남는다. 상세:
  `완료/AIRI-TTS-ASAR-CANDIDATE-BUILD-2026-08-13.md` 및
  `evidence/AIRI-TTS-ASAR-CANDIDATE-BUILD-2026-08-13.json`.

- **2026-08-13** (source ASAR deployment safety): source-built-ASAR install,
  automatic rollback, and explicit restore scripts completed their synthetic
  >1 MiB test path. They require artifact/current/backup SHA-256 checks,
  bounded critical-payload ASAR validation, no-reparse/hard-link checks,
  fail-closed AIRI process handling plus an exclusive launch barrier,
  per-target Global mutex, exact displaced-file backups, atomic replace,
  rollback, and idempotency. The full validator passed the actual installed
  ASAR read-only at SHA-256 `1B68AE...B0`; it was not stopped or modified. This does not
  complete an installation or runtime TTS duration/pitch verification.
  [GitHub issue #2](https://github.com/kkp8121-rgb/airi-local-stack/issues/2)
  remains the authorization/tracking gate. Detail:
  `완료/AIRI-SOURCE-ASAR-DEPLOY-SAFETY-2026-08-13.md`.

- **2026-08-13** (B4a chat priority policy): `broadcast-director/priority-policy.mjs`에 B1 screened event를 동결된 `{priority}` 또는 invalid `null`로 분류하는 무상태 결정론적 정책을 추가했다. 질문 > 화제 확장 > 진심 리액션 > 응원 > 긍정 fallback 순서이며 strict shape/ID/Unicode code point/timestamp·descriptor snapshot을 검증한다. V8 legacy RegExp 보존 위험을 피하기 위해 개인정보 매처는 RegExp 없이 수동 문자열 처리만 사용하고 sentinel 회귀가 비변경을 확인한다. Korean-first 휴리스틱의 오분류는 순서만 바꾸며 B3 모더레이션을 대체하지 않는다. 로컬 broadcast 집중 시험은 24/24 PASS, 독립 combined ingress/policy/director 검토는 36/36 PASS다. B4a/G5/M4는 partial이며 B4b 런타임과 외부·인간 게이트는 남는다. 상세: `완료/AIRI-B4A-CHAT-PRIORITY-POLICY-2026-08-13.md`.

- **2026-08-13** (B4a broadcast-director foundation): Node built-ins-only,
  default-OFF/inert 오프라인 코어를 추가했다. caller monotonic `nowMs`를 쓰는
  20분×6 블록, 정확한 12초 질문 대기·3:2 closed/open cycle, 침묵 사다리,
  B1 screened event 우선순위/유실 없는 bounded backpressure, 이름만의 후원 ACK,
  opaque approved-topic lease, pause/kill/replay/frozen output 계약을 포함한다.
  집중 테스트 17 PASS와 독립 최종 검토 PASS는 compressed deterministic simulation
  범위뿐이다. 실제 2시간 방송·무오디오 공백·YouTube 지연/쿼터/OAuth·런타임
  adapter·AIRI/TTS/OBS·외부 killswitch·실제 moderation·설치 ASAR 변경은 증명하지
  않는다. G5/B4와 M4는 partial이며 B4b와 승인 비공개 리허설이 남고 STT는
  OFF/deferred다. 상세: `완료/AIRI-B4A-BROADCAST-DIRECTOR-FOUNDATION-2026-08-13.md`.

- **2026-08-13** (I2a viewer-memory foundation): default-inert, separate
  SQLite storage and the content-free B1 observation boundary were added.
  Strict `broadcast:v1` pseudonyms, manual tier caps, five-name history,
  explicit typed facts (90-day maximum), 730-day event dedup retention,
  365-day inactive pruning, deletion, count-only donations, and untrusted
  callback candidates are covered by focused JS 17 and Python unittest 19
  PASS. The CI-equivalent 44-path Python 3.12 matrix also passed 877 tests,
  skipped 1, and passed 723 subtests with 7 warnings. No B1b/OAuth/live
  adapter, AIRI injection, model parsing/prompt,
  renderer, or runtime DB/launcher wiring was added; I2 remains partial until
  an authorized next-broadcast callback smoke. Detail:
  `완료/AIRI-I2A-VIEWER-MEMORY-FOUNDATION-2026-08-13.md`.

- **2026-08-13** (dev PC, TTS PCM sample-rate hardening): 이미 동작하던
  progressive WAV 경로가 32 kHz PCM을 output rate에 맞추지 않던 결함을 수정했다.
  chunk-safe mono/stereo resampler, 실제 worklet의 lossless bounded backpressure,
  pre-roll/terminal flush, abort waiter 해제, streaming body 비보관을 추가했다.
  focused Stage UI 28 tests, Stage UI·Tamagotchi typecheck, Electron production
  build와 3층 apply/reverse가 PASS했다. layer-3는 130,974 bytes, SHA-256
  `CC172A16281E56DC03E6A6F261B5531367711C0393D57E171C932EA8544C5E3E`다.
  설치본은 변경하지 않았으므로 실제 duration/pitch 회귀가 다음 게이트다. 상세:
  `완료/AIRI-TTS-PCM-SAMPLE-RATE-HARDENING-2026-08-13.md`.

- **2026-08-13** (dev PC, production-context source binding v2): 실제 proxy
  context shaping을 0/8/20/48 압력×3회 재측정했다. generic structured-output
  계약은 언어·문체 문단만 제거하고 character-state·knowledge 근거를 보존하며,
  source-oriented field와 swapped/reordered anti-overfit 회귀를 통과했다. 구조는
  PASS, 7개 필드 중 6개는 12/12지만 `dialogue_marker`는 memory marker
  `silver-fern`을 12/12 복사해 semantic/gate/authoritative 결과가 FAIL이다.
  prompt tuning은 여기서 중단하고 default 2048·extraction OFF를 유지한다.
  Python 3.12.13 전체 matrix는 **858 passed / 1 skipped / 708 subtests /
  7 warnings** PASS, checkpoint·Node는 27/27 PASS다. `f4c765f`의 push run
  `31623362906`과 PR run `31623367654`도 모두 PASS했다. 상세:
  `완료/AIRI-PRODUCTION-CONTEXT-CONTINUITY-GATE-2026-08-13.md`.

- **2026-08-13** (dev PC, context window SSoT/4096 triage): root
  `-NumCtx`/비공백 `AIRI_NUM_CTX`를 strict 512..32768(기본 2048)로 모든 proxy
  child·verify-only·warmup·health 재사용에 배선했다. invalid env는 서비스 작업 전,
  live 2048 재사용에 4096 요청은 health mismatch로 fail-closed다. `/health.prompt_budget`
  은 prompt 원문 없는 terminal-sampled 숫자 telemetry다. raw Mi:dm 4096은
  complete/schema 12/12, retry 0이지만 exact/card/부정 0/12 FAIL; 초기 사용자
  물리 절단만 해소했다. GPU paired/live 최소 여유 543 MiB도 승격 근거가 아니다.
  따라서 관측성은 완료, 품질 remediation은 계속 FAIL이고 운영 기본값 2048을 유지한다.
  current Python 3.12 41-path matrix는 **833 passed / 1 skipped / 708 subtests /
  7 warnings** (64.98s) PASS이며, proxy full은 286 passed / 377 subtests / 5 warnings
  (2.23s), API shard는 323 passed / 569 subtests다. historical 829는 base `aef5300`에만
  해당한다.
  다음 조건은 production-path deterministic context gate, holdout/continuity ledger
  또는 더 나은 모델, 인간 100건 검수다. 상세:
  `완료/AIRI-CONTEXT-WINDOW-SSOT-AND-4096-TRIAGE-2026-08-13.md`.

- **2026-08-13** (dev PC, I1 Kanana 공식 원본 후보): Kakao 공식 commit
  `6a5d7889964c4c590299d16e309eabab1f73f8a9`의 BF16 shard 해시를 검증하고,
  llama.cpp `b10375` 고정 source/tool로 프로젝트 자체 BF16→Q4_K_M GGUF를
  생성하고 manifest→model blob 해시까지 고정했다. 격리
  11436 CPU의 `kanana-airi-extraction:3b-q4_k_m` smoke는 schema/connectivity
  PASS지만 recall 0, coverage 0, unexpected 1, op/alias 0, total 24,715.938 ms로
  fail-fast FAIL해 full을 생략했다. extraction은 off, MEM-04 활성 추출 실측은
  계속 대기한다. 상세:
  `완료/AIRI-KANANA-EXTRACTION-CANDIDATE-GATE-2026-08-13.md`.
  공개 방송은 Kanana License §2.2/§3.1/§4.1/§4.2의 법률/Kakao 확인 전
  미승격이며 표시·Notice만으로 충분하다고 보지 않는다.
  같은 계열의 historical base `aef5300` CI 41경로는 829 passed / 1 skipped /
  706 subtests였고, 현 배치 Python 3.12 41경로는 **833 passed / 1 skipped /
  708 subtests / 7 warnings** (64.98s) PASS다. proxy full은 286 passed / 377
  subtests / 5 warnings (2.23s), API shard는 323 passed / 569 subtests다. checkpoint·Node 27/27·patch
  manifest도 PASS했다.

- **2026-08-12** (dev PC, 사용자 결정): 기본 방송 프로파일을 chat/text 입력 +
  STT OFF로 고정했고 Electron 마이크 토글도 OFF로 둔다. `-Stt off` 런처 재실행은
  `STTMode=off`, `STT=disabled`, 빈 STT model/device, `8890` 부재와
  `8880/11434/11435` listener 및 proxy health `ok`를 확인했다. repo-path 일치
  STT PID 16220/26220 종료 뒤 GPU paired average는 7786.4→6742.4 MiB
  (관측 차이 1044 MiB)였으나, 동시 무관 GPU 작업이 있어 formal clean B0 capacity
  proof는 아니다. 상세: `완료/AIRI-STT-OFF-BROADCAST-PROFILE-2026-08-12.md`.

- **2026-08-12** (dev PC, I1 신규 후보, 당시 상태): 11436 격리 CPU에서 Qwen3.5 4B
  Q4_K_M과 Granite 4.0 3B smoke는 첫 행 fail-fast FAIL, Gemma3 4B는 smoke
  PASS 뒤 full 7-row balanced FAIL(독립 verifier 거부)했다. 셋 다 설치된 로컬
  후보일 뿐 운영 모델이 아니며 extraction은 off다. 당시 Kanana-2-3B는 공식 BF16 원본 직접 변환
  provenance 및 Kanana Open License broadcast/attribution 검토 전 보류했고,
  제3자 pull CLI 중단 뒤 설치가 완료된 tag도 load·측정하지 않았다. 상태값은 변하지 않는다.
- **2026-08-12** (dev PC): 당시 tip의 CI `python-core-tests` matrix 41개
  추적 경로를 같은 `requirements-ci.txt` 환경에서 재실행해
  **825 passed / 1 skipped / 706 subtests**를 확인했다(2026-08-13 `aef5300`
  재검증은 829/1/706). 기억 기술 레퍼런스의
  “Mi:dm 추출 미측정”을 실측 balanced FAIL로 고치고, C1 사용자 방향 결정과
  헌법 최종 인간 승인을 분리했다. 로드맵 상태값은 변하지 않는다.
- **2026-08-12** (dev PC): 공개 합성 장문 context·memory·card 하네스를
  추가하고 `num_ctx=2048`에서 EXAONE/Mi:dm을 4압력×3회 실측했다. exact는
  EXAONE 3/12, Mi:dm 0/12로 양 모델 FAIL. Mi:dm은 같은 무압력 입력도
  1,139 token(EXAONE 756)을 사용했고 20 filler쌍에서 2,042 token으로
  포화됐다. 최신 정정·tail memory는 양 모델 12/12 보존했다.

- **2026-08-12** (dev PC, 사용자 청취·결정 반영): T-05는 126번을 한국어
  예비 후보로 보존하되 낭독조·감정 부족 때문에 운영 승격하지 않고 현행
  일본어 참조 음성을 유지한다. 정식 팬덤명은 만들지 않고 일반 호칭
  “시청자들”만 쓰며, 방송에서 자연 발생 호칭이 쌓인 뒤 재검토한다. 실제
  마이크 실측은 사용자 요청으로 추후 보류했다.

- **2026-08-12** (dev PC, 당시 상태): 팬덤명 “아이리스” 공개 충돌 검토 FAIL.
  Hololive `IRyS`, 국내 인터넷 방송인 `@anyiris`, K-pop `IRRIS (아이리스)`와
  같은 엔터테인먼트 검색면에서 충돌하고 과거 한예슬 팬클럽의 정확 명칭
  선사용도 확인했다. AIRI 캐릭터명은 유지하고 당시 팬덤명만 사용자
  재선정으로 되돌렸다(`완료/AIRI-FANDOM-NAME-COLLISION-CHECK-2026-08-12.md`).

- **2026-08-12** (dev PC): 동일 설치 Electron·warm TTS에서 모델 순서를
  Mi:dm→EXAONE→Mi:dm→EXAONE으로 교차하고 모델별 n=10의 matched
  text→render A/B를 완료했다. Mi:dm first substantive render는 P50
  1,501.5ms/P95 2,597.2ms, EXAONE은 1,752.5/3,233.0ms였다. 작은 표본과
  TTS 분산 때문에 지연 gate 완료 근거로만 사용하며 품질 우위로 해석하지 않는다.

- **2026-08-12** (dev PC): B3 3종 배선과 설치 Electron 가시 배지를 완료
  (3층 source test/typecheck/build 신규 검증 포함). B0-2는 VRAM
  6,084/6,131/6,289MiB·최소 여유 1,736MiB에서 실제 NVENC H.264 1080p60,
  B0-3는 x264 1080p30 veryfast CPU 평균 44.8%·최대 70%·정상 5,346 frames를
  확인했다. cloud streaming 하네스·테스트와 T-05 라이선스 확인 후보 3종은
  준비 완료이나 당시 live TTFT는 API key·외부 승인, T-05는 사용자 청취
  검토 대기였다.

- **2026-08-12** (dev PC): 필수 실기 1차 배치 — 설치 Electron의 stale
  EXAONE tag→Mi:dm 정규화, foreground 단일 runner, evaluator/eval provenance,
  EXAONE 롤백, digest 일치/불일치 fail-closed를 검증하고 Mi:dm 실측 digest를
  운영 런처 기본 pin으로 고정. I1 Mi:dm balanced 7-fixture는 품질 기준 FAIL로
  추출 off 유지. B3는 TTS 폴백 5종을 기존 ACK 2종과 함께 7/7 preload하고
  moderation launcher env를 fail-closed로 배선.

- **2026-08-12** (검토 PC): CI job 타임아웃 해소 — `d13c27c` run에서
  ollama-proxy-model shard가 10분 cap에 정확히 잘림(저하 runner + 5s
  busy_timeout 기준 bounded-wait 테스트의 고정 대기). ① bounded-wait
  테스트를 테스트 전용 400ms timeout으로 패치(의미 동일, 고정 5s+ 제거,
  76 passed 32s→25s) ② 최중량 test_airi_memory.py를 전용 shard로 분할
  (10분 계약 유지, manifest 자동 대조 PASS). 상태값 변화 없음.
- **2026-08-12** (검토 PC): CI 저하 runner 견고성 수정 2건 — ① MEM-04
  busy_timeout 500→5000ms (저하 runner에서 8-thread 락 실패 재발. 당초
  500ms가 sqlite3 기본 5s 예산을 축소한 회귀였음 — WAL 유지, 상한 복원)
  ② tail matcher 성능 가드 0.15→0.6s (저하 runner 실측 0.38s 오탐 —
  알고리즘 회귀는 초 단위라 가드 가치 유지). 상태값 변화 없음.
- **2026-08-12** (검토 PC): 메타 서사 호칭 변경 "주인님"→"사장님" (사용자
  재결정 — 하드웨어 자학 개그를 1인 방송국·노동 개그로 확장 가능한 구도).
  헌법 §5·§6 확정 문구, 계획 §4, 인수인계, 색인 일괄 교체. 과거 로그의
  "주인님" 표기는 당시 기록으로 보존.
- **2026-08-12** (검토 PC): 캐릭터 문구 확정 — 시그니처 인사(메타 개그형
  C안)·팬덤명 "아이리스"·클로징(메타 개그형 신규 제작) 사용자 선택 완료.
  헌법 §6 확정본 반영, 미채택 후보는 밈 시드 풀로 보존. 남은 것: T-05
  샘플 검토·아이리스 실존 충돌 확인(웹 검색 예산 소진으로 미수행)·인간
  검수.
- **2026-08-12** (검토 PC, 당시 상태): 사용자 결정 5건 처리 — 결정 1(AI 단독형+메타
  서사 "주인님") 확정, 결정 2 조건부(dev PC 실측 2종 후 재결정), 결정 3
  부분 확정(이름 AIRI·호칭 확정, 인사·팬덤명 선택 대기), 결정 4 확정(조건
  기반 M3→리허설→데뷔), 결정 5 확정(재정의 제안 기각, §12 원문 유지).
  문서만 반영, 코드 변경 없음.
- **2026-08-12** (검토 PC): CI flaky 수정 — I1 신규 테스트
  `test_extraction_triggers_coalesce_to_one_session_worker`의 shutdown
  flush 상한 2s→20s (cold 실행에서 드레인 미완으로 1/10 간헐 실패,
  `45a26a4` CI 실패 원인. 상한 의미라 통과 케이스 비용 불변). 상태값
  변화 없음.
- **2026-08-12** (검토 PC): 현황판을 체크리스트 형식으로 개편 (사용자
  요청 — `[x]`/`[~]`/`[ ]` + 완료 일자 병기). 상태값 변화 없음.
- **2026-08-12** (`802bb82`, 검토 PC): 현행성 문서 12종 전수 실측 검토 —
  stale 20여 건 수정(사전 키 `blocked_dialogue` 교정, `AIRI_LLM_MODE`→
  `AIRI_CHAT_PROVIDER`+`AIRI_ALLOW_EXTERNAL_CHAT`, 프롬프트 751/949자
  혼동 등), 정확 확인 39건.
- **2026-08-12** (`f405d74`, 검토 PC): 로드맵 방향 문서 3종 모델 중립
  개정 + 2종 개명. 성장 전략 결정 1은 Mi:dm 전환으로 대체, 결정 5는
  Mi:dm(MIT)으로 해소. 원본 3종 아카이브 보존.
- **2026-08-12** (`41b1c20`, 검토 PC): 현황판 신설. 검토 PC 선행 배치
  반영 — 모델 SSoT 게이트 4종 코드 해소, I1 추출 배선(발효 대기),
  MEM-04 WAL, B3 모더레이션 코드 완료(M3 일부 선행), C1 헌법 초안.
- **2026-08-13** (최신 사용자 결정·읽기 전용 continuation audit): §2 로컬 실기 배치는 완료다. push/CI green은 완료 조건이 아니며 저장소는 private 유지·public visibility 변경 없음, 사용자가 요청할 때까지 push하지 않는다. historical Actions billing run `31673311636`과 `31673428754`는 각각 13 jobs 모두 `runner_id=0`/steps 0으로 runner 배정 전 실패한 사실을 보존한다. §3의 승인된 기존 extraction 후보(Mi:dm 포함)는 모두 FAIL이고 verifier는 `EXTRACTION_GATE_GATE_NOT_PASSED`; 11436·runner 없음·extraction OFF를 유지하며 새 full balanced PASS 전에는 failed weight를 **extraction runner에서** 재실행하거나 extraction을 활성화하면 안 된다. 동일 weight의 격리 foreground-chat A/B는 새 G3 계획에 따라 허용하며 extraction 결과와 분리한다. §4 구현은 완료: 설치 ASAR SHA-256 `1B68AE5ECB9DB998002AC7268DE707661EC0C81FC4BD90836F3C3E25719B88B0`, live TTS cache 7/7, 기본 moderation OFF이며 중복 재시작은 하지 않는다. §9-b는 126번 예비 보존·현행 일본어 음성 유지·STT/mic 보류로 완료다. cloud call은 명시적 전송·지출·모델 승인이 필요하고, B0-1은 YouTube OAuth/quota가 필요하다.

- **2026-08-13** (production context v2): generic structured-output 계약으로 spoken style 충돌을 제거하고 source-oriented fields, 답 canary가 없는 질문, swapped/reordered anti-overfit test를 적용했다. 구조 변환 PASS, 7개 필드 중 6개 12/12이며 두 continuity color는 v1보다 개선됐지만 `dialogue_marker` 0/12가 memory marker `silver-fern`을 결정적으로 복사해 semantic/gate/authoritative는 FAIL이다. dialogue-vs-memory는 모델 한계로 결론냈고 prompt tuning을 계속하지 않는다. default `num_ctx=2048`·extraction OFF를 유지한다.

- **2026-08-13** (latency dashboard KPI): 상단 대시보드의 기존 raw
  `playback.start` 집계가 heuristic/mixed 행을 포함해 상단은 통과로 보이는
  반면 per-turn 행은 heuristic 포함 및 substantive KPI 보류를 정확히 표시하는
  모순이 가능했던 점을 수정했다. fixed `/dashboard-metrics.mjs`의
  pure 집계는 non-synthetic cloud-search, explicit STT/LLM/playback,
  유한 `vadEndWaitMs >= 0`, `stt.start <= llm.content <=
  kpi.substantive_playback_start`, 유한 nonnegative 결과만 허용한다.
  newest-five/P50/P95/worst/pass는 substantive KPI만 사용하며 raw scalar는
  진단용이다. Node 5/5, latency Python 32 passed + 15 subtests, checkpoint,
  independent review 모두 PASS이며, 별도 Python 3.12 전체 명령
  `python -m pytest -q ollama-proxy test_latency_trace.py
  test_start_airi_background.py latency-monitor stt`도 875 passed / 1 skipped /
  738 subtests / 7 warnings (49.88s) PASS다. live mic/runtime 실측은 없고 STT는
  OFF/deferred, 설치 AIRI·서비스·모델은 변경하지 않았으며 물리적 5-turn
  gate는 닫지 않았다. 상세:
  `완료/AIRI-LATENCY-DASHBOARD-SUBSTANTIVE-KPI-2026-08-13.md`.

- **2026-08-14** (dev PC, local LLM P0–P7 actual A/B): 여섯 후보 exact HF
  revision/manifest를 고정하고 실행 가능한 다섯 common Q4와 Mi:dm/Granite native
  bounded-offload를 한 번에 하나씩 실측했다. P2/P3/P4, common P5 120-turn,
  P6 20-turn review packet, common P7 Electron→GPT-SoVITS→Windows render n=10을
  완료했다. Motif는 pinned license file 부재·remote code·8 GB safe quant 부재로
  UNRUNNABLE이며 다른 후보는 계속 실행했다. common 첫 render P50/P95는
  Mi:dm 1.762/2.489초, Ministral 2.347/4.589초, Qwen3 9.148/9.575초,
  Phi 1.842/3.740초, Granite 1.694/3.158초다. 모호성·근거·불확실성·무조건 동의
  12-scene 리허설은 Qwen 8, Phi/Ministral 7, Mi:dm 6, Granite 5였지만 Qwen은
  P50 30.020초와 빈 응답으로 foreground 부적합이다. 운영 Mi:dm 유지,
  Phi/Ministral 인간 검수 challenger, 인간 packet 대기. 설치 ASAR 불변,
  STT/extraction/moderation OFF. 상세:
  `진행중/AIRI-LOCAL-LLM-CANDIDATE-AB-RESULT-2026-08-14.md`.

- **2026-08-14 (Motif actual-status correction and closeout):** This supplements
  the prior planning/unavailable record without rewriting history. Motif exact
  revision `70bf316e166f2a256b1068e35c8310541a6a06bc` had official F32 shards
  fully downloaded and hash-verified; audited remote code then ran offline.
  Native BF16+CPU offload actually completed P1/P2/P3/P4/P6. The experimental,
  localhost-only Transformers+bitsandbytes NF4 backend (explicitly not
  Ollama-native) actually completed common P1/P2/P4/P5/P6/intelligence/P7.
  Native/common P2 were 0/16 and 1/16. Common P3 explicitly does not support
  JSON-schema and returned HTTP 400. Common P5 was 80/120 with TTFT about 8.02 s;
  intelligence was 4/12 (clarify 0/2, unknown 0); P7 render P50 was about 9.22 s.
  Result: not recommended. The pinned LICENSE file remains absent: evaluation
  exception only, with no public or revenue deployment approval.

  - [x] Exact revision, official F32 shard hashes, and remote-code audit recorded
    — 2026-08-14
  - [x] Native and local-NF4 actual evaluation paths recorded — 2026-08-14
  - [x] Operational baseline restored: Mi:dm exact digest; STT, extraction, and
    moderation OFF; no loaded runner; installed ASAR unchanged — 2026-08-14
  - [ ] Public/revenue Motif deployment approval (blocked: pinned LICENSE file absent)

- **2026-08-14 (Mi:dm–Motif native clean rerun checkpoint):** 기존 Motif 비교는 단일
  EOS 방법론 오류와 이전 대화에서 유래한 fixture 우려 때문에 역사 기록으로만 보존하고,
  비교 결론에서는 대체한다. 새 일반 합성 방송 16건을 native 경로에서 재실행했으며
  메시지 해시는 64/64 일치했고, `hf_card` 1회 및 `broadcast_equal` 3회 profile에서
  TTFT/총 시간/tok/s를 기록했다. equal-profile 핵심 수치는 Mi:dm TTFT
  P50/P95 `0.156/0.157s`, 총 시간 `2.657/8.391s`, `13.973 tok/s`; Motif는
  `0.203/0.219s`, `12.493/24.516s`, `5.227 tok/s`다. 품질은 인간 검수 대기이며,
  Mi:dm은 운영 기준을 유지하고 Motif는 배포 차단을 유지한다. 상세:
  `진행중/AIRI-MIDM-MOTIF-NATIVE-BROADCAST-RERUN-2026-08-14.md`.
  - [x] native rehearsal 및 Motif dual-EOS 집중 회귀: 28 PASS, 1 skip
  - [x] eval unittest discovery: 135 PASS, 1 skip
  - [x] Python 3.12 core pytest: 999 PASS, 2 skip, 869 subtests PASS
  - [x] sender Node 계약: 32 PASS
  - [x] six-manifest complete-set 및 current checkpoint: PASS
  - [x] Mi:dm exact digest, local provider, `num_ctx=2048`, STT/extraction/moderation
    OFF, Ollama temporary runner 없음으로 복원
  - [x] Actions run `31775348398`: 13개 job 모두 step 0, 로그 없이 실패. 기존 결제
    차단 상태로 기록하고 로컬 전체 suite/checkpoint/manifest를 검증 근거로 사용
