import { apiJson } from '@/api/client'

export type SysDictListItem = {
  id: string
  workspace_id: string
  dict_code: string
  dict_name: string | null
  dict_sort: number | null
  create_at: string | null
  update_at: string | null
}

export type SysDictCreateBody = {
  dict_code: string
  dict_name?: string | null
  dict_sort?: number | null
}

export type SysDictPatchBody = Partial<{
  dict_code: string
  dict_name: string | null
  dict_sort: number | null
}>

export type SysDictItem = {
  id: string
  dict_uuid: string
  parent_uuid: string | null
  code: string
  name: string
  item_sort: number | null
  create_at: string | null
  update_at: string | null
}

export type SysDictItemCreateBody = {
  code: string
  name: string
  item_sort?: number | null
  parent_uuid?: string | null
}

export type SysDictItemPatchBody = Partial<{
  code: string
  name: string
  item_sort: number | null
  parent_uuid: string | null
}>

export function listDicts(workspaceId: string) {
  return apiJson<SysDictListItem[]>(`/workspaces/${workspaceId}/dicts`)
}

export function createDict(workspaceId: string, body: SysDictCreateBody) {
  return apiJson<SysDictListItem>(`/workspaces/${workspaceId}/dicts`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function patchDict(workspaceId: string, dictId: string, body: SysDictPatchBody) {
  return apiJson<SysDictListItem>(`/workspaces/${workspaceId}/dicts/${dictId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteDict(workspaceId: string, dictId: string) {
  return apiJson<null>(`/workspaces/${workspaceId}/dicts/${dictId}`, {
    method: 'DELETE',
  })
}

export function listDictItems(workspaceId: string, dictId: string) {
  return apiJson<SysDictItem[]>(`/workspaces/${workspaceId}/dicts/${dictId}/items`)
}

export function createDictItem(
  workspaceId: string,
  dictId: string,
  body: SysDictItemCreateBody,
) {
  return apiJson<SysDictItem>(`/workspaces/${workspaceId}/dicts/${dictId}/items`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function patchDictItem(
  workspaceId: string,
  dictId: string,
  itemId: string,
  body: SysDictItemPatchBody,
) {
  return apiJson<SysDictItem>(
    `/workspaces/${workspaceId}/dicts/${dictId}/items/${itemId}`,
    {
      method: 'PATCH',
      body: JSON.stringify(body),
    },
  )
}

export function deleteDictItem(workspaceId: string, dictId: string, itemId: string) {
  return apiJson<null>(`/workspaces/${workspaceId}/dicts/${dictId}/items/${itemId}`, {
    method: 'DELETE',
  })
}
