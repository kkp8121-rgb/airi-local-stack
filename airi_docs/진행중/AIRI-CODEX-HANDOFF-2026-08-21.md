# AIRI Codex GPU 인수인계 — broadcast continuity v4

갱신: 2026-08-21 KST

상태: **v4 corpus 확정, E1 QLoRA 완료, E2 사용자 요청으로 중단, T3 런처 검증 완료·실측 미실행**

운영 채택: **금지** (`adoption_authorized=false`, `t3_status=pending`)

이 문서가 다음 Codex/Claude PC 세션의 GPU 작업 단일 진입점이다. 이전
`AIRI-CODEX-HANDOFF-2026-08-20.md`의 방송 학습 진행 상태를 대체하되,
그 문서의 greybox·추출 게이트 이력은 과거 근거로 보존한다.

## 1. 반드시 지킬 상태

- 현재 서비스 모델이나 기본 태그를 v4로 바꾸지 않는다.
- 외부 chat/search, 기억 추출, greybox는 계속 OFF다.
- E1/E2는 실제 11435 live-context T3와 사용자 승인 전까지 후보일 뿐이다.
- 모델 weight, adapter, GGUF, report, 로그는 `D:\AIRI-Models`에만 두고 Git에
  넣지 않는다.
- T3 baseline/candidate는 동일 fixture, seed, memory arm, contract, history,
  max tokens, proxy flags, isolated memory/knowledge DB로 실행한다.
- 단일 seed, raw Ollama 직결, caller system prompt, summary-only 결과는 근거로
  인정하지 않는다.

## 2. 확정된 v4 corpus

파일:

- `ollama-proxy/training/seed/airi_broadcast_continuity_v4.jsonl`
- `ollama-proxy/training/seed/airi_broadcast_continuity_v4_chat.jsonl`
- `ollama-proxy/training/synthesize_broadcast_continuity_v4.py`
- `ollama-proxy/training/tests/test_synthesize_broadcast_continuity_v4.py`
- 40개 author card partition (`..._cards_m01..m16`, `c1/c2/c3a/c3b`,
  `d01..d10`, `g1/g2a/g2b/g3`, `n1/n2/n3a/n3b`)

고정값:

- source SHA-256:
  `43f9c1ed1abf1d32c94329de81d8ba9ddef93f560ef914814d34e0520eeba2ed`
- chat SHA-256:
  `96cc223ca5915355394480b60b459d9d039ffad4b47304974c5d939d4686eb44`
- 1,000행, train/dev/test `800/100/100`
- family: memory known 256, memory unknown 64, donation 180,
  briefing/topic 250, grounding/capability 130, natural broadcast 120
- 교차 split fact/update/decoy token 충돌 0
- `v4-v4-` ID 0, replacement character 0, source/chat target 불일치 0
- exact trainer token 수: all max 2,010, train max 2,010;
  `>2016` 0. 따라서 `max_seq_len=2048`을 낮추지 않는다.

재생성·검증:

```powershell
python ollama-proxy/training/synthesize_broadcast_continuity_v4.py --overwrite
python -m unittest ollama-proxy/training/tests/test_synthesize_broadcast_continuity_v4.py -v
```

직전 결과: generator 8/8 PASS. 독립 한국어 전수 감사에서 거짓 행동 주장,
근거 없는 기억 소유권, template/ID/split 누출 blocker 0. 실제 파일 bytes와
in-memory render가 두 SHA에 exact 일치했다.

## 3. QLoRA 실행 결과

공통 입력:

```text
Python: D:\AIRI-Models\venv-midm-broadcast-qlora-py312\Scripts\python.exe
Base: D:\AIRI-Models\airi-broadcast-v3-20260821\merged-hf
Base model.safetensors SHA-256:
394b6624de810fd0630ba451c31b3530cc26444ba0e1fa7d98842b6af6e8f506
GPU: RTX 3060 Ti 8GB
r=8, alpha=16, dropout=0.05, lr=2e-5, seq=2048,
batch=1, gradient_accumulation=16, seed=42
```

