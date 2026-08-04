# 다음 세션 인수인계

## 가장 중요한 현재 판정

사용자의 실제 마이크 음성 대화는 아직 실패한다. 준비한 WAV 파일을 STT API로 직접 전사한 성공 기록을 실제 마이크 성공으로 보고하지 말 것.

사용자 기대 동작은 Neuro-sama처럼 보통 크기의 한국어 발화를 거의 즉시 이해하고 한 번만 답하는 것이다. 현재 로컬 경로는 짧은 오디오 조각, 빈 전사, 반복 환각 때문에 이 기준에 미달한다.

상세 증상과 수치는 `AIRI-VOICE-INPUT-ISSUE-2026-08-05.md`에 있다.

## 현재 동작하는 경로

- AIRI 0.11.3 실행
- Ollama `exaone-airi:2.4b`
- Ollama 호환 프록시 `127.0.0.1:11435`
- Chatterbox Multilingual TTS `127.0.0.1:8880`
- 선택 음색 A-C00, 로컬 참조 파일 `chatterbox/voices/airi-reference.wav`
- 텍스트 입력 → LLM 응답 → TTS → Live2D 립싱크
- happy/sad/surprised 표정 토큰
- 같은 STT 서버에 한국어 WAV를 직접 보내는 파일 전사

## 현재 AIRI 설정

- LLM: OpenAI Compatible, Base URL `http://127.0.0.1:11435/v1/`
- LLM 모델: `exaone-airi:2.4b`
- TTS: OpenAI Compatible, Base URL `http://127.0.0.1:8880/v1/`
- TTS 모델: `tts-1-ko`
- TTS 음성: `airi-vtuber`
- STT: OpenAI Compatible, Base URL `http://127.0.0.1:8890/v1/`
- STT 모델: `whisper-1`
- 마이크: `Default - 마이크(USB Audio Device) (1b3f:2008)`
- 자동 전송: 켜짐, 2초
- 설정 화면의 모델 기반 VAD: 켜짐/로드 완료로 표시

위 AIRI UI 설정은 앱의 로컬 사용자 데이터에 저장되며 Git에는 포함되지 않는다.

## 다음 작업 우선순위

1. 실제 마이크 발화가 담긴 AIRI 녹음 조각을 안전하게 확보한다.
2. 발화가 0.8~1.6초로 분리되는 지점을 AIRI 캡처/VAD와 STT 서버 사이에서 분리 진단한다.
3. 배치형 faster-whisper 대신 저지연 한국어 스트리밍 STT 후보를 비교한다.
4. 스피커 출력의 마이크 재입력을 차단한다.
5. 실제 사용자 발화로 연속 5회 정확히 인식·응답할 때만 완료 처리한다.

TTS 음색이나 LLM 페르소나 튜닝은 이 문제보다 우선하지 않는다.

## 실행 파일

- 전체 로컬 서비스 시작: `start-airi-local-stack.ps1`
- 전체 로컬 서비스 종료: `stop-airi-local-stack.ps1`
- STT 서버: `stt/openai_stt_server.py`
- LLM 호환 프록시: `ollama-proxy/ollama_proxy.py`
- Chatterbox OpenAI 호환 TTS: `chatterbox/openai_server.py`

## 제외된 로컬 자산

- 모든 개인/추출/생성 음성 파일
- Chatterbox 및 Whisper 다운로드 모델
- `.venv`와 캐시
- 진단 로그와 화면 캡처

이 파일들은 현재 PC에는 남아 있지만 원격 저장소에는 올라가지 않는다.

