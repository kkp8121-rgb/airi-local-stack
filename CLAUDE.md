# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`AGENTS.md` is the authoritative contributor contract for this repo. It is imported by the line
below, so Claude Code loads it together with this file. This file is a table of contents: the
details live in the category files under `airi_docs/참조/claude-guide/`.

@AGENTS.md

## What this repository is

A Windows-first **integration workspace** for running AIRI 0.11.3 (a separately installed Electron
desktop VTuber app) against a fully local Korean stack: local LLM, Korean TTS, CUDA STT, memory,
knowledge, and an in-progress live-broadcast persona. The AIRI app itself is **not** in this repo —
it is patched from the outside via byte-exact patches and ASAR replacement. Prose is mostly Korean;
code, identifiers, and commit subjects are English.

## Session start protocol (non-negotiable)

Before running anything — at session start, goal resume, reboot, or right after a context compact —
read in this order and reconcile against real state (`git status`, HEAD SHA, running PIDs, artifact
SHAs) **read-only**:

1. `AGENTS.md`
2. `airi_docs/진행중/AIRI-WORKING-STATE.md` — the mutable live SSoT (frontmatter carries
   `goal_status`, `git_head`, `worktree_state`, `active_trainer_count`, `current_handoff`)
3. the current handoff: **`airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-09-30.md`** (end of the 2026-09-30 session:
   state, rules and pitfalls, next steps), then its detail doc `AIRI-BROADCAST-READINESS-HANDOFF-2026-09-29.md`
   (§7 operator formats, §8-7 v6, §8-8 ep19; RP decisions stay in `AIRI-PERSONA-RP-HANDOFF-2026-09-26.md`, the stack
   and simulator how-to in `AIRI-LIVE-BROADCAST-HANDOFF-2026-09-24.md` §3-§4)
4. `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md`
5. `NEXT-SESSION.md`

Never resume from a chat summary alone. If live state disagrees with the machine, stop and correct
the record from observation before executing. Do not start a duplicate process without first
checking the exact command line of any running PID. Heartbeat cadence (120 minutes, 30 during GPU
work or long campaigns), intent/receipt checkpoints, and redaction:
[goal-state-policy.md](airi_docs/참조/claude-guide/goal-state-policy.md).

## Current context (2026-09-29)

- This is the **new PC** (RTX 5060 Ti 8 GiB, no D: drive), not the GPU PC. **Do not install or
  launch the AIRI desktop app here** (user instruction). GPT-SoVITS and STT are not installed, so
  latency including TTS is a GPU-PC task.
- Active track: broadcast readiness with the persona-v4 fine-tune — real-app-path show simulations,
  default-off live-path features in the proxy, evaluation tools outside Git. Results, remaining work,
  and open decisions are in the current handoff and the `AIRI-WORKING-STATE.md` receipts.
- Operational adoption stays forbidden (`adoption_authorized=false`); new proxy behavior stays
  default-off until the user decides.

## Load-bearing rules

- **Patches are byte-sensitive.** Never move, reformat, or whitespace-clean
  `airi_docs/patches/*.patch`; regenerate only deliberately and update the manifest in the same
  change. → [patching.md](airi_docs/참조/claude-guide/patching.md)
- **Commit and push only with explicit approval** in the current session; every push needs its own
  approval. → [conventions.md](airi_docs/참조/claude-guide/conventions.md#commits-and-pull-requests)
- **Never commit secrets or runtime data**: `.env`, credentials, model weights, personal audio,
  logs, SQLite data, generated outputs, response-bearing evaluation reports. External chat, search,
  and memory providers stay explicit opt-ins.
  → [conventions.md](airi_docs/참조/claude-guide/conventions.md#security-and-configuration)
- **Default tests are offline and deterministic** (no GPU, services, models, or installed AIRI
  archive). A new Python test file under a sharded root must be added to the CI matrix, and
  count-floored suites need their floor raised.
  → [commands-and-tests.md](airi_docs/참조/claude-guide/commands-and-tests.md#ci-matrix-and-count-floors)
- **Serena is not used**; navigate with the built-in tools and `rg`.
  → [conventions.md](airi_docs/참조/claude-guide/conventions.md#code-navigation)
- **Measurements need receipts**: a number counts only with a recorded command, exit code,
  artifact, and SHA. → [docs-map.md](airi_docs/참조/claude-guide/docs-map.md#measurement-bar)

## Category files (`airi_docs/참조/claude-guide/`)

| File | Contents |
|---|---|
| [architecture.md](airi_docs/참조/claude-guide/architecture.md) | runtime data flow, components (incl. live briefing selection, simulator, System1), local assets |
| [commands-and-tests.md](airi_docs/참조/claude-guide/commands-and-tests.md) | start/stop, test commands, CI shards and count floors, known local test baseline |
| [patching.md](airi_docs/참조/claude-guide/patching.md) | patch artifacts, deploying the patched ASAR, rollback |
| [conventions.md](airi_docs/참조/claude-guide/conventions.md) | code style, commits and PRs, security and configuration, code navigation |
| [docs-map.md](airi_docs/참조/claude-guide/docs-map.md) | `airi_docs/` folder semantics, entry points, handoff lineage, measurement bar |
| [goal-state-policy.md](airi_docs/참조/claude-guide/goal-state-policy.md) | session start, heartbeat and checkpoints, long-goal state policy |
