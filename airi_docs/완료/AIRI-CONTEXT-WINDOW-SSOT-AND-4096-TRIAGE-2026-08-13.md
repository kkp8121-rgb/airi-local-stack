# AIRI context window SSoT·4096 triage (2026-08-13)

## 결론

측정·관측 및 fail-closed 배선은 완료했지만, Mi:dm `num_ctx=4096`은 **품질
PASS가 아니며 운영 승격하지 않는다. 기본값은 반드시 2048을 유지한다.** 4096은
초기 사용자 정보의 물리적 절단은 없앴지만 card/부정 귀속 실패를 해결하지 못했다.

## context SSoT와 관측성

- root는 `-NumCtx` 또는 공백이 아닌 `AIRI_NUM_CTX`를 받으며, strict 범위는
  512..32768, 기본값은 2048이다. 잘못된 환경값은 서비스 작업 전에 거부한다.
- 값은 verify-only를 포함한 모든 proxy child 경로와 warmup에 전달된다. live health가
  다르면 fail-closed이며 root 요약에도 표시된다. child 재사용은 health `num_ctx`를
  검증하고 `exit`가 아닌 `return`으로 복귀해 root가 계속 실행한다.
- proxy `/health.prompt_budget`은 prompt 내용을 저장하지 않는 숫자형 terminal-sampled
  telemetry다. 설정값 2048, 임계값 `num_ctx-8=2040`, prepared/terminal/saturation
  counter 및 마지막 message 수·input 문자수·prompt_eval·utilization을 제공한다.
  character evaluator의 2048은 별도 설정이다.
- live fail-closed 확인: invalid `AIRI_NUM_CTX`는 서비스 작업 전에 거부됐고, live
  2048 proxy 재사용에 4096 요청은 정확히 거부됐다. live는 2048로 유지됐다.
  malformed 또는 fractional health `num_ctx`도 정확히 거부된다.

## raw 4096 Mi:dm A/B

동일 fixture/runner, temperature 0, seed 42, 압력 4단계×3회로 실행했다. 모델 digest는
`92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f`.

- 보고서: `ollama-proxy/eval/results/model-llm-context-midm-4096-2026-08-13.json`
  (30,609 B, SHA-256 `542B0632765F10B8807C76EE2EC451383414A4F0CD99B995095B3AED01D316ED`)
- complete/schema first-pass 12/12, retry 0, exact 0/12 FAIL.
- p0/p1/p2/p3 prompt P50은 1139/1547/2159/3587. active card 0/12, 부정 0/12;
  초기 사용자 12/12, 초기 assistant는 3/3·0/3·0/3·2/3, 정정/tail은 12/12였다.
- 2048의 p2/p3 2042 ceiling 및 초기 사용자 소실은 해소됐지만 card/부정 attribution은
  해결되지 않았다. card 중복이나 fixture 약화는 하지 않았다.

## GPU·live 관측

- GPU monitor 33 samples, 00:36:56.280–00:37:07.423 KST: used 5148..7482 MiB,
  free 543..2877 MiB, util 23..99%. `ollama ps`는 Mi:dm 100% GPU·context4096을
  보인 뒤 사라졌다. paired/live 관측일 뿐 clean B0 capacity proof가 아니며 최소
  543 MiB 여유는 운영 승격에 너무 작다.
- 새 live proxy PID 28404는 2048이다. root 재사용 요약은 NumCtx2048, Warmup200,
  STT off/disabled, TTS ok, extraction/moderation off, digest pinned다. 비변경
  synthetic local-quality-probe 1턴은 정직한 2회 시도: prepared 0→2, terminal
  0→2, saturation 0, 마지막 prompt_eval 1136/utilization .554688/message 3/input
  chars 1366. 개인 memory를 읽거나 쓰지 않았고 pending_total 1190만 관측했다
  (전후 동일이라고 주장하지 않음). `ollama ps`는 Mi:dm only·context2048이었다.

## 검증 범위와 다음 조건

- 현재 worktree: root config 17 pass; `ollama-proxy/test_ollama_proxy.py`는
  **286 passed / 377 subtests / 5 warnings** (2.23s), API shard는 **323 passed /
  569 subtests**다. PS parser, `py_compile`, diff check도 PASS다. Python 3.12 41-path
  matrix는 **833 passed / 1 skipped / 708 subtests / 7 warnings** (64.98s) PASS다.
  historical 829는 base `aef5300`에만 해당한다.
- raw gate는 proxy/Electron/memory end-to-end가 아니다. telemetry는 실제 terminal
  row만 관측하므로 정상적으로 일찍 닫힌 stream에는 terminal sample이 없을 수 있다.
- 남은 작업은 production-path deterministic context gate, holdout/continuity ledger
  또는 더 나은 모델, 인간 100건 검수다.
