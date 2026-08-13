import assert from 'node:assert/strict'
import test from 'node:test'
import { StreamListQuotaError, assembleQuotaReport, runStreamListTrial } from './streamlist-quota.mjs'

function stream(items, hooks = {}) {
  return {
    async *[Symbol.asyncIterator]() {
      try { yield * items } finally { hooks.closed = (hooks.closed || 0) + 1 }
    }
  }
}

const response = (messageCount = 0, nextPageToken = null, offline = false) => ({ messageCount, nextPageToken, offline })
const clock = () => 10
// Mirrors the module's own stop-reason contract; a returned reason outside this
// list is a leaked internal sentinel, which `assembleQuotaReport` must reject.
const STOP_REASONS = ['normal_close', 'duration_cap', 'message_cap', 'response_cap', 'connection_cap', 'offline', 'aborted', 'open_failure', 'read_failure', 'invalid_summary']
// The clock stops the trial once it has been read more than `zeros` times, so a
// deadline can be placed exactly after a batch has already been received.
const steppedClock = (zeros) => { let ticks = 0; return () => (ticks++ < zeros ? 0 : 5) }
const forged = (secret) => { const error = new StreamListQuotaError(secret); error.rawChat = secret; return error }

test('normal close and first response counts are content-free', async () => {
  const result = await runStreamListTrial({ kind: 'message', openStream: async () => stream([response(2)]), now: clock })
  assert.deepEqual(result, { schema: 'airi.streamlist-quota-trial.v1', kind: 'message', status: 'completed', stopReason: 'normal_close', durationMs: 0, messages: 2, responses: 1, discardedResponses: 0, connections: 1, resumes: 0, firstResponseMs: 0, firstMessageMs: 0 })
  assert.equal(Object.isFrozen(result), true)
})

test('empty duration does not open a stream', async () => {
  let opened = 0
  const result = await runStreamListTrial({ kind: 'idle', durationMs: 0, openStream: async () => { opened += 1; return stream([]) }, now: clock })
  assert.equal(opened, 0)
  assert.equal(result.stopReason, 'duration_cap')
})

test('zero-message cap, offline, timing, and natural reconnect close are exact', async () => {
  let opened = 0
  const zero = await runStreamListTrial({ kind: 'message', maxMessages: 0, openStream: async () => { opened += 1; return stream([]) }, now: clock })
  const offline = await runStreamListTrial({ kind: 'idle', openStream: async () => stream([response(0, null, true)]), now: clock })
  const natural = await runStreamListTrial({ kind: 'reconnect', maxConnections: 1, openStream: async () => stream([response()]), now: clock })
  assert.equal(opened, 0)
  assert.equal(zero.stopReason, 'message_cap')
  assert.equal(offline.stopReason, 'offline')
  assert.equal(natural.stopReason, 'normal_close')
  assert.equal(offline.firstResponseMs, 0)
  assert.equal(offline.firstMessageMs, null)
})

test('message and response caps stop bounded trials', async () => {
  const messages = await runStreamListTrial({ kind: 'message', maxMessages: 2, openStream: async () => stream([response(2)]), now: clock })
  const responses = await runStreamListTrial({ kind: 'idle', maxResponses: 1, openStream: async () => stream([response(), response()]), now: clock })
  assert.equal(messages.stopReason, 'message_cap')
  assert.equal(responses.stopReason, 'response_cap')
})

test('reconnect resumes are bounded and tokens never leave the result', async () => {
  const seen = []
  const result = await runStreamListTrial({ kind: 'reconnect', maxConnections: 2, openStream: async ({ pageToken }) => { seen.push(pageToken); return stream([response(0, 'private-token')]) }, now: clock })
  assert.deepEqual(seen, [null, 'private-token'])
  assert.equal(result.stopReason, 'connection_cap')
  assert.equal(result.resumes, 1)
  assert.equal(JSON.stringify(result).includes('private-token'), false)
})

