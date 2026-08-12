# AIRI 모델·LLM 변경 비교 분석 — 2026-08-12

## 결론

현재 기본 후보인 `midm-airi:2.0-mini`를 유지할 근거는 있다. 같은 16개
합성 fixture의 raw 모델 자동 gate는 기존 `exaone-airi:2.4b`의 3/16에서
Mi:dm의 9/16으로 개선됐고, 현재 production proxy 정책을 포함한 120-turn
교차 순서 A/B에서도 Mi:dm이 더 낮은 지연과 더 적은 실패를 보였다.

다만 이것은 모든 품질·지연 축의 승리를 뜻하지 않는다. Mi:dm의 raw 첫
토큰은 더 늦고 초당 생성량도 낮았다. 답변이 훨씬 짧아서 raw 완료 시간과
TTS 부담이 줄어드는 대신, 설명의 풍부함과 유용성이 부족할 위험이 있다.
또한 16개 자동 gate의 최종 판정은 두 모델 모두 FAIL이며 사람 검토를
대체하지 않는다.

## 실제로 바뀐 것

- 모델은 EXAONE 3.5 계열 Q4_K_M에서 Mi:dm 2.0 Mini Instruct Q4_K_M으로
  바뀌었다. 추론 엔진은 계속 로컬 Ollama/llama.cpp GGUF 경로다. 엔진
  교체가 아니라 모델·tokenizer/template 교체다.
- Mi:dm runtime tag는 AIRI system prompt가 직접 통제하도록 명시적
  header template와 stop token을 사용한다.
- 유효 `num_ctx`는 전후 모두 2,048이다. Mi:dm 원본의 더 긴 최대 context는
  현재 AIRI에서 사용하지 않는다.
- production sampling 기본값 `temperature=0.45`, `top_p=0.9`,
  `repeat_penalty=1.05`, `keep_alive=30m`은 모델 교체로 바뀌지 않았다.
- `num_gpu=999` 단일화, evaluator 기본 OFF, terminal token/time telemetry,
  balanced grounding, 질문용 evidence gate와 bounded retry/fallback이 함께
  들어갔다. 이들은 모델 자체 효과와 분리해서 평가해야 한다.
- KURE fp16, TTS cache/readiness, WAV progressive playback, STT streaming은
  별도 계층 변경이며 Mi:dm의 성능으로 계산하지 않는다.

## 1. Raw 모델 A/B

2026-08-12에 로컬에 보존된 두 모델을 외부 다운로드 없이 다시 측정했다.
동일 runner 0.3.4, Ollama 0.32.6, fixture/system prompt, `num_ctx=2048`,
`num_gpu=999`, `temperature=0`, `seed=42`, case당 3회 조건이다. 이 경로는
proxy grounding, memory, journal, Electron, STT, TTS를 우회한다.

| 항목 | EXAONE | Mi:dm | Mi:dm 변화 |
|---|---:|---:|---:|
| 자동 gate | 3/16 | 9/16 | +6 case, +37.5%p |
| warm TTFT 중앙값 | 129.1ms | 163.8ms | +34.7ms, 26.9% 느림 |
| 전체 완료 중앙값 | 388.8ms | 241.8ms | -147.0ms, 37.8% 빠름 |
| 생성량 중앙값 | 164.6 tok/s | 140.5 tok/s | 14.6% 낮음 |
| 답변 길이 중앙값 | 78자 | 24자 | 69.2% 짧음 |
| 출력 token 중앙값 | 43 | 11 | 더 짧은 답변 |
| runtime tag 크기 | 1,644,933,429B | 1,426,273,511B | -208.5MiB, -13.3% |

Mi:dm이 새로 통과한 축은 emoji 없는 축하, control-token 요청 경계, 성인
간 비노골적 대화 2건, character-card identity와 control precedence다.
반면 greeting contract, 짧은 응원, 모호한 요청의 확인 질문, memory가 없을
때 이름을 꾸미지 않는 응답, tool 진실성, 성인·미성년 안전 경계는 여전히
실패했다. 짧은 답변이 자동 `max_sentences` gate에는 유리하지만, 그 자체가
더 자연스럽거나 충분히 도움이 된다는 뜻은 아니다.

Mi:dm은 tokenizer/template 차이로 같은 fixture의 prompt token 중앙값이
855.5였고 EXAONE은 427.5였다. tokenizer 간 token 수는 직접 비교 가능한
언어 길이가 아니지만, 동일 2,048 context에서 Mi:dm 쪽의 여유가 더 작을
가능성은 별도 장문 대화 gate로 확인해야 한다.

