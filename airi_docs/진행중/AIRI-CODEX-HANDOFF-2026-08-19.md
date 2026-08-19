# 코덱스(GPU dev PC) 통합 인계 — 2026-08-19 (클로드 PC 발신)

> 2026-08-18~19 클로드 PC 배치 전체를 소화한 뒤의 **코덱스 대기열
> 단일 SSoT**다. 진입 순서: 이 문서 → `로드맵/AIRI-ROADMAP-STATUS.md`
> (v3 — 최상위) → `로드맵/AIRI-ROADMAP-LOG.md` 최근 항목.
> 클로드 PC는 무GPU라 아래 작업은 전부 코덱스 몫이다.

## 0. 먼저 알아야 할 구조 변화 (2026-08-19)

1. **로드맵 v3** — 주 지표가 위반률(빼기)에서 **발화 실질(더하기)**로
   교체됐다. 갱신 로그 기록 의무는 `AIRI-ROADMAP-LOG.md`로 이동
   (STATUS 본문은 상태 변화 시에만).
2. **P3 = 학습 트랙이 주 경로** (사용자 확정 — "모델을 학습시키는
   방향"). 체급 A/B는 보조(P3-M)로 강등.
3. **운영 기본값 변경** (`start-local-ollama-proxy.ps1`, 전부 사용자
   승인): `AIRI_IMMEDIATE_ACK=marker`(ACK "응!" 발화 제거 — C안),
   침묵 폴백 풀 ON, 방송 계약 v3 ON, 기억 가드 ON.
4. **레거시 문서 정리** — 08-13 이전 인계문은 전부 `아카이브/`
   (현재 상태 검증 사용 금지).

## 1. 최우선 — P3-T2-b: QLoRA 학습 실행

데이터 측은 클로드 PC에서 완결됐다. 흐름:

```
[완료] 합성 181건 → [사용자] 검수 폼 회신 → [완료] apply_behavior_review_reply.py
  → seed/airi_behavior_reviewed.jsonl → [완료] export_behavior_chat_dataset.py
  → seed/airi_behavior_chat_sft.jsonl (chat messages 포맷, 운영 프롬프트 그대로)
  → [코덱스] QLoRA 학습 ← ★여기부터
```

**주의 — 기존 트레이너는 그대로 못 쓴다**:
`train_airi_style_qlora.py`는 **EXAONE config에 하드 핀**돼 있다
(`expected_exaone_config`, 08-07 시절). 필요 작업:
- Mi:dm(`K-intelligence/Midm-2.0-Mini-Instruct`) 재핀 + config 계약 교체
- 입력을 chat-format JSONL(`messages` 배열)로 — 익스포터 산출물 그대로
- 기존 fail-closed 계약(로컬 전용·어댑터 전용·CUDA 필수·해시 검증)은
  유지할 가치가 있다 — 구조를 버리지 말고 모델 계약만 바꿀 것
- 학습 후 어댑터를 Ollama 태그로 만들어 T3 게이트에 넣는다

**T3 게이트 (학습 전/후)**: `eval/broadcast_sim/run_broadcast_sim.py`
을 base vs adapter 태그로 각각 실행해 비교. 기준선(클로드 CPU,
seeded+briefing+acts): **fact_usage 7%(2/29)·앵커 35%·다양성 71%·
단답 2/48·존댓말 0**. 통과 판단 전 §3의 분산 데이터를 반드시 참조
(1-run 차이는 노이즈일 수 있다). 존댓말·addressee 회귀 가드 필수.

## 2. GPU 재실측 대기열 (기존 + 신규)

- **marker 모드 체감 지연** — ACK 발화 제거로 첫 음성이 실제 TTFT로
  후퇴. GPU TTFT 실측으로 허용 범위 확인 (`AIRI_IMMEDIATE_ACK`
  audible/marker A/B)
- 게이트 경로 폴백률 reps 확대, 치환표 중기 조치 ①② 판단 (기존)
- TTS 재검증 (v2ProPlus 스트리밍 계약) (기존)
- 시뮬 하네스 GPU 실행 — CPU 대비 지연 대표성 확보 + P3-M 판단 재료

## 3. 실측 시 알아야 할 함정 (클로드 실측에서 나온 것)

- **런 간 분산이 크다**: 같은 구성 반복에서 p50 3자~11자까지 흔들린
  실측 있음(control 붕괴). 시드 3종(11/22/33) 분산 데이터가
  `broadcast-sim-variance-*-2026-08-19.json`으로 커밋돼 있다 —
  단일 런으로 통과/실패를 단정하지 말 것.
- **absence 폴백 선점**: `memory_absence_fallback_required`(:6916)는
  모델 호출 전에 응답하고 히스토리만 검사한다 — 브리핑(시스템
  프롬프트)을 못 본다. **B4a 운영 브리핑 이식 시 디렉터→프록시
  "브리핑 근거 있음" 신호 계약이 필요**하다.
- 시뮬 CPU 실행 조건: `--num-ctx 4096` 필수(주제 블록+카드 병합
  ≈2,250토큰), `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS=30`.
  GPU에서는 기본값으로 재확인할 것.

## 4. 변경 금지·주의 경계 (기존 유지)

- `airi_docs/patches/` 무접촉 (CI 경로 핀)
- 픽스처 2종(rehearsal semantic) 무수정, OFF 경로 바이트 동일 원칙
- 운영 ON 추가 변경·외부 API·라이브 캠페인 = 사용자 승인 경유
- B1b(YouTube 자격증명)·인간 검수 100건 = 외부/사용자 대기

## 5. 참고 문서 (전부 완료/에 있음, 2026-08-18~19)

P3 판정: `AIRI-P1-LEVER-EXHAUSTION-P3-GATE-2026-08-19.md` /
T1 데이터: `AIRI-P3T1-BEHAVIOR-SFT-SYNTHESIS-2026-08-19.md` /
P1·P2 실측 2종: `AIRI-P1P2-*-2026-08-19.md` / 시뮬 기준: `AIRI-BROADCAST-SIM-3ARM-2026-08-18.md` /
기억 리서치: `참조/AIRI-MEMORY-TECH-RESEARCH-2026-08-18.md`
