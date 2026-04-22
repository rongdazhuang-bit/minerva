export type TokenResponse = {
  access_token: string
  refresh_token: string
  token_type: string
}

export type RuleListItem = {
  id: string
  workspace_id: string
  name: string
  type: string
  created_at: string
  current_published_version_id: string | null
}

export type LatestVersion = {
  id: string
  version: number
  state: string
  flow_json: Record<string, unknown>
}

export type RuleDetail = RuleListItem & {
  latest_version: LatestVersion | null
}

export type RuleVersion = {
  id: string
  rule_id: string
  version: number
  state: string
}

export type ExecutionListItem = {
  id: string
  workspace_id: string
  rule_id: string
  rule_version_id: string
  status: string
  step_count: number
  error_code: string | null
  created_at: string
}

export type ExecutionEventItem = {
  id: string
  event_type: string
  payload: Record<string, unknown>
  created_at: string
}

export type ExecutionDetail = ExecutionListItem & {
  current_node_id: string | null
  error_detail: string | null
  input_json: Record<string, unknown>
  context_json: Record<string, unknown>
  events: ExecutionEventItem[]
}
