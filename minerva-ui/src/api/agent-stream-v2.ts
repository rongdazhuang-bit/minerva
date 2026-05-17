/**
 * Agent SSE v2 event types and line parser.
 */

export const AGENT_SSE_SCHEMA_VERSION = 2 as const

export type AgentSseEventV2 = {
  v: typeof AGENT_SSE_SCHEMA_VERSION
  type: string
  run_id: string
  session_id?: string | null
  ts: string
  payload: Record<string, unknown>
}

export type AgentStreamV2ParseResult =
  | { kind: 'event'; event: AgentSseEventV2 }
  | { kind: 'done' }
  | { kind: 'error'; code: string; message: string }

/** Type guard for v2 SSE JSON payloads. */
export function isAgentSseEventV2(value: unknown): value is AgentSseEventV2 {
  if (!value || typeof value !== 'object') return false
  const o = value as Record<string, unknown>
  return o.v === AGENT_SSE_SCHEMA_VERSION && typeof o.type === 'string' && typeof o.run_id === 'string'
}

/**
 * Parse one SSE ``data:`` payload (without prefix).
 * Returns ``null`` for empty lines.
 */
export function parseAgentV2SseLine(raw: string): AgentStreamV2ParseResult | null {
  const trimmed = raw.trim()
  if (!trimmed) return null
  if (trimmed === '[DONE]') return { kind: 'done' }
  try {
    const j = JSON.parse(trimmed) as unknown
    if (isAgentSseEventV2(j)) return { kind: 'event', event: j }
    const err = j as { payload?: { code?: string; message?: string } }
    if (j && typeof j === 'object' && (j as { type?: string }).type === 'run.error') {
      const p = err.payload ?? {}
      return {
        kind: 'error',
        code: String(p.code ?? 'error'),
        message: String(p.message ?? ''),
      }
    }
  } catch {
    return null
  }
  return null
}

/** Format one v2 event as a single process-log line for the UI. */
export function formatAgentV2TraceLine(event: AgentSseEventV2): string {
  const p = event.payload
  switch (event.type) {
    case 'plan.created': {
      const steps = (p.steps as unknown[]) ?? []
      return `[plan] ${steps.length} step(s)`
    }
    case 'plan.step_updated':
      return `[step] ${String(p.step_id ?? '')} ${String(p.status ?? '')} (${String(p.skill_id ?? '')})`
    case 'subagent.started':
      return `[subagent] start ${String(p.skill_id ?? '')}`
    case 'subagent.finished':
      return `[subagent] end ${String(p.skill_id ?? '')} ${String(p.status ?? '')}`
    case 'tool.started':
      return `[tool] ${String(p.name ?? '')} …`
    case 'tool.finished':
      return `[tool] ${String(p.name ?? '')} done`
    case 'memory.retrieved':
      return `[memory] hits=${String(p.hit_count ?? 0)}`
    case 'run.started':
      return '[run] started'
    case 'run.finished':
      return `[run] finished ${String(p.status ?? '')}`
    case 'run.error':
      return `[run.error] ${String(p.code ?? '')}: ${String(p.message ?? '')}`
    case 'llm.delta':
      return ''
    default:
      return `[${event.type}]`
  }
}
