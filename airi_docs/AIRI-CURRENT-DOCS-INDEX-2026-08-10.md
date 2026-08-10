# Current documentation index — 2026-08-10

Use this file to distinguish current source-based handoff material from older
runtime observations.

## Current

- `AIRI-SERVER-CHANNEL-PLAYBACK-CHECKPOINT-2026-08-10.md` is the authoritative
  handoff for cancellation, parent correlation, playback-start proof, sender
  behavior, and current verification.
- `patches/AIRI-v0.11.3-round-cancel-source-replacement.md` is the authoritative
  manifest for the combined runtime patch and its current SHA-256/size/scope.
- `patches/AIRI-v0.11.3-context-correlation-sanitizer.patch` is an additional
  patch for the generic `context:update` occurrence. Apply it after the
  combined patch; it is intentionally separate from the input `contextUpdates`
  sanitizer already present in the combined patch.

## Historical

`AIRI-HANDOFF-2026-08-07.md` and `AIRI-TRACK-M-CHECKPOINT-2026-08-08.md`
preserve earlier test totals, listener observations, archive hashes, and
installation procedures. Those values are not current branch status. Do not
use their old patch hashes or test counts to validate the current checkout.

## Verification boundary

The current branch is source/patch work only. Do not create governed topic
boards, send real microphone text, expose raw IDs or dialogue, or infer natural
playback completion from playback-start evidence.
