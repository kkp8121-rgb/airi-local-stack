import { createHmac } from 'node:crypto'

const EXPECTED_KEYS = ['authorDisplayName', 'authorId', 'kind', 'messageId', 'publishedAtMs', 'scopeId', 'source', 'text', 'version']
const BIDI = /[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/u
const DISALLOWED_CONTROL = /[\u0000-\u0008\u000e-\u001f\u007f-\u009f]/u
const RAW_ID_DISALLOWED = /[\u0000-\u001f\u007f-\u009f\s]/u
const ID_RE = /^(?:yt:v1:|viewer:v1:)[A-Za-z0-9_-]{43}$/
const MAX_RAW_ID = 256

function isWellFormed(value) {
  for (let index = 0; index < value.length; index++) {
    const code = value.charCodeAt(index)
    if (code >= 0xd800 && code <= 0xdbff) {
      if (index + 1 >= value.length) return false
      const next = value.charCodeAt(++index)
      if (next < 0xdc00 || next > 0xdfff) return false
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      return false
    }
  }
  return true
}

function codePoints(value) { return Array.from(value).length }
function normalize(value, max) {
  if (typeof value !== 'string' || !isWellFormed(value) || DISALLOWED_CONTROL.test(value) || BIDI.test(value)) return null
  const normalized = value.normalize('NFC').trim().replace(/\s+/gu, ' ')
  if (normalized.length === 0 || codePoints(normalized) > max) return null
  return normalized
}
function rawId(value) {
  if (typeof value !== 'string' || !isWellFormed(value) || value.length === 0 || value.length > MAX_RAW_ID) return null
  return RAW_ID_DISALLOWED.test(value) || BIDI.test(value) ? null : value
}
function bytes(key) {
  if (Buffer.isBuffer(key) || key instanceof Uint8Array) return Buffer.from(key)
  if (typeof key === 'string') return Buffer.from(key, 'utf8')
  return null
}
function id(key, prefix, payload) {
  return `${prefix}${createHmac('sha256', key).update(payload).digest('base64url')}`
}
function candidateToIngress(candidate, identityKey, now) {
  if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate) || ![Object.prototype, null].includes(Object.getPrototypeOf(candidate))) return null
  const ownKeys = Reflect.ownKeys(candidate)
  if (ownKeys.some(key => typeof key !== 'string')) return null
  const keys = ownKeys.sort()
  if (keys.length !== EXPECTED_KEYS.length || keys.some((key, index) => key !== EXPECTED_KEYS[index])) return null
  if (candidate.version !== 1 || candidate.source !== 'youtube' || candidate.kind !== 'text') return null
  if (!Number.isSafeInteger(candidate.publishedAtMs) || candidate.publishedAtMs < now - 120000 || candidate.publishedAtMs > now + 30000) return null
  const scopeId = rawId(candidate.scopeId)
  const messageId = rawId(candidate.messageId)
  const authorId = rawId(candidate.authorId)
  const displayName = normalize(candidate.authorDisplayName, 80)
  const text = normalize(candidate.text, 1000)
  if (!scopeId || !messageId || !authorId || !displayName || !text) return null
  return Object.freeze({
    eventId: id(identityKey, 'yt:v1:', `event\0youtube\0${scopeId}\0${messageId}`),
    viewerKey: id(identityKey, 'viewer:v1:', `viewer\0youtube\0${authorId}`),
    displayName,
    text,
    kind: 'text',
    publishedAtMs: candidate.publishedAtMs,
  })
}
function callbackEvent(event) { return Object.freeze({ ...event }) }

export class ChatIngress {
  #enabled; #key; #screen; #capacity; #recentCapacity; #now; #queue = []; #recent = new Map(); #flushing = null; #closed = false

  constructor({ enabled = false, identityKey, screen, capacity = 64, recentCapacity = 4096, now = () => Date.now() } = {}) {
    this.#enabled = enabled === true
    this.#capacity = capacity
    this.#recentCapacity = recentCapacity
    this.#now = now
    if (!Number.isSafeInteger(capacity) || capacity < 1 || !Number.isSafeInteger(recentCapacity) || recentCapacity < 1) throw new TypeError('capacities must be positive safe integers')
    if (this.#enabled) {
      this.#key = bytes(identityKey)
      if (!this.#key || this.#key.length < 32) throw new TypeError('enabled chat ingress requires an identityKey of at least 32 bytes')
      if (typeof screen !== 'function') throw new TypeError('enabled chat ingress requires a screen callback')
      this.#screen = screen
    }
  }
  submit(candidate) {
    if (!this.#enabled || this.#closed) return { status: 'disabled' }
    const event = candidateToIngress(candidate, this.#key, this.#now())
    if (!event) return { status: 'rejected' }
    if (this.#queue.some(item => item.event.eventId === event.eventId)) return { status: 'duplicate' }
    if (this.#recent.has(event.eventId)) {
      this.#recent.delete(event.eventId)
      this.#recent.set(event.eventId, true)
      return { status: 'duplicate' }
    }
    if (this.#queue.length >= this.#capacity) return { status: 'backpressure' }
    this.#queue.push({ event, allowed: undefined })
    return { status: 'queued' }
  }
  async flush(deliver) {
    if (typeof deliver !== 'function') throw new TypeError('deliver callback is required')
    if (!this.#enabled || this.#closed) return { status: 'disabled' }
    if (this.#flushing) return this.#flushing
    this.#flushing = this.#flush(deliver).finally(() => { this.#flushing = null })
    return this.#flushing
  }
  async #flush(deliver) {
    while (this.#queue.length && !this.#closed) {
      const head = this.#queue[0]
      if (head.allowed === undefined) {
        try { head.allowed = (await this.#screen(callbackEvent(head.event))) === true } catch { return this.#closed ? { status: 'disabled' } : { status: 'screen_failed' } }
        if (this.#closed) return { status: 'disabled' }
      }
      if (!head.allowed) {
        this.#consume(head.event.eventId)
        continue
      }
      if (this.#closed) return { status: 'disabled' }
      try { await deliver(callbackEvent(head.event)) } catch { return this.#closed ? { status: 'disabled' } : { status: 'delivery_failed' } }
      if (this.#closed) return { status: 'disabled' }
      this.#consume(head.event.eventId)
    }
    return this.#closed ? { status: 'disabled' } : { status: 'flushed' }
  }
  #consume(eventId) {
    if (this.#closed) return
    this.#queue.shift()
    this.#recent.delete(eventId)
    this.#recent.set(eventId, true)
    while (this.#recent.size > this.#recentCapacity) this.#recent.delete(this.#recent.keys().next().value)
  }
  stats() { return { enabled: this.#enabled && !this.#closed, queued: this.#queue.length, recent: this.#recent.size, capacity: this.#capacity, recentCapacity: this.#recentCapacity, flushing: this.#flushing !== null } }
  close() { this.#closed = true; this.#enabled = false; this.#queue = []; this.#recent.clear(); if (this.#key) this.#key.fill(0); this.#key = undefined; this.#screen = undefined }
}

export function createChatIngress(options) { return new ChatIngress(options) }
export function isChatIngressId(value) { return typeof value === 'string' && ID_RE.test(value) }
