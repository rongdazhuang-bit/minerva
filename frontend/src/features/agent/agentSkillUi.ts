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

/** Parse leading ``/skill_id`` when id is in ``knownSkillIds`` (case-insensitive). */
export function parseSkillPrefixFromDraft(
  draft: string,
  knownSkillIds: readonly string[],
): string | null {
  const m = draft.match(/^\/([a-z][a-z0-9_]*)(\s|$)/i)
  if (!m) return null
  const id = m[1].toLowerCase()
  const known = new Set(knownSkillIds.map((s) => s.toLowerCase()))
  return known.has(id) ? id : null
}

/** When draft starts with ``/unknown_id``, return that id if it is not registered. */
export function parseInvalidSkillPrefixFromDraft(
  draft: string,
  knownSkillIds: readonly string[],
): string | null {
  const m = draft.match(/^\/([a-z][a-z0-9_]*)(\s|$)/i)
  if (!m) return null
  const id = m[1].toLowerCase()
  const known = new Set(knownSkillIds.map((s) => s.toLowerCase()))
  return known.has(id) ? null : id
}

/** Skills eligible for the composer slash menu. */
export function composerVisibleSkills(
  skills: {
    id: string
    description: string
    composer_description?: string
    composer_visible?: boolean
  }[],
): { id: string; description: string }[] {
  return skills
    .filter((s) => s.composer_visible !== false)
    .map((s) => ({
      id: s.id,
      description: (s.composer_description ?? s.id).trim() || s.id,
    }))
}

/** Filter slash menu options by typed prefix after ``/``. */
export function filterSlashSkillOptions(
  options: { id: string; description: string }[],
  filter: string,
): { id: string; description: string }[] {
  const q = filter.trim().toLowerCase()
  if (!q) return options
  return options.filter(
    (o) => o.id.toLowerCase().includes(q) || o.description.toLowerCase().includes(q),
  )
}

/** User-visible chat bubble text without leading ``/skill_id`` prefix. */
export function formatUserMessageForDisplay(
  content: string,
  knownSkillIds: readonly string[],
): string {
  const skillId = parseSkillPrefixFromDraft(content, knownSkillIds)
  if (!skillId) return content
  return stripSkillPrefixFromDraft(content, skillId)
}

/** Build user-visible message with ``/skill_id`` prefix for the chat bubble. */
export function buildDisplayUserMessage(body: string, skillId: string | null): string {
  if (!skillId) return body
  const inner = body.trim()
  return inner ? `/${skillId} ${inner}` : `/${skillId}`
}

import { extractReasoningTokens, extractTotalTokens } from '@/api/agent-stream-v2'

export type AgentReasoningSegment = {
  phase: string
  step_id: string | null
  skill_id: string | null
  text: string
  reasoning_tokens: number
}

export type AgentChatMsg = {
  id: string
  role: 'user' | 'assistant'
  content: string
  /** Merged plain reasoning text (legacy / fallback). */
  reasoning?: string
  reasoningSegments?: AgentReasoningSegment[]
  reasoningTokens?: number
  processLog?: string[]
  /** Total LLM tokens consumed for this assistant turn (from SSE run usage). */
  totalTokens?: number
}

export function reasoningSegmentKey(
  phase: string,
  stepId: string | null | undefined,
  skillId: string | null | undefined,
): string {
  return `${phase}:${stepId ?? ''}:${skillId ?? ''}`
}

/** Human-readable segment title aligned with backend merged banners. */
export function formatReasoningSegmentLabel(segment: AgentReasoningSegment): string {
  if (segment.phase === 'planner') return '[Planner]'
  if (segment.phase === 'synthesizer') return '[Synthesizer]'
  if (segment.phase === 'subagent') {
    const sk = segment.skill_id ?? '-'
    const sid = segment.step_id ?? '-'
    return `[${sk} · ${sid}]`
  }
  return `[${segment.phase}]`
}

