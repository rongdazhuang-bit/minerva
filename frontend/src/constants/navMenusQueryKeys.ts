/** React Query keys for sidebar nav menu (`GET /sys/menus/nav`). */
export const navMenusQueryKeys = {
  all: ['sys', 'menus', 'nav'] as const,
  byWorkspace: (workspaceId: string) =>
    [...navMenusQueryKeys.all, workspaceId] as const,
}
