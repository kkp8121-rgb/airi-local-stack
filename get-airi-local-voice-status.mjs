import { readFile, stat } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const DEFAULT_SOURCE_ROOT = join(tmpdir(), 'airi-v0113-source-codex-20260808')
const MAX_CONFIG_BYTES = 16 * 1024
export const CLIENT_POSSIBLE_EVENTS = ['input:local:voice-status:request', 'output:local:voice-status:response']
export const SNAPSHOT_KEYS = ['stageMounted', 'voiceInputEnabled', 'providerConfigured', 'recording', 'transcribing', 'vad', 'microphonePermission', 'lastCapture']
const PERMISSIONS = new Set(['granted', 'denied', 'prompt', 'unavailable'])
const CAPTURE_OUTCOMES = new Set(['none', 'capture-started', 'capture-skipped', 'transcription-started', 'transcription-accepted', 'transcription-empty', 'transcription-error', 'permission-denied', 'stream-unavailable'])

function hasExactKeys(value, keys) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const actual = Object.keys(value).sort()
  const expected = [...keys].sort()
  return actual.length === expected.length && actual.every((key, index) => key === expected[index])
}

export function validateServerConfig(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || value.hostname !== '127.0.0.1' || value.tlsConfig != null)
    throw new Error('Refusing a non-exact-loopback AIRI server channel.')
  const token = typeof value.authToken === 'string' ? value.authToken.trim() : ''
  if (!token || token.length > 512)
    throw new Error('AIRI server channel token is invalid.')
  return { hostname: '127.0.0.1', token }
}

export function isAllowedSnapshot(value) {
  return hasExactKeys(value, SNAPSHOT_KEYS)
    && ['stageMounted', 'voiceInputEnabled', 'providerConfigured', 'recording', 'transcribing'].every(key => typeof value[key] === 'boolean')
    && hasExactKeys(value.vad, ['active', 'listening', 'inputLive', 'inputEnabled', 'inputMuted', 'isSpeech', 'score', 'threshold', 'recentMax', 'recentSamples'])
    && typeof value.vad.active === 'boolean'
    && typeof value.vad.listening === 'boolean'
    && typeof value.vad.inputLive === 'boolean'
    && typeof value.vad.inputEnabled === 'boolean'
    && typeof value.vad.inputMuted === 'boolean'
    && typeof value.vad.isSpeech === 'boolean'
    && ['score', 'threshold', 'recentMax'].every(key => Number.isFinite(value.vad[key]) && value.vad[key] >= 0 && value.vad[key] <= 1)
    && Array.isArray(value.vad.recentSamples)
    && value.vad.recentSamples.length <= 50
    && value.vad.recentSamples.every(sample => Number.isFinite(sample) && sample >= 0 && sample <= 1)
    && PERMISSIONS.has(value.microphonePermission)
    && hasExactKeys(value.lastCapture, ['outcome', 'atMs'])
    && CAPTURE_OUTCOMES.has(value.lastCapture.outcome)
    && (value.lastCapture.atMs === null || (Number.isFinite(value.lastCapture.atMs) && value.lastCapture.atMs >= 0))
}

async function loadConfig(path) {
  const info = await stat(path)
  if (!info.isFile() || info.size <= 0 || info.size > MAX_CONFIG_BYTES) throw new Error('AIRI server channel config file is invalid.')
  return validateServerConfig(JSON.parse(await readFile(path, 'utf8')))
}

async function main() {
  const appData = process.env.APPDATA
  if (!appData) throw new Error('APPDATA is unavailable.')
  const config = await loadConfig(resolve(process.env.AIRI_SERVER_CHANNEL_CONFIG || join(appData, 'ai.moeru.airi', 'server-channel-config.json')))
  const sourceRoot = resolve(process.env.AIRI_SOURCE_ROOT || DEFAULT_SOURCE_ROOT)
  const { Client } = await import(pathToFileURL(join(sourceRoot, 'packages', 'server-sdk', 'dist', 'index.mjs')).href)
  const nonce = globalThis.crypto.randomUUID().replaceAll('-', '')
  const observedEventTypes = new Set()
  let registryModuleCount = 0
  let voiceCapableModuleCount = 0
  const client = new Client({
    name: 'local-codex-voice-status',
    url: `ws://${config.hostname}:6121/ws`,
    token: config.token,
    autoConnect: false,
    autoReconnect: false,
    possibleEvents: CLIENT_POSSIBLE_EVENTS,
    onAnyMessage: (event) => {
      if (typeof event?.type === 'string' && observedEventTypes.size < 32)
        observedEventTypes.add(event.type)
      if (event?.type === 'registry:modules:sync' && Array.isArray(event.data?.modules)) {
        registryModuleCount = event.data.modules.length
        voiceCapableModuleCount = event.data.modules.filter(module =>
          Array.isArray(module?.possibleEvents)
          && module.possibleEvents.includes('input:local:voice-status:request')
          && module.possibleEvents.includes('output:local:voice-status:response'),
        ).length
      }
    },
  })
  let unsubscribe
  let timer
  try {
    const snapshot = await new Promise(async (resolvePromise, rejectPromise) => {
      timer = setTimeout(() => {
        const types = [...observedEventTypes].sort().join(',') || 'none'
        rejectPromise(new Error(`Timed out waiting for local voice status; observed event types: ${types}; registry modules: ${registryModuleCount}; voice-capable modules: ${voiceCapableModuleCount}`))
      }, 5_000)
      unsubscribe = client.onEvent('output:local:voice-status:response', (event) => {
        if (event?.data?.nonce !== nonce || !isAllowedSnapshot(event?.data?.snapshot)) return
        resolvePromise(event.data.snapshot)
      })
      await client.connect()
      client.sendOrThrow({ type: 'input:local:voice-status:request', data: { nonce } })
    })
    process.stdout.write(`${JSON.stringify(snapshot)}\n`)
  }
  finally {
    if (timer) clearTimeout(timer)
    unsubscribe?.()
    client.close(1000, 'local voice status complete')
  }
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href
if (isMain) main().catch((error) => { process.stderr.write(`${JSON.stringify({ error: error instanceof Error ? error.message : 'unknown error' })}\n`); process.exitCode = 1 })
