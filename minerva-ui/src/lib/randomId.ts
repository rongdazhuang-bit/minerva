let fallbackSeq = 0

/**
 * Generate a unique string id (``crypto.randomUUID`` when available, else time + random).
 * Use where HTTP or older browsers lack ``randomUUID`` (e.g. Mermaid render targets).
 */
export function randomId(): string {
  const c = globalThis.crypto
  if (c != null && typeof c.randomUUID === 'function') {
    return c.randomUUID()
  }
  fallbackSeq += 1
  return `${Date.now().toString(36)}-${fallbackSeq.toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}
