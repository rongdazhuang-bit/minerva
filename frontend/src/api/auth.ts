import { apiJson, publicApiJson } from '@/api/client'
import type { TokenResponse } from '@/api/types'

export type AuthCaptchaResponse = {
  captcha_id: string
  image: string
}

export type AuthCaptchaScope = 'login' | 'register'

/** Fetch a fresh CAPTCHA image (data URL); public, no login required. */
export function fetchAuthCaptchaApi(scope: AuthCaptchaScope) {
  return publicApiJson<AuthCaptchaResponse>(`/auth/${scope}/captcha`)
}

/** @deprecated Use fetchAuthCaptchaApi('login') */
export function fetchLoginCaptchaApi() {
  return fetchAuthCaptchaApi('login')
}

export function loginApi(
  email: string,
  password: string,
  captchaId: string,
  captchaCode: string,
) {
  return apiJson<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({
      email,
      password,
      captcha_id: captchaId,
      captcha_code: captchaCode,
    }),
  })
}

export function registerApi(
  email: string,
  password: string,
  captchaId: string,
  captchaCode: string,
) {
  return apiJson<TokenResponse>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({
      email,
      password,
      captcha_id: captchaId,
      captcha_code: captchaCode,
    }),
  })
}
