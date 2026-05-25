/**
 * Helpers for agent skill prefix in the composer and chat bubbles.
 */

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

/** True when ``s`` looks like a server-side agent message UUID. */
export function isAgentMessageUuid(s: string): boolean {
  return UUID_RE.test(s.trim())
}

/** Strip leading ``/skill_id`` token for API ``user_message``. */
export function stripSkillPrefixFromDraft(draft: string, skillId: string | null): string {
  if (!skillId) return draft.trim()
  const re = new RegExp(`^/?${skillId}\\s*`, 'i')
  return draft.replace(re, '').trim()
}

/** Build user-visible message with ``/skill_id`` prefix for the chat bubble. */
export function buildDisplayUserMessage(body: string, skillId: string | null): string {
  if (!skillId) return body
  const inner = body.trim()
  return inner ? `/${skillId} ${inner}` : `/${skillId}`
}

import { extractTotalTokens } from '@/api/agent-stream-v2'

export type AgentChatMsg = {
  id: string
  role: 'user' | 'assistant'
  content: string
  reasoning?: string
  processLog?: string[]
  /** Total LLM tokens consumed for this assistant turn (from SSE run usage). */
  totalTokens?: number
}

/** 将服务端消息与本地 UI 状态（推理、轨迹）按 id 或顺序合并。 */
export function mergeAgentChatWithLocal(
  server: AgentChatMsg[],
  local: AgentChatMsg[],
): AgentChatMsg[] {
  return server.map((sm, index) => {
    const byId = local.find((m) => m.id === sm.id)
    const byIndex = local[index]
    const src = byId ?? (byIndex?.role === sm.role ? byIndex : undefined)
    const serverTok = sm.totalTokens
    const localTok = src?.totalTokens
    const totalTokens =
      serverTok != null && localTok != null
        ? Math.max(serverTok, localTok)
        : (serverTok ?? localTok)
    return {
      ...sm,
      reasoning: src?.reasoning,
      processLog: src?.processLog,
      totalTokens,
    }
  })
}

/** Map API messages to chat bubbles (skip ``tool`` rows). */
export function agentMessagesToChat(
  rows: {
    id: string
    role: string
    content: string | null
    meta_json?: unknown
  }[],
): AgentChatMsg[] {
  const out: AgentChatMsg[] = []
  for (const m of rows) {
    if (m.role !== 'user' && m.role !== 'assistant') continue
    const text = (m.content ?? '').trim()
    if (m.role === 'assistant' && !text) continue
    const usage = (m.meta_json as { usage?: unknown } | null | undefined)?.usage
    const totalTokens = extractTotalTokens(usage) ?? undefined
    out.push({ id: m.id, role: m.role, content: m.content ?? '', totalTokens })
  }
  return out
}

/** Derive session title from the first user question (max 200 chars). */
export function titleFromFirstQuestion(content: string): string | null {
  const line = content.trim().replace(/\s+/g, ' ')
  if (!line) return null
  return line.length > 200 ? line.slice(0, 200) : line
}

/** Format session timestamp for sidebar (always includes calendar date). */
export function formatSessionListDate(iso: string | null | undefined, locale?: string): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return ''
    return d.toLocaleString(locale, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  } catch {
    return ''
  }
}

function truncateLabel(text: string, max = 48): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

/** Label for sidebar session row (prefers title from first user question). */
export function sessionListLabel(
  item: { title: string | null; preview: string | null },
  fallback: string,
): string {
  const t = (item.title ?? '').trim()
  const p = (item.preview ?? '').trim()
  if (t && t !== fallback) return truncateLabel(t)
  if (p) return truncateLabel(p)
  if (t) return truncateLabel(t)
  return fallback
}
