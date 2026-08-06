# AIRI 저지연 계획 코드 실측 감사

- 실측일: 2026-08-06
- 목적: `AIRI-NEUROSAMA-LOW-LATENCY-PLAN.md`의 기술 가정을 실제 소스 코드로 검증
- 방법: 대상 레포 5종을 `external/`에 클론 후 읽기 전용 코드 분석 (병렬 에이전트 6개)

## 실측 대상

| 레포 | 경로 | 버전/커밋 |
|---|---|---|
| AIRI | `external/airi` | **v0.11.3 태그** (설치본과 동일) |
| GPT-SoVITS | `external/GPT-SoVITS` | main `d523079` (2026-07-22) |
| MOSS-TTS-Nano | `external/MOSS-TTS-Nano` | main `cc7bdf1` |
| Chatterbox | `external/chatterbox` | main `5de7a54` |
| RVC-WebUI | `external/RVC-WebUI` | main `81eed5e` |

---

## 1. AIRI v0.11.3 실측 — 계획서의 전제가 크게 바뀜

### 1-1. 이미 존재하는 것 (계획서가 "신규 구현"으로 잡았던 것)

**문장 분리 TTS 큐 — 완비** (`packages/pipelines-audio/`)
- `tts-chunker.ts`: hard(`.。?！…` 등)/soft(`,、:` 등) 구두점 기반 grapheme 스캐너. 기본 `boost=2, minimumWords=4, maximumWords=12` — **첫 2개 청크는 soft 구두점에서도 조기 방출**(첫 오디오 지연 최적화가 이미 설계에 있음).
- `speech-pipeline.ts`: TTS **4병렬 합성**(`ttsMaxConcurrent=4`) + sequence 리오더 버퍼 + timeline 직렬 재생.
- → 계획서 **Phase 4(첫 구절 분리기)는 신규 구현이 아니라 파라미터 튜닝**.

**취소/중단 — TTS·재생은 완비** 
- intent별 `AbortController`, `cancelIntent`/`interrupt`/`stopAll`, 재생 항목별 abort (`playback-manager.ts`).
- 새 메시지 작성 시 자동 `stopAll('new-message')` (`Stage.vue:768-778`).
- → 계획서 **Phase 2의 클라이언트 측 절반은 이미 존재**.

**계측 — OpenTelemetry 풀 트레이싱 존재** (`stage-shared/src/perf/io-trace.ts`)
- 스팬: InteractionTurn / SpeechRecognition / LLMInference / TTSSynthesis / AudioPlayback.
- `LLM_TTFT` 속성 + FirstToken 이벤트 실측 배선(`stores/chat.ts:113-140`), `turnId/intentId/streamId/segmentId/sequence` 전 페이로드 관통.
- → 계획서 **Phase 0은 신규 구축이 아니라 "기존 OTel 활용 + TTFA 스팬 추가"**.

**Live2D 립싱크 — 스트리밍 호환 구조**
- wlipsync AudioWorklet이 실시간 오디오 그래프를 128프레임 단위 소비(AEIOUS vowel weight). 전체 버퍼 전제 아님 → 재생 소스를 스트리밍으로 교체해도 립싱크는 무변경 동작 가능(추정, 실험 필요).

**부분 전사 아키텍처 — 이미 존재하나 미배선**
- `transcribeForMediaStream`(`hearing.ts:787-1114`): PCM16 청크 ReadableStream + WebSocket 스트리밍 전사 경로 존재. 단 `aliyun-nls`/`browser-web-speech` 2개 provider만 배선.
- OpenAI-compatible provider는 `supportsStreamInput/Output: false` → 전체 blob 업로드만.
- → 계획서 **Phase 3은 "신규 프로토콜 설계"가 아니라 "기존 스트리밍 전사 경로에 로컬 STT provider 추가"가 정석 경로**.

### 1-2. 확정된 갭 (진짜 신규 작업)

