# AIRI Wikimedia topic intake checkpoint — 2026-08-10

## Outcome

A default-off Korean Wikimedia adapter now provides the first concrete source
for the local topic-review workflow. It can only append policy-bound raw
discovery evidence. It cannot create a pending topic, approve a line, compile a
runtime board, call a model, write memory, or make AIRI speak.

No real source-policy registry, contact address, topic evidence, curation,
decision, cache, or runtime board is included in this checkpoint. Enabling the
adapter still requires an operator-created reviewed policy and explicit CLI
arguments.

## Network and source boundary

- The source is fixed to Korean Wikipedia's `포털:요즘 화제` Action API page.
- A metadata request selects one exact current revision; a second request uses
  that revision's `oldid`. Page, revision, and response URL mismatches fail
  closed.
- DNS is resolved before connecting. Every returned address must be public and
  global. HTTPS connects to a pinned approved address, validates the
  `ko.wikipedia.org` certificate name, and verifies the actual socket peer.
- Redirects and compressed responses are not accepted. Response size, JSON,
  HTML, item count, URL shape, and one absolute collection deadline are bounded.
- Only direct items from top-level portal lists are retained. Nested lists,
  references, navigation, scripts, styles, non-article namespaces, controls,
  and duplicate URLs are discarded or reject the response.

## Cache and provenance boundary

The optional ETag cache is reusable only when it remains bound to all of the
following:

- the exact reviewed source-policy hash;
- the exact metadata request URL and portal revision timestamp;
- the rendered portal-body hash; and
- the canonical ordered raw-discovery snapshot hash and row count.

A cache/raw mismatch does not trigger a permissive fallback or overwrite.
`published_at` records when the portal revision exposed the item; it is not
presented as the linked article's original publication date. The reviewed
policy must bind the fixed portal attribution URL, `Wikipedia contributors`,
and CC BY-SA 4.0.

## Human gates that remain mandatory

1. A human creates and reviews the local source-policy registry.
2. The adapter may append raw evidence only when explicitly enabled.
3. A curator rewrites selected raw evidence into a Korean pending line.
4. A different explicit review decision verifies source, timestamp, grounding,
   line, and expiry.
5. The deterministic compiler creates a provenance-bound runtime board.
6. The startup validator must accept that board before proactive delivery.

The default remains no network fetch and no automatic broadcast.

## Verification

- Adapter-focused synthetic unit tests cover default-off behavior, pinned DNS
  and peer checks, exact revision flow, parser containment, encoding and size
  rejection, optional ETag behavior, cache/raw binding, deadline enforcement,
  exact license policy, and output-artifact isolation.
- Existing raw collection, discovery/curation, and human review workflow tests
  remain part of the checkpoint regression set.
- Tests use injected transports and synthetic HTML/JSON only; they do not fetch
  Wikimedia, call a model, start a service, or create real topic data.