### 3.1 1-step probe — 완료

- dev loss `3.4270614578`
- peak PyTorch CUDA `5,400,689,664` bytes
- output:
  `D:\AIRI-Models\airi-broadcast-v4-20260821\probe-r8-seq2048-step1-lr2e5`

### 3.2 E1 — 완료, 아직 미채택

- 800 microsteps / 50 optimizer updates
- train first3 mean `3.3845` → last3 mean `2.9151`
- dev loss `2.8938066467`
- peak PyTorch CUDA `6,134,145,536` bytes
- adapter:
  `D:\AIRI-Models\airi-broadcast-v4-20260821\adapter-r8-seq2048-e1-lr2e5`
- report:
  `D:\AIRI-Models\airi-broadcast-v4-20260821\adapter-r8-seq2048-e1-lr2e5-report.json`
- adapter model SHA-256:
  `379b2a5aba1ea5750e0c0d42dbb3b6830f53085b2e61a063f4e3222138305041`
- adapter config SHA-256:
  `930eddf68b9b61936a6b905249f047ba539dc77c04f14f99fa5015333963de2c`
- report SHA-256:
  `0f71b042a74379623197129b609251254c174df3ef026d076523beffb5b41f41`

독립 감사 결과: dataset/base pin exact, LoRA/CAUSAL_LM rank 8, base weight 복사
없음, `training_authorization=true`, `adoption_authorized=false`,
`t3_status=pending`.

### 3.3 E2 — 중단, 재실행 필요

사용량 한계가 가까워졌다는 사용자 요청에 따라 첫 실행은 약 14분, 인계 재검증 중
시작한 두 번째 실행은 약 3분 시점에 각각 Ctrl+C로 안전 중단했다. 두 실행 모두
checkpoint 저장 전이며 GPU는 520MiB 수준으로 해제됐다. 다음 두 경로는 **둘 다
존재하지 않는다**. 재개가 아니라 처음부터 동일 seed로 재실행한다.

```text
D:\AIRI-Models\airi-broadcast-v4-20260821\adapter-r8-seq2048-e2-lr2e5
D:\AIRI-Models\airi-broadcast-v4-20260821\adapter-r8-seq2048-e2-lr2e5-report.json
```

정확한 재실행 명령:

```powershell
$Py = 'D:\AIRI-Models\venv-midm-broadcast-qlora-py312\Scripts\python.exe'
& $Py .\ollama-proxy\training\train_airi_behavior_lora.py `
  --mode cuda-qlora `
  --dataset .\ollama-proxy\training\seed\airi_broadcast_continuity_v4_chat.jsonl `
  --dataset-sha256 96cc223ca5915355394480b60b459d9d039ffad4b47304974c5d939d4686eb44 `
  --model-dir D:\AIRI-Models\airi-broadcast-v3-20260821\merged-hf `
  --model-sha256 394b6624de810fd0630ba451c31b3530cc26444ba0e1fa7d98842b6af6e8f506 `
  --seed 42 --lora-r 8 --lora-alpha 16 --lora-dropout 0.05 `
  --learning-rate 2e-5 --max-seq-len 2048 --batch-size 1 `
  --gradient-accumulation 16 --max-steps 1600 `
  --output D:\AIRI-Models\airi-broadcast-v4-20260821\adapter-r8-seq2048-e2-lr2e5 `
  --report D:\AIRI-Models\airi-broadcast-v4-20260821\adapter-r8-seq2048-e2-lr2e5-report.json
if ($LASTEXITCODE -ne 0) { throw 'v4 E2 training failed' }
```

예상: 1 epoch 실측 약 64분이므로 E2 전체는 약 2시간. E2 report의 epoch 1/2
dev loss와 `selected_dev_epoch`을 E1 `2.8938066467`과 비교한다.

## 4. 병합·GGUF 패키징 — E2 완료 뒤

도구:

- `ollama-proxy/training/merge_airi_behavior_lora.py`
- `ollama-proxy/training/package_airi_gguf.py`
- converter b10375 script SHA:
  `21b70f59d9cfa5f3963bfe9b1c648c16b1fdeca9cff67778bf776d1137b267b5`
