# B3-d Korean input-safety evaluator

This directory is a pure offline regression evaluator and gap inventory for AIRI's deterministic, rule-based input prefilter. It pins a synthetic Korean-first corpus and the active input-policy hash; it never contacts a model, service, proxy, Electron app, UI, TTS, or network.

The 100 `policy_contract` cases are the sole policy gate denominator. The 20 `semantic_gap` cases are `human_review_only`: the evaluator records their actual verdict histogram but assigns `exact: null` and never lets them pass, promote, or make a semantic-safety claim. Reports contain IDs, metadata, verdict fields, and hashes only—never source text, normalized text, or paths.

Run from the repository root:

`python -m unittest -v ollama-proxy/eval/input_safety/test_airi_ko_input_safety_eval.py`

`python ollama-proxy/eval/input_safety/run_airi_ko_input_safety_eval.py --output ollama-proxy/eval/results/local-b3d-input-safety-report.json`

The optional output path above is ignored. Do not commit generated reports.

B3-d remains overall **FAIL** and operationally **OFF**, even when the rule-policy contract is `PASS`. It is not a semantic classifier, jailbreak defense, live deployment proof, installed-AIRI proof, or evidence for model/proxy/Electron/UI/TTS behavior.
