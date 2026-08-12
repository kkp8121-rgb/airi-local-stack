# AIRI chat ingress (B1a)

This is an offline, transport-neutral YouTube chat admission core. It is disabled unless `AIRI_CHAT_INGRESS=on`; no adapter, WebSocket client, SDK, OAuth flow, persistence, or live polling is included.

When enabled, supply an identity key of at least 32 bytes and a screening callback to `createChatIngress`. Its result is awaited and only a literal `true` allows delivery. Accepted text and display names are normalized and held only in the bounded in-memory queue, then delivered through a caller-provided function. They are personal data and, after delivery, may enter the existing local AIRI history. B1a creates no persistence of its own.

`toAiriEvent(ingress)` builds the established fixed `input:text` envelope: `data.text`, `route.delivery.required: true`, and `metadata.event.id`. It emits no YouTube/viewer sidecar until that protocol is typed. Raw upstream identifiers are used transiently for HMAC pseudonyms and are neither retained nor emitted.

`toViewerObservation(ingress, { broadcastKey })` in `viewer-observation.mjs` is a separate, pure local-memory boundary for a screened ingress event. It accepts only the frozen ingress shape and a caller-supplied `broadcast:v1:` HMAC pseudonym, then returns a frozen observation containing only versioned HMAC event/viewer/broadcast keys, normalized display name, kind, and timestamp. It never includes chat text, raw YouTube IDs, or parsed `[YouTube]` envelope data. A future live adapter must derive the broadcast key with the same secret under a separate domain; it must never pass the provider's raw stream ID.

Future B1b persistence must write this observation separately before the unchanged `toAiriEvent` delivery. Identity-key rotation deliberately resets viewer identity unless an explicit migration is designed and approved.
