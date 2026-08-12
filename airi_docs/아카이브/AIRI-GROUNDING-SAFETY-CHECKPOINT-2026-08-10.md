# AIRI grounding safety checkpoint — 2026-08-10

## Outcome

Foreground Korean grounding now fails closed unless the accepted model draft
preserves the user's complete NFKC-normalized surface token sequence. Internal
punctuation, quote boundaries, Latin identifier case, semantic polarity and
the factual order of every token are retained. Only a verified final Korean
declarative ending and the final period/exclamation mark may vary.

The deterministic observation fallback uses the same boundary, requires one
complete declarative sentence, rejects ellipsis and unbalanced quotations, and
continues to send and journal one identical canonical dialogue string.

## Rejected unsafe designs

- Broad Korean suffix rewrites were removed after a homograph changed the
  meaning of an otherwise matching sentence.
- Bag-of-words and ordered-subsequence checks were rejected because they could
  reverse subject/object roles or join facts from different clauses.
- Contiguous proper-subspan acceptance was rejected because it could remove
  uncertainty, dream context, or reported-speech attribution.
- Particle inference was rejected because a bare Korean noun can end in the
  same syllable as a grammatical particle.
- Case-folded surface matching was rejected because it changes identifiers and
  brand-like Latin tokens.

## Verification

- Python compilation passed.
- Grounding-focused proxy tests: 15 passed.
- Full proxy regression: 212 passed.
- Independent adversarial review found no remaining HIGH or MED safety blocker.
- `git diff --check` passed (line-ending warnings only).

A focus-free loopback server-channel probe was run after restarting only the
local proxy with the modified source:

- request/completion succeeded without UI focus;
- LLM terminal duration: 2372.3 ms;
- one TTS segment completed in 1823.4 ms;
- playback-start telemetry followed TTS completion by 8 ms;
- no STT stage was involved;
- both model drafts failed the stricter grounding boundary and the canonical
  full-observation fallback was used.

No raw dialogue, session identifiers, round identifiers, or microphone audio
are recorded in this checkpoint.

## Known limits and next work

- The safe full-observation fallback remains repetitive. This checkpoint does
  not claim that dialogue naturalness is solved.
- Balanced ASCII single-quoted reported speech remains fail-closed because an
  apostrophe-safe parser was not introduced. Double and Korean quote pairs are
  handled.
- The existing per-stage watchdogs do not yet constitute one hard end-to-end
  eight-second foreground deadline.
- The next naturalness experiment must not weaken full-surface factual
  preservation or add another model call. It should be measured separately.

## Proactive broadcast boundary

The governed topic workflow remains at `policy_required` with all governed
artifact counts zero. The synthetic/offline topic regression suite passed 72
tests, but no production topic board was created or enabled. Human source-policy
approval, collection authorization, curation, and explicit topic approval are
still required before compilation and activation.
