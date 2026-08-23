/** Detail layout with tabs for documents, graph, summaries, Q&A, and settings. */

import { Tabs } from 'antd'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { GraphKbDocumentsPage } from '@/features/graph-kb/documents/GraphKbDocumentsPage'
import { GraphKbGraphPage } from '@/features/graph-kb/graph/GraphKbGraphPage'
import { GraphKbQaPage } from '@/features/graph-kb/qa/GraphKbQaPage'
import { GraphKbSettingsPage } from '@/features/graph-kb/settings/GraphKbSettingsPage'
import { GraphKbProvider } from '@/features/graph-kb/shared/GraphKbContext'
import { GraphKbSummariesPage } from '@/features/graph-kb/summaries/GraphKbSummariesPage'
import './GraphKbSectionLayout.css'

export const GRAPH_KB_DETAIL_TABS = ['documents', 'graph', 'summaries', 'qa', 'settings'] as const

export type GraphKbDetailTab = (typeof GRAPH_KB_DETAIL_TABS)[number]

export type GraphKbSectionLayoutProps = {
  graphId: string
  activeTab: GraphKbDetailTab
  onTabChange: (tab: GraphKbDetailTab) => void
}

/** Renders the active tab panel for the graph KB detail shell. */
function GraphKbDetailTabPanel({ tab }: { tab: GraphKbDetailTab }) {
  switch (tab) {
    case 'documents':
      return <GraphKbDocumentsPage />
    case 'graph':
      return <GraphKbGraphPage />
    case 'summaries':
      return <GraphKbSummariesPage />
    case 'qa':
      return <GraphKbQaPage />
    case 'settings':
      return <GraphKbSettingsPage />
    default:
      return <GraphKbDocumentsPage />
  }
}

/** Tabbed shell for graph KB detail inside the fullscreen modal. */
export function GraphKbSectionLayout({ graphId, activeTab, onTabChange }: GraphKbSectionLayoutProps) {
  const { t } = useTranslation()

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
    <GraphKbProvider graphId={graphId}>
      <div className="minerva-graph-kb-section-layout">
        <div className="minerva-graph-kb-section-layout__tabs">
          <Tabs
            activeKey={activeTab}
            items={tabItems}
            onChange={(key) => {
              onTabChange(key as GraphKbDetailTab)
            }}
          />
        </div>
        <div className="minerva-graph-kb-section-layout__body minerva-scrollbar-styled">
          <GraphKbDetailTabPanel tab={activeTab} />
        </div>
      </div>
    </GraphKbProvider>
  )
}
