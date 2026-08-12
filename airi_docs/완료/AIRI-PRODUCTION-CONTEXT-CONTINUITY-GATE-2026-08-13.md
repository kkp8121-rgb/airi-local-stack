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

보고서 version 2.0: 73,737 B, SHA-256 `2D1F3B03DA5A704F01E279AF000B19D798DCB91B3EFBE750243CD094F1B2AEC2`. Ollama와 Mi:dm digest pin은 v1과 동일하다.

| provenance | SHA-256 |
|---|---|
| canonical fixture | `543e581b19d6b35f4116a5d984f3b72552e83a2505c9519057529ea5dc1950ab` |
| fixture file | `73e3a63d920c6b495e648425571221704477a5622263f2b4181c1560628d661d` |
| runner | `bb52b9b41a470308b162b9db076f67cf7e028950aa657e93459b0f3bc869c297` |
| `ollama_proxy.py` | `af67b573c71792c24aca096956d2c3c36486edffb9fbd2f0c4bab6bcced96a22` |
| `memory_runtime.py` | `6bee09e886aac7d6609f3e96413aaaee71da40c9e685ac590b8b59bae54f9531` |
| `airi_memory.py` | `1d2f4ca6301e0ed0e41020dcc22c03fda27cca8f8de3ae964e1e591f87aef965` |
| `foreground_context.py` | `455f50cbbaf786b83da57edd4f3c15293977667529300da4d2dd8c593b6dde5c` |
| `continuity_ledger.py` | `b1129d01dd0aaf98db90d2a99dd7790cbc6d303e836f27f77f937c8b963fc4f1` |
| `character_state.py` | `a5d5e933dbf510f03fed451e448a840ee166550c58cc9608ff5aae525d0541e1` |

정확히 압력 `0/8/20/48` filler pair 각각 3회(총 12회), `num_ctx=2048`, `num_gpu=999`, temperature `0`, seed `42`, `think=false`로 실행했다. 관측상 재시도는 0회이며 모든 호출의 `prompt_eval_count`는 정확히 1245였다.

## 결과

| 축 | 결과 |
|---|---|
| 구조 | PASS — 모든 pressure의 최종 full native payload hash가 동일, 원본 입력 불변 |
| 제거·순서 | PASS — 0..48 old filler pair와 dropped holdout 부재, prepared/native role·순서, private-name strip, active card 1회, latest user 최후 모두 통과 |
| 의미 | FAIL — 7개 필드 중 `dialogue_marker`만 0/12; 모델이 memory marker `silver-fern`을 결정적으로 복사 |
| 나머지 의미 필드 | 나머지 6개 필드는 각 12/12; 두 continuity color 필드는 v1의 11/12에서 개선 |
| 결정성 | raw/parsed output 모두 결정적 |
| 시간 | total P50 `1714.961 ms`, P95 `3962.483 ms` |

v2는 spoken style 충돌을 제거한 generic structured-output 계약, source-oriented fields, 답 canary가 없는 현재 질문, swapped/reordered offline anti-overfit test를 사용한다. structured-output 전환은 언어·문체 문단만 제거하고 character-state·knowledge 근거는 보존한다. 구조 PASS는 prompt 조립의 증거일 뿐 답변 품질 PASS가 아니다. 두 continuity color 필드는 v1의 11/12에서 12/12로 개선됐고 parsed output도 결정적으로 안정됐지만, `dialogue_marker` 0/12가 memory marker `silver-fern`을 복사하므로 semantic/gate/authoritative 결과는 엄격하게 FAIL이다. 이는 dialogue-vs-memory 구분의 모델 한계다. prompt tuning을 계속하거나 full quality pass라고 부르지 않으며, context/`num_ctx`를 승격하지 않는다. 운영 기본값은 **2048**로 유지한다.

## 검증 한계와 후속

- v2 전체 CI-equivalent Python 3.12.13 matrix는 **858 passed / 1 skipped / 7 warnings / 708 subtests, 45.04s PASS**다.
- 첫 커밋과 CI는 성공했다. 이 v2 batch는 아직 커밋/CI 실행 전이다. extraction과 설치본 STT는 OFF를 유지하며, 실제 mic은 사용자 재개 요청까지 보류한다.
- `dialogue_marker`는 현 prompt/schema 개선의 범위를 넘는 모델 한계로 결론냈다. 추가 prompt tuning은 하지 않는다.
