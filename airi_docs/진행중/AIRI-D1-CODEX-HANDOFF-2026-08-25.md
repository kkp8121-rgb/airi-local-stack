# AIRI D1 실행 인계 문서 (2026-08-25)

> **2026-08-25 13:05 KST 최신 — D1 matrix 완주, comparator `winner=null`. 실행 단계는
> 끝났고 이 문서는 결과·진단 기록으로 넘어간다.** 48-report matrix는 12:38:14 KST에
> exit 0으로 완주했고(48/48 전 증거), goal의 `no_winner` 경로대로 **3×500 campaign은
> 실행하지 않았다**. 실패 root `D:\AIRI-Models\airi-d1-blind-matrix-20260825\`는 그대로
> 보존한다. blind v4는 소비됐고 재사용·재실행 금지다. 진단 원문은
> `AIRI-D1-DETERMINISTIC-LAYER-CONTRACT-2026-08-25.md` **§6**, row 단위 근거는
> WORKING-STATE 2026-08-25 13:05 receipt에 있다. **다음 라운드는 사용자 결정 사항이며
> 자동으로 시작하지 않는다.**

## 0. 최종 상태 (관측값)

| 항목 | 값 |
|---|---|
| 관측 시각 | `2026-08-25T12:39:32.9033202+09:00` |
| HEAD = origin/main | `927116ca38b39a6b1304b227f669e98c280b9bfb` (이 배치 직전 기준) |
| worktree | 이 결과 문서 배치 전까지 clean; 사용자 코드 변경 0 |
| detached wrapper | PID `7832` **종료**, `launcher.exit-code.txt = 0` |
| exact command | `"C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -File D:\AIRI-Models\airi-d1-blind-matrix-20260825\launch-d1-matrix.ps1` |
| matrix 결과 | reports/health/run-contract/packets/runtime **48/48**, stdout `237,532 B`, stderr `0 B` |
| comparator | `comparisons\d1-blind.json`, schema `airi.d1-blind-comparison.v1`, `status=pass`, **`winner=null`**, 실패 게이트 45 |
| 서비스 정리 | owned 포트 11435/11436/8880/9880/8890/8892 전부 free, AIRI 잔여 프로세스 0 |
| GPU | idle — **D1은 GPU 학습이 전혀 없다** |
| goal | `user-goal-2026-08-25-0454-d1` (WORKING-STATE frontmatter `authorization` 참조) |
| adoption | `false` 고정. campaign 미실행이며 채택은 별도 사용자 승인 사항 |

D1 goal 5단계 중 **1~4가 끝났고 5(분기)는 `no_winner` 경로로 종결**됐다. 남은 행동은
없으며 다음 방향은 사용자 지시를 기다린다.

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

## 2. 실행 단계 (전부 종결)

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

### 2.2 [완료] 48-report matrix — exit 0, 재실행 금지

2026-08-25 09:28:26 KST detached wrapper PID 7832로 정확히 한 번 시작해 12:38:14 KST에
종료했다. `launcher.exit-code.txt = 0`(2 B), reports/health/run-contract/packets/runtime
**48/48**(arm별 12씩), plan evidence 12, comparisons 1, `summary.json`
(`airi.t3-matrix-launcher.v2`, `matrix_profile=d1`, `run_count=48`,
`comparisons={d1: pass-no-winner}`) 모두 계약치와 일치한다. health **48/48 전부**
`before`·`after` 양쪽에서 `handle_grounding_guard=true`·`deterministic_utterance_layer=true`
이고, environment attestation은 `airi.d1-environment-attestation.v1` / `run_count=48` /
두 플래그 `'on'` / 두 `*_health_attested=true`다. retained `evidence\model-manifest.json`
재계산 SHA는 summary의 `050ae10f...e330`과 exact 일치한다. stdout `transport_failures`
전량 0, stderr 0 B다. **blind v4는 소비됐다. 이 matrix는 어떤 이유로도 재실행하지 않는다.**

### 2.3 [종결] 판정 — `no_winner`

comparator verdict는 `winner=null`, `no_winner_reason='no arm passed every applicable
gate'`, 실패 게이트 45개다. score는 baseline 0.105751 / e2 0.109299 / e2-c1 0.116965 /
e2-c2 0.108908이다. **goal의 `no_winner` 경로대로 3×500 live campaign을 실행하지 않았고
자동 후속 라운드도 시작하지 않았다.** 실패 root를 보존하고 진단만 기록했다.

진단 요약(전량 근거는 contract §6, row 단위 표는 WORKING-STATE 13:05 receipt):

1. **전 arm 턴의 33.9~35.3%가 프록시 `LOCAL_ERROR_DIALOGUE`** 로 모델 발화가 없다.
   D1 고유가 아니라 E2-C1 30.3~31.6%, E2-C2 37.2~38.6%로 **세 라운드 공통**이며
   `summary.fallback`이 세지 않아 지금까지 보고된 적이 없다.
2. **P3 `answer_recall_question` 과발동(D1 신규 회귀)** 이 `continuity_callback`
   320행 중 176행(55%)을 회수 폴백으로 대체해 `long_callback`·`complete_show_arc`를
   정확히 0.0으로 만들었다. 실제 모델 발화는 27행(8.4%)뿐이다.
3. `unknown_identity_safe`는 분모 12행이 **전 arm 12/12 차단**이라 측정 자체가 불가능했다.
   `stale_transition_clean`·donation composite도 25~58%가 차단돼 raw 1.0이 산술적으로
   도달 불가였다.
4. P4는 decoy 위반을 3라운드 최저(0.025~0.05)로 줄였지만 0에 미달, P5는 측정 가능한
   donation 턴에서 live rate 0.688(e2-c2)로 최고였다. `invented_handle`은 5/4/8/6으로
   85% 감소하고 학습 단조 악화도 사라졌으나, 감소분 일부는 발화 부재의 산술 효과이므로
   가드 공로로 승격하지 않는다.
5. **미확정**: 프록시 오류의 근본 원인은 프록시 stdout 미보존으로 특정하지 못했다.
   코드상 후보는 memory 경로(`prepare_memory_body` → `fetch_local_dialogue`)의 포괄 예외
   처리이며, 확정에는 프록시 stdout을 남기는 짧은 재현 실행이 필요하다(GPU 불필요).

결과 문서는 WORKING-STATE receipt, contract §6, ROADMAP-STATUS/LOG, NEXT-SESSION에
반영했다. adoption은 `false` 유지이며 campaign 결과와 무관하게 별도 승인 사항이다.

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

**[결과-후 2026-08-25 13:05]** 위 세 해석 분기 중 어느 것도 그대로 적용할 수 없었다.
네 목표 게이트의 분모가 25~100% 차단돼(프록시 오류 + P3 회수 폴백) "닫혔는가"를
판정할 재료 자체가 부족했기 때문이다. 따라서 이번 라운드는 **게이트 체계의 타당성
논의로 넘어가지 않는다** — 먼저 계측(프록시 오류율, P3 발동 범위)을 고치고 다시
재야 한다. 어떤 경우에도 hard gate는 완화하지 않으며 판단은 사용자 몫이다.

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
