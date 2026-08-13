import { sendAiriLocalEvent } from '../send-airi-local-text.mjs'
import { toAiriEvent } from './airi-event.mjs'
import { parseChatIngressConfig } from './config.mjs'
import { createChatIngress } from './core.mjs'
import { createProxyScreen } from './proxy-screen.mjs'

export function createLocalChatIngressRuntime({
  config = parseChatIngressConfig(),
  screen,
  deliverEvent = sendAiriLocalEvent,
  senderOptions,
  now,
} = {}) {
  if (!config || typeof config !== 'object' || Array.isArray(config))
    throw new TypeError('Chat ingress runtime config is required.')
  if (typeof deliverEvent !== 'function')
    throw new TypeError('Chat ingress runtime delivery function is required.')
  const enabled = config.enabled === true
  const ingress = createChatIngress({
    enabled,
    identityKey: config.identityKey,
    capacity: config.capacity,
    recentCapacity: config.recentCapacity,
    ...(now ? { now } : {}),
    ...(enabled ? { screen: screen || createProxyScreen() } : {}),
  })
  let closed = false
  return Object.freeze({
    submit(candidate) { return ingress.submit(candidate) },
    flush() {
      return ingress.flush(async event => {
        if (closed)
          throw new Error('chat ingress runtime is closed')
        await deliverEvent(toAiriEvent(event), senderOptions)
      })
    },
    stats() { return Object.freeze({ ...ingress.stats() }) },
    close() { closed = true; ingress.close() },
  })
}
