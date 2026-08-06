# AIRI Status Reconciliation — 2026-08-06

This file reconciles older planning notes with the current workspace state.

Older Chatterbox latency figures in the original plan are historical measurements, not the active GPT-SoVITS path; use `AIRI-LOCAL-TECH-SPECS.md` and the runtime verification documents for current numbers.

## Completed in the workspace

- Local GPT-SoVITS v2ProPlus API and AIRI OpenAI-compatible speech proxy are running on `9880` and `8880`.
- Warm GPT-SoVITS streaming measurements on the RTX 3060 Ti passed the current latency target (roughly 0.4–0.6 seconds to first chunk in the gate suite).
- Windows Korean G2P compatibility was installed and exercised.
- Local faster-whisper STT source is present at `stt/openai_stt_server.py` and runs on `8890`.
- STT startup waits for model readiness; debug audio persistence and transcription text logging are disabled by default.
- MOSS-TTS-Nano ONNX Korean CPU voice cloning was measured and failed the realtime RTF<1 gate; it remains a fallback experiment, not the active AIRI TTS.

## AIRI UI runtime evidence

Actual AIRI 0.11.3 user-agent requests to `/v1/audio/speech` and actual Opus/WebM microphone POSTs to STT are now present in the local logs. Five consecutive accurate microphone turns and absence of speaker loopback still require user acceptance testing; effective AEC/NS/AGC settings also need `MediaStreamTrack.getSettings()` verification.

## Reproducible launchers

- Current GPT-SoVITS path: `start-gpt-sovits-airi-stack.ps1`
- Current all-in-one local path: `start-airi-local-stack.ps1`
- Latency dashboard: `show-airi-latency-dashboard.ps1`
- Contract and listener check: `gpt-sovits/verify-local-stack.ps1`

The GPT-SoVITS launcher also starts AIRI's Ollama compatibility proxy on `11435`; AIRI should use this URL for the local LLM, not the raw Ollama port when the proxy's prompt/tool normalization is required.
