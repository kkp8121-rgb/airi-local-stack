# AIRI Mi:dm 파인튜닝 파이프라인 재검토 — 2026-08-25 검토 PC (Claude)

> **편입 메모 (2026-08-25 16:40 KST, GPU PC)**: 이 문서는 검토 PC(GPU 없음)에서 HEAD
> `8b284a7`(08-21) 기준으로 작성된 **시점 고정 실측 기록**이다. §3 파이프라인 상태·§9 재개
> 순서는 이후 E2·E2-C1·E2-C2·D1 라운드로 **시효가 만료**됐으니 현행 상태는
> `진행중/AIRI-WORKING-STATE.md`를 따른다. §5(Modelfile TEMPLATE 실효 없음, KT 프리앰블
> ≈514토큰 고정 소모)는 GPU PC에서 v3 baseline **패키징 태그**로 재검증했다 — Ollama 0.32.6,
> 실효 템플릿 Jinja 4,063자, user 1건 `prompt_eval_count` **514**, system+history 3턴 554.
> 단 패키징 태그의 `parameters`에는 `stop`이 없어 표 1 #4는 패키징 태그에 한해 미검증이다.
> §6 R2 F5/F6은 blind comparator 경로에서 해결됐고 F7은 M2 배치에서 코드 게이트로 닫는다.
> 이 발견은 프록시 400 `exceed_context_size_error`(M1 확정)의 고정비 원인이며 `num_ctx`
> 4096 승격의 근거다.

갱신: 2026-08-25

상태: **재검토 완료. 코드 변경 0건, 커밋 0건. 신규 실측 발견 1건(템플릿·토큰 예산)과 사용자 결정 1건.**

대상: `C:\Projects\airi\airi-local-stack` (main), HEAD `8b284a7` (2026-08-21 17:50 +0900), 작업 트리 clean.
검토 PC = 이 PC(GPU 없음, Ollama 0.32.14). 학습·T3는 GPU PC(RTX 3060 Ti 8GB, 문서상 Ollama 0.32.6) 몫이며 `D:\AIRI-Models`는 이 PC에서 접근 불가.

이 문서는 자기완결형이다. 2026-08-21 인계문(`AIRI-CODEX-HANDOFF-2026-08-21.md`)과 배치 검수(`AIRI-CODEX-BATCH-EVAL-2026-08-21.md`)의 주장을 **코드·API 실측으로 재확인**하고, 문서에 없던 항목은 이 PC의 Ollama로 직접 프로브해 확정했다. 인계문·검수 문서를 대체하지 않으며, 재개 순서(§9)만 보강한다.

---

## 0. 검토 방식

- 문서의 모든 수치·주장은 인용하지 않고 코드 라인·API 응답으로 재확인했다. 재확인 못 한 항목은 "기록 기준"으로 표기했다.
- 가설은 추측으로 남기지 않았다. Ollama 템플릿 동작은 이 PC에서 임시 태그 5종을 만들어 `prompt_eval_count`로 실측한 뒤 전부 삭제했다(§5, 부록 A).
- continuity governance(BATCH-EVAL §3/§7)는 **2026-08-21 사용자 확인으로 종결**된 항목이다("맞아 승인했어" — §7이 공식 기록). 본 검토는 재론하지 않는다. 잔여는 절차 개선 1건(향후 일괄 승인을 검증 가능한 아티팩트로 남길 것)뿐이다.

---

## 1. 요약

