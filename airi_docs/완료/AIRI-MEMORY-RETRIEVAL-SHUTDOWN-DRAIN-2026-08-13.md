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
