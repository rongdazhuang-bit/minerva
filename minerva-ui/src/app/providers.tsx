import type { ReactNode } from 'react'
import { AuthProvider } from '@/app/AuthContext'
import './providers.css'

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <div className="minerva-spa-wrapper">{children}</div>
    </AuthProvider>
  )
}
