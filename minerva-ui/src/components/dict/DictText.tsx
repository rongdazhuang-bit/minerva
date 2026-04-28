import { useMemo } from 'react'
import { useDictItemTree } from '@/hooks/useDictItemTree'

type DictTextProps = {
  dictCode: string
  value: string | null | undefined
  /** 无映射时展示；默认回退为 `value`。 */
  fallback?: string
}

/** 将存库的 item `code` 显示为字典 `name`（多级树展平后匹配）。 */
export function DictText({ dictCode, value, fallback }: DictTextProps) {
  const { data, isLoading } = useDictItemTree(dictCode)
  const label = useMemo(() => {
    const code = value ?? ''
    if (!code) return null
    for (const it of data?.flat ?? []) {
      if (it.code === code) return it.name
    }
    return null
  }, [data?.flat, value])

  if (isLoading) return '…'
  if (value == null || value === '') return '—'
  if (label != null) return label
  return fallback ?? value
}
