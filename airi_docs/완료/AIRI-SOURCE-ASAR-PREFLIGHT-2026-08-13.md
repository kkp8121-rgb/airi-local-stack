# AIRI source ASAR read-only preflight — 2026-08-13

Evidence sidecar:
`airi_docs/evidence/AIRI-TTS-ASAR-CANDIDATE-BUILD-2026-08-13.json`,
SHA-256 `5A5960A52E1337E0F4F4EFE3C6F9C5BE5787D353B7908CE002A90552F87A3813`.
It pins candidate `app.asar` at 1,131,077,260 bytes /
`6767625E9B5C0A01625A6ADA59544480EA4FE4235AAA117A16471A1718C9BCED` and
installed current `app.asar` at 1,356,257,019 bytes /
`1B68AE5ECB9DB998002AC7268DE707661EC0C81FC4BD90836F3C3E25719B88B0`.

The batch consists of the read-only preflight command, its offline synthetic
contract suite, and checkpoint wiring in `test-current-checkpoint.ps1`. Static
gates cover evidence digest/schema/pins, ASAR and executable hashes, fuses,
non-reparse paths and identities, unpacked manifests, patch bytes, processes,
and final drift checks. Synthetic cases use temporary fixtures only.

A live read-only invocation reached the process gate and refused because seven
exact installed AIRI processes were running. No process was stopped, no mutex
or launch barrier was acquired, and no install file was mutated. This is not a
live preflight PASS, install authorization, or installation.

The result is point-in-time only. A separately authorized installer must
revalidate inputs and acquire its mutex and executable launch barrier. Explicit
install approval, runtime TTS duration/pitch, text-to-render, portable
packaging, and Godot remain pending. STT/microphone remains OFF/deferred.
