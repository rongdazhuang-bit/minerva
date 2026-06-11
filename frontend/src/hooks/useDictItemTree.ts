import { useQuery } from '@tanstack/react-query'
import { fetchDictByCode } from '@/api/dicts'
import { dictQueryKeys } from '@/constants/dictQueryKeys'

export const DICT_QUERY_STALE_MS = 3 * 60 * 1000
export const DICT_QUERY_GC_MS = 5 * 60 * 1000
const DICT_PAGE = 1
const DICT_PAGE_SIZE = 100

export function useDictItemTree(dictCode: string) {
  return useQuery({
    queryKey: dictQueryKeys.byCode(dictCode, DICT_PAGE, DICT_PAGE_SIZE),
    queryFn: () => fetchDictByCode(dictCode),
    enabled: Boolean(dictCode),
    staleTime: DICT_QUERY_STALE_MS,
    gcTime: DICT_QUERY_GC_MS,
  })
}
