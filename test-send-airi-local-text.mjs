import assert from 'node:assert/strict'
import test from 'node:test'

import {
  CLIENT_POSSIBLE_EVENTS,
  assistantMessageShape,
  assistantText,
  buildInputTextEvent,
  createAssistantEventTracker,
  decodeTextArgument,
  isCorrelatedOutputEvent,
  resolveAssistantShape,
  resolveAssistantText,
  validateServerConfig,
} from './send-airi-local-text.mjs'

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
  ])
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
