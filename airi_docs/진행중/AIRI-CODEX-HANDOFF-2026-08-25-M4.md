# AIRI M4 Codex 인수인계 — 결정론 계층 운영 경로 배선 수정 + blind v6 재측정 (2026-08-25)

> **이 문서가 Codex의 단일 진입점이다.** 읽는 순서: `AGENTS.md` →
> `airi_docs/진행중/AIRI-WORKING-STATE.md`(전체) → **이 문서** →
> `airi_docs/진행중/AIRI-D1-DETERMINISTIC-LAYER-CONTRACT-2026-08-25.md` §6·§7 →
> `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md` → `NEXT-SESSION.md`. 읽은 뒤 `git status`, HEAD,
> 실행 중 PID, owned 포트를 **read-only로 대조**하고 나서야 실행한다. 채팅 요약을 믿지 않는다.
> 작성: Claude main 세션(airi-d6), 2026-08-25 21:39 KST, HEAD `91792a1`.

## 0. 인계 시점 상태 (관측값)

| 항목 | 값 |
|---|---|
| HEAD = local main = origin/main | `91792a1` (`docs: register parallel batch documents and record the merge receipt`) |
| worktree | clean. 병렬 branch `feature/parallel-offline-20260825`는 `9ccf870`로 main에 병합 완료 |
| 실행 중 프로세스 | AIRI 0 (상시 `ollama serve` PID 18616 제외). owned 포트 11435/11436/8880/9880/8890/8892 free |
| GPU | RTX 3060 Ti 8GB 유휴. **M4는 GPU 학습이 없다** (추론 matrix만) |
| 마지막 verdict | d1v5 `D:\AIRI-Models\airi-d1v5-blind-matrix-20260825\run\comparisons\d1-blind.json` — `winner=null`, 실패 38 게이트 |
| 소비된 blind | v1·v2·v3·v4·**v5** 전부 소비. 재사용·재실행 금지 |
| adoption | `false` 고정. campaign 결과와 무관하게 별도 사용자 승인 |
| 알려진 기존 실패 | `ollama-proxy/training/tests/test_synthesize_broadcast_behavior_v2.py` 2건(병합 전부터, CI matrix 포함) — M4 범위 밖, 건드리지 말고 기록만 유지 |

## 1. 오늘까지 끝난 것 (전부 origin/main)

| 배치 | 내용 | commit |
|---|---|---|
| M1 | 프록시 오류 메시지 기록(`local_error_detail`), `service_error` 지표, P3 probe/confirmation 분류 | `aed7562` |
| M1 | 근본 원인 확정: Ollama 400 `exceed_context_size_error`(n_prompt_tokens 2,552~2,827 > 2,048) | `12f0feb` |
| M1 | 브리핑 마커(`BRIEFING_EVIDENCE_MARKER`) — **live 모드에서는 무효였음(§2)** | `714e196` |
| M2 | `num_ctx` 2048→4096, `context_exceeded_observations`, campaign F7 게이트, 검토 문서 편입 | `6450a96`~`50041f1` |
| M2 | lm-eval·llama.cpp perplexity greybox 기준선 (`완료/AIRI-M2-GREYBOX-EVAL-2026-08-25.md`) | `956a226`, `bae4e4a` |
| M3 | native_baseline 픽스처 핀 수리, 일반 능력 게이트(`verify_general_capability_gate.py`, ≤2%p) | `2061f10` |
| M3 | blind v5 봉인, launcher `d1v5`, seal `d1v5` generation, commitment/tests | `e9eed2f` |
| M3 | d1v5 48-report matrix(exact-once, 17:35→21:15) + verifier v5 수용 + verdict + 진단 | `07ad82f`, `e6880ab` |
| 병렬 | legacy T3 comparator F5/F6, 게이트 evidence 바인딩, P2-4b 오프너(off), P3-T4 설계안 | `9ccf870`(merge) |

d1v5 결과 핵심: 계측은 작동한다(`service_error` 0/1,132×4, memory_probe 36/40,
`unknown_identity_safe` 학습 arm 1.0, 점수 0.34~0.37). 남은 실패는 §2의 배선 결함에 귀결된다.

## 2. 확정된 결함 — 코드 위치 (라인은 `91792a1` 기준)

**결정론 계층(P3/P4/P5)은 운영 프로토콜(live-broadcast)에서 근거를 받지 못한다.**

1. 시뮬레이터/디렉터는 live 모드에서 system 메시지를 보내지 않는다:
   `ollama-proxy/eval/broadcast_sim/run_broadcast_sim.py:540`
   `messages = [] if live_broadcast else [{"role": "system", ...}]`. 브리핑·후원 계약은
   `live_context_for_turn(...)`(`:209`) → 요청의 `broadcast_context`로 간다.
