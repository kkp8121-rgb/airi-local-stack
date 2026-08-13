# AIRI memory retrieval shutdown drain — 2026-08-13

## Scope and result

The memory-retrieval lifecycle gap found during the PR #7 push CI was fixed on
branch `fix/memory-retrieval-shutdown-drain-2026-08-13`. Do not infer a fixed
commit hash from this record: inspect the current branch tip with `git log -1`.

The first memory-shard attempt reported **159 passed**, then failed while its
teardown removed `memory.db` with Windows `WinError 32`. The same PR's memory
shard retry and the subsequent main CI passed. This is timing-sensitive, but it
is a real lifecycle gap rather than a harmless CI-only result.

## Cause and change

`wait_for(to_thread(...))` could time out while the physical SQLite worker
thread continued to run without being tracked. Teardown could therefore race
that worker's still-open database handle.

The retrieval path now uses a shielded, tracked task and a cooperative cancel
event. Timeout and caller cancellation both signal that event; task completion
cleans up tracking and consumes errors. Shutdown signals active work early and
awaits it within the already-configured shutdown deadline. While stopping,
retrieval requests are rejected as failed.

Admission is bounded by `AIRI_MEMORY_MAX_CONCURRENT_RETRIEVALS` (positive
environment value; default **8**). Saturation fails soft instead of putting
work into an unbounded executor queue.

## Verification

- Focused `memory_runtime` suite: **62 passed**.
- CI-equivalent memory shard: **166 passed + 27 subtests, 4 warnings**.
- Full Python 3.12 regression: **881 passed, 1 skipped, 738 subtests,
  7 warnings (45.92s)**.
- Offline checkpoint and independent final review: **PASS**.
- `py_compile` and scoped `git diff --check`: **PASS**.

The earlier 10x lifecycle-regression runs predate the admission cap; they are
not claimed as verification of the final bounded-admission behavior.

## Limits and non-claims

Cooperative cancellation cannot instantly interrupt a native SQLite call.
Shutdown waits only for the existing configured deadline and may return with a
worker still tracked if that worker cannot cooperate before the deadline.

All verification used offline synthetic temporary databases. No installed AIRI,
service, model, or runtime database was mutated. STT and microphone work remain
OFF/deferred. This evidence does not enable extraction, demonstrate active
extractor lock contention, or change any installed ASAR.

## Post-push CI status

Push run `31653832303` for commit `b369195` completed **FAIL** with 11 jobs
successful and 2 failed. `offline-contracts` failed because the ASAR preflight
synthetic drift case encountered an accessible-process identity refusal before
its expected drift assertion. The memory shard reached **165 passed** and then
`test_threshold_and_idempotency` teardown again hit Windows `WinError 32` on
`memory.db`.

The second failure is outside the retrieval-task set fixed in this batch: that
test schedules extraction/background store work. It proves that the broader
`asyncio.to_thread` store/extraction shutdown lifecycle still needs review.
Therefore this branch is a handoff checkpoint, **not PR/merge ready evidence**,
despite the green local suites and retrieval-specific independent review.

## Review-PC next action

Fetch `fix/memory-retrieval-shutdown-drain-2026-08-13` and inspect its branch
tip plus run `31653832303`. Audit and deterministically test physical executor
work from extraction/background store calls before opening a PR; then rerun the
full workflow and require every job to pass. Do not alter the installed ASAR.

## 후속 반영 (검토 PC, 2026-08-13)

위 next action을 수행해 두 실패를 모두 근본 해소했다.

1. **store/extraction lifecycle**: `to_thread` 사용 30지점 전수 감사 —
   retrieval(기추적)·embedder 로드(DB 핸들 없음, 의도적 미추적)를 제외한
   26지점을 `_store_call()`(추적 task + shield + done callback 해제 + 늦은
   예외 소비)로 통일하고, shutdown이 `_store_workers`를 별도 window
   (`shutdown_flush_timeout_ms` 크기, 새 env 없음) 안에서 drain하도록 했다.
   재현 테스트 2종을 수정 전 상태에서 먼저 실행해 실패를 확인(타이밍 운이
   아닌 동작 단언 실패)한 뒤 수정 후 통과를 실측했다. WinError 32의 재발은
   이제 assertion(`_store_workers` 불변식)으로 드러난다.
2. **ASAR preflight 계약 시험**: 실패 메커니즘은 계약 스위트가 실제
   프로세스 테이블을 14회 조회하던 것 — CI의 수명 짧은/열람 불가
   프로세스가 drift 단언 앞에서 fail-closed를 발동시켰다. 운영 스크립트는
   무변경으로 두고 계약 시험이 `EnableTestHooks` 게이트 하의 통제된
   프로세스 테이블(실재 non-AIRI 이미지 — identity 비교 경로 실행 유지)을
   주입하도록 해 실제 조회를 0회로 만들었다. 훅이 운영 경로에서 활성화될
   수 없음(스위치 opt-in·`$env:` 부재)을 정적 단언으로 고정했다.

검증(검토 PC 실측): 전체 스위트 900 passed / 1 skipped / 738 subtests,
`test-current-checkpoint.ps1` PASS, `test-patch-manifest.ps1` PASS,
lifecycle 테스트 세트 10회 반복 안정. 남은 한계: store 호출에는 협력 취소
지점이 없어 drain은 순수 대기이며(최악 shutdown 2×flush window ≈ 6초),
`SQLITE_BUSY` 장기 점유 시 여전히 추적된 worker를 남기고 반환할 수 있다.
이 시점부터 본 브랜치는 PR/merge ready로 판정한다.
