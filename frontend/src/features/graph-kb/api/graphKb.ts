/** Workspace graph knowledge base (GraphKB) APIs. */

import { apiOrigin, apiJson } from '@/api/client'
import { getAccessToken, refreshTokens, forceLogoutOnAuthFailure } from '@/api/tokenSession'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'

export type GraphKbOut = {
  id: string
  workspace_id: string
  name: string
  description: string | null
  engine: string
  permission: string
  llm_model: string | null
  llm_model_provider: string | null
  embedding_model: string | null
  embedding_model_provider: string | null
  indexing_status: string
  created_by: string
  updated_by: string | null
  create_at: string | null
  update_at: string | null
  member_user_ids: string[]
}

export type GraphKbListPageOut = {
  items: GraphKbOut[]
  total: number
  page: number
  page_size: number
}

export type GraphKbListParams = {
  page?: number
  page_size?: number
  name?: string
  mine_only?: boolean
}

export type GraphKbCreateBody = {
  name: string
  description?: string | null
  engine: string
  permission: string
  llm_model?: string | null
  llm_model_provider?: string | null
  embedding_model?: string | null
  embedding_model_provider?: string | null
  member_user_ids?: string[]
}

export type GraphKbPatchBody = {
  name?: string
  description?: string | null
  permission?: string
  llm_model?: string | null
  llm_model_provider?: string | null
  embedding_model?: string | null
  embedding_model_provider?: string | null
  member_user_ids?: string[]
}

export type GraphKbDocumentOut = {
  id: string
  workspace_id: string
  graph_id: string
  source_type: string
  name: string
  storage_key: string | null
  text_content: string | null
  mime_type: string | null
  size_bytes: number | null
  indexing_status: string
  error: string | null
  created_by: string
  create_at: string | null
}

export type GraphKbDocumentListPageOut = {
  items: GraphKbDocumentOut[]
  total: number
  page: number
  page_size: number
}

export type GraphKbDocumentDeleteOut = {
  document_id: string
  reindex_enqueued: boolean
  message: string | null
}

export type GraphKbPlainTextBody = {
  name: string
  text: string
}

export type GraphKbJobOut = {
  id: string
  workspace_id: string
  graph_id: string
  kind: string
  status: string
  error: string | null
  started_at: string | null
  finished_at: string | null
  created_by: string
  create_at: string | null
}

export type GraphKbEntityOut = {
  id: string
  workspace_id: string
  graph_id: string
  engine_entity_id: string
  name: string
  entity_type: string | null
  description: string | null
  community_id: string | null
}

export type GraphKbEntityListPageOut = {
  items: GraphKbEntityOut[]
  total: number
  page: number
  page_size: number
}

export type GraphKbRelationOut = {
  id: string
  workspace_id: string
  graph_id: string
  from_entity_id: string
  to_entity_id: string
  relation_type: string | null
  description: string | null
  weight: number | null
}

export type GraphKbRelationListPageOut = {
  items: GraphKbRelationOut[]
  total: number
  page: number
  page_size: number
}

export type GraphKbGraphViewOut = {
  nodes: Record<string, unknown>[]
  edges: Record<string, unknown>[]
}

export type GraphKbGraphViewParams = {
  seed_entity_id?: string
  hops?: 1 | 2
  community_id?: string
}

export type GraphKbSummaryOut = {
  id: string
  workspace_id: string
  graph_id: string
  engine_community_id: string
  title: string | null
  summary: string | null
  level: number | null
  parent_id: string | null
}

export type GraphKbSummaryListPageOut = {
  items: GraphKbSummaryOut[]
  total: number
  page: number
  page_size: number
}

export type GraphKbQueryBody = {
  query: string
  mode: string
  top_k?: number
}

export type GraphKbQueryOut = {
  answer: string
  citations: Record<string, unknown>[]
}

