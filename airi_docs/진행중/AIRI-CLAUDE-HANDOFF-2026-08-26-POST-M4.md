# AIRI Claude 인수인계 — M4 종료와 다음 결정론 계층 라운드 준비 (2026-08-26)

> **2026-08-26 11:29 KST 대체 고지:** 사용자가 §4 Goal을 제출해 M5가 시작됐고 step 1~3(진단·수리·검증)은
> 완료됐으나, 사용자 결정 (C)로 step 4 이후(blind v7 저작·seal·matrix·campaign)는 **공회전으로 판정돼
> 중단·대체**됐다. 현재 단일 진입점은 `AIRI-REALITY-CHECK-AND-FINETUNE-REVIEW-2026-08-26.md`이며 이 문서의 §4·§5는
> 이력으로만 남는다.

> **(이력) Claude Code의 단일 진입점이었다.** 먼저 `AGENTS.md` →
> `airi_docs/진행중/AIRI-WORKING-STATE.md` 전체 → **이 문서** →
> `airi_docs/진행중/AIRI-D1-DETERMINISTIC-LAYER-CONTRACT-2026-08-25.md` §8·§9 →
> `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md` → `NEXT-SESSION.md` 순서로 읽는다.
> 그 뒤 실제 HEAD/local/origin/remote, worktree, PID/command line, owned 포트와 d1v6
> terminal 산출물을 읽기 전용으로 대조한다. 채팅 요약만으로 이어서 실행하지 않는다.

이 문서는 자신을 포함한 최종 문서 commit SHA를 자가 참조하지 않는다. Claude는 이 파일이
`origin/main`에서 실제로 도달 가능한지 먼저 확인해야 한다. 도달하지 않거나 저장소 상태가 아래
관측과 다르면 새 작업을 시작하지 말고 `AIRI-WORKING-STATE.md`와 대시보드를 실제 상태로 먼저
정정한다.

## 0. 인계 결론

- M4는 **완료**다(`goal_status=complete`). live 결정론 입력 배선, red/green 통합 테스트,
  P3 rejected-branch 확장, fresh blind v6 봉인·계약, exact-once 48-report matrix, verdict 진단,
  사용자용 대시보드와 Codex/Claude 공용 skill까지 검증했다.
- d1v6 verdict는 `winner=null`(`no_winner`, 실패 gate 29개)다. 따라서 조건부 3×500 campaign은
  `[N/A]`이며 실행하지 않았고, retained/adopted model도 없다.
- 사용자 승인에 따라 M4 로컬 commit 묶음과 이 Claude 인계 배치를 한 번의 최종 push로
  게시한다. 이 문서의 기준 parent HEAD는
  `09de314c84c2a075ddaab99e0bab4968a04b78f0`; Claude는 실제 최종 remote SHA를 직접 읽는다.
- 운영 채택·운영 모델/태그 변경은 승인되지 않았다(`adoption_authorized=false`). 다음 M5는
  아래 Goal 명령을 사용자가 Claude 세션에 실제로 입력한 뒤에만 시작한다.

## 1. M4 완료 증거

### 코드·회귀

- `original_messages` 의미를 보존한 채 인증·주입된 live `context_note`를 결정론 계층 입력으로
  전달한다. runtime은 브리핑에 server-owned `BRIEFING_EVIDENCE_MARKER`를 붙이고
  `DONATION_CONTINUATION_CONTRACT`로 P5 `donation_turn`을 활성화한다.
- 신규 live P3 recall/P5 donation 통합 테스트는 pre-fix `07ad82f`에서 2 FAIL, 수정 tree에서
  2 PASS였다. flag OFF outbound bytes exact 회귀도 유지한다.
- `_REJECTED_BRANCH_RE`는 1글자 토큰과 최대 2어절을 받고, 소비된 v5 continuity arc 12개를
  읽기 전용 진단 입력으로 대조해 12/12를 추출했다.
- fresh blind v6는 v1~v5와 다른 한국어 설정 3종이며 handle-topic collision 0으로 봉인됐다.
  commitment·launcher d1v6 binding·verifier generation·tests·CI·synthetic 48-report comparator를
  모두 먼저 검증했다. blind 원문은 Git에 없다.

### d1v6 terminal receipt

- 외부 root: `D:\AIRI-Models\airi-d1v6-blind-matrix-20260825`
- wrapper exit-code receipt: `0`
- report·health·run-contract·packet: 각 48개, 고유 union/intersection 48/48,
  duplicate·missing 0
