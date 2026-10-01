# Documentation map

Split out of `CLAUDE.md` on 2026-09-24. `AGENTS.md` remains authoritative.

## Folder semantics

`airi_docs/` is organized by state, and the folder decides how much a claim is worth:

| Folder | Meaning |
|---|---|
| `진행중/` | current contracts (treat as branch state) |
| `진행예정/` | approved-but-unstarted plans (read before starting) |
| `로드맵/` | roadmap (log every work batch in `AIRI-ROADMAP-LOG.md`) |
| `완료/` | valid evidence for finished work |
| `보류/` | paused work |
| `아카이브/` | superseded — **never** use for verifying current state |
| `참조/` | timeless reference (this guide lives in `참조/claude-guide/`) |
| `patches/` | pinned artifacts (see [patching.md](patching.md)) |

Start at `airi_docs/AIRI-CURRENT-DOCS-INDEX-2026-08-10.md`, which is kept current despite its
filename.

## Entry points for the current work

- Live SSoT: `airi_docs/진행중/AIRI-WORKING-STATE.md` (frontmatter `goal_status`, `git_head`,
  `worktree_state`, `active_trainer_count`, `current_handoff`; receipts such as `sim10_receipt`).
- Current handoff: `airi_docs/진행중/AIRI-HANDOFF-2026-10-01.md` — state, held-out benchmark and
  candidate-judge results, new pitfalls, next steps. The previous handoff
  `airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-09-30.md` keeps the stack how-to (§4) and the standing rules and
  pitfalls (§5); its detail doc `airi_docs/진행중/AIRI-BROADCAST-READINESS-HANDOFF-2026-09-29.md` covers the
  broadcast-readiness rounds with persona-v4 (§8-1 to §8-11); earlier: `AIRI-PERSONA-RP-HANDOFF-2026-09-26.md`
  for the RP decisions, `AIRI-LIVE-BROADCAST-HANDOFF-2026-09-24.md` for the simulator how-to.
- Held-out benchmark (how improvements are judged): `airi_docs/진행중/AIRI-HELDOUT-BENCHMARK-2026-10-01.md`;
  decision-model (Jev-style, Ollama `/v1/systemone`) comparison: `airi_docs/진행중/AIRI-DECISION-MODEL-EVAL-2026-10-01.md`.
- System1 (Jev) candidate-judge plan and results: `airi_docs/진행중/AIRI-SYSTEM1-CANDIDATE-JUDGE-2026-09-23.md`
  (§0-§6 the 2026-09-23 plan, §7 the v2 scenarios, §8 the live-broadcast simulations).
- Roadmap: `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md` (user dashboard and M8 checklist; the
  live-broadcast tuning is not an M8 item and does not change the M8 numbers) and
  `airi_docs/로드맵/AIRI-ROADMAP-LOG.md`.
- `NEXT-SESSION.md` — next-session entry note.

## Handoff lineage

- `airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-09-30.md` — end of the 2026-09-30 session (written for Codex),
  superseded as the current handoff on 2026-10-01 evening; §4 and §5 stay valid.
- `airi_docs/진행중/AIRI-GPU-PC-HANDOFF-2026-09-01-STAGE3.md` — M8 Stage 3 on the GPU PC. Stage 3,
  M8-10 and Stage 4 ran after it; their results live in the `m8_*` / `stage4_*` receipts of
  `AIRI-WORKING-STATE.md`. Its asset locations remain valid.
- Section 0-A of `airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-08-27.md` is still valid for where every
  GPU-PC asset lives; its M7 verdict is not.
- `airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-08-21.md`, `NEXT-SESSION.md` and the roadmap carry the old
  E2 contract markers (`execution_order=...`, `adoption_authorized=false`) pinned by
  `test-airi-work-continuity.ps1`; the `execution_order` marker is not the current work order.

## Measurement bar

Measurements here are held to a high bar: a number counts as verified only with a recorded command,
exit code, artifact, and SHA. Do not promote a synthetic or partial measurement to a completed goal.
Live-broadcast simulation readings so far are AI readings; human judgement is still pending.
