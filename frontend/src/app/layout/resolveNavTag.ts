import type { TFunction } from 'i18next'
import type { SysMenuNode } from '@/api/menus'
import {
  findBestMenuHit,
  filterNavMenuNodes,
  normalizeMenuPath,
  normalizePathnameForMenuMatch,
} from '@/app/layout/menuNavMatch'

/** Pinned overview route used as the first non-closable nav tag. */
export const OVERVIEW_PATH = '/app/overview'

/** Resolved identity + display title for one nav tag. */
export type ResolvedNavTag = {
  /** Stable tag key (menu leaf path or normalized pathname). */
  key: string
  /** Navigate target when the tag is clicked. */
  path: string
  /** Display title already translated when from i18n. */
  title: string
  /** False only for the pinned overview tag. */
  closable: boolean
}

/**
 * Fallback leaf title when the current pathname does not hit the nav menu tree.
 * Mirrors the former AppBreadcrumb leaf titles.
 */
export function resolveFallbackNavTitle(
  pathname: string,
  t: TFunction,
): string {
  const p = normalizePathnameForMenuMatch(pathname)

  if (p === OVERVIEW_PATH || p === '/app/overview/') return t('nav.overview')

  if (p.startsWith('/app/settings/models')) return t('settings.models')
  if (p.startsWith('/app/settings/ocr')) return t('settings.ocr')
  if (p.startsWith('/app/settings/file-storage')) return t('settings.fileStorage')
  if (p.startsWith('/app/settings/celery')) return t('settings.celery')
  if (p.startsWith('/app/settings/data-sources')) return t('settings.dataSources')
  if (p.startsWith('/app/settings/menus')) return t('settings.menuConfig')
  if (p.startsWith('/app/settings/users')) return t('settings.users')
  if (p.startsWith('/app/settings/roles')) return t('settings.roles')
  if (p.startsWith('/app/settings/grants')) return t('settings.grants')
  if (p.startsWith('/app/settings/permissions')) return t('settings.permissions')
  if (p.startsWith('/app/settings/tenants')) return t('settings.tenants')
  if (p.startsWith('/app/settings/dictionary')) return t('settings.dictionary')
  if (p.startsWith('/app/settings')) return t('nav.settings')

  if (p.startsWith('/app/agents/skills')) return t('nav.agentsSkills')
  if (p.startsWith('/app/agents/mcp')) return t('nav.agentsMcp')
  if (p.startsWith('/app/agents/memory')) return t('nav.agentsMemory')
  if (p.startsWith('/app/agents')) return t('nav.agentsChat')

  if (p.startsWith('/app/translate')) return t('nav.docTranslateTranslate')

  if (p.startsWith('/app/dataset') || p.startsWith('/app/knowledge-base')) {
    return t('nav.dataset')
  }

  if (p.startsWith('/app/smart-review/review-by-text')) {
    return t('nav.smartReviewTextToText')
  }
  if (p.startsWith('/app/smart-review/text-proofreading')) {
    return t('nav.smartReviewTextProofreading')
  }
  if (p.startsWith('/app/smart-review/drawing-review')) {
    return t('nav.smartReviewDrawingReview')
  }
  if (p.startsWith('/app/smart-review')) {
    return t('nav.smartReviewTextProofreading')
  }

  if (p.startsWith('/app/file-ocr/tasks')) return t('nav.rulesFileOcrTaskList')
  if (p.startsWith('/app/file-ocr')) return t('nav.rulesFileOcrOverview')

  if (p.startsWith('/app/rules/management')) return t('nav.rulesManagementList')
  if (p.startsWith('/app/rules/config/config-prompts')) {
    return t('nav.rulesPromptManagement')
  }
  if (p.startsWith('/app/rules')) return t('nav.rulesOverview')

  return t('breadcrumb.home')
}

/** Display label for a menu node (i18n when configured). */
export function resolveMenuNodeTitle(node: SysMenuNode, t: TFunction): string {
  return node.i18n_key ? t(node.i18n_key) : node.menu_name
}

/**
 * Resolve tag key/path/title for the current location from the nav tree.
 * Menu-leaf identity: nested detail URLs share the leaf menu path as key.
 */
export function resolveNavTagForPath(
  nodes: SysMenuNode[],
  pathname: string,
  t: TFunction,
  hideMenuKeys?: Set<string>,
): ResolvedNavTag {
  const normalized = normalizePathnameForMenuMatch(pathname)
  if (normalized === OVERVIEW_PATH) {
    return {
      key: OVERVIEW_PATH,
      path: OVERVIEW_PATH,
      title: t('nav.overview'),
      closable: false,
    }
  }

  const filtered = filterNavMenuNodes(nodes, hideMenuKeys)
  const hit = findBestMenuHit(filtered, pathname)
  if (hit?.node.path?.trim()) {
    const menuPath = normalizeMenuPath(hit.node.path.trim())
    return {
      key: menuPath,
      path: menuPath,
      title: resolveMenuNodeTitle(hit.node, t),
      closable: menuPath !== OVERVIEW_PATH,
    }
  }

  return {
    key: normalized,
    path: normalized,
    title: resolveFallbackNavTitle(pathname, t),
    closable: true,
  }
}
