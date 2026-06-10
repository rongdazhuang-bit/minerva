import { apiJson } from '@/api/client'

/** Nested menu node from list/nav endpoints. */
export type SysMenuNode = {
  id: string
  parent_id: string | null
  menu_name: string
  i18n_key: string | null
  menu_key: string | null
  order_num: number
  path: string | null
  menu_type: 'M' | 'C' | 'F'
  perms: string | null
  icon: string | null
  visible: boolean
  status: boolean
  is_external: boolean
  remark: string | null
  create_at: string | null
  update_at: string | null
  children?: SysMenuNode[]
}

export type SysMenuCreateBody = {
  parent_id?: string | null
  menu_name: string
  i18n_key?: string | null
  menu_key?: string | null
  order_num?: number
  path?: string | null
  menu_type: 'M' | 'C' | 'F'
  perms?: string | null
  icon?: string | null
  visible?: boolean
  status?: boolean
  is_external?: boolean
  remark?: string | null
}

export type SysMenuPatchBody = Partial<SysMenuCreateBody>

export type MenuDeleteResult = {
  deleted_count: number
}

export type ListMenusParams = {
  menu_name?: string
  status?: boolean
}

export function listMenus(params?: ListMenusParams) {
  const sp = new URLSearchParams()
  if (params?.menu_name?.trim()) sp.set('menu_name', params.menu_name.trim())
  if (params?.status != null) sp.set('status', String(params.status))
  const q = sp.toString()
  return apiJson<SysMenuNode[]>(`/sys/menus${q ? `?${q}` : ''}`)
}

export function listNavMenus() {
  return apiJson<SysMenuNode[]>('/sys/menus/nav')
}

export function createMenu(body: SysMenuCreateBody) {
  return apiJson<SysMenuNode>('/sys/menus', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function patchMenu(id: string, body: SysMenuPatchBody) {
  return apiJson<SysMenuNode>(`/sys/menus/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteMenu(id: string) {
  return apiJson<MenuDeleteResult>(`/sys/menus/${id}`, { method: 'DELETE' })
}
