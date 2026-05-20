/** Formatting helpers for translation job sidebar rows. */

/** Format job list timestamp for sidebar display. */
export function formatTranslateJobDate(iso: string | null | undefined): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
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
