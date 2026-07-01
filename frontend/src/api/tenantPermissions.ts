/** HTTP client for tenant menu permissions, administrators, and member pickers. */
import { apiJson } from '@/api/client'
import type { SysMenuNode } from '@/api/menus'
import { listMenus } from '@/api/menus'

/** GET tenant permissions response. */
export type SysTenantPermissions = {
  menu_ids: string[]
}

/** One tenant member row for admin multi-select. */
export type SysTenantUserOption = {
  id: string
  nickname: string
  email: string
  status: boolean
}

/** GET tenant administrators response. */
export type SysTenantAdmins = {
  user_ids: string[]
}

/** Load enabled menu ids for a tenant. */
export function getTenantPermissions(tenantId: string) {
  return apiJson<SysTenantPermissions>(`/sys/tenants/${tenantId}/permissions`)
}

/** Replace tenant menu permissions. */
export function putTenantPermissions(tenantId: string, menu_ids: string[]) {
  return apiJson<SysTenantPermissions>(`/sys/tenants/${tenantId}/permissions`, {
    method: 'PUT',
    body: JSON.stringify({ menu_ids }),
  })
}

/** Load tenant administrator user ids. */
export function getTenantAdmins(tenantId: string) {
  return apiJson<SysTenantAdmins>(`/sys/tenants/${tenantId}/admins`)
}

/** Replace tenant administrator grants. */
export function putTenantAdmins(tenantId: string, user_ids: string[]) {
  return apiJson<SysTenantAdmins>(`/sys/tenants/${tenantId}/admins`, {
    method: 'PUT',
    body: JSON.stringify({ user_ids }),
  })
}

/** List tenant members for administrator picker options. */
export function listTenantUsers(tenantId: string) {
  return apiJson<{ items: SysTenantUserOption[] }>(`/sys/tenants/${tenantId}/users`)
}

/** List active platform users for administrator picker on tenant create form. */
export function listPlatformUserOptions() {
  return apiJson<{ items: SysTenantUserOption[] }>('/sys/tenants/meta/user-options')
}

/** Load full sys_menu tree for tenant permission picker (same as menu config). */
export function listTenantPermissionMenuTree(): Promise<SysMenuNode[]> {
  return listMenus()
}
