# AIRI 업그레이드 경로 탐색 — 2026-08-11

- **범위**: 코드 실측 + 웹 리서치 + GitHub 탐색 + Hugging Face 탐색 + 타당성 적대검증
- **투입**: 20 에이전트 병렬 (워크플로 16 + 전용 4), 누적 약 2.9M 토큰 / 도구 호출 1,200회 이상
- **성격**: **읽기 전용 조사**. 이 문서 2종 작성 외에 소스·설치본·서비스·모델을 변경하지 않았습니다. 모델 다운로드, 서비스 기동, 실제 마이크 입력을 수행하지 않았습니다.
- **부록**: `AIRI-UPGRADE-SCOUT-DATA-2026-08-11.md` (축별 후보 전량 + 검증 판정)

---

## 이 문서를 읽는 법

본문(§0 이하)은 조사 에이전트들의 종합 로드맵입니다. 그 앞에 **오케스트레이터가 직접 실측해 에이전트 보고를 정정한 4건**을 먼저 둡니다. 정정분이 로드맵의 일부 수치보다 우선합니다.

---

## ⚠️ 오케스트레이터 정정 — 에이전트 보고와 어긋난 4건

### 정정 1. 벡터 검색 "635배"는 단순 이식으로 재현되지 않습니다

GitHub 탐색 에이전트가 *"NumPy 0.147ms vs pure-Python 93.3ms = 635배"*를 근거로 벡터 DB 도입 취소를 권고했습니다. 이 PC에서 직접 측정한 결과 **단계별 비용이 다릅니다** (2,000행 × 1024차원, numpy 2.5.1):

| 단계 | 실측 |
|---|---:|
| blob join (`b"".join`) | 2.791ms |
| `frombuffer` + reshape | 0.001ms |
| **정규화 (norm + divide)** | **9.231ms** ← 지배적 |
| **matmul (정규화 캐시 시)** | **0.196ms** |
| **전체 재구축 (매 쿼리)** | **15.977ms** |
| **캐시 전략 (matmul만)** | **0.258ms** |

에이전트의 `0.147ms`는 **matmul만 잰 값**입니다. 매 쿼리마다 행렬을 재구축하면 실제로는 약 16ms입니다.

**결론은 유효하되 권고가 바뀝니다**: "NumPy로 교체"가 아니라 **"NumPy + 정규화 행렬 캐시(쓰기 시 무효화)"**입니다. 캐시 없이도 16ms로 150ms 예산에 여유가 크지만, 캐시하면 0.26ms로 떨어집니다. 메모리 비용은 2,000행 7.8MB / 10,000행 39MB로 무시 가능합니다.

부수 검증 2건은 사실로 확인됐습니다.
- 저장 포맷 `struct.pack("<%sf")` 바이트가 `np.frombuffer(dtype="<f4")`와 **완전 동일** → 저장 계층 변경 없이 drop-in
- 정확도 오차 최대 **2.2e-08**

측정 환경은 검토 PC이며 개발 PC(5600X)와 다릅니다. 절대값이 아니라 **단계 비율**을 근거로 삼으십시오.

### 정정 2. `prompt_lang="ja"`는 버그가 아닙니다

Hugging Face 탐색 에이전트가 *"GPT-SoVITS는 v2부터 한국어를 공식 지원하므로 `prompt_lang="ja"` 우회는 불필요한 품질 손실"*이라며 비용 0의 개선으로 지목했습니다. **오독입니다.**

```python
# gpt-sovits/openai_compatible_proxy.py:106-119
"text_lang": "ko",          # 합성 언어 — 이미 한국어
"prompt_lang": PROMPT_LANG, # "ja"
"prompt_text": "声聞こえてるかどうかだけ教えてほしいんだけどなぁ。..."
```

`prompt_lang`은 **레퍼런스 오디오 전사문의 언어**이고 그 전사문이 실제로 일본어입니다. `"ko"`로 바꾸면 오히려 깨집니다. 로드맵 T3-3도 같은 결론에 독립적으로 도달했습니다(`api_v2.py:31` 정의상 올바름 + 과거 무음 사고의 수정 결과).

남는 질문은 **일본어 레퍼런스로 한국어를 교차 합성하는 것이 최적인가**이며, 이는 비용 0이 아니라 같은 음색의 한국어 녹음이 필요합니다. 화자 변경 승인이 선행 게이트입니다.

### 정정 3. 소스 빌드 전환은 **이미 완료**됐습니다 — 최대 레버의 선행조건이 풀렸습니다

로드맵 §6-1이 "축 간 판정 충돌"로 남긴 항목입니다. 레포 문서에서 근거를 찾았습니다.

`airi_docs/AIRI-WORK-CHECKPOINT-2026-08-10.md:88-105` 기록:
- "최신 source build와 설치" — Tamagotchi Electron main/preload/renderer 빌드 통과
- 기존 packaged dependencies/resources에 fresh `out`을 mirror해 **28,085-entry `app.asar`** 생성
- 설치본 SHA-256 `D3A623CE…`, 크기 1,359,495,376 bytes
- 직전 설치본은 exact recovery backup으로 보존
- canonical source patch를 82개 source path로 재생성, 정방향·역방향 apply check 통과

즉 **UP-02는 완료 상태**이며, 이에 의존하던 T-01(클라이언트 청크 재생)과 Phase 6(AEC 동적 토글)이 **지금 착수 가능**합니다.

> 이 기록이 `AIRI-CURRENT-DOCS-INDEX-2026-08-10.md`에서 **Historical로 분류된 문서**에 들어 있습니다. 2026-08-10 독립 검토가 지적한 "색인이 문서를 정리하는 대신 증거를 잘라낸다"의 두 번째 실례입니다. 조사 에이전트가 이 충돌을 스스로 해소하지 못한 원인도 같습니다.

### 정정 4. `kure-fp16` 배선 지점 확인

로드맵이 "이득/비용 비율 1위"로 지목한 항목입니다. 코드에서 확인했습니다.

```python
# ollama-proxy/memory_runtime.py:157-170  SentenceTransformerEmbedder.__init__
kwargs: dict[str, Any] = {"local_files_only": True}
if device != "auto":
    kwargs["device"] = device
self.model = SentenceTransformer(resolved_model, **kwargs)
```

`kwargs`에 `model_kwargs={"torch_dtype": "float16"}`를 추가하는 **1~2줄** 변경이 맞습니다. 다만 절감치 **−1,150MiB는 추정**이며 실측이 아닙니다 — KURE-v1 `model.safetensors` 2.27GB에서 역산한 값입니다. 적용 전후 `nvidia-smi` 실측이 필요합니다.

---

## 조사가 뒤집은 기존 전제 3건 (로드맵 §0 요약)

| # | 기존 전제 | 정정 |
|---|---|---|
| ① | 블로커 #4 "TTS cold start 6.9초" | **표준 기동 경로에서는 사용자에게 노출되지 않습니다.** 런처가 프록시 기동 뒤 8880으로 실제 합성 1건을 동기 호출하므로 스크립트 반환 시점에 이미 warm입니다. 남는 구멍은 백엔드가 이미 떠 있어 워밍업을 스킵하는 경로 하나뿐입니다 |
| ② | 블로커 #3의 원인은 `echoCancellation:false` | **아닙니다.** half-duplex의 실제 원인은 재생 시작 시 VAD·마이크 스택을 **물리적으로 teardown**하는 로직입니다. AEC를 켜도 재생 중 VAD 이벤트가 0건이라 barge-in 트리거 자체가 생기지 않습니다 |
| ③ | TTS AbortSignal 미전달이 barge-in 1순위 | **이미 구현 완료**로 판정돼 후보에서 제외(BLOCKED). 잔여 작업은 취소 배선이 아니라 억제 해제 + 트리거 이동입니다 |

