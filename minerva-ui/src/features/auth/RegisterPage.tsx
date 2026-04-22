import { registerApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import { Card, Form, Input, Button, Typography, message } from 'antd'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'

export function RegisterPage() {
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
        background: 'radial-gradient(1000px 500px at 80% 10%, #2a1f1a, #0a0c10), #0a0c10',
        padding: 16,
      }}
    >
      <Card style={{ width: 400, maxWidth: '100%' }} title={t('auth.register')}>
        <Form
          form={form}
          layout="vertical"
          onFinish={async (v) => {
            try {
              const o = await registerApi(v.email, v.password)
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
          <Form.Item
            name="password"
            label={t('auth.password')}
            rules={[{ required: true }, { min: 8, message: '≥8' }]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>
            {t('auth.register')}
          </Button>
        </Form>
        <Typography.Paragraph style={{ marginTop: 12, marginBottom: 0, textAlign: 'center' }}>
          <Link to="/login">{t('auth.login')}</Link>
        </Typography.Paragraph>
      </Card>
    </div>
  )
}
