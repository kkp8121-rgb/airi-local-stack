# AIRI exact-surface fallback checkpoint — 2026-08-10

## Outcome

The local foreground grounding lane no longer has to finish silently after two
completed model drafts fail the factual-preservation gate. For a deliberately
narrow Korean declarative shape, the deterministic recovery keeps the complete
NFKC-normalized user surface and changes only the final ASCII period to an
exclamation mark. It adds no word, inferred emotion, judgment, cause, or model
request, and the existing full-surface verifier still approves the result.

The punctuation-only path requires an overt `이/가` nominative outside balanced
quotations. Subjectless commands and offers remain content-free. Period-written
question endings `-까`, `-니`, `-냐`, `-지`, and `-나` are explicitly excluded,
as are existing personal-deixis, control, language, knowledge, safety, label,
ellipsis, multi-sentence, and unbalanced-quote cases.

A grounding retry must also reach an actual upstream terminal item. When a
complete retry sentence closes the public boundary before Ollama's following
terminal row arrives, the proxy now keeps reading only inside the existing
corrective deadline. Timeout, invalid transport, language rejection, and EOF
without a terminal remain content-free and are never journaled.

## Verification

- Python compilation passed.
- Full proxy regression: 217 tests passed.
- Focused regressions cover a split content/terminal retry, incomplete retry
  EOF, commands, period-written questions, balanced reported speech, personal
  deixis, and exact wire/journal identity.
- `git diff --check` passed (line-ending warnings only).
- Independent read-only review found no remaining HIGH or MED release blocker.

## Focus-free measurement

After restarting only the exact loopback proxy process, one synthetic
server-channel turn exercised the new path without UI focus:

- input length: 18 characters;
- assistant length: 18 characters;
- matching completion: 1141 ms;
- LLM terminal duration: 1095.5 ms;
- grounding selection: deterministic exact-surface (`4`);
- TTS: one segment with first audio observed;
- playback start: observed.

No raw dialogue, assistant text, session/round identifiers, microphone audio,
or content-derived hashes are recorded in this checkpoint.

## Known limit

This is a liveness safeguard, not a naturalness solution. When both model drafts
are unsafe, the response deliberately echoes the verified observation with only
terminal prosody changed. A later naturalness experiment must preserve the same
fact, role, quotation, polarity, and terminal-stream boundaries and must not
weaken this fail-closed verifier.
