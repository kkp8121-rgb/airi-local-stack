# AIRI 지연 개선 인수인계 — 2026-08-07

> 후속 구현이 적용됐다. 현재 구조와 최신 실측은 먼저 `AIRI-CLOUD-SEARCH-REACTION-2026-08-07.md`를 읽는다. 아래의 CPU STT, VAD 1200ms, buffered first-token 상태는 이 체크포인트 당시 기록이며 현재 런타임에는 CUDA STT, VAD 450ms, 즉시 SSE 선반응이 적용돼 있다.

## 최신 후속 상태 — 커밋 인계 시점

- 설치 AIRI 자동 검증에서 `음유잉여를 웹에서 검색해줘`가 실제 Codex 구독 검색으로 라우팅됐고, 검색 중 첫 `응!` 재생은 합성 입력 종료 기준 **1,184ms**였다.
- 검색 최종 답변은 `음유잉여 = 이터널 리턴 이바 장인, 대회명 UmU`로 반환됐다. 이 값은 자동 텍스트 입력 경로이며 실제 마이크 5회 acceptance를 대체하지 않는다.
- 첫 사용자 마이크 시도는 음성 청크 5개 중 4개가 Whisper 내부 VAD에서 segment 0개가 되어 무효였다. 비정숙 빈 결과만 `vad_filter=false`로 한 번 재시도하는 fallback을 추가했고 단위·실음원 HTTP 검증은 통과했지만, 사용자 물리 발화로는 아직 재검증하지 못했다.
- latency monitor는 원문·오디오를 저장하지 않으며 **수치 계측도 메모리 전용**이다. 프로세스가 재시작되면 표본이 사라진다. 다음 에이전트는 테스트 중 monitor를 재시작하지 않거나, 원문 없는 JSONL/SQLite 수치 영속화를 먼저 구현한다.
- 완료 판정은 최근 실제 마이크 검색 5회가 모두 `cloud_search=1`, 실제 `playback:start` 보유, 발화 종료 추정→재생 시작 **각각 2,000ms 이하**일 때만 한다.
- 현재 자동 테스트는 proxy 7 + STT 12 + TTS 3 + monitor 5 = **27개**다.

GPU 없는 PC에서는 통합 런처가 기본 CUDA를 요구하므로 STT를 다음과 같이 별도로 시작한다. CPU에서 2초 목표는 아직 증명되지 않았다.

```powershell
.\stt\start-local-stt.ps1 -Device cpu -ComputeType int8 -CpuThreads 8
```

그 뒤 latency monitor, Ollama proxy, GPT-SoVITS 스택을 각각 시작하거나 통합 런처에 STT device 인자를 전달하도록 후속 수정한다. 모델 가중치·Python 가상환경·Codex 로그인 세션·AIRI 설치본은 Git에 포함되지 않는다.

## 현재 사용자 체감 기준

- 사용자가 직접 5회 측정한 `발화 종료 → AIRI 첫말` 체감 평균: **약 8초**
- 같은 5턴의 계측 결과:

| 구간 | 평균 | 최소~최대 |
|---|---:|---:|
| STT 서버 처리 | 1,488ms | 1,392~1,575ms |
| STT 완료→LLM 요청 | 637ms | 527~894ms |
| LLM 전체 생성 | 1,028ms | 870~1,317ms |
| TTS 첫 바이트 | 774ms | 546~1,228ms |
| 마지막 TTS 세그먼트 완료 | 4,560ms | 2,971~7,051ms |
| TTS lock 대기 | 2,334ms | 1,106~4,209ms |

화면의 `Voice input transcribed`가 발화 종료 약 3초 뒤 표시된다는 사용자 관측은 VAD 무음 판정 1,200ms + STT 평균 1,488ms + 업로드/UI 처리와 일치한다. 현재 8초의 가장 큰 병목은 2~3개 문장 TTS의 직렬 lock과 AIRI의 완성 오디오 버퍼링이다. 사용자 체감 8초를 기준 KPI로 사용하고, 마지막 세그먼트 완료 기반 9초 추정치는 상한으로만 취급한다.

## 이번 체크포인트에 포함된 변경

- `latency_trace.py`: STT·LLM·TTS 요청 경로를 방해하지 않는 bounded queue 계측
- `latency-monitor/`: 최근 20턴 메모리 전용 waterfall + CPU/RAM/GPU/VRAM GUI
- `show-airi-latency-dashboard.ps1`: `http://127.0.0.1:8892/` 실행
- STT: 분석/Whisper/전체 시간 계측, CPU threads 6→8
  - 동일 음원 3회 A/B에서 약 7% 단축
- LLM proxy: 현재 전체 생성 시점을 정확히 기록
  - 중요: OpenAI chat 경로는 여전히 upstream `stream=false` 강제
- GPT-SoVITS proxy: lock 대기, 첫 오디오 바이트, stream 종료 계측
- 통합 런처: latency monitor 자동 시작 및 Ollama/EXAONE cold-load 워밍업
- `AIRI-RUNTIME-TECH-AUDIT-2026-08-06.md`: 문서 기술과 실제 런타임 대조

