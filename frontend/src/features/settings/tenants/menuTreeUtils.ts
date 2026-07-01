/** Tree helpers shared by tenant permission drawer and role form. */
import type { DataNode } from 'antd/es/tree'
import type { SysMenuNode } from '@/api/menus'

/** Collect all node keys from a menu tree. */
export function collectAllKeys(nodes: SysMenuNode[]): string[] {
  const out: string[] = []
  const walk = (items: SysMenuNode[]) => {
    for (const n of items) {
      out.push(n.id)
      if (n.children?.length) walk(n.children)
    }
  }
  walk(nodes)
  return out
}

/** Build Ant Design tree nodes from menu API tree. */
export function buildTreeData(nodes: SysMenuNode[]): DataNode[] {
  return nodes.map((n) => {
    let title = n.menu_name
    if (n.menu_type === 'F' && n.perms) {
      title = `${n.menu_name} (${n.perms})`
    }
    return {
      key: n.id,
      title,
      children: n.children?.length ? buildTreeData(n.children) : undefined,
    }
  })
}
