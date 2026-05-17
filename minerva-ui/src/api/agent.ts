/**
 * 工作区智能体 v2：会话 CRUD 与 SSE v2 流式 run（服务端托管 model_id）。
 */
import { ApiError, apiOrigin } from '@/api/client'
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

export type AgentCapabilityListItem = {
  id: string
  description: string
}

export type AgentRunCreateBodyV2 = {
  user_message: string
  model_id: string
  temperature?: number | null
  max_tokens?: number | null
  preferred_capabilities?: string[]
}

export type AgentStreamEvent = AgentStreamV2ParseResult

function authHeaders(): HeadersInit {
  const headers: Record<string, string> = {}
  const token = localStorage.getItem('access_token')
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

function v2Base(workspaceId: string) {
  return `${apiOrigin()}/workspaces/${workspaceId}/agent/v2`
}

async function handleAuth(res: Response) {
  if (res.status === 401) {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    window.location.assign('/login')
  }
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

/** GET 最近会话列表（侧栏历史）。 */
export async function listAgentSessions(
  workspaceId: string,
  limit = 20,
): Promise<{ sessions: AgentSessionListItem[] }> {
  const res = await fetch(`${v2Base(workspaceId)}/sessions?limit=${limit}`, {
    headers: new Headers(authHeaders()),
  })
  await handleAuth(res)
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
  return JSON.parse(text) as { sessions: AgentSessionListItem[] }
}

/** DELETE 会话。 */
export async function deleteAgentSession(
  workspaceId: string,
  sessionId: string,
): Promise<void> {
  const res = await fetch(`${v2Base(workspaceId)}/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: new Headers(authHeaders()),
  })
  await handleAuth(res)
  if (res.status === 204) return
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
}

/** GET 会话详情与消息历史。 */
export async function getAgentSessionDetail(
  workspaceId: string,
  sessionId: string,
): Promise<AgentSessionDetailOut> {
  const res = await fetch(`${v2Base(workspaceId)}/sessions/${sessionId}`, {
    headers: new Headers(authHeaders()),
  })
  await handleAuth(res)
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
  return JSON.parse(text) as AgentSessionDetailOut
}

/** GET 内置 capabilities 列表。 */
export async function listAgentCapabilities(
  workspaceId: string,
): Promise<{ capabilities: AgentCapabilityListItem[] }> {
  const res = await fetch(`${v2Base(workspaceId)}/capabilities`, {
    headers: new Headers(authHeaders()),
  })
  await handleAuth(res)
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
  return JSON.parse(text) as { capabilities: AgentCapabilityListItem[] }
}

/** POST 创建会话。 */
export async function createAgentSession(
  workspaceId: string,
  body: { title?: string | null; agent_key?: string | null } = {},
): Promise<AgentSessionOut> {
  const headers = new Headers(authHeaders())
  headers.set('Content-Type', 'application/json')
  const res = await fetch(`${v2Base(workspaceId)}/sessions`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
  await handleAuth(res)
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
  const headers = new Headers(authHeaders())
  headers.set('Content-Type', 'application/json')
  const res = await fetch(`${v2Base(workspaceId)}/sessions/${sessionId}/runs`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      user_message: body.user_message,
      model_id: body.model_id,
      temperature: body.temperature ?? null,
      max_tokens: body.max_tokens ?? null,
      preferred_capabilities: body.preferred_capabilities ?? [],
    }),
    signal,
  })
  await handleAuth(res)
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
