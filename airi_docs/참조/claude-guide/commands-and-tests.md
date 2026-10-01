# Commands and tests

Split out of `CLAUDE.md` on 2026-09-24. `AGENTS.md` remains authoritative.

## Commands

Run from the repository root in PowerShell. CI targets Python 3.12 / Node 22 on `windows-latest`.
Service-dependent checks may require the local GPU stack; CI checks run offline.

```powershell
.\start-airi-local-stack.ps1        # start proxy + TTS (+ STT with -Stt on) + monitoring
.\stop-airi-local-stack.ps1         # stop the stack cleanly
.\test-current-checkpoint.ps1       # the offline contract suite CI runs
```

- `start-airi-local-stack.ps1` starts the local Ollama proxy, TTS, and monitoring; STT only with
  `-Stt on` (default off unless `AIRI_STT` is set). It is heavily parameterized (STT on/off,
  `-OllamaNumGpu`, `-NumCtx`, memory/knowledge toggles and DB paths, extraction provider and gate
  profile, `-ChatProvider` local/openai/anthropic, `-LiveBroadcast`). External chat/search/memory
  providers are always explicit opt-ins — never flip them on by default.
- The live briefing candidate selection has no launcher parameter; it is enabled only through
  `AIRI_LIVE_BRIEFING_CANDIDATES` / `AIRI_LIVE_BRIEFING_COVERAGE` and stays off by default
  (see [architecture.md](architecture.md)).
- `test-current-checkpoint.ps1` runs the offline work-continuity, roadmap-dashboard,
  training-durability, patch-manifest, entrypoint, applicability, ASAR, and Node/Python contract
  checks used by CI. The first two are the document contracts `test-airi-work-continuity.ps1` and
  `test-airi-roadmap-dashboard-contract.ps1`.
- On the new PC the AIRI desktop app is not installed or launched (user instruction); do not start
  it as part of any command sequence there.

## Tests

```powershell
python -m pytest -q ollama-proxy test_latency_trace.py test_start_airi_background.py latency-monitor stt
python -m pytest -q ollama-proxy/test_ollama_proxy.py                  # single file
python -m pytest -q ollama-proxy/test_ollama_proxy.py -k some_case     # single test
node --test test-send-airi-local-text.mjs                              # single Node suite (sender contract)
node --test chat-ingress/test-*.mjs
.\test-patch-manifest.ps1                                              # single PowerShell contract
git diff --check -- . ':(exclude)airi_docs/patches/*.patch'            # whitespace (no formatter configured)
```

- Python tests use pytest and follow `test_*.py`; Node tests use `node:test` in `test-*.mjs`;
  PowerShell contract checks use `test-*.ps1`. Add regression coverage beside the affected
  component.
- Everything in the offline contract suite must pass without GPU, services, models, or the installed
  AIRI archive. Keep new default tests deterministic, offline, and free of personal model/audio
  dependencies. CI enforces passing tests, not a numeric coverage threshold.

## CI matrix and count floors

- CI (`.github/workflows/remediation-checkpoint.yml`) runs the whitespace check plus
  `test-current-checkpoint.ps1`, then shards the Python suite by explicit test-file lists to fit a
  10-minute budget. **When you add a Python test file under a sharded root, add it to the matrix in
  that workflow** or it will never run in CI. Recent examples: `test_live_briefing_select.py` sits in
  the `ollama-proxy-model` shard and `eval/live_broadcast_sim/test_sim_broadcast.py` in the
  `ollama-proxy-evaluations` shard.
- Several suites invoked by `test-current-checkpoint.ps1` assert a minimum test count
  (chat-ingress >= 47, broadcast rehearsal >= 37, input safety >= 16, affect evaluator fence >= 11);
  raise the floor when you add tests there.

## Known local test baseline (recorded 2026-10-01)

Source: `wc_referee_receipt_20261001` and `precommit_checks_wc_referee_20261001` in
`airi_docs/진행중/AIRI-WORKING-STATE.md` (stack stopped).

- `ollama-proxy\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider ollama-proxy test_latency_trace.py test_start_airi_background.py latency-monitor`
  → 2684 passed, 17 skipped, 5 failed. The 5 failures are the known baseline: 4
  `test_airi_session_header_patch` tests blocked by this PC's PowerShell execution policy, and 1
  `test_synthesize_broadcast_continuity_v4` test. System Python 3.12 has no httpx; use the repo venv.
- `stt` is excluded on this PC because the proxy venv has no `av` module.
- `test-current-checkpoint.ps1` on this PC: run it from Windows PowerShell with the machine module path and
  `C:\AIRI-Models\venvs\llamacpp-convert\Scripts` first on `PATH` (its training-durability step needs a
  Python with torch; it sometimes times out at 30 seconds — run it again). Every step then passes up to
  B4c, which fails only because that venv has no httpx; run B4c with the repo venv
  (`-m unittest -v ollama-proxy/eval/broadcast_chat/test_run_broadcast_rehearsal.py`, 85 tests, floor 37)
  and the three Node groups after it (chat-ingress 47, broadcast-director 24, latency dashboard 5).
- The document contract tests `test-airi-work-continuity.ps1` and
  `test-airi-roadmap-dashboard-contract.ps1` passed before and after the 2026-09-24 documentation
  refresh (final rerun 11:59 KST, exit 0); rerun them after any edit to `NEXT-SESSION.md`, `airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-08-21.md`,
  `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md`, the live state, or `AGENTS.md`, whose markers they pin.
