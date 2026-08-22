---
schema_version: 1
updated_at_kst: "2026-08-22 17:52:00 +09:00"
checkpoint_id: "20260822-1752-p0a-receipt-doc-validation"
goal_status: "active"
authorization: "repo-gpu-package-test-commit-push; operational-adoption-forbidden"
active_phase: "p0-checkpoint-resume-implementation"
git_head: "6f0c1358d2acd18b828ebc0ae8482a348712c461"
worktree_state: "dirty-p0a-receipt-docs-only"
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

- 2026-08-22 사용자 `/goal` 명령으로 기존 pause가 해제됐고 goal은 `active`다.
- 저장소 구현·수정, GPU 학습, merge/package, 로컬 서비스, T3·campaign 및
  검증된 milestone commit/push가 허가됐다. 운영 모델 채택과 기본 모델 변경은
  별도 사용자 승인 전까지 금지한다.
- 2026-08-22 17:40 KST compact 복구 재확인: Python trainer/durable runner
  프로세스 0. GPU process 목록에도 AIRI trainer/runner workload는 0이다.
- v4 파인튜닝은 E1 adapter/report까지만 완료·검증됐고 아직 미채택이다.
- E2 adapter/report, merge/package, v4 T3, live campaign 산출물은 0이다.
- HEAD와 origin/main은 P0-A 구현 commit
  `6f0c1358d2acd18b828ebc0ae8482a348712c461`로 일치한다. 구현 push 뒤
  AIRI trainer/runner 0이며 이 milestone receipt 문서 갱신만 dirty다.

## 2. 현재 작업 트랜잭션

| 항목 | 값 |
|---|---|
| 의도 | trainer full-state atomic checkpoint/exact resume와 agent-independent runner/safe-pause/reboot recovery의 P0 코드·회귀 구현 |
| 허용 범위 | 저장소 Python/PowerShell/테스트 구현과 offline CPU 회귀만 허용; GPU·서비스·E2 실행 금지 |
| 시작 전 증거 | HEAD=origin/main `e93d552`; live-state 단독 dirty; actual Python trainer 0. trainer SHA `3e6fb394...fa880`, trainer test `e69086b7...ad19e`, background pattern `ef651e44...e2eb`, campaign pattern `431bfb55...0102`, atomic merge pattern `e54207d8...aeb5` |
| exact 명령 | `D:\AIRI-Models\venv-midm-broadcast-qlora-py312\Scripts\python.exe -m pytest -q ollama-proxy/training/tests/test_behavior_training_checkpoint.py ollama-proxy/training/tests/test_train_airi_behavior_lora.py ollama-proxy/training/tests/test_durable_training_runner.py`; root PowerShell contract test와 `python -m py_compile`은 새 파일 확정 뒤 receipt에 exact 기록; 관련 offline checkpoint와 diff-check |
| 출력 경로 | Git: trainer+checkpoint module/tests, Python durable runner, `run-airi-behavior-training-durable.ps1`, `pause-airi-safely.ps1`, root runner contract test. Runtime 설계: `D:\AIRI-Models\airi-broadcast-v4-20260821\runs\e2-seed42\{run-state.json,control,checkpoints,logs}`; final E2 adapter/report 기존 경로 유지 |
| 완료 조건 | optimizer 경계 full-state checkpoint, same-volume fsync/verify/immutable publish+latest/previous, exact pin resume, corrupt latest quarantine/previous fallback, pause ack, durable run-state/PID identity/reboot duplicate 방지, CPU 중단/재개 exact 동등성 회귀 PASS |
| 중단·복구 | 구현 중 quota/PC 중단은 Git diff와 이 intent부터 재개; runner/GPU가 0이므로 런타임 진척 없음. 테스트 실패 시 P0 완료·E2 허용으로 승격하지 않음 |
| 현재 행동 | P0-A 구현 `6f0c1358...c461` origin/main push 완료. SSoT 6종에 actual receipt를 반영해 continuity/diff/security, exact docs commit/push를 완료한 뒤 clean HEAD에서 P0-B controlled GPU intent로 이동한다. E2 금지. |

## 3. 마지막 내구성 체크포인트

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

1. P0-A의 16개 코드·문서 배치에 focused continuity, diff/security 검증을 수행한다.
2. exact 16개만 stage해 `feat: add durable AIRI training recovery`로 commit/push하고
   HEAD=origin/main, clean worktree, 관련 PID 0 receipt를 남긴다.
3. clean HEAD에서 별도 intent를 기록한 뒤 controlled GPU 중단·재개 동등성과 실제
   E2 속도의 checkpoint 손실 상한 10분 이하를 실측·고정한다.
4. P0-B GPU receipt 전에는 E2를 시작하지 않는다.

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