| # | 항목 | 판정 | 근거 |
|---|---|---|---|
| 1 | 파이프라인 상태 | v4 corpus 확정 · E1 완료(미채택) · **E2 미실행(중단 후 산출물 없음)** · T3 미실행 · `adoption_authorized=false` | §3 |
| 2 | 학습 설정(QLoRA r8/lr2e-5/seq2048) | **적정** — v3 병합본 위 누적 학습이므로 낮은 LR·낮은 rank가 맞음 | §4 |
| 3 | Mi:dm 고유 토크나이저 함정 4종 | **전부 무해 또는 이미 처리** (실측) | §4 |
| 4 | 정지 토큰(`<\|eot_id\|>`) 미선언 우려 | **해소** — Ollama 0.32.x가 GGUF 내장 템플릿에서 stop을 자동 부여 (실측) | §5 |
| 5 | **[신규] Modelfile TEMPLATE 실효 없음 → KT 프리앰블 ≈500토큰이 매 턴 서빙 프롬프트에 포함** | 학습·서빙은 **일치**(둘 다 포함). 단 `num_ctx 2048`의 **25%가 고정 소모**되고, 런처 테스트가 단언하는 "프리앰블 제거" 의도는 실효되지 않음 | §5 |
| 6 | 코덱스 선결 R2 F5/F6/F7 | **HEAD에서 미해결 확인(코드 라인)** — E2 전 수리 필수 | §6 |
| 7 | 검토 PC 로컬 태그 | digest `106cfaac…` ≠ 런처 핀 `92a9ba2e…` — 이 PC에서 스택 기동 시 preflight fail-closed 예상 | §7 |
| 8 | 사용자 결정 | 프리앰블 정책(유지 vs 제거) — E2 재실행 **전**에 결정해야 함 | §8 |

---

## 2. 직전 대화 검토(2026-08-25 오전)에서 정정하는 것

같은 날 대화로 보고한 1차 검토는 문서 열람만으로 작성돼 아래가 틀렸다. 이 문서가 정정본이다.

| 1차 검토 주장 | 정정 | 근거 |
|---|---|---|
| "governance 위반 판정이 미해결" | **2026-08-21 §7로 이미 종결**. 판정은 "위반"→"승인 기록 누락"으로 하향, E1 유효 후보 유지 | BATCH-EVAL §7, ROADMAP-LOG 08-21 추기 |
| "패키징 태그의 `TEMPLATE {{ .Prompt }}`가 system·history를 유실할 가능성" | **반증**. Ollama 0.32.x는 Modelfile TEMPLATE를 무시하고 GGUF 내장 Jinja로 렌더한다. system+history는 정상 포함(Δ93토큰) | §5 프로브 A~D |
| "`PARAMETER stop` 부재 → 생성이 안 멈출 수 있음" | **해소**. stop 4~5종이 내장 템플릿에서 자동 부여됨 | §5 프로브 C |
| "pad=eos 충돌 우려" | **무해**. 턴 종료 토큰은 `<\|eot_id\|>`(131301)이고 pad는 `<\|end_of_text\|>`(2)라 겹치지 않으며, 패딩 라벨은 `-100` 마스킹 | `train_airi_behavior_lora.py:334-335, 367-368` |
| "GPU = RTX 3060 8GB" | 인계문 실측은 **3060 Ti** 8GB | HANDOFF §3 |

---

## 3. 파이프라인 현재 상태 (실측)

### 3.1 자산

| 항목 | 값 | 확인 |
|---|---|---|
| 서비스 모델 | `midm-airi:2.0-mini` = `hf.co/DevQuasar/K-intelligence.Midm-2.0-Mini-Instruct-GGUF:Q4_K_M` | `ollama-proxy/Modelfile.midm-airi:1` |
| 런처 검증 digest 핀 | `92a9ba2ee8c79ba46c22907b50b15eb1ca55c94d04230eca73917936ef36485f` (2026-08-12 `a77e1dd`) | `test_midm_model_configuration.py:125` |
| 베이스 모델 스펙 | LlamaForCausalLM · 2.3B · 48층 · hidden 1792 · 32 heads / 8 KV · head_dim 128 · ctx 32,768 · vocab 131,392 · MIT | HF `config.json` + `/api/show model_info` |
| 학습 베이스 | `D:\AIRI-Models\airi-broadcast-v3-20260821\merged-hf` (v3 병합본 위 누적) SHA `394b6624…` | HANDOFF §3 (기록 기준) |
| v4 corpus | 1,000행, train/dev/test 800/100/100, 최대 2,010토큰, source SHA `43f9c1ed…` / chat SHA `96cc223c…` | HANDOFF §2 (기록 기준). 로컬 파일 존재 확인 |
| corpus 행 구조 | system×5(AIRI 페르소나 2,960자 · 사실 · affect 상태 · 방송 카드 · 문체 규범) → user → assistant | `airi_broadcast_continuity_v4_chat.jsonl` 1행 실측 |

