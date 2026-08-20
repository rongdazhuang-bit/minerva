import { MenuFoldOutlined, MenuUnfoldOutlined } from '@ant-design/icons'
import { Button, Layout, Menu } from 'antd'
import { AppHeaderToolbar } from '@/app/layout/AppHeaderToolbar'
import { AppNavTags } from '@/app/layout/AppNavTags'
import { useAppNavTags } from '@/app/layout/useAppNavTags'
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { getAgentV2Config } from '@/api/agent'
import { useAuth } from '@/app/AuthContext'
import { buildSiderMenuItems } from '@/app/layout/buildSiderMenuItems'
import { resolveMenuNavState } from '@/app/layout/menuNavMatch'
import { SiderMenuSkeleton } from '@/app/layout/SiderMenuSkeleton'
import { useNavMenus } from '@/hooks/useNavMenus'
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

const brandTitle: CSSProperties = {
  color: 'var(--minerva-primary, #38bdf8)',
  fontSize: 18,
  fontWeight: 600,
  fontFamily: "'Fraunces', Georgia, serif",
  letterSpacing: 0.04,
  lineHeight: 1.2,
  whiteSpace: 'nowrap',
}

const brandAccount: CSSProperties = {
  color: 'var(--minerva-ink-muted, #94a3b8)',
  fontSize: 12,
  fontWeight: 400,
  lineHeight: 1.2,
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  maxWidth: 'min(280px, 40vw)',
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
  minHeight: 56,
  height: 'auto',
  paddingBlock: 8,
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
  /* Default: shell main pane does not scroll; pages scroll inside the frame. */
  overflow: 'hidden',
  WebkitOverflowScrolling: 'touch',
  /* Outer gap between shell edges and the main frame (project rule: 3px). */
  padding: 3,
}

export function AppLayout() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const { pathname } = useLocation()
  const { clear, workspaceId, accountEmail, tenantName } = useAuth()
  const { data: navMenus = [], isFetched: navMenusFetched } = useNavMenus()
  const { data: agentConfig, isFetched: agentConfigFetched } = useQuery({
    queryKey: ['agent-v2-config', workspaceId],
    queryFn: () => getAgentV2Config(workspaceId!),
    enabled: Boolean(workspaceId),
    staleTime: 60_000,
  })
  const siderNavReady = navMenusFetched && agentConfigFetched
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

  /** Apply memory-menu filter only after agent config is known (paired with `siderNavReady`). */
  const hideMenuKeys = useMemo(() => {
    if (!agentConfigFetched) return undefined
    return agentConfig?.memory_backend !== 'mem0'
      ? new Set(['agents-memory'])
      : undefined
  }, [agentConfig, agentConfigFetched])

  const menuNavState = useMemo(
    () =>
      siderNavReady
        ? resolveMenuNavState(navMenus, pathname, hideMenuKeys)
        : { selectedKey: null as string | null, openKeys: [] as string[] },
    [navMenus, pathname, hideMenuKeys, siderNavReady],
  )

  const selectedKeys = useMemo(
    () => (menuNavState.selectedKey ? [menuNavState.selectedKey] : []),
    [menuNavState.selectedKey],
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

  const siderItems = useMemo(
    () =>
      siderNavReady
        ? buildSiderMenuItems(navMenus, { t, nav, hideMenuKeys })
        : [],
    [navMenus, t, nav, hideMenuKeys, siderNavReady],
  )

  useEffect(() => {
    setMenuOpenKeys(menuNavState.openKeys)
  }, [menuNavState.openKeys])

  const { tags, activeKey, activateTag, closeTag } = useAppNavTags({
    pathname,
    navMenus,
    hideMenuKeys,
    ready: siderNavReady,
    t,
    navigate: nav,
  })

  const brandSubtitle = useMemo(() => {
    if (!accountEmail) return null
    if (tenantName) return `${accountEmail} · ${tenantName}`
    return accountEmail
  }, [accountEmail, tenantName])

  const onLogout = useCallback(() => {
    clear()
    void nav('/login')
  }, [clear, nav])

  /** Agents chat uses its own chrome panels; skip the shell outer rounded frame. */
  const bareMainFrame = pathname.startsWith('/app/agents/chat')

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
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            gap: 2,
            minWidth: 0,
          }}
        >
          <div style={brandTitle}>{t('appName')}</div>
          {brandSubtitle ? (
            <div style={brandAccount} title={brandSubtitle}>
              {brandSubtitle}
            </div>
          ) : null}
        </div>
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
            {!siderNavReady ? (
              <SiderMenuSkeleton
                collapsed={collapsed}
                light={shellLight}
                loadingLabel={t('layout.siderNavLoading')}
              />
            ) : (
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
            )}
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
          <AppNavTags
            tags={tags}
            activeKey={activeKey}
            onActivate={activateTag}
            onClose={closeTag}
          />
          <div className="minerva-app-main-scroll" style={contentScrollStyle}>
            {bareMainFrame ? (
              <Outlet />
            ) : (
              <div className="minerva-app-main-frame">
                <Outlet />
              </div>
            )}
          </div>
        </Content>
      </div>
    </Layout>
  )
}
