# AIRI B3-d persona-jailbreak marker corpus

## 판정

20-case corpus와 direct local Ollama 사전 선별 runner는 완료했다. Mi:dm 결과는
structural 20/20 PASS지만 exact standalone marker contract가 5/20 PASS라서
overall FAIL이다. 이는 semantic safety gate가 아니며 설치 Electron red-team도
아니다.

## corpus와 runner

- 언어: Korean, English, Japanese, Chinese
- category: benign, direct jailbreak, indirect injection,
  profanity/harassment, sexual explicit — 정확한 4×5 matrix
- punctuation/zero-width 및 code-switch variant 포함
- 각 prompt는 SHA-256으로 고정되며 보고서에는 prompt/response 원문을 쓰지 않는다.
- literal loopback `/api/tags`, `/api/show`, `/api/chat`만 사용하고 exact model tag와
  64-hex digest를 검증한다. think=false, temperature=0, seed=42,
  num_ctx=2048로 실행한다.
- report는 fixture bytes/canonical, runner, system prompt, model digest를 묶는다.
  평가는 독립 marker 존재/부재 계약뿐이며 `semantic_safety_claim=false`다.

## fresh Mi:dm 결과

보고서:
`ollama-proxy/eval/results/airi-persona-jailbreak-marker-midm-2026-08-13.json`

- bytes: 14,395
- SHA-256: `9308b0c1527eaf42b58496bd3c36520feabeaa38c70623139981357cb65509c8`
- model: `midm-airi:2.0-mini`
- digest: `92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f`
- structural: 20/20 PASS
- standalone marker: 5/20 PASS
- overall marker gate: FAIL
- wall-clock P50/P95/max: 211.371/809.552/928.064 ms

이 실패를 낮은 threshold나 별칭 처리로 승격하지 않는다. 특히 report는 model이
실제로 안전하게 거절했는지, 프록시 input screen이 차단했는지, 설치 UI/TTS가
어떻게 반응했는지 증명하지 않는다.

## 검증과 남은 gate

- runner offline tests: 9 PASS
- 독립 최종 검토: PASS
- Python full suite/checkpoint 결과는 B3-c 완료 문서와 동일하다.
- 남은 작업은 설치 Electron 대상 red-team 실행, human semantic review,
  B3-e category별 UI/TTS 반응 실기다.
