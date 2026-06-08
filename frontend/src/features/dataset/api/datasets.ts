/** Workspace knowledge base (dataset) APIs. */

import { apiOrigin, apiJson } from '@/api/client'

import { getAccessToken, refreshTokens, forceLogoutOnAuthFailure } from '@/api/tokenSession'



export type DatasetListItem = {

  id: string

  name: string

  description: string | null

  indexing_technique: string | null

  document_count: number

  create_at: string | null

  update_at: string | null

}



export type DatasetListOut = {

  items: DatasetListItem[]

  total: number

}



export type DatasetListParams = {

  page?: number

  page_size?: number

  name?: string

  indexing_technique?: string

  created_from?: string

  created_to?: string

}



export type DatasetUploadOut = {

  id: string

  name: string

  size: number

  extension: string

  mime_type: string | null

}



export type ProcessRuleOut = {

  process_rule: Record<string, unknown>

}



export type SegmentPreview = {

  content: string

  word_count: number

}



export type FilePreview = {

  file_id: string

  file_name: string

  segment_count: number

  segments: SegmentPreview[]

}



export type IndexingEstimateOut = {

  total_segments: number

  total_chars: number

  preview_file_count: number

  previews: FilePreview[]

}



export type IndexingEstimateBody = {

  file_ids: string[]

  process_rule?: Record<string, unknown>

  indexing_technique?: string

  doc_form?: string

  preview_file_id?: string

}



export type DatasetInitBody = {

  name: string

  description?: string | null

  indexing_technique: string

  doc_form?: string

  file_ids: string[]

  process_rule?: Record<string, unknown>

  retrieval_model?: Record<string, unknown>

  embedding_model?: string

  embedding_model_provider?: string

}



export type DatasetInitOut = {

  dataset: {

    id: string

    name: string

    description: string | null

    indexing_technique: string | null

    collection_name: string | null

  }

  batch: string

  documents: Array<{

    id: string

    name: string

    indexing_status: string

    batch: string

  }>

  indexing_task_id: string | null

}



export type BatchIndexingStatusOut = {

  batch: string

  total: number

  completed: number

  failed: number

  processing: number

  documents: Array<{

    id: string

    name: string

    indexing_status: string

    error: string | null

    completed_at: string | null

    processing_started_at: string | null

  }>

}



function datasetPath(workspaceId: string, suffix = '') {

  return `/workspaces/${workspaceId}/datasets${suffix}`

}



/** Fetch paginated knowledge bases for the current workspace. */

export function listDatasets(workspaceId: string, params?: DatasetListParams) {

  const sp = new URLSearchParams()

  if (params?.name?.trim()) sp.set('name', params.name.trim())

  if (params?.indexing_technique?.trim()) sp.set('indexing_technique', params.indexing_technique.trim())

  if (params?.created_from?.trim()) sp.set('created_from', params.created_from.trim())

  if (params?.created_to?.trim()) sp.set('created_to', params.created_to.trim())

  if (params?.page != null) sp.set('page', String(params.page))

  if (params?.page_size != null) sp.set('page_size', String(params.page_size))

  const q = sp.toString()

  const suffix = q ? `?${q}` : ''

  return apiJson<DatasetListOut>(datasetPath(workspaceId, suffix))

}



/** Upload one source file for dataset creation. */

export function uploadDatasetFile(

  workspaceId: string,

  file: File,

  onProgress?: (percent: number) => void,

): Promise<DatasetUploadOut> {

  const url = `${apiOrigin()}${datasetPath(workspaceId, '/files/upload')}`



  const sendOnce = async (retried: boolean): Promise<DatasetUploadOut> => {

    const token = await getAccessToken()

    const formData = new FormData()

    formData.append('file', file)

    return new Promise<DatasetUploadOut>((resolve, reject) => {

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

          resolve(JSON.parse(text) as DatasetUploadOut)

        })()

      }

      xhr.send(formData)

    })

  }



  return sendOnce(false)

}



/** Load default chunking and cleaning rules. */

export function getDatasetProcessRule(workspaceId: string) {

  return apiJson<ProcessRuleOut>(datasetPath(workspaceId, '/process-rule'))

}



/** Preview chunking for uploaded files. */

export function estimateDatasetIndexing(workspaceId: string, body: IndexingEstimateBody) {

  return apiJson<IndexingEstimateOut>(datasetPath(workspaceId, '/indexing-estimate'), {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify(body),

  })

}



/** Create knowledge base and start indexing. */

export function initDataset(workspaceId: string, body: DatasetInitBody) {

  return apiJson<DatasetInitOut>(datasetPath(workspaceId, '/init'), {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify(body),

  })

}



/** Poll batch indexing progress. */

export function getBatchIndexingStatus(workspaceId: string, datasetId: string, batch: string) {

  return apiJson<BatchIndexingStatusOut>(

    datasetPath(workspaceId, `/${datasetId}/batch/${batch}/indexing-status`),

  )

}