## 2. 현재 LLM proxy 정책을 포함한 A/B

두 모델을 같은 현재 proxy에 명시적으로 지정했다. production sampling
기본값을 유지하고, public synthetic 6 case를 모델당 10회씩 A→B와 B→A
두 순서로 실행했다. 총 120 turn/model이며 test-origin header 때문에
memory와 journal을 변경하지 않는다.

| 항목 | EXAONE | Mi:dm | Mi:dm 변화 |
|---|---:|---:|---:|
| 표본 | 120 | 120 | 동일 |
| 전체 P50 | 633.6ms | 514.4ms | -119.2ms, 18.8% 빠름 |
| 전체 P95 | 1,336.4ms | 737.7ms | -598.7ms, 44.8% 빠름 |
| 빈 답변 | 2 | 0 | -2 |
| placeholder | 2 | 0 | -2 |
| 보수적 lexical violation | 3 | 0 | -3 |
| transport error | 0 | 0 | 동일 |

순서별로도 방향은 같았다. A→B에서 EXAONE 595.0/1,326.6ms,
Mi:dm 509.4/684.8ms였고, B→A에서 Mi:dm 514.8/758.4ms,
EXAONE 644.3/1,343.1ms였다(P50/P95).

EXAONE 문제 표본은 second-person question 2건의 빈 답/placeholder/화자
귀속 violation과 meal recommendation 1건의 외부 식당 claim이었다.
Mi:dm에서는 probe가 탐지한 해당 문제가 없었다. raw tok/s가 낮은 Mi:dm이
proxy 전체에서는 더 빠른 이유는 짧은 출력과 더 높은 1차 계약 준수율이
retry/fallback 비용을 줄였기 때문으로 해석할 수 있다. 다만 request별
retry 횟수를 이 보고서가 직접 집계하지 않았으므로 인과 확정은 아니다.

## 3. 전체 Electron 체인과의 관계

소스 build의 Mi:dm Electron text→default-render 20회는 개발용 source 측정이며, 운영 채택 또는 설치본 전환을 뜻하지 않는다. 운영 채택에는 설치본을 별도로 source에서 rebuild·검증해야 한다. 이 source 측정의 substantive output은
P50 1,963ms, P95 2,720ms였고 20/20이 완료·출력됐다. 이후 dev PC에서 동일
설치 ASAR·warm TTS를 고정하고 Mi:dm→EXAONE→Mi:dm→EXAONE 교차 블록으로
모델별 n=10의 matched control을 추가했다. first substantive render
P50/P95는 Mi:dm 1,501.5/2,597.2ms, EXAONE 1,752.5/3,233.0ms였다.

따라서 요구한 installed Electron matched 지연 gate는 완료됐고 현 구성에서
Mi:dm 기본 후보 유지에 모순되는 지연 증거는 없었다. 다만 n=10의 작은
표본이고 prompt별 TTS·render 분산이 커 일반적인 인과 우위나 품질 우위로
확대하지 않는다. 원시값과 통제 조건은
`완료/AIRI-INSTALLED-MODEL-RENDER-AB-2026-08-12.md`에 보존했다.

## 장점

1. 동일 raw fixture에서 구조적 계약 준수가 3/16→9/16으로 개선됐다.
2. 현재 proxy 대화 경로에서는 P50/P95와 빈 답·placeholder·탐지 violation이
   모두 개선됐다.
3. 답변이 짧아 raw 전체 완료와 이후 TTS 부담에는 유리하다.
4. runtime tag 파일은 약 208.5MiB 작다.
5. Mi:dm은 MIT이므로 EXAONE 3.5의 연구·비상업 제한을 제거한다. MIT의
   copyright/permission notice 보존 의무는 배포 시 계속 지켜야 한다.
6. `-ChatModel exaone-airi:2.4b` rollback tag와 원본 모델은 보존돼 있다.

## 단점과 남은 위험 (최초 분석 시점)

1. raw TTFT는 26.9% 느리고 tok/s는 14.6% 낮다. 긴 답변에서는 불리할 수
   있다.
2. 답변 중앙값이 69.2% 짧다. 간결함과 정보 손실을 구분하는 human review가
   필요하다. 자동 gate 9/16도 최종 FAIL이다.
3. effective context는 여전히 2,048이다. tokenizer 차이를 반영한 장문
   대화·memory/card 비교는 후속 dev PC 배치에서 완료했으나 양 모델 FAIL로
   위험이 확인됐다(아래 후속 반영 참조).
