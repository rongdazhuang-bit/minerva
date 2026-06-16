/** Hit testing and dataset settings APIs. */
import { apiJson } from '@/api/client'
import type { DatasetDetail } from '@/features/dataset/api/documents'

export type HitTestingRecord = {
  score: number
  segment: {
    id: string
    content: string
    document_id: string
    position: number
    word_count: number
    answer?: string
    child_content?: string
  }
  document: {
    id: string
    name: string
  }
}

export type HitTestingOut = {
  query: string
  records: HitTestingRecord[]
}

export type DatasetQueryItem = {
  id: string
  content: string
  source: string
  create_at: string | null
}

export type DatasetQueryListOut = {
  items: DatasetQueryItem[]
  total: number
}

export type DatasetPatchBody = {
  name?: string
  description?: string | null
  indexing_technique?: string
  embedding_model?: string | null
  embedding_model_provider?: string | null
  retrieval_model?: Record<string, unknown>
  process_rule?: Record<string, unknown>
}

/** Patch knowledge base settings. */
export function patchDataset(workspaceId: string, datasetId: string, body: DatasetPatchBody) {
  return apiJson<DatasetDetail>(`/workspaces/${workspaceId}/datasets/${datasetId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/** Run hit testing for one query. */
export function runHitTesting(
  workspaceId: string,
  datasetId: string,
  body: { query: string; retrieval_model?: Record<string, unknown> },
) {
  return apiJson<HitTestingOut>(`/workspaces/${workspaceId}/datasets/${datasetId}/hit-testing`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/** List hit-testing query history. */
export function listDatasetQueries(
  workspaceId: string,
  datasetId: string,
  params?: { page?: number; page_size?: number },
) {
  const sp = new URLSearchParams()
  if (params?.page != null) sp.set('page', String(params.page))
  if (params?.page_size != null) sp.set('page_size', String(params.page_size))
  const q = sp.toString()
  return apiJson<DatasetQueryListOut>(
    `/workspaces/${workspaceId}/datasets/${datasetId}/queries${q ? `?${q}` : ''}`,
  )
}
