import { navMenusQueryKeys } from '@/constants/navMenusQueryKeys'
import { queryClient } from '@/lib/queryClient'

/** Invalidate cached sidebar nav after menu CRUD or role changes that affect nav. */
export function notifyMenuNavRefresh(): void {
  void queryClient.invalidateQueries({ queryKey: navMenusQueryKeys.all })
}
