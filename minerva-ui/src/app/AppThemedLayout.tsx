import zhCN from 'antd/locale/zh_CN'
import { ConfigProvider } from 'antd'
import { useEffect, useLayoutEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import {
  MINERVA_TONE_EVENT,
  getAppLayoutTheme,
  readStoredAuthTone,
  syncMinervaToneClass,
  type AuthTone,
} from '@/features/auth/authTheme'

/** Wraps `/app` routes: zh locale, antd theme, and global tone from localStorage + `MINERVA_TONE_EVENT`. */
export function AppThemedLayout() {
  const { pathname } = useLocation()
  const [tone, setTone] = useState<AuthTone>(() => readStoredAuthTone())

  // e.g. after login navigation: re-read so shell matches the tone saved on the auth page
  useLayoutEffect(() => {
    setTone(readStoredAuthTone())
  }, [pathname])

  useEffect(() => {
    const onTone = () => setTone(readStoredAuthTone())
    window.addEventListener(MINERVA_TONE_EVENT, onTone)
    return () => window.removeEventListener(MINERVA_TONE_EVENT, onTone)
  }, [])

  useLayoutEffect(() => {
    syncMinervaToneClass(tone)
  }, [tone])

  return (
    <ConfigProvider
      locale={zhCN}
      theme={getAppLayoutTheme(tone)}
      wave={{ disabled: true }}
    >
      <div className="minerva-route-surface">
        <Outlet />
      </div>
    </ConfigProvider>
  )
}
