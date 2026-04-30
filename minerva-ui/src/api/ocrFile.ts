import { apiJson } from '@/api/client'

export type OcrFileOverviewStats = {
  init_count: number
  process_count: number
  success_count: number
  failed_count: number
}

function ocrFilePath(workspaceId: string, suffix = '') {
  return `/workspaces/${workspaceId}/ocr-files${suffix}`
}

export function getOcrFileOverviewStats(workspaceId: string) {
  return apiJson<OcrFileOverviewStats>(ocrFilePath(workspaceId, '/overview-stats'))
}
