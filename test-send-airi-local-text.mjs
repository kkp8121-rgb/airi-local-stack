import assert from 'node:assert/strict'
import test from 'node:test'

import {
  CLIENT_POSSIBLE_EVENTS,
  assistantMessageShape,
  assistantText,
  buildInputTextEvent,
  createSendTiming,
  createAssistantEventTracker,
  decodeTextArgument,
  isCorrelatedOutputEvent,
  resolveAssistantShape,
  resolveAssistantText,
  validateServerConfig,
} from './send-airi-local-text.mjs'

test('creates a content-free wall-clock send timestamp for cross-process meters', () => {
  const timing = createSendTiming()
  assert.equal(Number.isSafeInteger(timing.sentEpochMs), true)
  assert.equal(typeof timing.startedAt, 'number')
  assert.equal('text' in timing, false)
})

test('builds input payload with the opaque event id in metadata', () => {
  assert.deepEqual(buildInputTextEvent('same text', 'input-a'), {
    type: 'input:text',
    data: { text: 'same text' },
    route: { delivery: { required: true } },
    metadata: { event: { id: 'input-a' } },
  })
})

test('correlates output only through metadata.event.parentId', () => {
  const id = 'input-a'
  assert.equal(isCorrelatedOutputEvent({ metadata: { event: { parentId: id } } }, id), true)
  assert.equal(isCorrelatedOutputEvent({ metadata: { event: { parentId: 'input-b' } } }, id), false)
  assert.equal(isCorrelatedOutputEvent({ metadata: { event: {} } }, id), false)
  assert.equal(isCorrelatedOutputEvent({ data: { text: 'same text' } }, id), false)
})

test('keeps same-text interleaved conversations and empty completions isolated', () => {
  const trackerA = createAssistantEventTracker('input-a')
  const trackerB = createAssistantEventTracker('input-b')
  const event = (type, parentId, message) => ({
    type,
    data: type === 'output:gen-ai:chat:cancelled'
      ? { reason: 'superseded' }
      : { text: 'same text', message },
    ...(parentId === undefined ? {} : { metadata: { event: { parentId } } }),
  })

  const messageA = event('output:gen-ai:chat:message', 'input-a', { content: 'answer A' })
  const messageB = event('output:gen-ai:chat:message', 'input-b', { content: 'answer B' })
  const completeA = event('output:gen-ai:chat:complete', 'input-a', { content: '' })
  const completeB = event('output:gen-ai:chat:complete', 'input-b', { content: '' })
  const missing = event('output:gen-ai:chat:message', undefined, { content: 'unrelated' })

  for (const item of [messageA, messageB, missing, completeA, completeB]) {
    trackerA.observe(item)
    trackerB.observe(item)
  }
  assert.equal(trackerA.completion(completeA, 1).assistant, 'answer A')
  assert.equal(trackerB.completion(completeB, 1).assistant, 'answer B')
  assert.equal(trackerA.eventStats.matchingAssistantMessages, 1)
  assert.equal(trackerB.eventStats.matchingAssistantMessages, 1)
  assert.equal(trackerA.eventStats.matchingCompletions, 1)
})

test('announces both the input and matching completion event contracts', () => {
  assert.deepEqual(CLIENT_POSSIBLE_EVENTS, [
    'input:text',
    'output:gen-ai:chat:message',
    'output:gen-ai:chat:complete',
    'output:gen-ai:chat:cancelled',
    'output:gen-ai:chat:playback-start',
  ])
})

function correlatedEvent(type, parentId, data = {}) {
  return { type, data, metadata: { event: { parentId } } }
}

test('waits for playback start when completion arrives first', () => {
  const tracker = createAssistantEventTracker('input-a')
  const complete = correlatedEvent('output:gen-ai:chat:complete', 'input-a', { message: { content: 'answer' } })
  const playback = correlatedEvent('output:gen-ai:chat:playback-start', 'input-a', {})

  tracker.observe(complete)
  assert.equal(tracker.waitTerminal(complete, 12), undefined)
  tracker.observe(playback)
  assert.deepEqual(tracker.waitPlaybackStart(playback, 34), {
    terminal: {
      cancelled: false,
      elapsedMs: 12,
      assistant: 'answer',
      assistantSource: 'completion',
      assistantShape: assistantMessageShape({ content: 'answer' }),
    },
    playback: { playbackStarted: true, playbackStartedMs: 34 },
  })
})