test('open, read, and invalid summaries are sanitized', async () => {
  const open = await runStreamListTrial({ kind: 'idle', openStream: async () => { throw new Error('provider secret') }, now: clock })
  const read = await runStreamListTrial({ kind: 'idle', openStream: async () => ({ [Symbol.asyncIterator]: () => ({ next: async () => { throw new Error('provider secret') } }) }), now: clock })
  const invalid = await runStreamListTrial({ kind: 'idle', openStream: async () => stream([{ messageCount: 1, nextPageToken: null, offline: false, text: 'secret' }]), now: clock })
  assert.deepEqual([open.stopReason, read.stopReason, invalid.stopReason], ['open_failure', 'read_failure', 'invalid_summary'])
})

test('timeout cleanup and hostile shapes fail safely', async () => {
  let cleared = 0
  const result = await runStreamListTrial({ kind: 'idle', durationMs: 5, now: () => 0, setTimeout: (fn) => { fn(); return 1 }, clearTimeout: () => { cleared += 1 }, openStream: async () => ({ [Symbol.asyncIterator]: () => ({ next: () => new Promise(() => {}), return: async () => {} }) }) })
  assert.equal(result.stopReason, 'duration_cap')
  assert.equal(cleared, 1)
  await assert.rejects(() => runStreamListTrial(Object.create(null)), StreamListQuotaError)
  const hostile = await runStreamListTrial({ kind: 'idle', openStream: async () => stream([{ messageCount: 0, nextPageToken: null, offline: false, [Symbol('x')]: 1 }]), now: clock })
  assert.equal(hostile.stopReason, 'invalid_summary')
})

test('clock and report allowlists reject forged or secret-bearing inputs', async () => {
  let tick = 2
  await assert.rejects(() => runStreamListTrial({ kind: 'idle', now: () => tick--, openStream: async () => stream([response()]) }), StreamListQuotaError)
  await assert.rejects(() => runStreamListTrial({ kind: 'idle', now: () => { throw new Error('clock secret') }, openStream: async () => stream([]) }), StreamListQuotaError)
  const trial = { schema: 'airi.streamlist-quota-trial.v1', kind: 'idle', status: 'completed', stopReason: 'bad reason', durationMs: 1, messages: 0, responses: 0, discardedResponses: 0, connections: 1, resumes: 0, firstResponseMs: null, firstMessageMs: null }
  assert.throws(() => assembleQuotaReport({ trial, quotaBefore: 1, quotaAfter: 1, quotaSource: 'secret' }), StreamListQuotaError)
  assert.throws(() => assembleQuotaReport({ trial, quotaBefore: 1, quotaAfter: 1, quotaSource: 'manual_google_cloud_console_snapshot' }), StreamListQuotaError)
})

test('hung open and hung iterator cleanup remain bounded', async () => {
  const timer = (fn) => { fn(); return 1 }
  const hungOpen = await runStreamListTrial({ kind: 'idle', durationMs: 5, now: () => 0, setTimeout: timer, clearTimeout: () => {}, openStream: async () => new Promise(() => {}) })
  let returns = 0
  const hungReturn = await runStreamListTrial({ kind: 'idle', now: clock, setTimeout: () => 1, clearTimeout: () => {}, openStream: async () => ({ [Symbol.asyncIterator]: () => ({ next: async () => ({ done: true, value: undefined }), return: () => { returns += 1; return new Promise(() => {}) } }) }) })
  assert.equal(hungOpen.stopReason, 'duration_cap')
  assert.equal(hungReturn.stopReason, 'normal_close')
  await Promise.resolve()
  assert.equal(returns, 1)
})

test('final received batch preserves bounded max-message overshoot', async () => {
  const result = await runStreamListTrial({ kind: 'message', maxMessages: 1, openStream: async () => stream([response(2_000)]), now: clock })
  assert.equal(result.messages, 2_000)
  assert.equal(result.stopReason, 'message_cap')
})

