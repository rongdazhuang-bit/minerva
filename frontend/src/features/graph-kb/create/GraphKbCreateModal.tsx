/** Opens the fullscreen modal wrapping {@link GraphKbCreateWizard}. */
import { Modal } from 'antd'
import { GraphKbCreateWizard } from './GraphKbCreateWizard'
import './GraphKbCreateModal.css'

export type GraphKbCreateModalProps = {
  open: boolean
  onClose: () => void
  onSuccess: (graphId: string) => void
}

/** Fullscreen modal host for the graph knowledge base creation form. */
export function GraphKbCreateModal({ open, onClose, onSuccess }: GraphKbCreateModalProps) {
  return (
    <Modal
      open={open}
      title={null}
      width="100%"
      centered={false}
      wrapClassName="minerva-graph-kb-create-modal"
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
      <GraphKbCreateWizard onCancel={onClose} onSuccess={onSuccess} />
    </Modal>
  )
}