- summary: `airi.t3-matrix-launcher.v2`, `status=pass`, `run_count=48`
- comparison: `airi.d1-blind-comparison.v1`, `status=pass`, `report_count=48`,
  `winner=null`, `adoption_authorized=false`
- 두 결정론 flag: 48/48 before·after true; `context_exceeded=0`, `service_error=0`
- wrapper·관련 child process·owned listener 0; 포트 11435/11436/8880/9880/8890/8892 free

### 최종 검증

- M4 affected clean run: 739 passed, 9 skipped, 297 subtests
- proxy/runtime: 403 OK
- deterministic layer/handle guard: 52 passed + 10 subtests
- patch manifest, current checkpoint, work continuity, roadmap dashboard contract: PASS
- Codex skill `quick_validate.py`: `PYTHONUTF8=1`에서 PASS
- 알려진 기존 경계: pinned Python 3.12에는 continuity-v4가 요구하는 `httpx`가 없어 해당 파일은
  WindowsApps Python으로 8/8 OK를 확인했다. `test_synthesize_broadcast_behavior_v2.py` 2건은
  M4 전부터 존재한 실패이며 별도 과제다.

## 2. no_winner 귀책과 다음 문제

| 축 | d1v6 결과 | 다음 라운드 판단 |
|---|---|---|
| P5 후원 이어말하기 | 전 arm donation composite 1.0 | 닫힘. 새 동작을 넓히지 말고 회귀만 유지 |
| P4 거부 선택 억제 | 전 arm decoy 0.0 | 닫힘. transition 잔여는 대부분 P3 required miss |
| P3 결정·사실 회수 | identity probe miss와 stale required miss가 지배 | 필수 답변/회수 predicate와 렌더링을 공개·합성 회귀로 분리 수리 |
| P2/P1 호명 | baseline 2, e2-c2 3 invented handle | v6 collision 0이므로 실제 question-row 잔여 경로를 진단·가드 |
| 공통 말투 | polite 위반 baseline 45, 나머지 43; 공통 43행은 opinion | P2~P5와 분리된 hard-zero 차단축으로 별도 처리 |

점수는 baseline 0.465862, e2 0.543016, e2-c1 0.510247, e2-c2 0.557373이지만 최고 점수
e2-c2도 자기 gate 10개를 실패했다. top score를 winner·retained model로 해석하지 않는다.
상세 row 귀책은 D1 contract §8이 권위다.

## 3. 인계 경계

- blind v1~v6는 모두 소비됐다. 재사용·재실행·재봉인하지 않는다.
- GPU 재학습·새 후보 학습, hard gate·threshold·metric·seed·fixture 정의 변경, 운영 서비스
  모델/태그 변경, 외부 provider/extraction/greybox 기본 ON, T-05 126번 승격을 금지한다.
- M4 `no_winner` 뒤 자동 후속 라운드는 금지됐다. 아래 M5 명령은 **사용자가 Claude에 실제로
  붙여 넣을 때만** 새 명시적 Goal이 된다. 이 문서의 존재나 repository pull만으로는 권한이 없다.
- M5도 winner일 때만 campaign을 실행하고, no_winner면 실패 축을 진단한 뒤 사용자 결정을
  기다린다. 결과와 무관하게 운영 채택은 별도 승인이다.
- 병렬 작업은 현재 tree에서 branch checkout하지 않고 `git worktree add`로 분리한다.
- Codex와 Claude의 로드맵 규칙은
  `AIRI-ROADMAP-DASHBOARD-CONTRACT.md` 하나가 원본이다. Claude는 project-local
  `.claude/skills/airi-roadmap-dashboard/SKILL.md`를 자동 발견한다.

## 4. Claude에 전달할 다음 Goal 명령

아래 블록을 사용자 메시지로 그대로 입력한다. 입력 전에는 M5가 승인된 것이 아니다.

