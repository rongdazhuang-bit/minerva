import { BgColorsOutlined, GlobalOutlined } from '@ant-design/icons'
import { Button, Dropdown, Tooltip, type MenuProps } from 'antd'
import { useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import type { AuthTone } from '@/features/auth/authTheme'

const leaveDelay = 0.15

function currentLangKey(lng: string) {
  return lng?.startsWith('zh') ? 'zh-CN' : 'en'
}

function LangItemIcon({ kind }: { kind: 'zh' | 'en' }) {
  if (kind === 'zh') {
    return <span className="auth-dropdown-icon auth-dropdown-icon--zh" aria-hidden>简</span>
  }
  return <span className="auth-dropdown-icon auth-dropdown-icon--en" aria-hidden>EN</span>
}

function ThemeItemIcon({ k }: { k: 'blue' | 'amber' }) {
  return (
    <span
      className={`auth-swatch ${k === 'blue' ? 'auth-swatch--blue' : 'auth-swatch--amber'}`}
      aria-hidden
    />
  )
}

type Props = {
  tone: AuthTone
  onToneChange: (t: AuthTone) => void
}

export function MinervaLangThemeControls({ tone, onToneChange }: Props) {
  const { t, i18n } = useTranslation()
  const langKey = currentLangKey(i18n.language)

  const langItems: MenuProps['items'] = useMemo(
    () => [
      { key: 'zh-CN', label: t('auth.langZh'), icon: <LangItemIcon kind="zh" /> },
      { key: 'en', label: t('auth.langEn'), icon: <LangItemIcon kind="en" /> },
    ],
    [t],
  )

  const themeItems: MenuProps['items'] = useMemo(
    () => [
      { key: 'blue', label: t('auth.themeMenuBlue'), icon: <ThemeItemIcon k="blue" /> },
      { key: 'amber', label: t('auth.themeMenuAmber'), icon: <ThemeItemIcon k="amber" /> },
    ],
    [t],
  )

  const onLangClick: NonNullable<MenuProps['onClick']> = useCallback(
    (e) => {
      const key = e.key as 'zh-CN' | 'en'
      void i18n.changeLanguage(key)
    },
    [i18n],
  )

  const onThemeClick: NonNullable<MenuProps['onClick']> = useCallback(
    (e) => onToneChange(e.key as AuthTone),
    [onToneChange],
  )

  return (
    <>
      <Tooltip title={t('auth.langSwitch')}>
        <Dropdown
          classNames={{ root: 'auth-toolbar-dropdown' }}
          getPopupContainer={() => document.body}
          styles={{ root: { zIndex: 2000 } }}
          destroyOnHidden
          menu={{
            items: langItems,
            onClick: onLangClick,
            selectedKeys: [langKey],
          }}
          trigger={['hover', 'click']}
          placement="bottomRight"
          mouseEnterDelay={0.05}
          mouseLeaveDelay={leaveDelay}
        >
          <Button
            type="text"
            className="auth-page-toolbar-btn"
            icon={<GlobalOutlined />}
            aria-label={t('auth.langSwitch')}
            aria-haspopup="menu"
          />
        </Dropdown>
      </Tooltip>
      <Tooltip title={t('auth.themeToggle')}>
        <Dropdown
          classNames={{ root: 'auth-toolbar-dropdown' }}
          getPopupContainer={() => document.body}
          styles={{ root: { zIndex: 2000 } }}
          destroyOnHidden
          menu={{
            items: themeItems,
            onClick: onThemeClick,
            selectedKeys: [tone],
          }}
          trigger={['hover', 'click']}
          placement="bottomRight"
          mouseEnterDelay={0.05}
          mouseLeaveDelay={leaveDelay}
        >
          <Button
            type="text"
            className="auth-page-toolbar-btn"
            icon={<BgColorsOutlined />}
            aria-label={t('auth.themeToggle')}
            aria-haspopup="menu"
          />
        </Dropdown>
      </Tooltip>
    </>
  )
}