export function appendReasoningDelta(
  segments: AgentReasoningSegment[],
  phase: string,
  text: string,
  stepId: string | null | undefined,
  skillId: string | null | undefined,
): AgentReasoningSegment[] {
  const key = reasoningSegmentKey(phase, stepId, skillId)
  const idx = segments.findIndex(
    (s) => reasoningSegmentKey(s.phase, s.step_id, s.skill_id) === key,
  )
  if (idx < 0) {
    return [
      ...segments,
      {
        phase,
        step_id: stepId ?? null,
        skill_id: skillId ?? null,
        text,
        reasoning_tokens: 0,
      },
    ]
  }
  const next = [...segments]
  next[idx] = { ...next[idx], text: next[idx].text + text }
  return next
}

export function updateReasoningSegmentTokens(
  segments: AgentReasoningSegment[],
  phase: string,
  tokens: number,
  stepId: string | null | undefined,
  skillId: string | null | undefined,
): AgentReasoningSegment[] {
  const key = reasoningSegmentKey(phase, stepId, skillId)
  return segments.map((s) =>
    reasoningSegmentKey(s.phase, s.step_id, s.skill_id) === key
      ? { ...s, reasoning_tokens: tokens }
      : s,
  )
}

export function hasVisibleReasoning(m: AgentChatMsg): boolean {
  const segs = m.reasoningSegments ?? []
  if (segs.some((s) => (s.text ?? '').trim().length > 0)) return true
  return Boolean((m.reasoning ?? '').trim())
}

/** Final reasoning token count from ``llm.reasoning.done`` / ``meta_json.reasoning.reasoning_tokens``. */
export function resolveReasoningTokenCount(m: AgentChatMsg): number {
  const direct = m.reasoningTokens
  if (typeof direct === 'number' && Number.isFinite(direct) && direct > 0) {
    return Math.trunc(direct)
  }
  return 0
}

function resolveReasoningTokensFromUsageMeta(metaJson: unknown): number | undefined {
  const usage = (metaJson as { usage?: unknown } | null | undefined)?.usage
  const fromUsage = extractReasoningTokens(usage)
  return fromUsage != null && fromUsage > 0 ? fromUsage : undefined
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
    const reasoningSegments =
      sm.reasoningSegments && sm.reasoningSegments.length > 0
        ? sm.reasoningSegments
        : src?.reasoningSegments
    const reasoningTokens =
      typeof sm.reasoningTokens === 'number' && sm.reasoningTokens > 0
        ? sm.reasoningTokens
        : typeof src?.reasoningTokens === 'number' && src.reasoningTokens > 0
          ? src.reasoningTokens
          : sm.reasoningTokens ?? src?.reasoningTokens
    return {
      ...sm,
      reasoning: sm.reasoning ?? src?.reasoning,
      reasoningSegments,
      reasoningTokens,
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
    reasoning_text?: string | null
    reasoning?: {
      segments?: AgentReasoningSegment[]
      reasoning_tokens?: number
    } | null
  }[],
): AgentChatMsg[] {
  const out: AgentChatMsg[] = []
  for (const m of rows) {
    if (m.role !== 'user' && m.role !== 'assistant') continue
    const text = (m.content ?? '').trim()
    if (m.role === 'assistant' && !text) continue
    const usage = (m.meta_json as { usage?: unknown } | null | undefined)?.usage
    const totalTokens = extractTotalTokens(usage) ?? undefined
    const metaReasoning = (
      m.meta_json as
        | {
            reasoning?: {
              segments?: AgentReasoningSegment[]
              reasoning_tokens?: number
            }
          }
        | null
        | undefined
    )?.reasoning
    const reasoning = m.reasoning ?? metaReasoning ?? undefined
    const segments = reasoning?.segments ?? []
    const usageReasoning = resolveReasoningTokensFromUsageMeta(m.meta_json)
    const reasoningTokensFromMeta =
      typeof reasoning?.reasoning_tokens === 'number'
        ? Math.trunc(reasoning.reasoning_tokens)
        : undefined
    const reasoningTokens =
      reasoningTokensFromMeta != null && reasoningTokensFromMeta > 0
        ? reasoningTokensFromMeta
        : usageReasoning
    out.push({
      id: m.id,
      role: m.role,
      content: m.content ?? '',
      totalTokens,
      reasoning: (m.reasoning_text ?? '').trim() || undefined,
      reasoningSegments: segments.length > 0 ? segments : undefined,
      reasoningTokens,
    })
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
