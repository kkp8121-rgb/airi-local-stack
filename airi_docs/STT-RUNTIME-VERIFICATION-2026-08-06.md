# AIRI Local STT Runtime Verification — 2026-08-06

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

## Endpoint check

An existing AIRI WebM recording was submitted to `POST /v1/audio/transcriptions` and returned a JSON transcription successfully. This proves the local server and multipart OpenAI-compatible route are operational; recognition quality still depends on the captured audio and should be evaluated from new user turns.
