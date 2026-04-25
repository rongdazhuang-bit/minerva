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

export type SysDictListPage = {
  items: SysDictListItem[]
  total: number
}

export type ListDictsParams = {
  page?: number
  page_size?: number
}

export function listDicts(workspaceId: string, params?: ListDictsParams) {
  const sp = new URLSearchParams()
  if (params?.page != null) sp.set('page', String(params.page))
  if (params?.page_size != null) sp.set('page_size', String(params.page_size))
  const q = sp.toString()
  return apiJson<SysDictListPage>(
    `/workspaces/${workspaceId}/dicts${q ? `?${q}` : ''}`,
  )
}

/** Load all dictionaries for the workspace (follows pagination until complete). */
export async function listAllDicts(workspaceId: string): Promise<SysDictListItem[]> {
  const pageSize = 100
  const out: SysDictListItem[] = []
  let page = 1
  while (true) {
    const { items, total } = await listDicts(workspaceId, { page, page_size: pageSize })
    out.push(...items)
    if (out.length >= total || items.length === 0) break
    page += 1
  }
  return out
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
