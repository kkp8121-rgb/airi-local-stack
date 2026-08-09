# AIRI style QLoRA review scaffold — local only

This is a scaffold, never an approval to train or deploy. The trainer is local-only, adapter-only, refuses remote models, GGUF, network paths, telemetry, CPU/multi-GPU fallback, and unsafe CUDA memory conditions. It re-verifies the exact dataset, manifest, C0/S1 fixtures, and closed immutable report before training.

## Production policy v3

Production requires at least 200 independently human-reviewed synthetic records, `training_eligible: true`, and S1 partition only. The exact ordered taxonomy is `banter`, `commentary`, `directness`, `seriousness`, `truthfulness`, `warmth`; each category has at least 20 records and splits are `train >=160`, `dev >=20`, `test >=20`.

Prompts are 1–280 characters with up to three sentences; answers are 1–160 characters with up to two. Both allow zero or one question mark, so neither requires a question-ending; question-ended answers are capped at 10 of 200 so missing-context clarification is represented without making the voice interrogation-heavy. Sentence detection covers `. ! ?` and `。！？`, while a natural unpunctuated short utterance is valid. Emoji, Markdown, controls, privacy-bearing fields/data, fixture overlap, mutable manifests, and non-independent reviewers are rejected.

C0 is frozen fixture-only material. C0 and S1 fixtures are mandatory and isolated from each other and reviewed data by IDs, groups, and prompt hashes. The schemas are `seed/airi_style_record.schema.json` and `seed/review-manifest.schema.json`.

## Pending review queue

Use the local human-review CLI with an explicit decision-sidecar output; it never modifies the pending input, a production dataset, or a manifest:

```powershell
python .\review_airi_style_pending.py --pending .\seed\airi_style_seed_pending.jsonl --decisions .\local-review-decisions.jsonl --reviewer "your-explicit-reviewer-id"
```

It displays one pending prompt/answer at a time. `approve` requires explicit `yes`, `no`, `yes` confirmation for VTuber voice, counselor tone, and safety/truth. `rewrite` and `reject` require notes; `skip` writes nothing. Existing decisions are skipped unless `--replace-decision` is supplied, and only the same reviewer may replace one. `--status` prints content-free counts, `--limit N` bounds a session, and sidecar writes are atomic.

`seed/airi_style_seed_pending.jsonl` is a separate S1-only synthetic pending queue, described by `seed/airi_style_pending_record.schema.json`. Run:

```powershell
python .\validate_airi_style_pending.py --dataset .\seed\airi_style_seed_pending.jsonl
```

It emits only a content-free count/category summary—never `VerificationResult`, an approved report, or a training authorization. Pending rows must remain `pending`, reviewer/approval time empty, and `training_eligible: false`; the production verifier and trainer reject them. Review decisions use `seed/airi_style_pending_decision.schema.json` (`approve`, `rewrite`, or `reject` plus voice/tone/safety fields). A decision cannot change eligibility.

Human identity, source custody, and any signature/key service are external governance duties; schema validation cannot authenticate a forged review.

Before human review, the pending gate also requires at least 200 rows, all category and split minimums, and at least 90% normalized answer uniqueness. It rejects normalized duplicate IDs, groups, and prompts; answers repeated three times; answer overlap between splits; a sentence repeated five times; English alphabet characters, Korean honorific endings, emoji, Markdown, control/format characters, and bidirectional controls in answers. These quality limits are pre-review screening only and do not grant approval, training eligibility, or authorization to train or deploy.
