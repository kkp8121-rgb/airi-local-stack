# AIRI grounding naturalness experiment — 2026-08-10

## Decision

Do not ship either corrective-prompt experiment. The production branch remains
at the exact-surface liveness checkpoint. No verifier, retry, selection,
boundary, wire, journal, application, or service code was retained from these
experiments.

The experiments called the already-running local Ollama model directly. They
did not pass through the proxy, application, memory journal, TTS, playback, or
external network. Only synthetic inputs were used, and only aggregate numeric
results are recorded here.

## Single-candidate preliminary result

A prompt aligned to the full-surface verifier was compared with the previous
anchor-ledger prompt on six fixed synthetic declaratives:

- previous prompt: strict accepted `0/6`, average `332.9 ms`;
- surface-aligned prompt: strict accepted `1/6`, average `237.1 ms`.

The small gain did not meet the release criterion, so the prompt-only patch was
fully reverted before any commit or service restart.

## Matched single versus structured candidates

Ten fixed synthetic declaratives were evaluated across three matched seeds per
arm. The structured arm requested exactly three candidates in one model call
and applied the unchanged production boundary and strict verifier offline.

Single candidate, 30 calls:

- strict-selected requests: `9/30`;
- non-exact verified endings: `9/30`;
- average: `233.2 ms`;
- p95: `255.0 ms`;
- maximum: `512.4 ms`.

Three structured candidates, 30 calls:

- schema parse: `30/30`;
- strict candidate available: `15/30`;
- non-exact first selected ending: `1/30`;
- average: `510.7 ms`;
- p95: `561.3 ms`;
- maximum: `574.4 ms`.

The structured prompt increased strict availability but usually placed the
exact punctuation-only echo first, worsening the natural-ending result while
roughly doubling latency.

## Exact candidate last

A final 30-call variant required the exact punctuation-only candidate to be the
third item so verified natural endings could appear first:

- schema parse: `30/30`;
- strict-selected requests: `7/30`;
- non-exact verified endings: `5/30`;
- average: `494.8 ms`;
- p95: `568.8 ms`;
- maximum: `701.9 ms`.

This underperformed the single-candidate strict and non-exact selection rates,
so the multi-candidate branch was also rejected without implementation.

## Boundary for next work

The current full-surface verifier intentionally allows ending/prosody changes,
not a genuinely new reaction. More candidate sampling does not resolve that
architectural constraint and adds latency. The next naturalness proposal must
therefore provide a separately auditable semantic-safety boundary or use a
human-approved style-training path. It must not weaken full-surface, quotation,
role, polarity, Latin-case, tool-truth, terminal, or canonical wire/journal
guarantees.

No raw model output, dialogue, prompt text, session/round identifier,
content-derived hash, microphone audio, or local absolute path is recorded in
this checkpoint.
