# AIRI 인수인계 문서 (2026-08-06)

## 현재 판정

- AIRI 0.11.3의 텍스트 입력 → LLM → GPT-SoVITS → Web Audio 재생 경로는 실제 UI 턴으로 확인했다.
- TTS의 속삭임·무음·혼합 언어 스트림 중단 원인은 해결했고 회귀 검사에 포함했다.
- 실제 마이크 요청은 STT 서버까지 도달한다.
- 약 0.899초로 반복되던 마이크 절단 원인은 AIRI의 900ms 볼륨 폴백이 VAD 소유 녹음까지 종료하던 프런트엔드 버그였다. 설치본 패치를 적용했다.
- 패치 후 실제 사용자 발화 연속 5회 검증은 아직 남았다. 이 검증 전에는 음성 대화를 완료로 판정하지 않는다.

## 실행 경로

| 기능 | 주소 | 상태 |
|---|---|---|
| Ollama | `127.0.0.1:11434` | 동작 |
| AIRI LLM 호환 프록시 | `127.0.0.1:11435` | 동작 |
| GPT-SoVITS v2ProPlus API | `127.0.0.1:9880` | 동작 |
| AIRI OpenAI 호환 TTS 프록시 | `127.0.0.1:8880/v1` | 동작 |
| faster-whisper STT | `127.0.0.1:8890/v1` | 동작, 실제 마이크 사용자 검증 대기 |

현재 AIRI 설정은 다음과 같다.

- LLM 모델: `exaone-airi:2.4b`
- TTS 모델/음성: `tts-1-ko` / `airi-vtuber`
- STT 모델: `whisper-1`
- 마이크: 기본 USB Audio Device

## 이번에 해결한 TTS 문제

참조 음성 `chatterbox/voices/airi-reference.wav`는 한국어가 아니라 일본어다. STT로 확인한 실제 문장을 TTS 기본 프롬프트로 사용하고 `prompt_lang=ja`로 수정했다. 기존 `prompt_lang=ko`, `안녕하세요.` 조합은 같은 WAV를 사용하면서도 일부 출력을 사실상 무음으로 만들었다.

영문이 섞인 문장은 GPT-SoVITS의 지연 로딩 의존성 때문에 HTTP 200 이후 스트림이 끊겼다. `wordsegment`와 NLTK `averaged_perceptron_tagger_eng`를 환경에 준비했고, `gpt-sovits/start-local-stack.ps1`이 시작 시 이를 검사하고 보완한다.

`gpt-sovits/test-airi-speech.ps1`은 이제 영문+한글 혼합 문장을 보내고 다음을 모두 검사한다.

- 스트림 완결
- RIFF/WAVE 및 PCM16 형식
- 재생 시간 0.25초 이상
- RMS 0.005 이상, 피크 0.02 이상

재시작 직후 첫 요청은 모델·참조 준비를 포함해 첫 청크 8.94초였다. 런처가 새 백엔드를 시작한 경우 내부 워밍업을 완료하도록 수정했으며, 그 뒤 계약 검사는 첫 청크 1.31초, 전체 2.93초, RMS 0.033810이었다. 순차 8회와 동시 4회 추가 테스트도 모두 유효하고 들리는 WAV를 만들었다.

## 실제 AIRI UI TTS 증거

채팅 창은 follower, 메인 Stage 창은 authority/TTS host로 정상 동작했다. 정상 인코딩된 실제 채팅 턴에서 다음 순서를 관찰했다.

1. 채팅 창 `requestIngest`
2. 메인 창 `chat-orchestrator.ingest`
3. `POST http://127.0.0.1:11435/v1/chat/completions` → 200
4. `POST http://127.0.0.1:8880/v1/audio/speech` → 200
5. 48 kHz 오디오 버퍼 1.50초와 2.18초가 `running` AudioContext에 재생 스케줄

별도 브라우저 디코딩 검사에서도 206,124바이트 응답을 3.22초 오디오로 정상 디코딩했다. 즉 현재 문제는 TTS HTTP 계약이나 Web Audio 디코더가 아니다.

## AIRI 마이크 분절 패치

설치 번들의 `useVoiceInputSession`은 Silero VAD와 볼륨 폴백을 동시에 시작한다. 볼륨 폴백은 900ms 동안 레벨이 낮으면 녹음을 끝내는데, 자신이 시작한 `volume` 세그먼트뿐 아니라 `vad` 세그먼트까지 종료했다. STT 로그의 반복 0.899초 청크와 정확히 일치한다.

`patch-airi-voice-input-segmentation.ps1`은 다음 두 지점만 동일 길이로 수정한다.

- 볼륨 폴백은 `volume` 소유 세그먼트만 종료한다. VAD가 실패했을 때의 폴백 기능은 유지한다.
- HTTP 성공 후 빈 전사는 공급자 오류가 아니라 무음으로 취급한다. 실제 전송·HTTP·파싱 예외는 계속 오류다.

설치본 백업:

`%LOCALAPPDATA%\Programs\airi\resources\app.asar.backup-before-voice-input-segmentation`

패치 스크립트는 재실행해도 추가 변경하지 않는 것을 확인했다.

## 재현 명령

전체 스택 시작/종료:

```powershell
.\start-airi-local-stack.ps1
.\stop-airi-local-stack.ps1
```

GPT-SoVITS를 새로 시작하면 런처는 포트 9880을 최대 120초 기다린 뒤 참조 음성 워밍업까지 완료한다. 워밍업을 의도적으로 건너뛸 때만 `gpt-sovits/start-local-stack.ps1 -SkipWarmup`을 사용한다.

서비스와 혼합 언어 TTS 계약 검사:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\gpt-sovits\verify-local-stack.ps1
```

STT 필터 테스트:

```powershell
Set-Location .\stt
$env:PYTHONDONTWRITEBYTECODE='1'
& .\.venv\Scripts\python.exe -m unittest -v test_transcription_filter.py
```

## 다음 작업

1. 사용자가 AIRI에서 보통 크기의 한국어 문장을 한 번 말한다.
2. `stt/stt-server.out.log`에서 새 청크가 900ms에 고정 절단되지 않는지 확인한다.
3. 해당 턴의 STT → LLM → TTS → 재생을 확인한다.
4. 스피커 출력의 마이크 재입력이나 중복 응답이 없는지 확인한다.
5. 같은 검증을 연속 5회 통과한다.

사용자 발화나 전사 원문을 저장하지 말 것. 현재 STT 기본값은 디버그 오디오와 전사 텍스트 로깅을 모두 비활성화한다.
