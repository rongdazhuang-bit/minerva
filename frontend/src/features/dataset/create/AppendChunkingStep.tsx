/** Append flow step 1 — shared chunking config with upload preview. */
import { useQuery } from '@tanstack/react-query'
import { Form, Input, message } from 'antd'
import type { FormInstance } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listModelProviders } from '@/api/modelProviders'
import { useAuth } from '@/app/AuthContext'
import { estimateDatasetIndexing } from '@/features/dataset/api/datasets'
import { getDataset } from '@/features/dataset/api/documents'
import { ChunkPreviewPanel, type PreviewSegment } from '@/features/dataset/create/ChunkPreviewPanel'
import { IndexingMethodPanel, type IndexingFormValues } from '@/features/dataset/create/IndexingMethodPanel'
import { RetrievalSettingsPanel } from '@/features/dataset/create/RetrievalSettingsPanel'
import { SegmentationSettingsPanel } from '@/features/dataset/create/SegmentationSettingsPanel'
import type { UploadedDatasetFile } from '@/features/dataset/create/StepTwoChunking'
import {
  ChunkingConfigPreviewLayout,
  ChunkingConfigSectionDivider,
} from '@/features/dataset/shared/ChunkingConfigPreviewLayout'
import {
  buildProcessRule,
  defaultChunkingFormValues,
  parseProcessRuleToForm,
  type ChunkingFormValues,
} from '@/features/dataset/shared/chunkingForm'
import {
  parseRetrievalModelToForm,
  type RetrievalFormValues,
} from '@/features/dataset/shared/retrievalForm'
import { getFirstFormValidationMessage } from '@/utils/formValidation'
import './StepTwoChunking.css'

import type { StepTwoFormValues } from '@/features/dataset/create/StepTwoChunking'

export type AppendChunkingStepProps = {
  datasetId: string
  uploads: UploadedDatasetFile[]
  form: FormInstance<StepTwoFormValues>
}

/** Chunking config for append-documents wizard (dataset-level read-only indexing/retrieval). */
export function AppendChunkingStep({ datasetId, uploads, form }: AppendChunkingStepProps) {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const [previewFileId, setPreviewFileId] = useState<string | undefined>(uploads[0]?.id)
  const [previewLoading, setPreviewLoading] = useState(false)
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

  const modelsQ = useQuery({
    queryKey: ['model-providers', workspaceId],
    queryFn: () => listModelProviders(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const embeddingOptions = useMemo(
    () =>
      (modelsQ.data ?? [])
        .filter((row) => row.enabled && row.tags.includes('EMBEDDINGS'))
        .map((row) => ({
          value: `${row.provider_name}::${row.model_name}`,
          label: `${row.provider_name} / ${row.model_name}`,
        })),
    [modelsQ.data],
  )

  const rerankOptions = useMemo(
    () =>
      (modelsQ.data ?? [])
        .filter((row) => row.enabled && row.tags.includes('RERANKING'))
        .map((row) => ({
          value: `${row.provider_name}::${row.model_name}`,
          label: `${row.provider_name} / ${row.model_name}`,
        })),
    [modelsQ.data],
  )

  const docForm = Form.useWatch('doc_form', form)
  const indexingTechnique = Form.useWatch('indexing_technique', form)
  const isHierarchical = docForm === 'hierarchical_model'
  const economyMode = indexingTechnique === 'economy'

  useEffect(() => {
    const dataset = datasetQ.data
    if (!dataset) return
    const savedRule = dataset.process_rule
    const chunkingValues =
      savedRule != null
        ? parseProcessRuleToForm(savedRule as Record<string, unknown>)
        : defaultChunkingFormValues(savedRule ?? {})
    const provider = dataset.embedding_model_provider
    const model = dataset.embedding_model
    form.setFieldsValue({
      doc_form: (dataset.chunk_structure as StepTwoFormValues['doc_form']) ?? 'text_model',
      indexing_technique:
        (dataset.indexing_technique as StepTwoFormValues['indexing_technique']) ?? 'high_quality',
      embedding_model_key: provider && model ? `${provider}::${model}` : undefined,
      ...chunkingValues,
      ...parseRetrievalModelToForm((dataset.retrieval_model ?? {}) as Record<string, unknown>),
    })
    setPreviewFileId((current) => current ?? uploads[0]?.id)
    setPreviewState(null)
  }, [datasetQ.data, form, uploads])

  const onPreview = useCallback(async () => {
    if (!workspaceId || !previewFileId) return
    let values: StepTwoFormValues
    try {
      values = await form.validateFields()
    } catch (error) {
      message.error(getFirstFormValidationMessage(error) ?? t('dataset.create.validation.formIncomplete'))
      return
    }
    const defaultRule = datasetQ.data?.process_rule ?? {}
    const processRule = buildProcessRule(values, defaultRule as Record<string, unknown>)
    setPreviewLoading(true)
    try {
      const result = await estimateDatasetIndexing(workspaceId, {
        file_ids: uploads.map((item) => item.id),
        process_rule: processRule,
        indexing_technique: values.indexing_technique,
        doc_form: values.doc_form,
        preview_file_id: previewFileId,
      })
      const first = result.previews[0]
      if (first && previewFileId) {
        setPreviewState({
          fileId: previewFileId,
          segments: first.segments ?? [],
          segmentCount: first.segment_count ?? first.segments?.length ?? 0,
        })
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : t('dataset.create.initFailed'))
    } finally {
      setPreviewLoading(false)
    }
  }, [datasetQ.data?.process_rule, form, previewFileId, t, uploads, workspaceId])

  const onResetChunking = useCallback(() => {
    const savedRule = datasetQ.data?.process_rule
    if (!savedRule) return
    form.setFieldsValue(parseProcessRuleToForm(savedRule as Record<string, unknown>))
    setPreviewState(null)
  }, [datasetQ.data?.process_rule, form])

  const previewUploads = useMemo(
    () => uploads.map((item) => ({ id: item.id, name: item.name })),
    [uploads],
  )

  const previewReady = previewState?.fileId === previewFileId
  const activeSegments = previewReady && previewState ? previewState.segments : []
  const activeSegmentCount = previewReady && previewState ? previewState.segmentCount : 0

  return (
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
        </Form>
      }
      previewPane={
        <ChunkPreviewPanel
          uploads={previewUploads}
          previewFileId={previewFileId}
          onPreviewFileIdChange={setPreviewFileId}
          segments={activeSegments}
          segmentCount={activeSegmentCount}
          loading={previewLoading}
          previewReady={previewReady}
          emptyHint={t('dataset.create.previewLoadHint')}
        />
      }
    />
  )
}
