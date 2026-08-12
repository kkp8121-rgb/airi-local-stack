# AIRI v0.11.3 Upgrade Scout runtime layer

This is the manifest for the third supported AIRI source patch layer. Apply it
only after these two existing layers, in order:

1. `AIRI-v0.11.3-local-runtime-source.patch`
2. `AIRI-v0.11.3-context-correlation-sanitizer.patch`
3. `AIRI-v0.11.3-upgrade-scout-runtime-20260811.patch`

## Pinned artifact

- Base release commit: `dbf812488829a61cc2e95909e021b215704d066c`
- Verified source commit after layers 1 and 2: `cfd46d321b2159d6f737ae4732b82fa04779a5da`
- Verified source commit after layer 3: `dcf9396a8f51fe4f1b73af9a48813bc43adca486`
- Verified source tree after layer 3: `d40b4a3d314bde97cc8eb90f790a649e1f08870f`
- Size: `106,205` bytes
- SHA-256: `13417A7464C35B2A8C2E8FDC54F37E629C32F031F9F7DA5EB6073B995E1F63DA`

## Scope

The layer contains the client-side Upgrade Scout work only:

- incremental loopback WAV playback with bounded PCM buffering and abort;
- progressive PCM for streaming WAV responses whose `data` size is zero;
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
- Focused moderation stream/store tests (21) and Stage UI/Tamagotchi typechecks pass.
- A fresh Windows build was installed as ASAR SHA-256
  `1B68AE5ECB9DB998002AC7268DE707661EC0C81FC4BD90836F3C3E25719B88B0`;
  an actual loopback blocked turn rendered the visible `필터당함` badge.
