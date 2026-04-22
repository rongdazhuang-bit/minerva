import { useCallback, useEffect, useState } from 'react'
import type { AuthTone } from '@/features/auth/authTheme'
import { persistAuthTone, readStoredAuthTone } from '@/features/auth/authTheme'

export function useAuthPageTone() {
  const [tone, setToneState] = useState<AuthTone>(() => readStoredAuthTone())

  useEffect(() => {
    persistAuthTone(tone)
  }, [tone])

  const setTone = useCallback((t: AuthTone) => {
    setToneState(t)
  }, [])

  const toggleTone = useCallback(() => {
    setToneState((p) => (p === 'blue' ? 'amber' : 'blue'))
  }, [])

  return { tone, setTone, toggleTone }
}
