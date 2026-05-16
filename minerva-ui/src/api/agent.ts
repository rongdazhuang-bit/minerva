/**
 * 工作区智能体会话：创建会话与发起 OpenAI 兼容 SSE 流式 run。
 */
import { ApiError, apiOrigin } from '@/api/client'
import {
  parseAgentSseDataLine,
  type AgentStreamParseResult,
  type OpenAiChatCompletionChunk,
} from '@/api/openai-stream'

export type AgentSessionOut = {
  id: string
  workspace_id: string
  title: string | null
  agent_key: string | null
  status: string
  created_at: string
  updated_at?: string | null
}

export type AgentSessionListItem = {
  id: string
  title: string | null
  preview: string | null
  created_at: string
  updated_at: string | null
}

export type AgentMessageOut = {
  id: string
  role: string
  content: string | null
  seq: number
  created_at: string
}

export type AgentSessionDetailOut = {
  session: AgentSessionOut
  messages: AgentMessageOut[]
}

export type AgentSkillListItem = {
  id: string
  description: string
}

/** GET 最近会话列表（侧栏历史）。 */
export async function listAgentSessions(
  workspaceId: string,
  limit = 20,
): Promise<{ sessions: AgentSessionListItem[] }> {
  const origin = apiOrigin()
  const headers = new Headers(authHeaders())
  const res = await fetch(
    `${origin}/workspaces/${workspaceId}/agent/sessions?limit=${limit}`,
    { headers },
  )
  const text = await res.text()
  if (res.status === 401) {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    window.location.assign('/login')
  }
  if (!res.ok) {
    try {
      const j = JSON.parse(text) as { code?: string; message?: string }
      throw new ApiError(j.code ?? 'error', j.message ?? text)
    } catch (e) {
      if (e instanceof ApiError) throw e
      throw new ApiError('http', text || res.statusText)
    }
  }
  return JSON.parse(text) as { sessions: AgentSessionListItem[] }
}

/** DELETE 会话（级联删除 message / run / run_node）。 */
export async function deleteAgentSession(
  workspaceId: string,
  sessionId: string,
): Promise<void> {
  const origin = apiOrigin()
  const headers = new Headers(authHeaders())
  const res = await fetch(
    `${origin}/workspaces/${workspaceId}/agent/sessions/${sessionId}`,
    { method: 'DELETE', headers },
  )
  if (res.status === 401) {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    window.location.assign('/login')
  }
  if (res.status === 204) return
  const text = await res.text()
  try {
    const j = JSON.parse(text) as { code?: string; message?: string }
    throw new ApiError(j.code ?? 'error', j.message ?? text)
  } catch (e) {
    if (e instanceof ApiError) throw e
    throw new ApiError('http', text || res.statusText)
  }
}

/** GET 会话详情与消息历史。 */
export async function getAgentSessionDetail(
  workspaceId: string,
  sessionId: string,
): Promise<AgentSessionDetailOut> {
  const origin = apiOrigin()
  const headers = new Headers(authHeaders())
  const res = await fetch(
    `${origin}/workspaces/${workspaceId}/agent/sessions/${sessionId}`,
    { headers },
  )
  const text = await res.text()
  if (res.status === 401) {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    window.location.assign('/login')
  }
  if (!res.ok) {
    try {
      const j = JSON.parse(text) as { code?: string; message?: string }
      throw new ApiError(j.code ?? 'error', j.message ?? text)
    } catch (e) {
      if (e instanceof ApiError) throw e
      throw new ApiError('http', text || res.statusText)
    }
  }
  return JSON.parse(text) as AgentSessionDetailOut
}

