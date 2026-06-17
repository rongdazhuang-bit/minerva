/**
 * 工作区智能体 v2：会话 CRUD 与 SSE v2 流式 run（服务端托管 model_id）。
 */
import { ApiError, authFetch } from '@/api/client'
import { apiOrigin } from '@/api/config'
import {
  parseAgentV2SseLine,
  type AgentStreamV2ParseResult,
  type AgentSseEventV2,
} from '@/api/agent-stream-v2'

export type AgentSessionOut = {
  id: string
  workspace_id: string
  title: string | null
  agent_key: string | null
  status: string
  created_at: string
  updated_at?: string | null
  usage?: Record<string, unknown> | null
}

export type AgentSessionListItem = {
  id: string
  title: string | null
  preview: string | null
  created_at: string
  updated_at: string | null
  usage?: Record<string, unknown> | null
}

export type AgentMessageOut = {
  id: string
  role: string
  content: string | null
  seq: number
  created_at: string
  meta_json?: Record<string, unknown> | null
  reasoning_text?: string | null
  reasoning?: {
    segments: Array<{
      phase: string
      step_id: string | null
      skill_id: string | null
      text: string
      reasoning_tokens: number
    }>
    reasoning_tokens: number
  } | null
}

export type AgentSessionDetailOut = {
  session: AgentSessionOut
  messages: AgentMessageOut[]
}

export type AgentSkillListItem = {
  id: string
  description: string
  composer_description?: string
  composer_visible?: boolean
}

/** One calendar day in agent overview token usage chart (7 rows). */
export type AgentOverviewUsageDailyStatItem = {
  date: string
  prompt_tokens: number
  completion_tokens: number
  cached_tokens: number
  reasoning_tokens: number
}

export type AgentOverviewUsageDailyStats = {
  items: AgentOverviewUsageDailyStatItem[]
}

export type AgentRunCreateBodyV2 = {
  user_message: string
  model_id: string
  temperature?: number | null
  max_tokens?: number | null
  preferred_skills?: string[]
  /** 从该助手消息起截断服务端历史并重新 run（须为会话内真实 message id）。 */
  regenerate_from_message_id?: string | null
  /** 截断最后一条助手消息并重新 run（无 message id 时使用）。 */
  regenerate_last_assistant?: boolean
  /** 是否开启思考模式；显式 false 覆盖 model_config / 全局默认。 */
  enable_thinking?: boolean | null
}

export type AgentConversationModel = {
  id: string
  provider_name: string
  model_name: string
  endpoint_url: string
  max_tokens: number | null
  tags: string[]
}

export type AgentStreamEvent = AgentStreamV2ParseResult

function v2Base(workspaceId: string) {
  return `${apiOrigin()}/workspaces/${workspaceId}/agent/v2`
}

async function parseJsonError(text: string, res: Response): Promise<never> {
  try {
    const j = JSON.parse(text) as {
      code?: string
      message?: string
      details?: { errors?: Array<{ loc?: unknown[]; msg?: string }> }
    }
    let message = j.message ?? text
    const errs = j.details?.errors
    if (Array.isArray(errs) && errs.length > 0) {
      const hint = errs
        .map((e) => {
          const loc = Array.isArray(e.loc) ? e.loc.join('.') : ''
          return loc ? `${loc}: ${e.msg ?? ''}` : (e.msg ?? '')
        })
        .filter(Boolean)
        .join('; ')
      if (hint) message = `${message} (${hint})`
    }
    throw new ApiError(j.code ?? 'error', message)
  } catch (e) {
    if (e instanceof ApiError) throw e
    throw new ApiError('http', text || res.statusText)
  }
}

/** Default page size for agent session sidebar infinite scroll. */
export const AGENT_SESSIONS_PAGE_SIZE = 20

/** GET /sessions 允许的 ``limit`` 上限（与后端 Query le=50 一致）。 */
export const AGENT_SESSIONS_LIST_MAX = 50

