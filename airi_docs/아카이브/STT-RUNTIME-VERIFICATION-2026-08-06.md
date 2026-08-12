# AIRI Local STT Runtime Verification — 2026-08-06

> **2026-08-07 주의:** 아래 Device/Threads(CPU INT8, 6 threads)는 CUDA float16 전환 이전 기록이다. 현행 기준은 `AIRI-LOCAL-TECH-SPECS.md`.

## Service

- Endpoint: `http://127.0.0.1:8890`
- Engine: faster-whisper `small`
- Device: CPU, INT8
- Threads: `6`
- Health: `ok`

The service was stopped and restarted through `stt/start-local-stt.ps1`. The script now waits for `/health` to report `status=ok` and fails after a bounded 60-second startup window instead of returning before model loading completes.

## Audio privacy

The earlier debug configuration persisted every uploaded recording under `stt/debug-recordings`. That could retain other people's speech if the selected input device contained a voice-chat mix. Debug persistence is now **off by default**; it is only enabled with `-EnableDebugAudio`, which prints a warning. The existing ten debug files were not deleted automatically.

The STT server remains bound to `127.0.0.1`; it does not publish audio to the network. Input-device selection and OS mixer routing still determine which sound reaches AIRI, so a microphone-only device must be selected when recording other people's speech is not authorized.

The server log now omits recognized text by default (`text_logged=false`). Use `--verbose-transcription-log` only for an intentional debugging session. Existing `stt-server.out.log` content from before this change may still contain text and was not rewritten automatically.

## Endpoint check

An existing AIRI WebM recording was submitted to `POST /v1/audio/transcriptions` and returned a JSON transcription successfully. This proves the local server and multipart OpenAI-compatible route are operational; recognition quality still depends on the captured audio and should be evaluated from new user turns.
