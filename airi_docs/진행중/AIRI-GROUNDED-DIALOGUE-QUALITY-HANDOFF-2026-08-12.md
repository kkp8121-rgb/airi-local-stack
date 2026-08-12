# AIRI Grounded Dialogue Quality Handoff - 2026-08-12

Read these documents first, in order:

1. `AIRI-UPGRADE-SCOUT-2026-08-11.md`
2. `AIRI-UPGRADE-SCOUT-DATA-2026-08-11.md`
3. this handoff

This change continues from parent `1fc36ce` on
`feat/upgrade-scout-full-2026-08-11`. It improves grounded dialogue quality
without changing the model, the normal sampling defaults, approved-knowledge
fixtures, or operational knowledge deployment.

## Decision

Do not improve factuality by deleting, truncating, or suppressing a useful
answer. AIRI should keep user-supported content, give useful generic choices
or criteria, distinguish uncertainty, and ask a natural follow-up question.
Only unsupported external claims, fact reversals, and speaker reversals should
trigger a rewrite or bounded fallback.

The local Mi:dm model remains `midm-airi:2.0-mini`. A deterministic-temperature
trial reduced variation but did not solve avoidance or unsolicited advice, so
the normal `temperature`, `top_p`, and repeat-penalty defaults were not changed.

## Implemented scope

- A narrow open-question path covers meal/recommendation and current-local
  questions while excluding action requests and personal-past questions.
- The first draft may use generic options and decision criteria, but it may not
  invent weather, venue existence/location/opening, availability, price,
  popularity, hearsay, or other current external facts.
- A rejected open-question answer is rewritten as a complete useful answer,
  not stripped down. After two unsafe drafts, the fallback still offers
  concrete broad options and one preference question.
- Two-sentence open-question answers are held until their safe boundary and are
  preserved consistently on the wire and in the journal.
- Explicit positive/negative mood reversals are rejected.
- Explicit second-person actions such as `니가 수건 접었어.` may not be
  changed into a subjectless assistant confirmation such as `응, 접었어.`.
- Narrow conversational fallbacks remain complete and natural for positive
  mood, tiredness, and second-person attribution instead of returning
  `음, 잠깐만.`.
- A stdlib-only, loopback-enforced quality probe records every public synthetic
  answer, latency, empty/placeholder counts, and conservative groundedness
  flags. Its exact turn-origin header keeps the run outside normal memory and
  journal mutation; the CLI does not accept arbitrary private prompt text.

## Local measurements

Before this change, 20 runs of `점심 뭐 먹을까?` produced about eight hard
unsupported restaurant/hearsay claims, ten unsupported weather framings, and
one placeholder. A broader baseline also observed a positive-mood reversal;
`오늘은 조금 피곤해.` and `니가 수건 접었어.` frequently fell back to a
placeholder.

After the final change, 60 non-mutating local synthetic turns (six public
prompts, ten repeats) had p50 512.7 ms and p95 739.7 ms, with zero empty
answers, zero placeholders, zero transport errors, and zero probe-detected
groundedness violations after individual-answer review. Ten meal turns all
returned useful generic options without weather, venue, or popularity claims.
Ten positive-mood turns had zero mood reversals. Twenty statement/question
variants that attributed towel-folding to AIRI had zero false confirmations,
speaker reversals, invented actors, or placeholders.

These are local text-path measurements, not a physical microphone, Electron
playback, STT, or TTS acceptance run. The probe is intentionally conservative
and is not a general factual verifier. Six of ten meal samples used the rich
deterministic fallback, so future work may improve first-pass acceptance rate
without weakening groundedness or usefulness.

## Verification

Run from the repository root:

```powershell
python ollama-proxy\benchmark_dialogue_quality.py --repeat 10
.\test-current-checkpoint.ps1
python -m pytest -q ollama-proxy test_latency_trace.py test_start_airi_background.py latency-monitor stt
```

Final recorded results:

- quality probe: 60 samples, p50 512.7 ms, p95 739.7 ms, 0 empty, 0 placeholder,
  0 flagged violation, 0 transport error
- `test-current-checkpoint.ps1`: PASS; the explicitly offline applicability
  step remained an expected SKIP
- Python suite: 733 passed, 1 skipped, 504 subtests passed in 36.62 seconds
- `git diff --check`: PASS

The probe accepts only a loopback endpoint and uses `midm-airi:2.0-mini` by
default. It offers named public cases rather than arbitrary prompt input.
Inspect the emitted answers as well as the aggregate counters because
conversational quality cannot be reduced to a single lexical score.

## Evidence and limits

The official Mi:dm Mini model card and tokenizer configuration require the
bundled chat template and warn that factual inaccuracies remain possible:

- <https://huggingface.co/K-intelligence/Midm-2.0-Mini-Instruct>
- <https://huggingface.co/K-intelligence/Midm-2.0-Mini-Instruct/raw/main/tokenizer_config.json>
- <https://github.com/K-intelligence-Midm/Midm-2.0>

Self-RAG, FActScore, and RAGAS support evaluating evidence-grounded claims
together with usefulness and answer coverage rather than maximizing deletion:

- <https://arxiv.org/abs/2310.11511>
- <https://arxiv.org/abs/2305.14251>
- <https://docs.ragas.io/en/v0.4.3/concepts/metrics/available_metrics/>

Chain-of-Verification is a multi-pass pattern and was not added to this
latency-sensitive path: <https://aclanthology.org/2024.findings-acl.212/>.

Approved-knowledge fixture reproducibility and operational knowledge delivery
remain separate workstreams. Model replacement, broader streaming STT/AEC
changes, and any new runtime model transition also remain behind their own
Scout/Wave B evidence and physical-device gates.

## Next reviewer

Fetch `feat/upgrade-scout-full-2026-08-11`, review this branch from `1fc36ce`,
run the commands above, and inspect the individual probe answers. Treat a
shorter answer as an improvement only when it remains complete and useful. Do
not restore the earlier overlap-only acceptance path, and do not weaken the
speaker, polarity, wire/journal, or timeout contracts to increase first-pass
acceptance.
