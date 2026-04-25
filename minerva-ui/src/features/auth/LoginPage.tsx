import { loginApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import { AuthPageToolbar } from '@/features/auth/AuthPageToolbar'
import { getAuthPageTheme } from '@/features/auth/authTheme'
import { useAuthPageBodyLock } from '@/features/auth/useAuthPageBodyLock'
import { useAuthPageTone } from '@/features/auth/useAuthPageTone'
import { Button, Checkbox, ConfigProvider, Form, Input, Typography, message } from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import './AuthPage.css'

const RE_MEMBER = 'minerva_remember_email'

export function LoginPage() {
  const { t } = useTranslation()
  const { setTokens } = useAuth()
  useAuthPageBodyLock()
  const { tone, setTone } = useAuthPageTone()
  const nav = useNavigate()
  const [form] = Form.useForm()
  const [remember, setRemember] = useState(
    () => localStorage.getItem(RE_MEMBER) != null,
  )

  useEffect(() => {
    const stored = localStorage.getItem(RE_MEMBER)
    if (stored) form.setFieldValue('email', stored)
  }, [form])

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
                  {t('appName')} {t('auth.login')}
                </h1>
                <p className="login-subtitle">{t('auth.loginSubtitle')}</p>
              </div>
            </div>

            <Form
              form={form}
              layout="vertical"
              requiredMark={false}
              onFinish={async (v) => {
                const { email, password } = v as { email: string; password: string }
                try {
                  if (remember) {
                    localStorage.setItem(RE_MEMBER, String(email).trim())
                  } else {
                    localStorage.removeItem(RE_MEMBER)
                  }
                  const o = await loginApi(email, password)
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
                label={t('auth.loginAccountLabel')}
                rules={[{ required: true, message: t('auth.loginAccountRequired') }]}
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
                rules={[{ required: true, message: t('auth.passwordRequired') }]}
              >
                <Input.Password allowClear autoComplete="current-password" />
              </Form.Item>
              <Form.Item>
                <Checkbox checked={remember} onChange={(e) => setRemember(e.target.checked)}>
                  {t('auth.remember')}
                </Checkbox>
              </Form.Item>
              <Form.Item style={{ marginBottom: 0 }}>
                <Button
                  type="primary"
                  htmlType="submit"
                  block
                  size="large"
                  style={{ height: 44, fontWeight: 600 }}
                >
                  {t('auth.loginAction')}
                </Button>
              </Form.Item>
            </Form>

            <Typography.Text
              type="secondary"
              className="login-link"
              style={{ display: 'block' }}
            >
              <Link to="/register">{t('auth.register')}</Link>
            </Typography.Text>
          </div>
        </ConfigProvider>
      </div>

      <p className="login-footer">© {new Date().getFullYear()} Minerva</p>
    </div>
  )
}
