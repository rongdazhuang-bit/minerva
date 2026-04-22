import { apiJson } from '@/api/client'
import type { RuleDetail, RuleListItem, RuleVersion } from '@/api/types'

export function listRules(workspaceId: string) {
  return apiJson<RuleListItem[]>(`/workspaces/${workspaceId}/rules`)
}

export function getRule(workspaceId: string, ruleId: string) {
  return apiJson<RuleDetail>(`/workspaces/${workspaceId}/rules/${ruleId}`)
}

export function createRule(
  workspaceId: string,
  body: { name: string; type: string; flow_json?: Record<string, unknown> },
) {
  return apiJson<RuleListItem>(`/workspaces/${workspaceId}/rules`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function addRuleVersion(
  workspaceId: string,
  ruleId: string,
  flowJson: Record<string, unknown>,
) {
  return apiJson<RuleVersion>(`/workspaces/${workspaceId}/rules/${ruleId}/versions`, {
    method: 'POST',
    body: JSON.stringify({ flow_json: flowJson }),
  })
}

export function publishVersion(
  workspaceId: string,
  ruleId: string,
  versionId: string,
) {
  return apiJson<RuleVersion>(
    `/workspaces/${workspaceId}/rules/${ruleId}/versions/${versionId}/publish`,
    { method: 'POST' },
  )
}
