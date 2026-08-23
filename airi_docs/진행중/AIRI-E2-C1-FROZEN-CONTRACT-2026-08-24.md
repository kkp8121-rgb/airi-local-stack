# AIRI E2-C1 교정 학습 동결 계약

갱신: 2026-08-24 02:00 KST

상태: **FROZEN / VALIDATED / MILESTONE PUSH PENDING**

기계 판독 상태:

```text
candidate=E2-C1
goal_status=active
freeze_status=pass
gpu_authorized=false
microsteps_completed=0
optimizer_steps_completed=0
adoption_authorized=false
blocker=frozen_milestone_commit_push_clean
```

이 문서는 E2-C1 학습 전에 한 번 고정한 데이터·학습·비오염 평가 계약이다. checkpoint에서
확인한 한국어 조사 오류 5건과 validator 공백은 `(으로,로)`/받침 ㄹ helper, template,
독립 verifier와 mutation regression으로 최소 수리했고 current bytes의 full gate가 PASS했다.
단, 이 frozen-contract 배치가 origin/main에 push되고 HEAD=origin/main clean/PID 0이 되기
전에는 GPU를 허가하지 않는다. 동결은 T3 승자나 운영 채택을 뜻하지 않는다.

## 1. 후보 정의와 금지선

- E2-C1은 원래 base와 검증된 E2 adapter **weight만** 초기값으로 사용한다.
- optimizer, scheduler, RNG, data cursor와 progress는 새로 시작한다. E2 checkpoint의
  optimizer/scheduler/RNG/cursor를 이어가는 resume는 금지한다.
- 같은 v4를 한 epoch 더 반복하는 E3가 아니다.
- 기존 공개 T3 fixture와 E1/E2 원본 24 reports는 진단·회귀 참고일 뿐 새 후보 선택
  근거로 재사용하지 않는다.
- blind response를 본 뒤 target, fixture, threshold, seed, step을 바꾸지 않는다.
- 운영 채택, 기본 서비스 모델·태그 변경은 별도 사용자 승인 전까지 금지한다.

교정 범위는 다음 여덟 축으로 제한한다.

1. 존재하지 않는 시청자 이름·닉네임 발명 억제
2. unknown identity의 안전하고 자연스러운 응답
3. 장기 callback과 방송 흐름 기억
4. 후원 호명·addressee·감사 의례·메시지 반응
5. 오래된 맥락 종료와 자연스러운 주제 전환
6. 사실 근거 활용과 complete show arc
7. 반말 방송체 유지와 존댓말 회귀 방지
8. transport·privacy·localhost·external-provider opt-in 회귀 방지

## 2. 고정 입력 provenance

| 입력 | 크기 | SHA-256 |
|---|---:|---|
| v4 source JSONL | 7,056,597 | `43f9c1ed1abf1d32c94329de81d8ba9ddef93f560ef914814d34e0520eeba2ed` |
| v4 chat JSONL | 6,886,621 | `96cc223ca5915355394480b60b459d9d039ffad4b47304974c5d939d4686eb44` |
| base `model.safetensors` | 4,611,084,960 | `394b6624de810fd0630ba451c31b3530cc26444ba0e1fa7d98842b6af6e8f506` |
| E2 adapter model | 56,318,520 | `2a72292c1f8b8a2b6551c7c842a63e130b4aba2ec119483c8d66d07384895c5b` |
| E2 adapter config | 863 | `e01129ea8e2237ef0dc297ffd3ea902a75f28d1b3ee2c34eee0b275d6a0382b0` |
| E2 artifact manifest | 2,141 | `70998cffe99a489e99272e41e264d5775ff221402dce9fbc63a7a74741747195` |
| E2 report | 1,536 | `628d640f17c7c1cb161b14c512e148b7dade0d721f0cb37a0748ee458fd6aa4c` |

E2 authority root는 `airi-broadcast-v4-e2-20260823-074326`이고 structured state는
`complete` revision 1,635, exit 0/`trainer-complete`, 1,600/1,600 microsteps,
100/100 optimizer steps, pending microbatch 0이다. E2 dev loss는 epoch 1
`2.893371758116589`, epoch 2 `2.735453106217887`이고 selected epoch은 2다.

## 3. 교정·replay·mixture 설계

