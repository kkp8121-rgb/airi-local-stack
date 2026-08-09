# AIRI latency acceptance 기록

## 범위와 한계

이 기록의 STT 입력은 사용자의 실제 마이크가 아니라 저장된 maple-stt-smoke.wav다. 따라서 음성 인식 정확도와 local service latency의 smoke 증거이지, 실제 마이크 acceptance나 실제 스피커 playback 증거가 아니다.

## 측정

- STT 8890 /v1/audio/transcriptions: 약 996.5ms
- STT 결과: 메이플스토리로 시작함
- AIRI proxy 11435 stream first content: 약 427.3ms
- AIRI proxy stream total: 약 605.1ms
- GPT-SoVITS 8880 /v1/audio/speech cold first byte: 약 6897.5ms
- GPT-SoVITS warm first byte: 약 613.3ms
- GPT-SoVITS warm total: 약 1192.9ms

TTS cold start가 첫 음성 지연의 주요 병목이다. 이 수치는 synthesis 응답의 첫 byte이며, renderer가 실제 WebAudio를 재생한 시각을 증명하지 않는다.

실제 발화 한 건에서 짧은 의미 변경 오인식이 확인된 뒤 STT 기본 beam을 1에서 3으로 올렸다. 원문과 오인식 문구는 이 문서에 남기지 않는다. 기존 large-v3-turbo/CUDA/float16 상태를 복원했고, 합성 smoke의 고유명사 시작은 유지됐다(약 2543ms). 실제 마이크 재검증은 새 입력이 필요하다.

## 모니터 상관관계

8892 snapshot의 최근 turn들은 STT만 explicit이고 LLM/TTS/playback은 heuristic으로 남아 있다. 따라서 snapshot의 서로 다른 단계 숫자를 하나의 voice turn latency로 합산하지 않는다.

## 다음 acceptance

새 자연 음성 turn을 만든 뒤, 같은 opaque round가 STT·LLM·TTS·playback 모두 explicit인지 먼저 확인해야 한다. 그 후에만 end-to-end latency를 기록한다. 전용 테스트 발화 원문은 문서에 보존하지 않는다.
