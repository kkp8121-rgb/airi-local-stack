const BLOCK_MS = 1_200_000
const TOTAL_MS = 7_200_000
const OPENING_MS = 30_000
const DEVELOPMENT_END_MS = 900_000
const PRIORITY = ['question', 'topic_expansion', 'sincere_reaction', 'cheer', 'positive']
const KINDS = new Set(PRIORITY)
const BAD_TEXT = /[\u0000-\u001f\u007f-\u009f\u202a-\u202e\u2066-\u2069\ud800-\udfff]/u

function snapshot(value, keys) {
    try {
        if (value === null || typeof value !== 'object' || ![Object.prototype, null].includes(Object.getPrototypeOf(value)) || Object.getOwnPropertySymbols(value).length) return null
        const names = Object.getOwnPropertyNames(value)
        if (names.length !== keys.length || !keys.every((key) => names.includes(key))) return null
        const copy = {}
        for (const key of keys) {
            const descriptor = Object.getOwnPropertyDescriptor(value, key)
            if (!descriptor || !('value' in descriptor) || !descriptor.enumerable) return null
            copy[key] = descriptor.value
        }
        return copy
    } catch { return null }
}

function normalText(value, maximum) { if (typeof value !== 'string' || BAD_TEXT.test(value)) return null; const normalized = value.normalize('NFC'); return [...normalized].length > 0 && [...normalized].length <= maximum ? normalized : null }
function safeNow(value) { return Number.isSafeInteger(value) && value >= 0 }
function eventId(value) { return typeof value === 'string' && /^yt:v1:[A-Za-z0-9_-]{43}$/.test(value) }
function leaseToken(value) { return typeof value === 'string' && /^[A-Za-z0-9._~-]{1,128}$/.test(value) ? value : null }
function freeze(value) { if (value && typeof value === 'object') { for (const child of Object.values(value)) freeze(child); Object.freeze(value) } return value }
function phase(elapsed) { if (elapsed >= TOTAL_MS) return 'complete'; const local = elapsed % BLOCK_MS; return local < OPENING_MS ? 'opening' : local < DEVELOPMENT_END_MS ? 'development' : 'closing' }

