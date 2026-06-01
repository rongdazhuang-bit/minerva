import { apiJson } from '@/api/client'

export type LayoutBlockOut = {
  block_key: string
  label: string
  source_text: string
  bbox: number[] | null
  overflow_policy: string
  skip_translate: boolean
}

export type LayoutPageOut = {
  page_index: number
  width: number | null
  height: number | null
  blocks: LayoutBlockOut[]
  page_raster_url: string | null
  source_markdown: string
  translated_markdown?: string | null
  images?: Record<string, string> | null
}

export type LayoutPagesOut = {
  file_id: string
  ocr_type: string
  layout_version: number
  pages: LayoutPageOut[]
}

function ocrFilePath(workspaceId: string, suffix: string) {
  return `/workspaces/${workspaceId}/ocr-files${suffix}`
}

function translateJobPath(workspaceId: string, jobId: string, suffix: string) {
  return `/workspaces/${workspaceId}/translate/jobs/${jobId}${suffix}`
}

/** Load layout pages for a SUCCESS OCR task. */
export function getOcrLayoutPages(workspaceId: string, ocrFileId: string) {
  return apiJson<LayoutPagesOut>(ocrFilePath(workspaceId, `/${ocrFileId}/layout-pages`))
}

/** Load layout pages for a translation job. */
export function getTranslateLayoutPages(workspaceId: string, jobId: string) {
  return apiJson<LayoutPagesOut>(translateJobPath(workspaceId, jobId, '/layout-pages'))
}
