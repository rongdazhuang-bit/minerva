import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  REFRESH_BUFFER_SEC,
  STORAGE_ACCESS,
  STORAGE_REFRESH,
  clearStoredTokens,
  getAccessToken,
  isAuthApiPath,
  isOnAuthUi,
  refreshTokens,
  setStoredTokens,
} from '@/api/tokenSession'

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

describe('tokenSession', () => {
  beforeEach(() => {
    installLocalStorageMock()
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('isAuthApiPath matches /auth routes', () => {
    expect(isAuthApiPath('/auth/login')).toBe(true)
    expect(isAuthApiPath('/workspaces/w1/dicts')).toBe(false)
  })

  it('isOnAuthUi matches login and register paths', () => {
    expect(isOnAuthUi('/login')).toBe(true)
    expect(isOnAuthUi('/workspace')).toBe(false)
  })

  it('getAccessToken returns token when not near expiry', async () => {
    const exp = Math.floor(Date.now() / 1000) + 3600
    const access = makeJwt(exp)
    localStorage.setItem(STORAGE_ACCESS, access)
    await expect(getAccessToken()).resolves.toBe(access)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('getAccessToken refreshes when within buffer window', async () => {
    const exp = Math.floor(Date.now() / 1000) + REFRESH_BUFFER_SEC - 10
    const oldAccess = makeJwt(exp)
    const newAccess = makeJwt(exp + 3600)
    localStorage.setItem(STORAGE_ACCESS, oldAccess)
    localStorage.setItem(STORAGE_REFRESH, 'refresh-old')
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({ access_token: newAccess, refresh_token: 'refresh-new' }),
        { status: 200 },
      ),
    )
    await expect(getAccessToken()).resolves.toBe(newAccess)
    expect(localStorage.getItem(STORAGE_ACCESS)).toBe(newAccess)
  })

  it('refreshTokens dedupes concurrent calls', async () => {
    localStorage.setItem(STORAGE_REFRESH, 'r1')
    let resolveFetch!: (v: Response) => void
    const pending = new Promise<Response>((r) => {
      resolveFetch = r
    })
    vi.mocked(fetch).mockReturnValueOnce(pending as Promise<Response>)
    const p1 = refreshTokens()
    const p2 = refreshTokens()
    resolveFetch(
      new Response(
        JSON.stringify({
          access_token: makeJwt(Math.floor(Date.now() / 1000) + 3600),
          refresh_token: 'r2',
        }),
        { status: 200 },
      ),
    )
    const [a, b] = await Promise.all([p1, p2])
    expect(a).toBe(true)
    expect(b).toBe(true)
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('clearStoredTokens removes both keys', () => {
    setStoredTokens('a', 'r')
    clearStoredTokens()
    expect(localStorage.getItem(STORAGE_ACCESS)).toBeNull()
    expect(localStorage.getItem(STORAGE_REFRESH)).toBeNull()
  })
})
