/** Fullscreen modal for graph knowledge base detail tabs. */

import { Modal } from 'antd'
import { useEffect, useState } from 'react'
import {
  GRAPH_KB_DETAIL_TABS,
  GraphKbSectionLayout,
  type GraphKbDetailTab,
} from '@/features/graph-kb/layout/GraphKbSectionLayout'
import './GraphKbDetailModal.css'

export type { GraphKbDetailTab }

export type GraphKbDetailModalProps = {
  open: boolean
  graphId: string | null
  /** Initial tab when the modal opens; tab switches are kept in local state. */
  initialTab?: GraphKbDetailTab
  onClose: () => void
}

/** Fullscreen modal host for documents, graph, summaries, Q&A, and settings tabs. */
export function GraphKbDetailModal({
  open,
  graphId,
  initialTab = 'documents',
  onClose,
}: GraphKbDetailModalProps) {
  const safeInitialTab = GRAPH_KB_DETAIL_TABS.includes(initialTab) ? initialTab : 'documents'
  const [activeTab, setActiveTab] = useState<GraphKbDetailTab>(safeInitialTab)

  useEffect(() => {
    if (open && graphId) {
      setActiveTab(safeInitialTab)
    }
  }, [open, graphId, safeInitialTab])

  return (
    <Modal
      open={open}
      title={null}
      width="100%"
      centered={false}
      wrapClassName="minerva-graph-kb-detail-modal"
      style={{ top: 0, maxWidth: '100vw', padding: 0, margin: 0 }}
      styles={{
        body: {
          flex: 1,
          minHeight: 0,
          overflow: 'hidden',
          padding: 0,
          display: 'flex',
          flexDirection: 'column',
        },
      }}
      footer={null}
      destroyOnHidden
      onCancel={onClose}
    >
      {graphId ? (
        <GraphKbSectionLayout graphId={graphId} activeTab={activeTab} onTabChange={setActiveTab} />
      ) : null}
    </Modal>
  )
}
