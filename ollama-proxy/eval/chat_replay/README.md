# Privacy-preserving local chat replay

This directory evaluates AIRI against authorized Korean livestream chat while
keeping real chat, identities, and responses out of git and normal reports. It
preserves event order, relative timing, source-text repeats, system noise, and
donation-event semantics. It does not imitate a named creator and it is not a
training-data pipeline.

The current foundation is ready for an authorized local capture, but no real
capture from the three target channels has been obtained or evaluated yet.
Public VOD/chat visibility is not collection permission.

## Official authorized YouTube LIVE capture

`collect_youtube_live_export.py` is the only provider collector currently
implemented. It reads a currently live, explicitly authorized YouTube broadcast
through the official `videos.list` and `liveChatMessages.list` endpoints. It is
not a VOD downloader and cannot recover an ended live chat. CHZZK and SOOP
remain provider-approved-envelope inputs only; no raw callback or public-player
collector is implemented for them.

The collector requires a local authorization document matching
`youtube-live-capture-authorization.schema.json`, the exact permission artifact
named by its provenance hash, the campaign identity key, and a YouTube API key.
All four inputs stay in ignored `local-replay-intake/`; the API key is read from
a file and is never accepted on the command line or written to output. The
authorization binds the exact video/channel/exporter, anonymous source slot,
phase, 30--120 minute duration, 300--20,000 event cap, redaction terms, and a
`provider_binding_hmac()` calculated with the same local identity key used by
normalization.

Do not construct the authorization or allowlist HMAC by hand. After a human has
verified the permission issuer, scope, retention window, and revocation state,
write one ignored request matching
`youtube-live-capture-preparation-request.schema.json`. Its exact shape is:

```json
{
  "schema_version": "airi.youtube-live-capture-preparation-request.v1",
  "operator_decision": {
    "authorization": "authorized",
    "authorization_basis": "operator_owned_broadcast",
    "authorized_at": "2026-08-15T00:00:00Z",
    "expires_at": "2026-08-15T03:00:00Z",
    "delete_by": "2026-08-16T00:00:00Z",
    "revoked": false,
    "purposes": ["local_replay_evaluation"]
  },
  "capture": {
    "provider": "youtube",
    "video_id": "LOCAL-VIDEO-ID",
    "channel_id": "LOCAL-CHANNEL-ID",
    "exporter_id": "airi-local-exporter",
    "source_slot": "channel_a",
    "phase": "opening",
    "duration_seconds": 1800,
    "max_events": 20000,
    "excluded_creator_names": ["local-redaction-term"]
  },
  "custody": {
    "provenance_file": "local-replay-intake/capture.permission.txt",
    "identity_key_file": "local-replay-intake/provider-identity.key"
  }
}
```

The custody paths use forward-slash relative paths from this directory. The
request, provenance file, and identity key must be three distinct files. Run
the offline preparer with a new, opaque bundle directory:

```powershell
python .\prepare_youtube_live_capture.py `
  --request .\local-replay-intake\capture-request.json `
  --output-dir .\local-replay-intake\capture-0123456789abcdef
```

It performs no network request and does not read an API key. It publishes only
`capture.authorization.json` and a one-entry
`provider-channel-allowlist.json` in the fresh bundle. It never merges or
overwrites a shared allowlist. The permission SHA and provider binding are
calculated mechanically, but their existence is not evidence that the operator
decision or permission issuer is genuine. Recheck permission and revocation
immediately before starting capture.

```powershell
python .\collect_youtube_live_export.py `
  --authorization .\local-replay-intake\capture-0123456789abcdef\capture.authorization.json `
  --provenance .\local-replay-intake\capture.permission.txt `
  --identity-key .\local-replay-intake\provider-identity.key `
  --api-key .\local-replay-intake\youtube-api.key `
  --output .\local-replay-intake\capture.safe.jsonl `
  --consent-output .\local-replay-intake\capture.consent-v2.json `
  --receipt .\reports\capture-live-receipt.json
