import { apiJson, publicApiJson } from '@/api/client'
import type { TokenResponse } from '@/api/types'

export type AuthCaptchaResponse = {
  captcha_id: string
  image: string
}

export type AuthCaptchaScope = 'login' | 'register'

/** Authorization summary from GET /auth/me/authorization. */
export type AuthorizationSummary = {
  email: string
  is_super_admin: boolean
  tenant_id: string | null
  tenant_name: string | null
  workspace_id: string | null
  workspace_role: string | null
  tenant_role: string | null
  is_tenant_admin: boolean
  tenant_features: string[]
  permissions: string[]
  menu_paths: string[]
}

/** Fetch a fresh CAPTCHA image (data URL); public, no login required. */
export function fetchAuthCaptchaApi(scope: AuthCaptchaScope) {
  return publicApiJson<AuthCaptchaResponse>(`/auth/${scope}/captcha`)
}

/** @deprecated Use fetchAuthCaptchaApi('login') */
export function fetchLoginCaptchaApi() {
  return fetchAuthCaptchaApi('login')
}

/** Authenticate and return bearer tokens. */
export function loginApi(
  email: string,
  password: string,
  captchaId: string,
  captchaCode: string,
) {
  return publicApiJson<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({
      email,
      password,
      captcha_id: captchaId,
      captcha_code: captchaCode,
    }),
  })
}

/** Register a new account and return bearer tokens. */
export function registerApi(
  email: string,
  password: string,
  captchaId: string,
  captchaCode: string,
) {
  return publicApiJson<TokenResponse>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({
      email,
      password,
      captcha_id: captchaId,
      captcha_code: captchaCode,
    }),
  })
}

/** Load effective permissions for the current session. */
export function fetchAuthorization() {
  return apiJson<AuthorizationSummary>('/auth/me/authorization')
}
