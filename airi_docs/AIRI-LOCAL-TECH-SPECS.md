# AIRI 로컬 음성 대화 기술 사양

최종 확인일: 2026-08-05  
프로젝트 위치: `C:\Projects\airi`

## 전체 구성

```text
마이크
  -> AIRI 네이티브 MediaRecorder (Opus/WebM)
  -> Silero VAD
  -> 로컬 STT (faster-whisper small)
  -> AIRI 채팅 세션
  -> Ollama / EXAONE LLM
  -> 로컬 TTS (Chatterbox Multilingual V3)
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
| GPU 사용 | `num_gpu=20`, CPU/GPU 혼합 실행 |
| 호환 주소 | `http://127.0.0.1:11435` |
| 업스트림 | `http://127.0.0.1:11434` |

## STT

| 항목 | 사양 |
|---|---|
| 엔진 | faster-whisper 1.2.1 |
| 백엔드 | CTranslate2 4.8.1 |
| 모델 | Whisper `small` |
| 연산 | CPU INT8, 6 threads |
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
- VAD 기본값: speech threshold 0.3, exit threshold 0.1, 무음 400ms, speech padding 80ms.
- STT 결과를 채팅으로 넘기는 AIRI 내부 버퍼 지연은 1.2초에서 0.4초로 패치했다.

## TTS

| 항목 | 사양 |
|---|---|
| 엔진 | Chatterbox Multilingual V3 |
| 패키지 | chatterbox-tts 0.1.7 |
| PyTorch | 2.6.0 + CUDA 12.4 |
| Transformers | 5.2.0 |
| GPU | RTX 3060 Ti CUDA 실행 |
| 참조 음성 | `chatterbox/voices/airi-reference.wav` |
| 참조 음성 길이 | 8.9초, 24kHz, mono, PCM16 WAV |
| AIRI voice ID | `airi-vtuber` |
| 모델 | `tts-1-ko` |
| Exaggeration | 0.65 |
| CFG weight | 0.00 |
| Temperature | 0.80 |
| CFM steps | 10 (음질 우선 안정값) |
| API | `http://127.0.0.1:8880/v1/audio/speech` |
| 서버 | FastAPI 0.141.1 / Uvicorn 0.52.1 |

TTS 서버는 AIRI의 OpenAI Compatible provider로 연결되어 있다. `tts-1-ko`와 `airi-vtuber` 설정은 로컬 설정 저장소에 저장되어 있다.

## 현재 성능 측정

측정은 RTX 3060 Ti와 현재 로컬 서비스가 실행 중인 상태에서 수행했다.

| 구간 | 측정 결과 |
|---|---:|
| STT `small`, beam 5 시절 | 약 4.9~9.5초 |
| STT `small`, beam 1 현재 | 약 3.0~3.5초 |
| STT `base` | 약 1초지만 한국어 오인식으로 사용하지 않음 |
| TTS 21자 문장 | 약 8초 전후 |
| AIRI STT 결과 버퍼 | 1.2초 -> 0.4초 |

TTS가 17~40초까지 늘어난 경우는 모델 생성 자체보다 이전 TTS 요청이 직렬 큐에 쌓인 상황이었다. 현재 서버에는 요청 대기시간과 순수 생성시간 로그가 기록된다.

## 적용된 프로젝트 변경

- `stt/openai_stt_server.py`
  - WebM/Opus 입력 지원
  - 한국어 초기 프롬프트 및 hotword
  - beam 1 저지연 설정
  - 저신뢰도·짧은 음성·무음 필터
  - 디버그 녹음 및 오디오 RMS/peak 기록
- `chatterbox/openai_server.py`
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

패치 백업은 AIRI 설치 디렉터리의 `app.asar.backup-*` 파일에 보관되어 있다.

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
- Ollama 요청의 `num_gpu`를 12로 제한해 Chatterbox가 GPU를 사용할 여지를 확보했다. RTX 3060 Ti 8GB에서 반응성과 품질을 절충한 값이다.
- 12GB 이상 VRAM 업그레이드는 현재 보류한다.
- GPT-SoVITS V4는 캐릭터 음성 확정 후 학습·교체하는 장기 단계로 유지한다.
- 현재는 LLM 응답 후 TTS를 생성하는 순차 방식이다. 진정한 동시 대화에는 문장 단위 LLM 스트리밍과 TTS 청크 재생이 다음 과제다.

현재 음질을 유지하면서 더 빠르게 하려면 다음 순서가 현실적이다.

1. LLM 응답의 첫 문장을 짧게 만들어 첫 TTS 재생 시점을 앞당긴다.
2. Ollama의 GPU 레이어 수를 줄여 LLM 생성 중 TTS와의 GPU 경쟁을 완화한다.
3. 12GB 이상 VRAM GPU로 LLM과 TTS를 동시에 운용한다.
4. 캐릭터가 확정되면 GPT-SoVITS V4 등 전용 한국어 캐릭터 모델을 비교한다.

`base` STT는 속도는 빠르지만 현재 음성 샘플에서 정확도가 부족해 기본값으로 채택하지 않았다. CFM steps를 6으로 줄이는 실험은 약 0.2초 개선에 그쳐 10단계를 유지한다.
