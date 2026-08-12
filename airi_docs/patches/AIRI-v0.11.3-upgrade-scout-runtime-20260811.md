# AIRI v0.11.3 Upgrade Scout runtime layer

This is the manifest for the third supported AIRI source patch layer. Apply it
only after these two existing layers, in order:

1. `AIRI-v0.11.3-local-runtime-source.patch`
2. `AIRI-v0.11.3-context-correlation-sanitizer.patch`
3. `AIRI-v0.11.3-upgrade-scout-runtime-20260811.patch`

## Pinned artifact

- Base release commit: `dbf812488829a61cc2e95909e021b215704d066c`
- Verified source commit after layers 1 and 2: `cfd46d321b2159d6f737ae4732b82fa04779a5da`
- Verified source commit after layer 3: `bf173f2de870e3f779db02548d691c7b51bb290f`
- Verified source tree after layer 3: `ff71039caa507c5676c2cee31125374c5cc37d35`
- Size: `130,974` bytes
- SHA-256: `CC172A16281E56DC03E6A6F261B5531367711C0393D57E171C932EA8544C5E3E`

## Scope

The layer contains the client-side Upgrade Scout work only:

- incremental loopback WAV playback with acknowledged bounded PCM
  backpressure, delayed pre-roll connection, terminal flush, and abort;
- progressive PCM for streaming WAV responses whose `data` size is zero;
- chunk-boundary-safe PCM resampling from GPT-SoVITS source rate to the
  AudioContext output rate, retaining mono/stereo frame alignment;
- playback-start ownership and a 12 ms abort fade;
- text self-echo suppression before caption, chat, journal, or memory effects;
- half-duplex, headphones, and speakers-with-AEC interaction modes;
- sustained-VAD barge-in routed through the global speech stop path;
- the dynamic VAD fallback and an inert 450 ms versus 300 ms experiment gate;
- loopback streaming STT transport, partial captions, and guarded final input.
- Electron-only moderation display: validated loopback `airi_moderation` SSE
  metadata becomes a transient `필터당함` badge without entering text, speech,
  memory, history, or cloud sync.

It does not change the GPT-SoVITS reference voice. The 300 ms VAD candidate is
not the production default, and AEC is enabled only in the explicit speakers
mode. It does not deploy approved knowledge fixtures into an operational DB.

## Verification

- The patch applies after the first two layers and reverses cleanly.
- Applying it preserves the existing Upgrade Scout audio/VAD/STT work and adds
  the moderation display contract.
- The Stage UI and Stage Tamagotchi production dependency graphs build.
- Stage UI and Stage Tamagotchi typechecks pass.
- Focused progressive WAV/resampler/backpressure tests pass (6 files, 28 tests).
- The Stage Tamagotchi Electron production build passes.
- Focused moderation stream/store tests (21) and Stage UI/Tamagotchi typechecks pass.
- A fresh Windows build was installed as ASAR SHA-256
  `1B68AE5ECB9DB998002AC7268DE707661EC0C81FC4BD90836F3C3E25719B88B0`;
  an actual loopback blocked turn rendered the visible `필터당함` badge.
