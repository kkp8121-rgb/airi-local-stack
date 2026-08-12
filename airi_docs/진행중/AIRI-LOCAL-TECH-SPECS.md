# AIRI 로컬 음성 대화 기술 사양

최종 확인일: 2026-08-12 (Upgrade Scout 적용 반영 갱신 — 이전 버전은
2026-08-07 코드 감사 기준이며 STT=CPU/small, LLM=EXAONE, TTS=Chatterbox
후보 등 stale 정보를 포함하고 있었다)
프로젝트 위치: `airi-local-stack` 저장소 (클론 위치는 PC마다 다를 수 있음)

## 전체 구성

```text
마이크
  -> AIRI 네이티브 MediaRecorder (Opus/WebM)
  -> Silero VAD
  -> 로컬 STT (faster-whisper large-v3-turbo, CUDA GPU)
  -> AIRI 채팅 세션
  -> Ollama 프록시(11435, SSE) -> midm-airi:2.0-mini
  -> 로컬 TTS (GPT-SoVITS v2ProPlus GPU, streaming_mode=2)
  -> AIRI Web Audio API / Live2D 립싱크
```

모든 음성·LLM 서버는 외부 공개 없이 PC의 `127.0.0.1`에서 실행된다.

## 하드웨어 및 운영체제

| 항목 | 사양 |
|---|---|
| 운영체제 | Windows 11 Pro, 빌드 26200 |
| CPU | AMD Ryzen 5 5600X, 6코어 12스레드 |
| GPU | NVIDIA GeForce RTX 3060 Ti, VRAM 8GB |
| NVIDIA 드라이버 | 591.74 (2026-08-07 확인 이후 재확인 없음 — 확인 필요) |
| AIRI 클라이언트 | v0.11.3 Electron fork (Live2D), 3층 런타임 패치 적용 |

## LLM

| 항목 | 사양 |
|---|---|
| 런타임 | Ollama 0.32.6 (출처: `AIRI-MODEL-LLM-CHANGE-ANALYSIS-2026-08-12.md` — 이전 실측은 0.32.5) |
| 기본 모델 | `midm-airi:2.0-mini` (Mi:dm 2.0 Mini Instruct, MIT 라이선스) |
| 롤백 태그 | `exaone-airi:2.4b` — `start-airi-local-stack.ps1 -ChatModel exaone-airi:2.4b`로 되돌릴 수 있음. 원본 모델과 Modelfile 모두 보존 |
| 양자화 | Q4_K_M |
| 컨텍스트 | `num_ctx=2048` (모델 교체 전후 동일 — Mi:dm 원본의 더 긴 최대 context는 사용하지 않음) |
| GPU 사용 | `num_gpu=999`(요청값). 프로덕션 경로는 프록시 CLI 인자가 최종 승리하며, 8GB 예산 초과 시 Ollama가 로드 시점에 레이어를 자동 하향한다. 현재 구성의 실제 오프로드 층수·VRAM 분해 실측은 확인 필요 |
| 프록시 주소 | `http://127.0.0.1:11435` (`ollama-proxy/ollama_proxy.py`, SSE `text/event-stream`) |
| 업스트림 | `http://127.0.0.1:11434` |

**SSoT 갭 — 코드 해소 완료, 실기 검증 대기** (2026-08-12 해소. 원 출처:
`AIRI-MODEL-LLM-CHANGE-ANALYSIS-2026-08-12.md` §단점 7~10): 프록시 내
`"exaone-airi:2.4b"` 하드코딩 8곳을 `resolve_chat_model()`(env
`AIRI_CHAT_MODEL` → 기본 `midm-airi:2.0-mini`) 단일 경유로 교체했고 소스에
EXAONE 문자열 0건을 테스트로 고정했다. foreground chat 요청의 model 필드는
SSoT로 정규화된다(loopback 검증 마커 면제, `AIRI_CHAT_MODEL_ENFORCE=0`
진단 스위치). 런처가 `AIRI_EVAL_MODEL`을 설정해 평가 provenance가 실제
모델과 일치한다. digest pin은 `AIRI_CHAT_MODEL_DIGEST` opt-in — 설정 시
불일치면 기동 차단(fail-closed), 미설정 시 관측 digest 기록만. ACK
metadata는 분기별 실측값(`audible`/`silent`)으로 교정됐다. 실제
Electron→proxy 턴에서의 정규화 동작·digest 실값 pin은 실기(dev PC) 검증
대기다.