2. 프록시는 그것을 `live_broadcast_runtime.render_broadcast_context`(`:98`~`:125`)로 note를
   만들어(`BROADCAST_BRIEFING_HEADER` 첫 줄 검사 `:113`, 브리핑 이어붙임 `:123`,
   `DONATION_CONTINUATION_CONTRACT` `:125`) `inject_live_broadcast_notes`(`ollama_proxy.py:4884`,
   호출 `:8977`)로 **body에 system note `airi_broadcast_context`를 주입**한다.
3. 그런데 계층 입력은 `ollama_proxy.py:7612`
   `build_layer_inputs(..., original_messages=context.original_messages)`이고,
   `context.original_messages`는 `:8935` `request_messages(original_body)` — **주입 전
   클라이언트 메시지**다. 따라서 `deterministic_utterance_layer.build_layer_inputs`(`:376`)의
   system 스캔(마커 `:365`, `system_briefing_evidence` `:368`, `DONATION_CONTINUATION_MARKER`)은
   live 모드에서 아무것도 보지 못한다.
4. 결과(d1v5 실측): P3 폴백 continuity_callback 62~65/80(arm별), `briefing_evidence_released`
   0/80, P5 `donation_turn` 항상 false → donation composite miss 29~39/52 전부
   `shared_tokens=false`, P4 결정 풀 비어 있음. `714e196`의 마커는 시뮬레이터
   `system_content`(live 모드 미전송)에 붙어 효과 0. **D1(v4)에도 동일했던 결함이다.**

부수 결함(같은 라운드에서 함께 닫을 것):
- **P3 추출 정규식** `deterministic_utterance_layer.py:85` `_REJECTED_BRANCH_RE`는 `말고` 앞뒤가
  단일 토큰 2~12자여야 해서 "가득 **말고 팔** 할만", "한 번씩 말고 두 번씩", "끝 장 말고 첫
  장부터", "젖은 천 말고 마른 천으로", "점등 뒤 말고 점등 전에"(v5 arc 12개 중 5개)를 못 잡는다.
- **blind handle 설계**: v5 viewer handle이 주제 명사 합성어(채밀칼날·훈연기연기·태엽감기…)라
  주제 발화가 roster 부분일치에 걸려 `invented_handle` 7/17/11/9가 대부분 채점 artefact였다.
  v6 저작·봉인 검사에서 handle과 주제 어휘(beat anchors·templates·seed/callback 본문)의
  부분일치를 금지해야 한다.
- 채점기 `broadcast_sim._tokens`가 조사를 안 벗겨 "손질값이"≠"손질값"(donation shared_tokens),
  `A가 아니라 B` 부정 교정문이 decoy 금지 패턴에 걸림 — **게이트 정의 변경이라 사용자 결정
  사항**. 이번 라운드에서 손대지 않는다. 진단 문서에만 유지.

## 3. M4 작업 계약 (순서 고정, 각 단계 verify 후 다음)

### 3.1 계층 입력 배선 수정 (프록시)
- `ollama_proxy.py` `:7612` 호출이 **주입 후** 메시지를 보게 한다. 권장: `inject_live_broadcast_notes`가
  만든 body의 messages(또는 `context_note` 문자열)를 `build_layer_inputs`에 별도 인자
  (`live_context_note=`)로 전달하고, `build_layer_inputs`가 그것을 system 부분으로 취급한다.
  `original_messages` 의미는 바꾸지 않는다(다른 소비자가 있다).
- `live_broadcast_runtime.render_broadcast_context` `:122-123`에서 브리핑을 note에 붙일 때
  **프록시 소유 마커** `deterministic_utterance_layer.BRIEFING_EVIDENCE_MARKER`를 앞에 붙인다
  (`note += '\n\n' + MARKER + '\n' + briefing`). 헤더 검사(`:113`)는 들어오는 브리핑 원문에 대한
  것이므로 유지. 시뮬레이터 측 `BRIEFING_EVIDENCE_BLOCK_MARKER`(`run_broadcast_sim.py`)는 비-live
  경로용으로 남기되 주석에 "live 경로는 runtime이 마커를 붙인다"를 명기.
- `DONATION_CONTINUATION_CONTRACT`가 note에 있을 때 `donation_turn=True`가 되는지 확인
  (문자열은 이미 `[후원 본문 이어말하기]`로 동일).
