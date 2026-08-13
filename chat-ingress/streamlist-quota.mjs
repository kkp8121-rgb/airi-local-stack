/**
 * Offline-only measurement core for a future, caller-owned streamList transport.
 * It deliberately knows nothing about credentials, endpoints, or provider objects.
 */

const MAX_DURATION_MS = 3_600_000
const MAX_MESSAGES = 200_000
const MAX_RESPONSES = 20_000
const MAX_CONNECTIONS = 1_000
const MAX_PAGE_TOKEN_LENGTH = 512
const MAX_CLEANUP_MS = 1_000
const KINDS = ['idle', 'message', 'reconnect']
const STATUSES = ['completed', 'failed', 'aborted']
const STOP_REASONS = ['normal_close', 'duration_cap', 'message_cap', 'response_cap', 'connection_cap', 'offline', 'aborted', 'open_failure', 'read_failure', 'invalid_summary']
const QUOTA_SOURCE = 'manual_google_cloud_console_snapshot'
const TIMEOUT = Object.freeze(Object.create(null))
const ABORTED = Object.freeze(Object.create(null))

// Module-private brand. The class stays exported so a caller can catch by type,
// but only errors this module itself raised are ever allowed to propagate; a
// provider-constructed StreamListQuotaError carries provider content and is
// sanitized like any other transport failure.
const INTERNAL = new WeakSet()

export class StreamListQuotaError extends Error {
  constructor(code) {
    super('streamList quota probe failed')
    this.name = 'StreamListQuotaError'
    this.code = code
  }
}

function fail(code) {
  const error = new StreamListQuotaError(code)
  INTERNAL.add(error)
  throw error
}

function isInternal(error) {
  return INTERNAL.has(error)
}

function snapshotExact(record, keys) {
  try {
    if (record === null || typeof record !== 'object' || Object.getPrototypeOf(record) !== Object.prototype) return false
    const names = Object.getOwnPropertyNames(record)
    const symbols = Object.getOwnPropertySymbols(record)
    if (symbols.length !== 0 || names.length !== keys.length || !keys.every((key) => names.includes(key))) return false
    const values = {}
    for (const key of names) {
      const descriptor = Object.getOwnPropertyDescriptor(record, key)
      if (!descriptor || !('value' in descriptor) || !descriptor.enumerable) return false
      values[key] = descriptor.value
    }
    return values
  } catch {
    return false
  }
}

function safeInteger(value, minimum, maximum) {
  return Number.isSafeInteger(value) && value >= minimum && value <= maximum
}

function boundedString(value, maximum) {
  return typeof value === 'string' && value.length <= maximum
}

function deepFreeze(value) {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    for (const child of Object.values(value)) deepFreeze(child)
    Object.freeze(value)
  }
  return value
}

function configValue(config, key, fallback, minimum, maximum) {
  if (!(key in config)) return fallback
  const value = config[key]
  if (!safeInteger(value, minimum, maximum)) fail('invalid_options')
  return value
}

function parseOptions(options) {
  try {
    const allowed = ['kind', 'durationMs', 'maxMessages', 'maxResponses', 'maxConnections', 'openStream', 'now', 'setTimeout', 'clearTimeout', 'signal']
    const snapshot = snapshotExact(options, Object.getOwnPropertyNames(options))
    if (!snapshot || !Object.keys(snapshot).every((key) => allowed.includes(key))) fail('invalid_options')
    const { kind, openStream } = snapshot
    if (!KINDS.includes(kind) || typeof openStream !== 'function') fail('invalid_options')
    const now = snapshot.now === undefined ? () => Math.floor(globalThis.performance.now()) : snapshot.now
    const setTimeoutFn = snapshot.setTimeout === undefined ? globalThis.setTimeout : snapshot.setTimeout
    const clearTimeoutFn = snapshot.clearTimeout === undefined ? globalThis.clearTimeout : snapshot.clearTimeout
    if (typeof now !== 'function' || typeof setTimeoutFn !== 'function' || typeof clearTimeoutFn !== 'function') fail('invalid_options')
    if (snapshot.signal !== undefined && !(snapshot.signal instanceof AbortSignal)) fail('invalid_options')
    return {
      kind,
      openStream,
      now,
      setTimeoutFn,
      clearTimeoutFn,
      signal: snapshot.signal,
      durationMs: configValue(snapshot, 'durationMs', 60_000, 0, MAX_DURATION_MS),
      maxMessages: configValue(snapshot, 'maxMessages', 1_000, 0, MAX_MESSAGES),
      maxResponses: configValue(snapshot, 'maxResponses', 1_000, 0, MAX_RESPONSES),
      maxConnections: configValue(snapshot, 'maxConnections', 1, 1, MAX_CONNECTIONS)
    }
  } catch (error) {
    if (isInternal(error)) throw error
    fail('invalid_options')
  }
}

