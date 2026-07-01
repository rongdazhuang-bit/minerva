import { apiJson } from '@/api/client'

/** All platform feature entitlement codes (align with backend FEATURE_CODES). */
export const TENANT_FEATURE_OPTIONS = [
  { value: 'feature:agent', labelKey: 'entitlements.featureAgent' },
  { value: 'feature:dataset', labelKey: 'entitlements.featureDataset' },
  { value: 'feature:ocr', labelKey: 'entitlements.featureOcr' },
  { value: 'feature:skills', labelKey: 'entitlements.featureSkills' },
  { value: 'feature:translate', labelKey: 'entitlements.featureTranslate' },
  { value: 'feature:rules', labelKey: 'entitlements.featureRules' },
  { value: 'feature:file_storage', labelKey: 'entitlements.featureFileStorage' },
] as const

/** GET tenant entitlements response. */
export type SysTenantEntitlements = {
  feature_codes: string[]
}

/** Load enabled feature codes for a tenant. */
export function getTenantEntitlements(tenantId: string) {
  return apiJson<SysTenantEntitlements>(`/sys/tenants/${tenantId}/entitlements`)
}

/** Replace tenant feature entitlements. */
export function putTenantEntitlements(tenantId: string, feature_codes: string[]) {
  return apiJson<SysTenantEntitlements>(`/sys/tenants/${tenantId}/entitlements`, {
    method: 'PUT',
    body: JSON.stringify({ feature_codes }),
  })
}

/** GET tenant administrator user ids. */
export type SysTenantAdmins = {
  user_ids: string[]
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
