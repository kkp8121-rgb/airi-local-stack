# Local topic review workflow

This directory is the only permitted location for local source-policy registries,
raw discoveries, curations, pending topics, and human decisions. These local
artifacts are deliberately ignored by Git; do not commit them or a runtime board.

Human curation, review, and compilation are offline only: they make no network,
model, or automatic-approval call. Optional source adapters are separate,
explicitly enabled intake steps and may write only untrusted raw evidence.

1. Use a locally reviewed `source-policies*.json` registry and a policy-bound raw
   discovery JSONL under this directory.
2. Curate raw evidence into an immutable curation ledger and pending JSONL:

```powershell
$reviewRoot = (Resolve-Path .\topic-review).Path
python .\curate_raw_topics.py --source-policies (Join-Path $reviewRoot source-policies.json) --raw-discoveries (Join-Path $reviewRoot raw.jsonl) --curations (Join-Path $reviewRoot curations.jsonl) --pending (Join-Path $reviewRoot pending.jsonl) --curator curator-id
```

3. Review curated pending rows into an absolute decision JSONL:

```powershell
python .\review_pending_topics.py --source-policies (Join-Path $reviewRoot source-policies.json) --raw-discoveries (Join-Path $reviewRoot raw.jsonl) --curations (Join-Path $reviewRoot curations.jsonl) --pending (Join-Path $reviewRoot pending.jsonl) --decisions (Join-Path $reviewRoot decisions.jsonl) --reviewer reviewer-id
```

4. Compile only explicit approvals into an explicit path directly inside
   `ollama-proxy/runtime`:

```powershell
$runtimeRoot = (Resolve-Path .\runtime).Path
python .\compile_approved_topics.py --source-policies (Join-Path $reviewRoot source-policies.json) --raw-discoveries (Join-Path $reviewRoot raw.jsonl) --curations (Join-Path $reviewRoot curations.jsonl) --pending (Join-Path $reviewRoot pending.jsonl) --decisions (Join-Path $reviewRoot decisions.jsonl) --output (Join-Path $runtimeRoot approved-topics.json)
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

The standalone enabled CLI intentionally always rejects because source-specific
network policy belongs to a reviewed adapter. An adapter must independently
enforce its redirect, encoding, size, deadline, DNS/TLS, and peer-IP policy,
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

### Wikimedia source-policy creation (default OFF)

`create_wikimedia_source_policy.py` is the offline human gate that can create
the fixed Korean Wikimedia policy required by the optional adapter. Without the
exact `--create-wikimedia-policy` flag it emits a content-free disabled status
before parsing arguments, reading a path or clock, prompting, locking, or
writing. It never fetches a page, starts a service, or creates raw discoveries,
pending topics, decisions, runtime boards, prompts, speech, memory, or model
input.

Use a real local reviewer identity and an absolute output under this directory:

```powershell
$reviewRoot = (Resolve-Path .\topic-review).Path
python .\create_wikimedia_source_policy.py `
  --create-wikimedia-policy `
  --output (Join-Path $reviewRoot source-policies.json) `
  --policy-id ko-wikipedia-portal `
  --reviewer reviewer-id
```

The reviewer must then type, in order, `approve-source`, `approve-license`, and
the exact policy ID. EOF, interruption during confirmation, or a mismatch
cancels without writing. The resulting canonical registry fixes the Korean
Wikipedia Action API host/path, portal attribution, and CC BY-SA 4.0 license;
it does not store the operational User-Agent contact. The same policy and same
reviewer are idempotent and preserve the original review timestamp and bytes.
An ID collision, different reviewer, noncanonical registry, concurrent owner,
or changed target fails closed. Cooperative writes use an ownership-token lock,
revalidate the production policy contract, and replace atomically only on
success.

This is a local human-governance record and hash binding, not a signature or an
independent verification of Wikipedia content. The registry remains ignored by
Git. This repository intentionally contains no real reviewer identity, contact,
created source-policy registry, raw discovery, or approval decision.

### Read-only workflow status (default OFF)

`topic_workflow_status.py` reports the first incomplete validated boundary
without exposing any path, policy ID, topic ID, source text, reviewer, hash, or
timestamp. Without the exact `--inspect-topic-workflow` flag it emits a fixed
disabled object before parsing or touching any path, file, clock, lock, or
network dependency.

```powershell
$reviewRoot = (Resolve-Path .\topic-review).Path
$runtimeRoot = (Resolve-Path .\runtime).Path
python .\topic_workflow_status.py `
  --inspect-topic-workflow `
  --source-policies (Join-Path $reviewRoot source-policies.json) `
  --raw-discoveries (Join-Path $reviewRoot raw.jsonl) `
  --curations (Join-Path $reviewRoot curations.jsonl) `
  --pending (Join-Path $reviewRoot pending.jsonl) `
  --decisions (Join-Path $reviewRoot decisions.jsonl) `
  --runtime-board (Join-Path $runtimeRoot approved-topics.json) `
  --policy-id ko-wikipedia-portal
