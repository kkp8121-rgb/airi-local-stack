# AIRI playback trace checkpoint — 2026-08-10

## Outcome

Focus-free server-channel chat now emits a content-free playback-start event only after the matching Web Audio source successfully executes `source.start(0)`.

The earlier absence of playback telemetry did not prove that audio playback had failed. The trace admitted only rounds registered by `sttAccepted`, so text turns could reach `source.start(0)` while the event was intentionally suppressed.

## Source change

- `voice-turn-latency.ts` owns a bounded `armedPlaybackTurns` set.
- `armPlaybackRound(roundId)` admits an authoritative chat round without pretending it was an STT turn.
- `sttAccepted(roundId)` retains its existing voice/LLM semantics and also arms playback.
- `firstPlaybackStart(roundId)` consumes the playback admission exactly once.
- `Stage.vue` arms the round synchronously after assigning `activeSpeechRoundId` in `onBeforeMessageComposed`.
- The existing call immediately after `source.start(0)` remains the only playback event emitter.

The canonical source patch is updated in `airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch`.

## Verification

- Focused latency tests: 3 passed.
- Stage UI typecheck: passed.
- Electron Vite application build: passed.
- The canonical patch applies cleanly to pinned AIRI v0.11.3 source commit `dbf812488829a61cc2e95909e021b215704d066c`.
- Patched file hashes reproduced from a clean source worktree:
  - `Stage.vue`: `16c613accd190e2817dddad5d08ab5a9d30d89a6`
  - `voice-turn-latency.ts`: `4dba92c136f53331a18d8b7984439355e4f5e964`
  - `voice-turn-latency.test.ts`: `48cc12525ab3671b6080baf37690d29ab876a3de`
- Packaged and installed ASAR:
  - size: `1,359,495,696` bytes
  - SHA-256: `1215584584AA3216A25D4AF15A6339AAE38611669ED1264E1F6E4C57E1002669`
- Previous installed archive was retained as `app.asar.pre-playback-trace-20260810-0721` for recovery.
- AIRI restarted with the background contract; Stage readiness passed and no visible window was opened.

## Live focus-free proof

One synthetic Korean declarative was sent through the loopback server-channel API without mouse, keyboard, or focus automation.

- request characters: 21
- matching completion: 998 ms
- assistant characters: 22
- TTS segments: 1
- TTS duration: 1,965.8 ms
- playback event: present with explicit round correlation
- playback timestamp: 14 ms after the TTS end timestamp

The monitor event is emitted after the successful `source.start(0)` call. It therefore proves that the application reached Web Audio playback start for this turn, while making no claim about physical speaker volume or hardware audibility.

## Privacy and persistence

- No transcript, assistant text, session identifier, or round identifier is stored in this checkpoint.
- Playback telemetry contains only an opaque per-turn correlation value and numeric timing.
- Focus-free input remains API-driven; no desktop focus or pointer control was used.
