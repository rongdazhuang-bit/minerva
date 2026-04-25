/** OCR 工具认证方式：与数据字典 AUTH_TYPE 明细 code 一致（大写）。 */

export const OCR_AUTH_NONE = 'NONE'
export const OCR_AUTH_BASIC = 'BASIC'
export const OCR_AUTH_API_KEY = 'API_KEY'

const LEGACY_TO_CANON: Record<string, string> = {
  none: OCR_AUTH_NONE,
  basic: OCR_AUTH_BASIC,
  api_key: OCR_AUTH_API_KEY,
}

/** 将历史小写枚举转为标准值；未知格式则原样返回（trim 后）。 */
export function canonicalOcrAuthType(code: string | null | undefined): string {
  if (code == null) return ''
  const k = String(code).trim()
  if (k === '') return ''
  const hit = LEGACY_TO_CANON[k.toLowerCase()]
  return hit ?? k
}

export function isOcrBasicAuth(code: string | null | undefined): boolean {
  return canonicalOcrAuthType(code) === OCR_AUTH_BASIC
}

export function isOcrApiKeyAuth(code: string | null | undefined): boolean {
  return canonicalOcrAuthType(code) === OCR_AUTH_API_KEY
}