4. 과거 isolated runtime GPU 증분은 Mi:dm 1,946MiB, EXAONE 1,792MiB로
   Mi:dm이 154MiB 더 컸다. 작은 disk blob이 작은 runtime VRAM을 보장하지
   않는다. 현재 full stack의 약 842MiB 여유는 KURE fp16 절감과 함께 얻은
   결과다.
5. factual inaccuracy 가능성은 남는다. 현재 0 violation은 6개 public
   synthetic case의 보수적 lexical probe 결과이지 일반 사실성 증명이 아니다.
6. balanced grounding은 품질을 지키지만 과거 A/B에서 off 약 270.7ms 대비
   약 639.5ms였고 5/8이 retry했다. 이후 10개 meal 중 6개는 deterministic
   fallback을 사용했다. 현재 품질은 모델과 runtime policy의 결합 결과다.
7. 런처의 `ChatModel`은 preflight·warmup·표시에 쓰이지만 local request의
   `model` 필드를 강제하지 않는다. Electron/provider가 EXAONE을 보내면
   실제 foreground model도 EXAONE일 수 있어 model SSoT가 완성되지 않았다.
8. opt-in evaluation provenance의 fallback은 아직 EXAONE이며 launcher가
   `AIRI_EVAL_MODEL`을 설정하지 않는다. Mi:dm 평가가 EXAONE으로 오표기될
   수 있어 이 상태의 신규 평가 데이터는 승격 근거로 쓰면 안 된다.
9. health/header는 audible `응!` ACK가 있는데도 `silent`로 보고한다. 이는
   모델 품질 문제는 아니지만 latency 해석을 왜곡할 수 있다.
10. startup preflight는 tag 이름만 확인하고 digest를 pin하지 않는다. 같은
    tag를 로컬에서 다시 만들면 다른 artifact도 통과할 수 있다.

## 판정과 다음 gate

- Mi:dm 기본 후보는 유지한다. 지금 증거에서는 EXAONE으로 되돌릴 이유보다
  품질·라이선스 이득이 크다.
- model SSoT 강제, evaluation provenance, ACK metadata, model digest pin은
  코드와 dev PC 실기 검증을 완료했다.
- 최소 100개 인간 검수 대화가 남았다. 장문 context/memory/card 합성 corpus는
  정확성·답변 완전성·화자·부정·retry·출력 token 측정을 완료했지만 양 모델
  FAIL이므로 개선 후 동일 fixture 회귀가 필요하다.
- 같은 설치 Electron·TTS warm state의 교차 matched text→render A/B는
  모델별 n=10으로 완료했다. 이는 지연 checkpoint이며 인간 품질 검수를
  대신하지 않는다.
- 승인 지식 fixture 재현성과 운영 지식 배포는 계속 별도 과제다. 이 모델
  비교는 어떤 승인 지식도 운영에 자동 배포하지 않았다.

## 재현 자료

Raw 보고서는 `ollama-proxy/eval/results/model-llm-ab-*-2026-08-12.json`에
보존했다. 모든 prompt/answer는 public synthetic이며 개인 대화, session ID,
운영 DB, raw audio를 포함하지 않는다.

```powershell
python ollama-proxy\eval\run_airi_baseline.py `
  --model exaone-airi:2.4b --runs 3 --num-ctx 2048 --num-gpu 999 `
  --temperature 0 --seed 42 --output exaone.json

python ollama-proxy\eval\run_airi_baseline.py `
  --model midm-airi:2.0-mini --runs 3 --num-ctx 2048 --num-gpu 999 `
  --temperature 0 --seed 42 --output midm.json

python ollama-proxy\benchmark_dialogue_quality.py `
  --model exaone-airi:2.4b --repeat 10 --report exaone-proxy.json

python ollama-proxy\benchmark_dialogue_quality.py `
  --model midm-airi:2.0-mini --repeat 10 --report midm-proxy.json
```

공식 license/limit 근거:

- <https://huggingface.co/K-intelligence/Midm-2.0-Mini-Instruct>
- <https://huggingface.co/LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct/blob/main/LICENSE>

## 후속 반영 (2026-08-12)

위 raw/proxy 분석은 2026-08-12 최초 분석 시점의 기록이다. 그 시점 이후
`932eae6`(feat: close model SSoT gates, arm memory extraction, add Korean
output moderation)에서 §단점 7~10이 코드 레벨로 해소됐고, 후속 dev PC
배치에서 네 항목의 실기 검증도 완료했다.

