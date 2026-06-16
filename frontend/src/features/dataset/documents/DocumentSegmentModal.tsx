/** Fullscreen modal host for document segment view or config panels. */
import { Modal } from 'antd'
import { useEffect, useState } from 'react'
import { DocumentSegmentConfigPanel } from './DocumentSegmentConfigPanel'
import { DocumentSegmentsViewPanel } from './DocumentSegmentsViewPanel'
import './DocumentSegmentModal.css'

export type DocumentSegmentModalMode = 'view' | 'config'

export type DocumentSegmentModalProps = {
  open: boolean
  mode: DocumentSegmentModalMode
  datasetId: string
  documentId: string | null
  onClose: () => void
}

/** Opens document segments or segmentation config in a fullscreen modal. */
export function DocumentSegmentModal({
  open,
  mode,
  datasetId,
  documentId,
  onClose,
}: DocumentSegmentModalProps) {
  const [activeDocumentId, setActiveDocumentId] = useState<string | null>(documentId)

  useEffect(() => {
    if (open && documentId) {
      setActiveDocumentId(documentId)
    }
    if (!open) {
      setActiveDocumentId(null)
    }
  }, [documentId, open])

  const wrapClassName =
    mode === 'config'
      ? 'minerva-document-segment-modal minerva-document-segment-modal--config'
      : 'minerva-document-segment-modal minerva-document-segment-modal--view'

  return (
    <Modal
      open={open}
      title={null}
      width="100%"
      centered={false}
      wrapClassName={wrapClassName}
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
      {activeDocumentId ? (
        mode === 'config' ? (
          <DocumentSegmentConfigPanel
            key={activeDocumentId}
            datasetId={datasetId}
            documentId={activeDocumentId}
            onDocumentChange={setActiveDocumentId}
          />
        ) : (
          <DocumentSegmentsViewPanel
            key={activeDocumentId}
            datasetId={datasetId}
            documentId={activeDocumentId}
            onDocumentChange={setActiveDocumentId}
          />
        )
      ) : null}
    </Modal>
  )
}
