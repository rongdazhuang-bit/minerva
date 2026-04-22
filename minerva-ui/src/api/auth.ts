import { apiJson } from '@/api/client'
import type { TokenResponse } from '@/api/types'

export function loginApi(email: string, password: string) {
  return apiJson<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function registerApi(email: string, password: string) {
  return apiJson<TokenResponse>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}
