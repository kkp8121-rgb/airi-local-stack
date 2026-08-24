# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`AGENTS.md` is the authoritative contributor contract for this repo. Read it in full; this file
summarizes the architecture and the parts that are easy to get wrong.

## What this repository is

A Windows-first **integration workspace** for running AIRI 0.11.3 (a separately installed Electron
desktop VTuber app) against a fully local Korean stack: local LLM, Korean TTS, CUDA STT, memory,
knowledge, and an in-progress live-broadcast persona. The AIRI app itself is **not** in this repo —
it is patched from the outside via byte-exact patches and ASAR replacement.

Documentation and prose are predominantly Korean; code, identifiers, and commit subjects are English.

## Session start protocol (non-negotiable)

Before running anything — at session start, goal resume, reboot, or right after a context compact —
read in this order and reconcile against real state (`git status`, HEAD SHA, running PIDs, artifact
SHAs) **read-only**:

1. `AGENTS.md`
2. `airi_docs/진행중/AIRI-WORKING-STATE.md` — the mutable live SSoT (YAML frontmatter carries
   `goal_status`, `git_head`, `worktree_state`, `active_trainer_count`, last receipt)
3. the current handoff named by that file (currently `airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-08-21.md`)
4. `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md`
5. `NEXT-SESSION.md`

Never resume from a chat summary alone. If live state disagrees with the machine, stop and correct
the record from observation before executing. Do not start a duplicate process without first
checking the exact command line of any running PID.

While a goal is active, refresh `AIRI-WORKING-STATE.md` at least every 60 minutes (15 during GPU
training, merge/package, T3 matrices, or long campaigns), and immediately on checklist completion,
process start/stop, checkpoint/hash/authorization/blocker changes, and pause/resume. Long or
state-changing commands get an **intent checkpoint** before and a **receipt checkpoint** after
(exit code, PID, artifacts, verification). No receipt means not complete. Redact credentials,
tokens, `.env` values, and personal paths from recorded commands.

## Architecture

Runtime data flow (all loopback-bound):

```
AIRI desktop app (installed separately, patched app.asar)
   |- chat (OpenAI/Ollama-compatible) -> ollama-proxy :11435 -> Ollama :11434
   |- TTS                             -> gpt-sovits openai proxy :8880 -> GPT-SoVITS API :9880
   |- STT                             -> stt (faster-whisper) :8890
                                         latency-monitor dashboard (latency_trace events)
```

- **`ollama-proxy/`** — the brain of the stack and by far the largest component. `ollama_proxy.py`
  is a FastAPI reverse proxy in front of Ollama that also owns memory (`airi_memory.py`,
  `memory_runtime.py`), knowledge (`knowledge_store.py`, Wikimedia topic pipeline), character and
  affect state (`character_state*.py`, `affect_state.py`, `affect_expression.py`), broadcast
  contracts (`broadcast_*.py`, `live_broadcast_runtime.py`, `continuity_ledger.py`), input
  screening / output moderation, and cloud-provider opt-ins (`cloud_chat_provider.py`). It exposes
  `/health`, `/v1/airi/evaluations/*`, `/v1/airi/input-screen`, `/v1/airi/broadcast/*`, and passes
  everything else through to upstream.
- **`ollama-proxy/eval/`** — offline evaluation harnesses and gates (baseline, context gate, persona
  jailbreak, broadcast sim/rehearsal, chat replay, input safety, embedding A/B). These encode
  fail-closed adoption gates; they are how model changes are judged.
- **`ollama-proxy/training/`** — local-only QLoRA/behavior training scaffold: synthesis
  (`synthesize_*.py`), human-review CLIs, dataset verifiers, `train_airi_behavior_lora.py`,
  `merge_airi_behavior_lora.py`, `package_airi_gguf.py`, `durable_training_runner.py`. It is a
  scaffold, not an authorization: trainers re-verify exact dataset SHAs, manifests, and closed
  reports and refuse remote models, network paths, and unsafe CUDA conditions.
- **`stt/`**, **`gpt-sovits/`**, **`latency-monitor/`** — speech in, speech out, and the latency
  dashboard. Each has its own `start-*.ps1` / `stop-*.ps1`.
- **`chat-ingress/`** (B1) and **`broadcast-director/`** (B4) — pure, dependency-free ESM cores for
  YouTube live-chat admission and broadcast scheduling. Both are **default-off**, contain no
  transport/OAuth/persistence, and have detailed contracts in their own `README.md`. Read those
  READMEs before touching either; the privacy boundaries (HMAC pseudonyms, display name kept out of
  prompt material) are load-bearing.
