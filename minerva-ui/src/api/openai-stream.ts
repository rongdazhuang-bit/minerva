/**
 * OpenAI ``chat.completion.chunk`` SSE types and parsers (agent + shared streaming UIs).
 */

/** Current ``minerva`` extension schema version on SSE chunks. */
export const MINERVA_SSE_SCHEMA_VERSION = 1 as const

/** Orchestration event kinds carried in ``chunk.minerva``. */
export type MinervaStreamEventKind =
  | 'run.started'
  | 'run.finished'
  | 'run.error'
  | 'node.updated'
  | 'tool.start'
  | 'tool.result'

/** Node snapshot for live orchestration traces. */
export type MinervaNodeSnapshot = {
  id: string
  parent_node_id?: string | null
  node_type: string
  node_name: string
  status: 'pending' | 'running' | 'success' | 'failed' | 'skipped'
  sequence_idx?: number | null
}

/** Tool invocation snapshot (previews are redacted server-side). */
export type MinervaToolSnapshot = {
  tool_call_id: string
  name: string
  arguments_preview?: string | null
  result_preview?: string | null
}

/** Error payload on ``run.error`` events. */
export type MinervaErrorPayload = {
  code: string
  message: string
}

/** Root ``minerva`` object on synthetic orchestration chunks (schema v1). */
export type MinervaChunkExtension = {
  v: typeof MINERVA_SSE_SCHEMA_VERSION
  event: MinervaStreamEventKind
  run_id: string
  ts: string
  session_id?: string
  status?: 'success' | 'failed'
  node?: MinervaNodeSnapshot
  tool?: MinervaToolSnapshot
  error?: MinervaErrorPayload
}

/** Streaming delta (OpenAI-compatible subset). */
export type OpenAiChunkDelta = {
  role?: string
  content?: string | null
  reasoning_content?: string | null
  reasoning?: string | null
  tool_calls?: unknown[]
}

/** One choice in a streaming chunk. */
export type OpenAiChunkChoice = {
  index: number
  delta: OpenAiChunkDelta
  finish_reason?: string | null
}

/** OpenAI ``chat.completion.chunk`` envelope (may include ``minerva``). */
export type OpenAiChatCompletionChunk = {
  id: string
  object: 'chat.completion.chunk'
  created: number
  model: string
  choices: OpenAiChunkChoice[]
  minerva?: MinervaChunkExtension
}

/** OpenAI-style error object on the SSE stream. */
export type OpenAiStreamError = {
  error: {
    message: string
    type?: string
    code?: string
  }
}

/** Parsed SSE payload variants from one ``data:`` line. */
export type AgentStreamParseResult =
  | { kind: 'chunk'; chunk: OpenAiChatCompletionChunk }
  | { kind: 'done' }
  | { kind: 'error'; error: OpenAiStreamError['error'] }

/** Type guard for ``minerva`` extension objects. */
export function isMinervaChunkExtension(value: unknown): value is MinervaChunkExtension {
  if (!value || typeof value !== 'object') return false
  const o = value as Record<string, unknown>
  return o.v === MINERVA_SSE_SCHEMA_VERSION && typeof o.event === 'string' && typeof o.run_id === 'string'
}

/** Type guard for OpenAI stream error JSON. */
export function isOpenAiStreamError(value: unknown): value is OpenAiStreamError {
  if (!value || typeof value !== 'object') return false
  const err = (value as OpenAiStreamError).error
  return Boolean(err && typeof err.message === 'string')
}

/** Type guard for a streaming completion chunk. */
export function isOpenAiChatCompletionChunk(value: unknown): value is OpenAiChatCompletionChunk {
  if (!value || typeof value !== 'object') return false
  const o = value as Record<string, unknown>
  return o.object === 'chat.completion.chunk' && Array.isArray(o.choices)
}

/**
 * Parse one SSE ``data:`` payload (without the ``data:`` prefix).
 * Returns ``null`` for empty lines.
 */
export function parseAgentSseDataLine(raw: string): AgentStreamParseResult | null {
  const trimmed = raw.trim()
  if (!trimmed) return null
  if (trimmed === '[DONE]') return { kind: 'done' }
  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed) as unknown
  } catch {
    return null
  }
  if (isOpenAiStreamError(parsed)) {
    return { kind: 'error', error: parsed.error }
  }
  if (isOpenAiChatCompletionChunk(parsed)) {
    return { kind: 'chunk', chunk: parsed }
  }
  return null
}

/** Extract model reasoning text from a chunk delta, if present. */
export function deltaReasoningText(delta: OpenAiChunkDelta): string {
  const rc = delta.reasoning_content
  if (typeof rc === 'string' && rc.length > 0) return rc
  const r = delta.reasoning
  if (typeof r === 'string' && r.length > 0) return r
  return ''
}

/** Format a ``minerva`` event as a single trace log line. */
export function formatMinervaTraceLine(ext: MinervaChunkExtension): string {
  switch (ext.event) {
    case 'run.started':
      return `[run.started] ${ext.run_id}`
    case 'run.finished':
      return `[run.finished] ${ext.status ?? ''}`
    case 'run.error':
      return `[run.error] ${ext.error?.code ?? ''}: ${ext.error?.message ?? ''}`
    case 'node.updated': {
      const n = ext.node
      if (!n) return `[node.updated]`
      return `[node] ${n.node_type}/${n.node_name} → ${n.status}`
    }
    case 'tool.start':
      return `[tool.start] ${ext.tool?.name ?? ''}`
    case 'tool.result':
      return `[tool.result] ${ext.tool?.name ?? ''}`
    default:
      return `[${ext.event}]`
  }
}
