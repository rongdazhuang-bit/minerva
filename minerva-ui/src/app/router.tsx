import type { ReactNode } from 'react'
import { Navigate, RouterProvider, createBrowserRouter } from 'react-router-dom'
import { AppThemedLayout } from '@/app/AppThemedLayout'
import { AppLayout } from '@/app/layout/AppLayout'
import { OverviewPage } from '@/features/workspace/OverviewPage'
import { SmartReviewPage } from '@/features/workspace/SmartReviewPage'
import { RulesFileOcrPage } from '@/features/workspace/RulesFileOcrPage'
import { RulesManagementPage, RulesOverviewPage, RulesSectionLayout } from '@/features/rules'
import { DataSourcesPage } from '@/features/settings/data-sources'
import { DictionaryPage } from '@/features/settings/dictionary'
import { SettingsSectionLayout } from '@/features/settings/layout'
import { MenuConfigPage } from '@/features/settings/menu-config'
import { ModelProvidersPage } from '@/features/settings/model-providers'
import { OcrSettingsPage } from '@/features/settings/ocr'
import { RolesPage } from '@/features/settings/roles'
import { UsersPage } from '@/features/settings/users'
import { LoginPage } from '@/features/auth/LoginPage'
import { RegisterPage } from '@/features/auth/RegisterPage'
import { useAuth } from './AuthContext'

function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

const router = createBrowserRouter([
  {
    element: <AppThemedLayout />,
    children: [
      { path: '/', element: <Navigate to="/app/overview" replace /> },
      { path: '/login', element: <LoginPage /> },
      { path: '/register', element: <RegisterPage /> },
      { path: '/auth/login', element: <LoginPage /> },
      { path: '/auth/register', element: <RegisterPage /> },
      {
        path: '/app',
        element: (
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        ),
        children: [
          { index: true, element: <Navigate to="overview" replace /> },
          { path: 'overview', element: <OverviewPage /> },
          { path: 'smart-review', element: <SmartReviewPage /> },
          {
            path: 'rules',
            element: <RulesSectionLayout />,
            children: [
              { index: true, element: <Navigate to="overview" replace /> },
              { path: 'overview', element: <RulesOverviewPage /> },
              { path: 'management', element: <RulesManagementPage /> },
            ],
          },
          { path: 'file-ocr', element: <RulesFileOcrPage /> },
          {
            path: 'settings',
            element: <SettingsSectionLayout />,
            children: [
              { index: true, element: <Navigate to="models" replace /> },
              { path: 'models', element: <ModelProvidersPage /> },
              { path: 'ocr', element: <OcrSettingsPage /> },
              { path: 'data-sources', element: <DataSourcesPage /> },
              { path: 'menus', element: <MenuConfigPage /> },
              { path: 'users', element: <UsersPage /> },
              { path: 'roles', element: <RolesPage /> },
              { path: 'dictionary', element: <DictionaryPage /> },
            ],
          },
        ],
      },
    ],
  },
])

export function AppRouter() {
  return <RouterProvider router={router} />
}
