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
}

export type AgentSessionDetailOut = {
  session: AgentSessionOut
  messages: AgentMessageOut[]
}

export type AgentSkillListItem = {
  id: string
  description: string
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
}

export type AgentStreamEvent = AgentStreamV2ParseResult

function v2Base(workspaceId: string) {
  return `${apiOrigin()}/workspaces/${workspaceId}/agent/v2`
}

async function parseJsonError(text: string, res: Response): Promise<never> {
  try {
    const j = JSON.parse(text) as { code?: string; message?: string }
    throw new ApiError(j.code ?? 'error', j.message ?? text)
  } catch (e) {
    if (e instanceof ApiError) throw e
    throw new ApiError('http', text || res.statusText)
  }
}

/** Default page size for agent session sidebar infinite scroll. */
export const AGENT_SESSIONS_PAGE_SIZE = 20

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

export type { AgentSseEventV2 }
