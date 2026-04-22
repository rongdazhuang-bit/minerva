import { loginApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import { Card, Form, Input, Button, Typography, message } from 'antd'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'

export function LoginPage() {
  const { t } = useTranslation()
  const { setTokens } = useAuth()
  const nav = useNavigate()
  const [form] = Form.useForm()

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        background: 'radial-gradient(1200px 600px at 20% 20%, #1a1f2e, #0a0c10), #0a0c10',
        padding: 16,
      }}
    >
      <Card style={{ width: 400, maxWidth: '100%' }} title={t('auth.login')}>
        <Form
          form={form}
          layout="vertical"
          onFinish={async (v) => {
            try {
              const o = await loginApi(v.email, v.password)
              setTokens(o.access_token, o.refresh_token)
              message.success('OK')
              void nav('/app/rules')
            } catch (e) {
              if (e instanceof ApiError) {
                void message.error(e.message)
              } else {
                void message.error(t('common.error'))
              }
            }
          }}
        >
          <Form.Item name="email" label={t('auth.email')} rules={[{ required: true }]}>
            <Input type="email" autoComplete="email" />
          </Form.Item>
          <Form.Item name="password" label={t('auth.password')} rules={[{ required: true }]}>
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>
            {t('auth.login')}
          </Button>
        </Form>
        <Typography.Paragraph style={{ marginTop: 12, marginBottom: 0, textAlign: 'center' }}>
          <Link to="/register">{t('auth.register')}</Link>
        </Typography.Paragraph>
      </Card>
    </div>
  )
}
