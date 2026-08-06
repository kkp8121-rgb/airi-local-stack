# AIRI 인수인계 문서 (2026-08-06)

## 현재 결론

- 로컬 LLM은 Ollama의 `exaone-airi:2.4b`를 사용한다.
- AIRI 호환 LLM 프록시는 `http://127.0.0.1:11435`에서 동작한다.
- STT 서버는 `http://127.0.0.1:8890`이다.
- 현재 TTS 경로는 Chatterbox가 아니라 GPT-SoVITS v2ProPlus GPU 경로다.
- TTS OpenAI 호환 프록시는 `http://127.0.0.1:8880/v1`이다.
- AIRI TTS 설정값은 모델 `tts-1-ko`, 음성 `airi-vtuber`, WAV 출력이다.

## 실행 중인 포트

| 기능 | 주소 | 확인 |
|---|---|---|
| Ollama 원본 | `127.0.0.1:11434` | 로컬 모델 백엔드 |
| AIRI LLM 호환 프록시 | `127.0.0.1:11435` | `/health` |
| GPT-SoVITS API | `127.0.0.1:9880` | `/docs` |
| AIRI TTS 호환 프록시 | `127.0.0.1:8880` | `/health`, `/v1/models` |
| STT | `127.0.0.1:8890` | `/health` |

## 최근 확인된 요청 흐름

STT 인식과 LLM 응답은 `200 OK`까지 성공했다. 과거에는 TTS도 `200 OK`와 첫 청크 약 0.7~1.4초가 확인됐다. 그러나 마지막 증상 재현 시에는 LLM 요청 뒤 새 TTS 요청이 기록되지 않았다. 따라서 현재 남은 문제는 모델 추론보다 AIRI 프론트엔드의 스트리밍 응답 전달·세션 캐시·재생 단계일 가능성이 높다.

사용자가 보고한 증상:

- 음성 대신 영어 채팅이 표시된 적이 있음
- 음성이 나와도 `데`, `헤` 같은 한 음절 또는 웅얼거림으로 들림
- 서버 로그상 새 TTS 요청이 없는 경우가 있음

## 이번 세션에서 수정했지만 아직 커밋하지 않은 파일

### `gpt-sovits/openai_compatible_proxy.py`

- GPT-SoVITS 스트리밍 생성에 전역 잠금을 추가해 동시 요청이 음성에 섞이지 않도록 했다.
- `parallel_infer`를 `False`로 변경했다.
- 참조 음성 프롬프트 텍스트 기본값은 `안녕하세요.`이다.

### `gpt-sovits/start-openai-proxy.ps1`

- 포트를 매개변수로 받을 수 있도록 수정했다.
- AIRI 현재 포트인 `8880`으로 실행 가능하다.

현재 워킹 트리에는 위 두 파일의 수정이 남아 있으므로 다음 세션에서 검토 후 커밋해야 한다.

## 다음 세션 재현 절차

1. `C:\Projects\airi\start-gpt-sovits-airi-stack.ps1` 실행
2. 필요하면 `gpt-sovits\start-openai-proxy.ps1 -Port 8880` 실행
3. 다음 주소 확인:

```powershell
Invoke-RestMethod http://127.0.0.1:11435/health
Invoke-RestMethod http://127.0.0.1:8880/health
Invoke-RestMethod http://127.0.0.1:8890/health
```

4. AIRI 제공자 설정에서 LLM은 `11435`, TTS Base URL은 `http://127.0.0.1:8880/v1`인지 확인
5. 기존 대화를 새로고침하거나 새 세션으로 시작해 짧은 문장으로 테스트
6. 테스트 중 다음 로그를 동시에 확인:

```powershell
Get-Content ollama-proxy/ollama-proxy.out.log -Wait
Get-Content gpt-sovits/proxy.out.log -Wait
Get-Content stt/stt-server.out.log -Wait
```

LLM `POST /v1/chat/completions` 직후 TTS `POST /v1/audio/speech`가 없으면 AIRI 프론트엔드 단계 문제다. TTS 요청은 있지만 음성이 웅얼거리면 프록시 직렬화 수정과 참조 음성·프롬프트를 다시 검증한다.

## STT 개인정보 주의

- STT는 기본적으로 디버그 음성 파일을 저장하지 않는다.
- `stt/start-local-stt.ps1 -EnableDebugAudio`를 명시적으로 사용할 때만 녹음 파일이 저장된다.
- 기존 `stt/debug-recordings`에는 과거 테스트 파일이 남아 있으므로, 삭제 전 사용자 확인이 필요하다.

## 후보 TTS 판단

- 실시간성과 음질의 현재 우선 후보: GPT-SoVITS v2ProPlus GPU
- GPU를 LLM에 양보해야 할 때의 후보: MOSS-TTS-Nano ONNX CPU
- MOSS ONNX는 현재 환경에서 약 4.687 RTF로 실시간 게이트를 통과하지 못했다.
- Chatterbox는 현재 AIRI 기본 경로가 아니다.

## 커밋 전 확인

```powershell
git diff -- gpt-sovits/openai_compatible_proxy.py gpt-sovits/start-openai-proxy.ps1
git status --short
```

검증이 끝나면 의미 있는 커밋 메시지로 커밋하고 원격 저장소에 푸시한다. 현재 최신 원격 관련 커밋은 `2e3aedc fix: start and verify AIRI Ollama compatibility proxy`다.
