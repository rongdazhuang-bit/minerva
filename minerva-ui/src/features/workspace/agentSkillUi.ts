/**
 * Helpers for agent skill prefix in the composer and chat bubbles.
 */

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

/** Map API messages to chat bubbles (skip ``tool`` rows). */
export function agentMessagesToChat(
  rows: { id: string; role: string; content: string | null }[],
): { id: string; role: 'user' | 'assistant'; content: string }[] {
  const out: { id: string; role: 'user' | 'assistant'; content: string }[] = []
  for (const m of rows) {
    if (m.role !== 'user' && m.role !== 'assistant') continue
    const text = (m.content ?? '').trim()
    if (m.role === 'assistant' && !text) continue
    out.push({ id: m.id, role: m.role, content: m.content ?? '' })
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
