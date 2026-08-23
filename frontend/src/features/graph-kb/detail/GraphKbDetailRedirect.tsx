/** Redirects legacy `/app/graph-kb/:graphId/*` URLs to the list page with modal query params. */

import { Navigate, useLocation, useParams } from 'react-router-dom'

const TAB_KEYS = ['documents', 'graph', 'summaries', 'qa', 'settings'] as const

/** Resolve tab key from the trailing path segment after graphId. */
function tabFromPath(pathname: string): (typeof TAB_KEYS)[number] {
  const segments = pathname.split('/').filter(Boolean)
  const lastSegment = segments[segments.length - 1]
  if (lastSegment && (TAB_KEYS as readonly string[]).includes(lastSegment)) {
    return lastSegment as (typeof TAB_KEYS)[number]
  }
  return 'documents'
}

/** Sends bookmarked detail routes to the list with `graphId` and `tab` search params. */
export function GraphKbDetailRedirect() {
  const { graphId = '' } = useParams()
  const location = useLocation()
  const tab = tabFromPath(location.pathname)

  if (!graphId) {
    return <Navigate to="/app/graph-kb" replace />
  }

  return <Navigate to={`/app/graph-kb?graphId=${encodeURIComponent(graphId)}&tab=${tab}`} replace />
}