```

The fixed stage enum is `policy_required`, `raw_required`,
`curation_required`, `review_required`, `compile_required`, `ready`, or
`rejected`. Counts cover only policies, raw rows, curations, pending rows,
decisions, approvals, and live runtime items. A runtime board is `ready` only
when it is live and its bytes exactly equal the deterministic board derived
from the currently bound pending and decision records. Expired or future
approvals are never reported as compilable.

The inspector is strictly read-only: it creates no missing file, takes no lock,
and never starts collection, compilation, a service, model, prompt, speech, or
memory operation. Because it intentionally does not block cooperative writers,
run it while the scheduler, curator, reviewer, and compiler are stopped. A
concurrent artifact change may produce a fail-closed `rejected` snapshot; rerun
after the writer exits.

### Optional Korean Wikimedia raw adapter (default OFF)

`wikimedia_topic_source.py` requires `--enable-wikimedia`, absolute local
policy/raw/cache paths, a policy ID, and a Wikimedia-style
`name/version (email-or-https-contact)` User-Agent. There is no bundled real
policy, contact, schedule, or enable flag. It fetches only the fixed
`포털:요즘 화제` page through at most two serial Action API requests: current
revision metadata, then rendered HTML for that exact `oldid` unless a strictly
bound 304 cache is reusable. It does not widen
to another page or section when the expected structure is absent.

Before connecting, every DNS answer must be a public global address. The HTTPS
socket connects to one of those pinned addresses, validates TLS for
`ko.wikipedia.org`, and then verifies the actual peer against the approved set.
Redirects, compressed responses, unexpected URLs/statuses, oversized bodies,
deadline overruns, malformed JSON/HTML, unsafe links, and mismatched revisions
fail closed. Only direct items from top-level portal lists are considered;
nested/reference/navigation content is discarded, bounded, and still treated
as untrusted evidence for a human curator.

An optional ETag is reused only while the canonical raw snapshot, policy hash,
portal revision timestamp, and rendered-body hash still match the cache. The
cache and all real review artifacts are ignored by Git. The adapter writes raw
discovery rows only—never pending topics, decisions, prompts, speech, memory,
runtime boards, database records, or approvals. The raw `published_at` is the
portal revision timestamp that exposed the item, not a claim about the linked
article's original publication date.

The reviewed policy must bind `Wikipedia contributors`, the fixed portal URL,
and the CC BY-SA 4.0 license URL. Human-curated downstream use must preserve
that attribution and identify transformed excerpts. Operational behavior
follows the official [Action API revision](https://www.mediawiki.org/wiki/API:Revisions),
[parse](https://www.mediawiki.org/wiki/API:Parsing_wikitext),
[API etiquette](https://www.mediawiki.org/wiki/API:Etiquette/en), and
[maxlag](https://www.mediawiki.org/wiki/Manual:Maxlag_parameter) guidance;
reuse follows the [Wikimedia Terms of Use](https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use/en).

### Optional raw intake schedule (default OFF)

`wikimedia_topic_scheduler.py` is a separate foreground scheduler for the raw
adapter. Neither local-stack launcher imports or starts it. Without the exact
`--enable-wikimedia-schedule` flag it emits only `{"status":"disabled"}` and
does not parse paths, acquire a lock, read a clock, sleep, fetch, or write.

An operator may start it only after creating the ignored reviewed policy and
choosing a real Wikimedia-compliant contact value:

```powershell
$userAgent = Read-Host 'Wikimedia User-Agent: name/version (email-or-https-contact)'
python .\wikimedia_topic_scheduler.py `
  --enable-wikimedia-schedule `
  --source-policies (Join-Path $reviewRoot source-policies.json) `
  --raw-discoveries (Join-Path $reviewRoot raw.jsonl) `
  --cache (Join-Path $reviewRoot .wikimedia-topic-cache.json) `
  --policy-id ko-wiki `
  --user-agent $userAgent
```

The default success interval is six hours; the default failure retry is 15
minutes. Explicit intervals are bounded to 15 minutes–24 hours and retries to
1–60 minutes. Collection is serial and completion-based, so a slow request
cannot overlap the next cycle. One ownership sidecar is held for the scheduler
lifetime; a second process fails closed. A crash can leave a stale ignored lock,
which must be reviewed only after confirming no scheduler is still running.

Scheduler output is limited to the content-free statuses `disabled`,
`complete`, `rejected`, and `stopped`. A rejected cycle waits for the bounded
retry interval; it does not loosen validation. The scheduler owns no queue or
state file and still cannot create pending topics, decisions, runtime boards,
prompts, speech, memory, or approvals. Stop it before inspecting or changing
its local source-policy/cache configuration.
