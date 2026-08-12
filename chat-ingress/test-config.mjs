import assert from 'node:assert/strict'
import test from 'node:test'
import { parseChatIngressConfig } from './config.mjs'

test('configuration is exact-off unless explicitly on', () => {
  assert.deepEqual(parseChatIngressConfig({}), { enabled: false, capacity: 64, recentCapacity: 4096, identityKey: undefined })
  for (const value of ['ON', 'true', '1', 'off', ' on']) assert.equal(parseChatIngressConfig({ AIRI_CHAT_INGRESS: value }).enabled, false)
  assert.deepEqual(parseChatIngressConfig({ AIRI_CHAT_INGRESS: 'on', AIRI_CHAT_INGRESS_IDENTITY_KEY: 'k'.repeat(32) }), { enabled: true, capacity: 64, recentCapacity: 4096, identityKey: 'k'.repeat(32) })
})
