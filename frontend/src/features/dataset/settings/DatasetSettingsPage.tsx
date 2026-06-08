/** Knowledge base settings page. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Form, Input, InputNumber, Select, Switch, Typography, message } from 'antd'
import { useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { listModelProviders } from '@/api/modelProviders'
import { useAuth } from '@/app/AuthContext'
import { getDataset } from '@/features/dataset/api/documents'
import { getDatasetProcessRule } from '@/features/dataset/api/datasets'
import { patchDataset } from '@/features/dataset/api/hitTesting'
import {
  buildProcessRule,
  parseProcessRuleToForm,
  type ChunkingFormValues,
} from '@/features/dataset/shared/chunkingForm'

type SettingsFormValues = ChunkingFormValues & {
  name: string
  description?: string
  search_method: 'semantic_search' | 'full_text_search' | 'hybrid_search'
  top_k: number
  score_threshold_enabled: boolean
  score_threshold: number
  reranking_enable: boolean
  reranking_model_key?: string
}

const DOC_FORM_LABEL: Record<string, string> = {
  text_model: 'dataset.create.docForm.text',
  hierarchical_model: 'dataset.create.docForm.hierarchical',
  qa_model: 'dataset.create.docForm.qa',
}

/** Split ``provider::model`` key into retrieval payload fields. */
function parseRerankKey(key?: string) {
  if (!key?.includes('::')) {
    return { reranking_provider_name: '', reranking_model_name: '' }
  }
  const [provider, model] = key.split('::', 2)
  return { reranking_provider_name: provider, reranking_model_name: model }
}

/** Build rerank model select value from retrieval payload. */
function toRerankKey(retrieval: Record<string, unknown> | undefined) {
  const cfg = (retrieval?.reranking_model ?? {}) as Record<string, unknown>
  const provider = String(cfg.reranking_provider_name ?? '').trim()
  const model = String(cfg.reranking_model_name ?? '').trim()
  return provider && model ? `${provider}::${model}` : undefined
}

