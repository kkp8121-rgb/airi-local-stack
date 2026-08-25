# AIRI D1 실행 인계 문서 (2026-08-25)

> **2026-08-25 10:27 KST 최신 — 감독권을 Codex에서 Claude Code로 이관했다. 이 문서가
> Claude의 단일 진입점이다.** detached matrix는 중단하지 않았고 재실행하지 않는다.
> Claude는 `AGENTS.md` →
> `airi_docs/진행중/AIRI-WORKING-STATE.md` → **이 문서** → `AIRI-ROADMAP-STATUS.md` →
> `NEXT-SESSION.md`를 읽고 `git status`/HEAD/PID/산출물 SHA를 read-only로 대조한 뒤에
> 감시를 재개한다. 설계 계약 원문은 `AIRI-D1-DETERMINISTIC-LAYER-CONTRACT-2026-08-25.md`이고
> 이 문서는 그 계약의 **실행 상태와 남은 단계**만 다룬다.
> 이관 본문 commit `c74b2481a79c3faa1d503e6e08d46d4bcd555b2a`는 origin/main에
> push됐고, 10:29:23 KST post-push에 HEAD/local/origin exact와 PID 7832 live를
> 재확인했다.

## 0. 인계 시점 상태 (관측값)

| 항목 | 값 |
|---|---|
| 관측 시각 | `2026-08-25T10:29:23.9276509+09:00` |
| HEAD = origin/main | `c74b2481a79c3faa1d503e6e08d46d4bcd555b2a` (이관 본문 push receipt) |
| worktree | clean (이 receipt 작성 전 기준); 사용자 코드 변경 0 |
| detached wrapper | PID `7832` live |
| exact command | `"C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -File D:\AIRI-Models\airi-d1-blind-matrix-20260825\launch-d1-matrix.ps1` |
| matrix 진행 | reports `15/48`, health `15/48`, stdout `75,213 B`, stderr `0 B`, exit receipt absent |
| Codex monitor | `/root/monitor_d1_matrix`만 `interrupted`; wrapper·launcher·서비스 제어 0 |
| GPU | idle — **D1은 GPU 학습이 전혀 없다** |
| goal | `user-goal-2026-08-25-0454-d1` (WORKING-STATE frontmatter `authorization` 참조) |
| adoption | `false` 고정. campaign 결과와 무관하게 별도 사용자 승인 사항 |

D1 goal 5단계 중 **1·2·3과 launcher/preflight가 끝났고 4(48-report matrix)가 exact-once
실행 중이며 5(분기)가 남았다.** blind v4는 이 실행으로 이미 소비됐다. Claude는 PID
7832를 중단·재실행·재시도하지 말고 read-only로 완주를 감시한 뒤 기존 comparator
verdict에 따라 §2.3 분기만 수행한다.

## 1. 끝난 것 (검증·push 완료)

### 1.1 결정론 발화 계층 — commit `9340a9b`

`ollama-proxy/deterministic_utterance_layer.py` 신규. 플래그
`AIRI_DETERMINISTIC_UTTERANCE_LAYER`(기본 off, off면 요청/응답 바이트 무변화).

- **P1** (`handle_grounding_guard.build_grounding_pools`에 `history_texts` 추가):
  이번 턴 history 메시지를 guard 풀과 `memory_pool` 신호에 함께 싣는다. 근거: E2-C2
  위반 표본 16/16이 실제 과거 시청자 재호명이었고 상당수가 history 창(8턴) 안에 있던
  **프롬프트 실재 근거**였다. 게이트 정의는 불변, 판정 입력 범위만 정확해진다.
- **P2** `guard_session_past_tokens`: 세션의 **과거 사용자 발화에만** 있고 이번 턴
  프롬프트 전체에 없는 한글 토큰을 `그거`로 치환(+조사 교정). 현재 주제어는 정의상
  프롬프트에 있으므로 건드리지 않는다.
- **P3** `answer_recall_question`: 회수형 질문이면 풀에서 `S는 A 말고 B` / `내 X는 Y야`
  를 추출해 결정론 응답으로 **대체**. 근거 없으면 안전 폴백(추측 금지).
- **P4** `suppress_rejected_branch`: 풀의 거부 분기(A)를 포함한 문장을 드롭(활용형
  어간 변형 포함), 전량 드롭 시 폴백, 라이브 제안이면 주어+B ack 선행.
