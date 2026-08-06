# AIRI Runtime Verification — 2026-08-06

## Services

- Ollama: `http://127.0.0.1:11434`
- AIRI Ollama compatibility proxy: `http://127.0.0.1:11435`
- GPT-SoVITS v2ProPlus API: `http://127.0.0.1:9880`
- AIRI OpenAI-compatible speech proxy: `http://127.0.0.1:8880/v1`
- faster-whisper STT: `http://127.0.0.1:8890/v1`

## Automated speech contract

`gpt-sovits/test-airi-speech.ps1` sends a mixed English/Korean request through the same OpenAI-compatible endpoint used by AIRI. It verifies the complete response stream, PCM WAV format, duration, RMS, and peak level.

Cold request immediately after a full GPT-SoVITS restart:

- HTTP status: `200`
- First audio chunk: `8944.5 ms`
- Total generation: `10836.6 ms`
- Audio: `3.880 s`, 32 kHz mono PCM16
- RMS: `0.031354`

Immediate warm repeat:

- First audio chunk: `586.6 ms`
- Total generation: `3313.9 ms`
- Audio: `5.145 s`, 32 kHz mono PCM16
- RMS: `0.036567`
- Peak: `0.479980`

The cold result includes model/reference preparation. The launcher now waits for the backend listener and performs one internal warmup when it starts a new backend. A post-warmup contract run returned a 1305.7 ms first chunk, 2927.3 ms total, and RMS 0.033810.

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Projects\airi\gpt-sovits\verify-local-stack.ps1
```

## AIRI renderer verification

A live AIRI chat turn was traced across both Electron renderers. The chat follower forwarded the message to the main Stage authority, which completed the LLM request and issued the speech request.

- LLM: `POST /v1/chat/completions` → 200
- TTS: `POST /v1/audio/speech` → 200
- Playback: two `AudioBufferSourceNode.start()` calls with 1.50 s and 2.18 s 48 kHz buffers on a running AudioContext

A separate renderer-side fetch and `decodeAudioData()` test decoded a 206,124-byte proxy response as 3.22 seconds of audio in 28 ms.

This proves the live text-input UI path through playback scheduling. It does not replace the required real-microphone validation.

## Microphone boundary

Pre-patch STT logs showed many 0.899-second segments. The installed AIRI volume fallback used a 900 ms stop delay and incorrectly stopped VAD-owned segments. `patch-airi-voice-input-segmentation.ps1` now restricts that stop path to volume-owned segments and treats a successful empty transcription as silence.

The remaining acceptance test is five consecutive real user microphone turns with exactly one correct response each and no speaker loopback. Audio persistence and transcript text logging remain disabled by default.
