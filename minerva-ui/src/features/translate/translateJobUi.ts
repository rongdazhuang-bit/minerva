import {
  DOC_TRANSLATE_STATUS_ASSEMBLING,
  DOC_TRANSLATE_STATUS_EXTRACTING,
  DOC_TRANSLATE_STATUS_FAILED,
  DOC_TRANSLATE_STATUS_OCR_RUNNING,
  DOC_TRANSLATE_STATUS_PENDING,
  DOC_TRANSLATE_STATUS_SUCCESS,
  DOC_TRANSLATE_STATUS_TRANSLATING,
} from '@/features/translate/constants'

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
  return status === DOC_TRANSLATE_STATUS_SUCCESS || status === DOC_TRANSLATE_STATUS_FAILED
}

/** Ant Design ``Tag`` color for one job status code. */
export function translateJobStatusTagColor(status: string): string | undefined {
  switch (status) {
    case DOC_TRANSLATE_STATUS_SUCCESS:
      return 'success'
    case DOC_TRANSLATE_STATUS_FAILED:
      return 'error'
    case DOC_TRANSLATE_STATUS_OCR_RUNNING:
    case DOC_TRANSLATE_STATUS_EXTRACTING:
    case DOC_TRANSLATE_STATUS_TRANSLATING:
    case DOC_TRANSLATE_STATUS_ASSEMBLING:
      return 'processing'
    case DOC_TRANSLATE_STATUS_PENDING:
      return 'default'
    default:
      return undefined
  }
}

type TranslateDetailQueryState = {
  isLoading: boolean
  isError: boolean
  data?: { pages?: unknown[] } | null
}

/** Show page-compare skeleton while job runs and layout/segments are not ready yet. */
export function shouldShowTranslateDetailPagesSkeleton(
  job: { status: string } | null | undefined,
  layoutPages: TranslateDetailQueryState,
  segmentsPageGroups: { isLoading: boolean },
): boolean {
  if (layoutPages.isLoading || segmentsPageGroups.isLoading) {
    return true
  }
  if (!job || isTranslateJobTerminal(job.status)) {
    return false
  }
  if (layoutPages.isError) {
    return true
  }
  const pageCount = layoutPages.data?.pages?.length ?? 0
  return pageCount === 0
}

/** Show segment-compare skeleton while job runs and no segments exist yet. */
export function shouldShowTranslateDetailSegmentsSkeleton(
  job: { status: string } | null | undefined,
  segmentsQuery: { isLoading: boolean },
  segmentCount: number,
): boolean {
  if (segmentsQuery.isLoading) {
    return true
  }
  if (!job || isTranslateJobTerminal(job.status)) {
    return false
  }
  return segmentCount === 0
}
