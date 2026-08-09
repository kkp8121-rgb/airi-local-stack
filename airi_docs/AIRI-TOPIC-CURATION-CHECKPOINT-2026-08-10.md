# AIRI topic curation checkpoint — 2026-08-10

## Outcome

- Network-capable topic intake can no longer write a ready-to-speak pending
  line. The compatibility entry point fails closed, and the only merge helper
  accepts policy-bound raw discovery records.
- A reviewed local source-policy registry binds the exact source label, feed
  URL, article host/path, license/attribution profile, reviewer, review time,
  and canonical policy hash.
- Raw title and snippet text remain untrusted evidence. They are shown only in
  the offline curation terminal and never enter AIRI prompts, speech, memory,
  runtime boards, decisions, or model input.
- Human curation records `curate` or `reject`; `skip` leaves the remaining raw
  queue untouched. Only curated rows materialize Korean pending records.
- Review and compilation require the policy, raw, curation, and pending files
  together. The former unbound pending compatibility path was removed.
- Runtime TopicBoard v2 still receives only separately reviewed and approved
  lines with pending/decision provenance. No actual source policy, raw topic,
  pending topic, decision, or runtime board was created in this checkpoint.

## Fail-closed boundaries

- HTTPS URLs reject credentials, fragments, explicit ports, IP literals,
  localhost, control characters, and bidirectional-control text.
- Raw records bind the exact policy revision, source metadata, content digest,
  publication/discovery time, and deterministic discovery ID.
- Curation and pending files are locked in canonical path order. Existing
  noncanonical, partial, mismatched, or duplicate state is rejected without
  overwrite.
- Repair can recreate only a missing pending file from an immutable canonical
  curation ledger. It never overwrites a mismatched existing pending file.
- Local source-policy registries and every JSONL workflow artifact are ignored
  by Git. Lock files are ownership-token based and stale locks fail closed.

## Verification

- Focused raw collection, curation, review, and compilation tests: 18 passed.
- Full `ollama-proxy` unit suite: 469 passed.
- Python compilation and `git diff --check`: passed.
- No network, model, service, database, or live topic request was made for this
  checkpoint.

## Next boundary

The next checkpoint may add one default-OFF official-source adapter. It must
use synthetic fixtures in tests, preserve attribution/license metadata, apply
strict network limits, and still stop at the raw discovery queue. Activation
and any real source-policy approval remain separate operator actions.
