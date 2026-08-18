# 침묵 폴백 조치 이행 — ②b register 정규화 + ⑤ 문구 다양화
greybox (2026-08-18, 클로드 PC)

`완료/AIRI-GATE-SHORT-RESPONSE-ANALYSIS-2026-08-18.md`가 제시한 조치
5+1안 중, 사용자가 goal로 승인한 **②b(결정론 폴백 register 정규화
수리)** 와 **⑤(침묵 폴백 문구 다양화 greybox)** 를 이행한 결과
문서다. `ollama-proxy/ollama_proxy.py` · `ollama-proxy/test_ollama_proxy.py`
구현 diff와 로컬 실측 결과 JSON을 근거로 한다. 나머지 조치(①③④)와
운영 승격은 계속 사용자 결정 대기다.

## 1. ②b — 결정론 폴백 register 정규화 수리

분석 문서 2.5절이 찾은 존댓말 잔존 5건을 다시 판별했다 — 전부
`grounded_observation_fallback` 산출물이고, 인용부호 안이 아니라
**인용 밖 지문에 붙은 진짜 갭**이다: `sp01`×2(단발 OFF/ON),
`ms04`×2(단발 OFF/ON, 어미 "주세요"), `rx03`×1(단발 ON). 셋 다 코드
상수·산출 규칙과 바이트 대조로 재현을 확인했다.

수리 지점은 결정론 폴백 3종(관찰·대화·질문)이 `dialogue` 변수에
대입되는 자리다(`ollama_proxy.py:7453`·`:7474`·`:7494`). 대입 직전에
새 함수 `normalize_fallback_dialogue_register`(정의 `:2816`)를
거치도록 바꿨다. 이 함수는:

- 텍스트를 인용부호 안/밖으로 분리한다(`_split_grounding_quote_segments`,
  `:2775` 부근) — 인용 스팬(시청자 발화를 그대로 옮긴 부분)은
  존댓말이어도 바이트 그대로 보존한다.
- 인용 밖 지문에는 기존 `normalize_korean_register` 치환표를 적용한다.
  치환 후에도 존댓말 어미가 남으면(`_POLITE_REGISTER_RE` 매치) 그
  줄 전체를 빈 문자열로 반환해 **fail-closed**한다 — 출력 경계가
  모델 발화에 적용하는 규칙과 동일하다.
- 이미 반말인 줄은 바이트 그대로 통과한다.

실효과는 케이스별로 갈린다:

| 케이스 | 원문 어미 | 치환 결과 |
|---|---|---|
| `sp01` | "응원할게요" | "응원할게" (반말화 성공) |
| `rx03` | "모으네요" | "모으네" (반말화 성공) |
| `ms04` | "주세요" | 치환표에 형태소 보존형 반말이 없어 **빈 문자열** → 다음 폴백(침묵 폴백)으로 폴스루 |

트레이드오프 — `ms04`처럼 치환 불가능한 에코 2건(단발 OFF/ON)은
분석 문서 데이터셋(172건) 기준으로 "관찰 에코" 분류에서 "침묵 폴백"
분류로 이동한다. 58/172(33.7%) 였던 침묵 폴백이 산술상 60/172로
**+2건(+1.2%p)** 늘어난다. 정규화를 인용 밖 지문에만 걸어 시청자
발화 인용은 침해하지 않았다.

## 2. ⑤ — 침묵 폴백 문구 다양화 greybox

`GROUNDING_SILENCE_FALLBACK_DIALOGUE`("음, 잠깐만.")가 결과의
33.7%를 차지하는 단조로움을 겨냥한 조치다. env var
`AIRI_SILENCE_FALLBACK_POOL`(`configured_silence_fallback_pool`,
`:2058`)로 게이트하며 **default-deny** — 미설정·빈 값·인식 불가
값이면 기존 단일 문구·바이트 동일 경로를 그대로 쓴다. `"1"/"true"/
"yes"/"on"`(대소문자·공백 무시)만 켠다.

켜면 `next_grounding_silence_fallback()`(`:2084`)가 락 보호 카운터로
6문구를 **결정론 순환**(라운드로빈, 랜덤 아님)한다 — 재시작해도
슬롯 0부터 다시 시작해 한 문구로 쏠리지 않는다. 3개 호출 지점
(`:7521`·`:8876`·`:9170`, 스트리밍·비스트리밍 버퍼 경로 전부)을 모두
이 함수로 교체했다.