## STT

| 항목 | 사양 |
|---|---|
| 엔진 | faster-whisper (버전 1.2.1, 2026-08-07 확인 이후 재확인 없음 — 확인 필요) |
| 백엔드 | CTranslate2 (버전 4.8.1, 2026-08-07 확인 이후 재확인 없음 — 확인 필요) |
| 모델 | `mobiuslabsgmbh/faster-whisper-large-v3-turbo` (`stt/openai_stt_server.py:79`) |
| 연산 | CUDA, `compute_type=int8_float16` (`stt/openai_stt_server.py:83-84`) |
| 탐색 | `BEAM_SIZE=1`(기본, Upgrade Scout T0/T1 SSoT 정렬 완료), `RECOVERY_BEAM_SIZE=3`(저신뢰 재시도 경로에서만 사용 — `stt/openai_stt_server.py:130-131`) |
| 언어 | 한국어(`ko`) |
| API | `http://127.0.0.1:8890/v1/audio/transcriptions` |
| 서버 | FastAPI / Uvicorn (2026-08-07 실측 버전 유지, 이후 재확인 없음 — 확인 필요) |

STT 기본 문맥은 `아이리, 내 말 들려?`를 포함하며 짧은 음성에서 숫자·고유명사
오인식을 줄이도록 설정되어 있다.

### 브라우저 음성 입력

- AIRI의 기존 PCM/WAV 녹음 경로 대신 네이티브 `MediaRecorder`를 사용한다.
- 녹음 코덱은 Opus/WebM이다.
- 브라우저의 자동 게인, 에코 제거, 노이즈 억제는 비활성화했다.
- VAD는 브라우저의 Silero VAD(ONNX 기반)를 사용한다. 무음 판정은 stock
  1200ms를 450ms로 패치했다.
- 볼륨 폴백은 타이머 연장(900→2700ms) 방식이다.
- STT 결과를 채팅으로 넘기는 AIRI 내부 버퍼 지연은 0.4초다.

이 절의 세부 수치는 2026-08-07 감사 기준이며, large-v3-turbo/beam=1 SSoT
정렬(Upgrade Scout T0/T1) 이후 재측정되지 않았다 — 확인 필요.

## TTS

| 항목 | 사양 |
|---|---|
| 엔진 | GPT-SoVITS v2ProPlus |
| 실행 | RTX 3060 Ti GPU, fp16 (`is_half: true`, `tts-infer-v2proplus.yaml:4-5`) |
| 직접 API(엔진) | `http://127.0.0.1:9880/tts`, `streaming_mode=2` (`gpt-sovits/openai_compatible_proxy.py:30,114`) |
| OpenAI 호환 프록시 | `http://127.0.0.1:8880/v1/audio/speech` — AIRI 클라이언트가 실제로 연결하는 지점 |
| 병렬 추론 | 비활성화, 프록시 전역 락으로 요청 직렬화(`TTS_LOCK`). 락 타임아웃 부재는 알려진 갭(T-03, `AIRI-UPGRADE-SCOUT-DATA-2026-08-11.md`) |
| 참조 음성 | `chatterbox/voices/airi-reference.wav`, 8.9초·24kHz·mono·PCM16 |
| 참조 언어 | 일본어(`prompt_lang=ja`) — 교차언어 클로닝이며 속도 손해는 없음. 한국어 레퍼런스 교체(T-05)는 화자 승인 대기로 미수행(`AIRI-UPGRADE-SCOUT-MEASUREMENT-2026-08-11.md`) |
| AIRI voice ID | `airi-vtuber` |
| 모델 | `tts-1-ko` |

fallback 자동 전환은 없다. Chatterbox는 legacy 설치 후보로만 남아 있으며
현재 활성 경로가 아니다.

## 프록시

| 항목 | 사양 |
|---|---|
| 파일 | `ollama-proxy/ollama_proxy.py` |
| 포트 | `11435` |
| 스트리밍 | SSE (`media_type="text/event-stream"` — `ollama_proxy.py:7011,7234,7389,7480,7504`) |
| 로컬 스코프 강제 | `enforce_local_scope` 미들웨어 — Origin 검증 + 허용 경로 검증. CORS 미들웨어 뒤(바깥쪽)에 등록되어 거부된 Origin은 프록시 본문에 도달하지 않는다 |

## 클라이언트

