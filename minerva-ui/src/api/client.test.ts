import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { authFetch } from '@/api/client'
import { REFRESH_BUFFER_SEC, STORAGE_ACCESS, STORAGE_REFRESH } from '@/api/tokenSession'

function makeJwt(expSec: number): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const payload = btoa(JSON.stringify({ exp: expSec, sub: 'u1' }))
  return `${header}.${payload}.sig`
}

function installLocalStorageMock(): void {
  const store = new Map<string, string>()
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => {
      store.set(k, v)
    },
    removeItem: (k: string) => {
      store.delete(k)
    },
    clear: () => store.clear(),
  })
}

describe('authFetch', () => {
  beforeEach(() => {
    installLocalStorageMock()
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('does not refresh before POST /auth/login even with expired access token', async () => {
    const exp = Math.floor(Date.now() / 1000) + REFRESH_BUFFER_SEC - 10
    localStorage.setItem(STORAGE_ACCESS, makeJwt(exp))
    localStorage.setItem(STORAGE_REFRESH, 'refresh-old')

    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    )

    await authFetch('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: 'a@b.c', password: 'secret' }),
    })

    expect(fetch).toHaveBeenCalledTimes(1)
    expect(String(vi.mocked(fetch).mock.calls[0]?.[0])).toContain('/auth/login')
  })
})