export type AgentSessionListResponse = {
  sessions: AgentSessionListItem[]
  has_more: boolean
  next_cursor: string | null
}

/** GET 最近会话列表（侧栏历史，支持 cursor 分页）。 */
export async function listAgentSessions(
  workspaceId: string,
  options?: { limit?: number; cursor?: string | null },
): Promise<AgentSessionListResponse> {
  const limit = options?.limit ?? AGENT_SESSIONS_PAGE_SIZE
  const params = new URLSearchParams({ limit: String(limit) })
  if (options?.cursor) {
    params.set('cursor', options.cursor)
  }
  const res = await authFetch(`${v2Base(workspaceId)}/sessions?${params}`)
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
  return JSON.parse(text) as AgentSessionListResponse
}

/** DELETE 会话。 */
export async function deleteAgentSession(
  workspaceId: string,
  sessionId: string,
): Promise<void> {
  const res = await authFetch(`${v2Base(workspaceId)}/sessions/${sessionId}`, {
    method: 'DELETE',
  })
  if (res.status === 204) return
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
}

/** GET 会话详情与消息历史。 */
export async function getAgentSessionDetail(
  workspaceId: string,
  sessionId: string,
): Promise<AgentSessionDetailOut> {
  const res = await authFetch(`${v2Base(workspaceId)}/sessions/${sessionId}`)
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
  return JSON.parse(text) as AgentSessionDetailOut
}

/** GET 内置 skills 列表。 */
export async function listAgentSkills(
  workspaceId: string,
): Promise<{ skills: AgentSkillListItem[] }> {
  const res = await authFetch(`${v2Base(workspaceId)}/skills`)
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
  return JSON.parse(text) as { skills: AgentSkillListItem[] }
}

/** GET Agent 对话页可选模型（服务端 SQL 已过滤 CHAT tag 等条件）。 */
export async function listAgentConversationModels(
  workspaceId: string,
): Promise<AgentConversationModel[]> {
  const res = await authFetch(`${v2Base(workspaceId)}/models`)
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
  return JSON.parse(text) as AgentConversationModel[]
}

/** GET 近 7 日智能体 token 用量（按 token 类型分 series）。 */
export async function getAgentOverviewUsageDailyStats(
  workspaceId: string,
): Promise<AgentOverviewUsageDailyStats> {
  const res = await authFetch(`${v2Base(workspaceId)}/overview-usage-daily-stats`)
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
  return JSON.parse(text) as AgentOverviewUsageDailyStats
}

/** POST 创建会话。 */
export async function createAgentSession(
  workspaceId: string,
  body: { title?: string | null; agent_key?: string | null } = {},
): Promise<AgentSessionOut> {
  const headers = new Headers({ 'Content-Type': 'application/json' })
  const res = await authFetch(`${v2Base(workspaceId)}/sessions`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
  return JSON.parse(text) as AgentSessionOut
}

export type StreamAgentRunResult = {
  runId: string | null
}

/**
 * 发起一次 v2 run，消费 SSE v2 ``data:`` 行。
 */
export async function streamAgentRun(
  workspaceId: string,
  sessionId: string,
  body: AgentRunCreateBodyV2,
  onEvent: (evt: AgentStreamEvent) => void,
  signal?: AbortSignal,
): Promise<StreamAgentRunResult> {
  const headers = new Headers({ 'Content-Type': 'application/json' })
  const res = await authFetch(
    `${v2Base(workspaceId)}/sessions/${sessionId}/runs`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify({
        user_message: body.user_message,
        model_id: body.model_id,
        temperature: body.temperature ?? null,
        max_tokens: body.max_tokens ?? null,
        preferred_skills: body.preferred_skills ?? [],
        regenerate_from_message_id: body.regenerate_from_message_id ?? null,
        regenerate_last_assistant: body.regenerate_last_assistant ?? false,
        enable_thinking: body.enable_thinking ?? null,
      }),
      signal,
    },
  )
  if (!res.ok) {
    const text = await res.text()
    await parseJsonError(text, res)
  }
  if (!res.body) {
    throw new ApiError('http', 'empty response body')
  }
  const runId = res.headers.get('X-Minerva-Run-Id')
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      for (const line of block.split('\n')) {
        if (!line.startsWith('data:')) continue
        const raw = line.replace(/^data:\s*/, '').trim()
        const parsed = parseAgentV2SseLine(raw)
        if (parsed) onEvent(parsed)
      }
    }
  }
  return { runId }
}

