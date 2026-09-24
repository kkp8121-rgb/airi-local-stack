# Architecture

Split out of `CLAUDE.md` on 2026-09-24. `AGENTS.md` remains the authoritative contributor contract;
this file describes how the stack fits together.

## What this repository is

A Windows-first **integration workspace** for running AIRI 0.11.3 (a separately installed Electron
desktop VTuber app) against a fully local Korean stack: local LLM, Korean TTS, CUDA STT, memory,
knowledge, and an in-progress live-broadcast persona. The AIRI app itself is **not** in this repo —
it is patched from the outside via byte-exact patches and ASAR replacement
(see [patching.md](patching.md)).

Root PowerShell scripts start, stop, patch, and verify the stack. Core integration code lives in
`ollama-proxy/` (chat, memory, and knowledge), `stt/`, `latency-monitor/`, and `gpt-sovits/`.
Operational notes and byte-sensitive patches are under `airi_docs/`. Tests are generally colocated;
root tests cover cross-component scripts.

Documentation and prose are predominantly Korean; code, identifiers, and commit subjects are English.

## Runtime data flow

All loopback-bound:

```
AIRI desktop app (installed separately, patched app.asar)
   |- chat (OpenAI/Ollama-compatible) -> ollama-proxy :11435 -> Ollama :11434
   |- TTS                             -> gpt-sovits openai proxy :8880 -> GPT-SoVITS API :9880
   |- STT                             -> stt (faster-whisper) :8890
                                         latency-monitor dashboard (latency_trace events)
```

- The AIRI desktop app's chat provider is `http://127.0.0.1:11435/v1` (OpenAI-compatible streaming).
  The offline campaign tool (`ollama-proxy/eval/live_broadcast_campaign/live_campaign.py`) and live
  simulation shows 01-03 drove turns through native `/api/chat` instead; the repository simulator
  (below) uses `/v1` streaming like the app.
- No app patch sends live-broadcast turn tokens from the AIRI app yet; the app-side wiring for
  broadcast turns (B1b/B4) is not implemented.

## Components

- **`ollama-proxy/`** — the brain of the stack and by far the largest component. `ollama_proxy.py`
  is a FastAPI reverse proxy in front of Ollama that also owns memory (`airi_memory.py`,
  `memory_runtime.py`), knowledge (`knowledge_store.py`, Wikimedia topic pipeline), character and
  affect state (`character_state*.py`, `affect_state.py`, `affect_expression.py`), broadcast
  contracts (`broadcast_*.py`, `live_broadcast_runtime.py`, `continuity_ledger.py`), input
  screening / output moderation, and cloud-provider opt-ins (`cloud_chat_provider.py`). It exposes
  `/health`, `/v1/airi/evaluations/*`, `/v1/airi/input-screen`, `/v1/airi/broadcast/*`, and passes
  everything else through to upstream. Live-broadcast tuning (2026-09-23/24) added:
  - `live_briefing_select.py` — **default-off** candidate selection for live briefing turns, wired
    into both the `/v1` streaming path and native `/api/chat`. Enabled only through environment
    variables (no launcher parameter): `AIRI_LIVE_BRIEFING_CANDIDATES` (2-6, recommended 3) and
    `AIRI_LIVE_BRIEFING_COVERAGE` (default 0.4). It acts only when the briefing carries a
    `- 이번 턴에 말할 것:` line. When on, it holds the early first-sentence emission, skips the
    memory-absence canned answer and the one-to-one correction retry, draws candidates, picks by
    coverage, and when every candidate is unfit speaks the briefing line itself (trailing laughter
    removed, final period ensured). Unfit: honorific or written-style endings, leaked labels,
    lookups that did not happen, repeating 20 characters of the previous answer, restating a
    corrected term, echoing congratulations or guessing feelings. `- 아직 말하지 말 것:` lines are
    stripped before the model sees the briefing. State is reported under `/health` →
    `live_briefing_select`.
  - `urgent_safety_context(user_text, previous_reply)` in `ollama_proxy.py` — applied on every path
    by default. Strong terms (자살·자해·죽고 싶·크게 다쳤·응급·폭력) are always urgent; weak terms
    (사고·위험) are urgent for a self-report, a request for help, or narrated harm, but not when the
    viewer echoes AIRI's previous answer, asks about someone else, or guesses.
- **`ollama-proxy/eval/`** — offline evaluation harnesses and gates (baseline, context gate, persona
  jailbreak, broadcast sim/rehearsal, chat replay, input safety, embedding A/B). These encode
  fail-closed adoption gates; they are how model changes are judged.
  `eval/live_broadcast_sim/sim_broadcast.py` (+ `test_sim_broadcast.py` in the CI evaluations
  shard) is the turn-by-turn live-broadcast simulator: broadcast control, `/v1` streaming, renderer
  receipt, close, and forced-history replay. Its output is response-bearing, so its ROOT stays
  outside Git.
- **`ollama-proxy/training/`** — local-only QLoRA/behavior training scaffold: synthesis
  (`synthesize_*.py`), human-review CLIs, dataset verifiers, `train_airi_behavior_lora.py`,
  `merge_airi_behavior_lora.py`, `package_airi_gguf.py`, `durable_training_runner.py`. It is a
  scaffold, not an authorization: trainers re-verify exact dataset SHAs, manifests, and closed
  reports and refuse remote models, network paths, and unsafe CUDA conditions.
  `training/system1/` is the evaluation-only System1 pipeline (candidate labels, judge training,
  contradiction synthesis and contradiction-judge training; see its `README.md`). The trained
  judges judge-v1 (reaction) and contradiction-v1 (contradiction) are **not wired** into operations.
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

## Machine and local assets (2026-09-24, new PC)

- Work PC: the **new PC** (RTX 5060 Ti 8 GiB, no D: drive), not the GPU PC (Codex PC). The AIRI
  desktop app is **not installed or launched** on this PC (user instruction). GPT-SoVITS and STT
  (faster-whisper) are not installed here, so latency including TTS is a GPU-PC task.
- Ollama 0.34.2 is installed. Tag `midm-airi:2.0-mini` differs from the launcher-pinned digest only
  in its manifest (same weights); the evaluation tag `midm-airi-evaltpl:2.0-mini` can be removed.
- Assets outside the repo: `C:\AIRI-Models\gguf\` (Mi:dm 2.0 mini, A.X-4.0-Light and Kanana 1.5
  8B Q4_K_M GGUFs, plus the evaluation-only template-swapped Mi:dm GGUF), `C:\AIRI-Models\system1\`
  (judge-v1, contradiction-v1), `C:\AIRI-Models\venvs\system1\` (training venv), and
  `C:\AIRI-Models\airi-human-eval\` (simulation transcripts, candidates, evaluation outputs —
  response-bearing, kept out of Git).
- Asset locations on the GPU PC: section 0-A of `airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-08-27.md`
  and `airi_docs/진행중/AIRI-GPU-PC-HANDOFF-2026-09-01-STAGE3.md` (see [docs-map.md](docs-map.md)).
