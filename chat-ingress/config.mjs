export const DEFAULT_CHAT_INGRESS_CONFIG = Object.freeze({
  enabled: false,
  capacity: 64,
  recentCapacity: 4096,
})

export function parseChatIngressConfig(env = process.env) {
  const enabled = env.AIRI_CHAT_INGRESS === 'on'
  return {
    ...DEFAULT_CHAT_INGRESS_CONFIG,
    enabled,
    identityKey: enabled ? env.AIRI_CHAT_INGRESS_IDENTITY_KEY : undefined,
  }
}