| 항목 | 원 지적 | 해소 내용 | dev PC 실기 결과 |
|---|---|---|---|
| 7. model SSoT | 런처 `ChatModel`이 local request의 `model` 필드를 강제하지 않음 | `resolve_chat_model()` 단일 경유와 local foreground 모델 정규화 | 설치 Electron이 보낸 stale EXAONE 요청을 Mi:dm으로 정규화, `normalized_requests=1`; `ollama ps` Mi:dm 단일 runner 확인 |
| 8. eval provenance | fallback이 EXAONE이고 launcher가 `AIRI_EVAL_MODEL`을 설정하지 않음 | 미설정 시 SSoT 폴백, 런처가 evaluator/eval model 설정 | root 요약의 evaluator model, 실제 턴 후 terminal `last_status=ok`, provenance `model`·`model_version` 일치 확인; EXAONE 롤백도 동일 확인 |
| 9. ACK 표기 | audible ACK인데 header/health가 `silent`로 보고 | 분기별 `X-AIRI-Immediate-Ack`, health 사용자 턴 기준 `audible` | 설치 Electron 턴과 latency 해석에서 audible ACK를 본답변 render와 분리 확인 |
| 10. digest pin | preflight가 tag 이름만 보고 digest를 pin하지 않음 | digest 설정 시 불일치 fail-closed, 관측·상태 노출 | Mi:dm 실측 digest를 운영 기본 pin으로 고정; 일치 pin verified, 1자 불일치 pin은 11435 listen 전 차단 확인 |

관련 증거: `완료/AIRI-DEV-PC-SSOT-VERIFICATION-2026-08-12.md`,
`완료/AIRI-INSTALLED-MODEL-RENDER-AB-2026-08-12.md`.

## 장문 context·memory·card 후속 실측 (2026-08-12)

공개 합성 fixture를 raw Ollama에 같은 `num_ctx=2048`·temperature 0·seed 42로
모델별 4압력×3회 실행했다. 같은 1,451자 무압력 입력의 prompt token P50은
EXAONE 756, Mi:dm 1,139였고, 20 filler쌍에서 EXAONE 1,896 대비 Mi:dm은
2,042로 이미 포화됐다. exact case는 EXAONE 3/12, Mi:dm 0/12로 둘 다 FAIL,
schema first-pass는 양쪽 12/12, retry는 0건이었다.

Mi:dm은 최신 정정과 tail memory는 12/12 보존했지만 활성 card와 부정은
0/12였다. 둘 다 무압력에서도 실패했으므로 전부를 물리 truncation으로
설명할 수 없고, 근거 귀속·부정 이해 문제가 섞여 있다. 이 단일 합성
gate만으로 롤백을 결정하지 않지만 Mi:dm의 장문/card 안전성을 주장하지도
않는다. 상세 조건과
원시 보고서는 `완료/AIRI-LONG-CONTEXT-MEMORY-CARD-AB-2026-08-12.md` 참조.

## production 경로 후속 (2026-08-13)

이 문서의 최초 분석에 남은 model SSoT/eval provenance/ACK/digest 미구현 지적은 **당시의 역사적 상태이며 해소됨**이다. production proxy에는 이어서 typed active card, bounded canonical continuity ledger, 순수 snapshot seam 및 명시 session만의 persistence가 들어갔다. 이는 raw Ollama A/B와 구분해야 한다.

권위 production-context gate version 2.0는 `num_ctx=2048`, 0/8/20/48 압력×3회에서 구조·privacy·ordering PASS를 확인했다. generic structured-output 계약으로 spoken style 충돌을 제거하고 source-oriented fields·답 canary가 없는 질문·swapped/reordered anti-overfit test를 더한 결과, 7개 필드 중 6개는 12/12가 됐고 두 continuity color 필드는 v1의 11/12에서 개선됐다. 그러나 `dialogue_marker`는 0/12로 memory marker `silver-fern`을 결정적으로 복사해 semantic/gate/authoritative 전체는 FAIL이다. 이는 dialogue-vs-memory 구분의 모델 한계이므로 추가 prompt tuning이나 quality PASS 주장을 하지 않는다. raw capacity 2048/4096 근거를 바꾸지 않으며 default 2048과 extraction OFF를 유지한다. 상세는 `완료/AIRI-PRODUCTION-CONTEXT-CONTINUITY-GATE-2026-08-13.md` 참조.
