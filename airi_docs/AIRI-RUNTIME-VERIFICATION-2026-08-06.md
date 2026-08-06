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

## Verification boundary

The scripted request proves the proxy-to-GPT-SoVITS contract, but it does not prove that a user-triggered AIRI UI turn reached the proxy. That final check must be confirmed from the proxy access log after speaking in AIRI.
