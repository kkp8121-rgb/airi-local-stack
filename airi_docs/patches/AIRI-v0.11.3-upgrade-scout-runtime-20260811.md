# AIRI v0.11.3 Upgrade Scout runtime layer

This is the manifest for the third supported AIRI source patch layer. Apply it
only after these two existing layers, in order:

1. `AIRI-v0.11.3-local-runtime-source.patch`
2. `AIRI-v0.11.3-context-correlation-sanitizer.patch`
3. `AIRI-v0.11.3-upgrade-scout-runtime-20260811.patch`

## Pinned artifact

- Base release commit: `dbf812488829a61cc2e95909e021b215704d066c`
- Verified source commit after layers 1 and 2: `cfd46d321b2159d6f737ae4732b82fa04779a5da`
- Verified source commit after layer 3: `16dbb36316b27c832b6ec8bf6a470f3a9a3e434e`
- Size: `85,541` bytes
- SHA-256: `EDE9FA204DB1869C8A3A7F2A9587A6B321742F008728EE489C2B6F49D435F9DA`

## Scope

The layer contains the client-side Upgrade Scout work only:

- incremental loopback WAV playback with bounded PCM buffering and abort;
- playback-start ownership and a 12 ms abort fade;
- text self-echo suppression before caption, chat, journal, or memory effects;
- half-duplex, headphones, and speakers-with-AEC interaction modes;
- sustained-VAD barge-in routed through the global speech stop path;
- the dynamic VAD fallback and an inert 450 ms versus 300 ms experiment gate;
- loopback streaming STT transport, partial captions, and guarded final input.

It does not change the GPT-SoVITS reference voice. The 300 ms VAD candidate is
not the production default, and AEC is enabled only in the explicit speakers
mode. It does not deploy approved knowledge fixtures into an operational DB.

## Verification

- The patch applies after the first two layers and reverses cleanly.
- Applying it reproduces the verified source tree at `16dbb36` exactly.
- The Stage UI and Stage Tamagotchi production dependency graphs build.
- Stage UI and Stage Tamagotchi typechecks pass.
- Focused client tests pass: playback manager 10, Stage UI 28, Tamagotchi 4.
