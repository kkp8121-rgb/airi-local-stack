# 코덱스(GPU dev PC) 통합 인계 — 2026-08-20 최종판 (클로드 PC 발신)

> 2026-08-20 클로드 PC 배치 전체(`c4c3e35`~`4046d75`, 17커밋)를 소화한 뒤의
> **코덱스 대기열 단일 SSoT**다. 진입 순서: 이 문서 →
> `로드맵/AIRI-ROADMAP-STATUS.md`(v3 — 최상위) →
> `로드맵/AIRI-ROADMAP-LOG.md` 최근 항목. 클로드 PC는 무GPU라 아래 작업은
> 전부 코덱스 몫이며, **데이터·트레이너·게이트 기준선까지 전부 준비돼 있어
> 코덱스는 실행과 GPU 실측만 하면 된다.**
>
> **이 문서가 `AIRI-CODEX-HANDOFF-2026-08-19.md`를 대체한다.** 08-19판은
> 소화 완료로 판정해 `아카이브/`로 이동 예정이며, 현재 상태 검증에 쓰지 말 것.
> 08-19판의 유효 내용(§1 학습 절차·T3 판정 기준·함정·경계)은 이 문서에
> 전부 승계·갱신해 실었다 — 이 문서만 읽으면 된다.
>
> 병행 지시서: `진행중/AIRI-CODEX-SERENA-TOKEN-ORDER-2026-08-20.md`
> (코덱스 PC에 Serena MCP를 붙여 Codex 토큰을 줄이는 작업 명령 — 이 문서와
> 독립이며, 그쪽 §7 결과표를 채우고 LOG에 1줄 기록하면 종결).

## 0. 먼저 알아야 할 구조 변화

### 0-1. 08-19 기준 (여전히 유효)

1. **로드맵 v3** — 주 지표가 위반률(빼기)에서 **발화 실질(더하기)**로 교체.
   배치별 갱신 로그 기록 의무는 `AIRI-ROADMAP-LOG.md`(STATUS 본문은 상태
   변화 시에만 수정).
2. **P3 = 학습 트랙이 주 경로** (사용자 확정 — "모델을 학습시키는 방향").
   체급 A/B는 보조(P3-M)로 강등.
3. **운영 기본값** (`start-local-ollama-proxy.ps1`, 전부 사용자 승인):
   `AIRI_IMMEDIATE_ACK=marker`(선반응 "응!" 발화 제거 — 표정 마커만),
   침묵 폴백 풀 ON, 방송 계약 v3 ON, 기억 가드(`AIRI_MEMORY_CLAIM_GUARD`) ON.

### 0-2. 2026-08-20 신규 (이번 배치)

1. **브리핑 근거 신호 계약이 실물로 존재한다.** 디렉터→프록시 헤더
   `X-AIRI-Briefing-Evidence: memory`(확장 가능 토큰·정확 일치·**루프백 피어
   전용**). 헤더가 있으면 absence 폴백의 선점을 우회한다. 헤더 부재 시 기존
   경로는 바이트 동일이며, `/health`에 `briefing_evidence` 누계
   (`signalled_requests`/`absence_bypasses`)가 노출된다.
   (`완료/AIRI-BRIEFING-EVIDENCE-SIGNAL-2026-08-20.md`, `f6a4167`+`df5b264`)
2. **근거 판정은 "좁힌 정의"가 현행이다** — `bool(viewer_lines)`가 아니라
   **관련도 매칭된 줄이 최소 하나 존재**. 부착률 68.1%→23.6%, 해제 4→2.
   행 단위 해제 관측성 `briefing_evidence_released`가 신설됐다.
   (`완료/AIRI-BRIEFING-EVIDENCE-NARROW-2026-08-20.md`, `a5abc2c`+`6889d1e`)
3. **추출 검수 폼이 v2로 갱신됐다 — 구 폼 회신은 거부된다.** 회신 헤더에
   큐 sha256(12자)이 결속되고 적용기가 필수 대조한다. 큐가 바뀐 상태에서 옛
   회신을 넣으면 `ReviewReplyError`로 전체 거부되며, 오류 메시지가 최신 폼
   파일명을 안내한다. **현행 폼 = `진행예정/AIRI-EXTRACTION-REVIEW-FORM-2026-08-20.html`
   (102건, 큐 sha `2988a82bd738`)**. 폼에 rewrite 브라우저 사전 검증
   (evidence ⊂ turns · 이름 ⊂ evidence)이 붙어 왕복 비용이 줄었다. (`eb9f46a`)
4. **런타임 Stage A가 v3-span opt-in을 갖는다(greybox, 기본 OFF).**
   `AIRI_MEMORY_EXTRACTION_STAGE_A_CONTRACT=conversation-v3-span`을 켤 때만
   벤치마크·학습 조립과 바이트 동일하게 수렴한다. 기본 `conversation-v2b`는
   프롬프트·user 메시지·JSON schema 세 요소 SHA-256이 변경 전과 동일함을
   HEAD 판 실제 구동으로 대조 확인했다. **켜기 전 §3 선행 조건 필수.** (`00482ec`)
5. **결정론 alias + 고정 택소노미 게이트가 있다(greybox, 둘 다 기본 OFF).**
   `AIRI_MEMORY_EXTRACTION_ALIAS_RESOLUTION` /
   `AIRI_MEMORY_EXTRACTION_TAXONOMY_GATE`. OFF 경로는 요청 본문·텔레메트리·
   DB 전 행 해시가 HEAD와 동일(`a2d345b6…`). **켜기 전 §3 선행 조건 필수.**
   (`9034428`)
