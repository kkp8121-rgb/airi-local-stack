# AIRI Wikimedia source-policy checkpoint — 2026-08-10

## Outcome

The optional Wikimedia topic intake now has an explicit offline human boundary
for creating its reviewed local source-policy registry. This checkpoint does
not enable collection, schedule a fetch, create a policy, or change the AIRI
runtime.

## Contract

- `create_wikimedia_source_policy.py` is inert unless the exact
  `--create-wikimedia-policy` flag is present.
- The disabled path does not parse paths, read the clock, prompt, acquire a
  lock, or write a file.
- Enabled creation requires an absolute `source-policies*.json` target directly
  under `ollama-proxy/topic-review`, a policy ID, a reviewer identity, and three
  exact typed confirmations.
- The record fixes the Korean Wikipedia API, article boundary, portal
  attribution, and CC BY-SA 4.0 license used by the guarded adapter. It stores no
  User-Agent contact and performs no network or model call.
- Existing canonical policies are preserved. The exact same policy and reviewer
  are idempotent; collisions, different reviewers, noncanonical input, target
  changes, and concurrent writers fail closed.
- A temporary canonical registry is validated through the production policy
  loader, fsynced, and atomically replaced only after the target is rechecked.
- Ownership-lock acquisition is interruption-safe, including an interrupt after
  exclusive sidecar creation but before its token is completely written.
- Terminal output contains only status and policy count. Success is reported
  only after lock release, preventing contradictory success/rejection output.

## Verification

- Focused source-policy creator tests cover the disabled dependency boundary,
  all confirmation cancellations, create/load/idempotence, collisions,
  noncanonical input, duplicate flags, invalid clock input, concurrent lock
  rejection, partial lock-acquisition interruption cleanup, and post-commit
  lock-release failure reporting.
- Related discovery, Wikimedia adapter, scheduler, and review-workflow tests are
  rerun before this checkpoint is pushed.
- The full proxy test suite is rerun after focused verification.

## Deliberately absent

No real reviewer, Wikimedia contact, source-policy registry, cache, raw topic,
curation, pending topic, decision, compiled runtime board, model response, user
dialogue, local path, or runtime identifier is committed here. Collection and
the scheduler remain default OFF.
