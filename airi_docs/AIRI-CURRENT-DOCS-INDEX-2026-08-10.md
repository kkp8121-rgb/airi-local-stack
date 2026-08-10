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

## Latest audit evidence

- `node --test test-send-airi-local-text.mjs`: 21/21 passed.
- The canonical patch and the separate generic-context sanitizer both apply
  cleanly in the pinned v0.11.3 verification checkout.
- The focused browser contract suite with the sanitizer applied passed 25/25
  in the dependency-equipped source checkout.
- The latest privacy/correlation audit found no HIGH or MED issue in the
  current patch boundary.
- `apply-airi-patches.ps1` now verifies all 10 active in-place patch sites,
  including the reaction-latency speech pre-roll marker, plus the required
  absence of the superseded segmentation marker.
- The orchestrator also rejects residual stock markers and child-script
  idempotence now returns to the orchestrator instead of terminating its host
  PowerShell process.
- Existing `app.asar.backup-pristine` files are now SHA-256 checked against the
  pinned pristine 0.11.3 archive before patching continues.
- `restore-airi-original.ps1` uses the same pristine hash contract, stages the
  backup in the target directory, verifies the staged bytes, and publishes via
  an atomic file replacement instead of truncating `app.asar` in place.
- Restore also rejects a container or reparse-point `app.asar` before resolving
  the path, preventing an archive symlink from redirecting replacement outside
  the installation.
- The apply orchestrator applies the same non-reparse checks to the install
  directory and archive before scanning or creating a pristine backup.
