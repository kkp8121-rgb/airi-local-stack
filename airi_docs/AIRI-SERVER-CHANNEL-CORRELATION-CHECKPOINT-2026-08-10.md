# AIRI server-channel correlation checkpoint — 2026-08-10

## Outcome

Focus-free text senders no longer identify a completed turn by comparing user
text. Each input now carries an opaque transport event ID, and the sender accepts
only assistant message/completion events whose `metadata.event.parentId` matches
that exact input ID.

This closes the same-text race where a superseded request could mistake a newer
request's completion for its own.

## Runtime contract

- The sender assigns `metadata.event.id` with `randomUUID()` before sending
  `input:text`.
- The Stage context bridge validates the ID with the existing bounded event-ID
  grammar and keeps the association in a renderer-local `WeakMap`.
- Assistant message and chat-complete outputs echo the ID only as
  `metadata.event.parentId`.
- Missing, malformed, or wrong parent IDs never fall back to text matching.
- A runtime that does not support parent correlation therefore fails closed for
  `--wait-complete` instead of accepting an ambiguous completion.
- Distinct inputs retain the existing latest-wins behavior. A superseded sender
  may time out, but it cannot accept the winning sender's completion.

## Privacy and persistence

The event ID is transport-only. It is not added to the user/assistant message,
provider body, session history, proxy journal, round ID, `gen-ai:chat.input`, or
renderer stream snapshot.

Input context updates retain only their source identity. Transport event metadata
is not copied into the context registry or `gen-ai:chat.contexts`.

No raw input, assistant text, session ID, round ID, or generated event ID is
recorded in this checkpoint.

## Verification

- Workspace sender tests: 12 passed.
- Workspace sender syntax checks: passed.
- Stage UI typecheck: passed.
- Canonical source patch applies cleanly to AIRI v0.11.3 commit
  `dbf812488829a61cc2e95909e021b215704d066c`.
- Normalized patched-file hashes reproduced from a clean worktree:
  - `context-bridge.ts`:
    `67B30C1188EC6376E68CD43D4EEE270AAC607C5F849A7B98C0048BB96B05A1D7`
  - `context-bridge.contract.browser.test.ts`:
    `676757D72608691FDF969E0019418A53A2A049D29951CD7AA682F7C94E4579C4`

The focused browser contract test could not execute because the local Playwright
Chromium binary is absent. No browser package was installed. The contract remains
covered statically by the Stage UI typecheck and by the updated source test, while
the workspace sender's pure interleaving tests execute without a browser.
