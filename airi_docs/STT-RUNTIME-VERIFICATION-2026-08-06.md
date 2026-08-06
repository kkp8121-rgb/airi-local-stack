# AIRI Local STT Runtime Verification — 2026-08-06

## Service

- Endpoint: `http://127.0.0.1:8890`
- Engine: faster-whisper `small`
- Device: CPU, INT8
- Threads: `6`
- Health: `ok`

The service was stopped and restarted through `stt/start-local-stt.ps1`. The script now waits for `/health` to report `status=ok` and fails after a bounded 60-second startup window instead of returning before model loading completes.

## Endpoint check

An existing AIRI WebM recording was submitted to `POST /v1/audio/transcriptions` and returned a JSON transcription successfully. This proves the local server and multipart OpenAI-compatible route are operational; recognition quality still depends on the captured audio and should be evaluated from new user turns.
