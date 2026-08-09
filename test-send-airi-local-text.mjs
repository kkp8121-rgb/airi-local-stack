import assert from 'node:assert/strict'
import test from 'node:test'

import {
  CLIENT_POSSIBLE_EVENTS,
  assistantMessageShape,
  assistantText,
  decodeTextArgument,
  resolveAssistantShape,
  resolveAssistantText,
  validateServerConfig,
} from './send-airi-local-text.mjs'

test('announces both the input and matching completion event contracts', () => {
  assert.deepEqual(CLIENT_POSSIBLE_EVENTS, [
    'input:text',
    'output:gen-ai:chat:message',
    'output:gen-ai:chat:complete',
  ])
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
