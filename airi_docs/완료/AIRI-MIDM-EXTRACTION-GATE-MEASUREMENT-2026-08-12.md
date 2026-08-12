# Mi:dm 기억 추출 게이트 실측 (2026-08-12)

## 재현 조건

- 후보: `midm-airi:2.0-mini`
- digest: `92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f`
- 격리 Ollama: `127.0.0.1:11436`, `OLLAMA_NUM_PARALLEL=1`,
  `OLLAMA_MAX_LOADED_MODELS=1`, CPU (`num_gpu=0`)
- 게이트: `balanced`, 7 fixtures, cloud 비허용, 요청 timeout 120초
- 원시 리포트: `ollama-proxy/runtime/extraction-gate-report.json`
  (runtime 산출물이라 Git에는 포함하지 않음)

```powershell
python ollama-proxy\benchmark_memory_track.py --mode extraction `
  --model midm-airi:2.0-mini `
  --model-digest 92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f `
  --ollama-url http://127.0.0.1:11436/api/chat --timeout 120 `
  --gate-profile balanced `
  --report ollama-proxy\runtime\extraction-gate-report.json
```

## 결과

**FAIL. 운영 추출은 자동 활성화하지 않는다.** 스키마 구조는 통과했으나
내용 판단과 Stage B 연결이 기준에 크게 못 미쳤다.

| 지표 | 실측 |
|---|---:|
| Stage A/B schema pass | 1.0 / 1.0 |
| connectivity | 0.7143 |
| Stage B coverage | 0.4286 |
| critical recall | 0.2619 (balanced 최소 0.7) |
| placeholder rate | 0.8571 (최소 0.85) |
| Stage B op alias accuracy | 0.1429 (최소 0.8) |
| unexpected | 11 |
| Stage A unexpected | 11 |
| Stage A latency P50/P95 | 9,580 / 18,696 ms |
| Stage B latency P50/P95 | 10,610 / 15,531 ms |
| total latency P50/P95 | 20,190 / 34,163 ms |

독립 verifier는 `EXTRACTION_GATE_GATE_NOT_PASSED`로 거부했다. 실패 코드는
`decision_coverage=1`, `entity_reference_ambiguous=1`,
`noop_candidate_mismatch=2`였다. 모든 요청은 120초 안에 끝났으므로 현재
병목은 timeout이 아니라 추출 품질과 20초급 CPU 지연이다.

## 판정과 후속

Mi:dm 2.0-mini도 기존 EXAONE/Qwen 후보와 마찬가지로 I1 승격 후보가 아니다.
실패 리포트가 있어도 root 런처의 fail-closed 검증은 이를 거부하고
`memory.extraction_enabled=false`를 유지해야 한다. 다른 후보 모델을
선정한 뒤 같은 digest-bound 절차를 반복한다. 기준을 낮추거나 실패
리포트를 운영에 강제 주입하지 않는다.
