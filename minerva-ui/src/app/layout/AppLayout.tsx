import {
  ApiOutlined,
  BarChartOutlined,
  BookOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  IdcardOutlined,
  MenuOutlined,
  ScanOutlined,
  SettingOutlined,
  TagsOutlined,
  UnorderedListOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Layout, Menu } from 'antd'
import { AppBreadcrumb } from '@/app/layout/AppBreadcrumb'
import { AppHeaderToolbar } from '@/app/layout/AppHeaderToolbar'
import type { CSSProperties } from 'react'
import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '@/app/AuthContext'
import { useMinervaTone } from '@/app/useMinervaTone'
import { SIDER_MIN_PX, useResizableSiderWidth } from '@/app/layout/useResizableSiderWidth'
import './appSiderResize.css'
import './appSiderMenu.css'
import './appLayoutScroll.css'

const { Sider, Header, Content } = Layout

const SUB_SETTINGS = 'sub-settings'
const SUB_RULES = 'sub-rules'

const siderStyle: CSSProperties = {
  background: 'var(--minerva-surface, #1b2838)',
  borderRight: '1px solid var(--minerva-border, #2d3f55)',
  height: '100%',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
}

const brandBase: CSSProperties = {
  color: 'var(--minerva-primary, #38bdf8)',
  fontSize: 18,
  fontWeight: 600,
  fontFamily: "'Fraunces', Georgia, serif",
  letterSpacing: 0.04,
  lineHeight: '56px',
  whiteSpace: 'nowrap',
}

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  flex: '0 0 auto',
  flexShrink: 0,
  width: '100%',
  background: 'var(--minerva-surface, #1b2838)',
  borderBottom: '1px solid var(--minerva-border, #2d3f55)',
  paddingInline: 20,
  height: 56,
  lineHeight: 1,
  overflow: 'visible',
  zIndex: 20,
}

const bodyRowStyle: CSSProperties = {
  flex: 1,
  minHeight: 0,
  display: 'flex',
  flexDirection: 'row',
  alignItems: 'stretch',
  overflow: 'hidden',
  background: 'var(--minerva-bg, #121a21)',
}

const contentOuterStyle: CSSProperties = {
  flex: 1,
  minWidth: 0,
  minHeight: 0,
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
  background: 'var(--minerva-bg, #121a21)',
  padding: 0,
}

const contentScrollStyle: CSSProperties = {
  flex: 1,
  minHeight: 0,
  display: 'flex',
  flexDirection: 'column',
  overflow: 'auto',
  overflowX: 'hidden',
  WebkitOverflowScrolling: 'touch',
  padding: 20,
}

function menuKeyForPath(pathname: string): string {
  if (pathname.startsWith('/app/settings/models')) return 'settings-models'
  if (pathname.startsWith('/app/settings/ocr')) return 'settings-ocr'
  if (pathname.startsWith('/app/settings/data-sources')) return 'settings-data-sources'
  if (pathname.startsWith('/app/settings/menus')) return 'settings-menus'
  if (pathname.startsWith('/app/settings/users')) return 'settings-users'
  if (pathname.startsWith('/app/settings/roles')) return 'settings-roles'
  if (pathname.startsWith('/app/settings/dictionary')) return 'settings-dictionary'
  if (pathname.startsWith('/app/settings')) return 'settings-models'
  if (pathname.startsWith('/app/smart-review')) return 'smart-review'
  if (pathname.startsWith('/app/file-ocr')) return 'file-ocr'
  if (pathname.startsWith('/app/rules/management')) return 'rules-mgmt-list'
  if (pathname.startsWith('/app/rules/overview')) return 'rules-overview'
  if (pathname.startsWith('/app/rules')) return 'rules-overview'
  return 'overview'
}