- **P5** `ensure_donation_engagement`: 후원 계속 턴에서 공유 토큰 0이면 메시지를
  인용한 감사 문장 부가.
- 배선: `prepare_openai_sse_dialogue`의 **3번째 gate**(moderation → handle guard →
  layer), early-safe/main 두 방출 지점 모두, `/health`에
  `deterministic_utterance_layer` 노출. `build_layer_inputs`가 system 문구를 P2
  grounding에는 넣고 P3/P4 증거 풀에서는 뺀다(계약 산문의 "…지 말고" 오염 방지).
- 테스트: 신규 25 + guard 18 + proxy 377. CI shard 등록 완료.
- **알려진 fail-safe**: early-safe first-sentence cutoff에서 P4가 첫 문장을 드롭하면
  뒤 문장 대신 폴백이 방송된다. 거부 옵션이 새는 것보다 안전하므로 의도된 동작이다
  (통합 테스트에 주석으로 고정).

### 1.2 blind v4 봉인 + D1 평가 하네스 — commit `a3f2f39`

- **봉인 root**: `D:\AIRI-Models\airi-d1-blind-freeze-20260825-v4`
  (root_id `airi-d1-blind-freeze-20260825-v4`, `response_viewed=false` — 어떤 arm의
  응답도 생성된 적 없다). sealed manifest raw SHA
  `44c05fbd475a6ca9b87fc3a8f07ec0af7a2eef9e023b993c89398ceb3b071682` (1,119 B),
  validation receipt raw SHA
  `8542bd61abe643825f500fd0112d0c8a33c8edf493e212981da105bb0f2b95f4` (872 B).

| role | size | raw SHA-256 | canonical SHA-256 |
|---|---:|---|---|
| identity/unknown/donation | 7,795 | `c210b7df96324f137b448066a6a8a7346a0b36edc0a3e03f491f992d37823420` | `9879c919f98420f4fb88523b8093dd3aa09ff2011e4a54fbca5a1d9c1c076e2d` |
| continuity/stale transition | 12,921 | `82e5eaab37e07d18c2630d50b59c5263a969259b6a39089778e8120c904d8ab8` | `5057f5c723b0a38265fa3a89626056f2b6ef64175c55774724699dc99a9ac320` |
| factual/show arc | 11,090 | `64a5df12e52c8f49d4e66d75ced74b686084aabc59d8bb3482e62a6726c14dd1` | `4e30d9986a78f2802fe24ce87f0de12bfaba784e4ffbf21b539a14e112912d80` |

  주제는 심야 국숫집 / 겨울 온실 야간 당번 / 마을 방앗간 떡메치기이며 전부 신규
  한국어 본문이다. offline 검증(model_calls 0): schema, 한글 하한, 4 seeds × 3 fixture
  결정론 stream 전 메시지 한글, 교정 proper noun 충돌 0, 공개 fixture 충돌 0,
  **v1·v2·v3 hash/핸들/템플릿 재사용 0**(검사가 실제 템플릿 재사용 1건을 잡아 교체함).
- **seal 도구 일반화**: `seal_e2c2_blind.py`에 `GENERATIONS` 딕셔너리와
  `--generation {e2c2,d1}` 추가. d1 세대는 schema 문자열·4 arms·v3 superseded 확장을
  갖는다. 기존 e2c2 동작과 테스트는 불변(18 pass).
- **commitment/policy**: `fixtures/commitments/airi_d1_blind_commitment.json`
  (4 arms, 48 reports, seeds `[73,89,97,20260824]`),
  `airi_d1_metric_policy.json`(schema `airi.d1-blind-metric-policy.v1`). **threshold
  값은 E2-C2 policy와 전부 동일**하고 바뀐 것은 (a) `report_completeness`가 4 arm/48,
  (b) 신규 `arm_rules {reference_arm: e2, delta_gated_arms: [e2-c1, e2-c2]}`,
  (c) selection 키 이름 `e2_c2_*` → `delta_gated_*`(값 0.08/4 동일)뿐이다. 완화 0.
- **verifier**: `ollama-proxy/training/verify_d1_frozen_contract.py`. sealed root까지
  포함해 실행 exit 0 확인.