export type AgentV2ConfigOut = {
  memory_backend: string
}

export type AgentMemoryProfileOut = {
  id: string
  workspace_id: string
  session_id: string | null
  profile_text: string
  updated_by: string | null
  updated_at: string
}

export type AgentMem0MemoryItemOut = {
  id: string
  memory: string
  created_at: string | null
}

export type AgentMem0MemoryListOut = {
  items: AgentMem0MemoryItemOut[]
  total: number
}

function memoryBase(workspaceId: string) {
  return `${v2Base(workspaceId)}/memory`
}

/** GET Agent v2 runtime flags (e.g. memory backend). */
export async function getAgentV2Config(workspaceId: string): Promise<AgentV2ConfigOut> {
  const res = await authFetch(`${v2Base(workspaceId)}/config`)
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
  return JSON.parse(text) as AgentV2ConfigOut
}

/** GET persistent memory profiles (mem0 backend only). */
export async function listAgentMemoryProfiles(
  workspaceId: string,
  sessionId?: string | null,
): Promise<AgentMemoryProfileOut[]> {
  const params = new URLSearchParams()
  if (sessionId) params.set('session_id', sessionId)
  const q = params.toString()
  const res = await authFetch(
    `${memoryBase(workspaceId)}/profiles${q ? `?${q}` : ''}`,
  )
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
  return JSON.parse(text) as AgentMemoryProfileOut[]
}

/** POST upsert memory profile. */
export async function createAgentMemoryProfile(
  workspaceId: string,
  body: { session_id?: string | null; profile_text: string },
): Promise<AgentMemoryProfileOut> {
  const res = await authFetch(`${memoryBase(workspaceId)}/profiles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
  return JSON.parse(text) as AgentMemoryProfileOut
}

/** PATCH profile text. */
export async function patchAgentMemoryProfile(
  workspaceId: string,
  profileId: string,
  body: { profile_text: string },
): Promise<AgentMemoryProfileOut> {
  const res = await authFetch(`${memoryBase(workspaceId)}/profiles/${profileId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
  return JSON.parse(text) as AgentMemoryProfileOut
}

/** DELETE profile. */
export async function deleteAgentMemoryProfile(
  workspaceId: string,
  profileId: string,
): Promise<void> {
  const res = await authFetch(`${memoryBase(workspaceId)}/profiles/${profileId}`, {
    method: 'DELETE',
  })
  if (res.status === 204) return
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
}

/** GET mem0 memories for a session. */
export async function listAgentMem0Memories(
  workspaceId: string,
  sessionId: string,
  limit = 50,
): Promise<AgentMem0MemoryListOut> {
  const params = new URLSearchParams({
    session_id: sessionId,
    limit: String(limit),
  })
  const res = await authFetch(`${memoryBase(workspaceId)}/memories?${params}`)
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
  return JSON.parse(text) as AgentMem0MemoryListOut
}

/** DELETE one mem0 memory. */
export async function deleteAgentMem0Memory(
  workspaceId: string,
  memoryId: string,
): Promise<void> {
  const res = await authFetch(
    `${memoryBase(workspaceId)}/memories/${encodeURIComponent(memoryId)}`,
    { method: 'DELETE' },
  )
  if (res.status === 204) return
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
}

export type { AgentSseEventV2 }