export function AppLayout() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const { pathname } = useLocation()
  const { clear } = useAuth()
  const tone = useMinervaTone()
  const shellLight = tone === 'sunshine'
  const { rowRef, siderWidth, onResizeStart } = useResizableSiderWidth()

  const selectedKeys = useMemo(() => [menuKeyForPath(pathname)], [pathname])

  const [menuOpenKeys, setMenuOpenKeys] = useState<string[]>([])

  useEffect(() => {
    setMenuOpenKeys((prev) => {
      let next = [...prev]
      if (pathname.startsWith('/app/settings')) {
        if (!next.includes(SUB_SETTINGS)) next.push(SUB_SETTINGS)
      } else {
        next = next.filter((k) => k !== SUB_SETTINGS)
      }
      if (pathname.startsWith('/app/rules')) {
        if (!next.includes(SUB_RULES)) next.push(SUB_RULES)
      } else {
        next = next.filter((k) => k !== SUB_RULES)
      }
      return next
    })
  }, [pathname])

  const showBreadcrumb = useMemo(() => {
    if (pathname === '/app/overview' || pathname === '/app/overview/') return false
    return true
  }, [pathname])

  const onLogout = useCallback(() => {
    clear()
    void nav('/login')
  }, [clear, nav])

  useLayoutEffect(() => {
    document.documentElement.classList.add('minerva-app-shell')
    return () => {
      document.documentElement.classList.remove('minerva-app-shell')
    }
  }, [])

  return (
    <Layout
      className="minerva-app-layout"
      style={{
        flex: 1,
        minHeight: 0,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        background: 'var(--minerva-bg, #121a21)',
        color: 'var(--minerva-ink, #e8f0f8)',
      }}
    >
      <Header style={headerStyle}>
        <div style={brandBase}>{t('appName')}</div>
        <AppHeaderToolbar onLogout={onLogout} />
      </Header>

      <div ref={rowRef} className="minerva-app-body-row" style={bodyRowStyle}>
        <Sider
          width={siderWidth}
          style={{
            ...siderStyle,
            flex: '0 0 auto',
            maxWidth: '20%',
            minWidth: SIDER_MIN_PX,
          }}
          theme={shellLight ? 'light' : 'dark'}
        >
          <div
            className="minerva-app-sider-scroll"
            style={{ flex: 1, minHeight: 0, overflow: 'auto' }}
          >
            <Menu
              mode="inline"
              className="minerva-app-sider-menu"
              theme={shellLight ? 'light' : 'dark'}
              style={{ background: 'transparent', border: 'none', paddingTop: 8 }}
              selectedKeys={selectedKeys}
              openKeys={menuOpenKeys}
              onOpenChange={setMenuOpenKeys}
              items={[
                {
                  key: 'overview',
                  icon: <BarChartOutlined />,
                  label: t('nav.overview'),
                  onClick: () => void nav('/app/overview'),
                },
                {
                  key: 'smart-review',
                  icon: <FileSearchOutlined />,
                  label: t('nav.smartReview'),
                  onClick: () => void nav('/app/smart-review'),
                },
                {
                  key: SUB_RULES,
                  icon: <BookOutlined />,
                  label: t('nav.rules'),
                  children: [
                    {
                      key: 'rules-overview',
                      icon: <DashboardOutlined />,
                      label: t('nav.rulesOverview'),
                      onClick: () => void nav('/app/rules/overview'),
                    },
                    {
                      key: 'rules-mgmt-list',
                      icon: <UnorderedListOutlined />,
                      label: t('nav.rulesManagementList'),
                      onClick: () => void nav('/app/rules/management'),
                    },
                  ],
                },
                {
                  key: 'file-ocr',
                  icon: <ScanOutlined />,
                  label: t('nav.rulesFileOcr'),
                  onClick: () => void nav('/app/file-ocr'),
                },
                {
                  key: SUB_SETTINGS,
                  icon: <SettingOutlined />,
                  label: t('nav.settings'),
                  children: [
                    {
                      key: 'settings-models',
                      icon: <ApiOutlined />,
                      label: t('settings.models'),
                      onClick: () => void nav('/app/settings/models'),
                    },
                    {
                      key: 'settings-ocr',
                      icon: <FileTextOutlined />,
                      label: t('settings.ocr'),
                      onClick: () => void nav('/app/settings/ocr'),
                    },
                    {
                      key: 'settings-data-sources',
                      icon: <DatabaseOutlined />,
                      label: t('settings.dataSources'),
                      onClick: () => void nav('/app/settings/data-sources'),
                    },
                    {
                      key: 'settings-menus',
                      icon: <MenuOutlined />,
                      label: t('settings.menuConfig'),
                      onClick: () => void nav('/app/settings/menus'),
                    },
                    {
                      key: 'settings-users',
                      icon: <UserOutlined />,
                      label: t('settings.users'),
                      onClick: () => void nav('/app/settings/users'),
                    },
                    {
                      key: 'settings-roles',
                      icon: <IdcardOutlined />,
                      label: t('settings.roles'),
                      onClick: () => void nav('/app/settings/roles'),
                    },
                    {
                      key: 'settings-dictionary',
                      icon: <TagsOutlined />,
                      label: t('settings.dictionary'),
                      onClick: () => void nav('/app/settings/dictionary'),
                    },
                  ],
                },
              ]}
            />
          </div>
        </Sider>
        <div
          className="minerva-sider-resize-handle"
          role="separator"
          aria-orientation="vertical"
          aria-label={t('layout.siderResize')}
          aria-valuenow={siderWidth}
          title={t('layout.siderResize')}
          onMouseDown={onResizeStart}
        />
        <Content style={contentOuterStyle}>
          {showBreadcrumb ? (
            <div
              style={{
                flexShrink: 0,
                padding: '12px 20px 10px',
                borderBottom: '1px solid var(--minerva-border, #2d3f55)',
              }}
            >
              <AppBreadcrumb />
            </div>
          ) : null}
          <div className="minerva-app-main-scroll" style={contentScrollStyle}>
            <Outlet />
          </div>
        </Content>
      </div>
    </Layout>
  )
}
