/** Cross-component signal to reload sidebar nav after menu CRUD. */

type NavRefreshListener = () => void

const listeners = new Set<NavRefreshListener>()

/** Subscribe to menu nav refresh events; returns unsubscribe. */
export function subscribeMenuNavRefresh(listener: NavRefreshListener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Notify AppLayout (and others) to re-fetch `/sys/menus/nav`. */
export function notifyMenuNavRefresh(): void {
  for (const listener of listeners) {
    listener()
  }
}
