# AIRI final session audit — 2026-08-09

## Verified

- The supplied handoff attachment was read in full.
- Local services 8880, 8890, 8892, 11434, and 11435 respond successfully; 11436 remains intentionally OFF.
- `airi-memory.sqlite3` contains only `user` and `assistant` conversation rows; the current `system` row count is zero.
- The proxy has a Korean-first short-response contract, no-card and active-card paths share the final output contract, and the proxy regression suite has 89 passing tests.
- The idle-broadcast director has protocol/meta candidate rejection tests (7 passing focused tests). The corrected AIRI bundle contains the filter at the real `/out/renderer` path. Earlier original and nested-output bundles remain as backups.
- External search, cloud chat/extraction, evaluation collection, and automatic extraction remain OFF.

## Not yet acceptance-proven

- A new renderer session has not yet supplied a real microphone turn after the corrected bundle installation.
- Therefore first-word STT accuracy, actual playback completion, and end-to-end latency for the corrected bundle remain unproven.
- Direct S1 style evaluation previously passed only 2/12 automatic cases; it is a diagnostic result, not evidence that AIRI already meets the final VTuber-style target.

## Required next user-visible check

Start AIRI, confirm Local Broadcast is OFF, open a fresh conversation, and test one ordinary greeting followed by one memory question. Only after those are clean should Local Broadcast be enabled for a short one-candidate check. Record the displayed input/output and the privacy-safe latency event counts; do not reuse the old polluted conversation for acceptance.
