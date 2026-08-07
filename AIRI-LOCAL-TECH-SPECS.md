# AIRI 로컬 음성 대화 기술 사양

최종 확인일: 2026-08-07 (코드 감사 반영 수정 — `AIRI-FIX-HANDOFF-2026-08-07.md` 참조)
프로젝트 위치: `airi-local-stack` 저장소 (클론 위치는 PC마다 다를 수 있음)

## 전체 구성

```text
마이크
  -> AIRI 네이티브 MediaRecorder (Opus/WebM)
  -> Silero VAD
  -> 로컬 STT (faster-whisper small)
  -> AIRI 채팅 세션
  -> Ollama / EXAONE LLM
  -> 로컬 TTS (GPT-SoVITS v2ProPlus GPU)
  -> AIRI Web Audio API / Live2D 립싱크
```

모든 음성·LLM 서버는 외부 공개 없이 PC의 `127.0.0.1`에서 실행된다.

## 하드웨어 및 운영체제

| 항목 | 사양 |
|---|---|
| 운영체제 | Windows 11 Pro, 빌드 26200 |
| CPU | AMD Ryzen 5 5600X, 6코어 12스레드 |
| GPU | NVIDIA GeForce RTX 3060 Ti, VRAM 8GB |
| NVIDIA 드라이버 | 591.74 |
| AIRI | 0.11.3, Electron 데스크톱 앱 |

## LLM

| 항목 | 사양 |
|---|---|
| 런타임 | Ollama 0.32.5 |
| 모델 | `exaone-airi:2.4b` |
| 실제 모델 정보 | EXAONE 계열, 2.7B parameters |
| 양자화 | Q4_K_M |
| 컨텍스트 | AIRI 프록시 기본 2,048 tokens |
| GPU 사용 | `num_gpu=12`, CPU/GPU 혼합 실행 |
| 호환 주소 | `http://127.0.0.1:11435` |
| 업스트림 | `http://127.0.0.1:11434` |

## STT

| 항목 | 사양 |
|---|---|
| 엔진 | faster-whisper 1.2.1 |
| 백엔드 | CTranslate2 4.8.1 |
| 모델 | Whisper `small` |
| 연산 | CUDA float16 (RTX 3060 Ti, 2026-08-07 전환) — CPU 폴백 시 INT8, 8 threads 권장 |
| 탐색 | `beam_size=1`, `best_of=1` |
| 언어 | 한국어(`ko`) |
| 문맥 | 한국어 대화 프롬프트 및 `아이리`, `AIRI` hotword |
| API | `http://127.0.0.1:8890/v1/audio/transcriptions` |
| 입력 | `audio/webm;codecs=opus` |
| 서버 | FastAPI 0.141.1 / Uvicorn 0.52.1 |

STT 기본 문맥은 `아이리, 내 말 들려?`를 포함하며 짧은 음성에서 숫자·고유명사 오인식을 줄이도록 설정되어 있다.

### 브라우저 음성 입력

- AIRI의 기존 PCM/WAV 녹음 경로 대신 네이티브 `MediaRecorder`를 사용한다.
- 녹음 코덱은 Opus/WebM이다.
- 브라우저의 자동 게인, 에코 제거, 노이즈 억제는 비활성화했다.
- VAD는 브라우저의 Silero VAD(ONNX 기반)를 사용한다.
- VAD 런타임: speech threshold 0.52, exit threshold 0.156. 무음 판정은 stock 1200ms를 450ms로 패치(`patch-airi-reaction-latency.ps1`). speech padding 360ms는 stock 유지 — 120ms 변경은 no-op으로 판명되어 2026-08-07 패치에서 제거.
- 볼륨 폴백은 2026-08-07부터 "VAD 분기 제거" 대신 **타이머 연장(900→2700ms)** 방식으로 패치한다. VAD 정상 시 450ms가 항상 먼저 종료하므로 900ms 선점 절단이 사라지고, VAD 정지 시에도 2700ms 안전망이 남아 영구 잠금이 없다.
- STT 결과를 채팅으로 넘기는 AIRI 내부 버퍼 지연은 1.2초에서 0.4초로 패치했다. (한때 100ms까지 낮췄으나 문장 병합이 무력화되어 400ms로 확정 — 휴지 후 이어 말하는 문장이 별도 턴으로 쪼개지는 문제)

## TTS

| 항목 | 사양 |
|---|---|
| 엔진 | GPT-SoVITS v2ProPlus |
| 실행 | RTX 3060 Ti GPU, fp16 |
| 스트리밍 | `streaming_mode=2`, `min_chunk_length=16` |
| fallback | 자동 fallback 없음; Chatterbox는 legacy 설치 후보 |
| 참조 음성 | `chatterbox/voices/airi-reference.wav` |
| 참조 음성 길이 | 8.9초, 24kHz, mono, PCM16 WAV |
| 참조 언어 | 일본어 (`prompt_lang=ja`), 실제 참조 문장 사용 |
| AIRI voice ID | `airi-vtuber` |
| 모델 | `tts-1-ko` |
| 병렬 추론 | 비활성화, 프록시 전역 잠금으로 요청 직렬화 |
| API | `http://127.0.0.1:8880/v1/audio/speech` |
| 서버 | FastAPI 0.141.1 / Uvicorn 0.52.1 |