test('waits for completion when playback start arrives first', () => {
  const tracker = createAssistantEventTracker('input-a')
  const playback = correlatedEvent('output:gen-ai:chat:playback-start', 'input-a', {})
  const complete = correlatedEvent('output:gen-ai:chat:complete', 'input-a', { message: { content: 'answer' } })

  tracker.observe(playback)
  assert.deepEqual(tracker.waitPlaybackStart(playback, 4), {
    playback: { playbackStarted: true, playbackStartedMs: 4 },
  })
  tracker.observe(complete)
  assert.deepEqual(tracker.waitTerminal(complete, 18), {
    cancelled: false,
    elapsedMs: 18,
    assistant: 'answer',
    assistantSource: 'completion',
    assistantShape: assistantMessageShape({ content: 'answer' }),
    playbackStarted: true,
    playbackStartedMs: 4,
  })
})

test('ignores wrong-parent and duplicate playback-start events', () => {
  const tracker = createAssistantEventTracker('input-a')
  const wrong = correlatedEvent('output:gen-ai:chat:playback-start', 'input-b', {})
  const playback = correlatedEvent('output:gen-ai:chat:playback-start', 'input-a', {})
  const complete = correlatedEvent('output:gen-ai:chat:complete', 'input-a', { message: { content: 'answer' } })

  tracker.observe(wrong)
  assert.equal(tracker.waitPlaybackStart(wrong, 2), undefined)
  tracker.observe(complete)
  assert.equal(tracker.waitTerminal(complete, 3), undefined)
  assert.equal(tracker.waitPlaybackStart(correlatedEvent('output:gen-ai:chat:playback-start', 'input-a', { leaked: true }), 3), undefined)
  tracker.observe(playback)
  assert.ok(tracker.waitPlaybackStart(playback, 4).terminal)
  tracker.observe(playback)
  assert.equal(tracker.waitPlaybackStart(playback, 5), undefined)
  assert.equal(tracker.eventStats.matchingPlaybackStarts, 2)
})

test('ignores malformed correlated playback payloads', () => {
  const tracker = createAssistantEventTracker('input-a')
  const malformed = [null, 'not-an-object', []].map(data => ({
    type: 'output:gen-ai:chat:playback-start',
    data,
    metadata: { event: { parentId: 'input-a' } },
  }))

  for (const event of malformed) {
    tracker.observe(event)
    assert.equal(tracker.waitPlaybackStart(event, 2), undefined)
  }

  const valid = correlatedEvent('output:gen-ai:chat:playback-start', 'input-a', {})
  tracker.observe(valid)
  assert.deepEqual(tracker.waitPlaybackStart(valid, 4), {
    playback: { playbackStarted: true, playbackStartedMs: 4 },
  })
  // The diagnostic counter records correlated envelopes, while the terminal
  // gate above accepts only the final exact empty-object payload.
  assert.equal(tracker.eventStats.matchingPlaybackStarts, 4)
})

test('treats matching cancellation as immediate while waiting for playback', () => {
  const tracker = createAssistantEventTracker('input-a')
  const cancelled = correlatedEvent('output:gen-ai:chat:cancelled', 'input-a', { reason: 'superseded' })

  tracker.observe(cancelled)
  assert.deepEqual(tracker.waitTerminal(cancelled, 7), { cancelled: true, elapsedMs: 7 })
})

