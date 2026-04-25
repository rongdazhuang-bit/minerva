import { apiJson } from '@/api/client'

export type ModelProviderGroupItem = {
  id: string
  model_name: string
  model_type: string
  enabled: boolean
  load_balancing_enabled: boolean
  auth_type: string
  endpoint_url: string | null
  has_api_key: boolean
  has_password: boolean
  context_size: number | null
  max_tokens_to_sample: number | null
  model_config: string | null
  create_at: string | null
  update_at: string | null
}

export type ModelProviderGroup = {
  provider_name: string
  items: ModelProviderGroupItem[]
}

export type ModelProviderListItem = ModelProviderGroupItem & {
  provider_name: string
}

export type ModelProviderDetail = {
  id: string
  workspace_id: string
  provider_name: string
  model_name: string
  model_type: string
  enabled: boolean
  load_balancing_enabled: boolean
  auth_type: string
  endpoint_url: string | null
  api_key: string | null
  auth_name: string | null
  auth_passwd: string | null
  context_size: number | null
  max_tokens_to_sample: number | null
  model_config: string | null
  create_at: string | null
  update_at: string | null
}

export type ModelProviderCreateBody = {
  provider_name: string
  model_name: string
  model_type: string
  enabled: boolean
  load_balancing_enabled: boolean
  auth_type: string
  endpoint_url?: string | null
  api_key?: string | null
  auth_name?: string | null
  auth_passwd?: string | null
  context_size?: number | null
  max_tokens_to_sample?: number | null
  model_config?: string | null
}

export type ModelProviderPatchBody = Partial<ModelProviderCreateBody>

export function listModelProvidersGrouped(workspaceId: string) {
  return apiJson<ModelProviderGroup[]>(`/workspaces/${workspaceId}/model-providers/grouped`)
}

export function listModelProviders(workspaceId: string) {
  return apiJson<ModelProviderListItem[]>(`/workspaces/${workspaceId}/model-providers/models`)
}

export function createModelProvider(workspaceId: string, body: ModelProviderCreateBody) {
  return apiJson<ModelProviderDetail>(`/workspaces/${workspaceId}/model-providers/models`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getModelProvider(workspaceId: string, modelId: string) {
  return apiJson<ModelProviderDetail>(
    `/workspaces/${workspaceId}/model-providers/models/${modelId}`,
  )
}

export function patchModelProvider(
  workspaceId: string,
  modelId: string,
  body: ModelProviderPatchBody,
) {
  return apiJson<ModelProviderDetail>(
    `/workspaces/${workspaceId}/model-providers/models/${modelId}`,
    {
      method: 'PATCH',
      body: JSON.stringify(body),
    },
  )
}

export function deleteModelProvider(workspaceId: string, modelId: string) {
  return apiJson<null>(`/workspaces/${workspaceId}/model-providers/models/${modelId}`, {
    method: 'DELETE',
  })
}
