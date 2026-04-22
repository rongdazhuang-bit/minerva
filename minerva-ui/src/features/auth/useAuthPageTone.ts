import { useCallback, useEffect, useLayoutEffect, useState } from 'react'
import type { AuthTone } from '@/features/auth/authTheme'
import { persistAuthTone, readStoredAuthTone } from '@/features/auth/authTheme'

export function useAuthPageTone() {
  const [tone, setToneState] = useState<AuthTone>(() => readStoredAuthTone())

  useEffect(() => {
    persistAuthTone(tone)
  }, [tone])

  /** 与 .login-shell / html 根背景一致，避免右侧槽位与主区色差 */
  useLayoutEffect(() => {
    const root = document.documentElement
    root.classList.toggle('minerva-auth-tone-amber', tone === 'amber')
    return () => {
      root.classList.remove('minerva-auth-tone-amber')
    }
  }, [tone])

  const setTone = useCallback((t: AuthTone) => {
    setToneState(t)
  }, [])

  const toggleTone = useCallback(() => {
    setToneState((p) => (p === 'blue' ? 'amber' : 'blue'))
  }, [])

  return { tone, setTone, toggleTone }
}
