import assert from 'node:assert/strict'
import test from 'node:test'

import { createLocalChatIngressRuntime } from './runtime.mjs'

const key = 'k'.repeat(32)
const NOW = 1_800_000_000_000
function candidate(messageId, text = 'hello') {
  return {
    version: 1,
    source: 'youtube',
    scopeId: 'stream-a',
    messageId,
    authorId: 'author-a',
    authorDisplayName: 'viewer',
    text,
    kind: 'text',
    publishedAtMs: NOW,
  }
}
function config() { return { enabled: true, identityKey: key, capacity: 4, recentCapacity: 8 } }

test('screened local runtime drops denied chat before AIRI delivery', async () => {
  const delivered = []
  const runtime = createLocalChatIngressRuntime({
    config: config(),
    screen: async () => false,
    deliverEvent: async event => { delivered.push(event) },
    now: () => NOW,
  })
  assert.equal(runtime.submit(candidate('denied')).status, 'queued')
  assert.deepEqual(await runtime.flush(), { status: 'flushed' })
  assert.deepEqual(delivered, [])
  assert.equal(runtime.stats().queued, 0)
})

test('screened local runtime preserves the admitted event id and omits viewer identity', async () => {
  const delivered = []
  const runtime = createLocalChatIngressRuntime({
    config: config(),
    screen: async () => true,
    deliverEvent: async (event, options) => { delivered.push({ event, options }) },
    senderOptions: Object.freeze({ settleDelayMs: 0 }),
    now: () => NOW,
  })
  assert.equal(runtime.submit(candidate('allowed', '오늘 방송 좋아')).status, 'queued')
  assert.deepEqual(await runtime.flush(), { status: 'flushed' })
  assert.equal(delivered.length, 1)
  assert.match(delivered[0].event.metadata.event.id, /^yt:v1:/)
  assert.equal(delivered[0].event.data.text, '[YouTube] 오늘 방송 좋아')
  assert.equal(delivered[0].event.data.text.includes('viewer'), false)
  assert.equal(JSON.stringify(delivered).includes('viewer:v1:'), false)
  assert.deepEqual(delivered[0].options, { settleDelayMs: 0 })
})

test('delivery failure remains retryable and close makes the runtime inert', async () => {
  let attempts = 0
  const runtime = createLocalChatIngressRuntime({
    config: config(),
    screen: async () => true,
    deliverEvent: async () => { if (++attempts === 1) throw new Error('retry') },
    now: () => NOW,
  })
  runtime.submit(candidate('retry'))
  assert.deepEqual(await runtime.flush(), { status: 'delivery_failed' })
  assert.equal(runtime.stats().queued, 1)
  assert.deepEqual(await runtime.flush(), { status: 'flushed' })
  assert.equal(attempts, 2)
  runtime.close()
  assert.equal(runtime.submit(candidate('late')).status, 'disabled')
  assert.deepEqual(await runtime.flush(), { status: 'disabled' })
})

test('default runtime is disabled and performs no network or delivery work', async () => {
  let delivered = 0
  const runtime = createLocalChatIngressRuntime({ deliverEvent: async () => { delivered++ } })
  assert.equal(runtime.submit(candidate('off')).status, 'disabled')
  assert.deepEqual(await runtime.flush(), { status: 'disabled' })
  assert.equal(delivered, 0)
})

test('screen outage retains the head for a later successful retry', async () => {
  let available = false
  let delivered = 0
  const runtime = createLocalChatIngressRuntime({
    config: config(),
    screen: async () => { if (!available) throw new Error('offline'); return true },
    deliverEvent: async () => { delivered++ },
    now: () => NOW,
  })
  runtime.submit(candidate('screen-retry'))
  assert.deepEqual(await runtime.flush(), { status: 'screen_failed' })
  assert.equal(runtime.stats().queued, 1)
  available = true
  assert.deepEqual(await runtime.flush(), { status: 'flushed' })
  assert.equal(delivered, 1)
})

test('maximum admitted display and chat text fit the final AIRI envelope', async () => {
  let delivered
  const runtime = createLocalChatIngressRuntime({
    config: config(),
    screen: async () => true,
    deliverEvent: async event => { delivered = event },
    now: () => NOW,
  })
  const maximum = { ...candidate('maximum', 'x'.repeat(1000)), authorDisplayName: 'n'.repeat(80) }
  assert.equal(runtime.submit(maximum).status, 'queued')
  assert.deepEqual(await runtime.flush(), { status: 'flushed' })
  assert.equal(Array.from(delivered.data.text).length, 1010)
  assert.equal(delivered.data.text.includes('n'.repeat(80)), false)
})
