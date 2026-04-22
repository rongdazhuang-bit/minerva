import { useEffect, useLayoutEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  MINERVA_TONE_EVENT,
  type AuthTone,
  readStoredAuthTone,
} from '@/features/auth/authTheme'

export function useMinervaTone(): AuthTone {
  const { pathname } = useLocation()
  const [tone, setTone] = useState<AuthTone>(() => readStoredAuthTone())

  useLayoutEffect(() => {
    setTone(readStoredAuthTone())
  }, [pathname])

  useEffect(() => {
    const h = () => setTone(readStoredAuthTone())
    window.addEventListener(MINERVA_TONE_EVENT, h)
    return () => window.removeEventListener(MINERVA_TONE_EVENT, h)
  }, [])

  return tone
}
