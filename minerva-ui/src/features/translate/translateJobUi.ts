/** Formatting helpers for translation job table and detail modals. */

/** Format job timestamp as ``yyyy-MM-dd HH:mm:ss`` (local time). */
export function formatTranslateJobDateTime(iso: string | null | undefined): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return ''
    const pad = (n: number) => String(n).padStart(2, '0')
    return (
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
      `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
    )
  } catch {
    return ''
  }
}

/** Label for a history row (prefers title, then file name). */
export function translateJobListLabel(
  job: { title: string | null; file_name: string | null },
  fallback: string,
): string {
  const t = (job.title ?? '').trim()
  if (t) return t
  const f = (job.file_name ?? '').trim()
  return f || fallback
}

/** Whether job status is terminal (no 3s polling). */
export function isTranslateJobTerminal(status: string): boolean {
  return status === 'SUCCESS' || status === 'FAILED'
}