- AIRI v0.11.3 Electron fork, Live2D 립싱크.
- 3층 런타임 패치 순서: **통합 패치(round-cancel-source-replacement) →
  context sanitizer → Upgrade Scout 레이어**.
- 패치 매니페스트는 `airi_docs/patches/`에 있으며 이동·수정 금지
  (`test-patch-manifest.ps1`과 CI가 경로를 핀한다).
- 적용 확인: `test-current-checkpoint.ps1`이 핀 checkout에서 3층 패치의
  정방향·역방향 적용을 검증한다(2026-08-12 최신 실행 PASS,
  `AIRI-CURRENT-DOCS-INDEX-2026-08-10.md` "최신 검증 증거" 절).

## 기억 (Memory)

| 항목 | 사양 |
|---|---|
| 저장소 | SQLite. 대화/기억은 `runtime/airi-memory.sqlite3`, 승인 지식은 별도 파일 `runtime/airi-knowledge.sqlite3` (`ollama-proxy/start-local-ollama-proxy.ps1:232-233`) |
| 동시성 | `_connect`에서 `PRAGMA busy_timeout=5000` 후 `PRAGMA journal_mode=WAL` (MEM-04, `airi_memory.py`). 당초 500ms(로컬 8-thread 10/10)로 잡았으나 저하된 CI runner(5배 느린 shard)에서 "database is locked" 재발 — 턴 쓰기 실패가 드문 대기보다 나쁘므로 sqlite3 connect 기본 예산(5s)을 복원. WAL로 실제 경합 창은 짧아 상한은 사실상 미발동. 추출 활성 상태의 락 경합 재평가는 실기 대기 |
| 임베딩 | KURE-v1, CUDA 상주, fp16 (`memory_runtime.py:156-174`의 `torch_dtype=torch.float16` 명시 캐스팅) |
| fp16 절감 실측 | CUDA allocated 2,165.938MiB(fp32) → 1,083.032MiB(fp16), 회수 약 1,082.9MiB (`AIRI-UPGRADE-SCOUT-MEASUREMENT-2026-08-11.md`). 검색 품질(MRR·Recall@1·Recall@3)은 fp32/fp16 양쪽 모두 1.0으로 동일 |
| journal 검색 | FTS5 인덱스(KM-08) — 기존 O(N) 파이썬 재토큰화를 대체. 실측 0.060ms/메시지, 미추출 4,096건 기준 247.4ms (`AIRI-UPGRADE-SCOUT-2026-08-11.md`) |
| 지식 검색 계약 | 700자 청크·100자 오버랩·SQLite FTS5 인덱스, `retrieve(top_k=4, max_chars=1600)` |

## 현재 성능 측정

수치는 모두 출처 문서와 실측 날짜를 표기한다. 서로 다른 경로(raw 모델
단독 / proxy 정책 포함 / 텍스트 전체 체인)는 직접 비교하지 않는다.

| 구간 | 결과 | 출처 |
|---|---:|---|
| KURE-v1 fp16 query | P50 26.774ms, P95 55.481ms | `AIRI-UPGRADE-SCOUT-MEASUREMENT-2026-08-11.md` |
| 기억 검색(10k×1024 벡터, dynamic) | P50 110ms (≤150ms 게이트 통과) | 〃 |
| Mi:dm raw 모델(로컬, proxy 우회) | warm TTFT 중앙값 163.8ms, 전체 완료 중앙값 241.8ms | `AIRI-MODEL-LLM-CHANGE-ANALYSIS-2026-08-12.md` |
| Mi:dm + 현행 proxy 정책 A/B(120 turn) | 전체 P50 514.4ms, P95 737.7ms | 〃 |
| GPT-SoVITS 격리 TTS(n=3) | 첫 byte P50 742.8ms, 완료 P50 2,013.5ms | `AIRI-UPGRADE-SCOUT-MEASUREMENT-2026-08-11.md` |
| STT WebSocket 스트리밍(3.3초 합성 음성) | 첫 partial 504.0ms, final 2,447.4ms | 〃 |
| Electron 텍스트 입력 → 첫 실질 렌더 신호(n=20, 실기) | P50 1,963ms, P95 2,720ms | `AIRI-ELECTRON-TEXT-TTS-MEASUREMENT-2026-08-12.md` |
| Electron 텍스트 입력 → 응답 완료(n=20, 실기) | P50 718ms, P95 794ms | 〃 |

**확인 필요 — 실측되지 않음**:

