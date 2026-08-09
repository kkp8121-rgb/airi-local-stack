# AIRI runtime checkpoint — 2026-08-09

## Installed state

- AIRI v0.11.3 source build installed as `resources/app.asar`.
- Installed SHA-256: `C8BEFE4E95C361710564FD7D897E2D3D716C9C60451C0E3BCE3A12FC5692809D`.
- Pre-install backup: `resources/app.asar.pre-topic-context-isolation-20260809`.
- AIRI is running with local automatic broadcast enabled.

## Local-only topic boundary

- `ollama-proxy/topic_board.py` validates an approved local JSON board.
- The board is connected only to exact-loopback `local-proactive` requests.
- Regular chat is unaffected.
- Proactive generation skips journal RAG and memory retrieval.
- AIRI proactive composition uses `historyProjection: system-only` and `runtimeContextProjection: none` so recent user examples and private character observations cannot become idle subjects.
- Raw topic content is transient and is not journaled, extracted, evaluated, or sent to cloud providers.
- Default runtime remains unconfigured/OFF until the user supplies an approved file under `ollama-proxy/runtime`.

## Evaluation

- Current prompt C0 v0.3 fixture: 16 cases, exactly one run per case.
- Automatic result: `7/16`, gate `FAIL`.
- JSON, summary table, and separate AI-assisted review are under `ollama-proxy/eval/results/*current-rerun*`.
- This is distinct from the historical v0.2 10-case `2/10` result.
- Independent human review remains a user acceptance item.

## Verification

- Topic board tests: 7 passed.
- Proxy tests: 93 passed.
- Core chat runtime tests: 23 passed.
- Audio chunk/pipeline tests: 26 passed.
- Broadcast/playback-proof/latency/channel tests: 28 passed.
- Tamagotchi chat-sync tests: 11 passed.
- Core, pipelines-audio, stage-ui, i18n, and stage-tamagotchi typechecks: passed.
- Tamagotchi production build: passed.
- PowerShell launcher syntax: passed.

## Live acceptance

- Proxy restarted with external search/chat/extraction/evaluation collection OFF.
- Port 11436 remains OFF.
- Stable session-header observation after restart: no missing requests.
- Initial repeated broadcast exposed one real GPT-SoVITS backend read timeout.
- GPT-SoVITS proxy/backend were restarted and a real WAV warmup returned HTTP 200.
- After restart, two consecutive local broadcasts reached natural WebAudio completion.
- A meta-shaped candidate was rejected before TTS, as designed.
- Memory `data_version` and pending totals remained unchanged across proactive broadcasts.
