import { apiJson } from '@/api/client'

/** One row rendered in file storage paginated table. */
export type FileStorageListItem = {
  id: string
  workspace_id: string
  name: string | null
  type: string | null
  enabled: boolean
  auth_type: string
  endpoint_url: string | null
  auth_name: string | null
  has_api_key: boolean
  has_password: boolean
  create_at: string | null
  update_at: string | null
}

/** Full detail payload returned for view/edit drawers. */
export type FileStorageDetail = {
  id: string
  workspace_id: string
  name: string | null
  type: string | null
  enabled: boolean
  auth_type: string
  endpoint_url: string | null
  api_key: string | null
  auth_name: string | null
  auth_passwd: string | null
  create_at: string | null
  update_at: string | null
}

/** Paginated list response for file storages. */
export type FileStorageListPage = {
  items: FileStorageListItem[]
  total: number
}

/** Create payload for file storage rows. */
export type FileStorageCreateBody = {
  name?: string | null
  type?: string | null
  enabled?: boolean
  auth_type: string
  endpoint_url?: string | null
  api_key?: string | null
  auth_name?: string | null
  auth_passwd?: string | null
}

/** Partial update payload for file storage rows. */
export type FileStoragePatchBody = Partial<{
  name: string | null
  type: string | null
  enabled: boolean
  auth_type: string
  endpoint_url: string | null
  api_key: string | null
  auth_name: string | null
  auth_passwd: string | null
}>

/** Query params accepted by list API. */
export type ListFileStorageParams = {
  page?: number
  page_size?: number
}

/** List file storage rows with server-side pagination. */
export function listFileStorages(workspaceId: string, params?: ListFileStorageParams) {
  const sp = new URLSearchParams()
  if (params?.page != null) sp.set('page', String(params.page))
  if (params?.page_size != null) sp.set('page_size', String(params.page_size))
  const q = sp.toString()
  return apiJson<FileStorageListPage>(
    `/workspaces/${workspaceId}/file-storages${q ? `?${q}` : ''}`,
  )
}

/** Create one file storage row. */
export function createFileStorage(workspaceId: string, body: FileStorageCreateBody) {
  return apiJson<FileStorageDetail>(`/workspaces/${workspaceId}/file-storages`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** Load one file storage row by id. */
export function getFileStorage(workspaceId: string, storageId: string) {
  return apiJson<FileStorageDetail>(`/workspaces/${workspaceId}/file-storages/${storageId}`)
}

/** Patch one file storage row by id. */
export function patchFileStorage(
  workspaceId: string,
  storageId: string,
  body: FileStoragePatchBody,
) {
  return apiJson<FileStorageDetail>(`/workspaces/${workspaceId}/file-storages/${storageId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

/** Delete one file storage row by id. */
export function deleteFileStorage(workspaceId: string, storageId: string) {
  return apiJson<null>(`/workspaces/${workspaceId}/file-storages/${storageId}`, {
    method: 'DELETE',
  })
}