```

Only publish time, event class, and text-message content cross the provider
message adapter. Provider-returned author IDs, profiles, display names and
message IDs, donation wording and amounts, page tokens, credentials, and raw
provider error text are not persisted. The explicitly authorized channel and
local exporter IDs do remain in the ignored safe-envelope header/events so the
normalizer can verify their local allowlist/HMAC binding and redact them before
model delivery. Messages returned from before the authorized start are
excluded. The collector honors the provider polling interval, bounds retries,
uses a no-proxy/no-redirect HTTPS transport, and stops on authorization expiry,
deletion deadline, explicit abort, live-chat end, byte/event limits, or unsafe
data. A successful run covers the whole requested interval and writes an exact
safe envelope, derived consent v2, and content-free HMAC receipt. Ordinary
write failures roll all three paths back. A process or power loss cannot make
three independent filesystem replacements globally atomic, so the operator
must require the capture receipt during normalization and run capture with
exclusive custody of these directories. Collector output uses the distinct
`airi.youtube-live-api-minimized.v1` source schema; for that schema the
normalizer rejects a missing, stale, or tampered capture receipt and verifies
its HMAC over both the exact export and canonical consent.

YouTube API-key reads are treated as non-authorized API data even when separate
creator permission exists: `delete_by` must be no later than 30 days after
capture starts, deletion/revocation controls remain mandatory, and unrelated
content owners are not combined unless the applicable permissions and platform
policy allow it. This collector has offline synthetic transport coverage only;
no real viewer chat has been captured by the repository batch.

## Custody and authorization

All raw exports, consent/provenance records, allowlists, local identity keys,
normalized exports, and private review packets must stay under the ignored
`local-replay-intake/` or `private-replays/` directories. Normal reports stay
under the ignored `reports/` directory. The CLIs reject paths outside those
directories or through a reparse point and write outputs with atomic
replacement.

The strict provider-safe normalizer accepts only
`airi.authorized-provider-export.v1` JSONL. It does **not** parse a CHZZK or SOOP
callback dump, a YouTube `liveChatMessage` resource, a VOD page, or an
unofficial historical-chat format. The provider labels only identify which
authorized exporter produced the safe envelope; they do not claim that any
platform offers a historical export API.

The first JSONL row is an exact header:

```json
{"record_type":"header","schema_version":"airi.authorized-provider-export.v1","provider":"chzzk","channel_id":"LOCAL-OPAQUE-ID","exporter_id":"LOCAL-EXPORTER-ID","source_schema":"provider-approved-envelope.v1","exported_at_ms":0}
```

Every following row has exactly `record_type`, `provider`, `channel_id`,
`occurred_at_ms`, `source_type` (`text`, `donation`, or `system`), and `text`.
There are no author/viewer/display-name/profile/amount fields. Order and equal
timestamps are preserved; decreasing timestamps, unknown fields, unsafe
Unicode, and more than 20,000 events fail closed. Donation text is always
replaced with `[후원 이벤트]`, so a donor name, wording, amount, or currency
cannot reach AIRI.

Normalization requires all of the following local-only inputs:

- an exact-source-hash consent v2 sidecar;
- the separate provenance/permission artifact bound by that sidecar;
- a strict channel allowlist;
- a 32-byte-or-longer local identity key;
- `capture_profile.source_slot` (`channel_a`..`channel_c`) and `phase`
  (`opening`, `middle`, `topic_transition`, or `game_transition`).

The allowlist and consent carry the same HMAC-SHA256 binding over provider,
channel, exporter, source schema, provenance hash, and anonymous source slot.
This protects against accidental cross-channel reuse and plain-SHA channel
fingerprints. It still does not authenticate the permission issuer: a human
must verify the written permission and its channel scope before normalization.
The local mapping from `channel_a`..`channel_c` to a creator never enters a
normal report.

Consent v2 has exactly these fields (values below are placeholders):

```json
{
  "schema_version": "airi.chat-replay-consent.v2",
  "authorization": "authorized",
  "authorization_basis": "creator_or_platform_written_permission",
  "authorized_at": "2026-08-15T00:00:00Z",
  "purposes": ["local_replay_evaluation"],
  "expires_at": "2026-08-16T00:00:00Z",
  "delete_by": "2026-08-16T00:00:00Z",
  "revoked": false,
  "source_sha256": "64-lowercase-hex-of-safe-envelope",
  "provenance_sha256": "64-lowercase-hex-of-permission-artifact",
  "excluded_creator_names": ["local-redaction-term"],
  "capture_profile": {
    "source_slot": "channel_a",
    "phase": "opening",
    "provider_binding_hmac": "64-lowercase-hex"
  }
}
```

The allowlist is `airi.provider-channel-allowlist.v1` with `entries`; each exact
entry contains `provider`, `channel_id`, `exporter_id`, `source_schema`,
`authorization_ref_sha256`, `source_slot`, `provider_binding_hmac`, `not_after`,
and `enabled`. The canonical calculation is the local
`provider_binding_hmac()` helper in `normalize_authorized_export.py`. Metadata
creation is intentionally an operator custody step: generating a syntactically
valid HMAC or sidecar does not establish that permission exists.

Example normalization for a YouTube live collector bundle (all files shown are
ignored):

```powershell
python .\normalize_authorized_export.py `
  --input .\local-replay-intake\capture.safe.jsonl `
  --consent .\local-replay-intake\capture.consent-v2.json `
  --capture-receipt .\reports\capture-live-receipt.json `
  --provenance .\local-replay-intake\capture.permission.txt `
  --allowlist .\local-replay-intake\capture-0123456789abcdef\provider-channel-allowlist.json `
  --identity-key .\local-replay-intake\provider-identity.key `
  --output .\local-replay-intake\capture.normalized.jsonl `
  --derived-consent-output .\local-replay-intake\capture.normalized.consent.json `
  --receipt .\reports\capture-normalization.json
```

