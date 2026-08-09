# AIRI v0.11.3 round correlation / cancellation source patch

Status: **implemented, verified, source-built, and installed as the live AIRI v0.11.3 `app.asar`.**

- Upstream tag: `v0.11.3`
- Peeled commit: `dbf812488829a61cc2e95909e021b215704d066c`
- Patch: `AIRI-v0.11.3-round-cancel.patch`
- Patch SHA-256: `8bd061184bb98b48fca1946dcaf1c8ae6707fb404541640f744a6a0b5aa9b26c`
- Patch size: 84,743 bytes
- Scope: 32 files, 817 insertions, 60 deletions
- Combined local-runtime patch: `AIRI-v0.11.3-local-runtime-source.patch`
- Combined patch SHA-256: `483cfc6e6cbfdd9df33402e3d02d95572fd7ec0dd1fc9772f7ccaca781ca6fa1`
- Combined patch size: 105,778 bytes
- Combined scope: 38 files, 1,009 insertions, 196 deletions

The patch was generated from the exact diff of a clean v0.11.3 checkout and
`git apply --check --reverse` succeeds against the fully patched checkout.
The original 32-file patch is retained as the round/cancel-only artifact. The
combined 38-file patch additionally preserves the installed local audio and
latency behavior as source changes. Both patches pass
`git apply --check --reverse` against their corresponding patched checkout.

## Implemented contract

### One bounded round ID

`ChatOrchestratorSendOptions.roundId` accepts only 1–128 characters matching
`[A-Za-z0-9][A-Za-z0-9._:-]*`; invalid or absent values fall back to the
runtime-generated ID. The same ID is stored on the user message and
`ChatStreamEventContext`.

For recorder-backed STT, the transcript buffer reserves a context before ASR.
Nearby VAD fragments retain one round ID until the buffered chat message is
flushed. Empty, skipped, stale, failed, cleared, and disposed reservations
settle without leaking the ID into a later turn.

A long-lived streaming-STT connection can emit multiple chat messages and does
not yet expose a truthful per-sentence transport ID. It is therefore excluded
from the explicit STT-to-LLM-to-TTS correlation claim.

### Session-scoped cancellation

The core runtime owns one active `{ AbortController, roundId }` per session.
Accepted user-facing input sets `supersedeActive: true`, cancelling only the
older active round in that session. Background/context producers retain the
existing FIFO queue behavior.

`cancelActiveRound(conversationId, optionalRoundId)` supports exact session and
optional round matching. The LLM provider receives the active signal through
`StreamOptions.abortSignal`. An abort is normal control flow: it does not emit
failure or success telemetry, append a finalized assistant message, or run
assistant-completion hooks. Identity-checked cleanup cannot delete a newer
controller.

Stage stops the previous speech pipeline synchronously when a new message
round is composed. REST TTS receives the same AbortSignal. Stale checks run
before and after fetch, after audio decode, immediately before playback, and
before caption publication, preventing late audio from an older round.

### Privacy-bounded transport headers

- LLM session/round headers are attached only to AIRI's official provider or
  an exact loopback custom endpoint (`localhost`, `127.0.0.1`, or `::1`).
- App-surface analytics remains official-provider-only.
- Recorder-backed STT receives the round header only at an exact loopback
  endpoint.
- REST TTS receives the round header only for the official speech provider or
  an exact loopback provider request URL.
- Arbitrary remote custom providers receive none of these local correlation
  headers.

### Speech-pipeline propagation

`roundId` is a separate optional field across speech turn, token, segment, TTS
request/result, cross-window bus, session, and playback. It does not replace
`turnId`, `intentId`, or `streamId`. The server `/audio/speech` route also
carries an accepted round header into TTS trace metadata.

The installed AIRI design already forwards token literals to a punctuation
chunker, so the proxy's true local Ollama SSE now lets the first complete
sentence begin TTS before model completion. REST synthesis still decodes one
complete sentence response before playing it; audio-byte streaming within a
sentence is not claimed.

### Preserved local audio / latency behavior