function summarize(response) {
  const snapshot = snapshotExact(response, ['messageCount', 'nextPageToken', 'offline'])
  if (!snapshot || !safeInteger(snapshot.messageCount, 0, 2_000) || typeof snapshot.offline !== 'boolean') fail('invalid_summary')
  if (snapshot.nextPageToken !== null && (!boundedString(snapshot.nextPageToken, MAX_PAGE_TOKEN_LENGTH) || snapshot.nextPageToken.length === 0)) fail('invalid_summary')
  return snapshot
}

function readClock(now, start, previous) {
  let value
  try { value = now() } catch { fail('invalid_clock') }
  if (!safeInteger(value, start, Number.MAX_SAFE_INTEGER) || value < previous) fail('invalid_clock')
  return value
}

function trialResult(kind, status, stopReason, elapsed, counts, cap) {
  return deepFreeze({
    schema: 'airi.streamlist-quota-trial.v1',
    kind,
    status,
    stopReason,
    durationMs: Math.min(elapsed, cap),
    messages: counts.messages,
    responses: counts.responses,
    discardedResponses: counts.discardedResponses,
    connections: counts.connections,
    resumes: counts.resumes,
    firstResponseMs: counts.firstResponseMs,
    firstMessageMs: counts.firstMessageMs
  })
}

function closeIterator(iterator, config) {
  try {
    const returnFn = iterator && iterator.return
    if (typeof returnFn !== 'function') return
    const cleanup = Promise.resolve().then(() => returnFn.call(iterator)).catch(() => {})
    let timer = null
    const timeout = new Promise((resolve) => {
      try { timer = config.setTimeoutFn(resolve, MAX_CLEANUP_MS) } catch { resolve() }
    })
    void Promise.race([cleanup, timeout]).catch(() => {}).finally(() => {
      try { if (timer !== null && timer !== undefined) config.clearTimeoutFn(timer) } catch { /* ignored */ }
    })
  } catch {
    // Cleanup is best effort; provider failures are intentionally never exposed.
  }
}

function closeStream(stream, config, state) {
  if (state.closed) return
  state.closed = true
  try {
    const getIterator = stream && stream[Symbol.asyncIterator]
    if (typeof getIterator === 'function') closeIterator(getIterator.call(stream), config)
  } catch {
    // Late provider shapes and cleanup errors are intentionally ignored.
  }
}

function abortRace(signal) {
  let remove = null
  const promise = new Promise((resolve) => {
    try {
      if (!signal) return
      if (signal.aborted) { resolve(ABORTED); return }
      if (typeof signal.addEventListener !== 'function') return
      const handler = () => resolve(ABORTED)
      signal.addEventListener('abort', handler, { once: true })
      remove = () => signal.removeEventListener?.('abort', handler)
    } catch { resolve(ABORTED) }
  })
  return { promise, remove: () => { try { remove?.() } catch { /* ignored */ } } }
}