### 3.2 실행 결과 (인계문 기록 기준 — GPU PC 산출물은 이 PC에서 검증 불가)

| 단계 | 상태 | 수치 |
|---|---|---|
| 1-step probe | 완료 | dev loss 3.4271, peak CUDA 5.40 GB |
| **E1** (800 microsteps / 50 updates) | 완료 · **미채택** | train 3.3845→2.9151, **dev 2.8938**, peak CUDA **6,134,145,536 B = 5.71 GiB / 8 GB** |
| **E2** (2 epoch, 1,600 steps) | **약 14분에 Ctrl+C 중단 · 산출물 없음** | 재실행 명령 HANDOFF §3.3에 exact 박제. 예상 ≈2시간(1 epoch 실측 64분) |
| merge / GGUF | 미실행 (E2 후) | 도구 핀 3종 HANDOFF §4 |
| T3 (36 reports) | 미실행 | baseline v3 태그 `midm-airi:2.0-mini-broadcast-v3-q4-20260821-04d64a38…` |
| 3×500 live campaign | 미실행 | T3 승자만 |

게이트: `adoption_authorized=false`, `t3_status=pending` — 패키저가 evidence에 하드코딩(`package_airi_gguf.py:270-271`). 서비스 모델·기본 태그 미변경.

### 3.3 로드맵 정합

학습 트랙은 로드맵 v3 P3의 **주 경로**로 사용자가 확정한 방향이다(2026-08-19 "모델을 학습시키는 방향으로", `AIRI-ROADMAP-STATUS.md:187-192`). 근거는 실패 정체가 지식이 아닌 행동 패턴(사실 활용 7%·지시 불응 3회)이고 크기 확대(8B)는 반증됐다는 것. 본 파인튜닝은 로드맵과 정합한다.

---

## 4. 학습 설정 검증

### 4.1 하이퍼파라미터 (HANDOFF §3 공통 입력)

```
mode=cuda-qlora (NF4 double-quant, compute bf16)   ← train_airi_behavior_lora.py:318-321
r=8, alpha=16, dropout=0.05, lr=2e-5, seq=2048, batch=1, grad_accum=16, seed=42
target_modules="all-linear"                          ← :352
```

판정: **적정.** stock 모델에 첫 LoRA를 붙일 때의 통상값(lr 2e-4 / r 16)이 아니라 **이미 v3까지 학습된 병합본 위에 누적**하는 상황이므로 10배 낮은 LR과 낮은 rank가 이전 학습 붕괴를 막는 올바른 선택이다. peak 5.71 GiB로 8GB 안에서 seq2048 무절단이 성립한다(`>2016` 토큰 행 0).

### 4.2 Mi:dm 고유 함정 4종 — 실측 대조

| 함정 | 실측 | 판정 |
|---|---|---|
| ① 턴 종료 `<\|eot_id\|>`(131301) ≠ `generation_config.eos`(2) | 학습 텍스트는 HF Jinja 템플릿으로 렌더돼 assistant 턴이 `<\|eot_id\|>`로 끝남(`:257-261`). 서빙은 Ollama가 stop에 `<\|eot_id\|>` 자동 포함(§5) | ✅ 무해 |
| ② pad == eos (`<\|end_of_text\|>`) | pad는 이미 설정돼 있어 `:334-335` 분기 미진입. 패딩 라벨 `-100`(`:367-368`), 실제 종료 토큰은 `<\|eot_id\|>`라 pad와 불일치 | ✅ 무해 |
| ③ `head_dim 128` ≠ hidden/heads(56), 생성 버전 transformers 4.48.2 vs 핀 **4.46.3** | E1이 정상 loss 곡선으로 완주 → 4.46.3이 `head_dim`을 존중함이 실증 | ✅ 문제 없음 |
| ④ KT 시스템 프리앰블(≈500토큰)이 학습 텍스트에 포함 | 포함됨. 그러나 서빙도 포함(§5)이라 **학습/서빙 일치**. 프롬프트 구간은 `-100` 마스킹(`:279`)이라 프리앰블은 loss에 기여하지 않음 | ✅ 일치. 단 토큰 예산 문제 → §5.4 |

