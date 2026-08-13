# AIRI chat ingress (B1a)

This is an offline, transport-neutral YouTube chat admission core. It is disabled unless `AIRI_CHAT_INGRESS=on`; no adapter, WebSocket client, SDK, OAuth flow, persistence, or live polling is included.

When enabled, supply an identity key of at least 32 bytes and a screening callback to `createChatIngress`. Its result is awaited and only a literal `true` allows delivery. Accepted text and display names are normalized and held only in the bounded in-memory queue, then delivered through a caller-provided function. They are personal data and, after delivery, may enter the existing local AIRI history. B1a creates no persistence of its own.

`toAiriEvent(ingress)` builds the fixed `input:text` envelope: `data.text`, `route.delivery.required: true`, and `metadata.event.id`. Its model-facing text contains the normalized chat body but deliberately omits the public display name; that name stays on the separate viewer-observation boundary instead of becoming prompt material. It emits no YouTube/viewer sidecar. Raw upstream identifiers are used transiently for HMAC pseudonyms and are neither retained nor emitted.

`toViewerObservation(ingress, { broadcastKey })` in `viewer-observation.mjs` is a separate, pure local-memory boundary for a screened ingress event. It accepts only the frozen ingress shape and a caller-supplied `broadcast:v1:` HMAC pseudonym, then returns a frozen observation containing only versioned HMAC event/viewer/broadcast keys, normalized display name, kind, and timestamp. It never includes chat text, raw YouTube IDs, or parsed `[YouTube]` envelope data. A future live adapter must derive the broadcast key with the same secret under a separate domain; it must never pass the provider's raw stream ID.

Future B1b persistence must write this observation separately before the unchanged `toAiriEvent` delivery. Identity-key rotation deliberately resets viewer identity unless an explicit migration is designed and approved.

## Local screened delivery spine

`proxy-screen.mjs` adapts the required screening callback to the exact loopback-only `/v1/airi/input-screen` contract. It screens the exact model-facing `[YouTube]` chat envelope, which contains no display name, accepts an exact content-free decision, and fails closed on timeout, transport failure, malformed data, or any non-loopback URL. A blocked public chat is consumed without AIRI delivery; direct local-user input is independently screened by the proxy, which can return the fixed AIRI fallback through the normal speech path.

`runtime.mjs` composes `createChatIngress → toAiriEvent → sendAiriLocalEvent`. It is still default-off and contains no YouTube transport, OAuth, polling, or persistence. Accepted events preserve the HMAC event ID through the authenticated loopback server channel; viewer keys and raw provider IDs never enter the AIRI envelope. Delivery failure remains retryable in the bounded ingress queue.

This closes only the local downstream seam. A real provider adapter, quota approval, operational enablement, and an installed-runtime behavioral rehearsal remain separate gates.

## Offline streamList quota measurement (B0-1)

`streamlist-quota.mjs` is a pure, offline measurement core for a future caller-owned streamList transport. It does not implement or live-call the official transport, use the filesystem, invoke AIRI ingress, or handle OAuth, API keys, SDKs, or networking. Any future live measurement requires explicit OAuth/API-key/quota approval.

The official transport is gRPC at `youtube.googleapis.com:443`. Official `streamList` uses `liveChatId` and `part`, and supplies `nextPageToken`; this module can pass a token transiently to an injected reconnect callback but never retains or emits it. Provider data and identifiers are never retained.

An injected future transport must honor the transient `AbortSignal` passed to `openStream`. A final already-received response batch can cross the configured message threshold; its actual bounded count is retained as measurement evidence.

A connection is counted as soon as the transport returns a stream, because anything discarded afterwards — a deadline that lands just past the open, a rejected iterator shape, or a batch received just past the deadline — has already consumed live quota. A batch discarded that way is recorded as `discardedResponses` instead of disappearing, so the served-response denominator for a manual quota delta is `responses + discardedResponses`. A reconnect trial that ends because the provider stopped supplying a page token reports `normal_close` at any configured connection count; `connection_cap` means only that the configured connection count was actually reached.

`StreamListQuotaError` stays exported so a caller can catch by type, but only errors this module raised itself are ever propagated. An error a transport constructs from that same class carries provider content, so it is sanitized into a stop reason like any other transport failure.

Take manual Cloud Console quota snapshots before and after a bounded trial, then pass only their numeric values and the fixed source label `manual_google_cloud_console_snapshot` to `assembleQuotaReport`. The official quota table currently does not publish a streamList cost, so the observed manual delta is evidence only; this module never infers undocumented pricing.
