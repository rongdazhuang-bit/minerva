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

/** OpenAI chat completion ``usage`` object (subset used by Minerva). */
export type OpenAIUsage = {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

/** Parse unknown payload fields into OpenAI-shaped usage, or null when invalid. */
export function parseOpenAIUsage(raw: unknown): OpenAIUsage | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  const prompt = coerceTokenCount(o.prompt_tokens ?? o.input_tokens)
  const completion = coerceTokenCount(o.completion_tokens ?? o.output_tokens)
  const total = coerceTokenCount(o.total_tokens)
  if (prompt == null && completion == null && total == null) return null
  const usage: Partial<OpenAIUsage> = {}
  if (prompt != null) usage.prompt_tokens = prompt
  if (completion != null) usage.completion_tokens = completion
  if (total != null) {
    usage.total_tokens = total
  } else if (prompt != null && completion != null) {
    usage.total_tokens = prompt + completion
  }
  if (
    usage.prompt_tokens == null ||
    usage.completion_tokens == null ||
    usage.total_tokens == null
  ) {
    return null
  }
  return usage as OpenAIUsage
}

/** Extract total token count from a usage object when only partial keys exist. */
export function extractTotalTokens(raw: unknown): number | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  const total = coerceTokenCount(o.total_tokens)
  if (total != null) return total
  const prompt = coerceTokenCount(o.prompt_tokens ?? o.input_tokens)
  const completion = coerceTokenCount(o.completion_tokens ?? o.output_tokens)
  if (prompt != null && completion != null) return prompt + completion
  return prompt ?? completion
}

/** Extract ``details.reasoning_tokens`` (or top-level) from a usage payload. */
export function extractReasoningTokens(raw: unknown): number | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  const direct = coerceTokenCount(o.reasoning_tokens)
  if (direct != null && direct > 0) return direct
  const details = o.details
  if (details && typeof details === 'object') {
    const nested = coerceTokenCount((details as Record<string, unknown>).reasoning_tokens)
    if (nested != null && nested > 0) return nested
  }
  return null
}

/**
 * Compact token count for UI: ``k`` (千), ``w`` (万), ``kw`` (千万).
 * Values below 1000 show the raw integer.
 */
export function formatTokenCount(count: number): string {
  const n = Math.trunc(count)
  if (!Number.isFinite(n) || n <= 0) return '0'
  if (n < 1_000) return String(n)

  const scaled = (value: number, suffix: string): string => {
    let text: string
    if (value >= 100) {
      text = String(Math.round(value))
    } else {
      const rounded = Math.round(value * 10) / 10
      text = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1).replace(/\.0$/, '')
    }
    return `${text}${suffix}`
  }

  if (n >= 10_000_000) return scaled(n / 10_000_000, 'kw')
  if (n >= 10_000) return scaled(n / 10_000, 'w')
  return scaled(n / 1_000, 'k')
}

/** Full token count with locale thousand separators (for trace / detail logs). */
export function formatTokenNumber(count: number, locale?: string): string {
  const n = Math.trunc(count)
  if (!Number.isFinite(n)) return '0'
  return new Intl.NumberFormat(locale).format(n)
}

/** Format usage for process-log display (original keys, grouped numbers). */
export function formatOpenAIUsageForTrace(usage: OpenAIUsage, locale?: string): string {
  const fmt = (value: number) => formatTokenNumber(value, locale)
  return `{prompt_tokens: ${fmt(usage.prompt_tokens)}, completion_tokens: ${fmt(usage.completion_tokens)}, total_tokens: ${fmt(usage.total_tokens)}}`
}

/** Serialize usage as compact OpenAI JSON (stable key order). */
export function formatOpenAIUsageJson(usage: OpenAIUsage): string {
  return JSON.stringify({
    prompt_tokens: usage.prompt_tokens,
    completion_tokens: usage.completion_tokens,
    total_tokens: usage.total_tokens,
  })
}

function coerceTokenCount(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return null
  return Math.trunc(value)
}

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

const SQL_QUERY_ARG_PATTERN = /['"]?(?:querySql|query_sql|sql)['"]?\s*:/i

/** Keep MCP SQL tool arguments intact in the process log; other tools stay clipped. */
function shouldShowFullToolArgumentsPreview(argsPreview: string): boolean {
  return SQL_QUERY_ARG_PATTERN.test(argsPreview)
}

/** Format one v2 event as a single process-log line for the UI. */
export function formatAgentV2TraceLine(event: AgentSseEventV2, locale?: string): string {
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
    case 'tool.started': {
      const argsPreview = String(p.arguments_preview ?? '').trim()
      if (argsPreview) {
        const clipped =
          shouldShowFullToolArgumentsPreview(argsPreview) || argsPreview.length <= 120
            ? argsPreview
            : `${argsPreview.slice(0, 120)}…`
        return `[tool] ${String(p.name ?? '')} … ${clipped}`
      }
      return `[tool] ${String(p.name ?? '')} …`
    }
    case 'tool.finished': {
      const resultPreview = String(p.result_preview ?? '').trim()
      if (resultPreview) {
        const clipped =
          resultPreview.length > 200 ? `${resultPreview.slice(0, 200)}…` : resultPreview
        return `[tool] ${String(p.name ?? '')} done → ${clipped}`
      }
      return `[tool] ${String(p.name ?? '')} done`
    }
    case 'memory.retrieved':
      return `[memory] hits=${String(p.hit_count ?? 0)}`
    case 'run.started':
      return '[run] started'
    case 'message.created':
      return '[message] created'
    case 'run.finished': {
      const usage = parseOpenAIUsage(p.usage)
      if (usage) {
        return `[run] finished ${String(p.status ?? '')} ${formatOpenAIUsageForTrace(usage, locale)}`
      }
      return `[run] finished ${String(p.status ?? '')}`
    }
    case 'run.error':
      return `[run.error] ${String(p.code ?? '')}: ${String(p.message ?? '')}`
    case 'llm.delta':
      return ''
    case 'llm.usage': {
      const usage = parseOpenAIUsage(p.usage)
      return usage ? `[usage] ${formatOpenAIUsageForTrace(usage, locale)}` : '[usage]'
    }
    default:
      return `[${event.type}]`
  }
}
