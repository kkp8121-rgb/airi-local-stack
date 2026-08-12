# AIRI cloud chat 스트리밍 지연 실측 (진행중)

## 준비 완료

`ollama-proxy/benchmark_cloud_chat_latency.py`가 실제
`CloudChatProvider.open_stream()`/`deltas()` 경로를 반복 호출하고 run별
TTFT·전체 지연과 P50을 계산한다. prompt와 응답 본문은 저장하지 않고 prompt
SHA-256만 남기며, 키나 provider 오류 본문도 출력하지 않는다. JSON은
`--report`를 명시할 때만 생성한다.

```powershell
$env:AIRI_CHAT_PROVIDER = 'openai'
$env:AIRI_ALLOW_EXTERNAL_CHAT = '1'
$env:AIRI_CHAT_MODEL = '<approved-streaming-model>'
$env:OPENAI_API_KEY = '<credential>'
python ollama-proxy/benchmark_cloud_chat_latency.py --runs 5 `
  --report ollama-proxy/runtime/cloud-chat-latency.json
```

Anthropic은 provider와 `ANTHROPIC_API_KEY`만 바꾼다. 외부 승인, credential,
모델 중 하나라도 없으면 네트워크 전에 nonzero로 종료한다. fake SSE와 기존
provider 계약을 묶은 unit test 10건이 PASS했다.

## 잔여 게이트

dev PC 환경에는 `OPENAI_API_KEY`와 `ANTHROPIC_API_KEY`가 없고 외부 전송을
즉시 승인한 상태도 아니므로 실제 호출은 수행하지 않았다. 승인된 provider와
모델로 최소 5회 TTFT/total P50을 채운 뒤에만 방송 중 cloud LLM 결정을 다시
내린다. Codex 구독 비스트리밍 수치는 이 측정에 혼합하지 않는다.
