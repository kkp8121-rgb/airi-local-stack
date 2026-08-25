# 로컬 LLM 파인튜닝에 도움이 되는 GitHub 프로젝트 — AIRI·Mi:dm 2.0 Mini·RTX 3060 Ti 8GB 기준

> **편입 메모 (2026-08-25 16:40 KST, GPU PC)**: 검토 PC에서 작성된 도구 판정표다. 판정
> (프레임워크 교체 이득 없음, lm-eval·perplexity는 지금 없는 평가 축)은 GPU PC HEAD에서도
> 유효하다(lm_eval/kmmlu/llama-perplexity 참조 0건 확인). M2 배치에서 lm-eval과 llama.cpp
> perplexity를 greybox로 도입한다. Unsloth·DPO는 학습 재개 자체가 별도 결정이라 보류.

갱신: 2026-08-25 (스타 수·PyPI 버전은 이 날짜 실측)

목적: "로컬 LLM 파인튜닝에 도움이 되는 GitHub 프로젝트가 있는가"를 일반론이 아니라 **AIRI의 현행 파이프라인에 얹었을 때 실제로 무엇이 좋아지는가**로 판정한다. 대상 모델은 `K-intelligence/Midm-2.0-Mini-Instruct`(2.3B, Llama 아키텍처, MIT), 학습 PC는 GPU PC(RTX 3060 Ti 8GB, Windows)다.

판정 기준 3가지:
1. **실익** — 현행 트레이너가 이미 하고 있는 일이면 이득 없음
2. **충돌** — 핀 고정·fail-closed·재현성(seed/SHA) 원칙과 부딪히는가
3. **8GB 성립** — 실측 VRAM 안에서 도는가

관련 문서: 파이프라인 상태·선결 과제는 `진행중/AIRI-CLAUDE-REVIEW-2026-08-25.md`, 학습 재개 명령은 `진행중/AIRI-CODEX-HANDOFF-2026-08-21.md`.

---

## 0. 결론 먼저

- 현행 트레이너(`ollama-proxy/training/train_airi_behavior_lora.py`)는 이미 **정석 구성**이다 — `peft` LoRA + `bitsandbytes` NF4 QLoRA, 응답 구간만 loss, seq2048 무절단, dataset/model SHA·seed 핀. **학습 프레임워크를 바꿔서 얻을 품질 이득은 없다.**
- 얻을 수 있는 것은 두 가지뿐이다: **① 지금 없는 평가 축**(일반 능력 회귀·양자화 손실) **② 속도**(epoch당 64분 → 절반 기대).
- 채택 권고 4건, 우선순위 순: **lm-evaluation-harness** → **llama.cpp `perplexity`**(이미 핀된 툴체인) → **Unsloth**(별도 venv greybox) → **TRL DPO**(반려 데이터가 쌓인 뒤).
- 나머지(LLaMA-Factory·axolotl·torchtune·ms-swift·ART·distilabel)는 AIRI에선 **해당 없음** — 이유는 §4.

---

## 1. 현행 스택 (실측)

| 구성 | 현재 | 근거 |
|---|---|---|
| 학습 루프 | **수제 PyTorch 루프** (HF `Trainer`/`SFTTrainer` 미사용) | trainer에 `Trainer(`·`TrainingArguments` 0건 |
| LoRA | `peft` `LoraConfig(target_modules="all-linear")`, r8/alpha16/dropout0.05 | `:352`, HANDOFF §3 |
| 양자화 학습 | `bitsandbytes` NF4 + double-quant, compute bf16 | `:318-321` |
| loss 마스킹 | 프롬프트 구간 `-100`, assistant 응답만 학습 | `:279` |
| 템플릿 | HF `apply_chat_template` (Mi:dm Jinja, KT 프리앰블 포함) | `:257-261` |
| 핀 | `torch 2.5.1 · transformers 4.46.3 · peft 0.13.2 · bitsandbytes 0.44.1` | `requirements-training.txt` |
| 실측 | 1 epoch(800행) **64분**, peak CUDA **5.71 GiB / 8 GB**, dev loss 3.43→2.89 | HANDOFF §3.1~3.2 |
| 배포 | HF safe-merge → `convert_hf_to_gguf.py`(b10375 핀) → `Q4_K_M` → Ollama 태그 | `merge_airi_behavior_lora.py`, `package_airi_gguf.py` |
| 평가 | broadcast 지표(T3 36-report, 3×500 캠페인) | HANDOFF §5~6 |
| **없는 것** | 일반 능력 회귀 측정(KMMLU 등) · 양자화 손실(perplexity) 계측 | 레포 코드 grep 0건 (08-11 스카우트 문서에서만 언급) |