### 4.3 의존성 핀 (`ollama-proxy/training/requirements-training.txt`)

`torch==2.5.1 · transformers==4.46.3 · peft==0.13.2 · bitsandbytes==0.44.1 · datasets==3.1.0 · accelerate==1.0.1 · safetensors==0.4.5` — 재현 핀 유지. E1 실행으로 조합 검증됨.

### 4.4 단위 테스트 공백 (기록)

- `tests/test_train_airi_behavior_lora.py:239-271`는 `chat_template=None`인 `BareTokenizer`로 `render_pair`를 검증한다 → **실제 Mi:dm Jinja 렌더 경로(프리앰블·`<\|eot_id\|>` 종료)는 단위 테스트가 덮지 않는다.** E1 완주가 유일한 증거다.
- `tests/test_package_airi_gguf.py`에는 Modelfile 내용(TEMPLATE·stop)에 대한 단언이 없다.

---

## 5. 템플릿·정지 토큰 실측 (신규 발견)

### 5.1 왜 확인했나

서빙 경로는 프록시 → Ollama **native `/api/chat`**(messages 배열 그대로, `template`/`raw` 오버라이드 없음 — `ollama_proxy.py:6716-6760`) → **Ollama 서버 측 템플릿 렌더**다. 그런데 태그별 Modelfile이 다르다:

| 태그 | Modelfile | 의도 |
|---|---|---|
| 서비스 `midm-airi:2.0-mini` | Go 템플릿(헤더만, **KT 프리앰블 없음**) + `PARAMETER stop` 4종 | 프리앰블 제거 — `test_midm_model_configuration.py:154-155`가 `"Mi:dm은"`·`"경어체"` 부재를 단언 |
| 패키징 후보/v3 baseline | `TEMPLATE {{ .Prompt }}` + stop **없음** (`package_airi_gguf.py:194-197`) | (문서·테스트에 논의 없음) |

학습은 HF `apply_chat_template`(KT 프리앰블 포함)이므로, Modelfile이 그대로 적용된다면 학습/서빙 시스템 헤더가 어긋나고(서비스 태그), `{{ .Prompt }}` 레거시 경로에서는 system·history가 유실될 수 있었다.

### 5.2 프로브 (이 PC, Ollama 0.32.14, 부록 A)

동일 두 페이로드(① user 1건 / ② system 260자 + user·assistant·user)로 `prompt_eval_count`(num_predict=1, keep_alive=0) 비교:

| 태그 | 생성 방식 | TEMPLATE | `/api/show` 실효 템플릿 | ① user_only | ② sys+hist | Δ |
|---|---|---|---|---|---|---|
| `midm-airi:2.0-mini` (이 PC) | 기존 | — | **Jinja 4,063자** | 514 | 607 | 93 |
| A | `/api/create` | `{{ .Prompt }}` | Jinja 4,063자 | 514 | 607 | 93 |
| B | `/api/create` | `Modelfile.midm-airi` Go 템플릿 | Jinja 4,063자 | 514 | 607 | 93 |
| C | **CLI `ollama create -f`** | `{{ .Prompt }}` (패키저와 동일) | Jinja 4,063자 | 514 | 607 | 93 |
| D | **CLI `ollama create -f`** | 레포 `Modelfile.midm-airi` 원본 | Jinja 4,063자 | 514 | 607 | 93 |

- user 메시지 1건("어떤 게임인데?")이 **514토큰**으로 렌더 = KT 프리앰블(≈490토큰) + 헤더 + 본문.
- **PARAMETER는 반영된다**(D는 Modelfile의 stop 4종 정확히, C는 부모 태그에서 stop 5종 상속). **TEMPLATE만 무시된다.**
- CLI가 새 template 레이어를 만들었음에도(`creating new layer sha256:b507b9c2…`/`8ebf7517…`) 실효 템플릿은 GGUF의 `tokenizer.chat_template`였다.