test('local deadline abort signal remains live and late streams are cleaned up', async () => {
  let observedAbort = false
  let returned = 0
  const result = await runStreamListTrial({ kind: 'idle', durationMs: 5, now: () => 0, setTimeout: (fn) => { fn(); return 1 }, clearTimeout: () => {}, openStream: async ({ signal }) => {
    observedAbort = signal.aborted
    return { [Symbol.asyncIterator]: () => ({ return: () => { returned += 1 } }) }
  } })
  await Promise.resolve()
  await Promise.resolve()
  assert.equal(result.stopReason, 'duration_cap')
  assert.equal(observedAbort, true)
  assert.equal(returned, 1)
})

test('post-open deadline closes the just-opened stream exactly once', async () => {
  const values = [0, 0, 5]
  let returned = 0
  const result = await runStreamListTrial({ kind: 'idle', durationMs: 5, now: () => values.shift() ?? 5, setTimeout: () => 1, clearTimeout: () => {}, openStream: async () => ({ [Symbol.asyncIterator]: () => ({ return: () => { returned += 1 } }) }) })
  await Promise.resolve()
  assert.equal(result.stopReason, 'duration_cap')
  assert.equal(returned, 1)
})

test('provider iterator sentinels cannot spoof timeout or abort', async () => {
  for (const value of [{ aborted: true }, { timeout: true }, { done: false, value: response(), aborted: true }]) {
    const result = await runStreamListTrial({ kind: 'idle', openStream: async () => ({ [Symbol.asyncIterator]: () => ({ next: async () => value }) }), now: clock })
    assert.equal(result.stopReason, 'read_failure')
  }
})

test('report state and caller signal contracts are exact', async () => {
  await assert.rejects(() => runStreamListTrial({ kind: 'idle', signal: { aborted: false }, openStream: async () => stream([]), now: clock }), StreamListQuotaError)
  const base = { schema: 'airi.streamlist-quota-trial.v1', kind: 'idle', status: 'completed', durationMs: 1, messages: 0, responses: 0, discardedResponses: 0, connections: 0, resumes: 0, firstResponseMs: null, firstMessageMs: null }
  assert.throws(() => assembleQuotaReport({ trial: { ...base, stopReason: 'normal_close' }, quotaBefore: 1, quotaAfter: 1, quotaSource: 'manual_google_cloud_console_snapshot' }), StreamListQuotaError)
  assert.throws(() => assembleQuotaReport({ trial: { ...base, stopReason: 'offline' }, quotaBefore: 1, quotaAfter: 1, quotaSource: 'manual_google_cloud_console_snapshot' }), StreamListQuotaError)
})

test('manual quota validation and report aggregation reject forbidden data', () => {
  const trial = { schema: 'airi.streamlist-quota-trial.v1', kind: 'idle', status: 'completed', stopReason: 'normal_close', durationMs: 1, messages: 0, responses: 0, discardedResponses: 0, connections: 1, resumes: 0, firstResponseMs: null, firstMessageMs: null }
  const report = assembleQuotaReport({ trial, quotaBefore: 100, quotaAfter: 103, quotaSource: 'manual_google_cloud_console_snapshot' })
  assert.equal(report.quotaDelta, 3)
  assert.equal(Object.isFrozen(report), true)
  assert.equal(/token|text|name|url|error|id/i.test(Object.keys(report).join(',')), false)
  assert.throws(() => assembleQuotaReport({ trial, quotaBefore: 3, quotaAfter: 2, quotaSource: 'manual_google_cloud_console_snapshot' }), StreamListQuotaError)
})