export type GraphKbQueryHistoryOut = {
  id: string
  workspace_id: string
  graph_id: string
  query: string
  mode: string
  answer: string | null
  citations: unknown
  created_by: string
  create_at: string | null
}

export type GraphKbQueryHistoryPageOut = {
  items: GraphKbQueryHistoryOut[]
  total: number
  page: number
  page_size: number
}

export type PageParams = {
  page?: number
  page_size?: number
}

/** Build `/workspaces/{id}/graph-kbs{suffix}` path. */
function graphKbPath(workspaceId: string, suffix = '') {
  return `/workspaces/${workspaceId}/graph-kbs${suffix}`
}

/** Append page / page_size query params with DEFAULT_PAGE_SIZE fallback. */
function withPageParams(params?: PageParams): URLSearchParams {
  const sp = new URLSearchParams()
  sp.set('page', String(params?.page ?? 1))
  sp.set('page_size', String(params?.page_size ?? DEFAULT_PAGE_SIZE))
  return sp
}

/** Fetch paginated graphs for the current workspace. */
export function listGraphKbs(workspaceId: string, params?: GraphKbListParams) {
  const sp = withPageParams(params)
  if (params?.name?.trim()) sp.set('name', params.name.trim())
  if (params?.mine_only != null) sp.set('mine_only', String(params.mine_only))
  return apiJson<GraphKbListPageOut>(graphKbPath(workspaceId, `?${sp.toString()}`))
}