`--capture-receipt` is mandatory for the YouTube live collector schema and is
not used for separately approved manual `provider-approved-envelope.v1`
exports.

The normalizer redacts declared creator names, header channel/exporter IDs,
URLs, handles, email, phone and resident-registration-number-shaped strings.
The normalized file contains only `timestamp_ms`, `kind`, and `text`. Automation
covers bounded explicit patterns, so a human privacy review is still mandatory
before model opt-in. Consent v1 remains accepted by the low-level importer for
older local artifacts, but the replay CLI requires consent v2 and its bound
capture profile.

## Flow and pattern report

The content-free report v3 includes duration, inter-arrival p50/p95/max and
rate, active fixed 5-second bins, the maximum count in a rolling half-open
5-second window, burst starts, duplicate/noise/eligible rates, and source-text
repeat clusters. Repeat detection happens before redaction in memory, so two
different source messages that collapse to the same placeholders are not
misclassified as repeats. Source text or its hash is never reported.

Bounded lexical surface signals are `question_mark`, `laughter_run`,
`correction_marker`, `emphasis`, `donation`, `noise`, and
`source_text_repeat`. Reports include counts and explicitly named adjacent
signal-pair counts. These are surface proxies, not proof of a joke, topic
transition, sentiment, or creator-specific style; those require private human
labels. Proxy response headers are reduced to a closed outcome enum for normal,
epistemic fallback, serious-safety, or input-screened behavior. Response text
is represented only by length and a local-key HMAC-SHA256 in the normal report,
so short responses do not leave a plain dictionary-testable fingerprint.

Before any model call, `offline_fixed_5s_response_sampler_v1` considers only
eligible events in fixed half-open `[k*5000,(k+1)*5000)` windows and sends at
most one event from each non-empty candidate window. Donation callouts and
question marks have priority; correction/emphasis/laughter and recent-selected
chat lexical overlap/novelty are deliberately narrow signals, so neutral
windows receive no reply. The v3 `response_sampling` summary is content-free
(no selected sequence IDs) and must match exactly between OFF/ON paired runs.
For model runs it is also covered by the run binding and report HMAC. It is an
offline sampling policy, not a live selector or a claim of semantic accuracy.

Actual campaign artifacts (unlike synthetic structure-only smoke tests) require
each anonymous source phase to be a contiguous 30–120 minute segment with
300–20,000 events. Each source needs at least two distinct qualifying phases;
in practice this means hundreds to thousands of chats. If a full VOD is longer,
split it into contiguous qualifying segments rather than treating a short
excerpt as campaign evidence. The response-sampling summary is HMAC-bound only
for model-run reports, where a run binding exists.

An offline structure-only run performs no network request:

```powershell
python .\run_chat_replay.py `
  --input .\local-replay-intake\capture.normalized.jsonl `
  --consent .\local-replay-intake\capture.normalized.consent.json `
  --provenance .\local-replay-intake\capture.permission.txt `
  --normalization-receipt .\reports\capture-normalization.json `
  --identity-key .\local-replay-intake\provider-identity.key `
  --report .\reports\capture-structure.json
```

The runner recomputes the normalization receipt HMAC over the exact normalized
bytes, provider class, bound source slot/phase, and provider-channel binding.
Missing or altered normalization evidence therefore fails before any model
request; a partially written normalization bundle is not replay-authorized.
Receipt v2 also carries a local-key `source_identity_hmac`, which stays stable
for the same provider/channel across exporters, schemas, phases, and anonymous
slots. This prevents one channel from satisfying multiple campaign slots.
The receipt HMAC itself becomes the per-capture `exact_capture_hmac`. These
values are local linking evidence only; the final campaign summary omits both.

For an explicitly approved Mi:dm experiment, add:

