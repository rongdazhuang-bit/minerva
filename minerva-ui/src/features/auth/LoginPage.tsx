import { loginApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import { useAuth } from '@/app/AuthContext'
import { useAppMessage } from '@/app/useAppMessage'
import { AuthCaptchaField } from '@/features/auth/AuthCaptchaField'
import { AuthPasswordInput } from '@/features/auth/AuthPasswordInput'
import { AuthPageToolbar } from '@/features/auth/AuthPageToolbar'
import { getAuthPageTheme, type AuthTone } from '@/features/auth/authTheme'
import { useAuthPageBodyLock } from '@/features/auth/useAuthPageBodyLock'
import { useAuthPageTone } from '@/features/auth/useAuthPageTone'
import { App as AntdApp, Button, Checkbox, ConfigProvider, Form, Input, Typography } from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'
import './AuthPage.css'

const RE_MEMBER = 'minerva_remember_email'

type LoginFormValues = {
  email: string
  password: string
  captcha_code: string
}

export function LoginPage() {
  useAuthPageBodyLock()
  const { tone, setTone } = useAuthPageTone()

  return (
    <div className={`login-shell tone-${tone}`}>
      <AuthPageToolbar tone={tone} onToneChange={setTone} />
      <div className="login-center">
        <div className="login-panel">
          <ConfigProvider theme={getAuthPageTheme(tone)}>
            <AntdApp>
              <LoginPageCard tone={tone} />
            </AntdApp>
          </ConfigProvider>
        </div>
      </div>
      <p className="login-footer">© {new Date().getFullYear()} Minerva</p>
    </div>
  )
}

function LoginPageCard({ tone }: { tone: AuthTone }) {
  const { t } = useTranslation()
  const messageApi = useAppMessage()
  const { setTokens } = useAuth()
  const nav = useNavigate()
  const [form] = Form.useForm<LoginFormValues>()
  const [remember, setRemember] = useState(
    () => localStorage.getItem(RE_MEMBER) != null,
  )
  const [captchaId, setCaptchaId] = useState('')
  const [captchaRefreshKey, setCaptchaRefreshKey] = useState(0)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    const stored = localStorage.getItem(RE_MEMBER)
    if (stored) form.setFieldValue('email', stored)
  }, [form])

  return (
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
          const { email, password, captcha_code: captchaCode } = v
          if (!captchaId) {
            void messageApi.error(t('auth.captchaRequired'))
            return
          }
          setSubmitting(true)
          try {
            if (remember) {
              localStorage.setItem(RE_MEMBER, String(email).trim())
            } else {
              localStorage.removeItem(RE_MEMBER)
            }
            const o = await loginApi(email, password, captchaId, captchaCode)
            setTokens(o.access_token, o.refresh_token)
            void messageApi.success('OK')
            void nav('/app/overview')
          } catch (e) {
            if (e instanceof ApiError) {
              void messageApi.error(e.message)
            } else {
              void messageApi.error(t('common.error'))
            }
            form.setFieldValue('captcha_code', '')
            setCaptchaRefreshKey((k) => k + 1)
          } finally {
            setSubmitting(false)
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
            disabled={submitting}
          />
        </Form.Item>
        <Form.Item
          name="password"
          label={t('auth.password')}
          rules={[{ required: true, message: t('auth.passwordRequired') }]}
        >
          <AuthPasswordInput
            allowClear
            autoComplete="current-password"
            disabled={submitting}
          />
        </Form.Item>
        <Form.Item
          name="captcha_code"
          label={t('auth.captchaLabel')}
          rules={[{ required: true, message: t('auth.captchaRequired') }]}
        >
          <AuthCaptchaField
            key={captchaRefreshKey}
            scope="login"
            onCaptchaIdChange={setCaptchaId}
          />
        </Form.Item>
        <Form.Item>
          <Checkbox
            checked={remember}
            disabled={submitting}
            onChange={(e) => setRemember(e.target.checked)}
          >
            {t('auth.remember')}
          </Checkbox>
        </Form.Item>
        <Form.Item style={{ marginBottom: 0 }}>
          <Button
            type="primary"
            htmlType="submit"
            block
            size="large"
            loading={submitting}
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
  )
}
