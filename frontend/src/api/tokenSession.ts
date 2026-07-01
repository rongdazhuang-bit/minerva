import { jwtDecode } from 'jwt-decode'

import { API_PATH_PREFIX, apiOrigin, AUTH_API_FETCH_TIMEOUT_MS } from '@/api/config'

export const STORAGE_ACCESS = 'access_token'
export const STORAGE_REFRESH = 'refresh_token'
/** Persisted login account (email) for shell display; cleared on logout. */
export const STORAGE_LOGIN_ACCOUNT = 'minerva_login_account'
/** Optional remember-me email on login form. */
export const STORAGE_REMEMBER_EMAIL = 'minerva_remember_email'

/** 在 access 过期前多少秒触发主动 refresh。 */
export const REFRESH_BUFFER_SEC = 120

type JwtExpPayload = { exp?: number }

const tokenListeners = new Set<() => void>()
let refreshInFlight: Promise<boolean> | null = null
let proactiveTimer: ReturnType<typeof setTimeout> | null = null

/** 订阅 localStorage 中 token 被本模块更新的通知（同 tab）。 */
export function subscribeTokensUpdated(listener: () => void): () => void {
  tokenListeners.add(listener)
  return () => tokenListeners.delete(listener)
}

function emitTokensUpdated(): void {
  tokenListeners.forEach((fn) => fn())
}

/** 写入新的 access/refresh 并通知订阅方。 */
export function setStoredTokens(access: string, refresh: string): void {
  localStorage.setItem(STORAGE_ACCESS, access)
  localStorage.setItem(STORAGE_REFRESH, refresh)
  emitTokensUpdated()
}

/** 清除本地 token 并通知订阅方。 */
export function clearStoredTokens(): void {
  localStorage.removeItem(STORAGE_ACCESS)
  localStorage.removeItem(STORAGE_REFRESH)
  localStorage.removeItem(STORAGE_LOGIN_ACCOUNT)
  emitTokensUpdated()
}

/** Read persisted login account for shell display. */
export function getStoredLoginAccount(): string | null {
  const v = localStorage.getItem(STORAGE_LOGIN_ACCOUNT)?.trim()
  if (v) return v
  const remembered = localStorage.getItem(STORAGE_REMEMBER_EMAIL)?.trim()
  return remembered || null
}

/** Persist login account (email) for shell display. */
export function setStoredLoginAccount(email: string): void {
  const s = email.trim()
  if (s) localStorage.setItem(STORAGE_LOGIN_ACCOUNT, s)
}

function readAccessExp(access: string): number | null {
  try {
    const p = jwtDecode(access) as JwtExpPayload
    return typeof p.exp === 'number' ? p.exp : null
  } catch {
    return null
  }
}

function accessNeedsRefresh(access: string): boolean {
  const exp = readAccessExp(access)
  if (exp == null) return true
  const now = Math.floor(Date.now() / 1000)
  return exp - now < REFRESH_BUFFER_SEC
}

/** 当前路径是否为登录/注册 UI（避免在认证页强制跳转）。 */
export function isOnAuthUi(pathname = window.location.pathname): boolean {
  const p = pathname
  return (
    p === '/login' ||
    p === '/auth/login' ||
    p.startsWith('/auth/login/') ||
    p === '/register' ||
    p === '/auth/register' ||
    p.startsWith('/auth/register/')
  )
}

function authPathname(pathOrUrl: string): string {
  if (pathOrUrl.startsWith('/')) return pathOrUrl.split('?')[0] ?? pathOrUrl
  try {
    return new URL(pathOrUrl, window.location.origin).pathname
  } catch {
    return pathOrUrl
  }
}

/** 登录/注册验证码 GET（无需 Bearer，须放行）。 */
export function isAuthCaptchaApiPath(pathOrUrl: string): boolean {
  const p = authPathname(pathOrUrl)
  return (
    p === `${API_PATH_PREFIX}/auth/login/captcha` ||
    p === `${API_PATH_PREFIX}/auth/register/captcha`
  )
}

/** 请求 URL 是否属于认证 API（不附带 token、不参与 401 自动 refresh）。 */
export function isAuthApiPath(pathOrUrl: string): boolean {
  return authPathname(pathOrUrl).startsWith(`${API_PATH_PREFIX}/auth/`)
}

/** 清 token；若不在认证页则跳转登录。 */
export function forceLogoutOnAuthFailure(): void {
  clearStoredTokens()
  if (!isOnAuthUi()) {
    window.location.assign('/login')
  }
}

/**
 * 调用 ``POST /auth/refresh`` 轮换 token；并发时复用同一 Promise。
 *
 * @returns 是否成功拿到新 access_token
 */
export async function refreshTokens(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight
  refreshInFlight = (async () => {
    const refresh = localStorage.getItem(STORAGE_REFRESH)
    if (!refresh) return false
    try {
      const res = await fetch(`${apiOrigin()}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
        signal: AbortSignal.timeout(AUTH_API_FETCH_TIMEOUT_MS),
      })
      if (!res.ok) return false
      const data = (await res.json()) as {
        access_token?: string
        refresh_token?: string
      }
      if (!data.access_token || !data.refresh_token) return false
      setStoredTokens(data.access_token, data.refresh_token)
      return true
    } catch {
      return false
    }
  })().finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}

/**
 * 返回可用于 Authorization 的 access token；临近过期时先 refresh。
 */
export async function getAccessToken(): Promise<string | null> {
  const access = localStorage.getItem(STORAGE_ACCESS)
  if (!access) return null
  if (!accessNeedsRefresh(access)) return access
  if (!localStorage.getItem(STORAGE_REFRESH)) return access
  const ok = await refreshTokens()
  if (!ok) return access
  return localStorage.getItem(STORAGE_ACCESS)
}

/** 取消已调度的主动 refresh 定时器。 */
export function cancelProactiveRefresh(): void {
  if (proactiveTimer != null) {
    clearTimeout(proactiveTimer)
    proactiveTimer = null
  }
}

/**
 * 根据当前 access 的 ``exp`` 调度一次主动 refresh（到期前 ``REFRESH_BUFFER_SEC``）。
 */
export function scheduleProactiveRefresh(): void {
  cancelProactiveRefresh()
  const access = localStorage.getItem(STORAGE_ACCESS)
  const refresh = localStorage.getItem(STORAGE_REFRESH)
  if (!access || !refresh) return

  const exp = readAccessExp(access)
  if (exp == null) return

  const nowSec = Math.floor(Date.now() / 1000)
  const triggerAtSec = exp - REFRESH_BUFFER_SEC
  const delayMs = Math.max(0, (triggerAtSec - nowSec) * 1000)

  proactiveTimer = setTimeout(() => {
    proactiveTimer = null
    void refreshTokens().then((ok) => {
      if (ok) scheduleProactiveRefresh()
    })
  }, delayMs)
}
