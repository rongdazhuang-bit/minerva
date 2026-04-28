import { apiJson } from '@/api/client'

export type RuleBaseListItem = {
  id: string
  workspace_id: string
  sequence_number: number
  engineering_code: string | null
  subject_code: string | null
  serial_number: string | null
  document_type: string | null
  review_section: string
  review_object: string
  review_rules: string
  review_rules_ai: string | null
  review_result: string
  status: string
  create_at: string | null
  update_at: string | null
}

export type RuleBaseListPage = {
  items: RuleBaseListItem[]
  total: number
}

export type RuleBaseCreateBody = {
  sequence_number: number
  engineering_code?: string | null
  subject_code?: string | null
  serial_number?: string | null
  document_type?: string | null
  review_section: string
  review_object: string
  review_rules: string
  review_rules_ai?: string | null
  review_result: string
  status: 'Y' | 'N'
}

export type RuleBasePatchBody = Partial<{
  sequence_number: number
  engineering_code: string | null
  subject_code: string | null
  serial_number: string | null
  document_type: string | null
  review_section: string
  review_object: string
  review_rules: string
  review_rules_ai: string | null
  review_result: string
  status: 'Y' | 'N'
}>

export type ListRuleBaseParams = {
  page?: number
  page_size?: number
  status?: 'Y' | 'N'
  engineering_code?: string
  subject_code?: string
  document_type?: string
}

function ruleBasePath(workspaceId: string, suffix = '') {
  return `/workspaces/${workspaceId}/rule-base${suffix}`
}

export function listRuleBase(workspaceId: string, params?: ListRuleBaseParams) {
  const sp = new URLSearchParams()
  if (params?.page != null) sp.set('page', String(params.page))
  if (params?.page_size != null) sp.set('page_size', String(params.page_size))
  if (params?.status) sp.set('status', params.status)
  if (params?.engineering_code) sp.set('engineering_code', params.engineering_code)
  if (params?.subject_code) sp.set('subject_code', params.subject_code)
  if (params?.document_type) sp.set('document_type', params.document_type)
  const q = sp.toString()
  const path = ruleBasePath(workspaceId, '')
  return apiJson<RuleBaseListPage>(q ? `${path}?${q}` : path)
}

export function createRuleBase(workspaceId: string, body: RuleBaseCreateBody) {
  return apiJson<RuleBaseListItem>(ruleBasePath(workspaceId, ''), {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function patchRuleBase(
  workspaceId: string,
  ruleId: string,
  body: RuleBasePatchBody,
) {
  return apiJson<RuleBaseListItem>(ruleBasePath(workspaceId, `/${ruleId}`), {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteRuleBase(workspaceId: string, ruleId: string) {
  return apiJson<null>(ruleBasePath(workspaceId, `/${ruleId}`), {
    method: 'DELETE',
  })
}

export function polishReviewRules(
  workspaceId: string,
  body: { review_rules: string },
) {
  return apiJson<{ review_rules_ai: string }>(
    ruleBasePath(workspaceId, '/polish-review-rules'),
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  )
}