```powershell
--loopback-url http://127.0.0.1:11435/v1/chat/completions `
--model midm-airi:2.0-mini `
--expected-epistemic-confidence on `
--private-review-output .\private-replays\capture-review.json
```

Model opt-in is bounded before the first health request: the prepared capture
must contain 300..20,000 events spanning 30..120 minutes, and the fixed
offline sampler must select at least one and no more than
`--max-model-calls` events (default 1441). `--max-run-seconds` defaults to
7200 and applies a cooperative monotonic deadline to the complete
health-and-request sequence. Each request starts with a socket timeout capped
by the budget remaining at that point.
It cannot hard-cancel a malicious peer that continuously trickles response
headers or body bytes. The loopback reader accepts at most 64 KiB response bodies and
responses must be 1..4000 characters. For the frozen 2048-token profile,
history stays in complete exchange pairs and is conservatively limited to
6,000 history characters and a 12 KiB serialized request. Private review
packets are serialized once and rejected above 96 MiB before atomic replace;
the scorer applies the same 96 MiB limit. Paired campaign evidence uses the
frozen default call, deadline, history, and request limits; smaller CLI limits
are diagnostic-only and fail the campaign profile check.

Only literal loopback port 11435 is accepted. The runner never changes the
epistemic gate; it only asserts `on` or `off`. Before and after every turn and
the full run, it verifies the frozen Mi:dm tag, exact pinned/verified digest,
`num_ctx=2048`, and expected gate state. Requests use temperature 0, seed 42,
`max_tokens=128`, non-streaming output, and an eight-exchange bounded history.

## Human response review

The ignored private packet contains every redacted event, including skipped
noise and repeats, plus any response. At the capture level, a reviewer fills
the bounded `source_review` fields:

- `atmosphere`: `calm`, `playful`, `excited`, `tense`, `supportive`, `mixed`,
  or `unclear`;
- `pace`: `slow`, `steady`, or `bursty`;
- `context_pressure`: `low`, `medium`, or `high`;
- one to four sorted `dominant_patterns` from `question_wave`,
  `laughter_wave`, `correction_wave`, `donation_reaction`, `topic_shift`,
  `game_transition`, `repetition_wave`, `cross_viewer_followup`, or `unclear`.

For each event, the reviewer fills `expected_action` and, for delivered
responses, the booleans `grounded`, `context_preserved`, `tone_ok`,
`privacy_ok`, `current_fact_ok`, `reference_grounding_ok`, and
`agreement_calibration_ok`. There is no free-text review field. Then run:

```powershell
python .\score_private_review.py `
  --input .\private-replays\capture-review.json `
  --replay-report .\reports\capture-structure.json `
  --identity-key .\local-replay-intake\provider-identity.key `
  --report .\reports\capture-human-score.json
```

The replay report is HMAC-bound as a whole, and every private response is
checked against its sequence, length, outcome, and local-key response HMAC
before labels are accepted. The ordered per-event `respond|ignore` source
labels receive a separate HMAC so OFF/ON margins cannot hide label swaps. The
resulting score has its own local-key HMAC.
The score report contains only TP/FP/FN/TN, precision/recall/F1, bounded
quality pass rates, explicit privacy/current-fact/reference/agreement failure
counts, anonymous capture metadata, and text-free bindings. These selection
numbers evaluate the replay selector used by this harness—not the future
B1b/B4a live priority path.

## Three-source paired campaign

Create an ignored `airi.chat-replay-campaign-manifest.v1` under
`private-replays/`, following `campaign-manifest.schema.json` and
`OPERATOR-CHECKLIST.md`. It must reference 12 to 32 unique report/score
basenames under `reports/` and contain:

- three distinct anonymous source identities (`channel_a`..`channel_c`);
- at least two distinct phases for each source;
- exactly one epistemic OFF and one ON run for every exact capture;
- a fresh, at-most-24-hour operator attestation that permission scope,
  privacy review, retention/revocation state, and exclusive local-model
  execution were checked.

Aggregate only after every private review is complete:

```powershell
python .\aggregate_replay_campaign.py `
  --manifest .\private-replays\campaign.json `
  --identity-key .\local-replay-intake\provider-identity.key `
  --output .\reports\campaign-summary.json
```

The validator requires the exact frozen Mi:dm digest and profile, verifies the
replay and score HMACs, requires paired source/labels to match, and rejects
missing arms, changed identities, reused captures, profile drift, stale
attestation, and incomplete review. The output pools content-free flow,
surface-signal and human atmosphere/pattern counts once per source capture,
then reports OFF/ON response-quality, epistemic-outcome and critical-failure
differences. It omits source/provider identities, file paths, pair IDs,
digests, HMACs, response rows, and text. A passing campaign still says
`automatic_adoption: false` and requires explicit user confirmation.

AIRI live selection precision and end-to-end latency remain unproven until the
same capture is replayed through `screened event -> 11435 proxy -> style gate
-> public wire/TTS`.

Committed fixtures are independently authored synthetic material and are not
anonymized real chat. Revocation or retention expiry requires deleting the raw
export, normalized derivative, consent/provenance/allowlist records, and private
review packet. Run real replay only in an exclusive local operator session; a
hostile process performing an ABA swap between checks is outside this local
custody boundary.
