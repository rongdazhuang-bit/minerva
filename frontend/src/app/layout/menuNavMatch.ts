import type { SysMenuNode } from '@/api/menus'

export type MenuNavState = {
  selectedKey: string | null
  openKeys: string[]
}

/** Ant Design Menu item key for a nav node (must match buildSiderMenuItems). */
export function menuItemKey(node: SysMenuNode): string {
  return node.menu_key ?? node.id
}

/** Strip trailing slash for stable path comparison. */
export function normalizeMenuPath(path: string): string {
  if (path.length > 1 && path.endsWith('/')) return path.slice(0, -1)
  return path
}

/** Legacy route aliases that redirect but should highlight the same menu path. */
export function normalizePathnameForMenuMatch(pathname: string): string {
  const p = normalizeMenuPath(pathname)
  if (p === '/app/knowledge-base' || p.startsWith('/app/knowledge-base/')) {
    return `/app/dataset${p.slice('/app/knowledge-base'.length)}`
  }
  return p
}

/** True when current URL equals the menu path or is a nested route under it. */
export function menuPathMatches(pathname: string, menuPath: string): boolean {
  const current = normalizePathnameForMenuMatch(pathname)
  const target = normalizeMenuPath(menuPath)
  if (!target) return false
  if (current === target) return true
  return current.startsWith(`${target}/`)
}

type MenuHit = {
  node: SysMenuNode
  ancestors: SysMenuNode[]
}

/** Apply the same hide rules as buildSiderMenuItems before matching. */
export function filterNavMenuNodes(
  nodes: SysMenuNode[],
  hideMenuKeys?: Set<string>,
): SysMenuNode[] {
  return nodes
    .filter((n) => !n.menu_key || !hideMenuKeys?.has(n.menu_key))
    .map((n) => ({
      ...n,
      children: n.children?.length
        ? filterNavMenuNodes(n.children, hideMenuKeys)
        : undefined,
    }))
}

function findBestMenuHit(nodes: SysMenuNode[], pathname: string): MenuHit | null {
  let best: MenuHit | null = null
  let bestPathLen = -1

  const walk = (list: SysMenuNode[], ancestors: SysMenuNode[]) => {
    for (const node of list) {
      const path = node.path?.trim()
      if (path && menuPathMatches(pathname, path)) {
        const len = normalizeMenuPath(path).length
        if (len > bestPathLen) {
          bestPathLen = len
          best = { node, ancestors }
        }
      }
      if (node.children?.length) {
        walk(node.children, [...ancestors, node])
      }
    }
  }

  walk(nodes, [])
  return best
}

/** Resolve selected and open keys from nav tree + current pathname (longest path prefix wins). */
export function resolveMenuNavState(
  nodes: SysMenuNode[],
  pathname: string,
  hideMenuKeys?: Set<string>,
): MenuNavState {
  const filtered = filterNavMenuNodes(nodes, hideMenuKeys)
  const hit = findBestMenuHit(filtered, pathname)
  if (!hit) {
    return { selectedKey: null, openKeys: [] }
  }
  return {
    selectedKey: menuItemKey(hit.node),
    openKeys: hit.ancestors.map(menuItemKey),
  }
}
