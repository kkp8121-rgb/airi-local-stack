# AIRI Local Temporary and Failed-Model Cleanup — 2026-08-13

## Result

The related goal was blocked because explicit authorization for Cloud and
YouTube transmission/spend was absent and every extraction candidate failed its
gate. It was not blocked by context exhaustion. The user then requested local
cleanup. No implementation code, patch, installed AIRI, or production service
was changed; nothing was pushed. This evidence update is committed locally only.

## Removed

| Category | Removed | Deletion-time measured space |
|---|---|---:|
| Failed Ollama candidates | `ministral-3:3b-instruct-2512-q4_K_M`, `phi4-mini:3.8b-q4_K_M`, `granite3.3:2b`; 13 unique unshared blobs | 6.511 GiB |
| Old ignored generated artifacts | `.codex` ASAR/runtime-package/patch-check directories and three obsolete ignored `airi_docs` ASARs | 37.882 GiB |
| Generated staging output | `node_modules`, `.cache`, `.turbo`, `dist`, and `out`; empty `node_modules` directories may remain | 2.167 GiB |
| Python generated metadata | caches and egg-info | 20.07 MiB |
| Clean registered worktree | obsolete feature-audit worktree | 18.43 MiB |

Approximate free space on C: increased from 12.41 GiB to 58.99 GiB: about
46.58 GiB net.

## Preserved

- Current and authoritative git worktrees, staging source checkout at clean HEAD
  `bf173f2d`, and the `verify` and `verify2` trees.
- Python 3.12 audit virtual environment, runtime databases/logs, patches, and
  evidence JSON.
- Installed AIRI and production services.

## Recovery boundary

The removed data is not recoverable from the recycle bin. The removed models,
dependencies, generated builds, and clean worktree are reproducible; the tracked
evidence reports remain available. Failed extraction candidates remain removed,
and extraction remains OFF pending a separately recorded passing gate and the
required approvals.
