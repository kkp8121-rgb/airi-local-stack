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
