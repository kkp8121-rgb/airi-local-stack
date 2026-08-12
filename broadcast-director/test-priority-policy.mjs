import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { ChatIngress } from '../chat-ingress/core.mjs'
import { createBroadcastDirector } from './core.mjs'
import { classifyBroadcastPriority } from './priority-policy.mjs'

const id = 'A'.repeat(43)
const event = (overrides = {}) => Object.freeze({ eventId: `yt:v1:${id}`, viewerKey: `viewer:v1:${id}`, displayName: '시청자', text: '좋은 방송이에요', kind: 'text', publishedAtMs: 0, ...overrides })
const priority = value => classifyBroadcastPriority(event({ text: value })).priority

test('classifies Korean-first cues and preserves documented precedence', () => {
  assert.equal(priority('오늘 방송 주제는 뭐야'), 'question')
  assert.equal(priority('어떻게 생각해'), 'question')
  assert.equal(priority('다음엔 언제 와'), 'question')
  assert.equal(priority('오늘 뭐해'), 'question')
  assert.equal(priority('어디야'), 'question')
  assert.equal(priority('이건 질문인가?'), 'question')
  assert.equal(priority('이건 질문인가？'), 'question')
  assert.equal(priority('https://example.invalid/?x=1'), 'positive')
  assert.equal(priority('(https://example.invalid/?x=1)'), 'positive')
  assert.equal(priority('[https://example.invalid/?x=1]'), 'positive')
  assert.equal(priority('link:https://example.invalid/?x=1'), 'positive')
  assert.equal(priority('https://example.invalid/?x=1 정말이야?'), 'question')
  assert.equal(priority('왜인지 이제 알겠어'), 'positive')
  assert.equal(priority('어떻게 생각해라는 말을 들었어'), 'positive')
  assert.equal(priority('누구인지 이제 알았어'), 'positive')
  assert.equal(priority('오늘은 방송이 즐거웠어'), 'positive')
  assert.equal(priority('그 얘기 더 자세히 고마워 화이팅'), 'topic_expansion')
  assert.equal(priority('고마워, 화이팅'), 'sincere_reaction')
  assert.equal(priority('화이팅!'), 'cheer')
  assert.equal(priority('감사하지 않아'), 'positive')
  assert.equal(priority('응원 안 해'), 'positive')
  assert.equal(priority('응원은 안 할게'), 'positive')
  assert.equal(priority('응원할 생각 없어'), 'positive')
  assert.equal(priority('응원은 못 할 것 같아'), 'positive')
  assert.equal(priority('자세히는 필요 없어'), 'positive')
  assert.equal(priority('자세히 설명할 필요는 없어'), 'positive')
  assert.equal(priority('그 얘기 더 고마워?'), 'question')
  assert.equal(priority('This is great'), 'positive')
  assert.equal(priority('정치와 종교 이야기도 듣고 싶어요'), 'positive')
})

test('returns a frozen, exact, private one-key result deterministically', () => {
  const input = event({ text: '관련해서 더 알려줘' })
  const first = classifyBroadcastPriority(input)
  const second = classifyBroadcastPriority(input)
  assert.deepEqual(first, { priority: 'topic_expansion' })
  assert.deepEqual(second, first)
  assert.equal(Object.isFrozen(first), true)
  assert.deepEqual(Object.keys(first), ['priority'])
  assert.equal(JSON.stringify(first).includes(input.text), false)
})

test('accepts null-prototype exact records and rejects hostile or malformed shapes', () => {
  const nullRecord = Object.assign(Object.create(null), event({ text: '감사합니다' }))
  assert.equal(classifyBroadcastPriority(nullRecord).priority, 'sincere_reaction')
  const accessor = { ...event() }; Object.defineProperty(accessor, 'text', { enumerable: true, get() { return '화이팅' } })
  assert.equal(classifyBroadcastPriority(accessor), null)
  const symbol = { ...event(), [Symbol('extra')]: 1 }
  assert.equal(classifyBroadcastPriority(symbol), null)
  assert.equal(classifyBroadcastPriority({ ...event(), extra: true }), null)
  assert.equal(classifyBroadcastPriority(event({ eventId: 'yt:v1:short' })), null)
  assert.equal(classifyBroadcastPriority(event({ viewerKey: `viewer:v1:${'x'.repeat(42)}` })), null)
  assert.equal(classifyBroadcastPriority(event({ kind: 'donation' })), null)
  assert.equal(classifyBroadcastPriority(event({ publishedAtMs: -1 })), null)
  assert.equal(classifyBroadcastPriority(event({ publishedAtMs: Number.MAX_SAFE_INTEGER + 1 })), null)
  assert.equal(classifyBroadcastPriority(event({ text: 'x\u202ey' })), null)
  assert.equal(classifyBroadcastPriority(event({ displayName: 'x\ud800' })), null)
  assert.equal(classifyBroadcastPriority(event({ text: 'e\u0301' })), null)
  assert.equal(classifyBroadcastPriority(event({ text: '😀'.repeat(1000) })).priority, 'positive')
  assert.equal(classifyBroadcastPriority(event({ text: '😀'.repeat(1001) })), null)
})

