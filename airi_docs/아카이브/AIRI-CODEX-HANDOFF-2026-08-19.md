# 코덱스(GPU dev PC) 통합 인계 — 2026-08-19 최종판 (클로드 PC 발신)

> 2026-08-18~19 클로드 PC 배치 전체(`cd9ca5a`~`2b84fb8`, 20+커밋)를
> 소화한 뒤의 **코덱스 대기열 단일 SSoT**다. 진입 순서: 이 문서 →
> `로드맵/AIRI-ROADMAP-STATUS.md`(v3 — 최상위) →
> `로드맵/AIRI-ROADMAP-LOG.md` 최근 항목. 클로드 PC는 무GPU라 아래
> 작업은 전부 코덱스 몫이며, **데이터·트레이너·게이트 기준선까지 전부
> 준비돼 있어 코덱스는 실행과 GPU 실측만 하면 된다.**

## 0. 먼저 알아야 할 구조 변화 (2026-08-19)

1. **로드맵 v3** — 주 지표가 위반률(빼기)에서 **발화 실질(더하기)**로
   교체. 배치별 갱신 로그 기록 의무는 `AIRI-ROADMAP-LOG.md`로 이동
   (STATUS 본문은 상태 변화 시에만 수정).
2. **P3 = 학습 트랙이 주 경로** (사용자 확정 — "모델을 학습시키는
   방향"). 체급 A/B는 보조(P3-M)로 강등.
3. **운영 기본값 변경** (`start-local-ollama-proxy.ps1`, 전부 사용자
   승인): `AIRI_IMMEDIATE_ACK=marker`(선반응 "응!" 발화 제거 — 표정
   마커만), 침묵 폴백 풀 ON, 방송 계약 v3 ON, 기억 가드
   (`AIRI_MEMORY_CLAIM_GUARD`) ON.
4. **레거시 정리** — 08-13 이전 인계문은 전부 `아카이브/`(현재 상태
   검증 사용 금지). 이 문서가 유일한 현행 인계문이다.

## 1. 최우선 — P3-T2-b: 행동 SFT QLoRA 학습

### 준비된 파이프라인 (클로드 PC 완결분)

```
[✅] 합성 181건  training/seed/airi_behavior_seed_pending.jsonl
[⏳ 사용자] 검수 폼 회신  airi_docs/진행예정/AIRI-BEHAVIOR-REVIEW-FORM-2026-08-19.html
[✅] 적용기  apply_behavior_review_reply.py  (미결정 있으면 fail-closed,
     수정 답변 반말 게이트, eligibility 유일 전환점 — 검수자 id 필수)
[✅] 익스포터  export_behavior_chat_dataset.py  (운영 시스템 프롬프트+브리핑+
     [YouTube] 프리픽스 그대로 chat messages 조립, sha256 출력)
[✅] 트레이너  train_airi_behavior_lora.py  (CPU 스모크로 루프 전체 검증 완료)
[⏳ 코덱스] CUDA 실행 ← ★여기
```

### 실행 절차 (검수 회신이 레포에 반영된 후)

```powershell
cd ollama-proxy/training
# 1) 검수 반영·익스포트가 아직 안 돼 있으면 (클로드가 이미 했으면 스킵):
python apply_behavior_review_reply.py --reply <회신.txt> --reviewer <사용자id> --approved-at 2026-08-XX
python export_behavior_chat_dataset.py     # 출력의 sha256을 다음 단계에 사용

# 2) Mi:dm HF 스냅샷을 로컬 디렉터리로 (허브 이름 직접 지정은 거부됨):
#    K-intelligence/Midm-2.0-Mini-Instruct → 예: D:\models\midm-2.0-mini

# 3) 학습:
python train_airi_behavior_lora.py --mode cuda-qlora `
  --dataset seed/airi_behavior_chat_sft.jsonl --dataset-sha256 <익스포터 출력값> `
  --model-dir <로컬 스냅샷 경로> --output adapters/behavior-v1
```

트레이너 계약: dataset sha 핀 필수(검수 우회 불가) · 로컬 스냅샷 전용
(허브 이름·네트워크 경로·URL 스킴 거부) · assistant 구간만 라벨(운영
프롬프트는 입력, 검수된 답만 정답) · 어댑터만 저장. 학습 루프는 tiny
모델 CPU 스모크로 loss 하강·어댑터 저장까지 검증됐다
(`tests/test_train_airi_behavior_lora.py`) — **코덱스가 검증할 것은
CUDA 경로(bitsandbytes 4bit 로드·VRAM)뿐**이다. 하이퍼파라미터 기본값은
트레이너 `DEFAULTS` 테이블(r16/α32/lr2e-4/300스텝) — 조정은 자유,
기록만 남길 것.

학습 후: 어댑터를 Ollama 태그로 빌드(base Mi:dm + adapter)해 T3에 투입.

### T3 게이트 — 반드시 두 방송 모두, 캘리브레이션 준수

```powershell
cd ollama-proxy/eval/broadcast_sim
# base vs adapter 태그 각각, 두 픽스처 각각 (총 4런 이상 권장, 시드 3종이면 12런):
python run_broadcast_sim.py --memory-arm seeded --briefing on --acts on --model <태그> --report <...>
python run_broadcast_sim.py --fixture second_broadcast_v1.json  (동일 옵션)
```

**판정 기준 (4-시드 분산 캘리브레이션 — 단일 런 판정 금지)**:

| 지표 | 1차 방송 기준선(4-run) | 2차(held-out) 기준선 | 통과 조건 |
|---|---:|---:|---|
| 사실 활용 | 7~12% | 15% | **노이즈 천장(12%/15%)을 유의하게 상회** |
| 결정론 축 | 만점 5연속 | 만점 | **만점 유지 (하락 = 즉시 불합격)** |
| 존댓말 위반 | 0 | 0 | 0 유지 |
| 앵커·다양성 | 21~48% / 62~83% | 44% / 77% | **3시드 평균**으로 비교 |
| 기억 프로브 | 0~1/3 | 2/3 | 하락 없음 |

**2차 방송은 과적합 검출기다** — 주제·시청자·프로브 사실이 학습
데이터와 분리돼 있어(회귀 테스트 강제), 1차만 오르고 2차가 안 오르면
암기다. 미통과 어댑터는 폐기하고 하이퍼파라미터/데이터 증량으로 재시도.

### 2차 학습 후보 (행동 SFT 이후)

`training/seed/airi_extraction_seed_pending.jsonl` — 추출 판단 학습쌍
102건(주체 선택 함정·{{user}} 등록·과추출 억제 장면, 전 타깃이 스팬
파서 무손실 통과·게이트 어휘와 분리). 검수·익스포트 경로는 행동 SFT
패턴을 따라 확장 예정(클로드 몫).

## 2. GPU 재실측 대기열 (학습과 병행 가능 — 검수 대기 중에도 진행)

1. **Qwen3-8B + `--stage-a-contract conversation-v3-span` 추출 게이트
   1회** — 스팬 계약 실측(클로드 CPU)에서 검증은 날조를 차단했지만
   판단 축이 미돌파. 8B는 구조 실패 0이었으므로 스팬 검증과 최상 궁합
   후보. `benchmark_memory_track.py --mode extraction --gate-profile
   balanced` (격리 Ollama에서, 기존 절차 그대로)
2. **marker 모드 체감 지연** — ACK 발화 제거로 첫 음성이 실제 TTFT로
   후퇴. `AIRI_IMMEDIATE_ACK` audible/marker A/B로 GPU TTFT 실측
3. **시뮬 하네스 GPU 실행** — CPU 대비 지연 대표성 + `--num-ctx`
   기본값 재확인(CPU에서는 주제 블록+카드 병합 ≈2,250토큰이라 4096
   필요했음. `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS=30`도 CPU 전용
   완화였다 — GPU 기본값으로 재검증할 것)
4. 게이트 경로 폴백률 reps 확대·치환표 중기 조치 ①② 판단 (기존)
5. TTS 재검증 — v2ProPlus 스트리밍 계약 (기존)

## 3. 실측 함정 (클로드 실측에서 나온 것 — 필독)

- **런 간 분산이 크다**: 같은 구성에서 p50 3~23자까지 흔들림 실측.
  시드 3종(11/22/33) 분산 데이터
  `broadcast-sim-variance-seed*-local-2026-08-19.json` 참조. 단일 런
  판정 금지.
- **absence 폴백 선점**: `memory_absence_fallback_required`
  (ollama_proxy.py:6916 부근)는 모델 호출 전에 응답하고 히스토리만
  검사한다 — 시스템 프롬프트의 브리핑을 못 본다. **B4a 운영 브리핑
  이식 시 디렉터→프록시 "브리핑 근거 있음" 신호 계약 필요.**
- **기존 style QLoRA 트레이너(`train_airi_style_qlora.py`)는 EXAONE
  config 하드 핀** — 행동 학습에 쓰지 말 것(새 트레이너 사용).
- 시뮬 픽스처를 수정하면 stream sha가 바뀌어 기존 리포트 `--rescore`가
  깨진다 — 비교 대상 런들과 같은 커밋의 픽스처로 돌릴 것.

## 4. 변경 금지·주의 경계 (기존 유지)

- `airi_docs/patches/` 무접촉 (CI 경로 핀)
- 픽스처 2종(rehearsal semantic) 무수정, OFF 경로 바이트 동일 원칙
- 운영 ON 추가 변경·외부 API·라이브 캠페인 = 사용자 승인 경유
- B1b(YouTube 자격증명)·인간 검수 100건 = 외부/사용자 대기
- 어댑터 운영 채택은 T3 통과 + 사용자 승인 후에만

## 5. 참고 문서 (2026-08-18~19, 전부 완료/)

학습 트랙: `AIRI-P3T1-BEHAVIOR-SFT-SYNTHESIS`·`AIRI-HELDOUT-AND-EXTRACTION-SFT` /
게이트 판정: `AIRI-P1-LEVER-EXHAUSTION-P3-GATE` /
스팬·분산: `AIRI-SPAN-CONTRACT-AND-VARIANCE` /
P1·P2 실측: `AIRI-P1P2-BRIEFING-DETERMINISTIC-ACTS`·`AIRI-P1P2-V2-RELEVANCE-GUARD` /
시뮬 기준: `AIRI-BROADCAST-SIM-3ARM-2026-08-18` /
기억 리서치: `참조/AIRI-MEMORY-TECH-RESEARCH-2026-08-18.md`
