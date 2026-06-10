import { MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons'
import { Button, Layout, Menu } from 'antd'
import { AppBreadcrumb } from '@/app/layout/AppBreadcrumb'
import { AppHeaderToolbar } from '@/app/layout/AppHeaderToolbar'
import type { CSSProperties } from 'react'
import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { getAgentV2Config } from '@/api/agent'
import { listNavMenus, type SysMenuNode } from '@/api/menus'
import { useAuth } from '@/app/AuthContext'
import { buildSiderMenuItems } from '@/app/layout/buildSiderMenuItems'
import { resolveMenuNavState } from '@/app/layout/menuNavMatch'
import { subscribeMenuNavRefresh } from '@/app/menuNavRefresh'
import { useMinervaTone } from '@/app/useMinervaTone'
import {
  SIDER_COLLAPSED_PX,
  SIDER_MIN_PX,
  useResizableSiderWidth,
} from '@/app/layout/useResizableSiderWidth'
import './appSiderResize.css'
import './appSiderMenu.css'
import './appLayoutScroll.css'

const { Sider, Header, Content } = Layout

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
  overflowY: 'auto',
  overflowX: 'hidden',
  WebkitOverflowScrolling: 'touch',
  padding: 20,
}

/** 智能体路由：顶/底由页内承担；左缘略收紧使对话区向左靠，右缘保持 20px 与面包屑/滚动条习惯一致。 */
function contentScrollStyleForPath(pathname: string): CSSProperties {
  if (pathname.startsWith('/app/agents/chat')) {
    return {
      ...contentScrollStyle,
      padding: '0 20px 0 10px',
      /* 历史侧栏与主区各自滚动，避免滚轮被外层主内容区抢走 */
      overflowY: 'hidden',
      overflowX: 'hidden',
    }
  }
  if (pathname.startsWith('/app/agents/memory')) {
    return {
      ...contentScrollStyle,
      overflowY: 'hidden',
      overflowX: 'hidden',
    }
  }
  if (pathname.startsWith('/app/settings/menus')) {
    return {
      ...contentScrollStyle,
      overflowY: 'hidden',
      overflowX: 'hidden',
    }
  }
  return contentScrollStyle
}

export function AppLayout() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const { pathname } = useLocation()
  const { clear, workspaceId, isAuthenticated } = useAuth()
  const [memoryBackend, setMemoryBackend] = useState('sql')
  const [navMenus, setNavMenus] = useState<SysMenuNode[]>([])
  const [navMenusRev, setNavMenusRev] = useState(0)
  const tone = useMinervaTone()
  const shellLight = tone === 'sunshine'
  const {
    rowRef,
    siderWidth,
    collapsed,
    toggleCollapsed,
    onResizeStart,
    onResizeTouchStart,
  } = useResizableSiderWidth()

  const hideMenuKeys = useMemo(
    () => (memoryBackend !== 'mem0' ? new Set(['agents-memory']) : undefined),
    [memoryBackend],
  )

  const menuNavState = useMemo(
    () => resolveMenuNavState(navMenus, pathname, hideMenuKeys),
    [navMenus, pathname, hideMenuKeys],
  )

  const selectedKeys = useMemo(
    () => (menuNavState.selectedKey ? [menuNavState.selectedKey] : []),
    [menuNavState.selectedKey],
  )

  const mainScrollStyle = useMemo(
    () => contentScrollStyleForPath(pathname),
    [pathname],
  )

  const [menuOpenKeys, setMenuOpenKeys] = useState<string[]>([])

  /** 展开态用受控 openKeys；折叠态不传 openKeys，由 Menu 以浮层展示并可点击子项。 */
  const siderMenuModeProps = useMemo(
    () =>
      collapsed
        ? {
            triggerSubMenuAction: 'click' as const,
            getPopupContainer: () => document.body,
            popupClassName: 'minerva-app-sider-menu-popup',
          }
        : {
            openKeys: menuOpenKeys,
            onOpenChange: setMenuOpenKeys,
          },
    [collapsed, menuOpenKeys],
  )

  useEffect(() => {
    if (!workspaceId) return
    void getAgentV2Config(workspaceId)
      .then((c) => setMemoryBackend(c.memory_backend))
      .catch(() => setMemoryBackend('sql'))
  }, [workspaceId])

  useEffect(() => subscribeMenuNavRefresh(() => setNavMenusRev((v) => v + 1)), [])

  useEffect(() => {
    if (!isAuthenticated) {
      setNavMenus([])
      return
    }
    let cancelled = false
    void listNavMenus()
      .then((rows) => {
        if (!cancelled) setNavMenus(rows)
      })
      .catch(() => {
        if (!cancelled) setNavMenus([])
      })
    return () => {
      cancelled = true
    }
  }, [isAuthenticated, navMenusRev])

  const siderItems = useMemo(
    () => buildSiderMenuItems(navMenus, { t, nav, hideMenuKeys }),
    [navMenus, t, nav, hideMenuKeys],
  )

  useEffect(() => {
    setMenuOpenKeys(menuNavState.openKeys)
  }, [menuNavState.openKeys])

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
          collapsible
          collapsed={collapsed}
          collapsedWidth={SIDER_COLLAPSED_PX}
          trigger={null}
          width={siderWidth}
          style={{
            ...siderStyle,
            flex: '0 0 auto',
            maxWidth: collapsed ? undefined : '20%',
            minWidth: collapsed ? SIDER_COLLAPSED_PX : SIDER_MIN_PX,
          }}
          theme={shellLight ? 'light' : 'dark'}
        >
          <div
            className="minerva-app-sider-scroll minerva-scrollbar-styled"
            style={{ flex: 1, minHeight: 0, overflow: 'auto' }}
          >
            <Menu
              mode="inline"
              inlineCollapsed={collapsed}
              className="minerva-app-sider-menu"
              theme={shellLight ? 'light' : 'dark'}
              style={{ background: 'transparent', border: 'none', paddingTop: 8 }}
              selectedKeys={selectedKeys}
              {...siderMenuModeProps}
              items={siderItems}
            />
          </div>
          <div className="minerva-app-sider-footer">
            <Button
              type="text"
              className="minerva-app-sider-collapse-btn"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              aria-label={collapsed ? t('layout.siderExpand') : t('layout.siderCollapse')}
              title={collapsed ? t('layout.siderExpand') : t('layout.siderCollapse')}
              onClick={toggleCollapsed}
            />
          </div>
        </Sider>
        {!collapsed ? (
          <div
            className="minerva-sider-resize-handle"
            role="separator"
            aria-orientation="vertical"
            aria-label={t('layout.siderResize')}
            aria-valuenow={siderWidth}
            title={t('layout.siderResize')}
            onMouseDown={onResizeStart}
            onTouchStart={onResizeTouchStart}
          />
        ) : null}
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
          <div className="minerva-app-main-scroll" style={mainScrollStyle}>
            <Outlet />
          </div>
        </Content>
      </div>
    </Layout>
  )
}
