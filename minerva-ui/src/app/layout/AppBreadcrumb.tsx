import { Breadcrumb } from 'antd'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useLocation } from 'react-router-dom'
import type { ItemType } from 'antd/es/breadcrumb/Breadcrumb'
import './appBreadcrumb.css'

function settingsLeafTitle(pathname: string, t: (k: string) => string): string | null {
  if (pathname.startsWith('/app/settings/models')) return t('settings.models')
  if (pathname.startsWith('/app/settings/ocr')) return t('settings.ocr')
  if (pathname.startsWith('/app/settings/file-storage')) return t('settings.fileStorage')
  if (pathname.startsWith('/app/settings/data-sources')) return t('settings.dataSources')
  if (pathname.startsWith('/app/settings/menus')) return t('settings.menuConfig')
  if (pathname.startsWith('/app/settings/users')) return t('settings.users')
  if (pathname.startsWith('/app/settings/roles')) return t('settings.roles')
  if (pathname.startsWith('/app/settings/dictionary')) return t('settings.dictionary')
  return null
}

function rulesBreadcrumb(
  pathname: string,
  t: (k: string) => string,
  home: ItemType,
): ItemType[] | null {
  if (!pathname.startsWith('/app/rules')) return null
  const rulesBase: ItemType = {
    title: <Link to="/app/rules/overview">{t('nav.rules')}</Link>,
  }
  if (pathname.startsWith('/app/rules/management')) {
    return [home, rulesBase, { title: t('nav.rulesManagementList') }]
  }
  if (pathname.startsWith('/app/rules/config/config-prompts')) {
    return [home, rulesBase, { title: t('nav.rulesConfig') }, { title: t('nav.rulesPromptManagement') }]
  }
  if (pathname.startsWith('/app/rules/overview') || pathname.match(/^\/app\/rules\/?$/)) {
    return [home, rulesBase, { title: t('nav.rulesOverview') }]
  }
  return [home, rulesBase, { title: t('nav.rulesOverview') }]
}

function fileOcrBreadcrumb(
  pathname: string,
  t: (k: string) => string,
  home: ItemType,
): ItemType[] | null {
  if (!pathname.startsWith('/app/file-ocr')) return null
  const fileOcrBase: ItemType = {
    title: <Link to="/app/file-ocr/overview">{t('nav.rulesFileOcr')}</Link>,
  }
  if (pathname.startsWith('/app/file-ocr/tasks')) {
    return [home, fileOcrBase, { title: t('nav.rulesFileOcrTaskList') }]
  }
  return [home, fileOcrBase, { title: t('nav.rulesFileOcrOverview') }]
}

export function AppBreadcrumb() {
  const { t } = useTranslation()
  const { pathname } = useLocation()

  const items: ItemType[] = useMemo(() => {
    const home: ItemType = { title: <Link to="/app/overview">{t('breadcrumb.home')}</Link> }

    if (pathname.startsWith('/app/smart-review')) {
      return [home, { title: t('nav.smartReview') }]
    }
    const fileOcr = fileOcrBreadcrumb(pathname, t, home)
    if (fileOcr) return fileOcr
    const rules = rulesBreadcrumb(pathname, t, home)
    if (rules) return rules
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
