# Patching the installed AIRI app

Split out of `CLAUDE.md` on 2026-09-24. `AGENTS.md` remains authoritative.

## Patch artifacts are byte-sensitive

`airi_docs/patches/*.patch` are byte-sensitive artifacts pinned by path in `test-patch-manifest.ps1`
and CI, including recorded hunk headers and specific Korean strings. **Do not move, reformat, or
whitespace-clean them**; regenerate only deliberately and update the manifest in the same change.
Preserve patch files byte-for-byte unless intentionally regenerating them. The CI whitespace check
excludes them (`':(exclude)airi_docs/patches/*.patch'`) because the manifest hash covers them
instead.

## Deploy and rollback

The deploy path is `apply-airi-patches.ps1` then `install-airi-source-asar.ps1` (SHA-256 of both the
artifact and the current installed `app.asar` are mandatory parameters), with
`restore-airi-source-asar.ps1` / `restore-airi-original.ps1` as rollback — all verified offline by
`test-airi-source-asar-*.ps1` against synthetic archives.

## Where this applies (2026-09-24)

- The AIRI desktop app is not installed or launched on the new PC (user instruction), so the deploy
  path is not run there.
- No app patch sends live-broadcast turn tokens from the AIRI app yet; the app-side broadcast-turn
  wiring (B1b/B4) is not implemented (see [architecture.md](architecture.md)).
