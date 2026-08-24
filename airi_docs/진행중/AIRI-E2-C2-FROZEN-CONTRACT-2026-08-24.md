# AIRI E2-C2 교정 학습 동결 계약 (2026-08-24)

> **상태: 설계 동결(design-frozen), blind v3 봉인 전.** 이 문서는 2026-08-24 17:00 KST
> 사용자 `/goal`(E2-C2 재설계 + 신규 blind + 36-report matrix)의 실행 계약이다.
> E2-C1 계약(`AIRI-E2-C1-FROZEN-CONTRACT-2026-08-24.md`)은 §12까지 포함해 역사
> 기록으로 불변이며, 이 문서가 E2-C2의 단일 계약이다. blind v3 pin은 봉인 시
> §5에 결과-전(pre-result)으로 추가하고, 그 후에는 결과를 본 뒤 어떤 target/
> fixture/threshold/seed도 바꾸지 않는다.

## 1. 후보 정의와 금지선

- E2-C2는 base + 검증된 E2 adapter **weight만** 초기값으로 사용한다(E2-C1과 동일한
  init 계약). optimizer/scheduler/RNG/data cursor는 새로 시작하며 checkpoint resume은
  금지한다. E2-C1 adapter를 초기값으로 쓰지 않는다 — E2-C1은 no_winner로 종결된
  후보이고, E2-C2는 같은 출발점(E2)에서 선량(dose)을 교정한 **독립 재도전**이다.
- 금지: blind v1/v2 재사용, hard gate 완화(threshold/seed/arms/metric 정의 변경 포함),
  같은 데이터로 epoch만 늘리는 E3(v4 계속 학습), 운영 서비스 모델/태그 변경, 외부
  provider/extraction/greybox 기본 ON, T-05 126번 음성 운영 승격. 운영 채택은 campaign
  결과와 무관하게 별도 사용자 승인 사항이다.
- no_winner면 campaign 없이 실패 축을 보존·진단 보고 후 대기한다. 자동 E2-C3
  루프를 돌지 않는다.

## 2. 언더트레이닝 진단 근거 (설계 입력)

E2-C1 blind v2 verdict(`airi.e2-c1-blind-comparison.v1`, 36 reports) 실측:

- 교정 **방향은 전 축에서 유효**했다: donation composite e2 0.167 → e2-c1 0.458,
  unknown_identity_safe 0.167 → 0.25, complete_show_arc +0.05, long_callback +0.019,
  memory_probe +0.025, viewer_fact_usage +0.005 (additive 4/5축 개선).
- 그러나 절대 최소선에는 전부 크게 미달했다(show_arc 0.1625/0.75, memory 0.075/0.5).
- invented_handle 28/40/53 악화는 §12(E2-C1 계약) 진단으로 **채점기 사각지대**(53건 중
  89%가 실제 memory 회수)였음이 확정됐고, 가드+채점기 신호(`a0020dd`)로 이미 닫혔다.
  이번 matrix는 `AIRI_HANDLE_GROUNDING_GUARD=on`으로 세 arm을 같은 조건에서 측정한다.
- 선량 비교: E1/E2 본 학습은 **LR 2e-5**, 1,600 microsteps/100 optimizer steps였다
  (handoff §7 exact 명령). E2-C1은 **LR 1e-5(절반), 512 microsteps/32 steps(1/3)** —
  mixture train 512행 기준 정확히 1 epoch, dev-loss 기반 epoch 선택이 사실상 무의미한
  단일 epoch였다. 교정 신호가 과소학습됐다는 §11 가설과 정합한다.

## 3. 데이터: 비율 재검토 결과 — 동결 유지

goal이 지시한 correction:replay 비율 재검토 결과, **E2-C1 frozen dataset을 byte-exact
그대로 유지**한다 (correction 480 + v4 replay 200 + mixture 680, train 512 = correction
352 : replay 160 = 11:5, dataset/replay manifest SHA는 E2-C1 계약 §3.3 pin과 동일).

근거:

1. E2-C1 결과에서 replay 부족 징후(망각)는 0이다 — polite 0, transport 0, donation
   callout 96.2% 유지. 비율이 원인이라는 증거가 없다.
2. 교정 축은 전부 올바른 방향으로 이동했다 — 부족한 것은 조성(composition)이 아니라
   선량이라는 것이 §2의 실측이다.
