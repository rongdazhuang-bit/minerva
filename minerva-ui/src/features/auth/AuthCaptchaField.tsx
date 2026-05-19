import { fetchAuthCaptchaApi, type AuthCaptchaScope } from '@/api/auth'
import { Input, Spin } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import './AuthPage.css'

type Props = {
  /** Login or register form; selects ``/auth/{scope}/captcha``. */
  scope: AuthCaptchaScope
  /** Bound captcha answer from ``Form.Item`` ``captcha_code``. */
  value?: string
  /** Propagates captcha answer edits to the form. */
  onChange?: (value: string) => void
  /** Notify parent when a new captcha challenge is loaded. */
  onCaptchaIdChange: (id: string) => void
}

/**
 * Auth form CAPTCHA: input and image on one row; click image to refresh.
 */
export function AuthCaptchaField({
  scope,
  value,
  onChange,
  onCaptchaIdChange,
}: Props) {
  const { t } = useTranslation()
  const [image, setImage] = useState('')
  const [loading, setLoading] = useState(false)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchAuthCaptchaApi(scope)
      onCaptchaIdChange(data.captcha_id)
      setImage(data.image)
      onChangeRef.current?.('')
    } finally {
      setLoading(false)
    }
  }, [onCaptchaIdChange, scope])

  useEffect(() => {
    void reload()
  }, [reload])

  return (
    <div className="auth-captcha-field">
      <Input
        allowClear
        className="auth-captcha-input"
        value={value}
        placeholder={t('auth.captchaPlaceholder')}
        autoComplete="off"
        maxLength={16}
        onChange={(e) => onChange?.(e.target.value)}
      />
      <button
        type="button"
        className="auth-captcha-image-btn"
        aria-label={t('auth.captchaRefresh')}
        title={t('auth.captchaRefresh')}
        onClick={() => void reload()}
        disabled={loading}
      >
        {loading && !image ? (
          <Spin size="small" />
        ) : (
          <img
            src={image || undefined}
            alt={t('auth.captchaImageAlt')}
            className="auth-captcha-image"
            draggable={false}
          />
        )}
      </button>
    </div>
  )
}