- **comparator**: `ollama-proxy/eval/broadcast_sim/compare_d1_blind.py`(24 tests).
  4-arm 규칙(결과-전 동결):
  - hard-zero·perfect-rate·additive **절대 최소선**은 **모든 arm**에 적용.
  - additive **delta**(vs e2)와 legacy 게이트는 **`e2-c1`/`e2-c2`에만** 적용
    (reference 자신에 대한 delta는 정의 불능).
  - eligible = 자기 적용 게이트를 전부 통과한 arm. eligible 중 최고 score가
    provisional, margin은 **다른 모든 arm 최고점 대비**로 계산하고 `>0.02` 요구.
    provisional이 delta-gated arm이면 score delta ≥0.08 + improved axes ≥4 추가 요구.
    없거나 동점이면 `no_winner`.
  - attestation은 `handle_grounding_guard=='on'` **및**
    `deterministic_utterance_layer=='on'`을 모두 요구하고, `run_count`는 commitment의
    `expected_matrix_reports`(48)와 일치해야 한다.
- 테스트 총계(인계 시점): broadcast_sim 169 passed/1 skipped(+32 subtests), proxy
  377, `test-current-checkpoint.ps1` PASS, `git diff --check` 0, CI shard 등록 완료.
- **주의(구현자 보고)**: `compare_d1_blind.py`의 delta-gated 추가 요구 두 분기는 동결
  threshold 하에서는 도달 불가(모든 additive delta를 넘긴 arm은 필연적으로 score
  delta ≥0.132, improved ≥4). 테스트는 그 분기를 검증하려고 **테스트 전용** policy
  변형(0.5/5)을 쓴다. 배포 policy 값은 0.02/0.08/4 그대로다.

## 2. 남은 작업 (Claude가 이어받는 부분)

### 2.1 [완료] launcher `d1` 프로파일 — commit `9e6b1f4`, receipt `a510004`

2026-08-25 09:23 KST 코덱스가 아래 계약을 구현해 origin/main에 push했다. root 검토로
기존 E2-C2 unbound-root 테스트 약화 1건을 원복한 뒤 launcher 25 pass,
broadcast_sim+launcher 194 pass/1 skip(+32 subtests), proxy 377 OK, 전체 offline
checkpoint/AST/diff-check를 통과했다. 기존 t3/e2c1/e2c2는 3 arm/36을 유지한다.

`run-airi-broadcast-t3-matrix.ps1`은 이제 `t3`/`e2c1`/`e2c2`/`d1` 4개 프로파일을
가지며, 아래 구현 항목은 commit `9e6b1f4`에서 완료됐다. 기존 세 프로파일은 3 arm/
36 report를 유지하고 d1만 4 arm/48 report다. (아래 라인 번호는 구현 전 `a3f2f39`
기준의 역사적 seam이다.)

1. `[ValidateSet('t3','e2c1','e2c2')]` → `d1` 추가 (line ~15).
2. `$isBlindProfile`에 `d1` 포함, `$requireGuardHealth`(현재 e2c2 전용)를 **d1도
   포함**하도록 확장하고, d1에서는 `/health.deterministic_utterance_layer`도 `$true`
   인지 `Assert-Health`에서 함께 검사한다(strict-mode 안전 접근:
   `$H.PSObject.Properties['...']` 패턴을 그대로 따를 것).
3. `$expectedArmNames`에 d1 분기 `@('baseline','e2','e2-c1','e2-c2')`.
   **arm 개수 3 가정을 푸는 곳**(현재 하드코딩된 `-lt 3` / `-ne 3`):
   arm 이름 비교 루프(line ~217), tag/digest distinct 검사(line ~226).
   fixture 개수 3은 그대로 유지된다(3 fixture × 4 seeds × 4 arms = 48).
4. blind 바인딩 분기: commitment 파일 `airi_d1_blind_commitment.json`, policy
   `airi_d1_metric_policy.json`, schema `airi.d1-blind-commitment.v1`, root_id
   `airi-d1-blind-freeze-20260825-v4`, sealed manifest SHA
   `44c05fbd475a6ca9b87fc3a8f07ec0af7a2eef9e023b993c89398ceb3b071682`,
   `expected_matrix_reports` 검사 36 → **commitment 값에서 읽어 비교**(하드코딩 금지
   권장; 최소한 d1 분기에서는 48).
5. 계획/증거 카운트 36 → `$expectedArmNames.Count * 3 * 4`로 파생. 영향 지점:
   plannedKeys 검사(line ~294), PreflightOnly 출력 `runs`(line ~321), 실행 후
   evidence 카운트 검사(line ~483), attestation `run_count`(line ~510), verdict
   `report_count` 검사(line ~532), summary `run_count`(line ~583). plan evidence는
   arm과 무관한 12(3 fixture × 4 seed)로 **그대로**다.