- **verify**: 아래 3.2 통합 테스트가 수정 전 FAIL → 수정 후 PASS. `test_ollama_proxy` 전량,
  `test_deterministic_utterance_layer`, `test_live_broadcast_runtime` 통과. flag off 경로
  바이트 무변화 회귀 유지.

### 3.2 live 경로 통합 테스트 (없어서 두 라운드를 놓쳤다)
- `ollama-proxy/test_ollama_proxy.py`에 live-broadcast 요청 픽스처를 추가: `broadcast_context.briefing`에
  `BROADCAST_BRIEFING_HEADER` + `- 이 시청자가 아까 "등불신호는 붉은빛 말고 초록빛으로 걸자"라고
  했었어…`, 사용자 발화 "등불 신호는 무슨 빛으로 걸기로 했지?" → SSE 최종 텍스트에 `초록빛`,
  `airi_moderation` 신호 `recall == "answered"`. 두 번째 픽스처: `donation_continuation=true` +
  공유 토큰 0 초안 → P5 인용문이 붙는지. 두 플래그 ON 조건에서만, OFF면 무변화.
- **verify**: 신규 테스트가 `07ad82f` 트리에서는 실패함을 먼저 보인다(회귀 민감성 증명).

### 3.3 P3 정규식 확장
- `_REJECTED_BRANCH_RE`를 1글자 토큰·띄어쓴 구(최대 2어절)까지 받도록 확장. 오프라인
  테스트: v5 continuity arc 12개 seed(`D:\AIRI-Models\airi-d1-blind-freeze-20260825-v5\long_continuity_and_stale_transition.json`,
  채점 완료라 열람 가능)로 12/12 추출 + 기존 25+ 테스트 유지. 오탐 방지: `_COMMON_STOPWORDS`
  분기는 유지.