test('ignores malformed or non-supersession cancellation payloads', () => {
  const tracker = createAssistantEventTracker('input-a')
  const malformed = [null, 'superseded', [], { reason: 'cancelled' }].map(data => ({
    type: 'output:gen-ai:chat:cancelled',
    data,
    metadata: { event: { parentId: 'input-a' } },
  }))

  for (const event of malformed) {
    tracker.observe(event)
    assert.equal(tracker.waitTerminal(event, 2), undefined)
  }

  const valid = correlatedEvent('output:gen-ai:chat:cancelled', 'input-a', { reason: 'superseded' })
  tracker.observe(valid)
  assert.deepEqual(tracker.waitTerminal(valid, 4), { cancelled: true, elapsedMs: 4 })
  assert.equal(tracker.eventStats.matchingCancellations, 5)
})

test('cancellation after playback start remains the terminal outcome', () => {
  const tracker = createAssistantEventTracker('input-a')
  const playback = correlatedEvent('output:gen-ai:chat:playback-start', 'input-a', {})
  const cancelled = correlatedEvent('output:gen-ai:chat:cancelled', 'input-a', { reason: 'superseded' })

  tracker.observe(playback)
  assert.deepEqual(tracker.waitPlaybackStart(playback, 4), {
    playback: { playbackStarted: true, playbackStartedMs: 4 },
  })
  tracker.observe(cancelled)
  assert.deepEqual(tracker.waitTerminal(cancelled, 9), { cancelled: true, elapsedMs: 9 })

  const lateComplete = correlatedEvent('output:gen-ai:chat:complete', 'input-a', { message: { content: 'late' } })
  tracker.observe(lateComplete)
  assert.equal(tracker.waitTerminal(lateComplete, 10), undefined)
})

test('a claimed terminal ignores late message and playback events', () => {
  const tracker = createAssistantEventTracker('input-a')
  const playback = correlatedEvent('output:gen-ai:chat:playback-start', 'input-a', {})
  const complete = correlatedEvent('output:gen-ai:chat:complete', 'input-a', { message: { content: 'answer' } })

  tracker.observe(playback)
  assert.deepEqual(tracker.waitPlaybackStart(playback, 4), {
    playback: { playbackStarted: true, playbackStartedMs: 4 },
  })
  tracker.observe(complete)
  assert.equal(tracker.waitTerminal(complete, 8).assistant, 'answer')

  const lateMessage = correlatedEvent('output:gen-ai:chat:message', 'input-a', { message: { content: 'late' } })
  tracker.observe(lateMessage)
  assert.equal(tracker.waitPlaybackStart(playback, 11), undefined)
  assert.equal(tracker.waitTerminal(complete, 12), undefined)
})

test('playback-first empty completion does not adopt a later message shell', () => {
  const tracker = createAssistantEventTracker('input-a')
  const playback = correlatedEvent('output:gen-ai:chat:playback-start', 'input-a', {})
  const complete = correlatedEvent('output:gen-ai:chat:complete', 'input-a', { message: {} })

  tracker.observe(playback)
  assert.deepEqual(tracker.waitPlaybackStart(playback, 3), {
    playback: { playbackStarted: true, playbackStartedMs: 3 },
  })
  tracker.observe(complete)
  const terminal = tracker.waitTerminal(complete, 7)
  assert.equal(terminal.assistantSource, 'none')
  assert.equal(terminal.assistant, '')

  const lateMessage = correlatedEvent('output:gen-ai:chat:message', 'input-a', {
    message: { content: 'late message' },
  })
  tracker.observe(lateMessage)
  assert.equal(tracker.waitTerminal(complete, 8), undefined)
})

test('playback wait keeps the first correlated completion across duplicate replays', () => {
  const tracker = createAssistantEventTracker('input-a')
  const playback = correlatedEvent('output:gen-ai:chat:playback-start', 'input-a', {})
  const first = correlatedEvent('output:gen-ai:chat:complete', 'input-a', {
    message: { content: 'first answer' },
  })
  const replay = correlatedEvent('output:gen-ai:chat:complete', 'input-a', {
    message: { content: 'replayed answer' },
  })

  tracker.observe(first)
  assert.equal(tracker.waitTerminal(first, 7), undefined)
  tracker.observe(replay)
  assert.equal(tracker.waitTerminal(replay, 8), undefined)
  tracker.observe(playback)
  const outcome = tracker.waitPlaybackStart(playback, 9)
  const terminal = outcome.terminal
  assert.equal(terminal.assistant, 'first answer')
  assert.equal(terminal.elapsedMs, 7)
})

