import { apiJson } from '@/api/client'

/** Tenant list row. */
export type SysTenantListItem = {
  id: string
  name: string
  slug: string
  status: boolean
  remark: string | null
  create_at: string | null
  update_at: string | null
}

/** Paginated tenants response. */
export type SysTenantListPage = {
  items: SysTenantListItem[]
  total: number
  page: number
  page_size: number
}

/** Query params for tenant list. */
export type SysTenantListParams = {
  name?: string
  status?: boolean
  page?: number
  page_size?: number
}

/** Create tenant request body. */
export type SysTenantCreateBody = {
  name: string
  slug: string
  status?: boolean
  remark?: string | null
}

/** Patch tenant request body. */
export type SysTenantPatchBody = Partial<SysTenantCreateBody>

/** Workspace list row under a tenant. */
export type SysWorkspaceListItem = {
  id: string
  tenant_id: string
  name: string
  slug: string
  status: boolean
  remark: string | null
  create_at: string | null
  update_at: string | null
}

/** Paginated workspaces response. */
export type SysWorkspaceListPage = {
  items: SysWorkspaceListItem[]
  total: number
  page: number
  page_size: number
}

/** Query params for workspace list. */
export type SysWorkspaceListParams = {
  name?: string
  status?: boolean
  page?: number
  page_size?: number
}

/** Create workspace request body. */
export type SysWorkspaceCreateBody = {
  name: string
  slug: string
  status?: boolean
  remark?: string | null
}

/** Patch workspace request body. */
export type SysWorkspacePatchBody = Partial<SysWorkspaceCreateBody>

function buildQuery(params: SysTenantListParams | SysWorkspaceListParams): string {
  const q = new URLSearchParams()
  if (params.name?.trim()) q.set('name', params.name.trim())
  if (params.status !== undefined) q.set('status', String(params.status))
  if (params.page != null) q.set('page', String(params.page))
  if (params.page_size != null) q.set('page_size', String(params.page_size))
  const s = q.toString()
  return s ? `?${s}` : ''
}

/** List tenants with optional filters. */
export function listTenants(params: SysTenantListParams = {}) {
  return apiJson<SysTenantListPage>(`/sys/tenants${buildQuery(params)}`)
}

/** Load one tenant. */
export function getTenant(tenantId: string) {
  return apiJson<SysTenantListItem>(`/sys/tenants/${tenantId}`)
}

/** Create a tenant. */
export function createTenant(body: SysTenantCreateBody) {
  return apiJson<SysTenantListItem>('/sys/tenants', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** Partially update a tenant. */
export function patchTenant(tenantId: string, body: SysTenantPatchBody) {
  return apiJson<SysTenantListItem>(`/sys/tenants/${tenantId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

/** Delete a tenant and cascade related rows. */
export function deleteTenant(tenantId: string) {
  return apiJson<void>(`/sys/tenants/${tenantId}`, {
    method: 'DELETE',
  })
}

/** List workspaces under a tenant. */
export function listWorkspaces(tenantId: string, params: SysWorkspaceListParams = {}) {
  return apiJson<SysWorkspaceListPage>(
    `/sys/tenants/${tenantId}/workspaces${buildQuery(params)}`,
  )
}

/** Load one workspace under a tenant. */
export function getWorkspace(tenantId: string, workspaceId: string) {
  return apiJson<SysWorkspaceListItem>(
    `/sys/tenants/${tenantId}/workspaces/${workspaceId}`,
  )
}

/** Create a workspace under a tenant. */
export function createWorkspace(tenantId: string, body: SysWorkspaceCreateBody) {
  return apiJson<SysWorkspaceListItem>(`/sys/tenants/${tenantId}/workspaces`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

/** Partially update a workspace. */
export function patchWorkspace(
  tenantId: string,
  workspaceId: string,
  body: SysWorkspacePatchBody,
) {
  return apiJson<SysWorkspaceListItem>(
    `/sys/tenants/${tenantId}/workspaces/${workspaceId}`,
    {
      method: 'PATCH',
      body: JSON.stringify(body),
    },
  )
}

/** Delete only the workspace row. */
export function deleteWorkspace(tenantId: string, workspaceId: string) {
  return apiJson<void>(`/sys/tenants/${tenantId}/workspaces/${workspaceId}`, {
    method: 'DELETE',
  })
}
