import { apiJson } from '@/api/client'

/** Authorization summary from GET /auth/me/authorization. */
export type AuthorizationSummary = {
  is_super_admin: boolean
  tenant_id: string | null
  workspace_id: string | null
  workspace_role: string | null
  tenant_role: string | null
  is_tenant_admin: boolean
  tenant_features: string[]
  permissions: string[]
  menu_paths: string[]
}

/** Load effective permissions for the current session. */
export function fetchAuthorization() {
  return apiJson<AuthorizationSummary>('/auth/me/authorization')
}
