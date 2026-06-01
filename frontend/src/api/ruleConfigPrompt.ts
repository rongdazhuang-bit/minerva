import { apiJson } from '@/api/client'

export type RuleConfigPromptListItem = {
  id: string
  workspace_id: string
  model_id: string
  provider_name: string
  model_name: string
  engineering_code: string | null
  subject_code: string | null
  document_type: string | null
  sys_prompt: string | null
  user_prompt: string | null
  chat_memory: string | null
  create_at: string | null
  update_at: string | null
}

export type RuleConfigPromptListPage = {
  items: RuleConfigPromptListItem[]
  total: number
}

export type RuleConfigPromptCreateBody = {
  model_id: string
  engineering_code?: string | null
  subject_code?: string | null
  document_type?: string | null
  sys_prompt?: string | null
  user_prompt?: string | null
  chat_memory?: string | null
}

export type RuleConfigPromptPatchBody = Partial<RuleConfigPromptCreateBody>

export type ListRuleConfigPromptParams = {
  page?: number
  page_size?: number
  engineering_code?: string
  subject_code?: string
  document_type?: string
}

function path(workspaceId: string, suffix = '') {
  return `/workspaces/${workspaceId}/rule-config/config-prompts${suffix}`
}

export function listRuleConfigPrompts(
  workspaceId: string,
  params?: ListRuleConfigPromptParams,
) {
  const sp = new URLSearchParams()
  if (params?.page != null) sp.set('page', String(params.page))
  if (params?.page_size != null) sp.set('page_size', String(params.page_size))
  if (params?.engineering_code) sp.set('engineering_code', params.engineering_code)
  if (params?.subject_code) sp.set('subject_code', params.subject_code)
  if (params?.document_type) sp.set('document_type', params.document_type)
  const q = sp.toString()
  const p = path(workspaceId, '')
  return apiJson<RuleConfigPromptListPage>(q ? `${p}?${q}` : p)
}

export function createRuleConfigPrompt(
  workspaceId: string,
  body: RuleConfigPromptCreateBody,
) {
  return apiJson<RuleConfigPromptListItem>(path(workspaceId, ''), {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function patchRuleConfigPrompt(
  workspaceId: string,
  configPromptId: string,
  body: RuleConfigPromptPatchBody,
) {
  return apiJson<RuleConfigPromptListItem>(path(workspaceId, `/${configPromptId}`), {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteRuleConfigPrompt(workspaceId: string, configPromptId: string) {
  return apiJson<null>(path(workspaceId, `/${configPromptId}`), { method: 'DELETE' })
}
