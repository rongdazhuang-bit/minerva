import { theme, type ThemeConfig } from 'antd'

/**
 * Ant Design theme + persistence for the six Minerva UI tones.
 * DARK_THEME_BG must stay in sync with `index.css` (`html.minerva-tone-*` CSS variables).
 * Legacy keys in localStorage (blue/amber) map in LEGACY_TONE.
 */
export const AUTH_TONES = [
  'cyan',
  'sea',
  'purple',
  'forest',
  'gold',
  'sunshine',
] as const

export type AuthTone = (typeof AUTH_TONES)[number]

const STORAGE_TONE = 'minerva_auth_tone'

const TONE_CLASS_PREFIX = 'minerva-tone-'

/** 旧版 localStorage 迁移为新版 key */
const LEGACY_TONE: Record<string, AuthTone> = {
  blue: 'cyan',
  amber: 'gold',
}

/** Fired on persist; AppThemedLayout and useMinervaTone listen to stay in sync without reload. */
export const MINERVA_TONE_EVENT = 'minerva-auth-tone'

/** 暗色五主题用霓虹色；「阳光」单独走浅色白底，主色为常规蓝 */
const PRIMARY: Record<AuthTone, string> = {
  cyan: '#38bdf8',
  sea: '#2dd4bf',
  purple: '#a78bfa',
  forest: '#4ade80',
  gold: '#f59e0b',
  sunshine: '#2563eb',
}

const baseDarkText = {
  colorText: '#e8f0f8',
  colorTextDescription: '#94a3b8',
} as const

/** 与 index.css 中各 minerva-tone 的底/面/边一致，切换主题时 Ant 组件背景同步 */
const DARK_THEME_BG: Record<
  Exclude<AuthTone, 'sunshine'>,
  {
    colorBgLayout: string
    colorBgContainer: string
    colorBgElevated: string
    colorBorder: string
    colorBorderSecondary: string
    inputBg: string
  }
> = {
  cyan: {
    colorBgLayout: '#0e1520',
    colorBgContainer: '#1a2836',
    colorBgElevated: '#1e2d40',
    colorBorder: '#2a3f58',
    colorBorderSecondary: '#1a2433',
    inputBg: '#121c28',
  },
  sea: {
    colorBgLayout: '#0b181a',
    colorBgContainer: '#152e30',
    colorBgElevated: '#193a3c',
    colorBorder: '#245050',
    colorBorderSecondary: '#122a2c',
    inputBg: '#0d2224',
  },
  purple: {
    colorBgLayout: '#120f1a',
    colorBgContainer: '#1e1830',
    colorBgElevated: '#221c3a',
    colorBorder: '#3a3258',
    colorBorderSecondary: '#1a1528',
    inputBg: '#16122a',
  },
  forest: {
    colorBgLayout: '#0c1512',
    colorBgContainer: '#142420',
    colorBgElevated: '#182a24',
    colorBorder: '#2a4a3c',
    colorBorderSecondary: '#101a16',
    inputBg: '#0e1a16',
  },
  gold: {
    colorBgLayout: '#15120e',
    colorBgContainer: '#221e18',
    colorBgElevated: '#2a251c',
    colorBorder: '#3d3428',
    colorBorderSecondary: '#1a1610',
    inputBg: '#1a1610',
  },
}

const baseLight = {
  borderRadius: 8,
  colorBgContainer: '#ffffff',
  colorBgElevated: '#ffffff',
  colorText: '#0f172a',
  colorTextDescription: '#64748b',
  colorBorder: '#e2e8f0',
  colorBorderSecondary: '#f1f5f9',
  controlHeight: 40,
} as const

function isAuthTone(v: string | null): v is AuthTone {
  return v != null && (AUTH_TONES as readonly string[]).includes(v)
}

export function readStoredAuthTone(): AuthTone {
  const v = localStorage.getItem(STORAGE_TONE)
  if (v && v in LEGACY_TONE) return LEGACY_TONE[v]!
  if (isAuthTone(v)) return v
  return 'cyan'
}

export function persistAuthTone(t: AuthTone) {
  localStorage.setItem(STORAGE_TONE, t)
  window.dispatchEvent(new Event(MINERVA_TONE_EVENT))
}

/**
 * 将当前强调色同步到 <html> 的 `minerva-tone-*` class，供全局 CSS 变量与页面样式使用。
 */
export function syncMinervaToneClass(tone: AuthTone) {
  const el = document.documentElement
  AUTH_TONES.forEach((u) => el.classList.remove(`${TONE_CLASS_PREFIX}${u}`))
  el.classList.add(`${TONE_CLASS_PREFIX}${tone}`)
  el.classList.remove('minerva-auth-tone-amber')
}

export function getAuthPageTheme(tone: AuthTone): ThemeConfig {
  if (tone === 'sunshine') {
    const colorPrimary = PRIMARY.sunshine
    return {
      algorithm: theme.defaultAlgorithm,
      token: {
        ...baseLight,
        colorBgLayout: '#f1f5f9',
        colorPrimary,
        colorLink: colorPrimary,
      },
      components: {
        Input: {
          activeBorderColor: colorPrimary,
          hoverBorderColor: '#3b82f6',
          colorBgContainer: '#ffffff',
        },
        Button: { primaryShadow: '0 2px 0 rgba(0,0,0,0.02)' },
      },
    }
  }
  const colorPrimary = PRIMARY[tone]
  const bg = DARK_THEME_BG[tone]
  return {
    algorithm: theme.darkAlgorithm,
    token: {
      borderRadius: 8,
      controlHeight: 40,
      ...baseDarkText,
      ...bg,
      colorPrimary,
      colorLink: colorPrimary,
    },
    components: {
      Input: {
        activeBorderColor: colorPrimary,
        hoverBorderColor: colorPrimary,
        colorBgContainer: bg.inputBg,
      },
      Button: { primaryShadow: '0 2px 0 rgba(0,0,0,0.15)' },
    },
  }
}

export function getAppLayoutTheme(tone: AuthTone): ThemeConfig {
  const t = getAuthPageTheme(tone)
  return {
    ...t,
    token: { ...t.token, borderRadius: 6, controlHeight: 32 },
  }
}

export function getTonePrimary(tone: AuthTone): string {
  return PRIMARY[tone]
}
