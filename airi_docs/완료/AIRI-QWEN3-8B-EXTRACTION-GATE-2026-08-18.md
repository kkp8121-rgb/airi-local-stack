# Qwen3-8B 추출 게이트 실측 — 크기 가설의 부분 반증 (2026-08-18, 클로드 PC)

## 결론 (먼저)

**Qwen3-8B는 full balanced 게이트를 통과하지 못했다.** 다만 지금까지
2~4B 후보 9종이 전부 즉시 실패했던 `persistent_trait` 단일 스모크는
**만점으로 통과**했다(recall 1.0 / unexpected 0 / alias 1.0 / gate_pass
true) — 이 스모크만 놓고 보면 리서치의 "2~4B 역량 한계" 가설과 부합한다.

그러나 같은 하네스로 **2.4B / 4B / 8B 3점 계열**을 전부 돌린 결과는
가설을 부분적으로 반증한다:

> **크기는 환각(unexpected)과 구조적 실패를 줄이지만, critical recall은
> 0.43~0.50에서 정체한다.** 즉 게이트를 막고 있는 것은 이 구간의
> 파라미터 수가 아니다.

따라서 **"더 큰 추출 모델"은 다음 수순이 아니다.** 리서치 §3-⑤가
후순위로 적어둔 **Stage A 재설계(생성 → 스팬 선택 + 코드 검증)**가
실제로는 선행 과제다. extraction은 계속 **OFF**다.

## 1. 실측 — 같은 하네스, 같은 옵션, 크기만 다름

`benchmark_memory_track.py --mode extraction --gate-profile balanced`
(7 fixtures 전량, fail-fast 없음), 격리 Ollama **11436**,
`num_gpu=0`, `num_ctx=8192`, `temperature=0`, `seed=42`, `think=false`,
`max_tokens=2048`, Stage A `conversation-v2b`, Stage B `decision-v2.1`,
cloud disabled.

| 지표 (balanced 기준) | exaone-airi **2.4B** | qwen3 **4B** | qwen3 **8B** | 통과선 |
|---|---:|---:|---:|---|
| schema / Stage A / Stage B | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 | — |
| connectivity | 0.571 | **1.0** | 0.714 | — |
| Stage B coverage | 0.857 | 0.714 | **1.0** | — |
| **critical recall** | 0.500 | 0.476 | 0.429 | ≥0.7 ❌ |
| **unexpected (건)** | **9** | 2 | 2 | rate ≤0.25 ❌ |
| placeholder | 0.857 | 0.857 | 0.857 | ≥0.85 ✅ |
| **op/alias accuracy** | 0.429 | 0.429 | 0.286 | ≥0.8 ❌ |
| failure codes | 1 | 2 | **0** | — |
| gate_pass | false | false | **false** | |
| total p50 (CPU) | 17,589 ms | 11,203 ms | 15,641 ms | — |

**크기가 실제로 고친 것**: 환각 추출 9건 → 2건(2.4B→4B에서 이미 해소),
구조적 실패 코드 0건(8B만), Stage B coverage 1.0(8B만).
**크기가 고치지 못한 것**: critical recall(0.50 → 0.48 → 0.43, 오히려
소폭 하락), alias accuracy(0.43 → 0.43 → 0.29).

recall/alias의 모델 간 차이는 fixture 7개·1회 실행 기준으로 **노이즈와
구분되지 않는다**. 반면 unexpected 9 → 2와 failure code 2 → 0은 방향이
일관된 개선이다.

### 스모크 대조 (기존 후보와 동일 조건)

| 후보 | `persistent_trait` 스모크 |
|---|---|
| Ministral 3 3B / Phi-4-mini 3.8B / Granite 3.3 2B / Kanana 2-3B (2026-08-13) | 전부 FAIL (recall 0~0.5) |
| **qwen3:8b (이번)** | **PASS** — recall 1.0, unexpected 0, alias 1.0, coverage 1.0 |
| qwen3:4b (이번, full 게이트 내) | recall 0.0 |
| exaone-airi:2.4b (이번, full 게이트 내) | recall 0.0 |

## 2. 왜 recall이 안 오르나 — 실패 2건 원문 진단

8B가 recall 0.0을 낸 두 fixture의 Stage A 산출물을 직접 뽑아 대조했다.

**`update_alias`** — 입력 `[turn 9] 하린은 이제 달빛 길드의 단장이 되었다.`

| | 내용 |
|---|---|
| 기대 | `entity/person 하린` (Stage B가 후보 `e0`를 UPDATE_ENTITY 하도록) |
| 실제 | `entity/organization 달빛 길드` (content: "단장이 되었다") |

상태가 바뀐 **주체**(하린)가 아니라 문장에 등장한 **다른 엔티티**를
집었다. 스키마는 완벽하고 문장 이해도 틀리지 않았다 — "무엇을 뽑아야
하는가"의 규약이 프롬프트에 충분히 박혀 있지 않다.

**`placeholder_connectivity_add`** — 입력 `하린은 달빛 길드 소속의
마도사다. {{user}}는 하린의 조수이며 별빛 나침반을 사용한다.`

| | 내용 |
|---|---|
| 기대 | `{{user}}` 엔티티 + 달빛 길드 + 별빛 나침반 + 관계 2종 |
| 실제 | 달빛 길드 ✅, 별빛 나침반 ✅, 하린→달빛 길드 ✅, **{{user}}→하린**(기대는 {{user}}→별빛 나침반), **`{{user}}` 엔티티 누락** |

5개 중 3개를 맞혔고(Stage A recall 0.6), 놓친 것은 **플레이스홀더
`{{user}}`를 엔티티로 등록하는 규약**이다. 이것도 능력이 아니라 규약
문제다.

