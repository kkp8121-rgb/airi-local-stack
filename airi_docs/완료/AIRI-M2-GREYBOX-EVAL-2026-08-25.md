# AIRI M2 greybox 평가 기준선 — lm-eval · llama.cpp perplexity (2026-08-25)

갱신: 2026-08-25 17:05 KST (GPU PC, RTX 3060 Ti 8GB)

상태: **완료. 운영 경로 변경 0, 학습 0, 가중치 수정 0.** 산출물은 전부
`D:\AIRI-Models\airi-m2-greybox-eval-20260825\`(Git 미포함)에 있고 아래 SHA로 고정한다.

배경: `참조/AIRI-FINETUNE-TOOLING-SURVEY-2026-08-25.md`가 "지금 없는 평가 축" 두 가지로
지목한 (1) 학습 누적에 따른 **일반 능력 회귀**와 (2) bf16→Q4_K_M **양자화 손실**을 처음으로
계측했다. 사용자 goal(2026-08-25 "제안 방향대로 진행, 이로운 툴 도입") 아래 M2 배치 B.

## 1. 환경

| 항목 | 값 |
|---|---|
| lm-eval venv | `D:\AIRI-Models\venv-lmeval` (uv 0.11.0, cpython 3.12.13), `lm_eval 0.4.12`, `transformers 5.15.1`, `accelerate 1.14.0`, `torch 2.13.0+cu130` (CUDA 13.0 가용) |
| llama.cpp | 기존 핀 `D:\AIRI-Models\llama-b10375-bin-win-cpu-x64\llama-perplexity.exe` (CPU, 추가 설치 0) |
| 실행 방식 | Git Bash 스크립트 `run-lmeval.sh` / `run-perplexity.sh` (nohup, 로그 root에 보존) |
| 함정 | Windows PowerShell 5.1은 lm_eval의 stderr 경고를 `NativeCommandError`로 승격하고, `cmd.exe /c` 리다이렉트 경로에서는 프로세스가 CPU 21초·연결 0으로 멈췄다(PID 정지 후 Git Bash로 대체). `venv-lmeval\Scripts\python.exe`는 uv 트램폴린이라 실제 인터프리터는 자식 PID다 |

## 2. lm-evaluation-harness — 일반 능력 기준선

명령(모델당 동일, `run-lmeval.sh`):

```
python -u -m lm_eval --model hf --model_args "pretrained=<dir>,dtype=bfloat16" \
  --tasks kobest,haerae --num_fewshot 0 --batch_size 16 --seed 42 \
  --output_path lmeval/<name> --log_samples
