/** Knowledge base settings page — reuses create-wizard configuration panels (Dify-aligned). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Form, Input, Spin, Typography, message } from 'antd'
import type { FormInstance } from 'antd'
import { useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { listModelProviders } from '@/api/modelProviders'
import { useAuth } from '@/app/AuthContext'
import { getDataset } from '@/features/dataset/api/documents'
import { getDatasetProcessRule } from '@/features/dataset/api/datasets'
import { patchDataset } from '@/features/dataset/api/hitTesting'
import { IndexingMethodPanel, type IndexingFormValues } from '@/features/dataset/create/IndexingMethodPanel'
import { RetrievalSettingsPanel } from '@/features/dataset/create/RetrievalSettingsPanel'
import { SegmentationSettingsPanel } from '@/features/dataset/create/SegmentationSettingsPanel'
import {
  buildProcessRule,
  parseProcessRuleToForm,
  type ChunkingFormValues,
} from '@/features/dataset/shared/chunkingForm'
import {
  buildRetrievalModel,
  parseRetrievalModelToForm,
  type RetrievalFormValues,
} from '@/features/dataset/shared/retrievalForm'
import './DatasetSettingsPage.css'

type SettingsFormValues = ChunkingFormValues &
  IndexingFormValues &
  RetrievalFormValues & {
    name: string
    description?: string
    indexing_technique: 'high_quality' | 'economy'
    embedding_model_key?: string
  }

/** Split ``provider::model`` composite key into patch payload fields. */
function parseEmbeddingKey(key?: string) {
  if (!key?.includes('::')) {
    return { embedding_model_provider: undefined, embedding_model: undefined }
  }
  const [provider, model] = key.split('::', 2)
  return { embedding_model_provider: provider, embedding_model: model }
}