3. 데이터를 고정하면 이번 실험이 **언더트레이닝 가설의 깨끗한 검정**이 된다: 변수는
   선량(steps)과 학습률뿐이다. 비율까지 바꾸면 결과 귀속이 불가능해진다.
4. frozen dataset의 full validation(§10, E2-C1 계약)을 그대로 승계해 재생성·재검증
   비용과 신규 결함 위험을 제거한다.

epoch 반복 시 correction과 replay가 같은 비율로 함께 반복되므로 망각 방지 비중은
epoch 수와 무관하게 유지된다. **E3 금지선과의 구분**: 금지된 E3는 v4 같은 데이터로
E2를 epoch만 연장하는 것이다. E2-C2는 교정 mixture 후보이고, 변경 축이 epoch 수만이
아니라 학습률(2배)을 포함하며, goal 문안이 이 재검토를 명시 승인했다.

## 4. 동결 학습 계약

| 항목 | E2-C1 (참고) | **E2-C2 (동결)** | 변경 근거 |
|---|---|---|---|
| candidate | E2-C1 | `E2-C2` | |
| initialization | base + E2 adapter weights only | 동일 | 동일 출발점 유지 |
| optimizer/scheduler/cursor | fresh | fresh | resume 금지 동일 |
| seed | 42 | `42` | 불변 |
| LoRA r/alpha/dropout | 8/16/0.05 | `8/16/0.05` | 불변 (VRAM 실증치) |
| batch / accumulation / seq | 1 / 16 / 2048 | `1 / 16 / 2048` | 불변 (8GB 실증치) |
| max microsteps | 512 (1 epoch) | **`1536` (3 epochs)** | E2 실증 규모(≈100 steps) 복원 |
| max optimizer steps | 32 | **`96`** | 1536/16 |
| learning rate | 1e-5 | **`2e-5`** | E1/E2 실증 LR 복원 |
| optimizer | AdamW 0.9/0.999/1e-8/wd 0.01 | 동일 | 불변 |
| scheduler | constant LambdaLR factor 1 | 동일 | 스케줄 형태 불변 |
| epoch 선택 | (단일 epoch, 무의미) | **epoch별 dev loss 평가, best-epoch 자동 선택** | trainer 내장(cuda-qlora), 고선량의 과적합 방어 |
| checkpoint interval | 3 opt steps / ≤600s | `3 opt steps / ≤600s` | 불변 |
| launcher | durable runner only | durable runner only | direct trainer 금지 불변 |

유효 교정 노출은 E2-C1 대비 steps 3배 × LR 2배 = **약 6배**다. 과적합은 dev 84행의
epoch별 loss와 best-epoch 선택(1~3 중)으로 방어하고, selected epoch/loss를 report에
기록한다.

bounded GPU smoke는 **1회만** 허용한다(E2-C1 smoke 패턴: fresh 외부 root, 80
microsteps/5 optimizer steps, K=1). smoke는 adapter-init seam·fresh optimizer·run-state/
checkpoint·safe pause/resume의 배관 검증이며 품질 진척이 아니다. smoke PASS receipt
기록 후 fresh timestamped external root에서 본 학습을 step 0부터 시작한다.

merge는 `merge_airi_behavior_lora.py`, 패키징은 `package_airi_gguf.py`(BF16 → Q4_K_M)로
E2-C1과 동일하게 SHA 핀 결속 하에 실행하고, Ollama 등록은 **평가 전용 태그**로만 한다
(운영 태그 `midm-airi:2.0-mini` 불변).

## 5. retained blind v3와 평가 계약

- **신규 저작**: 3 fixture(logical role은 비교 가능성을 위해 E2-C1과 동일 —
  `identity_unknown_and_donation_ritual`, `long_continuity_and_stale_transition`,
  `factual_grounding_and_complete_show_arc`), 전부 **처음 쓰는 한국어 본문**이다.
  v1(영어 결함)·v2(소비됨)의 archetype/probe/handle/사실/문구를 재사용하지 않는다.
- **proper noun 충돌 0**: 새 fixture의 모든 handle/donor/사실 토큰은 교정 데이터의
  proper noun 전수(`synthesize_broadcast_e2_c1.py`의 `_HANDLES` 18종,
  `_UNKNOWN_HANDLES` 16종, `_DONORS` 17종, 시나리오 사실/decoy 상수)와 충돌 0이어야
  하며, 이를 offline 검증으로 기계 확인한다.
