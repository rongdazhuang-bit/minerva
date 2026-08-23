/** Detail layout with tabs for documents, graph, summaries, Q&A, and settings. */

import { Tabs } from 'antd'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import './GraphKbSectionLayout.css'

const TAB_KEYS = ['documents', 'graph', 'summaries', 'qa', 'settings'] as const

/** Resolve the active tab from the last path segment after graphId. */
function tabFromPath(pathname: string): (typeof TAB_KEYS)[number] {
  const lastSegment = pathname.split('/').filter(Boolean).at(-1)
  if (lastSegment && (TAB_KEYS as readonly string[]).includes(lastSegment)) {
    return lastSegment as (typeof TAB_KEYS)[number]
  }
  return 'documents'
}

/** Shell for `/app/graph-kb/:graphId/*` sub-routes. */
export function GraphKbSectionLayout() {
  const { t } = useTranslation()
  const { graphId = '' } = useParams()
  const navigate = useNavigate()
  const location = useLocation()

  const activeKey = useMemo(() => tabFromPath(location.pathname), [location.pathname])

  const tabItems = useMemo(
    () => [
      { key: 'documents', label: t('graphKb.tabs.documents') },
      { key: 'graph', label: t('graphKb.tabs.graph') },
      { key: 'summaries', label: t('graphKb.tabs.summaries') },
      { key: 'qa', label: t('graphKb.tabs.qa') },
      { key: 'settings', label: t('graphKb.tabs.settings') },
    ],
    [t],
  )

  if (!graphId) {
    return null
  }

  return (
    <div className="minerva-graph-kb-section-layout">
      <div className="minerva-graph-kb-section-layout__tabs">
        <Tabs
          activeKey={activeKey}
          items={tabItems}
          onChange={(key) => {
            navigate(`/app/graph-kb/${graphId}/${key}`)
          }}
        />
      </div>
      <div className="minerva-graph-kb-section-layout__body minerva-scrollbar-styled">
        <Outlet />
      </div>
    </div>
  )
}
