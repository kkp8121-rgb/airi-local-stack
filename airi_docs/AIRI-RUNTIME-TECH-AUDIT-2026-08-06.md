# AIRI 문서 기술과 실제 런타임 대조 — 2026-08-06

> **2026-08-07 주의:** 이 문서의 STT 항목(CPU INT8)은 CUDA float16 전환 이전 기록이며, 이후 코드 감사·수정(`AIRI-LOCAL-STACK-REVIEW-2026-08-07.md`, `AIRI-FIX-HANDOFF-2026-08-07.md`)이 반영되지 않았다. 현행 스펙 기준은 `AIRI-LOCAL-TECH-SPECS.md`를 사용한다.

이 문서는 `airi_docs`의 설계·계획 문구와 현재 PC에서 실행되는 프로세스, 포트, health 응답, 실제 AIRI 요청 로그 및 설치 `app.asar`를 대조한 판정표다. 계획 문서보다 이 문서와 실시간 지연 대시보드를 현재 런타임의 기준으로 사용한다.

## 판정 기준

- **ACTIVE**: 현재 실행 경로에서 실제 요청이 확인됨
- **PATCHED / 사용자 검증 필요**: 설치본에 적용됐으나 체감·브라우저 effective setting까지 확인되지 않음
- **AVAILABLE**: 코드나 모델은 설치돼 있지만 현재 실행 경로가 아님
- **PLANNED**: 설계·후보 문서만 있고 현재 런타임에는 없음
- **STALE**: 더 최신 코드·로그·하드웨어와 불일치

## 실제 활성 파이프라인

```text
AIRI MediaRecorder (Opus/WebM) + Silero VAD
  → faster-whisper small (CPU INT8, 8 threads, batch POST)
  → Ollama proxy (최근 10메시지 + system override + tool 제거)
  → Ollama EXAONE 2.4b (CPU/GPU 혼합)
  → GPT-SoVITS v2ProPlus (GPU, streaming_mode=2, 전역 직렬 lock)
  → AIRI가 문장별 완성 WAV를 버퍼링한 뒤 Web Audio 재생
```

리스너 `8890`, `11435`, `11434`, `8880`, `9880`과 AIRI의 실제 POST 로그를 확인했다.

## 기술별 판정

| 기술 | 판정 | 현재 실제 상태 |
|---|---|---|
| GPT-SoVITS v2ProPlus | **ACTIVE** | CUDA/fp16, `streaming_mode=2`, `min_chunk_length=16`; 8880 프록시와 9880 백엔드 사용 |
| TTS 전역 lock / `parallel_infer=false` | **ACTIVE** | 인접 문장 음성 혼합을 막기 위해 합성을 직렬화 |
| faster-whisper small | **ACTIVE** | CPU INT8, 8 threads, worker 1; GPU를 사용하지 않음. 동일 음원 3회 A/B 평균에서 6 threads보다 약 7% 단축 |
| Silero VAD | **ACTIVE** | 설치 AIRI 브라우저 런타임에서 발화 분절에 사용 |
| MediaRecorder Opus/WebM | **ACTIVE** | STT 로그에서 실제 `audio/webm;codecs=opus` 업로드 확인 |
| Ollama EXAONE 호환 프록시 | **ACTIVE** | context 2048, `num_gpu=12`, 최근 10메시지만 전달, system/tool 정규화 |
| 문장 단위 TTS 분할 | **ACTIVE** | 한 LLM 턴이 여러 짧은 TTS 요청으로 나뉨 |
| ACT 감정 토큰 | **ACTIVE** | LLM 프록시가 응답마다 감정을 추론해 ACT 토큰을 삽입 |
| Live2D 표정 반영 | **AVAILABLE / 미검증** | ACT parser와 Live2D 지원 코드는 있으나 이번 런타임 감사에서 실제 표정 변화까지 검증하지 않음 |
| transcript flush 400ms 패치 | **PATCHED / 사용자 검증 필요** | 설치 `app.asar`에서 400ms 확인; 8~9초 체감의 주원인인지 계측 전 |
| VAD/볼륨 분절 및 빈 전사 패치 | **PATCHED / 사용자 검증 필요** | 900ms 폴백이 VAD 세그먼트를 끊던 버그는 수정됨; 연속 대화 acceptance 필요 |
| AEC/NS/AGC 비활성화 | **PATCHED / 사용자 검증 필요** | 설치본 대상 블록은 비활성화됐지만 `MediaStreamTrack.getSettings()` 확인은 아직 없음 |
| 점진적 TTS 오디오 재생 | **PLANNED** | GPT 백엔드는 바이트를 스트리밍하지만 AIRI는 문장 WAV 전체를 받은 뒤 재생 |
| 스트리밍 STT / 부분 전사 | **PLANNED** | 현재는 발화 종료 후 전체 Blob을 multipart로 한 번에 전송 |
| true barge-in | **PLANNED** | 현재는 재생 중 마이크를 막는 half-duplex; 일반 abort/stop 코드와 사용자 발화 끼어들기는 다름 |
| 장기기억 / vector·graph RAG | **PLANNED** | 현재는 최근 대화 10개를 단순 절삭할 뿐 검색·임베딩·기억 저장이 없음 |
| 클라우드 LLM | **PLANNED** | 현재 LLM은 로컬 Ollama EXAONE |
| MOSS-TTS-Nano | **AVAILABLE** | 설치·CPU 실험은 있으나 realtime gate 실패, 실행 경로 아님 |
| Chatterbox | **AVAILABLE (legacy)** | 코드·환경은 있으나 현재 8880은 GPT-SoVITS; 자동 fallback 체인은 없음 |