6. **결정론 발화의 히스토리 격리가 시뮬 러너에 들어갔다.** 후원 thank 렌더러
   호명이 히스토리·브리핑 "방금 흐름"으로 되먹여져 이후 모델 턴이 재호명하던
   결함을 되먹임 사본만 이름 없는 A4.2 v1 문구로 치환해 고쳤다
   (`invented_handle_turns` 2→0, 결정론 축 무훼손). **운영 디렉터(B4a/B4b)
   이식 시 같은 격리가 필요하다.** (`4046d75`)
7. **사전 존재 결함 3건이 수리됐다** — soak-transport 계약 테스트(침묵 폴백 풀
   재동기화, `4f1af2b`) / `chat_replay` 패키지 이름 충돌로 인한 수집 오류 6건
   + Windows CRLF 픽스처 해시 훼손(`de4018c`) / `rescore_report()`가 자유변수
   `args` 참조로 **호출할 때마다 NameError로 죽던 것**(= CLI `--rescore`가 지금까지
   한 번도 성공한 적 없었음, `a5abc2c`). main 스위트가 이제 깨끗하다.

## 1. 최우선 — 순서 불변 (08-19 §1 절차 그대로 유효)

```
검수 회신 (사용자)          → T2-b QLoRA (코덱스)        → T3 양방송 게이트
 · 기존 행동 181건            · 1차 = 행동 181+affect 120  · 1차 + 2차(held-out)
 · affect 행동 120건           · 표현 팔레트 함께 학습      · affect probe+인간 선호
 · 추출 102건                 · 2차 = 추출                 · 미통과 어댑터 폐기
```

**08-19 인계문 §1의 절차·명령·계약은 한 글자도 바뀌지 않았다.** 아래는 그
승계본이다.

### 1-1. 준비된 파이프라인 (클로드 PC 완결분)

```
[⛔ 반려·보존] 합성 181건   training/seed/airi_behavior_seed_pending.jsonl
     ★ 2026-08-21 사용자 총평: 너무 짧고 후원/선택 채팅을 방송 주제로 확장하지 못한다.
       큐와 폼은 실패 재현용이며 회신 적용·학습 금지.
[⛔ 반려·보존] affect 행동 합성 120건
     training/seed/airi_behavior_affect_seed_pending.jsonl
     ★ 상태 표현만 늘었고 동일한 챗봇형 단답 구조다. 검수 회신·학습 금지.
[✅] 한국 방송 반응 event/beat 재설계
     airi_docs/참조/AIRI-KR-BROADCAST-REGISTER-REFERENCE-2026-08-21.md
     ★ 공식 관찰 7건(탬 5·아리사 2) 비식별 JSONL + 별도 출처 원장
[✅] AIRI 원본 방송 반응 파일럿 24건
     ollama-proxy/training/seed/airi_broadcast_response_pilot_pending.jsonl
     ★ 16/4/4, single/burst 15/9, 중앙값 98자, 입력보다 짧은 답 0, 전건 학습 금지
[⏳ 사용자] 24건 묶음 총평 — 행별 approve/rewrite/reject 작업 없음
     airi_docs/진행예정/AIRI-KR-BROADCAST-RESPONSE-PILOT-2026-08-21.md
[✅] 적용기   apply_behavior_review_reply.py  (미결정 있으면 fail-closed,
     큐 SHA·수정 답변 반말/affect 안전 게이트, eligibility 유일 전환점 — 검수자 id 필수)
[✅] 익스포터 export_behavior_chat_dataset.py (운영 시스템 프롬프트+브리핑+
     [YouTube] 프리픽스 그대로 조립; affect는 request-local 상태/표현 prompt 포함,
     검수된 두 행동 큐를 복수 --reviewed로 결합, sha256 출력)
[✅] 트레이너 train_airi_behavior_lora.py     (CPU 스모크로 루프 전체 검증 완료)
[⛔] CUDA 행동 실행 — 24건 총평 반영·별도 전량 검수 계약 전 금지

[✅] 추출 학습쌍 102건  training/seed/airi_extraction_seed_pending.jsonl
[⏸ 보류] 추출 검수 폼 회신  airi_docs/진행예정/AIRI-EXTRACTION-REVIEW-FORM-2026-08-20.html
     ★ 2026-08-20 v2 — 큐 sha 결속. 구 폼 회신은 거부된다.
[✅] 적용기   apply_extraction_review_reply.py (스팬 스키마 게이트 — 손으로 고친
     target은 parse_stage_a_span 재통과 필수[evidence가 turns 원문에 실재 +
     모든 이름이 그 인용 안 + drop 0], 한 건이라도 실패 시 회신 전체 거부)
[✅] 익스포터 export_extraction_sft_dataset.py (벤치마크 Stage A 조립을 import해
     재사용 — 학습 프롬프트 복붙 금지가 테스트로 강제됨, sha256 출력)
[⏸ 코덱스] 2차 학습 (새 행동 SFT 승인·통과 이후)
```

### 1-2. 실행 절차 (검수 회신이 레포에 반영된 후)

> **2026-08-21 중지선:** 아래 명령은 재현을 위해 보존하지만 현행 181/120 행동
> 큐에는 실행하지 않는다. `AIRI-KR-BROADCAST-REGISTER-REFERENCE-2026-08-21.md`의
> 24건 event/beat 파일럿에 사용자 총평을 반영하고 별도 전량 검수 계약을 닫은 뒤 새
> 큐·새 SHA로 절차를 다시 열어야 한다. 사용자에게 행별 승인 작업을 요구하지 않는다.

