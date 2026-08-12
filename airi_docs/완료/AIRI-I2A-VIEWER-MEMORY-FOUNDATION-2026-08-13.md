# AIRI I2a Viewer Memory Foundation — 2026-08-13

## Status

I2a foundation is implemented and tested; I2 is still partial. This batch is default-inert/off and has no launcher, proxy-runtime, renderer, or live-service integration. The next completion gate is an authorized next-broadcast callback smoke.

## Implemented boundary

- A separate SQLite store is created only with explicit `enabled=True`; the disabled default creates no database.
- Existing databases are accepted only when their exact dedicated ownership marker and schema signature match. Creation is atomic under one write lock; unrelated or partially conflicting databases are rejected without added tables.
- Records use strict 43-character HMAC pseudonyms only: `yt:v1` event, `viewer:v1` viewer, and `broadcast:v1` broadcast keys. Raw YouTube IDs never enter this store.
- The B1 screened text is deliberately excluded. The JS observation boundary accepts the frozen ingress event but emits only pseudonymous keys, normalized display name, kind, and timestamp; it does not parse `[YouTube]` or alter `toAiriEvent` delivery.
- The JS wire shape is snapshotted against accessor/Proxy changes, and the Python adapter converts its exact millisecond timestamp to seconds. Observations and facts more than 30 seconds in the future fail closed.
- Manual tiers are capped at tier 1 = 10–20 and tier 2 = 30–50. Display-name history keeps at most five names per viewer.
- Facts are explicit typed inputs only (`interest` or `status`) with approved provenance and a maximum 90-day lifetime. There is no model extraction or prompt injection path.
- Event dedup tombstones are retained for 730 days and cannot be configured shorter than the 365-day inactive-viewer retention; expired facts and inactive viewers are pruned. Explicit deletion removes a viewer and its linked pseudonymous event records.
- Donation storage is count-only. Amounts and free-form donation data are not accepted. Health exposes counts/status only and is content-free.
- Callback output is an untrusted typed candidate for a future policy/renderer; it is not rendered text and has no runtime integration.

## Explicitly not included

No B1b live adapter, OAuth, quota work, AIRI injection, persistence wiring from ingress, model parsing, prompt construction, runtime database/launcher wiring, or donation support beyond the explicit count flag exists in I2a.

## Verification

- `node --test chat-ingress/test-*.mjs`: 17 passing tests.
- `python -m unittest -q test_viewer_memory.py` from `ollama-proxy/`: 19 passing tests.
- `python -m pytest -q ollama-proxy/test_viewer_memory.py`: 19 passing tests and 15 passing subtests.
- CI-equivalent 44-path Python 3.12 matrix: 877 passed, 1 skipped, 723 subtests passed, 7 warnings.
- `test-current-checkpoint.ps1`: PASS (sender 27, chat-ingress 17, patch/entrypoint contracts).

No network, model, service, installed-AIRI, or personal runtime database was used.