- **offline(stream-only) 검증**: fixture schema(`airi.broadcast-sim-fixture.v1`,
  `validate_fixture`) + 한글 비율 stream 검증(v1 재발 방지, `model_calls=0`) + 충돌
  검사. 모델 호출 0으로 봉인 전 완료한다.
- **봉인**: 새 external root `D:\AIRI-Models\airi-e2-c2-blind-freeze-<timestamp>`에
  sealed manifest(`airi.e2-c2-blind-sealed-manifest.v1`) + validation receipt
  (`language_validation` 필수)로 봉인. repository에는 body를 넣지 않고 commitment
  (`airi_e2_c2_blind_commitment.json`)와 metric policy(`airi_e2_c2_metric_policy.json`)만
  둔다. `response_viewed=false`.
- **reseal 가드**: 신규 commitment test는 v1 root(`...-000430`)·v2 root
  (`airi-e2-c1-blind-freeze-20260824-v2`)의 root_id와 fixture hash 전부를 superseded로
  고정해 재봉인을 금지한다.
- seeds `[73, 89, 97, 20260824]` 불변, arms `baseline / e2 / e2-c2`(reference arm은
  `e2` 유지), 3 fixture × 4 seeds × 3 arms = **36 reports**.
- **threshold/metric policy는 E2-C1 policy와 값 단위로 동일하게 복사**한다 — hard zero
  (transport/polite/invented handle/privacy/localhost/external provider), hard perfect
  (unknown identity safe, donation composite, stale transition clean, decoy 0), additive
  최소선/delta, score weights, unique top margin, candidate 요건(score delta >=+0.08,
  additive 4/5축 개선) 전부 완화 없이 승계한다.
- **측정 조건**: matrix는 프록시를 `AIRI_HANDLE_GROUNDING_GUARD=on`으로 띄워 실행한다.
  가드 신호는 프록시 측 계산이므로 세 arm에 동일하게 적용된다(공정 비교). launcher의
  environment attestation(`airi.e2-c2-environment-attestation.v1`)에 guard 상태를
  필수 필드로 기록하고 comparator가 이를 gate한다.
- 실행 도구: `run-airi-broadcast-t3-matrix.ps1 -MatrixProfile e2c2 -BlindRoot <sealed
  root>` + `compare_e2c2_blind.py`(candidate `e2-c2`, reference `e2`). 기존 t3/e2c1
  profile 동작은 불변.

## 6. 실행 순서 (fail-closed)

1. 이 설계 문서·live state receipt·ROADMAP-LOG 기록 → 검증(diff-check,
   test-current-checkpoint) → docs commit/push.
2. blind v3 저작 + offline 검증 + 봉인 + commitment/policy/test + launcher `e2c2`
   profile + comparator + guard env 주입/attestation 구현 → 전체 offline 회귀
   (기존 suite + 신규 테스트, CI shard 등록) → commit/push. 이 단계까지 GPU 0.
3. bounded GPU smoke 1회(intent→실행→receipt) → durable 본 학습 1536/96 step 0부터
   (15분 heartbeat) → safe merge → BF16/Q4_K_M 패키징 → 평가 태그 등록. 각 단계
   전후 intent/receipt.
4. 36-report matrix(guard=on) → `compare_e2c2_blind.py` verdict.
5. winner면 3×500 turn live campaign 연속 실행. no_winner면 campaign 없이 실패 축
   보존·진단 보고 후 사용자 지시 대기(자동 E2-C3 금지). adoption은 어느 경우에도
   별도 사용자 승인 전 금지.

## 7. 고정 입력 provenance (학습 측)

E2-C1 계약 §2·§3.3의 pin을 그대로 승계한다: base `model.safetensors`
`394b6624...8f506`, E2 adapter model `2a72292c...895c5b`, E2 adapter config
`e01129ea...0382d0`, E2 artifact manifest `70998cff...747195`, mixture chat JSONL
1,970,252 bytes `c845adfc...1b1980`, dataset manifest `fe1ca6c8...59c9f0`, replay
manifest `23883d8d...86bbd5`. durable runner가 launch 시 전부 재검증한다.
