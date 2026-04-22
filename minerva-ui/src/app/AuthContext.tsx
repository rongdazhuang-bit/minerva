import { jwtDecode } from 'jwt-decode'
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

const STORAGE_A = 'access_token'
const STORAGE_R = 'refresh_token'

type JwtPayload = { wid?: string }

function readWidFromToken(access: string | null): string | null {
  if (!access) return null
  try {
    const p = jwtDecode(access) as JwtPayload
    return p.wid ?? null
  } catch {
    return null
  }
}

type AuthValue = {
  accessToken: string | null
  refreshToken: string | null
  workspaceId: string | null
  isAuthenticated: boolean
  setTokens: (a: string, r: string) => void
  clear: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [accessToken, setAccess] = useState<string | null>(() =>
    localStorage.getItem(STORAGE_A),
  )
  const [refreshToken, setRefresh] = useState<string | null>(() =>
    localStorage.getItem(STORAGE_R),
  )
  const workspaceId = useMemo(
    () => readWidFromToken(accessToken),
    [accessToken],
  )

  const setTokens = useCallback((a: string, r: string) => {
    localStorage.setItem(STORAGE_A, a)
    localStorage.setItem(STORAGE_R, r)
    setAccess(a)
    setRefresh(r)
  }, [])

  const clear = useCallback(() => {
    localStorage.removeItem(STORAGE_A)
    localStorage.removeItem(STORAGE_R)
    setAccess(null)
    setRefresh(null)
  }, [])

  const value = useMemo(
    () => ({
      accessToken,
      refreshToken,
      workspaceId,
      isAuthenticated: Boolean(accessToken),
      setTokens,
      clear,
    }),
    [accessToken, refreshToken, workspaceId, setTokens, clear],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const v = useContext(AuthContext)
  if (!v) throw new Error('useAuth outside AuthProvider')
  return v
}