6. 런타임 플래그: e2c2가 `$env:AIRI_HANDLE_GROUNDING_GUARD='on'`을 켜는 자리에서
   d1은 **가드 + `$env:AIRI_DETERMINISTIC_UTTERANCE_LAYER='on'` 둘 다** 켜고,
   `finally`에서 둘 다 `Restore-Env`로 복원한다(이미 `$previousGuard` 패턴 있음).
7. attestation: schema `airi.d1-environment-attestation.v1`, 기존 zero_violations
   3종 + `handle_grounding_guard='on'` + **`deterministic_utterance_layer='on'`**,
   evidence에 `..._health_attested=$true` 두 개.
8. comparator 호출: `compare_d1_blind.py`, 출력 `comparisons\d1-blind.json`,
   verdict schema `airi.d1-blind-comparison.v1`. 인자 형태는 e2c2와 동일
   (`--reports-dir --policy --commitment --output --environment-attestation
   --expected-model-manifest-sha256`).
9. **계약 테스트 갱신 필수**: `test_broadcast_t3_matrix_launcher_contract.py`에
   `D1BlindProfileContract` 추가(e2c2 클래스가 템플릿). ValidateSet 값 검사
   테스트는 현재 `'t3,e2c1,e2c2'` 문자열을 비교하므로 `d1`을 더해 갱신해야 한다.
   4-arm model manifest fixture(태그 4개·digest 4개 distinct)가 필요하다.

**model manifest**(matrix 실행 인자)는 4 arm 모두 이미 Ollama에 등록돼 있고 digest도
검증했다. 아래 값을 그대로 쓰면 된다(파일은 새로 만들 것, 예:
`D:\AIRI-Models\airi-d1-blind-matrix-20260825\d1-model-manifest.json`):

```json
{"schema_version":"airi.broadcast-sim-t3-model-manifest.v2","arms":[
 {"name":"baseline","tag":"midm-airi:2.0-mini-broadcast-v3-q4-20260821-04d64a38eeb4638babb90b12647d3704","digest":"e683802b7e9bc72dc0c0ad094bedf4c49142c6248c1b148d3100001c04ff5291"},
 {"name":"e2","tag":"midm-airi:e2-broadcast-v4-20260823-401e5c801201b94583a149022afb6b52","digest":"4afe7f4e2559a2f87785d02aeaf1a84a09f78b440ca476b718537b91b98ca243"},
 {"name":"e2-c1","tag":"midm-airi:e2c1-broadcast-v4-20260824-08df7ecfc4c32bdfb7cdbeaef932583e","digest":"fccbfde9f6d40dd7d728c7da386fcbb20154f9987f09d9d9305226632a94a9e1"},
 {"name":"e2-c2","tag":"midm-airi:e2c2-broadcast-v4-20260824-5eda8184e7118093773b4eafe513ec96","digest":"66364b4a1eeb33459b957d5024d864a45264897d121c2db0cc1f528b7bd48252"}]}
```

### 2.2 [실행 중] 48-report matrix 감시 — 재실행 금지

2026-08-25 09:28:26 KST detached wrapper PID 7832로 정확히 한 번 시작했고 blind v4는
소비됐다. 10:27:00 KST 기준 reports/health 15/48, stdout 75,211 B, stderr 0 B, exit
receipt absent다. Codex monitor subagent만 종료됐으며 wrapper·launcher·서비스는 계속
실행 중이다. **아래 launcher 명령은 역사적 호출 계약일 뿐 다시 실행하지 않는다.**
Claude의 다음 행동은 PID/command, report/health 증가, stdout/stderr, exit receipt를
read-only로 감시하고, 종료 뒤 48/48 completeness와 `comparisons\d1-blind.json` verdict를
검증하는 것이다.

다음 두 문단과 명령은 **이미 완료된 09:26~09:28 KST 시작 절차의 역사 기록**이다.
현재 세션에서 실행하지 않는다.

2026-08-25 09:26 KST 당시 preflight PASS: external model manifest 767 B SHA
`050ae10f86cef5801b625a54bdfaa136ad927873e62b0e44226fa241b38ae330`, 48/48
unique run keys, arm 순서 4개, seed sets 3×4, comparison d1-blind, OutputDir 미생성.
그 시점에는 blind 응답 생성이 0이었고, 이후 09:28:26 KST exact-once wrapper가 시작됐다.

