# Local topic review workflow

This directory is the only permitted location for local pending-topic JSONL and human decision JSONL. The files are deliberately ignored by Git; do not commit a pending queue, decisions, or a runtime board.

The workflow is offline only: it makes no network, RSS, model, or automatic-approval call.

1. Place an absolute, regular, non-symlink pending JSONL under this directory.
2. Review it into an absolute decision JSONL under this directory:

```powershell
python .\review_pending_topics.py --pending C:\...\ollama-proxy\topic-review\pending.jsonl --decisions C:\...\ollama-proxy\topic-review\decisions.jsonl --reviewer reviewer-id
```

3. Compile only explicit approvals into an explicit output path directly inside `ollama-proxy/runtime`:

```powershell
python .\compile_approved_topics.py --pending C:\...\pending.jsonl --decisions C:\...\decisions.jsonl --output C:\...\ollama-proxy\runtime\approved-topics.json
```

Pending records use `pending_schema_version: 1` and exactly these fields: `id`, `title`, `source`, HTTPS `source_url`, `published_at`, `summary`, `broadcast_line`, `expires_at`, and `review`. The review object must remain exactly `{ "status": "pending", "reviewer": "", "reviewed_at": "" }`; it has no `approved` field. `broadcast_line` must satisfy the current runtime loader's bounded, grounded, non-honorific Korean-line contract.

Decisions bind the whole canonical pending record with `record_sha256`. An `approve` requires every verification flag to be true. A `rewrite` or `reject` requires non-empty notes. Existing decisions may be replaced only with `--replace-decision` and only by the same reviewer. All writes are atomic.

The compiler preserves pending order, emits schema-v2 runtime fields plus immutable pending/decision provenance bindings, rejects stale hashes, malformed decisions, expired topics, and zero-live output, validates the temporary board with the current runtime loader, then intentionally atomically replaces the requested output only on success. A failure never overwrites the existing output. It never adds timestamps, so identical inputs produce identical bytes.

Runtime boards require root `approval_workflow_version: 1`. Each item binds its HTTPS source URL and canonical pending-record hash, then binds the canonical approving decision hash and all five confirmations. This is local human-governance provenance, not a cryptographic signature or independent proof of source truth.

CLI status and failures are content-free: they do not expose paths, IDs, source text, notes, or reviewer identity.
