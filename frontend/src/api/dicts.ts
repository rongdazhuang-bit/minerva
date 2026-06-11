import { apiJson } from '@/api/client'

/** 嵌套子项，与 `GET /sys/dicts?code=` 中 `item_tree` 一致。 */
export type SysDictItemNode = {
  id: string
  dict_uuid: string
  parent_uuid: string | null
  code: string
  name: string
  item_sort: number | null
  create_at: string | null
  update_at: string | null
  children: SysDictItemNode[]
}

export type SysDictListItem = {
  id: string
  dict_code: string
  dict_name: string | null
  dict_sort: number | null
  create_at: string | null
  update_at: string | null
  /** 仅 `code` 查询时返回。 */
  item_tree?: SysDictItemNode[] | null
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
  /** 按 `dict_code` 精确过滤；有值时同页返回 `item_tree`。 */
  code?: string
  /** 列表筛选：字典编码模糊匹配。 */
  dict_code?: string
  /** 列表筛选：字典名称模糊匹配。 */
  dict_name?: string
}

export function listDicts(params?: ListDictsParams) {
  const sp = new URLSearchParams()
  if (params?.page != null) sp.set('page', String(params.page))
  if (params?.page_size != null) sp.set('page_size', String(params.page_size))
  if (params?.code != null && params.code !== '') sp.set('code', params.code)
  if (params?.dict_code != null && params.dict_code !== '') sp.set('dict_code', params.dict_code)
  if (params?.dict_name != null && params.dict_name !== '') sp.set('dict_name', params.dict_name)
  const q = sp.toString()
  return apiJson<SysDictListPage>(`/sys/dicts${q ? `?${q}` : ''}`)
}

const DICT_BY_CODE_PAGE_SIZE = 100

export type FetchDictByCodeResult = {
  listRow: SysDictListItem | null
  itemTree: SysDictItemNode[]
  /** 深度优先展开，便于表格 `code`→`name` 映射（含多级子项）。 */
  flat: SysDictItem[]
}

export function flattenDictItemTree(
  nodes: SysDictItemNode[] | null | undefined,
): SysDictItem[] {
  if (!nodes?.length) return []
  const out: SysDictItem[] = []
  const walk = (n: SysDictItemNode) => {
    const { children, ...rest } = n
    out.push(rest)
    for (const c of children) walk(c)
  }
  for (const n of nodes) walk(n)
  return out
}

/** 单次请求：按 `dict_code` 取主表行 + 树形子项。 */
export async function fetchDictByCode(dictCode: string): Promise<FetchDictByCodeResult> {
  const { items, total } = await listDicts({
    page: 1,
    page_size: DICT_BY_CODE_PAGE_SIZE,
    code: dictCode,
  })
  if (total === 0 || items.length === 0) {
    return { listRow: null, itemTree: [], flat: [] }
  }
  const row = items[0]
  const itemTree = row.item_tree ?? []
  return {
    listRow: row,
    itemTree,
    flat: flattenDictItemTree(itemTree),
  }
}

/** Load all platform dictionaries (follows pagination until complete). */
export async function listAllDicts(): Promise<SysDictListItem[]> {
  const pageSize = 100
  const out: SysDictListItem[] = []
  let page = 1
  while (true) {
    const { items, total } = await listDicts({ page, page_size: pageSize })
    out.push(...items)
    if (out.length >= total || items.length === 0) break
    page += 1
  }
  return out
}

export function createDict(body: SysDictCreateBody) {
  return apiJson<SysDictListItem>('/sys/dicts', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function patchDict(dictId: string, body: SysDictPatchBody) {
  return apiJson<SysDictListItem>(`/sys/dicts/${dictId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteDict(dictId: string) {
  return apiJson<null>(`/sys/dicts/${dictId}`, {
    method: 'DELETE',
  })
}

export function listDictItems(dictId: string) {
  return apiJson<SysDictItem[]>(`/sys/dicts/${dictId}/items`)
}

export function createDictItem(dictId: string, body: SysDictItemCreateBody) {
  return apiJson<SysDictItem>(`/sys/dicts/${dictId}/items`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function patchDictItem(dictId: string, itemId: string, body: SysDictItemPatchBody) {
  return apiJson<SysDictItem>(`/sys/dicts/${dictId}/items/${itemId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteDictItem(dictId: string, itemId: string) {
  return apiJson<null>(`/sys/dicts/${dictId}/items/${itemId}`, {
    method: 'DELETE',
  })
}
