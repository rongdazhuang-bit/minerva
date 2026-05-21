/** Workspace document translation jobs API. */
import { ApiError, apiJson, apiOrigin, authFetch } from '@/api/client'

export type DocTranslateJobListItem = {
  id: string
  title: string | null
  file_name: string | null
  file_ext: string
  source_lang: string
  target_lang: string
  source_object_key: string
  result_object_key: string | null
  segment_total: number
  segment_done: number
  status: string
  progress: number
  create_at: string | null
  update_at: string | null
}

export type DocTranslateJobDetail = DocTranslateJobListItem & {
  model_id: string
  ocr_file_id: string | null
  error_code: string | null
  error_message: string | null
}

export type DocTranslateJobListOut = {
  items: DocTranslateJobListItem[]
  total: number
}

export type DocTranslateJobListParams = {
  page?: number
  page_size?: number
  file_name?: string
  status?: string
  create_at_start?: string
  create_at_end?: string
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

export function listTranslateJobs(workspaceId: string, params?: DocTranslateJobListParams) {
  const sp = new URLSearchParams()
  if (params?.file_name?.trim()) sp.set('file_name', params.file_name.trim())
  if (params?.status?.trim()) sp.set('status', params.status.trim())
  if (params?.create_at_start?.trim()) sp.set('create_at_start', params.create_at_start.trim())
  if (params?.create_at_end?.trim()) sp.set('create_at_end', params.create_at_end.trim())
  if (params?.page != null) sp.set('page', String(params.page))
  if (params?.page_size != null) sp.set('page_size', String(params.page_size))
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

/** Trigger browser download for one SUCCESS job via authenticated redirect to presigned URL. */
export async function downloadTranslateJob(
  workspaceId: string,
  jobId: string,
  suggestedFileName: string,
): Promise<void> {
  const res = await authFetch(
    `${apiOrigin()}/workspaces/${workspaceId}/translate/jobs/${jobId}/download`,
    { method: 'GET', redirect: 'manual' },
  )

  if (res.status === 302 || res.status === 307 || res.status === 303) {
    const target = res.headers.get('Location')
    if (!target?.trim()) {
      throw new ApiError('translate.download_failed', '下载重定向地址无效。')
    }
    const a = document.createElement('a')
    a.href = target
    a.download = suggestedFileName.trim() || 'translated'
    a.rel = 'noreferrer'
    a.target = '_blank'
    document.body.appendChild(a)
    a.click()
    a.remove()
    return
  }

  if (!res.ok) {
    try {
      const j = (await res.json()) as { code?: string; message?: string }
      throw new ApiError(j.code ?? 'error', j.message ?? res.statusText)
    } catch (e) {
      if (e instanceof ApiError) throw e
      throw new ApiError('http', res.statusText)
    }
  }

  const blob = await res.blob()
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = suggestedFileName.trim() || 'translated'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}
