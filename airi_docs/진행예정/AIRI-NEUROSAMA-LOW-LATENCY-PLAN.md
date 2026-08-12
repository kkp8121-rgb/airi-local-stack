# AIRI 저지연 한국어 AI 버튜버 개발 계획 (v2.1)

- 작성 기준일: 2026-08-06 (v2 코드 실측 반영 → v2.1 후보 D·기억 계층 추가)
- 프로젝트 위치: `C:\Projects\airi`
- 기반 문서: `AIRI-LOCAL-TECH-SPECS.md`, `AIRI-CODE-AUDIT-2026-08-06.md`(AIRI 본체 실측), **`AIRI-RAG-REPOS-AUDIT-2026-08-06.md`**(RAG 레포 3종 실측 — 기억 계층 설계 결정표 §4)
- 이전 판: `archive/AIRI-NEUROSAMA-LOW-LATENCY-PLAN-v1-2026-08-06.md`, `archive/AIRI-NEUROSAMA-LOW-LATENCY-PLAN-v2-2026-08-06.md`
- 목표 플랫폼: Windows 단일 PC (Ryzen 5 5600X / RTX 3060 Ti 8GB)
- 기준 애플리케이션: AIRI 0.11.3 (소스: `external/airi`, v0.11.3 태그 = 설치본 동일)

## v1 → v2 개정 요지

코드 실측 감사로 계획의 전제가 다음과 같이 바뀌었다.

| # | v1의 전제 | 실측 결과 | 계획 반영 |
|---|---|---|---|
| 1 | 계측 체계를 신규 구축한다 | AIRI에 OpenTelemetry 풀 트레이싱 존재 (LLM TTFT 스팬, turnId/intentId/segmentId 관통) | Phase 0 축소: 기존 OTel 활용 + TTFA 스팬 추가 |
| 2 | TTS 큐·취소를 신규 구현한다 | 문장 분리 큐(4병렬 합성·순서 보장)와 intent 취소·재생 중단 완비 | Phase 2 축소: LLM abort 주입 1개소 + 서버측 취소만 신규 |
| 3 | LLM 첫 구절 분리기를 신규 구현한다 | tts-chunker가 이미 존재 (첫 2청크 soft 구두점 조기 방출) | Phase 4 축소: 파라미터 튜닝 + 프롬프트 구두점 유도 |
| 4 | 부분 STT는 프로토콜부터 설계한다 | PCM16 청크 WebSocket 스트리밍 전사 경로 기존재 (미배선) | Phase 3 경로 변경: 기존 경로에 로컬 provider 배선 |
| 5 | (미인지) | **TTS 청크 스트리밍 없음** — 클라이언트는 문장 전체 오디오 수신 후 재생 | Phase 5 신설 (조건부 — Phase 1 실측 후 결정) |
| 6 | (미인지) | **Barge-in은 블로커** — 재생 중 마이크를 끄는 half-duplex 구조 + AEC 하드코딩 | Phase 6에 suppression 해체 + 에코 대책 명시 |
| 7 | (미인지) | app.asar 패치는 업스트림 dead code/dormant 값과 얽혀 유지보수 불가 | Phase 0에 **소스 빌드 전환** 신설 (최우선) |
| 8 | GPT-SoVITS 후보 (스펙 문서는 V4 언급) | **v2ProPlus만 프레임 스트리밍** (v3/v4는 문장 단위 강등) | v2ProPlus 확정, V4 폐기 |
| 9 | MOSS-TTS-Nano 후보 B | 한국어 TN 결함(중국어 정규화기 폴백) + x86 수치 전무 | 게이트 조건부로 강등 |
| 10 | Chatterbox 8초는 "구조 문제"로 추정 | T3 autoregressive 루프가 병목임을 코드로 확정, 스트리밍 API 없음 | 교체 확정 (유지 시나리오 폐기) |
| 11 | 지연 예산 구간 합 ≠ 종단 목표 (3.7>3.0, 1.35>1.2) | 측정 앵커 미정의로 이중 계상 (1.2초 상수는 VAD 무음 판정일 가능성) | §6 예산 재배분 + 앵커 정의 |

## v2 → v2.1 개정 요지 (후보 D — 기억 계층 + 클라우드 LLM)

배경: ① AIRI 본체에 동작하는 기억 시스템이 없고 매 턴 전체 히스토리를 무절삭 전송함이 확인됨(본체 감사 §1). ② 사용자 자체 RAG 레포 3종(talkain-api·rag_rnd·rag_cache) 실측으로 기억 계층 설계의 대부분이 실전 검증된 답을 확보함(RAG 감사 §4 결정표). ③ LLM을 클라우드 API로 옮기면 8GB GPU를 STT/TTS에 전유시켜 STT를 GPU화할 수 있음.

반영 사항: **후보 D 신설**(§11), **병렬 트랙 M 신설**(§8 — 음성 파이프라인과 독립 진행), §6 예산 변형, §10 후보 D 채택 게이트, §12 완료 기준의 127.0.0.1 조항 개정, Phase 3에 GPU STT 우선 실험 추가.