```powershell
# HISTORICAL EXACT COMMAND — DO NOT RUN AGAIN
.\run-airi-broadcast-t3-matrix.ps1 -MatrixProfile d1 `
  -OutputDir 'D:\AIRI-Models\airi-d1-blind-matrix-20260825\run' `
  -ModelManifest 'D:\AIRI-Models\airi-d1-blind-matrix-20260825\d1-model-manifest.json' `
  -BlindRoot 'D:\AIRI-Models\airi-d1-blind-freeze-20260825-v4'
```

- `-PreflightOnly` 48 run key와 blind 바인딩은 이미 PASS했다. 다시 실행하지 않는다.
- 실측 기준: E2-C2의 36-report matrix가 약 2시간 40분이었다. 48은 **3.5~4시간** 예상.
  heartbeat 상한 14분, 첫 3 report에서 perfect-rate 분모 nonzero와
  `evidence\health-*.json`의 두 플래그 attest를 조기 확인할 것.
- 실패 시 root 보존, 같은 명령 반복 금지, 원인 확정 후 재기록.

### 2.3 [분기] 판정 후속

- **winner 있음** → top-score arm으로 3×500 turn live campaign을 이어서 실행한다
  (goal 승인 범위). adoption은 여전히 별도 승인.
- **no_winner** → campaign 없이 실패 축을 보존하고, 어떤 게이트가 왜 남았는지
  진단해 보고한 뒤 대기한다. **자동으로 다음 라운드를 시작하지 않는다.**

두 경우 모두 receipt를 WORKING-STATE에 쓰고, contract 문서(§7 자리)에 결과-후 절을
추가하고, ROADMAP-LOG/STATUS/NEXT-SESSION을 갱신한 뒤 commit/push한다.

## 3. 이번 라운드에서 무엇을 확인하려는가 (판정 해석의 사전 고정)

D1은 **학습 없이** 게이트가 닫히는지를 본다. 해석 기준을 결과 보기 전에 고정한다:

- 4 arm 전부에서 `invented_handle`, donation composite, `stale_transition_clean`,
  `decoy_fact_use`가 목표치에 도달하면 → 결정론 계층이 실제로 게이트를 구조적으로
  보장한다는 뜻이고, 그다음 관심사는 additive 축의 절대 최소선이다.
- 게이트는 닫혔는데 additive 절대 최소선(0.4~0.75)이 여전히 전 arm 미달이면 →
  E2-C1/E2-C2의 진단(③ 전 arm이 최소선의 2~4배 미달)이 재확인되는 것이며, 다음
  논의는 "모델 체급/데이터"가 아니라 **게이트 체계 자체의 타당성**이 된다. 이 경우도
  hard gate를 완화하지 않는다 — 판단은 사용자 몫이다.
- 특정 게이트만 남으면 그 게이트의 실패 row를 원문으로 진단해(blind는 채점 완료 후
  열람 가능) 계층의 어느 부분(P2~P5)이 못 잡았는지 지목한다.

## 4. 금지선 (goal 원문)

GPU 재학습·새 후보 학습, blind v1/v2/v3 재사용, **hard gate 완화**, 운영 서비스
모델/태그 변경, 외부 provider/extraction/greybox 기본 ON, T-05 126번 승격. 운영
채택은 campaign 결과와 무관하게 별도 사용자 승인 사항이다.

## 5. 환경 메모

- 테스트 인터프리터가 갈린다: `pytest`는 `D:\AIRI-Models\venv-midm-broadcast-qlora-py312\
  Scripts\python.exe`(3.12, pytest 9.1.1)에만 있고, `httpx`/`fastapi`가 필요한
  `test_ollama_proxy.py`·rehearsal은 `C:\Users\kkp74\AppData\Local\Microsoft\
  WindowsApps\python.exe`(3.14)로 `unittest` 실행해야 한다. 리포 venv 2종에는 pytest가
  없다.
- `test-current-checkpoint.ps1`의 durability 계약은 간헐적으로 30초 타임아웃 flake를
  낸다(2회 관측, 재실행 시 PASS). 실패하면 한 번 재실행해 보고, 재현되면 그때
  조사한다.
- `test-patch-manifest.ps1`이 **tracked된 ollama-proxy 테스트가 CI 매트릭스에
  있는지** 검사한다. 새 Python 테스트를 추가하면 `.github/workflows/
  remediation-checkpoint.yml`에 같은 배치로 등록해야 체크포인트가 통과한다.
