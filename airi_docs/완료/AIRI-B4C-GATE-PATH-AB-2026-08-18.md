# B4c 게이트 경로 A/B — 존댓말 축 종결 실측 (2026-08-18,
검토 PC 로컬)

사용자 결정 sim_2(2026-08-18)에 따라 raw 경로 시뮬레이션은 사람
검토 근거로 **불인정**됐고, 향후 검토 근거는 11435 스타일
게이트(가능하면 TTS 포함) 경유 재검증으로 생산하기로 했다. 이
문서는 그 게이트 축의 첫 실측(검토 PC 로컬)이다. TTS 포함 축은
코덱스(GPU dev PC) 몫으로 남는다.

## 배경

B4c 방송 발화 계약은 지금까지 raw 직접 호출로만 실측했다
(`완료/AIRI-B4C-CONTRACT-AB-2026-08-14.md`,
`완료/AIRI-B4C-ADDRESSEE-CONTRACT-V3-2026-08-18.md`). 로드맵에는
'스타일 게이트 방송 경로 배선 확인'이 코드 실측(치환+드롭 로직
확인)까지만 등록돼 있었고, 게이트를 실제로 경유한 응답 품질
실측은 없었다. 사용자가 raw 경로 시뮬레이션 검토본을 인정하지
않기로 한 이상, 이 갭을 먼저 메워야 향후 검토 근거를 만들 수
있다.

## 구성

검토 PC에서 레포 `ollama_proxy.py`를 11435로 직접 기동했다 —
로컬 Ollama(11434)를 upstream으로, 모델은
`midm-airi:2.0-mini`(digest `106cfaac…`), `num_ctx=2048`, CPU
추론(`num_gpu=0`)이다. 샘플링은 운영 런처 기본값
temperature=0.45·top_p=0.9·repeat_penalty=1.05를 그대로 썼다.
memory·knowledge·moderation·screening·epistemic·affect는 전부
OFF로 평가 최소 구성이다.

계약 토글은 proxy 프로세스 env `AIRI_BROADCAST_CONTRACT`로
제어했다(OFF arm 미설정 / ON arm `1`). proxy는 러너가 보낸 시스템
메시지를 자기 운영 프롬프트로 교체한다 — 로그의
`active_character_card_merged: true`와 `system_chars` OFF
1991 vs ON 2593(계약 블록 ~600자 추가) 차이로 확인했다.
**즉 이 실측은 운영 경로 그 자체의 OFF/ON**이다. 러너
`--contract`는 off로 고정했고, 결과 JSON의 contract 필드는 러너
기준이라 off로 기록됨을 명기한다.

설치된 AIRI 앱·서비스는 무접촉이었다. 실측 후 proxy 프로세스는
소유 PID만 종료했다.

## 1. 발견 — 운영 프로토콜 요소

게이트 경로 응답에는 `<|ACT {"emotion":...}|>` 형태의 Live2D
감정 마커와 선반응 ACK("응!")가 포함된다 — **의도된 프로토콜**이다.
단발 AB의 TTFT p50이 OFF 10.1ms·ON 17.6ms로 극히 짧은 것 자체가
ACK가 즉시 발행된다는 증거다.

러너의 원 채점기는 이 마커·ACK를 본문에 포함해 계산하므로
`control_leak` 38/38(전건)과 자수 과대 집계가 그대로 나온다. 이는
게이트 경로 고유의 프로토콜 요소이지 결함이 아니다 — 다만
존댓말·반말·길이 마커를 있는 그대로 읽으면 왜곡된다.

따라서 아래 결과는 분석 단계에서 마커·선두 ACK를 분리한 뒤
(regex `<\|ACT [^|]*\|>` 제거 + 선두 `응!` 1회 제거) 러너의 원
채점기(`score_response`/`score_addressee`)로 재계산한 값이다.
러너가 낸 원 리포트(오염 포함)는 로그에 그대로 보존했다.

## 2. 결과 — 프로토콜 분리 재집계 (전 arm 실패 0, 총 172응답)

단발 38픽스처×2 arm + 리허설 2×24턴×2 arm = 172응답.

| | 단발 gate-OFF | 단발 gate-ON | 리허설 gate-OFF | 리허설 gate-ON |
|---|---:|---:|---:|---:|
| 반말(banmal) | 94% | 92% | **100%** | **100%** |
| 존댓말 위반 | 2건 | 3건 | **0건** | **0건** |
| 태그의문 | 5% | 15% | 6% | **18%** |
| length_fit | 42% | 39% | 50% | 47% |
| 자수 p50/p95 | 9/51 | 7/51 | 11/37 | 9/27 |
| addressee | 10/13 | 10/13 | 13/15 | **14/15** |
| addr 실패 | dn04·gr01·sp01 | 동일 | b04·b18 | b18 |

비교 기준(같은 날 raw 직접 호출): raw OFF 리허설 존댓말 24/24·
반말 0%, raw v3 ON 반말 앵커 복불복(0%↔88%).

## 3. 판정

1. **게이트가 존댓말 축을 종결한다** — 리허설 위반 0·반말 100%
   양 arm. raw에서 첫 턴 앵커로 잠기던 문제가 게이트 경로에서
   완전 해소됐다. "계약(지시)+게이트(출력 강제) 이중 배선" 가설
   실증 완료.
2. 계약 ON의 추가 기여는 게이트 위에서도 유효하다 — 태그의문
   5→15%/6→18%, 리허설 addressee 13→14(b04 주체 반전 해소).
3. **잔존 addressee(dn04·gr01·sp01·b18)는 게이트+계약 어떤
   조합으로도 불변**이다 — 결정론 렌더러(A4.2, thank B안 확정)
   이관의 최종 실측 근거다.
4. 관찰: 게이트 경로 응답이 매우 짧다(자수 p50 7~11 — length_fit
   하한 10자 미달 다수). 짧은 리액션 조각 자체는 관찰 연구
   정합이나 7~9자 수준의 단문 비율은 단조로움 관찰 대상이다.
5. 후속: ①러너에 프로토콜 분리 채점 옵션(현재는 분석 스크립트로
   수행) ②TTS 포함 재검증은 코덱스(GPU) ③라이브 배선 실증은
   B1b 조건 유지.

## 4. 한계

- **CPU 로컬**이다 — 완료 p50 ~4.0~4.5s는 비대표(proxy 재시도·
  평가 계층 포함).
- reps=1, 자동 마커 휴리스틱이다.
- ACK/마커 분리는 분석 단계 후처리이며, 러너가 낸 원 리포트와는
  다른 값임을 명기한다.
- 원 응답:
  `ollama-proxy/eval/results/broadcast-chat-gate-{off,on}-local-2026-08-18.json`,
  `broadcast-rehearsal-gate-{off,on}-local-2026-08-18.json`.

원 응답 전문:
`ollama-proxy/eval/results/broadcast-chat-gate-off-local-2026-08-18.json`,
`broadcast-chat-gate-on-local-2026-08-18.json`,
`broadcast-rehearsal-gate-off-local-2026-08-18.json`,
`broadcast-rehearsal-gate-on-local-2026-08-18.json`.

관련: `완료/AIRI-B4C-CONTRACT-AB-2026-08-14.md`(v1 계약 raw
전/후), `완료/AIRI-B4C-ADDRESSEE-CONTRACT-V3-2026-08-18.md`(v2/v3
계약 raw 실측 — addressee 사이드카 28케이스 출처),
`ollama-proxy/broadcast_contract.py`(계약 구현),
`ollama-proxy/ollama_proxy.py`(11435 스타일 게이트 구현).
