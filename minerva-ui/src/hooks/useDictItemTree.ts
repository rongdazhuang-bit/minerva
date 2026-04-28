import { useQuery } from '@tanstack/react-query'
import { fetchDictByCode } from '@/api/dicts'
import { useAuth } from '@/app/AuthContext'
import { dictQueryKeys } from '@/constants/dictQueryKeys'

export const DICT_QUERY_STALE_MS = 3 * 60 * 1000
export const DICT_QUERY_GC_MS = 5 * 60 * 1000
const DICT_PAGE = 1
const DICT_PAGE_SIZE = 100

export function useDictItemTree(dictCode: string) {
  const { workspaceId } = useAuth()
  return useQuery({
    queryKey: dictQueryKeys.byCode(
      workspaceId ?? '',
      dictCode,
      DICT_PAGE,
      DICT_PAGE_SIZE,
    ),
    queryFn: () => fetchDictByCode(workspaceId!, dictCode),
    enabled: Boolean(workspaceId && dictCode),
    staleTime: DICT_QUERY_STALE_MS,
    gcTime: DICT_QUERY_GC_MS,
  })
}
