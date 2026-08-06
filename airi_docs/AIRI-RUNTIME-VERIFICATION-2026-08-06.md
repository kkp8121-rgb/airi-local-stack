# AIRI Runtime Verification — 2026-08-06

## Services

The reproducible local stack is:

- Ollama: `http://127.0.0.1:11434`
- GPT-SoVITS v2ProPlus API: `http://127.0.0.1:9880`
- AIRI OpenAI-compatible speech proxy: `http://127.0.0.1:8880/v1`

## Speech contract check

`gpt-sovits/test-airi-speech.ps1` sends the same OpenAI-compatible request shape used by AIRI and saves a WAV result. The latest run returned:

- HTTP status: `200`
- First audio chunk: `501.6 ms`
- Total generation: `1.90 s`
- Output: `206,124 bytes`, WAV

The proxy reuses a persistent `requests.Session` so repeated turns can use HTTP keep-alive.

For a one-command check of all three listeners, the model advertisement, and the speech contract, run:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Projects\airi\gpt-sovits\verify-local-stack.ps1
```

The latest run passed with a `399.8 ms` first chunk and `1.64 s` total generation.

`start-local-stack.ps1` now exits with an error when any required listener fails to open, instead of reporting a partial startup as successful.

To start all local services, including faster-whisper STT, use:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Projects\airi\start-airi-local-stack.ps1
```

The integrated launcher keeps STT debug-audio persistence disabled.

## Verification boundary

The scripted request proves the proxy-to-GPT-SoVITS contract, but it does not prove that a user-triggered AIRI UI turn reached the proxy. That final check must be confirmed from the proxy access log after speaking in AIRI.
