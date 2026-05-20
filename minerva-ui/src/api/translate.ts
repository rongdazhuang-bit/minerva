/** Workspace document translation jobs API. */
import { apiJson, apiOrigin, authFetch } from '@/api/client'

export type DocTranslateJobListItem = {
  id: string
  title: string | null
  file_name: string | null
  file_ext: string
  source_lang: string
  target_lang: string
  status: string
  progress: number
  segment_total: number
  segment_done: number
  create_at: string | null
  update_at: string | null
}

export type DocTranslateJobDetail = DocTranslateJobListItem & {
  model_id: string
  source_object_key: string
  result_object_key: string | null
  ocr_file_id: string | null
  error_code: string | null
  error_message: string | null
}

export type DocTranslateJobListOut = {
  jobs: DocTranslateJobListItem[]
  next_cursor: string | null
}

export type DocTranslateSegment = {
  id: string
  seq: number
  source_text: string
  translated_text: string | null
  status: string
}

export type DocTranslateSegmentListOut = {
  segments: DocTranslateSegment[]
}

export type DocTranslateJobCreateOut = {
  id: string
  status: string
}

export function listTranslateJobs(
  workspaceId: string,
  params?: { limit?: number; cursor?: string | null },
) {
  const sp = new URLSearchParams()
  if (params?.limit != null) sp.set('limit', String(params.limit))
  if (params?.cursor) sp.set('cursor', params.cursor)
  const q = sp.toString()
  const suffix = q ? `/jobs?${q}` : '/jobs'
  return apiJson<DocTranslateJobListOut>(`/workspaces/${workspaceId}/translate${suffix}`)
}

export function getTranslateJob(workspaceId: string, jobId: string) {
  return apiJson<DocTranslateJobDetail>(
    `/workspaces/${workspaceId}/translate/jobs/${jobId}`,
  )
}

export function listTranslateJobSegments(workspaceId: string, jobId: string) {
  return apiJson<DocTranslateSegmentListOut>(
    `/workspaces/${workspaceId}/translate/jobs/${jobId}/segments`,
  )
}

export async function createTranslateJob(
  workspaceId: string,
  body: {
    file: File
    source_lang: string
    target_lang: string
    model_id: string
  },
): Promise<DocTranslateJobCreateOut> {
  const form = new FormData()
  form.append('file', body.file)
  form.append('source_lang', body.source_lang)
  form.append('target_lang', body.target_lang)
  form.append('model_id', body.model_id)
  const res = await authFetch(`${apiOrigin()}/workspaces/${workspaceId}/translate/jobs`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as { code?: string; message?: string }
    throw new Error(err.message ?? res.statusText)
  }
  return (await res.json()) as DocTranslateJobCreateOut
}

export function deleteTranslateJob(workspaceId: string, jobId: string) {
  return apiJson<null>(`/workspaces/${workspaceId}/translate/jobs/${jobId}`, {
    method: 'DELETE',
  })
}

export function translateJobDownloadUrl(workspaceId: string, jobId: string) {
  return `${apiOrigin()}/workspaces/${workspaceId}/translate/jobs/${jobId}/download`
}
