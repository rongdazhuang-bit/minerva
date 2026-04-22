import { theme, type ThemeConfig } from 'antd'

export type AuthTone = 'blue' | 'amber'

const STORAGE_TONE = 'minerva_auth_tone'

export const MINERVA_TONE_EVENT = 'minerva-auth-tone'

export function readStoredAuthTone(): AuthTone {
  const v = localStorage.getItem(STORAGE_TONE)
  if (v === 'amber' || v === 'blue') return v
  return 'blue'
}

export function persistAuthTone(t: AuthTone) {
  localStorage.setItem(STORAGE_TONE, t)
  window.dispatchEvent(new Event(MINERVA_TONE_EVENT))
}

export function getAuthPageTheme(tone: AuthTone): ThemeConfig {
  if (tone === 'amber') {
    return {
      algorithm: theme.defaultAlgorithm,
      token: {
        colorPrimary: '#c9a227',
        borderRadius: 8,
        colorText: '#0f172a',
        colorTextDescription: '#64748b',
        colorBorder: '#e2e8f0',
        colorBgContainer: '#ffffff',
        controlHeight: 40,
      },
      components: {
        Input: { activeBorderColor: '#c9a227', hoverBorderColor: '#d4a82c' },
        Button: { primaryShadow: '0 2px 0 rgba(0,0,0,0.02)' },
      },
    }
  }
  return {
    algorithm: theme.defaultAlgorithm,
    token: {
      colorPrimary: '#2563eb',
      borderRadius: 8,
      colorText: '#0f172a',
      colorTextDescription: '#64748b',
      colorBorder: '#e2e8f0',
      colorBgContainer: '#ffffff',
      controlHeight: 40,
    },
    components: {
      Input: { activeBorderColor: '#2563eb', hoverBorderColor: '#3b82f6' },
      Button: { primaryShadow: '0 2px 0 rgba(0,0,0,0.02)' },
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
