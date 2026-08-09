import assert from 'node:assert/strict'
import test from 'node:test'
import { CLIENT_POSSIBLE_EVENTS, SNAPSHOT_KEYS, isAllowedSnapshot, validateServerConfig } from './get-airi-local-voice-status.mjs'

test('uses only the local voice status event pair', () => {
  assert.deepEqual(CLIENT_POSSIBLE_EVENTS, ['input:local:voice-status:request', 'output:local:voice-status:response'])
  assert.equal(CLIENT_POSSIBLE_EVENTS.some(x => x.includes('chat') || x.includes('context')), false)
})
test('refuses TLS and remote server channels', () => {
  assert.deepEqual(validateServerConfig({ hostname: '127.0.0.1', authToken: ' x ', tlsConfig: null }), { hostname: '127.0.0.1', token: 'x' })
  assert.throws(() => validateServerConfig({ hostname: 'localhost', authToken: 'x', tlsConfig: null }))
  assert.throws(() => validateServerConfig({ hostname: '127.0.0.1', authToken: 'x', tlsConfig: {} }))
})
test('prints only exact allowlisted snapshots', () => {
  const snapshot = {
    stageMounted: true,
    voiceInputEnabled: true,
    providerConfigured: true,
    recording: false,
    transcribing: false,
    vad: {
      active: true,
      listening: true,
      inputLive: true,
      inputEnabled: true,
      inputMuted: false,
      isSpeech: false,
      score: 0.4,
      threshold: 0.52,
      recentMax: 0.8,
      recentSamples: [0.2, 0.8],
    },
    microphonePermission: 'granted',
    lastCapture: { outcome: 'none', atMs: null },
  }
  assert.equal(isAllowedSnapshot(snapshot), true)
  assert.equal(isAllowedSnapshot({ ...snapshot, text: 'nope' }), false)
  assert.equal(isAllowedSnapshot({ ...snapshot, vad: { ...snapshot.vad, text: 'nope' } }), false)
  assert.equal(isAllowedSnapshot({ ...snapshot, vad: { ...snapshot.vad, score: Infinity } }), false)
  assert.equal(isAllowedSnapshot({ ...snapshot, vad: { ...snapshot.vad, recentSamples: [1.1] } }), false)
  assert.equal(isAllowedSnapshot({ ...snapshot, lastCapture: { outcome: 'bad', atMs: null } }), false)
  assert.deepEqual(Object.keys(snapshot).sort(), [...SNAPSHOT_KEYS].sort())
})