## 문서에서 특히 혼동하기 쉬운 표현

1. GPT-SoVITS의 `streaming_mode=2`는 **백엔드 응답 스트리밍**이다. AIRI가 첫 바이트를 즉시 재생한다는 뜻은 아니다.
2. Opus/WebM과 VAD 사용은 **스트리밍 STT**가 아니다. 현재 STT는 발화 종료 후 batch POST다.
3. 기존 abort/stop 기능이 있다고 **true barge-in**이 구현된 것은 아니다.
4. `AIRI-MEMORY-TECH-REFERENCE`와 RAG 감사는 **구현 완료 보고서가 아니라 이식 설계 자료**다.
5. MOSS와 Chatterbox는 현재 **자동 장애 fallback이 아니다**.

## 현재 하드웨어와 자원 해석

- 실제 CPU: **AMD Ryzen 5 5600X, 6코어 12스레드**. 일부 계획 문서의 Ryzen 7 8700G는 STALE이다.
- GPU: RTX 3060 Ti 8GB. 관측 시 약 6.3/8.2GB VRAM이 이미 상주해 평균 GPU 사용률보다 VRAM 여유가 더 큰 제약이다.
- STT는 의도적으로 CPU 전용이고, LLM은 CPU/GPU 혼합이며, TTS는 GPU를 짧게 사용한다. 세 단계가 순차 실행되므로 총 CPU/GPU가 동시에 100%가 되는 구조가 아니다.
- 모델 가중치는 요청 사이에도 RAM/VRAM에 남는다. 따라서 메모리는 높고 순간 연산률은 낮게 보이는 것이 정상이다.
- 작업 관리자에 같은 Python 서비스가 두 개씩 보이는 것은 이 환경의 `.venv\Scripts\python.exe` 런처가 실제 uv-managed Python 자식 프로세스를 실행하기 때문이다. 부모 런처는 약 3~5MB이고 모델을 한 벌 더 로드한 별도 머신이 아니다. AIRI.exe 여러 개도 Electron의 renderer/GPU/utility 프로세스 분리다.

## 실시간 확인

`show-airi-latency-dashboard.ps1`을 실행하면 `http://127.0.0.1:8892/`에서 STT 분석·Whisper·LLM·TTS 첫 바이트·전체 WAV와 CPU/RAM/GPU/VRAM을 함께 볼 수 있다. 계측은 숫자만 최근 20턴까지 메모리에 유지하며 대화 내용과 오디오는 저장하지 않는다.

통합 런처는 Ollama/EXAONE도 한 번 워밍업한다. 이 PC에서 모델이 내려간 상태의 첫 LLM 요청은 약 4초가 걸렸고 워밍 상태 요청은 약 0.7초였으므로, cold-load를 첫 사용자 발화 전에 처리하기 위함이다.