The combined patch also carries the previously binary-patched behavior into
reviewable source: browser audio processing is disabled, recorder-backed STT
uses native `MediaRecorder` with a preferred Opus/WebM format and 128 kbps,
the volume fallback stop delay is 2,700 ms, VAD silence/pad defaults are
450/600 ms, buffered voice transcript flush is 400 ms, empty STT output is
treated as silence, and playback-start telemetry is sent best-effort to the
loopback latency monitor. The older behavior that sent session correlation to
an arbitrary remote custom endpoint was deliberately not restored; official
and exact loopback endpoints retain correlation, while arbitrary remote custom
providers receive none.

## Verification

All implementation edits were complete before the final focused regression.

| Boundary | Result |
|---|---:|
| core-agent orchestrator | 16/16 |
| pipelines speech / transcript / TTS chunking | 30/30 |
| stage-ui chat/hearing/voice/TTS/audio/VAD | 66/66 |
| Tamagotchi chat-sync | 10/10 |
| server speech route/tracing | 74/74 |
| **Focused total** | **196/196** |

Type checks passed for `core-agent`, `pipelines-audio`, `stage-ui`, `server`,
`stage-web`, `stage-pocket`, and `stage-tamagotchi`. After integrating the
local audio/latency source changes, fresh package builds passed for
`core-agent` and `pipelines-audio`, and a fresh Tamagotchi production build
passed. Earlier Web, Pocket, Tamagotchi, and server build checks for the
round/cancel-only patch also passed.

The root `build:packages` orchestration command itself could not locate a pnpm
binary through Turbo under Corepack. This was an environment/tool-launch issue;
the impacted package builds, app builds, type checks, and tests above completed
successfully. One earlier whole `pipelines-audio` attempt also exposed three
pre-existing playback-manager timing failures; the changed pipeline, buffer,
and chunker suites pass 30/30.

`git diff --check` exits 0. Windows Git reports only the checkout's configured
LF-to-CRLF conversion warnings.

## Installed artifact checkpoint

- Installed product version: `0.11.3.0`
- Installed `app.asar` size: 1,119,409,243 bytes
- Installed/artifact SHA-256: `203c84f10ea90d12bdefed27ca51f3b701dba34730597a4d0bce8cf1deaa3f76`
- Atomic rollback archive SHA-256: `cb672061d4a92f36d9450e8a30fe08134d0c66bbc388e1b3c444ad4a328634c8`
- Independent pre-install backup: `<local-app-data>/AIRI-Codex-Backups/<checkpoint>/app.asar`
- In-place rollback: `<airi-install>/resources/app.asar.rollback-before-round-cancel-source-20260808`

The built archive contains 28,082 entries and reports package version 0.11.3.
Four representative main/renderer files extracted from the archive matched the
fresh build byte-for-byte. All 135 `app.asar.unpacked` native files matched the
installed copies by relative path, size, and SHA-256, so only `app.asar` was
replaced. The builder's outer `win-unpacked` finalization exceeded the command
timeout; its archive-producing child completed, and the fully validated
`app.asar` was used directly rather than treating the partial outer directory
as a portable distribution.

## Apply to a clean source checkout

Do not apply this directly to `app.asar`. From a clean upstream checkout:

```powershell
git checkout v0.11.3
git rev-parse HEAD
git apply --check airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch
git apply airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch
```

The reported HEAD must be
`dbf812488829a61cc2e95909e021b215704d066c`. The installed artifact above was
built from this pinned checkout after explicit user authorization.

## Remaining live boundaries

- The source patch is installed. Live end-to-end cancellation, stale-output
  suppression, and equal STT/LLM/TTS round-header observation still require the
  user's next natural conversation and are not claimed from static tests alone.
- Typed/newly accepted user input and explicit runtime cancellation abort
  network work. True acoustic full-duplex barge-in remains outside this patch;
  it needs echo cancellation or another reliable user-speech trigger.
- Character-card, memory, dialogue-director, and tool semantics are not used as
  cancellation or correlation side channels and were not bypassed.