### 5.3 결론

1. **Ollama 0.32.x는 GGUF에 Jinja `chat_template`이 있으면 Modelfile TEMPLATE보다 우선한다.** 병합 스크립트가 base 토크나이저를 그대로 저장하고(`merge_airi_behavior_lora.py:306,317`) llama.cpp 변환이 이를 GGUF에 내장하므로, 패키징 후보도 같은 동작이 기대된다.
2. 따라서 **학습(HF Jinja) = 서빙(Ollama Jinja)** 으로 시스템 헤더가 일치한다. `{{ .Prompt }}` 레거시 유실 가설은 기각. T3의 baseline v3/E1/E2는 모두 같은 패키저 산출물이므로 **템플릿은 T3 교락 요인이 아니다.** v3의 memory 12/24→8/24 회귀(HANDOFF §5)도 템플릿으로 설명되지 않는다.
3. 정지 토큰: `<\|eot_id\|>`는 학습 종료 토큰이자 서빙 stop(자동 부여)이다. 우려 해소.

### 5.4 함의 — 조치 필요

| # | 함의 | 조치 |
|---|---|---|
| a | **토큰 예산**: `num_ctx 2048` 중 **≈514토큰(25%)이 매 턴 KT 프리앰블+헤더에 고정 소모**된다. NEXT-SESSION의 "고정 주제 블록+카드 병합 시 2,246토큰 — 4096 필요"는 이 몫을 별도 항목으로 계상하지 않은 것으로 보인다 | P1 예산 재배분 시 프리앰블 514토큰을 **고정비로 명시 계상**. 4096 승격 판단의 근거 수치에 반영 |
| b | **의도 불일치**: `Modelfile.midm-airi`의 Go 템플릿과 `test_midm_model_configuration.py:154-155`는 "프리앰블 제거"를 보장하는 듯 읽히지만 **실효가 없다**(런타임에는 프리앰블 포함). 문서·테스트가 실제 동작보다 강한 약속을 하고 있다 | 테스트 주석 또는 TECH-SPECS에 "Ollama 0.32에서 TEMPLATE 실효 없음, 프리앰블 포함 서빙" 명기. 사용자 결정(§8) 후 정리 |
| c | **날짜 문자열**: 템플릿의 `strftime_now`는 HF에서는 실제 날짜, Ollama Jinja에서는 정의 여부 미확인(미정의 시 `'04 Jul 2025'` 고정) | 경미(수 토큰). GPU PC 확인 시 함께 관찰 |
| d | **GPU PC 확정 1회**: 이 PC 실측은 hf.co 부모 태그 기준이다. 패키징 태그(`FROM <로컬 .gguf>`)도 동일한지 GPU PC에서 확인 | 아래 명령 1회 실행, 결과를 인계문에 기록 |

```powershell
# GPU PC — v3 baseline 패키징 태그의 실효 템플릿·stop 확인 (기대: template이 '{%'로 시작하는 Jinja, stop에 <|eot_id|> 포함)
$tag = 'midm-airi:2.0-mini-broadcast-v3-q4-20260821-04d64a38eeb4638babb90b12647d3704'
Invoke-RestMethod -Uri http://127.0.0.1:11434/api/show -Method Post -ContentType 'application/json' `
  -Body (@{ model = $tag } | ConvertTo-Json) | Select-Object parameters, @{n='template_head';e={$_.template.Substring(0,80)}}