/** Run one bounded, injected-transport trial.  Transport failures are sanitized into stop reasons. */
export async function runStreamListTrial(options) {
  const config = parseOptions(options)
  let start
  try { start = config.now() } catch { fail('invalid_clock') }
  if (!safeInteger(start, 0, Number.MAX_SAFE_INTEGER)) fail('invalid_clock')
  let previousClock = start
  const elapsed = () => { previousClock = readClock(config.now, start, previousClock); return previousClock - start }
  const counts = { messages: 0, responses: 0, discardedResponses: 0, connections: 0, resumes: 0, firstResponseMs: null, firstMessageMs: null }
  if (config.durationMs === 0) return trialResult(config.kind, 'completed', 'duration_cap', 0, counts, config.durationMs)
  if (config.maxMessages === 0) return trialResult(config.kind, 'completed', 'message_cap', 0, counts, config.durationMs)
  if (config.maxResponses === 0) return trialResult(config.kind, 'completed', 'response_cap', 0, counts, config.durationMs)
  let pageToken = null
  let iterator = null
  const localController = new AbortController()
  const abortLocal = () => { try { localController.abort() } catch { /* ignored */ } }
  let status = 'completed'
  let stopReason = 'normal_close'
  try {
    while (counts.connections < config.maxConnections) {
      // Every round starts from a natural close. Only an explicit cap, failure,
      // or abort below may name a stop reason, and each of those breaks out.
      stopReason = 'normal_close'
      try { if (config.signal && config.signal.aborted) { status = 'aborted'; stopReason = 'aborted'; break } } catch { status = 'failed'; stopReason = 'read_failure'; break }
      let stream
      const streamCleanup = { closed: false }
      const openingAbort = abortRace(config.signal)
      let openTimer = null
      let openingTimedOut = false
      try {
        // pageToken is transient reconnect state. It is never retained in a result.
        const remaining = config.durationMs - elapsed()
        const deadline = new Promise((resolve) => {
          try { openTimer = config.setTimeoutFn(() => { openingTimedOut = true; abortLocal(); resolve(TIMEOUT) }, remaining) } catch { openingTimedOut = true; abortLocal(); resolve(TIMEOUT) }
        })
        const opening = Promise.resolve().then(() => config.openStream(Object.freeze({ kind: config.kind, pageToken, signal: localController.signal })))
        // Keep a late provider rejection observed; a late stream is immediately best-effort closed.
        void opening.then((late) => {
          try {
            if (openingTimedOut || localController.signal.aborted) closeStream(late, config, streamCleanup)
          } catch { /* late provider shapes are ignored */ }
        }, () => {})
        const opened = await Promise.race([opening, deadline, openingAbort.promise])
        if (opened === ABORTED) { status = 'aborted'; stopReason = 'aborted'; abortLocal(); break }
        if (opened === TIMEOUT) { stopReason = 'duration_cap'; break }
        stream = opened
        // A returned stream is a connection the provider already served, so it
        // is counted here rather than after the shape checks below. Anything
        // discarded past this point still consumed live quota.
        counts.connections += 1
        if (pageToken !== null) counts.resumes += 1
        if (elapsed() >= config.durationMs) { abortLocal(); closeStream(stream, config, streamCleanup); stopReason = 'duration_cap'; break }
      } catch (error) {
        if (isInternal(error)) throw error
        status = 'failed'; stopReason = 'open_failure'; break
      } finally {
        try { if (openTimer !== null && openTimer !== undefined) config.clearTimeoutFn(openTimer) } catch { /* ignored */ }
        openingAbort.remove()
      }
      let asyncIterator
      try { asyncIterator = stream && stream[Symbol.asyncIterator] } catch { status = 'failed'; stopReason = 'open_failure'; break }
      if (typeof asyncIterator !== 'function') { status = 'failed'; stopReason = 'open_failure'; break }
      try { iterator = asyncIterator.call(stream) } catch { status = 'failed'; stopReason = 'open_failure'; break }
      try { if (!iterator || typeof iterator.next !== 'function') { status = 'failed'; stopReason = 'open_failure'; break } } catch { status = 'failed'; stopReason = 'open_failure'; break }
      let reconnect = false
      while (true) {
        try { if (config.signal && config.signal.aborted) { status = 'aborted'; stopReason = 'aborted'; break } } catch { status = 'failed'; stopReason = 'read_failure'; break }
        const elapsedMs = elapsed()
        if (elapsedMs >= config.durationMs) { stopReason = 'duration_cap'; break }
        let timer = null
        let timedOut = false
        const remaining = config.durationMs - elapsedMs
        const timeout = new Promise((resolve) => {
          try { timer = config.setTimeoutFn(() => { timedOut = true; abortLocal(); resolve(TIMEOUT) }, remaining) } catch { abortLocal(); resolve(TIMEOUT) }
        })
        const readAbort = abortRace(config.signal)
        let step
        try { step = await Promise.race([Promise.resolve(iterator.next()), timeout, readAbort.promise]) } catch (error) {
          if (isInternal(error)) throw error
          status = 'failed'; stopReason = 'read_failure'; break
        }
        finally {
          try { if (timer !== null && timer !== undefined) config.clearTimeoutFn(timer) } catch { /* cleanup failure is sanitized */ }
          readAbort.remove()
        }
        if (step === ABORTED) { status = 'aborted'; stopReason = 'aborted'; abortLocal(); break }
        if (timedOut || step === TIMEOUT) { stopReason = 'duration_cap'; break }
        const stepSnapshot = snapshotExact(step, ['done', 'value'])
        if (!stepSnapshot || typeof stepSnapshot.done !== 'boolean') { status = 'failed'; stopReason = 'read_failure'; break }
        if (stepSnapshot.done) break
        let response
        // Summarizing only ever rejects the provider's own batch shape, so no
        // failure from it is allowed to reach the caller unsanitized.
        try { response = summarize(stepSnapshot.value) } catch { status = 'failed'; stopReason = 'invalid_summary'; break }
        const responseMs = elapsed()
        // The batch arrived and was already paid for upstream, so it is
        // recorded separately instead of vanishing from the measurement.
        if (responseMs >= config.durationMs) { counts.discardedResponses += 1; stopReason = 'duration_cap'; break }
        counts.responses += 1
        if (counts.firstResponseMs === null) counts.firstResponseMs = responseMs
        if (response.messageCount > 0 && counts.firstMessageMs === null) counts.firstMessageMs = responseMs
        if (response.messageCount > config.maxMessages - counts.messages) {
          counts.messages += response.messageCount
          stopReason = 'message_cap'
          break
        }
        counts.messages += response.messageCount
        if (response.offline) { stopReason = 'offline'; break }
        if (counts.responses >= config.maxResponses) { stopReason = 'response_cap'; break }
        if (counts.messages >= config.maxMessages) { stopReason = 'message_cap'; break }
        if (config.kind === 'reconnect' && response.nextPageToken !== null) {
          pageToken = response.nextPageToken
          reconnect = true
          break
        }
      }
      closeIterator(iterator, config)
      iterator = null
      // Reconnect intent is a local flag, never a stop reason: naming it would
      // leave a value that is not a stop reason behind for the next round.
      if (status !== 'completed' || !reconnect) break
      if (counts.connections >= config.maxConnections) { stopReason = 'connection_cap'; break }
    }
    // A natural close is not a cap at any configured connection count.
  } finally {
    abortLocal()
    closeIterator(iterator, config)
  }
  return trialResult(config.kind, status, stopReason, elapsed(), counts, config.durationMs)
}