/** Create an empty graph knowledge base. */
export function createGraphKb(workspaceId: string, body: GraphKbCreateBody) {
  return apiJson<GraphKbOut>(graphKbPath(workspaceId), {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** Load one graph detail. */
export function getGraphKb(workspaceId: string, graphId: string) {
  return apiJson<GraphKbOut>(graphKbPath(workspaceId, `/${graphId}`))
}

/** Patch mutable graph fields (engine is immutable). */
export function patchGraphKb(workspaceId: string, graphId: string, body: GraphKbPatchBody) {
  return apiJson<GraphKbOut>(graphKbPath(workspaceId, `/${graphId}`), {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

/** Delete a graph (sync SQL + async cleanup). */
export function deleteGraphKb(workspaceId: string, graphId: string) {
  return apiJson<null>(graphKbPath(workspaceId, `/${graphId}`), {
    method: 'DELETE',
  })
}

/** Upload one source file into the graph document list. */
export function uploadGraphKbDocument(
  workspaceId: string,
  graphId: string,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<GraphKbDocumentOut> {
  const url = `${apiOrigin()}${graphKbPath(workspaceId, `/${graphId}/documents/upload`)}`

  const sendOnce = async (retried: boolean): Promise<GraphKbDocumentOut> => {
    const token = await getAccessToken()
    const formData = new FormData()
    formData.append('file', file)
    return new Promise<GraphKbDocumentOut>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', url, true)
      if (token?.trim()) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
      xhr.upload.onprogress = (evt) => {
        if (evt.lengthComputable && onProgress) {
          onProgress(Math.max(0, Math.min(100, Math.round((evt.loaded / evt.total) * 100))))
        }
      }
      xhr.onerror = () => reject(new Error('network error'))
      xhr.onload = () => {
        void (async () => {
          const text = xhr.responseText ?? ''
          if (xhr.status === 401 && !retried) {
            const ok = await refreshTokens()
            if (ok) {
              try {
                resolve(await sendOnce(true))
              } catch (e) {
                reject(e)
              }
              return
            }
            forceLogoutOnAuthFailure()
          }
          if (xhr.status === 401) {
            forceLogoutOnAuthFailure()
            reject(new Error('unauthorized'))
            return
          }
          if (xhr.status < 200 || xhr.status >= 300) {
            try {
              const j = JSON.parse(text) as { message?: string }
              reject(new Error(j.message ?? text))
            } catch {
              reject(new Error(text || xhr.statusText))
            }
            return
          }
          resolve(JSON.parse(text) as GraphKbDocumentOut)
        })()
      }
      xhr.send(formData)
    })
  }

  return sendOnce(false)
}

/** Import a plain-text body as a graph document. */
export function importGraphKbPlainText(
  workspaceId: string,
  graphId: string,
  body: GraphKbPlainTextBody,
) {
  return apiJson<GraphKbDocumentOut>(graphKbPath(workspaceId, `/${graphId}/documents/text`), {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** List documents for a graph. */
export function listGraphKbDocuments(workspaceId: string, graphId: string, params?: PageParams) {
  const sp = withPageParams(params)
  return apiJson<GraphKbDocumentListPageOut>(
    graphKbPath(workspaceId, `/${graphId}/documents?${sp.toString()}`),
  )
}

/** Delete one document; may enqueue reindex. */
export function deleteGraphKbDocument(workspaceId: string, graphId: string, docId: string) {
  return apiJson<GraphKbDocumentDeleteOut>(
    graphKbPath(workspaceId, `/${graphId}/documents/${docId}`),
    { method: 'DELETE' },
  )
}

/** Enqueue index / reindex for a graph. */
export function enqueueGraphKbIndex(workspaceId: string, graphId: string) {
  return apiJson<GraphKbJobOut>(graphKbPath(workspaceId, `/${graphId}/index`), {
    method: 'POST',
  })
}

/** Poll one job status. */
export function getGraphKbJob(workspaceId: string, graphId: string, jobId: string) {
  return apiJson<GraphKbJobOut>(graphKbPath(workspaceId, `/${graphId}/jobs/${jobId}`))
}

/** List entity projections. */
export function listGraphKbEntities(workspaceId: string, graphId: string, params?: PageParams) {
  const sp = withPageParams(params)
  return apiJson<GraphKbEntityListPageOut>(
    graphKbPath(workspaceId, `/${graphId}/entities?${sp.toString()}`),
  )
}

/** List relation projections. */
export function listGraphKbRelations(workspaceId: string, graphId: string, params?: PageParams) {
  const sp = withPageParams(params)
  return apiJson<GraphKbRelationListPageOut>(
    graphKbPath(workspaceId, `/${graphId}/relations?${sp.toString()}`),
  )
}

/** Fetch a canvas subgraph (seed + hops or community). */
export function getGraphKbGraphView(
  workspaceId: string,
  graphId: string,
  params?: GraphKbGraphViewParams,
) {
  const sp = new URLSearchParams()
  if (params?.seed_entity_id?.trim()) sp.set('seed_entity_id', params.seed_entity_id.trim())
  if (params?.hops != null) sp.set('hops', String(params.hops))
  if (params?.community_id?.trim()) sp.set('community_id', params.community_id.trim())
  const q = sp.toString()
  return apiJson<GraphKbGraphViewOut>(
    graphKbPath(workspaceId, `/${graphId}/graph-view${q ? `?${q}` : ''}`),
  )
}

/** List community / topic summaries. */
export function listGraphKbSummaries(workspaceId: string, graphId: string, params?: PageParams) {
  const sp = withPageParams(params)
  return apiJson<GraphKbSummaryListPageOut>(
    graphKbPath(workspaceId, `/${graphId}/summaries?${sp.toString()}`),
  )
}

/** Ask a question against a completed graph index. */
export function queryGraphKb(workspaceId: string, graphId: string, body: GraphKbQueryBody) {
  return apiJson<GraphKbQueryOut>(graphKbPath(workspaceId, `/${graphId}/query`), {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** List Q&A history for a graph. */
export function listGraphKbQueries(workspaceId: string, graphId: string, params?: PageParams) {
  const sp = withPageParams(params)
  return apiJson<GraphKbQueryHistoryPageOut>(
    graphKbPath(workspaceId, `/${graphId}/queries?${sp.toString()}`),
  )
}