test('a provider-constructed quota error is sanitized like any other transport failure', async () => {
  const open = await runStreamListTrial({ kind: 'idle', now: clock, openStream: async () => { throw forged('phone 010-1234-5678') } })
  const read = await runStreamListTrial({ kind: 'idle', now: clock, openStream: async () => ({ [Symbol.asyncIterator]: () => ({ next: async () => { throw forged('chat body') } }) }) })
  const summary = await runStreamListTrial({ kind: 'idle', now: clock, openStream: async () => stream([new Proxy({ messageCount: 1, nextPageToken: null, offline: false }, { ownKeys() { throw forged('batch body') } })]) })
  assert.deepEqual([open.stopReason, read.stopReason, summary.stopReason], ['open_failure', 'read_failure', 'invalid_summary'])
  assert.deepEqual([open.status, read.status, summary.status], ['failed', 'failed', 'failed'])
  assert.equal(/010-1234-5678|chat body|batch body|rawChat/.test(JSON.stringify([open, read, summary])), false)
  const hostileOptions = new Proxy({ kind: 'idle', openStream: async () => stream([]), now: clock }, { ownKeys() { throw forged('option body') } })
  await assert.rejects(() => runStreamListTrial(hostileOptions), (error) => error instanceof StreamListQuotaError && error.code === 'invalid_options' && !('rawChat' in error))
})

test('a natural close after several reconnects is not a connection cap', async () => {
  const tokens = ['first-private-token', 'second-private-token']
  let opened = 0
  const result = await runStreamListTrial({ kind: 'reconnect', maxConnections: 5, now: clock, openStream: async () => { opened += 1; const token = tokens.shift(); return stream(token ? [response(0, token)] : []) } })
  assert.equal(opened, 3)
  assert.deepEqual([result.status, result.stopReason], ['completed', 'normal_close'])
  assert.deepEqual([result.connections, result.resumes], [3, 2])
  assert.equal(JSON.stringify(result).includes('private-token'), false)
  const report = assembleQuotaReport({ trial: result, quotaBefore: 4, quotaAfter: 7, quotaSource: 'manual_google_cloud_console_snapshot' })
  assert.deepEqual([report.stopReason, report.connections], ['normal_close', 3])
})

test('connections and discarded batches count what the provider already served', async () => {
  const postOpen = await runStreamListTrial({ kind: 'idle', durationMs: 5, now: steppedClock(2), setTimeout: () => 1, clearTimeout: () => {}, openStream: async () => ({ [Symbol.asyncIterator]: () => ({ return: () => {} }) }) })
  assert.deepEqual([postOpen.stopReason, postOpen.connections, postOpen.discardedResponses], ['duration_cap', 1, 0])
  const rejectedShape = await runStreamListTrial({ kind: 'idle', now: clock, openStream: async () => ({}) })
  assert.deepEqual([rejectedShape.stopReason, rejectedShape.connections], ['open_failure', 1])
  const rejectedIterator = await runStreamListTrial({ kind: 'idle', now: clock, openStream: async () => ({ [Symbol.asyncIterator]: () => ({}) }) })
  assert.deepEqual([rejectedIterator.stopReason, rejectedIterator.connections], ['open_failure', 1])
  const discarded = await runStreamListTrial({ kind: 'idle', durationMs: 5, now: steppedClock(4), setTimeout: () => 1, clearTimeout: () => {}, openStream: async () => stream([response(3)]) })
  assert.deepEqual([discarded.stopReason, discarded.connections], ['duration_cap', 1])
  assert.deepEqual([discarded.responses, discarded.discardedResponses, discarded.messages], [0, 1, 0])
  assert.equal(assembleQuotaReport({ trial: discarded, quotaBefore: 0, quotaAfter: 1, quotaSource: 'manual_google_cloud_console_snapshot' }).discardedResponses, 1)
  assert.throws(() => assembleQuotaReport({ trial: { ...discarded, stopReason: 'normal_close' }, quotaBefore: 0, quotaAfter: 1, quotaSource: 'manual_google_cloud_console_snapshot' }), StreamListQuotaError)
})

