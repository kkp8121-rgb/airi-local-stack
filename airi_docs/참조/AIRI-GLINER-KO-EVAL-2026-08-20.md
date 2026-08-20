# GLiNER 계열 한국어 엔티티 추출 실측 (2026-08-20)

**목적**: `AIRI-MEMORY-TECH-RESEARCH-2026-08-18.md` 실행 로드맵 ⑤·§7의 잔여
미확인 사항 — "GLiNER2 한국어 NER 품질 미실측" — 을 해소한다. LLM 0회
(LLM-free) 엔티티 후보축으로 GLiNER 계열이 AIRI의 추출 게이트(Stage A)에
보조 필터·후보 프리필터로 쓸만한지 실측 판정한다.

**범위 한정**: 측정 전용 작업이다. 레포 코드는 무수정이며, 측정 스크립트·
중간 산출물은 세션 scratchpad에 위치한다(레포 밖).

---

## 0. 원 리서치 문서 용어 정정 (SSoT 정합성)

`AIRI-MEMORY-TECH-RESEARCH-2026-08-18.md` §2(114-117행)는 "GLiNER2(205M~340M
비-LLM zero-shot NER, Graphiti `gliner2_client.py`가 사용)"라고 인용하고,
§7(326-328행)은 "GLiNER-Multi의 다국어(MultiCoNER 11개 언어) 실측은
ChatGPT를 상회하나 한국어 개별 수치는 미확인"이라 기술한다. 실측 결과 이
둘은 **서로 다른 두 세대의 별개 프로젝트**이며, 혼용하면 안 된다는 점을
정정한다:

- **GLiNER2** (pip `gliner2`, Fastino AI, 2025 EMNLP demo) — 모델은
  `fastino/gliner2-base-v1`(205M)·`fastino/gliner2-large-v1`(340M) 2종
  뿐이며, HuggingFace 모델 카드에 **English 단일 언어 태그만** 있다.
  한국어·다국어 학습 근거 없음 — 이 계열은 **한국어 후보에서 제외**.
- **GLiNER** (pip `gliner`, urchade 원조 아키텍처, 2023 arXiv:2311.08526) —
  `urchade/gliner_multi-v2.1` 등 다국어 계열(mDeBERTa-v3-base 기반)이
  존재하나 학습 언어 목록에 한국어가 명시적으로 확인되지 않았다. 대신
  커뮤니티가 mDeBERTa 한국어 특화 백본(`lighthouse/mdeberta-v3-base-kor-further`)
  으로 파인튜닝한 **`taeminlee/gliner_ko`**가 존재하며, 이것이 이번 실측
  대상이다.

즉 로드맵이 지목한 "GLiNER2"는 한국어를 지원하지 않고, 한국어가 실제로
되는 쪽은 이름이 다른 원조 GLiNER 계열의 커뮤니티 파인튜닝 모델이다. 향후
문서에서 "GLiNER2"와 "GLiNER(-Multi/-ko)"를 구분해 표기할 것을 제안한다.

---

## 1. 설치 내역

| 항목 | 값 |
|---|---|
| venv 경로 | `C:\tmp\glinervenv` (짧은 경로 — torch WinError 206 함정 회피, 문제 없이 로드 확인) |
| Python | 3.12.10 |
| torch | 2.13.0+cpu (`--index-url https://download.pytorch.org/whl/cpu`로 설치, CUDA 불필요) |
| gliner | 0.2.28 |
| python-mecab-ko | 1.3.7 (+ `python-mecab-ko-dic` 2.1.1 — Windows용 사전 빌드 wheel 존재, 별도 mecab 바이너리 설치 불필요) |
| 모델 | `taeminlee/gliner_ko` (base encoder: `lighthouse/mdeberta-v3-base-kor-further`) |
| 모델 다운로드 | HuggingFace Hub에서 정상 다운로드(1회 성공, 재시도 불요), 로드 포함 약 102초 |
| 라이선스 | **CC-BY-NC-4.0 (비상업)** — 저자가 "연구용" 명시. AIRI가 이 모델을 상용 배포 경로에 넣을 계획이면 라이선스 재검토 필요(확인 필요로 남김). |

**모델 선택 근거**: 브리프가 요구한 "한국어/다국어 지원 소형" 조건에서,
① `gliner2`(Fastino)는 영어 전용이라 배제, ② `gliner_multi-v2.1`은
다국어이나 한국어 학습 여부가 모델 카드에 명시되지 않아 불확실, ③
`taeminlee/gliner_ko`는 KONNE 벤치마크(한국어 15종 개체명) 기준
Precision 72.51 / Recall 79.82 / F1 75.99로 **한국어 학습이 실측 문서화된
유일한 소형(mDeBERTa-base급, ~279M 추정) 후보**였다. 이 근거로
`taeminlee/gliner_ko`를 1순위로 채택했다.

---

## 2. 측정 방법

