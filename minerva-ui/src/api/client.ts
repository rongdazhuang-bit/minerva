import { resolveApiBaseUrl } from '@/api/config'
import {
  forceLogoutOnAuthFailure,
  getAccessToken,
  isAuthApiPath,
  refreshTokens,
} from '@/api/tokenSession'

export { apiOrigin, resolveApiBaseUrl } from '@/api/config'

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

const base = resolveApiBaseUrl()

/**
 * 带 Bearer 的 ``fetch``：临近过期主动 refresh；401 时 refresh 并重试一次。
 */
export async function authFetch(url: string, init?: RequestInit): Promise<Response> {
  const attempt = async (retried: boolean): Promise<Response> => {
    const token = await getAccessToken()
    const headers = new Headers(init?.headers)
    if (token) headers.set('Authorization', `Bearer ${token}`)
    const res = await fetch(url, { ...init, headers })
    if (res.status !== 401 || isAuthApiPath(url)) {
      return res
    }
    if (retried) {
      forceLogoutOnAuthFailure()
      return res
    }
    const ok = await refreshTokens()
    if (!ok) {
      forceLogoutOnAuthFailure()
      return res
    }
    return attempt(true)
  }
  return attempt(false)
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  const hasBody = init?.body !== undefined
  if (hasBody && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const res = await authFetch(`${base}${path}`, { ...init, headers })
  const text = await res.text()
  if (!res.ok) {
    try {
      const j = JSON.parse(text) as { code?: string; message?: string }
      throw new ApiError(j.code ?? 'error', j.message ?? text)
    } catch (e) {
      if (e instanceof ApiError) throw e
      throw new ApiError('http', text || res.statusText)
    }
  }
  if (!text) return null as T
  return JSON.parse(text) as T
}
