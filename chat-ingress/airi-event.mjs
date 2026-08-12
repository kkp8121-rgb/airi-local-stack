const EVENT_ID_RE = /^yt:v1:[A-Za-z0-9_-]{43}$/

export function toAiriEvent(ingress) {
  if (!ingress || typeof ingress !== 'object' || !EVENT_ID_RE.test(ingress.eventId)) {
    throw new TypeError('eventId must be a yt:v1 HMAC identifier')
  }
  if (typeof ingress.displayName !== 'string' || typeof ingress.text !== 'string') {
    throw new TypeError('ingress text fields are required')
  }
  return {
    type: 'input:text',
    data: { text: `[YouTube] ${ingress.displayName}: ${ingress.text}` },
    route: { delivery: { required: true } },
    metadata: { event: { id: ingress.eventId } },
  }
}
