/**
 * 未设置 VITE_API_BASE_URL 时，生产构建用同源相对路径；
 * 开发环境默认连本机 FastAPI，避免把 /auth 等误发到 Vite（5173）而 404。
 */
function resolveApiBaseUrl(): string {
  const v = import.meta.env.VITE_API_BASE_URL
  if (v != null && String(v).trim() !== '') {
    return String(v).replace(/\/$/, '')
  }
  if (import.meta.env.DEV) {
    return 'http://127.0.0.1:8000'
  }
  return ''
}

const base = resolveApiBaseUrl()

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  const token = localStorage.getItem('access_token')
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const hasBody = init?.body !== undefined
  if (hasBody && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const res = await fetch(`${base}${path}`, { ...init, headers })
  const text = await res.text()
  if (res.status === 401) {
    if (!path.startsWith('/auth/')) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      const p = window.location.pathname
      const onAuthUi =
        p === '/login' ||
        p === '/auth/login' ||
        p.startsWith('/auth/login/') ||
        p === '/register' ||
        p === '/auth/register' ||
        p.startsWith('/auth/register/')
      if (!onAuthUi) {
        window.location.assign('/login')
      }
    }
  }
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