**적대적 검증에서 제외(BLOCKED)된 주요 항목**: STT `chunk_length` 30초 창 축소(STT 축이 "최대 단일 레버"라 부른 것), SenseVoice, TTS 엔진 교체 2종, speculative decoding, 화자 인증·전이중 S2S, spoken-only commit.

---

## 요약 — 결론 5줄

1. **"P50 ≤2초"는 현재 목표 정의로 산술이 닫히지 않습니다.** 발화종료 450ms + STT 850ms = 1,300ms를 LLM이 시작도 전에 소진하고, 남은 700ms에 TTS warm first byte 613ms가 거의 전부 들어갑니다. **지표를 첫 반응(≤1.5초, 사실상 달성)과 본답변 첫 음절(≤2.5초, Wave B로 도달)로 분리**하는 것이 권고입니다.
2. **가장 큰 한 방은 클라이언트 청크 재생**입니다. 서버는 이미 정직하게 스트리밍하는데 클라이언트가 100% 버립니다 — 두 개의 독립 실측이 −580ms(warm)와 −1,350ms(라이브 턴)로 일치합니다. 엔진을 무엇으로 바꿔도 고쳐지지 않는 **클라이언트 계약 문제**입니다.
3. **가장 싼 한 방은 `kure-fp16`** — 1~2줄로 추정 −1,150MiB. VRAM 예산 초과분 전체보다 크며, 이것 없이는 `num_gpu=999`·`num_ctx` 상향·모델 교체가 전부 막혀 있습니다.
4. **Ollama는 교체하지 마십시오.** 한국어 소형 모델이 GGUF에만 존재해(EXL2/EXL3/ONNX/AWQ 0개) llama.cpp 계열 이탈이 불가능하고, LLM 427ms는 목표를 통과한 유일한 구간입니다. 유일한 실질 결함(단일 러너 경합)은 `OLLAMA_NUM_PARALLEL=2`로 해소됩니다.
5. **라이선스 블로커에는 해답이 있습니다.** EXAONE 3.5는 NC 확정이고 EXAONE 4.0은 1.2B 다음이 32B라 후속이 없습니다. **KT `Midm-2.0-Mini-Instruct`(MIT, 2.3B)**가 한국어 품질 손실 없이(HAERAE 70.8 vs 61.3, Ko-IFEval 73.3 vs 65.4) VRAM도 −160MiB입니다.

---

# AIRI 업그레이드 로드맵 — 내일 착수 순서 (2026-08-11)

> 입력: 실측 3축(BUDGET / VRAM / MEMSCALE) + 조사 6축(TTS / STT / LLM / ARCH / UPSTREAM / PROXY), 적대적 검증 통과분만.
> 이 문서의 모든 수치는 **실측 / 추정 / 미측정** 중 하나로 라벨링했습니다. 라벨 없는 단정은 쓰지 않았습니다.

---

## 0. 먼저 — 종합 과정에서 드러난 3개의 판정 정정

로드맵을 짜기 전에, 축 간 대조에서 **기존 전제가 뒤집힌 항목 3건**을 먼저 확정해야 합니다. 이걸 모르고 착수하면 없는 문제를 고치게 됩니다.

| # | 기존 전제 | 정정 | 근거 |
|---|---|---|---|
| ① | 블로커 #4 "TTS cold start 6.9초" | **표준 기동 경로에서는 사용자에게 노출되지 않습니다.** 런처가 프록시 기동 뒤 8880으로 실제 합성 1건을 동기 호출(`Invoke-WebRequest -TimeoutSec 180`)하므로 스크립트 반환 시점에 이미 warm입니다. 워밍업 payload의 `text_lang`이 항상 `"ko"`라 g2pk2/MeCab 사전도 그때 로드됩니다. 남는 구멍은 `Test-Port 9880`이 true라 `$startedBackend=false`가 되는 경로(백엔드가 이미 떠 있을 때 런처 워밍업 스킵) 하나뿐입니다. | `gpt-sovits/start-local-stack.ps1:103-104,106-127`, `:110`(text_lang=ko 강제), `GPT_SoVITS/text/cleaner.py:37` → `text/korean.py:289` |
| ② | 블로커 #3의 원인은 `echoCancellation:false` | **아닙니다.** half-duplex의 실제 원인은 재생 시작 시 VAD·마이크 스택을 **물리적으로 teardown**하는 로직입니다. AEC를 켜도 재생 중 VAD 이벤트는 0건이라 barge-in 트리거 자체가 생기지 않습니다. `echoCancellation:false`는 별개 문제(STT raw capture)이고, 되돌릴 근거는 barge-in이 아니라 **STT 0-segment 실패율**입니다. | `apps/stage-tamagotchi/src/renderer/pages/index.vue:589-603`, `renderer/utils/voice-input-suppression.ts:1`(쿨다운 800ms), `patch-airi-audio-constraints.ps1:5-8`, `airi_docs/AIRI-LOCAL-STACK-REVIEW-2026-08-07.md:112` |
| ③ | ARCH-05(TTS AbortSignal 미전달)가 barge-in 1순위 | **이미 구현 완료 상태로 판정되어 후보에서 제외**됐습니다(BLOCKED). barge-in의 실제 잔여 작업은 취소 배선이 아니라 억제 해제 + 트리거 이동입니다. | ARCH 축 검증 결과(ARCH-08 verify 내 교차 확인) |

추가로, **적대적 검증에서 제외(BLOCKED)된 항목**을 명시합니다 — 요약문이 여전히 이들을 "최대 레버"로 지목하고 있어 혼동 위험이 큽니다.

- **STT-01 `chunk_length` 30초 창 축소 → BLOCKED.** STT 축 요약이 "최대 단일 레버"라 부른 항목이 살아남지 못했습니다. 따라서 **STT 축의 실현 가능 절감은 요약문보다 훨씬 작습니다**(beam -50~150ms 추정 + 이중 디코드 -10ms 실측이 전부).
- **STT-08(SenseVoice), T-06/T-07(TTS 엔진 교체), L5/L9(speculative decoding 포함), ARCH-09/ARCH-10(화자 인증·전이중 S2S), PX-07(spoken-only commit) → 전부 BLOCKED.**

---

## 1. 지연 예산 재구성

### 1-1. 현재(warm) — 두 개의 숫자를 분리해야 합니다

기존 "warm 합 ≈2,037ms"는 **ACK(캐시된 '응!')와 서버측 TTS first byte를 섞은 낙관 합성치**입니다. 사용자가 실제로 겪는 값은 다릅니다.

| 구간 | 낙관 합성치(문서 2,037ms 기준) | 실제 체감(warm) | 라벨 |
|---|---:|---:|---|
| 발화종료 감지 (클라 VAD) | 예산 밖 | 450 | 실측(패치 상수) |
| STT | 996.5 | 996.5 | 실측(저장 WAV) |
| LLM 첫 구절 | 427.3 ← **ACK** | 605.1 ← **본답변**(문장 완결까지 무음) | 실측 |
| TTS 첫 오디오 | 613.3 ← **서버 first byte** | 1,192.9 ← **재생 시작**(완성 버퍼링) | 실측 |
| **종단** | **≈2,037** | **≈3,244** | 산술 합 |

근거: `airi_docs/AIRI-LATENCY-ACCEPTANCE-2026-08-09.md:11-13`, `airi_docs/AIRI-PLAYBACK-TRACE-CHECKPOINT-2026-08-10.md`(재생 = TTS end +14ms), `ollama-proxy/ollama_proxy.py:5931-6044`(로컬 루프가 `boundary.feed()` 반환값 폐기) · `:6376`(유일한 본문 delta), `airi_docs/patches/AIRI-v0.11.3-local-runtime-source.patch:4189`(`decodeAudioData(전체 ArrayBuffer)`), `patch-airi-reaction-latency.ps1:9-10,250-254`(minSilence 1200→450).

