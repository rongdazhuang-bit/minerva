/** Step 2 — chunking settings and segment preview. */

import { useQuery } from '@tanstack/react-query'
import { Form, Input, message } from 'antd'
import type { FormInstance } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { listModelProviders } from '@/api/modelProviders'
import {
  estimateDatasetIndexing,
  getDatasetProcessRule,
  type DatasetUploadOut,
} from '@/features/dataset/api/datasets'
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
  defaultChunkingFormValues,
  parseProcessRuleToForm,
  type ChunkingFormValues,
} from '@/features/dataset/shared/chunkingForm'
import {
  defaultRetrievalFormValues,
  type RetrievalFormValues,
} from '@/features/dataset/shared/retrievalForm'
import { getFirstFormValidationMessage } from '@/utils/formValidation'
import './StepTwoChunking.css'

export type UploadedDatasetFile = DatasetUploadOut & { uid: string }

export type StepTwoFormValues = ChunkingFormValues &
  IndexingFormValues &
  RetrievalFormValues & {
    name: string
    description?: string
    indexing_technique: 'high_quality' | 'economy'
    embedding_model_key?: string
  }

export type { ChunkingFormValues }

export { buildProcessRule, parseProcessRuleToForm }

export type StepTwoChunkingProps = {
  workspaceId: string
  uploads: UploadedDatasetFile[]
  form: FormInstance<StepTwoFormValues>
}

/** Chunking form and preview panel with independent left/right scroll. */
export function StepTwoChunking({ workspaceId, uploads, form }: StepTwoChunkingProps) {
  const { t } = useTranslation()
  const [previewFileId, setPreviewFileId] = useState<string | undefined>(uploads[0]?.id)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewState, setPreviewState] = useState<{
    fileId: string
    segments: PreviewSegment[]
    segmentCount: number
  } | null>(null)

  const ruleQ = useQuery({
    queryKey: ['dataset-process-rule', workspaceId],
    queryFn: () => getDatasetProcessRule(workspaceId),
    enabled: Boolean(workspaceId),
  })

  const modelsQ = useQuery({
    queryKey: ['model-providers', workspaceId],
    queryFn: () => listModelProviders(workspaceId),
    enabled: Boolean(workspaceId),
  })

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

  const indexingTechnique = Form.useWatch('indexing_technique', form)
  const docForm = Form.useWatch('doc_form', form)
  const searchMethod = Form.useWatch('search_method', form)
  const hierarchicalMode = docForm === 'hierarchical_model'
  const economyMode = indexingTechnique === 'economy'

  useEffect(() => {
    if (hierarchicalMode && indexingTechnique === 'economy') {
      form.setFieldValue('indexing_technique', 'high_quality')
    }
  }, [form, hierarchicalMode, indexingTechnique])

  useEffect(() => {
    if (economyMode && (searchMethod === 'semantic_search' || searchMethod === 'hybrid_search')) {
      form.setFieldValue('search_method', 'full_text_search')
    }
  }, [economyMode, form, searchMethod])

  useEffect(() => {
    const defaultRule = ruleQ.data?.process_rule
    if (!defaultRule) return
    const chunkDefaults = defaultChunkingFormValues(defaultRule)
    form.setFieldsValue({
      ...chunkDefaults,
      ...defaultRetrievalFormValues(),
      name: form.getFieldValue('name'),
      description: form.getFieldValue('description'),
      indexing_technique: form.getFieldValue('indexing_technique') ?? 'high_quality',
      embedding_model_key: form.getFieldValue('embedding_model_key'),
      search_method: form.getFieldValue('search_method') ?? 'semantic_search',
    })
  }, [form, ruleQ.data?.process_rule])

  const onPreview = useCallback(async () => {
    let values: StepTwoFormValues
    try {
      values = await form.validateFields()
    } catch (error) {
      message.error(getFirstFormValidationMessage(error) ?? t('dataset.create.validation.formIncomplete'))
      return
    }
    const defaultRule = ruleQ.data?.process_rule ?? {}
    const processRule = buildProcessRule(values, defaultRule)
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
    } finally {
      setPreviewLoading(false)
    }
  }, [form, previewFileId, ruleQ.data?.process_rule, t, uploads, workspaceId])

  const onResetChunking = useCallback(() => {
    const defaultRule = ruleQ.data?.process_rule ?? {}
    form.setFieldsValue({
      ...defaultChunkingFormValues(defaultRule),
      ...defaultRetrievalFormValues(),
    })
    setPreviewState(null)
  }, [form, ruleQ.data?.process_rule])

  const previewReady = previewState?.fileId === previewFileId
  const activeSegments = previewReady && previewState ? previewState.segments : []
  const activeSegmentCount = previewReady && previewState ? previewState.segmentCount : 0

  return (
    <ChunkingConfigPreviewLayout
      configPane={
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            indexing_technique: 'high_quality',
            doc_form: 'text_model',
            parent_mode_type: 'paragraph',
            delimiter: '\\n\\n',
            max_length: 1024,
            chunk_overlap: 50,
            parent_delimiter: '\\n\\n',
            parent_max_length: 1024,
            sub_delimiter: '\\n',
            sub_max_length: 512,
            use_qa_segmentation: false,
            qa_language: 'Chinese Simplified',
            remove_extra_spaces: true,
            remove_urls_emails: false,
            recognize_formula: false,
            recognize_table: false,
            ...defaultRetrievalFormValues(),
          }}
        >
          <Form.Item name="doc_form" hidden>
            <Input />
          </Form.Item>
          <Form.Item
            name="name"
            hidden
            preserve
            rules={[{ required: true, message: t('dataset.create.field.nameRequired') }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="description" hidden preserve>
            <Input />
          </Form.Item>

          <SegmentationSettingsPanel
            form={form as unknown as FormInstance<ChunkingFormValues>}
            onPreview={() => void onPreview()}
            onReset={onResetChunking}
            previewLoading={previewLoading}
          />

          <ChunkingConfigSectionDivider />

          <IndexingMethodPanel
            form={form as unknown as FormInstance<IndexingFormValues>}
            embeddingOptions={embeddingOptions}
            modelsLoading={modelsQ.isLoading}
            economyDisabled={hierarchicalMode}
          />

          <ChunkingConfigSectionDivider />

          <RetrievalSettingsPanel
            form={form as unknown as FormInstance<RetrievalFormValues>}
            rerankOptions={rerankOptions}
            modelsLoading={modelsQ.isLoading}
            vectorSearchDisabled={economyMode}
          />
        </Form>
      }
      previewPane={
        <ChunkPreviewPanel
          uploads={uploads}
          previewFileId={previewFileId}
          onPreviewFileIdChange={setPreviewFileId}
          segments={activeSegments}
          segmentCount={activeSegmentCount}
          loading={previewLoading}
          previewReady={previewReady}
        />
      }
    />
  )
}