test('rejects malformed completion envelopes but accepts a valid empty shell', () => {
  const tracker = createAssistantEventTracker('input-a')
  for (const [elapsedTerminal, elapsedWait, data] of [
    [1, 2, null],
    [3, 4, 'malformed'],
    [5, 6, []],
  ]) {
    const malformed = correlatedEvent('output:gen-ai:chat:complete', 'input-a', data)
    assert.equal(tracker.terminal(malformed, elapsedTerminal), undefined)
    assert.equal(tracker.waitTerminal(malformed, elapsedWait), undefined)
  }

  const validEmpty = correlatedEvent('output:gen-ai:chat:complete', 'input-a', {
    message: { content: '' },
  })
  const terminal = tracker.terminal(validEmpty, 7)
  assert.equal(terminal.cancelled, false)
  assert.equal(terminal.assistant, '')
})

test('default completion terminal does not require playback start', () => {
  const tracker = createAssistantEventTracker('input-a')
  const complete = correlatedEvent('output:gen-ai:chat:complete', 'input-a', { message: { content: 'answer' } })

  tracker.observe(complete)
  assert.equal(tracker.terminal(complete, 9).cancelled, false)
})

test('claims only the first exact correlated terminal for same-text conversations', () => {
  const trackerA = createAssistantEventTracker('input-a')
  const trackerB = createAssistantEventTracker('input-b')
  const event = (type, parentId, message) => ({
    type,
    data: type === 'output:gen-ai:chat:cancelled'
      ? { reason: 'superseded' }
      : { text: 'same text', message },
    ...(parentId === undefined ? {} : { metadata: { event: { parentId } } }),
  })
  const messageB = event('output:gen-ai:chat:message', 'input-b', { content: 'answer B' })
  const cancelledA = event('output:gen-ai:chat:cancelled', 'input-a')
  const malformedCancelledA = { ...cancelledA, data: { reason: 'other' } }
  const completeA = event('output:gen-ai:chat:complete', 'input-a', { content: 'late A' })
  const completeB = event('output:gen-ai:chat:complete', 'input-b', { content: '' })

  for (const item of [messageB, cancelledA, completeB, completeA]) {
    trackerA.observe(item)
    trackerB.observe(item)
  }

  assert.deepEqual(trackerA.terminal(cancelledA, 7), { cancelled: true, elapsedMs: 7 })
  const malformedTracker = createAssistantEventTracker('input-a')
  assert.equal(malformedTracker.terminal(malformedCancelledA, 6), undefined)
  assert.equal(trackerA.terminal(completeB, 8), undefined)
  assert.equal(trackerA.terminal(completeA, 9), undefined)
  assert.equal(trackerA.eventStats.matchingCancellations, 1)
  assert.equal(trackerA.eventStats.matchingCompletions, 1)

  const completedB = trackerB.terminal(completeB, 10)
  assert.equal(completedB.cancelled, false)
  assert.equal(completedB.assistant, 'answer B')
  assert.equal(completedB.assistantSource, 'message-event')
})

test('extracts assistant text from string or text-part content only', () => {
  assert.equal(assistantText({ content: '짧은 답' }), '짧은 답')
  assert.equal(assistantText({ content: [
    { type: 'text', text: '첫째' },
    { type: 'image', image: 'ignored' },
    { type: 'text', text: '둘째' },
  ] }), '첫째둘째')
  assert.equal(assistantText({}), '')
})

