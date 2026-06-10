import type { MenuProps } from 'antd'
import type { TFunction } from 'i18next'
import type { SysMenuNode } from '@/api/menus'
import { menuItemKey } from '@/app/layout/menuNavMatch'
import { resolveMenuIcon } from '@/features/settings/menu-config/menuIconMap'

type BuildOpts = {
  t: TFunction
  nav: (path: string) => void
  hideMenuKeys?: Set<string>
}

/** Convert API nav tree nodes into Ant Design Menu items. */
export function buildSiderMenuItems(
  nodes: SysMenuNode[],
  opts: BuildOpts,
): MenuProps['items'] {
  return nodes
    .filter((n) => !n.menu_key || !opts.hideMenuKeys?.has(n.menu_key))
    .map((n) => {
      const key = menuItemKey(n)
      const label = n.i18n_key ? opts.t(n.i18n_key) : n.menu_name
      const icon = resolveMenuIcon(n.icon)
      const children = n.children?.length
        ? buildSiderMenuItems(n.children, opts)
        : undefined
      if (children && children.length > 0) {
        return { key, icon, label, children }
      }
      return {
        key,
        icon,
        label,
        onClick: () => {
          if (!n.path) return
          if (n.is_external) window.open(n.path, '_blank', 'noopener')
          else opts.nav(n.path)
        },
      }
    })
}
