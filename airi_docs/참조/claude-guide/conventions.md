# Conventions

Split out of `CLAUDE.md` on 2026-09-24 (merges the former `CLAUDE.md` conventions section and its
imported copy of the `AGENTS.md` guidelines). `AGENTS.md` remains authoritative.

## Coding style

Follow the surrounding file. No repository-wide formatter is configured, so check whitespace with
`git diff --check -- . ':(exclude)airi_docs/patches/*.patch'`.

- Python: 4 spaces, `snake_case`, `PascalCase` classes, type hints, uppercase constants.
- JavaScript: 2 spaces, ESM imports, single quotes, `camelCase`, **no semicolons**.
- PowerShell: 4 spaces, PascalCase parameters, approved `Verb-Noun` functions, `Set-StrictMode` /
  `$ErrorActionPreference = 'Stop'`.
- Tests are colocated: `test_*.py` (pytest), `test-*.mjs` (`node:test`), `test-*.ps1` (contract
  checks). Root-level tests cover cross-component scripts.
- Upstream snapshots (`chatterbox/`, `faster-qwen3-tts/`, `Qwen3-TTS-Openai-Fastapi/`, `external/`)
  are documented in `THIRD-PARTY-SOURCES.md`; keep changes to them easy to audit.

## Commits and pull requests

- Commits: Conventional-Commit subjects (`fix:`, `test:`, `docs:`, `ci:`, `feat:`), short and
  imperative, unrelated changes separated.
- Do not commit or push unless the current session explicitly authorizes it — much of this repo's
  workflow is deliberately local-only until a receipt exists. Push needs the user's approval every
  time. As of 2026-09-24 local `main` is ahead of `origin/main` with no push (exact state: the live
  state's `git_head` / `worktree_state` and `git status`).
- Pull requests should explain behavior, identify affected services or patches, list verification
  commands and results, and link relevant issues. Include screenshots or latency/audio evidence for
  UI, playback, or performance changes.

## Security and configuration

- Never commit `.env`, credentials, model weights, personal audio, logs, SQLite runtime data, or
  generated outputs (`.gitignore` excludes these intentionally). Response-bearing evaluation
  reports, simulation transcripts, and runtime packets stay out of Git (for the live simulations:
  under `C:\AIRI-Models\airi-human-eval\`).
- External chat, search, and memory providers must remain explicit opt-ins.
- New proxy behavior for live broadcasts ships default-off (for example
  `AIRI_LIVE_BRIEFING_CANDIDATES`); operational adoption needs a separate user decision.
- Do not weaken localhost bindings or unpin CI dependencies without documenting the security impact.
- Redact credentials, tokens, `.env` values, and personal paths from recorded commands.

## Code navigation

Serena is not used and must not be reintroduced or assumed (see
`airi_docs/진행중/AIRI-CODEX-SERENA-TOKEN-ORDER-2026-08-20.md` — measured net token loss). Use the
built-in file/search tools and `rg`, narrowed to the range you actually need, for symbol lookups,
references, and cross-file renames as well as for text search and running shells/tests.

### 코드 탐색 정책 (2026-08-23)

- Serena는 사용하지 않는다. 설치·연결·재도입·의존을 작업 전제로 두지 않는다.
- 심볼·참조·타입 계층·cross-file rename/move도 repository built-in 도구와 `rg`로
  필요한 범위만 좁혀 확인한다.
- 1~2줄 수정, 자유 텍스트/문자열 검색, 설정·JSON·픽스처·ps1·md 파일,
  쉘·git·테스트 실행도 기존 built-in 도구를 사용한다.