> **주의**: 실제 음성 턴 실측은 STT 시작 +8,968ms(후속 턴 7.5~11.8초)입니다. 위 3,244ms와의 격차는 cold·러너 재적재·기억 검색 초과 등 비정상 경로가 섞인 값이며, **이 격차의 분해가 이 로드맵의 최대 미측정 항목**입니다(§6-4).

### 1-2. 웨이브별 예상치

| 구간 | 현재(체감) | Wave A<br>T0+T1 (1주) | Wave B<br>+T2 핵심 (3~4주) | Wave C<br>+T3 (분기) |
|---|---:|---:|---:|---:|
| 발화종료 감지 | 450 | 450 | 450 *(300은 A/B 조건부)* | 300 또는 스트리밍 STT로 흡수 |
| STT | 996.5 | **850~950** | 850~950 | **300~500** (STT-06 시) |
| LLM 첫 구절 | 605.1 | **450~600** | **300~500** | 300~500 |
| TTS 첫 오디오(재생 시작) | 1,192.9 | 1,192.9 *(불변)* | **700~800** | 700~800 |
| **본답변 첫 음절 종단** | **≈3,244** | **≈2,950~3,190** | **≈2,300~2,700** | **≈1,600~2,100** |
| **첫 반응(ACK) 종단** | ≈1,500 (추정) | ≈1,450 | ≈1,300 | ≈1,150 |

**각 칸의 근거와 라벨**

- **STT 850~950**: beam 3→1 −50~150ms(추정, `stt/openai_stt_server.py:115`; 인코더는 beam과 무관하므로 ALIGN-08의 −700ms는 정정됨) + 이중 디코드 제거 −10ms(**실측**, 검토 PC 8700G: WAV 7.5ms / webm-opus 9.5ms, `stt/openai_stt_server.py:371-391` vs `:394-406`). `chunk_length`가 BLOCKED이므로 이 이상은 구조 변경(STT-06) 없이는 없습니다.
- **LLM 450~600 → 300~500**: 평가자 off −0~50ms(**실측 상한**, `character_state_evaluator.py:327-343` `asyncio.wait(timeout=0.05)`), 기억 검색 초과 회수(§1-3), 절 단위 증분 SSE −100~200ms(추정, 하향 조정됨 — 아래 참조), prefix 안정화 −미지수(§6-3).
- **TTS 1,192.9 → 700~800**: 클라이언트 청크 재생으로 재생 시작이 서버 first byte(**실측** 613.3ms)로 당겨지고, 언더런 방지 프리롤 100~200ms(추정)를 더한 값입니다.
- **ACK 종단 ≈1,500**: ACK delta는 기억·지식 검색 **이전**에 방출되고(`ollama_proxy.py:5671-5676` vs `:5811-5825`), TTS는 `_WAV_CACHE`에서 락 이전에 반환됩니다(`gpt-sovits/openai_compatible_proxy.py:58,122-127,367-376`). 따라서 450+996.5+수십ms. **미측정 — 클라이언트가 ACK 오디오를 실제로 언제 재생하는지 확인 필요.**

### 1-3. 결론: "P50 ≤2초"는 지금의 목표 정의로는 도달 불가입니다

산술이 닫히지 않습니다.

```
발화종료 450 + STT 850 = 1,300ms  ← LLM이 시작도 하기 전에 소진
남은 예산 700ms 안에 LLM 첫 구절 + TTS 첫 오디오를 넣어야 하는데,
TTS warm first byte 613.3ms(실측) 단독으로 거의 전부를 씁니다.
```

즉 **T0~T2를 전부 해도 본답변 첫 음절 P50은 2.3~2.7초대**이고, 문자 그대로의 ≤2초는 **STT 또는 발화종료 감지를 구조적으로 줄이는 T3(STT-06 스트리밍 STT)** 없이는 불가능합니다.

**권고: 목표를 두 지표로 분리하십시오.**

| 지표 | 정의 | 달성 경로 |
|---|---|---|
| **첫 반응 P50 ≤1.5초** | T0 → ACK 오디오 재생 시작 | **사실상 달성 상태.** 클라이언트 ACK 재생 시점만 확인하면 됩니다 |
| **본답변 첫 음절 P50 ≤2.5초** | T0 → 본답변 첫 음절 | Wave B로 도달 가능 |
| ~~본답변 첫 음절 P50 ≤2.0초~~ | — | T3(STT-06, XL) 필요. **Wave B 실측 후 재결정** |

---

## 2. 티어 분류 (각 티어 안에서 이득/비용 비율 순)

### T0 — 즉시 (설정·파라미터, 코드 0줄, 오늘 저녁)

| 순위 | 항목 | 이득 | 비용 | 근거 |
|---|---|---|---|---|
| 1 | **PX-00 텔레메트리 판독** — llm/end의 `ollama_prompt_eval_count`·`prompt_eval_ms`·`raw_chars_16_ms`·`raw_content_last_ms` | 0ms. 대신 PX-01·PX-02·BUDGET-S1의 기대값을 추정→실측으로 전환 | 30분, 코드 0줄 | `ollama_proxy.py:68-77,5975-5981,6400-6412` |
| 2 | **vram-measure-now** — num_gpu=999 현행 구성 단계별 nvidia-smi + `ollama ps` PROCESSOR + `offloaded N/…` | 0ms. **모든 VRAM 판단의 전제**(현재 근거는 num_gpu=0 시점 2026-08-08 데이터) | 10분 | `start-airi-local-stack.ps1:97,102,185,186,200-221`; `latency-monitor/monitor_server.py:274` |
| 3 | **UP-02 완료 여부 확인** (§6-1) | 0ms. T1~T2 절반의 실행 가능 여부가 여기서 갈립니다 | 5분 | 축 간 판정 충돌 |
| 4 | **BUDGET-C1 캐릭터 평가자 off** (`-EnableCharacterEvaluator $false`) | 턴당 0~50ms + GPU 러너 경합 제거 | 런처 인자 1개 | `ollama_proxy.py:5096`, `character_state_evaluator.py:327-343` |
| 5 | **BUDGET-C5 `GPT_SOVITS_BACKEND_TIMEOUT` 60→15** | 지연 0. 최악 대기 60초→15초 | env 1개 | `gpt-sovits/openai_compatible_proxy.py:44,223-231` |
| 6 | **`AIRI_GROUNDING_MODE=off` A/B** | 진단용. grounding 재시도 빈도·비용 무코드 측정 | env 1개 | `ollama_proxy.py:1651-1657,1684` |
| 7 | *(조건부)* **BUDGET-C2 지식 off** | 게이트 통과 턴에서 0~350ms | 런처 인자 1개 | `ollama_proxy.py:416,420-429` |

> C2는 **T1의 KM-01(O(N²) 제거)로 대체하는 편이 낫습니다.** 기능을 끄지 않고 같은 비용을 없앱니다. C2는 KM-01 착수가 늦어질 때만 임시로 쓰십시오.
> **BUDGET-C4(기억 타임아웃 150→70)는 권장하지 않습니다** — KM-03이 근본 해결하며, 그 전까지는 회상 성공률만 더 떨어뜨립니다.

### T1 — 소규모 (며칠, 되돌리기 쉬움)

