import assert from 'node:assert/strict'
import test from 'node:test'

import {
  CLIENT_POSSIBLE_EVENTS,
  assistantText,
  decodeTextArgument,
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
