# Broadcast director core

`core.mjs` is an offline deterministic state machine using Node built-ins only (no external dependencies). It is default-off: call `createBroadcastDirector({ enabled: true })` to create one. Time is always supplied by the caller as a monotonic safe integer (`nowMs`); the module has no clocks, timers, files, network, logs, raw provider IDs, or persistence. This is B4a foundation code only: it supplies no live adapters or runtime completion integration.

Inputs are copied from strict data-descriptor snapshots (including frozen and null-prototype ingress objects). `submitChat` accepts the B1 screened event `{eventId, viewerKey, displayName, text, kind:'text', publishedAtMs}` and a separate `{priority}` classification. Chat text is limited to 1000 NFC code points. The core neither verifies nor derives identity HMACs, and never puts `viewerKey` into actions or stats. The bundled pure policy classifier is available after B1 screening, but composition remains explicit: no runtime or live adapter calls it automatically. Donations similarly accept pseudonym, display name, message, and timestamp—never an amount. Strings are NFC-normalized and timestamps may be no more than 30 seconds ahead of supplied wall time.

The schedule has six 20-minute blocks: 0–30s opening, 30s–15m development, then closing. Openings request an approved opaque topic lease. Development uses a one-at-a-time 3:2 closed/open question cycle: after an ask is explicitly completed, it waits exactly 12 seconds before emitting a self-answer if no higher-priority chat is queued. The final closing retains `final_qa`, `thanks`, `next_broadcast_preview`, and `broadcast_complete` until consumed.

Actions replay unchanged until exact `complete`; action IDs prevent ABA completion. Chat is strict priority (`question`, `topic_expansion`, `sincere_reaction`, `cheer`, `positive`) with FIFO inside a class. Capacity returns `backpressure` rather than dropping. Donations produce immediate name-only acknowledgement, then at a closing or explicit seam a private read request and a separate reaction request. Lease requests require `resolveLease`, not `complete`; active tokens are unique until the terminal lease-complete action succeeds. A failed terminal completion replays for delivery. Lease actions only pass opaque lease tokens; terminal releases carry delivered state. `kill`, `close`, and terminal broadcast completion return `leaseReleases`; callers MUST synchronously release every returned token before teardown. The provisional silence threshold defaults to 60 seconds and is constrained to 30–300 seconds.

`pause` freezes elapsed time and blocks intake/output. `kill` and `close` clear every queue, dedupe entry, and in-flight action. `stats()` returns count-only health fields, never payloads.
## B4 priority policy

`priority-policy.mjs` provides `classifyBroadcastPriority(screenedEvent)`, a pure,
deterministic Korean-first routing heuristic for the frozen B1 text event shape. It
applies this precedence: question, topic expansion, sincere reaction, cheer, then
positive. It keeps no chat data; valid inputs return only a frozen `{ priority }`
result and invalid inputs return `null`.

The classifier is not moderation and does not decide whether a message is allowed.
Its occasional misclassification can only reorder valid chat in the director; it
makes no claim to infer human intent accurately. This module has no runtime or live
adapter, and does not mark B4 as complete.