> **실행 환경 주의**: 본 계획의 실제 실행은 이 PC가 아닌 별도 PC(GPT 세션)에서 진행된다. 그 환경에는 `external/` 클론 레포가 없으므로, 트랙 M에 필요한 코드 자산은 **`AIRI-MEMORY-TECH-REFERENCE.md`**(클론에서 추출한 프롬프트 원문·공식·알고리즘)에 자기완결적으로 수록했다. 이관 문서 세트(6종): 본 계획서 + 감사 2종 + 기술 레퍼런스 + 스펙 문서 + `rtk-setup-guide.md`(토큰 절감 도구 설치 — 현재 `C:\Users\ovencode\Documents\`에 위치, 계측 명령 보호 §4 포함).

---

## 1. 프로젝트 목표

게임 플레이 기능을 제외하고, 뉴로사마처럼 **빠르게 받아치는 체감**을 가진 한국어 로컬 AI 버튜버 대화 시스템을 구축한다.

```text
사용자가 마이크로 한국어 발화
→ AIRI가 발화 종료를 빠르게 감지
→ 음성을 한국어 텍스트로 변환
→ 캐릭터성 있는 짧은 답변 생성
→ 버튜버다운 한국어 음성으로 즉시 발화
→ 사용자가 끼어들면 기존 발화를 중단하고 새 입력 처리
```

핵심 지표는 두 가지다.

1. **사용자의 마지막 음절부터 AIRI의 첫 음절까지 걸리는 시간**
2. **사용자가 끼어든 시점부터 AIRI 음성이 멈출 때까지 걸리는 시간**

## 2. 범위

### 포함

- 한국어 음성 입력, VAD 발화 종료 감지, 한국어 STT (부분 전사 또는 GPU 일괄)
- 로컬 LLM 스트리밍, 버튜버풍 한국어 TTS, TTS 취소·큐 정리
- 사용자 끼어들기(barge-in) + **에코 대책** (v2 추가 — barge-in의 전제 조건)
- **AIRI 소스 빌드 전환** (v2 추가 — app.asar 패치 대체)
- **로컬 기억 계층** — vector RAG + 확신도 엣지 관계 테이블, 메모리 프록시 (v2.1 추가)
- **클라우드 LLM 옵션(후보 D)** — 게이트 통과 시 로컬 LLM 대체, GPU를 음성에 전유 (v2.1 추가)
- Live2D 립싱크, 캐릭터 성격·말투 유지, 단계별 지연 계측, 단일 PC 자원 배분

### 제외

- 게임 플레이·화면 인식·게임 SDK, VRChat·외부 장치 제어, 복잡한 비전 모델
- 멀티 에이전트 대화, 대규모 방송 인프라, 초기 단계의 고급 OBS 연출

## 3. 현재 시스템 기준선 (실측 반영)

### 파이프라인과 하드웨어

v1과 동일 (스펙 문서 참조): 마이크 → VAD → faster-whisper small(CPU INT8) → Ollama/EXAONE 2.4b(Q4, num_gpu=20) → Chatterbox(GPU) → Web Audio/Live2D. RTX 3060 Ti 8GB, Ryzen 5 5600X.

### AIRI v0.11.3 내부 구현 현황 (코드 실측 — 감사 문서 §1)

| 구성요소 | 상태 | 위치 (external/airi 기준) |
|---|---|---|
| 문장 분리 TTS 큐 | ✅ 완비 — boost=2/min4/max12 words, 4병렬 합성, 순서 보장 | `packages/pipelines-audio/src/processors/tts-chunker.ts`, `speech-pipeline.ts` |
| TTS·재생 취소 | ✅ 완비 — intent별 AbortController, 새 메시지 시 자동 stopAll | `packages/pipelines-audio/src/managers/playback-manager.ts`, `Stage.vue:768-778` |
| 계측 (OTel) | ✅ 완비 — LLM TTFT, TTS 합성/재생 스팬, ID 관통 | `packages/stage-shared/src/perf/io-trace.ts`, `stores/chat.ts:113-140` |
| 스트리밍 전사 경로 | ⚠️ 존재하나 미배선 — aliyun/web-speech만 사용 | `stores/modules/hearing.ts:787-1114` |
| Live2D 립싱크 | ✅ 스트리밍 호환 — AudioWorklet 실시간 그래프 | `packages/model-driver-lipsync/src/live2d/index.ts` |
| TTS 청크 스트리밍 | ❌ 없음 — 문장 전체 ArrayBuffer 수신 후 재생 | `Stage.vue:476-487` (`generateSpeech`) |
| LLM HTTP 중단 | ❌ 미배선 — 세대 비교로 결과만 무시 | `packages/core-agent/src/runtime/chat-orchestrator-runtime.ts:703` |
| Barge-in | ❌ 정반대 — 재생 중 마이크 차단(half-duplex, +800ms 꼬리) | `apps/stage-tamagotchi/src/renderer/utils/voice-input-suppression.ts` |
| AEC/NS/AGC | 하드코딩 `true` (토글 없음) | `packages/stage-ui/src/composables/audio/audio-device.ts:62-75` |

### 로컬 패치 3종 — 실체 확인 필요 (블로킹)

스펙 문서의 기술과 업스트림 코드가 3건 불일치한다 (감사 §1-3): MediaRecorder 녹음(업스트림은 mediabunny WAV, MediaRecorder는 dead code), VAD 0.3/400/80(업스트림 실효값은 0.52/1200/360, 스펙 값은 dormant 내부 기본값과 일치), "STT 버퍼 1.2→0.4초"(업스트림의 1.2초 상수는 VAD 무음 판정뿐). **로컬 서버 코드(`stt/openai_stt_server.py`, `chatterbox/openai_server.py`)와 패치된 app.asar의 실제 경로 확인이 선행되어야 한다.**

## 4. 현재 성능과 병목

실측값은 v1과 동일: STT small beam1 3.0~3.5초, TTS 21자 약 8초(큐 적체 시 17~40초), LLM 미측정.

병목의 원인은 이제 코드로 확정됐다.

1. **Chatterbox TTS 8초** = T3 autoregressive 루프(30-layer, 토큰당 1 forward) 구조 병목. 파라미터 튜닝으로 해결 불가, 스트리밍 API 없음 → **엔진 교체 확정**
2. **STT 3초대** = 발화 종료 후 전체 blob 일괄 업로드 구조 (부분 전사 미배선)
3. **GPU 경쟁** = LLM(num_gpu=20)과 TTS의 8GB VRAM 공유
4. **TTS 직렬 큐 적체** = 서버측 취소 부재 (클라이언트 취소는 존재)
5. **VAD/버퍼 지연** = 실효 상수의 실체 확인 필요 (§3 로컬 패치)
6. LLM 첫 토큰/첫 구절 지연 = 미측정 — **기존 OTel TTFT 스팬으로 즉시 측정 가능**

## 5. 뉴로사마와의 비교에서 가져올 요소

v1과 동일하되, 참고 요소 중 **"첫 구절 우선 처리·재생과 다음 합성의 병렬 처리·이전 발화 취소"는 AIRI에 이미 구현되어 있음**이 확인됐다. 남은 차별 요소는 ① 빠른 턴 전환(STT·TTS 저지연화), ② 끼어들기 즉시 중단(half-duplex 해체), ③ 캐릭터성 있는 짧은 답변(프롬프트)이다.

> 뉴로사마급 목표 = 동일 장비 복제가 아니라, 사용자가 말을 마친 뒤 **1~2초대에 자연스러운 첫 반응이 나오는 체감**의 구현.

## 6. 목표 지연 예산 (v2 — 앵커 정의 + 산술 정합)

### 측정 앵커 (Phase 0에서 이 정의대로 계측)

| 구간 | 시작 앵커 → 끝 앵커 |
|---|---|
| 발화 종료 감지 | 물리적 발화 끝(T0) → `vad_speech_end` 이벤트 |
| STT 확정 | `vad_speech_end` → `stt_final` |
| LLM 첫 구절 | `stt_final` → `llm_first_clause` (tts-chunker 첫 emit) |
| TTS 첫 오디오 | `llm_first_clause` → `audio_play_start` (재생 버퍼 포함) |
| 종단 | T0 → `audio_play_start` = 위 4구간의 합 |

각 구간은 연속·비중첩으로 정의한다 (이중 계상 금지). v1의 "AIRI STT 버퍼 0.4초"는 별도 항목에서 제거 — 실체가 VAD 무음 판정으로 확인되면 "발화 종료 감지"에 포함되는 값이다.

### 1차 목표 (구간 합 = 3.0초)

| 구간 | 1차 목표 |
|---|---:|
| 발화 종료 감지 | 400ms |
| STT 확정 | 1,200ms |
| LLM 첫 구절 | 600ms |
| TTS 첫 오디오 | 800ms |
| **종단 (T0 → 첫 음절)** | **3.0초 이하** |
| 끼어들기 → 음성 중단 | 500ms 이하 |

### 최종 목표 (구간 합 극단값 = 1.15~2.05초, 운용 목표는 그 안의 1.2~2.0초)

| 구간 | 최종 목표 |
|---|---:|
| 발화 종료 감지 | 200~300ms |
| STT 확정 (부분 전사 후 잔여 확정) | 300~500ms |
| LLM 첫 구절 | 300~500ms |
| TTS 첫 오디오 (재생 버퍼 50~150ms 포함) | 350~750ms |
| **종단 (T0 → 첫 음절)** | **1.2~2.0초** |
| 끼어들기 → 음성 중단 | 200~300ms |

### 후보 D 적용 시 예산 변형 (v2.1)

- **STT 확정**: LLM이 GPU에서 빠지면 faster-whisper를 CUDA로 이전 — 부분 전사 없이 **일괄 처리로도 P50 1초 미만** 기대(실측 필요). 1차 목표의 STT 1,200ms를 큰 폭 하회할 가능성.
- **LLM 첫 구절**: "기억 검색(≤150ms) + 네트워크 왕복 + 클라우드 TTFT + 첫 구절 생성"으로 재정의. Haiku급 스트리밍 실측 필요 — 로컬(300~600ms)보다 늘어날 수 있음.
- **종단 목표는 동일 유지** — STT 단축분이 LLM 증가분을 상쇄하는지가 §10 후보 D 게이트의 핵심 판정이다. 기억 검색은 LLM 첫 구절 예산 내 포함 항목으로 계측한다(`memory_retrieve_start/end` 타임스탬프 추가).

## 7. 목표 아키텍처

`[기존]` = AIRI에 이미 있음(활용), `[개조]` = 기존 코드 수정, `[신규]` = 새로 구현.

```text
마이크 입력
  ├─ Silero VAD [기존 — 파라미터 튜닝 [개조]]
  ├─ 부분 STT [개조 — 기존 스트리밍 전사 경로에 로컬 faster-whisper provider 배선]
  │    ├─ 발화 중 PCM16 청크 전송 + 임시 전사
  │    └─ 발화 종료 시 잔여 구간만 확정
  ├─ LLM 스트리밍 [기존]
  │    └─ tts-chunker 첫 구절 분리 [기존 — 파라미터 튜닝 [개조]]
  ├─ TTS: GPT-SoVITS v2ProPlus 서버 [신규 — streaming_mode=2]
  │    ├─ 문장 단위 병렬 합성 + 순서 보장 재생 [기존]
  │    └─ (조건부) 문장 내부 청크 스트리밍 재생 [신규 — Phase 5]
  └─ Web Audio 재생 + Live2D 립싱크 [기존 — 스트리밍 호환 확인됨]

끼어들기 경로 [개조+신규]
  사용자 새 발화 감지 (재생 중 마이크 유지 — half-duplex 억제 해체 [개조])
  → 재생 중단 + TTS 큐 정리 [기존 stopAll/interrupt]
  → 진행 중 서버 합성 취소 [신규 — GPT-SoVITS /stop]
  → LLM HTTP 중단 [개조 — abortSignal 주입 1개소]
  → 에코로 인한 자기 트리거 방지 [신규 — AEC 재활성화/게이팅]
```

## 8. 단계별 개발 계획

### Phase 0. 기반 구축 — 소스 빌드 전환 + 계측 완결

v2 신설 최우선 Phase. 이후 모든 클라이언트 개조(Phase 3·5·6)의 전제 조건.

작업:

1. **로컬 패치 실체 확인** — 실행 중인 서버 코드·패치된 app.asar 경로 확보, 패치 diff 추출 (블로킹: 사용자 확인 필요)
2. `external/airi` v0.11.3 **소스 빌드 재현** (pnpm 모노레포, stage-tamagotchi Electron 빌드) → 설치본과 동작 동등성 확인
3. 로컬 패치 3종(녹음 경로·VAD 값·AEC off)을 **소스 레벨로 이식** — 업스트림 dead code(`useAudioRecord`)/dormant 값과의 관계를 정리하며 이식
4. 계측 완결: 기존 OTel io-trace에 **TTFA 스팬**(`llm_first_clause` → `audio_play_start`) 추가, 로컬 STT/TTS 서버 로그의 request_id를 OTel `turnId`와 연결
5. 기준선 측정: LLM TTFT(기존 스팬으로 즉시), 구간별 P50/P90/P95 첫 실측

완료 조건:

- 소스 빌드 앱이 현재 설치본과 동일하게 동작 (STT·TTS·립싱크 회귀 없음)
- §6 앵커 정의 그대로 5개 구간이 하나의 타임라인으로 기록됨
- LLM 구간 실측값 확보 (v1의 "미측정" 해소)

### Phase 1. TTS 엔진 교체 — GPT-SoVITS v2ProPlus 최우선

후보 서열 (감사 §2로 확정):

```text
1. GPT-SoVITS v2ProPlus 제로샷 GPU  ← 최우선 (유일한 프레임 스트리밍 실증 후보)
2. GPT-SoVITS v2ProPlus 파인튜닝    ← 제로샷 음색 불만족 시
3. MOSS-TTS-Nano ONNX CPU           ← 게이트 통과 시만 (아래)
4. 한국어 TTS → RVC                 ← 최후 수단 (§10)
```

Chatterbox 유지 시나리오는 폐기한다 (T3 구조 병목 + 스트리밍 API 부재 확정).

작업:

1. GPT-SoVITS 설치 (`install.ps1 -Device CU126`) + **한국어 G2P 동작 검증** (Windows에서 `eunjeon`/mecab 의존성이 requirements 누락 — 감사 §2-2)
2. `api_v2.py` 서버 기동 (포트 분리, 예: 9880) — v2ProPlus 가중치(`s2Gv2ProPlus.pth` + `s1v3.ckpt`)
3. `streaming_mode=2` + `min_chunk_length`(기본 16토큰≈0.32초 분량) 스윕 벤치마크 — §9 표준 문장 7종
4. 제로샷: 현행 참조 음성(`airi-reference.wav` 8.9초)으로 음색 비교 → 불만족 시 정제 음성 5~15분 파인튜닝
5. AIRI 연동: OpenAI Compatible 어댑터 (기존 `/v1/audio/speech` 계약 유지 — 로컬 어댑터 서버 또는 GPT-SoVITS 앞단 프록시)
6. LLM 동시 구동 상태 TTFA·VRAM 실측

채택 기준 (v1 유지):

- 첫 오디오 P50 800ms 이하, P95 1.5초 이하 (LLM 동시 구동 상태 포함)
- 20~40자 문장 실시간보다 빠른 생성 (참고 RTF: 4060Ti 0.028 — 3060 Ti 실측 필요)
- 한국어 발음·캐릭터성 Chatterbox 동등 이상 (라틴 문자 음차·BERT 미사용 운율 확인 — 감사 §2-2 리스크)

MOSS-TTS-Nano 게이트 (모두 통과 시만 후보 유지):

- 한국어 TN 우회(`--disable-wetext-processing`) 후 발음 품질 확인 (한글 미인식 → 중국어 정규화기 폴백 결함 확인됨)
- Ryzen 5600X 실측 RTF < 1 (x86 공개 수치 전무 — 직접 측정 외 근거 없음)
- Windows 설치 성공 (pynini 마찰 문서화됨)

### Phase 2. 취소 경로 완결

클라이언트 취소는 완비 — 남은 것은 3개소다.

작업:

1. **LLM HTTP 중단 배선**: `chat-orchestrator-runtime.ts:703`의 `streamText` 호출에 turn별 `AbortController.signal` 주입 (배관은 `llm-service.ts:231-233`에 준비됨)
2. **GPT-SoVITS 취소 노출**: 엔진 내부 `TTS.stop()`(존재 확인)을 `/stop` 커스텀 엔드포인트로 노출 + 클라이언트 disconnect 시 generator 종료
3. **서버측 최신 요청 우선**: 로컬 TTS 어댑터에 turn 세대 비교 → 이전 세대 미시작 요청 폐기 (클라이언트 `turnId`/`intentId` 헤더 전달)

완료 조건:

- 새 발화 시작 시 이전 LLM HTTP 연결이 실제로 끊김 (Ollama 로그 확인)
- 서버 큐에 이전 turn 요청이 남지 않음 — "10초 이상 늦은 응답 재생" 재현 불가
- 취소 전파 종단 시간(새 발화 → 서버 합성 중단) 500ms 이내

### Phase 3. STT 저지연화 (GPU 우선) + VAD 튜닝

v1의 "신규 프로토콜 설계"를 폐기하고 **기존 경로 배선**으로 변경한다. v2.1 추가: **실험 순서를 GPU 우선으로 재정의** — 후보 D 채택(또는 LLM GPU 레이어 축소)으로 VRAM 여유가 생기면, ① faster-whisper CUDA 이전(일괄 처리 유지, 서버 설정 변경만)을 먼저 실측하고, ② P50 1초 미만이 나오면 부분 전사(아래 1~3번)는 **조건부 항목으로 강등**한다. GPU 이전이 부분 전사보다 구현 비용이 훨씬 낮다.

작업:

1. AIRI `transcribeForMediaStream`(`hearing.ts:787-1114`, PCM16 청크 ReadableStream) 경로에 **로컬 faster-whisper용 스트리밍 provider 추가** — provider feature flag `supportsStreamInput/Output` 오버라이드 (`stores/providers.ts:819-856` 패턴 참조)
2. STT 서버에 WebSocket 수신 + 롤링 윈도우 부분 전사 구현 (500~1,000ms 간격, 이전 전사와 정렬, 발화 종료 시 잔여 구간만 재디코딩)
3. 한국어 hotword·저신뢰도/무음 필터 유지 (현행 서버 로직 이식)
4. VAD 파라미터 튜닝: 실효값 확인(§3) 후 무음 판정 400ms→200~300ms 실험 — **조기 종료 오검출률(말 끊김)을 별도 지표로 함께 계측**

완료 조건:

- STT 확정(speech_end→stt_final) P50 500ms 이하, P95 1초 이하 (부분 전사 잔여 확정 기준)
- 한국어 정확도 현행 `small` 일괄 처리 대비 허용 범위 내
- VAD 조기 종료 오검출이 벤치마크 대화에서 5% 이하

### Phase 4. LLM 첫 구절 튜닝

분리기는 기존 tts-chunker를 사용한다. 신규 구현 없음.

작업:

1. chunker 파라미터 오버라이드 실험 (`Stage.vue:364` 부근에서 `boost`/`minimumWords`/`maximumWords`/`ttsMaxConcurrent` 지정) — 첫 청크 emit까지의 토큰 수 최소화 vs 부자연스러운 끊김 트레이드오프
2. **시스템 프롬프트에 구두점 사용 유도** — chunker는 구두점에서만 분할하므로(코드 확인), 구두점 없는 긴 문장은 스트림 종료까지 버퍼링되는 함정이 있다. "짧은 첫 문장 + 문장부호 필수" 지시 포함
3. 응답 정책: 기본 1~3문장, 첫 문장 짧게, 서론 제거 (v1 유지)
4. LLM 첫 구절(stt_final→llm_first_clause) P50 실측 — 미달 시 Phase 7의 num_gpu 조정과 연계

완료 조건: LLM 첫 구절 P50 600ms 이하 (1차), 벤치 대화에서 "음," 단독 같은 파편 청크 미발생

### Phase 5. TTS 청크 스트리밍 재생 (조건부)

**Phase 1 실측 후 결정한다.** GPT-SoVITS가 빠르면 문장 단위 재생만으로 TTFA 목표를 충족할 수 있다 — 첫 문장이 짧으면(Phase 4) 문장 전체 생성 완료까지의 시간 자체가 작기 때문이다.

진입 조건: Phase 1+4 완료 후 "TTS 첫 오디오" 구간 P50 > 800ms일 때만 진행.

작업 (진입 시):

1. `speech-pipeline.ts`의 `tts()` 계약을 `Promise<AudioBuffer>` 단일 반환에서 청크 스트림 지원으로 확장
2. 재생을 `AudioBufferSourceNode` 단발에서 청크 큐잉 재생(AudioWorklet 또는 버퍼 이어붙이기)으로 교체 — `Stage.vue:255` `playFunction` 교체 지점
3. 립싱크 회귀 확인 (wlipsync는 실시간 그래프 소비라 구조상 호환 — 실험으로 검증)

### Phase 6. Barge-in + 에코 대책

v1의 "취소 배선"에서 **"half-duplex 구조 해체"로 재정의**한다. AIRI는 재생 중 마이크를 끄므로(suppression), 끼어들기는 기존 훅 추가가 아니라 구조 변경이다.

작업:

1. `voice-input-suppression.ts`의 `shouldSuppressVoiceInput` 해체 — 재생 중에도 VAD 유지
2. **에코 대책** (해체 순간 자기 TTS를 자기가 듣는 self-interrupt가 발생한다):
   - 1안: 재생 구간 한정 AEC 재활성화 (`audio-device.ts:62-75` constraints를 동적 토글로 개조 — 현행 로컬 패치는 상시 off)
   - 2안: 재생 중 VAD threshold 상향 + 자기 출력 구간 에너지 게이팅
   - 3안: 헤드폰 사용 전제 모드 (설정 토글)
   - 1안부터 실험, 실패 시 2·3안 조합
3. speech_start → 기존 `stopAll`/`interrupt` + Phase 2의 서버 취소 연결
4. 오검출 대책: 끼어들기 확정 조건(최소 발화 길이 300ms 등)으로 노이즈 트리거 방지

완료 조건:

- 스피커 재생 중 사용자 발화 → 200~500ms 내 음성 중단, self-interrupt 미발생
- 30분 대화에서 에코로 인한 의도치 않은 중단 0건

### Phase 7. 자원 경쟁 최적화

작업: v1 실험 항목 유지 (num_gpu 스윕, LLM CPU 비중, 모델 상시 로드, 참조 임베딩 캐시) + v2 추가:

- **VRAM 예산표 작성** (실측 기입): EXAONE Q4 num_gpu별 / GPT-SoVITS v2ProPlus fp16 / Electron·Live2D 렌더링 / 여유분 — 합계 8GB 이내 검증
- **CPU 코어 배분표**: STT(현행 6 threads) + LLM CPU 레이어 + (후보 B 시) MOSS TTS의 동시 실행 경합 측정 — 6코어 12스레드 내 배분
- GPT-SoVITS는 fp16 자동(sm 8.6) 확인됨 — 추가로 RVC 채택 시 `RVC_CUDA_GRAPH=1` 실험

결정 기준: 종단 첫 발화 P50/P95 (추측 금지, v1 유지)

### Phase 8. 캐릭터성과 감정

지연 목표 달성 후 진행 (v1 유지). v2 추가 사항:

- GPT-SoVITS **참조 캐시가 단일 슬롯**이므로 감정별 레퍼런스 전환 시 매번 재추출된다 — 감정 구현 전 **다중 슬롯 캐시 확장**(감정별 TTS 인스턴스 또는 캐시 레이어)을 선행
- 최소 감정 세트(neutral/happy/surprised/embarrassed/sad), Live2D 표정 동기화 (v1 유지)

### 병렬 트랙 M. 기억 계층 + 클라우드 LLM (v2.1 신설 — 후보 D의 전제)

음성 파이프라인 Phase(0~8)와 **독립적으로 병행 가능**하다 — 127.0.0.1 프록시 방식이라 AIRI 클라이언트 수정이 없고, 지금 쓰는 Ollama 프록시(11435)와 같은 자리에 꽂힌다. 설계 근거는 `AIRI-RAG-REPOS-AUDIT-2026-08-06.md` §4 결정표, 코드 자산 원문은 `AIRI-MEMORY-TECH-REFERENCE.md`.

**M0. 게이트 벤치 (셋 다 통과해야 M1 진행)**

1. **추출 품질**: 로컬 EXAONE 2.4b로 Stage A/B 추출(기술 레퍼런스 §1 프롬프트, JSON schema 강제) 실측 — 클라우드 mini급과 품질 비교. *주의: talkain·rag_rnd 모두 소형 모델 추출은 미검증 — 실패한 가정의 재검증이다.* 미달 시 추출만 클라우드 mini급 폴백(비실시간·배치라 저비용).
2. **임베딩**: KURE-v1 vs BGE-M3 한국어 대화 검색 정확도 + 지연 (RTX 3060 Ti, 목표 ≤80ms). API 임베딩 금지(200~400ms 실측 — 예산 초과).
3. **클라우드 TTFT**: Haiku급 스트리밍 첫 토큰 실측 (프록시 경유, 상주 프로세스+직접 API — CLI 경유는 TTFT 2s+ 실측으로 금지).

**M1. 프록시 MVP**

- 127.0.0.1 OpenAI-compatible 프록시 (상주 프로세스, Anthropic/OpenAI 직접 API 호출, 스트리밍 패스스루 + abort 전파)
- **워터마크 히스토리 절삭**: `extracted_up_to_msg` 이하 raw 턴 제거 → 메모리 블록 대체, 인트로 보존, 추출 지연 시 last-N cap으로 degrade (요약 LLM 0회)
- 프롬프트 조립: 정적 블록(가이드라인·페르소나) 선두 고정 + `cache_control`(prompt caching), 변동 블록(기억·최근 턴)은 뒤에
- fail-soft 3원칙: 임베딩 실패 행만 제외, 검색 실패 시 빈 블록, 파싱 실패 시 워터마크 미갱신→자연 재시도 — **기억이 발화를 절대 막지 않는다**
- 로컬 EXAONE 폴백 (클라우드 장애 시)

**M2. 기억 파이프라인**

- 저장: SQLite 단일 파일 — vector는 브루트포스 cosine(1만 행 미만, 실측 <1ms 근거) → 초과 시 sqlite-vec 전환. 그래프 DB 도입 금지(1-hop뿐이면 관계형 테이블로 충분 — talkain Neo4j 폐기 근거)
- 스키마: entity/fact(trait·moment·scene)/relation + **확신도 엣지**(KNOWS/HEARD_ABOUT/BELIEVES + 출처) + `superseded_by` 이력 보존
- 추출: Stage A(원자 분해)/Stage B(기존 후보 대조 → ADD/UPDATE/SUPERSEDE/NOOP, alias 조작) — 응답 완료 후 fire-and-forget, pending ≥3 트리거 + 세션 종료 force flush
- 검색(LLM 0회): RAG 게이트(잡담 스킵) → NameScanner(정적 인물명 스캔) → 임베딩 1회 → entity top-k + trait/moment SQL + scene vector(over-fetch 4x) + 1-hop 확장 → `0.7·cosine + 0.3·exp(-0.05·Δturn)` 재랭킹(canon은 decay 면제)
- canon-snapshot: 방송 세션 시작 시 페르소나 canon 복제(벡터째 — 재임베딩 0), 세션 학습이 원본 미오염
- 다층 캐시: 질문 임베딩·검색 결과·주제 키 컨텍스트 캐시 + 전역 off 스위치(비교 실측용)

**M3. 통합·전환 게이트**

- 후보 A(로컬 LLM) vs 후보 D 종단 실측 비교(§9 벤치 + §10 게이트) → 채택 결정
- 채택 시: Phase 3 GPU STT 확정, Phase 7 VRAM 예산표 재작성(LLM 제외), §12 개정 조항 발효
- (선택) 체감 지연 보강: 검색 중 대기 멘트 선스트리밍, `[N]`/`[C]` 태그 스트리밍 파서(TTS는 `[C]`만) — 기술 레퍼런스 §4·§5

완료 조건: 기억 검색 P50 150ms 이하 / M0 게이트 3종 통과 기록 / 30분 대화에서 기억 일관성 시나리오(과거 사실 교차 질문) 통과 / 프록시 다운 시에도 발화 지속(fail-soft 검증)

**M+. 지연 추가 최적화 (v2.1 — 반영분과 도입 후 R&D 구분)**

지금 반영 (구현 비용 낮음·효과 확실):

1. M1 요건 추가 — 프록시는 API 서버와 **keep-alive 커넥션 풀(HTTP/2) 상시 유지** (턴당 TLS 핸드셰이크 100~300ms 제거)
2. M1 요건 추가 — **캐시 워밍**: 연속 대화는 직전 턴이 캐시를 데워두므로(TTL 5분) 별도 조치 불요. 방송 시작 직후·5분+ 휴지 후에만 `max_tokens=0` 프리워밍 요청으로 첫 턴 prefill 선지불
3. M0 게이트 ③ 확장 — **리전 비교**: Bedrock 서울(ap-northeast-2)에 대상 모델 가용 여부 확인 필요 → 가용 시 "Anthropic 직접 vs Bedrock 서울" TTFT 비교 축 추가
4. M3 선택 항목 승격 — **로컬 반사 응답**: 고정 대기 멘트 대신 상주 EXAONE이 300ms 내 맥락 리액션(짧은 감탄·응수)을 먼저 발화하고 클라우드 본답변이 이어받는 2단 구조. 체감 첫 반응 1초 미만 고정이 목표

도입 후 R&D 백로그 (효과 크나 복잡도·리스크 높음 — 파이프라인 안정화 후):

- 투기적 실행: 부분 전사 시점에 LLM 선요청, 최종 전사 불일치 시 폐기 (STT+LLM 구간 중첩 — 폐기 호출 비용·오발화 처리 필요)
- 시맨틱 endpointing: 고정 무음 창 대신 운율·부분 전사 기반 턴 종료 예측 (오검출 트레이드오프 실측 필요)
- pre-bake 리액션 음성: 예측 가능한 감정 리액션을 유휴 시간에 선합성 → 0ms 재생 (Phase 8 감정 시스템과 연계)
- CrossEncoder 리랭킹: 기억 검색 정확도 부족 시에만 백그라운드 경로로 (실시간 부적합 — 0.8s+ 실측)

## 9. 표준 벤치마크

테스트 문장 7종 (v1 유지):

```text
안녕하세요. 오늘은 어떤 이야기를 해볼까요?
잠깐만요, 그건 제가 생각했던 것과 조금 다른데요.
정말요? 그건 꽤 재미있겠는데요!
아, 아니거든요! 제가 언제 그랬다고 그래요?
오늘도 같이 있어줘서 고마워요.
아이리, 지금 내 말 잘 들려?
RTX 3060 Ti의 메모리는 8기가바이트예요.
```

조건 (v1 + v2 추가):

- 동일 참조 음성·샘플레이트, 모델 사전 로드, 워밍업 분리, 문장당 10회, P50/P90/P95
- LLM 미실행/동시 실행 각각 측정
- **TTFA(첫 오디오)와 총 생성시간을 반드시 분리 기록** (Chatterbox는 스트리밍이 없어 TTFA=총시간이었음 — 비교 시 동일 기준 주의)
- 스트리밍 모드는 `min_chunk_length` 값별로 기록

## 10. 의사결정 기준

### TTS

```text
GPT-SoVITS v2ProPlus streaming_mode=2에서 TTFA P50 800ms 이하 + 한국어 만족
→ 채택 (기본 시나리오)

제로샷 음색 불만족
→ 5~15분 파인튜닝 → 재평가

GPU 경쟁으로 지연 심함
→ Phase 7 num_gpu 스윕 먼저 → 그래도 미달 시 MOSS 게이트 평가

MOSS 게이트(한국어 TN 우회 품질 + Ryzen RTF<1 + Windows 설치) 통과
→ 후보 B (GPU를 LLM 전담)

모두 미달
→ LLM API 사용 검토 또는 12GB+ GPU 업그레이드 (fallback, 스펙 문서 개선방향 3)
```

### RVC (모두 만족 시만 추가 — v1 유지 + 실측 근거 보강)

- GPT-SoVITS 단독보다 음색 유사도 확실히 우위
- 추가 지연 300~500ms 이내 — **단, README의 90~170ms는 GPU 단독 점유+ASIO 조건. 매 청크 2초대 컨텍스트 HuBERT 재추론 구조라 LLM·TTS 동시 구동 실측 통과 필수**
- 캐릭터 학습 데이터 10~50분 확보 가능 (1분 미만 비권장 — 공식 FAQ)
- 서버형 통합은 `infer/rtrvc.py::RVC` 코어 + VST 워커 패턴 참조 (실증 코드 확인됨)

### Phase 5 (청크 스트리밍) 진입

- Phase 1+4 완료 시점에 "TTS 첫 오디오" P50 ≤ 800ms면 **진입하지 않는다** (문장 단위로 충분)

### 후보 D (클라우드 LLM 전환) 채택 게이트 (v2.1)

다음을 **모두** 충족할 때 후보 A 대비 채택한다:

- 트랙 M0~M2 완료 + 기억 검색 P50 ≤ 150ms
- 종단(T0→첫 음절) P50이 후보 A 대비 동등 이하 — STT GPU화 이득 ≥ LLM 네트워크·TTFT 증가분
- 월 예상 API 비용이 허용 한도 내 (캐싱 적용 후 실사용량 기준 — Haiku급 추정 턴당 3~5원, 실측 확정)
- 대화 텍스트의 외부 전송을 사용자가 명시 승인 (§12 개정 조항)
- 클라우드 장애 시 로컬 EXAONE 폴백 동작 확인 (방송 중 무중단)

## 11. 예상 최종 구성 후보

### 후보 A (기본): GPT-SoVITS 스트리밍

```text
Silero VAD [기존] → 부분 faster-whisper [기존 경로 배선]
→ EXAONE 2.4b 스트리밍 [기존] → tts-chunker [기존]
→ GPT-SoVITS v2ProPlus GPU (streaming_mode=2) [신규]
→ Web Audio / Live2D [기존]
```

### 후보 B (게이트 통과 시): GPU를 LLM 전담

```text
동일 → MOSS-TTS-Nano ONNX CPU [신규]
⚠️ CPU 경합 주의: STT 6 threads + LLM CPU 레이어 + TTS CPU가 6코어 공유 (Phase 7 배분표 필수)
```

### 후보 C (최후): 음색 유사도 최우선

```text
동일 → 빠른 한국어 TTS → RVC (rtrvc 청크 변환) → Web Audio / Live2D
```

### 후보 D (v2.1 — 트랙 M 게이트 통과 시): 클라우드 LLM + 풀 GPU 음성 + 로컬 기억

```text
Silero VAD [기존]
→ faster-whisper GPU (일괄, 부분 전사 불요 기대) [개조 — 서버 설정]
→ 메모리 프록시 127.0.0.1 (기억 검색·워터마크 절삭·캐싱·폴백) [신규 — 트랙 M]
→ 클라우드 LLM 스트리밍 (Haiku급, prompt caching, 로컬 EXAONE 폴백) [신규]
→ tts-chunker [기존] → GPT-SoVITS v2ProPlus (8GB VRAM 전유) [신규]
→ Web Audio / Live2D [기존]
＋ 백그라운드: 기억 추출 (EXAONE — M0 게이트 통과 시, 미달 시 클라우드 mini급)
```

초기 권장안은 후보 A. RVC(후보 C)는 §10 조건 전부 통과 시만. **후보 D는 트랙 M을 병행 진행해 §10 게이트에서 후보 A와 실측 대결로 결정**한다 — 채택 시 응답 품질(기억·캐릭터성)과 STT 지연에서 이득, LLM 구간과 프라이버시에서 트레이드오프.

## 12. 완료 기준

### 필수 (v1 유지)

- 종단(T0→첫 음절) P50 2초 이하, P95 3초 이하
- 끼어들기 후 300~500ms 이내 음성 중단 + **self-interrupt 0건** (v2 추가)
- TTS 큐 적체로 10초 이상 늦은 응답이 재생되지 않음
- 한국어 발음 현행 Chatterbox 동등 이상, 음색 일관성 유지, Live2D 립싱크 정상
- **음성 파이프라인(VAD·STT·TTS)과 기억 DB·프록시는 `127.0.0.1` 한정** (v2.1 개정 — 후보 A~C에서는 LLM 포함 전부 로컬. **후보 D 채택 시에만** LLM 대화 텍스트의 외부 API 전송을 허용하며, 이는 §10 후보 D 게이트의 명시 승인 항목이다)

### 권장

- 첫 반응 P50 1.5초 이하 / STT 확정 P50 500ms / LLM 첫 구절 P50 500ms / TTS 첫 오디오 P50 500ms
- 30분 대화 무적체·무누수, **소스 빌드 재현 절차 문서화** (v2 추가)

## 13. 즉시 수행할 작업

1. **[블로킹] 로컬 서버 코드·패치된 app.asar 실제 경로 확인** — 스펙 기재 위치(`C:\Projects\airi\stt\`, `chatterbox\`)에 없음. 확인 후 패치 diff 추출
2. `external/airi` 소스 빌드 재현 (pnpm install → stage-tamagotchi 빌드) 및 설치본 동등성 확인
3. 기존 OTel로 **LLM TTFT 즉시 실측** (신규 코드 없이 가능 — v1의 "LLM 미측정" 해소)
4. GPT-SoVITS 설치 + 한국어 G2P(mecab) 동작 검증 + v2ProPlus 제로샷 스트리밍 벤치 (§9 문장 7종, `min_chunk_length` 스윕)
5. LLM 미실행/실행 각각 TTFA·VRAM 측정 → 채택 판정 (§8 Phase 1 기준)
6. 채택 확정 시 Phase 2(취소 3개소) 착수 — LLM abort 주입이 가장 저비용·고효과
7. ~~Chatterbox 8초의 TTFA/총시간 분리 측정~~ → **해소됨** (스트리밍 없음 = TTFA≈총시간, 코드 확인)
8. ~~AIRI가 전체 WAV를 기다리는지 확인~~ → **해소됨** (전체 ArrayBuffer 수신 후 재생, 코드 확인)
9. **[트랙 M — 병행 가능] M0 게이트 벤치 착수** — EXAONE Stage A/B 추출 품질, KURE-v1/BGE-M3 임베딩 지연, 클라우드 TTFT (기술 레퍼런스 §1·§2의 프롬프트·공식으로 즉시 실행 가능)
10. **[트랙 M] LLM GPU 철수 상태에서 faster-whisper CUDA 실측** — 후보 D의 STT 이득 크기를 조기 확인 (Phase 3 GPU 우선 실험과 동일 항목)

## 14. 개발 우선순위 요약

```text
[메인 트랙 — 음성 파이프라인]
Phase 0  기반 (소스 빌드 + 계측 완결 + LLM 실측)
→ Phase 1  TTS 교체 (GPT-SoVITS v2ProPlus 벤치·채택)
→ Phase 2  취소 완결 (LLM abort + /stop + 서버 큐)
→ Phase 3  STT 저지연화 (GPU 우선 → 미달 시 부분 전사) + VAD 튜닝
→ Phase 4  LLM 첫 구절 튜닝 (chunker 파라미터 + 프롬프트)
→ Phase 5  (조건부) TTS 청크 스트리밍 재생
→ Phase 6  Barge-in (half-duplex 해체 + 에코 대책)
→ Phase 7  자원 최적화 (VRAM/CPU 예산표)
→ Phase 8  감정·캐릭터 (다중 슬롯 캐시 선행)

[병렬 트랙 M — 기억 계층 + 클라우드 LLM (후보 D)]
M0 게이트 벤치 (추출 품질·임베딩·TTFT)
→ M1 프록시 MVP (절삭·캐싱·fail-soft·폴백)
→ M2 기억 파이프라인 (Stage A/B·canon-snapshot·LLM 0회 검색)
→ M3 통합 — §10 게이트에서 후보 A와 실측 대결 → 채택 결정
```

현 시점 최우선 작업은 **로컬 패치 실체 확인(블로킹)과 GPT-SoVITS v2ProPlus의 3060 Ti 실측 벤치마크**이며, 트랙 M의 M0 게이트 벤치는 이와 병행 착수할 수 있다. AIRI에 이미 문장 파이프라인·취소·계측이 있으므로, TTS 엔진만 빠른 것으로 바뀌어도 1차 목표(3초)에 근접할 수 있다 — 나머지는 실측이 가리키는 병목 순서대로 진행하고, 후보 D는 추측이 아니라 §10 게이트의 실측 대결로 결정한다.