/** Settings tab: full chunking/indexing/retrieval UI with conditional field locks. */
export function DatasetSettingsPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const { datasetId = '' } = useParams()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<SettingsFormValues>()

  const detailQ = useQuery({
    queryKey: ['dataset-detail', workspaceId, datasetId],
    queryFn: () => getDataset(workspaceId!, datasetId),
    enabled: Boolean(workspaceId && datasetId),
  })

  const ruleQ = useQuery({
    queryKey: ['dataset-process-rule', workspaceId],
    queryFn: () => getDatasetProcessRule(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const modelsQ = useQuery({
    queryKey: ['model-providers', workspaceId],
    queryFn: () => listModelProviders(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const row = detailQ.data
  const chunkStructure = row?.chunk_structure ?? 'text_model'
  const isHierarchical = chunkStructure === 'hierarchical_model'
  const indexingTechnique = row?.indexing_technique ?? 'high_quality'
  const hasDocuments = (row?.document_count ?? 0) > 0
  const isHighQuality = indexingTechnique === 'high_quality'
  const economyDisabled = isHierarchical || (isHighQuality && hasDocuments)
  const indexingLocked = isHighQuality && hasDocuments

  const embeddingOptions = useMemo(() => {
    return (modelsQ.data ?? [])
      .filter((item) => item.enabled && item.tags.includes('EMBEDDINGS'))
      .map((item) => ({
        value: `${item.provider_name}::${item.model_name}`,
        label: `${item.provider_name} / ${item.model_name}`,
      }))
  }, [modelsQ.data])

  const rerankOptions = useMemo(() => {
    return (modelsQ.data ?? [])
      .filter((item) => item.enabled && item.tags.includes('RERANKING'))
      .map((item) => ({
        value: `${item.provider_name}::${item.model_name}`,
        label: `${item.provider_name} / ${item.model_name}`,
      }))
  }, [modelsQ.data])

  const watchedIndexing = Form.useWatch('indexing_technique', form)
  const searchMethod = Form.useWatch('search_method', form)
  const economyMode = watchedIndexing === 'economy'

  useEffect(() => {
    if (!row) return
    const savedRule = (row.process_rule ?? ruleQ.data?.process_rule ?? {}) as Record<string, unknown>
    const retrieval = (row.retrieval_model ?? {}) as Record<string, unknown>
    const provider = row.embedding_model_provider
    const model = row.embedding_model
    form.setFieldsValue({
      name: row.name,
      description: row.description ?? undefined,
      doc_form: (row.chunk_structure as SettingsFormValues['doc_form']) ?? 'text_model',
      indexing_technique: (row.indexing_technique as SettingsFormValues['indexing_technique']) ?? 'high_quality',
      embedding_model_key: provider && model ? `${provider}::${model}` : undefined,
      ...parseProcessRuleToForm(savedRule),
      ...parseRetrievalModelToForm(retrieval),
    })
  }, [form, row, ruleQ.data?.process_rule])

  useEffect(() => {
    if (isHierarchical && watchedIndexing === 'economy') {
      form.setFieldValue('indexing_technique', 'high_quality')
    }
  }, [form, isHierarchical, watchedIndexing])

  useEffect(() => {
    if (economyMode && (searchMethod === 'semantic_search' || searchMethod === 'hybrid_search')) {
      form.setFieldValue('search_method', 'full_text_search')
    }
  }, [economyMode, form, searchMethod])

  const saveM = useMutation({
    mutationFn: (values: SettingsFormValues) => {
      const defaultRule = (row?.process_rule ?? ruleQ.data?.process_rule ?? {}) as Record<string, unknown>
      const processRule = buildProcessRule(
        { ...values, doc_form: (chunkStructure as ChunkingFormValues['doc_form']) ?? 'text_model' },
        defaultRule,
      )
      const embedding = parseEmbeddingKey(values.embedding_model_key)
      const body: Parameters<typeof patchDataset>[2] = {
        name: values.name.trim(),
        description: values.description?.trim() || null,
        process_rule: processRule,
        retrieval_model: buildRetrievalModel(values, (row?.retrieval_model ?? {}) as Record<string, unknown>),
      }
      if (!indexingLocked && values.indexing_technique !== indexingTechnique) {
        body.indexing_technique = values.indexing_technique
      }
      if (values.indexing_technique === 'high_quality') {
        body.embedding_model = embedding.embedding_model ?? null
        body.embedding_model_provider = embedding.embedding_model_provider ?? null
      }
      return patchDataset(workspaceId!, datasetId, body)
    },
    onSuccess: () => {
      message.success(t('dataset.settings.saved'))
      void queryClient.invalidateQueries({ queryKey: ['dataset-detail', workspaceId, datasetId] })
    },
    onError: (err: Error) => message.error(err.message),
  })

  const loading = detailQ.isLoading || ruleQ.isLoading

  return (
    <Spin spinning={loading}>
      <div className="minerva-dataset-settings-page minerva-scrollbar-thin">
        <Form form={form} layout="vertical" onFinish={(values) => saveM.mutate(values)}>
          <Typography.Title level={5} className="minerva-dataset-settings-page__section-title">
            {t('dataset.settings.basicSection')}
          </Typography.Title>
          <Form.Item
            name="name"
            label={t('dataset.create.field.name')}
            rules={[{ required: true, message: t('dataset.create.field.nameRequired') }]}
          >
            <Input allowClear placeholder={t('dataset.create.field.namePh')} />
          </Form.Item>
          <Form.Item name="description" label={t('dataset.create.field.description')}>
            <Input.TextArea allowClear rows={2} />
          </Form.Item>

          <div className="minerva-dataset-settings-page__section-divider" role="separator" />

          <Form.Item name="doc_form" hidden>
            <Input />
          </Form.Item>

          <SegmentationSettingsPanel
            form={form as unknown as FormInstance<ChunkingFormValues>}
            docFormLocked
            hidePreviewActions
            onPreview={() => undefined}
            onReset={() => undefined}
          />
          <div className="minerva-dataset-settings-page__section-divider" role="separator" />

          <IndexingMethodPanel
            form={form as unknown as FormInstance<IndexingFormValues>}
            embeddingOptions={embeddingOptions}
            modelsLoading={modelsQ.isLoading}
            economyDisabled={economyDisabled}
            indexingLocked={indexingLocked}
            hideEconomyDisabledHint
          />

          <div className="minerva-dataset-settings-page__section-divider" role="separator" />

          <RetrievalSettingsPanel
            form={form as unknown as FormInstance<RetrievalFormValues>}
            rerankOptions={rerankOptions}
            modelsLoading={modelsQ.isLoading}
            vectorSearchDisabled={economyMode}
          />

          <div className="minerva-dataset-settings-page__actions">
            <Button type="primary" htmlType="submit" loading={saveM.isPending}>
              {t('common.save')}
            </Button>
          </div>
        </Form>
      </div>
    </Spin>
  )
}