| 순위 | 항목 | 이득 | 비용 | 근거 |
|---|---|---|---|---|
| 1 | **kure-fp16** — `SentenceTransformer(..., model_kwargs={"torch_dtype":"float16"})` | **약 −1,150MiB VRAM (추정)**. 8GB 예산 초과분(추정 740~940MiB) 전체보다 큼. 품질 유지(GPU 상주 유지) | **1~2줄** | `memory_runtime.py:156-171`; `https://huggingface.co/nlpai-lab/KURE-v1/tree/main`(model.safetensors 2.27GB, 2026-08-11) |
| 2 | **L8 num_ctx/num_gpu SSoT** — 5곳 정렬 + **`ollama_proxy.py:3616-3617`의 dialogue director `num_ctx=1024` 제거** | 러너 재적재 stall 제거, 부분 오프로드 시 +1.2~1.5초 리스크 제거, TTFT 재현성 | 상수 5곳 + 게이트 1블록 | `ollama_proxy.py:107-108,3616-3617,4617-4618,4732-4733,4770-4771`; `Modelfile.exaone-airi:2-3`; `start-local-ollama-proxy.ps1:3,8,251` |
| 3 | **KM-01 지식 `retrieve()`의 매 쿼리 `initialize()` O(N²) 제거** | **실측**: 백필 anti-join 200청크 5.9ms → 1,000청크 105.7ms → 3,000청크 **2,560.6ms**. 반환 0행이어도 전액 지불 | 2줄 제거 + 인덱스 1개 | `knowledge_store.py:239-241,254-256,393` |
| 4 | **ARCH-08 텍스트 self-echo 가드** (NFKC + 문자 n-gram) | 자기 발화가 히스토리·**기억 DB에 영구 기록**되는 비가역 오염 차단 | 수십 줄, 의존성 0 | `index.vue:448-458,479-483`; 소스 패치 전수 grep 0건 |
| 5 | **STT-07 SSoT 정렬** + **STT-00 A/B 하네스** | 지연 0. `small/float16` vs `turbo/int8_float16` 3배 차이가 실행 경로에 따라 갈리는 상태 종결 | 기본값 1곳 + 스크립트 | `start-airi-local-stack.ps1:2-3,186-188` vs `stt/start-local-stt.ps1:2,5` vs `stt/openai_stt_server.py:76,81` |
| 6 | **STT-02 beam 3→1** *(STT-00 CER 표 확인 후)* | −50~150ms 추정 | 1줄 (`RECOVERY_BEAM_SIZE=3` 안전망 유지) | `stt/openai_stt_server.py:115-116,561,860-894` |
| 7 | **STT-04 이중 PyAV 디코드 제거** | **−10ms 실측**. 996.5ms의 1% — 싸고 안전하니 곁다리로 | 시그니처 1개 | `stt/openai_stt_server.py:387,832-837` |
| 8 | **ARCH-06 중단 시 8~15ms 게인 램프** | 클릭·팝 제거(방송 품질). barge-in 빈도에 비례 | 노드 1개 | `Stage.vue:295-304`(`source.stop()` 즉시), `:276-284` |
| 9 | **T-02① `/health` `immediate_response_cache.ready==total` 폴링** | 백엔드 잔존 프로세스 경로의 cold 노출 차단 | 폴링 루프 | `gpt-sovits/start-local-stack.ps1:103-104` |
| 10 | **UP-05 900ms 폴백 역채택** *(UP-02 후)* | 하드코딩 2700ms → `vadMinSilence + 900` 동적 추종 | S | `voice-input-session.ts:78,499`; 업스트림 `bcf7742`(#2095, 2026-07-26) |
| 11 | *(A/B 게이트 필수)* **STT-05 VAD 450→300** | −150ms **단, 무조건 아님** | 상수 1개 | `patch-airi-reaction-latency.ps1:9,17-20`(speechPad 360→600 상향 이력 = 봉투 한계 증거) |

> **T-03(TTS_LOCK acquire 타임아웃)은 T1에서 뺐습니다.** 검증 결과 `speech`가 sync def라 threadpool 40슬롯 중 1개만 점유하고, 실효 큐 깊이가 ~1(`response_sentence_limit=1`)이라 starvation이 성립하지 않습니다. 초과 시 503은 발화 유실=무음이라 1.2초 대기보다 UX가 나쁩니다. BUDGET-C5(env)로 충분합니다.

### T2 — 구조 (주 단위)

| 순위 | 항목 | 이득 | 비용 | 근거 |
|---|---|---|---|---|
| 1 | **KM-03 + KM-02 + KM-04 묶음** — numpy 벡터화 + fail-soft 계약 수정 + 벤치 차원 2→1024 | **실측**: 파이썬 cosine 1024dim 2,000행 379ms(BUDGET, 8700G) / 126.1µs·행(MEMSCALE) → numpy `M@q` **0.24ms**. 개발 PC(5600X, Zen3)는 1.2~1.4배 더 느릴 것으로 추정. **지연 −250~380ms + 기억 기능 복구**(현재 150ms 상한을 2.5배 초과 → 조용히 폐기 중일 가능성 높음) | M. 신규 의존성 **0**(numpy 2.5.1 이미 설치) | `airi_memory.py:177-188,1697-1705,1732-1737`; `memory_runtime.py:390-399,478,481-482`; `benchmark_memory_track.py:523-528,594-595` |
| 2 | **T-01 / BUDGET-S2 클라이언트 청크 재생** (AudioWorklet + PCM 링버퍼) | **−580ms(실측 warm: 1,192.9−613.3)** ~ **−1,350ms(실측 라이브 턴)**. barge-in 200~500ms의 전제조건(링버퍼 flush) | **L~XL**. UP-02 선행 | `api_v2.py:422-429`(백엔드는 이미 진짜 스트리밍), `patch:4189,4070`; MSE는 함정(Chromium은 raw PCM/WAV 미지원) |
| 3 | **PX-02 (+L7) 프롬프트 prefix 안정화** — `inject_character_state`·`memory_block`·**journal 3종 전부** tail 이동 | 미지수. PX-00의 `prompt_eval_count`가 매 턴 수백~2,048이면 −150~700ms(추정), 작으면 기각 | M | `ollama_proxy.py:3761`(첫 system에 append), `character_state.py:220-230`(`silence_ms`/`version` = 매 턴 변경), `airi_memory.py:1803,1684-1685`, tail 참조구현 `:3196-3242` |
| 4 | **PX-06(a) 로컬 스트리밍 제너레이터 분리** | 지연 0. 항목 2·3·5가 전부 같은 2,260줄 `proxy()`를 건드리므로 **충돌 방지 선행 작업** | L(중첩 클로저 → 컨텍스트 객체 필요) | `ollama_proxy.py:5006-7265`(await 51개), `:5656 stream_local_with_ack` |
| 5 | **PX-01 / BUDGET-S1 절 단위 증분 SSE** | **−100~200ms로 하향**(원 추정 300~800ms는 같은 문서의 검증관이 이미 반증). 출력이 1문장·≤96자로 하드 캡 | L | `ollama_proxy.py:6008`(반환값 폐기), `:6376`, `:5594-5610`(클라우드 대조군), `:1256-1258` |
| 6 | **barge-in 묶음: ARCH-03 → ARCH-01 → ARCH-04** | 끼어들기 지표를 **최초로 측정 가능**하게 만들고 목표 200~500ms 대역 진입 | M×3, 순서 고정 | `index.vue:589-603,307-352,475`; `speech-output-control.ts:4`; `workers/vad/vad.ts:144-148`; `Stage.vue:651-657` |
| 7 | **KM-08 journal_recall FTS5** | **실측** 0.060ms/메시지 → 미추출 4,096건 247.4ms. 코사인과 같은 150ms 예산 공유 | M | `airi_memory.py:27,940-958,970-977`; 한국어 패턴 재사용 `knowledge_store.py:44-67` |
| 8 | **KM-05 보존기간·GC·WAL·VACUUM** | 스캔 행 수 유계화. **`DELETE FROM`이 memory/conversation_message에 전무** | M(정책 결정 필요) | `airi_memory.py:261-265,397,445` |
| 9 | **UP-01 업스트림 main 리베이스** | 직접 지연 0. `#1803`(Whisper worker fail-fast) + UP-05 획득 | M. **미릴리스 브랜치** 회귀 리스크 | `compare/v0.11.3...main` = 126커밋(2026-08-11) |

### T3 — 전략 (스택·모델 전환)

| 순위 | 항목 | 판정 |
|---|---|---|
| 1 | **L2 KT Mi:dm 2.0 Mini Instruct 2.3B (MIT)** | **채택 권고.** NC→MIT로 라이선스 블로커 완전 해소(의무 조항 0건). 한국어 품질 **손실 없음** — KT 자체 표에서 EXAONE 3.5 2.4B 직접 비교: HAERAE 70.8 vs 61.3 / KMMLU 45.1 vs 43.5 / Ko-IFEval 73.3 vs 65.4 / Ko-MTBench 74.0 동률 / LogicKor 7.7 vs 7.4. VRAM **−160MiB**(Q4_K_M 1.33GiB vs EXAONE 1.49GiB, 실측 blob). **단 하나 실측 필요**: 48층 deep-narrow라 층당 커널 런치 1.6배 → tok/s 회귀 여부. 출처: `https://huggingface.co/K-intelligence/Midm-2.0-Mini-Instruct`(2026-08-11) |
| 2 | **ARCH-02 Chromium AEC3 재활성화** | **스피커 방송을 할 때만.** `echoCancellation`만 true, NS/AGC는 false 유지. 전제(§6-8) 미검증 + STT 회귀 게이트 필수 |
| 3 | **T-05 한국어 레퍼런스 확보** | `prompt_lang="ja"`는 **버그가 아닙니다**(`api_v2.py:31` 정의상 올바름, 과거 무음 사고의 수정 결과 — `airi_docs/AIRI-HANDOFF-2026-08-06.md:30`). 이득은 속도 0, 품질(교차언어 억양). **화자 변경 승인이 선행 게이트** |
| 4 | **STT-06 스트리밍 부분 전사** | P50 ≤2.0초의 **유일한 구조적 경로**. XL + 상시 GPU 점유(정량 미측정). **Wave B 실측 후에만 착수** |
| 5 | L3 Kanana 1.5 2.1B (Apache) | 폴백 전용. 품질 후퇴 명시적(KoMT 6.54 < 7.24), VRAM 회수 약 70MiB뿐 |
| 6 | L1 Kanana 2 3B / 후보 D(LLM 클라우드) | **보류.** L1은 라이선스 §4.1 모호 + KoMT 6.92 < 7.24 + VRAM +600~700MiB. 후보 D는 별도 승인 사안 |

---

## 3. 의존 관계

```
[T0 계측 3종] ─────────────────────────────────────────────┐
  PX-00 ──▶ PX-02(prefix) 승격/기각 판정                    │
       └──▶ PX-01(증분 SSE) 이득 확정                       │
  vram-measure-now ──▶ kure-fp16 검증 ──▶ L8 num_ctx 상향   │
  UP-02 완료 여부 확인 ──┐                                  │
                         │                                  │
kure-fp16 ───────────────┼──▶ L8(num_ctx 4096) ─────────────┤
  (−1,150MiB, 유일한     │      ▲                           │
   예산 확보 수단)       │      │                           │
       │                 │   ollama-num-parallel(적용지점 불명)
       └──▶ startup-order (예산 확보 전에는 피해자만 이동)   │
       └──▶ L1/추가 GPU 상주 제안 해금                       │
                         │                                  │
UP-02(소스 빌드) ────────┴──▶ T-01(클라 청크 재생) ★        │
       ├──▶ ARCH-03(억제 강등) ──▶ ARCH-01(헤드폰 모드)      │
       │                              └──▶ ARCH-04(트리거)  │
       │                                     └──▶ ARCH-02   │
       ├──▶ UP-05 / UP-01                                   │
       └──▶ UP-06 heard_response 차용 (barge-in 동작 후)     │
                                                            │
KM-01(지식 O(N²)) ──▶ BUDGET-C2(지식 off) 불필요화          │
KM-03(numpy) ──┬──▶ BUDGET-C4(timeout 70) 불필요화          │
               ├──▶ KM-04(벤치 차원) 동일 PR 필수            │
               ├──▶ PX-04(gather) 영구 기각                  │
               └──▶ KM-02(fail-soft) 동시 적용 권장          │
                                                            │
PX-06(a) proxy 분해 ──▶ PX-01 / PX-02 / T-01 서버측 충돌 방지┘

T-01 ──▶ BUDGET-C6(min_chunk_length 튜닝)이 비로소 의미 발생
T-01 + ARCH-03/01/04 ──▶ barge-in 200~500ms 달성 가능
STT-07 ──▶ STT-00 ──▶ STT-02 (정렬 없이는 A/B 수치가 무의미)
Wave B 실측 ──▶ STT-06 착수 여부 결정
```

**절대 순서 3개 (위반 시 개악)**

1. `kure-fp16` **전에** `startup-order`나 `num_ctx` 상향을 하지 마십시오 — 총합을 1MB도 줄이지 않고 피해자만 STT/GPT-SoVITS로 옮깁니다.
2. `KM-03` **전에** `KM-04`(벤치 차원 교정)를 단독 머지하지 마십시오 — 게이트가 즉시 FAIL 고정됩니다. 같은 PR로.
3. `ARCH-01/03/04`는 **묶음으로만** 의미가 있습니다 — ARCH-04 단독은 효과 0(재생 중 VAD가 teardown되어 speech-start가 발생하지 않음), ARCH-03 단독도 효과 0(전송 게이트가 여전히 억제 의존), ARCH-01 단독은 측정만 되고 달성은 안 됨.

---

## 4. 버리는 것 (검증은 통과했으나 이 프로젝트에는 권하지 않음)

### 4-A. 측정해보니 이득이 없는 것

| 항목 | 버리는 이유 |
|---|---|
| **PX-08 FastAPI/uvicorn/httptools/uvloop 튜닝** | **실측 합계 1ms 미만**. BaseHTTPMiddleware 1개 순비용 첫 청크 +0.104ms, 청크당 13.3µs. uvloop은 Windows 미지원. `workers>1`은 **금지**(기억·캐릭터·토픽 런타임이 프로세스별로 분리) |
| **JSON 왕복 / deepcopy 최적화** | 8,335B 페이로드 10왕복 **총 1.8ms 실측**, deepcopy 0.015ms |
| **PX-04 `asyncio.gather(기억, 지식)`** | **실측** 순수 파이썬 2개 동시 = **0.96배**(GIL로 손해), 혼합 1.23배. KM-03 후에는 이득 ~5ms |
| **PX-03 `num_predict=0` 선프리필** | 미리 프리필할 수 있는 토큰(안정 prefix = 이미 캐시됨)과 필요한 토큰(memory_block·journal·새 user 턴 = 검색 후 확정)이 **서로소**. `OLLAMA_NUM_PARALLEL` 기본값 1이라 워밍업이 유효 캐시를 덮어써 **더 느려질 수 있음** |
| **BUDGET-C6 TTS 스트리밍 파라미터 튜닝** | T-01 이전에는 이득 **정확히 0**. 여기 시간을 쓰면 실제 병목(클라이언트)을 못 봅니다 |
| **UP-09 업스트림 `streaming-pipeline.ts` 이식** | 업스트림 WS 파이프라인도 `flushAccumulatedAsSentence()`에서 **문장 단위 `decodeAudioData`**(`streaming-pipeline.ts:180-209`). "바이트 단위 스트리밍"이 아니므로 XL 비용에 이득 ~0. 게다가 클라우드 전용(`getAuthToken` 필수, `SERVER_URL` 고정) |
| **T-08 Supertonic ACK 합성기** | ACK는 이미 WAV 캐시로 **~0ms**(`openai_compatible_proxy.py:58,122-127`). 공개 클로닝 경로가 없어 ACK(화자 A)→본답변(화자 B) 음색 불일치만 추가 |

### 4-B. 근거가 뒤집힌 것

| 항목 | 버리는 이유 |
|---|---|
| **T-02 ②③ (503 반환 / korean 선-import)** | ③은 중복(워밍업 `text_lang="ko"` 강제로 이미 로드됨). ②는 클라이언트 재시도가 1회뿐이라 503 = 첫 발화 무음 = 개악. **①(/health 폴링)만 채택** |
| **T-03 TTS_LOCK acquire 타임아웃** | threadpool starvation 전제가 성립하지 않음(sync def → 스레드 1개 점유, 실효 큐 깊이 ~1). 진짜 hang(requests의 per-read timeout)은 이 수정으로 안 고쳐짐 |
| **STT-03 `without_timestamps=True`** | 타임스탬프 토큰은 세그먼트당 **2개**(감싸는 형태)이지 토큰마다가 아님. `vad_filter=True`+`max_new_tokens=64` 조건에서 절감은 한 자릿수 ms. 대신 `segment_timing_is_valid`(`:509-529`) 환각 필터와 526줄 회귀 스위트를 잃음 |
| **BUDGET-C3 임베더 비활성/CPU 이전** | `kure-fp16`이 **같은 VRAM 문제를 품질 손실 없이** 해결. CPU 이전은 질문 임베딩이 TTFT 직렬 경로(`airi_memory.py:1665`)에 있어 150ms 예산을 위협 |
| **BUDGET-C4 기억 타임아웃 150→70** | KM-03이 근본 해결. 그 전까지는 회상 성공률만 하락하는 응급조치 |
| **L6 llama.cpp llama-server 직접 구동** | Ollama가 **이미 llama-server를 벤더링해 직접 기동**(`llm/llama_server.go:368-408`, `--cache-prompt` 기본 on). 순증 이득은 `--cache-reuse` 하나뿐인데 RoPE KV shifting 근사라 출력이 달라짐 — 캐릭터 일관성 프로젝트에 무비용 아님. `-ngl` 결정론은 L8로 해결 |
| **L9 speculative decoding** | 타깃이 이미 2.4B, temp 0.45 샘플링이 수용률 삭감, draft VRAM 여유 없음, Ollama는 Apple MLX 한정. **적극 비추천** |
| **L10 한국어 imatrix 재양자화** | 인용된 3.8% PPL 개선은 **Mistral-7B + IQ2_XS(2.06bpw)** 실험. Q4_K_M(4.8bpw) 외삽 근거 없음. 모델 바꿀 때마다 재생성 필요 → L2/L3의 "커뮤니티 GGUF 즉시 pull" 장점을 스스로 폐기 |
| **VRAM `startup-order`** | 총합을 1MB도 줄이지 않음. 예산 확보 전 적용하면 피해자만 STT/TTS로 이동(CUDA OOM 또는 CPU 폴백) |

### 4-C. 유지보수 비용이 이득을 넘는 것 (1인 운영)

| 항목 | 버리는 이유 |
|---|---|
| **KM-06 sqlite-vec** | pre-1.0 알파(0.1.9 / 2026-03-31), **ANN 미구현**(issue #25 open) → numpy와 동일한 brute force. 아키텍처적 우위 없음 |
| **KM-07 faiss-cpu / hnswlib** | 수백만 벡터에서만 유의미. KM-05 적용 시 현실 상한 수만 행 → numpy 50,000행 6.695ms(예산의 1~4%). ANN은 recall<100%로 "저장했는데 안 나오는" 조용한 누락 — 기억 계층에서 최악의 실패 모드. hnswlib은 Windows 휠 부재(MSVC 빌드 실패 다수 보고) |
| **KM-09 knowledge embedding BLOB 전환** | `allow_semantic` 기본 False라 **현재 프로덕션에서 이 비용이 발생하지 않음**. KM-01 먼저 |
| **ARCH-07 재생 참조 신호 상관 게이트** | "AEC보다 단순"이 성립하지 않음 — 지연 추정(AEC3 delay estimator와 동일 난제) + 두 AudioContext 클럭 드리프트가 그대로 남음. 정당한 끼어들기를 막는 최악 실패 모드 존재. ARCH-02 실측이 우선 |
| **UP-07 pipecat / LiveKit Agents 채택** | 블로커 #2·#3이 전부 **Electron 클라이언트** 안에 있는데 이들은 서버측만 대체. pipecat README에 **한국어 언급 0건**, self-hosted TTS 목록에 GPT-SoVITS 없음(Piper뿐), Windows 네이티브 명시 없음 |
| **UP-06 Open-LLM-VTuber 전면 대체** | pushed_at 2026-05-15(약 3개월 정체), v2.0 전면 재작성 예고. **`heard_response` 개념만 차용**(barge-in 동작 후, MIT 고지 유지, Live2D 샘플 에셋은 별도 라이선스라 가져오지 말 것) |
| **UP-08 Amica** | pushed_at 2025-07-23, 13개월 정체 |
| **TTS 엔진 교체 전부** (Fish S2 Pro / Kokoro / MeloTTS / MOSS-TTS-Nano / Qwen3-TTS) | Fish = 상업 사용 별도 라이선스 필요(EXAONE NC 문제의 TTS 반복) + H200 수치. Kokoro = 한국어 없음. MeloTTS = 클로닝 없음. MOSS-TTS-Nano = **이 PC 실측 RTF 4.687**. Qwen3-TTS = 3090/4090 수치, 한국어 근거 없음 |
| **STT 대안 모델 전부** (Parakeet / Canary / Moonshine / Distil-Whisper / Kyutai) | **한국어 미지원**. Voxtral-Mini-4B-Realtime은 한국어 O이나 BF16 ≥16GB — 후보 D를 채택해도 4B BF16은 안 들어감. 재검토 트리거는 "검증된 int8/AWQ 빌드 등장 **+** 후보 D 채택" |

---

## 5. 가장 큰 한 방

# ★ 클라이언트 청크 재생 (T-01 / BUDGET-S2)
### AudioWorklet + PCM 링버퍼로 `decodeAudioData(전체 ArrayBuffer)` 대체

**이득: −580ms (warm 실측) ~ −1,350ms (라이브 턴 실측)**

**왜 이것인가 — 근거 5가지**

1. **유일하게 독립적인 두 실측이 일치합니다.** (a) acceptance warm: 1,192.9 − 613.3 = **580ms**. (b) 2026-08-10 라이브 턴: TTS 1,965.8ms인데 재생은 TTS **end** +14ms → first byte 대비 약 **1,350ms**. 다른 어떤 후보도 이 수준의 증거를 갖지 못했습니다(`airi_docs/AIRI-LATENCY-ACCEPTANCE-2026-08-09.md`, `airi_docs/AIRI-PLAYBACK-TRACE-CHECKPOINT-2026-08-10.md`).

2. **서버는 이미 정직하게 스트리밍하는데 클라이언트가 100% 버립니다.** `api_v2.py:422-429`가 첫 청크에 WAV 헤더를 흘린 뒤 raw int16 PCM으로 전환합니다. 그런데 `patch:4189`가 `res: ArrayBuffer` 전체를 받고 `decodeAudioData(res)`를 호출합니다. 소스 패치 전수 grep에서 **AudioWorklet / MediaSource 0건**. 즉 `streaming_mode=2`·`min_chunk_length=16`·`parallel_infer` 튜닝의 현재 이득은 **정확히 0**입니다.

3. **엔진을 무엇으로 바꿔도 고쳐지지 않습니다.** TTS 축 판정대로 GPT-SoVITS v2ProPlus는 8GB 예산에서 여전히 최선이고(2026-08-11 릴리스 API 조회: 최신 태그 20250606v2pro), 한국어+제로샷+8GB를 통과하는 대체재가 없습니다. 이 결함은 엔진 교체로 우회 불가능한 **클라이언트 계약** 문제입니다.

4. **barge-in 200~500ms의 물리적 전제입니다.** 링버퍼 flush로 즉시 중단이 가능해지고, 그 없이는 ARCH-01/03/04를 다 해도 재생 중단이 완성 버퍼 단위로 남습니다.

5. **제약 위반이 하나도 없습니다.** VRAM 0, 127.0.0.1 유지, 한국어 무관, 라이선스 무관, 서버 변경 최소(현행 `media_type="wav"`도 44B 헤더 뒤 raw PCM이 이어지므로 **헤더만 파싱하면 프록시 변경 0줄**).

**실행 전 반드시 알아야 할 것**

- **MediaSource는 함정입니다.** Chromium MSE는 raw PCM/WAV/ogg를 재생하지 못합니다. AudioWorklet + 링버퍼가 유일한 경로입니다.
- **샘플레이트를 하드코딩하지 마십시오.** `TTS.py:361`의 32000은 클래스 기본값이고 실제 값은 `:526`에서 체크포인트 hps로 덮어써집니다. WAV 헤더를 파싱하십시오.
- **재배선 범위**: `playbackManager`가 AudioBuffer로 제네릭 고정(`patch:4040-4110`), lipsync analyser 배선(`Stage.vue:276-284`), round-cancel이 AudioBuffer 결과에 키잉 — 이 3개를 함께 갈아야 합니다. 그래서 L~XL입니다.
- **선행조건**: UP-02(소스 빌드). §6-1 확인 결과에 따라 **이미 충족일 수 있습니다.**
- **이득 상한 주의**: `response_sentence_limit=1` + "10~45자 한 문장" 계약 때문에 "문장이 길수록 선형 증가"는 성립하지 않습니다.

### 준우승: `kure-fp16` — "가장 싼 한 방"

**1~2줄로 −1,150MiB(추정).** 8GB 예산 초과분(추정 740~940MiB) 전체보다 큽니다. 이것 없이는 `num_gpu=999`가 산술적으로 성립하지 않고, `num_ctx` 상향도 `startup-order`도 L1도 전부 막혀 있습니다. **이득/비용 비율로는 로드맵 전체 1위**입니다. 다만 지연 자체는 직접 줄이지 않으므로 "가장 큰 한 방"은 T-01입니다.

---

## 6. 불확실성 — 실측 없이는 판단 불가한 항목과 확인 절차

### 6-1. ★ UP-02(소스 빌드 전환)가 이미 완료됐는가 — **축 간 판정 충돌**

**충돌**: ARCH 축 검증관은 `airi_docs/AIRI-WORK-CHECKPOINT-2026-08-10.md:88-105`("최신 source build와 설치", Electron main/preload/renderer 빌드 통과, **28,085-entry app.asar 재생성 + SHA-256 기록")을 근거로 **"in-place asar 등길이 패치 제약은 더 이상 적용되지 않는다"**고 판정했습니다. 반면 UPSTREAM 축은 UP-02를 **미완료 전제**로 최우선 항목에 두고 Windows 빌드 비용(godot `extraResources`, 네이티브 의존)을 나열합니다.

**이 하나로 T1~T2의 절반(T-01·ARCH 전체·UP-05·UP-01)이 "내일 착수 가능"인지 "L급 선행작업 필요"인지가 갈립니다.**

**확인 절차 (5분)**
```powershell
# 1) 현재 설치본 asar 엔트리 수 — 28,085와 대조
npx asar list "<AIRI설치경로>\resources\app.asar" | Measure-Object -Line
# 2) SHA-256 대조
Get-FileHash "<AIRI설치경로>\resources\app.asar" -Algorithm SHA256
#    → AIRI-WORK-CHECKPOINT-2026-08-10.md 기록값과 비교
# 3) 소스 트리에 빌드 산출물이 있는가
ls external\airi\apps\stage-tamagotchi\dist, external\airi\apps\stage-tamagotchi\out
# 4) 패치 스크립트가 최근에 다시 돌았는가
ls airi-local-stack\patch-airi-*.ps1 | select Name, LastWriteTime
```
- 일치 → **UP-02 완료. T-01/ARCH 즉시 착수 가능. 로드맵 3~4주 단축.**
- 불일치 → UP-02가 T1 최우선. 단 `pnpm --filter @proj-airi/stage-tamagotchi...`로 범위를 좁혀 `isolated-vm`·`node-pty` 네이티브 컴파일을 회피하고, `engines/stage-tamagotchi-godot` 산출물(.NET SDK + Godot export) 필요 여부를 먼저 확인하십시오.

### 6-2. num_gpu=999의 실제 오프로드 층수와 VRAM 총합

**현 상태**: 산술상 8,930~9,130MiB로 8,192MiB를 **740~940MiB 초과**(추정)이며, Ollama는 로드 시점 가용량에 맞춰 자동 하향하므로 실제 층수가 실행마다 다를 수 있습니다. **현 구성 실측이 2026-08-08(num_gpu=0 시점) 이후 없습니다.**

**절차**
1. `start-airi-local-stack.ps1` 기본 프로필로 기동하며 각 단계 직후 `nvidia-smi` 스냅샷(`:97 monitor → :102 proxy/KURE → :185 GPT-SoVITS → :186 STT → :200-221 Ollama warmup`).
2. 워밍업 직후 `ollama ps`의 PROCESSOR 컬럼 + Ollama 서버 로그의 `offloaded N/…layers to GPU`.
3. `kure-fp16` 적용 전/후를 같은 절차로 대조.

**판정 기준**: N < 전체 층수면 생성 속도가 약 25~30 tok/s로 떨어져(실측 CPU 17.82 tok/s와 GPU 추정 70~110 tok/s의 혼합) 60자 응답에 **+1.2~1.5초**(추정)가 붙어 목표를 이것 하나로 파괴합니다.
※ EXAONE 3.5 2.4B는 30층(HF config)이므로 로그 표기가 `N/31`인지 `N/30`인지 실제 문자열을 확인하십시오.

### 6-3. Ollama가 프롬프트 prefix KV를 실제로 재사용하는가

**PX-02의 전제 전체가 여기 걸려 있습니다.** 인용된 `--cache-prompt` 문서는 llama.cpp server의 것이고, 실제 업스트림은 Ollama입니다. Ollama가 요청 간 prefix를 재사용한다는 공식 명시가 문서에 없습니다.

**절차 (1분)**: 완전히 동일한 프롬프트를 2회 연속 전송하고 `llm/end` 이벤트의 `ollama_prompt_eval_count`를 비교합니다.
- 2회차가 크게 줄어듦 → 재사용 있음. **PX-02를 T2 상단으로 승격.**
- 동일 → 재사용 없음. **PX-02 기각**, 대신 §6-2의 num_ctx/러너 재적재 쪽에 집중.

### 6-4. ★ 라이브 턴 8,968ms와 warm 산술 3,244ms의 격차 5,724ms는 어디서 오는가

**이 로드맵 전체에서 가장 큰 미측정 항목입니다.** 후속 턴도 7.5/7.7/11.8초라 일회성 cold가 아닙니다.

**후보 가설(전부 미검증)**: (a) 기억 검색 150ms 초과 후에도 `asyncio.to_thread`가 취소되지 않아 GIL을 계속 점유(5,000행 630ms 스캔이 타임아웃 후 480ms 더), (b) dialogue director의 `num_ctx=1024`가 러너 언로드→재로드를 유발(`ollama_proxy.py:3616-3617`), (c) 부분 오프로드로 인한 tok/s 저하, (d) grounding 재시도(상한 5.0s) 발동, (e) TTS 워밍업 락 경합.

**절차**: 실제 마이크 턴 5~10건에서 latency-monitor 이벤트를 **한 세션 안에서 시계열로** 덤프하고 인접 이벤트 간 간격을 전수 정렬하십시오. 단계 간 heuristic 합산(8892 snapshot)이 아니라 **동일 trace_id 내 타임스탬프 차**로만 판단해야 합니다. 여기서 5초짜리 구멍 하나가 나오면 **이 로드맵의 우선순위가 통째로 바뀝니다.**

### 6-5. 기억 검색이 지금 실제로 몇 %의 턴에서 타임아웃하는가

파이썬 cosine이 2,000행에서 이미 150ms 상한을 2.5배 초과하므로 "느린 것" 이전에 **조용히 안 되고 있을** 가능성이 큽니다. 그리고 타임아웃 시 `memory_runtime.py:478`이 빈 결과에도 `extraction_watermark`를 적용해 **과거 턴까지 히스토리에서 제거**하고, `MEMORY_QUERY_RE` 매칭 질문이면 "기억에 없으면 모른다고 짧게 말해"가 주입되어(`ollama_proxy.py:4026-4041`) AI가 **실제로 저장된 사실을 부정**합니다.

**절차**: `/health`의 memory 카운터 + latency-monitor의 `memory retrieve_end` 이벤트 + 현재 DB 행 수(`SELECT count(*) FROM memory WHERE status='active'`)를 함께 읽으십시오. 행 수가 1,000을 넘으면 KM-03을 **T2 1순위에서 T1으로 승격**하십시오 — 지연 문제가 아니라 기능 정지 문제입니다.

### 6-6. STT 996.5ms의 인코더/디코더/VAD 분해

**주의 — 정정**: `analysis_ms`(`:838`)는 PyAV 디코드+메트릭 구간이고 `inference_ms`(`:847`)는 `whisper.transcribe` **전체**입니다. **이 둘로는 인코더/디코더를 분리할 수 없습니다.** faster-whisper 내부 계측을 별도로 넣어야 합니다. beam 되돌림의 기대 이득이 여기서 확정됩니다.

또한 STT-00의 CER 측정에는 **참조 녹음이 선행 필요**합니다 — 계획서 §9의 문장 7종은 TTS 합성용 텍스트이고 정답 전사가 없습니다. TTS로 합성한 WAV로 재면 acceptance 문서가 이미 경고한 "실제 마이크 아님" 한계를 그대로 반복합니다.

### 6-7. VAD 450→300ms가 순이득인가 순손실인가

**절차**: 현행 450 / 300 각각에서 실제 마이크 발화 20건씩을 녹음하고, ① 발화당 세그먼트 분할 횟수, ② 선두 고유명사 절단율, ③ 턴당 STT 왕복 횟수를 기록합니다. 분할이 1회라도 늘면 그 턴은 STT 왕복(≈900ms+)을 한 번 더 물어 **−150ms가 +750ms로 역전**됩니다. 근거: `patch-airi-reaction-latency.ps1:17-20`이 이미 "선두 고유명사가 2턴 중 1턴 잘려 speechPad를 360→600으로 올렸다"고 기록 — 봉투가 한계에 있습니다.

### 6-8. Chromium AEC3가 Web Audio 출력을 참조 신호로 잡는가

MDN은 `true`가 최소 `remote-only`(RTCPeerConnection 원격 트랙) 수준을 취소한다고만 하고, **참조 신호가 무엇인지 명시하지 않습니다.** AIRI 자기 출력은 `audioContext.destination` 직결(`Stage.vue:276-284`)입니다. 스펙상 보장하려면 `echoCancellation: "all"`이 필요한데 Chromium 지원 여부가 미확인입니다.

**절차 (헤드폰 없이, 스피커 재생 중)**: `echoCancellation:true`로 마이크 스트림을 열고 AIRI 발화 중 마이크 RMS와 Silero VAD speech 확률을 로깅합니다. 재생 중 speech 확률이 임계 미만으로 유지되면 참조에 포함된 것입니다. **이 실측 전에 AEC 알고리즘을 고르는 논의는 데이터 없이 하는 선택입니다.**

### 6-9. 그 외 (착수 시점에 함께 확인)

| # | 항목 | 절차 |
|---|---|---|
| a | **TTS cold 6,897ms의 구성** | `openai_compatible_proxy.py:254`가 이미 남기는 `lock_wait_ms`를 cold 샘플에서 읽으십시오. 이 값이 지배적이면 워밍업 경합, 작으면 순수 CUDA 초기화 |
| b | **KURE fp16 검색 품질 회귀** | 기존 DB 벡터는 fp32 생성분. `test_airi_memory`/`test_memory_runtime` 회귀 + Hit@k 스팟 검증. **KURE-v1 공식 fp16 검증 문서 없음 — 확인 필요** |
| c | **Mi:dm 2.0 Mini(48층)의 실제 tok/s** | 파라미터는 적지만 층당 커널 런치가 EXAONE 30층 대비 1.6배. 3060 Ti 실측 필요. 벤치마크 표는 KT 자체 표라는 편향 caveat 유지 |
| d | **`OLLAMA_NUM_PARALLEL` 적용 지점** | 프로덕션 런처는 Ollama를 **기동하지 않습니다**(`start-local-ollama-proxy.ps1:250-251`은 파이썬 프록시만). 런처에 env를 추가해도 no-op. 실제 적용은 Ollama 서비스 환경변수 + 서비스 재시작. 공식 FAQ상 기본값이 이미 **1**이므로 이득이 0일 수 있음. `OLLAMA_MAX_LOADED_MODELS` 기본 "3 × GPU 수"가 8GB에서는 더 실질적 위험 |
| e | **`speechPadMs=600`이 종단에 가산되는가** | 세그먼트 끝 패딩이 전송 시점을 늦추는지 실측. §1-2 표는 이를 가산하지 않았으므로, 가산된다면 모든 종단값에 +600ms |
| f | **num_ctx 2048에서 truncation이 실제로 발생 중인가** | 시스템 프롬프트 947자(실측) + 최근 60턴이 2048 토큰에 들어갈 리 없음. truncation은 KV prefix를 통째로 깨뜨려 지연·품질 동시 악화. Ollama 로그 또는 `prompt_eval_count` 상한 도달 여부로 확인 |

---

## 7. 내일 아침 착수 순서 (요약 카드)

```
[오전 — 계측 3종, 코드 0줄, 약 1시간]
  1. UP-02 완료 여부 확인 (5분)          ← 로드맵 3~4주가 여기서 갈립니다
  2. vram-measure-now (10분)             ← 이후 모든 VRAM 판단의 전제
  3. PX-00 텔레메트리 판독 (30분)        ← PX-01/PX-02 기대값 확정
  4. Ollama prefix 재사용 2회 테스트 (1분)
  5. /health memory 카운터 + DB 행 수 (5분) ← KM-03 승격 여부

[오후 — T0 설정, 재기동 1회]
  6. -EnableCharacterEvaluator $false
  7. GPT_SOVITS_BACKEND_TIMEOUT=15
  8. (진단) AIRI_GROUNDING_MODE=off A/B

[이번 주 — T1, 이득/비용 비율 순]
  9.  kure-fp16 (1~2줄)                  ★ 비율 1위
 10.  L8 num_ctx/num_gpu SSoT + dialogue director num_ctx=1024 제거
 11.  KM-01 지식 O(N²) 제거
 12.  ARCH-08 self-echo 가드
 13.  STT-07 SSoT → STT-00 하네스 → STT-02 beam 1 → STT-04

[3~4주 — T2]
 14.  KM-03+KM-02+KM-04 묶음             (기억 기능 복구 + −250~380ms)
 15.  PX-06(a) proxy 분해                (충돌 방지 선행)
 16.  T-01 클라이언트 청크 재생          ★★ 가장 큰 한 방 (−580~1,350ms)
 17.  PX-02 prefix 안정화                (§6-3 결과가 크면 승격)
 18.  ARCH-03 → ARCH-01 → ARCH-04        (barge-in 묶음)

[분기 — T3, Wave B 실측 후 재결정]
 19.  L2 Mi:dm 2.0 Mini (MIT)            ← 라이선스 블로커 해소, 품질 손실 없음
 20.  STT-06 스트리밍 STT                ← P50 ≤2.0초를 문자 그대로 원할 때만
```

**절대 하지 말 것**: 계측(1~5) 없이 9번 이후로 건너뛰기 / kure-fp16 전에 num_ctx 상향·startup-order / KM-04 단독 머지 / ARCH-04 단독 적용 / uvicorn·JSON·TTS 스트리밍 파라미터 튜닝.
