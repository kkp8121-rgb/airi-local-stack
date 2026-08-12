# AIRI source ASAR deployment safety — 2026-08-13

## 판정

`airi-source-asar-deploy-common.ps1`, `install-airi-source-asar.ps1`,
`restore-airi-source-asar.ps1`, and `test-airi-source-asar-deploy.ps1` provide
a narrow, source-built-ASAR deployment safety path. The synthetic deployment
tests passed with ASAR files larger than 1 MiB. This is tooling completion
only: the installed AIRI app was not stopped, backed up, replaced, or otherwise
modified.

## Safety contract

- Install requires the artifact SHA-256 and the current installed `app.asar`
  SHA-256; restore likewise requires current and backup SHA-256 values.
- Artifact, current archive, rollback archive, and restored archive must pass
  bounded ASAR pickle/strict-UTF-8 JSON validation. The validator checks
  payload bounds for `package.json`, `out/main/index.js`,
  `out/preload/index.mjs`, and `out/renderer/index.html`, then reads the real
  package payload and requires `ai.moeru.airi` version `0.11.3`.
- Every existing path component must be a regular local-drive,
  non-reparse path. File identity rejects target/artifact or target/backup
  hard-link aliases.
- A same-target Global mutex serializes install and restore. The scripts fail
  closed on uninspectable AIRI processes and hold an exclusive `airi.exe`
  launch barrier across backup, replacement, verification, and rollback.
- `File.Replace` writes the exact displaced target directly to a unique,
  persistent verified backup. Install and explicit restore verify both sides
  and restore those exact displaced bytes on any post-replace failure.
- Synthetic coverage includes wrong expected hashes, malformed or truncated
  critical ASAR entries, wrong package identity, exact displaced-backup bytes,
  install and restore post-replace rollback, launch-barrier and live-process
  refusal, hard-link/junction rejection, explicit restore, and idempotency.

## Observed boundary and next gate

The shared validator passed against the actual installed archive in a
read-only probe at 1,356,257,019 bytes and SHA-256
`1B68AE5ECB9DB998002AC7268DE707661EC0C81FC4BD90836F3C3E25719B88B0`;
the digest remained identical before and after validation. No installed archive
write and no AIRI stop were authorized or performed.
Consequently, this record does not claim a completed installation, installed
source behavior, or runtime TTS duration/pitch verification.

[GitHub issue #2](https://github.com/kkp8121-rgb/airi-local-stack/issues/2) is
the tracking gate for any authorized installed-ASAR operation. Before that gate
is explicitly cleared, use the scripts only on the synthetic fixture path; do
not treat source build success or these tests as installed-runtime evidence.
