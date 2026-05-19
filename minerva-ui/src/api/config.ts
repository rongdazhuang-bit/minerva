/** 认证相关 ``fetch`` 超时（毫秒），避免后端/代理不可达时无限挂起。 */
export const AUTH_API_FETCH_TIMEOUT_MS = 15_000

/** 规则润色等 LLM 调用超时（毫秒），与后端 ``AI_HTTP_READ_TIMEOUT``（默认 120s）对齐并留余量。 */
export const AI_LLM_FETCH_TIMEOUT_MS = 130_000

/**
 * 未设置 VITE_API_BASE_URL 时，生产构建用同源相对路径；
 * 开发环境默认走 Vite 同源代理（见 vite.config.ts），浏览器使用 http://localhost:5173。
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
