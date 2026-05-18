/**
 * 未设置 VITE_API_BASE_URL 时，生产构建用同源相对路径；
 * 开发环境默认走 Vite 同源代理（见 vite.config.ts），便于局域网设备访问 dev server。
 */
export function resolveApiBaseUrl(): string {
  const v = import.meta.env.VITE_API_BASE_URL
  if (v != null && String(v).trim() !== '') {
    return String(v).replace(/\/$/, '')
  }
  return ''
}

/** API 根地址（无尾部斜杠）。 */
export function apiOrigin(): string {
  return resolveApiBaseUrl()
}
