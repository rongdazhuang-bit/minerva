import { useCallback, useEffect, useState } from 'react'
import type { TFunction } from 'i18next'
import type { NavigateFunction } from 'react-router-dom'
import type { SysMenuNode } from '@/api/menus'
import {
  OVERVIEW_PATH,
  resolveNavTagForPath,
  type ResolvedNavTag,
} from '@/app/layout/resolveNavTag'

/** One open page tag in the app shell nav bar. */
export type AppNavTag = ResolvedNavTag

type UseAppNavTagsArgs = {
  pathname: string
  navMenus: SysMenuNode[]
  hideMenuKeys?: Set<string>
  /** Wait for nav menus so menu-leaf keys are stable before opening tags. */
  ready: boolean
  t: TFunction
  navigate: NavigateFunction
}

type UseAppNavTagsResult = {
  tags: AppNavTag[]
  activeKey: string
  activateTag: (key: string) => void
  closeTag: (key: string) => void
}

/** Build the pinned overview tag (always first, never closable). */
function overviewTag(t: TFunction): AppNavTag {
  return {
    key: OVERVIEW_PATH,
    path: OVERVIEW_PATH,
    title: t('nav.overview'),
    closable: false,
  }
}

/** Ensure overview stays first and refresh its title when locale changes. */
function withPinnedOverview(tags: AppNavTag[], t: TFunction): AppNavTag[] {
  const rest = tags.filter((tag) => tag.key !== OVERVIEW_PATH)
  return [overviewTag(t), ...rest]
}

/**
 * Session-scoped multi-tag nav state for the app shell.
 * Syncs open tags from pathname; activate/close drive React Router navigation.
 */
export function useAppNavTags({
  pathname,
  navMenus,
  hideMenuKeys,
  ready,
  t,
  navigate,
}: UseAppNavTagsArgs): UseAppNavTagsResult {
  /** Open tags; overview is always first. */
  const [tags, setTags] = useState<AppNavTag[]>(() => [overviewTag(t)])
  /** Key of the tag matching the current route. */
  const [activeKey, setActiveKey] = useState(OVERVIEW_PATH)

  useEffect(() => {
    if (!ready) return
    const resolved = resolveNavTagForPath(navMenus, pathname, t, hideMenuKeys)
    setActiveKey(resolved.key)
    setTags((prev) => {
      const pinned = withPinnedOverview(prev, t)
      const idx = pinned.findIndex((tag) => tag.key === resolved.key)
      if (idx >= 0) {
        return pinned.map((tag, i) =>
          i === idx
            ? {
                ...tag,
                title: resolved.title,
                path: resolved.path,
                closable: resolved.closable,
              }
            : tag,
        )
      }
      if (resolved.key === OVERVIEW_PATH) return pinned
      return [...pinned, resolved]
    })
  }, [pathname, navMenus, hideMenuKeys, ready, t])

  const activateTag = useCallback(
    (key: string) => {
      const tag = tags.find((item) => item.key === key)
      if (!tag) return
      if (tag.path !== pathname) {
        void navigate(tag.path)
      }
    },
    [tags, pathname, navigate],
  )

  const closeTag = useCallback(
    (key: string) => {
      if (key === OVERVIEW_PATH) return

      setTags((prev) => {
        const pinned = withPinnedOverview(prev, t)
        const idx = pinned.findIndex((tag) => tag.key === key)
        if (idx < 0) return pinned
        const wasActive = key === activeKey
        const next = pinned.filter((tag) => tag.key !== key)
        if (wasActive) {
          const neighbor = next[idx] ?? next[idx - 1] ?? next[0]
          if (neighbor) void navigate(neighbor.path)
        }
        return next
      })
    },
    [activeKey, navigate, t],
  )

  return { tags, activeKey, activateTag, closeTag }
}
