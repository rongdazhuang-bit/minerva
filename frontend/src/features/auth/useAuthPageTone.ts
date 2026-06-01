import { useCallback, useEffect, useLayoutEffect, useState } from 'react'
import {
  AUTH_TONES,
  type AuthTone,
  persistAuthTone,
  readStoredAuthTone,
  syncMinervaToneClass,
} from '@/features/auth/authTheme'

/**
 * Tone state for login/register. Applies `minerva-tone-*` to `<html>` before paint,
 * then persists; broadcast lets the authenticated shell update if already mounted.
 */
export function useAuthPageTone() {
  const [tone, setToneState] = useState<AuthTone>(() => readStoredAuthTone())

  useLayoutEffect(() => {
    syncMinervaToneClass(tone)
  }, [tone])

  useEffect(() => {
    persistAuthTone(tone)
  }, [tone])

  const setTone = useCallback((t: AuthTone) => {
    setToneState(t)
  }, [])

  const toggleTone = useCallback(() => {
    setToneState((p) => {
      const i = AUTH_TONES.indexOf(p)
      return AUTH_TONES[(i + 1) % AUTH_TONES.length]!
    })
  }, [])

  return { tone, setTone, toggleTone }
}