1. **TTS 청크 스트리밍 없음**: `generateSpeech()`가 전체 ArrayBuffer 수신 → `decodeAudioData` → `AudioBufferSourceNode.start(0)` (`Stage.vue:476-487, 318`). `streamSpeech`는 의존성에 없음. 문장 단위 병렬화는 있으나 **문장 내부 TTFA는 서버 생성 완료에 종속**. 청크 스트리밍하려면 `SpeechPipelineOptions`의 `tts()` 계약(`Promise<AudioBuffer>` 단일 반환) 변경 필요 — 중규모 개조.
2. **LLM HTTP 중단 미배선**: 취소는 세대(generation) 비교로 **결과만 무시**, HTTP는 계속 흐름. `abortSignal` 배관은 준비되어 있으나(`llm-service.ts:231-233`) 호출부(`chat-orchestrator-runtime.ts:703`)가 미주입 — **1개소 주입으로 해결 가능한 소규모 작업**.
3. **Barge-in은 아키텍처 블로커**: 업스트림은 barge-in이 없을 뿐 아니라 **정반대 구조** — TTS 재생 중 마이크 청취를 중단하는 half-duplex 억제(`voice-input-suppression.ts`: assistantSpeaking 동안 + 종료 후 800ms 억제). barge-in을 하려면 이 suppression 구조 해체가 선행되어야 하며, 그 순간 에코 문제(자기 TTS를 자기가 듣는 self-interrupt)가 노출됨. AEC는 하드코딩 `true`(`audio-device.ts:62-75`, 토글 없음) — 로컬 패치본은 이를 꺼둔 상태라 더 취약.

### 1-3. 스펙 문서와 업스트림 코드의 불일치 (로컬 패치 실체 확인 필요)

| 스펙 문서 기술 | 업스트림 v0.11.3 실측 | 해석 |
|---|---|---|
| "네이티브 MediaRecorder(Opus/WebM) 사용" | 프로덕션 경로는 **mediabunny WAV/pcm-s16**. MediaRecorder 코드는 존재하나 **참조 0건인 dead code** | 로컬 패치가 dead code를 살렸거나 별도 구현 — app.asar 실체 확인 필요 |
| "VAD 기본값 threshold 0.3, 무음 400ms, padding 80ms" | 런타임 실효값은 **0.52 / 1200ms / 360ms** (`stores/ai/models/vad.ts:22-25`). 0.3/400/80은 워커 내부의 **미사용 기본값**(`workers/vad/vad.ts:26-35`) | 로컬 패치가 dormant 값을 활성화했을 가능성 |
| "STT 결과 버퍼 1.2초 → 0.4초 패치" | 업스트림에서 1.2초 상수는 **VAD `MIN_SILENCE_DURATION_MS=1200`뿐**. 별도 "STT 결과 버퍼"는 미발견 (`autoSendDelay=2000ms`는 기본 비활성 레거시 경로) | "버퍼 1.2s"의 정체는 사실상 VAD 무음 판정일 가능성 — 계획서 4장의 "VAD 0.4s + 버퍼 0.4s" 이중 계상 여부 재검토 필요 |
| "에코 제거·노이즈 억제·자동 게인 비활성화" | 업스트림은 셋 다 하드코딩 `true` | 로컬 패치로 끈 것 — barge-in 도입 시 재검토 필수 |

**미해결**: 스펙에 기재된 `stt/openai_stt_server.py`, `chatterbox/openai_server.py`가 `C:\Projects\airi`에 없음. 실행 중인 로컬 서버 코드와 패치된 `app.asar`의 실제 위치 확인 필요.

---

## 2. TTS 후보 실측

### 2-1. Chatterbox (현행) — "구조가 병목" 가설 확정

- `generate()` = ① T3 autoregressive(30-layer Llama_520M, **토큰당 1 forward 순차 루프**) → ② S3Gen/CFM(스텝당 전체 시퀀스 병렬, 6~10스텝 저비용). CFM steps 감소가 0.2초만 개선된 것과 정합 — **8초의 지배 비용은 T3 루프**.
- 스트리밍 API 없음(`S3GenStreamer`는 정의 없는 죽은 참조). torch.compile 미적용(팀이 고려 후 비활성화한 흔적). conditionals 캐싱은 호출 측 책임(`audio_prompt_path` 생략 시 재사용).
- 업스트림 multilingual은 `cfg_weight=0`이어도 **무조건 batch=2**(이중 계산) — 로컬 패치("이중 T3 배치 제거")가 이 갭을 메운 것으로 교차 확인.
- ChatterboxNano/Turbo: 저지연 방향성(소형 백본+무CFG+2-step meanflow)은 옳으나 **영어 전용**.
- **판정: 유지하며 TTFA 1초 미만 불가. 교체 결정 타당.**

### 2-2. GPT-SoVITS — 후보 A(v2ProPlus) 코드로 정당화

