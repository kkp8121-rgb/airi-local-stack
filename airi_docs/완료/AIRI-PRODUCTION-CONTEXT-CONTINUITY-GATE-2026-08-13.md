# AIRI production-context continuity gate — 2026-08-13

## 목적과 권위 범위

이 문서는 실제 AIRI proxy의 context 조립 경로가 긴 합성 이력에서도 원문 대화나 임의 값을 지속하지 않고, 순서가 정해진 축약 입력을 Ollama native payload로 내보내는지 측정한 권위 결과다. 결과는 **완료 / FAIL**이다. 구현·측정 체크는 닫지만 모델 품질 통과나 운영 context 승격을 뜻하지 않는다.

이는 raw Ollama capacity A/B(2048/4096)의 대체물이 아니다. 그 A/B가 물리적 수용량과 모델 반응을 측정했다면, 본 게이트는 production shaping 뒤의 native 요청과 그 요청의 필드 귀속을 측정한다.

## 구현된 변환 경로와 불변식

원본 요청 메시지 → 순수 연속성 snapshot 또는 명시 session의 지속 ledger → foreground projection → memory assembler → active card·continuity ledger·request-local state 삽입 → latest user를 마지막에 둔 native Ollama payload 순서다.

- ledger는 유한한 key→value enum의 엄격한 ASCII assignment/retract와 유한 noun allowlist의 한국어 1인칭 반려동물 소유 polarity만 해석한다. 임의 key·opaque value·비밀/지시문 형태는 거부하고 원문 transcript는 보관하지 않는다. rolling signature상 exact replay 또는 append-only 확장만 허용하며, 동등/더 긴 분기는 상태를 비우고 fail-closed한다. bounded LRU·`RLock`·content-free counters와 bounded tombstone으로 퇴출 직후의 오래된 재생도 차단한다. tombstone이 다시 LRU 퇴출된 뒤까지 영구 차단한다고 주장하지 않는다.
- ledger 지속은 명시 session header가 있을 때만 허용하며, header가 없으면 해당 요청의 순수 ledger snapshot만 쓴다. 이 문장은 기존 implicit memory/character session 동작까지 stateless라고 주장하지 않는다. 별도로 본 평가 하네스의 frozen snapshot seam은 `MemoryRuntime`/store/DB/I/O를 사용하지 않는다.
- character-state prompt에는 raw `current_topic`/`last_question`뿐 아니라 evaluator가 원문을 복사할 수 있는 model-owned 자유 텍스트·list를 넣지 않는다. active card는 전용 typed message 한 번이며 private `name`은 native 변환에서 제거한다.
- static prefix 뒤에 projected history, frozen memory, active card, canonical continuity ledger, request-local state를 차례로 두고 latest user를 마지막에 둔다.

## 실행·provenance

```powershell
python ollama-proxy\eval\run_airi_production_context_gate.py `
  --model midm-airi:2.0-mini --runs 3 --num-ctx 2048 --num-gpu 999 `
  --temperature 0 --seed 42 --num-predict 128 --keep-alive 5m `
  --output ollama-proxy\eval\results\airi-production-context-gate-midm-2048-2026-08-13.json `
  --fail-on-gate
```

보고서: 72,402 B, SHA-256 `FDACB97B8DD2F383B7EDDB56FCDCCB32C5093A104B665190ADD4F76981D81F30`. Ollama `0.32.6`, model `midm-airi:2.0-mini`, digest `92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f`이다.

| provenance | SHA-256 |
|---|---|
| fixture | `92fd7d0eb190b59cef2da8ccc947a05ce0c34a73494cca86f620aff7c2cc67ab` |
| fixture file | `15628cf32deb737a9d3aac1e86924efe37d9ea3e76c47fda7148ee325e79a251` |
| runner | `dafe904292c0042bb2de3b765e0bbd806821aeb86401e87186b42d8b885eca03` |
| `ollama_proxy.py` | `5ead00816546dddf8af8c6f945887195df742bb95f9cf5fad034bb9a650cf32d` |
| `memory_runtime.py` | `6bee09e886aac7d6609f3e96413aaaee71da40c9e685ac590b8b59bae54f9531` |
| `airi_memory.py` | `1d2f4ca6301e0ed0e41020dcc22c03fda27cca8f8de3ae964e1e591f87aef965` |
| `foreground_context.py` | `455f50cbbaf786b83da57edd4f3c15293977667529300da4d2dd8c593b6dde5c` |
| `continuity_ledger.py` | `b1129d01dd0aaf98db90d2a99dd7790cbc6d303e836f27f77f937c8b963fc4f1` |
| `character_state.py` | `a5d5e933dbf510f03fed451e448a840ee166550c58cc9608ff5aae525d0541e1` |

정확히 압력 `0/8/20/48` filler pair 각각 3회(총 12회), `num_ctx=2048`, `num_gpu=999`, temperature `0`, seed `42`, `think=false`로 실행했다. 관측상 재시도는 0회이며 모든 호출의 `prompt_eval_count`는 정확히 1435였다.

## 결과

| 축 | 결과 |
|---|---|
| 구조 | PASS — 모든 pressure의 최종 full native payload hash가 동일, 원본 입력 불변 |
| 제거·순서 | PASS — 0..48 old filler pair와 dropped holdout 부재, prepared/native role·순서, private-name strip, active card 1회, latest user 최후 모두 통과 |
| 의미 | FAIL — `bridge_fact` 0/12; 모델이 주로 bridge marker가 아니라 `silver-fern`을 복사 |
| 나머지 의미 필드 | active card, Korean pet negation, tail memory, dropped holdout은 각 12/12. continuity fact/latest correction은 각 11/12 |
| 결정성 | raw/parsed output 모두 비결정적 — 첫 0-pressure run에서 두 continuity 필드에 key prefix를 붙임 |
| 시간 | total P50 `869.495 ms`, P95 `3339.170 ms` |

구조 PASS는 prompt 조립의 증거일 뿐 답변 품질 PASS가 아니다. `bridge_fact` 0/12에 더해 continuity fact/latest correction도 각 11/12이므로 전체 semantic/gate 결과는 엄격하게 FAIL이다. 따라서 full quality pass라고 부르지 않으며, context/`num_ctx`를 승격하지 않는다. 운영 기본값은 **2048**로 유지한다.

## 검증 한계와 후속

- authoritative CI-equivalent Python 3.12.13 exact workflow path matrix(신규 `test_continuity_ledger.py`와 `eval/test_airi_production_context_gate.py` 포함)는 **855 passed / 1 skipped / 7 warnings / 708 subtests, 44.67s PASS**다. 최종 continuity hardening 뒤 focused 테스트도 29건 PASS했고 독립 재검토는 blocker 0으로 끝났다. 별도로 Python 3.14 unittest discovery에서는 이미 알려진 환경/타이밍 오류 `test_first_raw_watchdog_closes_response_when_send_already_completed`가 남아 682개 중 681개만 통과했으므로, 이 환경 결과를 전체 검증 실패 원인으로 확대 해석하지 않는다.
- CI는 push 전이므로 pending이다. extraction은 설치 후보가 모두 gate FAIL이라 OFF를 유지한다. STT/실제 mic은 사용자 재개 요청까지 보류다.
- 다음 remediation은 모델이 bridge와 memory 필드를 구별해 binding하도록 prompt/schema·표현을 좁히고, 동일 고정 4×3 production gate를 다시 실행하는 것이다.
