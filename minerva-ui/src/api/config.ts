/**
 * 未设置 VITE_API_BASE_URL 时，生产构建用同源相对路径；
 * 开发环境默认连本机 FastAPI，避免把 /auth 等误发到 Vite（5173）而 404。
 */
export function resolveApiBaseUrl(): string {
  const v = import.meta.env.VITE_API_BASE_URL
  if (v != null && String(v).trim() !== '') {
    return String(v).replace(/\/$/, '')
  }
  if (import.meta.env.DEV) {
    return 'http://127.0.0.1:8000'
  }
  return ''
}

/** API 根地址（无尾部斜杠）。 */
export function apiOrigin(): string {
  return resolveApiBaseUrl()
}