- **v2ProPlus가 유일한 저지연 선택지**: v3/v4는 flow-matching+외부 보코더(BigVGAN 등) 구조로 **프레임 스트리밍 미지원 — 문장 단위로 자동 강등**(`TTS.py:1067-1078`). v2ProPlus는 경량 VITS 직결 디코더 + 화자 유사도 개선. 스펙 문서의 "V4 비교" 언급은 저지연 관점에서 폐기해야 함.
- 진짜 스트리밍: `api_v2.py` `streaming_mode=2` → semantic token **16개(hz=50, ≈0.32초 분량) 생성 시점부터 첫 청크** 디코딩. `min_chunk_length`/`overlap_length`/`fixed_length_chunk`로 TTFA-품질 트레이드오프 조절.
- RTF 참고치(README): 4060Ti 0.028, M4 CPU 0.526. 3060 Ti 직접 수치 없음 — 실측 필요.
- 한국어: `ko`/`all_ko` 지원, g2pk2+jamo 프런트엔드. 리스크: ① 한국어는 BERT 문맥 특징 미사용(zero placeholder — 운율 단순화 가능성), ② 라틴 문자는 글자 단위 음차("AI"→"에이아이"), ③ **Windows에서 mecab(`eunjeon`) 의존성이 requirements에 없음 — 설치 검증 필수**.
- **취소 API 갭**: 엔진에 `stop()` 존재하나 **HTTP 미노출**(WebUI 버튼만 배선) — barge-in용 `/stop` 커스텀 엔드포인트 추가 필요.
- 참조 캐시: 단일 슬롯(동일 경로 재사용 시 무료) — 다중 캐릭터/감정별 레퍼런스 전환 시 매번 재추출 → Phase 6 감정 구현 시 다중 슬롯 캐시 확장 필요.
- fp16 자동(3060 Ti = sm 8.6). Windows 통합 패키지 + `install.ps1` 제공.

### 2-3. MOSS-TTS-Nano — 후보 B 약화, 실측 게이트 필수

- 실재 확인: OpenMOSS 공식, 0.1B + 20M 토크나이저, 48kHz, Apache-2.0(코드 기준; 모델 카드 별도 확인 필요).
- ONNX CPU 런타임·프레임 스트리밍·TTFA 계측(`first_audio_latency_seconds`)·제로샷 클로닝 모두 실제 구현 확인.
- **한국어 결함 확인**: 언어 표에 `ko`는 있으나 **텍스트 정규화 언어 판별이 한글 미인식 → 중국어 정규화기 기본 적용**(`text_normalization_pipeline.py:131-138`). 한국어 데모/샘플 0건. 사용 시 `--disable-wetext-processing` 우회 검증 필요.
- CPU 실시간 주장의 정량 근거 없음(M4 정성 사례뿐, x86 수치 전무). Windows pip 설치 마찰(pynini) 문서화됨. OpenAI 호환 서버는 이 레포가 아닌 외부(vLLM-Omni).
- **판정: 후보 B는 "Ryzen 실측 RTF + 한국어 TN 우회 검증" 게이트 통과 시에만 유효.**

### 2-4. RVC — 조건부 가능, 우선순위 유지(최후 수단)

- 서버형 청크 호출 가능: `infer/rtrvc.py::RVC` 코어 + `RVCRealtimeVST/worker` 참조 구현(공유메모리 IPC). CUDA Graph opt-in(`RVC_CUDA_GRAPH=1`).
- 지연 요소: README의 90~170ms end-to-end 주장은 **GPU 단독 점유 + ASIO 조건**. 매 청크마다 컨텍스트 전체(기본 2~2.5초)를 HuBERT 재추론하는 구조라 **LLM·TTS와 GPU 공유 시 경합 리스크 큼**.
- 캐릭터 학습: 10~50분 데이터 권장(1분 미만 비권장) — 캐릭터 음성 데이터 확보 계획 필요.
- **판정: 계획서의 "조건부 추가" 유지가 옳음. 3060 Ti 동시 구동 실측 전 채택 금지.**

---

## 3. 계획서 Phase별 영향 요약

| Phase | 계획서 정의 | 실측 후 재정의 |
|---|---|---|
| 0 계측 | 신규 구축 | **축소**: 기존 OTel io-trace 활용 + TTFA 스팬 추가 + 로컬 서버 로그와 turnId 연결 |
| 1 TTS 교체 | 4후보 비교 | **후보 서열 확정**: GPT-SoVITS v2ProPlus(스트리밍 실증) > MOSS(게이트 통과 시) > RVC(최후). Chatterbox 유지 시나리오 폐기 |
| 2 큐/취소 | 신규 구현 | **축소+재편**: 클라이언트 취소는 기존 intent/playback 활용. 신규는 ① LLM abort 주입(1개소) ② GPT-SoVITS `/stop` 엔드포인트 ③ half-duplex 억제 해체+에코 대책(신규 HIGH) |
| 3 부분 STT | 신규 프로토콜 | **경로 변경**: `transcribeForMediaStream` 스트리밍 전사 경로에 로컬 faster-whisper provider 배선 (WebSocket PCM16 청크 구조 기존재) |
| 4 첫 구절 | 신규 분리기 | **축소**: tts-chunker 파라미터 튜닝. 단 **구두점에서만 분할**하므로 LLM 프롬프트에 구두점 사용 유도 필수(구두점 없는 긴 문장 = 스트림 종료까지 버퍼링 함정 확인됨) |
| 5 자원 | 실험 | 유지. GPT-SoVITS fp16 자동, RVC CUDA Graph 등 실험 축 추가 |
| 6 감정 | 감정별 레퍼런스 | 유지 + GPT-SoVITS 단일 슬롯 캐시 → 감정별 전환 비용 대책(다중 슬롯) 추가 |