/** A deterministic, default-off state machine. It owns no provider identity or topic body. */
export function createBroadcastDirector(input = {}) {
    let optionNames = []
    try { optionNames = Object.getOwnPropertyNames(input || {}) } catch { return disabled() }
    const option = snapshot(input, optionNames)
    if (!option || option.enabled !== true) return disabled()
    if (!Object.keys(option).every((key) => ['enabled', 'capacity', 'recentCapacity', 'silenceThreshold'].includes(key))) throw new TypeError('unknown option')
    const capacity = option.capacity === undefined ? 128 : option.capacity
    const recentCapacity = option.recentCapacity === undefined ? 4096 : option.recentCapacity
    const silenceThreshold = option.silenceThreshold === undefined ? 60_000 : option.silenceThreshold
    if (!Number.isSafeInteger(capacity) || capacity < 8 || capacity > 4096 || !Number.isSafeInteger(recentCapacity) || recentCapacity < 8 || recentCapacity > 65_536 || !Number.isSafeInteger(silenceThreshold) || silenceThreshold < 30_000 || silenceThreshold > 300_000) throw new RangeError('unsafe limits')

    let state = 'new'; let wall = null; let elapsed = 0; let serial = 0; let lastAudience = 0; let lastSilenceStep = 0; let silence = 0
    let inFlight = null; let cycle = null; const marks = new Set(); const mandatory = []; const regular = []; const acks = []; const reads = []; const seamReads = []; const recent = new Map(); const activeLeases = new Map()
    const chats = new Map(PRIORITY.map((kind) => [kind, []]))
    const queued = () => mandatory.length + regular.length + acks.length + reads.length + seamReads.length + PRIORITY.reduce((n, k) => n + chats.get(k).length, 0)
    const response = (status, extra = {}) => freeze({ status, ...extra })
    const make = (type, extra = {}) => freeze({ actionId: `bd:v1:a${++serial}`, type, ...extra })
    const touch = (id) => { recent.delete(id); recent.set(id, true); while (recent.size > recentCapacity) recent.delete(recent.keys().next().value) }
    const room = (n = 1) => queued() + (inFlight ? 1 : 0) + n <= capacity
    const push = (list, action) => { if (!room()) return false; list.push(action); return true }
    const pushMany = (list, actions) => { if (!room(actions.length)) return false; list.push(...actions); return true }
    const validTime = (now) => safeNow(now) && (wall === null || now >= wall)
    const addMilestones = () => {
        for (let b = 0; b < 6; b += 1) {
            const start = b * BLOCK_MS; const close = start + DEVELOPMENT_END_MS
            if (elapsed >= start && !marks.has(`o${b}`)) { const group = [make('block_opening', { block: b + 1, signature: b === 0 }), make('topic_lease_request', { purpose: 'opening', block: b + 1 })]; if (!pushMany(mandatory, group)) return; marks.add(`o${b}`) }
            if (elapsed >= close && !marks.has(`c${b}`)) { const group = [make('closing', { block: b + 1, final: b === 5 }), ...(b === 5 ? [make('final_qa'), make('thanks'), make('next_broadcast_preview'), make('broadcast_complete')] : [])]; if (!pushMany(mandatory, group)) return; marks.add(`c${b}`) }
        }
    }
    const refresh = () => {
        addMilestones()
        if (state !== 'running') return
        if (cycle?.stage === 'waiting' && (phase(elapsed) !== 'development' || elapsed >= cycle.deadline)) {
            if (phase(elapsed) === 'development' && !PRIORITY.some((kind) => chats.get(kind).length)) { const answer = make('self_answer', { pattern: cycle.pattern }); if (push(regular, answer)) cycle = { stage: 'answering', pattern: cycle.pattern } } else cycle = null
        }
        if (phase(elapsed) !== 'development' && cycle && cycle.block !== Math.floor(elapsed / BLOCK_MS)) cycle = null
        if (!cycle && phase(elapsed) === 'development' && room()) {
            const block = Math.floor(elapsed / BLOCK_MS); const index = [...marks].filter((m) => m.startsWith(`q${block}:`)).length
            const pattern = ['closed', 'closed', 'closed', 'open', 'open'][index % 5]
            cycle = { stage: 'asking', pattern, block }; marks.add(`q${block}:${index}`); push(regular, make('question_ask', { pattern }))
        }
    }
    const advance = (now) => { if (!validTime(now)) return false; if (state === 'running') elapsed += now - wall; wall = now; refresh(); return true }
    const choose = () => {
        if (inFlight || state !== 'running') return inFlight
        let item = mandatory.shift() || acks.shift()
        if (!item) for (const kind of PRIORITY) if (chats.get(kind).length) { item = chats.get(kind).shift(); if (cycle?.stage === 'waiting') cycle = null; break }
        if (!item) item = seamReads.shift()
        if (!item && phase(elapsed) === 'closing') item = reads.shift()
        if (!item) item = regular.shift()
        if (item) inFlight = item
        return item
    }
    const clear = () => { inFlight = null; cycle = null; mandatory.length = regular.length = acks.length = reads.length = seamReads.length = 0; for (const list of chats.values()) list.length = 0; recent.clear(); activeLeases.clear() }
    const releases = () => {
        return freeze([...activeLeases.values()].map((item) => freeze({ ...item })))
    }
    const api = {
        start(now) { if (state !== 'new') return response(state === 'running' ? 'already_started' : state); if (!safeNow(now)) return response('rejected', { reason: 'invalid_time' }); state = 'running'; wall = now; refresh(); return response('started') },
        advance(now) { if (state !== 'running') return response(state); return advance(now) ? response('advanced', { phase: phase(elapsed) }) : response('rejected', { reason: 'invalid_time' }) },
        submitChat(value, classification) {
            if (state !== 'running') return response(state)
            const e = snapshot(value, ['eventId', 'viewerKey', 'displayName', 'text', 'kind', 'publishedAtMs']); const c = snapshot(classification, ['priority'])
            if (!e || !c || !eventId(e.eventId) || typeof e.viewerKey !== 'string' || !/^viewer:v1:[A-Za-z0-9_-]{43}$/.test(e.viewerKey) || !(e.displayName = normalText(e.displayName, 80)) || !(e.text = normalText(e.text, 1000)) || e.kind !== 'text' || !KINDS.has(c.priority) || !safeNow(e.publishedAtMs) || e.publishedAtMs > wall + 30_000) return response('rejected', { reason: 'invalid_event' })
            if (recent.has(e.eventId)) { touch(e.eventId); return response('duplicate') }
            if (!room()) return response('backpressure')
            touch(e.eventId); chats.get(c.priority).push(make('chat_emit', { eventId: e.eventId, displayName: e.displayName, text: e.text, priority: c.priority })); lastAudience = elapsed; lastSilenceStep = elapsed; silence = 0; return response('accepted')
        },
        submitDonation(value) {
            if (state !== 'running') return response(state)
            const e = snapshot(value, ['eventId', 'displayName', 'message', 'publishedAtMs'])
            if (!e || !eventId(e.eventId) || !(e.displayName = normalText(e.displayName, 80)) || !(e.message = normalText(e.message, 280)) || !safeNow(e.publishedAtMs) || e.publishedAtMs > wall + 30_000) return response('rejected', { reason: 'invalid_event' })
            if (recent.has(e.eventId)) { touch(e.eventId); return response('duplicate') }
            if (!room(2)) return response('backpressure')
            touch(e.eventId); acks.push(make('donation_name_callout_request', { eventId: e.eventId, displayName: e.displayName })); reads.push(make('donation_read_request', { eventId: e.eventId, displayName: e.displayName, message: e.message })); lastAudience = elapsed; lastSilenceStep = elapsed; silence = 0; return response('accepted')
        },
        pause(now) { if (state !== 'running') return response(state); if (!advance(now)) return response('rejected', { reason: 'invalid_time' }); state = 'paused'; return response('paused') },
        resume(now) { if (state !== 'paused') return response(state); if (!validTime(now)) return response('rejected', { reason: 'invalid_time' }); wall = now; state = 'running'; return response('running') },
        nextAction(now) { if (state !== 'running') return response(state); if (!advance(now)) return response('rejected', { reason: 'invalid_time' }); return choose() || response('idle') },
        complete(value, now) {
            if (state !== 'running') return response(state)
            const c = snapshot(value, ['actionId', 'outcome']); if (!c || typeof c.actionId !== 'string' || !['ok', 'failed'].includes(c.outcome) || !inFlight || c.actionId !== inFlight.actionId) return response('rejected', { reason: 'stale_action' })
            if (inFlight.type === 'topic_lease_request') return response('rejected', { reason: 'requires_lease_resolution' })
            if (!advance(now)) return response('rejected', { reason: 'invalid_time' })
            const done = inFlight; inFlight = null
            if (done.type === 'topic_lease_complete' && c.outcome === 'failed') { inFlight = done; return response('delivery_failed') }
            if (done.type === 'question_ask' && c.outcome === 'ok') cycle = { stage: 'waiting', pattern: done.pattern, block: Math.floor(elapsed / BLOCK_MS), deadline: elapsed + 12_000 }
            else if (done.type === 'question_ask') cycle = null
            if (done.type === 'self_answer') cycle = null
            if (done.type === 'donation_read_request') push(regular, make('donation_reaction_request', { eventId: done.eventId, displayName: done.displayName }))
            if (done.type === 'topic_speech_request') { const lease = activeLeases.get(done.leaseToken); if (lease) lease.delivered = c.outcome === 'ok'; push(regular, make('topic_lease_complete', { leaseToken: done.leaseToken, delivered: c.outcome === 'ok', purpose: done.purpose, ...(done.block ? { block: done.block } : {}) })) }
            if (done.type === 'topic_lease_complete') activeLeases.delete(done.leaseToken)
            if (done.type === 'broadcast_complete') { const leaseReleases = releases(); clear(); state = c.outcome === 'ok' ? 'completed' : 'failed'; return response(state, { leaseReleases }) }
            refresh(); return response('completed')
        },
        requestSeam(now) { if (state !== 'running') return response(state); if (!advance(now)) return response('rejected', { reason: 'invalid_time' }); while (reads.length) seamReads.push(reads.shift()); return response('seam_open') },
        noteSilence(now) { if (state !== 'running') return response(state); if (!advance(now)) return response('rejected', { reason: 'invalid_time' }); if (elapsed - lastAudience < silenceThreshold || elapsed - lastSilenceStep < silenceThreshold) return response('not_due'); const type = ['narration_what_how_why', 'topic_lease_request', 'binary_question'][Math.min(silence, 2)]; if (!push(regular, make(type, type === 'topic_lease_request' ? { purpose: 'backup' } : {}))) return response('backpressure'); silence += 1; lastSilenceStep = elapsed; return response('scheduled') },
        resolveLease(value, now) {
            if (state !== 'running') return response(state)
            const r = snapshot(value, ['actionId', 'approved', 'leaseToken']); if (!r || !inFlight || inFlight.type !== 'topic_lease_request' || r.actionId !== inFlight.actionId || typeof r.approved !== 'boolean' || (r.approved && !leaseToken(r.leaseToken))) return response('rejected', { reason: 'stale_action' })
            if (r.approved && activeLeases.has(r.leaseToken)) return response('rejected', { reason: 'active_lease_token' })
            if (!advance(now)) return response('rejected', { reason: 'invalid_time' })
            const lease = inFlight; inFlight = null; const extra = { purpose: lease.purpose, ...(lease.block ? { block: lease.block } : {}) }; if (r.approved) { activeLeases.set(r.leaseToken, { leaseToken: r.leaseToken, ...extra, delivered: false }); push(regular, make('topic_speech_request', { ...extra, leaseToken: r.leaseToken })) } else push(regular, make('topic_lease_complete', { ...extra, delivered: false })); return response('resolved')
        },
        kill() { if (state === 'closed') return response('closed'); const leaseReleases = releases(); clear(); state = 'killed'; return response('killed', { leaseReleases }) },
        close() { if (state === 'killed') return response('killed'); const leaseReleases = releases(); clear(); state = 'closed'; return response('closed', { leaseReleases }) },
        stats() { return freeze({ status: state, phase: state === 'running' || state === 'paused' ? phase(elapsed) : state, elapsedMs: elapsed, queued: queued(), inFlight: inFlight ? 1 : 0, chatQueued: PRIORITY.reduce((n, k) => n + chats.get(k).length, 0), donationQueued: acks.length + reads.length + seamReads.length, mandatoryQueued: mandatory.length, regularQueued: regular.length, dedupeSize: recent.size, activeLeaseCount: activeLeases.size }) }
    }
    return freeze(api)
}

function disabled() { const f = () => freeze({ status: 'disabled' }); return freeze({ start: f, advance: f, submitChat: f, submitDonation: f, pause: f, resume: f, complete: f, nextAction: f, requestSeam: f, noteSilence: f, resolveLease: f, kill: f, close: f, stats: () => freeze({ status: 'disabled', queued: 0, inFlight: 0 }) }) }
export const BROADCAST_SCHEDULE = freeze({ blocks: 6, blockMs: BLOCK_MS, openingMs: OPENING_MS, developmentEndMs: DEVELOPMENT_END_MS, totalMs: TOTAL_MS })
