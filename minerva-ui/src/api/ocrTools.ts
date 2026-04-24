import { apiJson } from '@/api/client'

export type OcrAuthType = 'none' | 'basic' | 'api_key'

export type OcrToolListItem = {
  id: string
  name: string
  url: string
  auth_type: string | null
  user_name: string | null
  remark: string | null
  has_api_key: boolean
  has_password: boolean
  create_at: string | null
  update_at: string | null
}

export type OcrToolDetail = {
  id: string
  workspace_id: string
  name: string
  url: string
  auth_type: string | null
  user_name: string | null
  user_passwd: string | null
  api_key: string | null
  remark: string | null
  create_at: string | null
  update_at: string | null
}

export type OcrToolCreateBody = {
  name: string
  url: string
  auth_type?: OcrAuthType | null
  user_name?: string | null
  user_passwd?: string | null
  api_key?: string | null
  remark?: string | null
}

export type OcrToolPatchBody = Partial<{
  name: string
  url: string
  auth_type: OcrAuthType | null
  user_name: string | null
  user_passwd: string | null
  api_key: string | null
  remark: string | null
}>

export function listOcrTools(workspaceId: string) {
  return apiJson<OcrToolListItem[]>(`/workspaces/${workspaceId}/ocr-tools`)
}

export function createOcrTool(workspaceId: string, body: OcrToolCreateBody) {
  return apiJson<OcrToolDetail>(`/workspaces/${workspaceId}/ocr-tools`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getOcrTool(workspaceId: string, toolId: string) {
  return apiJson<OcrToolDetail>(`/workspaces/${workspaceId}/ocr-tools/${toolId}`)
}

export function patchOcrTool(workspaceId: string, toolId: string, body: OcrToolPatchBody) {
  return apiJson<OcrToolDetail>(`/workspaces/${workspaceId}/ocr-tools/${toolId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteOcrTool(workspaceId: string, toolId: string) {
  return apiJson<null>(`/workspaces/${workspaceId}/ocr-tools/${toolId}`, {
    method: 'DELETE',
  })
}
