import assert from 'node:assert/strict'
import test from 'node:test'
import { createChatIngress, isChatIngressId } from './core.mjs'
import { toAiriEvent } from './airi-event.mjs'

const NOW = 1_700_000_000_000
const key = Buffer.alloc(32, 7)
const screenAllow = async () => true
function candidate(overrides = {}) {
  return { version: 1, source: 'youtube', scopeId: 'scope', messageId: 'message', authorId: 'author', authorDisplayName: '  A\u0301   viewer ', text: ' hello   world ', kind: 'text', publishedAtMs: NOW, ...overrides }
}
function core(options = {}) { return createChatIngress({ enabled: true, identityKey: key, screen: screenAllow, now: () => NOW, ...options }) }
async function deliveredEvent(ingress) {
  const events = []
  await ingress.flush(async event => events.push(event))
  return events[0]
}

test('disabled is exact default and needs neither key nor screener', () => {
  const ingress = createChatIngress()
  assert.deepEqual(ingress.submit(candidate()), { status: 'disabled' })
  assert.deepEqual(ingress.stats(), { enabled: false, queued: 0, recent: 0, capacity: 64, recentCapacity: 4096, flushing: false })
})

test('enabled requires a sufficient identity key and any awaitable screen callback', () => {
  assert.throws(() => createChatIngress({ enabled: true, identityKey: 'short', screen: screenAllow }), /identityKey/)
  assert.throws(() => createChatIngress({ enabled: true, identityKey: key }), /screen/)
  assert.doesNotThrow(() => createChatIngress({ enabled: true, identityKey: key, screen: () => true }))
})

test('strict candidate validation normalizes only safe text and display input', () => {
  const ingress = core()
  assert.deepEqual(ingress.submit(candidate({ authorDisplayName: '\t Alice \r\n', text: '\f hello \v world \t' })), { status: 'queued' })
  for (const bad of [
    candidate({ extra: 1 }), Object.assign(candidate(), { [Symbol('extra')]: true }), candidate({ version: 2 }), candidate({ source: 'twitch' }), candidate({ kind: 'member' }),
    candidate({ publishedAtMs: NOW - 120001 }), candidate({ publishedAtMs: NOW + 30001 }), candidate({ publishedAtMs: 1.5 }),
    candidate({ text: ' \t ' }), candidate({ text: `bad${String.fromCharCode(0)}text` }), candidate({ text: `bad${String.fromCharCode(0x0085)}text` }),
    candidate({ text: `bad${String.fromCharCode(0x061c)}text` }), candidate({ text: `bad${String.fromCharCode(0x200e)}text` }), candidate({ text: `bad${String.fromCharCode(0x200f)}text` }), candidate({ text: `bad${String.fromCharCode(0x202e)}text` }), candidate({ text: `bad${String.fromCharCode(0x2066)}text` }),
    candidate({ text: `${String.fromCharCode(0xd800)}bad` }), candidate({ text: 'x'.repeat(1001) }), candidate({ authorDisplayName: 'x'.repeat(81) }), candidate({ messageId: 'x'.repeat(257) }),
  ]) assert.deepEqual(ingress.submit(bad), { status: 'rejected' })
})

test('code-point bounds support astral characters and raw IDs reject unsafe Unicode', () => {
  const astral = String.fromCodePoint(0x1f600)
  const ingress = core()
  assert.equal(ingress.submit(candidate({ authorDisplayName: astral.repeat(80), text: astral.repeat(1000) })).status, 'queued')
  assert.equal(ingress.submit(candidate({ messageId: 'too-display', authorDisplayName: astral.repeat(81) })).status, 'rejected')
  assert.equal(ingress.submit(candidate({ messageId: 'too-text', text: astral.repeat(1001) })).status, 'rejected')
  for (const value of ['raw id', `raw${String.fromCharCode(1)}`, `raw${String.fromCharCode(0x200f)}`, `raw${String.fromCharCode(0xd800)}`]) {
    assert.equal(ingress.submit(candidate({ messageId: value })).status, 'rejected')
  }
})

