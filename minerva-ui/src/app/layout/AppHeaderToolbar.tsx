import { LogoutOutlined } from '@ant-design/icons'
import { Button, Tooltip } from 'antd'
import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useMinervaTone } from '@/app/useMinervaTone'
import '@/features/auth/AuthPage.css'
import { MinervaLangThemeControls } from '@/features/auth/MinervaLangThemeControls'
import { persistAuthTone, type AuthTone } from '@/features/auth/authTheme'
import './AppHeaderToolbar.css'

type Props = {
  onLogout: () => void
}

export function AppHeaderToolbar({ onLogout }: Props) {
  const { t } = useTranslation()
  const tone = useMinervaTone()

  const onToneChange = useCallback((next: AuthTone) => {
    persistAuthTone(next)
  }, [])

  return (
    <div className="app-header-toolbar">
      <MinervaLangThemeControls tone={tone} onToneChange={onToneChange} />
      <Tooltip title={t('auth.logout')}>
        <Button
          type="text"
          className="auth-page-toolbar-btn"
          icon={<LogoutOutlined />}
          onClick={onLogout}
          aria-label={t('auth.logout')}
        />
      </Tooltip>
    </div>
  )
}