**데이터셋**: `ollama-proxy/training/seed/airi_extraction_seed_pending.jsonl`
(102건). 실측 확인: 96건이 1개 이상의 정답 항목을 가지며 합산 144개 gold
항목(entity 72 + relation 36 + fact 36), 6건(`skip_chatter`)은 정답이
`extracted: []`(추출 0건이 정답)이다 — 브리프의 "96/144" 수치와 일치.

**gold name 필드 정의**: `target.extracted[]`의 각 항목은 kind에 따라
name 보유 필드가 다르다 — `entity`는 `name`, `relation`은 `sourceName`+
`targetName`, `fact`는 `subjectNames`(배열). 144개 gold 항목 전체에서
이 필드들을 모으면 이름 참조 180개(relation 항목이 2개씩 참조하므로 항목
수보다 많음)가 나온다. **항목 단위(item-level) 채점**을 기본으로 하되
(브리프의 "144항목"과 정합), relation/fact처럼 이름이 여러 개인 항목은
"이름 중 하나라도 GLiNER가 잡으면 hit"(any-hit)으로 1차 집계하고,
"관련된 이름을 모두 잡아야 hit"(all-hit, 엄격판)을 보조 지표로 별도
계산했다 — any-hit만 보면 relation 회수율이 과대평가될 수 있어서다(§4
참고).

**GLiNER 호출**: `model.predict_entities(turns_text, labels, threshold=0.5)`.
`turns` 필드는 실제 프로덕션 입력 포맷 그대로(`[turn N] ...` 접두 포함)
사용 — 가공 없이 그대로 넣었다.

**라벨 프롬프트 선택**: 스모크 테스트에서 한국어 라벨(`["인물","조직",
"사물"]`)과 영어 라벨(`["person","organization","item"]`)을 비교한 결과
**영어 라벨이 일관되게 더 높은 신뢰도**를 보였다(예: "새벽 공방" 조직
탐지 신뢰도 0.556→0.910). 최종 측정은 영어 라벨로 진행 — 이 자체가
"한국어 인식 품질" 관찰 항목 중 하나다(§4).

**관대 매칭 정의**: `lenient_match(gold, pred)` = (완전일치) OR (한쪽이
다른 쪽의 부분 문자열) OR (말미 1~2글자 제거 변형끼리 위 조건 성립 —
조사 결합 잔차 흡수용). 코드: `scratchpad/gliner/run_eval.py`.

**환경/CPU 참고**: 측정 PC는 AMD Ryzen 7 8700G(8코어/16스레드), CUDA
미사용(CPU 전용 torch). 이 환경에 대해 실행 중 프로세스 단위 CPU 점유율을
별도 계측하지는 않았다(확인 필요) — 다만 레포 문서(`AIRI-LOCAL-TECH-SPECS.md`
등)에 백그라운드 작업 CPU 사용률 캡(최대 70%) 정책이 기록되어 있어,
아래 지연시간은 **절대 성능치가 아닌 참고치**로만 사용할 것.

---

## 3. 결과

### 3.1 전체 겹침률 (item-level recall, any-hit)

| 지표 | 값 |
|---|---|
| 전체 gold 항목 | 144 (96레코드) |
| GLiNER 적중 | 105 |
| **전체 겹침률** | **72.9%** (105/144) |
| `{{user}}` 플레이스홀더 관련 24항목 제외 시 | 105/120 = **87.5%** |
| skip_chatter 6건 과추출 | **0건 / 6건** (완전 무과추출) |

`{{user}}`는 AIRI 시드가 사용하는 템플릿 치환 토큰이며 자연어 개체명이
아니다 — 어떤 라벨 프롬프트로도 GLiNER(혹은 일반 NER 모델)가 이를
"사람"으로 인식할 수 없는 것은 **모델 결함이 아니라 데이터 포맷 특성**
이므로, 이 24항목을 제외한 87.5%가 "실제 한국어 NER 역량"에 더 가까운
수치다.

### 3.2 kind·subtype별 breakdown (any-hit)

| kind:subtype | 총 항목 | 적중 | 회수율 |
|---|---|---|---|
| entity:person (실제 캐릭터명만, `{{user}}` 12건 제외 시 36/36) | 48 | 36 | 75.0%(전체) / **100%**(실명만) |
| entity:organization | 12 | 9 | 75.0% |
| entity:item | 12 | 0 | **0.0%** |
| relation:affiliation | 12 | 12 | 100%(any-hit) |
| relation:uses | 12 | 0 | 0.0%(any-hit — `{{user}}`+item 조합이라 구조적으로 0) |
| relation:friendship | 12 | 12 | 100% |
| fact:trait | 18 | 18 | 100% |
| fact:moment | 18 | 18 | 100% |

**relation 엄격판(all-hit — 양쪽 이름 모두 GLiNER가 잡아야 인정)**:
36건 중 21건 = **58.3%** (affiliation 9/12 + friendship 12/12 + uses 0/12).
any-hit 100%(affiliation/friendship)는 "사람 이름 쪽만 잡혀도 hit" 처리의
결과이므로 실제 관계 추출 보조용으로는 이 58.3%가 더 현실적인 참고치다.

