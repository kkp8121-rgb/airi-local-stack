# AIRI G1a A4.2 must-act realization foundation

Date: 2026-08-17
Status: offline foundation implemented, locally verified, and independently reviewed

## Purpose

Following commit `a269cca` and the actual A4.1 run, fix the offline/default-inert
contract for a later must-act realization experiment. This record does not authorize
runtime behavior or operational adoption.

A4.1 condition B (`reply_act`) improved over `affect_only` on expected act (68.9%
vs 60.7%) and direction reversals (5 vs 10). It did not establish adoption: expected
act was only 68.9% for B versus 68.0% OFF, grounding was OFF 63.1% versus B 60.7%,
pathology was B 24 versus OFF 18, and donation thank was 0/3. The quality gate is
therefore **FAIL**; operational affect and reply-act contracts remain **OFF**.

## Fixed A4.2 boundary

The intended foundation is an input-free renderer for exactly these semantic acts:
`thank`, `deescalate`, `close`, `correct`, and `repair`, plus a content-free oracle.

It excludes all of the following:

- production endpoint;
- proxy runtime wiring;
- event mapper;
- B4b adapter;
- live model or TTS use;
- operational ON; and
- any change to B4a action shapes.

Ownership is deliberately separated: a future broadcast director selects the semantic
act; a proxy-side renderer realizes only constrained wording for that selected act; and
a future B4b adapter only delivers an approved artifact and reports the outcome. The
B4b adapter must never invent names, amounts, or other facts.

`deescalate` is permitted only with a trusted closed emergency marker. Deterministic
postconditions are structural checks only. They are not proof of factual grounding,
safety adequacy, emotion, or response quality. Human review remains required.

## Implemented files

The isolated implementation is:

- `ollama-proxy/eval/affect_broadcast/must_act_realization.py` — fixed five-act
  input-free renderer and structural postconditions;
- `ollama-proxy/eval/affect_broadcast/test_must_act_realization.py` — deterministic
  renderer, rejection, hash binding, and content-free oracle coverage; and
- `ollama-proxy/eval/affect_broadcast/must_act_realization_v1.json` — 31-entry
  content-free oracle pinned to the exact base fixture and reply-act sidecar.

Only the initial breathing-difficulty escalation at `fatigue-09` may use the closed
emergency marker. The ordinary fatigue warning and eight ongoing/third-party emergency
states are explicitly `human_review_only`: repeating an initial 119 instruction after
connection, responder dispatch, or third-party hearsay could regress the situation or
address the wrong person. The implementation does not modify a production endpoint,
proxy runtime, event mapper, B4b, live-model/TTS, or B4a action-shape file.

## Local validation

- `python -m unittest -v ollama-proxy/eval/affect_broadcast/test_must_act_realization.py
  ollama-proxy/eval/affect_broadcast/test_affect_broadcast_eval.py`: **27/27 PASS**.
- The evaluation CI shard now includes `test_must_act_realization.py`.
- `test-current-checkpoint.ps1`: **PASS** after staging the new CI-tracked test.
- Independent review found one purity-test AST gap for `from module import name`; the
  test now derives `ImportFrom` roots from `node.module` and includes a regression.
- A deeper guarded-compositor safety review found that one de-escalation template was
  not stage-correct for nine different states. The oracle was narrowed to one initial
  escalation and nine human-review routes before any derived comparison.
- Full diff-check is run at batch completion and recorded in the commit hand-off.
- CI execution is not claimed; it remains billing blocked.

## Next step

Design a distinct guarded model condition on top of this reviewed foundation. Do not
rerun or adopt it operationally until that separate condition is implemented and
reviewed.
