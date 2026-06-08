/** Opens the fullscreen modal wrapping {@link DatasetCreateWizard}. */
import { Modal } from 'antd'
import { useState } from 'react'
import { DatasetCreateWizard } from './DatasetCreateWizard'
import './DatasetCreateWizardModal.css'

export type DatasetCreateWizardModalProps = {
  open: boolean
  datasetId?: string
  onClose: () => void
  onSuccess: (datasetId: string) => void
}

/** Fullscreen modal host for the knowledge base creation wizard. */
export function DatasetCreateWizardModal({
  open,
  datasetId,
  onClose,
  onSuccess,
}: DatasetCreateWizardModalProps) {
  const [indexingInProgress, setIndexingInProgress] = useState(false)

  return (
    <Modal
      open={open}
      title={null}
      width="100%"
      centered={false}
      wrapClassName="minerva-dataset-create-modal"
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
      mask={{ closable: !indexingInProgress }}
      keyboard={!indexingInProgress}
      closable={!indexingInProgress}
      onCancel={() => {
        if (!indexingInProgress) onClose()
      }}
    >
      <DatasetCreateWizard
        datasetId={datasetId}
        onCancel={onClose}
        onSuccess={onSuccess}
        onIndexingChange={setIndexingInProgress}
      />
    </Modal>
  )
}
