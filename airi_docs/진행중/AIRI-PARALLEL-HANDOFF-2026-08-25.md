# AIRI 병렬 오프라인 세션 인계 (2026-08-25)

> branch `feature/parallel-offline-20260825` 전용 기록. main 세션(d1v5 48-report matrix
> 감독, wrapper PID 28296)과 자원을 공유하지 않는 오프라인 작업만 수행했다. main
> commit/push 0, `AIRI-WORKING-STATE.md` 수정 0, GPU·서비스·포트·`D:\AIRI-Models` 쓰기 0.
> **병합은 main 세션이 d1v5 verdict receipt 이후 수행한다.** 이 문서는 병합 뒤 `완료/`로
> 옮기거나 폐기한다.

## 0. 중요 사실 — 단일 working tree에서의 branch checkout

`git checkout -b feature/parallel-offline-20260825`를 `C:\Projects\airi` **단일 working
tree**에서 실행했다(reflog 18:19:57 KST). 그 시각 이미 d1v5 matrix(17:35:52 시작)가 같은
tree의 `ollama-proxy/eval/broadcast_sim/run_broadcast_sim.py`를 run마다 import하고 있었다.
결과적으로 commit `3895921`(18:29:42 KST) 이후 생성된 d1v5 report(e2 arm부터)는 payload에
`model_digest`/`max_tokens` 키를 추가로 갖고, 그 이전 baseline 12개는 갖지 않는다.
main 세션(airi-d6) 확인: d1 comparator의 SETTINGS 비교는 고정 키만 보므로 **게이트 영향
0**. 이후 main 세션 요청에 따라 sim/proxy/affect_broadcast/launcher 경로 편집과
checkout/switch/stash/reset/rebase를 중단했고, 남은 작업은 문서 전용으로 마쳤다.
향후 병렬 작업은 `git worktree add C:\Projects\airi-parallel <branch>`로 별도 디렉터리에서
해야 한다(main 세션이 matrix 종료 후 정리).

부수 관측: 기존 실패 확인용으로 scratchpad에 `git worktree add … 973a6be`를 잠시 만들었다
가 `git worktree remove`로 지웠다(이 tree·branch 상태 변화 0).

## 1. 완료 항목과 commit

| # | 항목 | commit | 변경 파일 |
|---|---|---|---|
| 1 | legacy comparator R2 F5/F6 | `3895921` | `eval/broadcast_sim/compare_broadcast_t3.py`, `run_broadcast_sim.py`, `test_compare_broadcast_t3.py`, `test_broadcast_sim.py` |
| 2 | 일반 능력 게이트 절차 배선 | `d2d3dfc` | `training/verify_general_capability_gate.py`, `package_airi_gguf.py`, `README.md`, `tests/test_package_airi_gguf.py`, `tests/test_verify_general_capability_gate.py` |
| 3 | P2-4b cheer/sincere 수신 오프너 | `9de8f7a` | `eval/affect_broadcast/reception_opener_realization.py`(신규), `test_reception_opener_realization.py`(신규), `.github/workflows/remediation-checkpoint.yml` |
| 4 | P3-T4 하드코딩 축소 설계안 | 이 배치의 docs commit | `진행예정/AIRI-P3-T4-HARDCODING-REDUCTION-DESIGN-2026-08-25.md`(신규), `로드맵/AIRI-ROADMAP-LOG.md`, 이 문서 |

### 1-1. comparator F5/F6 (`3895921`)

- `MIN_SEEDS_PER_FIXTURE = 4`: 선택된 manifest fixture 중 하나라도 seed 4개 미만이면
  `fixture seed count below minimum 4`로 fail.
- `CONFOUNDERS = (memory_arm, contract_version, max_tokens)` + `ARM_IDENTITY = (model,
  model_digest)`: 모든 report에 필수(타입 검사: `max_tokens` 양의 int, `model_digest` 64-hex).
  한 디렉터리 안에서는 5개 전부 동일, base/candidate 간에는 CONFOUNDERS 동일, 두 arm의
  `model_digest`는 **달라야** 한다(같으면 `share one model digest`로 fail — 같은 모델 비교는
  비교가 아니라는 판단, 가정으로 기록).
- `run_broadcast_sim.py`: `read_model_digest()`가 `/health` `chat_model.digest.digest`를
  읽어 payload `model_digest`(없으면 `null`)와 `max_tokens`(CLI 값)를 기록한다. 판독
  시점은 show close 뒤·transport close 앞이라 기존 이벤트 순서 테스트가 그대로 성립한다.
