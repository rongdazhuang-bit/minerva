/** Shared GraphKB form helpers: engines, ACL, model keys, and member options. */

import { listUsers } from '@/api/users'

/** GraphRAG Microsoft-style index engine. */
export const ENGINE_GRAPHRAG = 'graphrag'
/** LightRAG incremental index engine. */
export const ENGINE_LIGHTRAG = 'lightrag'

/** Creator-only ACL. */
export const PERMISSION_ONLY_ME = 'only_me'
/** Creator plus explicit member list. */
export const PERMISSION_PARTIAL_MEMBERS = 'partial_members'
/** Any workspace member may view. */
export const PERMISSION_ALL_TEAM_MEMBERS = 'all_team_members'

/** Allowed upload suffixes (must match backend ``ALLOWED_UPLOAD_SUFFIXES``). */
export const GRAPH_KB_UPLOAD_ACCEPT = '.txt,.md,.pdf,.docx,.html,.csv'

/** Index / document status values from the GraphKB API. */
export const GRAPH_KB_ACTIVE_INDEX_STATUSES = new Set(['pending', 'running'])

export type GraphKbFormValues = {
  name: string
  description?: string
  engine: string
  permission: string
  member_user_ids?: string[]
  llm_model_key?: string
  embedding_model_key?: string
}

export type SelectOption = {
  value: string
  label: string
}

/** Build Ant Select value ``provider::model``. */
export function toModelKey(
  provider: string | null | undefined,
  model: string | null | undefined,
): string | undefined {
  if (!provider?.trim() || !model?.trim()) return undefined
  return `${provider}::${model}`
}

/** Split a composite model Select value into provider and model name. */
export function parseModelKey(key?: string | null): {
  provider: string | null
  model: string | null
} {
  if (!key?.includes('::')) {
    return { provider: null, model: null }
  }
  const [provider, model] = key.split('::', 2)
  return { provider: provider || null, model: model || null }
}

/** Map indexing / job status to an Ant Design Tag color. */
export function indexingStatusColor(status: string): string {
  switch (status) {
    case 'completed':
      return 'green'
    case 'running':
      return 'blue'
    case 'pending':
      return 'gold'
    case 'failed':
      return 'red'
    default:
      return 'default'
  }
}

/** Format stored byte length for the documents table. */
export function formatSizeBytes(value: number | null | undefined): string {
  if (value == null) return '—'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1).replace(/\.0$/, '')} KB`
  return `${(value / (1024 * 1024)).toFixed(1).replace(/\.0$/, '')} MB`
}

/** Return true when the filename suffix is accepted by GraphKB upload. */
export function isGraphKbAllowedExtension(filename: string): boolean {
  const lower = filename.trim().toLowerCase()
  return GRAPH_KB_UPLOAD_ACCEPT.split(',').some((ext) => lower.endsWith(ext))
}

/**
 * Load enabled workspace members for the ACL multi-select.
 * Uses a larger page size only to collapse pagination, not as the UI default.
 */
export async function listWorkspaceMemberOptions(workspaceId: string): Promise<SelectOption[]> {
  const pageSize = 100
  const first = await listUsers(workspaceId, { page: 1, page_size: pageSize, status: true })
  const items = [...first.items]
  const pages = Math.max(1, Math.ceil(first.total / pageSize))
  for (let page = 2; page <= pages; page += 1) {
    const next = await listUsers(workspaceId, { page, page_size: pageSize, status: true })
    items.push(...next.items)
  }
  return items.map((row) => ({
    value: row.id,
    label: row.nickname?.trim() ? `${row.nickname} (${row.email})` : row.email,
  }))
}