test('pseudonyms are domain separated, exact-length, and raw IDs never leak', async () => {
  const ingress = core()
  ingress.submit(candidate({ scopeId: 'scope-secret', messageId: 'message-secret', authorId: 'author-secret' }))
  const event = await deliveredEvent(ingress)
  assert.match(event.eventId, /^yt:v1:[A-Za-z0-9_-]{43}$/)
  assert.match(event.viewerKey, /^viewer:v1:[A-Za-z0-9_-]{43}$/)
  assert.ok(isChatIngressId(event.eventId) && isChatIngressId(event.viewerKey))
  assert.ok(!isChatIngressId('yt:v1:abc'))
  assert.notEqual(event.eventId, event.viewerKey)
  const serialized = JSON.stringify([event, ingress.stats()])
  for (const raw of ['scope-secret', 'message-secret', 'author-secret']) assert.ok(!serialized.includes(raw))
  assert.equal(event.displayName.codePointAt(0), 0x00c1)
  assert.equal(event.text, 'hello world')
})

test('duplicate checks precede capacity, remain retryable, and touch the recent LRU', async () => {
  const ingress = core({ capacity: 1, recentCapacity: 2 })
  assert.equal(ingress.submit(candidate({ messageId: 'a' })).status, 'queued')
  assert.equal(ingress.submit(candidate({ messageId: 'a' })).status, 'duplicate')
  assert.equal(ingress.submit(candidate({ messageId: 'two' })).status, 'backpressure')
  await ingress.flush(async () => {})
  assert.equal(ingress.submit(candidate({ messageId: 'two' })).status, 'queued')
  await ingress.flush(async () => {})
  assert.equal(ingress.submit(candidate({ messageId: 'a' })).status, 'duplicate')
  assert.equal(ingress.submit(candidate({ messageId: 'c' })).status, 'queued')
  await ingress.flush(async () => {})
  assert.equal(ingress.submit(candidate({ messageId: 'two' })).status, 'queued')
  assert.equal(ingress.submit(candidate({ messageId: 'a' })).status, 'duplicate')
})

test('FIFO has a single-flight screen and delivery path', async () => {
  let active = 0; let maximum = 0; const order = []; let release
  const wait = new Promise(resolve => { release = resolve })
  const ingress = core({ screen: async event => { active++; maximum = Math.max(maximum, active); order.push(`screen:${event.text}`); await wait; active--; return true } })
  ingress.submit(candidate({ text: 'first' })); ingress.submit(candidate({ messageId: 'two', text: 'second' }))
  const first = ingress.flush(async event => { active++; maximum = Math.max(maximum, active); order.push(`deliver:${event.text}`); active-- })
  const second = ingress.flush(async () => { throw new Error('must share flight') })
  release(); await Promise.all([first, second])
  assert.equal(maximum, 1)
  assert.deepEqual(order, ['screen:first', 'deliver:first', 'screen:second', 'deliver:second'])
})

test('screen denial consumes, failures retain, and successful screen decisions cache', async () => {
  let screens = 0; let failScreen = true; let failDelivery = true
  const ingress = core({ screen: async event => { screens++; if (event.text === 'fail-screen' && failScreen) throw new Error('no'); return event.text !== 'deny' } })
  ingress.submit(candidate({ text: 'deny' })); ingress.submit(candidate({ messageId: 'two', text: 'fail-screen' })); ingress.submit(candidate({ messageId: 'three', text: 'fail-delivery' }))
  assert.deepEqual(await ingress.flush(async () => {}), { status: 'screen_failed' })
  assert.equal(ingress.stats().queued, 2)
  failScreen = false
  assert.deepEqual(await ingress.flush(async event => { if (event.text === 'fail-delivery' && failDelivery) throw new Error('no') }), { status: 'delivery_failed' })
  assert.equal(screens, 4)
  failDelivery = false
  await ingress.flush(async () => {})
  assert.equal(screens, 4)
  assert.equal(ingress.stats().queued, 0)
})

