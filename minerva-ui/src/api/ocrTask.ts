import { apiJson } from '@/api/client'

export type OcrFileOverviewStats = {
  init_count: number
  process_count: number
  success_count: number
  failed_count: number
}

export type OcrFileListItem = {
  id: string
  workspace_id: string
  file_name: string | null
  ocr_type: string
  status: string
  file_size: number | null
  object_key: string
  page_count: number | null
  create_at: string | null
  update_at: string | null
}

export type OcrFileListPage = {
  items: OcrFileListItem[]
  total: number
}

export type OcrFileListParams = {
  file_name?: string
  ocr_type?: string
  status?: string
  create_at_start?: string
  create_at_end?: string
  page?: number
  page_size?: number
}

export type OcrFileCreateBody = {
  ocr_type: 'PADDLE_OCR' | 'MINER_U'
  files: Array<{
    file_name: string
    file_size: number
    object_key: string
  }>
}

export type OcrFileBatchCreateOut = {
  items: OcrFileListItem[]
  total: number
}

export type OcrS3UploadOut = {
  object_key: string
  file_name: string
  content_type: string | null
  size: number
  download_url: string
}

function ocrFilePath(workspaceId: string, suffix = '') {
  return `/workspaces/${workspaceId}/ocr-files${suffix}`
}

function resolveApiBaseUrl(): string {
  const v = import.meta.env.VITE_API_BASE_URL
  if (v != null && String(v).trim() !== '') {
    return String(v).replace(/\/$/, '')
  }
  if (import.meta.env.DEV) return 'http://127.0.0.1:8000'
  return ''
}

export function getOcrFileOverviewStats(workspaceId: string) {
  return apiJson<OcrFileOverviewStats>(ocrFilePath(workspaceId, '/overview-stats'))
}

export function listOcrFiles(workspaceId: string, params?: OcrFileListParams) {
  const sp = new URLSearchParams()
  if (params?.file_name != null && params.file_name.trim() !== '') sp.set('file_name', params.file_name)
  if (params?.ocr_type != null && params.ocr_type.trim() !== '') sp.set('ocr_type', params.ocr_type)
  if (params?.status != null && params.status.trim() !== '') sp.set('status', params.status)
  if (params?.create_at_start != null && params.create_at_start.trim() !== '') {
    sp.set('create_at_start', params.create_at_start)
  }
  if (params?.create_at_end != null && params.create_at_end.trim() !== '') {
    sp.set('create_at_end', params.create_at_end)
  }
  if (params?.page != null) sp.set('page', String(params.page))
  if (params?.page_size != null) sp.set('page_size', String(params.page_size))
  const q = sp.toString()
  return apiJson<OcrFileListPage>(ocrFilePath(workspaceId, q ? `?${q}` : ''))
}

export function createOcrFiles(workspaceId: string, body: OcrFileCreateBody) {
  return apiJson<OcrFileBatchCreateOut>(ocrFilePath(workspaceId), {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function uploadOcrSourceFile(
  workspaceId: string,
  file: File,
  onProgress?: (percent: number) => void,
) {
  const base = resolveApiBaseUrl()
  const url = `${base}/workspaces/${workspaceId}/s3/files:upload?module_prefix=ocr_file`
  const token = localStorage.getItem('access_token')
  const formData = new FormData()
  formData.append('file', file)
  return new Promise<OcrS3UploadOut>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url, true)
    if (token != null && token.trim() !== '') {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    }
    xhr.upload.onprogress = (evt) => {
      if (evt.lengthComputable && onProgress != null) {
        onProgress(Math.max(0, Math.min(100, Math.round((evt.loaded / evt.total) * 100))))
      }
    }
    xhr.onerror = () => reject(new Error('network error'))
    xhr.onload = () => {
      const text = xhr.responseText ?? ''
      if (xhr.status < 200 || xhr.status >= 300) {
        try {
          const parsed = JSON.parse(text) as { message?: string }
          reject(new Error((parsed.message ?? text) || xhr.statusText))
          return
        } catch {
          reject(new Error(text || xhr.statusText))
          return
        }
      }
      try {
        resolve(JSON.parse(text) as OcrS3UploadOut)
      } catch {
        reject(new Error('invalid upload response'))
      }
    }
    xhr.send(formData)
  })
}
