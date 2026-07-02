import { apiJson } from '@/api/client'

/** Department dict tree node for user form. */
export type SysUserDepartmentNode = {
  id: string
  dict_uuid: string
  parent_uuid: string | null
  code: string
  name: string
  item_sort: number | null
  create_at: string | null
  update_at: string | null
  children: SysUserDepartmentNode[]
}

/** Tenant option from sys_tenant for user create form. */
export type SysUserTenantOption = {
  id: string
  name: string
  slug: string
}

/** Workspace option from sys_workspaces for user create form. */
export type SysUserWorkspaceOption = {
  id: string
  tenant_id: string
  name: string
  slug: string
}

/** Actor form capabilities for a target workspace. */
export type SysUserCapabilities = {
  is_super_admin: boolean
  actor_workspace_role: string | null
  can_edit_membership_role: boolean
  assignable_membership_roles: string[]
  can_pick_tenant_workspace: boolean
  is_tenant_admin: boolean
  default_tenant_id: string | null
  can_pick_tenant?: boolean
  can_pick_workspace?: boolean
  fixed_tenant_id?: string | null
  fixed_tenant_name?: string | null
}

/** Platform-level list/form scope capabilities from JWT context. */
export type SysUserListCapabilities = {
  is_super_admin: boolean
  is_tenant_admin: boolean
  can_pick_tenant: boolean
  can_pick_workspace: boolean
  fixed_tenant_id: string | null
  fixed_tenant_name: string | null
  default_filter_tenant_id: string | null
  default_filter_workspace_id: string | null
  actor_workspace_role: string | null
  can_edit_membership_role: boolean
  assignable_membership_roles: string[]
}

/** Assignable role option. */
export type SysUserRoleOption = {
  id: string
  role_name: string
  role_key: string
  status: boolean
}

/** Workspace user list/detail row. */
export type SysUserListItem = {
  id: string
  email: string
  nickname: string
  phone: string | null
  status: boolean
  remark: string | null
  department_item_id: string | null
  department_name: string | null
  membership_role: string
  role_ids: string[]
  role_names: string[]
  tenant_id?: string | null
  workspace_id?: string | null
  tenant_name?: string | null
  workspace_name?: string | null
  created_at: string
  update_at: string | null
  can_hard_delete: boolean
}

/** Paginated users response. */
export type SysUserListPage = {
  items: SysUserListItem[]
  total: number
  page: number
  page_size: number
}

/** Query params for user list. */
export type SysUserListParams = {
  email?: string
  nickname?: string
  phone?: string
  status?: boolean
  membership_role?: string
  role_id?: string
  workspace_id?: string
  page?: number
  page_size?: number
}

/** Create user request body. */
export type SysUserCreateBody = {
  email: string
  password: string
  nickname: string
  phone?: string | null
  status?: boolean
  remark?: string | null
  membership_role: string
  department_item_id?: string | null
  role_ids?: string[]
}

/** Patch user request body. */
export type SysUserPatchBody = Partial<Omit<SysUserCreateBody, 'email'>> & {
  password?: string
}

function buildQuery(params: SysUserListParams): string {
  const q = new URLSearchParams()
  if (params.email?.trim()) q.set('email', params.email.trim())
  if (params.nickname?.trim()) q.set('nickname', params.nickname.trim())
  if (params.phone?.trim()) q.set('phone', params.phone.trim())
  if (params.status !== undefined) q.set('status', String(params.status))
  if (params.membership_role?.trim()) {
    q.set('membership_role', params.membership_role.trim())
  }
  if (params.role_id?.trim()) q.set('role_id', params.role_id.trim())
  if (params.workspace_id?.trim()) q.set('workspace_id', params.workspace_id.trim())
  if (params.page != null) q.set('page', String(params.page))
  if (params.page_size != null) q.set('page_size', String(params.page_size))
  const s = q.toString()
  return s ? `?${s}` : ''
}

/** List workspace members with optional filters. */
export function listUsers(workspaceId: string, params: SysUserListParams = {}) {
  return apiJson<SysUserListPage>(
    `/workspaces/${workspaceId}/users${buildQuery(params)}`,
  )
}

/** Load one workspace member. */
export function getUser(workspaceId: string, userId: string) {
  return apiJson<SysUserListItem>(`/workspaces/${workspaceId}/users/${userId}`)
}

/** Create a user and add to workspace. */
export function createUser(workspaceId: string, body: SysUserCreateBody) {
  return apiJson<SysUserListItem>(`/workspaces/${workspaceId}/users`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** Partially update a workspace member. */
export function patchUser(
  workspaceId: string,
  userId: string,
  body: SysUserPatchBody,
) {
  return apiJson<SysUserListItem>(
    `/workspaces/${workspaceId}/users/${userId}`,
    {
      method: 'PATCH',
      body: JSON.stringify(body),
    },
  )
}

/** Remove user from workspace (keep global account). */
export function removeUserMembership(workspaceId: string, userId: string) {
  return apiJson<void>(
    `/workspaces/${workspaceId}/users/${userId}/membership`,
    { method: 'DELETE' },
  )
}

/** Hard-delete global user account. */
export function deleteUserAccount(workspaceId: string, userId: string) {
  return apiJson<void>(`/workspaces/${workspaceId}/users/${userId}`, {
    method: 'DELETE',
  })
}

/** Load SYS_DEPARTMENT tree for user form. */
export function listUserDepartmentTree(workspaceId: string) {
  return apiJson<SysUserDepartmentNode[]>(
    `/workspaces/${workspaceId}/users/meta/departments`,
  )
}

/** Load assignable roles for user form. */
export function listUserAssignableRoles(workspaceId: string) {
  return apiJson<SysUserRoleOption[]>(
    `/workspaces/${workspaceId}/users/meta/roles`,
  )
}

/** Load platform list/form scope capability flags. */
export function getUserListCapabilities() {
  return apiJson<SysUserListCapabilities>('/sys/users/meta/capabilities')
}

/** List workspace members under a tenant with optional workspace filter. */
export function listTenantWorkspaceUsers(
  tenantId: string,
  params: SysUserListParams = {},
) {
  return apiJson<SysUserListPage>(
    `/sys/tenants/${tenantId}/workspace-users${buildQuery(params)}`,
  )
}

/** Load form capability flags for the current actor. */
export function getUserCapabilities(workspaceId: string) {
  return apiJson<SysUserCapabilities>(
    `/workspaces/${workspaceId}/users/meta/capabilities`,
  )
}

/** List active tenants from sys_tenant (super admin only). */
export function listUserFormTenants(workspaceId: string) {
  return apiJson<SysUserTenantOption[]>(
    `/workspaces/${workspaceId}/users/meta/tenants`,
  )
}

/** List active workspaces in sys_workspaces for one tenant (super admin only). */
export function listUserFormWorkspaces(workspaceId: string, tenantId: string) {
  return apiJson<SysUserWorkspaceOption[]>(
    `/workspaces/${workspaceId}/users/meta/tenants/${tenantId}/workspaces`,
  )
}