function quotaNumber(value) {
  if (!safeInteger(value, 0, Number.MAX_SAFE_INTEGER)) fail('invalid_quota')
  return value
}

/** Assemble a content-free report from manual Cloud Console before/after snapshots. */
export function assembleQuotaReport(input) {
  const inputSnapshot = snapshotExact(input, ['trial', 'quotaBefore', 'quotaAfter', 'quotaSource'])
  if (!inputSnapshot) fail('invalid_report_input')
  const { trial, quotaBefore, quotaAfter, quotaSource } = inputSnapshot
  const trialSnapshot = snapshotExact(trial, ['schema', 'kind', 'status', 'stopReason', 'durationMs', 'messages', 'responses', 'discardedResponses', 'connections', 'resumes', 'firstResponseMs', 'firstMessageMs'])
  if (!trialSnapshot || trialSnapshot.schema !== 'airi.streamlist-quota-trial.v1') fail('invalid_report_input')
  for (const key of ['durationMs', 'messages', 'responses', 'discardedResponses', 'connections', 'resumes']) quotaNumber(trialSnapshot[key])
  // At most one already-received batch can be discarded per connection, so the
  // served-response denominator is responses plus discardedResponses.
  if (trialSnapshot.durationMs > MAX_DURATION_MS || trialSnapshot.messages > MAX_MESSAGES + 1_999 || trialSnapshot.responses > MAX_RESPONSES || trialSnapshot.discardedResponses > trialSnapshot.connections || trialSnapshot.connections > MAX_CONNECTIONS || trialSnapshot.resumes > Math.max(0, trialSnapshot.connections - 1) || trialSnapshot.messages > trialSnapshot.responses * 2_000) fail('invalid_report_input')
  for (const key of ['firstResponseMs', 'firstMessageMs']) {
    const value = trialSnapshot[key]
    if (value !== null && (!safeInteger(value, 0, trialSnapshot.durationMs))) fail('invalid_report_input')
  }
  if ((trialSnapshot.responses > 0) !== (trialSnapshot.firstResponseMs !== null) || (trialSnapshot.messages > 0) !== (trialSnapshot.firstMessageMs !== null) || (trialSnapshot.messages > 0 && (trialSnapshot.responses === 0 || trialSnapshot.connections === 0)) || (trialSnapshot.responses > 0 && trialSnapshot.connections === 0) || (trialSnapshot.firstMessageMs !== null && (trialSnapshot.firstResponseMs === null || trialSnapshot.firstMessageMs < trialSnapshot.firstResponseMs))) fail('invalid_report_input')
  if (!KINDS.includes(trialSnapshot.kind) || !STATUSES.includes(trialSnapshot.status) || !STOP_REASONS.includes(trialSnapshot.stopReason)) fail('invalid_report_input')
  if ((trialSnapshot.kind !== 'reconnect' && (trialSnapshot.connections > 1 || trialSnapshot.resumes !== 0)) || (trialSnapshot.stopReason === 'aborted') !== (trialSnapshot.status === 'aborted') || (['open_failure', 'read_failure', 'invalid_summary'].includes(trialSnapshot.stopReason) && trialSnapshot.status !== 'failed') || (trialSnapshot.status === 'failed' && !['open_failure', 'read_failure', 'invalid_summary'].includes(trialSnapshot.stopReason)) || (trialSnapshot.status === 'completed' && !['normal_close', 'duration_cap', 'message_cap', 'response_cap', 'connection_cap', 'offline'].includes(trialSnapshot.stopReason)) || (trialSnapshot.stopReason === 'connection_cap' && (trialSnapshot.kind !== 'reconnect' || trialSnapshot.status !== 'completed'))) fail('invalid_report_input')
  if ((trialSnapshot.stopReason === 'normal_close' && trialSnapshot.connections < 1) || (trialSnapshot.stopReason === 'offline' && (trialSnapshot.responses < 1 || trialSnapshot.connections < 1))) fail('invalid_report_input')
  const before = quotaNumber(quotaBefore)
  const after = quotaNumber(quotaAfter)
  if (after < before || quotaSource !== QUOTA_SOURCE) fail('invalid_quota')
  return deepFreeze({
    schema: 'airi.streamlist-quota-report.v1',
    method: 'streamList',
    kind: trialSnapshot.kind,
    status: trialSnapshot.status,
    stopReason: trialSnapshot.stopReason,
    durationMs: trialSnapshot.durationMs,
    messages: trialSnapshot.messages,
    responses: trialSnapshot.responses,
    discardedResponses: trialSnapshot.discardedResponses,
    connections: trialSnapshot.connections,
    resumes: trialSnapshot.resumes,
    firstResponseMs: trialSnapshot.firstResponseMs,
    firstMessageMs: trialSnapshot.firstMessageMs,
    quotaBefore: before,
    quotaAfter: after,
    quotaDelta: after - before,
    quotaSource
  })
}

export const createQuotaReport = assembleQuotaReport