/** Settings tab for retrieval and chunking configuration. */
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

  const chunkStructure = detailQ.data?.chunk_structure ?? 'text_model'
  const isHierarchical = chunkStructure === 'hierarchical_model'

  const rerankOptions = useMemo(() => {
    return (modelsQ.data ?? [])
      .filter((row) => row.enabled && row.tags.includes('RERANKING'))
      .map((row) => ({
        value: `${row.provider_name}::${row.model_name}`,
        label: `${row.provider_name} / ${row.model_name}`,
      }))
  }, [modelsQ.data])

  const rerankingEnabled = Form.useWatch('reranking_enable', form)

  useEffect(() => {
    const row = detailQ.data
    if (!row) return
    const retrieval = (row.retrieval_model ?? {}) as Record<string, unknown>
    const savedRule = (row.process_rule ?? ruleQ.data?.process_rule ?? {}) as Record<string, unknown>
    form.setFieldsValue({
      name: row.name,
      description: row.description ?? undefined,
      doc_form: (row.chunk_structure as SettingsFormValues['doc_form']) ?? 'text_model',
      ...parseProcessRuleToForm(savedRule),
      search_method: (retrieval.search_method as SettingsFormValues['search_method']) ?? 'semantic_search',
      top_k: Number(retrieval.top_k ?? 3),
      score_threshold_enabled: Boolean(retrieval.score_threshold_enabled),
      score_threshold: Number(retrieval.score_threshold ?? 0.5),
      reranking_enable: Boolean(retrieval.reranking_enable),
      reranking_model_key: toRerankKey(retrieval),
    })
  }, [detailQ.data, form, ruleQ.data?.process_rule])

  const saveM = useMutation({
    mutationFn: (values: SettingsFormValues) => {
      const defaultRule = (detailQ.data?.process_rule ?? ruleQ.data?.process_rule ?? {}) as Record<
        string,
        unknown
      >
      const processRule = buildProcessRule(
        { ...values, doc_form: (chunkStructure as ChunkingFormValues['doc_form']) ?? 'text_model' },
        defaultRule,
      )
      const rerank = parseRerankKey(values.reranking_model_key)
      return patchDataset(workspaceId!, datasetId, {
        name: values.name.trim(),
        description: values.description?.trim() || null,
        process_rule: processRule,
        retrieval_model: {
          search_method: values.search_method,
          top_k: values.top_k,
          score_threshold_enabled: values.score_threshold_enabled,
          score_threshold: values.score_threshold,
          reranking_enable: values.reranking_enable,
          reranking_mode: 'reranking_model',
          reranking_model: rerank,
        },
      })
    },
    onSuccess: () => {
      message.success(t('dataset.settings.saved'))
      void queryClient.invalidateQueries({ queryKey: ['dataset-detail', workspaceId, datasetId] })
    },
    onError: (err: Error) => message.error(err.message),
  })

  return (
    <Card title={t('dataset.tabs.settings')}>
      <Form form={form} layout="vertical" onFinish={(values) => saveM.mutate(values)}>
        <Form.Item
          name="name"
          label={t('dataset.create.field.name')}
          rules={[{ required: true, message: t('dataset.create.field.nameRequired') }]}
        >
          <Input allowClear />
        </Form.Item>
        <Form.Item name="description" label={t('dataset.create.field.description')}>
          <Input.TextArea allowClear rows={2} />
        </Form.Item>
        <Form.Item label={t('dataset.create.field.docForm')}>
          <Typography.Text>
            {t(DOC_FORM_LABEL[chunkStructure] ?? 'dataset.create.docForm.text')}
          </Typography.Text>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            {t('dataset.settings.docFormHint')}
          </Typography.Paragraph>
        </Form.Item>
        <Form.Item name="search_method" label={t('dataset.settings.searchMethod')}>
          <Select
            allowClear={false}
            options={[
              { value: 'semantic_search', label: t('dataset.settings.semantic') },
              { value: 'full_text_search', label: t('dataset.settings.fullText') },
              { value: 'hybrid_search', label: t('dataset.settings.hybrid') },
            ]}
          />
        </Form.Item>
        <Form.Item name="top_k" label={t('dataset.settings.topK')}>
          <InputNumber min={1} max={20} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="score_threshold_enabled" label={t('dataset.settings.thresholdEnabled')} valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item name="score_threshold" label={t('dataset.settings.threshold')}>
          <InputNumber min={0} max={1} step={0.05} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="reranking_enable" label={t('dataset.settings.rerankEnabled')} valuePropName="checked">
          <Switch />
        </Form.Item>
        {rerankingEnabled ? (
          <Form.Item
            name="reranking_model_key"
            label={t('dataset.settings.rerankModel')}
            rules={[{ required: true, message: t('dataset.settings.rerankModelRequired') }]}
          >
            <Select allowClear options={rerankOptions} loading={modelsQ.isLoading} />
          </Form.Item>
        ) : null}
        <Typography.Title level={5} style={{ marginTop: 8 }}>
          {t('dataset.settings.chunkingSection')}
        </Typography.Title>
        <Form.Item name="delimiter" label={t('dataset.create.field.delimiter')}>
          <Input allowClear placeholder="\\n\\n" />
        </Form.Item>
        <Form.Item name="max_length" label={t('dataset.create.field.maxLength')}>
          <InputNumber min={100} max={8192} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="chunk_overlap" label={t('dataset.create.field.overlap')}>
          <InputNumber min={0} max={500} style={{ width: '100%' }} />
        </Form.Item>
        {isHierarchical ? (
          <>
            <Typography.Text strong>{t('dataset.settings.parentChunk')}</Typography.Text>
            <Form.Item name="parent_delimiter" label={t('dataset.create.field.delimiter')}>
              <Input allowClear placeholder="\\n\\n" />
            </Form.Item>
            <Form.Item name="parent_max_length" label={t('dataset.create.field.maxLength')}>
              <InputNumber min={200} max={8192} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="parent_chunk_overlap" label={t('dataset.create.field.overlap')}>
              <InputNumber min={0} max={500} style={{ width: '100%' }} />
            </Form.Item>
            <Typography.Text strong>{t('dataset.settings.subChunk')}</Typography.Text>
            <Form.Item name="sub_delimiter" label={t('dataset.create.field.delimiter')}>
              <Input allowClear placeholder="\\n" />
            </Form.Item>
            <Form.Item name="sub_max_length" label={t('dataset.create.field.maxLength')}>
              <InputNumber min={100} max={4096} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="sub_chunk_overlap" label={t('dataset.create.field.overlap')}>
              <InputNumber min={0} max={500} style={{ width: '100%' }} />
            </Form.Item>
          </>
        ) : null}
        <Form.Item name="remove_extra_spaces" label={t('dataset.create.field.removeSpaces')} valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item name="remove_urls_emails" label={t('dataset.create.field.removeUrls')} valuePropName="checked">
          <Switch />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={saveM.isPending}>
          {t('common.save')}
        </Button>
      </Form>
    </Card>
  )
}
