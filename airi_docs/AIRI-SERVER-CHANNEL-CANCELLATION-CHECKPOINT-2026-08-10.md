# AIRI server-channel cancellation checkpoint — 2026-08-10

## Scope completed

This checkpoint closes the lifecycle gap left after parent-correlation was added to the local text sender. A newer `input:text` now produces a separate, content-free `output:gen-ai:chat:cancelled` terminal for the superseded active round. The cancellation terminal is correlated only by the existing opaque transport parent relationship; it carries no user text, assistant text, session identifier, round identifier, usage, audio, or context.

The sender treats a matching completion and a matching cancellation as mutually exclusive first-terminal outcomes. A cancellation is reported as `cancelled: true` with the fixed reason `superseded`; it is not reported as a successful completion and contains no assistant payload. Wrong-parent, missing-parent, duplicate, and same-text cross-request events are ignored. Old runtimes that do not know the new event retain the existing timeout behavior.

The core runtime now exposes a synchronous, error-isolated cancellation hook. Supersession emits the hook exactly once before aborting the active controller, while manual cancellation and normal completion do not emit it. The renderer bridge maps only valid local input correlations to the new server event, strips transport correlation from context-update metadata and broadcast snapshots, and preflights cancellation before per-event ingestion locks. A renderer-local active-parent guard prevents replaying the same input event from cancelling its own round.

## Files and source patch

- Workspace sender: `send-airi-local-text.mjs` and `test-send-airi-local-text.mjs`.
- Official source changes: plugin protocol, core hook/runtime, stage chat store, channel store, and context bridge plus focused tests.
- Canonical source replacement: `airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch`.

The canonical patch was regenerated from the pinned AIRI v0.11.3 base (`dbf8124`) after applying the previous checkpoint and copying the current selected source files. A fresh clean worktree accepted it with `git apply --check --whitespace=nowarn`.

## Verification

- Core runtime focused Vitest: 27 passed.
- Core-agent, stage-ui, and plugin-protocol typechecks: passed.
- Workspace sender Node tests: 13 passed; syntax checks passed.
- Canonical source patch apply check: passed.
- Stage browser contract test was attempted but could not launch because the local Playwright Chromium executable is not installed. No browser or service installation was performed in this checkpoint.

## Installed-runtime proof

The official source was rebuilt and packaged into an archive of 1,359,499,075 bytes with SHA-256 `E59A3E456ECC1615B7A57AFA61BA0947C39977717C74C86A799179C21988AA6D`. The prior installed archive was preserved before replacement. The installed background runtime reported `stageMounted=true`, voice enabled/configured, and microphone permission `granted` through the passive status probe.

A privacy-safe same-text race was then run with two separate sender processes, 250ms apart. The first sender returned `sent=true`, `cancelled=true`, fixed reason `superseded` in 318ms; the second returned `sent=true`, `completed=true` in 1,936ms with 14 assistant characters. Both stderr streams were empty. The monitor retained 19 completed LLM turns at inspection time; the newest eligible turn had one TTS segment and a playback record. No raw text, session identifier, or round identifier was recorded here.

A future playback-wait mode remains separate work; it must use an explicit parent-correlated renderer event and must not poll the latency monitor.

No real microphone transcript, assistant response, session identifier, or round identifier is recorded in this document.