test('a caller abort signal stops opening and reading trials', async () => {
  const onOpen = new AbortController()
  const opening = await runStreamListTrial({ kind: 'idle', signal: onOpen.signal, now: clock, openStream: async () => { onOpen.abort(); return new Promise(() => {}) } })
  const onRead = new AbortController()
  const reading = await runStreamListTrial({ kind: 'idle', signal: onRead.signal, now: clock, openStream: async () => ({ [Symbol.asyncIterator]: () => ({ next: () => { onRead.abort(); return new Promise(() => {}) } }) }) })
  const already = new AbortController()
  already.abort()
  let opened = 0
  const before = await runStreamListTrial({ kind: 'idle', signal: already.signal, now: clock, openStream: async () => { opened += 1; return stream([]) } })
  assert.deepEqual([opening.status, reading.status, before.status], ['aborted', 'aborted', 'aborted'])
  assert.deepEqual([opening.stopReason, reading.stopReason, before.stopReason], ['aborted', 'aborted', 'aborted'])
  assert.deepEqual([opened, opening.connections, reading.connections], [0, 0, 1])
})

test('every produced stop reason is a contract reason that round-trips into a report', async () => {
  const aborted = new AbortController()
  const produced = [
    await runStreamListTrial({ kind: 'message', now: clock, openStream: async () => stream([response(2)]) }),
    await runStreamListTrial({ kind: 'idle', durationMs: 0, now: clock, openStream: async () => stream([]) }),
    await runStreamListTrial({ kind: 'idle', durationMs: 5, now: steppedClock(4), setTimeout: () => 1, clearTimeout: () => {}, openStream: async () => stream([response(3)]) }),
    await runStreamListTrial({ kind: 'message', maxMessages: 2, now: clock, openStream: async () => stream([response(2)]) }),
    await runStreamListTrial({ kind: 'idle', maxResponses: 1, now: clock, openStream: async () => stream([response(), response()]) }),
    await runStreamListTrial({ kind: 'reconnect', maxConnections: 2, now: clock, openStream: async () => stream([response(0, 'private-token')]) }),
    await runStreamListTrial({ kind: 'reconnect', maxConnections: 4, now: clock, openStream: (() => { let round = 0; return async () => { round += 1; return stream(round < 3 ? [response(0, 'private-token')] : []) } })() }),
    await runStreamListTrial({ kind: 'idle', now: clock, openStream: async () => stream([response(0, null, true)]) }),
    await runStreamListTrial({ kind: 'idle', signal: aborted.signal, now: clock, openStream: async () => { aborted.abort(); return new Promise(() => {}) } }),
    await runStreamListTrial({ kind: 'idle', now: clock, openStream: async () => { throw new Error('provider secret') } }),
    await runStreamListTrial({ kind: 'idle', now: clock, openStream: async () => ({ [Symbol.asyncIterator]: () => ({ next: async () => { throw new Error('provider secret') } }) }) }),
    await runStreamListTrial({ kind: 'idle', now: clock, openStream: async () => stream([{ messageCount: 1, nextPageToken: null, offline: false, text: 'secret' }]) })
  ]
  const seen = new Set()
  for (const trial of produced) {
    assert.equal(STOP_REASONS.includes(trial.stopReason), true, `stop reason outside the contract: ${trial.stopReason}`)
    seen.add(trial.stopReason)
    const report = assembleQuotaReport({ trial, quotaBefore: 1_000, quotaAfter: 1_007, quotaSource: 'manual_google_cloud_console_snapshot' })
    assert.equal(report.schema, 'airi.streamlist-quota-report.v1')
    assert.deepEqual([report.stopReason, report.status, report.quotaDelta], [trial.stopReason, trial.status, 7])
    assert.deepEqual([report.responses, report.discardedResponses, report.connections], [trial.responses, trial.discardedResponses, trial.connections])
  }
  assert.deepEqual([...seen].sort(), [...STOP_REASONS].sort())
})