- quantizer bundle SHA:
  `354c70ff428a9805f64749d4b80736567488119b656e7819e8ff9a09221aadbe`
- Ollama exe SHA:
  `a64341018083a575267896f8117e66cca0a04262a963bfb3053e46ce2fc4acda`

E1 merge pins:

```text
base artifact manifest: bac2b8153cbe3e960a4a95163f6806eeee72a482c1cffbbd35fe8e0efc108209
E1 adapter artifact manifest: 9254f81d0d62e782caa0e7c04e3214e55ba246a979ce8515a2aedf302e38b05b
```

E2 adapter SHA와 manifest SHA는 E2 완료 후 계산한다. 두 후보 모두
HF safe-merge → BF16 GGUF → Q4_K_M 순서로 패키징한다. 패키저가 128-bit
build suffix를 붙이므로 최종 태그는 각 `package-evidence.json`에서 읽는다.
패키징은 모델 태그를 만드는 상태 변경이지만 운영 채택은 아니다.

## 5. T3 — 병합 후 필수, 아직 실행하지 않음

baseline v3:

```text
tag: midm-airi:2.0-mini-broadcast-v3-q4-20260821-04d64a38eeb4638babb90b12647d3704
digest: e683802b7e9bc72dc0c0ad094bedf4c49142c6248c1b148d3100001c04ff5291
```

fixtures/seeds:

- first calibration canonical SHA
  `0d558c0ce3e019569673ed96f4f171e3464e1e044028e7de6b7ede9d5b8085d6`:
  `11,22,33,20260818`
- second heldout calibration canonical SHA
  `c2ae8a2db00f8f0ed8bd4ee4d909bde965bcbf18dd359b8dbaf340f4c65a57b1`:
  `11,22,33,20260818`
- third final blind 180-minute canonical SHA
  `ddb43f03f88dacff70ebd8a6221274e51348e01e9fe542153139c0330bd52b61`:
  `44,55,66,20260822`

각 baseline/E1/E2 모델에 12 reports, 총 36 reports가 필요하다. 공통 설정은
`--memory-arm seeded --contract on --protocol operational --author-format runtime
--history-turns 8 --max-tokens 220 --briefing on --briefing-evidence on --acts on
--live-broadcast-context on`이다.

전용 launcher `run-airi-broadcast-t3-matrix.ps1`과 오프라인 계약 테스트
`test_broadcast_t3_matrix_launcher_contract.py`를 추가했다. 이전 반려 초안의 배열 비교,
health schema, memory-arm confound, 반복 디렉터리 문제를 모두 제거했으며 다음을
fail-closed로 고정한다.

- model manifest는 exact `baseline/e1/e2` 세 태그와 서로 다른 64-hex digest만 허용
- 승인 fixture manifest와 세 fixture raw/canonical SHA를 실행 전 retained copy에서 재검증
- 세 모델 모두 공통 `seeded`, `max_tokens=220`, `timeout=180`, `num_ctx=2048`,
  live context/briefing/evidence/acts ON
- 매 run fresh empty memory/knowledge DB와 fresh master/observer capability
- local provider, pinned+verified digest, memory/knowledge ready, knowledge 0문서/0청크,
  screening/moderation/epistemic/affect/show-arc ready를 실행 전후 health로 증명
- GPT-SoVITS cache wrapper 소유권, streaming mode 2, min chunk 16, WAV/nonparallel을
  고정하고 하위 script가 바꾼 process 환경까지 최종 복원
- fixture+seed별 immutable stream plan과 report의 exact turn 집합, unique action/trace,
  모든 row의 live context + durable receipt를 검증
- 36 reports가 모두 생긴 뒤 baseline↔E1과 baseline↔E2 두 12-pair comparator를 모두 실행
- report/packet/health/run-contract/plan/comparison와 run별 SQLite/sidecar 전체를 해시 inventory;
  성공 summary도 `adoption_authorized=false`