test('callback events are frozen copies and hostile mutation cannot alter retries', async () => {
  let failScreen = true; let screens = 0; const delivered = []
  const ingress = core({ screen: event => {
    screens++
    assert.throws(() => { event.text = 'poison' }, TypeError)
    if (failScreen) { failScreen = false; throw new Error('fail closed') }
    return true
  } })
  ingress.submit(candidate())
  assert.deepEqual(await ingress.flush(async () => {}), { status: 'screen_failed' })
  assert.deepEqual(await ingress.flush(async event => { delivered.push(event.text) }), { status: 'flushed' })
  assert.deepEqual(delivered, ['hello world'])
  assert.equal(screens, 2)

  let failDelivery = true
  const retry = core()
  retry.submit(candidate())
  assert.deepEqual(await retry.flush(async event => {
    assert.throws(() => { event.text = 'poison' }, TypeError)
    if (failDelivery) { failDelivery = false; throw new Error('retry') }
  }), { status: 'delivery_failed' })
  const retryDelivered = []
  await retry.flush(async event => retryDelivered.push(event.text))
  assert.deepEqual(retryDelivered, ['hello world'])
})

test('close races prevent post-close delivery and consumption', async () => {
  let releaseScreen; const screenWait = new Promise(resolve => { releaseScreen = resolve }); let delivered = 0
  const screenRace = core({ screen: async () => { await screenWait; return true } })
  screenRace.submit(candidate())
  const screenFlush = screenRace.flush(async () => { delivered++ })
  screenRace.close(); releaseScreen()
  assert.deepEqual(await screenFlush, { status: 'disabled' })
  assert.equal(delivered, 0)
  assert.equal(screenRace.stats().recent, 0)

  let releaseDelivery; const deliveryWait = new Promise(resolve => { releaseDelivery = resolve }); let started
  const deliveryStarted = new Promise(resolve => { started = resolve }); let deliveryCalls = 0
  const deliveryRace = core()
  deliveryRace.submit(candidate({ messageId: 'one' })); deliveryRace.submit(candidate({ messageId: 'two' }))
  const deliveryFlush = deliveryRace.flush(async () => { deliveryCalls++; started(); await deliveryWait })
  await deliveryStarted
  deliveryRace.close(); releaseDelivery()
  assert.deepEqual(await deliveryFlush, { status: 'disabled' })
  assert.equal(deliveryCalls, 1)
  assert.equal(deliveryRace.stats().recent, 0)
})

test('close clears state, disables admission, and stats are content-free', () => {
  const ingress = core(); ingress.submit(candidate()); ingress.close()
  assert.deepEqual(ingress.submit(candidate()), { status: 'disabled' })
  assert.deepEqual(ingress.stats(), { enabled: false, queued: 0, recent: 0, capacity: 64, recentCapacity: 4096, flushing: false })
  assert.ok(!JSON.stringify(ingress.stats()).includes('hello'))
})

test('AIRI mapper emits the established envelope and rejects malformed IDs', async () => {
  const ingress = core()
  ingress.submit(candidate({ scopeId: 'scope-secret', messageId: 'message-secret', authorId: 'author-secret' }))
  const event = await deliveredEvent(ingress)
  const output = toAiriEvent(event)
  assert.deepEqual(output, { type: 'input:text', data: { text: '[YouTube] hello world' }, route: { delivery: { required: true } }, metadata: { event: { id: event.eventId } } })
  const serialized = JSON.stringify(output)
  for (const forbidden of ['viewerKey', 'youtube', 'source', 'textRaw', 'contextUpdates', 'overrides', 'metadata.source', 'scope-secret', 'message-secret', 'author-secret']) assert.ok(!serialized.includes(forbidden))
  for (const eventId of ['raw-message-id', 'yt:v1:abc', `viewer:v1:${'a'.repeat(43)}`, `yt:v1:${'a'.repeat(42)}`]) {
    assert.throws(() => toAiriEvent({ ...event, eventId }), /eventId/)
  }
})