```powershell
cd ollama-proxy/training
# 1) 검수 반영·익스포트가 아직 안 돼 있으면 (클로드가 이미 했으면 스킵):
python apply_behavior_review_reply.py --reply <회신.txt> --reviewer <사용자id> --approved-at 2026-08-XX
python apply_behavior_review_reply.py `
  --pending seed/airi_behavior_affect_seed_pending.jsonl `
  --reply <affect-회신.txt> --reviewer <사용자id> --approved-at 2026-08-XX `
  --output seed/airi_behavior_affect_reviewed.jsonl
python export_behavior_chat_dataset.py `
  --reviewed seed/airi_behavior_reviewed.jsonl `
  --reviewed seed/airi_behavior_affect_reviewed.jsonl
# 출력의 sha256을 다음 단계에 사용

# 2) Mi:dm HF 스냅샷을 로컬 디렉터리로 (허브 이름 직접 지정은 거부됨):
#    K-intelligence/Midm-2.0-Mini-Instruct → 예: D:\models\midm-2.0-mini

# 3) 학습:
python train_airi_behavior_lora.py --mode cuda-qlora `
  --dataset seed/airi_behavior_chat_sft.jsonl --dataset-sha256 <익스포터 출력값> `
  --model-dir <로컬 스냅샷 경로> --output adapters/behavior-v1