TTS 서버는 AIRI의 OpenAI Compatible provider로 연결되어 있다. `tts-1-ko`와 `airi-vtuber` 설정은 로컬 설정 저장소에 저장되어 있다.

## 현재 성능 측정

측정은 RTX 3060 Ti와 현재 로컬 서비스가 실행 중인 상태에서 수행했다.

| 구간 | 측정 결과 |
|---|---:|
| STT `small`, beam 5 시절 (CPU, historical) | 약 4.9~9.5초 |
| STT `small`, beam 1 CPU 시절 (historical) | 약 3.0~3.5초 |
| STT `small` CUDA float16 서버 내부 처리 (2026-08-07) | 첫 실요청 670.3ms / warm 291.3ms — 업로드·클라이언트 구간 제외 수치 |
| STT `base` | 약 1초지만 한국어 오인식으로 사용하지 않음 |
| GPT-SoVITS 첫 청크 | 워밍업 후 약 0.4~1.2초 |
| GPT-SoVITS 전체 생성 | 짧은 문장 약 1~3초 |
| AIRI STT 결과 버퍼 | 1.2초 -> 0.4초 |

이전 Chatterbox 측정은 현재 활성 경로의 수치가 아니다. 현재 구간별 지연은 `show-airi-latency-dashboard.ps1`에서 STT·LLM·TTS 첫 바이트·전체 WAV로 분리해 측정한다.

## 적용된 프로젝트 변경

- `stt/openai_stt_server.py`
  - WebM/Opus 입력 지원
  - 한국어 초기 프롬프트 및 hotword
  - beam 1 저지연 설정
  - 저신뢰도·짧은 음성·무음 필터
  - 디버그 녹음 및 오디오 RMS/peak 기록
- `chatterbox/openai_server.py` (legacy, 현재 비활성)
  - OpenAI Compatible `/v1/audio/speech`
  - 참조 음성 conditionals 사전 준비
  - TTS 생성/대기시간 계측
  - CUDA TF32 설정
  - `cfg_weight=0`일 때 불필요한 이중 T3 배치 제거
  - CFM steps 설정 지원
- AIRI 설치본 `app.asar`
  - 네이티브 MediaRecorder 녹음 경로 적용
  - 브라우저 자동 음성 필터 비활성화
  - STT 결과 버퍼 지연 400ms 적용
- `latency_trace.py`, `latency-monitor/`
  - STT·LLM·TTS 비차단 숫자 계측
  - 최근 20턴 메모리 전용 waterfall 및 CPU/RAM/GPU/VRAM 표시

패치 백업은 2026-08-07부터 단일 pristine 백업 체계로 운영한다: 최초 패치 전 원본만 `app.asar.backup-pristine`으로 1회 보존하고, 복원은 `restore-airi-original.ps1`, 일괄 적용은 `apply-airi-patches.ps1`을 사용한다. **주의: 설치본의 실제 패치 적용 여부는 PC마다 다르므로, acceptance 측정 전 `apply-airi-patches.ps1`의 최종 검증 출력으로 반드시 확인한다.**

## 테스트 및 상태

- STT 필터 회귀 테스트: 7개 통과
- STT health: 정상
- TTS health: 정상
- Ollama proxy: `11435` listening
- STT: `8890` listening
- TTS: `8880` listening
- AIRI 진단용 remote debugging 포트: 닫힘

## 추가 개선 방향

### 실시간 대화 우선 조정 (2026-08-05)

- Ollama 시스템 프롬프트에 `응!`, `그렇구나!` 같은 짧은 첫 반응과 약 25자 안팎의 짧은 답변을 지시했다.
- 통합 런처가 Ollama/EXAONE을 미리 호출해 모델 미상주 시 첫 사용자 턴에 붙던 약 4초의 cold-load를 시작 단계로 이동한다.
- Ollama와 GPT-SoVITS v2ProPlus를 RTX 3060 Ti 8GB에서 동시 상주시키는 구성을 실측했다. GPU 여유가 제한적이므로 다른 GPU 작업은 피한다.
- 12GB 이상 VRAM 업그레이드는 현재 보류한다.
- GPT-SoVITS V4는 캐릭터 음성 확정 후 학습·교체하는 장기 단계로 유지한다.
- 현재는 LLM 응답 후 TTS를 생성하는 순차 방식이다. 진정한 동시 대화에는 문장 단위 LLM 스트리밍과 TTS 청크 재생이 다음 과제다.

현재 음질을 유지하면서 더 빠르게 하려면 다음 순서가 현실적이다.

1. LLM 응답의 첫 문장을 짧게 만들어 첫 TTS 재생 시점을 앞당긴다.
2. Ollama의 GPU 레이어 수를 줄여 LLM 생성 중 TTS와의 GPU 경쟁을 완화한다.
3. 12GB 이상 VRAM GPU로 LLM과 TTS를 동시에 운용한다.
4. 캐릭터가 확정되면 GPT-SoVITS V4 등 전용 한국어 캐릭터 모델을 비교한다.

`base` STT는 속도는 빠르지만 현재 음성 샘플에서 정확도가 부족해 기본값으로 채택하지 않았다. CFM steps를 6으로 줄이는 실험은 약 0.2초 개선에 그쳐 10단계를 유지한다.
