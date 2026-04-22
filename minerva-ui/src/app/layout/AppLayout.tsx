import {
  BulbOutlined,
  ClusterOutlined,
  LogoutOutlined,
} from '@ant-design/icons'
import { Button, Layout, Menu, Select } from 'antd'
import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '@/app/AuthContext'

const { Sider, Header, Content } = Layout

export function AppLayout() {
  const { t, i18n } = useTranslation()
  const nav = useNavigate()
  const path = useLocation().pathname
  const { clear } = useAuth()

  const onLogout = useCallback(() => {
    clear()
    void nav('/login')
  }, [clear, nav])

  const left = path.startsWith('/app/executions') ? 'executions' : 'rules'

  return (
      <Layout style={{ minHeight: '100vh', background: '#0a0e12' }}>
        <Sider width={200} style={{ background: 'linear-gradient(180deg, #0f1419 0%, #0a0d11 100%)' }}>
          <div
            style={{
              padding: '20px 16px 12px',
              color: 'var(--minerva-amber, #c9a227)',
              fontSize: 18,
              fontFamily: "'Fraunces', Georgia, serif",
              letterSpacing: 0.04,
            }}
          >
            {t('appName')}
          </div>
          <Menu
            theme="dark"
            style={{ background: 'transparent' }}
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
        <Layout>
          <Header
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end',
              gap: 12,
              background: '#0f1419',
              borderBottom: '1px solid #1e2630',
            }}
          >
            <Select
              size="small"
              value={i18n.language}
              onChange={(lng) => void i18n.changeLanguage(lng)}
              options={[
                { value: 'zh-CN', label: '中文' },
                { value: 'en', label: 'EN' },
              ]}
              style={{ width: 100 }}
            />
            <Button type="text" icon={<LogoutOutlined />} onClick={onLogout}>
              {t('auth.logout')}
            </Button>
          </Header>
          <Content style={{ padding: 20, minHeight: 360 }}>
            <Outlet />
          </Content>
        </Layout>
      </Layout>
  )
}
