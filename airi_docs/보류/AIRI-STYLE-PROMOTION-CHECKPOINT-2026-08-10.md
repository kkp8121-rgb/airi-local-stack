# AIRI reviewed-style promotion checkpoint — 2026-08-10

## Outcome

The repository now has a default-off, offline compiler that can mechanically
promote a completely reviewed 200-record S1 pending queue into a deterministic
production-verifiable bundle. This checkpoint does not contain or create review
decisions, reviewer identities, governance envelopes, evaluation fixtures,
promotion bundles, gate reports, adapters, or model output.

## Safety boundary

- Promotion requires the exact opt-in flag and explicit local input paths.
- Exact input bytes are bound by a separately supplied governance envelope.
- Every pending record must have one complete, approving, record-hash-bound human
  decision; rewrite, reject, missing, extra, stale, or case-mismatched reviewers
  fail closed.
- Inputs are read once through checked regular-file handles. Existing symlink and
  Windows reparse-point path components are rejected.
- A per-output ownership lock serializes cooperative writers and cleans up an
  interrupted partial acquisition. Publication refuses an existing output.
- The staged bundle is verified through the production gate before publication.
- No immutable gate report is generated, so promotion alone cannot authorize
  training. The existing trainer still re-verifies its governed inputs.

## Bundle contract

A successful bundle contains exactly:

- `reviewed-dataset.jsonl`
- `review-manifest.json`
- `c0-fixture.jsonl`
- `s1-fixture.jsonl`
- `promotion-approval.json`

Dataset IDs and partition groups are deterministic derivatives of canonical
pending-record hashes. Prompt, answer, split, and category content are preserved.
No wall-clock value is introduced by the compiler.

## Verification at this checkpoint

Focused tests cover deterministic output, default-off behavior, governance and
fixture drift, decision completeness and approval state, exact reviewer identity,
pre-existing output preservation, cooperative lock exclusion, and interrupted
lock cleanup. Repository-wide proxy regression is run before the checkpoint is
committed and pushed.

## Remaining human work

No production C0/S1 fixture artifacts, complete decision sidecar, or governance
approval envelope currently exist in this checkpoint. Human review and external
identity/custody controls remain prerequisites. The hashes used here are binding
and tamper-evident, not cryptographic signatures.
