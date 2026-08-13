# AIRI 신규 로컬 추출 후보 스모크 동기화 (2026-08-13)

## 결론

신규 로컬 후보 Ministral 3 3B, Phi-4-mini, Granite 3.3 2B의 격리 CPU
`persistent_trait` 스모크는 모두 FAIL이다. 각각 단일 fixture에서 fail-fast로
중단됐으므로 full balanced gate가 아니며, 운영 verifier 입력이나 승격 근거가
될 수 없다. extraction은 계속 OFF다. 통과 extractor가 없으므로 MEM-04 활성
Stage-B commit↔foreground 락 경합 실측도 아직 시작하지 않는다.

## 고정된 추적 리포트와 측정값

모든 실행은 `num_gpu=0`, `num_ctx=8192`, `temperature=0`, `seed=42`,
`think=false`, `max_tokens=2048`, Stage A `conversation-v2b`, Stage B
`decision-v2.1`, cloud disabled였다. runtime JSON의 구조와 값을 그대로 복사한
뒤 저장소 `.gitattributes` 계약(`text eol=lf`)으로 줄바꿈만 정규화했다.

| 후보 (Ollama tag) | tag digest / installed bytes | tracked report (bytes / SHA-256) | persistent_trait 결과 | Stage A / Stage B / total |
|---|---|---|---|---:|
| `ministral-3:3b-instruct-2512-q4_K_M` | `f04aa1c738f64e13c625b82ae92504fc0260fa6723b509ed1ece0fa188179b1d` / 2,953,840,808 B | `ollama-proxy/eval/results/extraction-gate-smoke-ministral-3-3b-instruct-2512-q4km-2026-08-13.json` (4,317 B / `0722F041392E8412FE3558A61AB57D458C722D9DDD8854B97E897CC2FAE53774`) | recall 0.0, unexpected 0, coverage 1.0, alias 0.0; `gate_row_failed` | 6,279.254 / 0.000 / 6,279.349 ms |
| `phi4-mini:3.8b-q4_K_M` | `78fad5d182a7c33065e153a5f8ba210754207ba9d91973f57dffa7f487363753` / 2,491,876,774 B | `ollama-proxy/eval/results/extraction-gate-smoke-phi4-mini-3.8b-q4km-2026-08-13.json` (4,511 B / `6164D460E5BD4475FA529FF56E0E50B5DF89337DB8CB6630E8FEED6D1B3868CB`) | recall 0.0, unexpected 1, coverage 0.0, alias 0.0; `entity_reference_missing` | 12,581.758 / 6,561.909 / 19,143.804 ms |
| `granite3.3:2b` | `07bd1f170855240f9e162bf54ea494a8bc1c73d8cbd1365d7fccbeb7d2504947` / 1,545,321,637 B | `ollama-proxy/eval/results/extraction-gate-smoke-granite3.3-2b-q4km-2026-08-13.json` (4,290 B / `69AB8ECF42E68B73B4CBE14F9C9CD18D89FA0F53E0108EEACD0A7FD62901D4B2`) | recall 0.5, unexpected 1, coverage 1.0, alias 1.0; `gate_row_failed` | 9,363.652 / 4,530.782 / 13,894.634 ms |

측정 직후 runtime 원본(CRLF)의 bytes/SHA-256은 순서대로 4,443 B /
`70FAC6715F1112887BC196CC2F0209DFAAA7F83A5395983C72CFEDFEE2D8A795`,
4,643 B / `F95396B238408DC69E0140FB67F0158C58CAB93C522651B71B1AF13E9828FB36`,
4,416 B / `4ED5659D4BE6A198591D3A717D8A3FFF0F93C6BFE6DBB98F7CEE9CEFD68649CB`다.
파싱된 JSON 값은 tracked LF evidence와 동일하다.

세 후보 모두 schema·Stage A schema·Stage B schema·connectivity는 1.0,
placeholder는 1.0이다. 그러나 balanced 기준 critical recall 0.7 이상,
unexpected rate 0.25 이하, Stage-B alias 0.8 이상을 충족하지 못했다.

## 원본·라이선스 판단 범위

- [Mistral AI Ministral-3-3B-Instruct-2512-BF16](https://huggingface.co/mistralai/Ministral-3-3B-Instruct-2512-BF16)는 공식 `mistralai` 원본이며 Apache-2.0이다.
- [Microsoft Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct)는 공식 `microsoft` 원본이며 MIT다.
- [IBM Granite-3.3-2B-Instruct](https://huggingface.co/ibm-granite/granite-3.3-2b-instruct)는 공식 `ibm-granite` 원본이며 Apache-2.0이다.

이는 후보를 로컬 기술 검증에 포함할 수 있는 provenance/licence 근거일 뿐,
추출 품질·운영 승격·공개 사용 승인이 아니다. 사용자 요청에 따른 후속 정리에서
실패한 세 tag는 제거했다: `ministral-3:3b-instruct-2512-q4_K_M`,
`phi4-mini:3.8b-q4_K_M`, `granite3.3:2b`. 제거량은 공유되지 않은 고유 blob
13개, 6.511 GiB다. tracked JSON evidence는 보존한다. production 11434 서비스의
프로세스·설정과 11435 proxy 설정/트래픽은 변경하지 않았고, active model runner도
남기지 않았다. push도 하지 않았다.

## 운영 경계

격리 포트 11436은 실행 뒤 중지됐으며 active runner가 없다. production
11434/11435의 실행 설정과 요청 경로는 건드리지 않았다. `/health`의
extraction은 계속 OFF이고,
full balanced PASS가 별도로 기록될 때까지 failed weight 재실행이나 자동
활성화를 하지 않는다.
