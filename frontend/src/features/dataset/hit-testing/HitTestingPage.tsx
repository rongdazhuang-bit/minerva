/** Hit testing page for one knowledge base (Dify-style split layout). */

import { AimOutlined, ClockCircleOutlined, PlayCircleOutlined, SettingOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Drawer, Form, Input, Space, Typography, message } from 'antd'
import type { FormInstance } from 'antd'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { listModelProviders } from '@/api/modelProviders'
import { useAuth } from '@/app/AuthContext'
import { DEFAULT_PAGE_SIZE } from '@/constants/pagination'
import { getDataset } from '@/features/dataset/api/documents'
import {
  listDatasetQueries,
  patchDataset,
  runHitTesting,
  type HitTestingRecord,
} from '@/features/dataset/api/hitTesting'
import { RetrievalSettingsPanel } from '@/features/dataset/create/RetrievalSettingsPanel'
import {
  buildRetrievalModel,
  parseRetrievalModelToForm,
  type RetrievalFormValues,
  type SearchMethod,
} from '@/features/dataset/shared/retrievalForm'
import './HitTestingPage.css'

const QUERY_MAX_LENGTH = 200

/** Map stored retrieval search_method to i18n label key suffix. */
function retrievalMethodLabelKey(method: string | undefined): string {
  const map: Record<string, string> = {
    semantic_search: 'dataset.settings.semantic',
    full_text_search: 'dataset.settings.fullText',
    hybrid_search: 'dataset.settings.hybrid',
  }
  return map[method ?? 'semantic_search'] ?? 'dataset.settings.semantic'
}

/** Render segment body with optional child chunk and Q&A answer. */
function SegmentBody({
  segment,
  t,
}: {
  segment: HitTestingRecord['segment']
  t: (key: string) => string
}) {
  return (
    <>
      <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
        {segment.content}
      </Typography.Paragraph>
      {segment.child_content ? (
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
          {t('dataset.hitTesting.childMatch')}: {segment.child_content}
        </Typography.Paragraph>
      ) : null}
      {segment.answer ? (
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
          {t('dataset.segments.column.answer')}: {segment.answer}
        </Typography.Paragraph>
      ) : null}
    </>
  )
}