두 사례 모두 "모델이 못 읽었다"가 아니라 **"우리 계약을 모른다"**에
가깝다. 파라미터를 늘려도 계약이 전달되지 않으면 그대로 실패한다 —
실제로 8B가 4B보다 이 두 건에서 나아지지 않았다.

## 3. 리서치 문서 정정

`참조/AIRI-MEMORY-TECH-RESEARCH-2026-08-18.md`의 다음 두 항목을 이번
실측으로 갱신한다.

- §3-② "Qwen3-8B를 M0 게이트에 투입" → **실행 완료, 결과 FAIL.**
  8B 투입은 유효한 실험이었고 스모크 통과라는 신호를 얻었지만
  full 게이트 통과 수단은 아니다.
- §7 한계 "Qwen3-8B 게이트 미실측" → **해소.**
- §1 표의 "2~4B 역량 한계" 3중 확증 → **범위 축소.** 학술 근거
  (Qwen-2.5-3B 포맷 오류 30.38%)와 OSS 근거(3B 3/6)는 모두 **스키마·포맷
  준수** 실패를 다룬다. 그런데 AIRI는 constrained decoding 덕에
  **2.4B에서도 schema_pass_rate 1.0**이라 그 실패 모드가 애초에
  발생하지 않는다. AIRI의 실패는 recall/alias, 즉 "무엇을 뽑을지"의
  판단이고, 이 축은 8B에서도 개선되지 않았다.

## 4. 권고 (다음 수순)

1. **Stage A 재설계 선행** — 리서치 §3-⑤의 "생성 → 스팬 선택 + 코드
   검증"(rag_cache 앵커 패턴). 위 진단 2건은 전부 스팬 선택 + 규칙
   검증으로 잡히는 유형이다.
2. **규약 명시 보강** — 상태 변화의 주체 우선, `{{user}}` 플레이스홀더
   등록 의무를 Stage A 프롬프트/스키마 설명에 못 박고 재측정. 저비용
   실험이고 위 진단이 직접 근거다.
3. 그 다음에도 모자라면 그때 8B급 + 좁은 LoRA(리서치 §2-1 LightMem)를
   검토한다. **모델 크기 확대 단독은 근거가 없다.**
4. extraction 활성화(`extraction_enabled=true`)는 **full balanced PASS
   기록 전까지 하지 않는다** — 기존 운영 경계 그대로.

## 5. 운영 경계 / provenance

- 실행은 전부 **격리 포트 11436**(`OLLAMA_NUM_PARALLEL=1`,
  `OLLAMA_MAX_LOADED_MODELS=1`)에서만 했고, 측정 후 **중지**했다.
  production 11434의 설정·프로세스와 11435 proxy는 건드리지 않았으며
  종료 후 `/api/ps`가 빈 목록(active runner 없음)임을 확인했다.
- 모델 provenance (Ollama tag digest / 설치 바이트 / 파라미터 / 양자화):

| tag | digest | bytes | params | quant |
|---|---|---:|---|---|
| `qwen3:8b` | `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41` | 5,225,388,164 | 8.2B | Q4_K_M |
| `qwen3:4b` | `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7` | 2,497,293,931 | 4.0B | Q4_K_M |
| `exaone-airi:2.4b` | `39806659ed1ad9248a729a7bc28a46b3ae73be57aa4f816b49ad551f865d1227` | 1,644,933,429 | 2.7B | Q4_K_M |

- 원 리포트(force-add로 추적):
  `ollama-proxy/eval/results/extraction-gate-qwen3-8b-balanced-2026-08-18.json`,
  `…-qwen3-4b-balanced-2026-08-18.json`,
  `…-exaone-airi-2.4b-balanced-2026-08-18.json`,
  `…-qwen3-8b-persistent-trait-smoke-2026-08-18.json`.
- 최초 스모크 1회는 `--ollama-url`에 `/api/chat` 경로를 빠뜨려
  `stage_a_transport`(32ms)로 실패했다. 이는 **모델 품질 판정에 쓰지
  않았고**, 경로 교정 후 재실행한 결과만 위 표에 있다.

## 6. 한계

- fixture 7개·모델당 1회 실행이다. `temperature=0`/`seed=42`로 재현성은
  있으나 **표본이 작아** 모델 간 recall 0.43 vs 0.50 차이는 유의하다고
  말할 수 없다. 방향이 일관된 것은 unexpected(9→2)뿐이다.
- 하네스가 `think=false`를 고정한다. Qwen3는 하이브리드 추론 모델이라
  이 설정이 8B에 불리할 수 있고, constrained decoding이 추론형 태스크를
  해친다는 보고("Let Me Speak Freely?", arXiv:2408.02442)도 리서치에
  이미 인용돼 있다. 즉 이번 수치는 **Qwen3-8B의 상한이 아니라 현행
  계약 하의 값**이다.
- 8B는 Qwen3 한 계열만 봤다. 한국어 특화 8B급(예: Kanana 8B 계열)은
  미측정이다.
- CPU 실행이라 지연 수치는 운영 대표성이 없다(GPU 재측정은 코덱스 소관).

관련: `참조/AIRI-MEMORY-TECH-RESEARCH-2026-08-18.md`(가설 출처),
`완료/AIRI-NEW-LOCAL-EXTRACTION-CANDIDATE-SMOKES-2026-08-13.md`(2~4B 선례),
`완료/AIRI-KANANA-EXTRACTION-CANDIDATE-GATE-2026-08-13.md`(스모크 프로토콜).
