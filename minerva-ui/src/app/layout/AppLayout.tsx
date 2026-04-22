import { BulbOutlined, ClusterOutlined } from '@ant-design/icons'
import { Layout, Menu } from 'antd'
import { AppHeaderToolbar } from '@/app/layout/AppHeaderToolbar'
import type { CSSProperties } from 'react'
import { useCallback, useLayoutEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '@/app/AuthContext'
import { useMinervaTone } from '@/app/useMinervaTone'
import { SIDER_MIN_PX, useResizableSiderWidth } from '@/app/layout/useResizableSiderWidth'
import './appSiderResize.css'

const { Sider, Header, Content } = Layout

const siderStyle: CSSProperties = {
  background: '#f8fafc',
  borderRight: '1px solid #e2e8f0',
  height: '100%',
  overflow: 'auto',
}

const brandAmber: CSSProperties = {
  color: '#a16207',
  fontSize: 18,
  fontWeight: 600,
  fontFamily: "'Fraunces', Georgia, serif",
  letterSpacing: 0.04,
  lineHeight: '56px',
  whiteSpace: 'nowrap',
}

const brandBlue: CSSProperties = {
  ...brandAmber,
  color: '#1d4ed8',
}

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  flex: '0 0 auto',
  flexShrink: 0,
  width: '100%',
  background: '#ffffff',
  borderBottom: '1px solid #e2e8f0',
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
  background: 'var(--minerva-bg, #f1f5f9)',
}

const contentStyle: CSSProperties = {
  flex: 1,
  minWidth: 0,
  minHeight: 0,
  padding: 20,
  overflow: 'auto',
  overflowX: 'hidden',
  WebkitOverflowScrolling: 'touch',
  background: 'var(--minerva-bg, #f1f5f9)',
}

export function AppLayout() {
  const { t } = useTranslation()
  const nav = useNavigate()
  const path = useLocation().pathname
  const { clear } = useAuth()
  const tone = useMinervaTone()
  const brand = tone === 'amber' ? brandAmber : brandBlue
  const { rowRef, siderWidth, onResizeStart } = useResizableSiderWidth()

  const onLogout = useCallback(() => {
    clear()
    void nav('/login')
  }, [clear, nav])

  const left = path.startsWith('/app/executions') ? 'executions' : 'rules'

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
        background: 'var(--minerva-bg, #f1f5f9)',
      }}
    >
      <Header style={headerStyle}>
        <div style={brand}>{t('appName')}</div>
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
          theme="light"
        >
          <Menu
            theme="light"
            style={{ background: 'transparent', border: 'none', paddingTop: 8 }}
            selectedKeys={[left]}
            items={[
              {
                key: 'rules',
                icon: <ClusterOutlined />,
                label: t('nav.rules'),
                onClick: () => void nav('/app/rules'),
              },
              {
                key: 'executions',
                icon: <BulbOutlined />,
                label: t('nav.executions'),
                onClick: () => void nav('/app/executions'),
              },
            ]}
          />
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
        <Content style={contentStyle}>
          <Outlet />
        </Content>
      </div>
    </Layout>
  )
}