/** Recall test page: query input + history on the left, results on the right. */
export function HitTestingPage() {
  const { t } = useTranslation()
  const { workspaceId } = useAuth()
  const { datasetId = '' } = useParams()
  const queryClient = useQueryClient()
  const [queryForm] = Form.useForm<{ query: string }>()
  const [retrievalForm] = Form.useForm<RetrievalFormValues>()
  const [records, setRecords] = useState<HitTestingRecord[]>([])
  const [activeQuery, setActiveQuery] = useState<string | null>(null)
  const [retrievalDrawerOpen, setRetrievalDrawerOpen] = useState(false)

  const detailQ = useQuery({
    queryKey: ['dataset-detail', workspaceId, datasetId],
    queryFn: () => getDataset(workspaceId!, datasetId),
    enabled: Boolean(workspaceId && datasetId),
  })

  const modelsQ = useQuery({
    queryKey: ['model-providers', workspaceId],
    queryFn: () => listModelProviders(workspaceId!),
    enabled: Boolean(workspaceId),
  })

  const historyQ = useQuery({
    queryKey: ['dataset-queries', workspaceId, datasetId],
    queryFn: () => listDatasetQueries(workspaceId!, datasetId, { page: 1, page_size: DEFAULT_PAGE_SIZE }),
    enabled: Boolean(workspaceId && datasetId),
  })

  const row = detailQ.data
  const economyMode = row?.indexing_technique === 'economy'
  const queryDraft = Form.useWatch('query', queryForm) ?? ''
  const searchMethod = Form.useWatch('search_method', retrievalForm) as SearchMethod | undefined
  const retrievalLabel = t(retrievalMethodLabelKey(searchMethod ?? row?.retrieval_model?.search_method as string))

  const rerankOptions = useMemo(() => {
    return (modelsQ.data ?? [])
      .filter((item) => item.enabled && item.tags.includes('RERANKING'))
      .map((item) => ({
        value: `${item.provider_name}::${item.model_name}`,
        label: `${item.provider_name} / ${item.model_name}`,
      }))
  }, [modelsQ.data])

  useEffect(() => {
    if (!row) return
    retrievalForm.setFieldsValue(parseRetrievalModelToForm(row.retrieval_model))
  }, [retrievalForm, row])

  useEffect(() => {
    if (economyMode && (searchMethod === 'semantic_search' || searchMethod === 'hybrid_search')) {
      retrievalForm.setFieldValue('search_method', 'full_text_search')
    }
  }, [economyMode, retrievalForm, searchMethod])

  const testM = useMutation({
    mutationFn: (query: string) => {
      const retrievalValues = retrievalForm.getFieldsValue(true) as RetrievalFormValues
      return runHitTesting(workspaceId!, datasetId, {
        query,
        retrieval_model: buildRetrievalModel(retrievalValues, (row?.retrieval_model ?? {}) as Record<string, unknown>),
      })
    },
    onSuccess: (data, query) => {
      setRecords(data.records)
      setActiveQuery(query)
      void historyQ.refetch()
    },
    onError: (err: Error) => message.error(err.message),
  })

  const saveRetrievalM = useMutation({
    mutationFn: (values: RetrievalFormValues) =>
      patchDataset(workspaceId!, datasetId, {
        retrieval_model: buildRetrievalModel(values, (row?.retrieval_model ?? {}) as Record<string, unknown>),
      }),
    onSuccess: () => {
      message.success(t('dataset.settings.saved'))
      setRetrievalDrawerOpen(false)
      void queryClient.invalidateQueries({ queryKey: ['dataset-detail', workspaceId, datasetId] })
    },
    onError: (err: Error) => message.error(err.message),
  })

  /** Submit trimmed query from form or history replay. */
  const runQuery = useCallback(
    (raw: string) => {
      const query = raw.trim()
      if (!query) return
      queryForm.setFieldsValue({ query })
      testM.mutate(query)
    },
    [queryForm, testM],
  )

  /** Revert drawer edits to persisted dataset retrieval settings. */
  const closeRetrievalDrawer = useCallback(() => {
    if (row) {
      retrievalForm.setFieldsValue(parseRetrievalModelToForm(row.retrieval_model))
    }
    setRetrievalDrawerOpen(false)
  }, [retrievalForm, row])

  const historyItems = useMemo(() => historyQ.data?.items ?? [], [historyQ.data?.items])
  const queryLength = String(queryDraft).length

  return (
    <div className="minerva-dataset-hit-testing">
      <div className="minerva-dataset-hit-testing__pane minerva-dataset-hit-testing__pane--left">
        <div className="minerva-dataset-hit-testing__left-top">
          <div className="minerva-dataset-hit-testing__source-box">
          <div className="minerva-dataset-hit-testing__source-header">
            <Typography.Text className="minerva-dataset-hit-testing__source-label">
              {t('dataset.hitTesting.sourceText')}
            </Typography.Text>
            <button
              type="button"
              className="minerva-dataset-hit-testing__retrieval-trigger"
              onClick={() => setRetrievalDrawerOpen(true)}
            >
              <span className="minerva-dataset-hit-testing__retrieval-trigger-label">{retrievalLabel}</span>
              <span className="minerva-dataset-hit-testing__retrieval-trigger-divider" aria-hidden />
              <SettingOutlined className="minerva-dataset-hit-testing__retrieval-trigger-icon" />
            </button>
          </div>

          <Form form={queryForm} layout="vertical" onFinish={(values) => runQuery(values.query)}>
            <div className="minerva-dataset-hit-testing__source-input">
              <Form.Item
                name="query"
                rules={[{ required: true, message: t('dataset.hitTesting.queryRequired') }]}
                style={{ marginBottom: 0 }}
              >
                <Input.TextArea
                  allowClear
                  className="minerva-dataset-hit-testing__source-textarea"
                  rows={5}
                  maxLength={QUERY_MAX_LENGTH}
                  placeholder={t('dataset.hitTesting.queryPh')}
                />
              </Form.Item>
            </div>
            <div className="minerva-dataset-hit-testing__source-footer">
              <Typography.Text type="secondary" className="minerva-dataset-hit-testing__source-count">
                {queryLength}/{QUERY_MAX_LENGTH}
              </Typography.Text>
              <Button
                type="primary"
                htmlType="submit"
                loading={testM.isPending}
                icon={<PlayCircleOutlined />}
              >
                {t('dataset.hitTesting.run')}
              </Button>
            </div>
          </Form>
        </div>
        </div>

        <div className="minerva-dataset-hit-testing__section-divider" role="separator" />

        <div className="minerva-dataset-hit-testing__history-panel">
          <Typography.Title level={5} className="minerva-dataset-hit-testing__history-title">
            {t('dataset.hitTesting.history')}
          </Typography.Title>

          <div className="minerva-dataset-hit-testing__history-scroll minerva-scrollbar-styled">
            {historyQ.isLoading ? (
              <div className="minerva-dataset-hit-testing__empty minerva-dataset-hit-testing__empty--history">
                <Typography.Text type="secondary">{t('common.loading')}</Typography.Text>
              </div>
            ) : historyItems.length === 0 ? (
              <div className="minerva-dataset-hit-testing__empty minerva-dataset-hit-testing__empty--history">
                <ClockCircleOutlined className="minerva-dataset-hit-testing__empty-icon" style={{ fontSize: 32 }} />
                <Typography.Text type="secondary">{t('dataset.hitTesting.recentEmpty')}</Typography.Text>
              </div>
            ) : (
              historyItems.map((item) => (
                <div
                  key={item.id}
                  className="minerva-dataset-hit-testing__history-item"
                  role="button"
                  tabIndex={0}
                  onClick={() => runQuery(item.content)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') runQuery(item.content)
                  }}
                >
                  <Typography.Paragraph className="minerva-dataset-hit-testing__history-content">
                    {item.content}
                  </Typography.Paragraph>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {item.create_at ? new Date(item.create_at).toLocaleString() : '—'}
                  </Typography.Text>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="minerva-dataset-hit-testing__pane minerva-dataset-hit-testing__pane--right">
        <div className="minerva-dataset-hit-testing__results-scroll minerva-scrollbar-styled">
          {records.length === 0 ? (
            <div className="minerva-dataset-hit-testing__empty">
              <AimOutlined className="minerva-dataset-hit-testing__empty-icon" />
              <Typography.Text type="secondary">{t('dataset.hitTesting.resultsPlaceholder')}</Typography.Text>
            </div>
          ) : (
            <>
              {activeQuery ? (
                <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
                  {t('dataset.hitTesting.resultsFor', { query: activeQuery })}
                </Typography.Paragraph>
              ) : null}
              {records.map((item, index) => (
                <div key={`${item.segment.id}-${index}`} className="minerva-dataset-hit-testing__result-item">
                  <div className="minerva-dataset-hit-testing__result-meta">
                    <Typography.Text strong>
                      #{index + 1} · {item.document.name}
                    </Typography.Text>
                    <span className="minerva-dataset-hit-testing__result-score">{item.score.toFixed(4)}</span>
                  </div>
                  <SegmentBody segment={item.segment} t={t} />
                </div>
              ))}
            </>
          )}
        </div>
      </div>

      <Drawer
        title={t('dataset.create.retrieval.title')}
        placement="right"
        width={480}
        open={retrievalDrawerOpen}
        destroyOnClose={false}
        onClose={closeRetrievalDrawer}
        className="minerva-dataset-hit-testing__retrieval-drawer"
        extra={
          <Space size={8}>
            <Button onClick={closeRetrievalDrawer}>{t('common.cancel')}</Button>
            <Button
              type="primary"
              loading={saveRetrievalM.isPending}
              onClick={() => {
                void retrievalForm.validateFields().then((values) => saveRetrievalM.mutate(values))
              }}
            >
              {t('common.save')}
            </Button>
          </Space>
        }
      >
        <Form form={retrievalForm} layout="vertical" component={false}>
          <RetrievalSettingsPanel
            form={retrievalForm as unknown as FormInstance<RetrievalFormValues>}
            rerankOptions={rerankOptions}
            modelsLoading={modelsQ.isLoading}
            vectorSearchDisabled={economyMode}
            hideHeader
          />
        </Form>
      </Drawer>
    </div>
  )
}
