/**
 * Agent skills filesystem management API (tenant owner/admin only).
 */
import { ApiError, apiJson, authFetch } from '@/api/client'
import { apiOrigin } from '@/api/config'

/** One skill package row in the global skills registry. */
export type SkillRegistryItem = {
  id: string
  description: string
  file_count: number
}

/** Indexed skills with on-disk file counts for the management UI. */
export type SkillRegistryOut = {
  skills: SkillRegistryItem[]
}

/** One node in a skill directory file tree. */
export type SkillFileTreeNode = {
  name: string
  path: string
  is_dir: boolean
  size?: number | null
  children?: SkillFileTreeNode[]
}

/** UTF-8 text payload for one skill file. */
export type SkillFileContentOut = {
  path: string
  content: string
}

/** Result of a write that may have refreshed skill_loader caches. */
export type SkillWriteResultOut = {
  path: string
  cache_reloaded: boolean
}

/** Response from uploading a zip skill package. */
export type SkillPackageUploadOut = {
  skill_id: string
}

function skillsMgmtBase(workspaceId: string) {
  return `${apiOrigin()}/workspaces/${workspaceId}/agent/v2/skills-mgmt`
}

async function parseJsonError(text: string, res: Response): Promise<never> {
  try {
    const j = JSON.parse(text) as { code?: string; message?: string }
    throw new ApiError(j.code ?? 'error', j.message ?? text)
  } catch (e) {
    if (e instanceof ApiError) throw e
    throw new ApiError('http', text || res.statusText)
  }
}

/** List indexed skills with descriptions and on-disk file counts. */
export function listSkillRegistry(workspaceId: string) {
  return apiJson<SkillRegistryOut>(`/workspaces/${workspaceId}/agent/v2/skills-mgmt/registry`)
}

/** Return the recursive file tree for one skill directory. */
export function getSkillTree(workspaceId: string, skillId: string) {
  return apiJson<SkillFileTreeNode[]>(
    `/workspaces/${workspaceId}/agent/v2/skills-mgmt/${encodeURIComponent(skillId)}/tree`,
  )
}

/** Read one UTF-8 text file under the global skills root. */
export function readSkillFile(workspaceId: string, path: string) {
  const params = new URLSearchParams({ path })
  return apiJson<SkillFileContentOut>(
    `/workspaces/${workspaceId}/agent/v2/skills-mgmt/files?${params}`,
  )
}

/** Save an editable skill text file and invalidate skill caches. */
export function writeSkillFile(workspaceId: string, path: string, content: string) {
  const params = new URLSearchParams({ path })
  return apiJson<SkillWriteResultOut>(
    `/workspaces/${workspaceId}/agent/v2/skills-mgmt/files?${params}`,
    {
      method: 'PUT',
      body: JSON.stringify({ content }),
    },
  )
}

/** Install one zip skill package whose archive root is a single directory. */
export async function uploadSkillPackage(
  workspaceId: string,
  file: File,
): Promise<SkillPackageUploadOut> {
  const form = new FormData()
  form.append('file', file)
  const res = await authFetch(`${skillsMgmtBase(workspaceId)}/upload`, {
    method: 'POST',
    body: form,
  })
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
  return JSON.parse(text) as SkillPackageUploadOut
}

/** Upload one file into an existing skill directory. */
export async function uploadSkillFile(
  workspaceId: string,
  dirPath: string,
  file: File,
): Promise<SkillWriteResultOut> {
  const params = new URLSearchParams({ path: dirPath })
  const form = new FormData()
  form.append('file', file)
  const res = await authFetch(
    `${skillsMgmtBase(workspaceId)}/files/upload?${params}`,
    {
      method: 'POST',
      body: form,
    },
  )
  const text = await res.text()
  if (!res.ok) await parseJsonError(text, res)
  return JSON.parse(text) as SkillWriteResultOut
}

/** Download one file from the global skills root. */
export async function downloadSkillFile(workspaceId: string, path: string): Promise<Blob> {
  const params = new URLSearchParams({ path })
  const res = await authFetch(
    `${skillsMgmtBase(workspaceId)}/files/download?${params}`,
  )
  if (!res.ok) {
    const text = await res.text()
    await parseJsonError(text, res)
  }
  return res.blob()
}

/** Delete one file or directory under the skills root. */
export function deleteSkillPath(workspaceId: string, path: string) {
  const params = new URLSearchParams({ path })
  return apiJson<null>(
    `/workspaces/${workspaceId}/agent/v2/skills-mgmt/files?${params}`,
    { method: 'DELETE' },
  )
}

/** Delete an entire skill package directory. */
export function deleteSkill(workspaceId: string, skillId: string) {
  return apiJson<null>(
    `/workspaces/${workspaceId}/agent/v2/skills-mgmt/${encodeURIComponent(skillId)}`,
    { method: 'DELETE' },
  )
}
