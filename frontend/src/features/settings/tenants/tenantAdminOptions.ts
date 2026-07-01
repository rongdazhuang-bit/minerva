import type { SysTenantUserOption } from '@/api/tenantPermissions'

/** Build Select options from tenant members plus orphan administrator ids. */
export function buildTenantAdminSelectOptions(
  members: SysTenantUserOption[],
  selectedAdminIds: string[],
  orphanLabel: (id: string) => string,
) {
  const memberById = new Map(members.map((u) => [u.id, u]))
  const options = members.map((u) => ({
    value: u.id,
    label: `${u.nickname} (${u.email})`,
  }))
  for (const id of selectedAdminIds) {
    if (!memberById.has(id)) {
      options.push({ value: id, label: orphanLabel(id) })
    }
  }
  return options
}