test('falls back to runtime text slices without duplicating standard content', () => {
  assert.equal(assistantText({ content: '', slices: [
    { type: 'text', text: 'slice answer' },
    { type: 'tool-call', toolCall: {} },
  ] }), 'slice answer')
  assert.equal(assistantText({ content: 'standard answer', slices: [
    { type: 'text', text: 'duplicate answer' },
  ] }), 'standard answer')
  assert.equal(assistantText({ content: '   ', slices: [
    { type: 'text', text: 'slice after whitespace shell' },
  ] }), 'slice after whitespace shell')
  assert.equal(assistantText({ content: '', slices: [
    { type: 'text', text: '   ' },
  ], categorization: { speech: 'categorized after whitespace slice' } }), 'categorized after whitespace slice')
  assert.equal(assistantText({ content: '', categorization: { speech: '   ' } }), '')
  assert.equal(assistantText({ content: '', categorization: { speech: 'categorized answer' } }), 'categorized answer')
})

test('reports only content-free assistant message shape metadata', () => {
  assert.deepEqual(assistantMessageShape({
    content: 'private text',
    slices: [{ type: 'text', text: 'private slice' }],
    categorization: { speech: 'private speech' },
    id: 'private id',
  }), {
    message_object: true,
    content_kind: 'string',
    content_parts: 0,
    slices_kind: 'array',
    slices_parts: 1,
    categorization_object: true,
    categorization_speech_kind: 'string',
  })
})

test('uses the matching assistant message when completion carries an empty shell', () => {
  assert.equal(resolveAssistantText({ content: 'completion answer' }, 'message answer'), 'completion answer')
  assert.equal(resolveAssistantText({ content: '', slices: [] }, 'message answer'), 'message answer')
  assert.equal(resolveAssistantText({ content: '' }, ''), '')
})

test('reports the actual empty event shape instead of the initialized shell', () => {
  const matchingShape = assistantMessageShape({
    content: '',
    slices: [],
    categorization: { speech: '' },
  })
  assert.deepEqual(
    resolveAssistantShape({ content: '' }, matchingShape, true),
    matchingShape,
  )

  const completion = { content: '', slices: [{ type: 'tool-call' }] }
  assert.deepEqual(
    resolveAssistantShape(completion, assistantMessageShape(undefined), false),
    assistantMessageShape(completion),
  )
})

test('ignores malformed correlated message envelopes when resolving an empty completion shape', () => {
  for (const malformedData of [
    null,
    {},
    { message: null },
    { message: 'malformed' },
    { message: [] },
  ]) {
    const tracker = createAssistantEventTracker('input-a')
    tracker.observe(correlatedEvent('output:gen-ai:chat:message', 'input-a', malformedData))
    const complete = correlatedEvent('output:gen-ai:chat:complete', 'input-a', {
      message: { content: '', slices: [] },
    })
    const terminal = tracker.terminal(complete, 4)
    assert.deepEqual(terminal.assistantShape, assistantMessageShape(complete.data.message))
  }
})

test('decodes direct and base64 Korean input without changing it', () => {
  const text = '한국어 테스트'
  assert.equal(decodeTextArgument(['--text', text]), text)
  assert.equal(
    decodeTextArgument(['--text-base64', Buffer.from(text, 'utf8').toString('base64')]),
    text,
  )
})

test('requires exactly one bounded nonempty text argument', () => {
  assert.throws(() => decodeTextArgument([]))
  assert.throws(() => decodeTextArgument(['--text', '', '--text-base64', '']))
  assert.throws(() => decodeTextArgument(['--text', '']))
  assert.throws(() => decodeTextArgument(['--text', 'x'.repeat(1001)]))
})

test('accepts only the authenticated plaintext loopback channel', () => {
  assert.deepEqual(validateServerConfig({
    hostname: '127.0.0.1',
    authToken: ' local-token ',
    tlsConfig: null,
  }), { hostname: '127.0.0.1', token: 'local-token' })
  assert.throws(() => validateServerConfig({ hostname: '0.0.0.0', authToken: 'x', tlsConfig: null }))
  assert.throws(() => validateServerConfig({ hostname: '127.0.0.1', authToken: '', tlsConfig: null }))
  assert.throws(() => validateServerConfig({ hostname: '127.0.0.1', authToken: 'x', tlsConfig: {} }))
})
