# System1 candidate judge — evaluation pipeline (2026-09-23)

Evaluation-only. Nothing here changes the operational proxy, the installed AIRI app, or any
default. Results and the reasoning behind them: `airi_docs/진행중/AIRI-SYSTEM1-CANDIDATE-JUDGE-2026-09-23.md`.

The judge is a Qwen2.5-0.5B (Apache-2.0) sequence classifier with a LoRA adapter and a trained
1-logit head. It scores one `viewer_reaction` candidate (`채팅: …\n반응: …`, see
`ollama-proxy/eval/broadcast_sim/system1_judge.py`) so the VOD storyline runner can stop at the
first acceptable candidate (`--candidate-select system1-early-exit`) instead of generating 16.

| File | Role |
|---|---|
| `make_variants.py` | storyline variants: same scenes/beats/spine, other real (pseudonymized) chats from each scene's time window; the fixed storyline's 32 staged chats are excluded (held out) |
| `label_candidates.py` | extract valid candidates from runner reports; deterministic checks + teacher rubric via an OpenAI-compatible llama-server |
| `teacher_prompt.py` | teacher rubric and acceptance rule v2 |
| `teacher_gold.jsonl`, `teacher_gold_check.py` | 16-item **AI-authored** gold set (not human-rated) used to pick the teacher |
| `train_system1.py` | LoRA + head training, AUC/Brier/ECE, reload check, GPU/CPU latency |
| `eval_chosen.py` | teacher-judge the reaction each run finally chose |
| `midm-airi-chat.jinja` | Llama-3 header template without the Mi:dm default preamble, for llama-server `--chat-template-file` (see the Ollama 0.34 finding in the results doc) |

Environment used: training venv outside the repo (`torch` cu128 build — the pinned
`requirements-training.txt` torch 2.5.1 predates the RTX 50xx sm_120 architecture), Ollama-bundled
`llama-server` started with its working directory at `lib/ollama/cuda_v13`, repository shim
`ollama-proxy/eval/llama_server_shim.py` on 11434, proxy via `start-local-ollama-proxy.ps1`.
Paths inside the scripts are absolute (`C:\AIRI-Models\…`, `C:\Projects\airi-local-stack\…`).
Labels, reports, adapters and review pages carry response text and stay outside Git.
