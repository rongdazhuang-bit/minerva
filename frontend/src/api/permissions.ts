import { apiJson } from '@/api/client'

/** One row from the global permission catalog. */
export type SysPermission = {
  id: string
  perm_code: string
  perm_name: string
  perm_type: string
  resource_pattern: string | null
  menu_id: string | null
  status: boolean
  remark: string | null
  create_at: string | null
  update_at: string | null
}

export type SysPermissionListPage = {
  items: SysPermission[]
  total: number
  page: number
  page_size: number
}

export type SysPermissionListParams = {
  perm_type?: string
  perm_code?: string
  page?: number
  page_size?: number
}

/** List permission catalog rows (super-admin only). */
export function listPermissions(
  params: SysPermissionListParams = {},
): Promise<SysPermissionListPage> {
  const q = new URLSearchParams()
  if (params.perm_type) q.set('perm_type', params.perm_type)
  if (params.perm_code) q.set('perm_code', params.perm_code)
  if (params.page != null) q.set('page', String(params.page))
  if (params.page_size != null) q.set('page_size', String(params.page_size))
  const qs = q.toString()
  return apiJson<SysPermissionListPage>(`/sys/permissions${qs ? `?${qs}` : ''}`)
}
