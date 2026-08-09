# Local topic review workflow

This directory is the only permitted location for local source-policy registries,
raw discoveries, curations, pending topics, and human decisions. These local
artifacts are deliberately ignored by Git; do not commit them or a runtime board.

The workflow is offline only: it makes no network, RSS, model, or automatic-approval call.

1. Use a locally reviewed `source-policies*.json` registry and a policy-bound raw
   discovery JSONL under this directory.
2. Curate raw evidence into an immutable curation ledger and pending JSONL:

```powershell
python .\curate_raw_topics.py --source-policies C:\...\topic-review\source-policies.json --raw-discoveries C:\...\topic-review\raw.jsonl --curations C:\...\topic-review\curations.jsonl --pending C:\...\topic-review\pending.jsonl --curator curator-id
```

3. Review curated pending rows into an absolute decision JSONL:

```powershell
python .\review_pending_topics.py --source-policies C:\...\topic-review\source-policies.json --raw-discoveries C:\...\topic-review\raw.jsonl --curations C:\...\topic-review\curations.jsonl --pending C:\...\topic-review\pending.jsonl --decisions C:\...\topic-review\decisions.jsonl --reviewer reviewer-id
```

4. Compile only explicit approvals into an explicit path directly inside
   `ollama-proxy/runtime`:

```powershell
python .\compile_approved_topics.py --source-policies C:\...\topic-review\source-policies.json --raw-discoveries C:\...\topic-review\raw.jsonl --curations C:\...\topic-review\curations.jsonl --pending C:\...\topic-review\pending.jsonl --decisions C:\...\topic-review\decisions.jsonl --output C:\...\ollama-proxy\runtime\approved-topics.json
```

Pending records use `pending_schema_version: 1` and exactly these fields: `id`, `title`, `source`, HTTPS `source_url`, `published_at`, `summary`, `broadcast_line`, `expires_at`, and `review`. The review object must remain exactly `{ "status": "pending", "reviewer": "", "reviewed_at": "" }`; it has no `approved` field. `broadcast_line` must satisfy the current runtime loader's bounded, grounded, non-honorific Korean-line contract.

Decisions bind the whole canonical pending record with `record_sha256`. An `approve` requires every verification flag to be true. A `rewrite` or `reject` requires non-empty notes. Existing decisions may be replaced only with `--replace-decision` and only by the same reviewer. All writes are atomic.

The compiler preserves pending order, emits schema-v2 runtime fields plus immutable pending/decision provenance bindings, rejects stale hashes, malformed decisions, expired topics, and zero-live output, validates the temporary board with the current runtime loader, then intentionally atomically replaces the requested output only on success. A failure never overwrites the existing output. It never adds timestamps, so identical inputs produce identical bytes.

Runtime boards require root `approval_workflow_version: 1`. Each item binds its HTTPS source URL and canonical pending-record hash, then binds the canonical approving decision hash and all five confirmations. This is local human-governance provenance, not a cryptographic signature or independent proof of source truth.

CLI status and failures are content-free: they do not expose paths, IDs, source text, notes, or reviewer identity.

## Candidate collection (default OFF)

`collect_topic_candidates.py` is a raw-discovery-only merge boundary. Without
explicit `--enable-collection`, it exits successfully with a content-free
disabled status and performs no network call or file write. It has no built-in
source URL, source policy, HTTP client, or adapter. It never writes pending
records directly.

The standalone enabled CLI intentionally always rejects because no reviewed
source adapter is installed. A future adapter must independently enforce its
network, redirect, decompression, size, timeout, DNS/TLS, and peer-IP policy,
then call `collect_raw_discoveries` with strict raw-v1 records. The merge helper
accepts only records bound to the exact reviewed source-policy hash and writes
under an ownership-token sidecar lock. It never creates pending dialogue,
decisions, runtime boards, database records, model calls, or approvals.

## Raw discovery and curation

Raw discovery JSONL is untrusted evidence only. Raw title/snippet text is never
copied into prompts, speech, memory, runtime boards, decisions, or model input.
`curate_raw_topics.py` displays the evidence locally and requires a human to
enter the pending ID, Korean title/summary/broadcast line, expiry, and final
confirmation. Immutable source metadata is copied from the raw record and bound
by the full reviewed policy hash, raw-record hash, and metadata hash.

Raw records are accepted only with an explicit reviewed local source-policy registry. The registry binds policy ID, source kind and label, exact feed URL, article host/path prefix, exact license profile, reviewer, and UTC review time. A curator may record `curate`, `reject` with notes, or `skip`; only curated rows materialize pending records, while rejected and uncurated raw evidence remain out of pending/runtime.

Readers require the source-policy, raw-discovery, curation, and pending paths
together and reject partial, noncanonical, or tampered state. There is no
unbound pending compatibility path. Curation and pending writes hold both
sidecar locks in canonical order; repair may recreate a missing pending file
from an immutable canonical curation ledger, but never overwrite a mismatched
existing pending file.

If a process stops after replacing the curation ledger but before replacing the
pending file, the two artifacts intentionally fail closed. Preserve both files,
verify the curation ledger, move the mismatched pending file aside manually for
operator review, and run `--repair-from-curations` only after the pending path is
absent. The tool never deletes or overwrites that mismatched preimage. Do not
delete lock files while a writer may be running; all cooperative writers use the
same ownership-lock protocol and stale locks fail closed.

Unbound pending input is no longer accepted. Review and compilation require all
three paired discovery arguments: `--source-policies`, `--raw-discoveries`,
and `--curations`. Local source-policy registries are ignored as
`source-policies*.json`; do not commit a real registry.
