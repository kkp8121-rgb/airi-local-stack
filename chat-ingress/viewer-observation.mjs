const INGRESS_KEYS = ['displayName', 'eventId', 'kind', 'publishedAtMs', 'text', 'viewerKey']
const OPTIONS_KEYS = ['broadcastKey']
const EVENT_ID_RE = /^yt:v1:[A-Za-z0-9_-]{43}$/
const VIEWER_KEY_RE = /^viewer:v1:[A-Za-z0-9_-]{43}$/
const BROADCAST_KEY_RE = /^broadcast:v1:[A-Za-z0-9_-]{43}$/
const BIDI = /[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/u
const DISALLOWED_CONTROL = /[\u0000-\u0008\u000e-\u001f\u007f-\u009f]/u
const MAX_DISPLAY_NAME_CODE_POINTS = 80

function isWellFormed(value) {
  for (let index = 0; index < value.length; index++) {
    const code = value.charCodeAt(index)
    if (code >= 0xd800 && code <= 0xdbff) {
      if (index + 1 >= value.length) return false
      const next = value.charCodeAt(++index)
      if (next < 0xdc00 || next > 0xdfff) return false
    } else if (code >= 0xdc00 && code <= 0xdfff) return false
  }
  return true
}

function safeRecord(value, keys, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    throw new TypeError(`${label} must be a plain record`)
  }
  const ownKeys = Reflect.ownKeys(value)
  if (ownKeys.some(key => typeof key !== 'string')) throw new TypeError(`${label} must not contain symbols`)
  const sorted = [...ownKeys].sort()
  if (sorted.length !== keys.length || sorted.some((key, index) => key !== keys[index])) throw new TypeError(`${label} has unsupported fields`)
  const snapshot = Object.create(null)
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key)
    if (!descriptor || !Object.hasOwn(descriptor, 'value') || descriptor.get || descriptor.set) throw new TypeError(`${label}.${key} must be a data property`)
    snapshot[key] = descriptor.value
  }
  return Object.freeze(snapshot)
}

function normalized(value, maxCodePoints, label) {
  if (typeof value !== 'string' || !isWellFormed(value) || BIDI.test(value) || DISALLOWED_CONTROL.test(value)) throw new TypeError(`${label} must be safe text`)
  const result = value.normalize('NFC').trim().replace(/\s+/gu, ' ')
  if (!result || Array.from(result).length > maxCodePoints) throw new TypeError(`${label} is out of bounds`)
  return result
}

/**
 * Build the content-free, local viewer-memory observation from one screened
 * ingress event. This deliberately excludes `text` and every raw provider ID.
 */
export function toViewerObservation(ingress, options) {
  const admitted = safeRecord(ingress, INGRESS_KEYS, 'ingress')
  const admittedOptions = safeRecord(options, OPTIONS_KEYS, 'options')
  if (!EVENT_ID_RE.test(admitted.eventId)) throw new TypeError('eventId must be a yt:v1 HMAC identifier')
  if (!VIEWER_KEY_RE.test(admitted.viewerKey)) throw new TypeError('viewerKey must be a viewer:v1 HMAC identifier')
  if (!BROADCAST_KEY_RE.test(admittedOptions.broadcastKey)) throw new TypeError('broadcastKey must be a broadcast:v1 HMAC identifier')
  if (admitted.kind !== 'text') throw new TypeError('kind must be text')
  if (!Number.isSafeInteger(admitted.publishedAtMs) || admitted.publishedAtMs < 0) throw new TypeError('publishedAtMs must be a non-negative safe integer')
  // Validate but never copy text. Its absence from the returned object is an
  // intentional privacy boundary, not an omission callers may fill later.
  normalized(admitted.text, 1000, 'text')
  return Object.freeze({
    eventId: admitted.eventId,
    viewerKey: admitted.viewerKey,
    displayName: normalized(admitted.displayName, MAX_DISPLAY_NAME_CODE_POINTS, 'displayName'),
    kind: admitted.kind,
    publishedAtMs: admitted.publishedAtMs,
    broadcastKey: admittedOptions.broadcastKey,
  })
}
