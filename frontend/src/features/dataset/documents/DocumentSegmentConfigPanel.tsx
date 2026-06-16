/** Document segmentation configuration and preview (reuses create-wizard panels). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Form, Input, Popconfirm, Spin, Typography, message } from 'antd'
import type { FormInstance } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listModelProviders } from '@/api/modelProviders'
import { useAuth } from '@/app/AuthContext'
import { estimateDatasetIndexing } from '@/features/dataset/api/datasets'
import {
  getDataset,
  getDocument,
  listDocuments,
  patchDocument,
} from '@/features/dataset/api/documents'
import { ChunkPreviewPanel, type PreviewSegment } from '@/features/dataset/create/ChunkPreviewPanel'
import { IndexingMethodPanel, type IndexingFormValues } from '@/features/dataset/create/IndexingMethodPanel'
import { RetrievalSettingsPanel } from '@/features/dataset/create/RetrievalSettingsPanel'
import { SegmentationSettingsPanel } from '@/features/dataset/create/SegmentationSettingsPanel'
import {
  ChunkingConfigPreviewLayout,
  ChunkingConfigSectionDivider,
} from '@/features/dataset/shared/ChunkingConfigPreviewLayout'
import {
  buildProcessRule,
  parseProcessRuleToForm,
  type ChunkingFormValues,
} from '@/features/dataset/shared/chunkingForm'
import {
  parseRetrievalModelToForm,
  type RetrievalFormValues,
} from '@/features/dataset/shared/retrievalForm'
import { getFirstFormValidationMessage } from '@/utils/formValidation'
import './DocumentSegmentConfigPanel.css'

type DocumentSegmentFormValues = ChunkingFormValues & IndexingFormValues & RetrievalFormValues

const CHUNKING_SNAPSHOT_KEYS = [
  'delimiter',
  'max_length',
  'chunk_overlap',
  'parent_mode_type',
  'parent_delimiter',
  'parent_max_length',
  'parent_chunk_overlap',
  'sub_delimiter',
  'sub_max_length',
  'sub_chunk_overlap',
  'remove_extra_spaces',
  'remove_urls_emails',
  'recognize_formula',
  'recognize_table',
  'use_qa_segmentation',
  'qa_language',
] as const satisfies ReadonlyArray<keyof ChunkingFormValues>

/** Serialize chunking-related form fields for dirty-state comparison. */
function serializeChunkingFields(values: Partial<DocumentSegmentFormValues>): string {
  const slice: Record<string, unknown> = {}
  for (const key of CHUNKING_SNAPSHOT_KEYS) {
    slice[key] = values[key]
  }
  return JSON.stringify(slice)
}

export type DocumentSegmentConfigPanelProps = {
  datasetId: string
  documentId: string
  onDocumentChange: (documentId: string) => void
}

