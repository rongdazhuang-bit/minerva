import { Breadcrumb } from 'antd'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router-dom'
import type { ItemType } from 'antd/es/breadcrumb/Breadcrumb'
import './appBreadcrumb.css'

function settingsLeafTitle(pathname: string, t: (k: string) => string): string | null {
  if (pathname.startsWith('/app/settings/models')) return t('settings.models')
  if (pathname.startsWith('/app/settings/ocr')) return t('settings.ocr')
  if (pathname.startsWith('/app/settings/data-sources')) return t('settings.dataSources')
  if (pathname.startsWith('/app/settings/menus')) return t('settings.menuConfig')
  if (pathname.startsWith('/app/settings/users')) return t('settings.users')
  if (pathname.startsWith('/app/settings/roles')) return t('settings.roles')
  if (pathname.startsWith('/app/settings/dictionary')) return t('settings.dictionary')
  return null
}

export function AppBreadcrumb() {
  const { t } = useTranslation()
  const { pathname } = useLocation()

  const items: ItemType[] = useMemo(() => {
    const home: ItemType = { title: <Link to="/app/overview">{t('breadcrumb.home')}</Link> }

    if (pathname.startsWith('/app/smart-review')) {
      return [home, { title: t('nav.smartReview') }]
    }
    if (pathname.startsWith('/app/rules')) {
      return [home, { title: t('nav.rules') }]
    }
    if (pathname.startsWith('/app/settings')) {
      const leaf = settingsLeafTitle(pathname, t)
      if (leaf) {
        return [
          home,
          { title: <Link to="/app/settings/models">{t('nav.settings')}</Link> },
          { title: leaf },
        ]
      }
      return [home, { title: t('nav.settings') }]
    }
    return [home, { title: t('nav.overview') }]
  }, [pathname, t])

  return <Breadcrumb className="minerva-breadcrumb" items={items} />
}
