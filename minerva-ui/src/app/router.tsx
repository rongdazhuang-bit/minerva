import type { ReactNode } from 'react'
import { Navigate, RouterProvider, createBrowserRouter } from 'react-router-dom'
import { AppThemedLayout } from '@/app/AppThemedLayout'
import { AppLayout } from '@/app/layout/AppLayout'
import { OverviewPage } from '@/features/workspace/OverviewPage'
import { SmartReviewPage } from '@/features/workspace/SmartReviewPage'
import { RulesLibraryPage } from '@/features/workspace/RulesLibraryPage'
import { SettingsSectionLayout } from '@/features/settings/SettingsSectionLayout'
import { ModelProvidersPage } from '@/features/settings/ModelProvidersPage'
import { OcrSettingsPage } from '@/features/settings/OcrSettingsPage'
import { DataSourcesPage } from '@/features/settings/DataSourcesPage'
import { MenuConfigPage } from '@/features/settings/MenuConfigPage'
import { UsersPage } from '@/features/settings/UsersPage'
import { RolesPage } from '@/features/settings/RolesPage'
import { DictionaryPage } from '@/features/settings/DictionaryPage'
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
          { path: 'rules', element: <RulesLibraryPage /> },
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