```

---

## 6. 코덱스 선결 목록 재확인

BATCH-EVAL §6의 11건 중 **T3 신뢰 필수 조건 3건은 코드 라인으로 미해결을 재확인**했다. 검수(`609459a`) 이후 코드 커밋은 0건(`8b284a7`는 문서만).

| 항목 | 실측 근거 | 상태 |
|---|---|---|
| **R2 F5** 시드 하한 부재 | `compare_broadcast_t3.py:117-152` — fixture별 seed를 수집·중복만 검사, **최소 개수 검사 없음** | 미해결 |
| **R2 F6** 교락 필드 미비교 | comparator에 `memory_arm`/`contract_version`/`max_tokens`/digest 비교 **0건**. sim 리포트 payload(`run_broadcast_sim.py:852-874`)는 `model`(태그명)·`memory_arm`·`contract_version`·`seed`·`fixture_sha256`·`history_turns`만 담고 **`max_tokens`·모델 digest는 없음** | 미해결 |
| **R2 F7** T3 미통과→캠페인 차단 0건 | `run-airi-live-broadcast-campaign.ps1`에서 `t3`/`adoption` 문자열 **0건** | 미해결 |
| R1 F3~F7, R2 F8~F10, R3 절차 개선 1건 | 코드 재검증 미수행 — BATCH-EVAL 기록 기준 | 기록 기준 |

HANDOFF §5도 "현 comparator가 model/digest, memory arm, max tokens, timeout을 자체 비교하지 않으므로 외부 manifest에서 반드시 고정한다"고 인정한다. **F5/F6/F7 미수리 상태의 T3 통과는 통과의 의미를 보증하지 못한다** — BATCH-EVAL §2 판단 유지.

---

## 7. 검토 PC 상태 (이 PC 한정)

| 항목 | 실측 | 영향 |
|---|---|---|
| `midm-airi:2.0-mini` digest | `106cfaacc185aec489cc…` (핀 `92a9ba2e…`와 **불일치**) | 이 PC에서 `start-airi-local-stack.ps1` 기본 실행 시 preflight가 fail-closed로 막힐 것. 원인(GGUF 블롭 버전 차 / Ollama 버전별 레이어 차)은 미확정 — 필요 시 `setup-midm-airi-model.ps1 -Recreate` 후 digest 재확인 |
| 로컬 모델 | `midm-airi:2.0-mini`, hf.co DevQuasar Q4_K_M, `exaone-airi:2.4b`, `exaone3.5:2.4b`, `qwen3:8b`, `qwen3:4b`, `granite4.1:3b` | 프로브 가능 환경 |
| `ollama` CLI | **Git Bash에서 `ollama list`가 hang**(120초+). PowerShell·HTTP API는 정상 | 실측 함정 — Bash 도구로 ollama CLI 호출 금지, PowerShell 또는 `127.0.0.1:11434` API 사용 |
| 임시 태그 | 프로브용 5종(`zz-tpl-probe:test`, `zz-probe-a/b/c/d`) 생성·**전부 삭제 확인** | 잔존 0 |
| GPU | Radeon 780M iGPU, RAM 31 GB(여유 1.4 GB) | 학습 불가. 프로브는 CPU 추론으로 8~10초/건 |

---

## 8. 사용자 결정 필요 — 1건

**KT 시스템 프리앰블 정책** (E2 재실행 **전**에 결정해야 한다 — 학습 렌더를 바꾸면 E2·병합·T3가 전부 새 조건이 된다):

| 안 | 내용 | 비용 | 비고 |
|---|---|---|---|
| **A. 유지 (권고)** | 현행대로 학습·서빙 모두 프리앰블 포함 | **0** — E2를 그대로 재실행 | v2→v3→v4 누적 학습이 전부 프리앰블 조건에서 이뤄졌으므로 정합. 대신 §5.4 a·b 정리(예산 계상·문서/테스트 문구) |
| B. 제거 | merged-hf의 `tokenizer_config.json` `chat_template`에서 프리앰블을 걷어낸 뒤 학습·GGUF 변환 → 학습·서빙 모두 미포함 | **높음** — v3 병합본이 프리앰블 조건 학습이라 stock Mi:dm부터 재학습이 원칙 | 턴당 ≈490토큰 회수. 로드맵 "프롬프트 지시보다 결정론 계층 우선"과는 무관한 순수 예산 이득 |

권고: **A.** 지금 얻을 것(예산 25%)보다 잃을 것(v2~v4 학습 체인 무효화·T3 일정)이 크다. B는 P1 예산 재배분에서 4096 승격으로도 흡수 가능하다.

---

## 9. 재개 순서 (권고 — HANDOFF §7 "다음 세션 첫 순서" 보강)

1. **§8 결정** (A면 코드 변경 없음)
2. **R2 F5/F6/F7 수리** — comparator 시드 하한(인계문 기준 fixture당 4 seed) · `memory_arm`/`contract_version`/`max_tokens`/모델 digest 비교 + sim payload에 `max_tokens`·digest 추가 · 캠페인 런처 T3-pass 게이트 → verify: `python -m pytest -q ollama-proxy/eval/broadcast_sim` + 의도적 교락 리포트로 FAIL 재현
3. **E2 재실행** — HANDOFF §3.3 exact 명령 그대로 (≈2시간) → verify: report의 epoch 1/2 dev loss vs E1 `2.8938`
4. **E1·E2 merge → package** → verify: `package-evidence.json` 핀 3종 + **§5.4 d 명령 1회**로 실효 템플릿·stop 기록
5. **T3 36 reports** (isolated launcher 선행, HANDOFF §5 blocker) → verify: F5/F6 수리된 comparator 통과 + blind fixture 미오염
6. **승자 3×500 live campaign** → 사용자에게 실제 응답 묶음 제출
7. 커밋 시 `AIRI-ROADMAP-LOG.md` 맨 위 기록 + `AIRI-CURRENT-DOCS-INDEX`에 본 문서 등록

---

## 부록 A — 프로브 절차 (재현용)

```text
환경: 이 PC, Ollama 0.32.14, 127.0.0.1:11434
SRC = hf.co/DevQuasar/K-intelligence.Midm-2.0-Mini-Instruct-GGUF:Q4_K_M
페이로드 ①: [user "어떤 게임인데?"]
페이로드 ②: [system 260자 AIRI 반말 지침, user "안녕 오늘 컨디션 어때", assistant "완전 좋아! 오늘 신작 얘기할 거야", user "어떤 게임인데?"]
옵션: stream=false, keep_alive=0, num_predict=1, num_ctx=2048, seed=1 → prompt_eval_count 비교
A/B: POST /api/create {model, from=SRC, template=...}           ← template 무시됨
C/D: ollama create <tag> -f <Modelfile> (PowerShell Start-Process) ← template 레이어 생성되나 실효 없음
확인: POST /api/show {model} → template(Jinja 4,063자), parameters(stop)
정리: DELETE /api/delete {model} → /api/tags에 zz-* 잔존 0
```

스크립트: 세션 scratchpad `probe_tpl.py` / `probe_tpl2.py` / `probe_tpl3.py` (레포 미포함 — 위 텍스트로 재현 가능).

## 부록 B — 참조 라인

- 트레이너 렌더·마스킹: `ollama-proxy/training/train_airi_behavior_lora.py:257-283`
- QLoRA 설정: `:318-321` / pad 분기 `:334-335` / LoRA target `:352` / 패딩 라벨 `:367-368`
- 패키저 Modelfile: `ollama-proxy/training/package_airi_gguf.py:194-197`, evidence 게이트 `:270-271`
- 병합 토크나이저 보존: `ollama-proxy/training/merge_airi_behavior_lora.py:306,317`
- 프록시 업스트림 변환: `ollama-proxy/ollama_proxy.py:6716-6760`, 시스템 프롬프트 `:1568`
- 서비스 Modelfile·테스트: `ollama-proxy/Modelfile.midm-airi`, `test_midm_model_configuration.py:124-155`
- T3 comparator: `ollama-proxy/eval/broadcast_sim/compare_broadcast_t3.py:80-152`; sim payload `run_broadcast_sim.py:852-874`
- 인계·검수: `진행중/AIRI-CODEX-HANDOFF-2026-08-21.md` §2~§7, `진행중/AIRI-CODEX-BATCH-EVAL-2026-08-21.md` §2·§6·§7
- 로드맵: `로드맵/AIRI-ROADMAP-STATUS.md:176-192` (P3 학습 트랙), `로드맵/AIRI-ROADMAP-LOG.md` 08-21 항목
