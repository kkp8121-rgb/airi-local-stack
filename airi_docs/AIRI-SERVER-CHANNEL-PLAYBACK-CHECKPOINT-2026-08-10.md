# AIRI server-channel playback checkpoint — 2026-08-10

## Scope

This checkpoint extends the loopback server-channel correlation work with an
optional playback-start proof. It is intentionally content-free: the new
event carries no text, audio, round ID, session ID, or model output.

## Implemented

- Added `output:gen-ai:chat:playback-start` to the protocol. Its data payload
  is an empty object; correlation is carried only by the envelope
  `metadata.event.parentId`.
- `Stage.vue` emits the local playback signal only after `source.start(0)`
  succeeds. Existing latency-monitor playback tracing remains unchanged.
- The context bridge keeps a bounded renderer-local round-to-parent map. It
  records only locally originating correlated rounds, ignores remote mirrors,
  sends one exact parent-correlated event, and clears the mapping on playback,
  cancellation, stale replacement, and disposal. Completion intentionally
  does not clear it because chat completion can precede audio start.
- `send-airi-local-text.mjs` adds opt-in `--wait-playback-start`. It waits for
  the exact correlated completion and playback-start events in either order;
  a matching supersession cancellation settles immediately. Default
  `--wait-complete` behavior is unchanged.

## Verification

- Root sender tests: 18/18 passed; Node syntax checks passed, including the
  completion-first/playback-later metadata path.
- Stage UI typecheck passed.
- Playback latency tests: 4/4 passed.
- Protocol typecheck passed.
- Runtime source patch applies cleanly to the pinned v0.11.3 base with
  `git apply --check --whitespace=nowarn`.
- Browser contract tests were not runnable because the local Playwright
  Chromium executable is absent; no browser binary was installed.

## Operational boundary

The optional sender flag proves playback-start, not natural playback end.
The default completion mode remains suitable for existing callers. No
production topic board, pending review data, raw discovery, or personal
dialogue was created by this checkpoint.

## Handoff request for the next Claude session

Please review commit history from the latest checkpoint and audit only the
current source patch and sender/bridge protocol. Verify:

1. playback-start is emitted only after successful `source.start(0)`;
2. parent correlation is exact and no round/session/text leaks into the wire,
   broadcast snapshots, journal, or persisted messages;
3. completion-first and playback-first ordering, duplicate events, stale
   rounds, remote mirrors, and supersession cancellation are fail-closed;
4. default `--wait-complete` remains behavior-compatible;
5. the generated runtime patch applies to the pinned base and does not include
   unrelated temporary/runtime artifacts.

Run offline tests and typechecks first. Do not create a governed topic board,
do not send real microphone text, and do not expose raw IDs or dialogue in
your report. If live validation is authorized, use only synthetic input and
report counts/statuses without text or identifiers.
