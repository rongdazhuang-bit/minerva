import { EyeInvisibleOutlined, EyeOutlined } from '@ant-design/icons'
import { Input } from 'antd'
import type { InputProps } from 'antd'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

export type AuthPasswordInputProps = Omit<InputProps, 'type' | 'suffix'>

/**
 * 与登录/注册页账号框相同的基础组件（antd Input + affix），避免 Input.Password 额外包裹层带来的样式与自动填充问题。
 */
export function AuthPasswordInput({
  autoComplete = 'current-password',
  ...props
}: AuthPasswordInputProps) {
  const { t } = useTranslation()
  const [visible, setVisible] = useState(false)

  return (
    <Input
      {...props}
      type={visible ? 'text' : 'password'}
      autoComplete={autoComplete}
      suffix={
        <span
          role="button"
          tabIndex={0}
          className="auth-password-toggle"
          aria-label={visible ? t('auth.hidePassword') : t('auth.showPassword')}
          onMouseDown={(e) => {
            e.preventDefault()
          }}
          onClick={() => {
            setVisible((v) => !v)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              setVisible((v) => !v)
            }
          }}
        >
          {visible ? <EyeInvisibleOutlined /> : <EyeOutlined />}
        </span>
      }
    />
  )
}
