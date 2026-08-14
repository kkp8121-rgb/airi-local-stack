import assert from 'node:assert/strict'
import test from 'node:test'
import { BROADCAST_SCHEDULE, createBroadcastDirector } from './core.mjs'

let n = 0; const priorities = new WeakMap()
const id = () => `yt:v1:${String(n++).padStart(43, 'a')}`
const chat = (priority, text) => { const event = { eventId: id(), viewerKey: `viewer:v1:${String(n).padStart(43, 'b')}`, displayName: 'Viewer', text, kind: 'text', publishedAtMs: 0 }; priorities.set(event, priority); return event }
const send = (d, event, priority = priorities.get(event) || 'positive') => d.submitChat(event, { priority })
const donation = (message) => ({ eventId: id(), displayName: 'Nora', message, publishedAtMs: 0 })
const make = (o = {}) => createBroadcastDirector({ enabled: true, ...o })
const done = (d, a, at) => a.type === 'topic_lease_request' ? d.resolveLease({ actionId: a.actionId, approved: false, leaseToken: '' }, at) : d.complete({ actionId: a.actionId, outcome: 'ok' }, at)
const boot = (d) => { d.start(0); for (;;) { const a = d.nextAction(0); if (a.status === 'idle') return; if (a.type.endsWith('lease_request')) d.resolveLease({ actionId: a.actionId, approved: false, leaseToken: '' }, 0); else done(d, a, 0) } }