- 실제 마이크 입력 기준 음성 전체 체인(STT→LLM→TTS→재생) P50/P95. 위 표의
  Electron 실기 측정은 텍스트 ingress로 STT를 대체한 것이며, 저자 스스로
  "STT, 마이크, 물리 스피커, 자연 재생 종료 성능을 이 텍스트 전용 체크포인트에서
  추론하지 말 것"이라고 명시했다.
- large-v3-turbo/beam=1 SSoT 정렬 이후의 STT 단독 P50·한국어 WER
  재측정치.
- 현재 `num_gpu=999` 구성의 VRAM 실측 분해(합/모델별). Mi:dm 도입 후
  전체 스택 동시 상주 peak(7,350/8,192MiB, 여유 약 842MiB)는 있으나,
  이는 STT+TTS+KURE+Mi:dm 합산 실측이며 모델별 세부 분해는 아니다.
- installed Electron `app.asar`의 Mi:dm first-audible 실측(위 Electron
  측정은 소스 빌드 `ef0217c5` 기준이며 설치본과 다르다).
- barge-in 200~500ms, real-mic VAD 20+20, speaker AEC 실측 — 모두
  `AIRI-UPGRADE-SCOUT-MEASUREMENT-2026-08-11.md`가 "아직 운영 채택으로
  승격하면 안 되는 항목"으로 명시.

## 적용된 프로젝트 변경

2026-08-07 기준(유지):

- `stt/openai_stt_server.py`
  - WebM/Opus 입력 지원
  - 한국어 초기 프롬프트 및 hotword
  - 저신뢰도·짧은 음성·무음 필터
  - 디버그 녹음 및 오디오 RMS/peak 기록
- AIRI 설치본 `app.asar`
  - 네이티브 MediaRecorder 녹음 경로 적용
  - 브라우저 자동 음성 필터 비활성화
  - STT 결과 버퍼 지연 400ms 적용

2026-08-11~12 Upgrade Scout 적용분 추가(`AIRI-UPGRADE-SCOUT-MEASUREMENT-2026-08-11.md`
T0~T3 기준):

- KURE fp16 전환, `num_ctx`/`num_gpu` SSoT, STT SSoT/beam=1/이중 decode
  제거, evaluator 기본 OFF, TTS 15초 상한, grounding A/B.
- journal FTS5(KM-08) 등 기억 계층 다수(KM-02~05/08), PX 계열 prefix
  캐시, T-01 AudioWorklet PCM 재생, ARCH-01/03/04 barge-in 묶음.
- Mi:dm 2.0 Mini Q4_K_M 기본 모델 전환, 조건부 AEC3 모드, STT-06 loopback
  streaming STT.
- Electron 클라이언트: GPT-SoVITS의 스트리밍 RIFF 헤더(zero-sized `data`
  chunk)를 빈 WAV로 오판하던 결함을 수정해 progressive playback을
  활성화(`AIRI-ELECTRON-TEXT-TTS-MEASUREMENT-2026-08-12.md`).

## 테스트 및 상태

최신 스냅샷은 `airi_docs/AIRI-CURRENT-DOCS-INDEX-2026-08-10.md`의 "최신
검증 증거(2026-08-12)" 절이 단일 출처다. 이 문서에 수치를 중복 기재하지
않고 인용만 남긴다 — 통합 Python 809 passed / 1 skipped / 706 subtests,
node 27/27, `test-current-checkpoint.ps1`·`test-patch-manifest.ps1` PASS
(tip `932eae6` 기준). CI 2-job green은 `294c4e6` 기준이며 이후 커밋은 push
시 재검증.

## 다음 게이트 (확인 필요 항목 포함)

`AIRI-MODEL-LLM-CHANGE-ANALYSIS-2026-08-12.md` "판정과 다음 gate" 절
인용:

1. model SSoT 강제(하드코딩 폴백 제거), evaluation provenance 정정,
   ACK metadata, model digest pin을 먼저 해소한다. — **코드 해소 완료
   (2026-08-12, `932eae6`). 위 "SSoT 갭" 절 참조. 남은 것은 실기 검증뿐.**
2. 최소 100개 인간 검수 대화 + 장문 context/memory/card corpus에서
   정확성·답변 완전성·화자 보존·retry율을 함께 측정한다.
3. 같은 Electron build·TTS warm state에서 모델 순서를 교차한 matched
   text→render A/B를 추가해야 모델 교체의 체감 지연을 확정할 수 있다.
