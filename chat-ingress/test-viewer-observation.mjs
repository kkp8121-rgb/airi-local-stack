import assert from 'node:assert/strict'
import test from 'node:test'
import { toViewerObservation } from './viewer-observation.mjs'

const eventId = `yt:v1:${'a'.repeat(43)}`
const viewerKey = `viewer:v1:${'b'.repeat(43)}`
const broadcastKey = `broadcast:v1:${'c'.repeat(43)}`
function ingress(overrides = {}) {
  return Object.freeze({ eventId, viewerKey, displayName: ' A\u0301  viewer ', text: 'private message', kind: 'text', publishedAtMs: 1_700_000_000_000, ...overrides })
}
function options(overrides = {}) { return Object.freeze({ broadcastKey, ...overrides }) }

test('maps a screened ingress event to an exact content-free observation', () => {
  const observation = toViewerObservation(ingress(), options())
  assert.deepEqual(observation, { eventId, viewerKey, displayName: 'Á viewer', kind: 'text', publishedAtMs: 1_700_000_000_000, broadcastKey })
  assert.ok(Object.isFrozen(observation))
  assert.equal(JSON.stringify(observation).includes('private message'), false)
  assert.equal(JSON.stringify(observation).includes('[YouTube]'), false)
})

test('does not expose a mutable result or retain caller object shape', () => {
  const observation = toViewerObservation(ingress(), options())
  assert.throws(() => { observation.broadcastKey = 'changed' }, TypeError)
  assert.equal(observation.broadcastKey, broadcastKey)
})

test('rejects hostile records, unsafe identifiers, text, and broadcast fields', () => {
  const accessor = { eventId, viewerKey, displayName: 'viewer', kind: 'text', publishedAtMs: 1, get text() { throw new Error('must not read') } }
  const hostile = [
    { ...ingress(), extra: true },
    Object.assign({}, ingress(), { [Symbol('extra')]: true }),
    Object.create({ eventId }),
    accessor,
    { ...ingress(), eventId: 'raw-youtube-id' },
    { ...ingress(), viewerKey: `viewer:v1:${'x'.repeat(42)}` },
    { ...ingress(), displayName: `bad\u202ename` },
    { ...ingress(), text: `bad${String.fromCharCode(0xd800)}` },
    { ...ingress(), publishedAtMs: -1 },
  ]
  for (const value of hostile) assert.throws(() => toViewerObservation(value, options()), TypeError)
  for (const value of [
    { broadcastKey, extra: true },
    { broadcastKey: 'raw-youtube-broadcast-id' },
    { broadcastKey: `broadcast:v1:${'x'.repeat(42)}` },
    Object.assign({}, options(), { [Symbol('extra')]: true }),
  ]) assert.throws(() => toViewerObservation(ingress(), value), TypeError)
})

test('snapshots admitted data properties against proxy time-of-check changes', () => {
  const source = { ...ingress() }
  let eventReads = 0
  const hostile = new Proxy(source, {
    getOwnPropertyDescriptor(target, key) {
      const descriptor = Reflect.getOwnPropertyDescriptor(target, key)
      if (key === 'eventId' && descriptor) {
        eventReads += 1
        return { ...descriptor, value: eventReads === 1 ? eventId : 'raw-youtube-id' }
      }
      return descriptor
    },
    get(target, key, receiver) {
      if (key === 'eventId') return 'raw-youtube-id'
      return Reflect.get(target, key, receiver)
    },
  })
  const observation = toViewerObservation(hostile, options())
  assert.equal(observation.eventId, eventId)
  assert.equal(JSON.stringify(observation).includes('raw-youtube-id'), false)
  assert.equal(eventReads, 1)
})
