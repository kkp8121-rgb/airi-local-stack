# AIRI topic workflow status checkpoint - 2026-08-10

## Outcome

The local topic pipeline now has a single read-only, content-free status command
that reports the first incomplete validated boundary from source policy through
the compiled runtime board. It does not activate collection or broadcasting.

## Contract

- `topic_workflow_status.py` is inert unless the exact
  `--inspect-topic-workflow` flag is present.
- The disabled path returns before argument parsing, path resolution, clock
  access, locking, filesystem access, network access, or writes.
- Enabled inspection requires explicit absolute paths for the policy registry,
  raw discoveries, curations, pending records, decisions, and runtime board,
  plus the requested policy ID.
- Every existing artifact is validated by the production policy, raw,
  curation, pending, decision, and runtime loaders. Missing future-stage paths
  remain absent; orphan or partial later artifacts fail closed.
- Output has exactly the fixed status/stage enums and seven bounded counts. It
  never includes paths, IDs, source text, notes, reviewers, hashes, timestamps,
  errors, prompts, or dialogue.
- The compiler and inspector share one pure deterministic runtime-board builder,
  so status compares the current runtime bytes against the exact bytes the
  compiler would produce.
- The compiler and inspector also share the all-items-live predicate. Expired,
  future, reversed, empty, or mixed-live approval sets are never reported as
  compilable.
- `ready` requires a nonempty production-loader result and exact current bytes.
  All-rejected or zero-approved workflows return to `raw_required` without
  inventing a topic.
- Inspection is intentionally lock-free and read-only. Operators should stop
  writers first; a concurrent change is allowed to produce a fail-closed
  rejected snapshot.

## Verification

- Synthetic status tests cover every stage, exact output keys and counts,
  default-OFF dependency isolation, malformed/duplicate arguments, missing
  policy ID, partial artifact pairs, all-rejected curations, zero approvals,
  tampered runtime bytes, expired approvals with and without a runtime board,
  ready-state byte equality, and no-write behavior.
- Existing compiler workflow tests verify deterministic output and failure
  preservation.
- Related topic workflow tests and the full proxy suite are rerun before push.

## Deliberately absent

No real policy, reviewer, contact, raw discovery, curation, pending topic,
decision, runtime board, cache, source text, model response, user dialogue,
absolute local path, or runtime identifier is committed. Collection, scheduling,
compilation, and automatic broadcasting remain unchanged and default OFF.
