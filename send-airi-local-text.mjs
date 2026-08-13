import { readFile, stat } from 'node:fs/promises'
import { randomUUID } from 'node:crypto'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const DEFAULT_SOURCE_ROOT = join(tmpdir(), 'airi-v0113-source-codex-20260808')
const MAX_CONFIG_BYTES = 16 * 1024
const MAX_TEXT_CODEPOINTS = 1000
const MAX_EVENT_TEXT_CODEPOINTS = 1100
export const CLIENT_POSSIBLE_EVENTS = [
  'input:text',
  'output:gen-ai:chat:message',
  'output:gen-ai:chat:complete',
  'output:gen-ai:chat:cancelled',
  'output:gen-ai:chat:playback-start',
]

export function assistantText(message) {
  const content = message?.content
  const contentText = typeof content === 'string'
    ? content
    : Array.isArray(content)
      ? content
          .filter(part => part && typeof part === 'object' && part.type === 'text' && typeof part.text === 'string')
          .map(part => part.text)
          .join('')
      : ''
  if (contentText.trim())
    return contentText

  // AIRI runtime messages also carry UI-native slices. Some packaged bridge
  // versions serialize an empty content field but retain completed speech here.
  const sliceText = Array.isArray(message?.slices)
    ? message.slices
        .filter(slice => slice && typeof slice === 'object' && slice.type === 'text' && typeof slice.text === 'string')
        .map(slice => slice.text)
        .join('')
    : ''
  if (sliceText.trim())
    return sliceText
  const categorizedText = message?.categorization?.speech
  return typeof categorizedText === 'string' && categorizedText.trim()
    ? categorizedText
    : ''
}

export function assistantMessageShape(message) {
  const content = message?.content
  const slices = message?.slices
  return {
    message_object: Boolean(message && typeof message === 'object' && !Array.isArray(message)),
    content_kind: Array.isArray(content) ? 'array' : typeof content,
    content_parts: Array.isArray(content) ? content.length : 0,
    slices_kind: Array.isArray(slices) ? 'array' : typeof slices,
    slices_parts: Array.isArray(slices) ? slices.length : 0,
    categorization_object: Boolean(message?.categorization && typeof message.categorization === 'object'),
    categorization_speech_kind: typeof message?.categorization?.speech,
  }
}

export function resolveAssistantText(completionMessage, matchingMessageText = '') {
  return assistantText(completionMessage) || (typeof matchingMessageText === 'string' ? matchingMessageText : '')
}

export function resolveAssistantShape(completionMessage, matchingMessageShape, matchingMessageSeen = false) {
  return assistantText(completionMessage) || !matchingMessageSeen
    ? assistantMessageShape(completionMessage)
    : matchingMessageShape
}

export function buildInputTextEvent(text, inputEventId) {
  return {
    type: 'input:text',
    data: { text },
    route: { delivery: { required: true } },
    metadata: { event: { id: inputEventId } },
  }
}

// Keep this wall-clock value separate from the monotonic elapsed-time clock:
// the meter runs in another process and can only correlate on Date.now().
export function createSendTiming() {
  return { sentEpochMs: Date.now(), startedAt: performance.now() }
}

export function isCorrelatedOutputEvent(event, inputEventId) {
  return event?.metadata?.event?.parentId === inputEventId
}

export function isEmptyPlaybackPayload(value) {
  return value !== null
    && typeof value === 'object'
    && !Array.isArray(value)
    && Object.keys(value).length === 0
}

function isValidCompletionEvent(event) {
  return event?.type === 'output:gen-ai:chat:complete'
    && event?.data !== null
    && typeof event?.data === 'object'
    && !Array.isArray(event.data)
}

function isValidMessageEvent(event) {
  if (event?.type !== 'output:gen-ai:chat:message'
    || event?.data === null
    || typeof event?.data !== 'object'
    || Array.isArray(event.data))
    return false
  const message = event.data.message
  return message !== null
    && typeof message === 'object'
    && !Array.isArray(message)
}