- blind comparator(`compare_d1_blind/e2c1/e2c2`)와 launcher는 변경 0. 기존 report(키 없음)는
  legacy comparator에서 fail-closed가 되는데, 이는 의도된 동작이다.

### 1-2. 능력 게이트 배선 (`d2d3dfc`)

- 경로 계약: `--package-evidence <dir>/package-evidence.json` → verdict는 같은 dir의
  `general-capability-verdict.json`(no-overwrite). 파일명이 `package-evidence.json`이
  아니거나 `tag_evidence.tag` 부재·`adoption_authorized != false`면 exit 1, verdict 미작성.
  verdict에 `package_evidence: {name, sha256, tag}` 결속. `--output`과 상호 배타.
- 패키저: evidence에 `"general_capability_gate": "pending"` 추가, 파일명 상수
  `EVIDENCE_FILENAME`/`GENERAL_CAPABILITY_VERDICT_FILENAME`(검증기 상수와 일치함을 테스트로
  고정). 패키징 실행 로직·게이트 실행 0.
- 절차: `training/README.md` "General-capability gate after merge/package" 절.

### 1-3. P2-4b (`9de8f7a`)

- 입력은 디렉터 분류(`broadcast-director/priority-policy.mjs` → `cheer` |
  `sincere_reaction`)와 variant index뿐. 반말 고정 템플릿 3×2, 이름·수치 슬롯 0.
- `AIRI_RECEPTION_OPENER` 기본 off, `select_reception_opener()`는 off이거나 미소유
  priority면 `None`. 러너·프록시 미배선(테스트로 고정). 배선은 별도 승인 사항이다.

## 2. 검증 결과 (이 세션 실측)

| 검사 | 인터프리터 | 결과 |
|---|---|---|
| `ollama-proxy/eval/broadcast_sim` 전량 | venv-midm pytest | 190 passed, 1 skipped, 43 subtests |
| `ollama-proxy/training/tests` 전량 | venv-midm pytest | 360 passed, 6 skipped, **2 failed**(`test_synthesize_broadcast_behavior_v2` 2건 — 손대지 않은 `973a6be` worktree에서도 동일 실패, 기존 환경 문제); `test_synthesize_broadcast_continuity_v4`는 httpx 필요 → WindowsApps python unittest 8 OK |
| `ollama-proxy/eval/affect_broadcast` 전량 | venv-midm pytest | 134 passed, 2 skipped |
| `test_broadcast_t3_matrix_launcher_contract.py` | venv-midm pytest | 34 passed, **3 failed** — 전부 `T3 requires no pre-existing owned service listeners`(matrix가 8880/8892/9880/11435 점유 중). 코드 변경과 무관, matrix 종료 후 재실행 필요 |
| `test_live_campaign_launcher_contract.py` | venv-midm pytest | 포함 실행, 실패 0 |
| `.\test-patch-manifest.ps1` | PowerShell | PASS(신규 테스트 CI matrix 등록 후) |
| `.\test-current-checkpoint.ps1` | PowerShell | PASS |
| `git diff --check` | — | 0 |

`test_ollama_proxy.py` 계열은 프록시 코드를 건드리지 않아 실행하지 않았다.

## 3. 미완·보류

- launcher 계약 3건 재실행(포트 free 이후).
- INDEX(`AIRI-CURRENT-DOCS-INDEX-2026-08-10.md`) 등록은 main 세션과의 충돌을 피하려고
  하지 않았다 — 병합 시 `진행예정/AIRI-P3-T4-…`와 이 문서를 등록해야 한다.
- P3-T4 설계안은 착수 조건(hard gate 4종 통과 blind 1회 + 계측 결함 2건 수리)이 미충족이라
  구현 착수 없음.
- P2-4b 러너 배선, F6 필드를 blind comparator로 확장하는 일은 요청 범위 밖이라 하지 않았다.

## 4. 병합 시 확인 사항

1. `git diff main..feature/parallel-offline-20260825 --stat` 파일 목록이 §1 표와 일치하는지.
2. `run_broadcast_sim.py` 변경이 d1v5 report 24/48(e2·e2-c1·e2-c2 arm 예상)의 payload 키를
   바꾼 사실을 d1v5 receipt에 함께 남길 것.
3. ROADMAP-LOG 최상단 항목이 main의 최신 항목과 충돌하면 병렬 항목을 그 아래로 옮긴다.
