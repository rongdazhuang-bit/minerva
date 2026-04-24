import {
  BgColorsOutlined,
  BellOutlined,
  CompassOutlined,
  DesktopOutlined,
  GlobalOutlined,
  NodeIndexOutlined,
  StarOutlined,
  SunOutlined,
} from '@ant-design/icons'
import { Button, Dropdown, Tooltip, type MenuProps } from 'antd'
import { useCallback, useMemo, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { type AuthTone, AUTH_TONES } from '@/features/auth/authTheme'

const leaveDelay = 0.15

const THEME_ORDER = AUTH_TONES

/** 与参考图一致：第 1、3 项为纯色强调，其余带轻微色差字；「阳光」在暗色菜单里用软蓝、无错位 */
const THEME_LABEL_MODE: AuthTone[] = ['cyan', 'purple']

const THEME_I18N: Record<AuthTone, string> = {
  cyan: 'auth.themeMenuCyan',
  sea: 'auth.themeMenuSea',
  purple: 'auth.themeMenuPurple',
  forest: 'auth.themeMenuForest',
  gold: 'auth.themeMenuGold',
  sunshine: 'auth.themeMenuSunshine',
}

const THEME_ICONS: Record<AuthTone, ReactNode> = {
  cyan: <DesktopOutlined className="auth-theme-item-icon auth-theme-item-icon--cyan" />,
  sea: <CompassOutlined className="auth-theme-item-icon auth-theme-item-icon--sea" />,
  purple: <StarOutlined className="auth-theme-item-icon auth-theme-item-icon--purple" />,
  forest: <NodeIndexOutlined className="auth-theme-item-icon auth-theme-item-icon--forest" />,
  gold: <BellOutlined className="auth-theme-item-icon auth-theme-item-icon--gold" />,
  sunshine: <SunOutlined className="auth-theme-item-icon auth-theme-item-icon--sun" />,
}

function currentLangKey(lng: string) {
  return lng?.startsWith('zh') ? 'zh-CN' : 'en'
}

function LangItemIcon({ kind }: { kind: 'zh' | 'en' }) {
  if (kind === 'zh') {
    return <span className="auth-dropdown-icon auth-dropdown-icon--zh" aria-hidden>简</span>
  }
  return <span className="auth-dropdown-icon auth-dropdown-icon--en" aria-hidden>EN</span>
}

function themeLabelClass(t: AuthTone) {
  if (t === 'sunshine') {
    return 'auth-theme-label auth-theme-label--sunshine-row'
  }
  if (THEME_LABEL_MODE.includes(t)) {
    return 'auth-theme-label auth-theme-label--accent'
  }
  return 'auth-theme-label auth-theme-label--glitch'
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
    () =>
      THEME_ORDER.map((k) => ({
        key: k,
        label: <span className={themeLabelClass(k)}>{t(THEME_I18N[k])}</span>,
        icon: THEME_ICONS[k],
      })),
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
          classNames={{ root: 'auth-toolbar-dropdown auth-toolbar-dropdown--theme' }}
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