export function createAssistantEventTracker(inputEventId) {
  const eventStats = {
    assistantMessages: 0,
    matchingAssistantMessages: 0,
    completions: 0,
    matchingCompletions: 0,
    cancellations: 0,
    matchingCancellations: 0,
    playbackStarts: 0,
    matchingPlaybackStarts: 0,
    errors: 0,
  }
  let matchingAssistantText = ''
  let matchingAssistantShape = assistantMessageShape(undefined)
  let matchingAssistantSeen = false
  let terminalClaimed = false
  let playbackStarted = false
  let playbackStartedMs
  let pendingCompletion

  function observe(event) {
    const correlated = isCorrelatedOutputEvent(event, inputEventId)
    if (event?.type === 'output:gen-ai:chat:message') {
      eventStats.assistantMessages++
      if (correlated) {
        eventStats.matchingAssistantMessages++
        if (!isValidMessageEvent(event))
          return correlated
        matchingAssistantSeen = true
        matchingAssistantShape = assistantMessageShape(event?.data?.message)
        const candidate = assistantText(event?.data?.message)
        if (candidate)
          matchingAssistantText = candidate
      }
    }
    else if (event?.type === 'output:gen-ai:chat:complete') {
      eventStats.completions++
      if (correlated)
        eventStats.matchingCompletions++
    }
    else if (event?.type === 'output:gen-ai:chat:cancelled') {
      eventStats.cancellations++
      if (correlated)
        eventStats.matchingCancellations++
    }
    else if (event?.type === 'output:gen-ai:chat:playback-start') {
      eventStats.playbackStarts++
      if (correlated)
        eventStats.matchingPlaybackStarts++
    }
    return correlated
  }

  return {
    eventStats,
    observe,
    completion(event, elapsedMs) {
      const completionText = assistantText(event?.data?.message)
      return {
        elapsedMs,
        assistant: resolveAssistantText(event?.data?.message, matchingAssistantText),
        assistantSource: completionText ? 'completion' : matchingAssistantText ? 'message-event' : 'none',
        assistantShape: resolveAssistantShape(
          event?.data?.message, matchingAssistantShape, matchingAssistantSeen,
        ),
      }
    },
    terminal(event, elapsedMs) {
      if (terminalClaimed || !isCorrelatedOutputEvent(event, inputEventId))
        return undefined
      if (event?.type !== 'output:gen-ai:chat:complete' && event?.type !== 'output:gen-ai:chat:cancelled')
        return undefined
      if (event?.type === 'output:gen-ai:chat:cancelled' && event?.data?.reason !== 'superseded')
        return undefined
      if (event?.type === 'output:gen-ai:chat:complete' && !isValidCompletionEvent(event))
        return undefined

      terminalClaimed = true
      return event.type === 'output:gen-ai:chat:cancelled'
        ? { cancelled: true, elapsedMs }
        : { cancelled: false, ...this.completion(event, elapsedMs) }
    },
    waitTerminal(event, elapsedMs) {
      if (terminalClaimed || !isCorrelatedOutputEvent(event, inputEventId))
        return undefined
      if (event?.type === 'output:gen-ai:chat:cancelled') {
        if (event?.data?.reason !== 'superseded')
          return undefined
        terminalClaimed = true
        return { cancelled: true, elapsedMs }
      }
      if (!isValidCompletionEvent(event))
        return undefined
      if (!playbackStarted) {
        // The first correlated completion is the terminal payload for this
        // request. Replays must not replace it while playback is still
        // pending (otherwise a duplicate can change the assistant payload).
        if (!pendingCompletion)
          pendingCompletion = { event, elapsedMs }
        return undefined
      }
      terminalClaimed = true
      return {
        cancelled: false,
        ...this.completion(event, elapsedMs),
        ...(playbackStarted
          ? { playbackStarted: true, playbackStartedMs }
          : {}),
      }
    },
    waitPlaybackStart(event, elapsedMs) {
      if (event?.type !== 'output:gen-ai:chat:playback-start'
        || !isCorrelatedOutputEvent(event, inputEventId)
        || !isEmptyPlaybackPayload(event?.data)
        || playbackStarted)
        return undefined
      playbackStarted = true
      playbackStartedMs = elapsedMs
      const playback = { playbackStarted: true, playbackStartedMs: elapsedMs }
      if (!pendingCompletion || terminalClaimed)
        return { playback }
      terminalClaimed = true
      return {
        terminal: {
          cancelled: false,
          ...this.completion(pendingCompletion.event, pendingCompletion.elapsedMs),
        },
        playback,
      }
    },
  }
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

export async function loadServerConfig(configPath) {
  const info = await stat(configPath)
  if (!info.isFile() || info.size <= 0 || info.size > MAX_CONFIG_BYTES)
    throw new Error('AIRI server channel config file is invalid.')
  return validateServerConfig(JSON.parse(await readFile(configPath, 'utf8')))
}

function exactDataObject(value, expectedKeys) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
    || ![Object.prototype, null].includes(Object.getPrototypeOf(value)))
    return undefined
  const keys = Reflect.ownKeys(value)
  if (keys.some(key => typeof key !== 'string') || keys.length !== expectedKeys.length
    || expectedKeys.some(key => !keys.includes(key)))
    return undefined
  const copy = Object.create(null)
  for (const key of expectedKeys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key)
    if (!descriptor || !descriptor.enumerable || !('value' in descriptor))
      return undefined
    copy[key] = descriptor.value
  }
  return copy
}

