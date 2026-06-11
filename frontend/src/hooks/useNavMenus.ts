import { useQuery } from '@tanstack/react-query'
import { listNavMenus } from '@/api/menus'
import { useAuth } from '@/app/AuthContext'
import { navMenusQueryKeys } from '@/constants/navMenusQueryKeys'

/** Cached sidebar nav tree; dedupes concurrent fetches (e.g. StrictMode remount). */
export function useNavMenus() {
  const { workspaceId, isAuthenticated } = useAuth()
  return useQuery({
    queryKey: navMenusQueryKeys.byWorkspace(workspaceId ?? ''),
    queryFn: listNavMenus,
    enabled: isAuthenticated && Boolean(workspaceId),
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  })
}
