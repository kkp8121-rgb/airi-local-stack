# AIRI Kanana-2-3B 추출 후보 — 공식 원본 기반 자체 변환·격리 CPU 스모크 (2026-08-13)

## 결론

Kanana-2-3B도 운영 추출에 사용하지 않는다. 공식 체크포인트를 직접
Q4_K_M GGUF로 변환한 `kanana-airi-extraction:3b-q4_k_m`은
`persistent_trait` balanced smoke에서 JSON schema와 connectivity는 통과했지만,
critical recall 0, Stage B coverage 0, unexpected 1, op/alias accuracy 0으로
fail-fast FAIL했다. 전체 7 fixtures는 의도적으로 실행하지 않았고 extraction은
계속 off다.

## 공식 원본과 변환 provenance

- 원본: Kakao [`kakaocorp/kanana-2-3b-instruct`](https://huggingface.co/kakaocorp/kanana-2-3b-instruct/tree/6a5d7889964c4c590299d16e309eabab1f73f8a9),
  commit `6a5d7889964c4c590299d16e309eabab1f73f8a9`.
- BF16 shard SHA-256:
  `879FD56F37B7452F34208EA99BE40AC2C8EBCD36DB636FE953303A753314171D`
  (4,962,632,064 B),
  `76D38F1E8AFF33A43FE038888B9C041CEC6D6CBFE735E3368BCEA3536B11F186`
  (2,055,352,808 B). 두 값은 공식 Git LFS oid와 일치한다.
- Ollama 0.32.6의 Safetensors 직접 import는
  `unsupported architecture "Qwen3ForCausalLM"`로 실패했다. 이 실패는 모델
  품질 판정에 사용하지 않았다.
- 자체 변환기는 llama.cpp release `b10375`, commit
  `ba360efe1f574ebae727aad64112d18ecedca85a`의 clean checkout이다.
  `convert_hf_to_gguf.py` SHA-256은
  `21B70F59D9CFA5F3963BFE9B1C648C16B1FDECA9CFF67778BF776D1137B267B5`다.
  같은 release의 Windows CPU zip
  SHA-256은 `C18AD6AA9CEF9D119E957472D71E34EB5183848EB9C57F51647FD18692A456C7`로
  GitHub release digest와 일치하며 여기서 `llama-quantize.exe`를 사용했다.
  변환은 llama.cpp의
  [GGUF/quantize 절차](https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md)를
  따랐다.
- BF16 GGUF: 7,023,719,904 B, SHA-256
  `2613368AF347BBED8DFEF968CFEDC7449E117A82C28FFB5C3DDA8C41EAAE8E3C`.
- Q4_K_M GGUF: 2,161,793,504 B, SHA-256
  `A676F57850BDFE6A016FA1991067B3F81B6CCB16E2CE4EE7DC454F1300DEB77B`.
  Ollama tag digest는
  `4a1d0b3322b50ffe5b16990129ab14f46abe1835e9b871e2b42a5ed144f65b9a`다.
  이는 416 B manifest의 SHA-256이다. manifest의 유일한 model layer가 Q4_K_M
  파일과 같은 SHA-256/2,161,793,504 B를 가리키며, 저장소 blob도 다시
  해시해 일치시켰다.
  `/api/show`는 qwen3, 3,508,972,032 parameters, Q4_K_M, context 32,768과
  공식 10,725자 chat template를 확인했다.

정확한 원본 metadata/tokenizer, converter module/requirements, Python 의존성,
변환·양자화(`imatrix` 없음)·Ollama create 명령, Modelfile 및 manifest→blob
연결은
`ollama-proxy/eval/results/extraction-gate-provenance-kanana-2-3b-q4km-2026-08-13.json`에
고정했다. 이 파일은 6,251 B, SHA-256
`CB80B8BA5FD2F8C5F9420CBBC09632BFCFB2358C41A2AC7A8AA49B1091D8D5E3`이다.
공식 원본 설정의 YaRN factor 40.0은 임의 수정하지 않았고, 변환 시 나온
context-ratio 및 tokenizer-regex 안내도 provenance에 보존했다.

제3자 Q8_0 tag는 이번 변환·실행·측정에 사용하지 않았다.

## 스모크 결과

11436 전용 Ollama에서 `num_gpu=0`, `num_ctx=8192`, parallel/max-loaded=1,
`temperature=0`, `seed=42`, `think=false`, `max_tokens=2048`, Stage A
`conversation-v2b`, Stage B `decision-v2.1`, cloud disabled로 실행했다.

| 지표 | 결과 |
|---|---:|
| schema / Stage A schema / Stage B schema | 1.0 / 1.0 / 1.0 |
| connectivity / Stage B coverage | 1.0 / 0.0 |
| critical recall / unexpected | 0.0 / 1 |
| placeholder / op-alias accuracy | 1.0 / 0.0 |
| Stage A / Stage B / total | 14,894.226 / 9,821.551 / 24,715.938 ms |

실패 코드는 `decision_coverage`; `stage_b_count=0`이다. 추적 리포트
`ollama-proxy/eval/results/extraction-gate-smoke-kanana-2-3b-q4km-2026-08-13.json`은
4,505 B, SHA-256
`C7A54FAF8DCCB9E240EB1CD9C951A247888906F48A36428B4FB4765ED3A472D8`이다.
partial smoke이므로 결과와 무관하게 운영 verifier 입력이 될 수 없다.

## 라이선스·운영 경계와 복구

고정 원본의 [Kanana Open License](https://huggingface.co/kakaocorp/kanana-2-3b-instruct/blob/6a5d7889964c4c590299d16e309eabab1f73f8a9/LICENSE)는
로컬 사용·수정 근거를 제공하지만, 이것만으로 공개·수익 방송 사용이 승인된
것은 아니다. §2.2 Responsible AI 준수, §3.1 재배포/공개 관련 Notice와
`Powered by Kanana` 표시, §4.1 제3자 원격 접근 상업 라이선스와 §4.2 자체
서비스 예외가 각각 적용될 수 있다. 대화형 공개 방송이 어느 범주인지 이
기술 검증만으로 확정할 수 없으므로, 법률 검토 또는 Kakao의 서면 확인 전에는
운영 승격하지 않는다. 표시·Notice만으로 충분하다고 해석해서도 안 된다.
Outputs는 라이선스상 Derivative Works가 아니며 Kakao가 권리를 주장하지 않지만,
출력과 사용 책임은 운영자에게 있다. 이번 산출물은 로컬 후보 검증 전용이다.

실행 후 CPU runner를 내리고, 소유권을 확인한 격리 Ollama PID 23212만 종료했다.
11436과 STT 8890은 listener가 없고 8880/9880/11434/11435는 유지됐다.
운영 `/health`는 Mi:dm digest pin verified,
`memory.extraction_enabled=false`, `memory.extraction_ready=false`,
external extraction false다. 통과 후보가 없으므로 MEM-04 활성 추출 락 경합과
다음 세션 콜백 실측도 계속 보류한다.
