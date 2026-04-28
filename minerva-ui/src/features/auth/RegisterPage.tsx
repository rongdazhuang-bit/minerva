import { registerApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import { AuthPasswordInput } from '@/features/auth/AuthPasswordInput'
import { AuthPageToolbar } from '@/features/auth/AuthPageToolbar'
import { getAuthPageTheme } from '@/features/auth/authTheme'
import { useAuthPageBodyLock } from '@/features/auth/useAuthPageBodyLock'
import { useAuthPageTone } from '@/features/auth/useAuthPageTone'
import { Button, ConfigProvider, Form, Input, Typography, message } from 'antd'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import './AuthPage.css'

export function RegisterPage() {
  const { t } = useTranslation()
  const { setTokens } = useAuth()
  useAuthPageBodyLock()
  const { tone, setTone } = useAuthPageTone()
  const nav = useNavigate()
  const [form] = Form.useForm()

  return (
    <div className={`login-shell tone-${tone}`}>
      <AuthPageToolbar tone={tone} onToneChange={setTone} />
      <div className="login-center">
        <ConfigProvider theme={getAuthPageTheme(tone)}>
          <div className="login-card">
            <div className="login-header">
              <div className={`login-logo tone-${tone}`} aria-hidden>
                M
              </div>
              <div>
                <h1 className="login-title">
                  {t('appName')} {t('auth.register')}
                </h1>
                <p className="login-subtitle">{t('auth.registerSubtitle')}</p>
              </div>
            </div>

            <Form
              form={form}
              layout="vertical"
              requiredMark={false}
              onFinish={async (v) => {
                const { email, password } = v as { email: string; password: string }
                try {
                  const o = await registerApi(email, password)
                  setTokens(o.access_token, o.refresh_token)
                  void message.success('OK')
                  void nav('/app/overview')
                } catch (e) {
                  if (e instanceof ApiError) {
                    void message.error(e.message)
                  } else {
                    void message.error(t('common.error'))
                  }
                }
              }}
            >
              <Form.Item
                name="email"
                label={t('auth.email')}
                rules={[{ required: true, message: t('auth.emailRequired') }]}
              >
                <Input
                  allowClear
                  type="email"
                  autoComplete="email"
                  placeholder="name@example.com"
                />
              </Form.Item>
              <Form.Item
                name="password"
                label={t('auth.password')}
                rules={[
                  { required: true, message: t('auth.passwordRequired') },
                  { min: 8, message: t('auth.passwordMin') },
                ]}
              >
                <AuthPasswordInput allowClear autoComplete="new-password" />
              </Form.Item>
              <Form.Item style={{ marginBottom: 0 }}>
                <Button
                  type="primary"
                  htmlType="submit"
                  block
                  size="large"
                  style={{ height: 44, fontWeight: 600 }}
                >
                  {t('auth.registerAction')}
                </Button>
              </Form.Item>
            </Form>

            <Typography.Text
              type="secondary"
              className="login-link"
              style={{ display: 'block' }}
            >
              <Link to="/login">{t('auth.goLogin')}</Link>
            </Typography.Text>
          </div>
        </ConfigProvider>
      </div>

      <p className="login-footer">© {new Date().getFullYear()} Minerva</p>
    </div>
  )
}