---

## 2. 후보 판정표

| 프로젝트 | ⭐ | 라이선스 | 무엇을 하나 | AIRI에 얹으면 | 판정 |
|---|---|---|---|---|---|
| **EleutherAI/lm-evaluation-harness** | 13.8k | MIT | 벤치마크 프레임워크. 한국어 태스크 `kmmlu`·`kobest`·`haerae`·`kormedmcqa` 내장(실측) | LoRA 누적(v2→v3→v4)의 **일반 능력 붕괴(catastrophic forgetting)** 를 처음으로 계측 | ✅ **채택 1순위** |
| **ggml-org/llama.cpp** `tools/perplexity` | 125.5k | MIT | GGUF perplexity 측정. `imatrix`·`quantize`·`export-lora`·`convert_lora_to_gguf.py`도 동봉(실측) | NF4→bf16→Q4_K_M 3단 변환 손실을 dev set으로 수치화. **툴체인이 이미 핀돼 있어 추가 설치 0** | ✅ **채택 2순위** |
| **unslothai/unsloth** | 74.7k | Apache-2.0 | 커널 패치로 LoRA/QLoRA **2배 속도·VRAM 70%↓**. `train_on_responses_only` 내장(실측). Windows 네이티브 지원 | 64분/epoch → ~30분 기대. **단 현행 venv와 비호환**(§3.3) | ✅ **채택 3순위 — greybox** |
| **huggingface/trl** | 19.1k | Apache-2.0 | SFT/DPO/GRPO 트레이너. `assistant_only_loss`·`completion_only_loss`·`packing`·`padding_free`(실측) | SFT는 현행 트레이너와 중복. **DPO**는 반려(총평) 데이터의 2차 활용 경로 | ✅ **채택 4순위 — DPO 한정** |
| huggingface/peft | 21.6k | Apache-2.0 | LoRA 표준 라이브러리 | **이미 사용 중**(0.13.2). 최신 0.20.0 | — 유지 |
| ollama/ollama | 179k | MIT | 서빙 | **이미 사용 중**(0.32.x) | — 유지 |
| hiyouga/LlamaFactory | 74.3k | Apache-2.0 | 100+ 모델 WebUI/CLI 통합 파인튜닝 | WebUI 중심 = 핀·fail-closed CLI 파이프라인과 **정면 충돌**. 1회성 실험 도구로만 | ❌ |
| axolotl-ai-cloud/axolotl | 12.4k | Apache-2.0 | YAML 설정 기반, Docker/Linux 지향(README에 Windows 언급 없음) | 재현성 철학은 맞으나 WSL2/Docker 필요 + 현행 트레이너와 기능 중복 | ❌ |
| meta-pytorch/torchtune | 5.8k | BSD-3 | PyTorch 네이티브 recipe(`lora_finetune_single_device`) | Llama 아키 모델 정의 수동 등록 필요, 이득 없음 | ❌ |
| modelscope/ms-swift | 15.3k | Apache-2.0 | 600+ 모델 CPT/SFT/DPO/GRPO 올인원 | LLaMA-Factory와 같은 이유 | ❌ |
| OpenPipe/ART | 10.7k | Apache-2.0 | 멀티스텝 에이전트 GRPO | 방송 발화에 보상 함수 정의가 없음. 로드맵 P3 이후 과제 | ❌ (보류) |
| argilla-io/distilabel | 3.4k | Apache-2.0 | 합성 데이터·AI 피드백 파이프라인 | 자체 `synthesize_*` 스크립트 + 검수 폼 + governance 결속이 이미 있고, 핵심은 **인간 승인 결속**이라 외부 도구가 풀 문제가 아님 | ❌ |
| instructkr/LogicKor · HAE-RAE-BENCH | 208 · 139 | - | 한국어 벤치마크 | 2024-10 / 2023-09 이후 미갱신. lm-eval의 `haerae`·`kmmlu`가 대체 | ❌ |

