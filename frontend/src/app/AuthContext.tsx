import { useQuery } from '@tanstack/react-query'
import { jwtDecode } from 'jwt-decode'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { fetchAuthorization } from '@/api/auth'
import {
  STORAGE_ACCESS,
  STORAGE_REFRESH,
  cancelProactiveRefresh,
  clearStoredTokens,
  scheduleProactiveRefresh,
  setStoredTokens,
  subscribeTokensUpdated,
} from '@/api/tokenSession'

type JwtPayload = {
  sub?: string
  wid?: string
  wrole?: string
  trole?: string
  sa?: boolean
}

function readUserIdFromToken(access: string | null): string | null {
  if (!access) return null
  try {
    const p = jwtDecode(access) as JwtPayload
    const sub = p.sub
    if (sub == null) return null
    const s = String(sub).trim()
    return s === '' ? null : s
  } catch {
    return null
  }
}

function readWidFromToken(access: string | null): string | null {
  if (!access) return null
  try {
    const p = jwtDecode(access) as JwtPayload
    return p.wid ?? null
  } catch {
    return null
  }
}

function readWorkspaceRoleFromToken(access: string | null): string | null {
  if (!access) return null
  try {
    const p = jwtDecode(access) as JwtPayload
    const r = p.wrole
    if (r == null) return null
    const s = String(r).trim()
    return s === '' ? null : s
  } catch {
    return null
  }
}

function readTenantRoleFromToken(access: string | null): string | null {
  if (!access) return null
  try {
    const p = jwtDecode(access) as JwtPayload
    const r = p.trole
    if (r == null) return null
    const s = String(r).trim()
    return s === '' ? null : s
  } catch {
    return null
  }
}

function readSuperAdminFromToken(access: string | null): boolean {
  if (!access) return false
  try {
    const p = jwtDecode(access) as JwtPayload
    return Boolean(p.sa)
  } catch {
    return false
  }
}

type AuthValue = {
  accessToken: string | null
  refreshToken: string | null
  /** Authenticated user id from JWT ``sub`` claim. */
  userId: string | null
  workspaceId: string | null
  workspaceRole: string | null
  /** Tenant role from JWT ``trole`` claim (null when absent or legacy token). */
  tenantRole: string | null
  /** Platform super administrator from JWT ``sa`` or authorization API. */
  isSuperAdmin: boolean
  /** Tenant administrator from authorization API. */
  isTenantAdmin: boolean
  /** Workspace admin from JWT ``wrole``. */
  isWorkspaceAdmin: boolean
  /** Active tenant id from authorization API (null before load). */
  tenantId: string | null
  /** Enabled tenant feature codes from authorization API. */
  tenantFeatures: ReadonlySet<string>
  /** Effective permission codes; super-admin behaves as full access in hasPerm. */
  permissions: ReadonlySet<string>
  hasPerm: (code: string) => boolean
  isAuthenticated: boolean
  setTokens: (a: string, r: string) => void
  clear: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

function readTokensFromStorage(): { access: string | null; refresh: string | null } {
  return {
    access: localStorage.getItem(STORAGE_ACCESS),
    refresh: localStorage.getItem(STORAGE_REFRESH),
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const initial = readTokensFromStorage()
  const [accessToken, setAccess] = useState<string | null>(initial.access)
  const [refreshToken, setRefresh] = useState<string | null>(initial.refresh)

  const syncFromStorage = useCallback(() => {
    const { access, refresh } = readTokensFromStorage()
    setAccess(access)
    setRefresh(refresh)
    scheduleProactiveRefresh()
  }, [])

  useEffect(() => {
    scheduleProactiveRefresh()
    const unsub = subscribeTokensUpdated(syncFromStorage)
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_ACCESS || e.key === STORAGE_REFRESH) {
        syncFromStorage()
      }
    }
    window.addEventListener('storage', onStorage)
    return () => {
      unsub()
      window.removeEventListener('storage', onStorage)
      cancelProactiveRefresh()
    }
  }, [syncFromStorage])

  const userId = useMemo(
    () => readUserIdFromToken(accessToken),
    [accessToken],
  )
  const workspaceId = useMemo(
    () => readWidFromToken(accessToken),
    [accessToken],
  )
  const workspaceRole = useMemo(
    () => readWorkspaceRoleFromToken(accessToken),
    [accessToken],
  )
  const tenantRole = useMemo(
    () => readTenantRoleFromToken(accessToken),
    [accessToken],
  )
  const isSuperAdminFromToken = useMemo(
    () => readSuperAdminFromToken(accessToken),
    [accessToken],
  )

  const authzQuery = useQuery({
    queryKey: ['auth', 'authorization', accessToken ?? ''],
    queryFn: fetchAuthorization,
    enabled: Boolean(accessToken),
    staleTime: 60_000,
  })

  const isWorkspaceAdmin = useMemo(() => {
    const r = workspaceRole?.toLowerCase()
    return r === 'admin'
  }, [workspaceRole])

  const isSuperAdmin = isSuperAdminFromToken || Boolean(authzQuery.data?.is_super_admin)
  const isTenantAdmin = Boolean(authzQuery.data?.is_tenant_admin)
  const tenantId = authzQuery.data?.tenant_id ?? null
  const tenantFeatures = useMemo(
    () => new Set(authzQuery.data?.tenant_features ?? []),
    [authzQuery.data?.tenant_features],
  )
  const permissions = useMemo(
    () => new Set(authzQuery.data?.permissions ?? []),
    [authzQuery.data?.permissions],
  )

  const hasPerm = useCallback(
    (code: string) => {
      if (isSuperAdmin || permissions.has('*')) return true
      if (
        isTenantAdmin &&
        (code === 'tenant:member:manage' || code === 'tenant:role:manage')
      ) {
        return true
      }
      if (code === 'tenant:member:manage' && isWorkspaceAdmin) return true
      if (code === 'workspace:manage' && isWorkspaceAdmin) return true
      return permissions.has(code)
    },
    [isSuperAdmin, isTenantAdmin, isWorkspaceAdmin, permissions],
  )

  const setTokens = useCallback((a: string, r: string) => {
    setStoredTokens(a, r)
    setAccess(a)
    setRefresh(r)
    scheduleProactiveRefresh()
  }, [])

  const clear = useCallback(() => {
    cancelProactiveRefresh()
    clearStoredTokens()
    setAccess(null)
    setRefresh(null)
  }, [])

  const value = useMemo(
    () => ({
      accessToken,
      refreshToken,
      userId,
      workspaceId,
      workspaceRole,
      tenantRole,
      isSuperAdmin,
      isTenantAdmin,
      tenantId,
      isWorkspaceAdmin,
      tenantFeatures,
      permissions,
      hasPerm,
      isAuthenticated: Boolean(accessToken),
      setTokens,
      clear,
    }),
    [
      accessToken,
      refreshToken,
      userId,
      workspaceId,
      workspaceRole,
      tenantRole,
      isSuperAdmin,
      isTenantAdmin,
      tenantId,
      isWorkspaceAdmin,
      tenantFeatures,
      permissions,
      hasPerm,
      setTokens,
      clear,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// Fast refresh in Vite works best for component-only modules; this file intentionally exports a hook alongside the provider.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const v = useContext(AuthContext)
  if (!v) throw new Error('useAuth outside AuthProvider')
  return v
}
