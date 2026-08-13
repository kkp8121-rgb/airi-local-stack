const EVENT_KEYS = Object.freeze(['eventId', 'viewerKey', 'displayName', 'text', 'kind', 'publishedAtMs'])
const DECISION_KEYS = Object.freeze(['version', 'allowed', 'category', 'rule'])
const ID_RE = /^(?:yt:v1:|viewer:v1:)[A-Za-z0-9_-]{43}$/
const LABEL_RE = /^[a-z][a-z0-9_]{0,63}$/
const BIDI = /[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/u
const CONTROL = /[\u0000-\u0008\u000e-\u001f\u007f-\u009f]/u
const TIMED_OUT = Symbol('timed-out')
const FAILED = Symbol('failed')

function snapshotExact(value, keys) {
  try {
    if (!value || typeof value !== 'object' || Array.isArray(value)
      || ![Object.prototype, null].includes(Object.getPrototypeOf(value)))
      return undefined
    const ownKeys = Reflect.ownKeys(value)
    if (ownKeys.some(key => typeof key !== 'string') || ownKeys.length !== keys.length
      || keys.some(key => !ownKeys.includes(key)))
      return undefined
    const copy = Object.create(null)
    for (const key of keys) {
      const descriptor = Object.getOwnPropertyDescriptor(value, key)
      if (!descriptor || !descriptor.enumerable || !('value' in descriptor))
        return undefined
      copy[key] = descriptor.value
    }
    return copy
  }
  catch {
    return undefined
  }
}

function screenedEvent(value) {
  const event = snapshotExact(value, EVENT_KEYS)
  return event && ID_RE.test(event.eventId) && ID_RE.test(event.viewerKey)
    && safeText(event.displayName, 80) && safeText(event.text, 1000) && event.kind === 'text'
    && Number.isSafeInteger(event.publishedAtMs) && event.publishedAtMs >= 0
    ? event
    : undefined
}

function safeText(value, maximum) {
  if (typeof value !== 'string' || !value || value.length > maximum * 2
    || CONTROL.test(value) || BIDI.test(value) || value !== value.normalize('NFC'))
    return false
  let points = 0
  for (let index = 0; index < value.length; index++) {
    const code = value.charCodeAt(index)
    if (code >= 0xd800 && code <= 0xdbff) {
      if (++index >= value.length) return false
      const next = value.charCodeAt(index)
      if (next < 0xdc00 || next > 0xdfff) return false
    }
    else if (code >= 0xdc00 && code <= 0xdfff) return false
    if (++points > maximum) return false
  }
  return true
}

function inputScreenEndpoint(value) {
  const url = new URL(value)
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1'
    || url.username || url.password || url.search || url.hash
    || url.pathname !== '/v1/airi/input-screen')
    throw new TypeError('Input screen endpoint must be the exact loopback HTTP endpoint.')
  const port = Number(url.port || 80)
  if (!Number.isSafeInteger(port) || port < 1 || port > 65535)
    throw new TypeError('Input screen endpoint port is invalid.')
  return url.href
}

function validDecision(value) {
  const decision = snapshotExact(value, DECISION_KEYS)
  if (!decision || decision.version !== 1 || typeof decision.allowed !== 'boolean'
    || typeof decision.category !== 'string' || typeof decision.rule !== 'string')
    return undefined
  if (decision.allowed)
    return decision.category === '' && decision.rule === '' ? decision : undefined
  return LABEL_RE.test(decision.category) && LABEL_RE.test(decision.rule) ? decision : undefined
}

export function createProxyScreen({
  endpoint = 'http://127.0.0.1:11435/v1/airi/input-screen',
  fetchImpl = globalThis.fetch,
  timeoutMs = 1000,
} = {}) {
  const url = inputScreenEndpoint(endpoint)
  if (typeof fetchImpl !== 'function')
    throw new TypeError('Input screen fetch implementation is required.')
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 30_000)
    throw new TypeError('Input screen timeout must be a safe integer from 1 through 30000.')

  return async value => {
    const event = screenedEvent(value)
    if (!event)
      throw new TypeError('Input screen event is malformed.')
    const deliveryText = toAiriEvent(event).data.text
    const controller = new AbortController()
    let timer
    const timeout = new Promise(resolve => {
      timer = setTimeout(() => {
        controller.abort()
        resolve(TIMED_OUT)
      }, timeoutMs)
    })
    try {
      const request = Promise.resolve()
        .then(() => fetchImpl(url, {
          method: 'POST',
          headers: Object.freeze({ 'content-type': 'application/json' }),
          body: JSON.stringify({ version: 1, source: 'youtube_chat', text: deliveryText }),
          signal: controller.signal,
          redirect: 'error',
        }))
        .then(async response => {
          if (response?.ok !== true || typeof response.text !== 'function') return FAILED
          const body = await response.text()
          if (typeof body !== 'string' || body.length > 4096) return FAILED
          try { return JSON.parse(body) } catch { return FAILED }
        })
        .catch(() => FAILED)
      const payload = await Promise.race([request, timeout])
      if (payload === TIMED_OUT || payload === FAILED)
        throw new Error('Input screening is unavailable.')
      const decision = validDecision(payload)
      if (!decision)
        throw new Error('Input screening returned a malformed decision.')
      return decision.allowed
    }
    finally {
      clearTimeout(timer)
      controller.abort()
    }
  }
}
import { toAiriEvent } from './airi-event.mjs'
