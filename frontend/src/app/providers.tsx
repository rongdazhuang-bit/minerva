/** Wraps TanStack Query and auth context around routed subtree. */

import { QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { AuthProvider } from '@/app/AuthContext'
import { queryClient } from '@/lib/queryClient'
import './providers.css'

/** Shell combining react-query and authentication providers. */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <div className="minerva-spa-wrapper">{children}</div>
      </AuthProvider>
    </QueryClientProvider>
  )
}