계측은 대화 원문과 오디오를 저장하지 않는다. 최근 20턴만 메모리에 있고 monitor 재시작 시 초기화된다.

## 다른 PC에서 재현

```powershell
git clone https://github.com/kkp8121-rgb/airi-local-stack.git
Set-Location .\airi-local-stack
.\start-airi-local-stack.ps1
.\show-airi-latency-dashboard.ps1
```

모델·Python 환경·AIRI 설치본은 Git에 포함되지 않는다. AIRI 0.11.3 설치 후 필요한 설치본 패치는 다음 순서로 적용한다.

```powershell
.\patch-airi-native-media-recorder.ps1
.\patch-airi-audio-constraints.ps1
.\patch-airi-transcript-latency.ps1
.\patch-airi-voice-input-segmentation.ps1
.\patch-airi-reaction-latency.ps1
.\patch-airi-playback-latency.ps1
```

각 스크립트는 설치 `app.asar`를 수정하므로 대상 PC에서 AIRI를 종료하고 실행해야 한다. 백업 파일은 해당 AIRI 설치 디렉터리에 생성된다.

## 이전 체크포인트의 구현 계획: 8초 → 2초

단순 GPU/스레드 상향으로는 불가능하다. 현재 VAD 1.2초 + STT 1.49초만으로 2초를 넘는다. 다음 순서로 파이프라인 대기를 제거한다.

### 1. AIRI 소스 빌드 기반으로 전환

현재 workspace에는 AIRI 소스가 없고 설치 `app.asar`만 패치돼 있다. AudioWorklet과 TTS 반환 계약 변경은 app.asar 문자열 패치로 진행하지 말고 AIRI 0.11.3 소스를 확보해 feature flag와 rollback 경로를 둔다.

### 2. GPT-SoVITS raw PCM 즉시 재생

GPT-SoVITS `external/GPT-SoVITS/api_v2.py`는 `media_type=raw`와 streaming generator를 이미 지원한다.

- 프록시가 32kHz mono PCM16 청크를 전달
- AIRI가 `Response.body`를 읽어 AudioWorklet ring buffer로 전달
- 100~150ms jitter buffer 후 재생 시작
- abort/다음 문장/재생 종료 이벤트 연결

이 단계가 가장 큰 체감 개선이다. 정확한 KPI를 위해 `AudioBufferSource.start()` 또는 AudioWorklet 첫 render 시점도 latency monitor에 `playback:start`로 전송한다.

### 3. LLM 진짜 스트리밍

`ollama-proxy/ollama_proxy.py`의 OpenAI chat 경로는 현재 `payload["stream"] = False`로 전체 답변을 기다린다.

- Ollama SSE/NDJSON을 증분 파싱
- ACT/emoji/말투 정규화를 스트리밍 안전하게 처리
- 6~15자 또는 첫 구두점에서 첫 TTS를 시작
- 첫 구절 후 나머지 토큰은 계속 전달

### 4. VAD 및 transcript A/B

- VAD 1,200→600ms부터 시작, 이후 400ms 평가
- transcript flush 400→150ms
- 20턴마다 문장 중간 절단률과 무응답률을 함께 기록

### 5. 부분 STT

내용 기반 첫말 P50 2초를 달성하려면 최종적으로 발화 중 PCM16 청크를 sliding-window STT에 보내 VAD 종료 시 마지막 부분만 확정해야 한다. RTX 3060 Ti는 추론 중 VRAM이 7.6/8.2GB까지 올라가므로 GPU STT를 무조건 추가하지 말고 CPU streaming 또는 LLM 메모리 이동과 함께 평가한다.

## 목표 게이트

- `발화 종료 → 내용 기반 첫 음성`: P50 ≤ 2.0초, P95 ≤ 2.5초
- `발화 종료 → transcript 표시`: P50 ≤ 1.0초, P95 ≤ 1.5초
- 문장 중간 절단률 < 5%
- TTS 겹침/속삭임/자기 목소리 재입력 0건
- 현재 음색·한국어 정확도 유지

빠른 체감 반응이 별도 목표라면 미리 합성한 짧은 반응을 0.5~1초에 재생할 수 있지만, 이는 내용 기반 2초 달성과 구분해 측정한다.

## 검증 명령

```powershell
Set-Location .\stt
& .\.venv\Scripts\python.exe -m unittest -v test_transcription_filter.py

Set-Location ..\latency-monitor
& ..\stt\.venv\Scripts\python.exe -m unittest -v test_monitor_server.py
```

아래 최신 검증 명령도 함께 실행한다.

```powershell
Set-Location .\ollama-proxy
& ..\chatterbox\.venv\Scripts\python.exe -m unittest -v test_ollama_proxy.py

Set-Location ..\gpt-sovits
& ..\external\GPT-SoVITS\.venv\Scripts\python.exe -m unittest -v test_openai_compatible_proxy.py
```

커밋 인계 시점 기준 총 27개 테스트와 Python compile, PowerShell parse, `git diff --check`가 통과해야 한다.