### 3.1 교정 데이터

교정 데이터는 120 whole scenario groups × 4 views = 480행이다.

| family | total | train | dev | test |
|---|---:|---:|---:|---:|
| identity noninvention | 72 | 56 | 8 | 8 |
| unknown identity | 64 | 48 | 8 | 8 |
| long callback | 68 | 52 | 8 | 8 |
| donation ritual | 68 | 52 | 8 | 8 |
| stale transition | 56 | 40 | 8 | 8 |
| factual grounding | 56 | 40 | 8 | 8 |
| complete show arc | 56 | 40 | 8 | 8 |
| safety regression | 40 | 24 | 8 | 8 |
| **합계** | **480** | **352** | **64** | **64** |

whole 4-row group는 split을 가로지르지 않는다. exact/normalized prompt·target collision,
fact/update/decoy token split collision과 correction 내부 train/dev/test leakage는 0이어야
한다.

### 3.2 v4 replay

- v4 검증 예제 200행을 catastrophic forgetting 방지 replay로 포함한다.
- selection seed는 `4201`이다.
- train/dev/test는 `160/20/20`이고 원 v4 whole group·split을 보존한다.
- replay source object는 원본 v4 object와 exact equality여야 한다.
- v4 dev/test를 E2-C1 train으로 옮기지 않는다.

### 3.3 최종 mixture

- combined total은 680행, train/dev/test `512/84/84`다.
- train correction:replay는 `352:160 = 11:5`다.
- correction/replay provenance와 row order는 dataset/replay manifest에 결속한다.

다음은 full validation을 통과한 frozen dataset pin이다.

| 파일 | 크기 | SHA-256 |
|---|---:|---|
| correction source | 680,148 | `9fc5b7bc260ec510611eb3939642d3480aece869690f1a0a0552d2f58d496055` |
| correction chat | 591,202 | `faf9ec3703fb8f409088d5a934258a5087b0145ee93075ac35439fbab4ad674b` |
| mixture source | 2,092,813 | `fe532451c5b7f8cac9bee62f91242c09391cc7bff0b219477d91fb71f244e643` |
| mixture chat | 1,970,252 | `c845adfc2c50f36db6f73e6bda56be5b6e7bbaef0b72f91a1ed7a595221c1980` |
| dataset manifest | 36,660 | `fe1ca6c85654699b5c1db01af2a6e7598a3d97c00c5451bd752cef9f59f8c9d0` |
| replay manifest | 15,673 | `23883d8d0b3d0befb2baef8fe585a5948fa2016586e2c335bd206f241a86bbd5` |

## 4. 동결 학습 계약

| 항목 | 값 |
|---|---|
| candidate | `E2-C1` |
| initialization | base + E2 adapter weights only |
| optimizer/scheduler/cursor | fresh, no checkpoint resume |
| seed | `42` |
| LoRA r/alpha/dropout | `8/16/0.05` |
| batch | `1` |
| gradient accumulation | `16` |
| max sequence length | `2048` |
| max microsteps | `512` |
| max optimizer steps | `32` |
| learning rate | `1e-5` |
| optimizer | AdamW, betas `0.9/0.999`, eps `1e-8`, weight decay `0.01` |
| scheduler | constant `LambdaLR`, factor `1` |
| checkpoint interval | every `3` optimizer steps; actual interval must remain ≤600 seconds |
| launcher | authoritative durable runner only; direct trainer forbidden |

GPU 전에 adapter initialization seam의 provenance, fresh optimizer/scheduler/RNG/cursor,
run-state/checkpoint와 safe pause/resume를 확인하는 bounded smoke는 한 번만 허용한다.
smoke는 품질 진척이 아니다. smoke PASS receipt의 commit/push와 HEAD=origin/main clean,
관련 PID 0 뒤 fresh timestamped external root에서 본 학습을 step 0부터 실행한다.

## 5. retained blind와 평가 계약

external evaluator root는
`D:\AIRI-Models\airi-e2-c1-blind-freeze-20260824-000430`이다. repository에는 body를
넣지 않고 commitment·policy만 둔다. root는 body를 읽지 않았고
`response_viewed=false`다.