/** Fullscreen segmentation settings and chunk preview for one document. */
export function DocumentSegmentConfigPanel({
  datasetId,
  documentId,
  onDocumentChange,
}: DocumentSegmentConfigPanelProps) {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<DocumentSegmentFormValues>()
  const [previewFileId, setPreviewFileId] = useState<string | undefined>()
  const [previewLoading, setPreviewLoading] = useState(false)
  const [savedSnapshot, setSavedSnapshot] = useState('')
  const [pendingFileId, setPendingFileId] = useState<string | null>(null)
  const [previewState, setPreviewState] = useState<{
    fileId: string
    segments: PreviewSegment[]
    segmentCount: number
  } | null>(null)

  const datasetQ = useQuery({
    queryKey: ['dataset-detail', workspaceId, datasetId],
    queryFn: () => getDataset(workspaceId!, datasetId),
    enabled: Boolean(workspaceId && datasetId),
  })

  const documentQ = useQuery({
    queryKey: ['dataset-document', workspaceId, datasetId, documentId],
    queryFn: () => getDocument(workspaceId!, datasetId, documentId),
    enabled: Boolean(workspaceId && datasetId && documentId),
  })

  const documentsQ = useQuery({
    queryKey: ['dataset-documents-picker', workspaceId, datasetId],
    queryFn: () => listDocuments(workspaceId!, datasetId, { page: 1, page_size: 100 }),
    enabled: Boolean(workspaceId && datasetId),
  })

  const modelsQ = useQuery({
    queryKey: ['model-providers', workspaceId],
    queryFn: () => listModelProviders(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const watchedValues = Form.useWatch([], form) as Partial<DocumentSegmentFormValues> | undefined

  const embeddingOptions = useMemo(() => {
    return (modelsQ.data ?? [])
      .filter((row) => row.enabled && row.tags.includes('EMBEDDINGS'))
      .map((row) => ({
        value: `${row.provider_name}::${row.model_name}`,
        label: `${row.provider_name} / ${row.model_name}`,
      }))
  }, [modelsQ.data])

  const rerankOptions = useMemo(() => {
    return (modelsQ.data ?? [])
      .filter((row) => row.enabled && row.tags.includes('RERANKING'))
      .map((row) => ({
        value: `${row.provider_name}::${row.model_name}`,
        label: `${row.provider_name} / ${row.model_name}`,
      }))
  }, [modelsQ.data])

  const previewUploads = useMemo(() => {
    const byFileId = new Map<string, { id: string; name: string }>()
    for (const doc of documentsQ.data?.items ?? []) {
      if (doc.file_id) {
        byFileId.set(String(doc.file_id), { id: String(doc.file_id), name: doc.name })
      }
    }
    const current = documentQ.data
    if (current?.file_id) {
      const fileId = String(current.file_id)
      if (!byFileId.has(fileId)) {
        byFileId.set(fileId, { id: fileId, name: current.name })
      }
    }
    return Array.from(byFileId.values())
  }, [documentQ.data, documentsQ.data?.items])

  const fileDocumentMap = useMemo(() => {
    const map = new Map<string, string>()
    for (const doc of documentsQ.data?.items ?? []) {
      if (doc.file_id) {
        map.set(String(doc.file_id), doc.id)
      }
    }
    if (documentQ.data?.file_id) {
      map.set(String(documentQ.data.file_id), documentQ.data.id)
    }
    return map
  }, [documentQ.data, documentsQ.data?.items])

  const isDirty = useMemo(() => {
    if (!savedSnapshot) return false
    return serializeChunkingFields(watchedValues ?? {}) !== savedSnapshot
  }, [savedSnapshot, watchedValues])

  useEffect(() => {
    const document = documentQ.data
    const dataset = datasetQ.data
    if (!document || !dataset) return

    const provider = dataset.embedding_model_provider
    const model = dataset.embedding_model
    const savedRule = document.process_rule
    const chunkingValues =
      savedRule != null ? parseProcessRuleToForm(savedRule as Record<string, unknown>) : {}

    form.setFieldsValue({
      doc_form: (document.doc_form as DocumentSegmentFormValues['doc_form']) ?? 'text_model',
      indexing_technique: (dataset.indexing_technique as DocumentSegmentFormValues['indexing_technique']) ?? 'high_quality',
      embedding_model_key: provider && model ? `${provider}::${model}` : undefined,
      ...chunkingValues,
      ...parseRetrievalModelToForm((dataset.retrieval_model ?? {}) as Record<string, unknown>),
    })
    setPreviewFileId(document.file_id ? String(document.file_id) : undefined)
    setPreviewState(null)
    setSavedSnapshot(savedRule != null ? serializeChunkingFields({ ...chunkingValues }) : '')
  }, [datasetQ.data, documentId, documentQ.data, form])

  const applyFileSwitch = useCallback(
    (fileId: string) => {
      setPreviewFileId(fileId)
      setPreviewState(null)
      const nextDocumentId = fileDocumentMap.get(fileId)
      if (nextDocumentId && nextDocumentId !== documentId) {
        onDocumentChange(nextDocumentId)
      }
    },
    [documentId, fileDocumentMap, onDocumentChange],
  )

  const onPreviewFileIdChange = useCallback(
    (fileId: string) => {
      if (fileId === previewFileId) return
      if (isDirty) {
        setPendingFileId(fileId)
        return
      }
      applyFileSwitch(fileId)
    },
    [applyFileSwitch, isDirty, previewFileId],
  )

  const onPreview = useCallback(async () => {
    if (!workspaceId || !previewFileId) {
      message.warning(t('dataset.documents.segmentConfig.fileMissing'))
      return
    }

    let values: DocumentSegmentFormValues
    try {
      values = await form.validateFields()
    } catch (error) {
      message.error(getFirstFormValidationMessage(error) ?? t('dataset.create.validation.formIncomplete'))
      return
    }

    const defaultRule = (documentQ.data?.process_rule ?? {}) as Record<string, unknown>
    const processRule = buildProcessRule(values, defaultRule)

    setPreviewLoading(true)
    try {
      const result = await estimateDatasetIndexing(workspaceId, {
        file_ids: [previewFileId],
        process_rule: processRule,
        indexing_technique: values.indexing_technique,
        doc_form: values.doc_form,
        preview_file_id: previewFileId,
      })
      const first = result.previews[0]
      if (first) {
        setPreviewState({
          fileId: previewFileId,
          segments: first.segments ?? [],
          segmentCount: first.segment_count ?? first.segments?.length ?? 0,
        })
      }
    } finally {
      setPreviewLoading(false)
    }
  }, [documentQ.data?.process_rule, form, previewFileId, t, workspaceId])

  const onResetChunking = useCallback(() => {
    const defaultRule = (documentQ.data?.process_rule ?? {}) as Record<string, unknown>
    const chunkingValues = parseProcessRuleToForm(defaultRule)
    form.setFieldsValue({
      doc_form: documentQ.data?.doc_form as DocumentSegmentFormValues['doc_form'],
      ...chunkingValues,
    })
    setPreviewState(null)
    setSavedSnapshot(serializeChunkingFields(chunkingValues))
  }, [documentQ.data, form])

  const saveM = useMutation({
    mutationFn: async () => {
      let values: DocumentSegmentFormValues
      try {
        values = await form.validateFields()
      } catch (error) {
        throw new Error(getFirstFormValidationMessage(error) ?? t('dataset.create.validation.formIncomplete'))
      }
      const defaultRule = (documentQ.data?.process_rule ?? {}) as Record<string, unknown>
      const processRule = buildProcessRule(values, defaultRule)
      return patchDocument(workspaceId!, datasetId, documentId, { process_rule: processRule })
    },
    onSuccess: () => {
      message.success(t('dataset.documents.segmentConfig.saveOk'))
      setSavedSnapshot(serializeChunkingFields(form.getFieldsValue(true)))
      setPreviewState(null)
      void queryClient.invalidateQueries({ queryKey: ['dataset-document', workspaceId, datasetId, documentId] })
      void queryClient.invalidateQueries({ queryKey: ['dataset-documents', workspaceId, datasetId] })
    },
    onError: (err: Error) => message.error(err.message),
  })

  const previewReady = previewState?.fileId === previewFileId
  const activeSegments = previewReady && previewState ? previewState.segments : []
  const activeSegmentCount = previewReady && previewState ? previewState.segmentCount : 0
  const loading = datasetQ.isLoading || documentQ.isLoading
  const isHierarchical = (documentQ.data?.doc_form ?? 'text_model') === 'hierarchical_model'
  const economyMode = (watchedValues?.indexing_technique ?? datasetQ.data?.indexing_technique) === 'economy'
  const isArchived = documentQ.data?.archived === true
  const processRuleMissing =
    documentQ.data != null &&
    (documentQ.data.process_rule_id == null || documentQ.data.process_rule == null)
  const previewFileName = useMemo(() => {
    if (!previewFileId) return undefined
    return previewUploads.find((item) => item.id === previewFileId)?.name
  }, [previewFileId, previewUploads])

  return (
    <Spin spinning={loading} wrapperClassName="minerva-document-segment-panel__spin">
      <div className="minerva-document-segment-panel">
        <ChunkingConfigPreviewLayout
          configPane={
            <Form form={form} layout="vertical">
              <Form.Item name="doc_form" hidden>
                <Input />
              </Form.Item>
              <Form.Item name="indexing_technique" hidden>
                <Input />
              </Form.Item>
              <Form.Item name="search_method" hidden>
                <Input />
              </Form.Item>

              <SegmentationSettingsPanel
                form={form as unknown as FormInstance<ChunkingFormValues>}
                docFormLocked
                onPreview={() => void onPreview()}
                onReset={onResetChunking}
                previewLoading={previewLoading}
              />

              {processRuleMissing ? (
                <Alert
                  type="warning"
                  showIcon
                  className="minerva-document-segment-panel__rule-alert"
                  message={t('dataset.documents.segmentConfig.processRuleMissing')}
                />
              ) : null}

              <ChunkingConfigSectionDivider />

              <IndexingMethodPanel
                form={form as unknown as FormInstance<IndexingFormValues>}
                embeddingOptions={embeddingOptions}
                modelsLoading={modelsQ.isLoading}
                economyDisabled={isHierarchical}
                indexingLocked
                embeddingReadOnly
                hideEconomyDisabledHint
              />

              <ChunkingConfigSectionDivider />

              <RetrievalSettingsPanel
                form={form as unknown as FormInstance<RetrievalFormValues>}
                rerankOptions={rerankOptions}
                modelsLoading={modelsQ.isLoading}
                vectorSearchDisabled={economyMode}
                retrievalLocked
              />

              <div className="minerva-document-segment-panel__save-row">
                <Button
                  type="primary"
                  loading={saveM.isPending}
                  disabled={isArchived || processRuleMissing}
                  onClick={() => saveM.mutate()}
                >
                  {t('dataset.documents.segmentConfig.saveAndProcess')}
                </Button>
              </div>
            </Form>
          }
          previewPane={
            <ChunkPreviewPanel
              uploads={previewUploads}
              previewFileId={previewFileId}
              previewFileName={previewFileName}
              onPreviewFileIdChange={onPreviewFileIdChange}
              segments={activeSegments}
              segmentCount={activeSegmentCount}
              loading={previewLoading}
              previewReady={previewReady}
              emptyHint={t('dataset.create.previewLoadHint')}
            />
          }
        />

        <Popconfirm
          open={pendingFileId != null}
          title={t('dataset.documents.segmentConfig.unsavedConfirm')}
          okText={t('dataset.documents.segmentConfig.unsavedConfirmOk')}
          cancelText={t('dataset.documents.segmentConfig.unsavedConfirmCancel')}
          onConfirm={() => {
            if (pendingFileId) {
              applyFileSwitch(pendingFileId)
            }
            setPendingFileId(null)
          }}
          onCancel={() => setPendingFileId(null)}
        >
          <span className="minerva-document-segment-panel__popconfirm-anchor" aria-hidden />
        </Popconfirm>
      </div>
    </Spin>
  )
}
