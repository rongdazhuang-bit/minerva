/**
 * 工作区智能体会话：创建会话与发起 SSE 流式 run（与后端 ``/agent`` 路由对齐）。
 */
import { ApiError, apiOrigin } from '@/api/client'

export type AgentSessionOut = {
  id: string
  workspace_id: string
  title: string | null
  agent_key: string | null
  status: string
  created_at: string
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

export type AgentSseEvent = {
  v: number
  type: string
  run_id: string
  ts: string
  session_id?: string
  text?: string
  code?: string
  message?: string
  status?: string
  [key: string]: unknown
}

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

/**
 * 发起一次 run，消费 ``text/event-stream``，按行解析 ``data:`` JSON 并回调 ``onEvent``。
 */
export async function streamAgentRun(
  workspaceId: string,
  sessionId: string,
  body: AgentRunCreateBody,
  onEvent: (evt: AgentSseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
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
        if (!raw || raw === '[DONE]') continue
        try {
          const evt = JSON.parse(raw) as AgentSseEvent
          onEvent(evt)
        } catch {
          // 忽略无法解析的行
        }
      }
    }
  }
}