| role | size | raw SHA-256 | canonical SHA-256 |
|---|---:|---|---|
| identity/unknown/donation | 2,378 | `fdf0a26a976542e9a47d9b1f0b5d24d31d571bf4b48b7930806f04be12f26162` | `62accd68e1b40d7c57f6b3b85a61dc9bc24696dc121c80b5fb152e8bf0ca912d` |
| continuity/stale transition | 2,803 | `71010d62b9b609370521912d434777d7759cd862dbd2c9e82447adc0ea9b2fee` | `3a33a467f3997a780b3ce17393af5c85d0d58577f9005615507888fec2cbeab5` |
| factual/show arc | 2,953 | `13b433cf26da8ab4f938dd9886d664b681971663c8f70ba1bebde17707868e40` | `d021b6b3f2026c12b961472eca98af1322b800843567e745bba706db38401e30` |

sealed manifest는 1,128 bytes SHA
`b664d162840fa326312638a9b3e504e704e9db2be33208e23ac66bedc31def58`, validation receipt는
739 bytes SHA `b121a91536866cb0f6b749fdf4f776d5940a41d71fa04e2c45d194b29aebbe85`다.
validation은 fixture 3 × seeds 4 × arms 3 = 36 reports, body output false, public fixture
collision false, old fixture/report selection reuse false, thresholds frozen으로 PASS했다.

- arms: `baseline`, `e2`, `e2-c1`
- seeds: `[73, 89, 97, 20260824]`
- hard zero: transport, polite, invented handle, privacy, localhost exposure,
  external provider without opt-in
- hard perfect: unknown identity safe, donation name/addressee/thanks/message engagement,
  stale transition clean; decoy fact use는 0
- additive gates vs E2:
  - topic anchor `>=0.55`, delta `>=-0.02`
  - fact grounded usage `>=0.40`, delta `>=+0.10`
  - memory `>=0.50`, delta `>=+0.15`
  - long callback `>=0.50`, delta `>=+0.20`
  - complete show arc `>=0.75`, delta `>=+0.20`
- score weights: topic/fact/memory/long-callback/show-arc
  `0.15/0.25/0.20/0.20/0.20`
- unique top margin은 `>0.02`; E2-C1은 E2 대비 score delta `>=+0.08`과 additive 5축
  중 4축 이상 개선이 모두 필요하다.
- tie, missing/duplicate report, hard gate 실패는 `no_winner`다.

## 6. 조사 blocker 해결 receipt

checkpoint generator와 독립 verifier는 `(으로,로)`와 받침 ㄹ 예외를 지원하지 않아 다음
5개 target 결함을 놓쳤다. current implementation은 종성 없음과 종성 ㄹ에 `로`, 다른
종성에 `으로`를 선택하며 generator/independent mutation regression으로 이 공백을 닫았다.

| row id | actual | required |
|---|---|---|
| `e2c1-long_callback-001-v3` | `“지금 색을 고르는 흐름”로` | `“지금 색을 고르는 흐름”으로` |
| `e2c1-complete_show_arc-002-v2` | `“우산 그림”로` | `“우산 그림”으로` |
| `e2c1-complete_show_arc-003-v1` | `“창가 화분”로` | `“창가 화분”으로` |
| `e2c1-complete_show_arc-010-v2` | `“고양이 그림”로` | `“고양이 그림”으로` |
| `e2c1-complete_show_arc-011-v1` | `“구름”로` | `“구름”으로` |

write-free audit mismatch 0 뒤 generator overwrite는 intent대로 정확히 한 번 실행됐고
current generated audit도 mismatch 0이다. counts/splits/replay/training/blind pins는
바뀌지 않았다. 위 표의 actual/required는 해결 전 역사적 재현값이며 current target에는
required 형태만 있다.

## 7. 첫 milestone PASS 조건

다음 데이터·평가 freeze 조건은 current bytes에서 모두 PASS했다.

- [x] exact five 조사 오류 0 및 `(으로,로)` mutation regression PASS
- [x] correction 480/replay 200/mixture 680과 split/family/group/11:5 exact
- [x] replay object equality와 v4 split 보존
- [x] prompt/target/token collision·contamination 0
- [x] family semantic metadata와 target coverage 전수 PASS
- [x] generator byte-stable `--check`, independent repository/external verifier PASS
- [x] blind body Git/training-path 노출 0, commitment/sealed/receipt exact
- [x] targeted tests, CI registration, diff/security/binary/oversize boundary PASS
- [ ] frozen milestone commit/push 뒤 HEAD=origin/main clean, staged/untracked 0, 관련 PID 0

