import zhCN from 'antd/locale/zh_CN'
import { ConfigProvider, theme } from 'antd'
import type { ReactNode } from 'react'
import { AuthProvider } from '@/app/AuthContext'

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#c9a227',
          borderRadius: 6,
          fontFamily: "'DM Sans', system-ui, sans-serif",
        },
      }}
      wave={{ disabled: true }}
    >
      <AuthProvider>{children}</AuthProvider>
    </ConfigProvider>
  )
}
