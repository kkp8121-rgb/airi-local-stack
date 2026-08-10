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
- Rebinding a valid round ID first invalidates any old mapping, preventing a
  later local or uncorrelated reuse from inheriting a stale parent.
- `send-airi-local-text.mjs` adds opt-in `--wait-playback-start`. It waits for
  the exact correlated completion and playback-start events in either order;
  a matching supersession cancellation settles immediately. Default
  `--wait-complete` behavior is unchanged.

## Verification

- Root sender tests: 20/20 passed; Node syntax checks passed, including the
  completion-first/playback-later metadata path.
- Stage UI typecheck passed.
- Playback latency tests: 4/4 passed.
- Protocol typecheck passed.
- Stale round-parent reuse regression coverage was added to the browser
  contract suite.
- Runtime source patch applies cleanly to the pinned v0.11.3 base with
  `git apply --check --whitespace=nowarn`.
- Browser contract suite: 24/24 passed after installing the local Playwright
  Chromium executable. It covers exact parent correlation, content-free
  playback output, remote-mirror rejection, completion-before-playback, and
  stale round-parent reuse.
- The follow-up context-correlation sanitizer patch adds a generic
  `context:update` regression: transport `metadata.event` is stripped before
  registry ingest and renderer broadcast. Its focused browser contract suite
  passes 25/25. Apply
  `airi_docs/patches/AIRI-v0.11.3-context-correlation-sanitizer.patch` after
  the canonical runtime patch when using a clean v0.11.3 checkout.

## Live synthetic proof

The rebuilt official source was packaged and installed locally, then AIRI was
started in background mode with the stage readiness gate satisfied. The
installed archive SHA-256 was
`A81C52811BCD6F5290A5C0D498357742F26D61CE33F8FEBDB767CC8AD388BC00`. A
synthetic, non-personal sender request using `--wait-playback-start
--print-assistant-shape` returned only content-free status fields indicating
`sent=true`, `completed=true`, and `playback_started=true`; completion latency
was 648 ms and playback-start latency was 1525 ms. A prior attempt had no TTS
segment and timed out as expected; the monitor recorded zero TTS segments for
that attempt. No response text or runtime identifiers are committed here.

## Operational boundary

The optional sender flag proves playback-start, not natural playback end.
The default completion mode remains suitable for existing callers. No
production topic board, pending review data, raw discovery, or personal
dialogue was created by this checkpoint.

No `--wait-playback-end` flag is shipped yet. The available audio end hooks
are emitted per playback item, while one chat response may produce multiple
items and an item may end by interruption or rejection rather than natural
completion. Treating the first item end as whole-turn completion would create
a false success signal. A future end proof needs a dedicated, round-correlated
event emitted only after the final naturally completed item, with explicit
interruption semantics and bounded state; until then playback-start is the
strongest safe bounded proof.

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