export function validateInputTextEvent(value) {
  const event = exactDataObject(value, ['type', 'data', 'route', 'metadata'])
  const data = exactDataObject(event?.data, ['text'])
  const route = exactDataObject(event?.route, ['delivery'])
  const delivery = exactDataObject(route?.delivery, ['required'])
  const metadata = exactDataObject(event?.metadata, ['event'])
  const metadataEvent = exactDataObject(metadata?.event, ['id'])
  const text = data?.text
  const id = metadataEvent?.id
  if (event?.type !== 'input:text' || delivery?.required !== true
    || typeof text !== 'string' || !Array.from(text).length
    || Array.from(text).length > MAX_EVENT_TEXT_CODEPOINTS || text.includes('\0')
    || typeof id !== 'string' || id.length < 1 || id.length > 256
    || /[\u0000-\u0020\u007f-\u009f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/u.test(id))
    throw new TypeError('AIRI input event must be the exact bounded input:text envelope.')
  return Object.freeze({
    type: 'input:text',
    data: Object.freeze({ text }),
    route: Object.freeze({ delivery: Object.freeze({ required: true }) }),
    metadata: Object.freeze({ event: Object.freeze({ id }) }),
  })
}

export async function sendAiriLocalEvent(inputEvent, {
  configPath,
  sourceRoot,
  serverConfig,
  ClientClass,
  waitComplete = false,
  waitPlaybackStart = false,
  timeoutMs = 90_000,
  settleDelayMs = 300,
  includeAssistant = false,
  includeAssistantShape = false,
  includeWallClockTiming = false,
} = {}) {
  const event = validateInputTextEvent(inputEvent)
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1
    || !Number.isSafeInteger(settleDelayMs) || settleDelayMs < 0)
    throw new TypeError('Sender timing bounds must be non-negative safe integers.')
  const waitForTerminal = waitComplete || waitPlaybackStart
  let normalizedConfig
  if (serverConfig === undefined) {
    const appData = process.env.APPDATA
    if (!configPath && !appData)
      throw new Error('APPDATA is unavailable.')
    const resolvedConfigPath = resolve(configPath
      || process.env.AIRI_SERVER_CHANNEL_CONFIG
      || join(appData, 'ai.moeru.airi', 'server-channel-config.json'))
    normalizedConfig = await loadServerConfig(resolvedConfigPath)
  }
  else {
    normalizedConfig = validateServerConfig(serverConfig)
  }
  const { hostname, token } = normalizedConfig
  let ResolvedClient = ClientClass
  if (!ResolvedClient) {
    const resolvedSourceRoot = resolve(sourceRoot || process.env.AIRI_SOURCE_ROOT || DEFAULT_SOURCE_ROOT)
    const sdkEntry = join(resolvedSourceRoot, 'packages', 'server-sdk', 'dist', 'index.mjs')
    ;({ Client: ResolvedClient } = await import(pathToFileURL(sdkEntry).href))
  }
  if (typeof ResolvedClient !== 'function')
    throw new TypeError('AIRI server SDK Client is unavailable.')

  const inputEventId = event.metadata.event.id
  let tracker = createAssistantEventTracker(inputEventId)
  const client = new ResolvedClient({
    name: 'local-codex-chat-ingress',
    url: `ws://${hostname}:6121/ws`,
    token,
    autoConnect: false,
    autoReconnect: false,
    possibleEvents: CLIENT_POSSIBLE_EVENTS,
    onError: () => { tracker.eventStats.errors++ },
    onAnyMessage: observed => { tracker.observe(observed) },
  })

  let startedAt
  let sentEpochMs
  let completeResolve
  let completeReject
  const completion = new Promise((resolvePromise) => {
    completeResolve = resolvePromise
  })
  let completionTimeout
  const settleTerminal = observed => {
    const terminal = waitPlaybackStart
      ? tracker.waitTerminal(observed, Math.round(performance.now() - startedAt))
      : tracker.terminal(observed, Math.round(performance.now() - startedAt))
    if (terminal)
      completeResolve(terminal)
  }
  const settlePlaybackStart = observed => {
    const outcome = tracker.waitPlaybackStart(observed, Math.round(performance.now() - startedAt))
    if (outcome?.terminal)
      completeResolve({ ...outcome.terminal, ...outcome.playback })
  }
  const unsubscribes = waitForTerminal
    ? [
        client.onEvent('output:gen-ai:chat:complete', settleTerminal),
        client.onEvent('output:gen-ai:chat:cancelled', settleTerminal),
        ...(waitPlaybackStart ? [client.onEvent('output:gen-ai:chat:playback-start', settlePlaybackStart)] : []),
      ]
    : []

  let completed
  try {
    completionTimeout = setTimeout(() => completeReject(new Error(
      `Timed out connecting or waiting for AIRI delivery (assistant_events=${tracker.eventStats.assistantMessages}, matching_assistant_events=${tracker.eventStats.matchingAssistantMessages}, completion_events=${tracker.eventStats.completions}, matching_completion_events=${tracker.eventStats.matchingCompletions}, cancellation_events=${tracker.eventStats.cancellations}, matching_cancellation_events=${tracker.eventStats.matchingCancellations}, playback_start_events=${tracker.eventStats.playbackStarts}, matching_playback_start_events=${tracker.eventStats.matchingPlaybackStarts}, errors=${tracker.eventStats.errors}).`,
    )), timeoutMs)
    const timeout = new Promise((_, rejectPromise) => {
      completeReject = rejectPromise
    })
    await Promise.race([client.connect(), timeout])
    const sendTiming = createSendTiming()
    sentEpochMs = sendTiming.sentEpochMs
    startedAt = sendTiming.startedAt
    client.sendOrThrow(event)
    completed = await Promise.race([
      waitForTerminal
        ? completion
        : new Promise(resolvePromise => setTimeout(resolvePromise, settleDelayMs)),
      timeout,
    ])
  }
  finally {
    if (completionTimeout)
      clearTimeout(completionTimeout)
    for (const unsubscribe of unsubscribes)
      unsubscribe()
    client.close(1000, 'local input sent')
  }

  return Object.freeze({
    sent: true,
    transport: 'loopback-server-channel',
    chars: Array.from(event.data.text).length,
    ...(includeWallClockTiming ? { sent_epoch_ms: sentEpochMs } : {}),
    ...(completed?.cancelled
      ? { cancelled: true, cancel_reason: 'superseded', cancelled_ms: completed.elapsedMs }
      : completed
      ? {
          completed: true,
          completed_ms: completed.elapsedMs,
          ...(completed.playbackStarted
            ? { playback_started: true, playback_started_ms: completed.playbackStartedMs }
            : {}),
          assistant_chars: Array.from(completed.assistant).length,
          ...(includeAssistant ? { assistant: completed.assistant } : {}),
          ...(includeAssistantShape
            ? { assistant_source: completed.assistantSource, assistant_shape: completed.assistantShape }
            : {}),
        }
      : {}),
  })
}

