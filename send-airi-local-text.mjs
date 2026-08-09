import { readFile, stat } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const DEFAULT_SOURCE_ROOT = join(tmpdir(), 'airi-v0113-source-codex-20260808')
const MAX_CONFIG_BYTES = 16 * 1024
const MAX_TEXT_CODEPOINTS = 1000
export const CLIENT_POSSIBLE_EVENTS = [
  'input:text',
  'output:gen-ai:chat:message',
  'output:gen-ai:chat:complete',
]

export function assistantText(message) {
  const content = message?.content
  if (typeof content === 'string')
    return content
  if (!Array.isArray(content))
    return ''
  return content
    .filter(part => part && typeof part === 'object' && part.type === 'text' && typeof part.text === 'string')
    .map(part => part.text)
    .join('')
}

export function decodeTextArgument(args) {
  const textIndex = args.indexOf('--text')
  const base64Index = args.indexOf('--text-base64')
  if ((textIndex >= 0) === (base64Index >= 0))
    throw new Error('Provide exactly one of --text or --text-base64.')

  let text
  if (textIndex >= 0) {
    text = args[textIndex + 1]
  }
  else {
    const encoded = args[base64Index + 1]
    if (typeof encoded !== 'string' || !/^[A-Za-z0-9+/]*={0,2}$/.test(encoded))
      throw new Error('Invalid base64 text argument.')
    text = Buffer.from(encoded, 'base64').toString('utf8')
  }

  const codepoints = Array.from(text ?? '')
  if (!codepoints.length || codepoints.length > MAX_TEXT_CODEPOINTS || codepoints.includes('\0'))
    throw new Error('Text must contain 1 to 1000 Unicode code points and no NUL.')
  return text
}

export function validateServerConfig(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('Server channel config must be an object.')
  if (value.hostname !== '127.0.0.1')
    throw new Error('Refusing a non-loopback AIRI server channel.')
  if (value.tlsConfig != null)
    throw new Error('This local sender does not accept a TLS or remote channel.')
  if (typeof value.authToken !== 'string')
    throw new Error('AIRI server channel token is missing.')
  const token = value.authToken.trim()
  if (!token || token.length > 512)
    throw new Error('AIRI server channel token is invalid.')
  return { hostname: value.hostname, token }
}

async function loadServerConfig(configPath) {
  const info = await stat(configPath)
  if (!info.isFile() || info.size <= 0 || info.size > MAX_CONFIG_BYTES)
    throw new Error('AIRI server channel config file is invalid.')
  return validateServerConfig(JSON.parse(await readFile(configPath, 'utf8')))
}

async function main() {
  const args = process.argv.slice(2)
  const text = decodeTextArgument(args)
  const waitComplete = args.includes('--wait-complete') || args.includes('--print-assistant')
  const printAssistant = args.includes('--print-assistant')
  const appData = process.env.APPDATA
  if (!appData)
    throw new Error('APPDATA is unavailable.')

  const configPath = resolve(
    process.env.AIRI_SERVER_CHANNEL_CONFIG
      || join(appData, 'ai.moeru.airi', 'server-channel-config.json'),
  )
  const sourceRoot = resolve(process.env.AIRI_SOURCE_ROOT || DEFAULT_SOURCE_ROOT)
  const sdkEntry = join(sourceRoot, 'packages', 'server-sdk', 'dist', 'index.mjs')
  const { hostname, token } = await loadServerConfig(configPath)
  const { Client } = await import(pathToFileURL(sdkEntry).href)

  const eventStats = {
    assistantMessages: 0,
    matchingAssistantMessages: 0,
    completions: 0,
    matchingCompletions: 0,
    errors: 0,
  }
  const client = new Client({
    name: 'local-codex-chat-ingress',
    url: `ws://${hostname}:6121/ws`,
    token,
    autoConnect: false,
    autoReconnect: false,
    possibleEvents: CLIENT_POSSIBLE_EVENTS,
    onError: () => { eventStats.errors++ },
    onAnyMessage: (event) => {
      if (event?.type === 'output:gen-ai:chat:message') {
        eventStats.assistantMessages++
        if (event?.data?.text === text)
          eventStats.matchingAssistantMessages++
      }
      else if (event?.type === 'output:gen-ai:chat:complete') {
        eventStats.completions++
        if (event?.data?.text === text)
          eventStats.matchingCompletions++
      }
    },
  })

  const startedAt = performance.now()
  let completeResolve
  let completeReject
  const completion = new Promise((resolvePromise, rejectPromise) => {
    completeResolve = resolvePromise
    completeReject = rejectPromise
  })
  const completionTimeout = waitComplete
    ? setTimeout(() => completeReject(new Error(
        `Timed out waiting for matching AIRI completion (assistant_events=${eventStats.assistantMessages}, matching_assistant_events=${eventStats.matchingAssistantMessages}, completion_events=${eventStats.completions}, matching_completion_events=${eventStats.matchingCompletions}, errors=${eventStats.errors}).`,
      )), 90_000)
    : undefined
  const unsubscribe = waitComplete
    ? client.onEvent('output:gen-ai:chat:complete', (event) => {
        if (event?.data?.text !== text)
          return
        completeResolve({
          elapsedMs: Math.round(performance.now() - startedAt),
          assistant: assistantText(event?.data?.message),
        })
      })
    : undefined

  let completed
  try {
    await client.connect()
    client.sendOrThrow({
      type: 'input:text',
      data: { text },
      route: { delivery: { required: true } },
    })
    completed = waitComplete
      ? await completion
      : (await new Promise(resolvePromise => setTimeout(resolvePromise, 300)), undefined)
  }
  finally {
    if (completionTimeout)
      clearTimeout(completionTimeout)
    unsubscribe?.()
    client.close(1000, 'local input sent')
  }

  const output = {
    sent: true,
    transport: 'loopback-server-channel',
    chars: Array.from(text).length,
    ...(completed
      ? {
          completed: true,
          completed_ms: completed.elapsedMs,
          assistant_chars: Array.from(completed.assistant).length,
          ...(printAssistant ? { assistant: completed.assistant } : {}),
        }
      : {}),
  }
  process.stdout.write(`${JSON.stringify(output)}\n`)
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href
if (isMain) {
  main().catch((error) => {
    process.stderr.write(`${JSON.stringify({ sent: false, error: error instanceof Error ? error.message : 'unknown error' })}\n`)
    process.exitCode = 1
  })
}
