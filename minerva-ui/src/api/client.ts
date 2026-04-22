const base = import.meta.env.VITE_API_BASE_URL ?? ''

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
      if (!window.location.pathname.startsWith('/login')) {
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
