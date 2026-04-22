import zhCN from 'antd/locale/zh_CN'
import { ConfigProvider } from 'antd'
import { useEffect, useLayoutEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import {
  MINERVA_TONE_EVENT,
  getAppLayoutTheme,
  readStoredAuthTone,
  type AuthTone,
} from '@/features/auth/authTheme'

export function AppThemedLayout() {
  const { pathname } = useLocation()
  const [tone, setTone] = useState<AuthTone>(() => readStoredAuthTone())

  useLayoutEffect(() => {
    setTone(readStoredAuthTone())
  }, [pathname])

  useEffect(() => {
    const onTone = () => setTone(readStoredAuthTone())
    window.addEventListener(MINERVA_TONE_EVENT, onTone)
    return () => window.removeEventListener(MINERVA_TONE_EVENT, onTone)
  }, [])

  useLayoutEffect(() => {
    document.documentElement.classList.toggle('minerva-auth-tone-amber', tone === 'amber')
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