마지막 항목은 repository publication gate다. 그 전에는 `gpu_authorized=false`를 유지한다.

## 8. 이후 fail-closed 순서

1. 검증된 frozen-contract milestone commit/push
2. adapter-init bounded GPU smoke 1회와 receipt commit/push
3. fresh external root에서 durable E2-C1 본 학습 step 0
4. adapter/config/report·epoch dev loss·selected epoch·E2 대비 회귀/개선 검증
5. safe merge → BF16 GGUF → Q4_K_M 및 exact tag/digest manifest
6. baseline/E2/E2-C1 × blind 3종 × seed 4 = 36 reports
7. hard/additive gate로 unique winner 판정
8. winner가 있을 때만 3 seed × 500 turn full-stack campaign
9. 실제 response·failure·invented handle·memory·repetition·context break·donation·transition·
   TTS/RAG/latency/trace/hash 사용자 판단 묶음 제출

T3 winner가 없으면 campaign과 운영 채택을 금지하고 실패 receipt만 commit/push한다.
사용자 승인 없이 E2-C2, 추가 epoch, 새 모델, 같은 blind 재실행을 자동 시작하지 않는다.

## 9. 검토 PC 재개 순서

1. `AGENTS.md`
2. `airi_docs/진행중/AIRI-WORKING-STATE.md`
3. `airi_docs/진행중/AIRI-CODEX-HANDOFF-2026-08-21.md`
4. `airi_docs/로드맵/AIRI-ROADMAP-STATUS.md`
5. `NEXT-SESSION.md`

위 5개를 전체 읽은 뒤 actual Goal, HEAD/local·remote main, worktree/stage, related PID,
E2 state/checkpoints, T3 inventory와 blind sealed receipt를 read-only로 대조한다. PID 0이면
pause를 실행하지 않는다. 이 checkpoint의 중복 판별 identity는 pre-intent HEAD
`911179286ae32c7d5922358bcc5cb1741e58a5c9`, checkpoint ID
`20260824-020037-e2-c1-full-freeze-validation-receipt-docs-intent`, HEAD `1de57a2`, 위
frozen code/data SHA, external blind root와 E2-C1 0/0/PID 0이다. 첫 동작은 frozen milestone
commit/push가 실제로 끝났는지 확인하는 것이다. clean/PID 0 전에는 GPU로 이동하지 않는다.

## 10. 2026-08-24 02:00 KST full freeze validation receipt

- pinned Python 3.12 pycompile: exit 0
- generator + independent verifier unit: 12 tests OK
- blind commitment pytest: 5 passed
- generator byte-stable `--check`: PASS
- repository-only verifier: PASS, correction/replay/mixture `480/200/680`
- external blind-root verifier: PASS, 같은 counts와 mixture chat SHA exact
- work-continuity: exit 0/literal PASS
- repository diff-check: exit 0, expected line-ending warning only
- independent current dataset audit: correction/replay/mixture 480/200/680, correction split
  352/64/64, mixture split 512/84/84, exact family splits, whole groups 120/bad 0,
  unique prompts/targets 480/480, cross-split collisions 0, metadata complete 480,
  factual decoy hit 0, `(으로,로)` 포함 quoted-josa mismatch 0, replay object mismatch 0,
  train correction/replay 352/160
- current 11-path boundary: 6,156,910 bytes, forbidden artifact/extension, NUL, oversize,
  strong credential와 personal path hit 0

checkpoint 단계의 첫 병렬 Python 검증 6개는 PowerShell call operator `&` 누락으로
interpreter 실행 전 parser exit 1, 첫 Hangul wrapper는 expected string interpolation parse
error로 exit 1이었다. 둘 다 mutation 0/비권위였고 corrected PASS가 대체한다.

결론: current data/evaluation contract의 freeze gate는 PASS했다. remaining blocker는 이
frozen contract와 SSoT의 commit/push/HEAD clean뿐이며 그 전에는 GPU를 시작하지 않는다.
