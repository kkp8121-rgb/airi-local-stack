# Session start and long-goal state policy

Split out of `CLAUDE.md` on 2026-09-24. The same policy is part of `AGENTS.md`, which remains
authoritative; `test-airi-work-continuity.ps1` pins its wording in `AGENTS.md` and the live state.

## Session start protocol (non-negotiable)

Before running anything — at session start, goal resume, reboot, or right after a context compact —
read in this order and reconcile against real state (`git status`, HEAD SHA, running PIDs, artifact
SHAs) **read-only**:

1. `AGENTS.md`
2. `airi_docs/진행중/AIRI-WORKING-STATE.md` — the mutable live SSoT (YAML frontmatter carries
   `goal_status`, `git_head`, `worktree_state`, `active_trainer_count`, `current_handoff`, and the
   receipts)
3. the current handoff: `airi_docs/진행중/AIRI-LIVE-BROADCAST-HANDOFF-2026-09-24.md` (the
   live-broadcast simulation tuning track). Earlier handoffs and which of their parts stay valid:
   [docs-map.md](docs-map.md).
4. `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md`
5. `NEXT-SESSION.md`

Never resume from a chat summary alone. If live state disagrees with the machine, stop and correct
the record from observation before executing. Do not start a duplicate process without first
checking the exact command line of any running PID.

## Heartbeat and checkpoints

While a goal is active, refresh `AIRI-WORKING-STATE.md` at least every 120 minutes (30 during GPU
training, merge/package, T3 matrices, or long campaigns), and immediately on checklist completion,
process start/stop, checkpoint/hash/authorization/blocker changes, and pause/resume. Long or
state-changing commands get an **intent checkpoint** before and a **receipt checkpoint** after
(exit code, PID, artifacts, verification). No receipt means not complete. Redact credentials,
tokens, `.env` values, and personal paths from recorded commands.

## 장기 Goal 상태 보존 정책 (2026-08-22)

- 세션 시작, goal resume, 재부팅, compact/요약 직후에는 어떤 실행보다 먼저
  `airi_docs/진행중/AIRI-WORKING-STATE.md`를 **전체 읽고**, 실제 goal status,
  `git status`, PID/command line, 관련 산출물·SHA를 read-only로 대조한다.
  compact된 채팅 요약만 믿고 이어서 실행하지 않는다.
- active goal에서는 live state를 마지막 기록 후 **최대 120분** 안에 갱신한다.
  GPU 학습, merge/package, T3, 장시간 campaign 중에는 상한을 **30분**으로 줄인다.
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
