import { apiJson } from '@/api/client'

export type DatasetDocument = {
  id: string
  name: string
  position: number
  indexing_status: string
  display_status: string
  enabled: boolean
  archived: boolean
  is_paused: boolean
  doc_form: string
  word_count: number | null
  hit_count: number
  error: string | null
  batch: string
  create_at: string | null
  update_at: string | null
  completed_at: string | null
  file_id?: string | null
  process_rule_id?: string | null
  process_rule?: Record<string, unknown> | null
}

export type DatasetDocumentListOut = {
  items: DatasetDocument[]
  total: number
}

export type DatasetDetail = {
  id: string
  name: string
  description: string | null
  indexing_technique: string | null
  embedding_model: string | null
  embedding_model_provider: string | null
  retrieval_model: Record<string, unknown> | null
  chunk_structure: string | null
  document_count: number
  process_rule_id: string | null
  process_rule: Record<string, unknown> | null
  create_at: string | null
  update_at: string | null
}

export type DatasetSegment = {
  id: string
  position: number
  content: string
  answer?: string | null
  word_count: number
  tokens: number
  enabled: boolean
  status: string
  hit_count: number
  child_count?: number
  create_at: string | null
  update_at: string | null
}

export type DatasetChildChunk = {
  id: string
  position: number
  content: string
  word_count: number
  index_node_id: string | null
  create_at: string | null
  update_at: string | null
}

export type DatasetSegmentListOut = {
  items: DatasetSegment[]
  total: number
}

function base(workspaceId: string, datasetId: string, suffix = '') {
  return `/workspaces/${workspaceId}/datasets/${datasetId}${suffix}`
}

/** Fetch one knowledge base detail. */
export function getDataset(workspaceId: string, datasetId: string) {
  return apiJson<DatasetDetail>(`/workspaces/${workspaceId}/datasets/${datasetId}`)
}

/** Delete one knowledge base. */
export function deleteDataset(workspaceId: string, datasetId: string) {
  return apiJson<null>(`/workspaces/${workspaceId}/datasets/${datasetId}`, { method: 'DELETE' })
}

/** Append uploaded files to an existing knowledge base. */
export function appendDocuments(
  workspaceId: string,
  datasetId: string,
  payload: { file_ids: string[]; process_rule?: Record<string, unknown> },
) {
  return apiJson<{ batch: string; documents: DatasetDocument[]; indexing_task_id: string | null }>(
    base(workspaceId, datasetId, '/documents'),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  )
}

/** List documents in one knowledge base. */
export function listDocuments(
  workspaceId: string,
  datasetId: string,
  params?: { page?: number; page_size?: number; keyword?: string },
) {
  const sp = new URLSearchParams()
  if (params?.keyword?.trim()) sp.set('keyword', params.keyword.trim())
  if (params?.page != null) sp.set('page', String(params.page))
  if (params?.page_size != null) sp.set('page_size', String(params.page_size))
  const q = sp.toString()
  return apiJson<DatasetDocumentListOut>(base(workspaceId, datasetId, `/documents${q ? `?${q}` : ''}`))
}

/** Fetch one document detail. */
export function getDocument(workspaceId: string, datasetId: string, documentId: string) {
  return apiJson<DatasetDocument>(base(workspaceId, datasetId, `/documents/${documentId}`))
}

/** Delete one document. */
export function deleteDocument(workspaceId: string, datasetId: string, documentId: string) {
  return apiJson<null>(base(workspaceId, datasetId, `/documents/${documentId}`), { method: 'DELETE' })
}

/** Enable or disable one document. */
export function setDocumentEnabled(
  workspaceId: string,
  datasetId: string,
  documentId: string,
  enabled: boolean,
) {
  const action = enabled ? 'enable' : 'disable'
  return apiJson<DatasetDocument>(
    base(workspaceId, datasetId, `/documents/${documentId}/status/${action}`),
    { method: 'POST' },
  )
}

/** Retry failed document indexing. */
export function retryDocument(workspaceId: string, datasetId: string, documentId: string) {
  return apiJson<DatasetDocument>(
    base(workspaceId, datasetId, `/documents/${documentId}/retry`),
    { method: 'POST' },
  )
}

/** Retry all failed documents in one knowledge base. */
export function retryFailedDocuments(workspaceId: string, datasetId: string) {
  return apiJson<{ retried_count: number; document_ids: string[] }>(
    base(workspaceId, datasetId, '/retry'),
    { method: 'POST' },
  )
}

/** Update one document (rename or segment settings). */
export function patchDocument(
  workspaceId: string,
  datasetId: string,
  documentId: string,
  body: { name?: string; process_rule?: Record<string, unknown> },
) {
  return apiJson<DatasetDocument>(base(workspaceId, datasetId, `/documents/${documentId}`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/** List segments for one document. */
export function listSegments(
  workspaceId: string,
  datasetId: string,
  documentId: string,
  params?: { page?: number; page_size?: number; keyword?: string },
) {
  const sp = new URLSearchParams()
  if (params?.keyword?.trim()) sp.set('keyword', params.keyword.trim())
  if (params?.page != null) sp.set('page', String(params.page))
  if (params?.page_size != null) sp.set('page_size', String(params.page_size))
  const q = sp.toString()
  return apiJson<DatasetSegmentListOut>(
    base(workspaceId, datasetId, `/documents/${documentId}/segments${q ? `?${q}` : ''}`),
  )
}

/** List child chunks for one parent segment. */
export function listChildChunks(
  workspaceId: string,
  datasetId: string,
  documentId: string,
  segmentId: string,
) {
  return apiJson<{ items: DatasetChildChunk[] }>(
    base(workspaceId, datasetId, `/documents/${documentId}/segments/${segmentId}/child_chunks`),
  )
}

/** Enable or disable one segment. */
export function setSegmentEnabled(
  workspaceId: string,
  datasetId: string,
  documentId: string,
  segmentId: string,
  enabled: boolean,
) {
  const action = enabled ? 'enable' : 'disable'
  return apiJson<DatasetSegment>(
    base(workspaceId, datasetId, `/documents/${documentId}/segments/${segmentId}/${action}`),
    { method: 'POST' },
  )
}