---

## 3. 채택 권고 4건 — 상세

### 3.1 lm-evaluation-harness — 일반 능력 회귀 가드 (지금 없는 축)

**왜**: v2→v3→v4로 LoRA를 병합본 위에 누적하고 있다. 방송 지표는 오르는데 한국어 일반 능력이 무너지고 있어도 현재 파이프라인은 **감지할 수단이 없다**. 8GB에서 2.3B bf16 병합본(4.6 GB)은 그대로 평가 가능하다.

**어떻게** (코드 변경 0, 별도 venv):
```powershell
uv venv D:\AIRI-Models\venv-lmeval --python 3.12; D:\AIRI-Models\venv-lmeval\Scripts\activate
uv pip install lm_eval torch --torch-backend=auto
# stock → v3 병합본 → E1/E2 병합본 순으로 동일 태스크·동일 seed·limit 고정
lm_eval --model hf --model_args pretrained=D:\AIRI-Models\airi-broadcast-v3-20260821\merged-hf,dtype=bfloat16 `
        --tasks kmmlu,kobest,haerae --num_fewshot 0 --batch_size 4 --seed 42 --output_path D:\AIRI-Models\eval\v3
```
**게이트 제안**: stock Mi:dm 대비 `kmmlu`·`kobest` 평균 하락 **≤ 2%p**(제안값 — 사용자 확정 필요). T3 36-report와 별개로 **병합 직후 1회**. 결과 JSON은 `package-evidence.json` 옆에 두고 Git 미포함(모델 산출물 규칙).

**주의**: GGUF 직접 평가(`gguf` 백엔드)는 존재 여부 미확인 — bf16 병합본 평가로 시작하고, 양자화 손실은 3.2로 따로 잰다.

### 3.2 llama.cpp `perplexity` — 양자화 손실 계측 (설치 0)

**왜**: 학습은 NF4, 병합은 bf16, 배포는 Q4_K_M — 3단 변환의 손실을 아무도 재지 않는다. T3는 Q4 태그로 돌지만 "학습 이득 중 얼마가 양자화에서 새는지"는 알 수 없다. 패키저가 이미 bf16 GGUF와 Q4 GGUF를 **둘 다** 만든다(`package_airi_gguf.py:231-236`) — 비교 재료가 공짜다.

**어떻게** (패키징 evidence에 2줄 추가 후보):
```powershell
# dev split 100행의 assistant 텍스트를 평문으로 뽑아 dev.txt 생성 후
llama-perplexity -m <output>\airi-bf16.gguf   -f dev.txt -c 2048
llama-perplexity -m <output>\airi-q4_k_m.gguf -f dev.txt -c 2048
```
**판정 기준 제안**: Q4 PPL / bf16 PPL ≤ **1.05**. 넘으면 `Q5_K_M` 검토(1.43→~1.7 GB, 8GB 서빙 여유 충분). `imatrix` 재양자화는 08-11 스카우트가 근거 부족으로 기각(`완료/AIRI-UPGRADE-SCOUT-2026-08-11.md:323`) — 유지.

### 3.3 Unsloth — 속도 (greybox, 별도 venv 필수)

**왜**: 1 epoch 64분 → Unsloth 통상 2배 → E2(2 epoch) 2시간 → ~1시간. VRAM도 5.71 GiB → 더 내려가 seq 여유 확보. Llama 아키텍처·Windows 네이티브·`load_in_4bit` 모두 지원. `train_on_responses_only(instruction_part="<|start_header_id|>user<|end_header_id|>\n\n", response_part="<|start_header_id|>assistant<|end_header_id|>\n\n")`이 Mi:dm의 Llama-3식 헤더에 그대로 맞는다.

**충돌** (PyPI `unsloth 2026.8.19` requires_dist 실측):

| 패키지 | AIRI 핀 | Unsloth 요구 | 결과 |
|---|---|---|---|
| transformers | 4.46.3 | **≥4.51.3, ≤5.5.0** | 비호환 |
| peft | 0.13.2 | **≥0.18.0** | 비호환 |
| bitsandbytes | 0.44.1 | **≥0.45.5** | 비호환 |
| trl | (없음) | ≥0.18.2, **≤0.24.0** | 최신 trl 1.10과도 충돌 |
| torch | 2.5.1 | ≥2.4, <2.12 | 호환 |

→ **현행 venv에 설치 금지.** `uv venv unsloth_env --python 3.13; uv pip install unsloth --torch-backend=auto`(README 실측 명령)로 **별도 venv**를 만들고, Unsloth 버전을 `2026.8.19`로 핀한다(커널 패치가 재현성 변수이므로).

**흡수 조건** (greybox → 동등성 → 교체):
1. 현행 트레이너의 계약을 그대로 재구현: dataset/model SHA 핀 검증, seed, `max_seq_len` 초과 시 거부, epoch별 dev loss, `training_authorization`/`adoption_authorized=false` report — 이 계약이 T3·governance의 근거라 **생략 불가**
2. 같은 데이터·seed로 E2를 양쪽에서 돌려 **dev loss 차이 ≤ 0.02, 시간 절감 ≥ 1.5배**면 채택. 마스킹 동등성은 두 트레이너의 `labels` 텐서를 같은 행에서 직접 비교
3. 채택해도 병합·GGUF·패키징은 현행 경로 유지(Unsloth의 GGUF 내보내기는 핀 체계 밖)

### 3.4 TRL DPO — 반려 데이터의 2차 활용 (데이터 확보 후)

**왜**: 08-20 인계문의 "행동 181·affect 120 총평 반려"는 사실상 **chosen/rejected 쌍의 원천**이다. SFT가 "좋은 예"만 보여준다면 DPO는 "이건 아니다"를 직접 가르친다 — 문체·톤처럼 결정론 계층이 못 잡는 축에 맞다.

**조건**: 쌍 데이터 **≥ 수백 건**, 같은 프롬프트에 chosen/rejected가 붙은 형식. `DPOTrainer(beta=0.1, learning_rate=5e-6)` + LoRA — 8GB에서 2.3B는 reference 모델 공유(peft adapter 분리)로 성립. 로드맵 원칙("프롬프트 지시보다 결정론 우선")상 **P1·P2로 못 잡는 축에 한정**.

**SFT에는 TRL을 쓰지 않는 이유**: TRL `assistant_only_loss`는 chat template에 `{% generation %}` 마커가 필요하고, Mi:dm 템플릿엔 없다. TRL이 알려진 템플릿엔 학습용 템플릿을 자동 치환하지만(`sft_trainer.py:1250-1253`) Mi:dm 커스텀 템플릿에 되는지는 **미확인** — 현행 트레이너의 `-100` 마스킹이 이미 같은 일을 정확히 하므로 바꿀 이유가 없다.

---

## 4. 채택하지 않는 것 — 이유

- **LLaMA-Factory / ms-swift**: 강점이 "GUI로 100+ 모델 즉시" — AIRI의 강점(모든 입력 SHA 핀, 산출물 evidence, 채택 게이트)과 반대 방향. 새 모델 후보를 30분 안에 훑는 **실험용**으로는 가치가 있으나 운영 경로에 넣지 않는다.
- **axolotl**: YAML 재현성은 AIRI 철학과 맞지만 Docker/Linux 지향이라 Windows GPU PC에선 WSL2 필요. 얻는 기능이 현행 트레이너와 겹친다.
- **torchtune**: recipe 품질은 좋으나 Mi:dm(커스텀 head_dim 128)을 모델 빌더에 직접 등록해야 하고, 이득이 없다.
- **ART(GRPO)**: 보상 함수가 정의된 태스크용. 방송 발화 품질은 현재 사람 총평·시뮬 지표라 보상화 전 단계. 로드맵 P3 이후.
- **distilabel**: 합성 데이터 파이프라인은 이미 `synthesize_broadcast_continuity_v4.py`(8/8 PASS)와 검수 폼이 있고, 08-21 검수에서 드러난 문제는 도구가 아니라 **승인 아티팩트 결속**이었다.
- **LogicKor / HAE-RAE-BENCH 단독 레포**: 갱신 정지. lm-eval 내장 태스크로 충분.

---

## 5. 8GB 참고 수치

| 방식 | 2.3B(Mi:dm Mini) 실측/추정 | 7B | 14B | 출처 |
|---|---|---|---|---|
| QLoRA 4bit | **5.71 GiB 실측**(seq2048, b1, GA16, checkpointing) | ~6 GB | ~12 GB | HANDOFF §3.2 / LLaMA-Factory 표(`x/2` GB) |
| LoRA 16bit | ~6.9 GB 추정(가중치 4.6 + 활성화·옵티마이저) | 16 GB ✗ | ✗ | LLaMA-Factory 표(`2x` GB) |
| Full | ✗ | ✗ | ✗ | 7B에 120 GB |

Mi:dm Mini는 8GB에서 **bf16 LoRA도 이론상 들어가지만**, 현행 NF4 QLoRA가 5.71 GiB로 여유를 남기고 있고 v3까지 같은 조건으로 누적됐으므로 바꾸지 않는다.

---

## 6. 도입 순서 (권고 — 전부 greybox, 운영 경로 무변경)

1. **lm-eval baseline** — stock Mi:dm · v3 병합본 2종을 `kmmlu,kobest,haerae`로 측정해 기준선 박제. 코드 변경 0 → verify: 두 결과 JSON 존재 + stock 수치가 공개 리더보드 근사
2. **perplexity 계측** — 다음 패키징(E1/E2)에서 bf16·Q4 PPL 2줄을 evidence 옆에 기록 → verify: 비율 ≤1.05
3. **Unsloth greybox** — 별도 venv, 계약 재구현, E2 동등성 비교 → verify: dev loss Δ≤0.02·시간 ≥1.5배 → 채택 시 `requirements-training-unsloth.txt` 신설(핀 분리)
4. **DPO** — 반려 쌍 수백 건 확보 후. 데이터 형식·governance(인간 승인 결속)는 SFT와 동일 적용

1~2는 E2 재실행과 병행 가능하다. 3은 E2를 **현행 트레이너로 먼저 마친 뒤**(비교 기준 확보) 시작한다.

---

## 부록 — 버전 실측 (2026-08-25)

| 패키지 | AIRI 핀 | PyPI 최신 | 비고 |
|---|---|---|---|
| unsloth | — | 2026.8.19 (08-20) | requires transformers 4.51.3~5.5.0, peft ≥0.18, bnb ≥0.45.5, trl ≤0.24 |
| trl | — | 1.10.0 (08-13) | `assistant_only_loss`·`completion_only_loss`·`packing`·`padding_free` 존재 |
| peft | 0.13.2 | 0.20.0 (07-28) | |
| transformers | 4.46.3 | 5.15.1 (08-19) | Mi:dm 생성 버전 4.48.2; 4.46.3에서 `head_dim` 존중 실증(E1 완주) |
| bitsandbytes | 0.44.1 | 0.50.1 (08-13) | |
| lm-eval 한국어 태스크 | — | `haerae kmmlu kobest kormedmcqa` | `lm_eval/tasks` 디렉터리 실측 |
| llama.cpp tools | b10375 핀 | `perplexity imatrix quantize export-lora llama-bench tokenize` + `convert_lora_to_gguf.py` | 레포 `tools/` 실측 |
