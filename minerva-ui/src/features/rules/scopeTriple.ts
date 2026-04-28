import type { DefaultOptionType } from 'antd/es/cascader'
import type { SysDictItem, SysDictItemNode } from '@/api/dicts'

/** 多级字典：第 1～3 级 code 依次对应 engineering_code / subject_code / document_type */
export const ENG_SUBJECT_DOC_DICT_CODE = 'RULE_ENG_SUBJECT_DOC'

export type ScopeTripleListParams = {
  engineering_code?: string
  subject_code?: string
  document_type?: string
}

export type ScopeTripleRow = {
  engineering_code: string | null
  subject_code: string | null
  document_type: string | null
}

export function buildCodeNameMap(items: SysDictItem[]) {
  const m = new Map<string, string>()
  for (const it of items) {
    m.set(it.code, it.name)
  }
  return m
}

export function dictNodesToCascaderOptions(nodes: SysDictItemNode[]): DefaultOptionType[] {
  return nodes.map((n) => ({
    value: n.code,
    label: n.name,
    children: n.children?.length ? dictNodesToCascaderOptions(n.children) : undefined,
  }))
}

export function pathToTriple(path: string[] | undefined | null) {
  const p = path?.filter((x) => x != null && String(x).trim() !== '') ?? []
  return {
    engineering_code: p[0] ?? null,
    subject_code: p[1] ?? null,
    document_type: p[2] ?? null,
  }
}

export function tripleToPath(
  eng: string | null | undefined,
  sub: string | null | undefined,
  doc: string | null | undefined,
): string[] | undefined {
  if (!eng?.trim()) return undefined
  const e = eng.trim()
  const out: string[] = [e]
  if (sub?.trim()) {
    out.push(sub.trim())
    if (doc?.trim()) out.push(doc.trim())
  }
  return out
}

export function listParamsFromCascadePath(
  path: string[] | undefined,
): ScopeTripleListParams {
  const p = path?.filter(Boolean) ?? []
  const o: ScopeTripleListParams = {}
  if (p.length >= 1) o.engineering_code = p[0]
  if (p.length >= 2) o.subject_code = p[1]
  if (p.length >= 3) o.document_type = p[2]
  return o
}

export function formatScopeTriplePathLabel(row: ScopeTripleRow, nameByCode: Map<string, string>) {
  const parts: string[] = []
  for (const c of [row.engineering_code, row.subject_code, row.document_type]) {
    if (!c) continue
    parts.push(nameByCode.get(c) ?? c)
  }
  return parts.length ? parts.join(' / ') : '—'
}

/** 在非空编码序列上与树前缀匹配，兼容仅有专业/文档类型等业务旧数据时的回显。 */
export function findSequentialPathInTree(
  nodes: SysDictItemNode[],
  codes: string[],
): string[] | undefined {
  if (!codes.length || !nodes.length) return undefined
  const walk = (
    arr: SysDictItemNode[],
    depth: number,
    acc: string[],
  ): string[] | undefined => {
    const code = codes[depth]
    for (const n of arr) {
      if (n.code !== code) continue
      const next = [...acc, n.code]
      if (depth === codes.length - 1) return next
      const sub = walk(n.children ?? [], depth + 1, next)
      if (sub) return sub
    }
    return undefined
  }
  return walk(nodes, 0, [])
}
