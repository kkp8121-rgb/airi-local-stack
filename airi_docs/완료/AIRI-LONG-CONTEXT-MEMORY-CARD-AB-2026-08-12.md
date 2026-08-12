# AIRI 장문 context·memory·card A/B 실측 (2026-08-12)

## 범위와 조건

모델 전환 분석에 남아 있던 2,048 context 장문 비교를 dev PC에서 완료했다.
하네스는 공개 합성 사실만 사용하고 raw Ollama `/api/chat`을 호출한다. 운영
DB·개인 대화·Electron·TTS·외부 네트워크는 사용하지 않는다.

- 모델: `exaone-airi:2.4b` digest `ec47936e…de4`,
  `midm-airi:2.0-mini` digest `92a9ba2e…85f`
- 공통: `num_ctx=2048`, `num_gpu=999`, temperature 0, seed 42, 3회
- 문맥 순서: 실제 AIRI system/final contract + 활성 card → 초기 사용자·AIRI
  사실 → 합성 filler 0/8/20/48쌍 → 최신 부정 정정 → tail memory → 질의
- 6개 exact 필드: card, 초기 사용자, 초기 AIRI, 최신 정정, 부정, tail memory
- retry는 전송·schema 오류에만 최대 1회이며 의미 오답은 재시도하지 않는다.

동일 입력 문자 수는 압력별 1,451/2,259/3,531/6,527자다. 보고서와 하네스는
fixture·runner·system prompt·final contract hash를 함께 기록한다.

## 결과

| 모델 | 압력 | prompt token P50 | exact case | card | 초기 사용자 | 초기 AIRI | 최신 정정 | 부정 | tail memory |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| EXAONE | 0 | 756 | 0/3 | 100% | 0% | 100% | 100% | 100% | 100% |
| EXAONE | 8 | 1,188 | 0/3 | 100% | 0% | 100% | 100% | 100% | 100% |
| EXAONE | 20 | 1,896 | 3/3 | 100% | 100% | 100% | 100% | 100% | 100% |
| EXAONE | 48 | 2,024 | 0/3 | 100% | 0% | 0% | 100% | 33.3% | 100% |
| Mi:dm | 0 | 1,139 | 0/3 | 0% | 100% | 100% | 100% | 0% | 100% |
| Mi:dm | 8 | 1,547 | 0/3 | 0% | 100% | 0% | 100% | 0% | 100% |
| Mi:dm | 20 | 2,042 | 0/3 | 0% | 0% | 0% | 100% | 0% | 100% |
| Mi:dm | 48 | 2,042 | 0/3 | 0% | 0% | 0% | 100% | 0% | 100% |

두 모델 모두 first-pass schema 12/12, retry 0/12, 전송 오류 0건이었다. 전체
exact case는 EXAONE 3/12(25%), Mi:dm 0/12(0%)로 **양 모델 FAIL**이다.
출력 token P50/P95는 EXAONE 86/89, Mi:dm 67/68이었다.

같은 입력에서 Mi:dm은 무압력부터 EXAONE보다 383 token을 더 사용했고,
20쌍에서 2,042 token으로 포화됐다. 최신 정정과 tail memory는 양쪽 12/12로
살았지만, Mi:dm은 card와 부정을 무압력에서도 놓쳤다. 따라서 이 둘은 단순
물리 truncation만이 아니라 구조화된 근거 귀속·부정 이해 실패도 포함한다.

## 판정과 운영 복구

장문 비교 **실측은 완료**, 안전 gate는 **FAIL**이다. 이 한 합성 task만으로
즉시 EXAONE 롤백을 결정하지 않는다. Mi:dm은 기존 16-case 자동 gate,
설치 Electron 지연, 라이선스에서 이점이 있으나, card·부정·context 여유가
안전하다는 주장도 금지한다. 인간 검수 100건과 문맥 예산/표현 개선 후 같은
fixture를 회귀 실행해야 한다.

원시 보고서:

- `ollama-proxy/eval/results/model-llm-context-exaone-2026-08-12.json` — SHA-256
  `7998D9CE7D087B72E73B28E65E5BF496D02406A0D0D1150626BE1E755098433E`
- `ollama-proxy/eval/results/model-llm-context-midm-2026-08-12.json` — SHA-256
  `026E119483F6E77C615E044D90E50C216841810E78F681A582297A4634B1D57D`

측정 후 EXAONE만 unload했고 `ollama ps`는 Mi:dm 단일 100% GPU·context 2048,
`/health`는 Mi:dm digest pinned/verified, extraction off, moderation off로 복구했다.

## 2026-08-13 4096 후속 triage

같은 fixture/runner·temperature 0·seed 42·3회로 Mi:dm `num_ctx=4096`을 재측정했다.
`eval/results/model-llm-context-midm-4096-2026-08-13.json`은 30,609 B, SHA-256
`542B0632765F10B8807C76EE2EC451383414A4F0CD99B995095B3AED01D316ED`이며 schema
first-pass 12/12·retry 0이지만 exact 0/12 FAIL이다. p0/p1/p2/p3 prompt P50은
1139/1547/2159/3587, active card·부정은 각각 0/12, 초기 사용자는 12/12, 초기
assistant는 3/3·0/3·0/3·2/3, 정정/tail은 12/12였다. 2048의 p2/p3 2042 ceiling
및 초기 사용자 물리 절단은 사라졌지만 card/부정 귀속은 실패했다. **4096은 품질
PASS가 아니며 운영 기본값은 2048을 유지한다.**

## 2026-08-13 production-context 후속 (별도 권위 결과)

위 raw capacity A/B와 4096 triage는 계속 유효하며 대체되지 않는다. 실제 proxy의 projection·typed card·continuity data 경로는 별도 `완료/AIRI-PRODUCTION-CONTEXT-CONTINUITY-GATE-2026-08-13.md`에서 2048, 4압력×3회로 측정했다. 구조·privacy·ordering은 PASS였지만 `bridge_fact` 0/12, continuity/latest correction 각 11/12로 semantic 전체는 FAIL이다. 따라서 운영 context 승격은 없고 기본값 2048을 유지한다.
