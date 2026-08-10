# AIRI Current Documentation Index - 2026-08-10

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
`AIRI-WORK-CHECKPOINT-2026-08-10.md` is also historical: it predates the
current branch handoff and records the superseded `b234abe` baseline and
82-path patch hash. Use the current patch manifest below instead.
The same historical rule applies to command examples in other documents dated
2026-08-07 or 2026-08-08: in particular, do not invoke individual
`patch-airi-*.ps1` steps from those pages. Use the current orchestrator contract
below instead.

The installed-artifact section in
`patches/AIRI-v0.11.3-round-cancel-source-replacement.md` is likewise a
historical checkpoint. For the current server-channel runtime observation,
use the 2026-08-10 server-channel checkpoint instead.

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
- The intermediate `resources` directory is also required to be a regular
  non-reparse directory, closing junction redirection between install root and
  `app.asar`.
- The apply orchestrator serializes its complete run with a named local mutex;
  concurrent invocations fail fast before touching the installation.
- If an internal patch step throws, the orchestrator stops the remaining patch
  sequence before final verification; restore from the verified pristine backup
  before investigating or retrying.
- `test-patch-entrypoints.ps1` is an offline regression check for the internal
  child-script guard and does not inspect or modify an AIRI installation.
- `test-patch-manifest.ps1` is an offline regression check for the three
  documented patch artifact sizes and SHA-256 values; it does not inspect or
  modify an AIRI installation.
- `test-current-checkpoint.ps1` runs the manifest, entrypoint, and sender
  contract checks together as one offline checkpoint command.
- `.github/workflows/remediation-checkpoint.yml` runs that same checkpoint on
  Windows for every push, pull request, or manual dispatch; it does not install
  or start AIRI.
- Restore uses the same mutex, so apply and restore cannot modify the archive
  concurrently.
- The six active `patch-airi-*.ps1` child files are implementation steps for
  the orchestrator; the seventh matching file,
  `patch-airi-transcript-latency.ps1`, is a deprecated stub. None are
  concurrent standalone entry points; use
  `apply-airi-patches.ps1` or `restore-airi-original.ps1` for supported
  operations. Each step now requires the orchestrator-only
  `-InternalOrchestrator` switch and refuses direct invocation before touching
  the archive.
- New pristine backups are hash-gated before and after staging, then published
  with no-clobber atomic move; concurrent runs may only reuse an independently
  verified backup.
- Existing backup reuse also rejects container or reparse-point backup paths
  before hashing.