### 3.3 한국어 인식 품질 관찰

1. **실제 캐릭터명(고유명사) 인식은 사실상 완벽** — 36/36(100%), 신뢰도
   대부분 0.99+.
2. **조사(particle) 처리**: mecab-ko 형태소 분석기가 대부분의 경우 조사를
   정확히 분리했다(예: "세라은" → `세라`+`은`, span은 조사 제외 `세라`만
   반환). 다만 **OOV(사전 미등재) 합성 이름 + 특정 조사 결합에서 실패
   사례 발견** — "세라이"(주격조사 이형태 결합, 6건) 케이스에서 mecab이
   `세라`+`이`로 분리하지 못하고 통짜로 `세라이`를 하나의 span으로 반환.
   관대 매칭(부분 문자열) 없이 완전일치만 썼다면 이 6건(105건 중 5.7%)이
   누락되어 전체 겹침률이 72.9%→68.75%로 떨어졌을 것 — **조사 결합 잔차
   흡수가 실사용에도 별도 후처리로 필요함을 시사**.
3. **라벨 프롬프트 언어가 신뢰도에 유의미한 영향** — 영어 라벨
   ("organization")이 한국어 라벨("조직")보다 일관되게 높은 신뢰도.
   모델이 영어 학습 데이터 비중이 높을 가능성을 시사(한국어 특화라도
   라벨 스키마는 영어 프롬프트가 유리).
4. **"item"(사물/아이템) 카테고리는 명확한 취약점** — 12/12 완전 누락,
   threshold를 0.05까지 낮춰도 최대 신뢰도 0.17(예: "바람 피리") 수준.
   허구/판타지풍 사물명(예: "청동 열쇠", "유리 등불")이 학습 데이터의
   ARTIFACTS 분포와 거리가 있는 것으로 추정 — **item 카테고리는 GLiNER
   단독으로 신뢰 불가**.
5. **`[turn N]` 접두 태그로 인한 오탐은 threshold=0.5 기준 0건** —
   전체 144개 예측 span 중 태그 관련 오탐 없음(단, threshold를 0.05까지
   낮추면 `[turn N]`이 item으로 오탐되는 사례가 나타나 — 낮은 threshold
   운용 시 주의 필요).
6. **skip_chatter 6건 전원 과추출 0건** — 일상 잡담성 텍스트에서 결정론적
   침묵(entity 리스트 빈값)을 유지했다. 이는 "후보 프리필터"로 쓸 때
   가장 중요한 성질(불필요한 노이즈 후보를 만들지 않음)이 확인된 것.

### 3.4 지연시간 (참고치 — 절대 성능 아님)

| 지표 | 값 |
|---|---|
| 평균 | 0.146s / 요청 |
| 중앙값 | 0.140s |
| p95 | 0.172s |
| 최대 | 0.374s |

단건 순차 호출(배치 미사용), CPU 전용(Ryzen 7 8700G), CPU 캡 정책 적용
여부 미계측 조건에서의 수치다.

---

## 4. 판정

**조건부 채택 가치 있음** — 근거: 실제 고유명사(인물) 인식은 사실상
완벽(100%)하고 잡담 텍스트에서 과추출이 0건으로, "LLM 호출 전에 후보를
좁히는 1차 필터"(예: Stage A 후보 프리필터·정답 검증 보강 축)로 쓰기에
충분한 정밀도-특이도 프로파일을 보인다. 다만:

- **entity:item(사물) 카테고리는 채택 범위에서 제외**해야 한다(0%
  회수율) — person/organization 두 타입 한정 채택을 제안.
- **`{{user}}` 같은 템플릿 토큰은 GLiNER(또는 어떤 NER이든) 앞단에서
  규칙 기반으로 별도 치환/보존 처리**가 필요 — NER 모델 교체로 해결될
  문제가 아니다.
- **조사 잔차 흡수용 후처리(말미 1~2글자 정규화 매칭)** 없이 완전일치만
  쓰면 회수율이 4%p가량 저평가된다 — 실전 도입 시 이 관대 매칭 로직을
  같이 이식해야 한다.
- **CC-BY-NC-4.0 비상업 라이선스** — 프로덕션 상용 배포 계획이 있다면
  라이선스 재검토 필요(확인 필요로 유보).
- 본 실측은 **96레코드/144항목의 합성(synthetic) 시드 데이터** 기준이며
  실제 사용자 발화의 다양성·비정형성은 반영하지 않는다 — 표본 규모·
  분포 한계를 감안해 해석할 것.

---

## 5. 산출물

- 측정 스크립트: `scratchpad/gliner/prep_gold.py`, `run_eval.py`,
  `smoke_test.py` (세션 scratchpad, 레포 밖)
- 원시 결과: `scratchpad/gliner/eval_results.json`,
  `scratchpad/gliner/gold_flat.json`, `scratchpad/gliner/smoke_out.json`
- venv: `C:\tmp\glinervenv` (재현 시 재사용 가능, 레포에는 미포함)
