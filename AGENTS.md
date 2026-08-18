# Repository Guidelines

## Project Structure & Module Organization

This is a Windows-first local AIRI stack. Root PowerShell scripts start, stop, patch, and verify it. Core integration code lives in `ollama-proxy/` (chat, memory, and knowledge), `stt/`, `latency-monitor/`, and `gpt-sovits/`. Operational notes and byte-sensitive patches are under `airi_docs/`. Tests are generally colocated; root tests cover cross-component scripts. `chatterbox/`, `faster-qwen3-tts/`, and `Qwen3-TTS-Openai-Fastapi/` are upstream snapshots documented in `THIRD-PARTY-SOURCES.md`; keep changes to them easy to audit.

## Build, Test, and Development Commands

- `.\start-airi-local-stack.ps1` starts the local Ollama proxy, TTS, STT, and monitoring services.
- `.\stop-airi-local-stack.ps1` stops the stack cleanly.
- `.\test-current-checkpoint.ps1` runs the offline patch-manifest, entrypoint, applicability, and Node contract checks used by CI.
- `python -m pytest -q ollama-proxy test_latency_trace.py test_start_airi_background.py latency-monitor stt` runs the core Python regression suite.
- `node --test test-send-airi-local-text.mjs` runs the sender contract tests directly.

Run commands from the repository root in PowerShell. CI targets Python 3.12 and Node 22. Service-dependent checks may require the local GPU stack; CI checks run offline.

## Coding Style & Naming Conventions

Follow the surrounding file: Python uses four spaces, `snake_case`, `PascalCase` classes, type hints, and uppercase constants; JavaScript uses two spaces, ESM imports, single quotes, `camelCase`, and no semicolons; PowerShell uses four spaces, PascalCase parameters, and approved `Verb-Noun` functions. No repository-wide formatter is configured, so check whitespace with `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'`. Preserve patch files byte-for-byte unless intentionally regenerating them.

## Testing Guidelines

Python tests use pytest and follow `test_*.py`; Node tests use `node:test` in `test-*.mjs`; PowerShell contract checks use `test-*.ps1`. Add regression coverage beside the affected component and keep default tests deterministic, offline, and free of personal model/audio dependencies. CI currently enforces passing tests, not a numeric coverage threshold.

## Commit & Pull Request Guidelines

Recent history follows Conventional Commit-style subjects: `fix: ...`, `test: ...`, `docs: ...`, and `ci: ...`. Use a short, imperative summary and separate unrelated changes. Pull requests should explain behavior, identify affected services or patches, list verification commands and results, and link relevant issues. Include screenshots or latency/audio evidence for UI, playback, or performance changes.

## Security & Configuration Tips

Never commit `.env` files, credentials, model weights, personal audio, logs, SQLite runtime data, or generated outputs; these are ignored intentionally. External chat, search, and memory providers must remain explicit opt-ins. Avoid weakening localhost bindings or pinned CI dependencies without documenting the security impact.
