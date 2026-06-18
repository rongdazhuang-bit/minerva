import { apiJson } from '@/api/client'

export type McpTransport = 'STDIO' | 'SSE' | 'STREAMABLE_HTTP'

export type McpClientListItem = {
  id: string
  name: string
  transport: McpTransport
  enabled: boolean
  remark: string | null
  last_test_at: string | null
  last_test_ok: boolean | null
  has_secrets: boolean
  create_at: string | null
  update_at: string | null
}

export type McpClientDetail = McpClientListItem & {
  workspace_id: string
  config: Record<string, unknown>
  secrets: Record<string, unknown>
}

export type McpClientBody = {
  name: string
  transport: McpTransport
  config: Record<string, unknown>
  secrets?: Record<string, unknown>
  enabled?: boolean
  remark?: string | null
}

export type McpTestResult = {
  ok: boolean
  tool_names: string[]
  error_code?: string | null
  error_message?: string | null
}

export type McpServerListItem = {
  id: string
  name: string
  slug: string
  enabled: boolean
  auth_type: string
  has_auth_secret: boolean
  exposure: Record<string, unknown>
  remark: string | null
  create_at: string | null
  update_at: string | null
}

export type McpServerDetail = McpServerListItem & {
  workspace_id: string
  auth_secret: string | null
}

export type McpServerBody = {
  name: string
  slug: string
  exposure?: Record<string, unknown>
  enabled?: boolean
  auth_type?: 'NONE' | 'BEARER' | 'API_KEY'
  auth_secret?: string | null
  remark?: string | null
}

export type McpRuntimeStatus = {
  client_enabled: boolean
  server_enabled: boolean
}

export function getMcpRuntimeStatus(workspaceId: string) {
  return apiJson<McpRuntimeStatus>(`/workspaces/${workspaceId}/mcp/runtime-status`)
}

export function listMcpClients(workspaceId: string) {
  return apiJson<McpClientListItem[]>(`/workspaces/${workspaceId}/mcp/clients`)
}

export function getMcpClient(workspaceId: string, clientId: string) {
  return apiJson<McpClientDetail>(`/workspaces/${workspaceId}/mcp/clients/${clientId}`)
}

export function testMcpClient(workspaceId: string, body: Pick<McpClientBody, 'transport' | 'config' | 'secrets'>) {
  return apiJson<McpTestResult>(`/workspaces/${workspaceId}/mcp/clients/test`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function createMcpClient(workspaceId: string, body: McpClientBody) {
  return apiJson<McpClientDetail>(`/workspaces/${workspaceId}/mcp/clients`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function patchMcpClient(workspaceId: string, clientId: string, body: Partial<McpClientBody>) {
  return apiJson<McpClientDetail>(`/workspaces/${workspaceId}/mcp/clients/${clientId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteMcpClient(workspaceId: string, clientId: string) {
  return apiJson<void>(`/workspaces/${workspaceId}/mcp/clients/${clientId}`, { method: 'DELETE' })
}

export function listMcpServers(workspaceId: string) {
  return apiJson<McpServerListItem[]>(`/workspaces/${workspaceId}/mcp/servers`)
}

export function createMcpServer(workspaceId: string, body: McpServerBody) {
  return apiJson<McpServerDetail>(`/workspaces/${workspaceId}/mcp/servers`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function patchMcpServer(workspaceId: string, serverId: string, body: Partial<McpServerBody>) {
  return apiJson<McpServerDetail>(`/workspaces/${workspaceId}/mcp/servers/${serverId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteMcpServer(workspaceId: string, serverId: string) {
  return apiJson<void>(`/workspaces/${workspaceId}/mcp/servers/${serverId}`, { method: 'DELETE' })
}