test('uses the Proxy data descriptor rather than ordinary property reads', () => {
  let reads = 0
  const target = { ...event({ text: '고마워' }) }
  const proxy = new Proxy(target, {
    get(object, key) {
      if (key === 'text') return '화이팅'
      return Reflect.get(object, key)
    },
    getOwnPropertyDescriptor(object, key) {
      const descriptor = Reflect.getOwnPropertyDescriptor(object, key)
      if (key === 'text') { reads += 1; return descriptor }
      return descriptor
    },
  })
  assert.equal(classifyBroadcastPriority(proxy).priority, 'sincere_reaction')
  assert.equal(reads, 1)
})

test('does not retain valid chat in legacy RegExp statics', async () => {
  const source = await readFile(new URL('./priority-policy.mjs', import.meta.url), 'utf8')
  assert.equal(source.includes('RegExp'), false)
  ;/PRIORITY_SENTINEL/u.test('PRIORITY_SENTINEL')
  const before = { input: RegExp.input, lastMatch: RegExp.lastMatch }
  const secret = classifyBroadcastPriority(event({ text: '고마워 PRIORITY_PRIVATE_CUE' }))
  const afterSecret = { input: RegExp.input, lastMatch: RegExp.lastMatch }
  const neutral = classifyBroadcastPriority(event({ text: '평범한 메시지' }))
  const afterNeutral = { input: RegExp.input, lastMatch: RegExp.lastMatch }
  assert.equal(secret.priority, 'sincere_reaction')
  assert.equal(neutral.priority, 'positive')
  assert.deepEqual(afterSecret, before)
  assert.deepEqual(afterNeutral, before)
})

test('rejects oversized UTF-16 input before scanning without legacy static retention', () => {
  ;/OVERSIZE_SENTINEL/u.test('OVERSIZE_SENTINEL')
  const before = { input: RegExp.input, lastMatch: RegExp.lastMatch }
  const result = classifyBroadcastPriority(event({ text: 'x'.repeat(2001) }))
  const after = { input: RegExp.input, lastMatch: RegExp.lastMatch }
  assert.equal(result, null)
  assert.deepEqual(after, before)
})

test('composes a screened B1 event with the director without classifier persistence', async () => {
  let delivered
  const ingress = new ChatIngress({ enabled: true, identityKey: Buffer.alloc(32, 7), now: () => 0, screen: async value => Object.isFrozen(value) })
  assert.deepEqual(ingress.submit({ version: 1, source: 'youtube', scopeId: 'scope', messageId: 'message', authorId: 'author', authorDisplayName: '시청자', text: '오늘 방송 주제는 뭐야', kind: 'text', publishedAtMs: 0 }), { status: 'queued' })
  assert.deepEqual(await ingress.flush(async value => { delivered = value }), { status: 'flushed' })
  assert.equal(Object.isFrozen(delivered), true)
  const director = createBroadcastDirector({ enabled: true })
  assert.equal(director.start(0).status, 'started')
  const classification = classifyBroadcastPriority(delivered)
  assert.equal(director.submitChat(delivered, classification).status, 'accepted')
  let action = director.nextAction(0)
  assert.equal(action.type, 'block_opening')
  assert.equal(director.complete({ actionId: action.actionId, outcome: 'ok' }, 0).status, 'completed')
  action = director.nextAction(0)
  assert.equal(action.type, 'topic_lease_request')
  assert.equal(director.resolveLease({ actionId: action.actionId, approved: false, leaseToken: undefined }, 0).status, 'resolved')
  action = director.nextAction(0)
  assert.deepEqual({ type: action.type, priority: action.priority, text: action.text }, { type: 'chat_emit', priority: 'question', text: '오늘 방송 주제는 뭐야' })
  assert.deepEqual(classifyBroadcastPriority(delivered), classification)
})