- **Root PowerShell scripts** — the operational surface: start/stop the stack, apply/restore
  patches, deploy the patched ASAR, run campaigns and training, and pause safely.
- **`chatterbox/`, `faster-qwen3-tts/`, `Qwen3-TTS-Openai-Fastapi/`, `external/`** — upstream
  snapshots recorded in `THIRD-PARTY-SOURCES.md`. Keep local changes small and auditable.

## Commands

Run from the repository root in PowerShell. CI targets Python 3.12 / Node 22 on `windows-latest`.

```powershell
.\start-airi-local-stack.ps1        # start proxy + TTS (+ STT with -Stt on) + monitoring
.\stop-airi-local-stack.ps1
.\test-current-checkpoint.ps1       # the offline contract suite CI runs
```

`start-airi-local-stack.ps1` is heavily parameterized (STT on/off, `-OllamaNumGpu`, `-NumCtx`,
memory/knowledge toggles and DB paths, extraction provider and gate profile, `-ChatProvider`
local/openai/anthropic, `-LiveBroadcast`). External chat/search/memory providers are always
explicit opt-ins — never flip them on by default.

Tests:

```powershell
python -m pytest -q ollama-proxy test_latency_trace.py test_start_airi_background.py latency-monitor stt
python -m pytest -q ollama-proxy/test_ollama_proxy.py                  # single file
python -m pytest -q ollama-proxy/test_ollama_proxy.py -k some_case     # single test
node --test test-send-airi-local-text.mjs                              # single Node suite
node --test chat-ingress/test-*.mjs
.\test-patch-manifest.ps1                                              # single PowerShell contract
git diff --check -- . ':(exclude)airi_docs/patches/*.patch'            # whitespace (no formatter configured)
```

CI (`.github/workflows/remediation-checkpoint.yml`) runs the whitespace check plus
`test-current-checkpoint.ps1`, then shards the Python suite by explicit test-file lists to fit a
10-minute budget. **When you add a Python test file under a sharded root, add it to the matrix in
that workflow** or it will never run in CI. Several suites invoked by `test-current-checkpoint.ps1`
also assert a minimum test count (chat-ingress >= 47, broadcast rehearsal >= 37, input safety >= 16,
affect evaluator fence >= 11); raise the floor when you add tests there.

Everything in the offline contract suite must pass without GPU, services, models, or the installed
AIRI archive. Keep new default tests deterministic and offline.

## Patching the installed AIRI app

`airi_docs/patches/*.patch` are byte-sensitive artifacts pinned by path in `test-patch-manifest.ps1`
and CI, including recorded hunk headers and specific Korean strings. **Do not move, reformat, or
whitespace-clean them**; regenerate only deliberately and update the manifest in the same change.
The deploy path is `apply-airi-patches.ps1` then `install-airi-source-asar.ps1` (SHA-256 of both the
artifact and the current installed `app.asar` are mandatory parameters), with
`restore-airi-source-asar.ps1` / `restore-airi-original.ps1` as rollback — all verified offline by
`test-airi-source-asar-*.ps1` against synthetic archives.

## Conventions

- Python: 4 spaces, `snake_case`, type hints, uppercase constants. JavaScript: 2 spaces, ESM,
  single quotes, `camelCase`, **no semicolons**. PowerShell: 4 spaces, PascalCase parameters,
  approved `Verb-Noun` functions, `Set-StrictMode` / `$ErrorActionPreference = 'Stop'`.
- Tests are colocated: `test_*.py` (pytest), `test-*.mjs` (`node:test`), `test-*.ps1` (contract
  checks). Root-level tests cover cross-component scripts.
- Commits: Conventional-Commit subjects (`fix:`, `test:`, `docs:`, `ci:`), short and imperative,
  unrelated changes separated. Do not commit or push unless the current session explicitly
  authorizes it — much of this repo's workflow is deliberately local-only until a receipt exists.
- Never commit `.env`, credentials, model weights, personal audio, logs, SQLite runtime data, or
  generated outputs (`.gitignore` excludes these intentionally). Response-bearing evaluation
  reports and runtime packets stay out of Git.
- Do not weaken localhost bindings or unpin CI dependencies without documenting the security impact.

## Code navigation

