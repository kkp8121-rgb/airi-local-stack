# AIRI 신규 로컬 추출 후보 게이트 — 격리 CPU 실측 (2026-08-12)

## 결론

신규 후보도 **운영 추출을 활성화하지 않는다.** `qwen3.5:4b-q4_K_M`와
`granite4:3b`는 첫 balanced smoke 행에서 fail-fast로 실패했고,
`gemma3:4b`는 동일 smoke 행은 통과했으나 7-row balanced full gate에서
실패했다. 독립 verifier도 Gemma full report를 거부했다. 세 tag는 로컬에
설치된 후보일 뿐 운영 모델이 아니다.

검증은 11436 격리 CPU Ollama에서만 수행했다. 모든 실행은 `num_ctx=8192`,
`num_gpu=0`, `temperature=0`, `seed=42`, `max_tokens=2048`, `think=false`,
Stage A `conversation-v2b`, Stage B `decision-v2.1`, local-files-only,
cloud disabled 조건이다.

## 후보별 결과

표의 tag·digest·크기는 같은 시점의 `/api/tags` 관측을 정규화한 아래 runtime
recovery artifact를 근거로 한다.

| 후보 | 식별 / 크기 | 결과 |
|---|---|---|
| Qwen3.5 | `qwen3.5:4b-q4_K_M`; digest `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`; 3,389,983,735 B | `persistent_trait` balanced smoke FAIL: recall 0, unexpected 1, alias 0; total 25,696.794 ms. fail-fast라 full은 의도적으로 생략. |
| Gemma 3 | `gemma3:4b`; digest `a2af6cc3eb7fa8be8504abaf9b04e88f17a119ec3f04a3addf55f92841195f5a`; 3,338,801,804 B | smoke `persistent_trait`는 quality/structure 모두 PASS, total 24,853.690 ms. 그러나 full 7-row balanced FAIL. |
| Granite 4.0 | `granite4:3b`; digest `89962fcc75239ac434cdebceb6b7e0669397f92eaef9c487774b718bc36a3e5f`; 2,099,521,385 B | `persistent_trait` balanced smoke FAIL: schema/connectivity/coverage는 1.0이나 recall 0, unexpected 0, alias 0; total 20,067.440 ms. fail-fast라 full은 의도적으로 생략. |

Gemma full aggregate: schema/Stage A schema/Stage B schema 모두 1.0이지만,
connectivity 0.8571428571, coverage 0.7142857143, recall 0.5, unexpected 5,
placeholder 0.8571428571, Stage A recall 0.4857142857, Stage A unexpected 5,
Stage A placeholder 0.8571428571, op/alias 0.5714285714였다. failure code는
`entity_reference_ambiguous` 1건 및 `noop_candidate_mismatch` 1건이며, total
latency P50/P95는 18,653.479/35,052.365 ms다.

## 증적 고정

- `ollama-proxy/eval/results/extraction-gate-smoke-qwen35-4b-q4km-2026-08-12.json` — SHA-256 `0D093F397CAD0C455174A8ABD850EA0F88CED8AEF6C9CA602161CEC8DF8F3A56`, 4,302 B.
- `ollama-proxy/eval/results/extraction-gate-smoke-gemma3-4b-2026-08-12.json` — SHA-256 `E1F6D7DD7D860F83B9348FA20AEDEEA6A0FD368DCB3BCECC0B744719BD4E13F4`, 4,266 B.
- `ollama-proxy/eval/results/extraction-gate-candidate-gemma3-4b-2026-08-12.json` — SHA-256 `633DFBF6853AAB7371EA6F5209375D83994F6717726F19C10A2B5CB67FF9BA56`, 10,005 B.
- `ollama-proxy/eval/results/extraction-gate-smoke-granite4-3b-2026-08-12.json` — SHA-256 `357A9B0AAC7B4C15B794E5EF09775CD44B73C92945212CFC3885AB4B64656BFC`, 4,287 B.
- `ollama-proxy/eval/results/extraction-gate-runtime-recovery-2026-08-12.json` — SHA-256 `34252145B36A85A2267AFB61A1314516494F79CE9700B15B57B06373AAA35A81`, 2,214 B. `/api/tags`, `ollama ps`, 11436 listener 수 및 11435 `/health`의 최소 관측 필드만 보존한다.

위 SHA-256과 크기는 `.gitattributes`의 `text eol=lf`를 적용한 **committed
blob** 기준이다. 원래 runtime CRLF 파일과 JSON 의미는 같다.

실행 뒤 11436은 종료했다. 현재 `ollama ps`는 GPU의 `midm-airi:2.0-mini`
하나만 보이며, `/health`는 pin/verify 상태이고
`extraction_enabled=false`, `extraction_ready=false`, external extraction=false다.
여기서 마지막 값의 정확한 health 필드명은
`memory.extraction_external_approved=false`다.
이는 위 runtime recovery artifact로 고정한 복구 확인일 뿐 activation 증거가 아니다.

## 다음 후보와 provenance 경계

아래 내용은 **2026-08-12 측정 종료 당시의 경계**다. 2026-08-13에는 공식
원본 직접 변환과 격리 CPU smoke까지 완료했지만 품질 FAIL했다. 현행 판정은
`완료/AIRI-KANANA-EXTRACTION-CANDIDATE-GATE-2026-08-13.md`를 따른다.

당시 Kanana-2-3B는 한국어 후보 중 유망하지만 실행을 보류했다. Kakao 공식 배포는
BF16 Safetensors만 제공한다. Ollama 호환 GGUF는 제3자 산출물이므로, 공식 원본의
직접 변환 provenance 및 Kanana Open License의 broadcast/attribution 검토가 먼저
필요하다. 제3자 pull CLI는 의도적으로 중단했지만 Ollama 서비스가 백그라운드에서
manifest 설치를 완료해 `hf.co/dummy9996/kanana-2-3b-instruct-GGUF:Q8_0`
tag는 inventory에 남았다. 이 tag는 한 번도 runner로 load하거나 측정하지 않았다.
따라서 Kanana를 검증·승격한 것으로 해석하면 안 된다.

공식 참고: [Qwen3.5 모델](https://huggingface.co/Qwen/Qwen3.5-4B),
[Qwen3.5 Ollama tag](https://ollama.com/library/qwen3.5/tags),
[Gemma 3 model card](https://ai.google.dev/gemma/docs/core/model_card_3),
[Gemma 3 4B Ollama tag](https://ollama.com/library/gemma3%3A4b),
[Granite 4.0 Micro model card](https://huggingface.co/ibm-granite/granite-4.0-micro),
[Granite 4.0 3B Ollama tag](https://ollama.com/library/granite4%3A3b),
[Kanana-2-3B 공식 배포](https://huggingface.co/kakaocorp/kanana-2-3b-instruct),
[Ollama import 안내](https://docs.ollama.com/import).