/** GET 工作区可用 agent skills（来自服务端 INDEX.md）。 */
export async function listAgentSkills(
  workspaceId: string,
): Promise<{ skills: AgentSkillListItem[] }> {
  const origin = apiOrigin()
  const headers = new Headers(authHeaders())
  const res = await fetch(`${origin}/workspaces/${workspaceId}/agent/skills`, { headers })
  const text = await res.text()
  if (res.status === 401) {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    window.location.assign('/login')
  }
  if (!res.ok) {
    try {
      const j = JSON.parse(text) as { code?: string; message?: string }
      throw new ApiError(j.code ?? 'error', j.message ?? text)
    } catch (e) {
      if (e instanceof ApiError) throw e
      throw new ApiError('http', text || res.statusText)
    }
  }
  return JSON.parse(text) as { skills: AgentSkillListItem[] }
}

export type AgentRunCreateBody = {
  user_message: string
  skill_ids?: string[]
  provider_kind?: string
  base_url: string
  api_key: string
  model: string
  temperature?: number | null
  max_tokens?: number | null
}

/** Callback payload: parsed chunk, terminal ``[DONE]``, or OpenAI error object. */
export type AgentStreamEvent = AgentStreamParseResult

function authHeaders(): HeadersInit {
  const headers: Record<string, string> = {}
  const token = localStorage.getItem('access_token')
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

/** POST 创建会话，返回会话实体。 */
export async function createAgentSession(
  workspaceId: string,
  body: { title?: string | null; agent_key?: string | null } = {},
): Promise<AgentSessionOut> {
  const origin = apiOrigin()
  const headers = new Headers(authHeaders())
  headers.set('Content-Type', 'application/json')
  const res = await fetch(`${origin}/workspaces/${workspaceId}/agent/sessions`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
  const text = await res.text()
  if (res.status === 401) {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    window.location.assign('/login')
  }
  if (!res.ok) {
    try {
      const j = JSON.parse(text) as { code?: string; message?: string }
      throw new ApiError(j.code ?? 'error', j.message ?? text)
    } catch (e) {
      if (e instanceof ApiError) throw e
      throw new ApiError('http', text || res.statusText)
    }
  }
  return JSON.parse(text) as AgentSessionOut
}

export type StreamAgentRunResult = {
  /** Run id from ``X-Minerva-Run-Id`` when present. */
  runId: string | null
}

/**
 * 发起一次 run，消费 OpenAI 兼容 ``text/event-stream``，按 ``data:`` 行解析并回调 ``onEvent``。
 */
export async function streamAgentRun(
  workspaceId: string,
  sessionId: string,
  body: AgentRunCreateBody,
  onEvent: (evt: AgentStreamEvent) => void,
  signal?: AbortSignal,
): Promise<StreamAgentRunResult> {
  const origin = apiOrigin()
  const headers = new Headers(authHeaders())
  headers.set('Content-Type', 'application/json')
  const payload: AgentRunCreateBody = {
    user_message: body.user_message,
    skill_ids: body.skill_ids ?? [],
    provider_kind: body.provider_kind ?? 'openai_compatible',
    base_url: body.base_url,
    api_key: body.api_key,
    model: body.model,
    temperature: body.temperature ?? null,
    max_tokens: body.max_tokens ?? null,
  }
  const res = await fetch(
    `${origin}/workspaces/${workspaceId}/agent/sessions/${sessionId}/runs`,
    {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      signal,
    },
  )
  if (res.status === 401) {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    window.location.assign('/login')
  }
  if (!res.ok) {
    const text = await res.text()
    try {
      const j = JSON.parse(text) as { code?: string; message?: string }
      throw new ApiError(j.code ?? 'error', j.message ?? text)
    } catch (e) {
      if (e instanceof ApiError) throw e
      throw new ApiError('http', text || res.statusText)
    }
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
      const lines = block.split('\n')
      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        const raw = line.replace(/^data:\s*/, '').trim()
        const parsed = parseAgentSseDataLine(raw)
        if (parsed) onEvent(parsed)
      }
    }
  }
  return { runId }
}

/** Re-export chunk type for UI consumers that only need the envelope shape. */
export type { OpenAiChatCompletionChunk }
