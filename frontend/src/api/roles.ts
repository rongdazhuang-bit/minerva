import { apiJson } from '@/api/client'
import type { SysMenuNode } from '@/api/menus'

/** Frontend flags for role list filters and create-form scope pickers. */
export type SysRoleCapabilities = {
  is_super_admin: boolean
  is_tenant_admin: boolean
  can_pick_tenant: boolean
  can_pick_workspace: boolean
  fixed_tenant_id: string | null
  fixed_tenant_name: string | null
  default_filter_tenant_id: string | null
  default_filter_workspace_id: string | null
}

/** Tenant-scoped role list row. */
export type SysRoleListItem = {
  id: string
  tenant_id: string
  tenant_name: string
  workspace_id: string
  workspace_name: string
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
  tenant_id?: string
  workspace_id?: string
  role_name?: string
  status?: boolean
  role_key?: string
  page?: number
  page_size?: number
}

/** Create role request body. */
export type SysRoleCreateBody = {
  workspace_id: string
  role_name: string
  role_key: string
  role_sort?: number
  status?: boolean
  remark?: string | null
  menu_ids?: string[]
}

/** Patch role request body. */
export type SysRolePatchBody = Partial<Omit<SysRoleCreateBody, 'workspace_id'>>

function buildQuery(params: SysRoleListParams): string {
  const q = new URLSearchParams()
  if (params.tenant_id) q.set('tenant_id', params.tenant_id)
  if (params.workspace_id) q.set('workspace_id', params.workspace_id)
  if (params.role_name?.trim()) q.set('role_name', params.role_name.trim())
  if (params.status !== undefined) q.set('status', String(params.status))
  if (params.role_key?.trim()) q.set('role_key', params.role_key.trim())
  if (params.page != null) q.set('page', String(params.page))
  if (params.page_size != null) q.set('page_size', String(params.page_size))
  const s = q.toString()
  return s ? `?${s}` : ''
}

/** Load role page capabilities for filters and create-form scope. */
export function getRoleCapabilities() {
  return apiJson<SysRoleCapabilities>('/sys/roles/meta/capabilities')
}

/** List roles across tenants (super admin only). */
export function listRolesPlatform(params: SysRoleListParams = {}) {
  return apiJson<SysRoleListPage>(`/sys/roles${buildQuery(params)}`)
}

/** List roles within one tenant with optional workspace filter. */
export function listRolesForTenant(tenantId: string, params: SysRoleListParams = {}) {
  return apiJson<SysRoleListPage>(
    `/sys/tenants/${tenantId}/roles${buildQuery(params)}`,
  )
}

/** Load menu tree for role permission assignment. */
export function listRoleMenuTree() {
  return apiJson<SysMenuNode[]>('/sys/roles/menu-tree')
}

/** Load tenant-scoped menu tree for role permission picker. */
export function listRoleMenuTreeForTenant(tenantId: string) {
  return apiJson<SysMenuNode[]>(`/sys/tenants/${tenantId}/roles/menu-tree`)
}

/** Load one role with menu ids. */
export function getRole(tenantId: string, roleId: string) {
  return apiJson<SysRoleDetail>(`/sys/tenants/${tenantId}/roles/${roleId}`)
}

/** Create a role under a tenant workspace. */
export function createRole(tenantId: string, body: SysRoleCreateBody) {
  return apiJson<SysRoleDetail>(`/sys/tenants/${tenantId}/roles`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** Partially update a tenant-scoped role. */
export function patchRole(tenantId: string, roleId: string, body: SysRolePatchBody) {
  return apiJson<SysRoleDetail>(`/sys/tenants/${tenantId}/roles/${roleId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

/** Delete a tenant-scoped role. */
export function deleteRole(tenantId: string, roleId: string) {
  return apiJson<void>(`/sys/tenants/${tenantId}/roles/${roleId}`, {
    method: 'DELETE',
  })
}