```

| name | 모델 | 시작→종료 | exit | results JSON (sha256 앞 16자 / bytes) |
|---|---|---|---:|---|
| stock | `midm-2.0-mini-instruct-hf` | 16:38:43→16:45:52 | 0 | `f58250c93f3e7b05` / 30,890 |
| v3-merged | `airi-broadcast-v3-20260821\merged-hf` | 16:45:52→16:52:38 | 0 | `4a5f0fc995ccd934` / 31,036 |
| e2c2-merged | `airi-e2-c2-merged-20260824\merged-hf` (base safetensors `394b6624…`, adapter `f3d23950…`) | 16:52:38→16:59:07 | 0 | `a93df8857a449b3f` / 31,026 |

loglikelihood 요청 15,577건/모델, GPU 최대 4,955 MiB. 요약 `lmeval-summary.json`
(`70b9d12667a3ef1d`, 2,255 B, schema `airi.m2-greybox-lmeval-baseline.v1`).

| task (acc, 0-shot) | stock | v3-merged | e2c2-merged | Δv3 | Δe2c2 | stock se |
|---|---:|---:|---:|---:|---:|---:|
| **kobest** (group) | 0.6838 | 0.6786 | 0.6749 | −0.53%p | −0.90%p | 0.0064 |
| kobest_boolq (1,404) | 0.8746 | 0.8625 | 0.8533 | −1.21 | −2.14 | 0.0088 |
| kobest_copa (1,000) | 0.7680 | 0.7700 | 0.7750 | +0.20 | +0.70 | 0.0134 |
| kobest_hellaswag (500) | 0.4500 | 0.4340 | 0.4260 | −1.60 | −2.40 | 0.0223 |
| kobest_sentineg (397) | 0.7128 | 0.7103 | 0.6977 | −0.25 | −1.51 | 0.0227 |
| kobest_wic (1,260) | 0.4881 | 0.4881 | 0.4881 | 0 | 0 | 0.0141 |
| **haerae** (group) | 0.7195 | 0.7076 | 0.7003 | −1.19%p | −1.92%p | 0.0131 |
| haerae_general_knowledge (176) | 0.4545 | 0.4659 | 0.4148 | +1.14 | −3.98 | 0.0376 |
| haerae_history (188) | 0.8138 | 0.8191 | 0.7926 | +0.53 | −2.13 | 0.0285 |
| haerae_loan_word (169) | 0.7101 | 0.6568 | 0.6864 | −5.33 | −2.37 | 0.0350 |
| haerae_rare_word (405) | 0.7852 | 0.7926 | 0.7778 | +0.74 | −0.74 | 0.0204 |
| haerae_standard_nomenclature (153) | 0.7451 | 0.6797 | 0.7255 | −6.54 | −1.96 | 0.0353 |

**읽는 법(판정 아님, 기준선)**: 두 그룹 모두 stock > v3 > e2c2로 **단조 하락**이며 누적
LoRA 병합이 일반 한국어 능력을 조금씩 깎는다. 크기는 작다 — kobest −0.9%p(se 0.64의
1.4배), haerae −1.9%p(se 1.31의 1.5배)로 서베이가 제안한 **≤2%p 게이트 안**이지만 e2c2의
haerae는 경계에 붙어 있다. `kobest_wic`는 세 모델 동일(0.4881 ≈ 우연 수준)이라 이 모델
급에서 변별력이 없다. 게이트 값은 **제안일 뿐 확정·강제하지 않았다**(`lmeval-summary.json`
`gate_proposal.status`).

## 3. llama.cpp perplexity — v3 Q4_K_M 양자화 손실

텍스트: v3 chat jsonl(`airi-broadcast-v3-20260821\dataset\airi_broadcast_continuity_v3_chat.jsonl`,
1,440행)의 assistant 발화 2,280턴을 이어 붙인 `ppl-text-v3-assistant.txt`(126,257자,
sha256 `a9acf119f214c33f…`). **학습 데이터이므로 절대값이 아닌 bf16 대비 비율만 의미**한다.
blind v1~v4는 사용하지 않았다.

```
llama-perplexity.exe -m <gguf> -f ppl-text-v3-assistant.txt -c 2048 -b 2048 -t 12 --chunks 24
```

| GGUF (`airi-broadcast-v3-20260821\package-q4`) | 시작→종료 | exit | PPL | 로그 sha256 |
|---|---|---:|---|---|
| `airi-bf16.gguf` (4,617,053,152 B) | 16:34:30→16:45:50 | 0 | **4.2542 ± 0.068** | `d53ac36527c31805` |
| `airi-q4_k_m.gguf` (1,426,272,608 B) | 16:25:36→16:34:30 | 0 | **4.3310 ± 0.070** | `41c9bf30f84729bc` |

**비율 Q4/bf16 = 1.0181** — 서베이 제안 기준(≤1.05) 안. v3 Q4 패키징의 양자화 손실은
작고, `Q5_K_M` 검토 조건에 해당하지 않는다.

## 4. 함의와 남은 것

- 두 축 모두 **패키징 evidence 옆에 매 라운드 2~3줄로 남길 가치**가 있다(모델당 7분 +
  CPU 20분). 다음 학습 라운드가 있으면 merge 직후 같은 명령으로 재측정한다.
- 일반 능력 게이트(≤2%p)를 **강제**할지는 사용자 결정 사항이다. 지금은 기준선만 박제했다.
- 이 측정은 방송 게이트(D1 `no_winner`)와 무관하며 그 판정을 바꾸지 않는다.
- 도입하지 않은 것: Unsloth(현행 venv 핀 비호환, 학습 재개 자체가 별도 결정), TRL DPO
  (쌍 데이터 미확보).
