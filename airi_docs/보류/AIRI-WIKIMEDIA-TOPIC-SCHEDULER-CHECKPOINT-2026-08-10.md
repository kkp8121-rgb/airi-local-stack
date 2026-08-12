# AIRI Wikimedia raw scheduler checkpoint — 2026-08-10

## Outcome

The guarded Wikimedia adapter can now be run periodically by a separate,
explicitly enabled foreground scheduler. The scheduler is not imported or
started by AIRI, the proxy, or either local-stack launcher. It remains outside
the human curation, approval, compiler, and runtime-board boundaries.

No real policy, contact address, raw evidence, cache, curation, decision, or
runtime board is included or activated.

## Runtime contract

- The exact `--enable-wikimedia-schedule` flag is required before argument
  parsing, path inspection, lock acquisition, clock reads, sleep, network, or
  file writes.
- Every enabled cycle calls only the existing policy-bound Wikimedia raw
  adapter. Its return value must be exactly non-negative `raw_count` and
  `added_count`, with `added_count <= raw_count`.
- Calls are serial and completion-based. A collection cannot overlap the next
  cycle in the same process.
- The default successful interval is six hours. Rejected cycles wait 15
  minutes. Explicit values remain bounded to 15 minutes–24 hours and 1–60
  minutes respectively.
- A topic-review-local ownership sidecar is held for the entire process
  lifetime. A concurrent scheduler for the same review root fails closed.
- `KeyboardInterrupt` removes the owned sidecar and returns a content-free
  stopped state. A crash may leave a stale ignored sidecar; the tool never
  guesses that it is safe to reclaim.

## Observability and isolation

The only scheduler output shapes are one-field JSON objects whose status is
`disabled`, `complete`, `rejected`, or `stopped`. They contain no topic text,
URL, path, policy or topic ID, contact, exception, reviewer, or session data.

The scheduler has no state file and cannot write pending topics, decisions,
compiled boards, databases, prompts, speech, memory, or approvals. A rejected
cycle retries without weakening any adapter validation.

## Verification

Synthetic tests cover the inert OFF path, exact adapter argument forwarding,
strict interval bounds, single ownership, serial success/failure cycles,
bounded retry scheduling, malformed collector results, content-free output,
and absence of persistent scheduler state. They inject the collector, clock,
and sleep functions; they make no network, service, or model call.