Serena is not used and must not be reintroduced or assumed (see
`airi_docs/진행중/AIRI-CODEX-SERENA-TOKEN-ORDER-2026-08-20.md` — measured net token loss). Use the
built-in file/search tools and `rg`, narrowed to the range you actually need, for symbol lookups,
references, and cross-file renames as well as for text search and running shells/tests.

## Documentation map

`airi_docs/` is organized by state, and the folder decides how much a claim is worth:
`진행중/` current contracts (treat as branch state), `진행예정/` approved-but-unstarted plans (read
before starting), `로드맵/` roadmap (log every work batch in `AIRI-ROADMAP-LOG.md`), `완료/` valid
evidence for finished work, `보류/` paused work, `아카이브/` superseded — **never** use for verifying
current state, `참조/` timeless reference, `patches/` pinned artifacts. Start at
`airi_docs/AIRI-CURRENT-DOCS-INDEX-2026-08-10.md`, which is kept current despite its filename.

Measurements here are held to a high bar: a number counts as verified only with a recorded command,
exit code, artifact, and SHA. Do not promote a synthetic or partial measurement to a completed goal.

<!-- imported-from: codex:project:instructions -->
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

## 코드 탐색 정책 (2026-08-23)

- Serena는 사용하지 않는다. 설치·연결·재도입·의존을 작업 전제로 두지 않는다.
- 심볼·참조·타입 계층·cross-file rename/move도 repository built-in 도구와 `rg`로
  필요한 범위만 좁혀 확인한다.
- 1~2줄 수정, 자유 텍스트/문자열 검색, 설정·JSON·픽스처·ps1·md 파일,
  쉘·git·테스트 실행도 기존 built-in 도구를 사용한다.

## 장기 Goal 상태 보존 정책 (2026-08-22)

- 세션 시작, goal resume, 재부팅, compact/요약 직후에는 어떤 실행보다 먼저
  `airi_docs/진행중/AIRI-WORKING-STATE.md`를 **전체 읽고**, 실제 goal status,
  `git status`, PID/command line, 관련 산출물·SHA를 read-only로 대조한다.
  compact된 채팅 요약만 믿고 이어서 실행하지 않는다.
- active goal에서는 live state를 마지막 기록 후 **최대 60분** 안에 갱신한다.
  GPU 학습, merge/package, T3, 장시간 campaign 중에는 상한을 **15분**으로 줄인다.
  체크리스트 완료·실패, 10분 이상 명령의 직전/직후, 프로세스 시작·중단,
  checkpoint·해시·권한·blocker 변경, pause/resume/종료 때는 시간과 무관하게 즉시 갱신한다.
- 장기·상태 변경 명령은 live state에 `intent checkpoint`를 먼저 쓰고, 종료 후
  exit code·PID·산출물·검증 결과를 `receipt checkpoint`로 쓴다. receipt가 없거나
  검증 산출물이 없으면 계산 시간이 있었어도 완료/진척으로 승격하지 않는다.
- 자동 compact 직전 알림은 보장되지 않으므로 pre-compact 기록 하나에 의존하지 않는다.
  heartbeat는 live state만 짧게 덮어쓰고, handoff·roadmap status는 milestone,
  권한 변경, pause/handoff 때 갱신하며 roadmap log는 작업 배치마다 기록한다.
- live state가 실제 프로세스·파일·SHA와 다르면 실행을 멈추고 관측 사실로 먼저
  정정한다. 실행 중인 PID의 exact command/output/log를 확인하기 전에는 중복
  프로세스를 시작하지 않는다.
- PC 전환이나 예상 가능한 종료 전에는 live state를 최종 receipt로 만든다. commit/push가
  해당 세션에서 명시적으로 허가되지 않았다면 임의로 수행하지 말고 로컬 전용임을 알린다.
- 사용량 0으로 응답이 끊기면 `interrupted-awaiting-quota-reset`으로 취급한다. 종료 전
  기록 기회를 가정하지 않으며, 재개 시 마지막 정상 receipt/checkpoint와 실제 기계 상태를
  다시 대조한다. 시간·토큰·compact·재부팅만으로 작업을 완료 처리하거나 축소하지 않는다.
- exact command와 경로를 기록할 때 credential, token, `.env` 값, 원문·개인 경로는
  redaction한다. live-state heartbeat만 dirty인 경우 입력 코드·데이터 clean preflight에서
  이 파일 하나를 명시적으로 제외하고 diff를 별도 검토한다. 다른 tracked/untracked 변경은
  허용하지 않는다.
