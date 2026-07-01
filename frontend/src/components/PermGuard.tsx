import type { ReactNode } from 'react'

import { useAuth } from '@/app/AuthContext'

/** Returns whether the current user has one permission code. */
export function usePerm(code: string): boolean {
  const { hasPerm } = useAuth()
  return hasPerm(code)
}

/** True when the actor may manage workspace-scoped configuration. */
export function useCanManageWorkspace(): boolean {
  const { isSuperAdmin, isWorkspaceAdmin, hasPerm } = useAuth()
  return isSuperAdmin || isWorkspaceAdmin || hasPerm('workspace:manage')
}

/** True when the actor may manage tenant member accounts. */
export function useCanManageUsers(): boolean {
  const { isSuperAdmin, isTenantAdmin, isWorkspaceAdmin, hasPerm } = useAuth()
  return (
    isSuperAdmin ||
    isTenantAdmin ||
    isWorkspaceAdmin ||
    hasPerm('tenant:member:manage')
  )
}

/** True when the actor may manage tenant-scoped agent skills (grant + feature). */
export function useCanManageTenantSkills(): boolean {
  const { isSuperAdmin, isTenantAdmin, tenantFeatures } = useAuth()
  return isSuperAdmin || (isTenantAdmin && tenantFeatures.has('feature:skills'))
}

/** True when the actor may list or revoke tenant/workspace grants. */
export function useCanManageGrants(): boolean {
  const { isSuperAdmin, isTenantAdmin, isWorkspaceAdmin } = useAuth()
  return isSuperAdmin || isTenantAdmin || isWorkspaceAdmin
}

type PermGuardProps = {
  perm: string
  children: ReactNode
  fallback?: ReactNode
}

/** Renders children only when ``hasPerm(perm)`` is true. */
export function PermGuard({ perm, children, fallback = null }: PermGuardProps) {
  const { hasPerm } = useAuth()
  if (!hasPerm(perm)) return fallback
  return children
}
