# 다음 세션 인수인계

## 가장 중요한 현재 판정

실제 마이크 요청은 AIRI에서 STT 서버까지 도달한다. 반복되던 약 0.899초 절단의 원인은 AIRI 볼륨 폴백의 900ms 타이머가 VAD 소유 녹음까지 종료하던 버그로 확인했고 설치본 패치를 적용했다. 다만 실제 사용자 발화 연속 5회 검증은 아직 하지 않았으므로 완료로 보고하지 말 것.

사용자 기대 동작은 Neuro-sama처럼 보통 크기의 한국어 발화를 거의 즉시 이해하고 한 번만 답하는 것이다. 패치 전 경로는 짧은 오디오 조각, 빈 전사, 반복 환각 때문에 이 기준에 미달했다. 패치 후에는 실제 사용자 발화로 개선 여부를 확인해야 한다.

상세 증상과 수치는 `AIRI-VOICE-INPUT-ISSUE-2026-08-05.md`에 있다.

## 현재 동작하는 경로

- AIRI 0.11.3 실행
- Ollama `exaone-airi:2.4b`
- Ollama 호환 프록시 `127.0.0.1:11435`
- GPT-SoVITS v2ProPlus API `127.0.0.1:9880`
- OpenAI 호환 TTS 프록시 `127.0.0.1:8880`
- 로컬 참조 파일 `chatterbox/voices/airi-reference.wav`와 정확한 일본어 프롬프트
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

1. 사용자가 보통 크기로 한국어 문장을 말하고, 패치 후 STT 청크가 더 이상 900ms 타이머에 고정 절단되지 않는지 확인한다.
2. STT → LLM → TTS → 재생을 실제 마이크 발화로 연속 5회 통과시킨다.
3. 스피커 출력의 마이크 재입력이 없는지 확인한다.
4. 실패가 남으면 개인정보 저장을 켜지 않은 상태에서 길이·RMS·피크·전사 글자 수 로그로 VAD와 STT를 분리 진단한다.
5. 그 뒤에만 저지연 한국어 스트리밍 STT 후보를 비교한다.

TTS 음색이나 LLM 페르소나 튜닝은 이 문제보다 우선하지 않는다.

## 실행 파일

- 전체 로컬 서비스 시작: `start-airi-local-stack.ps1`
- 전체 로컬 서비스 종료: `stop-airi-local-stack.ps1`
- STT 서버: `stt/openai_stt_server.py`
- LLM 호환 프록시: `ollama-proxy/ollama_proxy.py`
- GPT-SoVITS OpenAI 호환 TTS: `gpt-sovits/openai_compatible_proxy.py`
- AIRI 음성 입력 설치 패치: `patch-airi-voice-input-segmentation.ps1`

## 제외된 로컬 자산

- 모든 개인/추출/생성 음성 파일
- GPT-SoVITS, Chatterbox 및 Whisper 다운로드 모델
- `.venv`와 캐시
- 진단 로그와 화면 캡처

이 파일들은 현재 PC에는 남아 있지만 원격 저장소에는 올라가지 않는다.