**신규 최우선 과제(계획서에 없던 것)**: 설치본 app.asar 패치 방식 → **소스 빌드 전환**. v0.11.3 소스가 확보됐고, 로컬 패치 3종(MediaRecorder·VAD값·AEC off)이 업스트림 dead code/dormant 값과 얽혀 있어 패치 유지보수가 취약함. TTS 스트리밍 계약 변경·suppression 해체 같은 중규모 개조는 app.asar 패치로 지속 불가능.

## 4. 남은 확인 필요 항목

1. 로컬 STT/TTS 서버 코드와 패치된 app.asar의 실제 경로 (스펙 기재 위치에 없음)
2. 로컬 app.asar 패치의 실체 (스펙 기술과 업스트림 코드 불일치 3건 — §1-3)
3. GPT-SoVITS v2ProPlus 3060 Ti 실측 (TTFA, LLM 동시 구동, VRAM)
4. GPT-SoVITS Windows 한국어 G2P 설치 검증 (`eunjeon`/mecab)
5. MOSS-TTS-Nano Ryzen 5600X 실측 RTF + 한국어 TN 우회 후 품질
6. chatterbox pip 0.1.7 wheel과 main 브랜치 코드 차이 (`import chatterbox.tts_turbo` 가능 여부)

## 5. 후속 설치 시도 기록 (2026-08-06)

- 공식 GPT-SoVITS 저장소 `RVC-Boss/GPT-SoVITS`를 커밋 `d523079`로 별도 `external/`에 확보했다.
- v2ProPlus API 코드에서 `streaming_mode=2`, `min_chunk_length=16` 및 한국어 프런트엔드(`ko_pron`, `g2pk2`) 경로를 재확인했다.
- Windows Python 3.11 별도 환경에서 CUDA PyTorch 설치를 시도했으나 120초 제한 내 완료되지 않았다. 기존 Chatterbox CUDA PyTorch를 `PYTHONPATH`로 재사용하는 우회는 `torch 2.6.0+cu124`, CUDA 사용 가능 상태까지 확인했다.
- GPT-SoVITS 전체 requirements 설치는 `pyopenjtalk`가 Windows에서 CMake/NMake와 MSVC를 요구해 중단됐다. 한국어 전용 경로는 `pyopenjtalk`가 직접 필요하지 않지만, 나머지 의존성 및 모델 가중치 설치 후 별도 검증이 필요하다.
- 추가 확인 결과 `pyopenjtalk-prebuilt==0.3.0`의 CPython 3.11 Windows 휠은 설치·import 가능했다. 그러나 한국어 모듈 import 시 `g2pk2`가 `eunjeon`을 실제 호출하고, `eunjeon`은 동일하게 Windows MSVC 확장을 요구해 한국어 G2P는 아직 실행되지 않는다. `jieba_fast`는 순수 Python `jieba` 호환 shim으로 대체 가능하지만 성능 저하가 있다.
- 우회 검증 완료: `python-mecab-ko==1.2.9` + `python-mecab-ko-dic` Windows 휠을 설치하고 `gpt-sovits/setup-windows-korean-g2p.ps1`로 `eunjeon.Mecab -> mecab.MeCab` 호환 어댑터를 주입했다. `안녕하세요. 아이리입니다.`가 자모열로 변환되는 것까지 성공했다. 이는 한국어 G2P 블로커를 제거하지만, 전체 GPT-SoVITS 의존성·가중치 설치와 음질/TTFA 검증은 남아 있다.
- 따라서 3060 Ti TTFA/VRAM 실측은 아직 미완료이며, 설치 장애를 해결한 뒤에만 채택 판정을 진행한다. 외부 클론과 별도 가상환경은 프로젝트 Git에 포함하지 않는다.
