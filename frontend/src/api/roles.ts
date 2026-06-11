import { apiJson } from '@/api/client'
import type { SysMenuNode } from '@/api/menus'

/** Workspace role list row. */
export type SysRoleListItem = {
  id: string
  workspace_id: string
  role_name: string
  role_key: string
  role_sort: number
  status: boolean
  remark: string | null
  create_at: string | null
  update_at: string | null
}

/** Role detail including assigned menu ids. */
export type SysRoleDetail = SysRoleListItem & {
  menu_ids: string[]
}

/** Paginated roles response. */
export type SysRoleListPage = {
  items: SysRoleListItem[]
  total: number
  page: number
  page_size: number
}

/** Query params for role list. */
export type SysRoleListParams = {
  role_name?: string
  status?: boolean
  role_key?: string
  page?: number
  page_size?: number
}

/** Create role request body. */
export type SysRoleCreateBody = {
  role_name: string
  role_key: string
  role_sort?: number
  status?: boolean
  remark?: string | null
  menu_ids?: string[]
}

/** Patch role request body. */
export type SysRolePatchBody = Partial<SysRoleCreateBody>

function buildQuery(params: SysRoleListParams): string {
  const q = new URLSearchParams()
  if (params.role_name?.trim()) q.set('role_name', params.role_name.trim())
  if (params.status !== undefined) q.set('status', String(params.status))
  if (params.role_key?.trim()) q.set('role_key', params.role_key.trim())
  if (params.page != null) q.set('page', String(params.page))
  if (params.page_size != null) q.set('page_size', String(params.page_size))
  const s = q.toString()
  return s ? `?${s}` : ''
}

/** List roles in a workspace with optional filters. */
export function listRoles(workspaceId: string, params: SysRoleListParams = {}) {
  return apiJson<SysRoleListPage>(
    `/workspaces/${workspaceId}/roles${buildQuery(params)}`,
  )
}

/** Load menu tree for role permission assignment. */
export function listRoleMenuTree(workspaceId: string) {
  return apiJson<SysMenuNode[]>(`/workspaces/${workspaceId}/roles/menu-tree`)
}

/** Load one role with menu ids. */
export function getRole(workspaceId: string, roleId: string) {
  return apiJson<SysRoleDetail>(`/workspaces/${workspaceId}/roles/${roleId}`)
}

/** Create a workspace role. */
export function createRole(workspaceId: string, body: SysRoleCreateBody) {
  return apiJson<SysRoleDetail>(`/workspaces/${workspaceId}/roles`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** Partially update a workspace role. */
export function patchRole(
  workspaceId: string,
  roleId: string,
  body: SysRolePatchBody,
) {
  return apiJson<SysRoleDetail>(`/workspaces/${workspaceId}/roles/${roleId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

/** Delete a workspace role. */
export function deleteRole(workspaceId: string, roleId: string) {
  return apiJson<void>(`/workspaces/${workspaceId}/roles/${roleId}`, {
    method: 'DELETE',
  })
}
