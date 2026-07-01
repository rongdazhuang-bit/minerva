import { apiJson } from '@/api/client'

/** One authorization grant within a tenant. */
export type SysUserGrant = {
  id: string
  user_id: string
  grant_type: string
  role_id: string | null
  permission_id: string | null
  scope_type: string
  scope_id: string | null
  status: boolean
  create_at: string | null
  update_at: string | null
}

export type SysUserGrantListPage = {
  items: SysUserGrant[]
  total: number
  page: number
  page_size: number
}

export type SysUserGrantListParams = {
  grant_type?: string
  user_id?: string
  scope_type?: string
  workspace_id?: string
  page?: number
  page_size?: number
}

export type SysUserGrantCreateBody = {
  user_id: string
  grant_type: 'role' | 'direct_permission'
  role_id?: string | null
  permission_id?: string | null
  scope_type: 'tenant' | 'workspace'
  scope_id?: string | null
}

/** List grants for one tenant (tenant admin or super admin). */
export function listTenantGrants(
  tenantId: string,
  params: SysUserGrantListParams = {},
): Promise<SysUserGrantListPage> {
  const q = new URLSearchParams()
  if (params.grant_type) q.set('grant_type', params.grant_type)
  if (params.user_id) q.set('user_id', params.user_id)
  if (params.scope_type) q.set('scope_type', params.scope_type)
  if (params.workspace_id) q.set('workspace_id', params.workspace_id)
  if (params.page != null) q.set('page', String(params.page))
  if (params.page_size != null) q.set('page_size', String(params.page_size))
  const qs = q.toString()
  return apiJson<SysUserGrantListPage>(
    `/sys/tenants/${tenantId}/grants${qs ? `?${qs}` : ''}`,
  )
}

/** Create a role or direct_permission grant. */
export function createTenantGrant(
  tenantId: string,
  body: SysUserGrantCreateBody,
): Promise<SysUserGrant> {
  return apiJson<SysUserGrant>(`/sys/tenants/${tenantId}/grants`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** Revoke one grant. */
export function deleteTenantGrant(tenantId: string, grantId: string): Promise<void> {
  return apiJson<void>(`/sys/tenants/${tenantId}/grants/${grantId}`, {
    method: 'DELETE',
  })
}

/** Replace workspace-scoped role grants for one user via Grant API. */
export async function replaceWorkspaceRoleGrants(
  tenantId: string,
  workspaceId: string,
  userId: string,
  roleIds: string[],
): Promise<void> {
  const existing = await listTenantGrants(tenantId, {
    user_id: userId,
    grant_type: 'role',
    scope_type: 'workspace',
    workspace_id: workspaceId,
    page_size: 200,
  })
  await Promise.all(existing.items.map((grant) => deleteTenantGrant(tenantId, grant.id)))
  await Promise.all(
    roleIds.map((roleId) =>
      createTenantGrant(tenantId, {
        user_id: userId,
        grant_type: 'role',
        role_id: roleId,
        scope_type: 'workspace',
        scope_id: workspaceId,
      }),
    ),
  )
}