**풀 문구는 후보이며 사용자 미승인이다**(상수 정의부 주석에도 명기,
`:2046`). 슬롯 0은 기존 감사 대상 문구와 바이트 동일이다.

| 슬롯 | 문구 |
|---|---|
| 0 | 음, 잠깐만. |
| 1 | 어, 그건 잠깐 생각해 볼게. |
| 2 | 잠깐, 나 정리 좀 하고! |
| 3 | 음… 뭐라고 하지? |
| 4 | 아, 잠깐 헷갈렸어. |
| 5 | 그건 좀 있다가 다시 말해 줄게. |

## 3. 실측 — 풀 ON, 게이트 단발

`broadcast-chat-gate-pool-local-2026-08-18.json`, `--protocol
operational`, `midm-airi:2.0-mini`, CPU.

| 항목 | 값 |
|---|---:|
| 호출 수 | 38 |
| 실패 | 0 |
| 침묵 폴백 발생 | 19 |
| 존댓말 위반(`v_polite_response`) | 0 |

침묵 폴백 19건의 슬롯 분포는 **4/3/3/3/3/3**이다(기존 단일 문구
경로라면 19건 전부 동일 문자열). 존댓말 위반은 이번 arm에서
0건이다 — 수리 전 같은 픽스처의 게이트 단발 OFF는 2건, ON은
3건이었다(`broadcast-chat-gate-{off,on}-local-2026-08-18.json`
재집계).

케이스 대조로 두 갈래를 실증했다 — `sp01`은 "…응원할게!"로
반말화됐고(`banmal` 마커 true), `ms04`는 정규화가 빈 문자열을
반환해 침묵 폴백 슬롯("어, 그건 잠깐 생각해 볼게.")으로 폴스루됐다.
결과 JSON은 `.gitignore`(`ollama-proxy/eval/results/`) 대상이라
보존하려면 **force-add가 필요**하다 — 이번 세션에서는 실행하지
않았다.

## 4. 테스트

`test_ollama_proxy.py`에 새 클래스 2종(`SilenceFallbackPoolGreyboxTests`
5건, `DeterministicFallbackRegisterTests` 6건, 합 **11건**)을
추가했다. 로컬 전체 스위트 재실행 결과:

```
323 passed, 5 warnings, 462 subtests passed
```

CI `ollama-proxy-api` 샤드는 같은 세션에서 424 passed, 로컬
checkpoint는 PASS였다(CI 자체는 billing 차단 상태라 로컬 실행이
대체 증거다).

## 5. 남은 것

1. 풀 문구 6종 사용자 승인 — 승인 전까지 `AIRI_SILENCE_FALLBACK_POOL`은
   계속 OFF, 운영 경로는 기존 단일 문구를 그대로 쓴다.
2. soak 러너의 `NON_SUBSTANTIVE_RESPONSES` 동기화 — 풀 승인 시에만
   진행.
3. "음… 뭐라고 하지?"는 NFKC 정규화 시 말줄임표(…)가 마침표 3개로
   펼쳐져 문장 종결 카운트 방식에 따라 2문장으로 잡힐 수 있다.
   현재 채점기 기준으론 허용 범위지만 승인 시 재판단 대상이다.
4. 중기 조치 ①(빈 경계 재시도)·②(치환표 보강)는 코덱스 GPU 재실측
   후 판단한다.

## 6. 한계

- CPU 로컬 1회 실행이고 샘플링 변동으로 어느 케이스가 폴백에
  걸리는지는 런마다 달라진다(이번 런의 `rx03`은 모델이 자체적으로
  반말 생성해 폴백 대상이 아니었다).
- 관찰 에코/침묵 폴백 분류와 존댓말 위반 마커는 자동 휴리스틱이다.

원 데이터: `ollama-proxy/eval/results/broadcast-chat-gate-pool-local-2026-08-18.json`,
대조 `broadcast-chat-gate-{off,on}-local-2026-08-18.json`.

관련: `완료/AIRI-GATE-SHORT-RESPONSE-ANALYSIS-2026-08-18.md`(원인
분석·조치안 출처), `ollama-proxy/ollama_proxy.py`(구현),
`ollama-proxy/test_ollama_proxy.py`(회귀 테스트).
