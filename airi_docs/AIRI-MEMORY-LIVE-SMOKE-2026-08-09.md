# AIRI live memory smoke

실행 스크립트: ollama-proxy/eval/proxy_memory_smoke.py

## 결과

- same-session recall: PASS
- fresh-session no-invention prompt: PASS
- public ACT exposure: PASS (노출 없음)
- conversation_message system rows: 0
- roles remain user/assistant pairs
- first request: 153.6ms
- same-session recall request: 2319.4ms
- fresh-session absence request: 93.7ms

세션 ID, 별명 원문, 전체 응답은 보고서에 저장하지 않았다. 이 smoke는 실제 AIRI proxy와 local memory DB를 사용했으며, 실제 마이크나 renderer playback을 검증하는 테스트는 아니다.
