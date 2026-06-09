/** Full-screen create wizard: upload, chunking, indexing. */

import { Button, Form, Space, Steps, message } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/app/AuthContext'
import { appendDocuments } from '@/features/dataset/api/documents'
import {
  getDatasetProcessRule,
  initDataset,
  type BatchIndexingStatusOut,
} from '@/features/dataset/api/datasets'
import './DatasetCreateWizard.css'
import { StepOneUpload, type UploadedDatasetFile } from '@/features/dataset/create/StepOneUpload'
import {
  StepTwoChunking,
  buildProcessRule,
  type StepTwoFormValues,
} from '@/features/dataset/create/StepTwoChunking'
import { buildRetrievalModel } from '@/features/dataset/shared/retrievalForm'
import { StepThreeProcessing } from '@/features/dataset/create/StepThreeProcessing'
import { getFirstFormValidationMessage, isFormValidationError } from '@/utils/formValidation'



export type DatasetCreateWizardProps = {

  /** When set, append documents to an existing knowledge base. */

  datasetId?: string

  onSuccess: (datasetId: string) => void

  onCancel: () => void

  onIndexingChange?: (active: boolean) => void

}



/** Renders the three-step create flow inside a fullscreen modal. */

export function DatasetCreateWizard({

  datasetId,

  onSuccess,

  onCancel,

  onIndexingChange,

}: DatasetCreateWizardProps) {

  const { t } = useTranslation()

  const { workspaceId } = useAuth()

  const [step, setStep] = useState(0)

  const [uploads, setUploads] = useState<UploadedDatasetFile[]>([])

  const [submitting, setSubmitting] = useState(false)

  const [initResult, setInitResult] = useState<{
    datasetId: string
    batch: string
    datasetName: string
    documents: Array<{ id: string; name: string }>
  } | null>(null)

  const [createSnapshot, setCreateSnapshot] = useState<StepTwoFormValues | null>(null)

  const [batchStatus, setBatchStatus] = useState<BatchIndexingStatusOut | null>(null)

  const [form] = Form.useForm<StepTwoFormValues>()



  const ruleQ = useQuery({

    queryKey: ['dataset-process-rule', workspaceId],

    queryFn: () => getDatasetProcessRule(workspaceId!),

    enabled: Boolean(workspaceId),

  })



  const isAppend = Boolean(datasetId)

  const handleAppend = useCallback(async () => {
    if (!workspaceId || !datasetId) return
    setSubmitting(true)
    onIndexingChange?.(true)
    try {
      const result = await appendDocuments(
        workspaceId,
        datasetId,
        uploads.map((item) => item.id),
      )
      setInitResult({
        datasetId,
        batch: result.batch,
        datasetName: '',
        documents: result.documents.map((doc) => ({ id: doc.id, name: doc.name })),
      })
      setStep(2)
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('dataset.create.initFailed'))
      onIndexingChange?.(false)
    } finally {
      setSubmitting(false)
    }
  }, [datasetId, onIndexingChange, t, uploads, workspaceId])

  const handleInit = useCallback(async () => {
    if (!workspaceId) return

    setSubmitting(true)
    onIndexingChange?.(true)
    try {
      const values = await form.validateFields()
      setCreateSnapshot(values)

      const defaultRule = ruleQ.data?.process_rule ?? {}
      const processRule = buildProcessRule(values, defaultRule)

      let embeddingModel: string | undefined
      let embeddingProvider: string | undefined

      if (values.embedding_model_key) {
        const [provider, model] = values.embedding_model_key.split('::')
        embeddingProvider = provider
        embeddingModel = model
      }

      const result = await initDataset(workspaceId, {
        name: values.name.trim(),
        description: values.description?.trim() || null,
        indexing_technique: values.indexing_technique,
        doc_form: values.doc_form ?? 'text_model',
        file_ids: uploads.map((item) => item.id),
        process_rule: processRule,
        retrieval_model: buildRetrievalModel(values),
        embedding_model: embeddingModel,
        embedding_model_provider: embeddingProvider,
      })

      setInitResult({
        datasetId: result.dataset.id,
        batch: result.batch,
        datasetName: result.dataset.name,
        documents: result.documents.map((doc) => ({ id: doc.id, name: doc.name })),
      })
      setStep(2)
    } catch (err) {
      if (isFormValidationError(err)) {
        message.error(getFirstFormValidationMessage(err) ?? t('dataset.create.validation.formIncomplete'))
      } else {
        message.error(err instanceof Error ? err.message : t('dataset.create.initFailed'))
      }
      onIndexingChange?.(false)
    } finally {
      setSubmitting(false)
    }
  }, [form, onIndexingChange, ruleQ.data?.process_rule, t, uploads, workspaceId])



  const onBatchFinished = useCallback(() => {
    onIndexingChange?.(false)
  }, [onIndexingChange])



  if (!workspaceId) {

    return null

  }



  return (

    <div className="minerva-dataset-create-wizard">
      <div className="minerva-dataset-create-wizard__header">
        <Steps
          current={step}
          size="small"
          className="minerva-dataset-create-wizard__steps"
          items={
            isAppend
              ? [{ title: t('dataset.create.step1') }, { title: t('dataset.create.step3') }]
              : [
                  { title: t('dataset.create.step1') },
                  { title: t('dataset.create.step2') },
                  { title: t('dataset.create.step3') },
                ]
          }
        />
      </div>

      <div
        className={
          !isAppend && step === 1
            ? 'minerva-dataset-create-wizard__body minerva-dataset-create-wizard__body--split minerva-scrollbar-thin'
            : step === (isAppend ? 1 : 2)
              ? 'minerva-dataset-create-wizard__body minerva-dataset-create-wizard__body--complete minerva-scrollbar-thin'
              : 'minerva-dataset-create-wizard__body minerva-scrollbar-thin'
        }
      >
        {step === 0 ? (
          <StepOneUpload
            workspaceId={workspaceId}
            value={uploads}
            onChange={setUploads}
            form={!isAppend ? form : undefined}
          />
        ) : null}
        {!isAppend && step === 1 ? (
          <StepTwoChunking workspaceId={workspaceId} uploads={uploads} form={form} />
        ) : null}
        {step === (isAppend ? 1 : 2) && initResult ? (
          <StepThreeProcessing
            workspaceId={workspaceId}
            datasetId={initResult.datasetId}
            batch={initResult.batch}
            datasetName={initResult.datasetName}
            onDatasetNameChange={(name) =>
              setInitResult((prev) => (prev ? { ...prev, datasetName: name } : prev))
            }
            documents={initResult.documents}
            formSnapshot={createSnapshot}
            status={batchStatus}
            onStatusChange={setBatchStatus}
            onFinished={onBatchFinished}
            onGoToDocuments={() => onSuccess(initResult.datasetId)}
            isAppend={isAppend}
          />
        ) : null}
      </div>

      {step !== (isAppend ? 1 : 2) ? (
        <div className="minerva-dataset-create-wizard__footer">
          <Button onClick={onCancel}>{t('common.cancel')}</Button>
          <Space>
            {!isAppend && step === 1 ? (
              <Button onClick={() => setStep((s) => s - 1)}>{t('dataset.create.prev')}</Button>
            ) : null}
            {step === 0 ? (
              <Button
                type="primary"
                disabled={uploads.length === 0}
                loading={isAppend && submitting}
                onClick={() => {
                  if (isAppend) void handleAppend()
                  else {
                    void form.validateFields(['name']).then(() => setStep(1))
                  }
                }}
              >
                {isAppend ? t('dataset.create.startIndexing') : t('dataset.create.next')}
              </Button>
            ) : null}
            {!isAppend && step === 1 ? (
              <Button type="primary" loading={submitting} onClick={() => void handleInit()}>
                {t('dataset.create.saveAndProcess')}
              </Button>
            ) : null}
          </Space>
        </div>
      ) : null}

      {datasetId ? <span hidden data-dataset-id={datasetId} /> : null}

    </div>

  )

}