test('default-off is inert', () => { const d = createBroadcastDirector(); assert.equal(d.start(0).status, 'disabled'); assert.equal(d.stats().queued, 0) })
test('screens established pseudonymous event ids and hostile shapes', () => {
    const d = make(); boot(d)
    assert.equal(send(d, { ...chat('question', 'ok'), eventId: 'yt:v1:short' }).status, 'rejected')
    const accessor = { eventId: id(), displayName: 'x', kind: 'question', publishedAtMs: 0 }; Object.defineProperty(accessor, 'text', { enumerable: true, get: () => 'x' })
    assert.equal(send(d, accessor).status, 'rejected')
    assert.equal(send(d, chat('question', 'bad\u202e')).status, 'rejected')
    assert.equal(send(d, new Proxy({}, { getPrototypeOf: () => { throw Error('hostile') } })).status, 'rejected')
    const frozen = Object.freeze(chat('positive', 'frozen')); assert.equal(send(d, frozen).status, 'accepted')
    const nullProto = Object.assign(Object.create(null), chat('positive', 'null')); assert.equal(send(d, nullProto, 'positive').status, 'accepted')
    assert.equal(send(d, { ...chat('positive', 'future'), publishedAtMs: 30_001 }).status, 'rejected')
})
test('priority FIFO, capacity, LRU dedupe and frozen replay', () => {
    const d = make({ capacity: 8 }); boot(d); const q1 = chat('question', 'q1')
    for (const e of [chat('cheer', 'c'), q1, chat('question', 'q2'), chat('topic_expansion', 't')]) assert.equal(send(d, e).status, 'accepted')
    assert.equal(send(d, q1).status, 'duplicate')
    for (const text of ['q1', 'q2', 't', 'c']) { const a = d.nextAction(0); assert.equal(a.text, text); assert.strictEqual(d.nextAction(0), a); done(d, a, 0) }
    for (let i = 0; i < 8; i++) send(d, chat('positive', `x${i}`)); assert.equal(send(d, chat('positive', 'over')).status, 'backpressure')
})
test('recent dedupe has independent true-LRU capacity', () => {
    const d = make({ capacity: 32, recentCapacity: 8 }); boot(d); const first = chat('positive', 'first'); send(d, first)
    for (let i = 0; i < 7; i++) send(d, chat('positive', `x${i}`))
    assert.equal(send(d, first).status, 'duplicate') // refresh first
    for (let i = 0; i < 8; i++) send(d, chat('positive', `y${i}`))
    assert.equal(send(d, first).status, 'accepted') // refreshed first is eventually evicted only after eight newer ids
})
test('donation queues an immediate validated name-callout then deferred read and separate reaction', () => {
    const d = make(); boot(d); d.submitDonation(donation('read later')); let a = d.nextAction(0)
    a = d.nextAction(0); assert.equal(a.type, 'donation_name_callout_request'); assert.equal(a.displayName, 'Nora'); assert.equal('message' in a, false); assert.equal('amount' in a, false); assert.equal('viewerKey' in a, false); done(d, a, 0); d.requestSeam(0); a = d.nextAction(0); assert.equal(a.type, 'donation_read_request'); assert.equal(a.message, 'read later'); done(d, a, 0); a = d.nextAction(0); assert.equal(a.type, 'donation_reaction_request'); done(d, a, 0)

    for (const displayName of [undefined, '', 'N'.repeat(81), 'Nora\u0000', 'Nora\u202e', '\ud800']) {
        const event = donation('not queued')
        if (displayName === undefined) delete event.displayName
        else event.displayName = displayName
        assert.equal(d.submitDonation(event).status, 'rejected')
        assert.equal(d.nextAction(0).status, 'idle')
    }
})
test('question cycle is 3:2 and waits exactly 12 seconds', () => {
    const d = make(); boot(d); d.advance(30_000)
    const patterns = []; for (let i = 0; i < 5; i++) { const ask = d.nextAction(30_000 + i * 12_000); patterns.push(ask.pattern); done(d, ask, 30_000 + i * 12_000); assert.equal(d.nextAction(41_999 + i * 12_000).status, 'idle'); const answer = d.nextAction(42_000 + i * 12_000); assert.equal(answer.type, 'self_answer'); done(d, answer, 42_000 + i * 12_000) }
    assert.deepEqual(patterns, ['closed', 'closed', 'closed', 'open', 'open'])
})
test('a chat admitted during a delayed question wait suppresses that self-answer', () => {
    const d = make(); boot(d); d.advance(30_000); const ask = d.nextAction(30_000); assert.equal(ask.type, 'question_ask'); done(d, ask, 30_000)
    send(d, chat('question', 'during wait')); const emitted = d.nextAction(42_000); assert.equal(emitted.type, 'chat_emit'); done(d, emitted, 42_000)
    assert.notEqual(d.nextAction(42_000).type, 'self_answer')
})
test('a full queue retries the due self-answer exactly once after capacity frees', () => {
    const d = make({ capacity: 8 }); boot(d); d.advance(30_000); const ask = d.nextAction(30_000); done(d, ask, 30_000)
    for (let i = 0; i < 4; i++) assert.equal(d.submitDonation(donation(`fill${i}`)).status, 'accepted')
    d.advance(42_000); assert.equal(d.stats().regularQueued, 0)
    let self = null; for (let i = 0; i < 8; i++) { const a = d.nextAction(42_000); if (a.type === 'self_answer') { self = a; break } done(d, a, 42_000) }
    assert.ok(self); done(d, self, 42_000); assert.equal(d.nextAction(42_000).type, 'question_ask')
})
test('silence lease is paced, opaque, ABA safe, pause freezes, close clears', () => {
    const d = make({ silenceThreshold: 30_000 }); d.start(0); d.advance(30_000); d.noteSilence(30_000); assert.equal(d.noteSilence(30_000).status, 'not_due'); let a; do { a = d.nextAction(30_000); done(d, a, 30_000) } while (a.type !== 'narration_what_how_why'); d.noteSilence(60_000); do { a = d.nextAction(60_000); if (a.type !== 'topic_lease_request') done(d, a, 60_000) } while (a.type !== 'topic_lease_request'); d.resolveLease({ actionId: a.actionId, approved: true, leaseToken: 'opaque' }, 60_000); assert.equal(d.complete({ actionId: a.actionId, outcome: 'ok' }, 60_000).status, 'rejected'); do { a = d.nextAction(60_000); if (a.type !== 'topic_speech_request') done(d, a, 60_000) } while (a.type !== 'topic_speech_request'); done(d, a, 60_000); do { a = d.nextAction(60_000); if (a.type !== 'topic_lease_complete') done(d, a, 60_000) } while (a.type !== 'topic_lease_complete'); d.pause(60_000); assert.equal(send(d, chat('question', 'no')).status, 'paused'); d.resume(90_000); assert.equal(d.stats().elapsedMs, 60_000); d.close(); assert.equal(d.stats().queued, 0)
})
test('silence backpressure does not consume a ladder step', () => {
    const d = make({ capacity: 8, silenceThreshold: 30_000 }); boot(d); for (let i = 0; i < 8; i++) send(d, chat('positive', `fill${i}`)); d.advance(30_000); assert.equal(d.noteSilence(30_000).status, 'backpressure')
    for (;;) { const a = d.nextAction(30_000); if (a.status === 'idle') break; done(d, a, 30_000) }
    assert.equal(d.noteSilence(30_000).status, 'scheduled'); let a; do { a = d.nextAction(30_000); if (a.type !== 'narration_what_how_why') done(d, a, 30_000) } while (a.type !== 'narration_what_how_why'); done(d, a, 30_000)
    d.noteSilence(60_000); do { a = d.nextAction(60_000); if (a.type !== 'topic_lease_request') done(d, a, 60_000) } while (a.type !== 'topic_lease_request'); d.resolveLease({ actionId: a.actionId, approved: false, leaseToken: '' }, 60_000)
    d.noteSilence(90_000); do { a = d.nextAction(90_000); if (a.type !== 'binary_question') done(d, a, 90_000) } while (a.type !== 'binary_question'); assert.equal(a.type, 'binary_question')
})
test('broadcast complete outcomes are terminal and clear private state', () => {
    for (const outcome of ['ok', 'failed']) { const d = make(); d.start(0); d.advance(6_900_000); let a; for (;;) { a = d.nextAction(6_900_000); if (a.type === 'topic_lease_request') d.resolveLease({ actionId: a.actionId, approved: false, leaseToken: '' }, 6_900_000); else if (a.type === 'broadcast_complete') break; else done(d, a, 6_900_000) }; assert.equal(d.complete({ actionId: a.actionId, outcome }, 6_900_000).status, outcome === 'ok' ? 'completed' : 'failed'); assert.equal(d.stats().queued, 0); assert.equal(d.stats().dedupeSize, 0); assert.equal(d.close().status, 'closed') }
})
test('a near-full opening milestone is atomic and retries without duplicates', () => {
    const d = make({ capacity: 8 }); boot(d); d.advance(900_000); let prior = d.nextAction(900_000); done(d, prior, 900_000); for (let i = 0; i < 7; i++) send(d, chat('positive', `hold${i}`)); d.advance(1_200_000); assert.equal(d.stats().mandatoryQueued, 0)
    const chatAction = d.nextAction(1_200_000); assert.equal(chatAction.type, 'chat_emit'); done(d, chatAction, 1_200_000)
    const opening = d.nextAction(1_200_000); assert.equal(opening.type, 'block_opening'); assert.equal(opening.block, 2); done(d, opening, 1_200_000); const lease = d.nextAction(1_200_000); assert.equal(lease.type, 'topic_lease_request'); assert.equal(lease.block, 2)
})
test('exact frozen B1 event and separate frozen classification do not leak viewerKey', () => {
    const d = make(); boot(d); const event = Object.freeze(chat('question', 'screened')); const classification = Object.freeze({ priority: 'question' })
    assert.equal(d.submitChat(event, classification).status, 'accepted'); const action = d.nextAction(0); assert.equal(action.type, 'chat_emit'); assert.equal('viewerKey' in action, false); assert.equal(JSON.stringify(d.stats()).includes(event.viewerKey), false); assert.equal(JSON.stringify(d.stats()).includes('screened'), false)
    assert.equal(d.submitChat(event).status, 'rejected'); assert.equal(d.submitChat({ eventId: event.eventId, displayName: 'x', text: 'x', kind: 'text', publishedAtMs: 0 }, classification).status, 'rejected'); assert.equal(d.submitChat(chat('positive', 'x'), { priority: 'invalid' }).status, 'rejected')
    const nullClass = Object.assign(Object.create(null), { priority: 'positive' }); assert.equal(d.submitChat(chat('positive', 'null class'), nullClass).status, 'accepted')
})
test('lease request requires resolution and terminal teardown returns unique release tokens', () => {
    const d = make(); d.start(0); const opening = d.nextAction(0); done(d, opening, 0); const request = d.nextAction(0); const before = d.stats().elapsedMs
    assert.equal(d.complete({ actionId: request.actionId, outcome: 'ok' }, 9_000).reason, 'requires_lease_resolution'); assert.equal(d.stats().elapsedMs, before); assert.strictEqual(d.nextAction(0), request)
    assert.equal(d.resolveLease({ actionId: request.actionId, approved: true, leaseToken: 'bad token' }, 9_000).status, 'rejected'); assert.equal(d.stats().elapsedMs, before)
    d.resolveLease({ actionId: request.actionId, approved: true, leaseToken: 'opaque-token' }, 0); const speech = d.nextAction(0); assert.equal(speech.type, 'topic_speech_request'); const killed = d.kill(); assert.deepEqual(killed.leaseReleases, [{ leaseToken: 'opaque-token', purpose: 'opening', block: 1, delivered: false }]); assert.equal(Object.isFrozen(killed.leaseReleases), true); assert.equal(d.stats().queued, 0)
})
test('B1 text bounds count code points', () => {
    const d = make(); boot(d); assert.equal(send(d, chat('positive', '😀'.repeat(1000))).status, 'accepted'); assert.equal(send(d, chat('positive', '😀'.repeat(1001))).status, 'rejected')
})
test('donation seam is one-shot', () => {
    const d = make(); boot(d); d.submitDonation(donation('one')); let a = d.nextAction(0); done(d, a, 0); d.requestSeam(0); a = d.nextAction(0); assert.equal(a.type, 'donation_read_request'); done(d, a, 0); a = d.nextAction(0); done(d, a, 0); d.submitDonation(donation('two')); a = d.nextAction(0); assert.equal(a.type, 'donation_name_callout_request'); done(d, a, 0); assert.notEqual(d.nextAction(0).type, 'donation_read_request'); d.requestSeam(0); assert.equal(d.nextAction(0).type, 'donation_read_request')
})
test('compressed six block rehearsal retains final outputs', () => {
    const d = make(); d.start(0); const types = []; for (let b = 0; b < 6; b++) { const at = b * 1_200_000 + 900_000; d.advance(at); for (;;) { const a = d.nextAction(at); if (a.status === 'idle' || a.status === 'completed') break; types.push(a.type); if (a.type.endsWith('lease_request')) d.resolveLease({ actionId: a.actionId, approved: false, leaseToken: '' }, at); else done(d, a, at) } }
    assert.equal(types.filter((x) => x === 'block_opening').length, 6); assert.equal(types.filter((x) => x === 'closing').length, 6); const final = types.slice(-5); assert.deepEqual(final, ['closing', 'final_qa', 'thanks', 'next_broadcast_preview', 'broadcast_complete']); for (let b = 0; b < 6; b++) assert.ok(types.indexOf('block_opening', b) < types.lastIndexOf('closing')); assert.equal(BROADCAST_SCHEDULE.totalMs, 7_200_000)
})
