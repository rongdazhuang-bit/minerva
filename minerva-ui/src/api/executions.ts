import { apiJson } from '@/api/client'
import type { ExecutionDetail, ExecutionListItem } from '@/api/types'

export function listExecutions(workspaceId: string) {
  return apiJson<ExecutionListItem[]>(`/workspaces/${workspaceId}/executions`)
}

export function getExecution(workspaceId: string, executionId: string) {
  return apiJson<ExecutionDetail>(
    `/workspaces/${workspaceId}/executions/${executionId}`,
  )
}

export function startExecution(
  workspaceId: string,
  body: { rule_id: string; input?: Record<string, unknown> },
) {
  return apiJson<ExecutionListItem>(`/workspaces/${workspaceId}/executions`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