```

추출(2차) 학습은 같은 패턴이며 적용기·익스포터만 추출 쪽 스크립트로 바꾼다:

```powershell
python apply_extraction_review_reply.py --reply <회신.txt> --reviewer <사용자id> --approved-at 2026-08-XX
python export_extraction_sft_dataset.py    # 기본 출력 seed/airi_extraction_sft.jsonl, sha256 출력
```

트레이너 계약: dataset sha 핀 필수(검수 우회 불가) · 로컬 스냅샷 전용(허브
이름·네트워크 경로·URL 스킴 거부) · assistant 구간만 라벨(운영 프롬프트는
입력, 검수된 답만 정답) · 어댑터만 저장. 학습 루프는 tiny 모델 CPU 스모크로
loss 하강·어댑터 저장까지 검증됐다(`tests/test_train_airi_behavior_lora.py`) —
**코덱스가 검증할 것은 CUDA 경로(bitsandbytes 4bit 로드·VRAM)뿐**이다.
하이퍼파라미터 기본값은 트레이너 `DEFAULTS` 테이블(r16/α32/lr2e-4/300스텝) —
조정은 자유, 기록만 남길 것.

학습 후: 어댑터를 Ollama 태그로 빌드(base Mi:dm + adapter)해 T3에 투입.

### 1-3. T3 게이트 — 반드시 두 방송 모두, 캘리브레이션 준수

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

**2차 방송은 과적합 검출기다** — 주제·시청자·프로브 사실이 학습 데이터와
분리돼 있어(회귀 테스트 강제), 1차만 오르고 2차가 안 오르면 암기다. 미통과
어댑터는 폐기하고 하이퍼파라미터/데이터 증량으로 재시도.

**2026-08-20 보강 근거**: 결정론 축이 만점을 유지한다는 것은 이번 배치에서
다시 확인됐다 — 브리핑 근거 계약 6런·좁힌 정의 3런·토큰 예산 9런·격리 전후
2런 전부에서 수신자·호명·여론·존댓말·이탈이 만점/0이었다. 즉 **결정론 축의
하락은 어댑터 결함 신호로 읽어도 안전하다**(배경 노이즈가 아니다).

## 2. GPU 재실측 대기열 (학습과 병행 가능 — 검수 대기 중에도 진행)

1. **Qwen3-8B + `conversation-v3-span` 추출 게이트 1회** — 스팬 계약 실측
   (클로드 CPU)에서 검증은 날조를 차단했지만 판단 축이 미돌파. 8B는 구조 실패
   0이었으므로 스팬 검증과 최상 궁합 후보.
   `benchmark_memory_track.py --mode extraction --gate-profile balanced`
   (격리 Ollama에서, 기존 절차 그대로)
2. **marker 모드 체감 지연** — ACK 발화 제거로 첫 음성이 실제 TTFT로 후퇴.
   `AIRI_IMMEDIATE_ACK` audible/marker A/B로 GPU TTFT 실측
3. **시뮬 하네스 GPU 실행** — CPU 대비 지연 대표성 + `--num-ctx` 기본값 재확인
   (CPU에서는 주제 블록+카드 병합 ≈2,250토큰이라 4096 필요했음.
   `AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS=30`도 CPU 전용 완화였다 —
   GPU 기본값으로 재검증할 것. **범위 주의는 §4-1**)
4. 게이트 경로 폴백률 reps 확대·치환표 중기 조치 ①② 판단 (기존)
5. TTS 재검증 — v2ProPlus 스트리밍 계약 (기존)
6. **★ ctx 예산 GPU 단일조건 재실측 (2026-08-20 신설)** —
   `--history-turns {4,8,12}` × 시드 {11,22,33} 9런을 **스로틀·워치독 변경
   없이 단일 조건**으로 다시 돌린다. 이유: 클로드 CPU 배치에서 history_turns
   축과 CPU 스로틀 epoch가 **완전히 교락**돼(h4=전부 스로틀 전, h12=전부
   스로틀 후) 앵커·다양성·fact_usage·프로브의 우열을 확정할 수 없었다.
   epoch를 고정하면 효과가 사라지거나 역전된다. **확정된 것은 둘뿐** —
   결정론 축은 4/8/12 전부 무영향(9런 만점), `--num-ctx 4096`은
   history_turns=12까지 거절 0건으로 수용.
   (`완료/AIRI-CTX-BUDGET-TRADEOFF-2026-08-20.md`)
7. **★ narrow evidence GPU 확인 (2026-08-20 신설)** — 좁힌 근거 정의의
   부착 23.6%(34/144)·해제 2건과 행 단위 해제 관측성이 GPU에서도 같은지
   확인하고, CPU 노이즈에 묻혀 판정 불가였던 축(프로브 3/9·사실활용 8/90·
   앵커 49/144)을 다중 시드로 다시 잰다. 부착률·해제 건수 자체는 시드·픽업·
   `select_viewer_lines_tagged`만의 함수라 **결정론적**이므로 GPU에서도
   같아야 정상 — 다르면 배선 사고를 의심할 것.
   (`완료/AIRI-BRIEFING-EVIDENCE-NARROW-2026-08-20.md`)

### 2026-08-20 코덱스 GPU 실행 결과

- **ctx 예산 단일조건 9런 완료** — RTX 3060 Ti, Mi:dm 고정 digest,
  `num_ctx=4096`, `num_gpu=999`, 워치독 30초, 시드 11/22/33에서 전 런
  전송 실패 0. h4/h8/h12의 앵커는 41/48/46 of 144, 사실 활용은
  5/7/5 of 90, 기억 프로브는 4/4/3 of 9, 오프너 다양성 평균은
  78.5/81.3/84.0%였다. 결정론 축은 전 런 만점·존댓말/이탈 0. 따라서
  CPU의 "h4 최고" 판정은 재현되지 않았고, h8은 사실·프로브 균형,
  h12는 다양성·단답 억제가 좋았으나 시드 분산이 커 단일 승격은 하지 않는다.
- **narrow evidence GPU 3런 완료** — 부착 **34/144**, 해제 **2/34**로
  CPU 결정론 배선과 정확히 일치했다. 앵커 49/144, 사실 활용 4/90,
  프로브 2/9로 판단 축은 CPU(49/144·8/90·3/9)보다 낮아 품질 개선
  주장은 하지 않는다. 전송 실패·존댓말·이탈·이름 발명은 0.
- **Qwen3-8B + v3-span 1회 완료·FAIL** — 고정 digest
  `500a1f...b8b41`, 격리 11436, `num_ctx=8192`, `num_gpu=999`.
  schema/A schema/B schema는 1.0이나 connectivity/B coverage 0.857,
  critical recall 0.262, placeholder 0.857, B op-alias 0.143,
  `entity_reference_missing` 1건으로 balanced gate FAIL. 이 v3-span
  리포트는 런타임 승인에 사용할 수 없고 §3 선행조건도 그대로 열린다.
- **marker 체감 A/B·TTS live gate 보류(환경 차단)** — TTS 런처가 외부
  GPT-SoVITS venv의 선언 의존성 누락으로 9880을 열지 못했다. 누락된
  `numpy<2.0`을 venv에 보충한 뒤에도 다음 필수 모듈 `soundfile`에서
  중단됐고 `pip check`가 다수 누락을 확인했다. 전체 외부 venv 재구축 없이
  canonical 7문장 gate나 실제 render A/B를 주장하지 않는다. AIRI source와
  server-channel config는 있으나 측정 시 6121/Electron도 비가동이었다.
  레포 내부 proxy streaming/lock/cancel 계약은 Python 3.12 임시 환경에서
  **23 passed**. 모든 greybox/extraction 운영 플래그는 OFF를 유지했다.

### 2026-08-21 사용자 피드백 후 affect 표현 실험

- 사용자 평가는 현행 행동 데이터가 "거짓말은 없지만 정직한 로봇처럼 들리고
  인간의 위트·감정이 없다"는 것이며, 목표 예시는 상태에 따라 기분 좋음과
  장난스런 독설이 오가는 반응이다. 이에 ①학습된 표현 팔레트와 ②런타임
  상태 선택을 분리했고, 사용자 지시에 따라 **②를 먼저 격리 실행**했다.
- 기존 `affect_state.py`와 proxy opt-in 주입은 이미 있었지만 production event
  producer와 state→expression selector가 없었다. 새 `affect_expression.py`는
  validated state만 받아 13개 primary를 closed mood/expression/response/safety
  계약으로 바꾸며, safety/deescalate는 careful로 강제한다. evaluator-only
  `run_affect_expression_probe.py`는 frozen fixture를 수정하지 않고 동일 요청에
  `off / typed snapshot / snapshot+expression`만 중첩 추가함을 canonical bytes로
  검증한다. 운영 runtime에는 evaluator import가 들어가지 않도록 fence를 확장했다.
- RTX 3060 Ti·고정 Mi:dm digest·`num_ctx=2048`·temperature 0.6·시드
  42/43/44에서 5상태 15 triplet, **45호출**을 위치 균형 실행했다. 지시를 더
  구체화한 v2도 별도 45호출 재실행했다. 두 런 모두 문자열 변화는
  snapshot/off 12/15, expression/off 12/15, expression/snapshot 12/15였으나
  이는 품질 지표가 아니다. v2 수동 판독에서 `playful_annoyed` 3건은 위트가
  없고, pleased 3건은 전 arm 동일 거부, competitive 3건은 방송 시작/종료 등
  문맥 오류, safety 3건 중 2건은 off보다 약한 안내였다. **운영 승격·게이트
  통과 주장은 0이며 결론은 "런타임 선택만으로 부족"이다.**
- 다음 순서는 사용자 검수/행동 QLoRA 데이터에 감정·위트 표현 팔레트를
  보강한 뒤 동일 probe와 블라인드 선호 평가를 재실행하는 것이다. 이를 위해
  별도 affect 행동 pending 120건과 검수 폼을 준비했다(13상태 각 8,
  playful_annoyed/concerned 각 16, split 90/15/15). 기존 181건은 무수정 보존하고
  두 reviewed 큐만 exporter에서 합친다. affect 폼 queue SHA는 `96d0d2d3c69d`,
  기존 행동 폼은 새 SHA 결속판 `eab7f6b76c06`이다. 120건은 첫 트랜치이며
  성격 품질 충분성은 학습 후에만 판정한다. production event ingress, affect
  운영 ON, wire 표정 방출은 재평가 통과+사용자 승인 전까지 금지. memory
  greybox도 OFF 유지.

> **후속 사용자 총평으로 위 “120건 검수→QLoRA” 순서는 폐기됐다.** 두 행동 큐는
> 답변 길이 중앙값이 13자/14자이고, 후원 의례·메시지별 반응·주제 확장·복귀 beat가
> 없는 챗봇형 단답이라는 판정을 받았다. 현행 진입점은
> `참조/AIRI-KR-BROADCAST-REGISTER-REFERENCE-2026-08-21.md`의 공식 방송 관찰과
> AIRI 고유 24건 파일럿 총평 반영이다. 실제 방송인의 고유 문체·캐치프레이즈·시청자
> 식별정보는 학습 데이터로 복사하지 않는다.

## 3. 활성화 선행 조건 — 켜기 전에 반드시 닫을 것

> 이번 배치의 greybox 3종은 **전부 기본 OFF**이며 OFF 경로 바이트 동일이
> 실측됐다. 아래는 **ON으로 돌리기 전에 해결해야 하는 항목**이며, 전부
> 실측 근거가 있는 것만 적었다(추정 항목 없음).

### 3-1. span 계약 (`AIRI_MEMORY_EXTRACTION_STAGE_A_CONTRACT=conversation-v3-span`)

1. **[차단성] `verify_extraction_gate` v2b 하드핀.**
   `ollama-proxy/verify_extraction_gate.py`의 `STAGE_A_CONTRACT =
   "conversation-v2b"`가 하드코딩이고 런처가 이를 기동 전 검증한다. 즉 span을
   켜면 **v2b로 인증된 게이트 리포트 위에서 span이 도는** 상태가 된다. 지금은
   운영 추출이 OFF(전 후보 게이트 FAIL)라 실해가 없지만, span opt-in을 실제로
   켜기 전 반드시 닫아야 한다. (근거: task-7-report §6-1)
2. **다중 라인·중복 라벨 = 분포 밖 입력 (v3-span 승격 전 필독).** span 포맷
   `[turn N] {content}`는 **role 태그를 잃는다** — 런타임 기본(v2b)의
   `[{turn_no}:{role}] {content}`와 달리, 한 턴이 user/assistant 2행이면
   `[turn 1] u` / `[turn 1] a`처럼 **같은 `[turn 1]` 라벨이 두 번** 나온다.
   학습 시드와 벤치마크 픽스처는 **전량 단일 라인**이라 모델이 이 형태를 본
   적이 없다 — 라이브 대화는 2행이 정상이므로 **켜는 순간 분포 밖 입력이
   된다**. 의도된 손실(계약 갈라짐 방지 우선)이지만, 활성화 전 이 입력에서의
   파서 손실률을 재야 하고 **v3-span을 프로덕션 계약으로 승격할 때는 role
   소실 자체를 먼저 결정해야 한다**. (근거: task-7-report §1-4)
3. **evidence 검증 스코프가 배치 전체다.** `parse_stage_a_span(raw, turns_text)`의
   `turns_text`는 배치 전체의 본문(래퍼 없는)이다. 즉 evidence가 **같은 배치의
   다른 턴** 텍스트에 있어도 substring 검증을 통과한다 — 턴 단위 귀속을
   보장하지 않는다. 활성화 전 이 완화가 허용 가능한지 판단할 것.
   (근거: task-7-report §1-4의 turns_text 단일값 설계)
4. **전량 드롭 시 워터마크가 무성 전진한다.** span 파서는 근거 미인용 항목을
   조용히 드롭하므로, 모든 항목이 드롭되면 "빈 추출"과 구분되지 않아
   `extraction_success`가 실행되고 **해당 턴은 다시 추출되지 않는다**.
   가시성은 `extract_end` 텔레메트리 `span_dropped`로 확보돼 있으나 전진
   자체는 미결이다. 해결 방향: 생존 0 + 드롭>0 배치를 워터마크 전진에서
   제외하거나, 최소한 드롭 임계 초과 시 운영 알람 부착.
   (근거: task-7-report §1-5, task-10-report §6-2-3 —
   `test_known_limitation_full_taxonomy_drop_advances_the_watermark`로
   현재 동작이 회귀 테스트에 고정돼 있다)

### 3-2. alias 해소 / 고정 택소노미

5. **[차단성] 미지 인물 접미 오병합.** ambiguity 가드는 **충돌하는 두 표기가
   양쪽 다 기지(旣知)일 때만** 발동한다. 같은 배치 안에서 첫 등장 이름이 색인에
   편입된 뒤 뒤따르는 **다른 인물**의 stem이 겹치면 그대로 흡수된다
   (`하린` 뒤의 `하린이` → `하린`). 초판 리포트의 "오병합 구조적 불가능"은
   리뷰 실측으로 **철회**됐다. 현재 동작은
   `test_known_limitation_unknown_names_collapse_inside_one_batch`로 상한이
   고정돼 있고, 위험 축은 `alias_entity_renamed`(엔티티 name 재작성) /
   안전 축은 `alias_reference_bound`(참조 결속)로 분리 계측된다.
   **활성화 전 라이브 오병합률·관계어 드롭률 측정이 선행 조건**이며, 결과에
   따라 (a) 접미 목록 축소 또는 (b) 엔티티 name 재작성을 기지 표기 한정으로
   좁히는 결정이 필요하다. (근거: task-10-report §2-2·§6-2-0·§9-1)
6. **두 플래그 동시 ON이 런타임에서 미검증.** 단위 조합은 커버되지만
   `ALIAS_RESOLUTION` + `TAXONOMY_GATE`를 함께 켠 런타임 조합 테스트가 없다.
   함께 켤 계획이면 그 조합부터 재라. (근거: task-10-report §6-2-7 ④)
   - 함께 측정할 것 2건: 고정 택소노미 밖 한국어 관계어(`동료`·`선배`·`스승`
     등, 9슬롯에 없음)의 **라이브 드롭률**(fail-soft — 항목만 손실, 배치는
     성공, `taxonomy_dropped`로 노출) / Stage B가 `add`를 고를 때
     `entity_reference_ambiguous`로 배치가 실패하는 빈도(**선재 결함**이나
     alias 해소 ON이 이 충돌에 도달할 확률을 높인다 — 대조군 실측으로 선재
     확인됨). (근거: task-10-report §6-2-1·§6-2-2)

### 3-3. 두 greybox 동시 활성화 (span ON + alias ON)

7. **span 계약 헤드라인이 완화된다 — 계약 서술 조정 필요.** span 파서는
   "이름이 evidence 안에 verbatim 존재"를 검증하는데, alias 재작성은 그
   **뒤에** 일어난다. 따라서 등록 테이블 canonical로 교체된 이름(예:
   `에어리`→`아이리`)은 evidence 원문에 없을 수 있고, **"저장된 이름은 전부
   원문 인용"이라는 span 계약의 헤드라인이 ON 조합에서 성립하지 않는다.**
   - **환각은 아니다**: 교체 대상은 항상 *이미 알려진 표기*(등록 테이블
     canonical / 저장소 활성 엔티티 / 같은 배치의 엔티티 이름)이며, 못 찾으면
     원문을 그대로 둔다 — 새 이름을 발명하지 않는다.
   - **데이터 정합 파손도 없다**: 게이트는 생존 항목의 subtype을 재작성하지
     않고 기존 행 마이그레이션도 없다.
   - **필요한 조치는 코드가 아니라 계약 서술 조정**이다. 두 플래그를 함께
     켤 때는 span 계약 문서·주석의 "저장 이름 = 원문 인용" 표현을 "원문 인용
     또는 그로부터 결정론적으로 해소된 기지 표기"로 고쳐야 한다.
     (근거: task-10-report §6-2-4)

### 3-4. 공통

8. **런처 env 미노출.** `AIRI_MEMORY_EXTRACTION_*` 계열(span 계약 플래그 포함
   3종)은 `start-local-ollama-proxy.ps1`에 노출돼 있지 않다. 운영에서 켜려면
   런처 노출이 선행돼야 하며, 노출 자체가 운영 기본값 변경이므로 **사용자
   승인 경유**다. (근거: task-10-report §6-2-6, task-7-report §6-2)

## 4. 실측 함정 (필독 — 전부 클로드 실측에서 나온 것)

### 4-1. ★ 워치독 env는 조용히 클램프된다 (2026-08-20 신규)

`AIRI_UPSTREAM_FIRST_RAW_TIMEOUT_SECONDS`의 **유효 범위는 1~30초**이고,
범위 밖 값은 **경고 없이 기본값 8초로 클램프**된다
(`ollama_proxy.py::configured_upstream_first_raw_timeout`). 문서가 안내하던
`=90`은 실제로는 **8초**로 동작했고, 이 때문에 한 배치의 첫 3런이 거의 전 턴
8초 워치독 폴백으로 오염돼 폐기·재실행됐다. 같은 클램프가 토큰 예산 배치의
5~9런에도 걸렸음이 사후 판명됐다(해당 런들의 침묵 폴백은 0~2/144라 실측
영향은 미미). **긴 워치독이 필요하면 30이 상한**이며, 그 이상은 값을 늘리는
것이 아니라 아무 효과 없이 8로 떨어뜨리는 것이다.
(`완료/AIRI-BRIEFING-EVIDENCE-NARROW-2026-08-20.md` §6,
`완료/AIRI-CTX-BUDGET-TRADEOFF-2026-08-20.md` §0-가)

### 4-2. ★ 백그라운드 런 체인이 멈춘다 (2026-08-20 신규)

장시간 시뮬 배치를 `run_in_background`로 한 런씩 이어 돌리면, 완료 알림 이후
다음 런을 잇지 못하고 **대기 상태로 정체**하는 일이 발생한다(한 배치에서 3회,
최장 ~2.5시간 손실). 근본 원인은 미확정이다. **우회책(실측 유효)**: 잔여 런을
**단일 스크립트로 묶어** 순차 실행 + 런별 결과 검증(`rows=48`) + 실패 시 1회
재시도까지 스크립트 내부에서 처리하고, 그 스크립트 **하나만** 백그라운드로
건다. 이 구조로 바꾼 뒤 정체 없이 완주했다.
(`완료/AIRI-CTX-BUDGET-TRADEOFF-2026-08-20.md` §0)

### 4-3. ★ B4a absence 폴백 신호 계약은 루프백 전용이다 (2026-08-20 신규)

`memory_absence_fallback_required`는 모델 호출 **전에** 응답하고 요청
히스토리만 검사한다 — 시스템 프롬프트의 브리핑은 못 본다. 이 사각지대를
디렉터가 헤더로 알려주는 것이 `X-AIRI-Briefing-Evidence` 계약이며,
**정확 일치 + 루프백 피어**일 때만 인정된다(동작을 바꾸는 기존 `X-AIRI-*`
마커 3종과 같은 급으로 취급 — 이 신호는 정직성 가드를 해제하기 때문).

→ **B4a 운영 디렉터가 프록시와 같은 호스트가 아니면 이 계약은 그대로 쓸 수
없다.** 원격 디렉터가 필요해지는 순간 계약을 다시 열어야 하며, 그때는 해제
관측도 `/health` 누계 대조가 아니라 프록시가 요청-응답 상관을 직접 남기는
텔레메트리로 승격을 검토한다(`/health` 대조는 **전용 프로세스·순차 실행**
전제에서만 안전하다 — 동시 트래픽이 있으면 오귀속된다).
이식 시 근거 판정은 **좁힌 정의**(관련도 매칭 줄 존재)를 쓸 것.

### 4-4. 승계 함정 (08-19판에서 그대로 유효)

- **런 간 분산이 크다**: 같은 구성에서 p50 3~23자까지 흔들림 실측. 시드 3종
  (11/22/33) 분산 데이터 `broadcast-sim-variance-seed*-local-2026-08-19.json`
  참조. **단일 런 판정 금지.**
- **기존 style QLoRA 트레이너(`train_airi_style_qlora.py`)는 EXAONE config
  하드 핀** — 행동 학습에 쓰지 말 것(새 트레이너 사용).
- **시뮬 픽스처를 수정하면 stream sha가 바뀌어** 기존 리포트 `--rescore`가
  깨진다 — 비교 대상 런들과 같은 커밋의 픽스처로 돌릴 것.
  (참고: `fixture_sha256`은 파일 raw 바이트 해시가 아니라
  `broadcast_sim.sha256_of(canonical_bytes(...))` 정규화 해시다. 두 값이 다른
  것은 정상이며 픽스처 불일치가 아니다.)
- **Windows 체크아웃 CRLF 주의**: `core.autocrlf=true` 환경에서 sha256이 고정된
  픽스처가 조용히 훼손될 수 있고 `git diff`는 정규화 때문에 무변화로 보인다.
  `chat_replay/fixtures/*.jsonl`은 `.gitattributes` `text eol=lf`로 고정했으나,
  **새 sha 고정 픽스처를 추가할 때 같은 규칙을 함께 넣을 것**.

### 4-5. 최종 whole-branch 리뷰 관찰 항목 (2026-08-20, 통합 결함 0)

> 배치 종료 리뷰에서 **통합 결함은 0건**이었다. 아래는 결함이 아니라
> **다음 작업자가 알고 있어야 하는 추적 항목**이다. 각 항목의 착수 시점을
> 함께 적었다.

1. **[다음 풀 sim 런에서 관찰] 격리 후 v1 문구 모방 여부 미측정.**
   Task 13 격리는 후원 턴의 되먹임 사본을 이름 없는 A4.2 v1 문구
   (`고마워. 함께해줘서 힘이 돼.`)로 치환한다. 후원이 연속으로 나는 런에서
   **모델이 이번엔 그 v1 문구 자체를 모방하기 시작하는지**는 아직 측정하지
   않았다(seed 11 1런 대조만 수행). 다음 풀 시뮬 배치에서 응답 다양성과 함께
   관찰할 것.
2. **[완료 2026-08-20 — 코덱스] 첫 실제 export 전 익스포터 보강.**
   `export_extraction_sft_dataset.py`가 ① `SPLITS` 밖 split 값 ② 빈/비문자열
   id ③ 레코드 id 중복을 전부 fail-closed로 거부한다. 회귀 테스트 2건을
   추가했다. 준비 감사 중 Windows CRLF 체크아웃 큐의 raw digest
   (`8375c9ec764e`)와 배포 폼의 LF digest(`2988a82bd738`)가 달라 실제 회신이
   전건 구 폼으로 거부될 결함도 발견했다. 폼 생성기와 적용기의 `queue_digest`를
   **LF 정규화 내용 SHA**로 통일하고 EOL 동일/내용 변경 상이 회귀를 추가했다.
   현재 기존 행동 폼 181 unique(`eab7f6b76c06`)·affect 행동 폼 120 unique
   (`96d0d2d3c69d`)·추출 폼 102 unique(`2988a82bd738`)가 각 큐와 일치한다.
   행동 폼/적용기도 동일 SHA 결속과 중복·거부/수정 overlap 차단을 갖췄다.
   training 전체 검증은 **136 passed, 3 skipped**(skip: symlink 1, 임시 환경의
   torch/peft/transformers 부재 CUDA 스모크 2), 두 행동 폼 JavaScript syntax와
   전체 offline checkpoint도 통과했다. 이 준비 상태는 재현용으로 보존하지만,
   **2026-08-21 사용자 총평 이후 행동 2종은 반려됐고 추출은 보류**다. 따라서
   reviewed/SFT 산출물은 계속 미생성이 정상이며 새 event/beat 파일럿 전에는 만들지 않는다.
3. **[워크플로 다음 수정 때] CI `python-core-tests` 잡에 `setup-node` 미선언.**
   폼 JS 검증 테스트는 Node로 실제 `<script>` 원문을 실행한다. 현재는 Windows
   러너 이미지에 Node가 내장돼 통과하지만, 이미지에서 Node가 빠지면 검증이
   **조용히 skip**된다(실패가 아니라 침묵). 워크플로를 다음에 손댈 때
   `setup-node` 선언을 추가할 것.
4. **[진단 개선 후보] `_REWRITE_RE`의 id 포맷 하드코딩.**
   `apply_extraction_review_reply.py`의 rewrite 정규식이 id 포맷을 하드코딩한다.
   fail-closed 자체는 성립하지만(미매치면 approved 정합 검증이 먼저 잡는다),
   **오류 메시지가 원인을 가린다** — "왜 매치가 안 됐는지"를 알려주는 진단
   1줄 추가가 후보다.
5. **[재정의 금지] 행 필드 `briefing_evidence`의 의미.**
   이 필드는 "**부착 결정**"(디렉터가 근거 있다고 판단해 헤더를 붙였는가)이지
   "전송 성공"이 아니다. 기존 결과 JSON과의 비교성을 위해 **의미를 재정의하지
   말 것**. 전송 사실을 따로 기록해야 하면 다음 측정 세대에서
   `briefing_evidence_sent` 같은 **별도 필드**를 신설한다.
   (해제 여부는 이미 별도 필드 `briefing_evidence_released`가 담당한다.)
6. **[관찰] training CI 샤드 timeout 예산.**
   `ollama-proxy-training` 샤드에 파일 3개가 늘고 Node 실행 테스트가 추가됐다
   (95 → 114 passed). 샤드 소요가 timeout 예산에 근접하는지 다음 CI 실행에서
   확인할 것.

## 5. 변경 금지·주의 경계

- `airi_docs/patches/` 무접촉 (CI 경로 핀)
- 픽스처 2종(rehearsal semantic) 무수정, **OFF 경로 바이트 동일 원칙**
  (이번 배치의 greybox 3종은 전부 이 원칙으로 실측 검증됨 — 새 opt-in을 넣을
  때도 같은 증명을 요구한다)
- 운영 ON 추가 변경·외부 API·라이브 캠페인 = 사용자 승인 경유
- B1b(YouTube 자격증명)·인간 검수 100건 = 외부/사용자 대기
- 어댑터 운영 채택은 T3 통과 + 사용자 승인 후에만
- **검수 회신 산출물(`seed/airi_*_reviewed.jsonl`·`*_sft.jsonl`)을 가짜
  reviewer로 채우지 말 것** — 사람 승인을 위조하게 된다. 실제 회신이 있어야
  나오는 산출물이며, 현재 3개 검수 경로 모두 미생성이 정상 상태다.

## 6. 참고 문서

**2026-08-20 (이번 배치)**
- `완료/AIRI-BRIEFING-EVIDENCE-SIGNAL-2026-08-20.md` — 근거 신호 계약·라이브 확정
- `완료/AIRI-BRIEFING-EVIDENCE-NARROW-2026-08-20.md` — 좁힌 정의·해제 관측성·
  워치독 클램프 사고(§6)
- `완료/AIRI-CTX-BUDGET-TRADEOFF-2026-08-20.md` — 토큰 예산 9런·epoch 교락·
  정정 추기(§0-가)
- `참조/AIRI-GLINER-KO-EVAL-2026-08-20.md` — LLM 0회 엔티티 프리필터 실측
  (person/org 조건부 채택, item 0%, GLiNER2≠GLiNER 용어 정정)
- `진행예정/AIRI-EXTRACTION-REVIEW-FORM-2026-08-20.html` — **현행 추출 검수 폼**
- `진행예정/AIRI-BEHAVIOR-REVIEW-FORM-2026-08-19.html` — **반려 큐 재현용, 회신 금지**
- `진행예정/AIRI-BEHAVIOR-AFFECT-REVIEW-FORM-2026-08-21.html` — **반려 큐 재현용, 회신 금지**
- `참조/AIRI-KR-BROADCAST-REGISTER-REFERENCE-2026-08-21.md` — **현행 행동 재설계 SSoT**
- `참조/data/airi_kr_broadcast_reference_events_2026-08-21.jsonl` — **학습 금지 추상 관찰 7건**
- `training/seed/airi_broadcast_response_pilot_pending.jsonl` — **AIRI 원본 batch 총평용 24건**
- `진행예정/AIRI-KR-BROADCAST-RESPONSE-PILOT-2026-08-21.md` — **사람이 읽는 24건 전체 총평본**
- `진행중/AIRI-CODEX-SERENA-TOKEN-ORDER-2026-08-20.md` — 병행 지시서

**2026-08-18~19 (승계)**
학습 트랙: `완료/AIRI-P3T1-BEHAVIOR-SFT-SYNTHESIS-2026-08-19.md` ·
`완료/AIRI-HELDOUT-AND-EXTRACTION-SFT-2026-08-19.md` /
게이트 판정: `완료/AIRI-P1-LEVER-EXHAUSTION-P3-GATE-2026-08-19.md` /
스팬·분산: `완료/AIRI-SPAN-CONTRACT-AND-VARIANCE-2026-08-19.md` /
P1·P2 실측: `완료/AIRI-P1P2-BRIEFING-DETERMINISTIC-ACTS-2026-08-19.md` ·
`완료/AIRI-P1P2-V2-RELEVANCE-GUARD-2026-08-19.md` /
시뮬 기준: `완료/AIRI-BROADCAST-SIM-3ARM-2026-08-18.md` /
기억 리서치: `참조/AIRI-MEMORY-TECH-RESEARCH-2026-08-18.md`