async function main() {
  const args = process.argv.slice(2)
  const text = decodeTextArgument(args)
  const printAssistant = args.includes('--print-assistant')
  const printAssistantShape = args.includes('--print-assistant-shape')
  const printWallClockTiming = args.includes('--print-wall-clock-timing')
  const waitComplete = args.includes('--wait-complete') || printAssistant || printAssistantShape
  const waitPlaybackStart = args.includes('--wait-playback-start')
  const appData = process.env.APPDATA
  if (!appData)
    throw new Error('APPDATA is unavailable.')

  const configPath = resolve(
    process.env.AIRI_SERVER_CHANNEL_CONFIG
      || join(appData, 'ai.moeru.airi', 'server-channel-config.json'),
  )
  const output = await sendAiriLocalEvent(
    buildInputTextEvent(text, randomUUID()),
    {
      configPath,
      sourceRoot: resolve(process.env.AIRI_SOURCE_ROOT || DEFAULT_SOURCE_ROOT),
      waitComplete,
      waitPlaybackStart,
      includeAssistant: printAssistant,
      includeAssistantShape: printAssistantShape,
      includeWallClockTiming: printWallClockTiming,
    },
  )
  process.stdout.write(`${JSON.stringify(output)}\n`)
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href
if (isMain) {
  main().catch((error) => {
    process.stderr.write(`${JSON.stringify({ sent: false, error: error instanceof Error ? error.message : 'unknown error' })}\n`)
    process.exitCode = 1
  })
}
