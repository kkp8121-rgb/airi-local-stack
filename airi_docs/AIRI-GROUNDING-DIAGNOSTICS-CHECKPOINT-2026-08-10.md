# AIRI grounding diagnostics checkpoint — 2026-08-10

## Outcome

The local foreground grounding lane now records why a model draft was rejected
without retaining dialogue, lexical tokens, hashes, or request/session IDs.
The existing answer-selection expressions and short-circuit order are unchanged.
Diagnostics run only after the public terminal frame and completed-turn journal
scheduling, under an exception guard.

Only three new numeric fields are added to a grounding-retry `llm/end` event:

- `grounding_selected`: fixed result code (strict retry, safe retry, safe initial
  draft, deterministic observation, or content-free refusal);
- `grounding_initial_reject_mask`: bounded initial-draft reason mask;
- `grounding_retry_reject_mask`: bounded retry reason mask, including reserved
  bits for language, transport, timeout, tool-truth, and diagnostic failures.

The masks use bits 0–22 and are always below `2^23`. These three fields are
inserted before the latency monitor's 24-key retention boundary. Response
duration is captured before the diagnostic work, so rejection analysis does not
inflate the reported completion time.

## Verification

- Python compilation passed.
- Full proxy regression: 215 tests passed.
- Diagnostic exceptions cannot change the selected wire dialogue or journal.
- Timeout plus diagnostic-error bits and invalid-transport bits have focused
  regressions.
- `git diff --check` passed (line-ending warnings only).
- Independent review found no HIGH or MED implementation blocker after the
  bounded-mask revision.

## Focus-free measurement

After restarting only the exact loopback proxy process, three synthetic
server-channel turns were measured without UI focus:

- completion: 693–1015 ms;
- LLM terminal: 656.0–971.8 ms;
- two turns selected the deterministic fact-preserving observation and reached
  one TTS segment plus playback start;
- one turn selected content-free refusal, emitted no assistant text, and
  correctly produced no TTS/playback;
- all three used one corrective grounding attempt;
- no STT stage was involved.

The refused turn's two model drafts both failed full-surface preservation and
minimum grounding overlap. Its user sentence used a declarative ending that the
current deterministic observation fallback does not rewrite. This is now a
measured liveness/naturalness gap rather than an inferred one.

No raw dialogue, assistant text, session/round identifiers, microphone audio,
or content-derived hashes are recorded in this checkpoint.

## Next boundary

The next change should reduce content-free completions without weakening the
full-surface factual gate, adding another model call, or introducing a canned
response. A conservative exact-surface fallback or a better first-pass prompt
can be evaluated separately against the new reason masks.
