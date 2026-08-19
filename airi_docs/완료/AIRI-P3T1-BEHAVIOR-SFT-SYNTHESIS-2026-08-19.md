# P3-T1 — 행동 SFT 학습 데이터 합성 (2026-08-19, 클로드 PC)

> 사용자 방향 확정("모델을 학습시키는 방향으로") 후 첫 배치. 로드맵
> P3를 학습 트랙(P3-T1~T4) 주 경로로 재정의하고, T1(데이터 합성)을
> 구현·생성했다. 기존 `training/` governance(합성→pending→**인간
> 검수**→승인→로컬 QLoRA)를 그대로 따른다 — **이 데이터만으로는 학습
> 불가**(`training_eligible: false`).

## 1. 왜 이 4행동인가 — 전부 실측된 실패다

| behavior | 건수 | 타깃 실패 (실측 근거) |
|---|---:|---|
| `fact_recall` | 126 | 사실 활용 7% 동결 — **운영 브리핑 포맷 그대로** 학습쌍에 넣어 "메모를 읽고 쓰는 행동" 자체를 가르친다 |
| `addressee` | 15 | 생일 반사 4/4·수신자 혼동(계약 v3 케이스워크 기반: 생일 후원·축하 받기·부탁은 내 몫·놀림 받아치기·행위 주체) |
| `register` | 10 | 존댓말 입력에 반말 응답 유지 |
| `substance` | 30 | 단답·몰개성 — 같은 입력에 서로 다른 실질 응답 3종씩 |
| 합계 | **181** | train 145 / dev 18 / test 18 |

## 2. 구현 (전부 결정론 — RNG·LLM 호출 0)

- `training/behavior_synthesis_config_v1.json` — 모든 문구·값·한도가
  이 테이블에 있다(매직넘버 0). 사실 8종×값 5~6개×질문 3형.
- `training/synthesize_behavior_pending.py` — 열거식 생성.
  **조사 엔진**: `{j_ya}/{j_eun}/{j_i}/{j_rago}` 토큰을 **직전 글자의
  받침**으로 해석(값 기준이 아님 — "별명은 반짝이야"가 첫 생성에서
  "별명는"으로 나온 실측 버그를 수리하고 회귀 테스트로 고정).
- **정답 게이트 내장**: 모든 answer가 방송 채점기(`score_response`)를
  통과해야 기록된다 — 존댓말 위반 정답이 하나라도 있으면 게이트가
  잡는 결함을 그대로 가르치게 되기 때문. 생성 181/181 banmal 확인.
- `training/seed/airi_behavior_pending_record.schema.json` — style
  파이프라인과 동형의 pending 계약(S1·review pending·eligible false).
- 테스트 6종(`training/tests/test_synthesize_behavior_pending.py`):
  결정론·**커밋 큐=생성기 출력 바이트 일치**·스키마 전수·register
  게이트 전수·운영 브리핑 포맷·조사 정합. 트레이닝 스위트 45 passed,
  CI `ollama-proxy-training` 샤드 등록.

## 3. 다음 (P3-T2~T4)

1. **T2-a 인간 검수** — 사용자 검수 필요. 기존 style 검수 CLI는 스키마가
   달라 behavior 큐를 못 읽는다 → **검수 UX(HTML 폼 또는 CLI 확장)를
   T2 착수 시 제공**. 검수 통과분만 학습 자격.
2. **T2-b QLoRA 학습** — 코덱스 GPU. 기존 트레이너는 style 데이터셋
   계약에 고정돼 있어 behavior 포맷(브리핑 필드 포함) 지원 확장 필요.
3. **T3 게이트** — 시뮬 하네스 전/후(fact_usage 7% 기준선 대비) +
   존댓말·addressee 회귀 가드 전부.
4. **T4** — 통과 행동부터 하드코딩 축소(thank 렌더러는 유지).

## 4. 한계

- 181건은 시드 규모다. style 정책 v3의 최소 200건 검수 기준을 참고하면
  검수 후 증분 생성(config 값 확장으로 즉시 가능)이 필요할 수 있다.
- 합성 데이터의 다양성은 템플릿 조합의 상한을 가진다 — T3 게이트가
  과적합(같은 문형 반복)을 잡는 안전망이다.
- briefing 필드는 fact_recall에만 있다. 학습 시 briefing을 시스템
  프롬프트에 넣는 조립은 T2-b 트레이너 확장 소관.

산출물: `training/seed/airi_behavior_seed_pending.jsonl`(181행).
관련: `완료/AIRI-P1-LEVER-EXHAUSTION-P3-GATE-2026-08-19.md`(게이트 판정),
`training/README.md`(governance), 로드맵 v3 §3 P3-T.
