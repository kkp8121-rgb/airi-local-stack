---
schema_version: 1
updated_at_kst: "2026-08-22 15:30:26 +09:00"
checkpoint_id: "20260822-1530-receipt-doc-validation"
goal_status: "active"
authorization: "repo-gpu-package-test-commit-push; operational-adoption-forbidden"
active_phase: "milestone-1-documentation-durability-audit"
git_head: "e822f9f120e27e561d2e90353da4ba8315e4e3dd"
worktree_state: "dirty-working-state-after-successful-push"
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
- 2026-08-22 15:09 KST 재확인: Python 학습 프로세스와 trainer 0.
- v4 파인튜닝은 E1 adapter/report까지만 완료·검증됐고 아직 미채택이다.
- E2 adapter/report, merge/package, v4 T3, live campaign 산출물은 0이다.
- HEAD는 `0c0ffbe6a90e2ddbb911c1ca17d470f367ee9ddd`이고 worktree는 기존 문서
  지속성 배치 9 modified + 2 untracked이며 아직 commit/push하지 않았다.

## 2. 현재 작업 트랜잭션

| 항목 | 값 |
|---|---|
| 의도 | 첫 문서·지속성 milestone push receipt를 장기 SSoT 5종에 기록하고 receipt commit/push 후 P0 구현으로 전환 |
| 허용 범위 | 이 milestone은 저장소 문서·오프라인 계약 테스트·Git commit/push만 수행; GPU·서비스·E2는 P0 구현·실증 전 실행 금지 |
| 시작 전 증거 | goal `active`; HEAD `0c0ffbe`; 9 modified + 2 untracked; trainer 0; corpus/base/E1 SHA exact; E2와 후속 산출물 0 |
| exact 명령 | `.\test-airi-work-continuity.ps1`; `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'`; `git add -- airi_docs/AIRI-CURRENT-DOCS-INDEX-2026-08-10.md airi_docs/로드맵/AIRI-ROADMAP-LOG.md airi_docs/로드맵/AIRI-ROADMAP-STATUS.md airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-08-21.md airi_docs/진행중/AIRI-WORKING-STATE.md`; `git commit -m "docs: record continuity milestone receipt"`; `git push origin main` |
| 출력 경로 | SSoT receipt 문서 5개만 Git에 반영; 모델·로그·런타임 산출물 생성 0 |
| 완료 조건 | receipt 문서 focused/diff-check PASS, receipt commit이 origin/main과 일치, worktree clean |
| 중단·복구 | commit/push 실패 시 e822f9f 본체 push는 완료 상태로 보존하고 receipt 문서만 재개 |
| 현재 행동 | 5-file receipt focused/diff-check PASS — exact receipt commit/push 실행 |

## 3. 마지막 내구성 체크포인트

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

1. active/P0-before-E2 계약과 continuity 회귀를 정정한다.
2. focused/full offline 검증과 diff·금지 데이터 검토 후 첫 milestone을 commit/push한다.
3. receipt와 clean push를 확인한 뒤 P0 checkpoint/resume/durable runner/safe-pause
   구현으로 이동한다. P0 실증 전에는 E2를 시작하지 않는다.

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
