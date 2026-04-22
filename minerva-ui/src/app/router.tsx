import type { ReactNode } from 'react'
import { Navigate, RouterProvider, createBrowserRouter } from 'react-router-dom'
import { AppLayout } from '@/app/layout/AppLayout'
import { LoginPage } from '@/features/auth/LoginPage'
import { RegisterPage } from '@/features/auth/RegisterPage'
import { ExecutionsListPage } from '@/features/executions/ExecutionsListPage'
import { RuleEditorPage } from '@/features/designer/RuleEditorPage'
import { RulesListPage } from '@/features/rules/RulesListPage'
import { ExecutionDetailPage } from '@/features/executions/ExecutionDetailPage'
import { useAuth } from './AuthContext'

function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

const router = createBrowserRouter([
  { path: '/', element: <Navigate to="/app/rules" replace /> },
  { path: '/login', element: <LoginPage /> },
  { path: '/register', element: <RegisterPage /> },
  {
    path: '/app',
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to="rules" replace /> },
      { path: 'rules', element: <RulesListPage /> },
      { path: 'rules/:ruleId/edit', element: <RuleEditorPage /> },
      { path: 'executions', element: <ExecutionsListPage /> },
      { path: 'executions/:executionId', element: <ExecutionDetailPage /> },
    ],
  },
])

export function AppRouter() {
  return <RouterProvider router={router} />
}