- PID는 현재 launcher의 직접 자식이면서 exact command identity인 프로세스만 회수하고,
  partial start도 listener 유무와 관계없이 종료를 기다린다

모델 세 태그가 준비되면 다음 형식의 외부 manifest를 만든다. 이 파일과 실행 산출물은
모델 디렉터리 아래에 두고 Git에 넣지 않는다.

```json
{"schema_version":"airi.broadcast-sim-t3-model-manifest.v2","arms":[
  {"name":"baseline","tag":"<baseline tag>","digest":"<64-hex>"},
  {"name":"e1","tag":"<E1 tag>","digest":"<64-hex>"},
  {"name":"e2","tag":"<E2 tag>","digest":"<64-hex>"}
]}
```

```powershell
.\run-airi-broadcast-t3-matrix.ps1 `
  -OutputDir D:\AIRI-Models\airi-broadcast-v4-20260821\t3-matrix `
  -ModelManifest D:\AIRI-Models\airi-broadcast-v4-20260821\t3-model-manifest.json
```

현재 launcher는 실제 E2 adapter/tag가 없으므로 production matrix를 시작하지 않았고,
이 상태에서는 model preflight에서 output/service 생성 전에 반드시 중단한다. T3에는
RAG corpus가 필요 없으므로 fresh knowledge DB는 빈 상태를 attest하며 populated campaign
fixture를 섞지 않는다.

통과 기준은 기존 calibration 계약과 새 blind fixture를 모두 만족해야 하며,
특히 v3의 memory 12/24→8/24, donation callout 40/40→38/40 회귀를 되돌려야 한다.
blind fixture는 폐쇄된 후 처음 사용하므로 결과를 보고 target을 고치면 오염이다.

## 6. T3 뒤 실제 스택 장시간 캠페인

T3 우승 후보만 `run-airi-live-broadcast-campaign.ps1`로 3 seed × 500 turns를
실행한다. 캠페인은 현재 다음을 fail-closed로 증명한다.

- semantic callback과 실제 미노출 decoy
- trace-bound RAG document/chunk receipt와 retained fixture/DB hash
- durable journal append/duplicate
- answer → canonical spoken text → TTS input SHA
- LLM start/content/end → TTS start/first/end 인과 순서
- 정상·실패 show close 증적
- endpoint/model/voice/streaming mode pin

캠페인 통과 전에는 live adoption도, Claude PC 전달용 완료 주장도 하지 않는다.

## 7. 직전 검증

- v4 generator: 8 passed
- LoRA trainer: 16 passed, 1 skipped(CUDA box라 gpu-less refusal skip)
- proxy runtime seam: 369 passed (v4 작성 전 완료; data-only 수정 뒤 코드 변화 없음)
- 인계 직전 묶음 회귀(live runtime, broadcast runner, campaign, v4,
  merge/package, stack/campaign launcher): **131 passed**
- `git diff --check -- . ':(exclude)airi_docs/patches/*.patch'`: whitespace error 0
- E1 artifact 독립 provenance audit: blocker 0
- E2: 두 번 모두 사용자 인계 요청에 따라 checkpoint 전 중단, 불완전 산출물 0
- T3 matrix launcher: 계약 unittest 8 passed, 시뮬/비교기 unittest 75 passed
  (1 skipped), PowerShell AST·py_compile·diff-check PASS
- T3 matrix launcher 독립 최종 감사: P0/P1 0, READY. 실제 서비스/GPU 실행은 E2 부재로 0
- `test-current-checkpoint.ps1`: PASS. 이 과정에서 기존 추적 방송 테스트 15개가 CI
  matrix에서 빠진 불일치, 의도적으로 허용한 `AI` 토큰 뒤 B3-d policy hash pin 누락,
  dry-run stream terminal 증적 누락을 발견해 각각 CI 등록·pin 재결속·synthetic terminal
  회귀 수정했다. B3-d 16/16, B4c rehearsal 83/83 PASS

다음 세션 첫 순서: **E2 재실행 → E1/E2 merge/package → isolated 36-report
T3 → 승자만 3×500 live campaign → 사용자에게 실제 응답 묶음 제출**.