```text
/goal [M5 — d1v6 no_winner 잔여 게이트 분리 수리 + fresh blind v7 재측정]

단일 진입점: airi_docs/진행중/AIRI-CLAUDE-HANDOFF-2026-08-26-POST-M4.md

시작 프로토콜: AGENTS.md → airi_docs/진행중/AIRI-WORKING-STATE.md(전체) → 위 Claude handoff →
airi_docs/진행중/AIRI-D1-DETERMINISTIC-LAYER-CONTRACT-2026-08-25.md §8·§9 →
airi_docs/로드맵/AIRI-ROADMAP-STATUS.md → NEXT-SESSION.md 순서로 전부 읽고, 채팅 요약을 믿지 말고
git status / HEAD·local·origin·remote / 실행 중 PID·command line / owned 포트
(11435,11436,8880,9880,8890,8892) / d1v6 terminal 산출물을 read-only로 대조한 뒤에만 실행한다.

수행 순서(각 단계 fresh verify 후 다음):
1. 채점 완료된 d1v6 report를 진단 입력으로만 사용해 P2 잔여 invented_handle 5행, P3 identity·
   stale required miss, 공통 polite opinion 43행을 서로 겹치지 않는 원인으로 분류한다. blind v6를
   새 평가에 재사용하거나 결과를 보고 gate·threshold·metric·seed 정의를 바꾸지 않는다.
2. GPU 학습 없이 최소 결정론 수리를 red/green으로 구현한다. P5 donation과 P4 decoy의 닫힌
   동작은 byte/behavior 회귀로 보존하고, P3 필수 회수·P2 근거 없는 호명·opinion 말투 축을 별도
   테스트로 고정한다. 기존 결정론 flag OFF 경로는 outbound bytes exact를 유지한다.
3. affected offline 회귀와 기존 알려진 환경/behavior-v2 실패 경계를 분리해 검증한다. 새 후보
   학습, 운영 모델/태그 변경, 외부 provider 기본 ON은 금지한다.
4. 외부 staging에 v1~v6와 다른 새 한국어 blind v7 fixture 3종을 저작한다. 기존 seal 계약의
   topic/template/handle collision, body-free commitment, no-overwrite, direct --check pin 대조를
   유지하고 v1~v6 재사용·재봉인을 금지한다. hard gate·threshold·metric·seed·fixture 정의는
   변경하지 않는다. 실제 matrix 전에 v7 commitment로 synthetic 48-report comparator를 오프라인
   실행할 수 있음을 확인한다.
5. 실제 -PreflightOnly 48/48 → WORKING intent commit/push → detached no-overwrite wrapper로
   d1v7 48-report matrix를 정확히 한 번 시작하고 14분 이하 WORKING+ROADMAP heartbeat로 감시한다.
   첫 3 report에서 두 flag attest, context_exceeded 0, service_error 0을 확인한다.
6. winner이면 retained model manifest의 exact arm tag/digest와 comparator verdict를 campaign
   launcher에 넘겨 seeds 101,202,303 × 500턴 × NumCtx 4096을 새 external root에서 실행한다.
   no_winner이면 campaign·자동 후속 라운드 없이 failed/per-arm gates, violation/perfect/axis rates로
   P2·P3·말투 축을 진단하고 사용자 결정을 기다린다.
7. airi-roadmap-dashboard 공통 계약에 따라 단계별 WORKING intent/receipt, 장시간 14분 heartbeat,
   배치별 ROADMAP-LOG, milestone 시 handoff·ROADMAP-STATUS·NEXT를 동기화한다. 전체 검증 후 정확한
   파일만 Conventional Commit으로 stage·commit하고, push 직전 매번 사용자 승인을 별도로 받는다.

금지: GPU 재학습·새 후보 학습, blind v1~v6 재사용·재실행·재봉인, hard gate·threshold·metric·
seed·fixture 정의 변경, P4/P5 닫힌 동작 완화, 운영 서비스 모델/태그 변경, 외부 provider/
extraction/greybox 기본 ON, T-05 126번 승격, 결과의 운영 채택 간주, 사용자 변경 reset/checkout/
revert, no_winner 뒤 자동 후속 라운드, matrix 중 import 대상 수정, 위임 결과의 무검증 채택.
운영 채택은 결과와 무관하게 별도 사용자 승인 사항이다.
```

## 5. Claude 첫 응답의 완료 조건

Claude는 Goal을 받은 첫 턴에 새 matrix나 서비스를 시작하지 않는다. 먼저 다음을 사용자에게
증거와 함께 짧게 보고한다.

1. 실제 final HEAD가 local/origin/remote에서 일치하고 worktree가 clean인지
2. d1v6 48/48·exit 0·no_winner·관련 PID/listener 0이 유지되는지
3. P4/P5는 닫혔고 P2/P3/말투가 남았다는 계약 해석이 §8과 일치하는지
4. M5 첫 변경 배치의 exact 파일 경계와 red/green 검증 명령

불일치가 하나라도 있으면 실행하지 않고 관측 사실로 WORKING과 대시보드를 먼저 정정한다.