### 3.4 blind v6 저작·봉인
- 외부 staging `D:\AIRI-Models\airi-d1-blind-staging-v6\`에 새 한국어 fixture 3종(v1~v5와 다른
  설정; 사용된 설정 목록은 `AIRI-PARALLEL-HANDOFF`가 아니라 각 봉인 root의 `topic.title`로 확인).
  **handle 규칙**: 2~6음절, beat anchors·archetype templates·seed/callback/donation 본문의
  어떤 토큰과도 부분일치 금지. 이 검사를 `seal_e2c2_blind.py`에 `check_handle_topic_collision`
  으로 추가하고 v6 generation(`d1v6`: v5 superseded — hash는
  `fixtures/commitments/airi_d1v5_blind_commitment.json`의 raw/canonical 6개 + root id)에서 강제.
- `--check --generation d1v6 --superseded-root <v1..v5 5개>`가 PASS하면 root id
  `airi-d1-blind-freeze-20260825-v6`(또는 실행일)로 봉인. 봉인 전 `--check` 결과를 **직접 재실행**해
  pins 대조(위임 결과 그대로 채택 금지).
- 리포: `airi_d1v6_blind_commitment.json`(d1 commitment와 key set 동일), launcher `d1v6`
  (`$isDeterministicLayerProfile`에 추가, 바인딩 분기만 신규), `verify_d1_frozen_contract.py`
  `ROOT_GENERATIONS`에 v6 추가, `test_d1v6_blind_commitment.py` + launcher 계약 클래스, CI matrix
  등록, `test-patch-manifest.ps1` PASS. **comparator를 v6 commitment로 오프라인 실행할 수 있는지
  (합성 48 report로) 먼저 확인** — d1v5는 이 확인이 없어 종료 단계에서 실패했다.

### 3.5 matrix exact-once → verdict 분기
- root `D:\AIRI-Models\airi-d1v6-blind-matrix-<date>\`, model manifest는
  `D:\AIRI-Models\airi-d1-blind-matrix-20260825\d1-model-manifest.json`(sha `050ae10f…e330`) 복사,
  wrapper는 `launch-d1v5-matrix.ps1` 구조(exit-code receipt no-overwrite). `-PreflightOnly` 48/48
  → WORKING intent commit/push → `Start-Process` 1회 → start receipt JSON → 12~14분 heartbeat
  read-only 감시(약 3시간 40분). 첫 3 report에서 두 플래그 attest·`context_exceeded 0`·
  `service_error 0` 조기 확인.
- winner → `run-airi-live-broadcast-campaign.ps1`에 **`-ComparatorVerdict <verdict.json>
  -ModelManifest <retained manifest>`**를 반드시 넘긴다(F7 게이트). seeds 101,202,303 × 500턴.
  no_winner → campaign 0, 진단(P2~P5 row 귀책) 후 대기. 어느 쪽이든 adoption=false.

## 4. 환경 함정 (오늘 실측)

- **인터프리터**: pytest는 `D:\AIRI-Models\venv-midm-broadcast-qlora-py312\Scripts\python.exe`;
  `fastapi/httpx` 필요한 `test_ollama_proxy.py`·`test_live_broadcast_runtime.py`·rehearsal은
  `C:\Users\kkp74\AppData\Local\Microsoft\WindowsApps\python.exe`(3.14)로 `unittest`. 서비스·
  시뮬레이터는 `C:\Projects\airi\stt\.venv\Scripts\python.exe`.
- **Windows PowerShell 5.1**: native 프로세스의 stderr를 `NativeCommandError`로 승격한다
  (`$ErrorActionPreference=Stop`). `cmd.exe /c` 리다이렉트 경로는 lm_eval에서 hang했다 — 긴
  Python 작업은 Git Bash에서 `nohup`으로 돌리고 로그를 root에 남겨라.
- **uv venv python.exe는 트램폴린**: 실제 인터프리터는 자식 PID. 프로세스 확인 시 부모만 보면
  "CPU 0초·5MB"로 오해한다.
- **열린 로그 파일 크기**: 디렉터리 메타데이터는 stale. `[IO.File]::Open(...,'ReadWrite')`로 stream
  length를 읽어라.
- **단일 working tree 사고**: 병렬 세션이 `C:\Projects\airi`에서 `git checkout -b`를 해 실행 중
  matrix가 import하는 파일이 바뀌었다. 병렬 작업은 반드시 `git worktree add <다른 경로> <branch>`.
  matrix 실행 중에는 이 tree의 `ollama-proxy/**`·`run-airi-*.ps1`을 절대 바꾸지 않는다.
- **시각 기록**: 문서 시각은 `Get-Date`/commit 시각으로 확인해 적는다(오늘 추정 시각이 최대
  1시간 앞서 기록돼 정정했다).
- `test_airi_native_baseline` 핀은 오늘 고쳤다. `test_synthesize_broadcast_behavior_v2` 2건은 기존
  실패(범위 밖).
- work-continuity 계약: `AIRI-WORKING-STATE.md` frontmatter `goal_status`는 `active|paused|complete|blocked`
  만 허용, `git_head`는 40자 SHA, 세 문서의 `goal_status=active` 리터럴과 일치해야 한다.
  commit 전 `.\test-airi-work-continuity.ps1`를 돌려라(오늘 한 번 실패한 채 push됐다).

## 5. 검증 명령

```powershell
D:\AIRI-Models\venv-midm-broadcast-qlora-py312\Scripts\python.exe -m pytest -q ollama-proxy/eval/broadcast_sim ollama-proxy/eval/affect_broadcast ollama-proxy/training/tests test_broadcast_t3_matrix_launcher_contract.py test_live_campaign_launcher_contract.py
C:\Users\kkp74\AppData\Local\Microsoft\WindowsApps\python.exe -m unittest test_ollama_proxy test_live_broadcast_runtime   # ollama-proxy 디렉터리에서
D:\AIRI-Models\venv-midm-broadcast-qlora-py312\Scripts\python.exe -m pytest -q ollama-proxy/test_deterministic_utterance_layer.py ollama-proxy/test_handle_grounding_guard.py
.\test-patch-manifest.ps1; .\test-current-checkpoint.ps1; .\test-airi-work-continuity.ps1
git diff --check -- . ':(exclude)airi_docs/patches/*.patch'
```

## 6. 금지선 (goal 원문 + 오늘 추가)

GPU 재학습·새 후보 학습, blind v1~v5 재사용·재실행, hard gate·threshold·metric·seed·fixture
정의 변경, 운영 서비스 모델/태그 변경, 외부 provider/extraction/greybox 기본 ON, T-05 126번
승격, campaign 결과의 운영 채택 간주, 사용자 변경 reset/checkout/revert, `no_winner` 뒤 자동
후속 라운드, 이 tree에서의 branch checkout(병렬은 worktree), matrix 실행 중 import 대상 파일
수정, `AIRI-WORKING-STATE.md` 외 heartbeat dirty 파일 방치, 위임 결과의 무검증 채택.

## 7. 기록 의무

단계마다 `AIRI-WORKING-STATE.md` intent/receipt(10분 이상 명령은 전후 필수, matrix 중 14분
heartbeat), 배치마다 `AIRI-ROADMAP-LOG.md`, milestone·권한 변경 시 이 문서·ROADMAP-STATUS·
NEXT-SESSION 갱신, 검증 후 Conventional Commit으로 exact stage → commit → push →
HEAD/local/origin exact·worktree clean 재확인.
