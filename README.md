# AIRI Korean Local Stack

Windows에서 AIRI 0.11.3을 로컬 LLM, 한국어 음성 합성, 로컬 음성 인식과 연결하기 위한 작업 저장소다.

현재 텍스트 대화, EXAONE 기반 로컬 LLM, Chatterbox Multilingual 기반 TTS, Live2D 립싱크·표정 반응은 동작한다. **실제 사용자 마이크 음성 인식은 미해결**이며 완료로 간주하면 안 된다.

## 구성

| 구성 요소 | 경로/포트 | 상태 |
|---|---|---|
| Ollama | `127.0.0.1:11434` | 동작 |
| AIRI용 Ollama 호환 프록시 | `ollama-proxy/`, `127.0.0.1:11435` | 동작 |
| Chatterbox Multilingual TTS | `chatterbox/`, `127.0.0.1:8880` | 동작 |
| faster-whisper STT | `stt/`, `127.0.0.1:8890` | 파일 입력 동작, 실제 마이크 실패 |
| AIRI 데스크톱 | 별도 설치, 0.11.3 | 텍스트/TTS/Live2D 동작 |

## 시작과 종료

```powershell
.\start-airi-local-stack.ps1
```

스택 종료:

```powershell
.\stop-airi-local-stack.ps1
```

AIRI 애플리케이션 자체는 Windows에 별도로 설치되어 있으며 위 스크립트와 별도로 실행한다.

## 다음 세션이 먼저 읽을 문서

1. `NEXT-SESSION.md`
2. `AIRI-VOICE-INPUT-ISSUE-2026-08-05.md`
3. `airi-setup-codex-2026-08-04.md`

## Git에 포함하지 않는 항목

개인 음성 원본·추출 음원·생성 샘플, 다운로드 모델 가중치, Python 가상환경, 로그와 화면 캡처는 의도적으로 제외한다. 현재 PC의 로컬 파일은 삭제하지 않으며 실행에는 계속 사용할 수 있다. 새 PC에서 복원할 때는 모델과 개인 음성 참조 파일을 다시 준비해야 한다.

## 제3자 소스

이 저장소에는 작업 당시 사용한 세 프로젝트의 소스 스냅샷과 로컬 수정이 포함된다. 원본 저장소와 기준 커밋은 `THIRD-PARTY-SOURCES.md`에 기록했다. 각 프로젝트의 라이선스 파일을 유지한다.

